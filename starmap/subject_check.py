"""Does each map beat DRAW what its words name, or only caption it? A heuristic, not understanding: it compares the words a beat
puts on screen (captions, stat labels) and the craft its narration names against what the compiled scene actually draws in the
beat's seconds (craft, paths, lines, rings, markers, tracked bodies, photo cards, footage, the camera's subject). It catches the
obvious misses -- "THE HELIOPAUSE" captioned over a path that does not show it, a named craft nowhere on screen -- before an
hour of rendering; it cannot say whether a picture is the right one. The 011 Voyager render passed every screen check (0 s
empty) while minutes of it were one picture under changing captions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Set

VISUAL = ("spacecraft", "tracker", "trajectory", "link", "distance", "rings", "marker", "pointer", "region", "orbit", "photo_card")
WORDS_ONLY = ("caption", "stat_chip", "big_number")
_STOP = {"the", "and", "for", "from", "with", "its", "that", "this", "than", "into", "over", "off", "out", "all", "one", "two",
         "first", "still", "like", "more", "years", "year", "times", "km", "billion", "million", "thousand", "per", "inside",
         "outside", "since", "after", "before", "about", "around", "nearly", "roughly", "only", "new", "now", "here"}


def _words(*texts: Any) -> Set[str]:
    out: Set[str] = set()
    for t in texts:
        if isinstance(t, (list, tuple)):
            out |= _words(*t)
        elif t:
            out |= {w[:6] for w in re.findall(r"[a-z]{3,}", str(t).lower().replace("_", " ").replace(".", " ")) if w not in _STOP}
    return out


def _during(L: Dict[str, Any], t0: float, t1: float) -> bool:
    return float(L.get("start", 0.0)) < t1 and float(L.get("end", 1e9)) > t0


def _drawn(spec: Dict[str, Any], t0: float, t1: float) -> Set[str]:
    """The vocabulary of what is drawn in [t0, t1): names, labels and ids of the visual layers, the camera's subjects."""
    got: Set[str] = set()
    for L in spec.get("layers") or []:
        if L.get("type") in VISUAL and _during(L, t0, t1):
            got |= _words(L.get("label"), L.get("title"), L.get("caption"), L.get("id"), L.get("of"), L.get("between"),
                          L.get("around"), L.get("body"), L.get("craft"), L.get("names"),
                          [r.get("label") for r in L.get("rings") or []], [r.get("names") for r in L.get("rings") or []])
    cam = spec.get("camera") or {}
    shots = [cam.get("start") or {}] + [m["to"] for m in cam.get("moves") or [] if t0 - 0.5 <= m["t"] < t1]
    for s in shots:
        got |= _words(s.get("target"), (s.get("path") or {}).get("trajectory"), (s.get("path") or {}).get("include"))
    return got


# things a caption can name that a picture could show, besides the catalog's own names (bodies, craft, boundaries, events)
THINGS = ("instrument", "transmitter", "antenna", "dish", "signal", "storm", "plume", "volcano", "ring", "magnetometer",
          "generator", "camera", "trajectory", "orbit", "flyby")


def subject_terms(cat: Any, dataset_ids: Sequence[str] = ()) -> List[str]:
    """What a caption can name that StarMap could draw: bodies and their aliases, the datasets' craft and events, the named
    boundaries round bodies, and a few kinds of physical thing."""
    terms: Set[str] = set(THINGS)
    terms |= {str(b).replace("_", " ") for b in getattr(cat, "body_ids", [])}
    terms |= {str(a).replace("_", " ") for a in (getattr(cat, "bodies", {}) or {}).get("aliases", {})}
    for bds in ((getattr(cat, "bodies", {}) or {}).get("boundaries") or {}).values():
        for bd in bds if isinstance(bds, list) else []:
            terms |= set(bd.get("says", []))
    for did in dataset_ids:
        ds = cat.index.datasets.get(did)
        if ds is not None:
            terms |= {e.replace("_", " ") for e in getattr(ds, "events", {})}
    return sorted((t.lower() for t in terms if len(t) > 2), key=len, reverse=True)


def check_subjects(plan: Any, spec: Dict[str, Any], craft_names: Iterable[str] = (), terms: Sequence[str] = ()) -> List[str]:
    """One line per beat where a caption names a subject (see subject_terms) or the narration names a craft, and nothing drawn
    on screen then is that subject. Numbers and rhetorical captions are not checked: they are meant to be words."""
    out: List[str] = []
    footage = spec.get("footage") or []
    names = [n for n in craft_names if n]
    for b in plan.beats:
        if b.mode == "footage":
            continue
        drawn = _drawn(spec, b.start, b.end)
        if any(L.get("type") == "body_labels" and _during(L, b.start, b.end) for L in spec.get("layers") or []):
            drawn |= _words(getattr(plan, "_planets", ()) or ("mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"))
        for L in spec.get("layers") or []:
            if L.get("type") != "caption" or not (b.start <= float(L.get("start", -1)) < b.end):
                continue
            text = (L.get("text") or "").lower()
            named = [t for t in terms if re.search(rf"\b{re.escape(t)}s?\b", text)]
            if not named:
                continue
            t0, t1 = float(L["start"]), float(L.get("end", float(L["start"]) + 3))
            card = any(x.get("type") == "photo_card" and _during(x, t0, t1) for x in spec["layers"]) or any(_during(f, t0, t1) for f in footage)
            if not card and not any(_words(t) & drawn for t in named):
                out.append(f"beat {b.id} ({b.start:.0f}s): the caption \"{L.get('text')}\" names {named[0]}, but nothing on screen draws it "
                           f"(a caption names a thing, it does not show it: add a row that draws it, or a picture)")
        low = (b.text or "").lower()
        craft_on = any(L.get("type") in ("spacecraft", "tracker") and _during(L, b.start, b.end) for L in spec.get("layers") or [])
        said = [n for n in names if n.lower() in low]
        # a wide view of the Sun's system names a craft and shows none (a close-up of a moon or a galaxy mentions the craft
        # in passing, and a beat about one craft may name another: neither is a miss)
        if said and not craft_on and getattr(b, "frame", "") in ("solar", "inner", "heliosphere"):
            out.append(f"beat {b.id} ({b.start:.0f}s): the narration names {said[0]} but no craft is on screen in this beat (add a craft row)")
    return out


def craft_names(cat: Any, dataset_ids: Sequence[str]) -> List[str]:
    """The names a narration uses for the craft of these datasets (each craft's own name)."""
    out: List[str] = []
    for did in dataset_ids:
        ds = cat.index.datasets.get(did)
        for cr in (ds.craft.values() if ds is not None else []):
            n = (cr.get("name") or cr.get("label") or "").title().replace("Voyager 1", "Voyager 1")
            if n and n not in out:
                out.append(n)
    return out
