"""Aviation planner (docs/aviation/PLAN.md section 2 + 5): timed narration (+ optional CSV rows) -> a timeline of shots.

    plan(scenes, rows=None) -> Plan(shots, modes, log)

scene = {scene_no, text, start, end}; rows = aviation.csv_rows.read_rows output in the same order (optional).
A shot is either
    {"kind": "footage", start, end, scene, mode, queries, cut}           a slot the footage director fills (clip_ok rules)
    {"layer": "<module>.<fn>", start, end, scene, params, full_frame}    an aviation (or War) card drawn over / instead of footage

How the modes become pictures
  smoothing   a lone line whose mode differs from both neighbours (which agree) and that scored weakly (< STRONG) takes theirs
  news        footage slots of 1-2 s (the burst); a card breaks the burst: the CSV's article card where given, else a fact strip
              with the narration's own sentence on a line that holds a number - never in the first OPEN_S of a news stretch (cold
              open is clips) and at most one per CARD_GAP_S
  flight /    one continuous dark map for the whole stretch (airports named in it, the route when a line names two airports in order
  weather     or the CSV gives from/to, holding loops when a line says hold/orbit, storms on weather lines, distance callouts);
              the HUD (time/fuel/altitude) per line from hud_plan; radio lines; weather icons; crew counters. A map longer than
              MAX_MAP_S is split by a short footage break and carries on (t0/total), never restarted
  fleet       footage slots of 4-8 s (beauty shots of the named type)
  people      footage slots of 3-6 s + crew counters when the line counts people
  numbers     a fact card (the sentence) on the blue backdrop
  evidence    the War document card: the sentence typeset, the reported clause highlighted
  end         'This is the story of X' -> the next-episode end card
Nothing is invented: card text is the narration's or the CSV's words; values come from the router.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from . import catalog as C
from . import footage as FT
from . import gfx as G
from . import hud as U
from . import router as R

STRONG = 3.0
MAP_MODES = ("flight", "weather")
MAX_MAP_S = 30.0
PLACE_MAP_S = 7.0             # a place map (no flight sequence): its routes are drawn by then; the rest of the line goes to footage
BREAK_S = 4.0
OPEN_S = 6.0
CARD_GAP_S = 10.0             # never two cards closer than this
CARD_EVERY_S = 16.0           # after this long without a card, any line that names something may carry one
CARD_MAX_S = 5.0              # a blue card holds 4-6 s in the reference; the rest of a long sentence goes back to clips
_HOLD = re.compile(r"\b(hold|holding|orbit|orbits|racetrack)\b", re.I)
_END = re.compile(r"\bstory of\s+((?:[A-Z][\w\-']*|\d+)(?:\s+(?:[A-Z][\w\-']*|\d+))*)")


@dataclass
class Plan:
    shots: List[Dict[str, Any]] = field(default_factory=list)
    modes: List[str] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)
    retention: Dict[str, Any] = field(default_factory=dict)
    balance: Dict[str, Any] = field(default_factory=dict)


def _row(rows: Optional[Sequence[dict]], i: int) -> dict:
    return dict(rows[i]) if rows and i < len(rows) and rows[i] else {}


def _smooth(cls: List[Any], modes: List[str], forced: List[bool]) -> List[str]:
    out = list(modes)
    for i in range(1, len(modes) - 1):
        if forced[i] or out[i - 1] != out[i + 1] or out[i] == out[i - 1]:
            continue
        if max(cls[i].scores.values()) < STRONG:
            out[i] = out[i - 1]
    return out


JOIN_STORY = ("numbers", "fleet", "people", "news")


_BIBLE: Dict[str, Any] = {}


def _bible(texts: Sequence[str], rows) -> Any:
    """The script bible, read once per script (the story director takes each airline's aircraft from it)."""
    key = "\n".join(texts) + repr(rows)
    if _BIBLE.get("key") != key:
        from . import bible as BB
        try:
            _BIBLE.update(key=key, bible=BB.read(list(texts), rows))
        except Exception:                       # the bible only improves the stickers: without it the era guess is used
            _BIBLE.update(key=key, bible=None)
    return _BIBLE["bible"]


_SKIN = {"n": 0}                # number cards placed so far in this film (the skin rotor)
_ART = {"n": 0}                 # cited articles so far: the 2nd, 4th ... without a page get the newspaper card


def _dz_ok(c: Any, r: dict) -> bool:
    from . import dossier as DZ
    return DZ.pick(c, r) is not None


def _numbers_card(c: Any, r: dict, graphics: List[tuple]) -> Optional[tuple]:
    """The card for a line with figures, rotating skins so no one look takes the film: the dossier card (J-11 study) on every
    other number card, the built aviation graphic (blue news skin) on the rest; whichever exists when only one does."""
    from . import dossier as DZ
    dz = DZ.pick(c, r)
    if not dz and not graphics:
        return None
    use_dz = dz is not None and (not graphics or _SKIN["n"] % 2 == 0)
    _SKIN["n"] += 1
    return dz if use_dz else graphics[0]


STAGE_CLIP_S = (4.0, 6.0)      # a story line's own clip, full screen, cut out of the stage


STAGE_SHOWS = ("ownership", "timeline", "split tree", "who got what", "argument")   # richer stage pieces keep their line; a plain
# sticker number graphic rotates with the dossier card (the rotor picks which one this line shows)


def _story_dossier(scenes, cls, rows, i: int, j: int, lg) -> List[tuple]:
    """Story lines whose figure the stage does not already show (its own sticker graphic, timeline, ownership ...) get a dossier
    card cut into the stage on every other number card: (start, end, scene_no, card shot)."""
    from . import dossier as DZ
    why = {e["scene"]: e.get("stage") or "" for e in lg}
    out = []
    for k in range(i, j + 1):
        sc, c, r = scenes[k], cls[k], _row(rows, k)
        no = sc.get("scene_no", k + 1)
        if any(str(why.get(no, "")).startswith(x) for x in STAGE_SHOWS):
            continue
        dz = DZ.pick(c, r)
        if not dz:
            continue
        if _SKIN["n"] % 2 == 1:
            _SKIN["n"] += 1
            continue
        _SKIN["n"] += 1
        a, b = float(sc["start"]), float(sc["end"])
        if b - a < 2.5:
            continue
        e = min(b, a + 5.0)
        out.append((a, e, no, {"layer": dz[0], "params": dict(dz[1]), "start": a, "end": e, "scene": no, "full_frame": True,
                               "mode": "story"}))
    return out


def _stage_with_clips(shot: Dict[str, Any], scenes, i: int, j: int, cards: Sequence[tuple] = ()) -> List[Dict[str, Any]]:
    """The stage gives way to real footage: a story line with its own clip (an archive YouTube clip, a Flow shot, the user's
    file) plays it full screen for 4-6 s from the line's start, then the stage resumes on its own clock (t_offset) - so a
    history chapter is stickers AND real pictures, never one long sticker block."""
    holes = []
    for k in range(i, j + 1):
        sc = scenes[k]
        if not (sc.get("has_clip") or (sc.get("footage") and str(sc.get("asset_type") or "") not in ("", "none"))):
            continue
        a, b = float(sc["start"]), float(sc["end"])
        if b - a < 2.5:
            continue
        hb = min(b, a + STAGE_CLIP_S[1]) if b - a >= STAGE_CLIP_S[0] else b
        holes.append((a, hb, sc.get("scene_no", k + 1), None))
    for a, b, no, card in cards:                         # dossier cards cut into the stage (never over a clip of the same line)
        if not any(h[2] == no for h in holes):
            holes.append((a, b, no, card))
    holes.sort(key=lambda h: h[0])
    if not holes:
        return [shot]
    out, s0 = [], float(shot["start"])
    cur = s0
    for a, b, no, card in holes:
        if a < cur - 1e-6:
            continue
        if a > cur + 0.3:
            out.append(dict(shot, start=cur, end=a, params=dict(shot["params"], t_offset=cur - s0)))
        out.append(card if card else {"kind": "footage", "start": a, "end": b, "scene": no, "mode": "story", "queries": [],
                                      "cut": STAGE_CLIP_S})
        cur = b
    if float(shot["end"]) > cur + 0.3:
        out.append(dict(shot, start=cur, end=float(shot["end"]), params=dict(shot["params"], t_offset=cur - s0)))
    elif out and out[-1].get("kind") == "footage":
        out[-1]["end"] = float(shot["end"])
    pieces = [x for x in out if x.get("layer") == "stage.lay_stage"]
    keep = [(t, n) for t, n in shot.get("cues") or [] if not any(a <= t < b for a, b, _, _c in holes)]
    for k, x in enumerate(pieces):
        x["cues"] = keep if k == 0 else []          # every sticker sound once, none over a full-screen clip
    return out


def _story_join(modes: List[str], forced: List[bool], cls: Sequence[Any]) -> List[str]:
    """A line next to a story line stays on the sticker stage instead of breaking the story: always a numbers line (its figures
    become sticker graphics); a fleet / people / news line when it scored weakly (< STRONG: no clear event of its own - for a
    1960s airline no footage would match anyway). Only a neighbour the ROUTER called story pulls a line in - a joined line never
    pulls the next one, so one history line cannot turn a whole business story into stickers. CSV modes, flight, weather and
    evidence are kept."""
    orig = list(modes)
    out = list(modes)
    for k, m in enumerate(orig):
        if m not in JOIN_STORY or forced[k] or m == "story":
            continue
        if m != "numbers" and max(cls[k].scores.values() or [0]) >= STRONG:
            continue
        if (k > 0 and orig[k - 1] == "story") or (k + 1 < len(orig) and orig[k + 1] == "story"):
            out[k] = "story"
    return out


def _slots(start: float, end: float, lo: float, hi: float) -> List[tuple]:
    length = end - start
    if length <= 0:
        return []
    n = max(1, int(round(length / ((lo + hi) / 2))))
    while n > 1 and length / n < lo:
        n -= 1
    while length / n > hi:
        n += 1
    step = length / n
    return [(start + k * step, start + (k + 1) * step) for k in range(n)]


def _card_worthy(c: Any, since: float) -> bool:
    """A line a fact card can carry: one with a number; once CARD_EVERY_S has passed without a card, also a line that names an
    airline, aircraft or date; after 1.5 x CARD_EVERY_S any full sentence (8+ words). The reference shows a blue card every
    10-20 s of a news stretch."""
    v = c.values
    if v["counts"] or v["money"] or v["percent"]:
        return True
    if since >= CARD_EVERY_S and (v["dates"] or c.airlines or c.aircraft):
        return True
    return since >= 1.5 * CARD_EVERY_S and len(c.text.split()) >= 8


def _mins(hhmm: str) -> float:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def _hhmm(mins: float) -> str:
    m = int(round(mins)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _hud_timeline(scenes, cls, rows) -> List[Optional[Dict[str, Any]]]:
    """Time and fuel on ONE timeline for the whole film: each reading the narration (or CSV) gives is pinned to the start of its line,
    values run linearly from one reading to the next across every line between them, and hold after the last. A line's HUD shows
    (value at its start, value at its end), so the next line starts exactly where this one stopped. Nothing before the first reading."""
    fuel_pts, time_pts = [], []
    for k, (s, c) in enumerate(zip(scenes, cls)):
        r = _row(rows, k)
        f = r.get("fuel") or (c.values["fuel_kg"][-1] if c.values["fuel_kg"] else None)
        t = r.get("time") or (c.values["times"][-1] if c.values["times"] else None)
        if f:
            fuel_pts.append((float(s["start"]), float(f)))
        if t:
            tm = _mins(t)
            if time_pts and tm < time_pts[-1][1] - 1e-6:
                tm += 24 * 60                              # past midnight
            time_pts.append((float(s["start"]), tm))

    def at(pts, x):
        if not pts or x < pts[0][0] - 1e-6:
            return None
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 - 1e-6 <= x <= x1 + 1e-6:
                return y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 1.0)
        return pts[-1][1]

    out: List[Optional[Dict[str, Any]]] = []
    for k, (s, c) in enumerate(zip(scenes, cls)):
        a, b = float(s["start"]), float(s["end"])
        fa, fb, ta, tb = at(fuel_pts, a), at(fuel_pts, b), at(time_pts, a), at(time_pts, b)
        if fa is None and ta is None:
            out.append(None)
            continue
        fuel = (int(round(fa / 10) * 10), int(round(fb / 10) * 10)) if fa is not None else None
        if fuel and fuel_pts and any(abs(x - a) < 1e-6 for x, _ in fuel_pts):
            fuel = (int(round(fa)), fuel[1])               # a stated reading shows exactly as said
        if fuel and fuel_pts and abs(fuel_pts[-1][0] - a) < 1e-6:
            fuel = (int(round(fa)), int(round(fa)))
        out.append({"fuel": fuel, "time": (_hhmm(ta), _hhmm(tb)) if ta is not None else None,
                    "altitude": (getattr(c, "state", {}) or {}).get("altitude_ft")})
    # values that were stated exactly stay exact where a line ends on the next reading
    for k in range(len(out) - 1):
        if out[k] and out[k + 1] and out[k]["fuel"] and out[k + 1]["fuel"]:
            out[k]["fuel"] = (out[k]["fuel"][0], out[k + 1]["fuel"][0])
        if out[k] and out[k + 1] and out[k]["time"] and out[k + 1]["time"]:
            out[k]["time"] = (out[k]["time"][0], out[k + 1]["time"][0])
    return out


def _fact(text: str, limit: int = 110) -> str:
    t = text.strip()
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def plan(scenes: Sequence[Dict[str, Any]], rows: Optional[Sequence[dict]] = None, web: Optional[Dict[str, Any]] = None,
         retention: bool = True) -> Plan:
    """web: aviation.storyweb.resolve results (None on the first pass: story stages request their web pictures)."""
    texts = [str(s.get("text") or "") for s in scenes]
    from . import story as _ST
    _ST._BD_USED.clear()                # a new film: every library photo is free to use once again
    _SKIN["n"] = 0
    _ART["n"] = 0
    from . import sides as SD
    SD.set_film(texts)                  # colour = side: the film's two sides, one colour each in every graphic
    cls = R.route_script(texts)
    SCRIPT_YEAR[0] = max([int(y) for t_ in texts for y in _YEAR.findall(t_)] or [0])     # the story's 'now' for timelines
    SCRIPT_FUEL[0] = max([float(f) for c_ in cls for f in (c_.values.get("fuel_kg") or [])] or [0.0])   # the fuel gauge's full scale
    _PREV_Q.clear()
    forced, modes = [], []
    for i, c in enumerate(cls):
        r = _row(rows, i)
        g_ = str(r.get("graphic") or "").strip().lower()
        if str(r.get("mode") or "").strip().lower() == "map" or (g_ == "routes" and _present_day(c)):
            modes.append("flight"); forced.append(True)        # CSV 'map' / a present-day 'routes' line: the real map, not a card
            c.values["place_map"] = True
        elif r.get("mode") in R.MODES:
            modes.append(r["mode"]); forced.append(True)
        else:
            modes.append(c.mode); forced.append(False)
    modes = _smooth(cls, modes, forced)
    modes = _story_join(modes, forced, cls)
    hplan = _hud_timeline(scenes, cls, rows)
    out = Plan(modes=modes)
    for i, c in enumerate(cls):
        out.log.append({"scene": scenes[i].get("scene_no", i + 1), "mode": modes[i],
                        "why": ("csv" if forced[i] else "router: " + "; ".join(c.reasons[:4]) or "neutral")})

    # stretches of the same look (flight and weather share one map)
    def group(m: str) -> str:
        return "map" if m in MAP_MODES else m

    i = 0
    news_last_card = -CARD_GAP_S    # no card yet; the rhythm runs across stretches; the cold open (OPEN_S) is the video's start
    while i < len(scenes):
        j = i
        while j + 1 < len(scenes) and group(modes[j + 1]) == group(modes[i]):
            j += 1
        g = group(modes[i])
        if g == "map":
            _map_stretch(out, scenes, cls, rows, hplan, i, j)
        elif g == "story":
            from . import story as ST
            shot, lg = ST.build(scenes, cls, rows, i, j, web=web, bible=_bible(texts, rows))          # one evolving sticker stage for the whole stretch
            out.shots.extend(_stage_with_clips(shot, scenes, i, j, _story_dossier(scenes, cls, rows, i, j, lg)))
            for e in lg:
                for L_ in out.log:
                    if L_["scene"] == e["scene"]:
                        L_["stage"] = e["stage"]
        else:
            news_last_card = _clip_stretch(out, scenes, cls, rows, modes, i, j, news_last_card)
        i = j + 1

    _graphics(out, scenes, cls, rows)
    _csv_dossier(out, scenes, cls, rows)
    _cap_holds(out, scenes, cls, rows)
    _split_long_footage(out)

    # the next-episode card on a line that says 'the story of X'
    for k, s in enumerate(scenes):
        m = _END.search(texts[k])
        if m and k >= len(scenes) - 2:
            _replace_with(out, s["start"], s["end"], {"layer": "gfx.lay_end_card", "start": s["start"], "end": s["end"],
                                                      "scene": s.get("scene_no"), "full_frame": True,
                                                      "params": {"kicker": "THE STORY OF", "title": m.group(1).strip()}})
    out.shots.sort(key=lambda x: (x["start"], 0 if x.get("full_frame") or x.get("kind") == "footage" else 1))
    if retention:                       # re-hooks on turn lines, 8 s variety, fast opening, callback (aviation/retention.py)
        from . import retention as RT
        out.retention = RT.apply(out, scenes)
    from . import balance as BL          # the mix of looks against the target bands; same template twice in a row is fixed
    out.balance = BL.apply(out, scenes)
    from . import transitions as TR      # the stage / map / news looks hand over with shared transitions
    TR.add(out)
    out.shots.sort(key=lambda x: (x["start"], 0 if x.get("full_frame") or x.get("kind") == "footage" else 1))
    return out


_RIGHT_NOW = re.compile(r"\bright now\b|\bat this moment\b|\bmeanwhile\b", re.I)
_REPORT = re.compile(r"\bweather report\b|\bforecast\b|\bmetar\b|\bbriefing\b", re.I)
_GLIDE = re.compile(r"\bglide\s*(?:slope|path)\b|\bdecision height\b|\bminimums\b|\bils\b|\bfinal approach\b", re.I)
_GAUGE = re.compile(r"\bgauges?\b|\breads?\b|\bquantity\b|\bindicat\w*|\bneedle\b", re.I)
_ROLE = (("first officer", "FIRST OFFICER"), ("second officer", "SECOND OFFICER"), ("flight engineer", "FLIGHT ENGINEER"),
         ("co-pilot", "CO-PILOT"), ("captain", "CAPTAIN"))
SCRIPT_FUEL: List[float] = [0.0]
_KEY = {"wind": "WIND", "haze": "VIS", "fog": "VIS", "cloud": "CLOUD", "storm": "WX", "rain": "WX", "hail": "WX", "heat": "TEMP"}


def _graphics(out: Plan, scenes, cls, rows) -> None:
    """Graphics the CSV's `graphic` column asks for, and the ones the narration itself calls for: a place title when a line says
    'right now' about a place, the altitude side view when a line gives two altitudes, a weather sheet for a weather-report line (its
    rows are that line's own words). Overlays sit over whatever is on screen; the side view is full frame for its line."""
    for k, (s, c) in enumerate(zip(scenes, cls)):
        r = _row(rows, k)
        g = str(r.get("graphic") or "").strip().lower()
        a, b = float(s["start"]), float(s["end"])
        sc = s.get("scene_no", k + 1)
        city = ""
        for code in [r.get("to") or "", r.get("from") or ""] + [x["id"] for x in reversed(c.airports)]:
            ap = C.get_airport(code) if code else None
            if ap:
                city = ap["city"]
                break
        if (g == "place_title" or (_RIGHT_NOW.search(c.text) and c.airports)) and city:
            out.shots.append({"layer": "gfx.lay_place_title", "start": a, "end": min(b, a + 3.5), "scene": sc,
                              "params": {"name": city, "pill": "RIGHT NOW" if _RIGHT_NOW.search(c.text) else ""}})
        alts = c.values.get("altitude_ft") or []
        if g == "altitude" or len(alts) >= 2:
            if alts:
                lo_hi = (alts[0], alts[-1]) if len(alts) >= 2 else (alts[0], alts[0])
                out.shots.append({"layer": "gfx.lay_altitude", "start": a, "end": b, "scene": sc, "full_frame": True,
                                  "params": {"from_ft": lo_hi[0], "to_ft": lo_hi[1], "lines": sorted(set(alts)),
                                             "label": (getattr(c, "state", {}) or {}).get("flight") or ""}})
        items = G.weather_items(c.text)
        if (g == "briefing_sheet" or _REPORT.search(c.text)) and items:
            stamp = ""
            m = re.search(r"\b(?:over|more than)?\s*(\w+)\s+hours?\s+old\b", c.text, re.I)
            if m:
                stamp = m.group(0).strip().upper()
            out.shots.append({"layer": "gfx.lay_sheet", "start": a, "end": b, "scene": sc,
                              "params": {"title": f"{city.upper()} WEATHER" if city else "WEATHER REPORT",
                                         "rows": [[_KEY.get(kind, "WX"), label] for kind, label, _sub in items],
                                         "highlight": list(range(len(items))), "stamp": stamp, "stamp_at": 2.0}})
        v = c.values
        al = (r.get("airline") or (c.airlines[0]["id"] if c.airlines else ""))
        from . import gfx_air as GA
        tail = GA.tail_of(al)
        low = c.text.lower()
        span = (a, min(b, a + CARD_HOLD_S))
        # a crew line: who they are, how old, how many hours (overlay over the cockpit / map)
        hours = next((n for n, noun in v.get("counts") or [] if noun == "hours"), None)
        role = next((lab for w, lab in _ROLE if w in low), "")
        if role and (v.get("age") or hours):
            m = re.search(r"([\d,]+)\s+hours?\s+on\s+(?:the\s+)?(?:type|this aircraft|the [a-z0-9\- ]+)", low)
            out.shots.append({"layer": "gfx_air.lay_crew", "start": a, "end": b, "scene": sc,
                              "params": {"role": role, "age": v.get("age"), "hours": hours, "name": FT._person(c),
                                         "on_type": int(m.group(1).replace(",", "")) if m else None}})
        if v.get("runways") and (v.get("length_m") or re.search(r"\bland\w*|\bcleared\b", low)):
            out.shots.append({"layer": "gfx_air.lay_runway", "start": span[0], "end": span[1], "scene": sc, "full_frame": True,
                              "params": {"runway": v["runways"][-1], "length_m": (v.get("length_m") or [None])[-1],
                                         "airport": c.airports[-1]["id"] if c.airports else ""}})
        if v.get("vs_fpm"):
            out.shots.append({"layer": "gfx_air.lay_descent", "start": span[0], "end": span[1], "scene": sc, "full_frame": True,
                              "params": {"fpm": v["vs_fpm"][0], "speed_kt": (v.get("speed_kt") or [None])[0], "tail": tail}})
        if _GLIDE.search(c.text) and alts:
            out.shots.append({"layer": "gfx_air.lay_approach", "start": span[0], "end": span[1], "scene": sc, "full_frame": True,
                              "params": {"from_ft": max(alts), "to_ft": min(alts) if len(alts) > 1 else 0, "lines": sorted(set(alts)),
                                         "tail": tail, "label": "glide slope"}})
        if _GAUGE.search(c.text) and v.get("fuel_kg"):
            out.shots.append({"layer": "gfx_air.lay_gauge", "start": span[0], "end": span[1], "scene": sc, "full_frame": True,
                              "params": {"value": v["fuel_kg"][-1], "max": max(SCRIPT_FUEL[0], v["fuel_kg"][-1] * 2), "unit": "KG",
                                         "label": "FUEL"}})
        if g == "title":
            title = (getattr(c, "state", {}) or {}).get("flight") or (c.airlines[0]["name"] if c.airlines else "")
            if title:
                out.shots.append({"layer": "gfx_air.lay_title", "start": a, "end": min(b, a + 4.0), "scene": sc, "full_frame": True,
                                  "params": {"title": title, "sub": (v.get("dates") or [""])[0]}})
        if g == "end_card" and not _END.search(c.text):
            title = (getattr(c, "state", {}) or {}).get("flight") or (c.airlines[0]["name"] if c.airlines else "")
            if title:
                _replace_with(out, a, b, {"layer": "gfx.lay_end_card", "start": a, "end": b, "scene": sc, "full_frame": True,
                                          "params": {"kicker": "THE STORY OF", "title": title}})


DOSSIER_CSV = ("dossier", "markers", "options", "family", "quotes")


def _csv_dossier(out: Plan, scenes, cls, rows) -> None:
    """The CSV's `graphic` asks for a dossier card on this line: it covers the line (up to CARD_HOLD_S = 5 s, the rest goes back to what was
    planned), drawn over the stage or the clips under it."""
    from . import dossier as DZ
    for k, (s, c) in enumerate(zip(scenes, cls)):
        r = _row(rows, k)
        g = str(r.get("graphic") or "").strip().lower()
        if g not in DOSSIER_CSV:
            continue
        card = DZ.from_csv(g, c, r)
        if not card:
            continue
        a, b = float(s["start"]), float(s["end"])
        e = min(b, a + CARD_HOLD_S)
        _replace_with(out, a, e, {"layer": card[0], "start": a, "end": e, "scene": s.get("scene_no", k + 1), "full_frame": True,
                                  "mode": out.modes[k] if k < len(out.modes) else "news", "params": dict(card[1])})


HOLD_S = {"stage.lay_stage": 8.0}     # a sticker stage builds for 8 s at most; any other full-frame card holds 6 s
CARD_HOLD_S = 5.0             # a card is read in 5 s (user, 2026-11-13: they ran ~7 s), then footage takes over
STAGE_MAX_S = 12.0
STAGE_GAP_S = 2.5             # nothing new on a stage for this long = a blank screen
NO_CAP = ("flightmap.lay_flight_map", "gfx.lay_end_card", "gfx_air.lay_title")


def _cap_holds(out: Plan, scenes, cls, rows) -> None:
    """No look sits still: a full-frame card / stage longer than its hold is cut there and the rest of its time goes to the line's
    own footage (or the nearest clip of the stretch). The same card twice at the same moment is drawn once (the longer one, then capped like the rest)."""
    seen: Dict[tuple, dict] = {}
    for sh in list(out.shots):
        if not (sh.get("full_frame") and sh.get("layer")):
            continue
        key = (sh["layer"], round(float(sh["start"]), 2), repr(sorted((sh.get("params") or {}).items(), key=lambda kv: kv[0])))
        if key in seen:
            other = seen[key]
            drop = sh if (sh["end"] - sh["start"]) < (other["end"] - other["start"]) else other     # the longer covers its time
            out.shots.remove(drop)
            seen[key] = other if drop is sh else sh
        else:
            seen[key] = sh
    by_no = {s.get("scene_no", k + 1): k for k, s in enumerate(scenes)}

    def filler(t: float, b: float, fallback_no: Any) -> None:
        while t < b - 1e-3:                                  # footage of the line(s) under it, one slot per line
            k = next((by_no[s_.get("scene_no", i_ + 1)] for i_, s_ in enumerate(scenes)
                      if float(s_["start"]) <= t + 1e-3 < float(s_["end"])), by_no.get(fallback_no, 0))
            e = min(b, float(scenes[k]["end"]))
            if e - t < 1e-3:
                break
            out.shots.append({"kind": "footage", "start": t, "end": e, "scene": scenes[k].get("scene_no"),
                              "mode": out.modes[k] if k < len(out.modes) else "news", "queries": _queries(cls[k], _row(rows, k)),
                              "cut": (e - t, e - t), "filler": True})    # borrows a nearby clip; never asks for a new search
            t = e

    # a stage with nothing new on screen for a while (only a caption / its blurred backdrop left) is a blank screen: footage covers the gap
    # and the stage picks up on its own clock where its next sticker comes
    for sh in [x for x in out.shots if x.get("layer") == "stage.lay_stage"]:
        a, b = float(sh["start"]), float(sh["end"])
        off = float((sh.get("params") or {}).get("t_offset") or 0.0)
        # only a caption or the blurred background picture left = a blank screen (the backdrop is a background, not a subject)
        els = [e for e in (sh.get("params") or {}).get("elements") or [] if e.get("kind") not in ("caption", "backdrop")]
        step, t, gap0, gaps = 0.1, a, None, []
        while t <= b + 1e-6:
            lt = t - a + off
            vis = any(float(e.get("t0") or 0.0) <= lt < (float(e["t1"]) if e.get("t1") is not None else 1e9) for e in els)
            if not vis and gap0 is None:
                gap0 = t
            if (vis or t >= b - 1e-6) and gap0 is not None:
                if t - gap0 >= STAGE_GAP_S:
                    gaps.append((gap0, t))
                gap0 = None
            t += step
        if not gaps:
            continue
        cues = list(sh.get("cues") or [])
        pieces, cur = [], a
        for ga, gb in gaps:
            if ga > cur + 0.3:
                pieces.append((cur, ga))
            filler(ga, min(b, gb), sh.get("scene"))
            cur = gb
        if b > cur + 0.3:
            pieces.append((cur, b))
        out.shots.remove(sh)
        for pa, pb in pieces:
            out.shots.append(dict(sh, start=pa, end=pb, params=dict(sh["params"], t_offset=off + pa - a),
                                  cues=[x for x in cues if pa <= float(x[0]) < pb]))

    for sh in list(out.shots):
        lay = sh.get("layer")
        if not (sh.get("full_frame") and lay) or lay in NO_CAP:
            continue
        hold = HOLD_S.get(lay, CARD_HOLD_S)
        a, b = float(sh["start"]), float(sh["end"])
        grace = 1.5 if lay == "stage.lay_stage" else 0.0     # a card never runs past its 5 s (a stage may finish its sentence)
        if b - a <= hold + grace:
            continue
        cut = a + hold
        if lay == "stage.lay_stage":            # a stage ends with a sentence (a question stays up until its line ends), 12 s at most
            ends = [float(s_["end"]) for s_ in scenes if a + hold - 1e-3 <= float(s_["end"]) <= min(b, a + STAGE_MAX_S) + 1e-3]
            cut = min(ends) if ends else cut
        if b - cut < 1.0:
            if lay == "stage.lay_stage":
                continue
            cut = b - 1.0                  # never a sub-second flash of footage after a card: the card ends a little earlier
        sh["end"] = cut
        if sh.get("cues"):
            sh["cues"] = [x for x in sh["cues"] if float(x[0]) <= cut]   # no sticker pop over the footage that follows
        filler(cut, b, sh.get("scene"))


FOOTAGE_MAX_S = 5.0            # a footage slot longer than this is split: a clip shorter than its slot would leave it empty


def _split_long_footage(out: Plan) -> None:
    """Footage slots over FOOTAGE_MAX_S become equal pieces (the clip picker plays one clip on through them, or cuts to the next
    clip when it runs out) - one 11 s slot with only 8 s clips around it showed a sticker on black instead."""
    for sh in [x for x in out.shots if x.get("kind") == "footage"]:
        a, b = float(sh["start"]), float(sh["end"])
        n = int(math.ceil((b - a) / FOOTAGE_MAX_S - 1e-9))
        if n <= 1:
            continue
        out.shots.remove(sh)
        step = (b - a) / n
        for k in range(n):
            x, y = a + k * step, (b if k == n - 1 else a + (k + 1) * step)
            out.shots.append(dict(sh, start=x, end=y, cut=(y - x, y - x)))


def _replace_with(out: Plan, a: float, b: float, shot: dict) -> None:
    keep = []
    for s in out.shots:
        if (s.get("kind") == "footage" or s.get("full_frame")) and s["start"] >= a - 1e-6 and s["end"] <= b + 1e-6:
            continue
        keep.append(s)
    keep.append(shot)
    out.shots[:] = keep


_PREV_Q: Dict[str, List[str]] = {}


def _queries(c: Any, r: dict) -> List[str]:
    """The CSV's searches, else the sentence's own; a fragment that names nothing ('airliner ...' fallback) keeps the previous
    line's searches - it is almost always still the same topic."""
    q = list(r.get("queries") or []) or FT.queries_for(c)
    if q and q[0].startswith("airliner") and _PREV_Q.get("q"):
        return list(_PREV_Q["q"])
    _PREV_Q["q"] = q
    return q


_MONEY_WORDS = (("profit", "PROFIT"), ("cash", "CASH"), ("revenue", "REVENUE"), ("loss", "LOSS"), ("invest", "INVESTMENT"),
                ("fuel", "FUEL BILL"), ("cost", "COSTS"))
_YEAR = re.compile(r"\b(19[2-9]\d|20[0-4]\d)\b")
SCRIPT_YEAR: List[int] = [0]


def _tail(c: Any, r: dict):
    from . import gfx_air as GA
    return GA.tail_of(r.get("airline") or (c.airlines[0]["id"] if c.airlines else ""))


def _air_graphics(c: Any, r: dict) -> List[tuple]:
    """Aviation graphics the line's own numbers call for, most telling first (at most two)."""
    from . import catalog as Cat

    v, low = c.values, c.text.lower()
    out: List[tuple] = []
    label = next((lab for w, lab in _MONEY_WORDS if w in low), "")
    if v.get("changes"):
        cur, a, b = v["changes"][0]
        out.append(("gfx_air.lay_change", {"before": a, "after": b, "currency": cur, "label": label or "CHANGE",
                                            "before_label": "BEFORE", "after_label": "NOW"}))
    pcts = list(v.get("percent") or [])
    if pcts and re.search(r"\bfull\b|load factor|occupancy|seats? (?:were|was|filled)", low):
        m = re.search(r"\bagainst\s+(\d+(?:\.\d+)?)", low)
        out.append(("gfx_air.lay_seats", {"now": pcts[0], "before": float(m.group(1)) if m else (pcts[1] if len(pcts) > 1 else None),
                                           "label": "SEATS FILLED"}))
    counts = dict((n, x) for x, n in (v.get("counts") or []))
    fleet = next((counts[n] for n in ("aircraft", "jets", "planes") if counts.get(n, 0) >= 10), 0)
    if fleet:
        out.append(("gfx_air.lay_fleet", {"count": fleet, "label": "AIRCRAFT"}))
    if counts.get("destinations", 0) >= 10:
        al = Cat.get_airline(r.get("airline") or "") or (c.airlines[0] if c.airlines else None)
        hub = (al or {}).get("hubs", [None])[0] if al and al.get("hubs") else (c.airports[0]["id"] if c.airports else None)
        if hub:
            out.append(("gfx_air.lay_network", {"hub": hub, "count": counts["destinations"], "label": "DESTINATIONS",
                                                 "plus": bool(re.search(r"more than|over|\+", low))}))
    if not v.get("changes") and not any(x[0] == "gfx_air.lay_seats" for x in out):
        sign = "+" if re.search(r"\b(jump\w*|rose|rise\w*|up|increase\w*|grew|growth|record)\b", low) else \
            ("-" if re.search(r"\b(fell|fall\w*|down|drop\w*|lost|loss|decline\w*|cut)\b", low) else "")
        icon = "freighter" if re.search(r"\bcargo\b|\bfreight", low) else "airliner"
        if pcts and (label or icon == "freighter"):
            val = pcts[0]
            word = next((w for w, lab in _MONEY_WORDS if lab == label), "")
            if word and len(pcts) > 1:          # 'passengers up 4.2 percent, revenue up 4.3 percent': the label's own figure
                at = low.find(word)
                ms = [(m.start(), float(m.group(1))) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)", low)]
                after = [x for x in ms if x[0] > at]
                if after:
                    val = after[0][1]
            out.append(("gfx_air.lay_big_number", {"value": val, "unit": "%", "sign": sign,
                                                    "label": ("CARGO " if icon == "freighter" else "") + (label or "REVENUE"), "icon": icon,
                                                    "tail": _tail(c, r)}))
        elif v.get("money") and label:
            cur, amt = v["money"][0]
            out.append(("gfx_air.lay_big_number", {"value": amt, "unit": cur, "sign": "", "label": label, "icon": icon, "tail": _tail(c, r)}))
    years = [int(y) for y in _YEAR.findall(c.text)]
    if years and SCRIPT_YEAR[0] and min(years) <= SCRIPT_YEAR[0] - 15:
        name = (c.airlines[0]["name"] if c.airlines else "").upper()
        out.append(("gfx_air.lay_timeline", {"from_year": min(years), "to_year": SCRIPT_YEAR[0], "label": name}))
    return out[:2]


def _clip_stretch(out: Plan, scenes, cls, rows, modes, i: int, j: int, last_card: float) -> float:
    s0 = scenes[i]["start"]
    for k in range(i, j + 1):
        s, c, r, mode = scenes[k], cls[k], _row(rows, k), modes[k]
        a, b = s["start"], s["end"]
        sc = s.get("scene_no", k + 1)
        card = None
        graphics = _air_graphics(c, r) if mode != "evidence" else []
        if s.get("has_clip") is False and mode != "evidence" and not (r.get("article") or {}).get("page") and not r.get("article"):
            # nothing filmed for this line: its aviation graphics share the line, else its own words as a clean text card
            first = _numbers_card(c, r, graphics)
            items = ([first] + [g for g in graphics if g is not first][:1]) if first else [("cards.lay_article", {"fact": _fact(c.text)})]
            step = (b - a) / len(items)
            for n_, (layer, params) in enumerate(items):
                out.shots.append({"layer": layer, "start": a + n_ * step, "end": a + (n_ + 1) * step, "scene": sc, "full_frame": True,
                                  "mode": mode, "params": params})
            if first:
                last_card = a
            continue
        if mode == "evidence" and not (r.get("article") or {}).get("page"):
            card = {"layer": "war.lay_document", "params": {"text": c.text, "highlight": c.text}}
        elif r.get("article"):
            art = dict(r["article"])
            _ART["n"] += 1
            if not art.get("page") and art.get("headline") and _ART["n"] % 2 == 0:
                # no page captured: the cream newspaper card (J-11 study J4g) on every other article, the blue typeset one on the rest
                card = {"layer": "dossier.lay_newspaper", "params": {"title": "The press", "outlet": art.get("outlet", ""),
                                                                    "date": art.get("date", ""), "headline": art["headline"]}}
            else:
                card = {"layer": "cards.lay_article", "params": dict(art, image_from="footage")}
        elif (graphics or _dz_ok(c, r)) and a - last_card >= CARD_GAP_S and b - max(a, OPEN_S) >= 2.5:
            layer, params = _numbers_card(c, r, graphics)
            card = {"layer": layer, "params": dict(params), "graphic_at": max(a, OPEN_S)}
        elif mode in ("news", "numbers", "fleet") and a >= OPEN_S and a - last_card >= CARD_GAP_S and \
                (b - a) >= 2.0 and (mode != "fleet" or c.values["counts"]) and _card_worthy(c, a - max(last_card, 0.0)):
            card = {"layer": "cards.lay_article", "params": {"fact": _fact(c.text), "image_from": "footage"}}
        lo, hi = FT.cut_range(mode)
        q = _queries(c, r)
        clip_from = a
        if card:
            g0 = float(card.pop("graphic_at", a))
            if g0 > a + 1e-6:                              # the cold open stays on clips; the graphic comes after it
                for x, y in _slots(a, g0, lo, hi):
                    out.shots.append({"kind": "footage", "start": x, "end": y, "scene": sc, "mode": mode, "queries": q, "cut": (lo, hi)})
            end = b
            if card["layer"] != "war.lay_document" and b - g0 > CARD_MAX_S + 1.0:
                end = g0 + CARD_MAX_S                      # the card, then the rest of the sentence on clips
            card.update(start=g0, end=end, scene=sc, full_frame=True, mode=mode)
            out.shots.append(card)
            if card["layer"] != "war.lay_document":
                last_card = g0
            if end >= b - 1e-6:
                continue
            clip_from = end
            if mode not in ("news", "numbers"):
                lo, hi = FT.cut_range("news")
        for x, y in _slots(clip_from, b, lo, hi):
            out.shots.append({"kind": "footage", "start": x, "end": y, "scene": sc, "mode": mode, "queries": q, "cut": (lo, hi)})
        counters = G.counters_from(c.values)
        if counters:
            out.shots.append({"layer": "gfx.lay_counters", "start": a, "end": b, "scene": sc, "params": {"items": counters}})
    return last_card


def _present_day(c: Any) -> bool:
    """Not a history line: no year more than 15 years before the script's latest year, no founding / renaming / merger words."""
    old = [y for y in R.plain_years(c.text) if SCRIPT_YEAR[0] and SCRIPT_YEAR[0] - y > 15]
    return not old and not R._HISTORY.search(c.text)


def _places(c: Any) -> List[str]:
    """The airports a line names, then (a place-map line only) the anchor airports of the regions it names ('Brazil', 'Africa')."""
    named = list(dict.fromkeys(a["id"] for a in c.airports))
    if c.values.get("place_map"):
        for x in R.region_airports(c.text):
            if x not in named and all(_km(x, y) > 800.0 for y in named):
                named.append(x)                 # a region's stand-in never sits on a place already shown (labels would overlap)
    return named


def _km(a: str, b: str) -> float:
    pa, pb = C.get_airport(a), C.get_airport(b)
    if not pa or not pb:
        return 1e9
    la1, lo1, la2, lo2 = map(math.radians, (pa["lat"], pa["lon"], pb["lat"], pb["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, h)))


_ROUTE_TO = re.compile(r"\b(?:flew|flies|fly|flying|flights?|routes?|services?)\s+to\b", re.I)
_NETWORK = re.compile(r"\bmap\b|\bnetwork\b|\broutes\b|\bdestinations\b", re.I)


def _airline_hubs(al_id: str) -> List[str]:
    al = C.get_airline(al_id) if al_id else None
    if not al and al_id:
        hits = C.find_airlines(al_id)
        al = hits[0].entry if hits else None
    return [h for h in (al or {}).get("hubs") or [] if C.get_airport(h)]


def _hub_of(c: Any, r: dict, named: Sequence[str], prev: str = "") -> str:
    """The line's hub: an airline hub among the airports the line names; else, for a line that names only regions, the hub
    already on the map, then the row's airline hub; else the first airport named. ('United States' is a region, not United.)"""
    own = [a["id"] for a in c.airports]
    hubs = [h for al_id in [r.get("airline") or ""] + [a["id"] for a in c.airlines] for h in _airline_hubs(al_id)]
    for h in hubs:
        if h in own:
            return h
    if own and hubs and _ROUTE_TO.search(c.text):
        return hubs[0]                                    # 'a DC-3 flew to Madrid': out of the airline's hub
    if own:
        return own[0]
    if prev:
        return prev
    row_hubs = _airline_hubs(r.get("airline") or "")
    return row_hubs[0] if row_hubs else (named[0] if named else "")


def _map_stretch(out: Plan, scenes, cls, rows, hplan, i: int, j: int) -> None:
    t0, t1 = scenes[i]["start"], scenes[j]["end"]
    airports: List[str] = []
    prm: Dict[str, Any] = {"airports": airports, "storms": [], "callouts": []}

    appear: Dict[str, float] = {}
    prm["appear"] = appear
    cur_rel = [0.0]

    def seen(a: str) -> None:
        if a and a not in airports:
            airports.append(a)
        if a and a not in appear:
            appear[a] = round(cur_rel[0], 3)              # the label pops in when the narration first names the airport

    last_airport = ""
    for k in range(i, j + 1):
        s, c, r = scenes[k], cls[k], _row(rows, k)
        rel = s["start"] - t0
        cur_rel[0] = rel
        named = _places(c)
        frm, to = r.get("from") or "", r.get("to") or ""
        if c.values.get("place_map") and not (frm and to):
            # a place line (no flight): the network from the hub - one line out to each place it names, drawn one after another
            hub = _hub_of(c, r, named, prm.get("hub", ""))
            prm["hub"] = hub
            dests = [x for x in named if x != hub]
            line_hubs = _airline_hubs(r.get("airline") or "") + [h for a in c.airlines for h in _airline_hubs(a["id"])]
            if hub and not dests and hub in line_hubs and _NETWORK.search(c.text):
                # 'Lisbon is a small hub with a big map': the network the script names anywhere else, out of this hub
                dests = [x for k2, c2 in enumerate(cls) if c2.values.get("place_map")
                         and _hub_of(c2, _row(rows, k2), _places(c2), hub) == hub for x in _places(c2) if x != hub]
                dests = list(dict.fromkeys(dests))
                # the whole network at world scale: places closer than ~1/8 of its span would print their names on each other
                span = max([_km(x, y) for x in [hub] + dests for y in [hub] + dests] or [0.0])
                kept: List[str] = []
                for x in dests:
                    if all(_km(x, y) >= 0.13 * span for y in [hub] + kept):
                        kept.append(x)
                dests = kept
            if hub and dests:
                seen(hub)
                legs = prm.setdefault("legs", [])
                for n_, d_ in enumerate(dests[:8]):
                    if not any((lg["from"], lg["to"]) == (hub, d_) for lg in legs):
                        legs.append({"from": hub, "to": d_, "start": rel + 0.3 + 0.35 * n_, "length": 2.2})
            named = ([hub] if hub else []) + dests
        for a in named + [frm, to]:
            seen(a)
        if not (frm and to) and len(named) >= 2 and not c.values.get("place_map"):
            frm, to = named[0], named[1]
        if frm and to and frm != to:
            legs = prm.setdefault("legs", [])
            if not legs or (legs[-1]["from"], legs[-1]["to"]) != (frm, to):
                leg = {"from": frm, "to": to, "start": rel + 0.3, "length": max(2.0, (s["end"] - s["start"]) * 1.5)}
                legs.append(leg)                           # a later leg appears only when the narration reaches it
                prm.setdefault("route", dict(leg))
        if named or r.get("from") or r.get("to"):
            last_airport = (named[-1] if named else (r.get("to") or r.get("from")))
            prm["active"] = last_airport
        if _HOLD.search(c.text) and last_airport:
            prm.setdefault("holding", {"at": last_airport, "laps": 3, "start": rel + 0.3, "length": max(4.0, (t1 - t0) - rel - 0.5)})
        if c.mode == "weather" or cls[k].scores.get("weather", 0) >= 4:
            at = named[-1] if named else last_airport
            items = G.weather_items(c.text)
            gust = next((x[2] for x in items if x[2].startswith("GUSTS")), "")
            if at and not any(st["at"] == at for st in prm["storms"]):
                prm["storms"].append({"at": at, "km": 40, "label": gust, "start": rel})
            if items:
                out.shots.append({"layer": "gfx.lay_weather", "start": s["start"], "end": s["end"], "scene": s.get("scene_no"),
                                  "params": {"items": items}})
        if c.values["distance_km"] and len(named) >= 2:
            prm["callouts"].append({"from": named[0], "to": named[1], "start": rel + 0.3})
        # overlays for this line
        hp = hplan[k] if k < len(hplan) else None
        alt = r.get("altitude") or (hp or {}).get("altitude")
        fuel = (hp or {}).get("fuel")
        tim = (hp or {}).get("time")
        if fuel or tim or alt:
            out.shots.append({"layer": "hud.lay_hud", "start": s["start"], "end": s["end"], "scene": s.get("scene_no"),
                              "params": {"time": tim, "fuel": fuel, "altitude": alt}})
        radio = list(r.get("radio") or [])
        if not radio and c.radio:
            q = re.search(r"[\"“]([^\"”]+)[\"”]", c.text)
            line = (q.group(1) if q else c.text).strip()
            radio = [{"speaker": U.speaker_of(line), "text": line}]
        if radio:
            out.shots.append({"layer": "hud.lay_radio", "start": s["start"], "end": s["end"], "scene": s.get("scene_no"),
                              "params": {"lines": radio}})
        counters = G.counters_from(c.values)
        if counters:
            out.shots.append({"layer": "gfx.lay_counters", "start": s["start"], "end": s["end"], "scene": s.get("scene_no"),
                              "params": {"items": counters}})
    if not airports:
        # a flight stretch that names no place: footage of the aircraft instead of an empty map
        for k in range(i, j + 1):
            s, c, r = scenes[k], cls[k], _row(rows, k)
            lo, hi = FT.cut_range("fleet")
            for x, y in _slots(s["start"], s["end"], lo, hi):
                out.shots.append({"kind": "footage", "start": x, "end": y, "scene": s.get("scene_no"), "mode": c.mode,
                                  "queries": _queries(c, r), "cut": (lo, hi)})
        return
    # camera: each line that names places re-frames the map on them (a route wide, a storm / hold / approach close on its airport)
    views: List[Dict[str, Any]] = []
    last_focus: Optional[List[str]] = None
    cam_hub = ""
    for k in range(i, j + 1):
        s, c, r = scenes[k], cls[k], _row(rows, k)
        named = _places(c)
        if c.values.get("place_map"):
            hub = _hub_of(c, r, named, cam_hub)
            cam_hub = hub or cam_hub
            named = ([hub] if hub else []) + [x for x in named if x != hub]
        frm, to = r.get("from") or "", r.get("to") or ""
        if frm and to and frm != to:
            focus = [frm, to]
        elif c.values.get("place_map") and prm.get("legs") and len(named) <= 1 and named:
            focus = list(dict.fromkeys([named[0]] + [lg["to"] for lg in prm["legs"] if lg["from"] == named[0]]))[:9]
        elif c.values.get("place_map") and len(named) >= 2:
            focus = named[:9]                              # the whole network in frame
        elif len(named) >= 2:
            focus = named[:2]
        elif named:
            focus = named[-1:]
        elif to:
            focus = [to]
        else:
            continue
        if focus != last_focus:
            views.append({"start": max(0.0, s["start"] - t0), "focus": focus})
            last_focus = focus
    if views:
        prm["views"] = views
    # beats: a line with its own aircraft shot (Flow video / checked YouTube) cuts to it; the map carries on around it (one clock, one
    # route); a map run longer than MAX_MAP_S still gets a short break so nothing sits too long
    total = t1 - t0
    segs: List[tuple] = []
    for k in range(i, j + 1):
        s = scenes[k]
        has_clip = bool(s.get("footage")) and str(s.get("asset_type") or "") in ("flow_video", "youtube_video", "flow_image", "stock_video", "local")
        kind = ("clip", k) if has_clip else ("map", None)
        if segs and segs[-1][2] == kind[0] and kind[0] == "map":
            segs[-1] = (segs[-1][0], s["end"], "map", None)
        else:
            segs.append((s["start"], s["end"], kind[0], kind[1]))
    # a place map (where an airline flies, no flight on it) says what it has to say once its routes are drawn: 7 s, then footage
    if any(cls[k].values.get("place_map") for k in range(i, j + 1)):
        # each place line gets the map on its own words (up to PLACE_MAP_S; its legs are timed to the line), the rest is footage
        def foot(a_: float, b_: float, k_: int) -> None:
            if b_ - a_ > 1e-3:
                out.shots.append({"kind": "footage", "start": a_, "end": b_, "scene": scenes[k_].get("scene_no"), "mode": "flight",
                                  "queries": _queries(cls[k_], _row(rows, k_)) or ["airliner flying above clouds"], "cut": (b_ - a_, b_ - a_)})
        for k in range(i, j + 1):
            s_ = scenes[k]
            a_, b_ = float(s_["start"]), float(s_["end"])
            if not cls[k].values.get("place_map"):
                foot(a_, b_, k)
                continue
            e_ = b_ if b_ - (a_ + PLACE_MAP_S) < 2.0 else a_ + PLACE_MAP_S
            out.shots.append({"layer": "flightmap.lay_flight_map", "start": a_, "end": e_, "full_frame": True, "mode": "flight",
                              "scene": s_.get("scene_no"), "params": dict(prm, t0=a_ - t0, total=total)})
            foot(e_, b_, k)
        return
    max_map = MAX_MAP_S
    for a, b, kind, k in segs:
        if kind == "clip":
            sc_ = scenes[k]
            out.shots.append({"kind": "footage", "start": a, "end": b, "scene": sc_.get("scene_no"), "mode": "flight",
                              "queries": _queries(cls[k], _row(rows, k)), "cut": (b - a, b - a)})
            continue
        pos = a
        while pos < b - 1e-6:
            end = min(b, pos + max_map)
            if b - end < BREAK_S + 2.0:
                end = b
            out.shots.append({"layer": "flightmap.lay_flight_map", "start": pos, "end": end, "full_frame": True, "mode": "flight",
                              "scene": _scene_at(scenes, i, j, pos), "params": dict(prm, t0=pos - t0, total=total)})
            if end >= b - 1e-6:
                break
            k2 = _index_at(scenes, i, j, end)
            out.shots.append({"kind": "footage", "start": end, "end": end + BREAK_S, "scene": scenes[k2].get("scene_no"), "mode": "flight",
                              "queries": _queries(cls[k2], _row(rows, k2)) or ["airliner flying above clouds"], "cut": (BREAK_S, BREAK_S)})
            pos = end + BREAK_S


def _index_at(scenes, i: int, j: int, t: float) -> int:
    for k in range(i, j + 1):
        if scenes[k]["start"] <= t < scenes[k]["end"]:
            return k
    return j


def _scene_at(scenes, i: int, j: int, t: float):
    return scenes[_index_at(scenes, i, j, t)].get("scene_no")
