"""Event context: the understanding turned into a resolved event (identity, dates, the moment, the place), using official indexes.

    resolve(u, net, evidence, overrides, recorded) -> EventContext

Network access goes through `net` (weather.intel.engine.Net: cached GETs that record each request in the evidence), so tests run
on saved official answers and a render can be reproduced from the evidence snapshot. Lookups that only some graphics need (the
advisory of a cone, the gauge of a river) are made lazily, when a graphic asks for them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..news.timeline import STATE_TZ
from . import identity as idn
from .evidence import Evidence
from .understand import Understanding

UTC = timezone.utc
STORM_CATEGORIES = ("hurricane", "tropical_storm")
CONTEXT_STORM_MIN_MENTIONS = 2  # a storm named once in a tornado story ("the remnants of Hurricane Isaias") is context, not the story
ZONE_HOURS = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7, "PDT": -7, "PST": -8, "UTC": 0}


@dataclass
class EventContext:
    u: Understanding
    category: str
    states: List[str]
    tz: str
    year: Optional[int] = None
    days: List[str] = field(default_factory=list)  # event days the story names (its own year), story order
    main_day: Optional[str] = None
    moment: Optional[datetime] = None  # the event's key moment (UTC): a touchdown, a landfall
    moment_note: str = ""
    storm: Optional[idn.StormRecord] = None
    storm_role: str = ""  # "primary" | "context"
    storm_note: str = ""
    context_storms: List[Tuple[str, str]] = field(default_factory=list)  # (name, note) storms named in passing
    landfalls: List[dict] = field(default_factory=list)
    peak: Optional[dict] = None
    focus: Optional[Tuple[float, float]] = None
    focus_name: str = ""
    track: List[Tuple[float, float]] = field(default_factory=list)  # the storm's (lat, lon) fixes, HURDAT2
    recorded: Optional[date] = None
    historical: bool = True
    notes: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    _cache: Dict[str, Any] = field(default_factory=dict)

    # ---- windows ---------------------------------------------------------------------------------------------------------------
    @property
    def conv_day(self) -> Optional[str]:
        if self.moment is not None:
            return idn.convective_day(self.moment)
        return self.main_day

    def window(self, before_h: float = 2.0, after_h: float = 2.0) -> Optional[Tuple[datetime, datetime]]:
        """A UTC window around the moment; with no moment, the storm-day default (10 UTC + 18 h of the main day)."""
        if self.moment is not None:
            a = (self.moment - timedelta(hours=before_h)).replace(minute=0, second=0, microsecond=0)
            b = (self.moment + timedelta(hours=after_h))
            b = b.replace(minute=0, second=0, microsecond=0) + (timedelta(hours=1) if b.minute or b.second else timedelta(0))
            return a, b
        if self.main_day:
            a = datetime.strptime(self.main_day, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(hours=10)
            return a, a + timedelta(hours=18)
        return None

    def span_days(self) -> Optional[Tuple[date, date]]:
        """The event's first and last day: the storm's US days (landfall to the last day the story names), or the days named."""
        ds = sorted(date.fromisoformat(d) for d in self.days)
        if not ds:
            return None
        return ds[0], ds[-1]

    def local(self, t: datetime) -> datetime:
        from ..tz import to_local

        return to_local(t, self.tz)[0]   # Weather's own US zone rules (Windows has no tz database)

    def to_dict(self) -> dict:
        return {"category": self.category, "states": self.states, "tz": self.tz, "year": self.year, "days": self.days, "main_day": self.main_day,
                "moment": self.moment.isoformat().replace("+00:00", "Z") if self.moment else None, "moment_note": self.moment_note,
                "convective_day": self.conv_day, "storm": self.storm.to_dict() if self.storm else None, "storm_role": self.storm_role,
                "storm_note": self.storm_note, "context_storms": self.context_storms, "landfalls": self.landfalls, "peak": self.peak,
                "focus": self.focus, "focus_name": self.focus_name, "recorded": self.recorded.isoformat() if self.recorded else None,
                "historical": self.historical, "hazards": self.u.hazards}


def local_to_utc(day: str, hour: int, minute: int, zone: str, tz: str) -> datetime:
    """A clock time on a day -> UTC: a said zone (EDT ...) wins; else the event's own zone (with its daylight saving)."""
    d = date.fromisoformat(day)
    if zone in ZONE_HOURS:
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=UTC) - timedelta(hours=ZONE_HOURS[zone])
    zname = {"ET": "America/New_York", "CT": "America/Chicago", "MT": "America/Denver", "PT": "America/Los_Angeles"}.get(zone, tz)
    return wall_to_utc(datetime(d.year, d.month, d.day, hour, minute), zname)


