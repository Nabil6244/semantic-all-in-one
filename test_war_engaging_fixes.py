"""War Documentary: general fixes from the 'ahmed test' render review (2026-11-08). Synthetic inputs only; no timestamps or script of that video.

- a day of the month next to a month name is a date, never a big statistic ('October 26' showed as '26 IT SHOWED')
- two figures of one unit around a contrast word are one comparison; the stat card keeps its '%'
- a leader who claims / says / warns gets the portrait card, may open the video, and is not pushed out by a card just before
- another channel's map / commentary video, or a clip whose title gives a different area, is not used as footage
- the same wide country map at most once in CONTEXT_REPEAT_S
- the finished timeline has no bare backdrop, no clip flash between two graphics, no source chip without its footage
"""

import unittest
from types import SimpleNamespace

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import direction as D
from cinematic_explainer.war import footage_match as F
from cinematic_explainer.war import planner as P
from cinematic_explainer.war import semantics as S


class Numbers(unittest.TestCase):
    def test_day_of_month_is_a_date_not_a_statistic(self):
        for t in ("In the four weeks to October 26, it showed gains of about 47 square kilometers.",
                  "On 26 October the bridge was hit.", "By the 3rd of March, 12 tanks were lost."):
            nums, _ = S.find_numbers(t)
            self.assertNotIn(26.0, [n.value for n in nums if "October" in t])
            self.assertNotIn(3.0, [n.value for n in nums])
        nums, _ = S.find_numbers("Russia fired 26 drones on 26 October.")
        self.assertEqual([(n.value, n.unit) for n in nums], [(26.0, "drones")])     # the count stays, the day goes

    def test_two_percentages_around_a_contrast_are_a_comparison(self):
        c = S._comparison("Moscow says the army holds 10 percent of the region, but analysts put it at 20.4 percent.", 0)
        self.assertIsNotNone(c)
        self.assertEqual((c.a.value, c.b.value, c.a.unit), (10.0, 20.4, "%"))
        self.assertIsNone(S._comparison("The army holds 10 percent of the region and lost 40 tanks.", 0))

    def test_stat_card_draws_the_percent_sign(self):
        from cinematic_explainer.war import layouts as L

        seen = {}
        real = L._count_text
        L._count_text = lambda v, *a, **k: (seen.setdefault("v", v), real(v, *a, **k))[1]
        try:
            L.lay_stat_split(3.0, 5.0, {"value": 10, "suffix": "%", "label": "of the region", "sub": "x"})
        finally:
            L._count_text = real
        self.assertEqual(seen["v"], "10%")


class Leaders(unittest.TestCase):
    def setUp(self):
        self.cat = P._default_catalog()

    def test_a_leader_who_claims_or_warns_is_introduced(self):
        for t in ("Vladimir Putin claimed the army took 300 square kilometers.", "Zelensky also warned of more strikes.",
                  "Putin has said the talks are over."):
            A = S.analyze_scene(t, self.cat)
            self.assertTrue(A.sentences[0].intro_figure, t)
        self.assertFalse(S.analyze_scene("Putin visited a tank factory.", self.cat).sentences[0].intro_figure)

    def test_figure_may_open_and_follows_a_card_closely(self):
        st = P._State(120.0, dict(P.DEFAULTS))
        fig = SimpleNamespace(kind="figure", key="figure:x", score=50)
        ok, code, why = st.check(fig, 0.0, 3.0, 1, True)
        self.assertTrue(ok, why)                                          # the hook: a named leader may open over footage
        st.acc.append(P._Acc("number", 36.5, 41.6, True, "number:10:%", 7))
        ok, code, why = st.check(fig, 41.9, 45.0, 8, True)
        self.assertTrue(ok, why)                                          # a person named after a number card is a cut, not clutter


