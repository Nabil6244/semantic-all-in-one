"""News Doc's plan: a footage-first timeline (docs/weather/news_footage_plan.md §3, §5b).

    discovery_plan(story)          every sentence a map beat: where Weather Intelligence may place the event's data graphics
    build(story, words, rows, wins, runs, ...) -> NdPlan

The timeline is a list of shots:
  map    the satellite map with the event's data, only at the strongest data moments, MAP_SHARE of the video at most, 5-10 s each,
         at least MAP_GAP_S apart (no map shot without data; if there is none at all, one short opening shot of the region,
         because the renderer needs one map start)
  news   a continuous run (5-12 s) of a local station's report about that part of the story (weather.newsdoc.harvest)
  stock  b-roll of what the line describes, when no news run is left for it
Shot lengths follow the reference: ~2.5-3.5 s in the cold open, ~4.5 s for impacts, ~6 s for explanations.

Graphics (drawn later by weather.newsdoc.graphics, composited by weather.newsdoc.finish) are scheduled on the footage, never on a
map shot, one big graphic at a time: a glitch + chapter word where a part starts; a quote card on a part's last line; a checklist
for a list of names; a navy bar chart for 2-4 numbers of one unit said together; a big number when one is said; a side panel for an
explanation; a yellow tag for a warning / agency / storm name; a place tag the first time a county or city is named."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from . import MAP_SHARE
from .story import OPENING_S, Story, word_time

MAP_GAP_S = 20.0
MAP_SHOT_S = 6.5
LOOP_SHOT_S = 9.0
LOOPS = {"radar", "satellite", "satellite_loop", "radar_loop"}
PRIORITY = {"storm_stats": 6, "hurricane_track": 6, "track": 6, "cone": 6, "storm_track": 6, "radar": 5, "warnings_archive": 5,
            "storm_reports": 5, "survey_tracks": 5, "survey": 5, "river_crest": 4, "hydrograph": 4, "rain_map": 4, "rain_total": 4,
            "snow_total": 4, "counter": 4, "record": 3, "beforeafter": 3, "timeline": 3, "explainer": 3, "storm_points": 4,
            "temp_trend": 3, "forecast_strip": 4, "current": 3, "alerts": 4, "wind_flow": 3, "post_hydrograph": 4, "post_bars": 3}
QUIET = {"source_line", "radar_legend", "alert_legend", "footage_credit"}
NOT_NEWSDOC = {"headline", "footage_credit", "hud_title", "caption"}   # Weather looks News Doc draws its own way
RIDERS = {"place_label"}   # Weather map graphics that ride along on a map shot but never start one
BIG = {"quote_card", "checklist", "chart", "number", "panel", "chapter", "ring", "line", "year", "pullquote", "nametag", "rings", "hbars",
       "dossier", "headline", "framed", "polaroids", "caption"}
FULLSCREEN = {"quote_card", "chart", "line", "rings", "hbars", "dossier", "framed", "polaroids", "forecast"}
NUMBER_GAP_S = 12.0   # big numbers at least this far apart
GAP_BIG_S = 7.0
# b-roll that shows no place (it may be filmed anywhere without misleading): a stock shot of a street, a town or a landscape
# needs proof it was filmed in the US (weather.footage_geo), so the defaults never ask for one
DEFAULT_STOCK = {"tornado": "dark rotating storm clouds", "severe": "lightning in dark storm clouds", "flood": "heavy rain falling into water close up",
                 "heavy_rain": "heavy rain falling close up", "hurricane": "heavy rain and strong wind close up", "tropical_storm": "heavy rain and strong wind close up",
                 "winter": "snow falling close up", "heat": "heat haze close up", "forecast": "dark storm clouds time lapse"}
VARIANTS = ("wide shot", "close up", "aerial view", "from the ground", "slow motion", "at dusk")


@dataclass
class Shot:
    t0: float
    t1: float
    kind: str                  # map | news | stock
    asset: str = ""            # a file (relative to the project) or "stock_video:..."
    line: int = 0
    place: str = ""
    rows: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Overlay:
    kind: str                  # glitch | chapter | quote_card | quote | checklist | chart | number | panel | ytag | place
    t0: float
    t1: float
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NdPlan:
    shots: List[Shot]
    overlays: List[Overlay]
    hybrid: Any
    rows: List[Any]
    notes: List[str] = field(default_factory=list)
    category: str = ""

    def shares(self) -> Dict[str, float]:
        total = sum(s.t1 - s.t0 for s in self.shots) or 1.0
        out = {k: round(sum(s.t1 - s.t0 for s in self.shots if s.kind == k) / total, 3) for k in ("map", "news", "stock")}
        out["fullscreen_graphics"] = round(sum(o.t1 - o.t0 for o in self.overlays if o.kind in FULLSCREEN) / total, 3)
        return out


# ---- the map moments --------------------------------------------------------------------------------------------------------

def discovery_plan(story: Story):
    """Every sentence (at least 3 s) a map beat with its place as the camera target: where the engine can see each data moment."""
    from hybrid.director import derive_cameras
    from hybrid.plan import Beat, HybridPlan

    region = story.states[0] if story.states else "United States"
    beats, cur = [], None
    for x in story.lines:
        if cur is not None and (x.span_start - cur["a"]) < 3.0:
            cur["z"], cur["text"] = x.span_end, cur["text"] + " " + x.text
            continue
        cur = {"a": x.span_start, "z": x.span_end, "text": x.text, "x": x}
        beats.append(cur)
    out = []
    for k, c in enumerate(beats):
        b = Beat(id=f"d{k + 1}", mode="map", start=round(c["a"], 3), end=round(story.duration if k == len(beats) - 1 else beats[k + 1]["a"], 3),
                 narration=c["text"])
        p = next(((q[2], q[3]) for q in c["x"].places if q[2] is not None), None)
        b.cam_place, b.cam_frame = (f"{p[0]:.2f},{p[1]:.2f}", "local") if p else ((c["x"].states or [region])[0], "region")
        out.append(b)
    plan = HybridPlan(duration=story.duration, beats=out, settings={"drift_pct_per_s": 0.0, "globe_opening": False})
    derive_cameras(plan)
    return plan


def pick_map_shots(rows, wins: Dict[str, Any], duration: float, share: float = MAP_SHARE) -> List[Dict]:
    """[{t0, t1, rows, place}]: the strongest data moments, within the budget, MAP_GAP_S apart."""
    budget = share * duration
    cands = [r for r in rows if r.type not in QUIET and r.type not in RIDERS and r.id in wins]
    cands.sort(key=lambda r: (-PRIORITY.get(r.type, 2), wins[r.id].t_in))
    shots: List[Dict] = []
    used = 0.0
    for r in cands:
        t = float(wins[r.id].t_in)
        length = LOOP_SHOT_S if r.type in LOOPS else MAP_SHOT_S
        t0 = max(0.0, t - 0.8)
        t1 = min(duration, t0 + length)
        if t1 - t0 < 4.0 or used + (t1 - t0) > budget + 1e-6:
            continue
        if any(t0 < s["t1"] + MAP_GAP_S and s["t0"] < t1 + MAP_GAP_S for s in shots):
            near = next((s for s in shots if s["t0"] - 0.5 <= t <= s["t1"] - 2.0), None)
            if near is not None:
                near["rows"].append(r.id)
            continue
        shots.append({"t0": round(t0, 3), "t1": round(t1, 3), "rows": [r.id], "place": r.place})
        used += t1 - t0
    for r in cands + [r for r in rows if r.type in RIDERS and r.id in wins]:   # graphics that arrive inside a chosen shot ride along
        for s in shots:
            if r.id not in s["rows"] and s["t0"] - 0.5 <= float(wins[r.id].t_in) <= s["t1"] - 2.0:
                s["rows"].append(r.id)
    return sorted(shots, key=lambda s: s["t0"])


# ---- footage --------------------------------------------------------------------------------------------------------------

def _target(story: Story, t: float, line) -> float:
    if t < OPENING_S:
        return 3.0
    if line is not None and line.explains:
        return 6.0
    return 4.5


def _line_at(story: Story, t: float):
    return next((x for x in story.lines if x.span_start - 1e-6 <= t < x.span_end), story.lines[-1])


def stock_request(text: str, category: str) -> str:
    from ..intel.beats import footage_request
    from ..motion import fallback_request
    from ..teamplate.cutaways import request_for

    from ..footage_geo import shows_place

    for f in (footage_request, request_for, fallback_request):
        try:
            r = f(text)
        except Exception:
            r = None
        if r and not shows_place(r):   # a request for a place (streets, towns, farmland) could only be filled from anywhere
            return r
    return DEFAULT_STOCK.get(category, "dark storm clouds time lapse")


def fill_footage(story: Story, gaps: List[tuple], runs: Sequence, notes: List[str]) -> List[Shot]:
    """Footage shots for the stretches between map shots: news runs of the part first, then stock of what the line says."""
    from .harvest import _part_hazard

    hazard = {k: _part_hazard(story, k) for k in range(len(story.parts))}   # a tornado part's b-roll is not the story's flood
    by_part: Dict[int, List] = {}
    for r in runs:
        by_part.setdefault(r.part, []).append(r)
    spare = [r for r in runs]
    used = set()
    asked: Dict[str, int] = {}
    shots: List[Shot] = []
    for a, z in gaps:
        t = a
        while z - t > 0.05:
            line = _line_at(story, t)
            pool = [r for r in by_part.get(line.part, []) if r.path not in used] or \
                   [r for r in spare if r.path not in used and (not line.states or r.place in line.states or r.part == line.part)]
            want = _target(story, t, line)
            run = pool[0] if pool and line.i > 0 else None   # the very first line opens on b-roll / the region, like the reference
            if run is not None:
                length = min(run.dur, z - t, 12.0 if t >= OPENING_S else 5.0)
            else:
                length = min(want, z - t)
            if z - (t + length) < 1.5:      # never leave a sliver: this shot takes it
                length = z - t
            if length < 1.2 and shots:
                shots[-1].t1 = round(z, 3)
                break
            if run is not None and length >= 3.0:
                used.add(run.path)
                shots.append(Shot(round(t, 3), round(t + length, 3), "news", run.path, line.i, run.place,
                                  meta={"title": run.title, "channel": run.channel, "url": run.url, "source_start": run.start}))
            else:
                req = stock_request(line.text, hazard.get(line.part, story.category))
                k = asked.get(req, 0)
                asked[req] = k + 1
                ask = req if k == 0 else f"{req}, {VARIANTS[(k - 1) % len(VARIANTS)]}"
                shots.append(Shot(round(t, 3), round(t + length, 3), "stock", f"stock_video:{ask}", line.i))
            t += length
    return shots


# ---- graphics ---------------------------------------------------------------------------------------------------------------

def _free(shots: List[Shot], a: float, b: float) -> bool:
    return not any(s.kind == "map" and s.t0 < b and a < s.t1 for s in shots)


TAG_MIN_S = 2.2


def _slot(shots: List[Shot], t0: float, length: float, latest: float, earliest: Optional[float] = None) -> Optional[float]:
    """t0; or, when a map shot is on screen then, just before it (not before `earliest`, the line's start) or right after it while the
    line is still being said; None when nothing fits."""
    if _free(shots, t0, t0 + length):
        return t0
    hit = [s for s in shots if s.kind == "map" and s.t0 < t0 + length and t0 < s.t1]
    if hit:
        before = min(s.t0 for s in hit) - length - 0.1
        if earliest is not None and before < earliest and min(s.t0 for s in hit) - 0.1 - earliest >= TAG_MIN_S:
            before = earliest   # a shorter stay before the map comes in (the tag leaves as the map cuts in)
        if earliest is not None and before >= earliest and _free(shots, before, min(before + length, min(s.t0 for s in hit) - 0.1)):
            return before
        end = max(s.t1 for s in hit)
        if end + 0.3 <= latest and _free(shots, end + 0.3, end + 0.3 + length):
            return end + 0.3
    return None


CHART_UNITS = {"FEET", "INCHES", "%", "WARNINGS", "TORNADOES", "STORM REPORTS"}
STOP = {"of", "at", "to", "was", "is", "are", "were", "the", "a", "an", "near", "about", "around", "with", "up", "by", "from", "on",
        "its", "it", "and", "now", "this", "that", "be", "will", "reach", "reached", "rise", "rising", "fall", "falling", "than", "more",
        "less", "over", "under", "nearly", "almost", "just", "still", "set", "for", "in"}


LABEL_KEYS = ("previous crest", "record crest", "river stage", "flood stage", "major flood", "moderate flood", "minor flood", "crest", "record", "forecast",
              "peak", "total", "normal", "level", "stage", "now")


def _label_before(text: str, said: str) -> str:
    """The bar's label: a measuring word next to the number ('the 14.0-foot flood stage' -> 'FLOOD STAGE'), else up to two meaningful
    words just before it."""
    first = said.split()[0] if said.split() else ""
    k = text.find(first) if first else -1
    if k >= 0:
        near = " ".join(re.findall(r"[A-Za-z]+", text[:k]).__getitem__(slice(-5, None)) + re.findall(r"[A-Za-z]+", text[k + len(first):])[:4]).lower()
        for key in LABEL_KEYS:
            if re.search(r"\b" + key + r"\b", near):
                return key.upper()
    head = text[:k] if k >= 0 else ""
    words = [w for w in re.findall(r"[A-Za-z]+", head)]
    keep = []
    for w in reversed(words):
        if w.lower() in STOP:
            if keep:
                break
            continue
        keep.insert(0, w)
        if len(keep) == 2:
            break
    return " ".join(keep).upper()[:18] or said.upper()[:18]


def _until_map(shots: List[Shot], t0: float, t1: float) -> float:
    """A tag leaves as a map shot cuts in."""
    nxt = min((s.t0 for s in shots if s.kind == "map" and t0 < s.t0 < t1), default=None)
    return t1 if nxt is None else nxt - 0.1


HAZARD_NOUNS = {"wind", "winds", "hail", "lightning", "rain", "flooding", "floods", "tornadoes", "tornado", "snow", "ice", "sleet", "heat",
                "surge", "storms", "thunderstorms", "damage", "outages", "debris", "erosion", "waves", "fog", "smoke", "cold"}


def _three_hazards(text: str) -> List[str]:
    """'wind, hail and lightning' -> the three (a list of exactly three weather words), else []."""
    m = re.search(r"\b([a-z]+),\s+([a-z]+),?\s+and\s+([a-z]+)\b", text)
    return [m.group(i) for i in (1, 2, 3)] if m and all(m.group(i) in HAZARD_NOUNS for i in (1, 2, 3)) else []


def _stills(shots: List[Shot], part_line_part: int, n: int) -> List[float]:
    """Times of footage moments to take stills from for a framed picture / polaroids: news shots of the story first."""
    pool = [s for s in shots if s.kind == "news"] + [s for s in shots if s.kind == "stock"]
    seen, out = set(), []
    for s in pool:
        if s.asset in seen:
            continue
        seen.add(s.asset)
        out.append(round((s.t0 + s.t1) / 2, 2))
        if len(out) == n:
            break
    return out


def _day_after(text: str, said: str) -> str:
    """'6.7 feet on Monday' -> 'MONDAY'."""
    first = said.split()[0] if said.split() else ""
    k = text.find(first)
    m = re.match(r"[^.;]{0,20}?\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|today|tonight|tomorrow)\b",
                 text[k + len(first):]) if k >= 0 else None   # after the number ('6.7' has a dot of its own)
    return m.group(1).upper() if m else ""


def _label_after(text: str, said: str) -> str:
    """The words that say what a percent is ('a 70 percent chance of rain' -> 'CHANCE OF RAIN')."""
    first = said.split()[0] if said.split() else ""
    k = text.find(first)
    tail = re.findall(r"[A-Za-z]+", text[k + len(first):]) if k >= 0 else []
    tail = [w for w in tail if w.lower() not in ("percent", "per", "cent")][:4]
    while tail and tail[-1].lower() in STOP:
        tail.pop()
    return " ".join(tail).upper()[:28]


def _red_phrase(text: str) -> str:
    """The words a quote card boxes in red: the line's last 2-4 words (where the reference puts its point)."""
    words = re.sub(r"[.!?…]+$", "", text.strip()).split()
    n = 3 if len(words) > 6 else 2
    return " ".join(words[-n:])


def schedule(story: Story, words: Sequence, shots: List[Shot], notes: List[str]) -> List[Overlay]:
    out: List[Overlay] = []
    big_until = -1e9
    last_kind = ""
    seen_places, seen_yellow = set(), set()
    last_chart = last_panel = -1e9
    part_last = {}
    for x in story.lines:
        part_last[x.part] = x.i
    last_glitch = -1e9
    last_at: Dict[str, float] = {}
    dossier_done = False
    pending = None
    quotes_made = 0

    def room(b: float) -> bool:   # time left in this sentence after the graphic already on screen
        return big_until + 0.3 <= b - 2.0
    u = getattr(story, "understanding", None)
    event_day = next((d.day for d in getattr(u, "dates", []) if d.day and not getattr(d, "reference", False)), "")
    starts = {first: (k, title) for k, (first, title) in enumerate(story.parts) if k > 0}
    for x in story.lines:
        a, b = x.span_start, x.span_end
        dur = b - a
        made = None
        if x.i in starts:   # a new part: glitch over the cut, then its chapter word
            _k, title = starts[x.i]
            if a - last_glitch >= 100.0 and _free(shots, a - 0.3, a + 0.4):
                out.append(Overlay("glitch", round(a - 0.12, 3), round(a + 0.3, 3)))
                last_glitch = a
            for k_, o in enumerate(out):   # what is still on screen leaves as the new part comes in
                if o.t1 > a - 0.05 and o.kind not in ("glitch",):
                    out[k_] = Overlay(o.kind, o.t0, round(max(o.t0 + 0.5, a - 0.05), 3), o.params)
            out[:] = [o for o in out if o.t1 - o.t0 >= 1.5 or o.kind == "glitch"]
            big_until = min(big_until, a)
            if title and _free(shots, a + 0.15, a + 2.6):   # the reference alternates a big chapter word and a small caption
                kind = "chapter" if _k % 2 == 1 else "caption"
                out.append(Overlay(kind, round(a + 0.15, 3), round(a + (2.6 if kind == "chapter" else 3.4), 3),
                                   {"text": " ".join(title.split()[:3]) if kind == "chapter" else title}))
                big_until, last_kind = a + 2.6, kind
        clock = re.search(r"\b(\d{1,2}:\d{2}\s?[AP]\.?M\.?)", x.text)
        if x.yellow and clock and room(b) and a - last_at.get("headline", -1e9) >= 40.0:
            t0 = _slot(shots, max(a + 0.3, big_until + 0.3), 4.2, b + 3.0, a)
            if t0 is not None and _free(shots, t0, t0 + 4.2):
                where = ", ".join(([p[0] for p in x.places] + x.states)[:2])
                out.append(Overlay("headline", round(t0, 3), round(t0 + 4.2, 3),
                                   {"title": f"{x.yellow[-1].upper()} ISSUED", "sub": " · ".join(v for v in (where, clock.group(1)) if v)}))
                big_until, last_at["headline"] = t0 + 4.2, t0
        if not dossier_done and x.yellow and a < 120.0 and pending is None:
            pending = (next((y for y in x.yellow if not y.startswith("National")), x.yellow[0]), x)
        d0 = next((t for t in [max(a + 0.2, big_until + 0.3)] + sorted(s.t1 + 0.2 for s in shots if s.kind == "map" and a < s.t1 < a + 40.0)
                   if t >= big_until + 0.3 and t + 4.4 <= b + 3.0 and _free(shots, t, t + 4.4)), None) if pending and a < 150.0 else None
        if d0 is not None:   # the event's case file, in the first free moment after it is named
            name, x0 = pending   # the event, not the agency
            dossier = Overlay("dossier", round(d0, 3), round(d0 + 4.4, 3),
                           {"title": name.upper(), "fields": [("EVENT", name), ("DATE", event_day or "—"),
                                                               ("AREA", ", ".join(([p[0] for p in x0.places] + x0.states)[:2]) or "—"),
                                                               ("STATUS", "UNDER REVIEW" if "Warning" not in name else "WARNING ISSUED")]})
            dossier_done, pending = True, None
            out.append(dossier)
            big_until = dossier.t1
        pair = re.search(r"\btwo (types|kinds|ways|sides|threats|problems)\b", x.text, re.I)
        if made is None and pair and room(b) and _free(shots, a, a + 5.0):
            stills = _stills(shots, x.part, 2)
            after = x.text.split(pair.group(0), 1)[-1]
            after = after.split(":", 1)[1] if ":" in after else after
            labels = [w.strip(" .").upper() for w in re.split(r",|\band\b|\bor\b", after) if w.strip(" .")][:2]
            if len(stills) == 2 and len(labels) == 2:
                made = Overlay("polaroids", round(a + 0.1, 3), round(a + 5.1, 3), {"title": pair.group(0).upper(), "labels": labels, "still_t": stills})
        if made is None and x.places and room(b) and a - last_at.get("framed", -1e9) >= 90.0:
            under = [s for s in shots if s.t0 < a + 4.5 and a < s.t1]
            stills = _stills(shots, x.part, 1)
            if stills and under and all(s.kind != "news" for s in under) and _free(shots, a, a + 4.5):
                made = Overlay("framed", round(a + 0.1, 3), round(a + 4.6, 3), {"caption": x.places[0][0].upper(), "still_t": stills})
        if made is None and x.i == part_last.get(x.part) and x.i > 0:   # the last line of each part (the story's last line too)
            if 6 <= x.words <= 26 and not x.numbers and dur >= 2.5 and room(b) and _free(shots, a, b):
                kind = "quote_card" if quotes_made % 2 == 0 else "quote"
                quotes_made += 1
                made = Overlay(kind, round(a + 0.05, 3), round(min(b, a + 8.0), 3), {"text": x.text, "red": _red_phrase(x.text)})
        if made is None and x.items and room(b) and dur >= 2.5:
            t0 = (word_time(words, a, b, x.items[0]) or a + 0.3) - 0.6
            t0 = _slot(shots, t0, 4.0, b - 2.0, a) if t0 is not None else None
            t1 = min(max(b + 0.5, (t0 or 0) + 4.0), (t0 or 0) + 8.0)
            if t0 is not None and _free(shots, t0, t1):
                title = (story.parts[x.part][1] or "IN THE PATH")
                made = Overlay("checklist", round(t0, 3), round(t1, 3), {"title": title, "items": x.items[:6]})
        days_said = len(re.findall(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|today|tonight|tomorrow)\b", x.text))
        if made is None and days_said < 3 and len([n for n in x.numbers if n.label in CHART_UNITS]) >= 2 and room(b) and a - last_chart >= 6.0:
            units = [n.label for n in x.numbers if n.label in CHART_UNITS]
            top = max(set(units), key=units.count)
            same = [n for n in x.numbers if n.label == top][:4]
            if len(same) >= 2 and top and _free(shots, a, min(b, a + 7.0) + 0.3):
                labels = [_label_before(x.text, n.text) for n in same]
                made = Overlay("hbars" if len(same) >= 3 else "chart", round(a + 0.05, 3), round(max(a + 4.0, min(b, a + 7.0)), 3),
                               {"title": (story.parts[x.part][1] or top), "unit": top, "values": [n.value for n in same],
                                "shown": [n.shown for n in same], "labels": labels})
                last_chart = a
        pct = next((n for n in x.numbers if n.shown.endswith("%")), None)
        if made is None and pct is not None and room(b) and a - last_at.get("ring", -1e9) >= 30.0:
            t0 = _slot(shots, (word_time(words, a, b, pct.text) or a + 0.3) - 0.1, 4.0, b, a)
            if t0 is not None:
                made = Overlay("ring", round(t0, 3), round(t0 + 4.0, 3), {"value": pct.value, "label": _label_after(x.text, pct.text)})
        series = [n for n in x.numbers if n.label in ("FEET", "INCHES", "°F", "MPH")]
        if made is None and len({n.label for n in series}) == 1 and len(series) >= 3 and days_said >= 2 and room(b) and a - last_chart >= 6.0 \
                and _free(shots, a, min(b, a + 7.0) + 0.3):
            made = Overlay("line", round(a + 0.05, 3), round(max(a + 4.5, min(b, a + 7.0)), 3),
                           {"title": (story.parts[x.part][1] or series[0].label), "unit": series[0].label, "values": [n.value for n in series[:6]],
                            "shown": [n.shown for n in series[:6]],
                            "labels": [(_day_after(x.text, n.text) or _label_before(x.text, n.text)) for n in series[:6]]})
            last_chart = a
        year = next((m for m in re.finditer(r"\b(19[5-9]\d|20\d\d)\b", x.text)   # a year said on its own, never one inside a date
                     if not re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December|"
                                      r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2}(st|nd|rd|th)?,?\s*$",
                                      x.text[:m.start()])), None)
        if made is None and year and room(b) and a - last_at.get("year", -1e9) >= 45.0:
            t0 = _slot(shots, (word_time(words, a, b, year.group(1)) or a + 0.3) - 0.1, 3.0, b, a)
            if t0 is not None:
                made = Overlay("year", round(t0, 3), round(t0 + 3.0, 3), {"text": year.group(1)})
        quoted = re.search(r"[\"“]([^\"”]{20,160})[\"”]", x.text)
        if made is None and quoted and room(b) and _free(shots, a, min(b, a + 6.0)):
            who = re.search(r"\b(?:said|says|according to)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)", x.text)
            role = re.search(r"said\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)+,\s+(?:the\s+|a\s+)?([a-z][a-z ]{3,40}?)(?:[,.]|$)", x.text)
            made = Overlay("pullquote", round(a + 0.1, 3), round(min(b, a + 6.0), 3),
                           {"text": quoted.group(1), "who": who.group(1) if who else "", "role": role.group(1).upper() if role else ""})
        person = re.search(r"\b(?:said|says)\s+([A-Z][a-z]+\s[A-Z][a-z]+)(?:,\s+(?:the\s+|a\s+)?([a-z][a-z ]{3,40}?)(?:[,.]|$))?", x.text)
        if made is None and person and not quoted and room(b) and _free(shots, a, a + 3.5):
            made = Overlay("nametag", round(a + 0.2, 3), round(a + 3.7, 3), {"name": person.group(1).upper(), "role": (person.group(2) or "").upper()})
        three = x.items if len(x.items) == 3 and all(len(i.split()) <= 2 for i in x.items) else _three_hazards(x.text)
        if made is None and three and room(b) and _free(shots, a, a + 4.0):
            made = Overlay("rings", round(a + 0.1, 3), round(a + 4.1, 3), {"items": [i.upper() for i in three]})
        if made is None and x.numbers and room(b) and a - last_at.get("number", -1e9) >= NUMBER_GAP_S:
            n = x.numbers[0]
            t0 = (word_time(words, a, b, n.text) or a + 0.3) - 0.1
            if _free(shots, t0, t0 + 3.4):
                made = Overlay("number", round(t0, 3), round(t0 + 3.4, 3), {"value": n.value, "shown": n.shown, "label": n.label,
                                                                           "corner": n.label in ("MPH", "FEET", "INCHES", "MILES")})
        p0 = max(a, big_until + 0.3)
        if made is None and x.explains and a - last_panel >= 150.0 and room(b) and _free(shots, p0, min(b, p0 + 6.0)):
            parts = [p.strip(" ,.") for p in re.split(r",|;|\bbecause\b|\bwhich means\b|\bthat means\b|\band\b", x.text) if len(p.split()) >= 3]
            if parts:
                made = Overlay("panel", round(p0 + 0.1, 3), round(max(p0 + 4.0, min(b, p0 + 8.0)), 3),
                               {"title": (story.parts[x.part][1] or "WHY IT MATTERS"), "bullets": parts[:3]})
                last_panel = a
        if made is not None and made.t0 < big_until + 0.3:
            shift = big_until + 0.3 - made.t0
            made = Overlay(made.kind, round(made.t0 + shift, 3), round(made.t1 + shift, 3), made.params)
            if not _free(shots, made.t0, made.t1):
                made = None
        if made is not None and made.kind == "pullquote" and made.params.get("who") and _free(shots, made.t1 + 0.1, made.t1 + 3.6):
            out.append(made)   # the speaker's name tag right after the quote
            big_until = made.t1
            made = Overlay("nametag", round(made.t1 + 0.1, 3), round(made.t1 + 3.6, 3), {"name": made.params["who"].upper(), "role": made.params.get("role", "")})
        if made is not None:
            out.append(made)
            big_until, last_kind = made.t1, made.kind
            last_at[made.kind] = made.t0
            if made.kind in FULLSCREEN:
                continue
        for y in (x.yellow if made is not None else []):   # top-left: beside a graphic that is not full screen
            if y.lower() in seen_yellow or y.startswith("National"):
                continue
            t0 = _slot(shots, (word_time(words, a, b, y) or a + 0.2) - 0.1, 3.2, b - 1.0, a)
            if t0 is not None:
                out.append(Overlay("ytag", round(t0, 3), round(_until_map(shots, t0, t0 + 3.2), 3), {"text": y.upper()}))
                seen_yellow.add(y.lower())
                break
        if made is not None:
            continue
        for y in x.yellow:   # tags: small, may come between big graphics
            if y.lower() in seen_yellow:
                continue
            t0 = _slot(shots, (word_time(words, a, b, y) or a + 0.2) - 0.1, 3.2, b - 1.0, a)
            if t0 is not None and t0 >= big_until:
                out.append(Overlay("ytag", round(t0, 3), round(_until_map(shots, t0, t0 + 3.2), 3), {"text": y.upper()}))
                seen_yellow.add(y.lower())   # top-left: it may share the screen with a place tag (bottom-left)
                break
        for name, kind, _lat, _lon in x.places:
            if name in seen_places:
                continue
            t0 = _slot(shots, (word_time(words, a, b, name) or a + 0.2) - 0.1, 3.6, b - 1.0, a)
            under = [s for s in shots if t0 is not None and s.t0 < t0 + 3.6 and t0 < s.t1]
            if under and any(s.kind != "news" for s in under):   # a place tag over b-roll would say the b-roll shows that place
                continue
            if t0 is not None and t0 >= big_until - 0.6:
                sub = x.place_state.get(name) or (x.states or story.states or [""])[0]
                out.append(Overlay("place", round(t0, 3), round(_until_map(shots, t0, t0 + 3.6), 3), {"name": name.upper(), "sub": sub.upper()}))
                seen_places.add(name)
                break
    out.sort(key=lambda o: o.t0)
    return out


