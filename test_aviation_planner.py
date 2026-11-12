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
        self.assertEqual(huds[0]["params"]["fuel"][0], 4220)
        mid = [h for h in huds if h["start"] == 8.0][0]
        lo, hi = sorted(mid["params"]["fuel"])
        self.assertTrue(3040 < lo < hi < 4220, mid["params"]["fuel"])     # its share of the fall, not the whole fall again

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


class RenderReviewFixes(unittest.TestCase):
    """Found in the first real 2-minute render (2026-11-13)."""

    def test_card_holds_at_most_five_seconds_then_clips(self):
        sc = scenes(["Air France launched Joon, a new airline with younger crews, a fashion brand image and lower costs."], each=10.0)
        rows = [{"mode": "news", "article": {"outlet": "Travel Weekly", "headline": "Air France launches Joon", "date": "December 1, 2017"},
                 "queries": ["Joon launch"], "radio": [], "from": "", "to": "", "fuel": None, "time": "", "altitude": None}]
        p = P.plan(sc, rows=rows)
        card = layers(p, "cards.lay_article")[0]
        self.assertLessEqual(card["end"] - card["start"], P.CARD_MAX_S + 1e-6)
        clips = [s for s in p.shots if s.get("kind") == "footage"]
        self.assertTrue(clips)
        self.assertAlmostEqual(clips[-1]["end"], 10.0)

    def test_hud_runs_on_one_timeline_across_lines(self):
        lines = ["Vistara 611 takes off from Srinagar at 1:24 PM with 4,900 kg of fuel.", "They climb towards Jammu.",
                 "The crew join the hold over Jammu.", "By 2:03 PM the fuel is down to 3,040 kg."]
        p = P.plan(scenes(lines))
        huds = sorted(layers(p, "hud.lay_hud"), key=lambda h: h["start"])
        fuels = [h["params"]["fuel"] for h in huds]
        # each line continues where the last one stopped, and fuel only goes down
        for a, b in zip(fuels, fuels[1:]):
            self.assertEqual(a[1], b[0])
        flat = [v for f in fuels for v in f]
        self.assertEqual(flat, sorted(flat, reverse=True))
        self.assertEqual(fuels[0][0], 4900)
        self.assertEqual(fuels[-1][-1], 3040)
        times = [h["params"]["time"] for h in huds]
        for a, b in zip(times, times[1:]):
            self.assertEqual(a[1], b[0])

    def test_a_later_leg_is_drawn_when_it_is_said(self):
        lines = ["Vistara 611 takes off from Srinagar for Jammu.", "Storm clouds build over Jammu.", "The crew join the hold over Jammu.",
                 "The crew turn from Jammu towards Amritsar."]
        p = P.plan(scenes(lines))
        legs = layers(p, "flightmap.lay_flight_map")[0]["params"]["legs"]
        self.assertEqual([(l["from"], l["to"]) for l in legs], [("SXR", "IXJ"), ("IXJ", "ATQ")])
        self.assertAlmostEqual(legs[1]["start"], 12.0, delta=0.5)


