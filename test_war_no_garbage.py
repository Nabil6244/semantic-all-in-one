"""War Documentary render 047 ('final 3') was garbage: half the video on near-identical maps (30 s of one Poland map), mismatched stock
(costume soldiers for '1,500 troops'), half-sentence cards and headlines, a map key for countries not on the map, a muddy big number and an
empty grey screen. These tests pin the general rules that fix it, on synthetic scenes (never tuned for that one video)."""

import shutil
import unittest
from types import SimpleNamespace

from war_test_media import clip

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


class MapCards(unittest.TestCase):
    def test_cards_are_whole_clauses_or_nothing(self):
        from cinematic_explainer.war.map_build import _STOP_END, card_for

        self.assertIsNone(card_for("So, here's the question this whole video is built around."))       # rhetoric is not a fact
        self.assertIsNone(card_for("You'll see why it matters before we're done."))
        self.assertIsNone(card_for("What made this one different is the water she sank in."))
        self.assertIsNone(card_for("What happens if the guns fall silent?"))
        c = card_for("It belonged to Bulgaria's exclusive economic zone, and Bulgaria is a member of NATO.")
        self.assertEqual((c["title"], c["sub"]), ("IT BELONGED TO BULGARIA'S EXCLUSIVE ECONOMIC ZONE", "Bulgaria is a member of NATO"))
        c = card_for("Russian drones struck a power plant near the border.")
        self.assertEqual((c["title"], c["sub"], c["variant"]), ("RUSSIAN DRONES STRUCK A POWER PLANT", "near the border", "red"))
        self.assertEqual(card_for("Russia moved 1,500 troops to the border on 3 March.")["sub"], "Russia moved 1,500 troops to the border")
        for s in ("And right in the middle of both, wedged between Poland and Lithuania, sits a small patch of Russia.",
                  "Over the same few weeks, two very different rehearsals have been running across Europe.",
                  "The ship was hit twice before the crew could get off."):
            c = card_for(s)
            if c:
                self.assertNotIn(c["title"].split()[-1].lower(), _STOP_END, s)
                self.assertLessEqual(len(c["title"].split()), 8, s)

    def test_at_most_two_cards_at_once(self):
        from cinematic_explainer.war import map_build

        self.assertLessEqual(map_build.CHIPS_PER_GROUP, 2)


class Headlines(unittest.TestCase):
    def test_whole_phrases_only(self):
        from cinematic_explainer.war.planner import headline_text

        self.assertEqual(headline_text("Out. Two sailors were airlifted."), "Two sailors were airlifted")            # carried-over tail skipped
        self.assertEqual(headline_text("The crew abandoned ship at first light. Two were airlifted."), "The crew abandoned ship at first light")
        self.assertEqual(headline_text("Russia is rehearsing how much it can get away with."), "Russia is rehearsing")
        self.assertEqual(headline_text("What happens if the guns fall silent?"), "")
        self.assertEqual(headline_text("Russia moved 1,500 troops toward Belarus."), "Russia moved 1,500 troops toward Belarus")   # never cut at the comma


class Legend(unittest.TestCase):
    def test_key_only_for_countries_in_view(self):
        from cinematic_explainer.war.maps_tactical import _fill_in_view

        bulgaria = (21.5, 40.8, 30.5, 45.0)
        self.assertTrue(_fill_in_view({"iso3": "BGR"}, bulgaria))
        self.assertFalse(_fill_in_view({"iso3": "RUS"}, bulgaria))          # Russia's whole-country box covers it; its land does not
        self.assertFalse(_fill_in_view({"iso3": "UKR"}, bulgaria))
        self.assertTrue(_fill_in_view({"iso3": "RUS"}, (14, 47, 33, 57)))  # Kaliningrad / the border is in this view

    def test_no_schematic_fill_jargon(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parent / "cinematic_explainer" / "war" / "maps_tactical.py").read_text(encoding="utf-8")
        self.assertNotIn('" · SCHEMATIC FILL"', src)


