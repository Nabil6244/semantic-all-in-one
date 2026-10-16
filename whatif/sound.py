"""What If's sound: restrained, as the references. A low drone bed under the whole video, a soft UI click as data lands, a low
thud for a title card and a blackout, a muffled swap at a diagram. Hard cuts are silent. The sounds, the no-stacking rule and
the mix (narration first, everything ducked under the voice) are pakMap's, used as they are (as StarMap does)."""

from __future__ import annotations

from typing import Any, Dict, List

LAYER_SFX = {"tm_metric": "ui_click", "tm_caption": "ui_click", "tm_title": "deep_thud", "tm_fade": "deep_thud", "tm_survival": "ui_click",
             "tm_clock": "ui_click", "tm_gauge": "ui_click", "tm_composition": "ui_click", "tm_logaxis": "ui_click", "tm_compare": "ui_click",
             "tm_discmap": "ui_click", "tm_annotate": "ui_click"}
MIN_GAP_S = 0.8


def sound_hints(spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    cues: List[Dict[str, Any]] = []
    for s in spec.get("shots") or []:
        if s.get("kind") == "plate":
            cues.append({"t": float(s["start"]), "sfx": "soft_transition", "source": "diagram plate"})
    for L in spec.get("layers") or []:
        sfx = LAYER_SFX.get(L.get("type"))
        if sfx and "start" in L:
            if L["type"] == "tm_caption" and L.get("size") != "large":
                continue
            cues.append({"t": float(L["start"]), "sfx": sfx, "source": f"{L['type']} layer"})
        if L.get("type") == "tm_survival":
            cues += [{"t": float(x["t"]), "sfx": "ui_click", "source": "survival clock change"} for x in (L.get("states") or [])[1:]]
    rank = ("deep_thud", "soft_transition", "ui_click")
    kept: List[Dict[str, Any]] = []
    for c in sorted(cues, key=lambda c: (c["t"], rank.index(c["sfx"]))):
        if kept and c["t"] - kept[-1]["t"] < MIN_GAP_S:
            continue
        kept.append(c)
    return {"cues": kept, "ambience": [{"t": 0.0, "ambience": "space_drone"}]}


def plan_sound(spec: Dict[str, Any], *, enabled: bool = True, catalog: Any = None):
    from pakmap.audio_mix import resolve_assets
    from pakmap.audio_plan import plan_audio

    plan = plan_audio({"duration": spec.get("duration", 0)}, sound_hints(spec), enabled=enabled, duration=spec.get("duration"))
    return resolve_assets(plan, catalog)


# ---- loudness: the references are all normalised to -14 LUFS integrated, loudness range about 4 LU, true peak about -1.5 dBFS
TARGET_LUFS, TARGET_TP, TARGET_LRA = -14.0, -1.5, 4.0


def measure_loudness(path: Any, ffmpeg: str = "ffmpeg") -> Dict[str, float]:
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBFS) of an audio file."""
    import re
    import subprocess

    r = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    summ = r.stderr[r.stderr.rfind("Summary:"):]
    pick = lambda pat: float(re.search(pat, summ).group(1))  # noqa: E731
    return {"lufs": pick(r"I:\s+(-?[0-9.]+) LUFS"), "lra": pick(r"LRA:\s+([0-9.]+) LU"), "peak": pick(r"Peak:\s+(-?[0-9.]+) dBFS")}


def normalize_loudness(src: Any, dst: Any, ffmpeg: str = "ffmpeg", *, lufs: float = TARGET_LUFS, tp: float = TARGET_TP, lra: float = TARGET_LRA) -> Any:
    """The final audio at the references' loudness (two-pass loudnorm: measured, then applied linearly so the dynamics are kept). Returns
    dst; if anything fails the source is returned untouched, so a normalisation problem never stops a video."""
    import json
    import re
    import subprocess
    from pathlib import Path

    try:
        a = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(src), "-af", f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", a.stderr, re.S).group(0))
        flt = (f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
               f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        b = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-af", flt, "-ar", "48000", str(dst)], capture_output=True, text=True)
        if b.returncode != 0 or not Path(dst).is_file():
            return src
        return dst
    except Exception:
        return src
