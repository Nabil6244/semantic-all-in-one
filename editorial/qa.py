"""Editorial QA — post-render scorecard. WARN by default; never blocks render."""

from __future__ import annotations

import json
import math
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .schema import HOOK_WINDOW_S, EditorialPlan


@dataclass
class QAIssue:
    scene_number: str
    timestamp: float
    severity: str  # PASS|WARN|FAIL (issues use WARN/FAIL)
    category: str
    message: str
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "scene_number": self.scene_number,
            "timestamp": round(self.timestamp, 2),
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "recommendation": self.recommendation,
        }

    def format_line(self) -> str:
        ts = self.timestamp
        return (
            f"Scene {self.scene_number}\n"
            f"00:{ts:06.1f}\n"
            f"{self.severity}\n"
            f"{self.message}"
            + (f"\n→ {self.recommendation}" if self.recommendation else "")
        )


@dataclass
class EditorialQAReport:
    score: float = 100.0
    verdict: str = "PASS"  # PASS|WARN|FAIL
    issues: List[QAIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "verdict": self.verdict,
            "issues": [i.to_dict() for i in self.issues],
            "metrics": self.metrics,
        }

    def format_summary(self) -> str:
        lines = [
            f"Editorial QA: {self.verdict} (score {self.score:.0f}/100)",
            "",
        ]
        if not self.issues:
            lines.append("No issues detected.")
        else:
            for issue in self.issues:
                lines.append(issue.format_line())
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _wav_peak_and_rms(path: Path) -> tuple[float, float]:
    try:
        with wave.open(str(path), "rb") as wf:
            sw = wf.getsampwidth()
            ch = wf.getnchannels()
            n = wf.getnframes()
            raw = wf.readframes(n)
            sr = wf.getframerate()
    except (wave.Error, OSError):
        return 0.0, 0.0
    if not raw or sw != 2:
        return 0.0, 0.0
    import array

    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return 0.0, 0.0
    peak = max(abs(s) for s in samples) / 32768.0
    acc = sum((s / 32768.0) ** 2 for s in samples)
    rms = math.sqrt(acc / len(samples))
    return peak, rms


def _probe_media_duration(path: Path) -> float:
    from providers import hidden_subprocess
    import shutil

    if not path.is_file():
        return 0.0
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wf:
                return wf.getnframes() / float(wf.getframerate() or 1)
        except (wave.Error, OSError):
            return 0.0
    if shutil.which("ffprobe") is None:
        return 0.0
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = hidden_subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float((proc.stdout or "").strip() or 0.0)
    except Exception:
        return 0.0


def _detect_black_frozen(
    video_path: Path,
    *,
    sample_times: Sequence[float],
) -> List[QAIssue]:
    """Lightweight black/frozen checks via ffmpeg blackdetect / freezedetect when available."""
    from providers import hidden_subprocess
    import shutil

    issues: List[QAIssue] = []
    if not video_path.is_file() or shutil.which("ffmpeg") is None:
        return issues
    # Sample first 60s + middle for practicality
    duration = _probe_media_duration(video_path)
    analyze_t = min(60.0, max(10.0, duration * 0.15)) if duration else 30.0
    cmd = [
        "ffmpeg", "-hide_banner",
        "-t", f"{analyze_t:.1f}",
        "-i", str(video_path),
        "-vf", "blackdetect=d=0.4:pix_th=0.10,freezedetect=n=0.003:d=0.6",
        "-an", "-f", "null", "-",
    ]
    try:
        proc = hidden_subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        err = (proc.stderr or "") + (proc.stdout or "")
    except Exception:
        return issues

    for line in err.splitlines():
        if "black_start:" in line:
            try:
                # black_start:1.2 black_end:1.8 black_duration:0.6
                parts = {p.split(":")[0].strip(): float(p.split(":")[1]) for p in line.split() if ":" in p}
                start = parts.get("black_start", 0.0)
                issues.append(
                    QAIssue(
                        scene_number="?",
                        timestamp=start,
                        severity="WARN",
                        category="black_frozen",
                        message=f"Black frame segment near {start:.1f}s",
                        recommendation="Check asset / transition at this timestamp.",
                    )
                )
            except (ValueError, IndexError):
                pass
        if "freeze_start:" in line:
            try:
                parts = {p.split(":")[0].strip(): float(p.split(":")[1]) for p in line.split() if ":" in p}
                start = parts.get("freeze_start", 0.0)
                issues.append(
                    QAIssue(
                        scene_number="?",
                        timestamp=start,
                        severity="WARN",
                        category="black_frozen",
                        message=f"Frozen frame segment near {start:.1f}s",
                        recommendation="Verify still assets aren't held too long without motion.",
                    )
                )
            except (ValueError, IndexError):
                pass
    return issues[:8]  # cap noise


