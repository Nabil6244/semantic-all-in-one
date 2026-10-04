"""Hybrid Map H2: timed narration, the Director's answer -> HybridPlan, deterministic validation, the critic's schema and the bounded
repair loop. A scripted fake LLM stands in for Gemini: no network, no key."""

from __future__ import annotations

import copy
import json
import re
import unittest

from hybrid import critic as critic_mod
from hybrid.director import DirectorError, derive_cameras, plan_beats, plan_from_payload, repair_beats, anchor_time, director_prompt
from hybrid.narration import build_sentences, split_script
from hybrid.pipeline import MAX_REPAIRS, plan_hybrid
from hybrid.plan import HybridPlan
from hybrid.validate import errors, validate, warnings

SCRIPT = (
    "Pakistan is a long country. It stretches from the Arabian Sea to the Karakoram. Most of its people live along one river. "
    "That river is the Indus. Farmers here plant wheat in the winter. They flood their fields from canals. In the north the mountains rise "
    "above seven thousand metres. Glaciers feed the river all summer. Far to the west lies Balochistan. It is almost half the country. "
    "Yet it holds only a small fraction of the people."
)


def synth_words(script: str, wps: float = 2.6, pause: float = 0.6):
    """Whisper-like words (lowercase, no punctuation) with a pause after each sentence."""
    words, t = [], 0.0
    for sent in split_script(script):
        for tok in sent.split():
            clean = re.sub(r"[^0-9a-z]+", "", tok.lower())
            if clean:
                words.append((clean, round(t, 3), round(t + 0.8 / wps, 3)))
                t += 1.0 / wps
        t += pause
    return words


WORDS = synth_words(SCRIPT)
DURATION = round(WORDS[-1][2] + 0.5, 3)
SENTENCES = build_sentences(WORDS, SCRIPT, DURATION)


def payload(**over):
    p = {"beats": [
        {"sentences": [0, 2], "mode": "map", "purpose": "locate the country and its river", "confidence": 0.9,
         "map": {"geo_intent": "show how long Pakistan is and where the people live", "camera": {"place": "Pakistan", "frame": "country", "move": "fly_to"},
                 "overlay_intent": "the country fill and the river line", "layers": [
                     {"type": "hud_title", "anchor": "pakistan is", "label": "PART 1", "sub": "ONE RIVER"},
                     {"type": "fill", "anchor": "long country", "place": "Pakistan", "role": "subject", "until": "after_footage"},
                     {"type": "line", "anchor": "one river", "kind": "river", "places": ["35.30,75.60", "29.40,71.00", "24.00,67.60"], "until": "after_footage"}]}},
        {"sentences": [3, 5], "mode": "footage", "purpose": "feel the farming on the river",
         "footage": {"footage_intent": "farmers working flooded wheat fields", "clips": [{"source": "stock_video", "query": "farmers irrigating wheat fields from a canal", "reason": "shows the work the map cannot"}]}},
        {"sentences": [6, 7], "mode": "map_footage", "purpose": "the north feeds the river",
         "map": {"geo_intent": "the Karakoram feeds the Indus", "camera": {"place": "Gilgit", "frame": "region", "move": "fly_to"}, "layers": [
             {"type": "marker", "anchor": "mountains rise", "place": "35.30,75.64", "label": "SKARDU", "role": "featured"}]},
         "support": {"source": "stock_image", "query": "glacier in the karakoram", "place": "35.30,75.64", "label": "GLACIER", "anchor": "glaciers feed"}},
        {"sentences": [8, 10], "mode": "map", "purpose": "the empty west",
         "map": {"geo_intent": "Balochistan is huge and empty", "camera": {"place": "Balochistan", "frame": "region", "move": "fly_to"}, "layers": [
             {"type": "fill", "anchor": "balochistan", "place": "Balochistan", "role": "compare"},
             {"type": "stat", "anchor": "almost half", "from": 0, "to": 44, "format": "0% OF THE COUNTRY", "sub": "BALOCHISTAN"}]}},
    ]}
    p.update(over)
    return p


