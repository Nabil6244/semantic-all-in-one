"""NHC's best track (HURDAT2, https://www.nhc.noaa.gov/data/hurdat/): the final, reviewed record of every Atlantic and eastern
Pacific storm, six-hourly plus special times. A row whose record identifier is "L" is a landfall; only those are called
landfalls (the working ATCF best track does not mark them).

Wind is in knots; on screen it is mph rounded to the nearest 5, as the NHC writes it, with the Saffir-Simpson category."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

INDEX = "https://www.nhc.noaa.gov/data/hurdat/"
CREDIT = "Storm track: NOAA National Hurricane Center best track (HURDAT2)."
STORM_ID = re.compile(r"^(AL|EP|CP)(\d\d)(\d{4})$")


def check_id(storm: str) -> str:
    s = str(storm).strip().upper()
    if not STORM_ID.match(s):
        raise ValueError(f"{storm!r} is not an NHC storm id (basin, number, year: AL092017)")
    return s


def latest_file(index_html: str, basin: str = "AL") -> str:
    """The newest HURDAT2 file named in the NHC folder listing ('hurdat2-1851-2025-092326.txt'; eastern Pacific: '-nepac-')."""
    pat = r"hurdat2-nepac-1949-(\d{4})-(\d{6,8})\.txt" if basin in ("EP", "CP") else r"hurdat2-1851-(\d{4})-(\d{6,8})\.txt"
    best = None
    for m in re.finditer(pat, index_html):
        stamp = m.group(2)
        mm, dd, yy = stamp[:2], stamp[2:4], stamp[4:]
        key = (int(m.group(1)), int(yy if len(yy) == 4 else "20" + yy), int(mm), int(dd))
        if best is None or key > best[0]:
            best = (key, m.group(0))
    if best is None:
        raise ValueError("the NHC HURDAT2 folder lists no best-track file")
    return INDEX + best[1]


@dataclass
class Fix:
    time: datetime
    record: str  # "L" landfall, "" otherwise (others: C, G, I, P, R, S, T, W)
    status: str  # HU, TS, TD, EX ...
    lat: float
    lon: float
    wind_kt: int
    pressure_mb: Optional[int]


def storm_block(text: str, storm: str) -> List[str]:
    """The lines of one storm (its header first) from a whole HURDAT2 file."""
    storm = check_id(storm)
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(storm + ","):
            n = int(ln.split(",")[2])
            return lines[i:i + 1 + n]
    raise ValueError(f"{storm} is not in the NHC best track (it may be too recent: the file is updated each spring)")


def parse_block(block: List[str]) -> "tuple[str, List[Fix]]":
    name = block[0].split(",")[1].strip()
    fixes = []
    for ln in block[1:]:
        p = [x.strip() for x in ln.split(",")]
        t = datetime.strptime(p[0] + p[1], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        lat = float(p[4][:-1]) * (1 if p[4].endswith("N") else -1)
        lon = float(p[5][:-1]) * (-1 if p[5].endswith("W") else 1)
        pr = int(p[7]) if p[7] and int(p[7]) > 0 else None
        fixes.append(Fix(t, p[2], p[3], lat, lon, int(p[6]), pr))
    return name, fixes


def mph(kt: int) -> int:
    """Knots -> mph rounded to the nearest 5 (115 kt -> 130 mph), as the NHC states it."""
    return int(5 * round(kt * 1.15078 / 5))


def category(kt: int, status: str) -> str:
    """'CATEGORY 4 HURRICANE', 'TROPICAL STORM', 'TROPICAL DEPRESSION' (Saffir-Simpson, by sustained wind in knots)."""
    if status == "HU" or kt >= 64:
        cat = 5 if kt >= 137 else 4 if kt >= 113 else 3 if kt >= 96 else 2 if kt >= 83 else 1
        return f"CATEGORY {cat} HURRICANE"
    if status in ("TS", "SS") or kt >= 34:
        return "TROPICAL STORM"
    return "TROPICAL DEPRESSION"


def landfalls(fixes: List[Fix]) -> List[Fix]:
    return [f for f in fixes if f.record == "L"]
