#!/usr/bin/env python3
"""Build the bundled place-boundary data for map scenes (map_scene/data/).

Inputs (public domain, downloaded once by a developer, not at runtime):
  ne_10m_admin_0_countries.geojson          Natural Earth (naturalearthdata.com)
  ne_10m_admin_1_states_provinces.geojson   Natural Earth
  cb_2023_us_county_5m.shp/.dbf             US Census cartographic boundaries
  ne_10m_land.geojson                       Natural Earth land (coastlines, for the sea mask)

Output: compact gzipped GeoJSON-like files with only names + geometry,
coordinates rounded to 3 decimals (~110 m — finer than any map scene shows).

Usage: python scripts/build_map_data.py <folder with the three inputs>
"""

from __future__ import annotations

import gzip
import json
import struct
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "map_scene" / "data"
DECIMALS = 3


def _round_ring(ring):
    out = []
    for x, y in ring:
        pt = [round(x, DECIMALS), round(y, DECIMALS)]
        if not out or out[-1] != pt:
            out.append(pt)
    if len(out) >= 3 and out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def _round_geometry(geom):
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return None
    result = []
    for poly in polys:
        rings = [r for r in (_round_ring(ring) for ring in poly) if r]
        if rings:
            result.append(rings)
    if not result:
        return None
    return {"type": "MultiPolygon", "coordinates": result}


def _write(name: str, features: list) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json.gz"
    data = json.dumps({"features": features}, separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb", compresslevel=9) as fh:
        fh.write(data)
    print(f"{path.name}: {len(features)} features, {path.stat().st_size / 1e6:.1f} MB")


def _alts(*values) -> list:
    seen, out = set(), []
    for v in values:
        for part in str(v or "").split("|"):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                out.append(part)
    return out


def build_countries(src: Path) -> None:
    feats = []
    for f in json.loads(src.read_text(encoding="utf-8"))["features"]:
        p, g = f["properties"], _round_geometry(f["geometry"])
        if g is None:
            continue
        feats.append({"n": p["NAME"], "alt": _alts(p.get("NAME_LONG"), p.get("ADMIN"), p.get("FORMAL_EN"),
                                                    p.get("NAME_EN"), p.get("NAME_ALT"), p.get("ABBREV")),
                      "iso": p.get("ADM0_A3") or "", "g": g})
    _write("countries", feats)


def build_admin1(src: Path) -> None:
    feats = []
    for f in json.loads(src.read_text(encoding="utf-8"))["features"]:
        p, g = f["properties"], _round_geometry(f["geometry"])
        if g is None or not p.get("name"):
            continue
        feats.append({"n": p["name"], "alt": _alts(p.get("name_en"), p.get("name_alt")),
                      "iso": p.get("adm0_a3") or "", "country": p.get("admin") or "",
                      "kind": p.get("type_en") or "", "postal": p.get("postal") or "", "g": g})
    _write("admin1", feats)


def _read_dbf(path: Path):
    raw = path.read_bytes()
    n_records, header_len, record_len = struct.unpack("<IHH", raw[4:12])
    fields, pos = [], 32
    while raw[pos] != 0x0D:
        name = raw[pos:pos + 11].split(b"\x00")[0].decode("ascii")
        fields.append((name, raw[pos + 16]))
        pos += 32
    rows = []
    for i in range(n_records):
        rec = raw[header_len + i * record_len: header_len + (i + 1) * record_len]
        off, row = 1, {}
        for name, length in fields:
            row[name] = rec[off:off + length].decode("utf-8", "replace").strip()
            off += length
        rows.append(row)
    return rows


def _signed_area(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:])) / 2.0


def _read_shp_polygons(path: Path):
    """Shapefile polygon (type 5) records -> list of MultiPolygon coordinate lists."""
    raw = path.read_bytes()
    pos, shapes = 100, []
    while pos < len(raw):
        content_len = struct.unpack(">I", raw[pos + 4:pos + 8])[0] * 2
        rec = raw[pos + 8: pos + 8 + content_len]
        pos += 8 + content_len
        if struct.unpack("<i", rec[:4])[0] != 5:
            shapes.append([])
            continue
        n_parts, n_points = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{n_parts}i", rec[44:44 + 4 * n_parts])) + [n_points]
        pts_off = 44 + 4 * n_parts
        pts = [struct.unpack("<2d", rec[pts_off + 16 * i: pts_off + 16 * i + 16]) for i in range(n_points)]
        rings = [pts[parts[i]:parts[i + 1]] for i in range(n_parts)]
        # Shapefile outer rings are clockwise (negative signed area here);
        # holes are counter-clockwise and belong to the preceding outer ring.
        polys = []
        for ring in rings:
            if _signed_area(ring) <= 0 or not polys:
                polys.append([ring])
            else:
                polys[-1].append(ring)
        shapes.append(polys)
    return shapes


def build_us_counties(shp: Path) -> None:
    rows = _read_dbf(shp.with_suffix(".dbf"))
    shapes = _read_shp_polygons(shp)
    feats = []
    for row, polys in zip(rows, shapes):
        g = _round_geometry({"type": "MultiPolygon", "coordinates": polys}) if polys else None
        if g is None:
            continue
        feats.append({"n": row["NAME"], "alt": _alts(row.get("NAMELSAD")), "state": row["STATE_NAME"],
                      "fips": row["GEOID"], "g": g})
    _write("us_counties", feats)


def build_land(src: Path) -> None:
    feats = []
    for f in json.loads(src.read_text(encoding="utf-8"))["features"]:
        g = _round_geometry(f["geometry"])
        if g is not None:
            feats.append({"g": g})
    _write("land", feats)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    build_countries(src / "ne_10m_admin_0_countries.geojson")
    build_admin1(src / "ne_10m_admin_1_states_provinces.geojson")
    build_us_counties(src / "cb_2023_us_county_5m.shp")
    build_land(src / "ne_10m_land.geojson")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
