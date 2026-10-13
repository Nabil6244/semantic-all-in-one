"""Observed rainfall over an area: NOAA's Multi-Radar Multi-Sensor (MRMS) 24-hour rainfall estimates, as archived by the Iowa
Environmental Mesonet (public domain) since 2015: one 8-bit PNG per hour for the whole US with a world file
(https://mesonet.agron.iastate.edu/archive/data/YYYY/MM/DD/GIS/mrms/p24h_YYYYMMDDHHMI.png, 0.01 degree cells).

The PNG holds an index per cell, not a colour; IEM's own encoding (iem scripts/mrms/make_mrms_rasters.py, convert_to_image):
    0..99    0.25 mm steps   (0 to 24.75 mm)
    100..179 1.25 mm steps   (25 to 123.75 mm)
    180..254 5 mm steps      (125 mm and up; 254 = 495 mm or more: a lower bound)
    255      missing
Each index stands for a range (the value was cut down to its step), so a cell reads as the middle of its step; 254 reads as
its lower bound and the cell is counted as "at least". A multi-day total is the sum of the 24-hour grids ending 12 UTC (7 AM
CDT) on each day of the range; a cell missing on any day is left out (no data), never filled in.

Radar estimates are observations of a kind (radar, corrected with rain gauges), not station measurements: on screen they are
"MRMS radar estimate"."""

from __future__ import annotations

import base64
import hashlib
import struct
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ARCHIVE = "https://mesonet.agron.iastate.edu/archive/data"
CREDIT = "Rainfall estimates: NOAA MRMS (radar with gauge correction), archived by the Iowa Environmental Mesonet."
SOURCE_TEXT = "Rain map: NOAA MRMS radar estimate via IEM"
MM_PER_IN = 25.4
MISSING = 255
CAP = 254
NODATA16 = 65535

# inches -> colour (light blue for an inch, through green, yellow, red, to purple and pink past 30 inches)
RAMP_IN: List[Tuple[float, str]] = [(1, "#A7D8F0"), (2, "#58B4E8"), (4, "#2F78D0"), (6, "#2FA65A"), (8, "#8CCB3C"), (10, "#F2E03A"),
                                     (15, "#F29A2E"), (20, "#E2402A"), (25, "#B5214A"), (30, "#8A2FB0"), (40, "#D58CF0")]


def png_url(ending: date, hour: int = 12, hours: int = 24) -> str:
    stamp = f"{ending:%Y%m%d}{hour:02d}00"
    return f"{ARCHIVE}/{ending:%Y/%m/%d}/GIS/mrms/p{hours}h_{stamp}.png"


def world_url(png: str) -> str:
    return png[:-4] + ".wld"


def day_endings(a: date, b: date) -> List[date]:
    """The 24-hour grids that make the total from a 12 UTC to b 12 UTC: those ending on a+1 .. b."""
    if b <= a:
        raise ValueError("a rain total runs from one day's 7 AM CDT (12 UTC) to a LATER day's: give two different dates")
    return [a + timedelta(days=k) for k in range(1, (b - a).days + 1)]


def index_to_mm(idx: np.ndarray) -> np.ndarray:
    """Cell index -> millimetres (middle of the step; 254 -> its lower bound 495; 255 -> NaN)."""
    i = idx.astype(np.float64)
    mm = np.where(i < 100, i * 0.25 + 0.125, np.where(i < 180, 25 + (i - 100) * 1.25 + 0.625, 125 + (i - 180) * 5 + 2.5))
    mm = np.where(idx == 0, 0.0, mm)
    mm = np.where(idx == CAP, 495.0, mm)
    return np.where(idx == MISSING, np.nan, mm)


def parse_world(text: str) -> Tuple[float, float, float, float]:
    """World file -> (x cell size, y cell size (negative), lon of the first cell's centre, lat of the first cell's centre)."""
    a, _d, _b, e, c, f = [float(x) for x in str(text).split()[:6]]
    return a, e, c, f


# ---- an 8-bit PNG, decoded with the standard library and numpy -------------------------------------------------------------