class MapLength(unittest.TestCase):
    def test_long_map_is_broken_by_footage(self):
        from cinematic_explainer.war.map_build import BREAK_S, CONTEXT_MAP_S, MAX_MAP_S, cap_pieces

        out = cap_pieces([(0.0, 30.0)], True)
        self.assertTrue(all(b - a <= MAX_MAP_S + 1e-6 for a, b in out))
        self.assertEqual(out[0], (0.0, MAX_MAP_S))
        self.assertAlmostEqual(out[1][0], MAX_MAP_S + BREAK_S)
        self.assertLess(sum(b - a for a, b in out), 30.0)
        self.assertEqual(cap_pieces([(0.0, 30.0)], False), [(0.0, CONTEXT_MAP_S)])     # no place of its own: the last map only briefly
        self.assertEqual(cap_pieces([(0.0, 8.0)], True), [(0.0, 8.0)])                   # a short map is untouched


def _plan(shots, layers=()):
    return SimpleNamespace(shots=list(shots), layers=list(layers), log=[])


class FootageReturns(unittest.TestCase):
    def rows(self, n, dur=5.0):
        return [{"_no": i + 1, "_start": i * dur, "_end": (i + 1) * dur, "text": "x"} for i in range(n)]

    def test_gap_takes_the_videos_own_footage_not_the_neighbour(self):
        from cinematic_explainer.render import Shot
        from cinematic_explainer.war import direction as D

        plan = _plan([Shot("a.mp4", 0, 5), Shot("b.mp4", 5, 10), Shot("c.mp4", 20, 25)])
        log = {str(i): SimpleNamespace(flags=[]) for i in range(1, 6)}
        counts = {}
        D._broll_returns(plan, self.rows(5), log, {}, counts, probe=lambda p: 12.0)
        fill = [s for s in plan.shots if 10 <= s.start < 20]
        self.assertTrue(fill)
        self.assertAlmostEqual(sum(s.end - s.start for s in fill), 10.0, places=1)       # the gap is covered
        self.assertTrue(all(s.end - s.start <= D.BROLL_MAX_S + 1e-6 for s in fill))
        self.assertNotEqual(fill[0].path, "b.mp4")                                        # not the clip just shown
        a_fill = [s for s in fill if s.path == "a.mp4"]
        self.assertTrue(all(s.seek >= 5.0 - 1e-6 for s in a_fill))                        # a moment of the clip not shown yet
        self.assertIn("kit_badge", [ly.kind for ly in plan.layers])                        # labelled as illustration
        self.assertIn("dir:broll_return", log["3"].flags)

    def test_full_frame_cards_and_maps_are_not_covered(self):
        from cinematic_explainer.render import Layer, Shot
        from cinematic_explainer.war import direction as D

        plan = _plan([Shot("a.mp4", 0, 5), Shot("b.mp4", 15, 20)], [Layer("tac_map", 5, 15, {})])
        D._broll_returns(plan, self.rows(4), {}, {}, {}, probe=lambda p: 12.0)
        self.assertEqual(len(plan.shots), 2)

    def test_no_footage_at_all_changes_nothing(self):
        from cinematic_explainer.war import direction as D

        plan = _plan([])
        D._broll_returns(plan, self.rows(3), {}, {}, {}, probe=lambda p: 12.0)
        self.assertEqual(plan.shots, [])

    def test_short_clip_ends_with_its_clip(self):
        from cinematic_explainer.render import Shot
        from cinematic_explainer.war import direction as D

        plan = _plan([Shot("yt.mp4", 0, 8), Shot("long.mp4", 8, 12)])
        D._fit_short_clips(plan, {}, probe=lambda p: 3.5 if p == "yt.mp4" else 20.0)
        self.assertAlmostEqual(plan.shots[0].end, 3.44, places=1)          # no held or looped last frame
        self.assertEqual(plan.shots[1].end, 12)


