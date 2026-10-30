"""Rep Theory scenes CSV direction: the optional look / prompt / muscle columns (reptheory/direction.py). A directed row gets its own scene with the look it asks for,
a Flow picture is drawn from the row's own prompt, a 3D clip shows the row's muscle, a look the sentence cannot support is reported and left to the app, and a CSV
without these columns plans exactly as before. Synthetic narration only: no Flow call, no 3D render, no network."""
from __future__ import annotations
import os, re, tempfile, unittest

os.environ.setdefault("REP_THEORY_ASSET_DIR", tempfile.mkdtemp(prefix="rt_dir_lib_"))

import test_rep_theory_variety as TV
from reptheory import app_section as A, beat_art as BA, beats as B, clip3d as C3, direction as DR, draw as D, scenes as S, variety as V

ROWS = [  # text, look, prompt, muscle, chapter
    ("Your forearms decide how long you can hang.", "3d", "", "forearms", "Grip"),
    ("Rest for two days before you train the same muscle again.", "takeaway", "", "", ""),
    ("Do twelve reps with good form, rather than twenty with bad form.", "versus", "", "", ""),
    ("Keep your core tight, because a sagging back takes the work away.", "", "the trainee holding a plank, side view", "", "Core"),
    ("Most people rush this, and that is why their progress stalls.", "figure", "", "", ""),
    ("Hold it for thirty seconds, three times.", "stat", "", "", ""),
    ("The key point is that small improvements add up.", "steps", "", "", ""),
    ("Your lats pull the body up while your biceps help.", "", "", "banana", ""),
]

def setUpModule(): TV.setUpModule()

def _directed(rows=ROWS):
    ss = TV.sentences([r[0] for r in rows])
    for s, r in zip(ss, rows): s.update(look=r[1], prompt=r[2], muscle=r[3], chapter=r[4])
    scenes = B.plan(ss)["scenes"]; logs = []
    stat = DR.apply(scenes, ss, log=logs.append); V.direct(scenes, three_d=True, flow=True)
    return ss, scenes, stat, logs

def _scene_of(scenes, text):
    return next(sc for sc in scenes if sc["text"].startswith(text.split(",")[0]))

class Direction(unittest.TestCase):
    def test_each_directed_row_gets_the_look_it_asks_for(self):
        _ss, scenes, stat, _logs = _directed()
        want = {0: "3d", 1: "takeaway", 2: "versus", 3: "flow", 4: "stock", 5: "stat", 7: "3d"}
        for i, look in want.items():
            sc = _scene_of(scenes, ROWS[i][0])
            self.assertEqual(sc["look"], look, ROWS[i][0]); self.assertTrue(sc["directed_look"])
        self.assertEqual(_scene_of(scenes, ROWS[2][0])["kind"], "versus")      # the planner's cut at the comma is joined back: the comparison is read whole
        self.assertEqual(stat["directed"], 7); self.assertEqual(stat["shared"], 0)

    def test_a_look_the_sentence_cannot_support_is_reported_not_faked(self):
        ss, scenes, stat, logs = _directed()
        self.assertEqual(stat["not_buildable"], 1)
        self.assertTrue(any("row 7: look steps" in m for m in logs))
        self.assertNotEqual(_scene_of(scenes, ROWS[6][0]).get("kind"), "steps")
        self.assertTrue(any("muscle 'banana'" in m for m in DR.check_rows(ss)))

    def test_chapters_label_the_sections(self):
        _ss, scenes, _stat, _logs = _directed()
        self.assertEqual(_scene_of(scenes, ROWS[0][0])["section"], "GRIP")
        self.assertEqual(_scene_of(scenes, ROWS[5][0])["section"], "CORE")

    def test_flow_picture_uses_the_rows_prompt_and_only_where_asked(self):
        _ss, scenes, _stat, _logs = _directed()
        want: list = []; BA.prepare(scenes, collect=want, directed=True)
        by_no = {w["no"]: w["prompt"] for w in want}
        plank = _scene_of(scenes, ROWS[3][0])
        self.assertTrue(by_no[plank["no"]].startswith("the trainee holding a plank, side view"))
        for i in (0, 1, 2, 4, 5, 7): self.assertNotIn(_scene_of(scenes, ROWS[i][0])["no"], by_no, ROWS[i][0])

    def test_3d_clip_shows_the_rows_muscle_and_only_where_asked(self):
        _ss, scenes, _stat, _logs = _directed()
        seen = []
        def fake_clip(text, seconds, **kw): seen.append(text); return None
        real = C3.clip_for; C3.clip_for = fake_clip
        try: C3.prepare(scenes, directed=True)
        finally: C3.clip_for = real
        self.assertIn("forearms", seen)                                       # the muscle column, not the sentence
        self.assertIn(ROWS[7][0], seen)                                       # an unknown muscle: the sentence's own lats
        self.assertEqual(len(seen), 2)                                        # "Keep your core tight" names a muscle but asked for a Flow picture

    def test_directed_scenes_draw(self):
        _ss, scenes, _stat, _logs = _directed(); ctx = D.Ctx(1280, 720)
        for sc in scenes:
            for t in (sc["start"] + 0.05, (sc["start"] + sc["end"]) / 2, sc["end"] - 0.05): S.frame(ctx, sc, t, tag=False)

    def test_csv_without_direction_plans_as_before(self):
        ss = TV.sentences([r[0] for r in ROWS])
        self.assertFalse(DR.has_direction(ss))
        for s in ss: s.update(look="", prompt="", muscle="", chapter="")
        self.assertFalse(DR.has_direction(ss))

    def test_prompt_example_uses_the_columns(self):
        text = A.prompt_text(); csv_text = re.search(r"CSV:\n(.*?)\n\nSCRIPT", text, re.S).group(1).strip()
        self.assertTrue(csv_text.startswith("text,chapter,look,prompt,muscle\n"))
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f: f.write(csv_text)
        rows = A.read_scenes_file(f.name)
        self.assertEqual([DR._row_look(r) for r in rows], ["3d", "stat", "flow"])
        self.assertEqual(DR.check_rows(rows), [])

if __name__ == "__main__":
    unittest.main()
