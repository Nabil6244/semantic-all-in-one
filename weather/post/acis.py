"""NOAA Regional Climate Centers' Applied Climate Information System (RCC-ACIS, https://data.rcc-acis.org/): observed daily station
data, and where a day ranks in a station's period of record.

ACIS daily values are strings: a number ("16.07"), "T" (a trace: some, too little to measure — counted as 0 in a sum), "M"
(missing), "S" (the amount is in a later multi-day value) or a number ending in "A" (an accumulation over several days). A total
with missing days is shown with how many are missing; it is never filled in.

Places: "Houston, TX" (a city in PLACES: its airport station for totals, its long "threaded" record for records) or an ACIS
station id ("IAH", "HOU", "IAHthr 9"). Threaded records ("IAHthr 9", "Houston Area") join a city's stations into one record
reaching back to the 1800s; they carry no location, so the map position comes from the airport station of the same code."""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

BASE = "https://data.rcc-acis.org"
CREDIT = "Observed station data: NOAA Regional Climate Centers (RCC-ACIS)."
SOURCE_TEXT = "Observed: NOAA RCC-ACIS station data"
TOP_N = 10

# city -> (station for totals, threaded record for records)
PLACES = {
    "houston,TX": ("IAH", "IAHthr 9"), "galveston,TX": ("GLS", "GLSthr 9"), "beaumont,TX": ("BPT", "BPTthr 9"),
    "port arthur,TX": ("BPT", "BPTthr 9"), "corpus christi,TX": ("CRP", "CRPthr 9"), "victoria,TX": ("VCT", "VCTthr 9"),
    "lake charles,LA": ("LCH", "LCHthr 9"), "dallas,TX": ("DFW", "DFWthr 9"), "austin,TX": ("AUS", "AUSthr 9"),
    "college station,TX": ("CLL", "CLLthr 9"), "new orleans,LA": ("MSY", "MSYthr 9"), "miami,FL": ("MIA", "MIAthr 9"),
    "tampa,FL": ("TPA", "TPAthr 9"), "chicago,IL": ("ORD", "ORDthr 9"), "new york,NY": ("NYC", "NYCthr 9"),
    "los angeles,CA": ("LAX", "LAXthr 9"), "phoenix,AZ": ("PHX", "PHXthr 9"), "las vegas,NV": ("LAS", "LASthr 9"),
    "denver,CO": ("DEN", "DENthr 9"), "atlanta,GA": ("ATL", "ATLthr 9"), "nashville,TN": ("BNA", "BNAthr 9"),
    "asheville,NC": ("AVL", "AVLthr 9"), "sacramento,CA": ("SAC", "SACthr 9"), "seattle,WA": ("SEA", "SEAthr 9"),
    "portland,OR": ("PDX", "PDXthr 9"),
}
# short on-screen names for stations whose ACIS names are long
LABELS = {
    "IAH": "HOUSTON (IAH)", "HOU": "HOUSTON HOBBY", "GLS": "GALVESTON", "BPT": "PORT ARTHUR", "LCH": "LAKE CHARLES",
    "CRP": "CORPUS CHRISTI", "VCT": "VICTORIA", "SGR": "SUGAR LAND", "DWH": "HOUSTON NORTH (DWH)", "CXO": "CONROE",
    "LBX": "ANGLETON", "EFD": "HOUSTON ELLINGTON", "DFW": "DALLAS-FORT WORTH", "MSY": "NEW ORLEANS", "NYC": "NEW YORK (CENTRAL PARK)",
}
ELEMS = {"pcpn": ("IN", "wettest", "max"), "snow": ("IN", "snowiest", "max"), "maxt": ("°F", "hottest", "max"),
         "mint": ("°F", "coldest", "min")}
ELEM_RE = re.compile(r"^(pcpn|snow|maxt|mint)(?::(all|date))?$")


def norm_place(text: str) -> str:
    name, _, state = str(text).partition(",")
    return f"{' '.join(name.split()).lower()},{state.strip().upper()}"


def is_city(target: str) -> bool:
    return "," in target


def station_for(target: str, *, record: bool = False) -> str:
    """'Houston, TX' -> 'IAH' ('IAHthr 9' for records); an ACIS id is returned as written."""
    t = str(target).strip()
    if is_city(t):
        hit = PLACES.get(norm_place(t))
        if hit is None:
            known = ", ".join(sorted(k.split(",")[0].title() + ", " + k.split(",")[1] for k in PLACES))
            raise ValueError(f"no ACIS station is known for {t!r} (known: {known}); or name the station id, e.g. IAH")
        return hit[1] if record else hit[0]
    if not re.fullmatch(r"[A-Za-z0-9]{3,11}(thr 9| \d{1,2})?", t):
        raise ValueError(f"{t!r} is neither 'City, ST' nor an ACIS station id (IAH, 414300, IAHthr 9)")
    return t


