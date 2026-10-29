"""Venice-narration board defects: clipped title, junk text fragments, a cause-effect chain shown one node at a time."""
import unittest

from PIL import Image, ImageDraw

from explainer.board import render as RN
from explainer.board import theme as T
from explainer.director import compose_ref as CR
from explainer.director.segment import norm
from test_explainer_recipes import author, visuals


class TitleFits(unittest.TestCase):
    def test_wide_title_shrinks_inside_frame(self):
        text, cx = "RELYING ON AGRICULTURE", 1270
        px = RN.title_px(text, cx, T.THEME.title_px * 1.15, 8, lambda q: T.font("title", q))
        self.assertLess(px, T.THEME.title_px * 1.15)
        x0, _, x1, _ = ImageDraw.Draw(Image.new("L", (4, 4))).textbbox((cx, 0), text, font=T.font("title", px), anchor="mm", stroke_width=8)
        self.assertLessEqual(x1, 1920 - 70)

    def test_short_title_keeps_size(self):
        base = T.THEME.title_px * 1.15
        self.assertEqual(RN.title_px("LOST AT SEA", 1270, base, 8, lambda q: T.font("title", q)), base)


class JunkFragments(unittest.TestCase):
    def test_junk_text(self):
        for t in ("youll", "youll find the coast", "time", "the", "years"):
            self.assertTrue(CR._junk_text(t), t)
        for t in ("scattered communities", "Venice", "1204"):
            self.assertFalse(CR._junk_text(t), t)

    def test_cut_on_participle(self):
        words = [(w, i * 0.3, i * 0.3 + 0.2) for i, w in enumerate("venice had very little farmland limited natural resources".split())]
        idx = list(range(len(words)))
        self.assertTrue(CR._cut_on_participle("little farmland limited", idx, words))
        self.assertFalse(CR._cut_on_participle("little farmland limited natural resources", idx, words))

    def test_best_phrases_never_offers_contraction(self):
        words = [(w, i * 0.3, i * 0.3 + 0.2) for i, w in enumerate("and youll find the balkan coastline".split())]
        got = CR.best_phrases(list(range(len(words))), words, {}, {}, {5}, k=3, max_words=6, min_score=0.0, min_words=1)
        self.assertTrue(got)
        self.assertFalse(any("youll" in p.text for p in got))


class ChainShowsBothSides(unittest.TestCase):
    def test_effect_node_arrives_a_beat_after_the_cause(self):
        r, words, _ = author("Over time these scattered communities developed into a permanent settlement.", "cause")
        self.assertEqual(r.recipe, "cause_effect")
        nodes = visuals(r, "node")
        self.assertEqual(len(nodes), 2)
        t = [words[c.anchor["index"]][1] + (c.offset_s if c.offset_s is not None else 0.1) for c in nodes]
        self.assertLessEqual(t[1] - t[0], 1.1)
        for c in nodes:
            self.assertEqual(words[c.anchor["index"]][0], norm(c.text.split()[0]))        # still anchored on its own word
        arrow = next(c for c in r.cues if c.kind == "arrow")
        self.assertGreaterEqual(words[arrow.anchor["index"]][1] + arrow.offset_s, t[1] - 1e-6)


class ScarcityRecipe(unittest.TestCase):
    def test_a_lack_and_its_limit_become_a_two_node_chain(self):
        from explainer.director import compose_recipes as CRC
        sc = dict(CRC.pick_recipe("venice had very little farmland limited natural resources".split()))
        self.assertIn("scarcity", sc)
        self.assertNotIn("scarcity", dict(CRC.pick_recipe("there was little food".split())))


if __name__ == "__main__":
    unittest.main()


class RecipeSurvivesVariety(unittest.TestCase):
    """A recipe board (a relationship drawn as nodes and an arrow) is not swapped for the ordinary layout when the same layout family has appeared twice before."""

    def test_recipe_beat_kept_when_family_repeats(self):
        from types import SimpleNamespace
        from explainer.director.compose_variety import variety_pass
        br = SimpleNamespace(phrases=[{"as": "node"}], recipe="scarcity")
        b = SimpleNamespace(id="e3", start=0.0, end=3.0)
        hist = [("node",), ("node",)]
        out, _bg, rec = variety_pass(br, b, 2, [("x", 0.0, 0.5)], {}, SimpleNamespace(background="paper"), {}, {}, "none", "idle", hist, [])
        self.assertIs(out, br)
        self.assertIn("family_kept", rec)


class FirstNodeNotLate(unittest.TestCase):
    def test_first_node_is_on_paper_within_a_second_of_the_beat_start(self):
        r, words, _end = author("and over the long years these scattered communities developed into a permanent settlement")
        nodes = [c for c in r.cues if (c.params or {}).get("style") == "node"]
        self.assertGreaterEqual(len(nodes), 2)
        first = min(float(words[c.anchor["index"]][1]) + (c.offset_s or 0.0) for c in nodes)
        self.assertLessEqual(first, float(words[0][1]) + 1.0 + 1e-6, first)