class FakeLLM:
    """complete(system, user) -> the next scripted answer. A callable answer receives (system, user)."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def complete(self, system, user):
        self.calls.append((system, user))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return a(system, user) if callable(a) else (a if isinstance(a, str) else json.dumps(a))


class TestNarration(unittest.TestCase):
    def test_the_script_splits_into_sentences(self):
        s = split_script("One two. Three four! Is it five? Yes.\n\nNew paragraph here.")
        self.assertEqual(s, ["One two.", "Three four!", "Is it five?", "Yes.", "New paragraph here."])

    def test_sentences_get_real_times_from_the_words(self):
        self.assertEqual(len(SENTENCES), 11)
        for a, b in zip(SENTENCES, SENTENCES[1:]):
            self.assertLessEqual(a.end, b.start + 1e-9)
        self.assertEqual(SENTENCES[0].start, WORDS[0][1])
        self.assertAlmostEqual(SENTENCES[0].end, WORDS[4][2], places=2)  # "pakistan is a long country" ends at the 5th word
        self.assertTrue(all(s.end > s.start for s in SENTENCES))

    def test_a_spoken_number_that_the_script_writes_as_digits_does_not_break_the_alignment(self):
        script = "There are 47 million people. They live in the south."
        words = [("there", 0, .3), ("are", .3, .5), ("forty", .5, .8), ("seven", .8, 1.1), ("million", 1.1, 1.5), ("people", 1.5, 1.9),
                 ("they", 2.6, 2.8), ("live", 2.8, 3.0), ("in", 3.0, 3.1), ("the", 3.1, 3.2), ("south", 3.2, 3.7)]
        s = build_sentences(words, script, 4.0)
        self.assertEqual((round(s[0].start, 1), round(s[0].end, 1)), (0.0, 1.9))
        self.assertEqual((round(s[1].start, 1), round(s[1].end, 1)), (2.6, 3.7))

    def test_without_a_script_sentences_come_from_pauses(self):
        s = build_sentences(WORDS, None, DURATION)
        self.assertGreaterEqual(len(s), 8)
        self.assertTrue(all(x.text.endswith(".") for x in s))

    def test_a_script_that_is_not_what_was_spoken_is_not_pretended(self):
        s = build_sentences(WORDS, "Completely different words about another subject entirely. Nothing matches here at all.", DURATION)
        self.assertTrue(len(s) >= 5)  # fell back to the pauses
        self.assertNotEqual([x.text for x in s][0], "Completely different words about another subject entirely.")


class TestPayloadToPlan(unittest.TestCase):
    def build(self, p=None):
        return plan_from_payload(p or payload(), SENTENCES, WORDS, DURATION)

    def test_beats_get_real_times_that_tile_the_narration(self):
        plan, problems = self.build()
        self.assertEqual(problems, [])
        self.assertEqual(plan.beats[0].start, 0.0)
        self.assertEqual(plan.beats[-1].end, DURATION)
        for a, b in zip(plan.beats, plan.beats[1:]):
            self.assertEqual(a.end, b.start)
        # the boundary is the pause between the two sentences
        self.assertAlmostEqual(plan.beats[0].end, (SENTENCES[2].end + SENTENCES[3].start) / 2, places=2)
        self.assertEqual([b.mode for b in plan.beats], ["map", "footage", "map_footage", "map"])
        self.assertIn("Most of its people live along one river", plan.beats[0].narration)

    def test_overlay_anchors_become_narration_times_inside_their_beat(self):
        plan, problems = self.build()
        lay = {l.type: l for l in plan.beats[0].layers}
        self.assertAlmostEqual(lay["hud_title"].t, WORDS[0][1], places=2)
        said = {w[0]: w[1] for w in WORDS}
        self.assertAlmostEqual(lay["line"].t, next(w[1] for w in WORDS if w[0] == "one" and w[1] > 3), places=2)
        self.assertTrue(all(plan.beats[0].start <= l.t < plan.beats[0].end for l in plan.beats[0].layers))
        self.assertEqual([l.id for l in plan.beats[0].layers], ["b1_hud_title1", "b1_fill2", "b1_line3"])

    def test_an_anchor_that_is_not_in_the_beat_is_placed_and_reported(self):
        p = payload()
        p["beats"][0]["map"]["layers"][1]["anchor"] = "words that are never spoken"
        plan, problems = self.build(p)
        self.assertTrue(any("beat b1" in x and "was not found" in x for x in problems), problems)
        self.assertTrue(plan.beats[0].start <= plan.beats[0].layers[1].t < plan.beats[0].end)

    def test_gaps_overlaps_and_bad_modes_are_reported_and_worked_around(self):
        p = payload()
        p["beats"][1]["sentences"] = [4, 5]            # sentence 3 is now in no beat
        p["beats"][3]["mode"] = "video"
        plan, problems = self.build(p)
        text = " | ".join(problems)
        self.assertIn("in no beat", text)
        self.assertIn("mode 'video'", text)
        self.assertEqual(plan.beats[-1].end, DURATION)                       # still a usable, gap-free plan
        for a, b in zip(plan.beats, plan.beats[1:]):
            self.assertEqual(a.end, b.start)
        p = payload(); p["beats"][1]["sentences"] = [2, 5]
        self.assertTrue(any("overlaps" in x for x in self.build(p)[1]))

    def test_footage_clips_become_source_references_and_stills_get_a_slow_push(self):
        p = payload()
        p["beats"][1]["footage"]["clips"].append({"source": "stock_image", "query": "terraced fields", "reason": "a still"})
        plan, _ = self.build(p)
        c = plan.beats[1].clips
        self.assertEqual([x.asset for x in c], ["stock_video:farmers irrigating wheat fields from a canal", "stock_image:terraced fields"])
        self.assertEqual([x.kenburns for x in c], [False, True])
        self.assertEqual(plan.beats[1].footage_intent, "farmers working flooded wheat fields")
        self.assertEqual(plan.beats[1].transition_sound, "")

    def test_a_map_footage_beat_carries_its_card(self):
        plan, problems = self.build()
        b = plan.beats[2]
        self.assertEqual(b.mode, "map_footage")
        self.assertEqual((b.support.asset, b.support.place, b.support.label), ("stock_image:glacier in the karakoram", "35.30,75.64", "GLACIER"))
        self.assertAlmostEqual(b.support.t, next(w[1] for w in WORDS if w[0] == "glaciers"), places=2)

    def test_the_camera_starts_once_and_moves_clear_of_the_footage_dissolves(self):
        plan, _ = self.build()
        steps = [(b.id, c.action, c.place) for b in plan.beats for c in b.camera]
        self.assertEqual(steps[0], ("b1", "start", "Pakistan"))
        self.assertEqual([s[1] for s in steps], ["start", "fly_to", "fly_to", "fly_to"])   # the opening fly-in, then one move per later beat
        first = plan.beats[0].camera
        self.assertEqual([(c.frame, c.t) for c in first], [("globe", 0.0), ("country", 1.4)])  # the planet for 1.4 s, then close
        legacy, _ = self.build()
        legacy.settings["globe_opening"] = False
        from hybrid.director import derive_cameras
        derive_cameras(legacy)
        self.assertEqual([c.action for b in legacy.beats for c in b.camera], ["start", "fly_to", "fly_to"])
        half = plan.setting("dissolve_s") / 2
        mv = plan.beats[2].camera[0]
        self.assertGreaterEqual(mv.t, plan.beats[2].start + half)             # after the dissolve out of the footage beat
        self.assertEqual(validate(plan), validate(plan))                      # idempotent
        self.assertEqual([f for f in validate(plan) if f.severity == "error"], [])

    def test_a_very_long_jump_pulls_out_to_the_globe_and_back_in_but_a_short_one_does_not(self):
        p = payload()
        p["beats"][3]["map"]["camera"] = {"place": "Kenya", "frame": "country", "move": "fly_to"}   # about 5000 km from Gilgit
        plan, _ = self.build(p)
        steps = [(c.action, c.place, c.frame) for c in plan.beats[3].camera]
        self.assertEqual(steps, [("fly_to", "Kenya", "globe"), ("fly_to", "Kenya", "country")])
        first, second = plan.beats[3].camera
        self.assertAlmostEqual(second.t, first.t + first.dur, places=2)                          # one continuous manoeuvre
        self.assertGreaterEqual(first.t, plan.beats[3].start)
        self.assertEqual([f for f in validate(plan) if f.severity == "error"], [])
        short, _ = self.build()                                                                   # Gilgit -> Balochistan is well under the threshold
        self.assertEqual([c.frame for c in short.beats[3].camera], ["region"])
        short.settings["globe_hop_km"] = 100000
        p2 = payload(); p2["beats"][3]["map"]["camera"] = {"place": "Kenya", "frame": "country", "move": "fly_to"}
        off, _ = self.build(p2)
        from hybrid.director import derive_cameras
        off.settings["globe_hop_km"] = 100000
        derive_cameras(off)
        self.assertEqual(len(off.beats[3].camera), 1)

    def test_the_same_place_means_the_camera_holds(self):
        p = payload()
        p["beats"][3]["map"]["camera"] = {"place": "Gilgit", "frame": "region", "move": "fly_to"}
        plan, _ = self.build(p)
        self.assertEqual([c.action for c in plan.beats[3].camera], [])

    def test_the_prompt_is_its_own_document(self):
        text = director_prompt()
        for needle in ("Hybrid Map", "NO visual churn", "map_footage", "persistent", "Never invent a statistic"):
            self.assertIn(needle, text.replace("Do not invent a statistic", "Never invent a statistic"))
        self.assertNotIn("Fact Map", text)
        self.assertNotIn("PakMap", text)


class TestValidation(unittest.TestCase):
    def plan(self, **mut):
        plan, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        for k, v in mut.items():
            setattr(plan, k, v)
        return plan

    def codes(self, plan, severity=None):
        return [f.code for f in validate(plan) if severity is None or f.severity == severity]

    def test_a_good_plan_has_no_errors_and_each_beat_carries_its_verdict(self):
        plan = self.plan()
        self.assertEqual(errors(validate(plan)), [])
        self.assertTrue(all(b.validation in ("ok", "warnings") for b in plan.beats))

    def test_footage_too_short_to_mean_anything_is_an_error_and_a_barely_there_one_a_warning(self):
        plan = self.plan()
        plan.beats[1].end = plan.beats[1].start + 1.5
        plan.beats[2].start = plan.beats[1].end
        self.assertIn("footage_too_short", self.codes(plan, "error"))
        plan = self.plan()
        plan.beats[1].end = plan.beats[1].start + 3.0
        plan.beats[2].start = plan.beats[1].end
        self.assertIn("footage_short", self.codes(plan, "warning"))

    def test_a_map_beat_with_nothing_to_show_is_an_error(self):
        plan = self.plan()
        b = plan.beats[3]
        b.layers, b.camera, b.cam_place, b.geo_intent = [], [], "", ""
        self.assertIn("map_no_geography", self.codes(plan, "error"))

    def test_a_footage_beat_without_a_clip_or_a_purpose(self):
        plan = self.plan()
        plan.beats[1].clips = []
        self.assertTrue(any("needs at least one clip" in f.message for f in validate(plan) if f.severity == "error"))
        plan = self.plan()
        plan.beats[1].footage_intent = ""
        for c in plan.beats[1].clips:
            c.reason = ""
        self.assertIn("footage_no_intent", self.codes(plan, "warning"))

    def test_unsupported_assets_and_transitions_are_errors(self):
        plan = self.plan()
        plan.beats[1].clips[0].asset = "stok_video:farmers"
        plan.beats[0].transition = "wipe"
        msgs = " | ".join(f.message for f in validate(plan) if f.severity == "error")
        self.assertIn("unsupported asset type 'stok_video'", msgs)
        self.assertIn("transition 'wipe' is not supported", msgs)

    def test_excessive_visual_churn_is_a_warning_not_a_block(self):
        d = {"version": 1, "duration": 60.0, "settings": {}, "beats": []}
        t = 0.0
        for i in range(10):
            mode = "map" if i % 2 == 0 else "footage"
            beat = {"id": f"b{i + 1}", "mode": mode, "start": t, "end": t + 6.0, "geo_intent": "x", "footage_intent": "y"}
            if mode == "map":
                beat["camera"] = [{"action": "start", "place": "Kenya", "frame": "country"}] if i == 0 else []
                beat["layers"] = [{"id": f"l{i}", "type": "marker", "t": t + 1, "place": "Nairobi", "label": "N"}]
            else:
                beat["footage"] = {"clips": [{"asset": f"stock_video:shot {i}"}]}
            d["beats"].append(beat)
            t += 6.0
        plan = HybridPlan.from_dict(d)
        found = validate(plan)
        self.assertIn("churn", [f.code for f in found if f.severity == "warning"])
        self.assertEqual(errors(found), [])

    def test_repeated_footage_and_redundant_map_beats_are_flagged(self):
        plan = self.plan()
        plan.beats[2].support.asset = plan.beats[1].clips[0].asset
        self.assertIn("repeated_footage", self.codes(plan, "warning"))

    def test_conflicting_overlays_are_named(self):
        plan = self.plan()
        for i in range(3):
            plan.beats[0].layers.append(copy.deepcopy(plan.beats[0].layers[0]))
            plan.beats[0].layers[-1].id, plan.beats[0].layers[-1].type, plan.beats[0].layers[-1].t = f"x{i}", "stat", 1.0 + i * 0.1
            plan.beats[0].layers[-1].value_to = 5.0
        self.assertIn("overlay_conflict", self.codes(plan, "error"))

    def test_a_chip_that_appears_with_no_time_left_to_read_it_is_flagged(self):
        plan = self.plan()
        plan.beats[3].layers[1].t = plan.beats[3].end - 1.2              # the number chip, 1.2 s before its beat (and the video) ends
        found = [f for f in validate(plan) if f.code == "layer_late"]
        self.assertEqual([(f.severity, f.beat) for f in found], [("warning", "b4")])
        self.assertIn("too short to read", found[0].message)
        self.assertEqual([f for f in validate(self.plan()) if f.code == "layer_late"], [])

    def test_a_caption_too_long_for_the_screen_is_flagged_and_repairable(self):
        from hybrid.pipeline import REPAIRABLE_WARNINGS
        plan = self.plan()
        cap = copy.deepcopy(plan.beats[0].layers[0])
        cap.id, cap.type, cap.t, cap.text = "capx", "caption", 1.0, "Balochistan: Covers ~50% of land area, home to <5% of population"
        plan.beats[0].layers.append(cap)
        found = [f for f in validate(plan) if f.code == "text_too_long"]
        self.assertEqual([(f.severity, f.beat) for f in found], [("warning", plan.beats[0].id)])
        self.assertIn("text_too_long", REPAIRABLE_WARNINGS)
        cap.text = "BALOCHISTAN: HALF THE LAND"
        self.assertEqual([f for f in validate(plan) if f.code == "text_too_long"], [])

    def test_a_stat_format_that_contains_the_number_is_an_error_but_real_patterns_pass(self):
        plan = self.plan()
        st = copy.deepcopy(plan.beats[0].layers[0]); st.id, st.type, st.t, st.value_to = "stx", "stat", 1.0, 37000000.0
        plan.beats[0].layers.append(st)
        for good in ("0 MILLION PEOPLE", "#,##0 KM", "0.0M", "0/5", "M0.0", "0.0 °C"):
            st.format = good
            self.assertEqual([f for f in validate(plan) if f.code == "stat_format"], [], good)
        st.format = "37,000,000 PEOPLE"
        found = [f for f in validate(plan) if f.code == "stat_format"]
        self.assertEqual([(f.severity, f.beat) for f in found], [("error", plan.beats[0].id)])
        st.format = "PEOPLE"
        self.assertEqual(len([f for f in validate(plan) if f.code == "stat_format"]), 1)

    def test_the_globe_is_for_the_opening_only_and_a_coordinate_cannot_make_a_region_view(self):
        from hybrid.plan import CameraStep
        from hybrid.pipeline import REPAIRABLE_WARNINGS
        plan = self.plan()
        self.assertEqual([c for c in self.codes(plan) if c in ("wide_view", "point_zoom")], [])
        plan.beats[0].camera = [CameraStep(action="start", place="Pakistan", frame="globe", t=0.0), CameraStep(action="fly_to", place="Pakistan", frame="country", t=1.5, dur=2.0)]
        self.assertEqual([c for c in self.codes(plan) if c == "wide_view"], [], "a globe opening that flies in is exactly right")
        plan.beats[3].camera = [CameraStep(action="fly_to", place="Balochistan", frame="continental", t=26.3, dur=2.4)]
        wide = [f for f in validate(plan) if f.code == "wide_view"]
        self.assertEqual([(f.severity, f.beat) for f in wide], [("warning", "b4")])
        plan.beats[3].camera = [CameraStep(action="fly_to", place="35.88,76.51", frame="region", t=26.3, dur=2.4)]
        pt = [f for f in validate(plan) if f.code == "point_zoom"]
        self.assertEqual([(f.severity, f.beat) for f in pt], [("warning", "b4")])
        self.assertTrue({"wide_view", "point_zoom"} <= REPAIRABLE_WARNINGS)

    def test_more_than_five_text_layers_at_once_is_an_error_like_the_renderers_rule(self):
        plan = self.plan()
        base = plan.beats[0]
        for i in range(6):
            lay = copy.deepcopy(base.layers[0])
            lay.id, lay.type, lay.t, lay.label, lay.sub = f"m{i}", "marker", 1.0 + i * 0.1, f"M{i}", ""
            lay.until = "end"
            base.layers.append(lay)
        errs = [f for f in validate(plan) if f.code == "overlay_conflict" and "text layers" in f.message]
        self.assertTrue(errs and errs[0].severity == "error")

    def test_warnings_never_block(self):
        plan = self.plan()
        plan.beats[3].geo_intent = ""
        found = validate(plan)
        self.assertTrue(warnings(found))
        self.assertEqual(errors(found), [])


class TestRetries(unittest.TestCase):
    def setUp(self):
        import hybrid.director as d

        self.d, self.saved = d, d.RETRY_DELAYS
        d.RETRY_DELAYS = (0.0, 0.0, 0.0)

    def tearDown(self):
        self.d.RETRY_DELAYS = self.saved

    def test_a_busy_provider_is_retried_and_the_plan_still_comes(self):
        from visual_director.llm import LLMError

        calls = []

        def flaky(system, user):
            calls.append(1)
            if len(calls) < 3:
                raise LLMError("Gemini API error: This model is currently experiencing high demand. Spikes in demand are usually temporary.")
            return json.dumps(payload())

        plan, _ = plan_beats(FakeLLM(flaky), SENTENCES, WORDS, DURATION)
        self.assertEqual((len(calls), len(plan.beats)), (3, 4))

    def test_a_real_failure_is_not_retried(self):
        from visual_director.llm import LLMError

        calls = []

        def broken(system, user):
            calls.append(1)
            raise LLMError("Gemini API key is not configured")

        with self.assertRaises(LLMError):
            plan_beats(FakeLLM(broken), SENTENCES, WORDS, DURATION)
        self.assertEqual(len(calls), 1)

    def test_it_gives_up_after_the_last_delay(self):
        from visual_director.llm import LLMError

        calls = []

        def busy(system, user):
            calls.append(1)
            raise LLMError("503 unavailable")

        with self.assertRaises(LLMError):
            plan_beats(FakeLLM(busy), SENTENCES, WORDS, DURATION)
        self.assertEqual(len(calls), len(self.d.RETRY_DELAYS) + 1)


class TestPlacesAndAnchors(unittest.TestCase):
    def build(self, p):
        return plan_from_payload(p, SENTENCES, WORDS, DURATION)[0]

    def test_a_place_pakmap_cannot_find_is_an_error_that_names_it_and_says_what_to_do(self):
        p = payload()
        p["beats"][2]["map"]["layers"][0]["place"] = "Skardu"
        found = [f for f in validate(self.build(p)) if f.code == "unresolved_place"]
        self.assertEqual(len(found), 1)
        self.assertIn("'Skardu'", found[0].message)
        self.assertIn('"lat,lon"', found[0].message)
        self.assertEqual(found[0].beat, "b3")

    def test_coordinates_are_accepted_for_features_the_gazetteer_lacks(self):
        self.assertEqual([f for f in validate(self.build(payload())) if f.code == "unresolved_place"], [])

    def test_a_fill_must_be_an_area(self):
        p = payload()
        p["beats"][0]["map"]["layers"][1]["place"] = "Lahore"
        self.assertIn("fill_not_area", [f.code for f in validate(self.build(p)) if f.severity == "error"])

    def test_a_country_suffix_is_stripped_when_that_makes_the_place_findable(self):
        from hybrid.director import clean_place

        self.assertEqual(clean_place("Balochistan, Pakistan"), "Balochistan")
        self.assertEqual(clean_place("Lahore"), "Lahore")
        self.assertEqual(clean_place("35.3,75.6"), "35.3,75.6")
        self.assertEqual(clean_place("city:Moscow,RUS"), "city:Moscow,RUS")
        self.assertEqual(clean_place("Somewhere Unknown, Nowhere"), "Somewhere Unknown, Nowhere")

    def test_a_coordinate_far_from_the_story_is_questioned(self):
        p = payload()
        p["beats"][3]["map"]["layers"].append({"type": "marker", "anchor": "yet it holds", "place": "-33.9,18.4", "label": "NOT HERE"})
        self.assertIn("place_outlier", [f.code for f in validate(self.build(p)) if f.severity == "warning"])

    def test_a_marker_outside_the_cameras_view_is_flagged_and_sent_back_for_repair(self):
        p = payload()
        p["beats"][3]["map"]["camera"] = {"place": "Quetta", "frame": "local", "move": "fly_to"}                      # a city-sized view...
        p["beats"][3]["map"]["layers"].append({"type": "marker", "anchor": "small fraction", "place": "Lahore", "label": "LAHORE"})   # ...with a city 700 km away
        found = [f for f in validate(self.build(p)) if f.code == "out_of_frame"]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].severity, found[0].beat), ("warning", "b4"))
        self.assertIn("LAHORE", found[0].message)
        self.assertEqual([f for f in validate(self.build(payload())) if f.code == "out_of_frame"], [])
        from hybrid.pipeline import _weak_beats
        from hybrid import critic as cm
        plan = self.build(p)
        self.assertIn("b4", _weak_beats(plan, validate(plan), cm.Critique(), []))

    def test_a_spoken_number_anchors_a_written_one_and_the_reverse(self):
        words = [("it", 0.0, .2), ("has", .2, .4), ("240", .4, 1.0), ("million", 1.0, 1.4), ("people", 1.4, 1.8)]
        self.assertAlmostEqual(anchor_time(words, "two hundred and forty million", 0, 3), 0.4, places=2)
        spoken = [("it", 0.0, .2), ("has", .2, .4), ("forty", .4, .6), ("seven", .6, .9), ("million", .9, 1.3)]
        self.assertAlmostEqual(anchor_time(spoken, "47 million", 0, 3), 0.4, places=2)
        self.assertIsNone(anchor_time(spoken, "never said", 0, 3))

    def test_a_beat_redone_keeps_its_own_place_on_the_timeline(self):
        redo = {"beats": [{"sentences": [3, 5], "mode": "map", "purpose": "x", "map": {"geo_intent": "g", "camera": {"place": "Punjab", "frame": "region"},
                                                                                        "layers": [{"type": "marker", "anchor": "farmers here", "place": "Lahore", "label": "LAHORE"}]}}]}
        base, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        fixed, _ = repair_beats(FakeLLM(redo), base, {"b2": ["x"]}, SENTENCES, WORDS)
        b = fixed.beats[1]
        self.assertTrue(b.start <= b.layers[0].t < b.end, (b.start, b.layers[0].t, b.end))
        self.assertEqual((b.start, b.end), (base.beats[1].start, base.beats[1].end))


class TestCritic(unittest.TestCase):
    def test_structured_findings_for_real_beats_only(self):
        raw = {"overall": {"balance": "balanced", "coherence": 4, "summary": "ok"}, "findings": [
            {"beat": "b2", "severity": "weak", "category": "motivation", "issue": "why footage here?", "suggestion": "fold into the map"},
            {"beat": "b9", "severity": "weak", "category": "mode", "issue": "no such beat"},
            {"beat": "b1", "severity": "bogus", "category": "nonsense", "issue": "x"}]}
        c = critic_mod.parse_critique(raw, ["b1", "b2", "b3"])
        self.assertEqual([(f.beat, f.severity, f.category) for f in c.findings], [("b2", "weak", "motivation"), ("b1", "note", "motivation")])
        self.assertEqual(list(c.weak()), ["b2"])
        self.assertTrue(c.ran)

    def test_the_critic_sees_what_a_number_chip_says_not_an_empty_label(self):
        plan, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        text = critic_mod.plan_summary(plan, validate(plan))
        self.assertIn("0 -> 44 '0% OF THE COUNTRY' sub 'BALOCHISTAN'", text)
        self.assertIn("river through 35.30,75.60 > 29.40,71.00 > 24.00,67.60", text)
        self.assertIn("hud_title 'PART 1' / 'ONE RIVER'", text)
        self.assertNotIn("NO VALUE", text)

    def test_the_critic_sees_the_plan_and_the_validator_and_is_asked_for_json_only(self):
        plan, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        llm = FakeLLM({"findings": []})
        found = validate(plan)
        c = critic_mod.critique(llm, plan, found)
        system, user = llm.calls[0]
        self.assertIn("You do NOT rewrite it", system)
        self.assertIn("b2", user)
        self.assertIn("farmers irrigating", user)
        self.assertEqual(c.findings, [])

    def test_a_non_object_answer_is_refused(self):
        with self.assertRaises(DirectorError):
            critic_mod.parse_critique(["nope"], ["b1"])


class TestPipelineAndRepair(unittest.TestCase):
    def director_or_critic(self, plans, critiques):
        """Route by the system prompt: the critic prompt starts 'You are the editorial critic'."""
        plans, critiques = list(plans), list(critiques)

        def answer(system, user):
            if system.startswith("You are the editorial critic"):
                return json.dumps(critiques.pop(0) if len(critiques) > 1 else critiques[0])
            return json.dumps(plans.pop(0) if len(plans) > 1 else plans[0])

        return FakeLLM(answer)

    def test_a_clean_plan_needs_no_repair(self):
        llm = self.director_or_critic([payload()], [{"findings": []}])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION, critic_policy="always", max_repairs=MAX_REPAIRS)
        self.assertEqual(res.repair_passes, 0)
        self.assertTrue(res.ok)
        self.assertEqual(len(llm.calls), 2)                                   # one plan, one critique

    def test_only_the_weak_beat_is_redone_and_everything_else_is_untouched(self):
        redo = {"beats": [{"sentences": [3, 5], "mode": "map", "purpose": "show the canals on the map",
                           "map": {"geo_intent": "the canal system of the Indus plain", "camera": {"place": "Punjab", "frame": "region", "move": "fly_to"},
                                   "layers": [{"type": "line", "anchor": "canals", "kind": "flow", "places": ["Lahore", "Multan"]}]}}]}
        weak = {"findings": [{"beat": "b2", "severity": "weak", "category": "motivation", "issue": "a stock shot adds nothing here", "suggestion": "use the map"}]}
        llm = self.director_or_critic([payload(), redo], [weak, {"findings": []}])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION, critic_policy="always", max_repairs=MAX_REPAIRS)
        self.assertEqual((res.repair_passes, res.repaired), (1, [["b2"]]))
        self.assertEqual(res.plan.beats[1].mode, "map")
        self.assertEqual(res.plan.beats[1].geo_intent, "the canal system of the Indus plain")
        original, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        for i in (0, 2, 3):                                                   # the other beats are exactly as the Director first made them
            self.assertEqual(res.plan.beats[i].mode, original.beats[i].mode)
            self.assertEqual((res.plan.beats[i].start, res.plan.beats[i].end), (original.beats[i].start, original.beats[i].end))
            self.assertEqual([l.label for l in res.plan.beats[i].layers], [l.label for l in original.beats[i].layers])
        self.assertEqual((res.plan.beats[1].start, res.plan.beats[1].end), (original.beats[1].start, original.beats[1].end))  # timing never changes
        self.assertTrue(res.ok)

    def test_several_redone_beats_go_back_to_the_right_beats_whatever_order_the_director_answers_in(self):
        # found by the real Director: it answers in timeline order, not the order the beats were sent in
        base, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        def beat(sent, place):
            return {"sentences": sent, "mode": "map", "purpose": f"about {place}", "map": {"geo_intent": f"show {place}", "camera": {"place": place, "frame": "region"},
                                                                                      "layers": [{"type": "fill", "anchor": place.lower(), "place": place, "role": "subject"}]}}
        a, d = beat([0, 2], "Punjab"), beat([8, 10], "Balochistan")
        weak = {"b4": ["x"], "b1": ["y"]}                                       # sent in the "wrong" order
        for answers, label in (([a, d], "no ids, timeline order"), ([{**d, "beat": "b4"}, {**a, "beat": "b1"}], "echoed ids, any order"), ([d, a], "ranges only, reversed")):
            fixed, _ = repair_beats(FakeLLM({"beats": answers}), base, weak, SENTENCES, WORDS)
            self.assertEqual(fixed.beats[0].geo_intent, "show Punjab", label)
            self.assertEqual(fixed.beats[3].geo_intent, "show Balochistan", label)
            self.assertEqual((fixed.beats[1].mode, fixed.beats[2].mode), ("footage", "map_footage"), label)   # the others are untouched

    def test_the_loop_is_bounded_even_when_the_critic_never_stops_complaining(self):
        weak = {"findings": [{"beat": "b2", "severity": "weak", "category": "mode", "issue": "still wrong", "suggestion": ""}]}
        redo = {"beats": [payload()["beats"][1]]}
        llm = self.director_or_critic([payload(), redo], [weak])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION, critic_policy="always", max_repairs=MAX_REPAIRS)
        self.assertEqual(res.repair_passes, MAX_REPAIRS)
        self.assertLessEqual(len(llm.calls), 1 + MAX_REPAIRS * 2 + 1)         # plan + (critic, repair) per pass + the last critique
        self.assertTrue(res.ok)                                               # critic complaints are warnings: the plan is kept

    def test_a_validator_error_sends_that_beat_back_even_without_the_critic(self):
        bad = payload()
        bad["beats"][1]["footage"]["clips"] = [{"source": "stok_video", "query": "farmers"}]       # unsupported source
        llm = self.director_or_critic([bad, {"beats": [payload()["beats"][1]]}], [{"findings": []}])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION)
        self.assertEqual(res.repaired[0], ["b2"])
        self.assertTrue(res.ok)
        self.assertEqual(res.plan.beats[1].clips[0].asset.split(":")[0], "stock_video")

    def test_a_plan_with_nothing_suspicious_is_accepted_without_any_critic_call(self):
        llm = self.director_or_critic([payload()], [{"findings": [{"beat": "b2", "severity": "weak", "category": "mode", "issue": "x"}]}])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION)
        kinds = [("critic" if system.startswith("You are the editorial critic") else "director") for system, _ in llm.calls]
        self.assertEqual(kinds, ["director"])                       # the plan passed its local checks, so the critic was never asked
        self.assertTrue(res.stats.get("critic_skipped"))
        self.assertEqual((res.repair_passes, res.stats["critic_calls"]), (0, 0))

    def test_one_repair_cycle_is_the_default_even_when_the_critic_keeps_complaining(self):
        weak = {"findings": [{"beat": "b2", "severity": "weak", "category": "mode", "issue": "still wrong", "suggestion": ""}]}
        redo = {"beats": [payload()["beats"][1]]}
        llm = self.director_or_critic([payload(), redo], [weak])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION, critic_policy="always")
        self.assertEqual(res.repair_passes, 1)
        self.assertLessEqual(len(llm.calls), 4)                     # plan, critic, repair, and (policy always) one last look: never a second repair

    def test_things_code_can_fix_are_fixed_without_asking_an_ai(self):
        bad = payload()
        bad["beats"][3]["map"]["layers"] = [{"type": "caption", "anchor": "balochistan", "text": "BALOCHISTAN COVERS NEARLY HALF OF ALL OF PAKISTAN'S LAND"},
                                           {"type": "stat", "anchor": "half", "from": 0, "to": 44000000, "format": "44,000,000 PEOPLE", "sub": "X"}]
        llm = self.director_or_critic([bad], [{"findings": []}])
        res = plan_hybrid(WORDS, llm, script=SCRIPT, duration=DURATION)
        lay = res.plan.beats[3].layers
        self.assertLessEqual(len(next(l for l in lay if l.type == "caption").text), 44)
        self.assertEqual(next(l for l in lay if l.type == "stat").format, "#,##0 PEOPLE")
        self.assertGreaterEqual(res.stats["local_fixes"], 2)
        self.assertEqual(len(llm.calls), 1)                         # fixed locally: no critic, no repair
        self.assertTrue(res.ok)

    def test_a_critic_request_is_one_compact_line_per_beat(self):
        plan, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        text = critic_mod.plan_summary(plan, validate(plan))
        self.assertEqual(len(text.splitlines()), 1 + len(plan.beats) + (1 if any(f.beat == "" for f in validate(plan)) else 0))
        self.assertNotIn("{", text.split("\n", 1)[1])               # no JSON scaffolding

    def test_a_loaded_plan_with_a_bad_place_gets_only_that_beat_repaired(self):
        from hybrid.pipeline import repair_errors

        bad = payload()
        bad["beats"][2]["map"]["layers"][0]["place"] = "Skardu"                       # not in the gazetteer: an error
        plan, _ = plan_from_payload(bad, SENTENCES, WORDS, DURATION)
        fixed_beat = {"beats": [{"sentences": [6, 7], "mode": "map_footage", "purpose": "the north feeds the river",
                                 "map": {"geo_intent": "the Karakoram feeds the Indus", "camera": {"place": "Gilgit", "frame": "region"},
                                         "layers": [{"type": "marker", "anchor": "mountains rise", "place": "35.30,75.64", "label": "SKARDU"}]},
                                 "support": {"source": "stock_image", "query": "glacier in the karakoram", "place": "35.30,75.64", "label": "GLACIER"}}]}
        llm = FakeLLM(fixed_beat)
        res = repair_errors(plan, WORDS, llm, script=SCRIPT, duration=DURATION)
        self.assertTrue(res.ok)
        self.assertEqual((res.repair_passes, res.repaired), (1, [["b3"]]))
        self.assertEqual(len(llm.calls), 1)                                          # no critic, one repair
        self.assertEqual([b.mode for b in res.plan.beats], [b.mode for b in plan.beats])
        self.assertEqual(res.plan.beats[0].layers[0].label, plan.beats[0].layers[0].label)   # the other beats are untouched

    def test_a_plan_with_nothing_to_repair_costs_no_llm_call(self):
        from hybrid.pipeline import repair_errors

        plan, _ = plan_from_payload(payload(), SENTENCES, WORDS, DURATION)
        llm = FakeLLM({"beats": []})
        res = repair_errors(plan, WORDS, llm, script=SCRIPT, duration=DURATION)
        self.assertEqual((res.repair_passes, len(llm.calls)), (0, 0))

    def test_a_critic_that_fails_does_not_lose_the_plan(self):
        def answer(system, user):
            if system.startswith("You are the editorial critic"):
                raise RuntimeError("quota")
            return json.dumps(payload())

        res = plan_hybrid(WORDS, FakeLLM(answer), script=SCRIPT, duration=DURATION, critic_policy="always")
        self.assertEqual(len(res.plan.beats), 4)
        self.assertTrue(any("critic unavailable" in x for x in res.log))
        self.assertEqual(res.repair_passes, 0)

    def test_unreadable_json_is_asked_for_again_once(self):
        llm = FakeLLM("not json at all", payload())
        plan, _ = plan_beats(llm, SENTENCES, WORDS, DURATION)
        self.assertEqual(len(plan.beats), 4)
        self.assertIn("could not be used", llm.calls[1][1])
        with self.assertRaises(DirectorError):
            plan_beats(FakeLLM("still not json"), SENTENCES, WORDS, DURATION)

    def test_notes_from_the_critic_appear_on_the_beat(self):
        note = {"findings": [{"beat": "b3", "severity": "note", "category": "pacing", "issue": "the card comes late", "suggestion": ""}]}
        res = plan_hybrid(WORDS, self.director_or_critic([payload()], [note]), script=SCRIPT, duration=DURATION, critic_policy="always")
        self.assertTrue(any("CRITIC (note)" in f and "card comes late" in f for f in res.plan.beats[2].findings))

    def test_the_result_round_trips_to_disk(self):
        import tempfile
        from pathlib import Path
        from hybrid.pipeline import load_plan, save_bundle

        res = plan_hybrid(WORDS, self.director_or_critic([payload()], [{"findings": []}]), script=SCRIPT, duration=DURATION)
        with tempfile.TemporaryDirectory() as d:
            save_bundle(d, res)
            back = load_plan(d)
            self.assertEqual(back.to_dict(), res.plan.to_dict())
            self.assertTrue((Path(d) / "plan_report.json").is_file())


if __name__ == "__main__":
    unittest.main()
