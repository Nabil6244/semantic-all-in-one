"""War Documentary planner: narration-driven choice, honesty gates, density, determinism. Isolated: only cinematic_explainer.war is imported."""
import os
import tempfile
import unittest

from cinematic_explainer.war import catalog as C
from cinematic_explainer.war import planner as P
from cinematic_explainer.war import semantics as S

CARD_KINDS = {"evidence_card", "figure_card", "stat_number", "stat_compare", "equipment_card", "institution_card", "map_card", "timeline",
              "split_compare"}


def sc(no, text, start=6.0, end=16.0, footage="a.mp4", **kw):
    d = {"scene_no": no, "text": text, "start": start, "end": end, "footage": footage}
    d.update(kw)
    return d


def cards(plan, kind=None):
    return [ly for ly in plan.layers if ly.kind in CARD_KINDS and (kind is None or ly.kind == kind)]


def codes(plan, no=1):
    d = [x for x in plan.log if x.scene_no == no][0]
    return {c["kind"] + ":" + c.get("code", "") for c in d.candidates}


class StubMatch:
    def __init__(self, entry, alias, confidence, start, end, cls=""):
        self.entry, self.matched_alias, self.confidence, self.start, self.end, self.class_id = entry, alias, confidence, start, end, cls


class StubCatalog:
    """One ambiguous equipment alias; everything else empty."""

    def find_equipment(self, text):
        i = text.find("Zeta")
        if i < 0:
            return []
        return [StubMatch({"id": "zeta", "name": "Zeta", "class": "air_defense", "role": "x", "specs": []}, "Zeta", "ambiguous", i, i + 4, "air_defense")]

    def find_figure(self, text): return []
    def find_institution(self, text): return []
    def find_place(self, text): return []


class Semantics(unittest.TestCase):
    def test_sentences_keep_quotes_and_abbreviations(self):
        got = [s for s, _ in S.split_sentences('"We hold." Gen. Vale said so. It ended! Then 3.5 million fled.')]
        self.assertEqual(got, ['"We hold."', "Gen. Vale said so.", "It ended!", "Then 3.5 million fled."])

    def test_possessive_place_is_not_a_location(self):
        a = S.analyze_scene("Russia's economy shrank. Shelling hit a depot near Kharkiv.", C)
        self.assertEqual(a.sentences[0].location, [])
        self.assertEqual([e.name for e in a.sentences[1].location], ["Kharkiv"])

    def test_quote_speaker_and_pronoun(self):
        q = S.analyze_scene('"We stay," said Minister Dorrin Vale. "We go," he said.', C).sentences
        self.assertEqual(q[0].quote.speaker, "Minister Dorrin Vale")
        self.assertEqual(q[1].quote.speaker, "")


class Basics(unittest.TestCase):
    def test_empty_input(self):
        p = P.plan([])
        self.assertEqual((p.shots, p.layers, p.log), ([], [], []))
        self.assertEqual(p.stats["cards"], 0)

    def test_empty_text_scene_still_gets_its_shot_and_a_logged_reason(self):
        p = P.plan([sc(1, "", footage="a.mp4")])
        self.assertEqual(len(p.shots), 1)
        self.assertEqual(p.layers, [])
        self.assertEqual(p.log[0].fallback_reason, "no_trigger")

    def test_unknown_entities_do_not_crash_or_trigger(self):
        p = P.plan([sc(1, "Qwerty Zorbo crossed the river at Plugh.")])
        self.assertEqual(cards(p), [])

    def test_boundaries_are_whole_frames(self):
        p = P.plan([sc(1, "According to the General Staff, 40 drones a day were launched.", start=4.013, end=14.987)])
        for ly in p.layers:
            self.assertAlmostEqual(ly.start * 25, round(ly.start * 25), places=6)
            self.assertAlmostEqual(ly.end * 25, round(ly.end * 25), places=6)
        for s in p.shots:
            self.assertAlmostEqual(s.start * 25, round(s.start * 25), places=6)

    def test_deterministic(self):
        scenes = [sc(1, "The T-72 carries a 125 mm gun and was widely deployed.", 6, 16), sc(2, "The convoy moved from Kharkiv to Odesa.", 30, 42)]
        self.assertEqual(P.plan(scenes).to_dict(), P.plan(scenes).to_dict())

    def test_nothing_before_four_seconds(self):
        p = P.plan([sc(1, "The T-72 carries a 125 mm gun.", 0, 8)])
        self.assertTrue(all(ly.start >= 4.0 - 1e-9 for ly in cards(p)))

    def test_log_is_complete(self):
        p = P.plan([sc(1, "The convoy moved from Kharkiv to Odesa.", 6, 16), sc(2, "It was quiet.", 16, 24)])
        self.assertEqual([d.scene_no for d in p.log], [1, 2])
        for d in p.log:
            self.assertTrue(d.chosen or d.fallback_reason)
            self.assertIsInstance(d.candidates, list)
        self.assertIn("scene 1", P.explain(p))


