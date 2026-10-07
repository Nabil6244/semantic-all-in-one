"""StarMap's sound design: which sound plays when, from the compiled spec. The sounds, the restraint rules (no stacking) and the
mix (narration first; effects and ambience ducked under the voice) are pakMap's (pakmap.audio_plan / audio_mix, used as they
are); only the choice of cues is StarMap's own:

    a deep "vacuum" drone under the map (space_drone), silent under footage (the clips carry their own sound)
    a soft whoosh when the camera flies to a new view; a deep "earth spin" when it crosses many orders of magnitude
    a soft transition as footage dissolves in
    a thud for a title, a pop for a marker, a pluck for a region, a whoosh as a flight path draws, ticks as a number counts up,
    a click for a photo card
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

LAYER_SFX = {"title": "deep_thud", "marker": "marker_pop", "region": "bubble_pluck", "trajectory": "directional_whoosh",
             "orbit": "directional_whoosh", "stat_chip": "counter_ticks", "photo_card": "ui_click"}
RANK = ("earth_spin", "deep_thud", "map_slide_whoosh", "soft_transition", "counter_ticks", "directional_whoosh", "marker_pop",
        "bubble_pluck", "ui_click")      # when two would play together, the earlier in this list wins
MIN_GAP_S = 0.6                       # never two effects closer than this (the narration stays in front)
BIG_MOVE = 1000.0      # a glide across more than this ratio of distances (Earth orbit -> Moon, Sun -> galaxy) is a major move


def _km(shot: Dict[str, Any]) -> float:
    d = shot.get("distance") or {}
    if d:
        return float(d.get("km") or d.get("au", 0) * 1.496e8 or d.get("ly", 0) * 9.4607e12 or 1.0)
    if "fill" in shot:
        return 2e4 / float(shot["fill"])
    if "fit" in shot:
        return 1e6 * float(shot["fit"])
    return 1e4


def sound_hints(spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """pakmap.audio_plan hints ({"cues": [...], "ambience": [...]}) for a StarMap spec."""
    cues: List[Dict[str, Any]] = []
    cam = spec.get("camera") or {}
    prev = _km(cam.get("start") or {})
    for m in cam.get("moves") or []:
        km = _km(m.get("to") or {})
        if m.get("dur", 0) > 0 and abs(math.log10(max(km, 1e-9) / max(prev, 1e-9))) > 0.15:
            big = abs(math.log10(km / prev)) >= math.log10(BIG_MOVE)
            cues.append({"t": float(m["t"]), "sfx": "earth_spin" if big else "map_slide_whoosh", "source": "camera move"})
        prev = km
    for L in spec.get("layers") or []:
        sfx = LAYER_SFX.get(L.get("type"))
        if sfx and "start" in L and not (L.get("type") == "trajectory" and L.get("draw") is False):
            if L.get("type") == "stat_chip" and not L.get("count_up"):
                sfx = "deep_thud"
            cues.append({"t": float(L["start"]), "sfx": sfx, "source": f"{L['type']} layer"})
    ambience: List[Dict[str, Any]] = [{"t": 0.0, "ambience": "space_drone"}]
    for f in sorted(spec.get("footage") or [], key=lambda x: x["start"]):
        cues.append({"t": max(0.0, float(f["start"]) - 0.25), "sfx": "soft_transition", "source": "footage dissolving in"})
        ambience.append({"t": float(f["start"]), "ambience": "none"})
        ambience.append({"t": float(f["end"]), "ambience": "space_drone"})
    # footage straight after footage: no drone flicker between the clips
    amb: List[Dict[str, Any]] = []
    for a in sorted(ambience, key=lambda x: x["t"]):
        if amb and abs(amb[-1]["t"] - a["t"]) < 1e-6:
            amb[-1] = a if a["ambience"] == "none" else amb[-1]
        else:
            amb.append(a)
    # restraint: one effect at a time, the more important one when two coincide
    kept: List[Dict[str, Any]] = []
    for c in sorted(cues, key=lambda c: (c["t"], RANK.index(c["sfx"]) if c["sfx"] in RANK else len(RANK))):
        if kept and c["t"] - kept[-1]["t"] < MIN_GAP_S:
            continue
        kept.append(c)
    end = float(spec.get("duration") or 0)
    amb = [a for a in amb if a["ambience"] == "none" or not end or a["t"] < end - 0.5]
    amb = [a for i, a in enumerate(amb) if i == 0 or a["ambience"] != amb[i - 1]["ambience"]]   # no repeated "none" between clips
    return {"cues": kept, "ambience": amb}


def plan_sound(spec: Dict[str, Any], *, enabled: bool = True, catalog: Any = None):
    """The AudioPlan (pakmap.audio_plan) with the library files found; nothing is read or mixed yet."""
    from pakmap.audio_mix import resolve_assets
    from pakmap.audio_plan import plan_audio

    plan = plan_audio({"duration": spec.get("duration", 0)}, sound_hints(spec), enabled=enabled, duration=spec.get("duration"))
    return resolve_assets(plan, catalog)
