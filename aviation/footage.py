"""Aviation footage rules (docs/aviation/PLAN.md section 5): what to search for, which clips may be used, how long to cut.

    queries_for(classification, max_q=3) -> ['Air France strike 2015', ...]   search phrases from the sentence's own names, no Gemini
    clip_ok(clip_text, classification) -> (ok, score, reason)                  clip title / words against the sentence
    livery_score(image, airline_id) -> 0..1                                     share of the frame in the airline's (non-white) colours
    cut_range(mode) -> (min_s, max_s)                                           shot lengths: news bursts 1-2 s, fleet beauty 4-8 s ...

Rules
- A sentence that names an aircraft type takes only a clip that names that type (an A350 line never shows a 737).
- A news sentence about an event (strike, launch, order, crash ...) of a named airline takes only a clip that names that airline;
  if none is found the planner shows an article card for it instead of generic b-roll.
- A named airline's own clip scores above another airline's clip of the same type (livery preference); livery_score adds a cheap
  local colour check on a frame.
- Investigation / report lines want graphics (report pages), not footage: no queries.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image

from . import catalog as C
from . import gfx as G

_EVENTS = (("strike", r"\bstrik\w*|\bwalkout"), ("launch", r"\blaunch\w*|\bunveil\w*"), ("order", r"\border(?:s|ed)?\b"),
           ("delivery", r"\bdeliver\w*"), ("crash", r"\bcrash\w*"), ("merger", r"\bmerg\w*"), ("collapse", r"\bbankrupt\w*|\bcollaps\w*"),
           ("rebrand", r"\brebrand\w*"), ("rejects", r"\breject\w*"), ("first flight", r"\bfirst flight\b"), ("grounding", r"\bground(?:ed|ing)\b"))
_PHASES = (("takeoff", r"\btak(?:e|es|ing|en) off\b|\btook off\b|\btakeoff\b|\bdepart\w*"), ("landing", r"\bland(?:s|ed|ing)?\b|\btouch\w* down"),
           ("approach", r"\bapproach\w*"), ("climbing above clouds", r"\bclimb\w*"), ("cruising", r"\bcruis\w*"), ("taxiing", r"\btaxi\w*"),
           ("boarding", r"\bboard\w*"), ("cockpit", r"\bcockpit\b|\bpilots?\b"))
CUTS = {"news": (2.0, 3.5), "fleet": (4.0, 8.0), "flight": (5.0, 15.0), "weather": (3.0, 6.0), "people": (3.0, 6.0),
        "numbers": (2.0, 3.5), "evidence": (4.0, 8.0)}      # a number line is part of the business story: it cuts like news
# (news was 1-2 s: with few real clips the same shot came back every second and the film felt frantic next to its cards)


def cut_range(mode: str) -> Tuple[float, float]:
    return CUTS.get(mode, (3.0, 6.0))


def _first(rx_list, low: str) -> str:
    for name, rx in rx_list:
        if re.search(rx, low):
            return name
    return ""


def _year(c: Any) -> str:
    if c.values.get("dates"):
        return c.values["dates"][0][:4]
    m = re.search(r"\b(19[5-9]\d|20\d\d)\b", c.text)
    return m.group(1) if m else ""


_STOP = set("""about above after again against airline airlines almost along already although always among another anything around
because before behind being below between beyond billion both cannot could didn doesn during either enough every first from
further going great having however itself just later least might million money month months more most much never other others
ought ourselves over people perhaps place plans quite rather really since something still such than that their theirs them
themselves then there these they thing things this those though three through today together under until very wasn were what
when where whether which while whole whose with within without would years year yet your described called""".split())


def _keywords(text: str, skip: str = "") -> List[str]:
    """Content words of the sentence, in order: 5+ letters, not a stop word, not part of the airline / aircraft names."""
    skipw = set(w.lower() for w in re.findall(r"[A-Za-z]+", skip))
    out: List[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", text):
        lw = w.lower()
        if lw in _STOP or lw in skipw or lw in out:
            continue
        out.append(lw)
    return out


def queries_for(c: Any, max_q: int = 3) -> List[str]:
    low = c.text.lower()
    if c.mode == "evidence":
        return []
    airline = c.airlines[0]["name"] if c.airlines else ""
    craft = c.aircraft[0]["name"] if c.aircraft else ""
    city = c.airports[0]["city"] if c.airports else ""
    phase = _first(_PHASES, low)
    event = _first(_EVENTS, low)
    out: List[str] = []

    def add(*parts: str) -> None:
        q = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
        if q and q not in out:
            out.append(q)

    if c.mode == "weather":
        kinds = [k for k, _, _ in G.weather_items(c.text)]
        if "storm" in kinds or "hail" in kinds:
            add("thunderstorm clouds", city, "airport" if city else "")
        if "rain" in kinds:
            add("heavy rain runway landing")
        if "fog" in kinds or "haze" in kinds:
            add("low visibility airport fog")
        add("storm clouds aerial timelapse")
        return out[:max_q]
    if craft:
        add(airline, craft)
        if c.mode == "fleet" and re.search(r"\bcabin|seats?\b|business class|economy", low):
            add(airline, craft, "cabin")
        add(airline, craft, phase or "takeoff")
    if c.mode == "news" and airline and event:
        add(airline, event, _year(c))
    kws = _keywords(c.text, skip=" ".join(a["name"] for a in c.airlines + c.aircraft + c.airports) + " " +
                    " ".join(a.get("city", "") for a in c.airports))
    if c.mode in ("news", "numbers") and not (airline and event) and len(kws) >= 2:
        add(airline, " ".join(kws[:3]), _year(c))
    if c.mode == "people":
        name = _person(c)
        if name:
            add(name, airline)
        elif re.search(r"\b(captain|first officer|pilots?|crew)\b", low):
            add(airline or "airline", "pilots cockpit")
    if city:
        add(city, "airport", phase)
    if airline:
        add(airline, phase or "aircraft")
    if not out and len(kws) >= 2:
        add(" ".join(kws[:3]))
    if not out:
        add("airliner", phase or "airport")
    return out[:max_q]


def _person(c: Any) -> str:
    """A person's name the sentence gives (two or more capitalised words that are not an airline, aircraft or place)."""
    taken = " ".join(a["name"] for a in c.airlines + c.aircraft + c.airports).lower()
    for m in re.finditer(r"\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+)+)\b", c.text):
        n = m.group(1)
        if n.lower() not in taken and not any(w.lower() in taken.split() for w in n.replace("-", " ").split()) and \
                n.split()[0] not in ("The", "Then", "In", "On", "At", "By", "And", "But", "So"):
            return n
    return ""


