"""weather_layers.csv: the weather layers of a Weather video, next to its Hybrid beat CSV (beats.csv).

The beat CSV stays an ordinary Hybrid beat CSV (hybrid.beat_csv reads it unchanged and rejects anything it does not know), so
the weather layers live here, in Weather's own file. One row per layer:

    beat         the beat (its id in beats.csv) the layer belongs to
    vo_anchor    the narrator's words it appears on (same matcher as Hybrid), or
    t            seconds into the narration
    id           a unique layer id
    type         temp_marker | forecast_strip | now_card | alert_area | satellite | source_line
    place        a city ('Dallas, TX') or, for alert_area, a state ('TX') or 'US'
    data_source  WHAT data, never the number:  nws:forecast@Dallas,TX#day1-5   nws:forecast@Dallas,TX#day1   nws:obs@Dallas,TX
                 nws:alerts@TX   gibs:geocolor@latest
    hold         seconds it stays (else until)
    until        beat_end (default) | end | a time in seconds
    extra        JSON for rarely used options

Every problem names its row as a spreadsheet numbers it (the header is row 1)."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .cities import US_STATES, find_city

COLUMNS = ("beat", "vo_anchor", "t", "id", "type", "place", "data_source", "hold", "until", "extra")
TYPES = ("temp_marker", "forecast_strip", "now_card", "alert_area", "satellite", "source_line")
EXTRA_KEYS = {
    "temp_marker": {"kind", "side"},             # kind: high | low | now (default high for forecasts, now for obs)
    "forecast_strip": {"title"},
    "now_card": {"anchor"},
    "alert_area": {"events", "opacity", "legend"},
    "satellite": {"opacity"},
    "source_line": {"text", "tz"},
}
DATA_SOURCE = re.compile(r"^(?P<provider>[a-z]+):(?P<product>[a-z_]+)@(?P<target>[^#]+?)(?:#(?P<selector>.+))?$")
DAY_RANGE = re.compile(r"^day(?P<a>[1-7])(?:-(?P<b>[1-7]))?$")


class SidecarError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class DataSource:
    provider: str
    product: str
    target: str
    selector: str = ""

    @property
    def text(self) -> str:
        return f"{self.provider}:{self.product}@{self.target}" + (f"#{self.selector}" if self.selector else "")

    def days(self) -> "tuple[int, int]":
        m = DAY_RANGE.match(self.selector or "day1")
        if not m:
            raise ValueError(f"{self.text}: the forecast day must be #day1 .. #day7 or a range like #day1-5")
        a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
        if b < a:
            raise ValueError(f"{self.text}: the day range must go forward (#day{a}-{b})")
        return a, b


def known_types() -> tuple:
    """The phase-1 types and every type registered in weather/layers/."""
    from .layers import discover

    return TYPES + tuple(sorted(t for t in discover() if t not in TYPES))


def extra_keys(typ: str) -> set:
    if typ in EXTRA_KEYS:
        return EXTRA_KEYS[typ]
    from .layers import get

    lt = get(typ)
    return set(lt.extra_keys) if lt else set()


def parse_data_source(text: str) -> DataSource:
    m = DATA_SOURCE.match(str(text).strip())
    if not m:
        raise ValueError(f"data_source {text!r} must look like nws:forecast@Dallas,TX#day1-5 (provider:product@target#selector)")
    return DataSource(m.group("provider"), m.group("product"), m.group("target").strip(), (m.group("selector") or "").strip())


@dataclass
class WxRow:
    line: int
    beat: str
    id: str
    type: str
    vo_anchor: str = ""
    t: Optional[float] = None
    place: str = ""
    data_source: Optional[DataSource] = None
    hold: Optional[float] = None
    until: Any = "beat_end"
    extra: Dict[str, Any] = field(default_factory=dict)


def _check(row: WxRow) -> None:
    """Raises ValueError for a row whose type, place and data_source do not fit together."""
    ds = row.data_source
    if row.type not in TYPES:   # a type registered in weather/layers/
        from .layers import get

        lt = get(row.type)
        if not lt.products:
            if ds is not None:
                raise ValueError(f"{row.type} takes no data_source")
        elif ds is None or (ds.provider, ds.product) not in [tuple(p) for p in lt.products]:
            raise ValueError(f"{row.type} takes {' or '.join(f'{a}:{b}@...' for a, b in lt.products)} (got {ds.text if ds else 'nothing'})")
        if lt.needs_place and not row.place:
            raise ValueError(f"{row.type} needs a place")
        if lt.check is not None:
            lt.check(row)
        return
    want = {
        "temp_marker": ("nws", ("forecast", "obs")), "forecast_strip": ("nws", ("forecast",)), "now_card": ("nws", ("obs",)),
        "alert_area": ("nws", ("alerts",)), "satellite": ("gibs", ("geocolor",)),
    }.get(row.type)
    if row.type == "source_line":
        if ds is not None:
            raise ValueError("source_line takes no data_source: it names the sources of the layers on screen with it")
        return
    if ds is None:
        raise ValueError(f"{row.type} needs a data_source")
    if (ds.provider, ds.product) not in [(want[0], p) for p in want[1]]:
        raise ValueError(f"{row.type} takes {' or '.join(f'{want[0]}:{p}@...' for p in want[1])} (got {ds.text})")
    if ds.provider == "nws" and ds.product in ("forecast", "obs"):
        find_city(ds.target)  # KeyError names the known cities
        if row.place and find_city(row.place).key != find_city(ds.target).key:
            raise ValueError(f"place {row.place!r} is not the city of the data_source ({ds.target})")
    if ds.product == "forecast":
        a, b = ds.days()
        if row.type == "forecast_strip" and not 3 <= b - a + 1 <= 7:
            raise ValueError(f"a forecast_strip shows 3 to 7 days (got #day{a}-{b})")
        if row.type == "temp_marker" and a != b:
            raise ValueError("a temp_marker shows one day (#day1, #day2 ...)")
    if ds.product == "alerts" and ds.target != "US" and ds.target.upper() not in US_STATES:
        raise ValueError(f"nws:alerts@ takes a state (TX) or US (got {ds.target!r})")
    if ds.product == "geocolor" and ds.target != "latest" and not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d0Z", ds.target):
        raise ValueError("gibs:geocolor@ takes latest or a UTC time on a 10-minute step (2026-10-13T12:40Z)")


def parse_sidecar(text: str) -> List[WxRow]:
    rows = list(csv.reader(io.StringIO(str(text).lstrip("\ufeff"))))
    if not rows:
        raise SidecarError(["weather_layers.csv is empty: the first row must be the header " + ",".join(COLUMNS)])
    head = [c.strip().lower() for c in rows[0]]
    problems = [f"unknown column {c!r} (columns: {', '.join(COLUMNS)})" for c in head if c and c not in COLUMNS]
    for need in ("beat", "id", "type"):
        if need not in head:
            problems.append(f"the header has no {need} column")
    if problems:
        raise SidecarError(problems)
    out: List[WxRow] = []
    ids: Dict[str, int] = {}
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        r = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        at = f"weather_layers.csv row {n}"
        try:
            typ = r.get("type", "").lower()
            if typ not in known_types():
                raise ValueError(f"unknown type {typ!r} (use {', '.join(known_types())})")
            if not r.get("id"):
                raise ValueError("needs an id")
            if not r.get("beat"):
                raise ValueError("needs the beat it belongs to (its id in beats.csv)")
            if r["id"] in ids:
                raise ValueError(f"duplicate id {r['id']!r} (also row {ids[r['id']]})")
            if not r.get("vo_anchor") and not r.get("t"):
                raise ValueError("needs vo_anchor (the narrator's words it appears on) or t (seconds)")
            extra = json.loads(r.get("extra") or "{}")
            if not isinstance(extra, dict):
                raise ValueError("extra must be a JSON object")
            bad = sorted(set(extra) - extra_keys(typ))
            if bad:
                raise ValueError(f"extra has {', '.join(bad)}, which {typ} does not use (it takes {', '.join(sorted(extra_keys(typ))) or 'nothing'})")
            until: Any = (r.get("until") or "beat_end").lower()
            if until not in ("beat_end", "end"):
                until = float(until)
            row = WxRow(line=n, beat=r["beat"], id=r["id"], type=typ, vo_anchor=r.get("vo_anchor", ""),
                        t=float(r["t"]) if r.get("t") else None, place=r.get("place", ""),
                        data_source=parse_data_source(r["data_source"]) if r.get("data_source") else None,
                        hold=float(r["hold"]) if r.get("hold") else None, until=until, extra=extra)
            if row.hold is not None and row.hold <= 0:
                raise ValueError("hold must be more than 0 seconds")
            _check(row)
        except json.JSONDecodeError as exc:
            problems.append(f"{at}: the extra cell is not valid JSON ({exc})")
            continue
        except (ValueError, KeyError) as exc:
            problems.append(f"{at}: {str(exc).strip(chr(39)) if isinstance(exc, KeyError) else exc}")
            continue
        ids[row.id] = n
        out.append(row)
    if problems:
        raise SidecarError(problems)
    if not out:
        raise SidecarError(["weather_layers.csv has no layers"])
    return out


def rows_to_csv(rows: List[WxRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([r.beat, r.vo_anchor, "" if r.t is None else r.t, r.id, r.type, r.place, r.data_source.text if r.data_source else "",
                    "" if r.hold is None else r.hold, r.until, json.dumps(r.extra) if r.extra else ""])
    return buf.getvalue()
