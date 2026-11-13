"""Aviation style: plan -> the War renderer's Shot / Layer lists, and one tiny real render through it."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from aviation import bridge as BR
from aviation import planner as P
from test_aviation_map import fake_tile
from test_aviation_planner import FLIGHT, NEWS, scenes


def _clip(path: Path, seconds: float = 3.0) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=30:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


class TimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = _clip(Path(cls.tmp.name) / "c.mp4", 4.0)
        cls.black = str(Path(cls.tmp.name) / "black.mp4")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, lines, pick=None, **kw):
        sc = scenes(lines)
        plan = P.plan(sc)
        pick = pick or (lambda slot: {"path": self.clip, "seek": 0.0, "source": "Euronews"})
        return BR.build_timeline(plan, sc, pick, black=self.black, map_extra={"fetch_tile": fake_tile, "cache": self.tmp.name}, **kw)

    def test_base_covers_the_whole_film(self):
        shots, layers, rep = self.build(NEWS + FLIGHT)
        t = 0.0
        for s in shots:
            self.assertAlmostEqual(s.start, t, places=6)
            t = s.end
        self.assertAlmostEqual(t, 40.0, places=6)

    def test_full_frame_cards_sit_on_black(self):
        shots, layers, rep = self.build(FLIGHT)
        maps = [ly for ly in layers if ly.kind == "flightmap.lay_flight_map"]
        self.assertTrue(maps)
        under = [s for s in shots if s.start <= maps[0].start < s.end]
        self.assertEqual(under[0].path, self.black)
        self.assertEqual(maps[0].params["fetch_tile"], fake_tile)

    def test_every_borrowed_clip_gets_a_source_tag(self):
        shots, layers, rep = self.build(NEWS)
        clips = [s for s in shots if s.path == self.clip]
        tags = [ly for ly in layers if ly.kind == "cards.tag_source"]
        self.assertEqual(len(tags), len(clips))
        self.assertEqual(tags[0].params["source"], "Euronews")

    def test_missing_clip_becomes_a_fact_card_not_black(self):
        shots, layers, rep = self.build([NEWS[0], NEWS[2]], pick=lambda slot: None)
        # a news line with no clip is a short sticker-stage beat (its aircraft + its own words), never a blue text-only card
        cards = [ly for ly in layers if ly.kind == "stage.lay_stage"]
        self.assertTrue(cards)
        self.assertFalse([ly for ly in layers if ly.kind == "cards.lay_article" and not (ly.params.get("video") or ly.params.get("page"))])
        self.assertTrue(all(any(e["kind"] == "caption" for e in ly.params["elements"]) for ly in cards))
        self.assertGreater(rep["missing_footage"], 0)
        covered = sum(ly.end - ly.start for ly in cards)
        self.assertAlmostEqual(covered, 8.0, places=6)

    def test_card_picture_comes_from_nearby_footage(self):
        shots, layers, rep = self.build(NEWS)
        card = [ly for ly in layers if ly.kind == "cards.lay_article"][0]
        self.assertEqual(card.params["video"], self.clip)

    def test_every_layer_kind_is_drawable(self):
        shots, layers, rep = self.build(NEWS + FLIGHT + ["This is the story of Vistara 944."])
        table = BR.card_table()
        for ly in layers:
            self.assertIn(ly.kind, table, ly.kind)


class SmokeRenderTest(unittest.TestCase):
    def test_tiny_render(self):
        from cinematic_explainer import render as RD

        with tempfile.TemporaryDirectory() as d:
            clip = _clip(Path(d) / "c.mp4", 3.0)
            sc = [{"scene_no": 1, "text": "Air France confirmed plans to cut 2,900 jobs in 2015.", "start": 0.0, "end": 2.0},
                  {"scene_no": 2, "text": "Vistara 611 takes off from Srinagar for Jammu with 4,900 kg of fuel.", "start": 2.0, "end": 4.0}]
            plan = P.plan(sc)
            shots, layers, rep = BR.build_timeline(plan, sc, lambda s: {"path": clip, "seek": 0.0, "source": "Test"},
                                                   black=str(Path(d) / "black.mp4"), map_extra={"fetch_tile": fake_tile, "cache": d})
            out = str(Path(d) / "out.mp4")
            RD.render(shots, layers, out, card_table=BR.card_table())
            dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]).strip())
            self.assertAlmostEqual(dur, 4.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()


class CardPictureTests(unittest.TestCase):
    def test_card_picture_is_its_own_scene_clip(self):
        with tempfile.TemporaryDirectory() as d:
            own, other = _clip(Path(d) / "own.mp4", 6.0), _clip(Path(d) / "other.mp4", 6.0)
            sc = [{"scene_no": 1, "text": "Air France confirmed plans to cut jobs.", "start": 0.0, "end": 4.0},
                  {"scene_no": 2, "text": "Air France launched Joon, a new airline with younger crews and lower costs.", "start": 4.0, "end": 14.0}]
            rows = [{}, {"mode": "news", "article": {"outlet": "Travel Weekly", "headline": "Air France launches Joon", "date": "2017"},
                         "queries": ["Joon"], "radio": [], "from": "", "to": "", "fuel": None, "time": "", "altitude": None}]
            plan = P.plan(sc, rows=rows)
            pick = lambda s: {"path": own if s.get("scene") == 2 else other, "seek": 0.0, "duration": 6.0}
            shots, layers, rep = BR.build_timeline(plan, sc, pick, black=str(Path(d) / "black.mp4"))
            card = [ly for ly in layers if ly.kind == "cards.lay_article"][0]
            self.assertEqual(card.params["video"], own)