class MismatchedFootage(unittest.TestCase):
    def test_unrelated_or_contradicting_clip_is_dropped_user_and_ai_kept(self):
        from cinematic_explainer.war.planner import _kept_anyway, _unrelated

        self.assertTrue(_unrelated({"relevance": 0.0, "relevance_contradictions": []}))
        self.assertTrue(_unrelated({"relevance": 0.6, "relevance_contradictions": ["different system: Patriot"]}))
        self.assertFalse(_unrelated({"relevance": 0.4, "relevance_contradictions": []}))
        self.assertFalse(_unrelated({}))                                         # never scored: not judged
        self.assertTrue(_kept_anyway({"user_supplied": True}))
        self.assertTrue(_kept_anyway({"ai_generated": True}))
        self.assertFalse(_kept_anyway({"provider": "pexels"}))

    def test_a_csv_clip_from_the_visuals_tab_is_kept_unless_it_contradicts(self):
        """Render 028 (2026-11-07): 15 of 34 CSV clips scored 0.0 on word overlap and were dropped, leaving the empty backdrop on screen."""
        from cinematic_explainer.war.planner import _unrelated
        from cinematic_explainer.war import footage_match as FM

        self.assertFalse(_unrelated({"relevance": 0.0, "relevance_contradictions": [], "csv_pick": True}))
        self.assertTrue(_unrelated({"relevance": 0.6, "relevance_contradictions": ["different system: Patriot"], "csv_pick": True}))
        meta = {"provider": "pexels", "csv_pick": True, "title": "people walking"}
        other = {"path": "/x/pool.mp4", "meta": {"provider": "youtube", "title": "Russian drones strike Odesa port"}}
        out = FM.match_scenes([{"scene_no": 1, "text": "Russian drones struck the port of Odesa.", "footage": "/x/csv.mp4", "footage_meta": meta}], [other])
        self.assertEqual(out[0]["footage"], "/x/csv.mp4")                     # never swapped for another clip

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
    def test_planner_drops_it_and_the_scene_gets_other_footage(self):
        from cinematic_explainer.war import planner

        A, B = clip("008.mp4"), clip("013.mp4")
        good = {"provider": "youtube", "kind": "youtube", "relevance": 0.5, "relevance_reasons": ["names the same place"]}
        bad = {"provider": "pexels", "generic": True, "mismatch": True, "relevance": 0.0, "relevance_contradictions": []}
        scenes = [{"text": "Russian drones struck the port of Odesa overnight.", "start": 0.0, "end": 5.0, "scene_no": 1, "footage": A, "footage_meta": good},
                  {"text": "Poland says it will send fifteen hundred troops.", "start": 5.0, "end": 10.0, "scene_no": 2, "footage": B, "footage_meta": bad},
                  {"text": "The talks in Geneva ended without a deal.", "start": 10.0, "end": 15.0, "scene_no": 3, "footage": A, "footage_meta": good}]
        p = planner.plan(scenes)
        flags = {str(d.scene_no): d.flags for d in p.log}
        self.assertIn("mismatch_dropped", flags["2"])
        self.assertFalse(any(s.path == B for s in p.shots))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
class WholePlan(unittest.TestCase):
    """A 160 s video where two scenes in three have no footage (worse than render 047): no empty screen, no map over 12 s, maps in proportion."""

    TEXT = ["A tanker sank in the Black Sea after an explosion.", "Bulgaria says the wreck sits in its waters near Varna.",
            "It belonged to Bulgaria's exclusive economic zone, and Bulgaria is a member of NATO.", "So here's the question this whole video is built around.",
            "Romania scrambled jets over Constanta.", "Drones crossed from Ukraine into Moldova and Romania.", "Nobody can find an earlier case like it.",
            "Poland and Lithuania sit right next to Kaliningrad.", "You'll see why it matters before we're done.", "Russia moved 1,500 troops toward Belarus.",
            "NATO says the exercise is defensive.", "The talks in Geneva ended without a deal."]

    def test_no_empty_screen_and_maps_in_proportion(self):
        from cinematic_explainer.war import direction as D
        from cinematic_explainer.war import planner
        from cinematic_explainer.war.map_build import MAX_MAP_S

        clips = [clip("008.mp4"), clip("013.mp4")]
        meta = {"provider": "youtube", "kind": "youtube", "relevance": 0.5, "relevance_reasons": ["names the same place"]}
        scenes = [{"text": self.TEXT[i % 12], "start": i * 5.0, "end": i * 5.0 + 5.0, "scene_no": i + 1,
                   **({"footage": clips[i % 2], "footage_meta": meta} if i % 3 == 0 else {})} for i in range(32)]
        p = planner.plan(scenes)
        maps = [(ly.start, ly.end) for ly in p.layers if ly.kind == "tac_map"]
        self.assertTrue(maps)
        self.assertLessEqual(max(b - a for a, b in maps), MAX_MAP_S + 0.05)
        self.assertLess(sum(b - a for a, b in maps), 0.6 * 160.0)        # maps are welcome (owner, 2026-10-31), one long one is not
        covered = sorted([(s.start, s.end) for s in p.shots] + [(ly.start, ly.end) for ly in p.layers if ly.kind in D.FULL_KINDS])
        cur, gaps = 0.0, []
        for a, b in covered + [(160.0, 160.0)]:
            if a - cur > 0.05:
                gaps.append((cur, a))
            cur = max(cur, b)
        self.assertEqual(gaps, [])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
