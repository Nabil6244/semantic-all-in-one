"""The narration read for News Doc: sentences with their times, the story's parts, and what each sentence offers the edit
(places, numbers, a list, a warning name, a line worth a quote card). Deterministic; no AI, no network."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

OPENING_S = 75.0          # the reference's cold open: faster cuts
PART_MIN_S = 45.0         # a new state named starts a part (chapter word, glitch) at most this often
HEADING_MIN_S = 12.0      # a heading the script writes always starts one (unless two come within seconds)
HEADING = re.compile(r"^([A-Z0-9][A-Z0-9 ,.'’&/-]{3,}?)(?:\s+[—–-]\s+([A-Z0-9][A-Z0-9 ,.'’&/-]+?))?(?=\s+[A-Z][a-z])")
YELLOW = re.compile(r"\b((?:Tornado|Severe Thunderstorm|Flash Flood|Flood|Winter Storm|Blizzard|Ice Storm|Hurricane|Tropical Storm|"
                    r"Storm Surge|Excessive Heat|Heat|Red Flag|High Wind|Extreme Wind|Special Marine) (?:Warning|Watch|Emergency|Statement|"
                    r"Advisory)|National Weather Service|National Hurricane Center|Storm Prediction Center|Weather Prediction Center|"
                    r"(?:Hurricane|Tropical Storm|Typhoon) [A-Z][a-z]+)\b")
EXPLAIN = re.compile(r"\b(because|which means|that means|this means|here's why|here is why|the reason|so that|that is why|that's why)\b", re.I)
UNITS = {"mph": "MPH", "in": "INCHES", "ft": "FEET", "mb": "MB", "F": "°F", "%": "%", "cat": "CATEGORY", "EF": "EF", "kt": "KNOTS",
         "mi": "MILES", "yd": "YARDS", "count": ""}


@dataclass
class Number:
    value: float
    unit: str
    text: str           # as said ("115 miles per hour")
    shown: str          # as drawn ("115")
    label: str          # under it ("MPH")


@dataclass
class Line:
    i: int
    text: str
    start: float          # the sentence's own words
    end: float
    span_start: float     # its slot in the timeline (to the next sentence)
    span_end: float
    part: int = 0
    heading: str = ""
    places: List[Tuple[str, str, Optional[float], Optional[float]]] = field(default_factory=list)  # (name, kind, lat, lon)
    place_state: Dict[str, str] = field(default_factory=dict)   # place name -> its state's name
    states: List[str] = field(default_factory=list)
    numbers: List[Number] = field(default_factory=list)
    yellow: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)       # a list of 3+ names
    explains: bool = False

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Story:
    lines: List[Line]
    duration: float
    category: str
    states: List[str]
    parts: List[Tuple[int, str]]   # (first line index, its title)
    understanding: object = None


def _fmt(v: float) -> str:
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _number(m) -> Optional[Number]:
    unit = m.unit
    if unit in ("min", "h"):
        return None
    shown = (f"EF{int(m.value)}" if unit == "EF" else f"CAT {int(m.value)}" if unit == "cat" else _fmt(m.value) + ("%" if unit == "%" else ""))
    label = "" if unit in ("EF", "cat", "%") else UNITS.get(unit, str(unit).upper())
    if unit == "count":
        q = str(getattr(m, "quantity", "") or "")
        label = {"count_warnings": "WARNINGS", "count_tornado": "TORNADOES", "count_reports": "STORM REPORTS"}.get(q, "")
        if not label:
            return None
    return Number(float(m.value), unit, m.text, shown, label)


def _items(text: str) -> List[str]:
    """'Communities in the path include Lancaster, Logan, Bremen and Amanda.' -> the names (3+), else []."""
    body = text.split(":", 1)[-1] if ":" in text else text
    name = r"[A-Z][\w'’.-]*(?:\s[A-Z][\w'’.-]*)*"
    m = re.search(rf"({name}(?:\s*,\s*{name})+(?:,?\s+and\s+{name})?)", body)
    if not m:
        return []
    names = [x.strip(" .") for x in re.split(r",\s*|\s+and\s+", m.group(1)) if x.strip(" .")]
    names = [re.sub(r"^and\s+", "", n) for n in names]
    return names if len(names) >= 3 else []


def read(words: Sequence, duration: float, script: str = "") -> Story:
    from hybrid.narration import build_sentences

    from ..intel.catalog import state_name
    from ..intel.understand import Segment, understand

    sents = build_sentences(list(words), script or None, duration)
    if not sents:
        raise ValueError("the narration has no sentences")
    n = len(sents)
    lines = []
    for k, s in enumerate(sents):
        a = 0.0 if k == 0 else s.start
        z = sents[k + 1].start if k + 1 < n else duration
        lines.append(Line(k, s.text.strip(), s.start, s.end, a, z))
    u = understand([Segment(f"s{x.i}", "footage", x.text, x.start, x.end) for x in lines])
    by = {x.i: x for x in lines}
    for p in u.places:
        x = by.get(int(p.seg[1:]))
        if x is None:
            continue
        if p.kind == "state":
            name = state_name(p.state)
            if name not in x.states:
                x.states.append(name)
        elif p.kind in ("county", "city") and not any(q[0] == p.name for q in x.places):
            x.places.append((p.name, p.kind, p.lat, p.lon))
            if p.state:
                x.place_state[p.name] = state_name(p.state)
    for m in u.measurements:
        x = by.get(int(m.seg[1:]))
        num = _number(m) if x is not None else None
        if num and not any(q.shown == num.shown for q in x.numbers):
            x.numbers.append(num)
    for x in lines:
        x.yellow = list(dict.fromkeys(m.group(1) for m in YELLOW.finditer(x.text)))
        x.items = _items(x.text)
        x.explains = bool(EXPLAIN.search(x.text))
        h = HEADING.match(x.text)
        if h and len(" ".join(g for g in h.groups() if g).split()) >= 2:
            x.heading = " — ".join(g.strip(" ,.") for g in h.groups() if g)
        elif x.text.isupper() and len(x.text.split()) >= 2:   # a heading the script writes on its own line ("MAJOR FLOODING — CANADIAN RIVER")
            x.heading = " — ".join(g.strip(" ,.:") for g in re.split(r"\s+[—–-]\s+", x.text.strip()) if g.strip(" ,.:"))
    # parts: a script heading, or a new state after a while
    parts: List[Tuple[int, str]] = [(0, "")]
    last_t, seen_states = 0.0, set(lines[0].states)
    for x in lines[1:]:
        new_state = [s for s in x.states if s not in seen_states]
        seen_states.update(x.states)
        if (x.heading and x.span_start - last_t >= HEADING_MIN_S) or (new_state and x.span_start - last_t >= PART_MIN_S):
            parts.append((x.i, x.heading.split(" — ")[0] if x.heading else new_state[0].upper()))
            last_t = x.span_start
    for k, (first, _t) in enumerate(parts):
        last = parts[k + 1][0] if k + 1 < len(parts) else n
        for x in lines[first:last]:
            x.part = k
    states = [state_name(s) for s in u.states]
    return Story(lines, duration, u.category, states, parts, u)


def word_time(words: Sequence, a: float, b: float, phrase: str) -> Optional[float]:
    """When the first word of `phrase` is said between a and b (None when it is not heard there)."""
    want = [w for w in re.findall(r"[a-z0-9]+", str(phrase).lower().replace(",", ""))]
    if not want:
        return None
    for w in words:
        if float(w[1]) < a - 0.05 or float(w[1]) >= b:
            continue
        got = re.findall(r"[a-z0-9]+", str(w[0]).lower().replace(",", ""))
        if got and got[0] == want[0]:
            return float(w[1])
    return None
