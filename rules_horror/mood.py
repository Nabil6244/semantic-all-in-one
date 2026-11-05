"""The colour follows the narration. Each row gets a mood from what the voice says (and the row's set and actions); a row with no signal keeps the mood
before it, so the colour changes when the story changes and not row by row. A `mood` cell in the CSV always wins.

night (default): navy dark | warm: amber lamp-lit rooms | cold: teal, tile, glass, water | red: danger, the scare | day: daylight, shops, school | dawn: first light."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

MOODS = ("night", "warm", "cold", "red", "day", "dawn")
_RULES = (   # most specific first; the first mood with a hit in the narration wins
    ("dawn", r"\b(sun come up|sunrise|first light|dawn|daybreak|see the sun)\b"),
    ("red", r"\b(scream\w*|blood\w*|bleed\w*|dead|die|dies|dying|kill\w*|trapped|teeth|panic\w*|run|ran|hunt\w*|grab\w*|too late|smile stretched|pressed flat)\b"),
    ("warm", r"\b(warm|yellow light|lamp\w*|candle\w*|fire|coffee|kitchen|cozy|lit house|somebody has been home|lived in)\b"),
    ("cold", r"\b(cold|ice|winter|freez\w*|tile|glass|mirror\w*|reflection\w*|water|tap|fog\w*|frost|sink|faucet|pane)\b"),
    ("day", r"\b(daylight|noon|afternoon|morning sun|sunny|bright|shop|store|school|class|office|bus)\b"),
)
_SET_MOOD = {"kitchen": "warm", "store": "day", "classroom": "day", "bathroom": "cold", "hall_mirror": "cold", "street": "night", "yard": "night"}
_ACTION_MOOD = {"glitch": "red", "red_eyes": "red", "mirror_press": "red", "cross": "red"}


def row_mood(row: Dict[str, Any]) -> Optional[str]:
    given = str(row.get("mood") or "").strip().lower()
    if given in MOODS:
        return given
    acts = set(str(row.get("action") or "").split("+"))
    for a, m in _ACTION_MOOD.items():
        if a in acts:
            return m
    text = f"{row.get('line', '')}".lower()
    for mood, pat in _RULES:
        if re.search(pat, text):
            return mood
    if row.get("set") in ("kitchen", "store", "classroom", "bathroom", "hall_mirror"):
        return _SET_MOOD[row["set"]]
    return None


def moods_for(rows: List[Dict[str, Any]], start: str = "night") -> List[str]:
    """One mood per row: a row's own signal, else the mood before it."""
    out, cur = [], start
    for r in rows:
        m = row_mood(r)
        if m:
            cur = m
        out.append(cur)
    return out
