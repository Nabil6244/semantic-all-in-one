"""War Documentary adapter for Wall Moments (docs/wall/PLAN.md, Phase 4): War's own layer lists for the shared wall/adapter.py.

    apply(shots, layers, scenes, words, *, pct=20, work=None, log=print) -> (shots, layers, report)

War differences from Aviation:
- the darker "war" wall theme;
- a moment never covers a scene's own real footage (War is footage-led; that footage stays full screen at 1080p);
- maps (tactical, satellite, front line, flyover), chapter titles and the opening title always stay as they are;
- a wall print is decoded through War's own shot chain (the same grade, vignette and blur-fill as the full-screen shot) and cropped to the
  shot's zoom at the hand-off frame, so pulling out of a clip and diving into the next one does not jump in colour or size;
- the clip right after a moment starts with a hard cut (its cross-fade would fade from a clip the wall was covering).
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from wall import adapter as WA

KEEP = ("tac_map", "tac_route", "map_card", "map_inset", "sat_map", "sat_range", "lay_satellite", "fx_roadmap", "kit_flyover",
        "kit_chapter", "kit_title", "kit_recap",
        # 2026-11-16 owner's picks ("these are the rich graphics that I like"): the wall never covers them
        "kit_counter", "kit_forces", "kit_chain", "sat_quote", "tac_route", "equipment_card", "lay_equipment_compare", "lay_equipment_hero",
        "lay_figure_pair", "lay_speaker_quote", "lay_timeline", "split_compare", "timeline", "kit_keywords", "kit_scale")
TRANSIENT = ("bc_", "fx_flash", "kit_grain", "source", "source_label", "status_chip", "kicker", "flag", "kit_flag", "kit_badge", "kit_tag",
             "kit_ribbon", "kit_chips", "shot_head", "shot_headline", "kit_sticker", "kit_stamp")
CARD = ("kit_", "lay_", "sat_quote", "equipment_card", "evidence_card", "figure_card", "institution_card", "list", "number", "portrait",
        "split_compare", "stat_compare", "stat_number", "timeline")
THEME = "war"


def _hand_off(shot: Any, at: float) -> Dict[str, Any]:
    """The War look of `shot` at film time `at`: segments' own static chain (grade, vignette, fill, colour tags) plus the crop its
    push / pan has reached at that frame. Returns {"graph": filter_complex [0:v] -> [o]} or {} for a plain shot."""
    from . import segments as SG

    tj = SG._shot_treat(shot, SG._frame(shot.start), SG._frame(shot.end))
    if not tj:
        return {}
    tr = json.loads(tj)
    static = dict(tr, m="none")
    for k in ("z0", "z1", "sf0", "sf1"):
        static.pop(k, None)
    chain = SG._stage(shot.path, "0:v", "s", 3600.0, json.dumps(static, sort_keys=True), 0, "w")
    chain = chain.replace("tpad=stop_mode=clone:stop_duration=60,", "")
    chain = re.sub(r",trim=duration=[\d.]+,setpts=PTS-STARTPTS", "", chain)
    crop = "null"
    if tr.get("m") not in (None, "none"):
        n1 = max(1, int(tr["sf1"]) - int(tr["sf0"]) - 1)
        f = min(1.0, max(0.0, (SG._frame(at) - int(tr["sf0"])) / n1))
        e = f * f * (3 - 2 * f)
        z0, z1 = float(tr["z0"]), float(tr["z1"])
        if tr["m"] in ("pan_left", "pan_right"):
            z = z1
            g = e if tr["m"] == "pan_right" else 1 - e
            x = f"(iw-iw/{z:.5f})*{g:.5f}"
        else:
            z = z0 + (z1 - z0) * e
            x = f"(iw-iw/{z:.5f})/2"
        crop = f"crop=w=iw/{z:.5f}:h=ih/{z:.5f}:x={x}:y=(ih-ih/{z:.5f})/2"
    chain = chain.replace(f"fps={SG.FPS},", f"fps={SG.FPS},{crop},", 1)    # zoom first, then grade and vignette (War's own order)
    return {"graph": f"{chain};[s]null[o]"}


STYLE = WA.Style(card=CARD, keep=KEEP, transient=TRANSIENT, theme=THEME, allow_strong=False, clip_extra=_hand_off, name="War")


def apply(shots: Sequence[Any], layers: Sequence[Any], scenes: Sequence[Dict[str, Any]], words: Any, *, pct: float = 20.0,
          work: Optional[str] = None, log: Callable[[str], None] = lambda m: None) -> Tuple[List[Any], List[Any], Dict[str, Any]]:
    out_layers, rep = WA.apply(shots, layers, scenes, words, STYLE, pct=pct, work=work, log=log)
    ends = {round(b, 3) for _a, b in rep["spans"]}
    out_shots = []
    for s in shots:
        if round(float(s.start), 3) in ends and float(getattr(s, "dissolve_in", 0.0) or 0.0) > 0:
            s = dataclasses.replace(s, dissolve_in=0.0)          # the wall dives straight into this clip
        out_shots.append(s)
    return out_shots, out_layers, rep
