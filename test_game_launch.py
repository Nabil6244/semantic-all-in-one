"""Game Launch style: scenes CSV parsing, cut-safe trailer clipping, the timeline, Shorts spans and the app wiring (no rendering)."""
import tempfile
import unittest
from pathlib import Path

from game_launch import plan as P
from game_launch import runner as R

ROOT = Path(__file__).resolve().parent
HEAD = "narration,shot,game_clip,game_at,real,real_at,left,right,title,subtitle,place\n"


def write(text: str) -> str:
    d = Path(tempfile.mkdtemp())
    f = d / "scenes.csv"
    f.write_text(HEAD + text, encoding="utf-8")
    return str(f)


class PlanTests(unittest.TestCase):
    def test_lines_and_continuation_rows(self):
        p = P.read(write('Line one.,chapter,t1.mp4,4,,,,,Vice City,,\n'
                         'Line two.,map,,,,,,,,,Vice City=Miami@25.77,-80.19\n'
                         ',split,t1.mp4,1:02.5,miami skyline,,vice city,miami,,,\n'))
        self.assertEqual(p["errors"], [])
        self.assertEqual(len(p["lines"]), 2)
        self.assertEqual([s["kind"] for s in p["lines"][1]["shots"]], ["map", "split"])
        split = p["lines"][1]["shots"][1]
        self.assertAlmostEqual(split["game_at"], 62.5)
        self.assertEqual((split["left"], split["right"]), ("VICE CITY", "MIAMI"))
        self.assertEqual(p["pins"][0]["real"], "Miami")
        self.assertEqual(p["lines"][0]["shots"][0]["number"], "01")

    def test_errors_are_reported_not_raised(self):
        p = P.read(write(',game,t1.mp4,1,,,,,,,\n'
                         'A line.,dance,,,,,,,,,\n'
                         'B line.,split,,,,,,,,,\n'
                         'C line.,map,,,,,,,,,Nowhere\n'))
        text = "\n".join(p["errors"])
        self.assertIn("first row needs narration", text)
        self.assertIn("'dance'", text)
        self.assertIn("needs game_clip", text)
        self.assertIn("needs real", text)
        self.assertIn("should look like", text)

    def test_real_file_and_search_rows_both_go_to_the_visuals_tab(self):
        d = Path(tempfile.mkdtemp())
        (d / "clip.mp4").write_bytes(b"x")
        f = d / "s.csv"
        f.write_text(HEAD + 'One.,real,,,clip.mp4,2,,,,,\n,real,,,miami beach drone,,,,,,\n', encoding="utf-8")
        p = P.read(str(f))
        self.assertEqual(p["errors"], [])
        vs = P.visual_scenes(p)
        self.assertEqual([v["scene_no"] for v in vs], [1, 2])
        self.assertEqual(vs[1]["prompt"], "miami beach drone")
        self.assertEqual(P.local_files(p), {1: str(d / "clip.mp4")})


class EngineTests(unittest.TestCase):
    def test_clip_never_crosses_a_cut(self):
        _inp, f = R._clip("x.mp4", 10.0, 3.0, cuts=[11.0, 20.0], seconds=60.0)
        self.assertIn("setpts=(PTS-STARTPTS)/0.4500", f)      # slowed to the floor ...
        self.assertIn("tpad=stop_mode=clone", f)              # ... then holds its last frame
        inp, f = R._clip("x.mp4", 10.0, 3.0, cuts=[20.0], seconds=60.0)
        self.assertIn("/1.0000", f)
        self.assertNotIn("tpad", f)
        self.assertEqual(inp[inp.index("-t") + 1], "3.000")

    def test_timeline_shares_line_time_and_fills_to_the_end(self):
        plan = {"lines": [{"text": "a", "vo_dur": 2.0, "shots": [{"kind": "title"}]},
                          {"text": "b", "vo_dur": 4.0, "shots": [{"kind": "map"}, {"kind": "split"}]},
                          {"text": "c", "vo_dur": 3.0, "shots": [{"kind": "chapter", "title": "X"}]}]}
        shots, vo, total = R.timeline(plan)
        self.assertEqual(shots[0]["start"], 0.0)
        for a, b in zip(shots, shots[1:]):
            self.assertAlmostEqual(a["start"] + a["len"], b["start"], places=2)
        self.assertLess(shots[1]["len"], shots[2]["len"])        # a map shares less of its line
        self.assertAlmostEqual(shots[-1]["start"] + shots[-1]["len"], total, places=2)
        self.assertGreater(vo[2][1] - (vo[1][1] + 4.0 + 0.32), 0.4)   # a breath before a chapter

    def test_short_spans_one_per_chapter_under_a_minute(self):
        lines = []
        for c in range(2):
            lines.append({"text": "chapter", "vo_dur": 2.0, "shots": [{"kind": "chapter", "title": f"Part {c}"}]})
            for _ in range(12):
                lines.append({"text": "x", "vo_dur": 6.0, "shots": [{"kind": "split", "right": "MIAMI"}]})
        shots, vo, total = R.timeline({"lines": lines})
        spans = R.short_spans(shots, vo, total)
        self.assertEqual(len(spans), 2)
        for sp in spans:
            self.assertLessEqual(sp["end"] - sp["start"], 58.5)
            self.assertEqual(sp["second"], "= MIAMI")

    def test_speakable_rewords_on_later_attempts(self):
        self.assertEqual(R._speakable("GTA 6.", 0), "GTA 6.")
        self.assertEqual(R._speakable("Is it real? GTA 6.", 3), "Is it real, GTA six.")

    def test_trailer_lookup_by_name_or_stem(self):
        d = Path(tempfile.mkdtemp())
        (d / "Trailer2.MP4").write_bytes(b"x")
        self.assertEqual(R.trailer_path(str(d), "trailer2.mp4").name.lower(), "trailer2.mp4")
        self.assertEqual(R.trailer_path(str(d), "trailer2").name, "Trailer2.MP4")
        self.assertIsNone(R.trailer_path(str(d), "trailer3.mp4"))

    def test_example_csv_parses(self):
        p = P.read(str(ROOT / "game_launch" / "example_scenes.csv"))
        self.assertEqual(p["errors"], [])
        self.assertGreaterEqual(len(p["pins"]), 2)


class AppWiringTests(unittest.TestCase):
    def test_registered_and_wired(self):
        from ui import style_registry as SR
        import export_state
        import visual_bridge

        self.assertIn("Game Launch", dict(SR.grouped(SR.with_extras(("Normal video",)))).get("Documentary", []))
        self.assertIn("Game Launch", SR.EXTRA_BLURBS)
        self.assertIn("Game Launch", SR.EXTRA_CARDS)
        self.assertIn("game_launch", visual_bridge.OWNERS)
        self.assertEqual(export_state.STYLE_LABELS.get("game_launch"), "Game Launch")
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for needle in ("from ui import game_launch_section as _gl_section", "_gl_section.activate(self)", "_gl_section.deactivate(self)",
                       "_gl_section.cta(self, action)", "_gl_section.sync_cta(self)", '"_gl_running"', 'return "Game Launch"',
                       '"gl_generate", "gl_render", "gl_cancel"', "_gl_section.resume_on_open(self)",
                       'gl_block.grid() if active == "Game Launch"'):
            self.assertIn(needle, src)
        self.assertIn('"Game Launch"', (ROOT / "ui" / "style_kit.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
