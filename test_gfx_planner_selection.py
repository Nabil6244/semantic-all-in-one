"""The production graphics planner (gfx_templates.auto_events): a scored choice among the rules that read the narration, not the first template that fits. What each
rule needs, what it never invents, how layouts vary, how graphics share the screen (zones) and what happens over footage (map-only graphics refused, others backed)."""

from __future__ import annotations

import unittest

import gfx_extractors as X
import gfx_templates as G
from test_hybrid_graphics_planning import _plain

FILL = "And so the story goes on through the quiet country for a long while, with plenty of time for the listener to look around. "


def _where(name):
    return {"Vancouver": (-123.1, 49.3), "Halifax": (-63.6, 44.6)}.get(name)


def plan(text, **kw):
    words = _plain(text, step=0.5)
    report = []
    ev = G.auto_events(words, niche="map", script=text, total=words[-1][2], report=report, **kw)
    return ev, [r for r in report if r["reason"] != "not_enough_in_the_sentence"]


def ids(ev):
    return [e["template"]["id"] for e in ev]


class TestRulesReadOnlyWhatTheNarrationSays(unittest.TestCase):
    def test_a_spoken_sequence_becomes_a_checklist_of_its_own_words(self):
        ev, _ = plan(FILL * 3 + "There are three steps to the old method. First, dig a deep shaft. Second, follow the channel. "
                     "Third, wash the gravel. " + FILL * 3)
        self.assertIn("checklist_card", ids(ev))
        self.assertEqual([e for e in ev if e["template"]["id"] == "checklist_card"][0]["slots"]["items"], ["Dig a deep shaft", "Follow the channel", "Wash the gravel"])

    def test_a_step_wider_than_the_card_gets_no_card_never_a_cut_item(self):
        ev, _ = plan(FILL * 3 + "First, dig a shaft through the rock. Second, follow the buried channel. Third, wash the gravel in the creek. " + FILL * 3)
        self.assertNotIn("checklist_card", ids(ev))

    def test_a_sequence_with_a_long_step_gets_no_card(self):
        ev, _ = plan(FILL * 3 + "First, dig a shaft through the solid rock all the way down to the old river bed. Second, follow the buried channel. "
                     "Third, wash the gravel in the creek. " + FILL * 3)
        self.assertNotIn("checklist_card", ids(ev))

    def test_three_things_named_together(self):
        ev, _ = plan(FILL * 3 + "The reserve protects three kinds of habitat: wetland, forest and grassland. " + FILL * 3)
        self.assertEqual(ids(ev), ["three_rings"])
        self.assertEqual(ev[0]["slots"]["items"], ["WETLAND", "FOREST", "GRASSLAND"])

    def test_only_two_or_four_things_get_no_rings(self):
        for line in ("The reserve protects three kinds of habitat: wetland and forest. ", "The reserve protects three kinds of habitat: wetland, forest, grassland and reeds. "):
            self.assertNotIn("three_rings", ids(plan(FILL * 3 + line + FILL * 3)[0]))

    def test_the_closing_question_is_the_narrations_own(self):
        ev, _ = plan(FILL * 3 + "So which of these places would you visit first? ")
        self.assertEqual(ids(ev), ["end_question"])
        self.assertEqual(ev[0]["slots"]["text"], "SO WHICH OF THESE PLACES WOULD YOU VISIT FIRST?")
        self.assertEqual(ev[0]["slots"]["kicker"], "")                    # not the library's "WHAT DO YOU THINK?"

    def test_a_question_in_the_middle_is_not_a_closing_question(self):
        self.assertNotIn("end_question", ids(plan(FILL * 2 + "So which of these places would you visit first? " + FILL * 3)[0]))

    def test_a_person_with_what_they_were(self):
        class Ctx:
            raw = "But in 1855, the painter Eugene von Guerard had recorded the original scene."
            resolve = staticmethod(lambda n: None)
            def time_at(self, c): return 2.0
        self.assertEqual(X.name_bar("", Ctx()), {"label": "EUGENE VON GUERARD", "sub": "PAINTER", "_t0": 2.0})

    def test_a_superlative_is_drawn_whole_or_not_at_all(self):
        class Ctx:
            def __init__(self, raw): self.raw = raw
            def time_at(self, c): return 1.0
        self.assertEqual(X.tag_fact("", Ctx("Mount William, the highest peak, reaches about 1,167 metres."))["text"], "THE HIGHEST PEAK")
        self.assertEqual(X.tag_fact("", Ctx("It is the largest volcanic province in Australia."))["text"], "THE LARGEST VOLCANIC PROVINCE")
        self.assertIsNone(X.tag_fact("", Ctx("It was the first Australian World Heritage site listed solely for its culture.")))      # runs on: never cut
        self.assertIsNone(X.tag_fact("", Ctx("It was the first big step toward something quite different here.")))

    def test_two_numbers_side_by_side_may_be_a_head_to_head_or_two_bars_never_with_no_unit(self):
        ev, report = plan(FILL * 3 + "Russia has 17 million square kilometres, Canada 10 million square kilometres. " + FILL)
        self.assertEqual(ids(ev), ["versus_numbers"])
        self.assertIn("rank_bars", {r["template"] for r in report})          # the other layout of the same two numbers was a candidate and lost on score

    def test_decades_are_dates_too(self):
        ev, _ = plan(FILL * 3 + "From the 1960s, restoration crews used that painting as a guide for the work. " + FILL * 2)
        self.assertEqual([(i, e["slots"]["text"]) for i, e in zip(ids(ev), ev)], [("year_wipe", "1960S")])

    def test_no_example_text_reaches_the_video(self):
        text = (FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3 + "Russia has 17 million square kilometres, Canada 10 million square kilometres. " + FILL * 3 +
                "The reserve protects three kinds of habitat: wetland, forest and grassland. " + FILL * 3 + "So which of these places would you visit first? ")
        ev, _ = plan(text)
        self.assertGreaterEqual(len(ev), 3)
        lib = G.load_library()
        for e in ev:
            for name, spec in e["template"]["slots"].items():
                if spec.get("required") or not isinstance(spec.get("default"), str) or (e["template"]["id"], name) in G._FUNCTIONAL_DEFAULTS or e["slots"].get(name):
                    continue                                                  # (a slot the narration filled shows its value, not its default)
                self.assertIn(spec["default"], ("",), f"{e['id']}.{name} would show {spec['default']!r}")
            self.assertTrue(all(isinstance(v, (str, int, float, list)) for v in e["slots"].values()))
            self.assertIn(e["template"]["id"], lib)


