"""War Documentary front lines (cinematic_explainer/war/frontline.py): sourced, dated control snapshots on the tactical map.

All snapshot data here is SYNTHETIC (test_data: true) and is never a real front line."""

import datetime as dt
import gzip
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from cinematic_explainer.render import Layer
from cinematic_explainer.war import frontline as FL
from cinematic_explainer.war import maps_tactical as MT


def synth(as_of, west=36.0, north=50.0, sid=None, status="assessed", **kw):
    """A synthetic eastern block plus a southern strip; `west` moves its western edge (smaller = further west)."""
    east = [[west, 46.6], [west - 0.4, 47.6], [west + 0.2, 48.6], [west + 0.6, north], [41.0, north], [41.0, 46.6]]
    south = [[32.0, 44.0], [32.0, 46.9], [west, 46.9], [west, 44.0]]
    s = {"id": sid or f"synthetic-{as_of}", "as_of": as_of, "source": "Synthetic test source", "licence": "test fixture",
         "status": status, "side": "russia", "areas": [east, south], "test_data": True}
    s.update(kw)
    return s


A = synth("2024-03-01")
B = synth("2024-06-01", west=35.6, north=49.6)          # moved west (gain) and pulled back in the north (loss)


class Row(dict):
    pass


class Plan:
    def __init__(self, layers, log=()):
        self.layers, self.log = list(layers), list(log)


class Dec:
    def __init__(self, no):
        self.scene_no, self.flags, self.candidates = no, [], []


class ValidationTests(unittest.TestCase):
    def test_requires_source_licence_date_area(self):
        self.assertTrue(FL.validate(A)[0])
        for k in ("source", "licence", "as_of"):
            bad = dict(A)
            bad.pop(k)
            self.assertFalse(FL.validate(bad)[0], k)
        self.assertFalse(FL.validate(dict(A, as_of="March 2024"))[0])
        self.assertFalse(FL.validate(dict(A, areas=[]))[0])
        self.assertFalse(FL.validate(dict(A, status="confirmed"))[0])

    def test_library_rejects_bad_files_and_sorts(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "b.json").write_text(json.dumps(B))
            Path(d, "a.json").write_text(json.dumps(A))
            Path(d, "nolicence.json").write_text(json.dumps({k: v for k, v in A.items() if k != "licence"} | {"id": "x"}))
            Path(d, "README.md").write_text("ignored")
            good, bad = FL.load_library([d])
        self.assertEqual([s["as_of"] for s in good], ["2024-03-01", "2024-06-01"])
        self.assertEqual(bad[0][0], "nolicence.json")

    def test_package_folder_ships_no_data(self):
        good, _ = FL.load_library([FL.DATA_DIR])
        self.assertEqual(good, [])

    def test_import_geojson_keeps_provenance(self):
        gj = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "keep"}, "geometry": {"type": "Polygon", "coordinates": [[[36, 47], [37, 47], [37, 48], [36, 48], [36, 47]]]}},
            {"type": "Feature", "properties": {"name": "drop"}, "geometry": {"type": "Polygon", "coordinates": [[[30, 47], [31, 47], [31, 48], [30, 47]]]}}]}
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "x.geojson")
            src.write_text(json.dumps(gj))
            out = FL.import_geojson(src, d, as_of="2024-01-05", source="S", licence="L", property_filter={"name": "keep"})
            snap = json.loads(gzip.open(out, "rt").read())
            self.assertEqual((snap["as_of"], snap["source"], snap["licence"], len(snap["areas"])), ("2024-01-05", "S", "L", 1))
            with self.assertRaises(ValueError):
                FL.import_geojson(src, d, as_of="2024-01-05", source="S", licence="")


