"""War Footage Director Stage 1: narration reader (cinematic_explainer/war/narration_read.py) + the CSV comma repair. Offline."""

import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.war import narration_read as N
from cinematic_explainer.war.director_eval import load_eval


class EvalSetTest(unittest.TestCase):
    """Acceptance on the 48 labelled scenes of renders 038 and 033."""

    @classmethod
    def setUpClass(cls):
        cls.rows = []
        for rid, r in load_eval()["renders"].items():
            got = N.read_scenes([{"scene_no": s["scene"], "text": s["text"]} for s in r["scenes"]])
            for s in r["scenes"]:
                cls.rows.append((rid, s, got[s["scene"]]))

    def test_footage_wanted_on_every_scene(self):
        wrong = [(rid, s["scene"]) for rid, s, x in self.rows if x.footage_wanted != s["footage_wanted"]]
        self.assertEqual(wrong, [])

    def test_actor_whenever_labelled(self):
        wrong = [(rid, s["scene"], x.actor, s["actor"]) for rid, s, x in self.rows if s["actor"] and x.actor != s["actor"]]
        self.assertEqual(wrong, [])

    def test_types_overlap(self):
        jac = [len(set(x.types) & set(s["types"])) / len(set(x.types) | set(s["types"])) for _, s, x in self.rows]
        self.assertGreaterEqual(sum(jac) / len(jac), 0.78)
        primary_ok = sum(1 for _, s, x in self.rows if x.primary in s["types"])
        self.assertGreaterEqual(primary_ok, len(self.rows) - 5)

    def test_key_terms_name_the_scene(self):
        miss = []
        for rid, s, x in self.rows:
            if s["footage_wanted"]:
                kl = [k.lower() for k in x.key_terms]
                if not any(any(e.lower() in k or k in e.lower() for k in kl) for e in s["key_terms"]):
                    miss.append((rid, s["scene"]))
        self.assertLessEqual(len(miss), 1, miss)

    def test_every_sentence_has_a_graphic(self):
        self.assertTrue(all(x.graphic_intents for _, _, x in self.rows))


class RuleTest(unittest.TestCase):
    def test_strike_on_russian_site_means_ukraine_acts(self):
        r = N.read("Overnight on November 5, drones set the Ryazan refinery on fire.")
        self.assertIn("EVENT", r.types)
        self.assertEqual(r.actor, "Ukraine")
        self.assertIn("Ryazan", r.key_terms)
        self.assertEqual(r.date.lower(), "overnight")

    def test_side_reversal_is_kept(self):
        self.assertEqual(N.read("Third, Russia is hitting back from the air.").actor, "Russia")
        self.assertEqual(N.read("Ukrainian drones hunted Russian troops near Pokrovsk.").actor, "Ukraine")

    def test_claim_wrapping_an_event_has_both(self):
        r = N.read("Reuters said Ryazan's main distillation unit was halted again after an October attack.")
        self.assertTrue({"CLAIM", "EVENT", "LOCATION"} <= set(r.types))
        self.assertEqual(r.outlet, "Reuters")
        self.assertTrue(r.footage_wanted)

    def test_tallies_and_negations_want_no_footage(self):
        for t in ("In all of 2022, DTEK counted 11 such strikes.",
                  "ISW says Russian forces seized 104.5 square kilometers in Zaporizhia Oblast between September 1 and mid-October.",
                  "The IEA says that by late August, only five major Russian refineries had not been hit.",
                  "They made no confirmed advances."):
            self.assertFalse(N.read(t).footage_wanted, t)

    def test_questions_transitions_and_outro(self):
        self.assertEqual(N.read("Do you think Russia can restart its offensive before winter?").types, ["QUESTION"])
        self.assertIn("TRANSITION", N.read("There are three parts to the answer, and the last one is a warning.").types)
        self.assertIn("TRANSITION", N.read("Subscribe to Warfront Brief for the next breakdown.").types)

    def test_country_is_not_a_location(self):
        r = N.read("Ukraine says its drones have disabled 51 percent of Russia's oil refining capacity.")
        self.assertNotIn("LOCATION", r.types)
        self.assertFalse(r.footage_wanted)

    def test_there_inherits_the_previous_place(self):
        a = N.read("He said Ukrainian forces cleared most of Mala Tokmachka, southeast of Orikhiv.")
        b = N.read("But Russia is still pushing there.", a)
        self.assertIn("MOVEMENT", b.types)
        self.assertEqual(b.actor, "Russia")
        self.assertTrue({"Orikhiv", "Mala Tokmachka"} & set(b.key_terms))

    def test_unknown_place_names_are_kept_not_guessed(self):
        r = N.read("ISW reported that Russian forces kept attacking near Lyman, Borova, Hulyaipole and Dobropillya.")
        names = {p.name for p in r.places}
        self.assertTrue({"Lyman", "Borova", "Hulyaipole", "Dobropillya"} <= names)
        self.assertEqual({p.kind for p in r.places if p.name == "Borova"}, {"unresolved"})
        self.assertIn("Dobropillia", r.key_terms)          # transliteration twin

    def test_movement_by_rail(self):
        r = N.read("Russia banned diesel exports and began importing gasoline by rail from Belarus and Kazakhstan.")
        self.assertTrue({"EVENT", "MOVEMENT"} <= set(r.types))
        self.assertTrue({"Belarus", "Kazakhstan"} <= set(r.countries))

    def test_read_scenes_passes_the_actor_on(self):
        out = N.read_scenes([{"scene_no": 1, "text": "Russian forces kept attacking near Lyman."},
                             {"scene_no": 2, "text": "They made no confirmed advances."}])
        self.assertEqual(out["2"].actor, "Russia")