class TestVarietyAndScoring(unittest.TestCase):
    TWO_NUMBERS = (FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 4 + "Bendigo produced well over twenty million ounces of gold. " + FILL * 3)

    def test_the_second_number_is_shown_in_a_different_layout(self):
        words = _plain(self.TWO_NUMBERS, step=1.6)
        ev = G.auto_events(words, niche="map", script=self.TWO_NUMBERS, total=words[-1][2])
        self.assertEqual(sorted(e["slots"]["value"] for e in ev), [20, 100])
        self.assertEqual(len({e["template"]["id"] for e in ev}), 2)
        self.assertTrue({e["template"]["id"] for e in ev} <= {"big_number", "gold_stat", "stat_countup", "counter_corner"})

    def test_with_one_layout_enabled_the_repeat_rules_still_hold(self):
        words = _plain(self.TWO_NUMBERS, step=0.5)
        ev = G.auto_events(words, niche="map", script=self.TWO_NUMBERS, total=words[-1][2], enabled=("big_number",))
        self.assertEqual(ids(ev), ["big_number", "big_number"] if len(ev) == 2 else ["big_number"])

    def test_the_report_names_the_layout_that_lost(self):
        ev, report = plan(FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3)
        self.assertEqual(ids(ev), ["big_number"])
        self.assertIn(("gold_stat", "a better layout was chosen (big_number)"), {(r["template"], r["reason"]) for r in report})

    def test_a_sentence_with_nothing_to_show_gets_nothing(self):
        ev, _ = plan(FILL * 6)
        self.assertEqual(ev, [])


