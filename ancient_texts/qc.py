"""The evaluator: one report with three lists -- hard failures, soft deviations, items for human review.

It compares a plan and (when there is one) a rendered file with the style's targets, adapting to what the script asks
for, and it never declares a video "equivalent" to the reference: numbers inside their bands say nothing about whether
the story is clear, the interpretation fair or the pictures right -- those are always listed for a person.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import audio as A
from .issues import Issue, split, summary

PROFILE_DIR = Path(__file__).resolve().parent / "reference_profiles"
ALWAYS_REVIEW = (
    ("story_clarity", "Is the story clear and does the conclusion answer the opening question without overstating it?"),
    ("interpretations_fair", "Are interpretations and disputes represented fairly, with the strongest objection heard?"),
    ("visuals_match", "Does each picture show what its narration names (contact sheet: narration -> picture -> reason)?"),
    ("reconstructions_labelled", "Could any AI reconstruction be mistaken for documentary evidence?"),
    ("quotations_fair", "Is every quotation shown in context and attributed to the edition it was checked against?"),
)


def load_profile(profile_id: str) -> dict:
    return json.loads((PROFILE_DIR / f"{profile_id}.json").read_text(encoding="utf-8"))


def measure_shots(video, *, threshold: float = 0.18, merge_below_s: float = 0.6) -> List[float]:
    """Shot lengths from ffmpeg scene detection, merging changes closer than `merge_below_s` (animation, not edits)."""
    ff = A.ffmpeg_bin()
    r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf", f"select='gt(scene,{threshold})',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    cuts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    dur = A._stream_duration(Path(video), "v")
    bounds = [0.0]
    for c in cuts:
        if c - bounds[-1] >= merge_below_s:
            bounds.append(c)
    if dur == dur and dur > bounds[-1]:
        bounds.append(dur)
    return [b - a for a, b in zip(bounds, bounds[1:])]


def evaluate(*, plan_report: Optional[dict] = None, issues: Sequence[Issue] = (), render: Optional[dict] = None,
             profile: Optional[dict] = None, profile_id: str = "", paid_call_attempts: Sequence[str] = (),
             protected_ok: Optional[bool] = None) -> dict:
    """Combine every check into the three lists. `render` is measure_render()'s output (or None when nothing was rendered)."""
    if profile is None:
        profile = load_profile(profile_id) if profile_id else {"style_targets": {}}
    targets = profile["style_targets"]
    out: List[Issue] = list(issues)
    if paid_call_attempts:
        out.append(Issue("paid_or_network_call", "hard", "refused paid/network attempts: " + "; ".join(paid_call_attempts)))
    if protected_ok is False:
        out.append(Issue("protected_file_changed", "hard", "a protected file no longer matches its recorded hash"))
    met, total = 0, 0

    def band(name: str, value: Optional[float], label: str) -> None:
        nonlocal met, total
        t = targets.get(name)
        if t is None or value is None:
            return
        total += 1
        lo, hi = (t.get("band") or [None, None]) if "band" in t else (None, t.get("max"))
        ok = (lo is None or value >= lo) and (hi is None or value <= hi)
        if ok:
            met += 1
        else:
            want = f"{lo}–{hi}" if lo is not None else f"≤{hi}"
            out.append(Issue(f"target_{name}", t.get("class", "soft"), f"{label} {value:g} outside the style target {want}"))

    if plan_report:
        n = max(1, plan_report.get("eligible_visual_scenes") or 0)
        band("card_share", plan_report.get("designed_cards", 0) / n, "card share")
        band("context_shot_share", plan_report.get("context_shots", 0) / n, "context-shot share")
    if render:
        shots = render.get("shots") or []
        if shots:
            band("shot_median_s", round(statistics.median(shots), 2), "median shot length (s)")
            band("longest_shot_s", round(max(shots), 2), "longest shot (s)")
        loud = render.get("loudness")
        if loud:
            band("integrated_lufs", loud["integrated_lufs"], "integrated loudness (LUFS)")
            band("true_peak_dbtp", loud["true_peak_dbtp"], "true peak (dBTP)")
        if render.get("av_duration_delta_s") is not None:
            band("av_duration_delta_s", render["av_duration_delta_s"], "audio/video duration difference (s)")
        if render.get("audio_status") == "failed":
            out.append(Issue("audio_finishing_failed", "hard", render.get("audio_message") or "audio finishing failed"))
    for code, question in ALWAYS_REVIEW:
        out.append(Issue(code, "review", question))
    groups = split(out)
    return {
        "verdict": f"{met} of {total} measured style targets within band; {summary(out)}. "
                   "This is not a judgement that the video is equivalent to the reference.",
        "hard_failures": [i.to_dict() for i in groups["hard"]],
        "soft_deviations": [i.to_dict() for i in groups["soft"]],
        "review_items": [i.to_dict() for i in groups["review"]],
        "targets_met": met,
        "targets_measured": total,
        "plan": plan_report or {},
        "render": render or {},
    }


