"""The feed behind "Suggested reports" (phase 5): the significant NWS warnings of the last weeks and the SPC storm reports of the
last days, handed to weather.post.suggest. Read-only public data; nothing is prepared until the user picks a suggestion.

    alert_history(client, now)       NWS /alerts (past alerts, actual, the SIGNIFICANT events only), every page
    report_history(get_text, now)    SPC filtered storm reports, one CSV per convective day (a missing day is skipped)
    suggestions(client, get_text, now, already)  -> (suggestions, problems)"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Tuple
from urllib.parse import quote

from ..cities import US_STATES
from ..nws import API
from ..news import spc
from .suggest import MAX_AGE, SIGNIFICANT, Suggestion, suggest

MAX_PAGES = 10
REPORT_DAYS = 10


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def alerts_url(now: datetime, days: int) -> str:
    events = ",".join(quote(e) for e in sorted(SIGNIFICANT))
    return f"{API}/alerts?status=actual&message_type=alert&start={_iso(now - timedelta(days=days))}&end={_iso(now)}&event={events}"


def _states(ugc: Iterable[str]) -> List[str]:
    return sorted({u[:2] for u in ugc if len(u) == 6 and u[:2] in US_STATES and u[2] in "CZ"})


def alert_history(client, now: datetime, days: int = MAX_AGE.days + 2) -> List[Dict[str, Any]]:
    url, out = alerts_url(now, days), []
    for _ in range(MAX_PAGES):
        d, _resp = client.get_json(url)
        for f in d.get("features", []):
            p = f.get("properties") or {}
            states = _states((p.get("geocode") or {}).get("UGC") or [])
            start, end = p.get("onset") or p.get("effective") or p.get("sent"), p.get("ends") or p.get("expires")
            if p.get("event") in SIGNIFICANT and states and start and end:
                out.append({"event": p["event"], "states": states, "onset": start, "ends": end})
        url = ((d.get("pagination") or {}).get("next")) or ""
        if not url or not d.get("features"):
            break
    return out


def report_history(get_text: Callable[[str], str], now: datetime, days: int = REPORT_DAYS) -> Tuple[List[Dict[str, Any]], List[str]]:
    out, missing = [], []
    for k in range(1, days + 1):
        day = (now - timedelta(days=k)).strftime("%Y-%m-%d")
        url = spc.REPORTS.format(yymmdd=(now - timedelta(days=k)).strftime("%y%m%d"))
        try:
            out += [{"kind": r["kind"], "state": r["state"], "time": r["time"]} for r in spc.reports(get_text(url), day) if r.get("state")]
        except Exception:  # noqa: BLE001 - a day SPC has not posted (or cannot be reached) is skipped and named
            missing.append(day)
    return out, missing


def suggestions(client, get_text: Callable[[str], str], now: datetime, already: Iterable[str] = ()) -> Tuple[List[Suggestion], List[str]]:
    problems = []
    alerts = alert_history(client, now)
    reports, missing = report_history(get_text, now)
    if missing:
        problems.append(f"SPC storm reports missing for {len(missing)} day(s) ({', '.join(missing[:3])}{'…' if len(missing) > 3 else ''})")
    return suggest(alerts, reports, now, already=already), problems


def event_text(s: Suggestion) -> str:
    """The THE EVENT line of the Post-Event prompt, from a suggestion."""
    return (f"THE EVENT: {s.title}. State: {s.state}. Dates (UTC): {s.start:%Y-%m-%d} to {s.end:%Y-%m-%d}. "
            f"{s.warnings} significant warning(s), {s.reports} storm report(s). Why it is ready: {'; '.join(s.why)}")
