"""A voiceover with no script: speech-to-text writes place names in lowercase, gives no capitals to find them by, and says its dates in centuries as often as years. These tests pin the
three rules that a lowercase Venice narration broke: places found without capitals, each scene's period read from its own part of the story, and no two Flow scenes asking for the same picture."""

import unittest
from types import SimpleNamespace

from explainer import scene_intel as SI
from explainer.director import compose_pictures as CPX
from explainer.director import plan as PL
from explainer.director import select as SL
from explainer.director.options import DirectorOptions


def timed(text, t0=0.0, step=0.3):
    out, t = [], t0
    for w in text.split():
        out.append((w, round(t, 2), round(t + step - 0.02, 2)))
        t += step
    return out


class LowercasePlaces(unittest.TestCase):
    def test_no_script_or_lowercase_transcript_is_lowercase(self):
        self.assertTrue(SL.lowercase_text(None, timed("just north of the adriatic sea sits venice")))
        self.assertTrue(SL.lowercase_text("Just north of the adriatic sea sits venice. Venice grew rich.", []))
        self.assertFalse(SL.lowercase_text("Just north of the Adriatic Sea sits Venice. It grew rich trading with Constantinople.", []))

    def test_places_found_without_capitals(self):
        words = timed("just north of the adriatic sea sits venice . venice grew rich . its ships sailed to constantinople "
                      "and to islands including crete . later vasco da gama reached india by sailing around africa")
        found, _notes = SL.transcript_places(words)
        for name in ("Adriatic Sea", "Venice", "Constantinople", "Crete", "India", "Africa"):
            self.assertIn(name, found)
        ok, _ign = SL.resolve_places(found, set())
        self.assertIn("Venice", ok)

    def test_everyday_words_are_not_places(self):
        words = timed("the arsenal became a major center . reading the map was nice . a mobile split of the capital city . the turkey was roasted")
        found, _notes = SL.transcript_places(words)
        self.assertEqual(found, [])

    def test_a_town_said_once_needs_a_place_word_before_it(self):
        found, notes = SL.transcript_places(timed("then crete fell quiet"))
        self.assertNotIn("Crete", found)
        self.assertTrue(any("Crete" in n for n in notes))
        self.assertIn("Crete", SL.transcript_places(timed("the fleet sailed to crete"))[0])

    def test_capitalised_script_keeps_the_old_rule(self):
        script = "Venice grew rich. Its ships sailed to Constantinople."
        self.assertFalse(SL.lowercase_text(script, []))
        cands, _weak = SL.place_candidates(script, DirectorOptions())
        self.assertIn("Constantinople", cands)


class PeriodOfAScene(unittest.TestCase):
    def test_a_date_beats_an_era_word(self):
        self.assertEqual(CPX.era_year("during the 5th and 6th centuries as the western roman empire collapsed".split()), 550)
        self.assertEqual(CPX.era_year("in 1204 venetian ships carried an army to the capital of the byzantine empire".split()), 1204)
        self.assertEqual(CPX.era_year("the byzantine empire".split()), CPX.ERA_WORDS["byzantine"])

    def test_today_does_not_carry_into_later_beats(self):
        words = timed("today it is famous for its canals . and the strangest part venice began as a place where people went to hide")
        beat = SimpleNamespace(start=words[7][1], end=words[-1][2] + 0.1)
        self.assertIsNone(CPX.era_of_beat(words, beat)["year"])
        self.assertEqual(CPX.era_year("today it is famous".split()), 2026)


def beat(bid, words, i0, i1, places=()):
    sents = [SimpleNamespace(text=" ".join(w[0] for w in words[i0:i1]))]
    b = SL.BeatPlan(bid, words[i0][1], words[i1 - 1][2] + 0.01, sents, kind="cartoon")
    b.places = [SL.PlaceHit(p, "admin1", True, {}) for p in places]
    return b


class FlowScenes(unittest.TestCase):
    TEXT = ("during the 5th and 6th centuries people fled to venice . the shallow water stopped invading armies . "
            "living on islands created a serious problem . in 1204 venetian ships carried an army to constantinople . "
            "back in venice merchants built grand palaces . in 1797 napoleon armies entered venice .")

    def setUp(self):
        self.words = timed(self.TEXT)
        ends = [i + 1 for i, w in enumerate(self.words) if w[0] == "."]
        spans = list(zip([0] + ends[:-1], ends))
        places = [["Venice"], [], [], ["Constantinople"], ["Venice"], ["Venice"]]
        self.beats = [beat(f"e{k + 1}", self.words, a, b, places[k]) for k, (a, b) in enumerate(spans)]
        self.rec = PL.scene_intel_pass(self.beats, self.words, DirectorOptions(scene_intel=True, scene_flow_share=1.0), SI)

    def test_each_scene_gets_its_own_period(self):
        years = {k: v.get("year") for k, v in self.rec.items()}
        self.assertEqual(years["e1"], 550)
        self.assertEqual(years["e4"], 1204)
        self.assertEqual(years["e6"], 1797)

    def test_prompts_name_the_place_and_never_repeat(self):
        prompts = [b.picture_query for b in self.beats if b.source == "flow_image"]
        self.assertTrue(prompts)
        self.assertEqual(len(prompts), len(set(p.lower() for p in prompts)))
        self.assertFalse(any(p.startswith("a place,") for p in prompts))
        self.assertIn("Constantinople", next(b.picture_query for b in self.beats if b.id == "e4"))
        self.assertIn("Venice", next(b.picture_query for b in self.beats if b.id == "e2"))     # the beat names no place: the story's place stands in

    def test_story_place_is_the_most_spoken_town(self):
        self.assertEqual(PL.story_place(self.beats), "Venice")


