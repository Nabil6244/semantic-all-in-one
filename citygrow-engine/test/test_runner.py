"""Runner: check / plan / world request on the real Istanbul world (no rendering, no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
import runner  # noqa: E402
import music_bed  # noqa: E402


class RunnerTest(unittest.TestCase):
    @unittest.skipUnless((HERE / "worlds" / "istanbul" / "meta.json").is_file(), "istanbul world not built")
    def test_check_and_plan(self):
        c = runner.check(str(HERE / "samples" / "istanbul_dev.csv"))
        self.assertEqual(c["errors"], [])
        self.assertGreater(c["duration"], 30)
        with tempfile.TemporaryDirectory() as d:
            p = runner.plan(str(HERE / "samples" / "istanbul_dev.csv"), d)
            tl = json.loads(Path(p["timeline"]).read_text())
            self.assertEqual(len(tl["holds"]), p["eras"])
            self.assertTrue(tl["credits"])

    def test_missing_world_asks_to_build(self):
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "x.csv"
            csv.write_text('row,year,era_name,population,focus,extra\nplan,,Nowhere,,"10.5,45.2","{""world"":""zz_not_built"",""size"":6}"\n'
                           'era,1000,Town,500,,\n', encoding="utf-8")
            c = runner.check(str(csv))
            self.assertEqual(c["errors"], [])
            wb = c["world_build"]
            self.assertEqual(wb["id"], "zz_not_built")
            self.assertEqual(wb["center"], [10.5, 45.2])
            self.assertEqual(wb["size"], 6.0)

    def test_music_bed_graph(self):
        g = music_bed.bed_filter(2, 250, 300)
        self.assertIn("acrossfade", g)
        self.assertIn("afade=t=out", g)
        self.assertNotIn("sidechain", g)
        self.assertIn("sidechaincompress", music_bed.bed_filter(1, 250, 100, voice=True))
        self.assertIn("Kevin MacLeod", music_bed.credit("ascending_the_vale"))


if __name__ == "__main__":
    unittest.main()
