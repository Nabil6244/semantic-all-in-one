"""Dates and numbers as a post-event report shows them ('AUG 27', 'AUG 25–SEP 1', '16.07 IN')."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Tuple

MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
DATE_RANGE = re.compile(r"^(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)$")


def day(text: str) -> date:
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{text!r} is not a date (write it as 2017-08-27)") from None


def date_range(text: str) -> Tuple[date, date]:
    """'2017-08-25..2017-08-30' -> (date, date); the range must go forward and be at most 60 days."""
    m = DATE_RANGE.match(str(text).strip())
    if not m:
        raise ValueError(f"{text!r} must be a date range like 2017-08-25..2017-08-30")
    a, b = day(m.group(1)), day(m.group(2))
    if b < a:
        raise ValueError(f"the date range {text} goes backwards")
    if (b - a).days > 60:
        raise ValueError(f"the date range {text} is longer than 60 days")
    return a, b


def days_between(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def short(d: date, year: bool = False) -> str:
    """'AUG 27' (or 'AUG 27, 2017')."""
    return f"{MONTHS[d.month - 1]} {d.day}" + (f", {d.year}" if year else "")


def span(a: date, b: date, year: bool = False) -> str:
    """'AUG 25–30', 'AUG 25–SEP 1' (en dash), with ', 2017' when asked."""
    if a == b:
        return short(a, year)
    tail = str(b.day) if (a.month, a.year) == (b.month, b.year) else short(b)
    return f"{short(a)}–{tail}" + (f", {b.year}" if year else "")


def inches(v: float, decimals: int = 2) -> str:
    return f"{v:.{decimals}f} IN"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "TH"
    else:
        suf = {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return f"{n}{suf}"


def no_digits(text: str, what: str) -> str:
    """Author-written labels may not carry numbers: every number on screen comes from data."""
    if re.search(r"\d", str(text)):
        raise ValueError(f"{what} {text!r} has a number in it; numbers on screen come from the data, so write words only")
    return str(text)


def named(fn):
    """Wrap a layer hook so a ValueError names its row ('weather_layers.csv row 7 (iah_total): ...')."""
    import functools

    @functools.wraps(fn)
    def run(row, *args, **kw):
        try:
            return fn(row, *args, **kw)
        except (ValueError, KeyError) as exc:
            msg = str(exc).strip("'\"") if isinstance(exc, KeyError) else str(exc)
            if msg.startswith("weather_layers.csv row"):
                raise
            raise ValueError(f"weather_layers.csv row {row.line} ({row.id}): {msg}") from exc
    return run


def amount(v: float) -> str:
    """41.90 -> '41.9', 3.0 -> '3.0', 12.07 -> '12.07' (a gauge reading as written, without a trailing zero)."""
    s = f"{v:.2f}"
    return s[:-1] if s.endswith("0") else s
