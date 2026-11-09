"""War Documentary: pictures that follow the narration, no colour burn, no overlapping (2026-11-09 reference re-check, section 10).

Synthetic sentences only: each rule is checked on its own, never tuned to one video.
"""

import unittest
from types import SimpleNamespace

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import direction as D
from cinematic_explainer.war import engagement as E
from cinematic_explainer.war import planner as P
from cinematic_explainer.war import segments as SG
from cinematic_explainer.war import semantics as S
from cinematic_explainer.war import subjects as SJ

CAT = P._default_catalog()


def _cite(text):
    s = S.analyze_scene(text, CAT, None, 0.0, 5.0).sentences[0]
    return s.citation.outlet if s.citation else None


class Citations(unittest.TestCase):
    def test_reporting_verbs_and_adverbs(self):
        self.assertEqual(_cite("AP noted that strikes hit the units that clean fuel."), "AP")
        self.assertEqual(_cite("Euromaidan Press counted it as the fifth refinery hit."), "Euromaidan Press")
        self.assertEqual(_cite("Reuters also said three refineries had cut output."), "Reuters")
        self.assertEqual(_cite("The IEA estimated that exports fell."), "IEA")

    def test_no_source_no_citation(self):
        self.assertIsNone(_cite("First, the strikes now reach deep into Russia."))
        self.assertIsNone(_cite("Second, Russians are feeling it."))

    def test_claim_noun_is_claim_wording(self):
        self.assertTrue(D._CLAIM.search("but the 51 percent figure is Ukraine's own claim."))
        self.assertTrue(D._CLAIM.search("Moscow repeated its claim on Monday."))
        self.assertFalse(D._CLAIM.search("The plant was hit again in October."))


def _row(no, text, start, end, footage=None, meta=None):
    return {"_no": no, "text": text, "_start": start, "_end": end, "footage": footage, "footage_meta": meta or {}, "words": None}


class SubjectPortraits(unittest.TestCase):
    def _run(self, rows, layers=None, portrait="putin.jpg", fits=lambda m: bool(m.get("csv_pick"))):
        plan = SimpleNamespace(layers=list(layers or []), shots=[])
        n = SJ.apply(plan, rows, CAT, {}, {}, set(D.FULL_KINDS), fits, portrait=lambda e: portrait)
        return n, plan

    def test_sentence_about_a_person_shows_them(self):
        n, plan = self._run([_row(1, "Putin could not break Ukraine in the trenches, so he turned to the power grid.", 0.0, 5.0, "clip.mp4")])
        self.assertEqual(n, 1)
        ly = plan.layers[0]
        self.assertEqual(ly.kind, "lay_figure_hero")
        self.assertEqual(ly.params["name"], "Vladimir Putin")
        self.assertEqual(ly.params["statement"], "")          # the narration is never put in his mouth
        self.assertLessEqual(ly.end - ly.start, SJ.MAX_S + 0.01)

    def test_passing_mention_is_not_the_subject(self):
        n, _ = self._run([_row(1, "Three refineries near the border were hit overnight, weeks after a speech by Putin.", 0.0, 5.0)])
        self.assertEqual(n, 0)

    def test_fitting_clip_keeps_the_screen(self):
        n, _ = self._run([_row(1, "Putin could not break Ukraine in the trenches.", 0.0, 4.0, "clip.mp4", {"csv_pick": True})])
        self.assertEqual(n, 0)

    def test_no_verified_portrait_no_card(self):
        n, _ = self._run([_row(1, "Putin could not break Ukraine in the trenches.", 0.0, 4.0)], portrait=None)
        self.assertEqual(n, 0)

    def test_never_over_a_full_graphic_and_not_twice_in_a_row(self):
        n, _ = self._run([_row(1, "Putin could not break Ukraine in the trenches.", 0.0, 4.0)],
                         layers=[Layer("tac_map", 0.0, 5.0, {}, dim=False)])
        self.assertEqual(n, 0)
        n, plan = self._run([_row(1, "Putin could not break Ukraine in the trenches.", 0.0, 4.0),
                             _row(2, "Putin then turned his missiles on the grid again.", 10.0, 14.0)])
        self.assertEqual(n, 1)                               # the same face again within 45 s keeps the clip


