"""Aviation style step 1: offline catalog (airlines, aircraft, airports) and the narration router (sentence -> mode + values)."""

import unittest

from aviation import catalog as C
from aviation import router as R


class CatalogTests(unittest.TestCase):
    def test_airline_by_name_and_code(self):
        self.assertEqual(C.find_airlines("Air France launched Joon")[0].entry["id"], "air_france")
        self.assertEqual(C.find_airlines("Then Vistara 611 pushed back")[0].entry["id"], "vistara")
        ids = [m.entry["id"] for m in C.find_airlines("Emirates and Qantas signed a deal")]
        self.assertEqual(ids, ["emirates", "qantas"])

    def test_airline_has_livery_and_hub(self):
        af = C.get_airline("air_france")
        self.assertTrue(af["colors"])
        self.assertIn("CDG", af["hubs"])

    def test_short_codes_are_case_sensitive(self):
        # 'BA' as a word in normal text must not become British Airways; the uppercase code may
        self.assertEqual(C.find_airlines("the ba ba sound"), [])
        self.assertEqual(C.find_airlines("BA flies to New York")[0].entry["id"], "british_airways")

    def test_aircraft_type_and_variant(self):
        m = C.find_aircraft("Boeing must tear open 30 finished 777X jets")
        self.assertEqual(m[0].entry["id"], "b777x")
        m = C.find_aircraft("the A321XLR is brilliant")
        self.assertEqual(m[0].entry["id"], "a321xlr")
        m = C.find_aircraft("an Airbus A320 took off")
        self.assertEqual(m[0].entry["id"], "a320")
        self.assertEqual(m[0].entry["body"], "narrow")

    def test_variant_wins_over_family(self):
        ids = [m.entry["id"] for m in C.find_aircraft("the 787-10 order")]
        self.assertEqual(ids, ["b787"])
        ids = [m.entry["id"] for m in C.find_aircraft("the A350-1000 is longer")]
        self.assertEqual(ids, ["a350"])

    def test_generic_aircraft_word(self):
        m = C.find_aircraft("the widebody jets sat on the apron")
        self.assertEqual(m[0].confidence, "generic")
        self.assertEqual(m[0].class_id, "widebody")

    def test_airport_by_city_and_code(self):
        a = C.find_airports("the short hop from Srinagar to Jammu")
        self.assertEqual([m.entry["id"] for m in a], ["SXR", "IXJ"])
        self.assertAlmostEqual(a[0].entry["lat"], 34.0, delta=0.3)
        self.assertEqual(C.find_airports("based at Charles de Gaulle")[0].entry["id"], "CDG")
        self.assertEqual(C.find_airports("delays at JFK")[0].entry["id"], "JFK")

    def test_every_entry_is_well_formed(self):
        for e in C.all_airlines():
            self.assertTrue(e["id"] and e["name"] and e["aliases"], e)
        for e in C.all_aircraft():
            self.assertIn(e["body"], ("narrow", "wide", "regional", "jumbo", "supersonic", "concept"), e)
        for e in C.all_airports():
            self.assertTrue(-90 <= e["lat"] <= 90 and -180 <= e["lon"] <= 180, e)


class ValueTests(unittest.TestCase):
    def test_clock_times(self):
        v = R.extract_values("At 1:38 PM the fuel read 4,220 kg")
        self.assertEqual(v["times"], ["13:38"])
        self.assertEqual(v["fuel_kg"], [4220])

    def test_fuel_in_tonnes(self):
        self.assertEqual(R.extract_values("they carried 6.2 tonnes of fuel")["fuel_kg"], [6200])

    def test_altitudes(self):
        v = R.extract_values("climb to flight level 210, then descend to 4,100 feet")
        self.assertEqual(v["altitude_ft"], [21000, 4100])

    def test_distances_and_speeds(self):
        v = R.extract_values("Amritsar is 109 km away, about 62 nautical miles, with gusts of 29 knots")
        self.assertEqual(v["distance_km"], [109, 115])
        self.assertEqual(v["speed_kt"], [29])

    def test_counts_money_percent(self):
        v = R.extract_values("139 passengers and 5 cabin crew; a $2.1 billion order, 40% of the fleet")
        self.assertIn((139, "passengers"), v["counts"])
        self.assertIn((5, "cabin crew"), v["counts"])
        self.assertEqual(v["money"], [("USD", 2.1e9)])
        self.assertEqual(v["percent"], [40.0])

    def test_flight_number(self):
        self.assertEqual(R.extract_values("Vistara 611 is getting ready")["flights"], ["Vistara 611"])
        self.assertEqual(R.extract_values("flight UK611 departed")["flights"], ["UK611"])

    def test_dates(self):
        v = R.extract_values("On the 5th of October 2015, Air France confirmed plans")
        self.assertEqual(v["dates"], ["2015-10-05"])
        self.assertEqual(R.extract_values("Then on December 1st, 2017, it launched")["dates"], ["2017-12-01"])

    def test_plain_years_are_not_altitudes_or_fuel(self):
        v = R.extract_values("In 2016 the plan had nine pillars")
        self.assertEqual(v["altitude_ft"], [])
        self.assertEqual(v["fuel_kg"], [])