class MoreMapsAndLayouts(unittest.TestCase):
    """The owner (2026-10-31): maps and full-frame layouts should be used more. Short maps over footage when a place is named, layouts spaced
    8 s apart instead of 25 s, icon explainers over footage too; still never one long map and never a headline under a map."""

    def scenes(self, texts, every=1):
        meta = {"provider": "youtube", "kind": "youtube", "relevance": 0.5, "relevance_reasons": ["names the same place"]}
        clips = [clip("008.mp4"), clip("013.mp4")]
        return [{"text": t, "start": i * 6.0, "end": i * 6.0 + 6.0, "scene_no": i + 1,
                 **({"footage": clips[i % 2], "footage_meta": meta} if i % every == 0 else {})} for i, t in enumerate(texts)]

    def test_a_named_place_over_footage_gets_a_short_map_and_the_headline_gives_way(self):
        from cinematic_explainer.war import planner

        texts = ["Russian drones struck the port of Odesa overnight.", "Romania scrambled two jets over Constanta.",
                 "The talks ended without a deal.", "Kyiv was hit by twelve missiles in February.", "Officials said repairs would take weeks.",
                 "A tanker sank near Varna after an explosion."]
        p = planner.plan(self.scenes(texts))
        maps = [ly for ly in p.layers if ly.kind in ("tac_map", "map_card")]
        self.assertGreaterEqual(len(maps), 3)
        self.assertTrue(all(ly.end - ly.start <= 12.05 for ly in maps))
        for h in (ly for ly in p.layers if ly.kind == "shot_headline"):
            self.assertFalse(any(m.start < h.end - 0.01 and m.end > h.start + 0.01 for m in maps))     # no headline under a map

    def test_icons_explain_things_over_footage_too(self):
        from cinematic_explainer.war import planner

        p = planner.plan(self.scenes(["The front barely moved this week.", "Cheap drones are emptying the stocks of air defence missiles.",
                                      "Nobody expected it to last this long."]))
        self.assertIn("kit_icons", [ly.kind for ly in p.layers])

    def test_full_frame_graphics_may_come_every_8_s(self):
        from cinematic_explainer.war.planner import DEFAULTS

        self.assertLessEqual(DEFAULTS["full_gap"], 8.0)
        self.assertLessEqual(DEFAULTS["clean_floor"], 0.30)
        self.assertGreaterEqual(DEFAULTS["per_minute"], 6)


