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

from . import footage as FT
from . import gfx as G
from . import hud as U
from . import router as R

STRONG = 3.0
MAP_MODES = ("flight", "weather")
MAX_MAP_S = 30.0
BREAK_S = 4.0
OPEN_S = 6.0
CARD_GAP_S = 10.0             # never two cards closer than this
CARD_EVERY_S = 16.0           # after this long without a card, any line that names something may carry one
_HOLD = re.compile(r"\b(hold|holding|orbit|orbits|racetrack)\b", re.I)
_END = re.compile(r"\bstory of\s+((?:[A-Z][\w\-']*|\d+)(?:\s+(?:[A-Z][\w\-']*|\d+))*)")


@dataclass
class Plan:
    shots: List[Dict[str, Any]] = field(default_factory=list)
    modes: List[str] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)


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


def _fact(text: str, limit: int = 110) -> str:
    t = text.strip()
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def plan(scenes: Sequence[Dict[str, Any]], rows: Optional[Sequence[dict]] = None) -> Plan:
    texts = [str(s.get("text") or "") for s in scenes]
    cls = R.route_script(texts)
    _PREV_Q.clear()
    forced, modes = [], []
    for i, c in enumerate(cls):
        r = _row(rows, i)
        if r.get("mode") in R.MODES:
            modes.append(r["mode"]); forced.append(True)
        else:
            modes.append(c.mode); forced.append(False)
    modes = _smooth(cls, modes, forced)
    hplan = U.hud_plan(cls)
    out = Plan(modes=modes)
    for i, c in enumerate(cls):
        out.log.append({"scene": scenes[i].get("scene_no", i + 1), "mode": modes[i],
                        "why": ("csv" if forced[i] else "router: " + "; ".join(c.reasons[:4]) or "neutral")})

    # stretches of the same look (flight and weather share one map)
    def group(m: str) -> str:
        return "map" if m in MAP_MODES else m

    i = 0
    news_last_card = 0.0            # the card rhythm runs across stretches; the cold open (OPEN_S) is the video's start
    while i < len(scenes):
        j = i
        while j + 1 < len(scenes) and group(modes[j + 1]) == group(modes[i]):
            j += 1
        g = group(modes[i])
        if g == "map":
            _map_stretch(out, scenes, cls, rows, hplan, i, j)
        else:
            news_last_card = _clip_stretch(out, scenes, cls, rows, modes, i, j, news_last_card)
        i = j + 1

    # the next-episode card on a line that says 'the story of X'
    for k, s in enumerate(scenes):
        m = _END.search(texts[k])
        if m and k >= len(scenes) - 2:
            _replace_with(out, s["start"], s["end"], {"layer": "gfx.lay_end_card", "start": s["start"], "end": s["end"],
                                                      "scene": s.get("scene_no"), "full_frame": True,
                                                      "params": {"kicker": "THE STORY OF", "title": m.group(1).strip()}})
    out.shots.sort(key=lambda x: (x["start"], 0 if x.get("full_frame") or x.get("kind") == "footage" else 1))
    return out


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


def _clip_stretch(out: Plan, scenes, cls, rows, modes, i: int, j: int, last_card: float) -> float:
    s0 = scenes[i]["start"]
    for k in range(i, j + 1):
        s, c, r, mode = scenes[k], cls[k], _row(rows, k), modes[k]
        a, b = s["start"], s["end"]
        sc = s.get("scene_no", k + 1)
        card = None
        if mode == "evidence":
            card = {"layer": "war.lay_document", "params": {"text": c.text, "highlight": c.text}}
        elif r.get("article"):
            card = {"layer": "cards.lay_article", "params": dict(r["article"], image_from="footage")}
        elif mode in ("news", "numbers", "fleet") and a >= OPEN_S and a - last_card >= CARD_GAP_S and \
                (b - a) >= 2.0 and (mode != "fleet" or c.values["counts"]) and _card_worthy(c, a - max(last_card, 0.0)):
            card = {"layer": "cards.lay_article", "params": {"fact": _fact(c.text), "image_from": "footage"}}
        if card:
            card.update(start=a, end=b, scene=sc, full_frame=True, mode=mode)
            out.shots.append(card)
            if card["layer"] == "cards.lay_article":
                last_card = a
            continue
        lo, hi = FT.cut_range(mode)
        q = _queries(c, r)
        for x, y in _slots(a, b, lo, hi):
            out.shots.append({"kind": "footage", "start": x, "end": y, "scene": sc, "mode": mode, "queries": q, "cut": (lo, hi)})
        counters = G.counters_from(c.values)
        if counters:
            out.shots.append({"layer": "gfx.lay_counters", "start": a, "end": b, "scene": sc, "params": {"items": counters}})
    return last_card


def _map_stretch(out: Plan, scenes, cls, rows, hplan, i: int, j: int) -> None:
    t0, t1 = scenes[i]["start"], scenes[j]["end"]
    airports: List[str] = []
    prm: Dict[str, Any] = {"airports": airports, "storms": [], "callouts": []}

    def seen(a: str) -> None:
        if a and a not in airports:
            airports.append(a)

    last_airport = ""
    for k in range(i, j + 1):
        s, c, r = scenes[k], cls[k], _row(rows, k)
        rel = s["start"] - t0
        named = [a["id"] for a in c.airports]
        for a in named + [r.get("from") or "", r.get("to") or ""]:
            seen(a)
        frm, to = r.get("from") or "", r.get("to") or ""
        if not (frm and to) and len(named) >= 2:
            frm, to = named[0], named[1]
        if frm and to and frm != to and "route" not in prm:
            prm["route"] = {"from": frm, "to": to, "start": rel + 0.3, "length": max(2.0, (s["end"] - s["start"]) * 1.5)}
        elif frm and to and frm != to and prm.get("route") and k > i:
            # a later leg: the flown track continues to the new airport
            prm.setdefault("track", [prm["route"]["from"], prm["route"]["to"]])
            if prm["track"][-1] != to:
                prm["track"].append(to)
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
        fuel = (r["fuel"], r["fuel"]) if r.get("fuel") else (hp or {}).get("fuel")
        tim = (r["time"], r["time"]) if r.get("time") else (hp or {}).get("time")
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
    # one map, split by short footage breaks when it runs long (it carries on, never restarts)
    total = t1 - t0
    pos = t0
    while pos < t1 - 1e-6:
        end = min(t1, pos + MAX_MAP_S)
        if t1 - end < BREAK_S + 2.0:
            end = t1
        out.shots.append({"layer": "flightmap.lay_flight_map", "start": pos, "end": end, "full_frame": True, "mode": "flight",
                          "scene": _scene_at(scenes, i, j, pos),
                          "params": dict(prm, t0=pos - t0, total=total)})
        if end >= t1 - 1e-6:
            break
        k = _index_at(scenes, i, j, end)
        out.shots.append({"kind": "footage", "start": end, "end": end + BREAK_S, "scene": scenes[k].get("scene_no"), "mode": "flight",
                          "queries": _queries(cls[k], _row(rows, k)) or ["airliner flying above clouds"], "cut": (BREAK_S, BREAK_S)})
        pos = end + BREAK_S


def _index_at(scenes, i: int, j: int, t: float) -> int:
    for k in range(i, j + 1):
        if scenes[k]["start"] <= t < scenes[k]["end"]:
            return k
    return j


def _scene_at(scenes, i: int, j: int, t: float):
    return scenes[_index_at(scenes, i, j, t)].get("scene_no")
