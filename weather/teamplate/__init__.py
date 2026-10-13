"""Weather Teamplate: a second editing style for Weather videos (Forecast, News, Post-Event).

The data, the beats, the narration, the CSV files and the renderer are the same as the Weather style's. What changes is the edit,
taken from the reference video the style was built from (a 20-minute coastal-flooding documentary, see docs/weather/teamplate.md):

  - cuts, not dissolves: footage cuts on a frame (Hybrid's dissolve becomes one frame), and the map cuts between beats instead of
    flying (the opening establishing move is kept);
  - footage first: a long stock shot is cut into ~5 s shots of the same subject (teamplate.footage.split_long_shots); a stock
    request that does not match what the narration describes is refused (teamplate.footage.relevance_problems);
  - titles are moments, not HUD furniture: a beat title is a keyword card (white heavy words, the key word in a red box) over a
    darkened frame for about 3 s, then a small black context tag; the video's first title is a chapter card (a serif italic
    kicker over a tracked title); a counter is a big count-up number with its label; places are orange tags with a pulse ring;
  - the map is graded darker and less saturated (radar, satellite and warning colours are not touched) with a soft vignette.

Every string on screen is the one Weather formatted from the data (weather/events.py and the layer modules); this module only moves,
times and restyles them. Nothing here is used unless a project picks the style (weather/weather.json "edit_style": "teamplate"),
so the Weather style's output is unchanged."""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

NAME = "Weather Teamplate"
KEY = "teamplate"
CLASSIC = "classic"
STYLES = {CLASSIC: "Weather", KEY: NAME}


def normalize(style: Optional[str]) -> str:
    """'teamplate' / 'Weather Teamplate' -> 'teamplate'; anything else (absent, unknown) -> 'classic'."""
    s = str(style or "").strip().lower()
    return KEY if s in (KEY, NAME.lower()) else CLASSIC


# ---- the style, as measured from the reference --------------------------------------------------------------------------
# Shot lengths: 185 shots in 1205 s, median 5.0 s, mean 6.5 s; most shots are 5 s, graphic holds 10 s, the opening montage ~4 s.
SHOT_S = 5.0                 # target footage shot
SHOT_SPLIT_FROM_S = 9.0      # a single stock shot at least this long is cut into ~SHOT_S shots
MAX_SHOTS = 4
CUT_S = 1.0 / 30.0           # a "dissolve" of one frame is a cut
RETURN_GRACE_S = 0.3
# Titles: keyword cards are up ~3 s; chapter cards (date kicker + title) ~4 s; the frame dims while they are up.
KEYWORD_HOLD_S = 3.2
CHAPTER_HOLD_S = 4.2
TAG_MAX_S = 12.0             # the black context tag after a keyword card
STAT_BIG_S = 6.0             # a counter's big count-up before it settles into a corner tag
DIP_IN_S, DIP_OUT_S = 0.35, 0.45
# Map look: the reference's maps are dark and muted, the colour kept for data. A raster grade on the base imagery only.
MAP_GRADE = {"saturation": -0.30, "contrast": 0.10, "brightness_min": 0.0, "brightness_max": 0.84, "hue_rotate": 0}
PUSH_ZOOM = 0.22             # the slow push-in after a map cut (zoom levels over the hold)
PUSH_MIN_S = 4.0


# ---- the plan (before Hybrid compiles it) ----------------------------------------------------------------------------------

def apply_plan(plan, notes: Optional[List[str]] = None) -> None:
    """Teamplate's edit of a Hybrid plan, in place: cuts instead of dissolves, long stock shots cut into shots of ~5 s."""
    from .footage import split_long_shots

    from dataclasses import replace

    from hybrid.plan import free_interval

    plan.settings["dissolve_s"] = CUT_S
    plan.settings["return_grace_s"] = RETURN_GRACE_S
    split_long_shots(plan, notes)
    # a camera move written at the very start of a map beat that follows footage would start inside the cut: start it after the cut
    for i, b in enumerate(plan.beats):
        if b.mode == "footage":
            continue
        lo, _hi = free_interval(plan, i)
        b.camera = [replace(c, t=lo) if c.action != "start" and lo - 0.1 <= c.t < lo else c for c in b.camera]