class LookAndCuts(unittest.TestCase):
    def test_no_crushing_grade(self):
        for g in ("film", "cold", "warm_archive"):
            f = SG._grade_filters(g)
            self.assertNotIn("gamma=0.9", f, g)              # gamma below 1 darkened every shadow
            self.assertNotIn("contrast=1.08", f, g)
        self.assertGreaterEqual(SG.DIM_BRIGHTNESS, 0.45)     # the footage behind a card is dimmed, never near-black
        self.assertGreaterEqual(SG.DIM_SHRINK, 24)           # and too blurred for burned-in words to be read

    def test_card_blacks_are_lifted_by_their_own_opacity(self):
        from PIL import Image

        im = Image.new("RGBA", (40, 10), (0, 0, 0, 0))
        im.paste((0, 0, 0, 255), (0, 0, 20, 10))                 # a solid black plate on the left, nothing on the right
        out = SG.lift_blacks(im)
        self.assertGreaterEqual(out.getpixel((5, 5))[0], SG.CARD_BLACK_LIFT - 1)
        self.assertEqual(out.getpixel((30, 5))[3], 0)             # transparent stays transparent: the clip shows through untouched
        self.assertGreaterEqual(SG.lift_blacks(Image.new("RGBA", (4, 4), (255, 255, 255, 255))).getpixel((1, 1))[0], 254)

    def test_hard_cuts_by_default(self):
        plan = SimpleNamespace(shots=[Shot("a.mp4", 0.0, 4.0, 0.0), Shot("b.mp4", 4.0, 8.0, 0.0)], layers=[])
        D._treat_shots(plan, {}, [], [], {}, film=True)
        self.assertTrue(all(not getattr(s, "dissolve_in", 0.0) for s in plan.shots))
        D._treat_shots(plan, {}, [], [], {}, film=True, dissolves=True)
        self.assertEqual(plan.shots[1].dissolve_in, 0.4)


class NoOverlapNoDoubleWords(unittest.TestCase):
    def test_percent_label_says_percent_once(self):
        from cinematic_explainer.war import broadcast as B

        for text, want in (("but the 51 percent figure is Ukraine's own claim.", "51 PERCENT"), ("Prices rose 19% this year.", "19 PERCENT"),
                           ("Exports fell 30 per cent.", "30 PERCENT")):
            sent = S.analyze_scene(text, CAT, None, 0.0, 5.0).sentences[0]
            self.assertEqual(B._label_of(sent, text)[0], want)

    def _stickers(self, layer):
        plan = SimpleNamespace(layers=[layer], shots=[])
        rows = [_row(1, "Reuters said diesel output fell at the refinery.", 0.0, 6.0, "clip.mp4")]
        D._choose_layouts(plan, rows, CAT, {}, {})
        return [ly for ly in plan.layers if ly.kind == "kit_sticker"]

    def test_claim_panel_sticker_sits_below_its_stamp(self):
        st = self._stickers(Layer("lay_claim", 0.0, 6.0, {"claim": "x", "claimant": "Reuters"}, dim=True))
        self.assertEqual(len(st), 1)
        self.assertGreaterEqual(st[0].params["y"], 0.6)                   # the stamp is drawn at about 0.35 of the height
        self.assertLessEqual(st[0].params["size"], 240)

    def test_no_sticker_where_the_layout_has_its_own_panel(self):
        self.assertEqual(self._stickers(Layer("lay_stat_split", 0.0, 6.0, {"value": 5, "text": "What it means ..."}, dim=True)), [])
        self.assertEqual(self._stickers(Layer("lay_claim", 0.0, 6.0, {"claim": "x", "confirmed": ["a"]}, dim=True)), [])


class EngagementCountsWhatIsSeen(unittest.TestCase):
    def test_hidden_cut_and_run_on_split_are_not_changes(self):
        shots = [Shot("a.mp4", 0.0, 6.0, 0.0), Shot("a.mp4", 6.0, 12.0, 6.0),      # the same clip running on across a split: no cut
                 Shot("b.mp4", 12.0, 18.0, 0.0), Shot("c.mp4", 15.0, 18.0, 0.0)]    # c starts under the map: not seen
        plan = SimpleNamespace(shots=shots, layers=[Layer("tac_map", 14.0, 18.0, {}, dim=False)])
        seen = [c for c in (0.0, 6.0, 12.0, 14.0, 15.0) if c <= 0.0 or E._seen_at(plan, c - 0.02) != E._seen_at(plan, c + 0.02)]
        self.assertEqual(seen, [0.0, 12.0, 14.0])


if __name__ == "__main__":
    unittest.main()