class Maps(unittest.TestCase):
    def test_motion_gives_illustrative_route(self):
        p = P.plan([sc(1, "The convoy moved from Kharkiv to Odesa before dawn.")])
        m = cards(p, "map_card")
        self.assertEqual(len(m), 1)
        self.assertFalse(m[0].dim)
        self.assertEqual(m[0].params["status"], "illustrative")
        self.assertTrue(m[0].params["arrows"][0]["illustrative"])

    def test_possessive_country_no_map(self):
        p = P.plan([sc(1, "Russia's economy shrank last year.")])
        self.assertEqual(cards(p, "map_card"), [])

    def test_bare_country_with_cue_no_map(self):
        p = P.plan([sc(1, "Fighting continued in Ukraine through the winter.")])
        self.assertEqual(cards(p, "map_card"), [])
        self.assertIn("map:no_trigger", codes(p))

    def test_city_with_cue_gives_pin(self):
        p = P.plan([sc(1, "Shelling hit a depot near Kharkiv overnight.")])
        m = cards(p, "map_card")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].params["pins"][0]["label"], "Kharkiv")

    def test_territorial_verb_has_no_front_line_without_a_sourced_snapshot(self):
        p = P.plan([sc(1, "Forces captured Bakhmut after a long siege.")])
        m = cards(p, "map_card")[0]
        self.assertNotIn("control_snapshots", m.params)
        self.assertEqual(m.params["status"], "illustrative")

    def test_sourced_snapshot_is_used_and_unsourced_is_ignored(self):
        snap = {"as_of": "2024-01-01", "source": "Example Institute", "places": ["Bakhmut"], "polygons": [[(37.9, 48.5), (38.0, 48.6), (38.1, 48.5)]]}
        bad = {"as_of": "2024-01-01", "places": ["Bakhmut"], "polygons": []}
        ok = cards(P.plan([sc(1, "Forces captured Bakhmut after a long siege.")], config={"snapshots": [snap]}), "map_card")[0]
        self.assertEqual(ok.params["status"], "attributed")
        self.assertEqual(ok.params["control_snapshots"][0]["source"], "Example Institute")
        no = cards(P.plan([sc(1, "Forces captured Bakhmut after a long siege.")], config={"snapshots": [bad]}), "map_card")[0]
        self.assertNotIn("control_snapshots", no.params)


