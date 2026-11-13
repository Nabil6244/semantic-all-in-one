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
        "galaxy_s27_island": ("bar", 3), "galaxy_s27_video": ("bar", 3), "round_island": (None, 3), "square_island": (None, 3), "vertical_pill": ("pill", 2),
        "air_plateau": ("air", 1)}


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


@lru_cache(maxsize=1)
def _catalog() -> Tuple[Dict[str, Any], ...]:
    try:
        d = json.loads(PHONES.read_text(encoding="utf-8"))
        return tuple(d.get("phones") or [])
    except Exception:
        return ()


def preset_of(phone: str) -> Optional[Dict[str, Any]]:
    """The catalog preset of a phone name (id, name or alias), else the longest preset name inside it ("iPhone 18 Dummy" -> iPhone 18), else None."""
    n = _norm(phone)
    nid = n.replace(" ", "_")
    for p in _catalog():
        if p.get("id") == nid or _norm(p.get("name")) == n or any(_norm(a) == n for a in p.get("aliases") or []):
            return p
    hit = named_in(phone)
    return hit[0][2] if hit else None


def _names() -> List[Tuple[str, Dict[str, Any]]]:
    """Every name a sentence can call a preset by: its name and its aliases of two words or more ("air 2"; never "galaxy" or "18")."""
    out = []
    for p in _catalog():
        for nm in [p.get("name")] + list(p.get("aliases") or []):
            if nm and len(_norm(nm).split()) >= 2:
                out.append((_norm(nm), p))
    return sorted(out, key=lambda x: -len(x[0]))


def named_in(text: str) -> List[Tuple[int, str, Dict[str, Any]]]:
    """The presets a text names, in order: (position, the words before it, preset); the longest name wins at a position."""
    t = " " + _norm(text) + " "
    taken: List[Tuple[int, int]] = []
    out = []
    for nm, p in _names():
        for m in re.finditer(r"(?<= )" + re.escape(nm) + r"(?= )(?! (?:pro|max|plus|ultra|mini|fold|flip|fe|edge|e|lite|neo|slim|air|xl|\d)\b)", t):   # "iPhone 18 Pro" is not the iPhone 18
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            out.append((m.start(), t[max(0, m.start() - 20):m.start()], p))
    return sorted(out, key=lambda x: x[0])


COMPARE = re.compile(r"\b(to|than|like|as|with|versus|vs)\s+(?:the\s+|an?\s+)?$")


OLD = re.compile(r"\b(original|first|old|older|current|last|previous|today s|existing)\s+$")


def subjects(lines: List[str], film_phone: str = "") -> List[Optional[Dict[str, Any]]]:
    """The phone each sentence is about: the first preset it names that is not the thing it is compared with ("identical to the iPhone 17"),
    carried on to the sentences after it until another phone is named. A name the film's phone grew out of ("the next iPhone Air" in an
    iPhone Air 2 film) is the film's phone, unless the sentence says it is the old one ("the original iPhone Air")."""
    me = preset_of(film_phone) if film_phone else None
    mine = _norm((me or {}).get("name"))
    cur: Optional[Dict[str, Any]] = None
    out = []
    for ln in lines:
        for _, before, p in named_in(ln):
            if COMPARE.search(before):
                continue
            nm = _norm(p.get("name"))
            if me and p is not me and mine.startswith(nm + " ") and not OLD.search(before):
                p = me
            cur = p
            break
        out.append(cur)
    return out


def follow(spec: Dict[str, Any], lines: List[str], starts: List[float], film_phone: str) -> int:
    """3D phone shots show the phone their sentence is about (the iPhone 18 while the narration is on the iPhone 18), not always the film's phone.
    `starts` are the sentences' start times. Returns how many shots changed phone."""
    if not lines or len(starts) != len(lines):
        return 0
    subj = subjects(lines, film_phone)
    me = preset_of(film_phone)
    n = 0
    for sh in spec.get("shots", []):
        if sh.get("kind") != "product" or sh.get("object") not in ("phone", "lineup") or not isinstance(sh.get("phone"), str):
            continue
        mid = (float(sh["start"]) + float(sh["end"])) / 2
        i = max([k for k, t in enumerate(starts) if t <= mid] or [0])
        p = subj[i]
        if not p or (me and p.get("id") == me.get("id")):
            continue
        sh["phone"] = p["name"]
        cols = [c.get("name") for c in p.get("colors") or []]
        if sh.get("color") not in cols:
            sh.pop("color", None)
        if sh.get("object") == "lineup":
            sh["colors"] = cols[:4] or sh.get("colors")
        n += 1
    return n


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
    design, cams = FLAT.get(layout_of(phone), (None, 3))
    cam = (preset_of(phone) or {}).get("camera") or {}
    if cam.get("count"):
        cams = int(cam["count"])                 # a layout with a lens count of its own (iPhone Air 1, Air 2 two)
    return design, cams


def fix_phones(layers: List[Dict[str, Any]], phone: str) -> None:
    """Every flat phone gets its own camera (in place): the film's phone as its 3D model has it, and a phone the narration compares it with as
    its own catalog preset has it (iPhone 18 a vertical pill, iPhone Air 2 a plateau with two lenses), never the film's phone's camera."""
    me = _norm(phone)
    for L in layers:
        if not isinstance(L, dict) or L.get("type") not in ("pt_flatphones", "pt_lenses"):
            continue
        for p in L.get("phones") or []:
            if not isinstance(p, dict):
                continue
            label = str(p.get("label") or "")
            own = preset_of(label)
            if not ((me and _norm(label) == me) or own):
                continue
            design, cams = camera_of(own["name"] if own else phone)
            p["cams"] = cams
            if design:
                p["design"] = design
            else:
                p.pop("design", None)
