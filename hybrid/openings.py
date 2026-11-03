"""The first seconds of a Hybrid video: so two videos do not open the same way (every video used to open on the globe for 1.4 s and fly
in for 2.2 s). The opening is picked from the first sentence, never from a template's sample, and a type used by one of the last two
videos waits its turn. Plain rules only: no Gemini call, so a CSV run still makes none.

    globe_fly_in        the whole planet, then a fly-in (a planet-wide story, or a place few viewers could find)
    continental_fly_in  a neighbourhood of countries, then a shorter fly-in
    close_pull_back     tight on the place (local), then out to the beat's own frame (a city, a site, a front line)
    settle_in           one step wider than the beat's frame, a short glide in (a region or a city)
    push_open           already at the beat's frame, a slow push in (a story that continues: "Since 2014 ...")
    stat_open           the camera holds still under a number or a date the first sentence states (a stat layer in the first seconds)
    route_open          the camera holds still while a route the first sentence follows draws (a line layer in the first seconds)
    cold_footage        the video opens on footage (the plan's own first beat); recorded so the next video is told

The type picked is kept in plan.settings["opening_picked"], so a repair or a second derive of the same plan keeps it. Within a type,
the title-free seed (the first sentence) changes the timings a little, so two openings of one type still differ."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .plan import CameraStep, HybridPlan

FRAMES = ("globe", "continental", "country", "region", "local")
TYPES = ("globe_fly_in", "continental_fly_in", "close_pull_back", "settle_in", "push_open", "stat_open", "route_open")
HISTORY_KEEP = 8
EARLY_LAYER_S = 3.5          # a stat or a line that appears this early can lead the opening

_PLANET = re.compile(r"\b(world|worlds|global|globe|planet|earth|continents?|countries|everywhere|international|across the (world|globe))\b", re.I)
_NUMBER = re.compile(r"\b(\d[\d,.]*\s*(%|percent|million|billion|thousand|km|miles|people|years?)?|1[5-9]\d\d|20\d\d|hundreds?|thousands?|millions?|billions?)\b", re.I)
_MOVE = re.compile(r"\b(routes?|trade|traders?|migrat\w*|invad\w*|invasion|march\w*|sail\w*|flow\w*|pipelines?|journey\w*|cross\w*|travel\w*|advanc\w*|shipp\w*|smuggl\w*|corridor|border)\b", re.I)
_GOING_ON = re.compile(r"\b(since|for (years|decades|centuries)|still|again|once more|continues?|ongoing|by now|today)\b", re.I)
_SCENE = re.compile(r"\b(city|town|village|capital|street|port|harbou?r|site|base|camp|palace|square|front( line)?|bridge|dam)\b", re.I)


def _frame_i(frame: str) -> int:
    return FRAMES.index(frame) if frame in FRAMES else FRAMES.index("region")


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:8], 16)


def _jit(seed: int, k: int, lo: float, hi: float) -> float:
    """A stable number in [lo, hi] from the seed (k picks a different one)."""
    v = ((seed >> (k * 3)) ^ (seed * (k + 7))) % 1000 / 999.0
    return round(lo + (hi - lo) * v, 2)


# ---- history ------------------------------------------------------------------------------------------------------------------------

def history_path() -> Optional[Path]:
    env = os.environ.get("HYBRID_OPENING_HISTORY")
    if env:
        return Path(env).expanduser()
    if "PYTEST_CURRENT_TEST" in os.environ or getattr(getattr(sys.modules.get("__main__"), "__spec__", None), "name", "") == "unittest.__main__":
        return None  # tests (pytest, or python -m unittest as CI runs them) never read or change the real history
    return Path.home() / ".semantic_yt_studio" / "hybrid" / "openings.json"


def load_history() -> List[Dict[str, Any]]:
    p = history_path()
    if p is None or not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [h for h in data if isinstance(h, dict) and h.get("type")] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record(kind: str, key: str) -> None:
    """Put this video's opening at the front of the history. The same video (key) planned again replaces its own entry."""
    p = history_path()
    if p is None:
        return
    hist = [h for h in load_history() if h.get("key") != key]
    hist.insert(0, {"type": kind, "key": key, "at": int(time.time())})
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(hist[:HISTORY_KEEP], indent=1), encoding="utf-8")
    except OSError:
        pass  # a history that cannot be written only loses the no-repeat rule for one video


def recent_types(key: str, n: int = 2) -> List[str]:
    """The opening types of the last n OTHER videos, newest first."""
    return [h["type"] for h in load_history() if h.get("key") != key][:n]


# ---- picking ------------------------------------------------------------------------------------------------------------------------

def available(target_frame: str, room: float, early_layers: Sequence[str]) -> List[str]:
    """The types that fit this first map beat: its frame and the seconds the camera has before the first footage dissolve."""
    fi = _frame_i(target_frame)
    out = []
    if target_frame != "globe" and room >= 4.2:
        out.append("globe_fly_in")
    if fi >= 2 and room >= 3.4:
        out.append("continental_fly_in")
    if 1 <= fi <= 3 and room >= 3.8:
        out.append("close_pull_back")
    if fi >= 3 and room >= 2.8:
        out.append("settle_in")
    if room >= 2.0:
        out.append("push_open")
    if "stat" in early_layers:
        out.append("stat_open")
    if "line" in early_layers:
        out.append("route_open")
    return out