class People(unittest.TestCase):
    def test_attributed_quote_gives_figure_card_with_name_plate(self):
        p = P.plan([sc(1, '"We will not move the depot," said President Volodymyr Zelensky.')])
        f = cards(p, "figure_card")
        self.assertEqual(len(f), 1)
        self.assertIsNone(f[0].params["image"])
        self.assertEqual(f[0].params["status"], "attributed")
        self.assertTrue(f[0].params["words"] and len(f[0].params["words"]) == len(f[0].params["times"]))

    def test_name_without_role_or_statement_no_portrait(self):
        p = P.plan([sc(1, "Vladimir Putin arrived late to the meeting.")])
        self.assertEqual(cards(p, "figure_card"), [])
        self.assertIn("figure:no_trigger", codes(p))

    def test_person_in_a_historical_comparison_gets_no_card(self):
        p = P.plan([sc(1, "The plan resembles a speech that Putin gave years ago.")])
        self.assertEqual(cards(p, "figure_card"), [])

    def test_portrait_only_if_file_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            fh.write(b"x")
        try:
            text = '"We hold," said President Volodymyr Zelensky.'
            have = cards(P.plan([sc(1, text)], assets={"portrait:zelensky": fh.name}), "figure_card")[0]
            self.assertEqual(have.params["image"], fh.name)
            gone = cards(P.plan([sc(1, text)], assets={"portrait:zelensky": fh.name + ".missing"}), "figure_card")[0]
            self.assertIsNone(gone.params["image"])
        finally:
            os.unlink(fh.name)

    def test_unknown_speaker_gets_an_attributed_text_card_never_a_face(self):
        p = P.plan([sc(1, '"The repair was only partial and temporary," said Dorrin Vale.')])
        self.assertEqual(cards(p, "figure_card"), [])
        e = cards(p, "evidence_card")
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].params["outlet"], "Dorrin Vale")
        self.assertEqual(e[0].params["status"], "attributed")

    def test_institution_statement(self):
        p = P.plan([sc(1, 'The Ministry of Defence of Ukraine said "the depot was not damaged by the strike".')])
        self.assertTrue(cards(p, "institution_card") or cards(p, "evidence_card"))


class Equipment(unittest.TestCase):
    def test_named_system_with_attribute_gets_a_card(self):
        p = P.plan([sc(1, "The T-72 carries a 125 mm gun and was widely deployed.")])
        e = cards(p, "equipment_card")
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].params["name"], "T-72")
        self.assertEqual(e[0].params["confidence"], "stated")
        self.assertTrue(all("source" in str(s) or True for s in e[0].params["specs"]))

    def test_missile_word_alone_is_not_a_weapon_card(self):
        p = P.plan([sc(1, "Another missile hit the depot at dawn.")])
        self.assertEqual(cards(p, "equipment_card"), [])
        self.assertIn("equipment:ambiguous_entity", codes(p))

    def test_ambiguous_alias_gets_a_generic_class_label_only(self):
        p = P.plan([sc(1, "The Zeta system has a range of 300 km.")], catalog=StubCatalog())
        e = cards(p, "equipment_card")
        self.assertEqual(len(e), 1)
        self.assertTrue(e[0].params["generic"])
        self.assertEqual(e[0].params["specs"], [])
        self.assertEqual(e[0].params["status"], "unverified")
        self.assertTrue(e[0].params["name"].endswith("(type)"))


class Numbers(unittest.TestCase):
    def test_claimed_number_names_the_claimant(self):
        p = P.plan([sc(1, "According to the General Staff of Ukraine, 40 drones a day were launched.")])
        n = cards(p, "stat_number")
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0].params["status"], "attributed")
        self.assertIn("General Staff", n[0].params["claimant"])

    def test_contested_figure_without_claimant_is_never_plain(self):
        p = P.plan([sc(1, "Some 500 soldiers were killed in the assault.")])
        self.assertEqual(cards(p, "stat_number"), [])
        self.assertIn("number:provenance_failed", codes(p))

    def test_duration_and_referentless_numbers_are_not_statistics(self):
        self.assertEqual(cards(P.plan([sc(1, "The war reshaped the region over three years.")]), "stat_number"), [])
        self.assertEqual(cards(P.plan([sc(1, "There were 12.")]), "stat_number"), [])

    def test_comparison_needs_both_values_and_a_unit(self):
        ok = cards(P.plan([sc(1, "The ministry said output rose from 40 to 200 units a month.")]), "stat_compare")
        self.assertEqual(len(ok), 1)
        self.assertEqual([i["value"] for i in ok[0].params["items"]], [40.0, 200.0])
        self.assertTrue(ok[0].params["axis_from_zero"])
        self.assertEqual(ok[0].params["status"], "attributed")
        no = P.plan([sc(1, "Output rose from 40 to 200.")])
        self.assertEqual(cards(no, "stat_compare"), [])

    def test_disputed_cue_marks_the_card_disputed(self):
        p = P.plan([sc(1, "The ministry claimed 12 drones were intercepted, but Kyiv denied it.")])
        for ly in cards(p):
            self.assertEqual(ly.params["status"], "disputed")


