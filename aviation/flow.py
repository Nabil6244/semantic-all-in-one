"""Aviation Flow routing (docs/aviation/PLAN.md section 7, step 3): AI shots in one shared flight-simulator look, only where they belong.

    LOOK                         the style every Aviation Flow prompt ends with (all shots of a film match)
    prompt_for(scene, row)       the CSV's own prompt + LOOK, else one built from the line: aircraft type, airline livery, phase of flight,
                                 place, weather and a camera that fits the phase (or the cockpit, for crew lines)
    assign(scenes, plan)         scenes the CSV left open: aircraft shots between the map beats of a flight stretch (an action line -
                                 take-off, climb, storm, hold, approach, landing - at least two lines apart, never the stretch's first),
                                 and the cockpit for unnamed-crew lines
    fallback(scenes, nos, plan)  YouTube found nothing that passed: aircraft / flight / weather / unnamed-crew lines get a Flow video;
                                 a named real event or a named person never does (they get a card)
    credits(scenes, have) / question(sum)   what Generate asks before spending: Flow videos cost credits, images are free
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from . import catalog as C
from . import footage as FT
from . import router as R

LOOK = ("photorealistic flight-simulator documentary shot, true-to-life aircraft and terrain, natural light, smooth slow camera move, "
        "no text, no captions, no watermark, only the airline's own livery markings")
VIDEO_CREDITS = 10
_ACTION = re.compile(r"\b(take[sn]?\s+off|took\s+off|takeoff|climb\w*|descen\w*|approach\w*|land(?:s|ed|ing)?|touch\w*\s+down|"
                     r"hold(?:ing)?|orbit\w*|storm\w*|cloud\w*|rain|turbulence|divert\w*|go-?around|cruis\w*|taxi\w*)\b", re.I)
_CREW = re.compile(r"\b(cockpit|flight\s+deck|pilots?|captain|first\s+officer|the\s+crew)\b", re.I)
_PHASE_WORDS = (("taking off from the runway", "low runway-side camera tracking the aircraft", r"\btak(?:e|es|ing|en)\s+off\b|\btook\s+off\b|\btakeoff\b"),
                ("on final approach", "camera below the approach path looking up at the aircraft", r"\bapproach\w*|\bdescen\w*"),
                ("landing on a wet runway", "low camera beside the runway as the wheels touch down", r"\bland(?:s|ed|ing)?\b|\btouch\w*\s+down"),
                ("in a holding pattern", "wide aerial camera circling with the aircraft", r"\bhold(?:ing)?\b|\borbit\w*"),
                ("climbing out", "chase camera from behind the left wing", r"\bclimb\w*"),
                ("cruising above the clouds", "chase camera from behind the left wing", r"\bcruis\w*"),
                ("taxiing to the runway", "low camera on the taxiway", r"\btaxi\w*"))


def _ids(row: Dict[str, Any], c: Any) -> tuple:
    airline = C.get_airline(row.get("airline") or "") or (c.airlines[0] if c.airlines else None)
    aircraft = C.get_aircraft(row.get("aircraft") or "") or (c.aircraft[0] if c.aircraft else None)
    return airline, aircraft


def prompt_for(scene: Dict[str, Any], row: Optional[Dict[str, Any]] = None) -> str:
    own = str(scene.get("prompt") or "").strip()
    if own and str(scene.get("asset_type") or "").startswith("flow") or (own and not scene.get("asset_type")):
        own = own.split("||")[0].strip().rstrip(".")
        return f"{own}. {LOOK}"
    row = row or {}
    text = str(scene.get("text") or "")
    c = R.classify(text)
    airline, aircraft = _ids(row, c)
    plane = aircraft["name"] if aircraft else "a twin-engine airliner"
    livery = f" in {airline['name']} livery" if airline else ""
    place = c.airports[-1]["city"] if c.airports else ""
    if _CREW.search(text) and not _ACTION.search(text):
        return (f"Inside the cockpit of {plane}{livery}: two pilots in uniform at work, instruments glowing, the view ahead through the "
                f"windscreen{(' over ' + place) if place else ''}, camera over the captain's shoulder. {LOOK}")
    low = text.lower()
    phase, camera = "flying", "chase camera from behind the left wing"
    for ph, cam, rx in _PHASE_WORDS:
        if re.search(rx, low):
            phase, camera = ph, cam
            break
    weather = ""
    if re.search(r"\b(storm\w*|thunder\w*|hail|monsoon|heavy rain|rain)\b", low):
        weather = " through dark storm clouds and heavy rain"
    elif re.search(r"\bcloud\w*", low):
        weather = " through towering clouds"
    where = f" at {place}" if place and phase in ("taking off from the runway", "landing on a wet runway", "taxiing to the runway") else \
        (f" near {place}" if place else "")
    return f"{plane}{livery} {phase}{where}{weather}, {camera}. {LOOK}"


def _named_event_or_person(c: Any) -> bool:
    if c.mode == "news" and (c.values.get("dates") or re.search(r"\b(strike|launch\w*|crash\w*|merger|bankrupt\w*|announce\w*)\b", c.text, re.I)):
        return True
    return bool(FT._person(c))


def assign(scenes: List[Dict[str, Any]], plan: Any, rows: Optional[Sequence[dict]] = None) -> int:
    """Aircraft shots between the map beats of flight stretches, and the cockpit for unnamed-crew lines (only where the CSV left the
    asset type open). Returns how many scenes were given a Flow video."""
    n = 0
    last = -10
    prev_mode = None
    for i, (sc, mode) in enumerate(zip(scenes, plan.modes)):
        row = (rows[i] if rows and i < len(rows) else None) or {}
        open_ = not str(sc.get("asset_type") or "").strip()
        in_map = mode in ("flight", "weather")
        first_of_stretch = in_map and prev_mode not in ("flight", "weather")
        prev_mode = mode
        if not open_:
            continue
        text = str(sc.get("text") or "")
        c = R.classify(text)
        crew = _CREW.search(text) and not FT._person(c)
        if in_map and not first_of_stretch and _ACTION.search(text) and i - last >= 2 or (crew and mode in ("people", "flight") and i - last >= 2):
            sc["asset_type"] = "flow_video"
            sc["prompt"] = prompt_for({"text": text}, row)
            last = i
            n += 1
    return n


def fallback(scenes: List[Dict[str, Any]], nos: Sequence[str], plan: Any, rows: Optional[Sequence[dict]] = None) -> int:
    want = {str(x) for x in nos}
    n = 0
    for i, sc in enumerate(scenes):
        if str(sc.get("scene_no")) not in want:
            continue
        c = R.classify(str(sc.get("text") or ""))
        mode = plan.modes[i] if i < len(plan.modes) else c.mode
        c.mode = mode
        if _named_event_or_person(c) or mode not in ("fleet", "flight", "weather", "people"):
            continue
        row = (rows[i] if rows and i < len(rows) else None) or {}
        sc["asset_type"] = "flow_video"
        sc["prompt"] = prompt_for({"text": sc.get("text", "")}, row)
        n += 1
    return n


def credits(scenes: Sequence[Dict[str, Any]], have: Optional[set] = None) -> Dict[str, int]:
    have = {str(x) for x in (have or set())}
    v = sum(1 for s in scenes if s.get("asset_type") == "flow_video" and str(s.get("scene_no")) not in have)
    im = sum(1 for s in scenes if s.get("asset_type") == "flow_image" and str(s.get("scene_no")) not in have)
    return {"videos": v, "images": im, "credits": v * VIDEO_CREDITS}


def question(s: Dict[str, int]) -> str:
    parts = []
    if s["videos"]:
        parts.append(f"{s['videos']} Flow videos = {s['credits']} credits")
    if s["images"]:
        parts.append(f"{s['images']} Flow images (free)")
    return ("This film needs " + " and ".join(parts) + " for the aircraft, cockpit and storm shots nobody filmed.\n\n"
            "Yes: make them.  No: those scenes use the map or cards instead.")
