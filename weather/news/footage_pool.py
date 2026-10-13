"""The footage pool of one weather event: clips proposed from public-domain and Creative Commons sources, each checked for
relevance and licence before anyone can approve it (docs/weather/weather_style_plan.md §6).

Relevance (both needed):
  - its date (NASA date_created, Commons date taken, YouTube publish date) falls inside the event window, from `before_days`
    before the event starts to `after_days` after it ends (footage of an event is published during it and in the weeks after);
  - the event's name or one of its places is named in the title or the description.
Licence:
  - NASA: public domain (a description crediting someone else is flagged for a check);
  - Commons: CC0, public domain (incl. US government works), CC BY and CC BY-SA; never NC, ND, fair use or an unknown licence;
  - YouTube: Creative Commons Attribution (YouTube's CC BY), or a US government channel (public domain, checked per clip);
    a standard-licence video from anyone else (news, storm chasers) is off (plan §6, tier 4).
A clip that fails the licence rule is rejected with the reason; one that passes stays "proposed" until the user approves it.
Credits: "Video: NASA", "Video: NOAA (public domain)", "CC BY 4.0 — <author>", "CC BY — <channel> (YouTube)"."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from . import sources
from .timeline import UTC

STATUSES = ("proposed", "approved", "rejected")
GOV_CHANNELS = {"nasa", "nasa video", "nasa goddard", "noaa", "noaa satellites", "national weather service", "nws", "fema",
                "u.s. geological survey", "usgs", "u.s. army corps of engineers", "u.s. coast guard", "uscg", "dvidshub", "nhc", "noaa nhc",
                "national hurricane center"}
OK_COMMONS = re.compile(r"^(cc0|cc[- ]zero|public domain|pd(-[\w.-]+)?|cc[- ]by(-sa)?[- ]?\d(\.\d)?|cc[- ]by(-sa)?)$", re.I)
BAD_COMMONS = re.compile(r"(nc|nd|non-?commercial|no ?deriv|fair ?use)", re.I)


@dataclass
class Event:
    name: str  # "Hurricane Ian"
    start: str  # YYYY-MM-DD
    end: str
    places: List[str] = field(default_factory=list)  # ["Fort Myers", "Florida", "Cayo Costa"]
    keywords: List[str] = field(default_factory=list)  # other names ("Ian")
    before_days: int = 2
    after_days: int = 30

    def window(self) -> "tuple[datetime, datetime]":
        a = datetime.strptime(self.start, "%Y-%m-%d").replace(tzinfo=UTC) - timedelta(days=self.before_days)
        b = datetime.strptime(self.end, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=self.after_days + 1)
        return a, b

    def names(self) -> List[str]:
        return [n for n in [self.name, *self.keywords, *self.places] if n]


@dataclass
class Clip:
    id: str
    source: str  # nasa | commons | youtube
    source_id: str
    title: str
    description: str = ""
    date: str = ""
    place: str = ""
    author: str = ""
    licence: str = ""
    licence_url: str = ""
    page_url: str = ""
    media_url: str = ""
    assets_url: str = ""
    credit: str = ""
    status: str = "proposed"
    reasons: List[str] = field(default_factory=list)  # why rejected, or what to check
    notes: List[str] = field(default_factory=list)
    channel_id: str = ""
    duration: Optional[float] = None
    decided: bool = False  # the user approved or rejected it (approval.py); the rules then only refresh the credit
    local_path: str = ""  # set once the clip is downloaded (approval.py)
    start_s: float = 0.0  # the part of the clip to use
    dur_s: float = 0.0
    use: str = ""  # historical | illustrative (the user's choice in the clip screen; shown on the credit chip)
    beat: str = ""  # the beat (narration segment) the clip is proposed for

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Clip":
        known = {k: d[k] for k in Clip.__dataclass_fields__ if k in d}
        return Clip(**known)


def _named(text: str, name: str) -> bool:
    return re.search(r"(?<![A-Za-z])" + re.escape(name.lower()) + r"(?![A-Za-z])", text.lower()) is not None


def relevance(clip: Clip, ev: Event) -> List[str]:
    """Why a clip is NOT relevant to the event ([] = relevant)."""
    out = []
    when = sources.parse_date(clip.date)
    a, b = ev.window()
    if when is None:
        out.append("it has no date, so it cannot be tied to the event")
    elif not a <= when < b:
        out.append(f"its date {clip.date} is outside the event window ({a:%Y-%m-%d} to {(b - timedelta(days=1)):%Y-%m-%d})")
    text = f"{clip.title} {clip.description}"
    if not any(_named(text, n) for n in ev.names()):
        out.append(f"neither the title nor the description names {', '.join(ev.names())}")
    return out


def licence_check(clip: Clip) -> "tuple[bool, str, List[str]]":
    """(allowed, credit text, notes)."""
    lic = (clip.licence or "").strip()
    if clip.source == "nasa":
        return True, "Video: NASA", list(clip.notes)
    if clip.source == "commons":
        if not lic or BAD_COMMONS.search(lic.replace("CC BY", "")) or not OK_COMMONS.match(lic.replace("_", " ")):
            return False, "", [f"Commons licence {lic or 'unknown'} is not allowed (CC0, public domain, CC BY or CC BY-SA only)"]
        if re.match(r"^(cc0|cc[- ]zero|public domain|pd)", lic, re.I):
            return True, f"Video: {clip.author or 'Wikimedia Commons'} (public domain)", []
        return True, f"{lic.upper().replace('CC-BY', 'CC BY').replace('-SA', '-SA')} — {clip.author or 'unknown author'}", []
    if clip.source == "youtube":
        if "creative commons" in lic.lower():
            return True, f"CC BY — {clip.author} (YouTube)", []
        if clip.author.strip().lower() in GOV_CHANNELS:
            return True, f"Video: {clip.author} (public domain)", ["a US government channel: check that this upload has no third-party footage"]
        return False, "", [f"YouTube licence {lic or 'standard'} from {clip.author or 'an unknown channel'}: only Creative Commons videos or US "
                           "government channels may be used (news and storm-chaser clips are off)"]
    return False, "", [f"unknown source {clip.source}"]


def assess(clip: Clip, ev: Event) -> Clip:
    """Fill credit/status/reasons from the rules. The user's decision stands, except that a clip whose licence is not allowed is
    never approved."""
    ok, credit, notes = licence_check(clip)
    why = relevance(clip, ev)
    clip.credit = credit
    if clip.decided and (ok or clip.status == "rejected"):
        return clip
    if not ok:
        clip.status, clip.reasons = "rejected", notes
    elif why:
        clip.status, clip.reasons = "rejected", [f"not relevant: {w}" for w in why]
    else:
        clip.status, clip.reasons = "proposed", notes
    return clip


def search(ev: Event, get_text: Callable[[str], str], *, youtube_ids: Optional[List[str]] = None,
           yt_extract: Optional[Callable[[str], Dict[str, Any]]] = None, use_commons: bool = True) -> "tuple[List[Clip], List[str]]":
    """(clips, problems): every source searched for the event, each clip assessed. A source that cannot be reached is skipped
    and named in problems."""
    a, b = ev.window()
    found: Dict[str, Clip] = {}
    problems: List[str] = []
    try:
        for d in sources.nasa_clips(get_text(sources.nasa_search_url(ev.name, a.year, b.year))):
            found.setdefault(d["id"], Clip.from_dict(d))
    except Exception as exc:  # noqa: BLE001 - a search source being down must not stop the others
        problems.append(f"NASA search failed: {exc}")
    if use_commons:
        try:
            for d in sources.commons_clips(get_text(sources.commons_search_url(ev.name))):
                found.setdefault(d["id"], Clip.from_dict(d))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"Wikimedia Commons search failed: {exc}")
    for vid in youtube_ids or []:
        try:
            d = sources.youtube_clip(vid, sources.youtube_info(vid, yt_extract))
            found.setdefault(d["id"], Clip.from_dict(d))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"YouTube {vid}: {exc}")
    clips = [assess(c, ev) for c in found.values()]
    return sorted(clips, key=lambda c: (STATUSES.index(c.status), c.date, c.id)), problems
