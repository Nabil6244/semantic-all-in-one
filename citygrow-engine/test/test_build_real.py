"""Real buildings: Overture Maps reading and the OpenStreetMap fallback, no network."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build_real as br  # noqa: E402

CENTER = (10.0, 45.0)


def wkb_polygon(rings, z=False, big=False):
    end = ">" if big else "<"
    out = bytes([0 if big else 1]) + struct.pack(end + "I", 1003 if z else 3) + struct.pack(end + "I", len(rings))
    for ring in rings:
        out += struct.pack(end + "I", len(ring))
        for lon, lat in ring:
            out += struct.pack(end + ("ddd" if z else "dd"), lon, lat, *([5.0] if z else []))
    return out


def wkb_multi(polys):
    return bytes([1]) + struct.pack("<II", 6, len(polys)) + b"".join(wkb_polygon(p) for p in polys)


def square(lon, lat, d=0.0002):
    return [(lon, lat), (lon + d, lat), (lon + d, lat + d), (lon, lat + d), (lon, lat)]


def world(d):
    meta = {"id": "t", "center": list(CENTER), "size_m": 4000, "credits": ["Elevation: x", "Buildings: old"]}
    Path(d, "meta.json").write_text(json.dumps(meta))
    return br.World("t", meta, Path(d))


class Wkb(unittest.TestCase):
    def test_polygon_outer_ring_only(self):
        rings = br.wkb_rings(wkb_polygon([square(10, 45), square(10.00005, 45.00005, 0.00005)]))
        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0].shape, (5, 2))
        self.assertAlmostEqual(rings[0][1][0], 10.0002)

    def test_z_values_and_big_endian(self):
        for blob in (wkb_polygon([square(10, 45)], z=True), wkb_polygon([square(10, 45)], big=True)):
            r = br.wkb_rings(blob)[0]
            self.assertEqual(r.shape, (5, 2))
            self.assertAlmostEqual(r[2][1], 45.0002)

    def test_multipolygon_gives_each_part(self):
        self.assertEqual(len(br.wkb_rings(wkb_multi([[square(10, 45)], [square(10.001, 45)]]))), 2)

    def test_not_a_polygon(self):
        with self.assertRaises(ValueError):
            br.wkb_rings(bytes([1]) + struct.pack("<Idd", 1, 10, 45))


class Overture(unittest.TestCase):
    def test_rows_become_buildings_with_heights_and_source_counts(self):
        with tempfile.TemporaryDirectory() as d:
            w = world(d)
            rows = [(wkb_polygon([square(10.001, 45.001)]), 30.0, None, None, ["OpenStreetMap"]),
                    (wkb_polygon([square(10.002, 45.001)]), None, 4, None, ["Microsoft ML Buildings"]),
                    (wkb_polygon([square(10.003, 45.001)]), None, None, "garage", ["Google Open Buildings"]),
                    (wkb_polygon([square(11.0, 45.0)]), None, None, None, ["OpenStreetMap"]),             # outside the world
                    (wkb_polygon([square(10.004, 45.001, 0.00002)]), None, None, None, ["OpenStreetMap"]),  # too small
                    (b"\x01junk", None, None, None, [])]
            out, by = br.overture_buildings_from_rows(w, rows)
            self.assertEqual([b[5] for b in out], [30.0, 14.2, 3.5])
            self.assertEqual(by, {"OpenStreetMap": 1, "Microsoft ML Buildings": 1, "Google Open Buildings": 1})
            self.assertAlmostEqual(out[0][3] * out[0][4], 0.0002 * 111320 * np.cos(np.radians(45)) * 0.0002 * 110574, delta=5)

    def test_files_for_picks_only_overlapping_files(self):
        index = [[0, 0, 20, 50, "a"], [20, 0, 40, 50, "b"], [-10, 40, 9, 60, "c"]]
        self.assertEqual(br.files_for(index, 44.9, 9.9, 45.1, 10.1), ["a"])

    def test_build_writes_buildings_and_credit(self):
        rows = [(wkb_polygon([square(10.001, 45.001)]), 12.0, None, None, ["OpenStreetMap", "Microsoft ML Buildings"]),
                (wkb_polygon([square(10.002, 45.001)]), None, None, None, ["Microsoft ML Buildings"])]
        with tempfile.TemporaryDirectory() as d:
            w = world(d)
            with mock.patch.object(br, "overture_release", return_value="2026-10-21.0"), \
                 mock.patch.object(br, "overture_index", return_value=[]), \
                 mock.patch.object(br, "query_overture", return_value=rows):
                res = br.build_buildings_overture(w)
            self.assertEqual(res["buildings"], 2)
            self.assertEqual(len(json.loads(Path(d, "buildings.json").read_text())), 2)
            credits = json.loads(Path(d, "meta.json").read_text())["credits"]
            self.assertEqual(credits[0], "Elevation: x")
            self.assertEqual(sum(c.startswith("Buildings:") for c in credits), 1)
            self.assertIn("Overture Maps Foundation, release 2026-10-21.0", credits[-1])
            self.assertLess(credits[-1].index("Microsoft"), credits[-1].index("OpenStreetMap"))   # most buildings first

    def test_auto_falls_back_to_osm_when_overture_fails(self):
        with tempfile.TemporaryDirectory() as d:
            w = world(d)
            with mock.patch.object(br, "build_buildings_overture", side_effect=RuntimeError("offline")), \
                 mock.patch.object(br, "build_buildings_osm", return_value={"buildings_source": "osm"}) as osm, \
                 mock.patch.dict(sys.modules, {"duckdb": mock.MagicMock()}):
                self.assertEqual(br.build_buildings(w, 2, "auto")["buildings_source"], "osm")
                osm.assert_called_once_with(w, 2)
                with self.assertRaises(RuntimeError):
                    br.build_buildings(w, 2, "overture")

    def test_osm_buildings_get_their_credit(self):
        g = [{"lon": a, "lat": b} for a, b in square(10.001, 45.001)]
        with tempfile.TemporaryDirectory() as d:
            w = world(d)
            with mock.patch.object(br, "overpass", return_value={"elements": [{"type": "way", "id": 1, "geometry": g, "tags": {"building:levels": "2"}}]}):
                res = br.build_buildings_osm(w, 1)
            self.assertEqual(res["buildings"], 1)
            self.assertEqual(json.loads(Path(d, "buildings.json").read_text())[0][5], 7.6)
            self.assertEqual(json.loads(Path(d, "meta.json").read_text())["credits"][-1], br.OSM_BUILDINGS_CREDIT)


if __name__ == "__main__":
    unittest.main()
