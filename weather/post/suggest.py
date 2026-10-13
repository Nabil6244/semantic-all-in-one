"""'A post-event report is ready to make': a pure rule over the warnings an area had and the storm reports that came in.

An episode is a run of significant warnings for one state, each starting within 48 hours of the one before. It is ready when
    - every warning of the episode has ended at least SETTLE hours ago (the daily station data and river readings are in),
    - the state has no significant warning in force now (the event is over there),
    - it was big enough: a hurricane or tropical storm warning, or at least MIN_WARNINGS warnings, or MIN_REPORTS storm reports,
    - for a severe-storm episode, the SPC reports are in (the last report is a day old; they stay "preliminary" on screen),
    - it ended no more than MAX_AGE days ago, and it was not suggested before (pass the ids already offered).
The suggestion names a title, the state, the dates and why; the user approves it before anything is prepared."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..tz import parse_iso
from .fmt import span

SETTLE = timedelta(hours=24)
REPORTS_SETTLE = timedelta(hours=24)
GAP = timedelta(hours=48)
MAX_AGE = timedelta(days=30)
MIN_WARNINGS = 3
MIN_REPORTS = 10

# warning -> the kind of event it points to (most serious first when an episode has several)
KINDS = [
    ("hurricane", ("Hurricane Warning", "Storm Surge Warning", "Extreme Wind Warning")),
    ("tropical", ("Tropical Storm Warning",)),
    ("tornado", ("Tornado Warning", "Tornado Emergency")),
    ("flood", ("Flash Flood Emergency", "Flash Flood Warning", "Flood Warning")),
    ("winter", ("Blizzard Warning", "Ice Storm Warning", "Winter Storm Warning")),
    ("heat", ("Extreme Heat Warning", "Excessive Heat Warning")),
    ("severe", ("Severe Thunderstorm Warning",)),
]
TITLES = {"hurricane": "Hurricane aftermath", "tropical": "Tropical storm aftermath", "tornado": "Tornado outbreak",
          "flood": "Flooding", "winter": "Winter storm", "heat": "Heat wave", "severe": "Severe storms"}
SIGNIFICANT = {e for _k, evs in KINDS for e in evs}
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "Washington, D.C.", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}


@dataclass(frozen=True)
class Alert:
    event: str
    state: str
    start: datetime
    end: datetime

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> List["Alert"]:
        """{event, states: [..] (or state), onset|effective|sent, ends|expires} -> one Alert per state."""
        start = d.get("onset") or d.get("effective") or d.get("sent")
        end = d.get("ends") or d.get("expires")
        if not (d.get("event") and start and end):
            raise ValueError(f"an alert needs event, a start (onset/effective/sent) and an end (ends/expires): {d}")
        states = d.get("states") or [d.get("state")]
        return [Alert(d["event"], str(s).upper(), parse_iso(start), parse_iso(end)) for s in states if s]


@dataclass(frozen=True)
class Report:
    kind: str  # tornado | wind | hail | flood ...
    state: str
    time: datetime

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Report":
        return Report(str(d.get("kind") or d.get("type") or "").lower(), str(d["state"]).upper(), parse_iso(d["time"]))


@dataclass
class Suggestion:
    id: str
    title: str
    kind: str
    state: str
    start: datetime
    end: datetime
    warnings: int
    reports: int
    why: List[str] = field(default_factory=list)


def _kind(events: Iterable[str]) -> str:
    evs = set(events)
    for k, names in KINDS:
        if evs & set(names):
            return k
    return "severe"


def episodes(alerts: Sequence[Alert]) -> Dict[str, List[List[Alert]]]:
    """state -> its episodes (runs of significant warnings, each starting within GAP of the run so far)."""
    out: Dict[str, List[List[Alert]]] = {}
    for a in sorted((x for x in alerts if x.event in SIGNIFICANT), key=lambda x: (x.state, x.start)):
        runs = out.setdefault(a.state, [])
        if runs and a.start <= max(x.end for x in runs[-1]) + GAP:
            runs[-1].append(a)
        else:
            runs.append([a])
    return out


def suggest(alerts: Sequence[Any], reports: Sequence[Any], now: datetime, *, already: Iterable[str] = ()) -> List[Suggestion]:
    """Post-event reports ready to make now, most recent first. `alerts`/`reports` are Alert/Report or their dicts."""
    al = [x for a in alerts for x in (Alert.from_dict(a) if isinstance(a, dict) else [a])]
    rp = [Report.from_dict(r) if isinstance(r, dict) else r for r in reports]
    seen = set(already)
    out = []
    for state, runs in episodes(al).items():
        active = any(a.start <= now < a.end for a in al if a.state == state and a.event in SIGNIFICANT)
        for run in runs:
            start, end = min(a.start for a in run), max(a.end for a in run)
            kind = _kind(a.event for a in run)
            sid = f"{state}:{start:%Y-%m-%d}:{kind}"
            if sid in seen or active or end > now - SETTLE or now - end > MAX_AGE:
                continue
            inside = [r for r in rp if r.state == state and start - timedelta(hours=6) <= r.time <= end + timedelta(hours=6)]
            big = kind in ("hurricane", "tropical") or len(run) >= MIN_WARNINGS or len(inside) >= MIN_REPORTS
            if not big:
                continue
            if kind in ("tornado", "severe"):
                if not inside or max(r.time for r in inside) > now - REPORTS_SETTLE:
                    continue   # storm reports still coming in
            why = [f"{len(run)} warning(s) ({', '.join(sorted({a.event for a in run}))}), the last ended {end:%Y-%m-%d %H:%MZ}",
                   "no warning in force in the state now"]
            if inside:
                why.append(f"{len(inside)} storm report(s) in (preliminary)")
            name = STATE_NAMES.get(state, state)
            title = f"{TITLES[kind]} in {name}, {span(start.date(), end.date(), year=True).title()}: what happened"
            out.append(Suggestion(sid, title, kind, state, start, end, len(run), len(inside), why))
    return sorted(out, key=lambda s: s.end, reverse=True)