# ---- the plan for the renderer ---------------------------------------------------------------------------------------------

def build(story: Story, words: Sequence, rows: List[Any], wins: Dict[str, Any], runs: Sequence, *, notes: Optional[List[str]] = None,
          share: float = MAP_SHARE) -> NdPlan:
    from hybrid.director import derive_cameras
    from hybrid.plan import Beat, Clip, HybridPlan

    notes = notes if notes is not None else []
    dur = story.duration
    picks = pick_map_shots(rows, wins, dur, share)
    region = story.states[0] if story.states else "United States"
    if not picks:   # the renderer needs one map start: a short opening "where", the region
        picks = [{"t0": 0.0, "t1": min(3.5, dur), "rows": [], "place": region}]
        notes.append("News Doc: no data graphic was found for a map shot, so the map is only a 3.5 s opening of the region")
    shots: List[Shot] = []
    gaps, t = [], 0.0
    for p in picks:
        if p["t0"] - t > 0.05:
            gaps.append((t, p["t0"]))
        t = p["t1"]
    if dur - t > 0.05:
        gaps.append((t, dur))
    shots += [Shot(p["t0"], p["t1"], "map", line=_line_at(story, p["t0"]).i, place=p["place"], rows=list(p["rows"])) for p in picks]
    shots += fill_footage(story, gaps, runs, notes)
    shots.sort(key=lambda s: s.t0)
    # never a gap or an overlap: each shot ends where the next starts
    for k in range(len(shots) - 1):
        shots[k].t1 = shots[k + 1].t0
    shots[-1].t1 = dur
    shots = [s for s in shots if s.t1 - s.t0 > 0.05]
    beats = []
    by_id = {r.id: r for r in rows}
    final_rows = []
    for k, s in enumerate(shots):
        bid = f"n{k + 1}"
        line = story.lines[s.line]
        if s.kind == "map":
            b = Beat(id=bid, mode="map", start=s.t0, end=s.t1, narration=line.text, purpose="map", cam_move="push_in")
            row_place = next((by_id[r].place for r in s.rows if r in by_id and by_id[r].place), "")
            loc = next(((q[2], q[3]) for q in line.places if q[2] is not None), None)
            if loc:
                b.cam_place, b.cam_frame = f"{loc[0]:.2f},{loc[1]:.2f}", "local"
            else:
                b.cam_place, b.cam_frame = (row_place if row_place and "," not in row_place else (line.states or [region])[0]), "region"
            for rid in s.rows:
                r = by_id.get(rid)
                if r is None:
                    continue
                r.beat, r.vo_anchor, r.t = bid, "", None
                final_rows.append(r)
            if s.rows:
                for r in rows:   # their source lines and legends go with them
                    if r.type in QUIET and r not in final_rows and r.id in wins and s.t0 - 0.5 <= wins[r.id].t_in <= s.t1:
                        r.beat, r.vo_anchor, r.t = bid, "", None
                        final_rows.append(r)
        else:
            b = Beat(id=bid, mode="footage", start=s.t0, end=s.t1, narration=line.text, purpose=s.kind,
                     clips=[Clip(asset=s.asset, reason="News Doc: " + ("news footage of the event" if s.kind == "news" else "b-roll of what is said"))],
                     footage_intent="show what the narration describes")
        beats.append(b)
    plan = HybridPlan(duration=dur, beats=beats, settings={"drift_pct_per_s": 0.0, "dissolve_s": round(1.0 / 30.0, 4), "globe_opening": False,
                                                          "return_grace_s": 0.0, "cover_ui": True})
    # cover_ui: footage covers the screen, so the renderer draws the map only while a map shot is on screen (pure footage frames are
    # copied straight from the clip: pakmap-engine/lib/footage_pass.mjs)
    derive_cameras(plan)
    overlays = schedule(story, words, shots, notes)
    overlays = ensure_all(story, words, shots, overlays, notes)
    return NdPlan(shots, overlays, plan, final_rows, notes, story.category)


