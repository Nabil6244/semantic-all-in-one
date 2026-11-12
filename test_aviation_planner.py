"""Aviation style step 6: the planner - timed narration (+ optional CSV rows) -> a timeline of footage slots and card layers."""

import unittest

from aviation import planner as P


def scenes(lines, each=4.0):
    out, t = [], 0.0
    for i, s in enumerate(lines, 1):
        out.append({"scene_no": i, "text": s, "start": t, "end": t + each})
        t += each
    return out


FLIGHT = ["Vistara 611 takes off from Srinagar for the short hop to Jammu.",
          "At 1:38 PM they have about 4,220 kg of fuel.",
          "Storm clouds and hail are building over Jammu, with gusts of 29 knots.",
          "The crew join the hold over Jammu.",
          "By 2:03 PM fuel is down to 3,040 kg."]
NEWS = ["On the 5th of October 2015, Air France confirmed plans to cut 2,900 jobs.",
        "Within hours, workers stormed a works council meeting near Paris Airport.",
        "Management could announce restructuring, but it could not deliver it.",
        "Then on December 1st, 2017, Air France launched a new airline called Joon.",
        "In its first year, Joon carried 3 million passengers."]


def layers(plan, name):
    return [s for s in plan.shots if s.get("layer") == name]


class SmoothingTests(unittest.TestCase):
    def test_weak_island_takes_its_neighbours_mode(self):
        p = P.plan(scenes(NEWS))
        self.assertEqual(p.modes[1], "news")                          # 'near Paris Airport' no longer flips to flight

    def test_strong_island_is_kept(self):
        lines = NEWS[:2] + ["At 1:38 PM they took off and climbed to flight level 210 with 4,220 kg of fuel."] + NEWS[2:3]
        self.assertEqual(P.plan(scenes(lines)).modes[2], "flight")


class FlightStretchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = P.plan(scenes(FLIGHT))

    def test_one_continuous_map(self):
        maps = layers(self.p, "flightmap.lay_flight_map")
        self.assertEqual(len(maps), 1)
        self.assertEqual((maps[0]["start"], maps[0]["end"]), (0.0, 20.0))
        prm = maps[0]["params"]
        self.assertIn("SXR", prm["airports"])
        self.assertIn("IXJ", prm["airports"])
        self.assertEqual((prm["route"]["from"], prm["route"]["to"]), ("SXR", "IXJ"))

    def test_events_land_when_they_are_said(self):
        prm = layers(self.p, "flightmap.lay_flight_map")[0]["params"]
        self.assertEqual(prm["storms"][0]["at"], "IXJ")
        self.assertAlmostEqual(prm["storms"][0]["start"], 8.0, delta=0.5)   # third line starts at 8 s into the map
        self.assertEqual(prm["holding"]["at"], "IXJ")
        self.assertAlmostEqual(prm["holding"]["start"], 12.0, delta=0.5)

    def test_hud_follows_the_readings(self):
        huds = layers(self.p, "hud.lay_hud")
        self.assertTrue(huds)
        self.assertEqual(huds[0]["start"], 4.0)                       # nothing before the first reading
        mid = [h for h in huds if h["start"] == 8.0][0]
        self.assertEqual(mid["params"]["fuel"], (4220, 3040))

    def test_weather_icons_on_weather_line(self):
        w = layers(self.p, "gfx.lay_weather")
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["start"], 8.0)

    def test_no_footage_needed_inside_a_short_map(self):
        self.assertFalse([s for s in self.p.shots if s.get("kind") == "footage" and s["start"] < 20.0])


class LongMapTests(unittest.TestCase):
    def test_long_map_gets_footage_breaks(self):
        lines = FLIGHT * 3                                            # 60 s of flight narration
        p = P.plan(scenes(lines))
        breaks = [s for s in p.shots if s.get("kind") == "footage"]
        self.assertTrue(breaks)
        self.assertTrue(all(3.0 <= b["end"] - b["start"] <= 5.0 for b in breaks))
        maps = layers(p, "flightmap.lay_flight_map")
        self.assertTrue(all(m["end"] - m["start"] <= P.MAX_MAP_S + 0.01 for m in maps))
        # the map carries on after a break: same airports, not restarted
        self.assertEqual(maps[0]["params"]["airports"], maps[-1]["params"]["airports"])


class NewsStretchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = P.plan(scenes(NEWS))

    def test_fast_footage_bursts(self):
        clips = [s for s in self.p.shots if s.get("kind") == "footage"]
        self.assertGreater(len(clips), 8)
        lengths = [c["end"] - c["start"] for c in clips]
        self.assertLessEqual(max(lengths), 2.0 + 1e-6)
        self.assertGreaterEqual(min(lengths), 1.0 - 1e-6)
        self.assertTrue(all(c["queries"] for c in clips))

    def test_a_card_breaks_the_burst(self):
        cards = layers(self.p, "cards.lay_article")
        self.assertTrue(cards)
        # the fact strip uses the narration's own words
        self.assertIn("3 million passengers", cards[0]["params"]["fact"])
        self.assertEqual(cards[0]["params"]["image_from"], "footage")

    def test_timeline_has_no_gaps(self):
        segs = sorted((s["start"], s["end"]) for s in self.p.shots if s.get("kind") == "footage" or s.get("full_frame"))
        t = 0.0
        for a, b in segs:
            self.assertLessEqual(a, t + 1e-6)
            t = max(t, b)
        self.assertGreaterEqual(t, 20.0 - 1e-6)


class CsvRowTests(unittest.TestCase):
    def test_csv_article_and_radio(self):
        sc = scenes(["Air France launched Joon.", "They asked to climb."])
        rows = [{"mode": "news", "article": {"outlet": "Travel Weekly", "headline": "Air France launches Joon", "date": "December 1, 2017"},
                 "queries": ["Joon launch 2017"], "radio": [], "from": "", "to": "", "fuel": None, "time": "", "altitude": None},
                {"mode": "flight", "article": None, "queries": [], "from": "IXJ", "to": "", "fuel": None, "time": "", "altitude": 10000,
                 "radio": [{"speaker": "FIRST OFFICER", "text": "Jammu, Vistara 611, request climb"}]}]
        p = P.plan(sc, rows=rows)
        art = layers(p, "cards.lay_article")
        self.assertEqual(art[0]["params"]["headline"], "Air France launches Joon")
        self.assertEqual(layers(p, "hud.lay_radio")[0]["params"]["lines"][0]["speaker"], "FIRST OFFICER")
        news = [s for s in p.shots if s.get("kind") == "footage" and s["start"] < 4.0]
        self.assertTrue(all(c["queries"] == ["Joon launch 2017"] for c in news))


class EndCardTests(unittest.TestCase):
    def test_next_episode_card(self):
        p = P.plan(scenes(NEWS[:2] + ["This is the story of Vistara 944. I'll see you there."]))
        ec = layers(p, "gfx.lay_end_card")
        self.assertEqual(ec[0]["params"]["title"], "Vistara 944")
        self.assertEqual(ec[0]["params"]["kicker"], "THE STORY OF")


class LogTests(unittest.TestCase):
    def test_every_scene_explained(self):
        p = P.plan(scenes(FLIGHT + NEWS))
        self.assertEqual(len(p.log), len(FLIGHT + NEWS))
        self.assertTrue(all("mode" in e and e["why"] for e in p.log))


if __name__ == "__main__":
    unittest.main()
