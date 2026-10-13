"""The daily prep: fetch -> story -> script -> plan -> resolved.json, all written into a project folder at once.

    coverage.json        everything fetched (every covered city, the national alerts): what the script was written from
    script.txt           the script to record
    beats.csv            the Hybrid beat CSV
    weather_layers.csv   the weather layers
    resolved.json        the data the layers show (copied from coverage.json where it is the same product, plus the alert areas,
                         the satellite picture and any layer type's own data)
    prep.json            when, the story and why, every script line with the numbers it says (weather.automation.changes reads it)

Nothing is written until everything is fetched and checked; then each file is written next to its final name and moved into
place, prep.json last. A failed fetch leaves the folder as it was. Running it again replaces the prep, except a script.txt
the user has edited since (refused unless force=True: the edit would be lost)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..nws import NwsClient
from ..resolve import Snapshot, _gibs_get, _iso, check_fresh, fetch_alerts, fetch_geocolor
from ..sidecar import parse_sidecar
from ..tz import to_local
from .fetch import fetch_coverage
from .plan import build_plan
from .script import write_script
from .story import pick_story

PREP_VERSION = 1
CENTRAL = "America/Chicago"
FILES = ("coverage.json", "script.txt", "beats.csv", "weather_layers.csv", "resolved.json", "prep.json")   # prep.json last


class PrepError(RuntimeError):
    pass


@dataclass
class PrepResult:
    project: Path
    story: Any
    script: Any
    plan: Any
    resolved: Snapshot
    notes: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = self.story
        return (f"Forecast for {s.on.strftime('%A, %B')} {s.on.day}: {s.kind.replace('_', ' ')} story, lead city {s.lead_city}. "
                f"Script: {self.script.word_count} words (about {self.script.word_count / 150:.1f} min at 150 words a minute), "
                f"{len(self.plan.beats)} beats.")


def central_date(now: datetime) -> date:
    return to_local(now, CENTRAL)[0].date()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_prep(project: Path) -> Optional[Dict[str, Any]]:
    f = Path(project) / "prep.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None


def script_edited(project: Path) -> bool:
    """True when script.txt is not the one the last prep wrote (the user changed it)."""
    p = read_prep(project)
    s = Path(project) / "script.txt"
    return bool(p and s.is_file() and sha(s.read_text(encoding="utf-8")) != p.get("script_sha"))


def resolve_for_layers(layers_csv: str, coverage: Snapshot, client: NwsClient, now: datetime, *,
                       gibs_get: Callable[[str], str] = _gibs_get, get_text=None, get_bytes=None) -> Snapshot:
    """resolved.json for the plan: forecasts and observations from the coverage snapshot (the same NWS answers the script was
    written from), alert areas and the satellite picture fetched here, each layer type's own data through its fetch hook."""
    from ..cities import find_city
    from ..layers import FetchContext, get as layer_type, http_bytes, http_text

    rows = parse_sidecar(layers_csv)
    snap = Snapshot(prepared=_iso(now))
    for r in rows:
        ds = r.data_source
        if ds is not None and ds.provider == "nws" and ds.product in ("forecast", "obs"):
            key = find_city(ds.target).key
            src = coverage.forecasts if ds.product == "forecast" else coverage.observations
            if key not in src:
                raise PrepError(f"weather_layers.csv row {r.line} ({r.id}): the prep has no {ds.product} for {key}")
            (snap.forecasts if ds.product == "forecast" else snap.observations)[key] = src[key]
    ctx = FetchContext(snap=snap, now=now, nws=client, get_text=get_text or http_text, get_bytes=get_bytes or http_bytes)
    for r in rows:
        ds = r.data_source
        lt = layer_type(r.type) if r.type not in ("temp_marker", "forecast_strip", "now_card", "alert_area", "satellite", "source_line") else None
        if lt is not None:
            if lt.fetch is not None:
                lt.fetch(r, ctx)
        elif ds is not None and ds.product == "alerts" and ds.target.upper() not in snap.alerts:
            area = ds.target.upper()
            snap.alerts[area] = fetch_alerts(client, area)
            snap.notes += [f"alerts {area}: {s}" for s in snap.alerts[area]["skipped"]]
        elif ds is not None and ds.product == "geocolor" and f"geocolor@{ds.target}" not in snap.satellite:
            snap.satellite[f"geocolor@{ds.target}"] = fetch_geocolor(ds.target, now, gibs_get)
    check_fresh(snap, now, when="prep")
    return snap


def _write_all(project: Path, contents: Dict[str, str]) -> None:
    """Every file next to its final name first; then moved into place in FILES order (prep.json last). On any error the
    temporary files are removed and nothing already in the folder is touched."""
    tmp: Dict[str, Path] = {}
    try:
        for name in FILES:
            t = project / f".{name}.prep-tmp"
            t.write_text(contents[name], encoding="utf-8")
            tmp[name] = t
        for name in FILES:
            os.replace(tmp[name], project / name)
    finally:
        for t in tmp.values():
            if t.exists():
                t.unlink()


def prep(project: "str | Path", contact: str = "", *, now: Optional[datetime] = None, client: Optional[NwsClient] = None,
         force: bool = False, library_dir: Optional[str] = None, gibs_get: Callable[[str], str] = _gibs_get, get_text=None, get_bytes=None,
         log: Callable[[str], None] = lambda s: None) -> PrepResult:
    from ..layers import discover

    discover()   # the layer types (and the covered metros in find_city)
    project = Path(project)
    project.mkdir(parents=True, exist_ok=True)
    if script_edited(project) and not force:
        raise PrepError(f"{project / 'script.txt'} was edited after the last prep; preparing again would replace your edit. "
                        "Save your version elsewhere, or prepare again with force.")
    now = now or datetime.now(timezone.utc)
    client = client or NwsClient(contact)
    log("fetching every covered city and the national alerts")
    coverage = fetch_coverage(client, now=now, log=log)
    story = pick_story(coverage)
    log(f"story: {story.kind} ({story.lead_city})")
    script = write_script(coverage, story, today=central_date(now))
    plan = build_plan(coverage, story, script)
    beats_csv, lib_notes = plan.beats_csv, []
    if library_dir:
        from ..footage_library import prefer_library

        beats_csv, lib_notes = prefer_library(beats_csv, library_dir)
    log("fetching the alert areas and the satellite picture for the layers")
    resolved = resolve_for_layers(plan.layers_csv, coverage, client, now, gibs_get=gibs_get, get_text=get_text, get_bytes=get_bytes)
    notes = list(dict.fromkeys(coverage.notes + resolved.notes))
    meta = {"version": PREP_VERSION, "prepared": _iso(now), "for_date": story.on.isoformat(), "story": story.to_dict(), "why": story.why,
            "script_sha": sha(script.text), "words": script.word_count, "lines": script.lines(), "beats": plan.beats,
            "notes": notes, "library": lib_notes}
    _write_all(project, {"coverage.json": coverage.to_json(), "script.txt": script.text, "beats.csv": beats_csv,
                         "weather_layers.csv": plan.layers_csv, "resolved.json": resolved.to_json(),
                         "prep.json": json.dumps(meta, indent=1, ensure_ascii=False)})
    return PrepResult(project, story, script, plan, resolved, notes)
