"""The Weather Intelligence engine: script + voiceover + project -> the event, its evidence, and the graphics, placed and fetched.

    run(project, plan, words, ...) -> IntelResult

    script / beats + transcript  -> understand (weather.intel.understand)
                                 -> resolve the event (identity, dates, moment, place: weather.intel.context, official indexes)
                                 -> graphic opportunities placed on the narration (weather.intel.planner, catalogue in catalog.py)
                                 -> data acquisition, each graphic on its own (one failing source never stops the others)
                                 -> verification (a graphic whose data turned out empty is dropped, with the reason)
                                 -> outputs (unless dry_run):
                                      intel/auto_plan.json   the engine's graphics (auto_* ids), the event, skips and conflicts
                                      intel/evidence.json    facts with provenance + every source request and its outcome
                                      intel/report.md        the production report ("Added for you" ...)
                                      resolved.json          the data snapshot the render is built from (the user's rows too)

The user's files are never written: beats.csv, weather_layers.csv, plan.csv and intel/overrides.json are read only. The user's
rows are preserved as they are; a user row that conflicts with the evidence (another storm, another day, today's picture in a
story about last year) is REPORTED with a proposal, and applied only when intel/overrides.json lists it under "accept".

Repeat runs replace the engine's own plan (stable ids), so graphics never accumulate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .catalog import Draft
from .evidence import Evidence, classify_error
from .sources import SOURCES, source_of
from .understand import Segment, understand

AUTO_PLAN_VERSION = 1
UTC = timezone.utc
URL_SOURCES = (  # URL prefix -> source id (for the request log)
    ("https://ftp.nhc.noaa.gov/atcf/index", "nhc_storm_list"), ("https://www.nhc.noaa.gov/gis/forecast", "nhc_gis_advisory"),
    ("https://www.nhc.noaa.gov/gis/archive_forecast", "nhc_gis_advisory"), ("https://www.nhc.noaa.gov/gis/best_track", "nhc_gis_best_track"),
    ("https://www.nhc.noaa.gov/data/hurdat", "nhc_hurdat2"), ("https://mesonet.agron.iastate.edu/archive/data", "mrms"),
    ("https://mesonet.agron.iastate.edu/geojson/sbw", "iem_warnings"), ("https://mesonet.agron.iastate.edu/cgi-bin/request/gis", "iem_warnings"),
    ("https://mesonet.agron.iastate.edu", "iem_radar"), ("https://www.spc.noaa.gov/climo/reports", "spc_reports"),
    ("https://www.spc.noaa.gov/products/outlook", "spc_outlook"), ("https://www.wpc.ncep.noaa.gov", "wpc_ero"),
    ("https://data.rcc-acis.org", "acis"), ("https://nwis.waterservices.usgs.gov", "usgs_iv"), ("https://waterservices.usgs.gov/nwis/site", "usgs_site"),
    ("https://api.water.noaa.gov", "nwps"), ("https://gibs.earthdata.nasa.gov", "gibs_daily"), ("https://api.weather.gov", "nws_api"),
)


def url_source(url: str) -> str:
    for prefix, sid in URL_SOURCES:
        if url.startswith(prefix):
            return sid
    return url.split("/")[2] if "://" in url else url


class Net:
    """Cached GETs (weather.layers.http_text / http_bytes: Weather's HTTP cache, retries with back-off, timeouts) that log each
    request in the evidence. Tests pass `get_text` / `get_bytes` reading saved official answers."""

    def __init__(self, ev: Evidence, *, get_text: Optional[Callable[..., str]] = None, get_bytes: Optional[Callable[..., bytes]] = None,
                 now: Optional[datetime] = None, offline: bool = False):
        from ..layers import http_bytes, http_text

        self.ev = ev
        self._text = get_text or http_text
        self._bytes = get_bytes or http_bytes
        self.now = now or datetime.now(UTC)
        self.offline = offline
        self.seen: Dict[str, str] = {}

    @property
    def stamp(self) -> str:
        return self.now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _get(self, fn, url: str, source: Optional[str], purpose: str, **kw):
        sid = source or url_source(url)
        if self.offline:
            self.ev.tried(sid, url, purpose, "skipped", "offline run", self.now)
            raise RuntimeError(f"{url} could not be fetched (offline run)")
        try:
            try:
                body = fn(url, **kw) if kw else fn(url)
            except TypeError:
                body = fn(url)
        except Exception as exc:
            status = classify_error(exc)
            self.ev.tried(sid, url, purpose, status, str(exc)[:300], self.now)
            raise
        if url not in self.seen:
            self.seen[url] = purpose
            self.ev.tried(sid, url, purpose, "ok", "", self.now)
        return body

    def text(self, url: str, *, source: Optional[str] = None, purpose: str = "", **kw) -> str:
        return self._get(self._text, url, source, purpose, **kw)

    def bytes(self, url: str, *, source: Optional[str] = None, purpose: str = "", **kw) -> bytes:
        return self._get(self._bytes, url, source, purpose, **kw)


@dataclass
class Conflict:
    row: str  # the user's row id
    kind: str  # stale | conflict
    problem: str
    proposal: str = ""
    replacement: str = ""  # a data_source text that would fix it
    applied: bool = False


@dataclass
class IntelResult:
    event: Dict[str, Any]
    drafts: List[Draft]
    added: List[Draft]
    dropped: List[Tuple[Draft, str]]
    skipped: List[Any]
    preserved: List[Tuple[str, str]]
    conflicts: List[Conflict]
    notes: List[str]
    assumptions: List[str]
    ambiguities: List[str]
    evidence: Evidence
    snapshot: Any = None
    report: str = ""
    beats: List[Segment] = field(default_factory=list)
    dry_run: bool = False
    mode: str = "A"
    paths: Dict[str, str] = field(default_factory=dict)
    claims: List[Dict[str, Any]] = field(default_factory=list)  # each number the narrator says, and the shown number that matches it


# ---- inputs -------------------------------------------------------------------------------------------------------------------

def intel_dir(project) -> Path:
    return Path(project.root) / "intel"


def load_overrides(project) -> Dict[str, Any]:
    p = intel_dir(project) / "overrides.json"
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def recording_time(project, voiceover: Optional[Path], overrides: Dict[str, Any]) -> Tuple[Optional[datetime], str]:
    """When the narration was recorded: the overrides, weather.json's recorded_at, else the voiceover file's time (an assumption)."""
    ov = (overrides.get("event") or {}).get("recorded_at")
    if ov:
        return datetime.fromisoformat(str(ov).replace("Z", "+00:00")).astimezone(UTC), "set in the overrides"
    try:
        wj = json.loads((Path(project.root) / "weather.json").read_text(encoding="utf-8"))
        if wj.get("recorded_at"):
            return datetime.fromisoformat(str(wj["recorded_at"]).replace("Z", "+00:00")).astimezone(UTC), "weather.json recorded_at"
    except (OSError, ValueError):
        pass
    if voiceover is not None and Path(voiceover).is_file():
        return datetime.fromtimestamp(Path(voiceover).stat().st_mtime, UTC), "the voiceover file's date (an assumption)"
    return None, ""


def segments_from_plan(plan, beats_text: str = "") -> List[Segment]:
    anchors = {}
    if beats_text:
        import csv
        import io

        for r in csv.DictReader(io.StringIO(beats_text.lstrip("﻿"))):
            if (r.get("row") or "").strip().lower() == "beat":
                anchors[(r.get("beat") or "").strip()] = (r.get("vo_anchor") or "").strip()
    out, cam = [], ""
    for b in plan.beats:
        steps = [c.place for c in b.camera if c.action in ("start", "fly_to") and c.place]
        cam = steps[-1] if steps else (b.cam_place or cam)
        out.append(Segment(b.id, b.mode, b.narration or "", b.start, b.end, anchors.get(b.id, ""), cam if b.mode != "footage" else "",
                           tuple(l.type for l in b.layers)))
    return out


def user_rows(project, notes: List[str]) -> List[Any]:
    """The user's weather rows (repaired the forgiving way), or [] when there is no weather_layers.csv."""
    if not project.layers_csv.is_file():
        return []
    from ..autofix import repair_layers

    try:
        return repair_layers(project.layers_csv.read_text(encoding="utf-8"), notes)
    except Exception as exc:
        notes.append(f"weather_layers.csv could not be read ({exc}); only the engine's graphics are used")
        return []


def draft_row(d: Draft, line: int = 0):
    """A Draft -> weather.sidecar.WxRow, checked the way a row of weather_layers.csv is."""
    from ..sidecar import WxRow, _check, parse_data_source

    row = WxRow(line=line, beat=d.beat, id=d.id, type=d.type, vo_anchor=d.vo_anchor, place=d.place,
                data_source=parse_data_source(d.data_source) if d.data_source else None, hold=d.hold,
                until=d.until if d.until in ("beat_end", "end") else float(d.until), extra=dict(d.extra))
    _check(row)
    return row


# ---- user rows against the evidence (mode B) -------------------------------------------------------------------------------------

def check_user_rows(rows: Sequence[Any], ctx, accept: Sequence[str]) -> List[Conflict]:
    out: List[Conflict] = []
    for r in rows:
        ds = r.data_source
        if ds is None:
            continue
        c = None
        if ds.target == "latest" and ctx.historical and ctx.main_day:
            rep = ""
            if r.type == "satellite" and ds.product == "geocolor":
                w = ctx.window(0, 0)
                t = (ctx.moment or (w[0] if w else None))
                if t is not None and (ctx.recorded or date.today()) - t.date() <= timedelta(days=55):
                    rep = f"gibs:geocolor@{t:%Y-%m-%dT%H}:{t.minute // 10 * 10:02d}Z"
            elif ds.provider == "spc" and ds.product == "outlook" and ctx.conv_day:
                rep = f"spc:outlook@{ctx.conv_day}#{ds.selector or 'day1'}"
            elif ds.provider == "wpc" and ctx.main_day:
                rep = f"wpc:ero@{ctx.main_day}#{ds.selector or 'day1'}"
            c = Conflict(r.id, "stale", f"{r.type} shows the LATEST {ds.provider.upper()} {ds.product} in a story about {ctx.main_day}",
                         f"use the picture/product of the event day ({rep})" if rep else "remove the row or name the event's time", rep)
        elif ds.provider == "nhc" and ctx.storm is not None and ds.target.upper() != ctx.storm.id:
            c = Conflict(r.id, "conflict", f"{r.type} uses storm {ds.target.upper()}, but the story's storm is {ctx.storm.id} "
                         f"({ctx.storm.name.title()} {ctx.storm.year})", f"use {ctx.storm.id}", ds.text.replace(ds.target, ctx.storm.id))
        elif ds.provider == "spc" and ds.product == "reports" and ctx.conv_day and ds.target != ctx.conv_day and ctx.moment is not None:
            c = Conflict(r.id, "conflict", f"storm reports of {ds.target}, but the event at {ctx.moment:%Y-%m-%d %H:%MZ} is in SPC's "
                         f"convective day {ctx.conv_day} (days run 12 UTC to 12 UTC)", f"use spc:reports@{ctx.conv_day}",
                         ds.text.replace(ds.target, ctx.conv_day))
        elif ds.provider == "iem" and ".." in ds.target and ctx.moment is not None:
            from ..news.timeline import parse_window

            try:
                a, b = parse_window(ds.target, max_hours=72)
                if not (a - timedelta(hours=6) <= ctx.moment <= b + timedelta(hours=6)):
                    c = Conflict(r.id, "conflict", f"{r.type} window {ds.target} is far from the event's moment ({ctx.moment:%Y-%m-%d %H:%MZ})",
                                 "check the window")
            except ValueError:
                pass
        if c is not None:
            if c.replacement and (f"{c.kind}:{r.id}" in accept or r.id in accept):
                from ..sidecar import parse_data_source

                r.data_source = parse_data_source(c.replacement)
                c.applied = True
            out.append(c)
    return out


# ---- acquisition --------------------------------------------------------------------------------------------------------------

PHASE1 = ("temp_marker", "forecast_strip", "now_card", "alert_area", "satellite", "source_line")


def acquire(rows: Sequence[Any], net: Net, *, contact: str = "", previous=None, now: Optional[datetime] = None,
            nws_client=None) -> Tuple[Any, Dict[str, str]]:
    """(snapshot, row id -> why its data could not be fetched). Every row is fetched on its own: one failure never stops the rest.
    Data still in `previous` (a fresh earlier snapshot) is reused instead of fetched again."""
    from ..layers import FetchContext, get as layer_type
    from ..resolve import Snapshot, prepare

    now = now or net.now
    snap = Snapshot(prepared=now.astimezone(UTC).replace(microsecond=0).isoformat())
    if previous is not None:
        snap.extra = dict(previous.extra)
        snap.forecasts, snap.observations = dict(previous.forecasts), dict(previous.observations)
        snap.alerts, snap.satellite = dict(previous.alerts), dict(previous.satellite)
    ctx = FetchContext(snap=snap, now=now, nws=None,
                       get_text=lambda u: net.text(u, purpose="graphic data"), get_bytes=lambda u: net.bytes(u, purpose="graphic data"))
    failed: Dict[str, str] = {}
    client = nws_client
    for r in rows:
        try:
            if r.type in PHASE1:
                ds = r.data_source
                if ds is None:
                    continue
                key_have = {"forecast": snap.forecasts, "obs": snap.observations, "alerts": snap.alerts}.get(ds.product)
                if key_have is not None:
                    from ..cities import find_city

                    k = ds.target.upper() if ds.product == "alerts" else find_city(ds.target).key
                    if k in key_have:
                        continue
                if ds.provider == "nws" and client is None:
                    if not contact:
                        raise ValueError("this graphic needs National Weather Service data: set the NWS contact first")
                    from ..nws import NwsClient

                    client = NwsClient(contact)
                part = prepare([r], client, now=now, gibs_get=lambda u: net.text(u, source="gibs_geocolor", purpose="satellite times"))
                snap.forecasts.update(part.forecasts)
                snap.observations.update(part.observations)
                snap.alerts.update(part.alerts)
                snap.satellite.update(part.satellite)
                snap.notes += part.notes
                continue
            lt = layer_type(r.type)
            if lt is not None and lt.fetch is not None:
                lt.fetch(r, ctx)
        except Exception as exc:
            failed[r.id] = f"{classify_error(exc)}: {str(exc)[:240]}"
    return snap, failed


def verify(d: Draft, snap) -> Optional[str]:
    from . import catalog as C

    check = {"storm_reports": C.v_reports, "warnings_archive": C.v_warnings, "counter": C.v_counter, "radar": C.v_radar}.get(d.type)
    return check(d, snap) if check else None


# ---- the run ------------------------------------------------------------------------------------------------------------------

def run(project, plan, words: Sequence = (), *, beats_text: str = "", fmt: str = "news", contact: str = "", voiceover: Optional[Path] = None,
        dry_run: bool = False, now: Optional[datetime] = None, get_text=None, get_bytes=None, fetch_data: bool = True,
        log: Callable[[str], None] = lambda m: None, nws_client=None) -> IntelResult:
    now = now or datetime.now(UTC)
    ev = Evidence(created=now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    net = Net(ev, get_text=get_text, get_bytes=get_bytes, now=now)
    ov = load_overrides(project)
    notes: List[str] = []
    urows = user_rows(project, notes)
    mode = "B" if project.layers_csv.is_file() and urows else "A"
    segs = segments_from_plan(plan, beats_text)
    recorded, rec_how = recording_time(project, voiceover, ov)
    log("[Weather] Reading the story…")
    u = understand(segs, recorded, year_override=(ov.get("event") or {}).get("year"))
    from .context import resolve

    ctx = resolve(u, net, ev, ov, [s.id for s in segs], recorded=recorded.date() if recorded else None, today=now.date())
    if recorded and rec_how.endswith("(an assumption)") and any(d.relative and d.year_from == "recording" for d in u.dates):
        ctx.assumptions.append(f"relative days (yesterday, Sunday ...) are counted from {rec_how}: {recorded:%Y-%m-%d}")
    ev.event = ctx.to_dict()
    log(f"[Weather] Event: {ctx.category.replace('_', ' ')}" + (f", {ctx.storm.name.title()} ({ctx.storm.id})" if ctx.storm else "")
        + (f", {ctx.main_day}" if ctx.main_day else "") + (f", {', '.join(ctx.states)}" if ctx.states else ""))
    from .planner import Planner

    conflicts = check_user_rows(urows, ctx, list(ov.get("accept") or []))
    pl = Planner(ctx, segs, net=net, fmt=fmt, contact=contact, user_rows=urows, overrides=ov, evidence=ev)
    drafts = pl.run()
    notes += pl.notes + ctx.notes
    taken = {r.id for r in urows}   # an id the user's file already uses (older automatic rows were auto_* too) stays theirs
    for d in drafts:
        if d.id in taken:
            old_id, d.id = d.id, f"{d.id}_engine"
            for x in drafts:
                if x.companion_of == old_id:
                    x.companion_of = d.id
    # graphics -> rows (checked as the sidecar checks rows)
    rows, dropped = [], []
    for d in drafts:
        try:
            rows.append(draft_row(d))
        except (ValueError, KeyError) as exc:
            dropped.append((d, f"not a valid {d.type} ({exc})"))
    snap = None
    if fetch_data:
        log("[Weather] Fetching the data the graphics need…")
        previous = None
        try:
            from ..generate import load_snapshot
            from ..resolve import check_fresh

            previous = load_snapshot(project)
            check_fresh(previous, now)
        except Exception:
            previous = None
        snap, failed = acquire(list(urows) + rows, net, contact=contact, previous=previous, now=now, nws_client=nws_client)
        mine = {d.id: d for d in drafts}
        for rid, why in failed.items():
            if rid in mine and not any(r.id == rid for r in urows):
                dropped.append((mine[rid], f"its data could not be fetched ({why})"))
            else:
                notes.append(f"your graphic {rid}: its data could not be fetched ({why})")
        keep_ids = {r.id for r in rows} - set(failed)
        for d in drafts:
            if d.id in keep_ids:
                why = verify(d, snap)
                if why:
                    dropped.append((d, why))
                    keep_ids.discard(d.id)
        _fit_loop_to_warnings(drafts, rows, keep_ids, snap, net, ctx, contact, now, notes)
        # a companion goes with its main graphic; a source line with the last data graphic of its beat
        for d in drafts:
            if d.companion_of and d.companion_of not in keep_ids and d.id in keep_ids:
                keep_ids.discard(d.id)
                dropped.append((d, f"it goes with {d.companion_of}, which was dropped"))
        for d in drafts:
            if d.type == "source_line" and d.id in keep_ids and not any(x.beat == d.beat and x.id in keep_ids and x.type != "source_line" for x in drafts):
                keep_ids.discard(d.id)
        added = [d for d in drafts if d.id in keep_ids]
        _facts_from_snapshot(ev, snap, added, ctx)
        shown = _numbers_shown(plan, words, urows, [r for r in rows if r.id in keep_ids], snap)
    else:
        bad = {d.id for d, _ in dropped}
        added = [d for d in drafts if d.id not in bad]
        shown = []
    claims = check_claims(u, shown)
    res = IntelResult(event=ctx.to_dict(), drafts=drafts, added=added, dropped=dropped, skipped=pl.skipped, preserved=pl.preserved,
                      conflicts=conflicts, notes=notes, assumptions=ctx.assumptions, ambiguities=ctx.ambiguities, evidence=ev, snapshot=snap,
                      beats=segs, dry_run=dry_run, mode=mode, claims=claims)
    from .report import report_text

    res.report = report_text(res, project, recorded_how=rec_how)
    if not dry_run:
        _write(project, res, beats_text, now)
    return res


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _write(project, res: IntelResult, beats_text: str, now: datetime) -> None:
    d = intel_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    plan = {"version": AUTO_PLAN_VERSION, "created": res.evidence.created, "mode": res.mode, "beats_sha": _hash(beats_text),
            "event": res.event, "rows": [x.to_dict() for x in res.added],
            "dropped": [{"id": x.id, "spec": x.spec, "reason": why} for x, why in res.dropped],
            "skipped": [asdict(s) for s in res.skipped], "preserved": [list(p) for p in res.preserved],
            "conflicts": [asdict(c) for c in res.conflicts], "accepted": [c.row for c in res.conflicts if c.applied]}
    (d / "auto_plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (d / "evidence.json").write_text(res.evidence.to_json(), encoding="utf-8")
    (d / "report.md").write_text(res.report, encoding="utf-8")
    res.paths = {"auto_plan": str(d / "auto_plan.json"), "evidence": str(d / "evidence.json"), "report": str(d / "report.md")}
    if res.snapshot is not None:
        project.resolved_json.write_text(res.snapshot.to_json(), encoding="utf-8")
        res.paths["snapshot"] = str(project.resolved_json)


# ---- what the render reads ----------------------------------------------------------------------------------------------------

def load_auto_plan(project) -> Optional[Dict[str, Any]]:
    p = intel_dir(project) / "auto_plan.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return d if d.get("version") == AUTO_PLAN_VERSION else None


def auto_rows(project, notes: Optional[List[str]] = None) -> List[Any]:
    """The engine's rows (WxRow), for weather.generate to add to the user's. A row that no longer checks is left out (said)."""
    d = load_auto_plan(project)
    if not d:
        return []
    out = []
    for i, raw in enumerate(d.get("rows") or [], start=1):
        try:
            out.append(draft_row(Draft(**raw), line=0))
        except (TypeError, ValueError, KeyError) as exc:
            if notes is not None:
                notes.append(f"automatic graphic {raw.get('id')}: left out ({exc})")
    return out


def accepted_replacements(project) -> Dict[str, str]:
    """User row id -> the data_source the user accepted in the overrides (applied in memory; the file is never changed)."""
    d = load_auto_plan(project) or {}
    return {c["row"]: c["replacement"] for c in d.get("conflicts") or [] if c.get("applied") and c.get("replacement")}


def merge_rows(project, rows: List[Any], notes: Optional[List[str]] = None) -> List[Any]:
    """The user's rows (with accepted replacements) followed by the engine's, user ids winning any clash."""
    from ..sidecar import parse_data_source

    rep = accepted_replacements(project)
    for r in rows:
        if r.id in rep:
            r.data_source = parse_data_source(rep[r.id])
    have = {r.id for r in rows}
    return list(rows) + [r for r in auto_rows(project, notes) if r.id not in have]


def _facts_from_snapshot(ev: Evidence, snap, added: Sequence[Draft], ctx) -> None:
    """Facts for the graphics the engine added: what each one shows, from the snapshot it will be rendered from."""
    from .catalog import v_counter

    for d in added:
        src = source_of(_ds(d))
        if d.type == "counter":
            from ..layers.counters import count
            from ..sidecar import parse_data_source

            class R:
                pass

            r = R()
            r.data_source, r.extra, r.id = parse_data_source(d.data_source), d.extra, d.id
            try:
                n, label, sub, s = count(r, snap)
                ev.add(kind="preliminary_report" if r.data_source.provider == "spc" else "warning", subject=label.title(),
                       what="count", value=n, where=",".join(d.extra.get("states", [])) or "US", source=src, record=s.url,
                       retrieved=s.fetched, issued=s.issued, quality="preliminary" if r.data_source.provider == "spc" else "final",
                       method="weather.layers.counters.count (one per report / one per warning event id)")
            except Exception:
                pass
        elif d.type == "storm_reports":
            from ..layers.severe import report_kinds, reports_key

            v = snap.extra.get(reports_key(d.data_source.split("@")[1].split("#")[0]), {})
            states = set(d.extra.get("states") or [])
            for k in report_kinds(d.data_source.split("#")[1] if "#" in d.data_source else ""):
                reps = [x for x in v.get("reports", []) if x["kind"] == k and (not states or x.get("state") in states)]
                ev.add(kind="preliminary_report", subject=f"{k} reports", what="count", value=len(reps), where=",".join(sorted(states)) or "US",
                       source="spc_reports", record=v.get("url", ""), retrieved=v.get("fetched", ""), valid=f"{v.get('start')}..{v.get('end')}",
                       quality="preliminary", caveats=["reports are not tornado counts: one tornado can bring several reports"])
                for x in reps[:12]:
                    ev.add(kind="preliminary_report", subject=f"{k} report", what="report", value=x.get("place", ""),
                           where=f"{x.get('county', '')}, {x.get('state', '')} ({x['lat']},{x['lon']})", source="spc_reports",
                           record=v.get("url", ""), retrieved=v.get("fetched", ""), issued=x["time"], quality="preliminary")
        elif d.type == "warnings_archive":
            from ..layers.severe import selected_warnings
            from ..sidecar import parse_data_source

            class R2:
                pass

            r = R2()
            r.data_source, r.extra = parse_data_source(d.data_source), d.extra
            try:
                v, ws = selected_warnings(snap, r)
                ev.add(kind="warning", subject="NWS warnings in the window", what="warning polygons", value=len(ws),
                       where=",".join(d.extra.get("states", [])) or "US", source="iem_warnings", record=v["url"], retrieved=v["fetched"],
                       valid=f"{v['start']}..{v['end']}", caveats=["one warning can have several polygons (updates)"])
            except Exception:
                pass
        elif d.data_source:
            ev.add(kind={"nhc_gis_advisory": "forecast", "nhc_gis_best_track": "best_track", "mrms": "estimate", "acis": "observed",
                         "usgs_iv": "observed", "spc_outlook": "forecast", "wpc_ero": "forecast", "iem_radar": "observed",
                         "gibs_daily": "observed", "gibs_geocolor": "observed", "nhc_hurdat2": "derived", "nws_api": "forecast"}.get(src, "observed"),
                   subject=d.spec, what=d.type, value=d.data_source, source=src, record=d.data_source, retrieved=ev.created,
                   quality="estimate" if src == "mrms" else "final", method=d.why)


def _ds(d: Draft):
    from ..sidecar import parse_data_source

    return parse_data_source(d.data_source) if d.data_source else None


# ---- entry points the app and the CLI share ---------------------------------------------------------------------------------------

def project_plan(project, words: Sequence, duration: float, notes: List[str]):
    """(HybridPlan, beats text): beats.csv repaired the forgiving way (weather.autofix), else beats built from the narration itself
    (weather.intel.beats) when the project has no beat plan."""
    if project.beats_csv.is_file():
        from ..autofix import repair_beats

        text = project.beats_csv.read_text(encoding="utf-8")
        plan, _aliases = repair_beats(text, words, duration, notes)
        return plan, text
    from .beats import plan_from_narration

    plan = plan_from_narration(words, duration, notes, script=_script_text(project))
    return plan, ""


def _script_text(project) -> str:
    p = Path(project.root) / "script.txt"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def enabled(project) -> bool:
    """On unless the project's weather.json says "intelligence": false."""
    try:
        return json.loads((Path(project.root) / "weather.json").read_text(encoding="utf-8")).get("intelligence", True) is not False
    except (OSError, ValueError):
        return True


def prepare_project(project, words: Sequence, duration: float, *, fmt: str = "news", contact: str = "", voiceover: Optional[Path] = None,
                    log: Callable[[str], None] = print, dry_run: bool = False, **kw) -> Optional[IntelResult]:
    """Run the engine for a project before Check plan / Generate. Never raises: a failure is logged and the render goes on with the
    user's own rows (and the data refresh the app always did)."""
    if not enabled(project):
        return None
    notes: List[str] = []
    try:
        plan, beats_text = project_plan(project, words, duration, notes)
        res = run(project, plan, words, beats_text=beats_text, fmt=fmt, contact=contact, voiceover=voiceover, dry_run=dry_run, log=log, **kw)
    except Exception as exc:   # the engine must never be the reason a video cannot be made
        log(f"[Weather] Weather Intelligence could not run ({exc!r}); the plan's own graphics are used")
        return None
    from .report import summary_lines

    for line in summary_lines(res):
        log(f"[Weather] {line}")
    if res.paths.get("report"):
        log(f"[Weather] Full report: {res.paths['report']}")
    return res


# ---- the narration's numbers against the data ----------------------------------------------------------------------------------

def _numbers_shown(plan, words, urows, arows, snap) -> List[Dict[str, Any]]:
    """The numbers the graphics will put on screen (weather.events numbers report), built the way the render builds them."""
    from ..autofix import build, windows

    try:
        rows, wins = windows(list(urows) + list(arows), plan, words, [])
        _rows, payload = build(rows, snap, wins, [])
        return list(payload.report.lines)
    except Exception:
        return []


NUM = __import__("re").compile(r"-?\d+(?:\.\d+)?")


def check_claims(u, shown: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each number the narration says (with a unit) -> the on-screen number that matches it, or "not verified". A claim is never
    called wrong: a number no fetched source shows is only unverified (the survey or the article it came from was not read)."""
    out, seen = [], set()
    for m in u.measurements:
        if m.unit in ("min", "h") or (m.unit, m.value) in seen:
            continue
        seen.add((m.unit, m.value))
        hit = None
        unit_word = {"cat": r"CAT(?:EGORY)?\s*", "EF": r"EF-?", "mph": None, "in": None, "ft": None, "mb": None}.get(m.unit, None)
        need = {"mph": "MPH", "in": "IN", "ft": "FT", "mb": "MB", "F": "°", "%": "%"}.get(m.unit, "")
        for ln in shown:
            text = str(ln.get("shown", ""))
            if unit_word is not None:
                if __import__("re").search(unit_word + str(int(m.value)) + r"\b", text.upper()):
                    hit = ln
                    break
                continue
            if need and need not in text.upper():
                continue
            if m.unit == "count":   # a count matches only a line that counts the same thing (warnings, tornadoes, reports)
                noun = {"count_warnings": "warning", "count_tornado": "tornado", "count_reports": "report"}.get(m.quantity, "")
                if noun not in (str(ln.get("label", "")) + " " + text).lower():
                    continue
            for x in NUM.findall(text):
                v = float(x)
                tol = 0.006 * max(abs(m.value), 1.0) if m.value != int(m.value) else 0.5
                if abs(v - m.value) <= tol:
                    hit = ln
                    break
            if hit:
                break
        out.append({"said": m.text, "beat": m.seg, "value": m.value, "unit": m.unit, "verified": bool(hit),
                    "by": f"[{hit['layer']}] {hit['label']}: {hit['shown']} ({hit['product']})" if hit else ""})
    return out


# ---- evidence-driven refinement --------------------------------------------------------------------------------------------------

def _fit_loop_to_warnings(drafts, rows, keep_ids, snap, net, ctx, contact, now, notes) -> None:
    """A radar loop the narration did not time (a window around the event's moment) is fitted to the warnings it shows: from a little
    before the first one is issued to a little after the last one ends. A ten-minute tornado warning in a five-hour loop is on screen
    for about a second; fitted, it stays long enough to read, and the loop is spent on the storm the story is about."""
    from ..layers.severe import selected_warnings, warnings_key
    from ..news.timeline import parse_window
    from ..tz import parse_iso

    radar = next((d for d in drafts if d.id == "auto_radar" and d.id in keep_ids and d.entity != "said"), None)
    warn = next((d for d in drafts if d.id == "auto_warnings" and d.id in keep_ids), None)
    if radar is None or warn is None:
        return
    wrow = next(r for r in rows if r.id == warn.id)
    try:
        v, ws = selected_warnings(snap, wrow)
        a0, b0 = parse_window(radar.data_source.split("@")[1].split("#")[0], max_hours=48)
    except (KeyError, ValueError):
        return
    live = [w for w in ws if parse_iso(w["ends"]) > a0 and parse_iso(w["starts"]) < b0]
    if ctx.moment is not None:
        near = [w for w in live if parse_iso(w["starts"]) - timedelta(hours=1) <= ctx.moment <= parse_iso(w["ends"]) + timedelta(hours=1)]
        live = near or live
    if not live:
        return
    first = min(parse_iso(w["starts"]) for w in live)
    last = max(parse_iso(w["ends"]) for w in live)
    pad = max(timedelta(minutes=10), min(timedelta(minutes=45), last - first))   # the warnings fill about a fifth of the loop or more
    a = first - pad
    b = last + pad
    a = a.replace(minute=a.minute // 5 * 5, second=0, microsecond=0)
    b = b.replace(second=0, microsecond=0) + timedelta(minutes=(5 - b.minute % 5) % 5)
    if (b - a) >= 0.7 * (b0 - a0):
        return
    target = f"{a:%Y-%m-%dT%H:%MZ}..{b:%Y-%m-%dT%H:%MZ}"
    old = (radar.data_source, warn.data_source)
    radar.data_source = radar.data_source.replace(radar.data_source.split("@")[1].split("#")[0], target)
    warn.data_source = warn.data_source.replace(warn.data_source.split("@")[1].split("#")[0], target)
    try:
        new_rows = [draft_row(radar), draft_row(warn)]
        part, failed = acquire(new_rows, net, contact=contact, now=now)
        if failed or verify(radar, part) or verify(warn, part):
            raise ValueError("; ".join(failed.values()) or "the fitted window has no data")
    except Exception as exc:
        radar.data_source, warn.data_source = old
        notes.append(f"the radar loop kept its first window ({exc})")
        return
    for k in [k for k in snap.extra if k.startswith("radar:") and k.endswith("@" + old[0].split("@")[1].split("#")[0])] + \
             [warnings_key(old[1].split("@")[1].split("#")[0], warn.extra.get("states", []))]:
        snap.extra.pop(k, None)
    snap.extra.update(part.extra)
    for i, r in enumerate(rows):
        if r.id == radar.id:
            rows[i] = new_rows[0]
        elif r.id == warn.id:
            rows[i] = new_rows[1]
    why = f"fitted to the warnings it shows ({first:%H:%MZ} to {last:%H:%MZ}): {target}"
    radar.why = f"radar mosaic {why}"
    warn.why = f"NWS warnings, same window ({why})"
