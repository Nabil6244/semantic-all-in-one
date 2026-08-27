"""Music Director — sections + intensity envelope + narration ducking on manual track.

Uses the user-selected background track only (no auto library).
Ducking is deterministic volume automation (stable across ffmpeg builds).
"""

from __future__ import annotations

import math
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from providers import hidden_subprocess

from .schema import EditorialPlan, HOOK_WINDOW_S

MusicSectionRole = str  # intro|build|climax|reflection|outro

_SECTION_BASE_GAIN = {
    "intro": 0.16,
    "build": 0.14,
    "climax": 0.12,
    "reflection": 0.10,
    "outro": 0.11,
}

_ROLE_GAIN = {
    "lift": 1.25,
    "hold": 1.0,
    "drop": 0.55,
    "none": 0.0,
}

_DUCK_FLOOR = 0.35   # fraction of base when narration is loud
_DUCK_CEILING = 1.15  # recovery in quiet gaps
_MAX_MUSIC = 0.22
_MIN_MUSIC = 0.04


@dataclass
class FilmSection:
    id: str
    start: float
    end: float
    role: MusicSectionRole

    def to_dict(self) -> dict:
        return {"id": self.id, "start": self.start, "end": self.end, "role": self.role}

    @classmethod
    def from_dict(cls, data: dict) -> "FilmSection":
        return cls(
            id=str(data.get("id") or ""),
            start=float(data.get("start") or 0.0),
            end=float(data.get("end") or 0.0),
            role=str(data.get("role") or "build"),
        )


@dataclass
class MusicCue:
    start: float
    end: float
    mood: str
    intensity: float
    duck_db: float = -6.0
    volume: float = 0.12

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "mood": self.mood,
            "intensity": self.intensity,
            "duck_db": self.duck_db,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MusicCue":
        return cls(
            start=float(data.get("start") or 0.0),
            end=float(data.get("end") or 0.0),
            mood=str(data.get("mood") or "hold"),
            intensity=float(data.get("intensity") or 0.5),
            duck_db=float(data.get("duck_db") or -6.0),
            volume=float(data.get("volume") or 0.12),
        )


