"""War Documentary story pass (cinematic_explainer/war/story.py): the cold-open montage hook and cards inside long map runs."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import catalog as C
from cinematic_explainer.war import planner
from cinematic_explainer.war import story as ST


def scenes(rows, clips):
    t, out = 0.0, []
    for i, (txt, g, clip) in enumerate(rows):
        out.append({"text": txt, "start": t, "end": t + 6.0, "scene_no": i + 1, "graphic": g, "footage": clip, "footage_meta": {}})
        t += 6.0
    return out


class P:
    def __init__(self, shots, layers):
        self.shots, self.layers, self.log = list(shots), list(layers), []


class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clips = []
        for i in range(6):
            c = str(Path(cls.tmp.name, f"c{i}.mp4"))
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x{20 * i + 30:02x}4060:s=320x180:d=8", "-r", "25", c], check=True)
            cls.clips.append(c)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_text_opening_without_footage_becomes_a_montage(self):
        rows = [("This is how the map of Ukraine changed in three years.", "title", None),
                ("On 24 February 2022, Russian forces invaded Ukraine.", "date", None)] + \
               [(f"Fighting continued for a long time in scene {i}.", "", self.clips[i]) for i in range(6)]
        plan = planner.plan(scenes(rows, self.clips), config={})
        early = [s for s in plan.shots if s.start < 12.0]
        self.assertGreaterEqual(len(early), 4)                                # a teaser of cuts, not one held clip
        self.assertGreaterEqual(len({s.path for s in early}), 3)              # different clips: a teaser
        from cinematic_explainer.war import direction as D
        full = [ly for ly in plan.layers if D._opaque(ly)]
        for s in early:                                                       # calm: no clip on screen for a split second (owner, 2026-11-09)
            seen = s.end - s.start - sum(max(0.0, min(s.end, ly.end) - max(s.start, ly.start)) for ly in full)
            self.assertTrue(seen < 0.05 or seen >= 1.99, (s.start, s.end, seen))
        self.assertAlmostEqual(min(s.start for s in plan.shots), 0.0)         # footage from the first frame
        for ly in plan.layers:
            if ly.kind in ("kit_title", "kit_datecard") and ly.start < 12:
                self.assertTrue(ly.params.get("over"), ly.kind)               # the words play over the montage
                self.assertLessEqual(ly.end - ly.start, ST.OPENER_MAX_S + 0.01)
        self.assertGreater(plan.stats["direction"]["story"]["hook"]["montage_cuts"], 0)

    def test_opening_with_its_own_footage_is_left_alone(self):
        rows = [("This is how the map of Ukraine changed in three years.", "title", self.clips[0])] + \
               [(f"Fighting continued for a long time in scene {i}.", "", self.clips[i]) for i in range(1, 6)]
        plan = planner.plan(scenes(rows, self.clips), config={})
        self.assertEqual(plan.stats["direction"]["story"]["hook"]["montage_cuts"], 0)

    def test_tail_of_a_long_shot_is_kept(self):
        plan = P([Shot(self.clips[1], 2.0, 20.0, 0.0)] + [Shot(self.clips[i], 20.0 + 3 * i, 23.0 + 3 * i, 0.0) for i in range(2, 6)],
                 [Layer("kit_title", 0.0, 4.0, {"text": "x"}, dim=False)])
        rows = [{"_start": 0.0, "_end": 2.0, "text": "a", "_no": 1}, {"_start": 2.0, "_end": 20.0, "text": "b", "_no": 2}]
        ST.hook(plan, rows, {})
        self.assertTrue(any(s.path == self.clips[1] and s.start >= 1.99 for s in plan.shots))


class RhythmTests(unittest.TestCase):
    def _run(self, texts):
        rows, layers, t = [], [], 0.0
        for i, (txt, place) in enumerate(texts):
            rows.append({"_start": t, "_end": t + 6.0, "text": txt, "_no": i + 1, "words": None})
            layers.append(Layer("tac_map", t, t + 6.0, {"theme": "tactical", "places": [{"name": place}]}, dim=False))
            t += 6.0
        plan = P([], layers)
        return plan, ST.map_rhythm(plan, rows, C, {})

    def test_date_card_then_map_keeps_the_maps_clock(self):
        plan, res = self._run([("In May 2023, after many months of brutal fighting, Russian forces captured Bakhmut.", "Bakhmut"),
                               ("In February 2024, after a long siege, Russian forces captured Avdiivka.", "Avdiivka"),
                               ("In November 2022, Russian troops withdrew from Kherson.", "Kherson")])
        self.assertGreater(res["date_cards"], 0)
        dc = [ly for ly in plan.layers if ly.kind == "kit_datecard"]
        self.assertEqual(dc[0].params["date"], "May 2023")
        m = next(ly for ly in plan.layers if ly.kind == "tac_map")
        self.assertGreater(m.params["t_offset"], 0.0)                         # pins still land on their words
        self.assertAlmostEqual(m.params["total_dur"], 6.0, places=2)

    def test_short_runs_untouched(self):
        plan, res = self._run([("Fighting moved to Bakhmut.", "Bakhmut")])
        self.assertEqual(res, {"date_cards": 0, "tail_cards": 0})


if __name__ == "__main__":
    unittest.main()


class FindTheGraphicsTests(unittest.TestCase):
    def test_graphics_index_lists_each_graphic_with_its_time(self):
        from cinematic_explainer.war.integration import graphics_index
        txt = graphics_index([Layer("kit_chart", 65.0, 70.0, {}, dim=False), Layer("kit_grain", 0, 99, {}, dim=False),
                              Layer("tac_map", 12.0, 18.0, {"control": [{"place": "Avdiivka"}]}, dim=False)])
        self.assertIn("0:12  Tactical / political map (tac_map)  6.0 s  [capture]", txt)
        self.assertIn("1:05  Animated chart (kit_chart)", txt)
        self.assertNotIn("kit_grain", txt)
        self.assertIn("2 kinds used", txt)

    def test_known_person_over_footage_gets_a_name_card(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        clip = str(Path(tmp.name, "c.mp4"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=8", "-r", "25", clip], check=True)
        sc = [{"text": "Crowds gathered in the square that morning.", "start": 0.0, "end": 6.0, "scene_no": 1, "footage": clip, "footage_meta": {}},
              {"text": "Later that week Zelensky visited soldiers near the front.", "start": 6.0, "end": 12.0, "scene_no": 2, "footage": clip,
               "footage_meta": {}}]
        plan = planner.plan(sc, config={})
        cards = [ly for ly in plan.layers if ly.kind == "kit_speaker"]
        self.assertTrue(cards)
        self.assertEqual(cards[0].params, {"name": "Volodymyr Zelensky", "role": "President of Ukraine"})