class GraphicFloor(unittest.TestCase):
    """The owner (2026-11-07): the graphics the style already has should be used. A footage-heavy render with plain narration (no places,
    numbers or quotes) showed one graphic in the whole video; now none of its stretches goes longer than the floor gap without one."""

    TEXTS = ["The war changed everything for the people who lived there.", "Nobody expected the fighting to last this long.",
             "Soldiers on both sides were exhausted after months in the trenches.", "Supplies were running low and morale was falling.",
             "Commanders argued about what to do next.", "Some wanted to push forward, others wanted to dig in.",
             "The winter made every decision harder.", "Roads turned to mud and vehicles got stuck.",
             "Many families had already left their homes.", "Those who stayed lived in basements for weeks.",
             "Then the government made a surprising decision.", "It would change the course of the conflict."]

    def plan(self, **cfg):
        from cinematic_explainer.war import planner

        meta = {"provider": "youtube", "kind": "youtube", "relevance": 0.5, "relevance_reasons": ["same topic"]}
        sc = [{"text": t, "start": i * 8.0, "end": i * 8.0 + 8.0, "scene_no": i + 1, "footage": clip("008.mp4"), "footage_meta": meta}
              for i, t in enumerate(self.TEXTS)]
        return planner.plan(sc, config=cfg or None)

    def graphics(self, p):
        from cinematic_explainer.war.direction import _NOT_A_GRAPHIC

        return sorted((ly for ly in p.layers if ly.kind not in _NOT_A_GRAPHIC), key=lambda ly: ly.start)

    def test_plain_narration_over_footage_still_gets_graphics_every_10_s(self):
        p = self.plan()
        self.assertNotIn("error", p.stats["direction"])
        g = self.graphics(p)
        self.assertGreaterEqual(len(g), 8)
        cur = 4.0
        for ly in g:
            self.assertLessEqual(ly.start - cur, 10.0 + 0.05, f"no graphic from {cur:.1f}s to {ly.start:.1f}s")
            cur = max(cur, ly.end)
        self.assertLessEqual(96.0 - cur, 10.0 + 0.05)

    def test_the_kit_rotates_never_the_same_kind_twice_in_a_row(self):
        g = [ly for ly in self.graphics(self.plan())]
        self.assertGreaterEqual(len({ly.kind for ly in g}), 3)
        floor = [ly.kind for ly in g]
        self.assertFalse(any(a == b for a, b in zip(floor, floor[1:])))

    def test_graphics_never_overlap_and_words_come_from_the_narration(self):
        g = self.graphics(self.plan())
        for a, b in zip(g, g[1:]):
            self.assertLessEqual(a.end, b.start + 0.01)
        said = " ".join(self.TEXTS).lower()
        for ly in g:
            words = (ly.params or {}).get("text") or (ly.params or {}).get("caption")
            if words:
                self.assertIn(words.lower().split()[0], said)

    def test_switch_off(self):
        self.assertLessEqual(len(self.graphics(self.plan(graphic_floor=False))), 2)


class MotionFill(unittest.TestCase):
    """The owner (2026-11-07): "we can use graphics instead of that" (the empty backdrop) and "add new graphics too, graphics animations"."""

    TEXTS = ["Officials said the decision was made in secret.", "Russian drones and missiles filled the sky every night.",
             "Soldiers needed fuel, ammunition and food.", "Nobody expected the fighting to last this long.",
             "The government announced a new plan for the winter.", "The cost kept rising for everyone."]

    def test_every_new_graphic_animates_and_is_registered(self):
        from cinematic_explainer.war import registry
        from cinematic_explainer.war.cards_motion import MOTION_CARDS

        cards = registry.all_cards()
        params = {"kit_kinetic": {"text": "The cost kept rising", "key": ["rising"]},
                  "kit_dossier": {"title": "A new plan", "body": "The government announced a new plan for the winter.", "mark": ["winter"]},
                  "kit_radar": {"label": "Drones filled the sky"}, "kit_keywords": {"items": ["Fuel", "Ammunition", "Food"], "title": "What they needed"}}
        for kind, fn in MOTION_CARDS.items():
            self.assertIs(cards[kind], fn)
            early, late = fn(0.3, 5.0, params[kind]), fn(2.5, 5.0, params[kind])
            self.assertEqual(late.size, (1280, 720))
            self.assertNotEqual(early.tobytes(), late.tobytes())          # it moves
            self.assertIsNone(fn(1.0, 5.0, {}))                            # no words, no graphic

    def test_a_stretch_without_footage_is_covered_by_motion_graphics_not_the_backdrop(self):
        from cinematic_explainer.war import planner
        from cinematic_explainer.war.direction import MOTION_KINDS

        sc = [{"text": t, "start": i * 8.0, "end": i * 8.0 + 8.0, "scene_no": i + 1} for i, t in enumerate(self.TEXTS)]
        p = planner.plan(sc, config={"map_build": False, "broll": False, "layouts": False, "icons": False, "graphic_floor": False})
        self.assertNotIn("error", p.stats["direction"])
        motion = sorted((ly for ly in p.layers if ly.kind in MOTION_KINDS), key=lambda ly: ly.start)
        self.assertGreaterEqual(len({ly.kind for ly in motion}), 3)
        self.assertFalse(any(a.kind == b.kind for a, b in zip(motion, motion[1:])))
        covered = sum(ly.end - ly.start for ly in p.layers if ly.kind not in ("kicker", "status_chip", "kit_badge", "shot_headline"))
        self.assertGreaterEqual(covered, 48.0 * 0.9)
        self.assertTrue(all(ly.end - ly.start <= 9.0 + 0.05 for ly in motion))

    def test_old_tag_fill_when_switched_off(self):
        from cinematic_explainer.war import planner
        from cinematic_explainer.war.direction import MOTION_KINDS

        sc = [{"text": t, "start": i * 8.0, "end": i * 8.0 + 8.0, "scene_no": i + 1} for i, t in enumerate(self.TEXTS)]
        p = planner.plan(sc, config={"map_build": False, "broll": False, "motion_fill": False, "graphic_floor": False})
        self.assertFalse(any(ly.kind in MOTION_KINDS for ly in p.layers))


