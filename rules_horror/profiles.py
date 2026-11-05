"""Nine look profiles, one per reference video (measured 2026-11-05 from all 9: frames, cut lists, loudness). A video gets ONE profile, picked from
what the story is about, so different videos look different instead of every video copying the first reference.

Pacing is measured: `max_beat` is the reference's 90th-percentile shot (seconds), `stabs` its quick cuts per minute (shots under 0.45 s: punch-ins,
flash frames). `card` is the rule-card design that video uses. Names are ours; no titles or art are taken from the channel."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional

PROFILES: Dict[str, Dict[str, Any]] = {
    # white line-art on black, one red accent, long holds
    "line_house":   dict(family="line", scheme="mono", card="black", max_beat=8.0, stabs=8.0, look=dict(vignette=0.34, grain=0.05),
                         words=r"deer|yard|porch|house|window|3 ?am|three in the morning|bedroom|neighbou?r|farm|field"),
    "line_pet":     dict(family="line", scheme="mono", card="black", max_beat=7.0, stabs=5.3, look=dict(vignette=0.36, grain=0.05),
                         words=r"dog|puppy|pet|cat|wolf|coyote|leash|bark"),
    "line_exam":    dict(family="line", scheme="mono", card="dim", max_beat=5.9, stabs=5.4, look=dict(vignette=0.38, grain=0.05),
                         words=r"\btest\b|exam|pencil|answer sheet|quiz|detention|study hall"),
    # dark navy cartoon, faces with grins, rule card over the dimmed scene
    "night_flight": dict(family="night", scheme="dark", card="dim", max_beat=4.6, stabs=5.1, look=dict(vignette=0.40, grain=0.04, saturate=0.85),
                         words=r"plane|flight|airport|cabin crew|attendant|pilot|runway|seat ?belt|turbulence|train|bus|subway"),
    "night_cinema": dict(family="night", scheme="dark", card="dim", max_beat=5.4, stabs=1.7, look=dict(vignette=0.44, grain=0.05, saturate=0.85),
                         words=r"cinema|movie|theat(?:er|re)|usher|screen|popcorn|audience|concert|stage"),
    # bright flat-colour interiors, many people, warm vignette and grain, themed rule cards, fast
    "bright_mall":  dict(family="bright", scheme="colour", card="tag", max_beat=3.3, stabs=9.3, look=dict(vignette=0.46, grain=0.07, saturate=0.9),
                         words=r"mall|boutique|mannequin|food court|escalator|fitting room|department store|hotel|lobby"),
    "bright_store": dict(family="bright", scheme="colour", card="hazard", max_beat=2.9, stabs=33.0, look=dict(vignette=0.38, grain=0.06),
                         words=r"store|supermarket|grocery|aisle|warehouse|hazmat|checkout|cashier|gas station|factory"),
    "bright_school": dict(family="bright", scheme="colour", card="paper", max_beat=2.6, stabs=25.5, look=dict(vignette=0.44, grain=0.07, saturate=0.9),
                          words=r"school|classroom|teacher|substitute|student|locker|homework|principal|library|office|hospital"),
    # underwater teal, bubbles, red eyes in the dark
    "deep_water":   dict(family="deep", scheme="deep", card="sign", max_beat=4.2, stabs=4.5, look=dict(vignette=0.42, grain=0.05),
                         words=r"aquarium|ocean|underwater|diver|diving|tank|sea|lake|pool|submarine|shark|beach|ship|boat"),
}
CARD_STYLES = ("black", "dim", "tag", "hazard", "paper", "sign")
SCHEMES = ("mono", "dark", "colour", "deep", "story")


def score(text: str) -> Dict[str, int]:
    t = text.lower()
    return {k: len(re.findall(p["words"], t)) for k, p in PROFILES.items()}


def pick(data: Dict[str, Any], given: Optional[str] = None) -> str:
    """The profile for this story: the `given` name (CSV `#look` line or the app menu) when it is a profile, else the one whose places and things the
    story mentions most. A story that matches none gets a profile from a hash of its text, so unrelated stories still spread over all nine."""
    meta = data.get("meta") or {}
    for want in (given, meta.get("look") if isinstance(meta.get("look"), str) else None):
        if want and str(want).strip().lower() in PROFILES:
            return str(want).strip().lower()
    rows = data.get("rows") or []
    text = " ".join(f"{r.get('line', '')} {r.get('set', '')} {r.get('subject', '')}" for r in rows)
    text += " " + " ".join(str(v) for v in meta.values())
    sc = score(text)
    best = max(sc.values()) if sc else 0
    if best > 0:
        return next(k for k, v in sc.items() if v == best)
    names = list(PROFILES)
    return names[int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16) % len(names)]


def get(name: str) -> Dict[str, Any]:
    return {"name": name, **PROFILES[name]}