# ---- the compiled spec (what the engine draws) -----------------------------------------------------------------------------

def _frame_ceil(t: float, fps: float) -> float:
    return math.ceil(t * fps - 1e-6) / fps


def _footage(events) -> List[List[float]]:
    spans = sorted([float(e["t_in"]), float(e["t_out"])] for e in events if e.get("type") == "media_full")
    out: List[List[float]] = []
    for a, b in spans:
        if out and a <= out[-1][1] + 1e-9:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _under_footage(t: float, windows) -> bool:
    return any(a - 1e-6 <= t <= b + 1e-6 for a, b in windows)


def cut_camera(camera: Dict[str, Any], fps: float, duration: float, footage) -> Dict[str, Any]:
    """The map cuts between beats: every fly_to after the opening becomes a one-frame move (no flight over the globe), followed by a
    slow push-in while the map holds. The opening move (the establishing zoom from the globe, in the first 3 s) is kept."""
    cam = copy.deepcopy(camera or {})
    moves = sorted(cam.get("moves") or [], key=lambda m: m["t"])
    out = []
    for i, m in enumerate(moves):
        if m.get("type") != "fly_to" or m["t"] < 3.0 or _under_footage(m["t"], footage):
            out.append(m)
            continue
        t = _frame_ceil(m["t"], fps)
        cut = {"type": "push_in", "t": t, "dur": 0.5 / fps, "to": dict(m["to"]), "easing": "linear"}
        out.append(cut)
        # the hold after the cut gets a slow push-in, until the next move or the next footage
        nxt = min([n["t"] for n in moves[i + 1:]] + [a for a, _b in footage if a > t] + [duration])
        start = t + 1.0 / fps
        dur = min(10.0, nxt - start - 0.2)
        if dur >= PUSH_MIN_S:
            out.append({"type": "push_in", "t": start, "dur": dur, "to": {"zoom": float(m["to"]["zoom"]) + PUSH_ZOOM}, "easing": "inOut"})
    cam["moves"] = out
    return cam


def split_keyword(label: str) -> Dict[str, Any]:
    """'THE PATH' -> words ['THE', 'PATH'], the key word (red box) the last one; '*BOTTOM* OF BLUFF' marks it explicitly."""
    words = [w for w in str(label).split() if w]
    accent = len(words) - 1
    for i, w in enumerate(words):
        if len(w) > 2 and w.startswith("*") and w.endswith("*"):
            accent = i
    return {"words": [w.strip("*") for w in words], "accent": max(0, accent)}


