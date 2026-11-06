"""The film's own phone drawn right on the flat graphics (2026-11-06, iPhone Duo test render: the flat cards drew it with a 3-lens iPhone Pro
module and the callouts with a Galaxy column, while the 3D model has two lenses).

camera_of(phone) reads the same camera layout the 3D engine picks (whatif-engine/data/phones.json by id / name / alias, else the brand rules of
lib/phone_models.mjs genericFor) and gives the flat drawing's design and lens count. fix_phones() applies it to every flat phone that is the
film's phone (its label is the phone's name), never to a phone the narration compares it with. No network, no AI.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PHONES = Path(__file__).resolve().parents[1] / "whatif-engine" / "data" / "phones.json"
FLAT = {"galaxy_ultra": (None, 4), "galaxy_s": (None, 3), "iphone_pro": ("iphone", 3), "iphone_base": ("iphone", 2), "pixel_bar": ("pixel", 3),
        "galaxy_s27_island": ("bar", 3), "galaxy_s27_video": ("bar", 3), "round_island": (None, 3), "square_island": (None, 3), "vertical_pill": (None, 3)}


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


@lru_cache(maxsize=1)
def _catalog() -> Tuple[Dict[str, Any], ...]:
    try:
        d = json.loads(PHONES.read_text(encoding="utf-8"))
        return tuple(d.get("phones") or [])
    except Exception:
        return ()


def layout_of(phone: str) -> str:
    n = _norm(phone)
    nid = n.replace(" ", "_")
    for p in _catalog():                         # an exact preset only (an alias like "iphone" must not turn every iPhone into the 17 Pro)
        if p.get("id") == nid or _norm(p.get("name")) == n or any(_norm(a) == n for a in p.get("aliases") or []):
            return (p.get("camera") or {}).get("layout") or "square_island"
    if re.search(r"\b(iphone|apple)\b", n):
        return "iphone_pro" if "pro" in n.split() else "iphone_base"
    if re.search(r"\b(pixel|google)\b", n):
        return "pixel_bar"
    if re.search(r"\b(galaxy|samsung|s\d{2})\b", n):
        return "galaxy_ultra" if "ultra" in n.split() else "galaxy_s"
    return "square_island"


def camera_of(phone: str) -> Tuple[Optional[str], int]:
    """(flat design, lens count) of the phone, as the 3D model has it."""
    return FLAT.get(layout_of(phone), (None, 3))


def fix_phones(layers: List[Dict[str, Any]], phone: str) -> None:
    """Every flat phone labelled with the film's phone gets that phone's camera (in place)."""
    if not phone:
        return
    design, cams = camera_of(phone)
    me = _norm(phone)
    for L in layers:
        if not isinstance(L, dict) or L.get("type") not in ("pt_flatphones", "pt_lenses"):
            continue
        for p in L.get("phones") or []:
            if isinstance(p, dict) and _norm(p.get("label")) == me:
                p["cams"] = cams
                if design:
                    p["design"] = design
                else:
                    p.pop("design", None)