def measure_render(video) -> dict:
    """What the finished file actually is: shot lengths, loudness, audio/video duration difference."""
    video = Path(video)
    out: dict = {"file": video.name}
    out["shots"] = [round(s, 3) for s in measure_shots(video)]
    if A.has_audio(video):
        out["loudness"] = A.measure(video).__dict__
        va, vv = A._stream_duration(video, "a"), A._stream_duration(video, "v")
        out["av_duration_delta_s"] = round(abs(va - vv), 3) if va == va and vv == vv else None
    else:
        out["loudness"] = None
        out["av_duration_delta_s"] = None
    return out


_SLUG = re.compile(r"/(?:photos?|videos?|illustrations?|vectors?|images?)/([a-z0-9][a-z0-9-]{4,})", re.I)


def _described(rec: dict) -> str:
    """What the provider says the picture is: title/alt/tags/description, plus the words of a descriptive URL slug
    (Pixabay/Pexels URLs read like 'literature-a-book-school-training-3259341'). Bare id URLs add nothing."""
    parts = [str(rec.get(k) or "") for k in ("title", "alt", "tags", "description")]
    for key in ("source_url", "url", "page_url"):
        m = _SLUG.search(str(rec.get(key) or ""))
        if m:
            parts.append(" ".join(w for w in m.group(1).split("-") if not w.isdigit()))
    return " ".join(parts).lower().strip()


def check_acquired_assets(images_dir, metas: Sequence, avoid_terms: Sequence[str] = (), named_terms: Sequence[str] = ()) -> List[Issue]:
    """After download: does what the provider says about each picture mention what its narration names? The existing
    download path only drops avoided subjects; this check reads the provider's description (and descriptive URL) and
    flags -- a person decides; nothing is swapped automatically.

    named_terms: the subject words that count as naming something (the pack's subject/document/place words, scholars,
    figures, artists). When the scene's anchors include any, the description must contain one of them; a shared common
    word ("caves", "book") is not enough. A picture with no description at all is reported as unverifiable."""
    manifest_path = Path(images_dir) / ".asset_manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [Issue("manifest_unreadable", "review", f"{manifest_path.name} could not be read")]
    records = manifest.get("scenes", manifest) if isinstance(manifest, dict) else {}
    named = {t.lower() for t in named_terms}
    issues: List[Issue] = []
    for m in metas:
        if m.source_kind not in ("document", "artwork", "real_world"):
            continue
        rec = None
        for key in (str(m.scene), f"{m.scene:03d}", f"scene_{m.scene:03d}"):
            if isinstance(records, dict) and isinstance(records.get(key), dict):
                rec = records[key]
                break
        if rec is None or rec.get("status") != "complete":
            continue
        described = _described(rec)
        if any(t.lower() in described for t in avoid_terms):
            issues.append(Issue("irrelevant_asset", "hard", f"scene {m.scene}: the downloaded picture is described as an avoided "
                                f"subject ({described[:80]})", str(m.scene)))
            continue
        if not described:
            issues.append(Issue("asset_unverifiable", "review", f"scene {m.scene}: the provider gives no description of the "
                                "picture; a person must check it shows what the narration names", str(m.scene)))
            continue
        anchors = [a.lower() for a in (m.anchors or [])]
        strong = [a for a in anchors if a in named] or [a for a in anchors if " " in a]
        query_artist = [w for w in (m.query or "").lower().split() if w in named]
        required = strong or query_artist
        if required:
            ok = any(a in described for a in required)
        else:
            ok = any(a in described for a in anchors) or \
                any(w in described for w in (m.query or "").lower().split() if len(w) > 3)
        if not ok:
            issues.append(Issue("asset_may_not_match", "review", f"scene {m.scene}: the picture is described as "
                                f"{described[:60]!r}, which names none of {(required or anchors)[:3]}", str(m.scene)))
    return issues