STORY = ("look at a map of southern europe and you will notice italy . just north of the adriatic sea sits venice , a city built on small islands . "
         "during the 5th and 6th centuries people fled into the lagoon to hide from invading armies . the shallow water made it hard for armies to reach them . "
         "venice had little farmland and few resources so its merchants turned to the sea . venetian merchants sailed to constantinople to trade silk and spices . "
         "in 1204 venetian ships carried an army to constantinople and the city was sacked . venice gained islands including crete across the eastern mediterranean . "
         "back in venice grand palaces rose beside the canals and the arsenal built ships . in 1797 napoleon armies entered venice and the republic came to an end .")


def direct_story(**kw):
    from explainer.director.plan import direct
    opt = DirectorOptions(scene_intel=True, cartoon_share=0.33, pictures=True, footage_source="stock_image", **kw)
    words = timed(STORY, step=0.42)
    return direct(words, None, opt, materialize=False), words


class MapsFromLowercase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.words = direct_story()
        cls.maps = [b for b in cls.res.plan["beats"] if b["mode"].startswith("map")]

    def test_more_than_one_map(self):
        self.assertGreaterEqual(len(self.maps), 3, [b["purpose"] for b in self.maps])

    def test_a_state_or_province_is_coloured_not_only_labelled(self):
        filled = {l.get("place") for b in self.maps for l in b.get("layers", []) if l["type"] == "fill"}
        self.assertTrue(filled & {"Venice", "Constantinople", "Crete"}, filled)


class FlowOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.words = direct_story(flow_only=True, scene_flow_share=1.0)
        cls.assets = [c["asset"] for b in cls.res.plan["beats"] for c in (b.get("footage") or {}).get("clips", []) if not c["asset"].endswith(".mp4")]      # board clips are files
        cls.cards = [b["support"]["asset"] for b in cls.res.plan["beats"] if b.get("support")]

    def test_no_stock_anywhere(self):
        self.assertTrue(self.assets)
        self.assertFalse([a for a in self.assets + self.cards if not a.startswith("flow_image:")])

    def test_every_flow_scene_is_different(self):
        self.assertEqual(len(self.assets), len({a.lower() for a in self.assets}))
        self.assertEqual(len(self.cards), len({a.lower() for a in self.cards}))

    def test_off_by_default_keeps_the_chosen_source(self):
        res, _w = direct_story()
        srcs = {c["asset"].split(":")[0] for b in res.plan["beats"] for c in (b.get("footage") or {}).get("clips", []) if not c["asset"].startswith("/")}
        self.assertIn("stock_image", srcs)
        self.assertNotIn("flow_only", res.report["options"])

    def test_the_app_turns_it_on_by_default(self):
        from explainer import integration as IT
        self.assertTrue(IT._flag(IT.full_look({}), "explainer_flow_only"))
        self.assertFalse(IT._flag(IT.full_look({"explainer_flow_only": False}), "explainer_flow_only"))

    def test_checker_accepts_a_director_flow_card(self):
        from explainer.beats.relevance import check_plan
        from explainer.director import lexicon as LX
        if not self.cards:
            self.skipTest("no map card in this plan")
        rep = check_plan(self.res.plan, self.words, allow_sources=LX.FOOTAGE_SOURCES, composed=[b["id"] for b in self.res.plan["beats"]])
        self.assertFalse([p for p in rep.problems if "photo card" in p], rep.problems)


class NoBoringRepeats(unittest.TestCase):
    def test_a_library_set_is_used_at_most_twice_then_flow(self):
        words = timed(" . ".join(["the fishermen waited by the shallow sea shore with their boat"] * 5) + " .")
        ends = [i + 1 for i, w in enumerate(words) if w[0] == "."]
        beats = [beat(f"e{k + 1}", words, a, b) for k, (a, b) in enumerate(zip([0] + ends[:-1], ends))]
        rec = PL.scene_intel_pass(beats, words, DirectorOptions(scene_intel=True, scene_flow_share=1.0), SI)
        composed = [k for k, v in rec.items() if v["route"] == "compose"]
        self.assertLessEqual(len(composed), PL.SET_MAX_USES, rec)

    def test_the_same_place_and_period_is_framed_differently_each_time(self):
        words = timed(" . ".join(["in 1204 merchants crowded the harbour"] * 4) + " .")
        ends = [i + 1 for i, w in enumerate(words) if w[0] == "."]
        beats = [beat(f"e{k + 1}", words, a, b, ["Venice"]) for k, (a, b) in enumerate(zip([0] + ends[:-1], ends))]
        PL.scene_intel_pass(beats, words, DirectorOptions(scene_intel=True, scene_flow_share=1.0), SI)
        shots = [next((s for s in PL.SCENE_SHOTS if s in b.picture_query), None) for b in beats if b.source == "flow_image"]
        self.assertEqual(len(shots), 4)
        self.assertEqual(len(set(shots)), 4, shots)


if __name__ == "__main__":
    unittest.main()