class DateAndPickTests(unittest.TestCase):
    def test_dates_in(self):
        ds = FL.dates_in("In late September 2022 and on 12 March 2024, and by 2023.")
        self.assertEqual(ds[0], (dt.date(2022, 9, 21), dt.date(2022, 9, 30)))
        self.assertEqual(ds[1], (dt.date(2024, 3, 12), dt.date(2024, 3, 12)))
        self.assertEqual(ds[2], (dt.date(2023, 1, 1), dt.date(2023, 12, 31)))

    def test_pick_never_passes_an_old_line_off_as_a_later_date(self):
        lib = [A, B]
        self.assertEqual(FL.pick(lib, dt.date(2024, 6, 20))["id"], B["id"])
        self.assertIsNone(FL.pick(lib, dt.date(2024, 12, 1)))           # B is 6 months old by then
        self.assertIsNone(FL.pick(lib, dt.date(2023, 1, 1)))            # nothing before the first snapshot

    def test_spec_rules(self):
        lib = [A, B]
        self.assertIsNone(FL.spec_for("Russian forces captured the town.", lib)[0])          # no date, not about now
        self.assertIsNone(FL.spec_for("The economy grew in March 2024.", lib)[0])            # no territorial cue
        s, _ = FL.spec_for("Between March 2024 and June 2024 the front line moved west.", lib)
        self.assertEqual((s["mode"], s["a"]["id"], s["b"]["id"]), ("compare", A["id"], B["id"]))
        s, _ = FL.spec_for("By June 2024 Russia controlled the area.", lib)
        self.assertEqual((s["mode"], s["snap"]["id"]), ("single", B["id"]))
        s, _ = FL.spec_for("Today the front line runs here.", lib, reference=dt.date(2026, 11, 8))
        self.assertEqual(s["stale"], "may have changed since")
        s, _ = FL.spec_for("Within days the line shifted.", lib, carried=(dt.date(2024, 6, 1), dt.date(2024, 6, 30)))
        self.assertEqual(s["mode"], "single")                        # the March snapshot is too old to stand for 'before June'
        s, _ = FL.spec_for("Within days the line shifted.", lib, carried=(dt.date(2024, 6, 1), dt.date(2024, 6, 30)), max_gap_days=120)
        self.assertEqual(s["mode"], "compare")


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.base = {"theme": "tactical", "places": [{"name": "Kharkiv"}, {"name": "Donetsk"}]}

    def test_no_frontline_unchanged(self):
        info = MT.render_info(dict(self.base), 3.0)
        self.assertNotIn("frontline", info)

    def test_single_draws_line_and_stamp(self):
        p = dict(self.base, frontline={"mode": "single", "snap": A, "start": 0.2})
        img = MT.tac_map(3.0, 6.0, p)
        info = MT.render_info(p, 3.0)
        self.assertTrue(info["frontline"]["drawn"])
        plain = np.asarray(MT.tac_map(3.0, 6.0, dict(self.base)).convert("RGB"), dtype=np.int16)
        self.assertGreater(np.abs(np.asarray(img.convert("RGB"), dtype=np.int16) - plain).sum(), 100000)
        lines = [s for s, _ in FL.stamp_lines(p["frontline"])]
        self.assertIn("AS OF 1 MAR 2024", lines)
        self.assertIn("TEST DATA · NOT A REAL FRONT LINE", lines)

    def test_compare_measures_change(self):
        ch = FL.change_km2(A, B)
        self.assertGreater(ch["gained"], 0)
        self.assertGreater(ch["lost"], 0)
        p = dict(self.base, frontline={"mode": "compare", "a": A, "b": B, "start": 0.5, "length": 1.0})
        info = MT.render_info(p, 3.0)
        self.assertEqual(info["frontline"]["change_km2"], ch)
        self.assertTrue(any("GAINS" in x for x in info.get("frontline_labels", [])))

    def test_disputed_is_hatched_not_solid(self):
        lines = [s for s, _ in FL.stamp_lines({"mode": "single", "snap": dict(A, status="disputed")})]
        self.assertTrue(lines[0].endswith("DISPUTED"))

    def test_invalid_snapshot_not_drawn(self):
        p = dict(self.base, frontline={"mode": "single", "snap": dict(A, source="")})
        self.assertFalse(MT.render_info(p, 3.0)["frontline"]["drawn"])


class AttachTests(unittest.TestCase):
    def _plan(self, text):
        rows = [Row(_no=1, _start=0.0, _end=6.0, text=text)]
        ly = Layer("tac_map", 0.0, 6.0, {"theme": "tactical", "places": [{"name": "Kharkiv"}]}, dim=False)
        return Plan([ly], [Dec(1)]), rows, ly

    def test_attaches_with_credits(self):
        plan, rows, ly = self._plan("Between March 2024 and June 2024 Russian forces advanced near Kharkiv.")
        res = FL.attach(plan, rows, {"frontline_snapshots": [A, B]})
        self.assertEqual(res["attached"], 1)
        self.assertEqual(ly.params["frontline"]["mode"], "compare")
        self.assertIn("dir:frontline", plan.log[0].flags)
        self.assertTrue(any("2024-06-01" in c and "[TEST DATA]" in c for c in res["credits"]))

    def test_empty_library_is_a_no_op(self):
        plan, rows, ly = self._plan("In March 2024 Russian forces captured the town.")
        res = FL.attach(plan, rows, {"frontline_snapshots": []})
        self.assertEqual(res["attached"], 0)
        self.assertNotIn("frontline", ly.params)

    def test_undated_history_gets_no_line(self):
        plan, rows, ly = self._plan("Russian forces captured the town.")
        res = FL.attach(plan, rows, {"frontline_snapshots": [A, B]})
        self.assertEqual(res["attached"], 0)
        self.assertEqual(len(res["skipped"]), 1)


if __name__ == "__main__":
    unittest.main()