class TestSharingTheScreen(unittest.TestCase):
    TEXT = FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3

    def _at(self):
        words = _plain(self.TEXT, step=0.5)
        return words, next(a for t, a, b in G.sentences(G.display_words(words, self.TEXT)) if "Coal" in t)

    PERSON = FILL * 3 + "Later, the painter Eugene von Guerard recorded the scene in detail for the colony. " + FILL * 3

    def test_a_corner_counter_does_not_stop_a_name_bar_but_a_caption_in_its_corner_does(self):
        words = _plain(self.PERSON, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, self.PERSON)) if "painter" in t)
        kw = dict(niche="map", script=self.PERSON, total=words[-1][2], enabled=("name_bar",), resolve=lambda n: None)
        self.assertEqual(ids(G.auto_events(words, taken=[(a - 1, a + 8, G.ZONES["counter_corner"])], **kw)), ["name_bar"])
        self.assertEqual(G.auto_events(words, taken=[(a - 1, a + 8, G.ZONES["typed_caption"])], **kw), [])

    def test_a_dimming_graphic_takes_the_whole_frame(self):
        words, a = self._at()
        self.assertEqual(G.zones_of(G.get("big_number")), G._ALL_ZONES)       # its dim covers the frame over the map: nothing beside it
        ev = G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), taken=[(a - 1, a + 8, G.ZONES["counter_corner"])])
        self.assertEqual(ev, [])

    def test_a_graphic_in_the_same_part_of_the_frame_does_stop_it(self):
        words, a = self._at()
        ev, = [G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), taken=[(a + 1, a + 8, G.ZONES["tag_fact"])])]
        self.assertEqual(ev, [])

    def test_an_unlisted_window_takes_the_whole_frame(self):
        words, a = self._at()
        self.assertEqual(G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), taken=[(a + 1, a + 8)]), [])


class TestOverFootage(unittest.TestCase):
    TEXT = FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3

    def _words(self):
        words = _plain(self.TEXT, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, self.TEXT)) if "Coal" in t)
        return words, a

    def test_a_map_layer_hidden_under_footage_does_not_block_a_graphic_above_it(self):
        words, a = self._words()
        foot = [(a - 3, a + 14)]
        under = [(a + 1, a + 5, G.ZONES["big_number"])]
        ev = G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), footage=foot, hidden_under_footage=under)
        self.assertEqual(ids(ev), ["big_number"])
        self.assertTrue(ev[0]["over_footage"])

    def test_the_same_window_blocks_when_footage_does_not_cover_it(self):
        words, a = self._words()
        under = [(a + 1, a + 5, G.ZONES["big_number"])]
        self.assertEqual(G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), hidden_under_footage=under), [])

    def test_a_route_is_never_drawn_over_footage(self):
        text = FILL * 3 + "The convoy travelled from Vancouver to Halifax over many weeks of hard driving. " + FILL * 3
        words = _plain(text, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, text)) if "Vancouver" in t)
        ok = G.auto_events(words, niche="map", script=text, total=words[-1][2], resolve=_where)
        self.assertEqual(ids(ok), ["route_travel"])
        report = []
        over = G.auto_events(words, niche="map", script=text, total=words[-1][2], resolve=_where, footage=[(a - 2, a + 12)], report=report)
        self.assertEqual(over, [])
        self.assertIn(("route_travel", "map_hidden_under_footage"), {(r["template"], r["reason"]) for r in report})

    def test_a_plate_over_footage_gives_way_to_a_soft_backing(self):
        text = FILL * 3 + "Russia has 17 million square kilometres, Canada 10 million square kilometres. " + FILL
        words = _plain(text, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, text)) if "Russia" in t)
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2], enabled=("versus_numbers",), footage=[(a - 2, a + 12)])
        self.assertEqual(ids(ev), ["versus_numbers"])
        self.assertTrue(ev[0]["over_footage"])
        self.assertFalse(ev[0]["template"].get("plate"))
        self.assertIn("shade", ev[0]["template"])


