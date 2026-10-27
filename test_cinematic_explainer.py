"""Cinematic Explainer Phase 1: cards are deterministic and inside the frame, motion matches the measured reference, the pack is isolated."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from cinematic_explainer import cards, demo, look as L
from cinematic_explainer.render import Layer, Shot, dim_spans, filter_graph, render

ROOT = Path(__file__).resolve().parent


def _h(img):
    return hashlib.sha1(img.tobytes()).hexdigest()


def _params():
    return {
        "source": {"outlet": "Example Source", "date": "12 October", "words": demo.SOURCE_WORDS, "times": demo.SOURCE_TIMES, "mark": demo.SOURCE_MARK},
        "number": {"value": 5, "prefix": "×", "label": "More than before", "sub": "fixture"},
        "list": {"title": "Three questions", "items": ["a", "b", "c"], "times": [0.6, 1.9, 3.2]},
        "portrait": {"image": demo.placeholder_portrait(), "name": "Sample", "role": "Placeholder"},
        "kicker": {"text": "Sample"}, "shot_head": {"text": "Sample headline"},
    }


class CardTests(unittest.TestCase):
    def test_deterministic(self):
        for kind, p in _params().items():
            a = cards.CARDS[kind](2.0, 5.0, p)
            b = cards.CARDS[kind](2.0, 5.0, p)
            self.assertEqual(_h(a), _h(b), kind)

    def test_inside_frame_and_not_blank_when_settled(self):
        for kind, p in _params().items():
            img = cards.CARDS[kind](3.0, 5.0, p)
            self.assertEqual(img.size, (L.W, L.H))
            box = img.getchannel("A").getbbox()
            self.assertIsNotNone(box, kind)
            x0, y0, x1, y1 = box
            self.assertTrue(x0 >= 0 and y0 >= 0 and x1 <= L.W and y1 <= L.H, kind)
            if kind != "shot_head":   # the lower third sits at the bottom by design
                self.assertLess(y1, L.H - 20, kind)

    def test_fade_in_and_out(self):
        p = _params()["number"]
        self.assertIsNone(cards.number(0.0, 5.0, p).getchannel("A").getbbox())          # nothing at t = 0
        self.assertIsNotNone(cards.number(2.5, 5.0, p).getchannel("A").getbbox())
        end = cards.number(4.99, 5.0, p).getchannel("A").getextrema()[1]
        mid = cards.number(2.5, 5.0, p).getchannel("A").getextrema()[1]
        self.assertLess(end, mid)

    def test_number_counts_up_in_the_measured_time(self):
        # reference A: the figure reaches its value in about 0.4 s after a 0.15 s start
        self.assertLess(L.COUNT_S, 0.5)
        seen = [_h(cards.number(t, 5.0, _params()["number"])) for t in (0.1, 0.25, 0.35, 0.45, 0.6, 1.0)]
        self.assertNotEqual(seen[1], seen[2])          # still changing mid-count
        self.assertEqual(_h(cards.number(1.6, 9.0, _params()["number"])), _h(cards.number(2.4, 9.0, _params()["number"])))  # settled and still

    def test_source_words_darken_in_narration_order(self):
        p = _params()["source"]
        early = cards.source(1.0, 6.0, p)
        late = cards.source(3.0, 6.0, p)
        self.assertNotEqual(_h(early), _h(late))
        # at 1.0 s only the first words are said: the card still has ghost (grey) text and no highlighter yellow
        yellow = lambda im: sum(1 for px in im.getdata() if px[0] > 240 and 190 < px[1] < 230 and px[2] < 40 and px[3] > 200)
        self.assertEqual(yellow(early), 0)
        self.assertGreater(yellow(late), 500)

    def test_list_rows_follow_item_times(self):
        p = _params()["list"]
        counts = [cards.list_card(t, 6.0, p).getchannel("A").getbbox()[3] for t in (0.4, 1.2, 2.4, 3.8)]
        self.assertEqual(counts, sorted(counts))
        self.assertLess(counts[0], counts[-1])

    def test_portrait_without_image_shows_nothing(self):
        self.assertIsNone(cards.portrait(2.0, 5.0, {"image": None, "name": "X", "role": "Y"}))


class TimelineTests(unittest.TestCase):
    def test_dim_spans_merge(self):
        ls = [Layer("source", 5.0, 8.0, dim=True), Layer("number", 8.1, 10.0, dim=True), Layer("list", 14.0, 16.0, dim=True), Layer("kicker", 1.0, 2.0)]
        self.assertEqual(dim_spans(ls), [(5.0, 10.0), (14.0, 16.0)])

    def test_filter_graph_has_no_per_pixel_expression(self):
        shots, layers = demo.timeline()
        g = filter_graph(shots, layers)
        self.assertNotIn("all_expr", g)
        self.assertEqual(g.count("overlay=enable"), len(dim_spans(layers)))

    def test_demo_layers_do_not_overlap_cards_of_the_same_kind(self):
        _, layers = demo.timeline()
        big = [ly for ly in layers if ly.kind in ("source", "number", "list", "portrait")]
        for a, b in zip(big, big[1:]):
            self.assertLessEqual(a.end, b.start)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg needed")
class RenderTests(unittest.TestCase):
    def test_short_render_has_exact_length_and_no_blank_frames(self):
        from war_test_media import clip   # Images/ is not in git: generated stand-ins on CI
        shots = [Shot(clip("008.mp4"), 0.0, 2.0), Shot(clip("013.mp4"), 2.0, 4.0, seek=1.0)]
        layers = [Layer("kicker", 2.2, 3.8, {"text": "Test"}), Layer("number", 2.2, 3.8, {"value": 5, "label": "x", "sub": ""}, dim=True)]
        with tempfile.TemporaryDirectory() as td:
            out = str(Path(td) / "t.mp4")
            stats = render(shots, layers, out)
            self.assertEqual(stats["frames"], 100)
            n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
                                "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip()
            self.assertEqual(int(n), 100)
            for t in (0.0, 1.0, 1.96, 2.0, 2.1, 3.0, 3.96):   # the cut at 2.0 s and the dim ramp: never a black or missing frame
                p = Path(td) / f"f{t}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", out, "-frames:v", "1", "-vf", "scale=64:36", str(p)], check=True)
                im = Image.open(p).convert("L")
                self.assertGreater(sum(im.getdata()) / (64 * 36), 6, t)


class IsolationTests(unittest.TestCase):
    def test_existing_doc_style_untouched(self):
        from graphics import doc_looks
        keys = set(doc_looks.LOOKS)
        import cinematic_explainer  # noqa: F401
        self.assertEqual(keys, set(doc_looks.LOOKS))
        self.assertNotIn("source", doc_looks.LOOKS)

    def test_nothing_outside_the_pack_imports_it(self):
        offenders = []
        for p in ROOT.glob("*.py"):
            if p.name == Path(__file__).name or p.name.startswith("test_war_"):
                continue   # the pack's own tests (the war package lives inside cinematic_explainer/)
            if p.name == "app.py":   # the one approved, additive style-picker hook: lazy imports only, never at module level
                text = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("\nimport cinematic_explainer", text)
                self.assertNotIn("\nfrom cinematic_explainer", text)
                continue
            if "cinematic_explainer" in p.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(p.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