class BakhmutRegressionTest(unittest.TestCase):
    """Render 040 (2026-11-09): a past-tense historical script placed no footage. One test per bug found there."""

    @classmethod
    def setUpClass(cls):
        r = load_eval()["renders"]["040"]
        cls.got = N.read_scenes([{"scene_no": s["scene"], "text": s["text"]} for s in r["scenes"]])

    def test_past_tense_story_sentences_are_events(self):
        for no in ("001", "004", "006", "007", "009", "010", "011", "014", "016"):
            self.assertTrue(self.got[no].footage_wanted, (no, self.got[no].types, self.got[no].reasons))
            self.assertIn("EVENT", self.got[no].types, no)

    def test_group_subject_gets_subject_footage(self):
        self.assertIn("SUBJECT", self.got["008"].types)          # "Ukrainian soldiers called the battle a meat grinder."

    def test_unknown_names_and_pronouns_carry_the_actor(self):
        self.assertEqual(self.got["001"].actor, "Russia")       # Prigozhin (no catalogue entry)
        self.assertEqual(self.got["007"].actor, "Russia")       # "Its fighters ..." after "Wagner recruited ..."
        self.assertEqual(self.got["010"].actor, "Ukraine")      # "The next day, he gave ..." after Zelensky
        self.assertEqual(self.got["016"].actor, "Russia")       # Wagner marched (not 'paid for with Wagner')
        self.assertIn("Yevgeny Prigozhin", self.got["001"].key_terms)

    def test_story_place_carries_into_sentences_that_do_not_name_it(self):
        self.assertIn("Bakhmut", self.got["007"].key_terms)
        self.assertEqual(self.got["007"].context_places, ["Bakhmut"])

    def test_marched_is_not_march_and_may_is_capitalised(self):
        self.assertNotIn("march", N.read("Wagner marched on Moscow.").date.lower())
        self.assertEqual(N.read("Russia may strike again.").date, "")
        self.assertIn("March", N.read("In March 2022, troops crossed the border.").date)

    def test_relative_and_carried_dates(self):
        self.assertEqual((self.got["010"].date, self.got["010"].date_source), ("December 21, 2022", "relative"))
        self.assertEqual(self.got["016"].date_source, "relative")        # never used to reject footage
        self.assertEqual(self.got["012"].date, "since December 2022")    # December before a May 2023 reference
        self.assertEqual(self.got["007"].date_source, "carried")
        self.assertEqual(self.got["009"].date_source, "stated")

    def test_duration_is_not_a_statistic(self):
        self.assertNotIn("STATISTIC", self.got["006"].types)     # "freedom after six months"


class CsvRepairTest(unittest.TestCase):
    def test_unquoted_comma_in_narration(self):
        from cinematic_explainer.war.app_section import read_scenes_csv
        body = ("scene_number,script_segment,asset_type,prompt,graphic\n"
                "1,Plain row.,none,,title\n"
                "13,Second, Russians are feeling it. AP reported long waits.,youtube_video,Russia gasoline queue || drivers waiting,number\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.csv"
            p.write_text(body, encoding="utf-8")
            rows = read_scenes_csv(str(p))
        self.assertEqual(rows[1]["text"], "Second, Russians are feeling it. AP reported long waits.")
        self.assertEqual(rows[1]["asset_type"], "youtube_video")
        self.assertEqual(rows[1]["prompt"], "Russia gasoline queue || drivers waiting")
        self.assertEqual(rows[1]["graphic"], "number")


if __name__ == "__main__":
    unittest.main()
