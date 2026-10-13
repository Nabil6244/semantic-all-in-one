"""What changed since the prep, in plain words, and which script lines say the numbers that moved (re-record just those).

    Dallas Tuesday high 92° → 94°
    Boston Tuesday chance of rain 54% → 70%
    Houston Wednesday: Sunny → Chance Showers And Thunderstorms
    new: Flood Warning for Harris County, Texas
    ended: Flood Watch (UT)

diff(old, new) compares two snapshots (pure, tested); check(project) fetches fresh (around the cache: a real new answer) the same
products the prep used, compares them with coverage.json and resolved.json, and lists the script lines (prep.json "lines") whose
numbers changed. It writes changes.json in the project and nothing else: the prep stays as it was until the user prepares again
or fetches the data again for the render."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..alerts import county_shapes
from ..resolve import Snapshot, fetch_alerts
from .fetch import day_date, fetch_coverage, national_alerts
from .story import _lower48


@dataclass
class Change:
    kind: str  # forecast | sky | now | alert_new | alert_ended
    text: str
    city: str = ""
    date: str = ""
    field: str = ""  # high | low | pop | now | short
    old: Any = None
    new: Any = None
    event: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ChangeReport:
    changes: List[Change] = field(default_factory=list)
    lines: List[Dict[str, Any]] = field(default_factory=list)  # {"text": script line, "changes": [texts]}
    checked: str = ""

    @property
    def text(self) -> str:
        if not self.changes:
            return "No changes since the prep: the script and the numbers on screen still match the latest data."
        out = ["Changed since the prep:"] + [f"  {c.text}" for c in self.changes]
        if self.lines:
            out += ["", "Script lines to re-record:"] + [f"  \"{ln['text']}\"  ({'; '.join(ln['changes'])})" for ln in self.lines]
        else:
            out += ["", "No script line says these numbers: the screen updates when the data is fetched again."]
        return "\n".join(out)

    def to_dict(self) -> Dict[str, Any]:
        return {"checked": self.checked, "changes": [c.to_dict() for c in self.changes], "lines": self.lines}


def _dow(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%A")


def _city(key: str) -> str:
    return key.split(",")[0]


def _where(a: Dict[str, Any], area: str) -> str:
    """Where an alert area is, for a sentence: its counties ('Harris County, TX'), else the state it was fetched for."""
    if a.get("area"):
        return a["area"] if len(a["area"]) <= 80 else a["area"][:77].rsplit(";", 1)[0] + " ..."
    shapes = county_shapes() if a.get("counties") else {}
    names = [f"{shapes[c]['name']} County, {shapes[c].get('state') or area}" for c in a.get("counties", []) if c in shapes]
    if names:
        return "; ".join(names[:3]) + (" ..." if len(names) > 3 else "")
    return area


def diff_forecasts(old: Snapshot, new: Snapshot, changes: List[Change]) -> None:
    for key, f in old.forecasts.items():
        g = new.forecasts.get(key)
        if g is None:
            continue
        newdays = {day_date(d).isoformat(): d for d in g["days"]}
        for d in f["days"]:
            iso = day_date(d).isoformat()
            e = newdays.get(iso)
            if e is None:
                continue
            for fld, label, unit in (("high", "high", "°"), ("low", "low", "°"), ("pop", "chance of rain", "%")):
                a = (d.get(fld) or {}).get("value")
                b = (e.get(fld) or {}).get("value")
                if a != b and not (fld == "pop" and max(a or 0, b or 0) < 20):   # small chances are not said or shown
                    show = lambda v: "none" if v is None else f"{v}{unit}"  # noqa: E731
                    changes.append(Change("forecast", f"{_city(key)} {_dow(iso)} {label} {show(a)} → {show(b)}", key, iso, fld, a, b))
            if d.get("short") != e.get("short"):
                changes.append(Change("sky", f"{_city(key)} {_dow(iso)}: {d.get('short')} → {e.get('short')}", key, iso, "short", d.get("short"), e.get("short")))
    for key, o in old.observations.items():
        p = new.observations.get(key)
        if p and o["temp"]["value"] != p["temp"]["value"]:
            changes.append(Change("now", f"{_city(key)} now {o['temp']['value']}° → {p['temp']['value']}° (observed)", key, "", "now",
                                  o["temp"]["value"], p["temp"]["value"]))


def diff_alerts(old: Dict[str, Dict[str, Any]], new: Dict[str, Dict[str, Any]], changes: List[Change], now: Optional[datetime] = None) -> None:
    """Alert areas by state (resolved.json "alerts"): new ones, and ones that ended (gone from the list, or past their end time)."""
    from ..tz import parse_iso

    for area, a in old.items():
        b = new.get(area)
        if b is None:
            continue
        before = {x["id"]: x for x in a["areas"]}
        after = {x["id"]: x for x in b["areas"]}
        for i, x in after.items():
            if i not in before:
                changes.append(Change("alert_new", f"new: {x['event']} for {_where(x, area)}", event=x["event"], new=i))
        for i, x in before.items():
            end = x.get("ends") or x.get("expires")
            if i not in after or (now and end and parse_iso(end) <= now):
                changes.append(Change("alert_ended", f"ended: {x['event']} for {_where(x, area)}", event=x["event"], old=i))


def diff_national(old: Snapshot, new: Snapshot, changes: List[Change]) -> None:
    """Warnings and watches over the lower 48 that came or went (the script's story and warnings lines name them)."""
    keep = lambda a: _lower48(a) and a["event"].endswith(("Warning", "Watch"))  # noqa: E731
    before = {a["id"]: a for a in national_alerts(old) if keep(a)}
    after = {a["id"]: a for a in national_alerts(new) if keep(a)}
    seen = {c.new for c in changes} | {c.old for c in changes}
    for i, a in after.items():
        if i not in before and i not in seen:
            changes.append(Change("alert_new", f"new: {a['event']} for {_where(a, '/'.join(a['states']))}", event=a["event"], new=i))
    for i, a in before.items():
        if i not in after and i not in seen:
            changes.append(Change("alert_ended", f"ended: {a['event']} for {_where(a, '/'.join(a['states']))}", event=a["event"], old=i))


def diff(old: Snapshot, new: Snapshot, *, now: Optional[datetime] = None) -> List[Change]:
    out: List[Change] = []
    diff_forecasts(old, new, out)
    diff_alerts(old.alerts, new.alerts, out, now)
    if national_alerts(old):
        diff_national(old, new, out)
    return out


def lines_to_rerecord(changes: List[Change], lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Script lines (prep.json "lines") that say a changed number, or name an alert type that came or went."""
    from .spoken import event_phrase

    out = []
    for ln in lines:
        hits = []
        for c in changes:
            if c.kind == "forecast" and any(r["city"] == c.city and r["date"] == c.date and r["field"] == c.field for r in ln["refs"]):
                hits.append(c.text)
            elif c.kind == "now" and any(r["city"] == c.city and r["field"] == "now" for r in ln["refs"]):
                hits.append(c.text)
            elif c.kind == "sky" and any(r["city"] == c.city and r["date"] == c.date for r in ln["refs"]):
                hits.append(c.text)
            elif c.kind.startswith("alert") and c.event and any(p in ln["text"].lower() for p in (event_phrase(c.event, 1)[2:].strip(), event_phrase(c.event, 2))):
                hits.append(c.text)
        if hits:
            out.append({"text": ln["text"], "changes": list(dict.fromkeys(hits))})
    return out


def check(project: "str | Path", contact: str = "", *, client=None, now: Optional[datetime] = None, log: Callable[[str], None] = lambda s: None) -> ChangeReport:
    """Fetch the prep's products again (bypassing the cache) and report what changed. Writes changes.json; nothing else."""
    from ..cache import HttpCache
    from ..nws import NwsClient
    from .prep import read_prep

    project = Path(project)
    meta = read_prep(project)
    if meta is None:
        raise FileNotFoundError(f"{project} has no prep.json: prepare the forecast first")
    now = now or datetime.now(timezone.utc)
    old_cov = Snapshot.from_json((project / "coverage.json").read_text(encoding="utf-8"))
    old_res = Snapshot.from_json((project / "resolved.json").read_text(encoding="utf-8"))
    if client is None:
        client = NwsClient(contact, cache=HttpCache(Path(tempfile.mkdtemp(prefix="wx-changes-"))))
    new_cov = fetch_coverage(client, now=now, log=log)
    new_res = Snapshot(prepared=new_cov.prepared, alerts={area: fetch_alerts(client, area) for area in old_res.alerts})
    changes: List[Change] = []
    diff_forecasts(old_cov, new_cov, changes)
    diff_alerts(old_res.alerts, new_res.alerts, changes, now)
    diff_national(old_cov, new_cov, changes)
    rep = ChangeReport(changes, lines_to_rerecord(changes, meta.get("lines", [])), new_cov.prepared)
    (project / "changes.json").write_text(json.dumps(rep.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")
    return rep
