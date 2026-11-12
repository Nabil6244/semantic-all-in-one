"""Aviation step 3: Flow video / image routing - one shared look, prompts from the line, where Flow goes (and never goes), the credit sum."""

import unittest

from aviation import flow as FL
from aviation import planner as P
from test_aviation_planner import scenes

FLIGHT_LONG = ["Vistara 611 takes off from Srinagar at 1:24 PM with 4,900 kg of fuel.", "They climb over the mountains towards Jammu.",
               "Storm clouds build over Jammu.", "The crew join the hold over Jammu.", "They descend for the approach in heavy rain.",
               "The crew turn towards Amritsar.", "They land on runway 34 at Amritsar."]


class PromptTests(unittest.TestCase):
    def test_csv_prompt_gets_the_shared_look(self):
        p = FL.prompt_for({"text": "x", "prompt": "Vistara A320 climbing over mountains, chase camera"}, {})
        self.assertTrue(p.startswith("Vistara A320 climbing"))
        self.assertIn(FL.LOOK, p)

    def test_auto_prompt_names_type_livery_phase_and_place(self):
        p = FL.prompt_for({"text": "Vistara 611 takes off from Srinagar at 1:24 PM."}, {"airline": "vistara", "aircraft": "a320"})
        for word in ("Airbus A320", "Vistara", "livery", "taking off", "Srinagar"):
            self.assertIn(word, p)

    def test_cockpit_line_asks_for_the_cockpit(self):
        p = FL.prompt_for({"text": "Inside the cockpit, the two pilots run their checks."}, {"aircraft": "a320"})
        self.assertIn("cockpit", p.lower())


class PlacementTests(unittest.TestCase):
    def test_flight_stretch_gets_aircraft_shots_between_map_lines(self):
        sc = scenes(FLIGHT_LONG)
        plan = P.plan(sc)
        FL.assign(sc, plan)
        kinds = [s.get("asset_type") for s in sc]
        n = kinds.count("flow_video")
        self.assertGreaterEqual(n, 2)
        self.assertLessEqual(n, 4)                                      # between map beats, not every line
        self.assertNotEqual(kinds[0:2], ["flow_video", "flow_video"])

    def test_the_csv_decides_where_it_says_so(self):
        sc = scenes(FLIGHT_LONG)
        for s in sc:
            s["asset_type"] = "none"
        FL.assign(sc, P.plan(sc))
        self.assertEqual({s["asset_type"] for s in sc}, {"none"})

    def test_named_real_event_never_gets_flow(self):
        sc = scenes(["On the 5th of October 2015, Air France workers stormed a meeting and tore executives' shirts."])
        sc[0]["asset_type"] = "youtube_video"
        FL.fallback(sc, ["1"], P.plan(sc))
        self.assertEqual(sc[0]["asset_type"], "youtube_video")

    def test_failed_aircraft_scene_falls_back_to_flow(self):
        sc = scenes(["The A350 seats 292 passengers in a three-class cabin."])
        sc[0]["asset_type"] = "youtube_video"
        FL.fallback(sc, ["1"], P.plan(sc))
        self.assertEqual(sc[0]["asset_type"], "flow_video")
        self.assertIn("A350", sc[0]["prompt"])

    def test_named_person_never_gets_flow(self):
        sc = scenes(["Chief executive Jean-Marc Janaillac told staff the plan would go ahead."])
        sc[0]["asset_type"] = "youtube_video"
        FL.fallback(sc, ["1"], P.plan(sc))
        self.assertEqual(sc[0]["asset_type"], "youtube_video")


class CreditTests(unittest.TestCase):
    def test_sum(self):
        sc = [{"asset_type": "flow_video"}, {"asset_type": "flow_video"}, {"asset_type": "flow_image"}, {"asset_type": "none"}]
        self.assertEqual(FL.credits(sc), {"videos": 2, "images": 1, "credits": 2 * FL.VIDEO_CREDITS})

    def test_already_made_are_free(self):
        sc = [{"asset_type": "flow_video", "scene_no": 1}, {"asset_type": "flow_video", "scene_no": 2}]
        self.assertEqual(FL.credits(sc, have={"1"})["videos"], 1)

    def test_question_text(self):
        q = FL.question({"videos": 3, "images": 2, "credits": 30})
        self.assertIn("3 Flow videos", q)
        self.assertIn("30 credits", q)
        self.assertIn("2 Flow images", q)


if __name__ == "__main__":
    unittest.main()