class CommaNumbers(unittest.TestCase):
    def test_2_000_with_a_comma_is_a_number_not_a_crash_and_2022_is_a_year(self):
        from cinematic_explainer.war.semantics import find_numbers

        nums, years = find_numbers("Losses rose from 2,000 in March to 46,000 by 2022.")
        self.assertIn(2000.0, [n.value for n in nums])
        self.assertEqual([y for y, _ in years], [2022])


class RichLayoutsMoreOften(unittest.TestCase):
    """The owner (2026-11-07, pointing at the stat split, equipment panel, figure panel ...): "these are the best stills, why you not adding?"
    Render 028 skipped them: '4 feet wide' had no referent the parser knew, 'missiles' / 'western tanks' named no model."""

    def plan(self, texts):
        from cinematic_explainer.war import planner

        return planner.plan([{"text": t, "start": i * 7.0, "end": i * 7.0 + 7.0, "scene_no": i + 1} for i, t in enumerate(texts)],
                            config={"map_build": False})

    def test_a_class_word_gets_the_equipment_panel_with_the_narrations_word_and_no_guessed_class(self):
        p = self.plan(["The war entered its third winter.", "Its missiles are hunting the power grid as winter closes in.",
                       "Nobody expected it to last.", "Western tanks were arriving at last."])
        eq = [ly for ly in p.layers if ly.kind == "lay_equipment_hero"]
        self.assertEqual(sorted(ly.params["type_word"] for ly in eq), ["Missiles", "Tanks"])
        miss = next(ly for ly in eq if ly.params["type_word"] == "Missiles")
        self.assertEqual(miss.params["class_label"], "Missile")              # never 'Cruise missile': the narration did not say which
        self.assertEqual(miss.params["status"], "unverified")

    def test_a_figure_in_digits_gets_the_stat_layout_labelled_with_the_narrations_words(self):
        p = self.plan(["Imagine a steel tube about 4 feet wide.", "Nobody expected it to last.",
                       "Its troops are attacking along 300 kilometres of front."])
        labels = [ly.params.get("label") for ly in p.layers if ly.kind in ("lay_stat_split", "kit_bignum", "stat_number")]
        self.assertIn("feet wide", labels)
        self.assertTrue(any(str(lb).startswith("kilometres") for lb in labels))

    def test_spelled_small_counts_and_years_stay_out(self):
        p = self.plan(["There is one way forward and one way back.", "In 2022 the war changed."])
        self.assertFalse(any(ly.kind in ("lay_stat_split", "kit_bignum", "stat_number") for ly in p.layers))


class WarFetch(unittest.TestCase):
    def test_youtube_clips_long_enough_for_a_scene_and_searches_ask_for_footage(self):
        from cinematic_explainer.war.app_section import WAR_YT_CLIP_S, csv_rows, war_manager

        yp = SimpleNamespace(clip_duration=3.5)
        m = war_manager(SimpleNamespace(settings={"gemini_enabled": True}, youtube_provider=yp))
        self.assertEqual(yp.clip_duration, WAR_YT_CLIP_S)
        self.assertFalse(m.settings["gemini_enabled"])
        rows = csv_rows([{"scene_no": 1, "text": "a", "asset_type": "youtube_video", "prompt": "Black Sea tanker sinking || tanker sinks"},
                         {"scene_no": 2, "text": "b", "asset_type": "youtube_video", "prompt": "Kharkiv strike footage"}])
        self.assertIn("Black Sea tanker sinking footage", rows[0].prompt)
        self.assertEqual(rows[1].prompt, "Kharkiv strike footage")

    def test_csv_prompt_asks_for_more_footage(self):
        from cinematic_explainer.war.app_section import csv_prompt_text

        t = csv_prompt_text()
        self.assertIn("70 to 80 percent", t)
        self.assertIn("No more than two none scenes in a row", t)


if __name__ == "__main__":
    unittest.main()