class ModeTests(unittest.TestCase):
    def mode(self, s):
        return R.classify(s).mode

    def test_news(self):
        self.assertEqual(self.mode("On the 5th of October 2015, Air France confirmed plans to cut 2,900 jobs."), "news")
        self.assertEqual(self.mode("In November 2016, the chief executive unveiled a plan called Trust Together."), "news")

    def test_flight(self):
        self.assertEqual(self.mode("They take off from Srinagar and climb towards Jammu."), "flight")
        self.assertEqual(self.mode("The crew joined the hold over Jammu with fuel running low."), "flight")

    def test_weather(self):
        self.assertEqual(self.mode("This is monsoon season, and storm clouds with heavy hail are building."), "weather")

    def test_fleet(self):
        self.assertEqual(self.mode("The A350 seats 292 passengers in a three-class cabin with a longer range."), "fleet")

    def test_evidence(self):
        self.assertEqual(self.mode("The investigation report found the crew had not checked the latest weather."), "evidence")

    def test_people(self):
        self.assertEqual(self.mode("The captain is 52, with more than 11,000 hours in his logbook."), "people")

    def test_numbers(self):
        self.assertEqual(self.mode("That was a loss of 1.2 billion euros, or 15 percent of revenue."), "numbers")

    def test_radio_call(self):
        c = R.classify('"Jammu, Vistara 611, request climb to 10,000 feet overhead."')
        self.assertTrue(c.radio)
        self.assertEqual(c.mode, "flight")

    def test_classification_explains_itself(self):
        c = R.classify("They take off from Srinagar and climb towards Jammu.")
        self.assertTrue(c.reasons)
        self.assertEqual([a["id"] for a in c.airports], ["SXR", "IXJ"])
        self.assertGreater(c.scores["flight"], c.scores["news"])

    def test_word_traps_from_real_narration(self):
        # verbs and compounds that look like another mode's word
        self.assertNotEqual(self.mode("Within hours, workers stormed a works council meeting."), "weather")
        self.assertNotEqual(self.mode("It could not cut its costs without going to war with its own people."), "numbers")
        self.assertNotEqual(self.mode("Inside the cabin are 5 cabin crew."), "fleet")
        self.assertEqual(self.mode("During those checks, the crew receive the weather report for Jammu."), "weather")

    def test_spoken_flight_number(self):
        self.assertEqual(R.extract_values("Vistara 6-1-1 is getting ready")["flights"], ["Vistara 611"])

    def test_empty_and_neutral_text(self):
        self.assertEqual(self.mode(""), "news")
        self.assertEqual(self.mode("And that is where it gets interesting."), "news")


class RouteTests(unittest.TestCase):
    def test_route_script_keeps_state(self):
        lines = ["It's the 4th of July 2019 at Srinagar airport.",
                 "Vistara 611 is getting ready for the short hop to Jammu.",
                 "At 1:38 PM they have about 4,220 kg of fuel.",
                 "By 2:03 PM fuel is down to 3,040 kg and they are cleared to 4,100 feet.",
                 "Air France later launched a new airline called Joon."]
        out = R.route_script(lines)
        self.assertEqual(len(out), 5)
        # the flight state carries forward to later sentences that don't repeat it
        self.assertEqual(out[2].state["time"], "13:38")
        self.assertEqual(out[3].state["fuel_kg"], 3040)
        self.assertEqual(out[3].state["altitude_ft"], 4100)
        self.assertEqual(out[3].state["flight"], "Vistara 611")
        self.assertEqual(out[2].mode, "flight")
        self.assertEqual(out[4].mode, "news")

    def test_short_neutral_line_follows_its_neighbours(self):
        lines = ["They take off from Srinagar and climb towards Jammu.", "Then it gets worse.",
                 "The crew joined the hold over Jammu with fuel running low."]
        self.assertEqual([c.mode for c in R.route_script(lines)], ["flight", "flight", "flight"])


if __name__ == "__main__":
    unittest.main()