def _merge(spans: List[List[float]]) -> List[List[float]]:
    out: List[List[float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 0.8:   # two cards close together share one dip (no flicker between them)
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def apply_spec(spec: Dict[str, Any], weather: Dict[str, Any]) -> "tuple[Dict[str, Any], Dict[str, Any]]":
    """(spec, weather part) restyled for Teamplate; new dicts, the arguments are not changed. Every string drawn is one the spec or the
    weather part already carried: titles, counters and labels are re-timed and re-typed, never re-worded."""
    spec = copy.deepcopy(spec)
    part = copy.deepcopy(weather)
    fps = float(spec.get("fps") or 30)
    duration = float(spec.get("duration") or 0)
    events = list(spec.get("events") or [])
    footage = _footage(events)
    camera = cut_camera(spec.get("camera") or {}, fps, duration, footage) if spec.get("camera") else spec.get("camera")
    cuts = [m["t"] + m["dur"] for m in (camera or {}).get("moves") or [] if m.get("type") == "push_in" and m["dur"] < 1.0 / fps]
    cuts += [a for a, _b in footage]

    def on_cut(t: float) -> float:
        """A card that starts just before the picture cuts waits for the cut: the reference cuts first, then builds the words."""
        later = [c for c in cuts if t - 0.05 <= c <= t + 1.2]
        return min(later) + 0.1 if later else t
    wx = list(part.get("events") or [])

    # footage: cut on a frame; a moving clip never gets a push-in (stills still do: "auto")
    for e in events:
        if e.get("type") == "media_full":
            e["dissolve_s"] = CUT_S
            e["cover_ui"] = True

    # titles: hud_title (the HUD chip, top left) -> a keyword card, then a context tag; the first one is the chapter card
    titles = sorted([e for e in events if e.get("type") == "hud_title"], key=lambda e: e["t_in"])
    events = [e for e in events if e.get("type") != "hud_title"]
    dips: List[List[float]] = []
    title_end: Dict[str, float] = {}
    for k, e in enumerate(titles):
        t0, t1 = float(e["t_in"]), float(e["t_out"])
        label, sub = str(e.get("label") or "").strip(), str(e.get("sub") or "").strip()
        if not label:
            continue
        if k == 0 and t0 < 1.0:
            a = t0 + 0.6
            b = min(t1, a + CHAPTER_HOLD_S)
            wx.append({"id": f"tp_{e['id']}", "type": "tp_title", "kind": "chapter", "title": label, "kicker": sub, "t_in": a, "t_out": b})
            dips.append([a, b])
            title_end[e["id"]] = b
            continue
        a = on_cut(t0 + 0.15)
        b = min(t1, a + KEYWORD_HOLD_S)
        if b - a < 1.2:
            continue
        wx.append({"id": f"tp_{e['id']}", "type": "tp_title", "kind": "keyword", **split_keyword(label), "t_in": a, "t_out": b})
        dips.append([a, b])
        title_end[e["id"]] = b
        if sub and t1 - b > 2.0:
            wx.append({"id": f"tp_{e['id']}_tag", "type": "tp_tag", "tone": "black", "text": sub.upper(), "t_in": b + 0.1,
                       "t_out": min(t1, b + 0.1 + TAG_MAX_S)})

    def after_title(t: float) -> float:
        """A graphic that would land on a title card waits until the card is gone."""
        for (a, b) in dips:
            if a - 0.3 <= t < b:
                return b + 0.25
        return t

    restyled = []
    for e in wx:
        typ = e.get("type")
        if typ == "counter":
            big_at = after_title(float(e["t_in"]))
            n = {**e, "type": "tp_stat", "big_in": big_at, "big_out": min(float(e["t_out"]), big_at + STAT_BIG_S)}
            if n["big_out"] - n["big_in"] >= 1.5:
                dips.append([n["big_in"], n["big_out"]])
            restyled.append(n)
        elif typ == "place_label":
            restyled.append({**e, "type": "tp_place"})
        elif typ == "headline":
            restyled.append({**e, "type": "tp_lower"})
        elif typ in ("source_line", "footage_credit") or str(typ).startswith("tp_"):
            restyled.append(e)
        else:   # a data graphic arriving under a card comes in just after it (the card speaks alone, as in the reference)
            t_in = after_title(float(e["t_in"]))
            restyled.append({**e, "t_in": t_in} if float(e["t_out"]) - t_in >= 2.0 else e)

    # nothing else talks while a card is up: map tags step aside under every dip and come back after it
    cards = _merge(dips)
    # and no place name or date sits over footage (generic stock is never captioned as the event): tags step aside under it too
    for e in restyled:
        if e["type"] in ("tp_place", "tp_tag", "tp_lower"):
            quiet = (cards if e["type"] == "tp_place" else []) + [list(w) for w in footage]
            e["hide"] = [[a, b] for a, b in _merge(quiet) if a < float(e["t_out"]) and b > float(e["t_in"])]
    for k, (a, b) in enumerate(cards):
        restyled.append({"id": f"tp_dip_{k + 1}", "type": "tp_dip", "t_in": max(0.0, a - 0.1), "t_out": min(duration or b + 0.6, b + 0.35)})
    if duration > 0:
        restyled.append({"id": "tp_vignette", "type": "tp_vignette", "t_in": 0.0, "t_out": duration})

    spec["events"] = events
    spec["camera"] = camera
    spec["imagery"] = {**(spec.get("imagery") or {}), "grade": dict(MAP_GRADE)}
    part["events"] = restyled
    return spec, part
