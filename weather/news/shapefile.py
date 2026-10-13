"""A small reader for ESRI shapefiles (.shp + .dbf), enough for the NHC and SPC GIS archives: points, polylines and polygons
in lon/lat, with their attribute rows. Standard library only (the app has no GIS package, and NHC ships its archive as zipped
shapefiles).

    shapes = read_zip(zip_bytes)                      # every layer in a zip: {"al092022-030_5day_pgn": Layer, ...}
    layer = shapes.find("_5day_pgn")                  # the layer whose name ends with that
    for rec in layer.records: rec.kind, rec.parts, rec.attrs

Shape types read: Point (1), PolyLine (3), Polygon (5), MultiPoint (8) and their Z/M variants (11, 13, 15, 18, 21, 23, 25, 28),
whose extra Z/M values are skipped. Polygons are returned as pakMap's MultiPolygon coordinates: outer rings (clockwise in a
shapefile) each start a polygon, and the holes that follow (counter-clockwise) join the polygon before them."""

from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

POINT, POLYLINE, POLYGON, MULTIPOINT = 1, 3, 5, 8
_BASE = {0: 0, 1: POINT, 3: POLYLINE, 5: POLYGON, 8: MULTIPOINT, 11: POINT, 13: POLYLINE, 15: POLYGON, 18: MULTIPOINT,
         21: POINT, 23: POLYLINE, 25: POLYGON, 28: MULTIPOINT}
KIND = {POINT: "point", POLYLINE: "line", POLYGON: "polygon", MULTIPOINT: "points", 0: "null"}


class ShapefileError(ValueError):
    pass


@dataclass
class Record:
    kind: str  # point | points | line | polygon | null
    parts: list  # point: [lon, lat]; points: [[lon, lat], ...]; line: [[[lon, lat], ...], ...] (parts); polygon: MultiPolygon coordinates
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Layer:
    name: str
    records: List[Record]
    fields: List[str] = field(default_factory=list)


class Layers(dict):
    def find(self, suffix: str) -> Layer:
        """The layer whose name ends with `suffix` (case-insensitive); ShapefileError names the layers there are."""
        hits = [v for k, v in self.items() if k.lower().endswith(suffix.lower())]
        if not hits:
            raise ShapefileError(f"no {suffix} layer in the archive (it has {', '.join(sorted(self)) or 'nothing'})")
        return hits[0]


def _ring_area(ring: Sequence[Sequence[float]]) -> float:
    """Signed area (shoelace): negative = clockwise, which a shapefile uses for outer rings."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, list(ring[1:]) + [ring[0]]):
        s += x1 * y2 - x2 * y1
    return s / 2


def rings_to_multipolygon(rings: List[list]) -> list:
    polys: list = []
    for ring in rings:
        if len(ring) < 3:
            continue
        if _ring_area(ring) <= 0 or not polys:   # clockwise (or the first ring): a new polygon
            polys.append([ring])
        else:   # counter-clockwise: a hole in the polygon before it
            polys[-1].append(ring)
    return polys


def read_shp(data: bytes) -> List[tuple]:
    """(kind, parts) for every record of a .shp file, in order."""
    if len(data) < 100:
        raise ShapefileError("the .shp file is shorter than its 100-byte header")
    code, = struct.unpack(">i", data[0:4])
    if code != 9994:
        raise ShapefileError(f"not a shapefile (file code {code}, expected 9994)")
    out = []
    pos = 100
    while pos + 8 <= len(data):
        _num, length = struct.unpack(">ii", data[pos:pos + 8])
        body = data[pos + 8: pos + 8 + 2 * length]
        pos += 8 + 2 * length
        if len(body) < 4:
            break
        st, = struct.unpack("<i", body[:4])
        base = _BASE.get(st)
        if base is None:
            raise ShapefileError(f"shape type {st} is not supported (points, lines and polygons only)")
        if base == 0:
            out.append(("null", None))
        elif base == POINT:
            x, y = struct.unpack("<2d", body[4:20])
            out.append(("point", [x, y]))
        elif base == MULTIPOINT:
            n, = struct.unpack("<i", body[36:40])
            pts = struct.unpack(f"<{2 * n}d", body[40:40 + 16 * n])
            out.append(("points", [[pts[2 * i], pts[2 * i + 1]] for i in range(n)]))
        else:
            nparts, npts = struct.unpack("<2i", body[36:44])
            starts = list(struct.unpack(f"<{nparts}i", body[44:44 + 4 * nparts])) + [npts]
            off = 44 + 4 * nparts
            xy = struct.unpack(f"<{2 * npts}d", body[off:off + 16 * npts])
            pts = [[xy[2 * i], xy[2 * i + 1]] for i in range(npts)]
            parts = [pts[starts[i]:starts[i + 1]] for i in range(nparts)]
            out.append(("line", parts) if base == POLYLINE else ("polygon", rings_to_multipolygon(parts)))
    return out


def read_dbf(data: bytes, encoding: str = "latin-1") -> "tuple[List[str], List[Dict[str, Any]]]":
    """(field names, rows) of a dBASE III table. Numbers become int/float (blank -> None); text is stripped."""
    if len(data) < 32:
        raise ShapefileError("the .dbf file is shorter than its header")
    nrec, hlen, rlen = struct.unpack("<IHH", data[4:12])
    fields = []
    pos = 32
    while pos < hlen - 1 and data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0", 1)[0].decode("ascii", "replace")
        ftype = chr(data[pos + 11])
        flen, fdec = data[pos + 16], data[pos + 17]
        fields.append((name, ftype, flen, fdec))
        pos += 32
    rows = []
    for i in range(nrec):
        rec = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        if not rec or rec[:1] == b"*":   # deleted
            continue
        off = 1
        row: Dict[str, Any] = {}
        for name, ftype, flen, fdec in fields:
            raw = rec[off:off + flen].decode(encoding, "replace").strip()
            off += flen
            if ftype in ("N", "F"):
                try:
                    row[name] = (int(raw) if fdec == 0 and "." not in raw else float(raw)) if raw and raw.strip("*") else None
                except ValueError:
                    row[name] = None
            elif ftype == "L":
                row[name] = raw.upper() in ("Y", "T") if raw and raw != "?" else None
            else:
                row[name] = raw
        rows.append(row)
    return [f[0] for f in fields], rows


def read_layer(name: str, shp: bytes, dbf: Optional[bytes]) -> Layer:
    shapes = read_shp(shp)
    names, rows = read_dbf(dbf) if dbf else ([], [])
    if rows and len(rows) != len(shapes):
        raise ShapefileError(f"{name}: {len(shapes)} shapes but {len(rows)} attribute rows")
    return Layer(name, [Record(k, p, rows[i] if rows else {}) for i, (k, p) in enumerate(shapes)], names)


def read_zip(blob: bytes) -> Layers:
    """Every shapefile layer (.shp with its .dbf) inside a zip archive, by layer name (the file name without .shp)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ShapefileError(f"not a zip archive ({exc})") from None
    names = {n.lower(): n for n in z.namelist()}
    out = Layers()
    for low, real in names.items():
        if not low.endswith(".shp"):
            continue
        stem = real[:-4].rsplit("/", 1)[-1]
        dbf = names.get(low[:-4] + ".dbf")
        out[stem] = read_layer(stem, z.read(real), z.read(dbf) if dbf else None)
    return out
