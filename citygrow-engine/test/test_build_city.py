"""Step 1: city world builder, no network (synthetic tiles and OSM)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build_city as bc  # noqa: E402

CENTER = (10.0, 45.0)


def fake_tile(z, x, y):
    """Sea (−20 m) west of lon 10.0, a hill rising east of it."""
    n = 2 ** z
    cols = (x + (np.arange(256) + 0.5) / 256) / n * 360 - 180
    a = np.where(cols < CENTER[0], -20.0, 5.0 + (cols - CENTER[0]) * 4000.0)
    return np.tile(a.astype(np.float32), (256, 1))


def fake_osm(world_id, bbox):
    lat0, lat1 = bbox[1] - 1, bbox[3] + 1
    lake = [(10.012, 45.012), (10.016, 45.012), (10.016, 45.016), (10.012, 45.016), (10.012, 45.012)]
    return {"elements": [
        {"type": "way", "tags": {"natural": "coastline"},
         "geometry": [{"lon": CENTER[0], "lat": lat1}, {"lon": CENTER[0], "lat": lat0}]},
        {"type": "way", "tags": {"natural": "water"}, "geometry": [{"lon": a, "lat": b} for a, b in lake]},
    ]}


def fake_roads(world_id, bbox):
    # one street east of the coast, one crossing the coast into the sea (cut at the water)
    return {"elements": [
        {"type": "way", "tags": {"highway": "residential"}, "geometry": [{"lon": 10.005, "lat": 44.995}, {"lon": 10.005, "lat": 45.005}]},
        {"type": "way", "tags": {"highway": "primary"}, "geometry": [{"lon": 9.99, "lat": 45.0}, {"lon": 10.008, "lat": 45.0}]},
        {"type": "way", "tags": {"highway": "footway"}, "geometry": [{"lon": 10.006, "lat": 44.995}, {"lon": 10.006, "lat": 45.005}]},
    ]}


def broken_osm(world_id, bbox):
    raise RuntimeError("offline")


class GridTest(unittest.TestCase):
    def test_centre_maps_to_middle(self):
        g = bc.Grid(*CENTER, 4000, 8)
        x, y = g.lonlat_to_px(*CENTER)
        self.assertAlmostEqual(x, g.w / 2, places=6)
        self.assertAlmostEqual(y, g.h / 2, places=6)
        self.assertEqual(g.w, 500)

    def test_cells_go_north_to_south(self):
        g = bc.Grid(*CENTER, 2000, 10)
        lats = g.cell_lats()
        self.assertTrue(np.all(np.diff(lats) < 0))
        self.assertTrue(np.all(np.diff(g.cell_lons()) > 0))


class FloodTest(unittest.TestCase):
    def test_barrier_stops_sea(self):
        elev = np.full((20, 20), -5.0, np.float32)
        barrier = np.zeros((20, 20), bool)
        barrier[:, 10] = True
        elev[:, 11:] = 0.2   # low land behind the coastline
        sea = bc.sea_mask(elev, barrier)
        self.assertTrue(sea[:, :10].all())
        self.assertFalse(sea[:, 11:].any())

    def test_edge_fallback(self):
        elev = np.full((10, 10), 5.0, np.float32)
        elev[:, :3] = 0.0
        elev[5, 6] = 0.0   # a low pit inland stays land
        sea = bc.edge_sea(elev)
        self.assertTrue(sea[:, :3].all())
        self.assertFalse(sea[5, 6])

    def test_join_rings(self):
        a = [(0, 0), (1, 0), (1, 1)]
        b = [(0, 0), (0, 1), (1, 1)]
        rings = bc._join_rings([a, b])
        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0][0], rings[0][-1])


class InlandTest(unittest.TestCase):
    def test_river_level_under_its_banks(self):
        elev = np.full((30, 30), 20.0, np.float32)
        elev[:, :] += np.arange(30)[None, :] * 0.1        # gentle slope east
        river = np.zeros((30, 30), bool); river[:, 14:17] = True
        lv = bc.inland_levels(elev, river)
        self.assertTrue((lv[river] > 15).all() and (lv[river] < elev[:, 13].min()).all(), "surface stays near the banks, not at sea level")
        self.assertTrue((lv[~river] == 0).all())

    def test_small_ponds_dropped(self):
        m = np.zeros((20, 20), bool); m[2:4, 2:4] = True; m[10:19, 5:15] = True
        lab, sizes = bc.components(m)
        self.assertEqual(sorted(sizes[1:]), [4, 90])


class BuildTest(unittest.TestCase):
    def test_build_with_osm(self):
        with tempfile.TemporaryDirectory() as d:
            out = bc.build("t", CENTER, size_km=4, cell=20, fetch_tile=fake_tile, osm_fetch=fake_osm, roads_fetch=fake_roads, out_root=Path(d))
            roads = json.loads((out / "roads.json").read_text())
            self.assertEqual(len(roads), 2, "footway skipped")
            primary = [r for r in roads if r["c"] == 1][0]
            self.assertTrue(all(x > -10 for x, _ in primary["p"]), "the part in the sea is cut")
            meta = json.loads((out / "meta.json").read_text())
            w, h = meta["w"], meta["h"]
            water = np.fromfile(out / "water.u8", np.uint8).reshape(h, w)
            elev = np.fromfile(out / "height.f32", "<f4").reshape(h, w)
            self.assertEqual(meta["water_source"], "osm")
            self.assertTrue(water[:, : w // 2 - 2].all(), "west of the coastline is sea")
            self.assertFalse(water[:, w // 2 + 2 : w // 2 + 20].any(), "east of it is land")
            # the lake (≈ 1–1.3 km east and north of centre) is water
            g = bc.Grid(*CENTER, 4000, 20)
            x, y = g.lonlat_to_px(10.014, 45.014)
            self.assertEqual(water[int(y), int(x)], 1)
            level = np.fromfile(out / "water_level.f32", "<f4").reshape(h, w)
            sea, lake = (water == 1) & (level == 0), (water == 1) & (level > 0)
            self.assertTrue((elev[sea] <= -1).all() and (elev[water == 0] >= 0.5).all())
            self.assertTrue(lake.any() and (elev[lake] < level[lake]).all(), "the lake on the hill keeps its own surface")
            self.assertTrue((out / "preview.png").exists())
            self.assertTrue(any("OpenStreetMap" in c for c in meta["credits"]))

    def test_build_offline_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            out = bc.build("t", CENTER, size_km=2, cell=20, fetch_tile=fake_tile, osm_fetch=broken_osm, roads_fetch=broken_osm, out_root=Path(d))
            meta = json.loads((out / "meta.json").read_text())
            self.assertEqual(meta["water_source"], "elevation")
            self.assertTrue(meta["warnings"])
            self.assertGreater(meta["water_share"], 0.3)


if __name__ == "__main__":
    unittest.main()
