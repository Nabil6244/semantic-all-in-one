"""War reference animations (owner 2026-11-16): the satellite "animated map" and the "IN 24 HOURS" icon chain.

No network: tile fetching is switched off, so the map uses its flat Natural Earth base (or tiles already in the cache)."""
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from cinematic_explainer.war import direction as D
from cinematic_explainer.war import graphics_ref as R
from cinematic_explainer.war import registry

SENT = ("In just 24 hours, China sent 49 fighter jets, two aircraft carriers, more than 100 warships and coast guard vessels, "
        "and a stealth drone from a catapult carrier.")


class ChainOf(unittest.TestCase):
    def test_counts_become_items_with_icons_and_period_title(self):
        c = R.chain_of(SENT, D._STICKERS)
        self.assertEqual([i["label"] for i in c["items"]],
                         ["49 fighter jets", "two aircraft carriers", "100+ warships & coast guard", "A stealth drone from a catapult carrier"])
        self.assertEqual([i["name"] for i in c["items"]], ["jet", "ship", "ship", "drone"])
        self.assertEqual(c["title"], "IN JUST 24 HOURS")

    def test_two_items_need_a_period(self):
        self.assertIsNotNone(R.chain_of("Russia launched 120 drones and 40 missiles overnight.", D._STICKERS))
        self.assertIsNone(R.chain_of("Russia launched 120 drones and 40 missiles.", D._STICKERS))

    def test_no_drawable_things_no_chain(self):
        self.assertIsNone(R.chain_of("He spoke 3 times in 24 hours about 5 ideas.", D._STICKERS))


class SatOf(unittest.TestCase):
    def test_named_strait(self):
        s = D._sat_of(NS(text="They would have to cross the Taiwan Strait, 130 km of open water.", entities=[], numbers=[]))
        self.assertEqual(s["strait"], "taiwan strait")
        self.assertEqual(s["km"], 130)

    def test_nothing_named(self):
        self.assertIsNone(D._sat_of(NS(text="The weather was bad all week.", entities=[], numbers=[])))


