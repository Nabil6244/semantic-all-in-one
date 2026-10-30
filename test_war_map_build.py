"""War Documentary map stretches (cinematic_explainer/war/map_build.py, maps_tactical additions): a stretch without footage becomes one political
map that builds with the narration instead of short maps, tags and an empty backdrop (render #047 had 12 empty stretches). No network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


def _plan(scenes, **cfg):
    from cinematic_explainer.war import integration as I, planner as P

    d = Path(tempfile.mkdtemp())
    return P.plan(I.load_scenes(d, [dict(s, no_footage=True) for s in scenes]), config=cfg)


SCENES = [
    {"scene_no": 1, "text": "In October Russian drones struck Vilnius from the east.", "start": 0.0, "end": 5.0},
    {"scene_no": 2, "text": "Poland and Lithuania called it an attack on NATO.", "start": 5.0, "end": 10.0},
    {"scene_no": 3, "text": "The alliance said it would defend every member.", "start": 10.0, "end": 15.0},
    {"scene_no": 4, "text": "Nobody expected what came next in the region.", "start": 15.0, "end": 21.0},
]


class CountryColours(unittest.TestCase):
    def test_one_colour_per_country_for_the_whole_video(self):
        from cinematic_explainer.war.maps_tactical import country_roles

        roles = country_roles(["Germany", "Russia", "Poland"])
        self.assertEqual(roles["RUS"], "red")
        self.assertNotEqual(roles["DEU"], roles["POL"])
        again = country_roles(["Poland", "Ukraine", "Atlantis"], roles)      # the same dict: earlier colours kept, unknown names skipped
        self.assertEqual(again["POL"], roles["POL"])
        self.assertEqual(again["UKR"], "blue")
        self.assertEqual(len(again), 4)


class Cards(unittest.TestCase):
    def test_cards_use_the_narrations_words(self):
        from cinematic_explainer.war.map_build import card_for

        self.assertEqual(card_for("On 17 October the jets went up over Sulina."), {"title": "17 OCTOBER", "sub": "the jets went up over Sulina", "variant": "dark"})
        self.assertEqual(card_for("Drones came in low from open water.")["title"], "DRONES CAME IN LOW FROM OPEN WATER")
        self.assertEqual(card_for("Russian drones struck a power plant near the border.")["variant"], "red")
        self.assertEqual(card_for("Bulgaria is a member of NATO, after all.")["variant"], "blue")
        self.assertIsNone(card_for("If you want more, hit subscribe now."))
        self.assertIsNone(card_for("Go."))
        c = card_for("Alpha Watan went to the bottom of the Black Sea.")
        self.assertEqual((c["title"], c["sub"]), ("ALPHA WATAN WENT TO THE BOTTOM", "of the Black Sea"))


class Build(unittest.TestCase):
    def test_a_stretch_without_footage_is_one_building_map(self):
        plan = _plan(SCENES)
        maps = [ly for ly in plan.layers if ly.kind == "tac_map"]
        self.assertEqual(len(maps), 1)
        m = maps[0]
        self.assertEqual((m.start, m.end), (0.0, 21.0))
        p = m.params
        self.assertEqual(p["theme"], "political")
        roles = {f["iso3"]: f for f in p["fills"]}
        self.assertEqual((roles["RUS"]["role"], roles["RUS"]["start"]), ("red", 0.0))         # the war's sides are coloured from the start
        self.assertGreater(roles["POL"]["start"], 4.0)                                          # Poland lights up when it is named
        self.assertNotEqual(roles["POL"]["role"], roles["LTU"]["role"])
        self.assertEqual([x["name"] for x in p["places"]], ["Vilnius"])
        self.assertEqual(p["places"][0]["kind"], "ring")                                        # named in a strike sentence
        self.assertIn("explosion", [g["kind"] for g in p["glyphs"]])
        self.assertIn("swarm", [g["kind"] for g in p["glyphs"]])                                 # drones named: arrows fly in
        self.assertEqual(p["chips"][0]["title"], "OCTOBER")
        self.assertEqual([c["group"] for c in p["chips"]], [i // 3 for i in range(len(p["chips"]))])
        self.assertFalse([ly for ly in plan.layers if ly.kind in ("kit_tag", "kit_sticker")])    # replaced by the map's own cards
        self.assertEqual(plan.stats["direction"]["counts"].get("empty_stretches", 0), 0)

    def test_nothing_sits_still_for_more_than_four_seconds(self):
        from cinematic_explainer.war.map_build import MAX_STILL_S

        p = next(ly for ly in _plan(SCENES).layers if ly.kind == "tac_map").params
        ev = sorted({0.0, 21.0} | {float(x["start"]) for k in ("places", "glyphs", "routes", "chips", "fills") for x in p.get(k) or []}
                    | {float(x) for x in p.get("focus_times") or []})
        self.assertLessEqual(max(b - a for a, b in zip(ev, ev[1:])), MAX_STILL_S + 0.01)

    def test_old_plans_without_the_switch(self):
        maps = [ly for ly in _plan(SCENES, map_build=False).layers if ly.kind == "tac_map"]
        self.assertTrue(all(ly.end - ly.start < 15 for ly in maps))

    def test_no_geography_anywhere_leaves_the_plan_as_it_was(self):
        sc = [{"scene_no": 1, "text": "Nobody saw it coming at all that night.", "start": 0.0, "end": 5.0},
              {"scene_no": 2, "text": "What happened next surprised even the experts.", "start": 5.0, "end": 11.0}]
        self.assertEqual([ly.kind for ly in _plan(sc).layers if ly.kind == "tac_map"], [])

    def test_a_card_in_the_middle_splits_the_map_without_restarting_it(self):
        from cinematic_explainer.render import Layer
        from cinematic_explainer.war import map_build as MB

        class P:
            layers = [Layer("lay_stat_split", 8.0, 11.0, {})]
            log = []
        rows = [dict(s, _no=s["scene_no"], _start=s["start"], _end=s["end"]) for s in SCENES]
        dec = type("D", (), {"flags": ["no_footage"], "candidates": []})
        log = {str(s["scene_no"]): dec() for s in SCENES}
        counts: dict = {}
        MB.build(P, rows, None, log, counts, [], ("lay_stat_split",))
        maps = sorted((ly for ly in P.layers if ly.kind == "tac_map"), key=lambda ly: ly.start)
        self.assertEqual([(ly.start, ly.end, ly.params["t_offset"]) for ly in maps], [(0.0, 8.0, 0.0), (11.0, 21.0, 11.0)])
        self.assertEqual({ly.params["total_dur"] for ly in maps}, {21.0})


class Render(unittest.TestCase):
    PARAMS = {"theme": "political", "fills": [{"iso3": "RUS", "role": "red"}, {"iso3": "POL", "role": "teal", "start": 3.0}],
              "places": [{"name": "Vilnius", "start": 1.0}], "glyphs": [{"place": "Vilnius", "kind": "swarm", "start": 1.5}],
              "focus": [[{"country": "Poland"}], ["Vilnius"]], "focus_times": [0.0, 4.0],
              "chips": [{"title": "A", "start": 0.5, "group": 0}, {"title": "B", "start": 5.0, "group": 1}]}

    def test_a_piece_renders_the_same_frame_as_the_whole_map(self):
        from cinematic_explainer.war.maps_tactical import tac_map

        whole = tac_map(6.0, 10.0, dict(self.PARAMS))
        piece = tac_map(2.0, 4.0, dict(self.PARAMS, t_offset=4.0, total_dur=10.0))
        self.assertEqual(whole.tobytes(), piece.tobytes())

    def test_the_stack_clears_and_the_country_lights_up(self):
        from cinematic_explainer.war.maps_tactical import render_info, tac_map

        early, late = tac_map(1.0, 10.0, dict(self.PARAMS)), tac_map(6.0, 10.0, dict(self.PARAMS))
        self.assertNotEqual(early.tobytes(), late.tobytes())
        self.assertNotEqual(render_info(dict(self.PARAMS), 1.0, 10.0)["view"], render_info(dict(self.PARAMS), 6.0, 10.0)["view"])   # camera moved on cue


if __name__ == "__main__":
    unittest.main()


class CardSet(unittest.TestCase):
    """Step 2 of docs/war/REFERENCE_PATTERNS.md: speaker cards, chapter openers and the white/red hook label."""

    def test_speakers_and_chapters_from_the_narration(self):
        from cinematic_explainer.war.map_build import card_for, chapter_of, speaker_of

        self.assertEqual(speaker_of("Britain's defence secretary, Wes Streeting, announced it in October."), ("Wes Streeting", "Britain's defence secretary"))
        self.assertEqual(speaker_of("Michel Hofman, a Belgian analyst, said the threat was real."), ("Michel Hofman", "Belgian analyst"))
        self.assertEqual(speaker_of("NATO chief Mark Rutte warned allies."), ("Mark Rutte", "NATO chief"))
        self.assertIsNone(speaker_of("In November, at least 1500 troops are due to gather in Poland."))
        self.assertEqual(chapter_of("Chapter 1, a rehearsal for the day after."), ("CHAPTER 1", "a rehearsal for the day after"))
        self.assertIsNone(chapter_of("Part of the problem is fuel."))
        self.assertEqual(card_for("NATO chief Mark Rutte warned allies."), {"title": "MARK RUTTE", "sub": "NATO chief", "variant": "white"})
        self.assertIsNone(card_for("Chapter two, the Black Sea."))                   # the opener carries it, not the stack

    def test_plan_puts_a_chapter_opener_and_a_speaker_over_footage(self):
        from cinematic_explainer.war import integration as I, planner as P

        d = Path(tempfile.mkdtemp())
        clip = d / "a.mp4"
        clip.write_bytes(b"x")
        sc = [{"scene_no": 1, "text": "Chapter 2, the Black Sea.", "start": 0.0, "end": 4.0, "no_footage": True},
              {"scene_no": 2, "text": "Michel Hofman, a Belgian analyst, expects more drones over the ports.", "start": 4.0, "end": 9.0, "footage": str(clip)}]
        plan = P.plan(I.load_scenes(d, sc), config={"layouts": False})        # with layouts on, a figure layout takes the person (the card yields)
        kinds = {ly.kind: ly for ly in plan.layers}
        self.assertEqual(kinds["kit_chapter"].params, {"label": "CHAPTER 2", "sub": "the Black Sea"})
        self.assertEqual(kinds["kit_speaker"].params, {"name": "Michel Hofman", "role": "Belgian analyst"})   # not in the catalog: no figure card

    def test_cards_render(self):
        from cinematic_explainer.war.cards_kit import kit_chapter, kit_speaker, kit_tag

        for im in (kit_chapter(1.0, 3.6, {"label": "CHAPTER 2", "sub": "the Black Sea"}), kit_speaker(1.0, 4.0, {"name": "Mark Rutte", "role": "NATO chief"}),
                   kit_tag(1.0, 3.2, {"text": "Stay supplied", "style": "hook"})):
            self.assertIsNotNone(im)
            self.assertGreater(im.getbbox()[2], 0)


class NumberCards(unittest.TestCase):
    def test_ratio_and_versus_from_the_narration(self):
        from cinematic_explainer.war.map_build import ratio_of, versus_of

        self.assertEqual(ratio_of("Eight in ten vessel strikes in the Black Sea were Russian, according to Ambrey."),
                         {"value": "8 in 10", "label": "vessel strikes", "sub": "according to Ambrey"})
        self.assertEqual(versus_of("NATO airspace breaches hit 18 this year, compared with 6 the year before."),
                         {"a": "18", "a_label": "this year", "b": "6", "b_label": "the year before"})
        self.assertEqual(versus_of("The first reading passed 106 for and 18 against."), {"a": "106", "a_label": "for", "b": "18", "b_label": "against"})
        self.assertEqual(versus_of("Losses rose from 6% to 18% in a month."), {"a": "18%", "a_label": "now", "b": "6%", "b_label": "before"})
        self.assertIsNone(ratio_of("In 2025 the army had 1500 troops in Poland."))
        self.assertIsNone(versus_of("In 2025 the army had 1500 troops in Poland."))
        self.assertIsNone(ratio_of("Ten in two minutes."))                         # not a share: the first number is larger

    def test_plan_and_render(self):
        from cinematic_explainer.war.cards_kit import kit_versus

        plan = _plan([{"scene_no": 1, "text": "The first reading in Vilnius passed 106 for and 18 against.", "start": 0.0, "end": 6.0},
                      {"scene_no": 2, "text": "Eight in ten vessel strikes near Odesa were Russian.", "start": 26.0, "end": 32.0}])
        kinds = {ly.kind: ly for ly in plan.layers}
        self.assertEqual(kinds["kit_versus"].params["a"], "106")
        self.assertEqual(kinds["kit_bignum"].params["value"], "8 in 10")
        self.assertGreater(kit_versus(1.0, 4.2, kinds["kit_versus"].params).getbbox()[2], 0)


class IconsAndFlags(unittest.TestCase):
    def test_icon_scene_for_things_without_a_place(self):
        plan = _plan([{"scene_no": 1, "text": "In Kharkiv the sirens went off again.", "start": 0.0, "end": 5.0},
                      {"scene_no": 2, "text": "Cheap drones are emptying the stocks of air defence missiles.", "start": 5.0, "end": 11.0},
                      {"scene_no": 3, "text": "Kharkiv is still standing.", "start": 11.0, "end": 16.0}])
        ic = [ly for ly in plan.layers if ly.kind == "kit_icons"]
        self.assertEqual(len(ic), 1)
        self.assertEqual([i["name"] for i in ic[0].params["icons"]][:2], ["drone", "aa_launcher"])
        self.assertEqual(ic[0].params["icons"][0]["label"], "drones")                 # the narration's word
        self.assertEqual(ic[0].params["link"], "arrow")
        maps = [ly for ly in plan.layers if ly.kind == "tac_map"]
        self.assertTrue(maps and all(ly.end <= ic[0].start + 0.01 or ly.start >= ic[0].end - 0.01 for ly in maps))   # the map steps aside

    def test_flag_before_a_chapter_only_for_a_known_flag(self):
        from cinematic_explainer.war.cards_kit import kit_flag

        plan = _plan([{"scene_no": 1, "text": "The front in Ukraine barely moved.", "start": 0.0, "end": 6.0},
                      {"scene_no": 2, "text": "Chapter 2, Poland gets ready.", "start": 6.0, "end": 10.0}])
        fl = [ly for ly in plan.layers if ly.kind == "kit_flag"]
        self.assertEqual([(ly.params["iso3"], ly.end) for ly in fl], [("POL", 6.0)])
        self.assertIsNone(kit_flag(0.5, 1.0, {"iso3": "GBR"}))                         # not a stripe flag: nothing is drawn
