"""Reference renders of a phone (product_trailer/references.py): spec, colours, file names and the run with a fake engine. No browser, no Node."""
import tempfile
import unittest
from pathlib import Path

from product_trailer import references as R

CATALOG = [{"id": "galaxy_s27_ultra", "name": "Galaxy S27 Ultra", "aliases": ["s27 ultra"],
            "colors": [{"name": "Navy"}, {"name": "Sky Blue"}, {"name": "Pink"}, {"name": "White"}, {"name": "Black"}]},
           {"id": "one_colour", "name": "One", "colors": [{"name": "Grey"}]}]


class Spec(unittest.TestCase):
    def test_five_lineup_shots_two_seconds_each_stills_in_the_middle(self):
        spec, times = R.build_reference_spec("galaxy s27 ultra", colours=["Black", "Sky Blue", "Pink", "White"])
        self.assertEqual(len(spec["shots"]), 5)
        self.assertEqual(times, [1.0, 3.0, 5.0, 7.0, 9.0])
        self.assertEqual(spec["duration"], 10.0)
        for i, s in enumerate(spec["shots"]):
            self.assertEqual((s["kind"], s["object"], s["room"]), ("product", "lineup", "gallery"))
            self.assertEqual((s["start"], s["end"]), (2.0 * i, 2.0 * i + 2.0))
            self.assertEqual(s["wordmark"], "", "no wordmark on the references")
            self.assertEqual(s["phone"], "galaxy s27 ultra")

    def test_the_two_single_phone_shots_use_the_second_colour(self):
        spec, _ = R.build_reference_spec("x", colours=["Black", "Sky Blue", "Pink", "White"])
        by = {s["id"]: s for s in spec["shots"]}
        self.assertEqual(by["one_three_quarter"]["colors"], ["Sky Blue"])
        self.assertEqual(by["camera_macro"]["colors"], ["Sky Blue"])
        self.assertEqual(by["fan_backs"]["colors"], ["Black", "Sky Blue", "Pink", "White"])
        self.assertEqual(by["row_fronts"]["pose"], "front")

    def test_a_one_colour_phone_still_works(self):
        spec, _ = R.build_reference_spec("x", colours=["Grey"])
        self.assertEqual({tuple(s["colors"]) for s in spec["shots"]}, {("Grey",)})


class Colours(unittest.TestCase):
    def test_from_the_preset_by_name_alias_or_id(self):
        for q in ("Galaxy S27 Ultra", "s27 ultra", "galaxy_s27_ultra"):
            self.assertEqual(R.preset_colours(q, CATALOG), ["Navy", "Sky Blue", "Pink", "White"], q)

    def test_unknown_phone_or_one_colour_preset_gets_the_defaults(self):
        self.assertEqual(R.preset_colours("no such phone", CATALOG), R.DEFAULT_COLOURS)
        self.assertEqual(R.preset_colours("one", CATALOG), R.DEFAULT_COLOURS)

    def test_the_real_catalog_loads(self):
        cols = R.preset_colours("galaxy s27 ultra")
        self.assertGreaterEqual(len(cols), 2)


class Files(unittest.TestCase):
    def test_names_are_numbered_in_prompt_order(self):
        names = [p.name for p in R.reference_files(Path("out"))]
        self.assertEqual(names, ["ref1_fan_backs.jpg", "ref2_row_fronts.jpg", "ref3_row_backs.jpg", "ref4_one_three_quarter.jpg", "ref5_camera_macro.jpg"])


class Run(unittest.TestCase):
    def test_render_writes_the_five_files_from_the_engine_stills(self):
        seen = {}

        def fake(spec, times, work, log):
            seen["spec"], seen["times"] = spec, list(times)
            out = []
            for i, t in enumerate(times):
                p = Path(work) / f"refs.mp4.t{t:g}.jpg"
                p.write_bytes(b"\xff\xd8jpeg" + bytes([i]))
                out.append(p)
            return out

        with tempfile.TemporaryDirectory() as d:
            res = R.render_references("galaxy s27 ultra", Path(d) / "refs", colours=["Black", "Pink"], runner=fake, log=lambda m: None)
            files = res["files"]
            self.assertEqual([f.name for f in files], [p.name for p in R.reference_files(Path(d))])
            for i, f in enumerate(files):
                self.assertTrue(f.is_file())
                self.assertEqual(f.read_bytes()[-1], i, "each file got its own still, in order")
            self.assertEqual(res["colours"], ["Black", "Pink"])
        self.assertEqual(seen["times"], [1.0, 3.0, 5.0, 7.0, 9.0])
        self.assertEqual(seen["spec"]["shots"][0]["colors"], ["Black", "Pink"])


if __name__ == "__main__":
    unittest.main()
