"""Stickman Phase 4: the Stickman CSV, native Shorts, the app page wiring and autorun. No network."""
import csv
import io
import re
import unittest
from pathlib import Path

from stickman import checker, csvplan, director, draw, looks, timeline
from test_stickman_director import BODY, fake_words

ROOT = Path(__file__).resolve().parent
EXAMPLE = (ROOT / "stickman" / "csv_prompt.txt").read_text().split("EXAMPLE\n", 1)[1]


def _direct(rows, **kw):
    body = csvplan.script_of(rows)
    words, dur = fake_words(body)
    return director.direct(body, words, dur, rows=rows, **kw)


class CsvTests(unittest.TestCase):
    def test_prompt_example_reads_clean(self):
        rows, problems = csvplan.read(EXAMPLE)
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[2]["action"], "sleep")
        self.assertEqual(rows[2]["props"], [{"name": "clock", "at": "side"}])
        self.assertEqual(rows[4]["who"], "other")
        self.assertEqual(csvplan.look_of(rows), "colour_pop")

    def test_prompt_lists_only_real_names(self):
        text = (ROOT / "stickman" / "csv_prompt.txt").read_text()
        from stickman import places, poses, props
        for name in poses.ALL:
            self.assertIn(name, text)
        for name in props.PROPS:
            self.assertRegex(text, rf"\b{re.escape(name)}\b")
        for name in places.PLACES:
            self.assertIn(name, text)

    def test_bad_names_are_notes_not_failures(self):
        rows, problems = csvplan.read("line,action,props,place,camera\nHello there.,moonwalk,unicorn,mars,drone\n")
        self.assertEqual(rows, [{"line": "Hello there."}])
        self.assertEqual(len(problems), 4)

    def test_needs_line_column(self):
        with self.assertRaises(csvplan.CsvError):
            csvplan.read("text,action\nhi,wave\n")


class CsvDirectingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, _ = csvplan.read(EXAMPLE)
        cls.spec = _direct(cls.rows, size=(640, 360))

    def _first_beat_of(self, k):
        n = len(" ".join(r["line"] for r in self.rows[:k]).split())
        said = 0
        for b in self.spec["beats"]:
            if said == n:
                return b
            said += len(b["words"])
        raise AssertionError("no beat starts that row")

    def test_rows_start_beats_and_set_choices(self):
        b = self._first_beat_of(1)
        self.assertEqual(b["acts"]["lead"]["do"], "facepalm")
        self.assertEqual(b["camera"]["kind"], "close")
        b = self._first_beat_of(2)
        self.assertEqual(b["acts"]["lead"]["do"], "sleep")
        self.assertEqual(b["props"][0]["name"], "clock")
        self.assertIn("action", b["locked"])
        self.assertEqual(self.spec["cards"][0]["text"], "8 HOURS")

    def test_friend_walks_in_then_does_the_csv_pose(self):
        b = self._first_beat_of(4)
        self.assertEqual(b["acts"]["other"], {"do": "walk", "to": 0.68, "then": "arms_crossed"})
        self.assertEqual(b["place"], "kitchen")

    def test_csv_place_turns_off_automatic_places(self):
        self.assertEqual([b["place"] for b in self.spec["beats"] if b.get("place")], ["bedroom", "kitchen"])

    def test_checker_keeps_csv_choices(self):
        s = _direct([{"line": "One two three.", "action": "think"}, {"line": "Four five six.", "action": "think"},
                     {"line": "Seven eight nine.", "action": "think"}, {"line": "Ten eleven twelve.", "action": "think"}], size=(640, 360))
        fixed, notes, left = checker.repair(s)
        self.assertEqual([b["acts"]["lead"]["do"] for b in fixed["beats"][1:]], ["think"] * 3)

    def test_plan_to_csv_round_trip(self):
        rows, problems = csvplan.read(csvplan.from_plan(self.spec))
        self.assertEqual(problems, [])
        self.assertEqual(csvplan.script_of(rows).split(), csvplan.script_of(self.rows).split())
        spec2 = _direct(rows, size=(640, 360))
        self.assertEqual([b["action"] for b in spec2["beats"]][1:], [b["action"] for b in self.spec["beats"]][1:])

    def test_mismatched_rows_rejected(self):
        words, dur = fake_words("Hello there friend.")
        with self.assertRaises(ValueError):
            director.direct("Hello there friend.", words, dur, rows=[{"line": "Hello there"}])


class ShortsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        words, dur = fake_words(BODY)
        cls.spec = director.direct(BODY, words, dur, title="Why You're Always Tired", shorts=True, look="colour_pop")

    def test_portrait_layout(self):
        self.assertEqual(self.spec["size"], [1080, 1920])
        self.assertTrue(self.spec["shorts"])
        self.assertEqual(self.spec["ground"], director.SHORTS_LAYOUT["ground"])
        self.assertEqual(self.spec["figures"]["lead"]["height"], 0.26)

    def test_short_caption_lines(self):
        for b in self.spec["beats"]:
            line = b["caption"].replace("*", "")
            self.assertLessEqual(len(b["words"]), 6, line)
            self.assertLessEqual(len(line), 28, line)

    def test_checker_and_frames_in_portrait(self):
        fixed, notes, left = checker.repair(self.spec)
        self.assertEqual(left, [])
        small = dict(fixed, size=[270, 480])
        frames = timeline.simulate(small)
        W = small["size"][0]
        for fr in frames[60::90]:
            for f in fr["figs"]:
                if 0 < f["joints"]["pelvis"][0] < W:
                    self.assertGreater(f["joints"]["head"][1], 0)
            self.assertEqual(len(draw.frame(fr, small, looks.get("colour_pop"))), 270 * 480 * 3)


class AppWiringTests(unittest.TestCase):
    def test_app_hooks(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for hook in ("from ui import stickman_section as _sm_section", '_sm_section.activate(self)', '_sm_section.cta(self, action)',
                     "_sm_section.sync_cta(self)", "_sm_section.resume_on_open(self)", '_sm_section.deactivate(self, remember=False)',
                     'return "Stickman"'):
            self.assertIn(hook, src)

    def test_style_card_and_labels(self):
        from ui import style_registry as R
        import export_state
        self.assertIn("Stickman", R.STANDALONE)
        self.assertEqual(R.group_of("Stickman"), "Explainers")
        self.assertIn("Stickman", R.EXTRA_CARDS)
        self.assertEqual(export_state.STYLE_LABELS["stickman"], "Stickman")

    def test_page_module_loads(self):
        from ui import stickman_section as S
        self.assertEqual(S.STYLE, "Stickman")
        self.assertEqual(set(v for v in S.LOOKS.values() if v), set(looks.LOOKS))

    def test_autorun_job(self):
        from autorun import job as J
        import make_video as MV
        self.assertEqual(J.STYLES["stickman"]["fields"]["script"], "_sm_script_var")
        self.assertEqual(MV.STYLES["stickman"][2], "stickman/csv_prompt.txt")
        script = ROOT / "stickman" / "demos" / "tired.txt"
        j = J.make_job("stickman", script=str(script))
        self.assertEqual(j["voice"], "")
        with self.assertRaises(J.JobError):
            J.make_job("stickman")


if __name__ == "__main__":
    unittest.main()
