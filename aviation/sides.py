"""Colour = side (docs/aviation/J11_REFERENCE_STUDY.md section 2): each film has two sides - the two countries the narration names
most, else its two most-named airlines - and every graphic paints the same side the same colour (side 'a' orange, side 'b'
light blue), so a viewer reads who is who without labels.

    film_sides(texts) -> {'a': {'kind', 'id', 'name'}, 'b': {...}}        or fewer keys when the story has one side / none
    set_film(texts) / current()                                            the planner sets it once per plan; graphics read it
    side_of(code_or_id_or_name) -> 'a' | 'b' | ''
    hex_of(side) -> '#F2A82C' | '#78ACE8' | ''                             for cards that take hex colours (political map)
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Sequence

from . import catalog as C

HEX = {"a": "#F2A82C", "b": "#78ACE8"}
_FILM: Dict[str, Dict[str, Any]] = {}


def film_sides(texts: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    from .story import _COUNTRIES, countries_in
    names = {code: name for name, code in _COUNTRIES.items()}
    cc: Counter = Counter()
    ac: Counter = Counter()
    for t in texts:
        for code in countries_in(str(t)):
            cc[code] += 1
        for m in C.find_airlines(str(t)):
            if m.entry:
                ac[m.entry["id"]] += 1
    top = [c for c, n in cc.most_common(2) if n >= 2]
    if len(top) == 2:
        return {s: {"kind": "country", "id": code, "name": names.get(code, code).title()} for s, code in zip("ab", top)}
    top = [a for a, n in ac.most_common(2) if n >= 2]
    return {s: {"kind": "airline", "id": a, "name": (C.get_airline(a) or {}).get("name", a)} for s, a in zip("ab", top)}


def set_film(texts: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    _FILM.clear()
    _FILM.update(film_sides(texts))
    return dict(_FILM)


def current() -> Dict[str, Dict[str, Any]]:
    return dict(_FILM)


def side_of(x: Any) -> str:
    s = str(x or "").strip().lower()
    if not s:
        return ""
    for k, v in _FILM.items():
        if s in (str(v["id"]).lower(), str(v["name"]).lower()):
            return k
        if v["kind"] == "airline" and s.replace(" ", "_") == str(v["id"]).lower():
            return k
    from .story import countries_in
    codes = countries_in(str(x)) if len(s) > 2 else [s.upper()]
    for k, v in _FILM.items():
        if v["kind"] == "country" and v["id"] in codes:
            return k
    return ""


def hex_of(side: str) -> str:
    return HEX.get(side, "")