def clip_ok(clip_text: str, c: Any) -> Tuple[bool, float, str]:
    text = str(clip_text or "")
    low = text.lower()
    clip_types = {m.entry["id"] for m in C.find_aircraft(text) if m.entry}
    clip_lines = {m.entry["id"] for m in C.find_airlines(text) if m.entry}
    want_types = {a["id"] for a in c.aircraft}
    want_lines = {a["id"] for a in c.airlines}
    if want_types and not (want_types & clip_types):
        return False, 0.0, "clip does not show " + ", ".join(sorted(a["name"].replace("Airbus ", "").replace("Boeing ", "") for a in c.aircraft))
    event = _first(_EVENTS, c.text.lower())
    if c.mode == "news" and event and want_lines and not (want_lines & clip_lines):
        return False, 0.0, f"news event ({event}) of {', '.join(sorted(want_lines))}: clip is not about that airline"
    score = 1.0 + 1.0 * len(want_types & clip_types) + 2.0 * len(want_lines & clip_lines)
    if want_lines and clip_lines and not (want_lines & clip_lines):
        score -= 1.0                                           # another airline's livery: allowed, ranked lower
    if event and re.search(dict(_EVENTS)[event], low):
        score += 1.0
    words = set(re.findall(r"[a-z]{4,}", c.text.lower())) & set(re.findall(r"[a-z]{4,}", low))
    score += 0.2 * len(words)
    return True, round(score, 2), "ok"


def _hex(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def livery_score(image: Image.Image, airline_id: str, tol: float = 60.0) -> float:
    a = C.get_airline(airline_id)
    if not a or image is None:
        return 0.0
    cols = [_hex(c) for c in a.get("colors") or [] if not min(_hex(c)) > 200]       # white is every airliner: no signal
    if not cols:
        return 0.0
    import numpy as np

    im = image.convert("RGB").copy()
    im.thumbnail((64, 64))
    px = np.asarray(im, dtype=np.float32).reshape(-1, 3)
    near = np.zeros(len(px), dtype=bool)
    for col in cols:
        near |= ((px - np.asarray(col, dtype=np.float32)) ** 2).sum(axis=1) <= tol * tol
    return float(near.mean()) if len(px) else 0.0
