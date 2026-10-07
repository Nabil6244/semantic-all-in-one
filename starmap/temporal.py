"""The temporal vocabulary of StarMap: what state a thing is in (STATUS), how its geometry is known (BASIS), and how precisely
its dates are known (PRECISION). The two axes are independent: Apollo 11 is historical + illustrated (real events, drawn
paths), Voyager 1 current + observed, Artemis III planned + modelled, a Moon base in 2050 hypothetical + illustrative.

Everything here is deterministic: the reference "now" of a project is a fixed date (the plan row's date, or the date the
project first checked its plan), never the clock of the machine that renders."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

STATUSES = ("historical", "current", "planned", "projected", "hypothetical")
BASES = ("observed", "modelled", "illustrated", "illustrative")
PRECISIONS = ("second", "minute", "day", "month", "year")

# certainty, most certain first: a CSV may only move a beat DOWN this list (towards less certain), never up
CERTAINTY = {"historical": 0, "current": 0, "planned": 1, "projected": 2, "hypothetical": 3}
# the statuses the viewer must be told about on screen (a badge), and the words used
BADGE = {"planned": "PLANNED", "projected": "PROJECTED", "hypothetical": "HYPOTHETICAL"}
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


class TemporalError(ValueError):
    pass


def check_status(value: str, where: str) -> str:
    v = (value or "").strip().lower()
    if v not in STATUSES:
        raise TemporalError(f"{where}: status must be one of {', '.join(STATUSES)} (got {value!r})")
    return v


def check_basis(value: str, where: str) -> str:
    v = (value or "").strip().lower()
    if v not in BASES:
        raise TemporalError(f"{where}: basis must be one of {', '.join(BASES)} (got {value!r})")
    return v


def check_precision(value: str, where: str) -> str:
    v = (value or "").strip().lower()
    if v not in PRECISIONS:
        raise TemporalError(f"{where}: precision must be one of {', '.join(PRECISIONS)} (got {value!r})")
    return v


def least_certain(statuses: Iterable[Optional[str]]) -> Optional[str]:
    """The least certain of some statuses (None when there are none): a beat showing planned and historical things is planned."""
    known = [s for s in statuses if s]
    return max(known, key=lambda s: (CERTAINTY[s], STATUSES.index(s))) if known else None


def parse_iso(s: str) -> datetime:
    t = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reference_date(value: str) -> str:
    """A reference "now" (a plan row date or a saved project date) as ISO UTC; a bare date means its noon UTC."""
    v = (value or "").strip()
    if not v:
        raise TemporalError("no reference date")
    if len(v) == 10:                                        # 2026-10-08
        v += "T12:00:00Z"
    try:
        return iso(parse_iso(v))
    except ValueError:
        raise TemporalError(f"the reference date must be an ISO date such as 2026-10-08 (got {value!r})") from None


def show_date(utc: str, precision: str = "minute", net: bool = False) -> str:
    """A date as the viewer should read it: only as precise as it is known ("NET SEP 2027", "2050", "1969-07-20 20:17 UTC")."""
    t = parse_iso(utc)
    if precision == "year":
        s = f"{t.year}"
    elif precision == "month":
        s = f"{MONTHS[t.month - 1]} {t.year}"
    elif precision == "day":
        s = f"{t.day} {MONTHS[t.month - 1]} {t.year}"
    elif precision == "second":
        s = t.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        s = t.strftime("%Y-%m-%d %H:%M UTC")
    return f"NET {s}" if net else s


def year_of(utc: str) -> int:
    return parse_iso(utc).year


def iso_days(a: str, b: str) -> float:
    """Days from date a to date b (negative when b is earlier)."""
    return (parse_iso(b) - parse_iso(a)).total_seconds() / 86400.0
