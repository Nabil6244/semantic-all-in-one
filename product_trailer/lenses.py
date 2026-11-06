"""Lens callouts (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 4).

The references draw a camera sentence as the phone's back with a line from each named lens out to its label ("ultrawide / 12MP"); a lens the
narrator asks about shows "??MP", and when the answer comes later the "??" turns into it on the word ("10MP"), even after a tweet in between, by
cutting back to the callouts. Here:
  mentions()       which lenses a run of words names, with the figure that belongs to each;
  layer_for()      the pt_lenses layer for a sentence (the director);
  follow()         lenses named / asked about / answered while the scene is on screen (from the narrator's word times);
  resolve_later()  an answer said after the scene ends: a short recap of the callouts after the shot it is said in.
Drawn by whatif-engine/layers/pt_lenses.mjs. No Gemini.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .voiceover import norm

ORDER = ("ultrawide", "main", "telephoto", "periscope")      # top to bottom on the phone, as on the reference renders
CAPS = {"ultrawide": "ultrawide", "main": "main", "telephoto": "telephoto", "periscope": "periscope"}
ASK = ("what about", "no word", "no details", "unknown", "not known", "dont know", "mystery")
NEAR = 4                       # a figure belongs to a lens at most this many words away
HORIZON_S = 30.0               # an answer this long after the scene still gets a recap
MIN_KEEP_S = 3.0               # the shot the answer is said in keeps at least this much before the recap cuts in
MIN_RECAP_S = 2.5
AFTER_WORD_S = 1.2             # the recap starts this long after the answer's first word (the answer is heard first, then seen)


def _kind_at(toks: Sequence[str], i: int) -> Optional[Tuple[str, int]]:
    w = toks[i]
    nxt = toks[i + 1] if i + 1 < len(toks) else ""
    if w == "ultrawide" or (w == "ultra" and nxt in ("wide", "wideangle")):
        return "ultrawide", (1 if w == "ultrawide" else 2)
    if w in ("main", "primary"):
        return "main", 1
    if w == "wide" and (i == 0 or toks[i - 1] != "ultra"):
        return "main", 1
    if w in ("telephoto", "tele", "zoom"):
        return "telephoto", 1
    if w == "periscope":
        return "periscope", 1
    return None


def _figure_at(toks: Sequence[str], i: int) -> Optional[Tuple[str, str, int]]:
    """('MP' | 'x', '50MP' | '3x', words used) for a figure starting at toks[i]."""
    w, nxt = toks[i], (toks[i + 1] if i + 1 < len(toks) else "")
    m = re.fullmatch(r"(\d{1,3})(mp|megapixels?)", w)
    if m:
        return "MP", m.group(1) + "MP", 1
    m = re.fullmatch(r"(\d{1,2})x", w)
    if m:
        return "x", m.group(1) + "x", 1
    if re.fullmatch(r"\d{1,3}", w):
        if nxt in ("mp", "megapixel", "megapixels"):
            return "MP", w + "MP", 2
        if nxt in ("x", "times") and int(w) <= 30:
            return "x", w + "x", 2
    return None


def _scan(toks: Sequence[str]) -> List[Dict[str, Any]]:
    """Every lens mention: {kind, i (first word, figure included), value, zoom}."""
    kinds, figs = [], []
    i = 0
    while i < len(toks):
        k = _kind_at(toks, i)
        if k:
            kinds.append({"kind": k[0], "k": i, "i": i, "value": None, "zoom": None})
            i += k[1]
            continue
        f = _figure_at(toks, i)
        if f:
            figs.append((i, f[0], f[1]))
            i += f[2]
            continue
        i += 1
    for fi, unit, val in figs:                                # each figure to the nearest lens word; a tie goes to the lens after it ("50MP main")
        best = min(kinds, key=lambda m: (abs(m["k"] - fi), m["k"] < fi), default=None)
        if best is None or abs(best["k"] - fi) > NEAR:
            continue
        if unit == "MP":
            best["value"] = val
        else:
            best["zoom"] = val
        best["i"] = min(best["i"], fi)
    for m in kinds:
        if m["value"] is None and m["zoom"]:
            m["value"] = m["zoom"]
    return kinds


def _tokens(text: str) -> List[str]:
    return [t for t in (norm(x) for x in re.split(r"[\s\-]+", str(text))) if t]


def mentions(toks: Sequence[str]) -> List[Tuple[str, int, Optional[str]]]:
    """(kind, first word index, value or None) for each lens named in `toks` (normalised words)."""
    return [(m["kind"], m["i"], m["value"]) for m in _scan([norm(t) for t in toks])]


def _asked(toks: Sequence[str], i: int) -> bool:
    before = " ".join(toks[max(0, i - 5):i])
    return any(a in before for a in ASK)


def _cap(m: Dict[str, Any]) -> str:
    c = CAPS[m["kind"]]
    return f"{m['zoom']} {c}" if m.get("zoom") and m.get("value") != m.get("zoom") else c


def is_camera_talk(text: str) -> bool:
    toks = _tokens(text)
    return bool(_scan(toks)) or any(w in toks for w in ("camera", "cameras", "lens", "lenses", "sensor", "sensors", "megapixel", "megapixels"))


def layer_for(text: str, phone: str) -> Optional[Dict[str, Any]]:
    """The pt_lenses layer for a sentence naming two or more lenses, or one lens it asks about; None otherwise."""
    toks = _tokens(text)
    ms = _scan(toks)
    kinds = list(dict.fromkeys(m["kind"] for m in ms))
    q = text.strip().endswith("?") or any(a in " ".join(toks) for a in ASK)
    if len(kinds) < 2 and not (kinds and q):
        return None
    lenses = []
    for k in ORDER:
        m = next((x for x in ms if x["kind"] == k), None)
        if m is None:
            continue
        none = m["k"] > 0 and toks[m["k"] - 1] in ("no", "without", "lacks", "lost")      # "there's no telephoto lens"
        val = m["value"] or ("None" if none else None) or ("??" if (q and (_asked(toks, m["k"]) or len(kinds) == 1 or text.strip().endswith("?"))) else None)
        lenses.append({"kind": k, "cap": _cap(m), "value": val})
    models = [m.group(1) for m in re.finditer(r"(?:Galaxy )?(S\d{2}(?: (?:Plus|Pro|Edge|Ultra|FE))?|iPhone \d+(?: (?:Pro Max|Pro|Plus|Air))?)", text)
              if not re.search(r"\b(?:behind|than|compared(?: to| with)?|versus|vs\.?|like|unlike|against|beats?|over)\s+(?:the\s+)?$", text[:m.start()], re.I)]   # a compared model is not the subject
    labels = list(dict.fromkeys(m if m.startswith("iPhone") else "Galaxy " + m for m in models))[:2] or [phone or "Galaxy S27 Ultra"]
    pal = ["#7a2f45", "#5b5a86"]
    return {"type": "pt_lenses", "title": "Cameras", "phones": [{"label": lb, "color": pal[i % 2]} for i, lb in enumerate(labels)], "lenses": lenses}


LOOKS = {"look", "looks", "looked", "appear", "appears", "smaller", "bigger", "larger", "size", "thinner", "thicker", "ring", "bezel", "bezels", "opening", "aperture"}
PART_INDEX = {"ultrawide": 0, "main": 1, "telephoto": -1, "periscope": -1}   # which lens of the 3D phone (-1: the last, the zoom lens)


def _looks_near(toks: Sequence[str], i: int) -> bool:
    return any(w in LOOKS for w in toks[max(0, i - 3):i + 10])   # "the 5X camera lens on the S27 Ultra looks smaller"


def ring_for(text: str) -> Optional[Dict[str, Any]]:
    """A sentence about how one lens looks ("the 5X camera lens looks much smaller"): which lens to ring and the word that names it."""
    raw = [w for w in re.split(r"[\s\-]+", str(text)) if w]
    toks = [norm(w) for w in raw]
    if not any(w in LOOKS for w in toks):
        return None
    for i, w in enumerate(toks):
        m = re.fullmatch(r"(\d{1,2})x", w)
        if m and int(m.group(1)) >= 3 and any(x in toks[i + 1:i + 4] for x in ("lens", "camera", "zoom", "telephoto")) and _looks_near(toks, i):
            return {"index": -1, "phrase": raw[i].strip(".,?!'\""), "label": f"{m.group(1)}x lens"}
    for m in _scan(toks):
        if _looks_near(toks, m["k"]):
            return {"index": PART_INDEX[m["kind"]], "phrase": raw[m["k"]].strip(".,?!'\""), "label": f"{CAPS[m['kind']].title()} lens"}
    return None


def _window(W, a: float, b: float):
    seq = [(w, s) for w, s, _ in W if a - 0.05 <= s <= b]
    return [w for w, _ in seq], [s for _, s in seq]


def _apply(L: Dict[str, Any], toks: List[str], times: List[float], base: float) -> None:
    lenses = L.setdefault("lenses", [])
    for m in _scan(toks):
        t = round(max(0.0, times[m["i"]] - base), 2)
        cur = next((x for x in lenses if x.get("kind") == m["kind"]), None)
        asked = _asked(toks, m["k"])
        if cur is None:
            cur = {"kind": m["kind"], "cap": _cap(m), "value": m["value"] or ("??" if asked else None), "at": t}
            lenses.append(cur)
            lenses.sort(key=lambda x: ORDER.index(x["kind"]) if x.get("kind") in ORDER else 9)
            continue
        if "at" not in cur:
            cur["at"] = t
        if "ring_at" not in cur and _looks_near(toks, m["k"]) and any(w in LOOKS - {"look", "looks", "looked", "appear", "appears"} for w in toks[max(0, m["k"] - 3):m["k"] + 7]):
            cur["ring_at"] = t                       # "the telephoto lens looks much smaller": a ring round that lens (gap 5)
        if m["value"] and cur.get("value") in (None, "", "??") and "set_at" not in cur:
            if cur.get("value") == "??" and t > float(cur.get("at", 0.0)) + 0.3:
                cur.update({"was": "??", "value": m["value"], "set_at": t})
            else:
                cur["value"] = m["value"]
            if m.get("zoom") and m["value"] != m["zoom"]:
                cur["cap"] = _cap(m)
        elif asked and cur.get("value") in (None, ""):
            cur["value"] = "??"


def follow(layers: List[Dict[str, Any]], W: Sequence[Tuple[str, float, float]]) -> List[Dict[str, Any]]:
    """Lenses named, asked about and answered inside each pt_lenses window, on their words (in place)."""
    for L in layers:
        if isinstance(L, dict) and L.get("type") == "pt_lenses" and not L.get("recap"):
            a, b = float(L.get("start", 0.0)), float(L.get("end", 0.0))
            toks, times = _window(W, a, b)
            _apply(L, toks, times, a)
    return layers


def resolve_later(shots: List[Dict[str, Any]], layers: List[Dict[str, Any]], W: Sequence[Tuple[str, float, float]]) -> None:
    """A lens still at "??" whose answer is said after its scene: the callouts come back, answered, after the answer is heard (in place)."""
    for L in [x for x in layers if isinstance(x, dict) and x.get("type") == "pt_lenses" and not x.get("recap")]:
        open_ = [x for x in L.get("lenses") or [] if x.get("value") == "??"]
        if not open_:
            continue
        end = float(L.get("end", 0.0))
        toks, times = _window(W, end + 0.05, end + HORIZON_S)
        found = [(m, times[m["i"]]) for m in _scan(toks) if m["value"] and any(o["kind"] == m["kind"] for o in open_)]
        if not found:
            continue
        m, tw = found[0]
        si = next((i for i, s in enumerate(shots) if float(s["start"]) <= tw < float(s["end"])), None)
        if si is None or shots[si].get("recap"):
            continue
        s = shots[si]
        cut = round(max(float(s["start"]) + MIN_KEEP_S, tw + AFTER_WORD_S), 3)
        old_end = float(s["end"])
        if old_end - cut < MIN_RECAP_S:
            continue
        s["end"] = cut
        for X in layers:                                     # the shot's own graphics end at the cut
            if isinstance(X, dict) and "start" in X and "end" in X and float(X["start"]) < cut < float(X["end"]) and float(X["start"]) >= float(s["start"]) - 0.05:
                X["end"] = round(cut - 0.03, 3) if X.get("type") != "pt_paper" else cut
        shots.insert(si + 1, {"id": f"{s['id']}r", "kind": "black", "start": cut, "end": round(old_end, 3), "exit": s.get("exit", "cut"), "recap": True})
        R = copy.deepcopy(L)
        R.update({"start": cut, "end": round(old_end - 0.03, 3), "recap": True, "fade_in": 0.15})
        R.pop("keep", None)
        for x in R["lenses"]:
            x["at"] = 0.0
            x.pop("set_at", None)
            x.pop("was", None)
            if x["kind"] == m["kind"]:
                x.update({"was": "??", "value": m["value"], "set_at": 0.6})
                if m.get("zoom") and m["value"] != m["zoom"]:
                    x["cap"] = _cap(m)
        at = next((i for i, X in enumerate(layers) if isinstance(X, dict) and X.get("type") == "pt_subtitle"), len(layers))   # under the subtitles
        layers[at:at] = [{"type": "pt_paper", "start": cut, "end": round(old_end, 3), "fade_in": 0, "fade_out": 0}, R]