class FlightBeatTests(unittest.TestCase):
    LINES = ["Vistara 611 takes off from Srinagar for Jammu.", "They climb over the mountains.", "Storm clouds build over Jammu.",
             "The crew join the hold over Jammu.", "They descend for the approach in heavy rain.", "The crew turn from Jammu towards Amritsar."]

    def plan_with_clips(self, with_clip):
        sc = scenes(self.LINES)
        for i in with_clip:
            sc[i]["footage"] = "/x/clip.mp4"
            sc[i]["asset_type"] = "flow_video"
        return P.plan(sc)

    def test_aircraft_shots_cut_into_the_map(self):
        p = self.plan_with_clips([1, 4])
        clips = [s for s in p.shots if s.get("kind") == "footage"]
        self.assertEqual([(c["start"], c["end"]) for c in clips], [(4.0, 8.0), (16.0, 20.0)])
        maps = layers(p, "flightmap.lay_flight_map")
        self.assertEqual([(m["start"], m["end"]) for m in maps], [(0.0, 4.0), (8.0, 16.0), (20.0, 24.0)])
        # the map carries on: its clock (t0) is the time since the stretch began, the whole stretch is one map
        self.assertEqual([m["params"]["t0"] for m in maps], [0.0, 8.0, 20.0])
        self.assertTrue(all(m["params"]["total"] == 24.0 for m in maps))

    def test_hud_stays_over_the_aircraft_shots(self):
        sc = scenes(["Vistara 611 takes off from Srinagar at 1:24 PM with 4,900 kg of fuel.", "They climb over the mountains.",
                     "By 2:03 PM fuel is down to 3,040 kg."])
        sc[1]["footage"], sc[1]["asset_type"] = "/x/c.mp4", "flow_video"
        p = P.plan(sc)
        self.assertTrue(any(h["start"] == 4.0 for h in layers(p, "hud.lay_hud")))

    def test_each_beat_reframes_on_its_line(self):
        p = self.plan_with_clips([])
        views = layers(p, "flightmap.lay_flight_map")[0]["params"]["views"]
        self.assertEqual(views[0]["focus"], ["SXR", "IXJ"])            # the route: wide
        storm = [v for v in views if abs(v["start"] - 8.0) < 0.6][0]
        self.assertEqual(storm["focus"], ["IXJ"])                       # the storm / hold: close on Jammu
        self.assertEqual(views[-1]["focus"], ["IXJ", "ATQ"])            # the diversion: wide again


class GraphicTriggerTests(unittest.TestCase):
    def test_csv_graphic_column_is_used(self):
        sc = scenes(["Vistara 611 takes off from Srinagar.", "Over Jammu the weather is turning.", "This is the story of Vistara 611."])
        rows = [{"graphic": ""}, {"graphic": "place_title", "to": "IXJ"}, {"graphic": "end_card"}]
        p = P.plan(sc, rows=rows)
        t = layers(p, "gfx.lay_place_title")
        self.assertEqual(t[0]["params"]["name"], "Jammu")
        self.assertTrue(layers(p, "gfx.lay_end_card"))

    def test_right_now_line_gets_the_place_title(self):
        sc = scenes(["Vistara 611 takes off from Srinagar for Jammu.", "But right now, over Jammu, storm clouds are building."])
        t = layers(P.plan(sc), "gfx.lay_place_title")
        self.assertEqual((t[0]["params"]["name"], t[0]["params"]["pill"]), ("Jammu", "RIGHT NOW"))

    def test_two_altitudes_get_the_side_view(self):
        sc = scenes(["Vistara 611 takes off from Srinagar.", "They are cleared from 11,000 feet up to flight level 200.", "They hold over Jammu."])
        alt = layers(P.plan(sc), "gfx.lay_altitude")
        self.assertEqual((alt[0]["params"]["from_ft"], alt[0]["params"]["to_ft"]), (11000, 20000))
        self.assertTrue(alt[0]["full_frame"])

    def test_weather_report_line_gets_a_sheet_from_its_own_words(self):
        sc = scenes(["Vistara 611 is at Srinagar.", "The weather report for Jammu says light winds, a little dust haze and a few clouds."])
        sh = layers(P.plan(sc), "gfx.lay_sheet")
        self.assertTrue(sh)
        labels = [r[1] for r in sh[0]["params"]["rows"]]
        self.assertIn("LIGHT WINDS", labels)
        self.assertEqual(sh[0]["params"]["title"], "JAMMU WEATHER")

    def test_airports_appear_when_first_named(self):
        sc = scenes(["Vistara 611 takes off from Srinagar for Jammu.", "Storm clouds build over Jammu.", "The crew turn from Jammu towards Amritsar."])
        prm = layers(P.plan(sc), "flightmap.lay_flight_map")[0]["params"]
        self.assertAlmostEqual(prm["appear"]["SXR"], 0.0)
        self.assertAlmostEqual(prm["appear"]["ATQ"], 8.0)
