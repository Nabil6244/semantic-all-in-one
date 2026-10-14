"""Event identity: which storm, which advisory, which day, which gauge — read from official indexes, never guessed.

    parse_storm_list(text)                      NHC ATCF storm list -> [StormRecord]
    resolve_storm(name, ...)                    the one storm a name means in this story, or None with the reason (two storms
                                                share a name: Harvey 1993/1999/2005/2011/2017; Isaias 2020/2026)
    advisories(html, storm_id)                  the advisory numbers NHC's GIS archive lists for a storm
    pick_advisory(storm_id, target, advs, ...)  the last advisory issued at or before a time (binary search on each file's
                                                ADVDATE; at most ~log2(n)+1 small downloads, all cached)
    hurdat_landfalls(text, storm_id)            the landfall (L) records of the final best track
    convective_day(t_utc)                       SPC's day for a moment (12 UTC to 11:59 UTC the next day)
    parse_sites(rdb) / pick_gauge(...)          USGS gauges on a named river, the one nearest the place the narration names
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional, Sequence, Tuple

UTC = timezone.utc
STORM_LIST = "https://ftp.nhc.noaa.gov/atcf/index/storm_list.txt"
ADVISORY_INDEX = "https://www.nhc.noaa.gov/gis/archive_forecast_results.php?id={basin}{num}&year={year}"
HURDAT_INDEX = "https://www.nhc.noaa.gov/data/hurdat/"
USGS_SITES = ("https://waterservices.usgs.gov/nwis/site/?format=rdb&stateCd={state}&siteType=ST,ST-TS&parameterCd=00065"
              "&siteStatus=all&hasDataTypeCd=iv")
TROPICAL_STATUS = {"ARCHIVE", "WARNING"}  # GENESIS / METWATCH entries are disturbances and invests, not named storms


@dataclass
class StormRecord:
    id: str  # AL092022
    name: str
    basin: str
    number: int
    year: int
    max_type: str  # the list's storm type (HU, TS ...)
    start: Optional[str]  # ISO UTC
    end: Optional[str]  # ISO UTC; None while the storm is still in the list as active
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


def _dtg(text: str) -> Optional[str]:
    text = text.strip()
    if not re.fullmatch(r"\d{10}", text) or text.startswith("9999"):
        return None
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def parse_storm_list(text: str) -> List[StormRecord]:
    out = []
    for line in text.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 21 or not re.fullmatch(r"(AL|EP|CP|WP|IO|SH)\d{2}\d{4}", p[20] or ""):
            continue
        try:
            out.append(StormRecord(p[20], p[0].upper(), p[1], int(p[7]), int(p[8]), p[9], _dtg(p[11]), _dtg(p[12]), p[18]))
        except ValueError:
            continue
    return out


def resolve_storm(name: str, records: Sequence[StormRecord], *, years: Sequence[int] = (), days: Sequence[str] = (),
                  recorded: Optional[date] = None, basins: Sequence[str] = ("AL", "EP", "CP")) -> Tuple[Optional[StormRecord], str]:
    """(the storm, how it was chosen) or (None, why not). A storm is chosen only when exactly one record fits what the story says:
    the year it names, then the dates it names (the storm must exist within ten days of one), then — with neither — the season of
    the recording. Two candidates left = ambiguous, and the engine says so instead of picking one."""
    name = name.strip().upper()
    cands = [r for r in records if r.name == name and r.status in TROPICAL_STATUS and r.basin in basins]
    if not cands:
        return None, f"no storm named {name.title()} is in the NHC storm list"
    how = []
    if years:
        by_year = [r for r in cands if r.year in set(years)]
        if by_year:
            cands = by_year
            how.append(f"the year the script says ({', '.join(sorted({str(r.year) for r in by_year}))})")
    if len(cands) > 1 and days:
        def near(r: StormRecord) -> bool:
            a = datetime.fromisoformat(r.start.replace("Z", "+00:00")).date() if r.start else None
            b = datetime.fromisoformat(r.end.replace("Z", "+00:00")).date() if r.end else (recorded or date.today())
            return a is not None and any(a - timedelta(days=10) <= date.fromisoformat(d) <= b + timedelta(days=10) for d in days)
        by_day = [r for r in cands if near(r)]
        if by_day:
            cands = by_day
            how.append("the dates the script says")
    if len(cands) > 1 and recorded is not None and not years and not days:
        season = [r for r in cands if r.year == recorded.year]
        if len(season) == 1:
            cands = season
            how.append(f"the season of the recording ({recorded.year})")
    if len(cands) == 1:
        r = cands[0]
        return r, f"{r.name.title()} = {r.id} ({r.year}), chosen by " + (" and ".join(how) if how else "its name (the only storm with it)")
    years_left = ", ".join(f"{r.id} ({r.year})" for r in cands)
    return None, f"{name.title()} is ambiguous: {years_left}. Say the year in the script, or set the storm in the overrides"


def advisories(html: str, storm_id: str) -> List[str]:
    sid = storm_id.lower()
    found = re.findall(rf"{sid}_5day_(\d{{3}}[A-Z]?)\.zip", html)
    return sorted(set(found), key=lambda a: (int(a[:3]), a[3:]))


def pick_advisory(storm_id: str, target: datetime, advs: Sequence[str], issued_of: Callable[[str], datetime], *,
                  max_fetches: int = 9) -> Tuple[Optional[str], Optional[datetime], List[str]]:
    """(advisory, its issue time, notes): the last advisory issued at or before `target` (binary search on issue time)."""
    notes: List[str] = []
    if not advs:
        return None, None, [f"NHC's GIS archive lists no advisories for {storm_id}"]
    lo, hi, best = 0, len(advs) - 1, None
    fetched = 0
    cache = {}

    def t_of(i: int) -> Optional[datetime]:
        nonlocal fetched
        if i not in cache:
            if fetched >= max_fetches:
                return None
            fetched += 1
            try:
                cache[i] = issued_of(advs[i])
            except Exception as exc:  # an advisory file that will not read: step around it
                notes.append(f"advisory {advs[i]} could not be read ({exc})")
                cache[i] = None
        return cache[i]

    while lo <= hi:
        mid = (lo + hi) // 2
        t = t_of(mid)
        if t is None:
            if fetched >= max_fetches:
                break
            hi = mid - 1
            continue
        if t <= target:
            best = (advs[mid], t)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        first = t_of(0)
        if first is not None and first > target:
            notes.append(f"the first advisory on {storm_id} was issued after {target:%Y-%m-%d %H:%MZ}: advisory {advs[0]} is used")
            return advs[0], first, notes
        return None, None, notes + [f"no advisory of {storm_id} could be placed in time"]
    return best[0], best[1], notes


def hurdat_landfalls(text: str, storm_id: str) -> List[dict]:
    """[{time, lat, lon, wind_kt, pressure_mb, status}] for the storm's landfall records (empty when it is not in the file)."""
    from ..post.besttrack import landfalls, parse_block, storm_block

    try:
        _name, fixes = parse_block(storm_block(text, storm_id))
    except ValueError:
        return []
    return [{"time": f.time.isoformat().replace("+00:00", "Z"), "lat": f.lat, "lon": f.lon, "wind_kt": f.wind_kt,
             "pressure_mb": f.pressure_mb, "status": f.status} for f in landfalls(fixes)]