class TestCompilePassesTheRightWindows(unittest.TestCase):
    def test_captions_under_footage_do_not_block_and_graphics_above_it_do(self):
        from pakmap.compile import compile_rows  # noqa: F401  (the planner is called from compile_rows: the unit tests above cover the logic)
        z = G.zones_of(G.get("typed_caption"))
        self.assertEqual(z, frozenset({"BL", "BC"}))
        self.assertEqual(G.zones_of(G.get("counter_corner")), frozenset({"TR"}))
        self.assertEqual(G.zones_of(G.get("ring_percent")), G._ALL_ZONES)          # a full-screen plate takes the whole frame


if __name__ == "__main__":
    unittest.main()


class TestFootageFirst(unittest.TestCase):
    TEXT = FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3

    def _words(self):
        words = _plain(self.TEXT, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, self.TEXT)) if "Coal" in t)
        return words, a

    def test_a_graphic_whose_footage_starts_just_after_its_words_moves_onto_the_footage(self):
        words, a = self._words()
        clip = (a + 2.0, a + 12.0)
        ev = G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), footage=[clip])
        self.assertEqual(ids(ev), ["big_number"])
        self.assertTrue(ev[0]["over_footage"])
        self.assertAlmostEqual(ev[0]["t_in"], clip[0] + 0.4, places=2)
        self.assertLessEqual(ev[0]["t_out"], clip[1])

    def test_footage_that_starts_too_late_does_not_pull_it_away_from_its_words(self):
        words, a = self._words()
        ev = G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], enabled=("big_number",), footage=[(a + 8.0, a + 20.0)])
        self.assertEqual(ids(ev), ["big_number"])
        self.assertNotIn("over_footage", ev[0])
        self.assertAlmostEqual(ev[0]["t_in"], a, places=2)

    def test_a_graphic_that_sits_on_the_map_is_never_pulled_onto_footage(self):
        text = FILL * 3 + "The convoy travelled from Vancouver to Halifax over many weeks of hard driving. " + FILL * 3
        words = _plain(text, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, text)) if "Vancouver" in t)
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2], resolve=_where, footage=[(a + 7.0, a + 17.0)])
        self.assertEqual(ids(ev), ["route_travel"])                  # footage comes after its time on the map: it stays on the map, where it can be seen
        self.assertNotIn("over_footage", ev[0])
        self.assertAlmostEqual(ev[0]["t_in"], a, places=2)
        report = []
        self.assertEqual(G.auto_events(words, niche="map", script=text, total=words[-1][2], resolve=_where, footage=[(a + 2.0, a + 12.0)], report=report), [])
        self.assertIn(("route_travel", "map_hidden_under_footage"), {(r["template"], r["reason"]) for r in report})

    def test_on_footage_graphics_may_follow_each_other_closer_than_on_the_map(self):
        self.assertLess(G.MIN_SPACING_FOOTAGE_S, G.MIN_SPACING_S)
        self.assertGreater(G.MAX_PER_MINUTE_FOOTAGE, G.MAX_PER_MINUTE)

    def test_with_footage_in_the_video_a_graphic_that_could_go_either_way_prefers_the_footage_layout_score(self):
        words, a = self._words()
        far = [(a + 60.0, a + 90.0)]                      # footage exists, but not near these words: the graphic stays where its words are
        ev = G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], footage=far)
        self.assertEqual(len(ev), 1)
        self.assertNotIn("over_footage", ev[0])