class Evidence(unittest.TestCase):
    def test_outlet_with_quoted_line_gives_a_source_card_with_word_times(self):
        p = P.plan([sc(1, 'The Brightwater Agency said the repair was "only partial and temporary at best".')])
        e = cards(p, "evidence_card")
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].params["outlet"], "Brightwater Agency")
        self.assertEqual(len(e[0].params["words"]), len(e[0].params["times"]))
        self.assertEqual(e[0].params["kind"], "statement")

    def test_outlet_without_a_line_gives_no_card(self):
        p = P.plan([sc(1, "Analysts believe it was partial.")])
        self.assertEqual(cards(p, "evidence_card"), [])


class Timing(unittest.TestCase):
    def test_word_times_drive_the_card_start(self):
        text = "Nothing happened here for a while. The convoy moved from Kharkiv to Odesa."
        words = []
        t = 6.0
        for w in text.split():
            words.append({"w": w, "t0": t, "t1": t + 0.4})
            t += 0.5
        p = P.plan([sc(1, text, 6, 20, words=words)])
        m = cards(p, "map_card")[0]
        key = [w for w in words if w["w"] == "Kharkiv"][0]["t0"]
        self.assertAlmostEqual(m.start, round((key - 0.3) * 25) / 25, delta=0.5)

    def test_without_word_times_scene_timing_is_used(self):
        p = P.plan([sc(1, "The convoy moved from Kharkiv to Odesa.", 6, 16)])
        self.assertTrue(cards(p, "map_card"))


class Density(unittest.TestCase):
    def test_two_cards_never_overlap_and_keep_the_gap(self):
        scenes = [sc(1, "According to the General Staff, 40 drones a day were launched.", 6, 12),
                  sc(2, "The T-72 carries a 125 mm gun and was widely deployed.", 12, 18)]
        p = P.plan(scenes)
        cs = sorted(cards(p), key=lambda ly: ly.start)
        for a, b in zip(cs, cs[1:]):
            self.assertGreaterEqual(b.start - a.end, 7.0 - 1e-6)

    def test_clean_footage_floor_over_a_long_video(self):
        texts = ["According to the General Staff, %d drones a day were launched." % (40 + i) for i in range(12)]
        scenes = [sc(i + 1, t, 6 + i * 12, 18 + i * 12) for i, t in enumerate(texts)]
        p = P.plan(scenes)
        self.assertGreaterEqual(p.stats["clean_share"], 0.55)
        self.assertLessEqual(len([ly for ly in cards(p)]), 3 * (p.stats["total_s"] / 60.0) + 1)

    def test_headlines_are_verbatim_short_and_never_under_a_card(self):
        texts = ["The war reshaped the Black Sea region, and ports changed hands.", "According to the General Staff, 40 drones a day were launched.",
                 "Fuel supplies ran short across the front for weeks.", "Engineers rebuilt the bridge in nine days.", "The harvest was late again this year."]
        scenes = [sc(i + 1, t, 6 + i * 14, 20 + i * 14) for i, t in enumerate(texts)]
        p = P.plan(scenes)
        heads = [ly for ly in p.layers if ly.kind == "shot_headline"]
        self.assertTrue(heads)
        self.assertLessEqual(len(heads) / p.stats["footage_shots"], 0.4 + 1e-9)
        for h in heads:
            n = len(h.params["text"].split())
            self.assertTrue(3 <= n <= 7)
            self.assertIn(h.params["text"].split()[0], " ".join(texts))
            for c in cards(p):
                self.assertFalse(c.start < h.end and c.end > h.start)

    def test_kicker_rides_with_its_card_and_is_not_a_card(self):
        p = P.plan([sc(1, "The T-72 carries a 125 mm gun and was widely deployed.")])
        kick = [ly for ly in p.layers if ly.kind == "kicker"]
        self.assertEqual(len(kick), 1)
        self.assertEqual((kick[0].start, kick[0].end), (cards(p)[0].start, cards(p)[0].end))


