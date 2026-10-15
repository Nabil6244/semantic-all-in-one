"""Format and editing style picked from the script, for script + voiceover -> video with no CSV (docs/weather/script_to_video_plan.md).

    detect_format(script) -> "forecast" | "news" | "post"
    style_for(fmt)        -> "teamplate" (News, Post-Event) | "classic" (Forecast)

Read deterministically from the words (no AI, no network). "auto" is what the Weather card and weather.json store when the user has
not picked a format or a style; an explicit pick always wins."""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

AUTO = "auto"
FORMATS = ("forecast", "news", "post")

FORECAST_CUES = ("forecast", "tomorrow", "tonight", "this weekend", "this week", "next week", "next few days", "coming days", "expect",
                 "will see", "will bring", "highs", "lows", "chance of", "by the weekend", "later this week", "the days ahead")
AFTERMATH_CUES = ("aftermath", "survey", "surveyed", "damage survey", "cleanup", "clean up", "recovery", "rebuild", "rebuilding",
                  "looking back", "years ago", "anniversary", "left behind", "death toll", "killed", "in the end", "final total",
                  "totals", "when it was over", "the days after", "since then")
NOW_CUES = ("right now", "currently", "unfolding", "this morning", "this afternoon", "this evening", "on the ground", "in effect",
            "until", "issued", "is moving", "are moving", "is expected", "take shelter", "if you are in", "if you're in", "live")


def _count(low: str, cues) -> int:
    return sum(len(re.findall(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", low)) for c in cues)


def detect_format(script: str, today: Optional[date] = None) -> str:
    """Forecast when the script looks ahead and names no event happening now; Post-Event when it looks back at an event (aftermath
    words, or a year before this one); News otherwise (an event happening now, or anything unclear)."""
    low = " ".join(str(script or "").lower().replace("’", "'").split())
    if not low:
        return "news"
    year = (today or date.today()).year
    past_years = {int(y) for y in re.findall(r"\b(19[5-9]\d|20\d\d)\b", low) if int(y) < year}
    ahead, after, now = _count(low, FORECAST_CUES), _count(low, AFTERMATH_CUES), _count(low, NOW_CUES)
    after += 2 if past_years else 0
    if ahead >= 3 and ahead > now + after:
        return "forecast"
    if after >= 3 and after > now:
        return "post"
    return "news"


def style_for(fmt: str) -> str:
    """News and Post-Event are footage-led stories (Weather Teamplate); a forecast is map-led (classic Weather)."""
    return "classic" if fmt == "forecast" else "teamplate"


def resolve_format(saved: Optional[str], script: str) -> str:
    s = str(saved or "").strip().lower()
    return s if s in FORMATS else detect_format(script)


def resolve_style(saved: Optional[str], fmt: str) -> str:
    s = str(saved or "").strip().lower()
    return s if s in ("classic", "teamplate") else style_for(fmt)