class Footage(unittest.TestCase):
    def test_map_and_commentary_channels_are_not_footage(self):
        n = F.narration_profile("The army seized about 6,500 square kilometers this year.")
        bad = [({"video_title": "Claimed 1,301 km². The Map Says They Lost Ground", "channel": "Some Channel"}, "different area"),
               ({"video_title": "RETREAT AT THE RIVER: drone swarms force pullback", "channel": "Balkan Mapper"}, "map or commentary"),
               ({"video_title": "[ Frontline Changes ] major advances", "channel": "X"}, "map or commentary")]
        for meta, want in bad:
            self.assertTrue(any(want in c for c in F.score_clip(n, meta)["contradictions"]), meta)
        ok = {"video_title": "Frontline fighting as forces advance - BBC News", "channel": "BBC News"}
        self.assertFalse(F._graphic_source(ok, n))


class Coverage(unittest.TestCase):
    def _plan(self, shots, layers):
        return SimpleNamespace(shots=shots, layers=layers)

    def test_bare_plate_is_closed_and_flashes_covered(self):
        real = D._clip_seconds
        D._clip_seconds = lambda p: 4.0                            # every clip 4 s long
        self.addCleanup(setattr, D, "_clip_seconds", real)
        plan = self._plan([Shot("a.mp4", 0.0, 4.0), Shot("b.mp4", 10.0, 10.8, seek=0.0)],
                          [Layer("tac_map", 5.0, 10.0), Layer("tac_map", 10.8, 14.0)])
        counts = {}
        D._final_coverage(plan, 14.0, counts)
        maps = sorted(plan.layers, key=lambda x: x.start)
        self.assertEqual((maps[0].end, maps[1].start), (10.4, 10.4))   # the 0.8 s glimpse of b.mp4 between two maps is shared by both
        cov = D._spans_union([(s.start, s.end) for s in plan.shots] + [(l.start, l.end) for l in plan.layers])
        self.assertEqual(cov, [(0.0, 14.0)])                       # the 4-5 s hole is closed

    def test_source_chip_only_where_its_footage_is_seen(self):
        plan = self._plan([Shot("a.mp4", 0.0, 3.0)], [Layer("status_chip", 0.5, 6.0, {"text": "UNVERIFIED · X"}), Layer("tac_map", 3.0, 8.0)])
        D._final_coverage(plan, 8.0, {})
        chips = [l for l in plan.layers if l.kind == "status_chip"]
        self.assertEqual(len(chips), 1)
        self.assertAlmostEqual(chips[0].start, 0.5, delta=0.05)
        self.assertAlmostEqual(chips[0].end, 3.0, delta=0.05)      # not on the map after its clip ended


class MapVariety(unittest.TestCase):
    def test_context_map_has_a_repeat_limit(self):
        self.assertGreaterEqual(D.CONTEXT_REPEAT_S, 60.0)


if __name__ == "__main__":
    unittest.main()


class WholeScriptSubject(unittest.TestCase):
    """Kerch render (2026-11-08): CNN 'attack on Russian bridge' dropped because one sentence named only Ukraine, a drive across the bridge
    dropped because the sentence said 'Moscow'. A clip about the video's own subject is not contradicted by one sentence's wording."""

    def test_clip_about_the_videos_subject_is_kept_another_war_is_not(self):
        script = ["The Kerch Strait bridge links Russia to Crimea.", "For Moscow, it is a symbol.", "Ukraine struck it again in July."]
        topic = F.Profile(" ".join(script))
        moscow = F.narration_profile(script[1], topic)
        self.assertEqual(F.score_clip(moscow, {"video_title": "4K drive across the Kerch Strait bridge"})["contradictions"], [])
        ukr = F.narration_profile(script[2], topic)
        self.assertEqual(F.score_clip(ukr, {"video_title": "New video shows attack on Russian bridge", "channel": "CNN"})["contradictions"], [])
        self.assertTrue(F.score_clip(ukr, {"video_title": "Israel strikes Gaza footage"})["contradictions"])


class ShortForm(unittest.TestCase):
    def test_billion_stays_in_the_narrations_short_form(self):
        p = P.plan([{"text": "It cost about 3.7 billion dollars, and it carries both a road and a railway.", "start": 0, "end": 6, "scene_no": 1},
                    {"text": "Officials said 2,000 troops were sent.", "start": 6, "end": 12, "scene_no": 2}])
        vals = [(ly.params or {}).get("value") for ly in p.layers if (ly.params or {}).get("value") is not None]
        self.assertIn("3.7 billion", vals)
        self.assertNotIn(3700000000, vals)