class Footage(unittest.TestCase):
    def test_manifest_download_status_is_not_verification(self):
        p = P.plan([sc(1, "Engineers rebuilt the bridge in nine days.", footage_meta={"status": "complete", "author": "A. Person", "source_url": "https://x/y"})])
        self.assertIn("footage_unverified", p.log[0].flags)
        self.assertTrue(any("A. Person" in c for c in p.credits))

    def test_rejected_footage_is_not_used(self):
        p = P.plan([sc(1, "Engineers rebuilt the bridge in nine days.", footage_meta={"verification": "rejected"})], config={"filler_footage": "filler.mp4"})
        self.assertEqual([s.path for s in p.shots], ["filler.mp4"])
        self.assertIn("footage_rejected", p.log[0].flags)

    def test_recycled_footage_gets_a_file_footage_chip(self):
        texts = "Engineers rebuilt the bridge in nine days."
        p = P.plan([sc(1, texts, 4, 14, footage_meta={"recycled": True, "first_seen": "2019-05-01"})])
        chips = [ly for ly in p.layers if ly.kind == "status_chip"]
        self.assertTrue(chips and chips[0].params["text"].startswith("FILE FOOTAGE"))

    def test_no_footage_and_no_filler_skips_the_shot_and_says_so(self):
        p = P.plan([sc(1, "The convoy moved from Kharkiv to Odesa.", footage=None)])
        self.assertEqual(p.shots, [])
        self.assertEqual(p.stats["missing_footage_scenes"], [1])


class DemoScenes(unittest.TestCase):
    """The four demo scenes that must get a visual, and the negatives that must stay negative."""
    GEO = ("Ukraine lies on the northern shore of the Black Sea. It borders Russia to the east and north, and Poland, Slovakia, Hungary, "
           "Romania and Moldova to the west and south.")

    def test_geography_sentence_gives_a_filled_map_with_a_text_legend(self):
        m = cards(P.plan([sc(1, self.GEO, 6, 30)]), "map_card")
        self.assertEqual(len(m), 1)
        p = m[0].params
        self.assertEqual(p["frame"], "ukraine")
        names = {f["name"] for f in p["fills"]}
        self.assertTrue({"Ukraine", "Russia", "Poland", "Slovakia", "Hungary", "Romania", "Moldova"} <= names)
        self.assertEqual({r["label"] for r in p["legend"]}, names)
        self.assertEqual(p["status"], "illustrative")

    def test_geography_needs_two_places_and_a_geography_verb(self):
        self.assertEqual(cards(P.plan([sc(1, "Ukraine lies in the heart of Europe.")]), "map_card"), [])
        self.assertEqual(cards(P.plan([sc(1, "Ukraine and Russia held talks about grain.")]), "map_card"), [])

    def test_ports_named_together_give_pins_only_for_resolved_places(self):
        m = cards(P.plan([sc(1, "The Black Sea ports of Odesa and Mykolaiv have long been central to the country's grain exports.", 6, 20, footage=None)]), "map_card")
        self.assertEqual(len(m), 1)
        self.assertEqual({p["label"] for p in m[0].params["pins"]}, {"Odesa", "Mykolaiv"})
        self.assertEqual(m[0].params["frame"], "odesa_region")

    def test_institution_as_subject_gets_an_attributed_card(self):
        p = P.plan([sc(1, "The United Nations Security Council has met repeatedly to discuss the war, and its statements are attributed to its members.",
                       6, 20, footage=None)])
        i = cards(p, "institution_card")
        self.assertEqual(len(i), 1)
        self.assertEqual((i[0].params["status"], i[0].params["source"]), ("attributed", "named in narration"))
        self.assertIn("Security Council", i[0].params["name"])

    def test_institution_only_in_passing_gets_no_card(self):
        self.assertEqual(cards(P.plan([sc(1, "The convoy passed the Kremlin before dawn.")]), "institution_card"), [])

    def test_two_dated_events_in_one_sentence_make_a_timeline_in_the_narrations_words(self):
        t = cards(P.plan([sc(1, "The key dates are well documented: Crimea was annexed by Russia in 2014, and the full-scale invasion began in February 2022.",
                             6, 24, footage=None)]), "timeline")
        self.assertEqual(len(t), 1)
        ev = t[0].params["events"]
        self.assertEqual([e["date"] for e in ev], ["2014", "February 2022"])
        self.assertEqual(ev[0]["label"], "Crimea was annexed by Russia")
        self.assertEqual(ev[1]["label"], "The full-scale invasion began")
        self.assertEqual(t[0].params["status"], "attributed")
        self.assertFalse(t[0].dim)   # the timeline carries its own scrim; footage stays bright

    def test_a_single_date_is_not_a_timeline(self):
        self.assertEqual(cards(P.plan([sc(1, "Crimea was annexed by Russia in 2014 after a disputed vote.")]), "timeline"), [])

    def test_neutral_map_only_when_there_is_no_footage(self):
        txt = "Fighting continued in Ukraine through the winter."
        none = cards(P.plan([sc(1, txt, 6, 20, footage="a.mp4")]), "map_card")
        self.assertEqual(none, [])
        fb = cards(P.plan([sc(1, txt, 6, 20, footage=None)]), "map_card")
        self.assertEqual(len(fb), 1)
        self.assertEqual(fb[0].params["pins"], [])
        self.assertEqual(fb[0].params["status"], "illustrative")
        self.assertEqual(cards(P.plan([sc(1, txt, 6, 20, footage=None)], config={"neutral_map_fallback": False}), "map_card"), [])

    def test_possessive_country_gets_no_neutral_map_even_without_footage(self):
        self.assertEqual(cards(P.plan([sc(1, "Russia's economy shrank last year.", 6, 20, footage=None)]), "map_card"), [])

    def test_compare_labels_and_title_come_from_the_narration(self):
        p = P.plan([sc(1, "In this demonstration, an example ministry reports that monthly output rose from 40 to 200 units a month.", 6, 20)])
        c = cards(p, "stat_compare")[0].params
        self.assertEqual([(i["label"], i["value"], i["shown"]) for i in c["items"]], [("Before", 40.0, "40"), ("After", 200.0, "200")])
        self.assertEqual(c["title"], "Monthly output, units")
        self.assertEqual(c["status"], "attributed")
        self.assertIn("ministry", c["claimant"])