class TestTheOtherLayouts(unittest.TestCase):
    def test_every_rule_can_be_reached_by_some_narration(self):
        """Each layout with a rule is placed, by the production planner, for a script that states what it needs (a table of what each rule reads: RULES)."""
        cases = {
            "big_number": "Coal seams more than a hundred metres thick lie under Gippsland.",
            "ring_percent": "About sixty percent of the valley floor is farmland and the rest is forest.",
            "year_wipe": "From the 1960s, restoration crews used that painting as a guide for the work.",
            "versus_numbers": "Russia has 17 million square kilometres, Canada 10 million square kilometres.",
            "three_rings": "The reserve protects three kinds of habitat: wetland, forest and grassland.",
            "checklist_card": "There are three steps. First, dig a deep shaft. Second, follow the channel. Third, wash the gravel.",
            "name_bar": "Later, the painter Eugene von Guerard recorded the scene in detail for the colony.",
            "quote_card": 'She wrote, "The river does not forget what the mountains told it long ago."',
            "end_question": "So which of these places would you visit first?",
            "chapter_serif": "Chapter two. The lost harbour.",
            "chapter_words": "Part two.",
            "keyword_title": "Nobody expected it.",
        }
        for tid, line in cases.items():
            text = FILL * 3 + line + " " + (FILL * 3 if tid != "end_question" else "")
            words = _plain(text, step=0.5)
            got = G.auto_events(words, niche="map", script=text, total=words[-1][2], resolve=lambda n: None, enabled=(tid,))
            self.assertEqual(ids(got), [tid], f"{tid}: {line}")

    def test_the_same_figure_has_four_layouts_and_a_comparison_has_four(self):
        figure = FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3
        words = _plain(figure, step=0.5)
        for tid in ("big_number", "gold_stat", "stat_countup", "counter_corner"):
            got = G.auto_events(words, niche="map", script=figure, total=words[-1][2], enabled=(tid,))
            self.assertEqual(ids(got), [tid])
            self.assertEqual(got[0]["slots"]["value"], 100)
        versus = FILL * 3 + "Russia has 17 million square kilometres, Canada 10 million square kilometres. " + FILL * 3
        words = _plain(versus, step=0.5)
        for tid in ("versus_numbers", "rank_bars", "bubble_compare", "stacked_compare"):
            got = G.auto_events(words, niche="map", script=versus, total=words[-1][2], enabled=(tid,))
            self.assertEqual(ids(got), [tid])
            rows = got[0]["slots"].get("rows") or [{"label": got[0]["slots"]["a_label"], "value": got[0]["slots"]["a_value"]}, {"label": got[0]["slots"]["b_label"], "value": got[0]["slots"]["b_value"]}]
            self.assertEqual([(r["label"], r["value"]) for r in rows], [("RUSSIA", 17), ("CANADA", 10)])

    def test_a_range_is_not_one_number(self):
        for line in ("As the sea rose it filled the bay roughly eight to ten thousand years ago.", "It covers between five and nine million square kilometres."):
            text = FILL * 3 + line + " " + FILL * 3
            words = _plain(text, step=0.5)
            self.assertEqual(G.auto_events(words, niche="map", script=text, total=words[-1][2], enabled=("big_number", "gold_stat", "stat_countup", "counter_corner")), [], line)

    def test_a_heading_with_its_title_in_the_next_sentence(self):
        text = FILL * 3 + "Chapter two. The lost harbour. " + FILL * 3
        words = _plain(text, step=0.5)
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2], enabled=("chapter_serif", "chapter_words"))
        self.assertEqual(ids(ev), ["chapter_serif"])
        self.assertEqual(ev[0]["slots"], {"kicker": "CHAPTER TWO", "title": "THE LOST HARBOUR"})

    def test_a_punchline_is_short_plain_and_follows_a_long_sentence(self):
        class Ctx:
            def __init__(self, raw, prev, index=1):
                self.raw, self.index, self.sents = raw, index, [(prev, 0, 1), (raw, 1, 2)]
            def time_at(self, c): return 1.0
        long = " ".join(["word"] * 20) + "."
        self.assertEqual(X.punchline("", Ctx("Nobody expected it.", long))["text"], "NOBODY EXPECTED IT")
        for bad in ("But nobody expected it.", "Nobody expected it, not once.", "Nobody expected 3 things.", "Did nobody expect it?", "It was a very long and winding road home.", "Part two."):
            self.assertIsNone(X.punchline("", Ctx(bad, long)), bad)
        self.assertIsNone(X.punchline("", Ctx("Nobody expected it.", "A short one here.")))      # no long sentence before it: not a beat

    def test_text_effects_are_rationed_and_rotate_through_the_styles(self):
        lines = ["Nobody expected it.", "The water went quiet.", "Nobody spoke.", "The road ended there.", "It was over."]
        text = FILL * 2 + (FILL * 8).join(l + " " for l in lines) + FILL * 2
        words = _plain(text, step=0.6)
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2])
        punch = [e for e in ev if RULE_GROUP(e["template"]["id"])]
        self.assertGreaterEqual(len(punch), 3)
        self.assertEqual(len({e["template"]["id"] for e in punch}), len(punch), "a style is not repeated while another is unused")
        self.assertTrue(all(b["t_in"] - a["t_out"] >= 75.0 for a, b in zip(punch, punch[1:])), [round(b["t_in"] - a["t_out"]) for a, b in zip(punch, punch[1:])])

    def test_text_the_plan_already_shows_is_not_repeated(self):
        text = FILL * 3 + "Nobody expected it. " + FILL * 3
        words = _plain(text, step=0.5)
        a = next(a for t, a, b in G.sentences(G.display_words(words, text)) if "Nobody" in t)
        report = []
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2], report=report, texts=[(a - 2, a + 6, "NOBODY EXPECTED IT")])
        self.assertEqual([e for e in ev if RULE_GROUP(e["template"]["id"])], [])
        self.assertIn("the_plan_already_says_it", {r["reason"] for r in report})

    def test_the_closing_question_is_sized_to_fit_the_frame(self):
        text = FILL * 3 + "So which of these places would you visit first? "
        words = _plain(text, step=0.5)
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2], enabled=("end_question",))
        size = [it["size"] for it in ev[0]["template"]["items"] if it.get("text") == "{text}"][0]
        self.assertLess(size, 96)
        self.assertLessEqual(len(ev[0]["slots"]["text"]) * 0.62 * size, 1700 + 1)


