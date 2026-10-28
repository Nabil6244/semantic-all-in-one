"""Build a graphic for one sentence from the drawing primitives of the What If engine (whatif-engine/lib/prims.mjs). The layout follows the
concept (a figure, a change, a comparison, a sequence, a timeline, a list, a quote, a definition) and every word and number on it comes from the
sentence, so the set of graphics is not a menu. Two sizes: a full plate (its own dark background) or a card over the footage.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .concepts import Concept, analyze, _fmt

PRIMS = {"text", "particles", "dot", "ring", "disc", "icon", "line", "arrow", "number", "path", "panel", "image", "glow", "band", "clock", "axis", "bar",
         "equation", "wave", "donut", "rail", "grid", "callout", "blackhole"}
ICON_NAMES = {"astronaut", "atom", "battery", "brain", "building", "camera", "car", "cell", "check", "cross", "cube", "drop", "earth", "eye", "flame", "heart",
              "hourglass", "human", "letter", "lightning", "magnet", "moon", "plane", "planet", "probe", "question", "radio", "rocket", "satellite", "ship", "skull",
              "star", "sun", "telescope", "thermometer", "tree", "warning"}
GOOD, BAD, INFO, WARM = "#2EE6A8", "#FF2A4B", "cyan", "#FFB703"


class _Frame:
    """Layout helper: a plate uses the whole frame; a card puts the same layout in a box over the footage (right side, upper two thirds)."""

    def __init__(self, plate: bool) -> None:
        self.plate = plate
        self.k = 1.0 if plate else 0.5
        self.x0, self.y0, self.w, self.h = (0.0, 0.0, 1.0, 1.0) if plate else (0.55, 0.1, 0.42, 0.56)

    def at(self, u: float, v: float) -> List[float]:
        return [round(self.x0 + self.w * u, 4), round(self.y0 + self.h * v, 4)]

    def sz(self, px: float) -> int:
        return max(11, int(round(px * (1.0 if self.plate else 0.62))))

    def chars(self, share: float = 0.8, px: float = 30) -> int:
        """Characters of a line that fit across `share` of the frame at size px (uppercase mono-ish: 0.62 px per size)."""
        return max(8, int(1280 * self.w * share / (self.sz(px) * 0.66)))


def _wrap(text: str, n: int, maxlines: int = 3) -> List[str]:
    out: List[str] = []
    cur = ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > n:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    if len(out) > maxlines:
        out = out[:maxlines]
        out[-1] = out[-1].rstrip(" ,;") + "…"
    return out


def _lines(f: _Frame, text: str, u: float, v: float, px: float, *, n: Optional[int] = None, gap: float = 0.09, align: str = "center", color: str = "white",
           in_: float = 0.4, maxlines: int = 3, **kw: Any) -> List[Dict[str, Any]]:
    out = []
    for i, ln in enumerate(_wrap(text, n or f.chars(0.86, px), maxlines)):
        out.append({"p": "text", "text": ln, "at": f.at(u, v + gap * i * (1 if f.plate else 1.15)), "size": f.sz(px), "align": align, "color": color, "in": round(in_ + 0.12 * i, 2), **kw})
    return out


def _backdrop(f: _Frame, accent: str) -> List[Dict[str, Any]]:
    if not f.plate:
        return [{"p": "panel", "at": [f.x0, f.y0], "w": f.w, "h": f.h, "accent": accent, "in": 0}]
    return [{"p": "glow", "at": [0.5, 0.5], "r": 0.55, "color": accent, "opacity": 0.12, "in": 0},
            {"p": "particles", "mode": "rise", "count": 26, "alpha": 0.22, "color": accent, "in": 0, "seed": 3}]


def _icon_item(f: _Frame, c: Concept, u: float, v: float, size: float) -> List[Dict[str, Any]]:
    return [{"p": "icon", "name": c.icon, "at": f.at(u, v), "size": round(size * (1.0 if f.plate else 0.7), 3), "in": 0.15}] if c.icon in ICON_NAMES else []


# ---- one builder per concept kind --------------------------------------------------------------------------------------------------------
def _stat(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    v = c.values[0]
    it: List[Dict[str, Any]] = _backdrop(f, WARM) + _icon_item(f, c, 0.5, 0.2, 0.16)
    it.append({"p": "number", "at": f.at(0.5, 0.52), "align": "center", "size": f.sz(120), "prefix": c.prefix, "unit": c.unit, "decimals": 0 if float(v).is_integer() else 1,
               "color": "white", "in": 0.2, "anim": {"value": {"keys": [[0.3, 0], ["end-0.9", v]], "ease": "out"}}})
    it += _lines(f, c.sub, 0.5, 0.76, 32, gap=0.08, color="cream", maxlines=2)
    return it


def _percent(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    p = max(0.0, min(100.0, c.values[0]))
    it = _backdrop(f, INFO)
    it.append({"p": "donut", "at": f.at(0.5, 0.45), "r": round(0.2 * (1 if f.plate else 0.55), 3), "width": 30 if f.plate else 16, "center": f"{_fmt(p)}%", "center_size": f.sz(52),
               "parts": [{"v": p, "color": "#00E5FF"}, {"v": 100 - p, "color": "#2A3240"}], "in": 0.2,
               "anim": {"progress": [[0.3, 0], ["end-0.8", 1]]}})
    it += _lines(f, c.sub, 0.5, 0.86, 30, gap=0.07, color="cream", maxlines=2)
    return it


def _compare(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    a, b = (c.values + [1.0, 1.0])[:2]
    top = max(a, b) or 1.0
    names = (c.names + ["THAT", "THIS"])[:2] if c.names else _compare_names(c)
    unit = f" {c.unit}" if c.unit else ""
    it = _backdrop(f, INFO)
    for k, (nm, val) in enumerate(zip(names, (a, b))):
        y = 0.38 + 0.26 * k
        it.append({"p": "bar", "at": f.at(0.08, y), "w": round(0.8 * f.w * val / top, 3) / f.w * f.w if False else round(0.8 * f.w * max(val / top, 0.04), 3), "h": 30 if f.plate else 16,
                   "color": WARM if k else "#7C8AA0", "value_text": f"{_fmt(val)}{unit}", "label": nm, "label_size": f.sz(28), "value_size": f.sz(32), "in": 0.3 + 0.3 * k,
                   "anim": {"value": [[0.4 + 0.3 * k, 0], ["end-1.2", 1]]}})
    
    return it


def _compare_names(c: Concept) -> List[str]:
    words = [w.upper() for w in c.terms if w not in ("times", "more", "less", "than", "much", "many")]
    if len(words) >= 2:
        return [" ".join(words[-2:]) if len(words) >= 3 else words[-1], words[0]]
    return ["THAT", "THIS"]


def _change(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    up = c.direction > 0
    col = GOOD if up else BAD
    it = _backdrop(f, col)
    it.append({"p": "arrow", "from": f.at(0.22, 0.62 if up else 0.3), "to": f.at(0.78, 0.3 if up else 0.62), "color": col, "width": 8 if f.plate else 5, "head": 30 if f.plate else 18,
               "in": 0.3, "anim": {"progress": [[0.4, 0], ["end-1.0", 1]]}})
    if c.unit == "%" and len(c.values) == 1:
        it.append({"p": "number", "at": f.at(0.5, 0.86), "align": "center", "size": f.sz(96), "prefix": "+" if up else "-", "unit": "%", "color": col, "in": 0.5,
                   "anim": {"value": {"keys": [[0.5, 0], ["end-0.9", c.values[0]]], "ease": "out"}}})
    else:
        a, b = (c.values + [c.values[0]])[:2]
        it.append({"p": "text", "text": f"{c.prefix}{_fmt(a)}", "at": f.at(0.2, 0.86), "size": f.sz(58), "align": "center", "color": "cream", "in": 0.3})
        it.append({"p": "text", "text": f"{c.prefix}{_fmt(b)}{(' ' + c.unit) if c.unit else ''}", "at": f.at(0.8, 0.86), "size": f.sz(58), "align": "center", "color": col, "in": 1.4})
    it += _lines(f, c.sub, 0.5, 0.14, 30, gap=0.07, color="cream", maxlines=1)
    return it


def _year_label(y: int) -> str:
    return f"{-y} BC" if y < 0 else str(y)


def _timeline(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    ys = c.years
    lo, hi = min(ys), max(ys)
    span = max(1, hi - lo)
    pos = [0.1 + 0.8 * ((y - lo) / span) if hi > lo else 0.5 for y in ys]
    it = _backdrop(f, WARM)
    it.append({"p": "axis", "from": f.at(0.06, 0.5), "to": f.at(0.94, 0.5), "color": "#8E99A8", "width": 3, "tick_size": f.sz(30),
               "ticks": [{"at": round((p - 0.06) / 0.88, 4), "label": _year_label(y), "color": "#FFB703"} for p, y in zip(pos, ys)], "in": 0.2,
               "anim": {"progress": [[0.2, 0], [1.4, 1]]}})
    for p, y in zip(pos, ys):
        it.append({"p": "dot", "at": f.at(p, 0.5), "r": 7, "color": WARM, "in": 0.6 + 0.3 * pos.index(p)})
    for p, lab in zip(pos, c.items or [""] * len(pos)):
        if lab:
            it.append({"p": "text", "text": lab, "at": f.at(p, 0.7), "size": f.sz(24), "align": "center", "color": "cream", "in": 0.8 + 0.3 * pos.index(p)})
    return it


def _process(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    n = len(c.items)
    it = _backdrop(f, INFO)
    it.append({"p": "rail", "at": f.at(0.1, 0.5), "w": round(0.8 * f.w, 3), "nodes": c.items, "all_labels": True, "label_size": f.sz(26), "color": "cyan", "in": 0.2,
               "anim": {"current": [[0.5, 0], ["end-0.8", n - 1]]}})
    for i, s in enumerate(c.items):
        it.append({"p": "text", "text": str(i + 1), "at": f.at(0.1 + 0.8 * i / max(1, n - 1), 0.34), "size": f.sz(54), "align": "center", "color": "cyan", "in": 0.4 + 0.4 * i})
    return it


def _list(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    it = _backdrop(f, WARM)
    for i, s in enumerate(c.items):
        y = 0.2 + 0.7 * i / max(5, len(c.items))
        it.append({"p": "dot", "at": f.at(0.12, y), "r": 6, "color": WARM, "style": "plain", "in": 0.3 + 0.35 * i})
        it.append({"p": "text", "text": s, "at": f.at(0.17, y + 0.015), "size": f.sz(40), "align": "left", "color": "white", "in": 0.3 + 0.35 * i})
    return it


def _quote(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    it = _backdrop(f, WARM)
    it.append({"p": "text", "text": "“", "at": f.at(0.08, 0.3), "size": f.sz(140), "align": "left", "color": WARM, "in": 0.1})
    it += _lines(f, c.headline, 0.5, 0.42, 34, gap=0.11, color="white", in_=0.3, maxlines=4)
    if c.sub:
        it.append({"p": "text", "text": "— " + c.sub, "at": f.at(0.5, 0.9), "size": f.sz(20), "align": "center", "color": WARM, "in": 1.2})
    return it


def _term(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    it = _backdrop(f, INFO) + _icon_item(f, c, 0.5, 0.18, 0.12)
    it.append({"p": "text", "text": c.headline, "at": f.at(0.5, 0.46), "size": f.sz(72), "align": "center", "color": "white", "in": 0.2})
    it.append({"p": "line", "from": f.at(0.3, 0.55), "to": f.at(0.7, 0.55), "color": "cyan", "width": 3, "in": 0.5})
    it += _lines(f, c.sub, 0.5, 0.68, 26, gap=0.08, color="cream", in_=0.7, maxlines=3)
    return it


def _keyword(c: Concept, f: _Frame) -> List[Dict[str, Any]]:
    it = _backdrop(f, INFO) + _icon_item(f, c, 0.5, 0.25, 0.16)
    it += _lines(f, c.headline, 0.5, 0.55, 56, gap=0.14, color="white", maxlines=2)
    return it


BUILDERS: Dict[str, Callable[[Concept, _Frame], List[Dict[str, Any]]]] = {
    "stat": _stat, "percent": _percent, "compare": _compare, "change": _change, "timeline": _timeline, "process": _process, "list": _list, "quote": _quote,
    "term": _term, "keyword": _keyword}
HOLD = {"stat": 5, "percent": 5.5, "compare": 6, "change": 5.5, "timeline": 6, "process": 6.5, "list": 6, "quote": 6, "term": 5.5, "keyword": 4}


def compose(c: Concept, *, plate: bool = True) -> Optional[Dict[str, Any]]:
    """The template (inline JSON, the same contract as whatif-engine/templates) drawing this concept, or None when there is nothing to draw."""
    b = BUILDERS.get(c.kind)
    if b is None:
        return None
    try:
        items = b(c, _Frame(plate))
    except (IndexError, ValueError):
        return None
    if not items:
        return None
    uid = hashlib.sha1(json.dumps([c.kind, c.headline, c.sub, c.values, c.years, c.items, plate], sort_keys=True).encode()).hexdigest()[:8]
    t = {"id": f"composed_{c.kind}_{uid}", "family": "composed", "use": f"Composed for this sentence ({c.kind}).", "tags": ["composed", c.kind], "plate": plate,
         "hold": HOLD.get(c.kind, 5), "cite": "ILLUSTRATION", "tint": "dark", "slots": {}, "items": items}
    return t if not problems(t) else None


def problems(t: Dict[str, Any]) -> List[str]:
    """Why a template (ours or an AI model's) cannot be drawn: unknown primitive or icon, missing fields, a slot it does not have."""
    from whatif import templates as wt

    p = list(wt.validate(t))
    for i, it in enumerate(t.get("items") or []):
        if not isinstance(it, dict) or it.get("p") not in PRIMS:
            p.append(f"item {i}: unknown primitive {it.get('p') if isinstance(it, dict) else it!r}")
        elif it.get("p") == "icon" and it.get("name") not in ICON_NAMES:
            p.append(f"item {i}: unknown icon {it.get('name')!r}")
    if len(t.get("items") or []) > 120:
        p.append("too many items")
    return p


# ---- an AI model as the author ---------------------------------------------------------------------------------------------------------
AUTHOR_SYSTEM = (
    "You design one motion graphic for a single narration sentence in a documentary-style video, on a 1280x720 frame, as JSON. Use ONLY these primitives "
    "(field \"p\"): " + ", ".join(sorted(PRIMS)) + ". Icons (p=icon, name): " + ", ".join(sorted(ICON_NAMES)) + ". Positions are fractions [x,y] of the frame. "
    "Every word and number comes from the sentence; invent nothing. Reply with ONLY a JSON object: "
    "{\"id\":\"x\",\"family\":\"composed\",\"use\":\"...\",\"plate\":true,\"hold\":6,\"cite\":\"ILLUSTRATION\",\"tint\":\"dark\",\"slots\":{},\"items\":[...]}. "
    "Items animate with \"in\" (seconds after start) and may use \"anim\". Keep text short (a few words), at most 14 items, nothing overlapping.")


def author(text: str, c: Concept, run: Callable[[str, str], str]) -> Optional[Dict[str, Any]]:
    """Ask an AI model (run(system, user) -> text) for a graphic of this sentence; kept only when it validates. None -> use compose()."""
    try:
        raw = run(AUTHOR_SYSTEM, f"Sentence: {text}\nConcept: {c.kind}; headline: {c.headline}; figures: {c.values}; years: {c.years}; items: {c.items}")
        m = re.search(r"\{.*\}", raw or "", re.S)
        t = json.loads(m.group(0)) if m else None
    except Exception:
        return None
    if not isinstance(t, dict):
        return None
    t.setdefault("slots", {})
    t["family"], t.setdefault("use", "Authored for this sentence."), t.setdefault("plate", True)
    t["id"] = "authored_" + hashlib.sha1(json.dumps(t.get("items"), sort_keys=True).encode()).hexdigest()[:8]
    return t if not problems(t) else None