def wall_to_utc(wall: datetime, tz: str) -> datetime:
    """A local wall-clock time in a US zone -> UTC, with Weather's own zone rules (weather.tz; no system tz database needed)."""
    from ..tz import is_dst, zone

    z = zone(tz)
    guess = wall.replace(tzinfo=UTC) - timedelta(hours=z.std_offset_h)
    return guess - timedelta(hours=1) if is_dst(guess - timedelta(hours=1), z) else guess


def seg_day(u: Understanding, seg_ids: List[str], seg: str, event_year: Optional[int]) -> Optional[str]:
    """The day a segment talks about: a date it says (in the event's year), else the last one said before it."""
    i = seg_ids.index(seg) if seg in seg_ids else len(seg_ids)
    best = None
    for d in u.dates:
        if not d.day or (event_year and int(d.day[:4]) != event_year) or d.seg not in seg_ids:
            continue
        j = seg_ids.index(d.seg)
        if j == i:
            return d.day
        if j < i:
            best = d.day
    return best


def resolve(u: Understanding, net, ev: Evidence, overrides: Dict[str, Any], seg_ids: List[str], *, recorded: Optional[date] = None,
            today: Optional[date] = None) -> EventContext:
    ov = overrides.get("event") or {}
    category = ov.get("category") or u.category
    states = [s.upper() for s in ov.get("states") or []] or u.states
    tz = STATE_TZ.get(states[0], "America/New_York") if states else "America/New_York"
    ctx = EventContext(u=u, category=category, states=states, tz=tz, recorded=recorded)
    ctx.assumptions += u.assumptions
    ctx.ambiguities += u.ambiguities
    years = [y for y, _ in u.years]
    # the event's year: the overrides, the most said year (ties: the first), the recording's
    if ov.get("year"):
        ctx.year = int(ov["year"])
    elif years:
        from collections import Counter

        c = Counter(years)
        top = max(c.values())
        ctx.year = next(y for y in years if c[y] == top)
    elif recorded:
        ctx.year = recorded.year
    ctx.days = list(dict.fromkeys(d.day for d in u.dates if d.day and (not ctx.year or int(d.day[:4]) == ctx.year)))
    if ov.get("day"):
        ctx.main_day = ov["day"]
    elif ctx.days:
        from collections import Counter

        c = Counter(d.day for d in u.dates if d.day in ctx.days)
        top = max(c.values())
        ctx.main_day = next(d for d in ctx.days if c[d] == top)
    _resolve_storms(ctx, u, net, ev, ov, years, recorded)
    _resolve_moment(ctx, u, ov, seg_ids)
    _resolve_focus(ctx, u, ov)
    ref = today or recorded or date.today()
    ctx.historical = bool(ctx.main_day and date.fromisoformat(ctx.main_day) < ref - timedelta(days=1)) or bool(ctx.storm and ctx.storm.end)
    if not ctx.main_day and not ctx.storm:
        if category in ("forecast", "general"):
            ctx.historical = False
        else:
            ctx.ambiguities.append("the script never says the event's date, so no archive can be searched (say the full date, like "
                                   "October 11, 2026, or set it in the overrides)")
    return ctx