def run_editorial_qa(
    plan: EditorialPlan,
    *,
    output_video: Optional[Path] = None,
    narration_path: Optional[Path] = None,
    ambience_beds: Optional[Sequence[dict]] = None,
    music_cues: Optional[Sequence[dict]] = None,
    images_dir: Optional[Path] = None,
    transition_map: Optional[dict] = None,
) -> EditorialQAReport:
    issues: List[QAIssue] = []
    metrics: Dict[str, Any] = {}
    score = 100.0

    scenes = plan.scenes
    metrics["scene_count"] = len(scenes)
    metrics["audio_end"] = plan.audio_end

    # 1. Timeline integrity
    for i, scene in enumerate(scenes):
        if scene.end <= scene.start:
            issues.append(
                QAIssue(
                    scene.scene_number,
                    scene.start,
                    "FAIL",
                    "timeline",
                    f"Invalid window {scene.start}–{scene.end}",
                    "Rebuild EditorialPlan after alignment.",
                )
            )
            score -= 8
        if i > 0 and abs(scene.start - scenes[i - 1].end) > 0.08:
            issues.append(
                QAIssue(
                    scene.scene_number,
                    scene.start,
                    "WARN",
                    "timeline",
                    f"Gap/overlap vs previous end {scenes[i - 1].end:.2f}",
                    "Confirm display timeline continuity.",
                )
            )
            score -= 2

    # 2. Scene coverage
    if not scenes:
        issues.append(QAIssue("-", 0, "FAIL", "coverage", "No scenes in EditorialPlan"))
        score -= 40

    # 3. Ambience coverage
    beds = list(ambience_beds or [])
    bed_scenes = {str(b.get("scene_number")) for b in beds}
    metrics["ambience_beds"] = len(beds)
    if beds:
        # Cross-cut merge detection: bed spanning past another scene's start
        by_sn = plan.scene_by_number()
        for bed in beds:
            sn = str(bed.get("scene_number") or "")
            scene = by_sn.get(sn)
            if scene is None:
                continue
            b_start = float(bed.get("start") or 0)
            b_end = float(bed.get("end") or 0)
            if b_start < scene.start - 0.05 or b_end > scene.end + 0.05:
                issues.append(
                    QAIssue(
                        sn,
                        b_start,
                        "FAIL",
                        "ambience",
                        "Ambience bed extends outside visual scene window",
                        "Keep one bed per visual scene (no cross-cut merge).",
                    )
                )
                score -= 10
            # Check if bed spans into next scene
            for other in scenes:
                if other.scene_number == sn:
                    continue
                if b_start < other.start < b_end - 0.05:
                    issues.append(
                        QAIssue(
                            sn,
                            other.start,
                            "FAIL",
                            "ambience",
                            f"Ambience crosses into scene {other.scene_number}",
                            "Split ambience at visual cuts.",
                        )
                    )
                    score -= 12
        missing = [s for s in scenes if s.scene_number not in bed_scenes and s.ambience_profile != "none"]
        # Soft: only warn if many missing relative to plan that expected ambience
        if len(missing) > max(3, len(scenes) * 0.15):
            for s in missing[:5]:
                issues.append(
                    QAIssue(
                        s.scene_number,
                        s.start,
                        "WARN",
                        "ambience",
                        "Ambience missing for scene window",
                        "Check SFX catalog / ambience planning.",
                    )
                )
            score -= min(15, len(missing))

    # 4. Audio levels
    if narration_path and Path(narration_path).is_file():
        peak, rms = _wav_peak_and_rms(Path(narration_path))
        metrics["narration_peak"] = round(peak, 3)
        metrics["narration_rms"] = round(rms, 3)
        if peak >= 0.99:
            issues.append(
                QAIssue("-", 0, "WARN", "levels", "Narration near clipping", "Lower input gain slightly.")
            )
            score -= 4

    # 5. Music ducking
    cues = list(music_cues or [])
    metrics["music_cues"] = len(cues)
    if cues:
        vols = [float(c.get("volume") if isinstance(c, dict) else getattr(c, "volume", 0)) for c in cues]
        if vols and max(vols) - min(vols) < 0.01:
            issues.append(
                QAIssue("-", 0, "WARN", "music", "Music envelope is nearly flat", "Enable narration-relative ducking.")
            )
            score -= 3
        else:
            metrics["music_vol_range"] = round(max(vols) - min(vols), 4) if vols else 0

    # 6. Transition density
    tmap = transition_map or plan.transition_style_map()
    n_boundaries = max(0, len(scenes) - 1)
    n_trans = len(tmap)
    metrics["transitions"] = n_trans
    if n_boundaries > 0:
        density = n_trans / n_boundaries
        metrics["transition_density"] = round(density, 3)
        if density > 0.55:
            issues.append(
                QAIssue("-", 0, "WARN", "transitions", f"High transition density ({density:.0%})", "Prefer hard cuts for explanation beats.")
            )
            score -= 5

    # 7. Camera variety
    styles = [s.camera_style for s in scenes]
    metrics["camera_styles"] = {k: styles.count(k) for k in sorted(set(styles))}
    for i, scene in enumerate(scenes):
        window = styles[max(0, i - 2) : i + 3]
        if window.count(scene.camera_style) >= 4:
            issues.append(
                QAIssue(
                    scene.scene_number,
                    scene.start,
                    "WARN",
                    "camera",
                    f"Camera style {scene.camera_style!r} repeated 4 times nearby",
                    "Vary push_in / pull_out / drift / hold.",
                )
            )
            score -= 2
            break

    # 8. Visual repetition
    keys = [s.visual_variety_key for s in scenes if s.visual_variety_key]
    for i in range(1, len(scenes)):
        if scenes[i].visual_variety_key and scenes[i].visual_variety_key == scenes[i - 1].visual_variety_key:
            if scenes[i].asset_type_intent == scenes[i - 1].asset_type_intent:
                issues.append(
                    QAIssue(
                        scenes[i].scene_number,
                        scenes[i].start,
                        "WARN",
                        "repetition",
                        "Neighboring scenes share visual variety key",
                        "Consider alternate framing or asset.",
                    )
                )
                score -= 1
                if sum(1 for x in issues if x.category == "repetition") >= 5:
                    break

    # 9. Hook quality
    hook = [s for s in scenes if s.start < HOOK_WINDOW_S]
    metrics["hook_scenes"] = len(hook)
    if hook:
        avg_att = sum(s.attention_score for s in hook) / len(hook)
        metrics["hook_avg_attention"] = round(avg_att, 3)
        static_hook = sum(1 for s in hook if s.camera_style in ("static", "hold"))
        if avg_att < 0.55:
            issues.append(
                QAIssue(hook[0].scene_number, 0, "WARN", "hook", "Weak first-30s attention", "Open with higher-energy beats.")
            )
            score -= 4
        if static_hook >= max(2, len(hook) - 1) and len(hook) >= 2:
            issues.append(
                QAIssue(hook[0].scene_number, 0, "WARN", "hook", "Mostly static cameras in first 30s", "Prefer push_in / subtle_drift.")
            )
            score -= 3

    # 10. Missing assets
    if images_dir is not None:
        from video_generator import find_image_for_scene, is_video_file

        missing = []
        for scene in scenes:
            try:
                p = find_image_for_scene(Path(images_dir), scene.scene_number)
            except Exception:
                p = None
            if p is None or not Path(p).is_file():
                missing.append(scene)
        metrics["missing_assets"] = len(missing)
        for scene in missing[:8]:
            issues.append(
                QAIssue(
                    scene.scene_number,
                    scene.start,
                    "FAIL",
                    "assets",
                    "Missing/broken scene asset",
                    "Re-run asset resolution or assign local file.",
                )
            )
            score -= 5

    # 11. Black/frozen (practical sample)
    if output_video is not None and Path(output_video).is_file():
        vid_dur = _probe_media_duration(Path(output_video))
        metrics["output_duration"] = round(vid_dur, 2)
        if plan.audio_end > 0 and vid_dur > 0:
            delta = abs(vid_dur - plan.audio_end)
            metrics["duration_delta"] = round(delta, 2)
            if delta > 2.5:
                issues.append(
                    QAIssue("-", 0, "WARN", "timeline", f"Output duration differs from narration by {delta:.1f}s")
                )
                score -= 3
        freeze_issues = _detect_black_frozen(Path(output_video), sample_times=[0, 10, 30])
        for fi in freeze_issues:
            # Map timestamp to scene when possible
            for scene in scenes:
                if scene.start <= fi.timestamp < scene.end:
                    fi.scene_number = scene.scene_number
                    break
            issues.append(fi)
            score -= 2

    score = max(0.0, min(100.0, score))
    fail_count = sum(1 for i in issues if i.severity == "FAIL")
    warn_count = sum(1 for i in issues if i.severity == "WARN")
    if fail_count > 0 and score < 70:
        verdict = "FAIL"
    elif fail_count > 0 or warn_count > 0 or score < 90:
        verdict = "WARN"
    else:
        verdict = "PASS"

    # Critical failures WARN by default (do not elevate to hard block)
    if verdict == "FAIL" and fail_count > 0:
        # Soften: still report FAIL in scorecard but pipeline treats as WARN
        pass

    return EditorialQAReport(score=score, verdict=verdict, issues=issues, metrics=metrics)


def save_editorial_qa(state_dir: Path, report: EditorialQAReport) -> Path:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "editorial_qa.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    summary = state_dir / "editorial_qa.txt"
    summary.write_text(report.format_summary(), encoding="utf-8")
    return path
