"""War Documentary broadcast overlays (war/broadcast.py, reference templates T1-T4): source tag, keyword label, caption box, big figure."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.render import Layer
from cinematic_explainer.war import broadcast as B
from cinematic_explainer.war import planner


class CardTests(unittest.TestCase):
    def test_cards_draw_and_refuse_empty(self):
        for fn, p in ((B.bc_source, {"text": "CNN"}), (B.bc_label, {"text": "44 missiles", "sub": "overnight"}),
                      (B.bc_caption, {"text": "the depot burned for two days", "quote": True}), (B.bc_bigword, {"text": "1 percent", "accent": "red"})):
            for t in (0.05, 1.0, 2.9):
                im = fn(t, 3.0, p)
                self.assertEqual(im.size, (1280, 720))
            self.assertIsNone(fn(1.0, 3.0, {}))
        self.assertGreater(B.bc_label(1.0, 3.0, {"text": "x"}).getchannel("A").getbbox()[2], 0)

    def test_source_text_only_for_recorded_outside_sources(self):
        self.assertEqual(B.source_text({"provider": "youtube", "channel": "CNN"}), "CNN")
        self.assertEqual(B.source_text({"provider": "youtube", "channel": "@ShaunPinnerUA"}), "X | @ShaunPinnerUA")
        self.assertEqual(B.source_text({"provider": "pexels", "author": "Jane"}), "")           # stock: no news source tag
        self.assertEqual(B.source_text({"provider": "youtube", "channel": "CNN", "user_supplied": True}), "")
        self.assertEqual(B.source_text({"provider": "youtube", "channel": "x", "ai_generated": True}), "")
        self.assertEqual(B.source_text({}), "")


class PlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = str(Path(cls.tmp.name, "c.mp4"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=10", "-r", "25", cls.clip], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _plan(self, texts, footage=True, meta=None):
        sc, t = [], 0.0
        for i, x in enumerate(texts):
            sc.append({"text": x, "start": t, "end": t + 7.0, "scene_no": i + 1, "footage": self.clip if footage else None,
                       "footage_meta": dict(meta or {})})
            t += 7.0
        return planner.plan(sc, config={})

    def test_marks_land_on_footage_from_the_narration(self):
        p = self._plan(["The night began quietly over the capital.",
                        "Officials said the depot had burned for two full days afterwards.",
                        "Rescue crews worked on through the night and into the day."],
                       meta={"provider": "youtube", "channel": "Reuters"})
        src = [ly for ly in p.layers if ly.kind == "bc_source"]
        self.assertTrue(src and all(ly.params["text"] == "Reuters" for ly in src))
        cap = [ly for ly in p.layers if ly.kind == "bc_caption"]
        self.assertTrue(cap and "DEPOT" in cap[0].params["text"].upper())
        self.assertGreaterEqual(cap[0].start, 7.0)                       # on its own sentence

    def test_label_and_big_figure_builders(self):
        from cinematic_explainer.war import catalog as C, semantics as S
        t = "Russia fired 44 missiles and 280 drones overnight."
        self.assertEqual(B._label_of(S.analyze_scene(t, C, None, 0, 5).sentences[0], t)[0], "44 MISSILES")
        t = "They had burned for two full days."
        self.assertIsNone(B._label_of(S.analyze_scene(t, C, None, 0, 5).sentences[0], t))
        t = "America approved 2.1 billion dollars of interceptors."
        self.assertEqual(B._bigword_of(S.analyze_scene(t, C, None, 0, 5).sentences[0])[0], "2.1 BILLION DOLLARS")
        t = "Reserves are down to their last 1% of shells."
        self.assertEqual(B._bigword_of(S.analyze_scene(t, C, None, 0, 5).sentences[0])[0], "1 PERCENT")

    def test_status_chip_drops_the_name_the_source_tag_shows(self):
        from cinematic_explainer.render import Shot
        from cinematic_explainer.war import catalog as C

        class P:
            pass
        P.shots = [Shot(self.clip, 0.0, 8.0, 0.0)]
        P.layers = [Layer("status_chip", 0.3, 6.0, {"status": "unverified", "text": "UNVERIFIED · CNN"}, dim=False)]
        rows = [{"_start": 0.0, "_end": 8.0, "_no": 1, "text": "Crowds gathered.", "footage": self.clip,
                 "footage_meta": {"provider": "youtube", "channel": "CNN"}}]
        B.apply(P, rows, {}, C)
        self.assertEqual(P.layers[0].params["text"], "UNVERIFIED")

    def test_never_without_footage(self):
        p = self._plan(["Russia fired 44 Iskander-M missiles at the grid before dawn."], footage=False)
        self.assertFalse([ly for ly in p.layers if ly.kind.startswith("bc_")])

    def test_never_over_a_full_frame_card(self):
        class P:
            shots = []
        from cinematic_explainer.render import Shot
        P.shots = [Shot(self.clip, 0.0, 10.0, 0.0)]
        P.layers = [Layer("tac_map", 0.0, 10.0, {}, dim=False)]
        rows = [{"_start": 0.0, "_end": 10.0, "_no": 1, "text": "Russia fired 44 Iskander-M missiles.", "footage": self.clip,
                 "footage_meta": {"provider": "youtube", "channel": "CNN"}}]
        from cinematic_explainer.war import catalog as C
        res = B.apply(P, rows, {}, C)
        self.assertEqual(sum(res.values()), 0)


if __name__ == "__main__":
    unittest.main()