def _resolve_storms(ctx: EventContext, u: Understanding, net, ev: Evidence, ov: Dict[str, Any], years: List[int],
                    recorded: Optional[date]) -> None:
    names: Dict[str, int] = {}
    for s in u.storms:
        names[s.name] = names.get(s.name, 0) + 1
    if ov.get("storm"):
        names = {"__override__": 99}
    if not names:
        if ctx.category in STORM_CATEGORIES:
            ctx.ambiguities.append("this is a tropical story but the script names no storm (\"Hurricane Ian\"), so no NHC data is used")
        return
    try:
        records = idn.parse_storm_list(net.text(idn.STORM_LIST, source="nhc_storm_list", purpose="storm identity"))
    except Exception as exc:
        ctx.notes.append(f"the NHC storm list could not be read ({exc}); storm graphics are left out")
        return
    for name, count in sorted(names.items(), key=lambda kv: -kv[1]):
        if name == "__override__":
            rec = next((r for r in records if r.id == str(ov["storm"]).upper()), None)
            note = f"storm set in the overrides: {ov['storm']}" + ("" if rec else " (not in the NHC storm list)")
        else:
            rec, note = idn.resolve_storm(name, records, years=years, days=ctx.days, recorded=recorded)
        primary = ctx.storm is None and (ctx.category in STORM_CATEGORIES or ctx.category in ("flood", "heavy_rain") or
                                         count >= CONTEXT_STORM_MIN_MENTIONS or name == "__override__")
        if rec is None:
            ev.tried("nhc_storm_list", idn.STORM_LIST, f"identity of {name.title()}", "ambiguous" if "ambiguous" in note else "unavailable", note)
            (ctx.ambiguities if "ambiguous" in note else ctx.notes).append(note)
            continue
        ev.add(kind="identity", subject=f"{rec.name.title()} ({rec.id})", what="storm identity", value=rec.id, source="nhc_storm_list",
               record=idn.STORM_LIST, retrieved=net.stamp, issued=rec.start or "", valid=f"{rec.start}..{rec.end or 'active'}",
               quality="final" if rec.status == "ARCHIVE" else "preliminary", method=note,
               caveats=[] if rec.status == "ARCHIVE" else ["the storm is still listed as active: its record may change"])
        if primary:
            ctx.storm, ctx.storm_role, ctx.storm_note = rec, "primary", note
            _storm_history(ctx, rec, net, ev)
        else:
            ctx.context_storms.append((rec.name.title(), note + f"; named {count} time(s) in a {ctx.category} story, so it is context, "
                                       "not the subject (no storm graphics)"))
            peak = storm_peak(rec, net, ev)
            called_hurricane = any(s.name == rec.name and s.kind.lower() == "hurricane" for s in u.storms)
            if called_hurricane and peak is not None and peak["wind_kt"] < 64:
                ctx.notes.append(f"the script calls {rec.name.title()} a hurricane; NHC's best track ({peak['source']}) has its peak at "
                                 f"{peak['wind_kt']:g} kt, below hurricane strength — worth checking before publishing")


def storm_peak(rec, net, ev: Evidence) -> Optional[dict]:
    """The storm's peak from NHC's best track: the final one (HURDAT2) for past seasons, the working one (GIS) while the season is
    on — never the storm list's type, which is the LAST status of an active storm, not its peak. Recorded as a fact."""
    from ..news import nhc
    from ..post.besttrack import mph

    try:
        url = nhc.BEST.format(id=rec.id.lower())
        pts = nhc.best_track(net.bytes(url, source="nhc_gis_best_track", purpose=f"peak of {rec.id}"))["points"]
    except Exception:
        return None
    pts = [p for p in pts if p.get("wind_kt") is not None]
    if not pts:
        return None
    top = max(pts, key=lambda p: p["wind_kt"])
    final = rec.status == "ARCHIVE"
    ev.add(kind="best_track", subject=f"{rec.name.title()} ({rec.id})", what="peak sustained wind", value=mph(int(top["wind_kt"])), unit="mph",
           where=f"{top['lat']},{top['lon']}", source="nhc_gis_best_track", record=url, retrieved=net.stamp, issued=top["time"],
           quality="final" if final else "preliminary", caveats=[] if final else ["working best track: revised after the season"],
           method=f"highest wind in the GIS best track ({top['wind_kt']:g} kt, {top.get('kind', '')})")
    return {"wind_kt": top["wind_kt"], "time": top["time"], "source": "final" if final else "working, preliminary"}