def base_sid(sid: str) -> str:
    """'IAHthr 9' -> 'IAH' (the station whose location a threaded record uses)."""
    return sid.split("thr")[0] if "thr" in sid else sid.split(" ")[0]


def label_for(sid: str, name: str) -> str:
    """On-screen name of a station: LABELS, else its ACIS name without airport words ('HOUSTON AREA')."""
    b = base_sid(sid).upper()
    if "thr" not in sid and b in LABELS:
        return LABELS[b]
    n = re.sub(r"\b(INTL|INTERNATIONAL|REGIONAL|REGL|MUNICIPAL|MUNI|MEMORIAL|MEM|AIRPORT|AP|ARPT|FIELD)\b", "", str(name).upper())
    return " ".join(n.split()) or b


def url(endpoint: str, params: Dict[str, Any]) -> str:
    return f"{BASE}/{endpoint}?params=" + urllib.parse.quote(json.dumps(params, separators=(",", ":")))


def daily_url(sids: Sequence[str], a: date, b: date, elem: str = "pcpn") -> str:
    return url("MultiStnData", {"sids": ",".join(sids), "sdate": a.isoformat(), "edate": b.isoformat(), "elems": [{"name": elem}],
                                "meta": ["name", "sids", "ll"]})


def meta_url(sid: str, elem: str = "pcpn") -> str:
    return url("StnMeta", {"sids": sid, "elems": elem, "meta": ["name", "sids", "ll", "valid_daterange"]})


def rank_url(sid: str, elem: str, d: date, scope: str = "all", n: int = TOP_N) -> str:
    """The n highest (lowest for mint) daily values of the period of record up to and including d (scope 'date': only that
    calendar date of each year)."""
    reduce = ELEMS[elem][2]
    e: Dict[str, Any] = {"name": elem, "smry": {"reduce": reduce, "add": "date", "n": n}, "smry_only": 1}
    sdate = "por"
    if scope == "date":
        e.update(interval=[1, 0, 0], duration="dly")
        sdate = f"1850-{d.month:02d}-{d.day:02d}"
    return url("StnData", {"sid": sid, "sdate": sdate, "edate": d.isoformat(), "elems": [e], "meta": ["name", "sids", "valid_daterange"]})


def day_url(sid: str, elem: str, d: date) -> str:
    return url("StnData", {"sid": sid, "sdate": d.isoformat(), "edate": d.isoformat(), "elems": [{"name": elem}],
                           "meta": ["name", "sids", "valid_daterange"]})


# ---- values ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Value:
    raw: str
    amount: Optional[float]  # None = missing
    trace: bool = False
    accumulated: bool = False  # a multi-day amount ("1.20A"), or part of one ("S")


def parse_value(raw: Any) -> Value:
    s = str(raw).strip()
    if s in ("M", "", "-"):
        return Value(s, None)
    if s == "T":
        return Value(s, 0.0, trace=True)
    if s == "S":
        return Value(s, 0.0, accumulated=True)
    acc = s.endswith("A")
    try:
        return Value(s, float(s.rstrip("A")), accumulated=acc)
    except ValueError:
        raise ValueError(f"ACIS value {s!r} is not a number, T, M, S or an accumulation") from None


@dataclass
class Total:
    amount: float
    days: int
    missing: List[str]  # dates without a value
    trace_days: int
    accumulated: bool

    @property
    def complete(self) -> bool:
        return not self.missing


def total(values: Sequence[Tuple[str, Any]]) -> Total:
    """Sum of [(date, raw)] daily values: traces count 0, missing days are listed (the total is then a lower bound)."""
    amt, missing, traces, acc = 0.0, [], 0, False
    for d, raw in values:
        v = parse_value(raw)
        if v.amount is None:
            missing.append(d)
            continue
        amt += v.amount
        traces += v.trace
        acc = acc or v.accumulated
    return Total(round(amt, 2), len(values), missing, traces, acc)


def peak_day(values: Sequence[Tuple[str, Any]]) -> Optional[Tuple[str, float]]:
    """(date, amount) of the wettest single day (an accumulation is not one day's rain, so it is skipped)."""
    best = None
    for d, raw in values:
        v = parse_value(raw)
        if v.amount is None or v.accumulated:
            continue
        if best is None or v.amount > best[1]:
            best = (d, v.amount)
    return best