# ---- every graphic, every video ---------------------------------------------------------------------------------------------

REQUIRED = ("dossier", "headline", "place", "orange_place", "ytag", "number", "year", "ring", "chart", "hbars", "line", "forecast",
            "checklist", "rings", "panel", "pullquote", "nametag", "quote_card", "quote", "chapter", "caption", "glitch", "framed",
            "polaroids")
LENGTH = {"dossier": 4.4, "headline": 4.2, "place": 3.4, "orange_place": 3.4, "ytag": 3.2, "number": 3.4, "year": 3.0, "ring": 4.0,
          "chart": 5.0, "hbars": 5.0, "line": 5.5, "forecast": 5.0, "checklist": 5.0, "rings": 4.0, "panel": 4.0, "pullquote": 4.5,
          "nametag": 3.5, "quote_card": 5.0, "quote": 5.0, "chapter": 2.5, "caption": 3.4, "glitch": 0.42, "framed": 4.5, "polaroids": 5.0}


def _all_numbers(story: Story):
    return [(x, n) for x in story.lines for n in x.numbers]


def _content(kind: str, story: Story, shots: List[Shot], t: float) -> Optional[Dict[str, Any]]:
    """What a missing graphic shows, taken from the story itself (said numbers, places, sentences) — never invented."""
    nums = _all_numbers(story)
    line_at = _line_at(story, t)
    places = [p[0] for x in story.lines for p in x.places] + story.states
    title = next((tt for _i, tt in story.parts if tt), story.category.replace("_", " ").upper() or "THE STORM")
    by_unit: Dict[str, list] = {}
    for x, n in nums:
        if n.label:
            by_unit.setdefault(n.label, []).append((x, n))
    big_unit = max(by_unit.values(), key=len) if by_unit else []
    if kind == "number" and nums:
        x, n = nums[0]
        return {"value": n.value, "shown": n.shown, "label": n.label, "corner": False}
    if kind == "year":
        m = next((m for x in story.lines for m in re.finditer(r"\b(19[5-9]\d|20\d\d)\b", x.text)), None)
        return {"text": m.group(1)} if m else None
    if kind == "ring":
        pct = next((n for _x, n in nums if n.shown.endswith("%")), None)
        if pct:
            return {"value": pct.value, "label": "CHANCE"}
        if len(big_unit) >= 2:   # derived from two said amounts: how far the larger is above the smaller
            hi, lo = max(n.value for _x, n in big_unit), min(n.value for _x, n in big_unit)
            if lo > 0 and hi > lo:
                return {"value": min(100.0, round((hi - lo) / lo * 100)), "label": f"ABOVE {lo:g} {big_unit[0][1].label}"}
        return None
    if kind in ("chart", "hbars", "line", "forecast") and len(big_unit) >= (2 if kind == "chart" else 3):
        sel = big_unit[:6]
        labels = [(_day_after(x.text, n.text) or _label_before(x.text, n.text)) for x, n in sel]
        d = {"title": title, "unit": sel[0][1].label, "values": [n.value for _x, n in sel], "shown": [n.shown for _x, n in sel], "labels": labels}
        if kind == "chart":
            d.update(values=d["values"][:2], shown=d["shown"][:2], labels=labels[:2])
        if kind == "forecast":   # only values said with their day ('6.7 feet on Monday'), under that part's title
            dated = [(x, n, _day_after(x.text, n.text)) for x, n in sel if _day_after(x.text, n.text)]
            if len(dated) < 2:
                return None
            d = {"title": story.parts[dated[0][0].part][1] or title, "days": [dd for _x, _n, dd in dated][:5],
                 "values": [n.shown for _x, n, _dd in dated][:5], "unit": dated[0][1].label}
        return d
    if kind in ("place", "orange_place") and places:
        return {"name": places[0].upper(), "sub": (story.states or [""])[0].upper()}
    if kind == "ytag":
        y = next((y for x in story.lines for y in x.yellow if not y.startswith("National")), None)
        return {"text": (y or title).upper()}
    if kind == "headline":
        y = next((y for x in story.lines for y in x.yellow), None)
        return {"title": (f"{y.upper()} ISSUED" if y else title), "sub": ", ".join(places[:2])}
    if kind == "dossier":
        u = getattr(story, "understanding", None)
        day = next((d.day for d in getattr(u, "dates", []) if d.day and not getattr(d, "reference", False)), "")
        return {"title": title, "fields": [("EVENT", title), ("DATE", day or "—"), ("AREA", ", ".join(places[:2]) or "—"),
                                           ("TYPE", story.category.replace("_", " ").upper())]}
    if kind == "checklist":
        items = list(dict.fromkeys(places))[:5]
        return {"title": "IN THE PATH", "items": items} if len(items) >= 2 else None
    if kind == "rings":
        u = getattr(story, "understanding", None)
        three = [h.replace("_", " ").upper() for h in getattr(u, "hazards", [])][:3]
        if len(three) < 3:
            three = list(dict.fromkeys(three + [p.upper() for p in places]))[:3]
        return {"items": three} if len(three) == 3 else None
    if kind == "panel":
        src = next((x for x in story.lines if x.explains), line_at)
        bullets = [p.strip(" ,.") for p in re.split(r",|;|\bbecause\b|\band\b", src.text) if len(p.split()) >= 3][:3] or [src.text[:80]]
        return {"title": story.parts[src.part][1] or "WHY IT MATTERS", "bullets": bullets}
    if kind in ("pullquote", "quote", "quote_card"):
        src = next((x for x in reversed(story.lines) if 6 <= x.words <= 26 and not x.numbers), line_at)
        return {"text": src.text, "who": "", "red": _red_phrase(src.text)}
    if kind == "nametag":
        who = next((m for x in story.lines for m in re.finditer(r"\b(?:said|says)\s+([A-Z][a-z]+\s[A-Z][a-z]+)", x.text)), None)
        if who:
            return {"name": who.group(1).upper(), "role": ""}
        agency = next((y for x in story.lines for y in x.yellow if y.startswith("National")), "")
        return {"name": (agency or "NATIONAL WEATHER SERVICE").upper(), "role": "SOURCE"}
    if kind in ("chapter", "caption"):
        return {"text": " ".join(line_at.text.split()[:3]).upper() if kind == "chapter" else title}
    if kind == "glitch":
        return {}
    if kind in ("framed", "polaroids"):
        stills = _stills(shots, 0, 2 if kind == "polaroids" else 1)
        if kind == "framed" and stills:
            return {"caption": (places[0] if places else title).upper(), "still_t": stills}
        if kind == "polaroids" and len(stills) == 2:
            parts = [tt for _i, tt in story.parts if tt][:2] or ["BEFORE", "AFTER"]
            return {"title": "TWO SIDES OF THE STORM", "labels": (parts + ["AFTER"])[:2], "still_t": stills}
    return None