@dataclass
class MusicPlan:
    enabled: bool = False
    source: str = "none"  # manual|none
    path: Optional[str] = None
    sections: List[FilmSection] = field(default_factory=list)
    cues: List[MusicCue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "source": self.source,
            "path": self.path,
            "sections": [s.to_dict() for s in self.sections],
            "cues": [c.to_dict() for c in self.cues],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MusicPlan":
        return cls(
            enabled=bool(data.get("enabled")),
            source=str(data.get("source") or "none"),
            path=data.get("path"),
            sections=[FilmSection.from_dict(s) for s in (data.get("sections") or []) if isinstance(s, dict)],
            cues=[MusicCue.from_dict(c) for c in (data.get("cues") or []) if isinstance(c, dict)],
        )


def assign_film_sections(plan: EditorialPlan) -> List[FilmSection]:
    """Partition the timeline into intro/build/climax/reflection/outro."""
    audio_end = float(plan.audio_end or 0.0)
    if audio_end <= 0 and plan.scenes:
        audio_end = float(plan.scenes[-1].end)
    if audio_end <= 0:
        return []

    # Fixed structural anchors by fraction of total runtime.
    bounds = [
        ("intro", 0.0, min(HOOK_WINDOW_S, audio_end * 0.12)),
        ("build", 0.0, 0.0),  # filled below
        ("climax", 0.0, 0.0),
        ("reflection", 0.0, 0.0),
        ("outro", 0.0, 0.0),
    ]
    intro_end = min(HOOK_WINDOW_S, max(audio_end * 0.08, 8.0), audio_end * 0.2)
    outro_start = max(intro_end, audio_end * 0.88)
    mid = audio_end * 0.5
    # Climax window around highest-attention cluster in middle 40–75%.
    peak_start = audio_end * 0.4
    peak_end = audio_end * 0.72
    if plan.scenes:
        mid_scenes = [s for s in plan.scenes if peak_start <= s.start <= peak_end]
        if mid_scenes:
            best = max(mid_scenes, key=lambda s: s.attention_score)
            peak_start = max(intro_end, best.start - best.duration)
            peak_end = min(outro_start, best.end + best.duration * 2)

    build_end = peak_start
    reflection_start = peak_end

    sections = [
        FilmSection("intro", 0.0, intro_end, "intro"),
        FilmSection("build", intro_end, build_end, "build"),
        FilmSection("climax", peak_start, peak_end, "climax"),
        FilmSection("reflection", reflection_start, outro_start, "reflection"),
        FilmSection("outro", outro_start, audio_end, "outro"),
    ]
    # Drop zero-length
    return [s for s in sections if s.end > s.start + 0.05]


def _section_role_at(sections: Sequence[FilmSection], t: float) -> str:
    for sec in sections:
        if sec.start <= t < sec.end:
            return sec.role
    return "build"


def _narration_rms_windows(narration_path: Path, *, window_s: float = 0.5) -> List[Tuple[float, float, float]]:
    """Return [(start, end, rms)] for a WAV narration. Empty if unreadable."""
    path = Path(narration_path)
    if path.suffix.lower() != ".wav" or not path.is_file():
        return []
    try:
        with wave.open(str(path), "rb") as wf:
            sr = int(wf.getframerate() or 0)
            ch = int(wf.getnchannels() or 1)
            sw = int(wf.getsampwidth() or 2)
            nframes = int(wf.getnframes() or 0)
            raw = wf.readframes(nframes)
    except (wave.Error, OSError):
        return []
    if sr <= 0 or not raw:
        return []

    import array

    if sw == 2:
        samples = array.array("h")
        samples.frombytes(raw)
        scale = 32768.0
    elif sw == 1:
        samples = array.array("B")
        samples.frombytes(raw)
        scale = 128.0
    else:
        return []

    if ch > 1:
        mono = []
        for i in range(0, len(samples), ch):
            chunk = samples[i : i + ch]
            if not chunk:
                break
            mono.append(sum(chunk) / len(chunk))
        samples = mono
    else:
        samples = list(samples)

    win = max(1, int(sr * window_s))
    out: List[Tuple[float, float, float]] = []
    for i in range(0, len(samples), win):
        chunk = samples[i : i + win]
        if not chunk:
            break
        acc = sum((s / scale) ** 2 for s in chunk)
        rms = math.sqrt(acc / len(chunk))
        t0 = i / float(sr)
        t1 = (i + len(chunk)) / float(sr)
        out.append((t0, t1, rms))
    return out


def build_music_cues(
    plan: EditorialPlan,
    *,
    sections: Optional[Sequence[FilmSection]] = None,
    narration_path: Optional[Path] = None,
    window_s: float = 0.75,
) -> List[MusicCue]:
    """Build time-varying music volume cues from sections + optional narration RMS."""
    sections = list(sections or assign_film_sections(plan))
    audio_end = float(plan.audio_end or (plan.scenes[-1].end if plan.scenes else 0.0))
    if audio_end <= 0:
        return []

    by_sn = plan.scene_by_number()
    scenes = list(plan.scenes)
    rms_windows = _narration_rms_windows(Path(narration_path), window_s=window_s) if narration_path else []
    if rms_windows:
        peak_rms = max((r for _, _, r in rms_windows), default=0.01) or 0.01
    else:
        peak_rms = 0.01

    cues: List[MusicCue] = []
    t = 0.0
    while t < audio_end - 0.01:
        t1 = min(audio_end, t + window_s)
        role = _section_role_at(sections, t)
        base = _SECTION_BASE_GAIN.get(role, 0.12)

        # Scene music_role at this time
        scene = next((s for s in scenes if s.start <= t < s.end), None)
        role_gain = _ROLE_GAIN.get(getattr(scene, "music_role", "hold") or "hold", 1.0)
        if scene and scene.purpose in ("hook", "reveal"):
            role_gain = max(role_gain, 1.15)
        if scene and scene.allow_silence:
            role_gain *= 0.7

        duck = 1.0
        if rms_windows:
            # Average RMS overlapping this window
            overlap = [r for a, b, r in rms_windows if a < t1 and b > t]
            if overlap:
                mean_rms = sum(overlap) / len(overlap)
                # High narration → duck toward floor
                loudness = min(1.0, mean_rms / (peak_rms * 0.65))
                duck = _DUCK_CEILING - (_DUCK_CEILING - _DUCK_FLOOR) * loudness
        elif scene is not None:
            # Heuristic duck from attention (proxy for dense VO)
            duck = 1.0 - 0.35 * float(scene.attention_score or 0.5)

        vol = base * role_gain * duck
        vol = max(_MIN_MUSIC, min(_MAX_MUSIC, vol))
        if role_gain <= 0:
            vol = 0.0
        cues.append(
            MusicCue(
                start=round(t, 3),
                end=round(t1, 3),
                mood=role,
                intensity=round(vol / _MAX_MUSIC if _MAX_MUSIC else 0.0, 3),
                duck_db=round(20 * math.log10(max(duck, 1e-3)), 2),
                volume=round(vol, 4),
            )
        )
        t = t1
    return cues


def build_music_plan(
    plan: EditorialPlan,
    *,
    music_path: Optional[Path | str] = None,
    narration_path: Optional[Path | str] = None,
) -> MusicPlan:
    path = Path(music_path) if music_path else None
    if path is None or not path.is_file():
        return MusicPlan(enabled=False, source="none", path=None)
    sections = assign_film_sections(plan)
    cues = build_music_cues(
        plan,
        sections=sections,
        narration_path=Path(narration_path) if narration_path else None,
    )
    return MusicPlan(
        enabled=True,
        source="manual",
        path=str(path),
        sections=sections,
        cues=cues,
    )


def render_ducked_music(
    music_path: Path | str,
    cues: Sequence[MusicCue],
    output_path: Path | str,
    *,
    duration: float,
) -> bool:
    """Render a continuous music stem with envelope applied in one ffmpeg pass.

    Uses a piecewise volume expression from cues (merged for stability).
    """
    music_path = Path(music_path)
    output_path = Path(output_path)
    if not music_path.is_file() or duration <= 0 or not cues:
        return False

    # Merge adjacent cues with nearly identical volume to keep the expression small.
    merged: List[MusicCue] = []
    for cue in cues:
        if merged and abs(merged[-1].volume - cue.volume) < 0.008:
            merged[-1] = MusicCue(
                start=merged[-1].start,
                end=cue.end,
                mood=merged[-1].mood,
                intensity=merged[-1].intensity,
                duck_db=merged[-1].duck_db,
                volume=merged[-1].volume,
            )
        else:
            merged.append(
                MusicCue(
                    start=cue.start,
                    end=cue.end,
                    mood=cue.mood,
                    intensity=cue.intensity,
                    duck_db=cue.duck_db,
                    volume=cue.volume,
                )
            )

    # Cap expression complexity — subsample if still huge.
    if len(merged) > 120:
        step = max(1, len(merged) // 100)
        compact: List[MusicCue] = []
        for i in range(0, len(merged), step):
            chunk = merged[i : i + step]
            compact.append(
                MusicCue(
                    start=chunk[0].start,
                    end=chunk[-1].end,
                    mood=chunk[0].mood,
                    intensity=chunk[0].intensity,
                    duck_db=chunk[0].duck_db,
                    volume=sum(c.volume for c in chunk) / len(chunk),
                )
            )
        merged = compact

    # Nested if(between(t,a,b),vol,...) expression — evaluated per-frame.
    expr = f"{merged[-1].volume:.5f}"
    for cue in reversed(merged[:-1]):
        expr = (
            f"if(between(t\\,{cue.start:.3f}\\,{cue.end:.3f})\\,"
            f"{cue.volume:.5f}\\,{expr})"
        )
    af = f"volume='{expr}':eval=frame"

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(music_path),
        "-t", f"{float(duration):.3f}",
        "-af", af,
        "-ac", "2",
        "-ar", "44100",
        str(output_path),
    ]
    result = hidden_subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and output_path.is_file():
        return True
    # Fallback: flat safe volume if expression fails on older ffmpeg
    cmd_flat = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(music_path),
        "-t", f"{float(duration):.3f}",
        "-af", "volume=0.12",
        "-ac", "2",
        "-ar", "44100",
        str(output_path),
    ]
    result = hidden_subprocess.run(cmd_flat, capture_output=True, text=True)
    return result.returncode == 0 and output_path.is_file()


def flat_bg_volume_fallback() -> float:
    """Legacy flat bed level when no EditorialPlan music data exists."""
    return 0.15
