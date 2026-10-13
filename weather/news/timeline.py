"""Event time and narration time.

A Weather News layer that replays a stretch of real time (a radar loop over six hours, warnings issued through an evening,
storm reports in the order they came in) maps that real window onto its own on-screen window linearly, so layers that name
the same UTC window and share a narration window stay in step (the warning appears on the radar frame of its issue time).

Also: the UTC windows written in data_sources ("2024-05-06T21:00Z..2024-05-07T03:00Z") and the time zone of a place."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

UTC = timezone.utc
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\dZ$")
DAY = re.compile(r"^\d{4}-\d\d-\d\d$")

# The time zone most of each state lives in (a state split between two zones uses its larger part).
STATE_TZ = {
    **{s: "America/New_York" for s in "CT DE DC FL GA IN KY ME MD MA MI NH NJ NY NC OH PA RI SC VT VA WV PR".split()},
    **{s: "America/Chicago" for s in "AL AR IL IA KS LA MN MS MO NE ND OK SD TN TX WI".split()},
    **{s: "America/Denver" for s in "CO ID MT NM UT WY".split()},
    "AZ": "America/Phoenix", "CA": "America/Los_Angeles", "NV": "America/Los_Angeles", "OR": "America/Los_Angeles",
    "WA": "America/Los_Angeles", "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
}
STATE_NAMES = {
    "alabama": "AL", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def parse_stamp(text: str) -> datetime:
    """'2024-05-06T21:00Z' -> aware UTC datetime. ValueError with the expected form otherwise."""
    text = str(text).strip()
    if not STAMP.match(text):
        raise ValueError(f"{text!r} is not a UTC time like 2024-05-06T21:00Z")
    return datetime.strptime(text, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def stamp(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def parse_window(text: str, *, max_hours: float = 72.0) -> Tuple[datetime, datetime]:
    """'2024-05-06T21:00Z..2024-05-07T03:00Z' -> (start, end), start before end, at most max_hours apart."""
    a, sep, b = str(text).partition("..")
    if not sep:
        raise ValueError(f"{text!r}: a time window is written start..end in UTC (2024-05-06T21:00Z..2024-05-07T03:00Z)")
    start, end = parse_stamp(a), parse_stamp(b)
    if end <= start:
        raise ValueError(f"{text!r}: the window must end after it starts")
    if (end - start) > timedelta(hours=max_hours):
        raise ValueError(f"{text!r}: the window is longer than {max_hours:g} hours")
    return start, end


def parse_day(text: str) -> datetime:
    if not DAY.match(str(text).strip()):
        raise ValueError(f"{text!r} is not a date like 2024-05-06")
    return datetime.strptime(str(text).strip(), "%Y-%m-%d").replace(tzinfo=UTC)


HOLD_END = 0.15  # the last picture of a replay holds for this share of the layer's time (the end is readable, not a flash)


def to_layer(t: datetime, start: datetime, end: datetime, t_in: float, t_out: float) -> float:
    """The narration second at which real time t shows, when [start, end] plays over [t_in, t_out] (the last HOLD_END of the
    window holds the end)."""
    k = (t - start).total_seconds() / max(1.0, (end - start).total_seconds())
    return round(t_in + max(0.0, min(1.0, k)) * (t_out - t_in) * (1 - HOLD_END), 3)


def place_tz(place: str, default: str = "America/New_York") -> str:
    """'Fort Myers, FL' / 'FL' / 'Florida' -> the zone used for clocks on screen."""
    p = str(place or "").strip()
    if not p:
        return default
    try:
        from ..cities import find_city

        return find_city(p).tz
    except KeyError:
        pass
    state = p.rsplit(",", 1)[-1].strip()
    if state.upper() in STATE_TZ:
        return STATE_TZ[state.upper()]
    code = STATE_NAMES.get(p.lower())
    return STATE_TZ.get(code, default) if code else default


def tz_of(row, default: str = "America/New_York") -> str:
    """A row's clock zone: extra {"tz"} first, then its place."""
    return (row.extra or {}).get("tz") or place_tz(row.place, default)


def short_day(t: datetime, tz: str) -> str:
    """'Sep 28' in the zone."""
    from ..tz import to_local

    local, _ = to_local(t, tz)
    return f"{local.strftime('%b')} {local.day}"


def iso(t: Optional[datetime]) -> str:
    return t.astimezone(UTC).replace(microsecond=0).isoformat() if t else ""


def span(a: datetime, b: datetime, tz: str, *, date: bool = False) -> str:
    """'10:00 AM–6:00 PM EDT' (one zone name when both ends share it); with date=True 'Sep 28, 10:00 AM–6:00 PM EDT', and the
    second date too when the span crosses midnight."""
    from ..tz import clock, to_local

    (la, za), (lb, zb) = to_local(a, tz), to_local(b, tz)
    ta, tb = clock(a, tz).rsplit(" ", 1)[0], clock(b, tz)
    if za != zb:
        ta = clock(a, tz)
    if date:
        da = f"{la.strftime('%b')} {la.day}, "
        if la.date() != lb.date():
            tb = f"{lb.strftime('%b')} {lb.day}, {tb}"
        return f"{da}{ta}–{tb}"
    return f"{ta}–{tb}"
