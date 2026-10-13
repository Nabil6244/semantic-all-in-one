"""US local time for issue times on screen ("Issued 1:26 PM CDT"), the same on every computer.

Python's zoneinfo needs a time-zone database that Windows does not have (and the app does not bundle tzdata), so the few US
zones the NWS names are written out here with the US daylight-saving rule (since 2007: second Sunday of March 2:00 local to
first Sunday of November 2:00 local). Arizona (America/Phoenix) and Hawaii keep standard time all year."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass(frozen=True)
class UsZone:
    std_offset_h: int
    std: str  # abbreviation in standard time
    dst: Optional[str]  # abbreviation in daylight time; None = no daylight saving


EASTERN = UsZone(-5, "EST", "EDT")
CENTRAL = UsZone(-6, "CST", "CDT")
MOUNTAIN = UsZone(-7, "MST", "MDT")
ARIZONA = UsZone(-7, "MST", None)
PACIFIC = UsZone(-8, "PST", "PDT")
ALASKA = UsZone(-9, "AKST", "AKDT")
HAWAII = UsZone(-10, "HST", None)

# The IANA names api.weather.gov returns for US points (properties.timeZone).
ZONES = {
    "America/New_York": EASTERN, "America/Detroit": EASTERN, "America/Kentucky/Louisville": EASTERN,
    "America/Kentucky/Monticello": EASTERN, "America/Indiana/Indianapolis": EASTERN, "America/Indiana/Vincennes": EASTERN,
    "America/Indiana/Winamac": EASTERN, "America/Indiana/Marengo": EASTERN, "America/Indiana/Petersburg": EASTERN,
    "America/Indiana/Vevay": EASTERN,
    "America/Chicago": CENTRAL, "America/Indiana/Tell_City": CENTRAL, "America/Indiana/Knox": CENTRAL,
    "America/Menominee": CENTRAL, "America/North_Dakota/Center": CENTRAL, "America/North_Dakota/New_Salem": CENTRAL,
    "America/North_Dakota/Beulah": CENTRAL,
    "America/Denver": MOUNTAIN, "America/Boise": MOUNTAIN,
    "America/Phoenix": ARIZONA,
    "America/Los_Angeles": PACIFIC,
    "America/Anchorage": ALASKA, "America/Juneau": ALASKA, "America/Sitka": ALASKA, "America/Yakutat": ALASKA,
    "America/Nome": ALASKA, "America/Metlakatla": ALASKA,
    "Pacific/Honolulu": HAWAII,
}


def zone(name: str) -> UsZone:
    try:
        return ZONES[name]
    except KeyError:
        raise ValueError(f"unknown US time zone {name!r} (known: {', '.join(sorted(ZONES))})") from None


def _nth_sunday(year: int, month: int, n: int) -> datetime:
    d = datetime(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)  # first Sunday
    return d + timedelta(weeks=n - 1)


def is_dst(utc: datetime, z: UsZone) -> bool:
    """Daylight time in zone z at the UTC instant `utc` (2:00 local standard time to 2:00 local daylight time)."""
    if z.dst is None:
        return False
    utc = utc.astimezone(timezone.utc).replace(tzinfo=None)
    start = _nth_sunday(utc.year, 3, 2) + timedelta(hours=2 - z.std_offset_h)   # 2:00 standard -> UTC
    end = _nth_sunday(utc.year, 11, 1) + timedelta(hours=2 - (z.std_offset_h + 1))  # 2:00 daylight -> UTC
    return start <= utc < end


def to_local(utc: datetime, name: str) -> "tuple[datetime, str]":
    """(local wall time, abbreviation) for a timezone-aware instant."""
    if utc.tzinfo is None:
        raise ValueError("to_local needs a timezone-aware time")
    z = zone(name)
    dst = is_dst(utc, z)
    off = z.std_offset_h + (1 if dst else 0)
    return utc.astimezone(timezone(timedelta(hours=off))), (z.dst if dst else z.std)


def parse_iso(text: str) -> datetime:
    """ISO 8601 as the NWS writes it (offset or Z); always timezone-aware."""
    t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError(f"time {text!r} has no offset")
    return t


def clock(utc: datetime, name: str, *, date: bool = False) -> str:
    """'1:26 PM CDT' (or 'Oct 12, 1:26 PM CDT' with date=True)."""
    local, abbr = to_local(utc, name)
    hour = local.hour % 12 or 12
    text = f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'} {abbr}"
    return f"{local.strftime('%b')} {local.day}, {text}" if date else text


def weekday(utc: datetime, name: str) -> str:
    """Three-letter weekday in the zone ('TUE')."""
    return to_local(utc, name)[0].strftime("%a").upper()