def parse_multi(text: str, sids: Sequence[str], a: date, b: date) -> List[Dict[str, Any]]:
    """MultiStnData answer -> one entry per requested station, in the order asked: {sid, name, ll, values: [[date, raw]]}."""
    from .fmt import days_between

    d = json.loads(text)
    if "error" in d:
        raise ValueError(f"ACIS answered: {d['error']}")
    dates = [x.isoformat() for x in days_between(a, b)]
    found = {}
    for st in d.get("data") or []:
        meta = st.get("meta") or {}
        ids = {s.split(" ")[0].upper() for s in meta.get("sids") or []} | {s.upper() for s in meta.get("sids") or []}
        for sid in sids:
            if sid.upper() in ids or base_sid(sid).upper() in ids and "thr" not in sid:
                vals = [row[0] if isinstance(row, list) else row for row in st.get("data") or []]
                if len(vals) != len(dates):
                    raise ValueError(f"ACIS sent {len(vals)} days for {sid}, expected {len(dates)}")
                found[sid] = {"sid": sid, "name": meta.get("name", sid), "ll": meta.get("ll"), "values": [[x, v] for x, v in zip(dates, vals)]}
    missing = [s for s in sids if s not in found]
    if missing:
        raise ValueError(f"ACIS has no data for {', '.join(missing)} between {a} and {b}")
    return [found[s] for s in sids]


def parse_meta(text: str, sid: str) -> Dict[str, Any]:
    d = json.loads(text)
    rows = d.get("meta") or []
    if not rows:
        raise ValueError(f"ACIS knows no station {sid!r}")
    m = rows[0]
    rng = (m.get("valid_daterange") or [[None, None]])[0] or [None, None]
    return {"sid": sid, "name": m.get("name", sid), "ll": m.get("ll"), "por_start": rng[0] if rng else None, "por_end": rng[1] if len(rng) > 1 else None}


# ---- records ----------------------------------------------------------------------------------------------------------------

@dataclass
class Ranking:
    elem: str
    day: str
    value: float
    rank: Optional[int]  # None = not among the top n
    tied: bool
    record: Tuple[float, str]  # the station's #1 other than this day: (value, date)
    top: List[Tuple[float, str]]
    por_start: str
    station: str
    n: int


def parse_rank(text: str) -> Tuple[List[Tuple[float, str]], Dict[str, Any]]:
    d = json.loads(text)
    if "error" in d:
        raise ValueError(f"ACIS answered: {d['error']}")
    rows = (d.get("smry") or [[]])[0]
    top = []
    for raw, when in rows:
        v = parse_value(raw)
        if v.amount is not None:
            top.append((v.amount, when))
    meta = d.get("meta") or {}
    rng = (meta.get("valid_daterange") or [[None]])[0] or [None]
    return top, {"name": meta.get("name", ""), "por_start": rng[0]}


def parse_day(text: str) -> Value:
    d = json.loads(text)
    if "error" in d:
        raise ValueError(f"ACIS answered: {d['error']}")
    rows = d.get("data") or []
    if not rows:
        raise ValueError("ACIS sent no value for that day")
    return parse_value(rows[0][1])


def rank_day(elem: str, day_iso: str, value: float, top: List[Tuple[float, str]], *, station: str, por_start: str, n: int = TOP_N) -> Ranking:
    """Where `value` on `day_iso` stands among the period-of-record extremes `top` (highest first; lowest first for mint)."""
    lower = ELEMS[elem][2] == "min"
    others = [(v, d) for v, d in top if d != day_iso]
    if not others:
        raise ValueError(f"ACIS sent no earlier values for {station} to compare {day_iso} with")
    beats = (lambda v: v < value) if lower else (lambda v: v > value)
    ahead = sum(1 for v, _ in others if beats(v))
    tied = any(abs(v - value) < 1e-9 for v, _ in others)
    full = len(top) >= n
    in_list = any(d == day_iso for _, d in top) or not full   # top runs to the day itself: absent = below the n-th
    rank = ahead + 1 if in_list else None
    return Ranking(elem, day_iso, value, rank, tied, others[0], top, por_start, station, n)


def headline(r: Ranking, scope: str = "all") -> str:
    """'WETTEST DAY ON RECORD', '3RD WETTEST DAY ON RECORD', 'TIED: HOTTEST DAY ON RECORD', 'WETTEST AUG 27 ON RECORD'."""
    from .fmt import day, ordinal, short

    word = ELEMS[r.elem][1].upper()
    what = f"{short(day(r.day))}" if scope == "date" else "DAY"
    if r.elem == "mint" and scope != "date":
        what = "MORNING"
    if r.rank is None:
        raise ValueError(f"{r.day} is not among the {r.n} {ELEMS[r.elem][1]} days on record at {r.station}: leave this record out")
    head = f"{word} {what} ON RECORD" if r.rank == 1 else f"{ordinal(r.rank)} {word} {what} ON RECORD"
    return f"TIED: {head}" if r.tied else head


def amount_text(elem: str, v: float) -> str:
    return f"{round(v)}°F" if elem in ("maxt", "mint") else f"{v:.2f} IN"