def RULE_GROUP(tid):
    return G.RULES.get(tid, {}).get("group")


class TestStableAndSafe(unittest.TestCase):
    TEXT = (FILL * 3 + "Coal seams more than a hundred metres thick lie under Gippsland. " + FILL * 3 + "Later, the painter Eugene von Guerard recorded the scene. " + FILL * 3
            + "Russia has 17 million square kilometres, Canada 10 million square kilometres. " + FILL * 3 + "Nobody expected it. " + FILL * 3 + "So which of these places would you visit first? ")

    def test_the_same_narration_always_gives_the_same_plan(self):
        words = _plain(self.TEXT, step=0.5)
        runs = [G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], resolve=lambda n: None, footage=[(60.0, 110.0)]) for _ in range(3)]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])
        self.assertGreaterEqual(len(runs[0]), 4)

    def test_a_planned_layout_needing_data_the_narration_lacks_is_rejected_not_filled(self):
        words = _plain(FILL * 8, step=0.5)
        rep = []
        self.assertEqual(G.auto_events(words, niche="map", script=FILL * 8, total=words[-1][2], report=rep), [])
        for line, tid in (("First, dig a deep shaft. Second, follow the channel.", "checklist_card"), ("The reserve protects three kinds of habitat: wetland and forest.", "three_rings"),
                          ("She said it.", "quote_card"), ("Fact seven.", "fact_card")):
            text = FILL * 3 + line + " " + FILL * 3
            w = _plain(text, step=0.5)
            self.assertEqual(G.auto_events(w, niche="map", script=text, total=w[-1][2], enabled=(tid,)), [], line)

    def test_no_slot_is_empty_where_the_template_requires_it(self):
        words = _plain(self.TEXT, step=0.5)
        lib = G.load_library()
        for e in G.auto_events(words, niche="map", script=self.TEXT, total=words[-1][2], resolve=lambda n: None):
            for name, spec in lib[e["template"]["id"]]["slots"].items():
                if spec.get("required"):
                    self.assertNotIn(e["slots"].get(name), (None, "", []), f"{e['id']}.{name}")