def _paeth_row(cur: np.ndarray, prev: np.ndarray) -> np.ndarray:
    out = cur.astype(np.int32).copy()
    p = prev.astype(np.int32)
    for k in range(len(out)):
        a = out[k - 1] if k else 0
        b, c = p[k], (p[k - 1] if k else 0)
        pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
        out[k] = (out[k] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
    return out.astype(np.uint8)


def decode_png_rows(data: bytes, r0: int, r1: int) -> Tuple[np.ndarray, int, int]:
    """Rows r0..r1-1 of an 8-bit one-channel PNG (palette or grey) as a uint8 array; plus the full width and height."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, width = 8, [], 0
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            width, height, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (0, 3) or interlace:
                raise ValueError(f"the MRMS PNG is not an 8-bit one-channel picture (depth {depth}, colour type {ctype})")
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + n
    stride = width + 1
    r1 = min(r1, height)
    need = r1 * stride
    dec = zlib.decompressobj()
    buf = dec.decompress(b"".join(idat), need)   # only as far as the last row asked for
    if len(buf) < need:
        raise ValueError("the PNG ends before its last row")
    raw = np.frombuffer(buf[:need], dtype=np.uint8).reshape(r1, stride)
    out = np.zeros((max(0, r1 - r0), width), dtype=np.uint8)
    prev = np.zeros(width, dtype=np.uint8)
    for r in range(r1):
        f, cur = raw[r, 0], raw[r, 1:]
        if f == 0:
            row = cur
        elif f == 1:
            row = (np.cumsum(cur, dtype=np.uint64) & 255).astype(np.uint8)
        elif f == 2:
            row = ((cur.astype(np.uint16) + prev) & 255).astype(np.uint8)
        elif f == 3:
            row = cur.astype(np.int32).copy()
            for k in range(width):
                row[k] = (row[k] + ((row[k - 1] if k else 0) + int(prev[k])) // 2) & 255
            row = row.astype(np.uint8)
        elif f == 4:
            row = _paeth_row(cur, prev)
        else:
            raise ValueError(f"PNG row {r} has an unknown filter {f}")
        prev = row
        if r >= r0:
            out[r - r0] = row
    return out, width, height


@dataclass
class Window:
    """The cells of the PNG inside bbox: rows r0..r1-1, cols c0..c1-1, and the bbox they really cover (cell edges)."""
    r0: int
    r1: int
    c0: int
    c1: int
    west: float
    south: float
    east: float
    north: float
    cell: float


def window(bbox: Sequence[float], world: Tuple[float, float, float, float], width: int = 7000, height: int = 3500) -> Window:
    w, s, e, n = bbox
    dx, dy, lon0, lat0 = world
    c0 = max(0, int(np.floor((w - lon0) / dx + 0.5)))
    c1 = min(width, int(np.ceil((e - lon0) / dx + 0.5)))
    r0 = max(0, int(np.floor((lat0 - n) / -dy + 0.5)))
    r1 = min(height, int(np.ceil((lat0 - s) / -dy + 0.5)))
    if c1 <= c0 or r1 <= r0:
        raise ValueError(f"the area {list(bbox)} is outside the MRMS grid")
    return Window(r0, r1, c0, c1, lon0 + (c0 - 0.5) * dx, lat0 + (r1 - 0.5) * dy, lon0 + (c1 - 0.5) * dx, lat0 - (r0 - 0.5) * -dy, dx)


def crop_mm(png: bytes, win: Window) -> np.ndarray:
    rows, _w, _h = decode_png_rows(png, win.r0, win.r1)
    return index_to_mm(rows[:, win.c0:win.c1])


@dataclass
class RainGrid:
    west: float
    south: float
    east: float
    north: float
    cell: float
    inches: np.ndarray  # rows north -> south; NaN = no data
    capped: int  # cells where a day reached the top of the encoding (the total there is "at least")
    capped_mask: Optional[np.ndarray] = None

    def to_dict(self) -> Dict:
        v = np.where(np.isnan(self.inches), NODATA16, np.clip(np.round(self.inches * 100), 0, NODATA16 - 1)).astype("<u2")
        return {"west": self.west, "south": self.south, "east": self.east, "north": self.north, "cell": self.cell, "rows": int(v.shape[0]),
                "cols": int(v.shape[1]), "capped": self.capped, "hundredths_z64": base64.b64encode(zlib.compress(v.tobytes(), 9)).decode("ascii"),
                "capped_z64": base64.b64encode(zlib.compress(np.packbits(self._mask()).tobytes(), 9)).decode("ascii")}

    def _mask(self) -> np.ndarray:
        return self.capped_mask if self.capped_mask is not None else np.zeros(self.inches.shape, dtype=bool)

    @staticmethod
    def from_dict(d: Dict) -> "RainGrid":
        v = np.frombuffer(zlib.decompress(base64.b64decode(d["hundredths_z64"])), dtype="<u2").reshape(d["rows"], d["cols"])
        inches = np.where(v == NODATA16, np.nan, v / 100.0)
        mask = None
        if d.get("capped_z64"):
            bits = np.unpackbits(np.frombuffer(zlib.decompress(base64.b64decode(d["capped_z64"])), dtype=np.uint8))
            mask = bits[: d["rows"] * d["cols"]].reshape(d["rows"], d["cols"]).astype(bool)
        return RainGrid(d["west"], d["south"], d["east"], d["north"], d["cell"], inches, int(d.get("capped", 0)), mask)

    def at(self, lon: float, lat: float) -> float:
        c = int((lon - self.west) / self.cell)
        r = int((self.north - lat) / self.cell)
        if 0 <= r < self.inches.shape[0] and 0 <= c < self.inches.shape[1]:
            return float(self.inches[r, c])
        return float("nan")

    def peak(self) -> Tuple[float, float, float, bool]:
        """(inches, lon, lat, at_least) of the wettest cell; at_least: a day there reached the top of the encoding."""
        if np.all(np.isnan(self.inches)):
            raise ValueError("the rain grid has no data")
        r, c = np.unravel_index(np.nanargmax(self.inches), self.inches.shape)
        return float(self.inches[r, c]), self.west + (c + 0.5) * self.cell, self.north - (r + 0.5) * self.cell, bool(self._mask()[r, c])

    def share_at_least(self, inches: float) -> float:
        ok = ~np.isnan(self.inches)
        return float(np.sum(ok & (self.inches >= inches)) / max(1, self.inches.size))


def sum_days(pngs: Sequence[bytes], world: Tuple[float, float, float, float], bbox: Sequence[float]) -> RainGrid:
    if not pngs:
        raise ValueError("no MRMS grids to add up")
    _rows, width, height = decode_png_rows(pngs[0], 0, 0)
    win = window(bbox, world, width, height)
    total, capped = None, None
    for png in pngs:
        idx = decode_png_rows(png, win.r0, win.r1)[0][:, win.c0:win.c1]
        mm = index_to_mm(idx)
        total = mm if total is None else total + mm   # NaN on any day stays NaN
        capped = (idx == CAP) if capped is None else (capped | (idx == CAP))
    capped = capped & ~np.isnan(total)
    return RainGrid(win.west, win.south, win.east, win.north, win.cell, total / MM_PER_IN, int(np.sum(capped)), capped)


def write_asc(grid: RainGrid, min_in: float, folder: Path) -> Path:
    """The grid as an ESRI ASCII grid for pakMap's value_overlay (cells under min_in are left empty: the map shows through).
    Named by its content, so the same grid is written once."""
    v = np.where(np.isnan(grid.inches) | (grid.inches < min_in), -9999.0, np.round(grid.inches, 2))
    rows, cols = v.shape
    head = f"ncols {cols}\nnrows {rows}\nxllcorner {grid.west:.6f}\nyllcorner {grid.south:.6f}\ncellsize {grid.cell:.6f}\nnodata_value -9999\n"
    body = "\n".join(" ".join("-9999" if x == -9999.0 else f"{x:.2f}" for x in row) for row in v) + "\n"
    text = head + body
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"mrms_{hashlib.sha1(text.encode()).hexdigest()[:16]}.asc"
    if not out.is_file():
        tmp = out.with_suffix(".tmp")
        tmp.write_text(text, encoding="ascii")
        tmp.replace(out)
    return out