class Cards(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(R, "_tile", lambda z, x, y, fetch=True: R.__dict__["_tile_cached"](z, x, y))
        R._tile_cached = lambda z, x, y: None          # offline: flat base
        p.start()
        self.addCleanup(p.stop)
        R._BASE.clear()

    def test_registered_and_full_frame(self):
        cards = registry.all_cards()
        self.assertIn("sat_map", cards)
        self.assertIn("kit_chain", cards)
        self.assertTrue({"sat_map", "kit_chain"} <= D.FULL_KINDS)
        self.assertEqual(D.CSV_GRAPHIC["animated map"], "satmap")
        self.assertEqual(D.CSV_GRAPHIC["chain"], "chain")

    def test_sat_map_frames_deterministic_and_opaque(self):
        p = {"strait": "taiwan strait", "legend": [{"colour": "red", "text": "A"}, {"colour": "blue", "text": "B"}]}
        a, b = R.sat_map(3.0, 8.0, p), R.sat_map(3.0, 8.0, p)
        self.assertEqual(a.size, (1280, 720))
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertEqual(a.getchannel("A").getextrema(), (255, 255))
        self.assertNotEqual(R.sat_map(1.0, 8.0, p).tobytes(), a.tobytes())     # the camera moves

    def test_sat_map_missing_points(self):
        self.assertIsNone(R.sat_map(1.0, 8.0, {"a": {"lat": 1}}))

    def test_chain_reveals_then_wipes(self):
        c = R.chain_of(SENT, D._STICKERS)
        early, mid, last = R.kit_chain(0.5, 8.0, c), R.kit_chain(5.0, 8.0, c), R.kit_chain(7.99, 8.0, c)
        self.assertEqual(mid.getchannel("A").getextrema()[1], 255)
        self.assertNotEqual(early.tobytes(), mid.tobytes())
        self.assertLess(sum(last.getchannel("A").histogram()[1:]), 1280 * 720 * 0.1)   # wiped away
        self.assertIsNone(R.kit_chain(1.0, 8.0, {"items": [{"name": "jet", "label": "x"}]}))


class MoreReaders(unittest.TestCase):
    def test_counter(self):
        c = R.counter_of("Russian drone launches rose from 400 to 2,000 a month in 2024.")
        self.assertEqual((c["a"]["value"], c["b"]["value"], c["b"]["label"], c["unit"], c["title"]), (400, 2000, "2024", "a month", "RUSSIAN DRONE LAUNCHES"))
        self.assertIsNone(R.counter_of("The war lasted from 2014 to 2022."))

    def test_forces_pairs_rows_and_bare_figures(self):
        f = R.forces_of("Russia has 3,000 tanks and 300 jets, while Ukraine has 900 tanks and 60 jets.", D._STICKERS)
        self.assertEqual([(r["name"], r["a"], r["b"]) for r in f["rows"]], [("tank", 3000, 900), ("jet", 300, 60)])
        g = R.forces_of("Russia has 3,000 tanks, while Ukraine has 900.", D._STICKERS)
        self.assertEqual(g["rows"][0]["b"], 900)
        self.assertIsNone(R.forces_of("Russia has 3,000 tanks.", D._STICKERS))

    def test_range_needs_a_place(self):
        pt = {"name": "Sevastopol", "lat": 44.62, "lon": 33.52}
        r = R.range_of("The missiles can reach targets 1,500 km away.", [pt])
        self.assertEqual((r["km"], r["shown"]), (1500, "1,500 km"))
        self.assertIsNone(R.range_of("The missiles can reach targets 1,500 km away."))
        self.assertAlmostEqual(R.range_of("It can fly 100 miles.", [pt])["km"], 160.9)

    def test_quote_needs_a_place(self):
        q = {"quote": "We will never let anyone take it", "speaker": ""}
        self.assertEqual(R.sat_quote_of(q, [], ["Taiwan"])["country"], "Taiwan")
        self.assertIsNone(R.sat_quote_of(q, [], []))


class MoreCards(Cards):
    def test_all_render(self):
        pt = {"label": "Sevastopol", "lat": 44.62, "lon": 33.52}
        cases = {"sat_range": {"centre": pt, "km": 300}, "sat_quote": {"quote": "Words said here today", "country": "Taiwan"},
                 "kit_counter": R.counter_of("Output rose from 40 to 200 a day."),
                 "kit_forces": R.forces_of("Russia has 3,000 tanks, while Ukraine has 900.", D._STICKERS)}
        cards = registry.all_cards()
        for kind, prm in cases.items():
            with self.subTest(kind=kind):
                self.assertIn(kind, D.FULL_KINDS)
                a, b = cards[kind](3.0, 8.0, prm), cards[kind](3.0, 8.0, prm)
                self.assertEqual(a.size, (1280, 720))
                self.assertEqual(a.tobytes(), b.tobytes())
                self.assertEqual(a.getchannel("A").getextrema()[1], 255)
                self.assertIsNone(cards[kind](3.0, 8.0, {}))


if __name__ == "__main__":
    unittest.main()


class ScriptPhrasings(unittest.TestCase):
    """Owner 2026-11-16: the Ukraine script never triggered the counter / forces cards; these are its own sentences."""

    def test_counter_from_then_and_against(self):
        from cinematic_explainer.war import graphics_ref as GR

        c = GR.counter_of("ISW counts 3,604 square kilometers for Russia in 2024, then 5,304 in 2025, including 473 retaken in Kursk.")
        self.assertEqual((c["a"]["shown"], c["a"]["label"], c["b"]["shown"], c["b"]["label"]), ("3,604", "2024", "5,304", "2025"))
        self.assertEqual(c["unit"], "square kilometers")
        c = GR.counter_of("That is 0.38 square kilometers a day this year, against about 13 a day in 2025.")
        self.assertEqual((c["a"]["shown"], c["a"]["label"], c["b"]["shown"], c["b"]["label"]), ("13", "2025", "0.38", "THIS YEAR"))
        self.assertIsNone(GR.counter_of("Russia sent 289 drones on November 3, 310 on November 4 and 317 on November 9."))
        self.assertIsNone(GR.counter_of("Between 2014 and 2022 the war changed."))

    def test_forces_without_a_pictogram_and_with_comma_and(self):
        from cinematic_explainer.war import direction as D, graphics_ref as GR

        f = GR.forces_of("ISW found Russia seized only 148 square kilometers, while Ukraine liberated at least 972, as of September 19.", D._STICKERS)
        self.assertEqual((f["left"]["name"], f["right"]["name"]), ("Russia", "Ukraine"))
        self.assertEqual([(r["label"], r["a_shown"], r["b_shown"]) for r in f["rows"]], [("square kilometers", "148", "972")])
        f = GR.forces_of("The next night Russia sent 310 drones, and Ukraine says it downed or neutralized 272, including 64 jet-powered.", D._STICKERS)
        self.assertEqual([(r["a_shown"], r["b_shown"]) for r in f["rows"]], [("310", "272")])
        self.assertIsNone(GR.forces_of("Russia lost 300 tanks, while Ukraine lost 90 jets.", D._STICKERS))
        self.assertIsNone(GR.forces_of("In September, ISW says Russia seized 175 square kilometers but lost 256.", D._STICKERS))


class SpiderwebPhrasings(unittest.TestCase):
    """2026-11-18 Operation Spiderweb render: the voice script spells numbers out and names aircraft by type."""

    def test_spoken_distance_from_a_country_is_a_range(self):
        r = R.range_of("Others went all the way to Belaya, in Siberia, more than four thousand kilometres from Ukraine.",
                       [{"name": "Belaya", "lat": 52.9, "lon": 103.6}], ["Ukraine"])
        self.assertEqual((r["shown"], r["centre"]["label"], r["km"]), ("4,000 km", "Ukraine", 4000.0))
        self.assertEqual(R._digits("two hundred and fifty km"), "250 km")
        self.assertIsNone(R.range_of("The bombers were parked hundreds, sometimes thousands, of kilometres away.", [], []))
        self.assertIsNone(R.range_of("The village is 12 km from the border.", [], []))

    def test_aircraft_type_names_count_in_a_chain(self):
        c = R.chain_of("Ukraine handed over eight Tu-160s and three Tu-95s, along with hundreds of cruise missiles.", D._STICKERS)
        self.assertEqual([i["label"] for i in c["items"]], ["eight Tu-160s", "three Tu-95s", "hundreds of cruise missiles"])

    def test_refused_csv_graphics_are_listed_before_render(self):
        from cinematic_explainer.war import engagement as E

        rep = {"summary": "x", "blocks": [], "issues": [], "csv_refused": ["scene 33: CSV asked for range: no stated reach"]}
        self.assertIn("CSV graphics not drawn (1", E.text(rep))


class LooseReaders(unittest.TestCase):
    """2026-11-18: all six reference cards in every War video - the ordinary ways a script says their facts."""

    def test_reported_speech(self):
        r = R.reported_of("According to President Zelensky, it took one year, six months and nine days from the start of planning.")
        self.assertEqual((r["speaker"], r["reported"]), ("President Zelensky", True))
        r = R.reported_of("Russia said it shot them down, but images showed damage, and the message was clear.")
        self.assertEqual(r["quote"], "It shot them down")
        self.assertIsNone(R.reported_of("Reports later said the drones ran on ArduPilot, free open-source software."))
        self.assertIsNone(R.reported_of("It said that was about a third of all the planes."))

    def test_two_counts_and_two_claimants(self):
        t2 = "American officials later told reporters that about twenty aircraft were hit, and that around ten of them were destroyed."
        c = R.pair_counter_of(t2, D._STICKERS)
        self.assertEqual((c["a"]["shown"], c["a"]["label"], c["b"]["shown"], c["b"]["label"]), ("20", "HIT", "10", "DESTROYED"))
        t1 = "The SBU claimed that 41 Russian aircraft were hit, including Tu-95 and Tu-22M3 bombers and A-50 radar planes."
        f = R.claims_forces_of((R.claimant_of(t1), t1), (R.claimant_of(t2), t2), D._STICKERS)
        self.assertEqual((f["left"]["name"], f["right"]["name"]), ("SBU", "American officials"))
        self.assertEqual([(x["a_shown"], x["b_shown"]) for x in f["rows"]], [("41", "20")])
        self.assertIsNone(R.chain_of(t1, D._STICKERS))            # 'Tu-95' and 'A-50' are names, not counts of 95 and 50

    def test_ref_figures_spot_repeats(self):
        self.assertTrue({8.0, 3.0} <= D._ref_figures({"items": [{"label": "eight Tu-160s"}, {"label": "three Tu-95s"}]}))
        self.assertNotIn(95.0, D._ref_figures({"label": "three Tu-95s"}))