def _storm_history(ctx: EventContext, rec: idn.StormRecord, net, ev: Evidence) -> None:
    """Landfalls and the peak from HURDAT2 (seasons before this one); a current storm has neither yet (said so)."""
    this_year = (ctx.recorded or date.today()).year
    if rec.year >= this_year:
        ctx.notes.append(f"{rec.name.title()} ({rec.id}) is from the current season: the final best track (HURDAT2, with landfalls) "
                         "is not published yet, so landfall times come from the script only")
        return
    try:
        index = net.text(idn.HURDAT_INDEX, source="nhc_hurdat2", purpose="HURDAT2 file list")
        from ..post.besttrack import latest_file

        url = latest_file(index, rec.basin)
        text = net.text(url, source="nhc_hurdat2", purpose=f"final best track of {rec.id}", max_age_s=30 * 86400.0)
    except Exception as exc:
        ctx.notes.append(f"HURDAT2 could not be read ({exc}); landfalls come from the script only")
        return
    ctx.landfalls = idn.hurdat_landfalls(text, rec.id)
    ctx.track = idn.hurdat_positions(text, rec.id)
    ctx.peak = idn.hurdat_peak(text, rec.id)
    from ..post.besttrack import mph

    for i, lf in enumerate(ctx.landfalls, 1):
        ev.add(kind="best_track", subject=f"{rec.name.title()} ({rec.id})", what=f"landfall {i}", value=lf["time"], where=f"{lf['lat']},{lf['lon']}",
               source="nhc_hurdat2", record=url, retrieved=net.stamp, issued=lf["time"],
               caveats=[f"sustained wind {mph(lf['wind_kt'])} mph ({lf['wind_kt']} kt)"])
    if ctx.peak:
        ev.add(kind="best_track", subject=f"{rec.name.title()} ({rec.id})", what="peak sustained wind", value=mph(ctx.peak["wind_kt"]),
               unit="mph", where=f"{ctx.peak['lat']},{ctx.peak['lon']}", source="nhc_hurdat2", record=url, retrieved=net.stamp,
               issued=ctx.peak["time"], method="maximum INTENSITY of the HURDAT2 block, knots to mph rounded to 5 (NHC convention)")
        if ctx.peak.get("min_pressure_mb"):
            ev.add(kind="best_track", subject=f"{rec.name.title()} ({rec.id})", what="minimum pressure", value=ctx.peak["min_pressure_mb"],
                   unit="mb", source="nhc_hurdat2", record=url, retrieved=net.stamp, issued=ctx.peak["min_pressure_time"] or "")


def _resolve_moment(ctx: EventContext, u: Understanding, ov: Dict[str, Any], seg_ids: List[str]) -> None:
    if ov.get("moment"):
        ctx.moment = datetime.strptime(ov["moment"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        ctx.moment_note = "set in the overrides"
        return
    if ctx.storm and ctx.landfalls:
        # the strongest landfall in the story's states, on the day the story is about when it has one there
        cands = [x for x in ctx.landfalls if _in_states(x, ctx.states)] or list(ctx.landfalls)
        on_day = [x for x in cands if ctx.main_day and ctx.local(_lf_time(x)).date().isoformat() == ctx.main_day]
        lf = max(on_day or cands, key=lambda x: (x["wind_kt"], -(x["pressure_mb"] or 9999)))
        ctx.moment = _lf_time(lf)
        from ..post.besttrack import mph

        ctx.moment_note = (f"the strongest landfall in {', '.join(ctx.states) or 'the story'} in the NHC best track (HURDAT2): {lf['time']}, "
                           f"{mph(lf['wind_kt'])} mph")
        if not ctx.main_day:
            ctx.main_day = ctx.local(ctx.moment).date().isoformat()
        return
    # the first clock time the story says, on the day of its segment
    for t in u.times:
        day = seg_day(u, seg_ids, t.seg, ctx.year) or ctx.main_day
        if not day:
            continue
        ctx.moment = local_to_utc(day, t.hour, t.minute, t.zone, ctx.tz)
        ctx.moment_note = f"\"{t.text}\" on {day} (beat {t.seg})" + ("" if t.zone else f", read in {ctx.tz.split('/')[-1].replace('_', ' ')} time")
        if not t.zone:
            ctx.assumptions.append(f"the time \"{t.text}\" has no zone: it is read as local time in {ctx.tz}")
        return


def _lf_time(lf: dict) -> datetime:
    return datetime.fromisoformat(lf["time"].replace("Z", "+00:00")).astimezone(UTC)


def _in_states(lf: dict, states: List[str]) -> bool:
    if not states:
        return True
    from .placegeo import state_of_point

    return state_of_point(lf["lat"], lf["lon"]) in states


def _resolve_focus(ctx: EventContext, u: Understanding, ov: Dict[str, Any]) -> None:
    if ov.get("focus"):
        lat, lon = (float(x) for x in str(ov["focus"]).split(","))
        ctx.focus, ctx.focus_name = (lat, lon), "set in the overrides"
        return
    for kind in ("coords", "county", "city"):
        for p in u.places_of(kind):
            if p.lat is not None and (not ctx.states or not p.state or p.state in ctx.states):
                ctx.focus, ctx.focus_name = (p.lat, p.lon), p.name
                return
    if ctx.moment is not None and ctx.landfalls:
        lf = next((x for x in ctx.landfalls if x["time"].startswith(ctx.moment.strftime("%Y-%m-%dT%H"))), ctx.landfalls[0])
        ctx.focus, ctx.focus_name = (lf["lat"], lf["lon"]), "landfall"
        return
    if ctx.states:
        from .placegeo import state_center

        c = state_center(ctx.states[0])
        if c:
            ctx.focus, ctx.focus_name = c, ctx.states[0]
