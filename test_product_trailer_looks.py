"""The three Review looks: mixed 3D sits in the bright daylight studio with the phone whole beside its text; infographic stays on the paper (3D kinds
drawn flat); news is footage first (YouTube runs by subject from a fake backend, cards only for figures / documents / quotes, no subtitles).
S27-family flat phones get the camera-bar back. Synthetic data, no network."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from product_trailer import director, news_footage as NF, review, studio

PHONE = "Galaxy S27 Ultra"
SCRIPT = "\n".join(["Samsung's next Ultra may have lost a camera.", "First, the design.", "The leak shows a horizontal camera bar on the back of the phone today.",
                    "Third, the battery.", "The S26 Ultra has 5,000 mAh, so that's about 700 mAh more.", "Tell me in the comments what you think."])


class Mixed(unittest.TestCase):
    def test_callouts_sit_in_the_bright_studio_with_safe_moves(self):
        shot, make, _ = review.feature_visual({"kind": "callout", "kicker": "First", "value": "Design", "sub": "", "feature": "design", "look": ""}, PHONE, 0)
        self.assertEqual(shot["backdrop"], "daylight")
        self.assertIn(shot["move"], review.TEXT_SAFE_MOVES)
        self.assertEqual(make(0, 3)[0]["ink"], "dark")
        wash, _, _ = review.feature_visual({"kind": "feature", "feature": "display", "kicker": "", "value": "Privacy", "sub": "x", "look": "wash:purple"}, PHONE, 1)
        self.assertEqual(wash["backdrop"], "wash")                  # a CSV wash look is kept

    def test_filler_and_rooms_are_bright(self):
        self.assertEqual(review._filler_shot(PHONE, ["Black"], 0, ["edge"])["backdrop"], "daylight")
        self.assertTrue(set(review.ROOMS) <= {"gallery", "loft", "terrace"})
        self.assertEqual(review.parse_script("[lineup: Colours | desk]\nThe colours.")["chapters"][0]["items"][0]["room"], "desk")   # an author's room still works


class Infographic(unittest.TestCase):
    def test_everything_stays_on_paper(self):
        with tempfile.TemporaryDirectory() as d:
            r = studio.plan_film("Review", out_dir=d, script=SCRIPT, phone=PHONE, style="infographic", disclaimer_on=False, subtitles=False)
            spec = json.loads(Path(r["spec_path"]).read_text())
        self.assertFalse([s for s in spec["shots"] if s["kind"] == "product"])
        self.assertNotIn("pt_subtitle", {L["type"] for L in spec["layers"]})
        bars = [p for L in spec["layers"] if L["type"] == "pt_flatphones" for p in L["phones"] if p.get("design") == "bar"]
        self.assertTrue(bars)

    def test_bar_back_only_for_the_films_family(self):
        spec = {"layers": [{"type": "pt_flatphones", "phones": [{"label": "Galaxy S26 Ultra"}, {"label": "Galaxy S27 Ultra"}, {"label": "iPhone 18 Pro"}, {"label": ""}]}]}
        studio.bar_phones(spec, PHONE)
        self.assertEqual([p.get("design") for p in spec["layers"][0]["phones"]], [None, "bar", None, "bar"])


class FakeBackend:
    def search(self, q, n):
        return [SimpleNamespace(video_id=f"v{i}{len(q)}", url="", title=f"Galaxy S27 Ultra {q} {i}", channel="c", duration=600) for i in range(4)]


class News(unittest.TestCase):
    def test_beats_are_footage_with_cards_only_for_figures(self):
        parsed = review.news_beats(director.auto_direct(review.parse_script(SCRIPT), PHONE))
        items = [it for ch in parsed["chapters"] for it in ch["items"]]
        self.assertFalse([it for it in items if it["kind"] in ("callout", "macro", "lineup", "chip", "xray")])
        self.assertTrue(any(it["kind"] == "scene" for it in items))                       # the battery before/after card stays
        foot = [it for it in items if it["kind"] == "footage"]
        self.assertGreaterEqual(len(foot), 5)
        self.assertIn("battery", {it["topic"] for it in foot})

    def test_resolve_cuts_runs_by_subject_and_caches(self):
        parsed = review.news_beats(director.auto_direct(review.parse_script(SCRIPT), PHONE))
        with tempfile.TemporaryDirectory() as d:
            def direct(c, start, length, dest):
                Path(dest).write_bytes(b"x" * 2000)
                return True

            def cut(src, a, z, dest):
                Path(dest).write_bytes(b"x" * 2000)
                return True
            from weather.newsdoc import harvest as H
            with mock.patch.object(H, "_direct", direct), mock.patch.object(H, "_cut", cut), mock.patch.object(H, "scene_cuts", lambda p: [2.5, 5.0, 8.0]), \
                    mock.patch.object(H, "media_seconds", lambda p: 30.0), mock.patch.object(H, "usable", lambda p, w=1.0: Path(p).is_file()), \
                    mock.patch.object(NF.time, "sleep", lambda s: None):
                got = NF.resolve(parsed, d, PHONE, backend=FakeBackend(), log=lambda m: None)
                self.assertEqual(got["missing"], 0)
                self.assertGreater(got["runs"], 10)
                paths = [it["path"] for ch in parsed["chapters"] for it in ch["items"] if it.get("kind") == "footage"]
                self.assertEqual(len(paths), len(set(paths)))                              # no run twice while others are unused
                again = review.news_beats(director.auto_direct(review.parse_script(SCRIPT), PHONE))
                self.assertIn("cache", " ".join(NF.resolve(again, d, PHONE, backend=None, log=lambda m: None)["notes"]))

    def test_titles_must_name_the_phone(self):
        c = [SimpleNamespace(video_id="a", title="Pixel 10 review", duration=600), SimpleNamespace(video_id="b", title="Galaxy S27 Ultra dummy", duration=600),
             SimpleNamespace(video_id="c", title="S27 Ultra LIVE stream", duration=600)]
        self.assertEqual([x.video_id for x in NF._pick(c, "S27", set())], ["b"])
        self.assertEqual(NF.queries({"chapters": [{"items": [{"kind": "footage", "topic": "price"}]}]}, PHONE)["price"], "Galaxy S26 Ultra hands on")


if __name__ == "__main__":
    unittest.main()