def hurdat_peak(text: str, storm_id: str) -> Optional[dict]:
    from ..post.besttrack import parse_block, storm_block

    try:
        _name, fixes = parse_block(storm_block(text, storm_id))
    except ValueError:
        return None
    if not fixes:
        return None
    top = max(fixes, key=lambda f: (f.wind_kt, -(f.pressure_mb or 9999)))
    low = min((f for f in fixes if f.pressure_mb), key=lambda f: f.pressure_mb, default=None)
    return {"time": top.time.isoformat().replace("+00:00", "Z"), "wind_kt": top.wind_kt, "lat": top.lat, "lon": top.lon,
            "min_pressure_mb": low.pressure_mb if low else None, "min_pressure_time": low.time.isoformat().replace("+00:00", "Z") if low else None,
            "first": fixes[0].time.isoformat().replace("+00:00", "Z"), "last": fixes[-1].time.isoformat().replace("+00:00", "Z")}


def convective_day(t: datetime) -> str:
    """SPC's convective day of a moment: 12 UTC to 11:59 UTC the next day (a 6 AM EDT tornado is in the previous day's file)."""
    return (t.astimezone(UTC) - timedelta(hours=12)).date().isoformat()


# ---- rivers --------------------------------------------------------------------------------------------------------------------

@dataclass
class Gauge:
    site: str
    name: str
    lat: float
    lon: float


ABBR = {"river": ("rv", "r", "river"), "bayou": ("bayou", "byu", "bu"), "creek": ("ck", "cr", "creek")}


def parse_sites(rdb: str) -> List[Gauge]:
    out = []
    for line in rdb.splitlines():
        if line.startswith("#") or not line.startswith("USGS"):
            continue
        p = line.split("\t")
        try:
            out.append(Gauge(p[1], p[2], float(p[4]), float(p[5])))
        except (IndexError, ValueError):
            continue
    return out


def _km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def river_gauges(river: str, sites: Sequence[Gauge]) -> List[Gauge]:
    """Gauges on the main stem of a named river ("Buffalo Bayou" -> "Buffalo Bayou at Houston, TX"; forks are left out)."""
    words = river.split()
    kind = words[-1].lower()
    base = " ".join(words[:-1]).lower()
    pats = [rf"^{re.escape(base)}\s+{a}\b" for a in ABBR.get(kind, (kind,))]
    return [g for g in sites if any(re.match(p, g.name.lower()) for p in pats)]


def pick_gauge(river: str, sites: Sequence[Gauge], context: str, near: Optional[Tuple[float, float]]) -> Tuple[Optional[Gauge], str]:
    """The gauge the narration means: one whose name holds a place said in the same sentence ("near Sheldon", "through downtown
    Houston"), else the one nearest the story's main place. (None, why) when the river has no gauge."""
    cands = river_gauges(river, sites)
    if not cands:
        return None, f"no USGS gage-height gauge was found on {river}"
    low = context.lower()
    named = [g for g in cands if (m := re.search(r"\b(?:at|nr|near|abv|bl)\s+([a-z .]+?)(?:,|$)", g.name.lower())) and
             any(w in low for w in [m.group(1).strip()] if len(m.group(1).strip()) > 3)]
    if len(named) == 1:
        return named[0], f"{named[0].name} ({named[0].site}): its place is named in the narration"
    pool = named or cands
    if near is not None:
        g = min(pool, key=lambda g: _km((g.lat, g.lon), near))
        return g, f"{g.name} ({g.site}): the gauge on {river} nearest the story's place"
    if len(pool) == 1:
        return pool[0], f"{pool[0].name} ({pool[0].site}): the only gauge on {river}"
    return None, f"{river} has {len(pool)} gauges and the narration does not say which place: set the gauge in the overrides"


def hurdat_positions(text: str, storm_id: str) -> List[Tuple[float, float]]:
    """(lat, lon) of every fix of the storm in HURDAT2 (empty when it is not there)."""
    from ..post.besttrack import parse_block, storm_block

    try:
        return [(f.lat, f.lon) for f in parse_block(storm_block(text, storm_id))[1]]
    except ValueError:
        return []