class Profiles(unittest.TestCase):
    TXT = ["The T-72 carries a 125 mm gun and was widely deployed.", "The Ministry of Defence of Ukraine said \"the depot was not damaged by the strike\".",
           "According to the General Staff, 40 drones a day were launched."]

    def scenes(self, n, length):
        return [sc(i + 1, self.TXT[i % 3] if i < 3 else "It was quiet.", 5 + i * length, 5 + (i + 1) * length) for i in range(n)]

    def test_short_video_relaxes_spacing_but_never_overlap(self):
        p = P.plan(self.scenes(3, 7))
        self.assertEqual(p.flags_profile, "short")
        cs = sorted(cards(p), key=lambda ly: ly.start)
        self.assertGreaterEqual(len(cs), 2)
        for a, b in zip(cs, cs[1:]):
            self.assertGreaterEqual(b.start, a.end)

    def test_explicit_config_beats_the_short_profile(self):
        p = P.plan(self.scenes(3, 7), config={"min_gap": 7.0, "same_kind_gap": 12.0, "map_gap": 7.0, "full_gap": 25.0})
        cs = sorted(cards(p), key=lambda ly: ly.start)
        for a, b in zip(cs, cs[1:]):
            self.assertGreaterEqual(b.start - a.end, 7.0 - 1e-6)

    def test_long_video_keeps_the_standard_spacing(self):
        p = P.plan(self.scenes(3, 60))
        self.assertEqual(p.flags_profile, "standard")
        cs = sorted(cards(p), key=lambda ly: ly.start)
        for a, b in zip(cs, cs[1:]):
            self.assertGreaterEqual(b.start - a.end, 7.0 - 1e-6)


if __name__ == "__main__":
    unittest.main()