def ensure_all(story: Story, words: Sequence, shots: List[Shot], overlays: List[Overlay], notes: List[str]) -> List[Overlay]:
    """Every News Doc graphic in every video (the owner's rule): each kind the schedule did not place is built from the story and put
    in the first free footage moment (a place tag may sit on a map shot: the map shows that place). Graphics never overlap, except a
    tag beside a graphic that is not full screen. A kind with nothing in the story to show is named in the notes."""
    out = sorted(overlays, key=lambda o: o.t0)
    have = {o.kind for o in out}
    small = {"place", "orange_place", "ytag", "glitch"}

    def busy(a: float, b: float, kind: str) -> bool:
        for o in out:
            if o.t0 < b and a < o.t1 and (kind not in small or o.kind in FULLSCREEN or o.kind in small):
                return True
        under = [s for s in shots if s.t0 < b and a < s.t1]
        if kind in ("place", "orange_place"):   # a place name only over the map of it or news footage of it, never over b-roll
            return not under or any(s.kind == "stock" for s in under)
        return any(s.kind == "map" for s in under)

    missing = [k for k in REQUIRED if k not in have]
    for kind in missing:
        length = LENGTH[kind]
        t = 2.0
        placed = False
        while t + length < story.duration - 0.5:
            if not busy(t, t + length, kind):
                params = _content(kind, story, shots, t)
                if params is None:
                    break
                out.append(Overlay(kind, round(t, 3), round(t + length, 3), params))
                out.sort(key=lambda o: o.t0)
                placed = True
                break
            t += 0.5
        if not placed:   # no free moment: it takes the place of a repeat (a kind already shown before)
            counts = {k: sum(1 for o in out if o.kind == k) for k in {o.kind for o in out}}
            spare = next((o for o in out if counts.get(o.kind, 0) >= 2 and o.kind not in small and o.t1 - o.t0 >= min(length, 3.5)
                          and not any(sh.kind == "map" and sh.t0 < o.t1 and o.t0 < sh.t1 for sh in shots)), None)
            params = _content(kind, story, shots, spare.t0) if spare is not None else None
            if spare is not None and params is not None:
                out[out.index(spare)] = Overlay(kind, spare.t0, round(min(spare.t1, spare.t0 + max(length, 3.5)), 3), params)
                placed = True
        if not placed:   # last resort: the longest graphic on screen gives its second half
            long_ = max((o for o in out if o.t1 - o.t0 >= 6.0 and o.kind not in small
                         and not any(sh.kind == "map" and sh.t0 < o.t1 and o.t0 < sh.t1 for sh in shots)), key=lambda o: o.t1 - o.t0, default=None)
            params = _content(kind, story, shots, long_.t0) if long_ is not None else None
            if long_ is not None and params is not None:
                mid = round((long_.t0 + long_.t1) / 2, 3)
                out[out.index(long_)] = Overlay(long_.kind, long_.t0, mid, long_.params)
                out.append(Overlay(kind, round(mid + 0.05, 3), long_.t1, params))
                out.sort(key=lambda o: o.t0)
                placed = True
        if not placed:
            notes.append(f"News Doc: the {kind} graphic has nothing in this story to show (or no free moment), so it is not in this video")
    return out