def score(kind: str, text: str, target_frame: str) -> float:
    s = 1.0
    planet, number, move = bool(_PLANET.search(text)), bool(_NUMBER.search(text)), bool(_MOVE.search(text))
    going_on, scene = bool(_GOING_ON.search(text)), bool(_SCENE.search(text))
    fi = _frame_i(target_frame)
    if kind == "globe_fly_in":
        s += 3.0 if planet else 0.0
    elif kind == "continental_fly_in":
        s += 1.5 if planet else 0.0
        s += 0.8 if fi == 2 else 0.0
    elif kind == "close_pull_back":
        s += 2.0 if scene else 0.0
    elif kind == "settle_in":
        s += 1.5 if (scene or fi == 4) else 0.5
    elif kind == "push_open":
        s += 2.0 if going_on else 0.0
    elif kind == "stat_open":
        s += 3.0 if number else 0.5
    elif kind == "route_open":
        s += 3.0 if move else 0.5
    return s


def pick(text: str, target_frame: str, room: float, early_layers: Sequence[str], recent: Sequence[str], forced: str = "") -> Tuple[str, str]:
    """(type, why). A forced type wins when it fits; otherwise the best score, after the recent ones lose their turn."""
    kinds = available(target_frame, room, early_layers)
    if not kinds:
        return "", "no room for an opening move"
    if forced in kinds:
        return forced, "set in Settings"
    seed = _seed(text)
    best, best_s, why = "", -99.0, ""
    for k, kind in enumerate(kinds):
        s = score(kind, text, target_frame) + _jit(seed, k, 0.0, 0.6)
        if recent[:1] and kind == recent[0]:
            s -= 4.0
        elif kind in recent[1:2]:
            s -= 2.5
        if s > best_s:
            best, best_s = kind, s
    if recent and best != recent[0]:
        why = f"{recent[0]} opened the last video"
    return best, why


# ---- the camera steps -------------------------------------------------------------------------------------------------------------

def steps_for(kind: str, place: str, frame: str, lo: float, hi: float, seed: int) -> List[CameraStep]:
    """The camera steps of the opening type on the first map beat (lo/hi: where the camera may move). Times are absolute."""
    fi = _frame_i(frame)
    if kind == "globe_fly_in":
        t, d = _jit(seed, 1, 1.1, 1.6), _jit(seed, 2, 2.0, 2.6)
        return [CameraStep("start", place, "globe", 0.0), CameraStep("fly_to", place, frame, t, round(min(d, hi - t - 0.2), 2))]
    if kind == "continental_fly_in":
        t, d = _jit(seed, 1, 0.8, 1.2), _jit(seed, 2, 1.8, 2.4)
        return [CameraStep("start", place, "continental", 0.0), CameraStep("fly_to", place, frame, t, round(min(d, hi - t - 0.2), 2))]
    if kind == "close_pull_back":
        tight = FRAMES[min(4, fi + (2 if fi <= 2 else 1))]
        t, d = _jit(seed, 1, 1.0, 1.5), _jit(seed, 2, 2.0, 2.6)
        return [CameraStep("start", place, tight, 0.0), CameraStep("fly_to", place, frame, t, round(min(d, hi - t - 0.2), 2))]
    if kind == "settle_in":
        t, d = _jit(seed, 1, 0.5, 0.9), _jit(seed, 2, 1.6, 2.2)
        return [CameraStep("start", place, FRAMES[fi - 1], 0.0), CameraStep("fly_to", place, frame, t, round(min(d, hi - t - 0.2), 2))]
    if kind == "push_open":
        t = 0.3
        return [CameraStep("start", place, frame, 0.0), CameraStep("push_in", t=t, dur=round(min(_jit(seed, 2, 5.0, 8.0), hi - t - 0.2), 2),
                                                                     zoom_delta=_jit(seed, 3, 0.4, 0.8))]
    # stat_open / route_open: the graphic leads, the camera stays where the story is
    return [CameraStep("start", place, frame, 0.0)]


def opening_text(plan: HybridPlan) -> str:
    """The first sentence(s) the opening follows: the first beat's narration, cut to its first ~30 words."""
    for b in plan.beats:
        if b.narration:
            return " ".join(b.narration.split()[:30])
    return ""


def apply(plan: HybridPlan, i: int, place: str, frame: str, lo: float, hi: float, *, text: str = "") -> List[CameraStep]:
    """The opening of map beat i (the plan's first, starting the video). Picks the type once per plan, records it, returns the steps."""
    text = opening_text(plan) or text or place
    key = f"{_seed(text):08x}"
    b = plan.beats[i]
    kind = str(plan.settings.get("opening_picked") or "")
    early = [l.type for l in b.layers if l.t <= EARLY_LAYER_S]
    if kind not in available(frame, hi - lo, early):
        forced = str(plan.setting("opening") or "auto")
        kind, why = pick(text, frame, hi - lo, early, recent_types(key), forced=forced if forced != "auto" else "")
        if not kind:
            return [CameraStep("start", place, frame, 0.0)]
        plan.settings["opening_picked"] = kind
        plan.settings["opening_note"] = f"opening: {kind}" + (f" ({why})" if why else "")
        record(kind, key)
    return steps_for(kind, place, frame, lo, hi, _seed(text))


def note_cold_open(plan: HybridPlan) -> None:
    """A plan whose first beat is footage opens cold: recorded, so the next video's opening is not footage-led as well."""
    if plan.settings.get("opening_picked") == "cold_footage":
        return
    text = opening_text(plan)
    plan.settings["opening_picked"] = "cold_footage"
    plan.settings["opening_note"] = "opening: cold_footage (the plan opens on footage)"
    record("cold_footage", f"{_seed(text):08x}")
