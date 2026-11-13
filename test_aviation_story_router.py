"""Aviation story mode: router rule, years, catalog history fields and lineage helpers."""
import unittest

from aviation import catalog as C
from aviation import router as R


class StoryRouterTests(unittest.TestCase):
    def test_story_sentences(self):
        for s in ("In 1966 the two governments formed Malaysia-Singapore Airlines.",
                  "Singapore Airlines was founded in 1972 after the airline split in two.",
                  "Malaysia Airlines became the national airline of Malaysia.",
                  "The company was renamed Malaysian Airways after independence.",
                  "The government kept a 30 percent stake in the flag carrier."):
            self.assertEqual(R.classify(s).mode, "story", s)

    def test_clear_lines_stay(self):
        self.assertEqual(R.classify("The aircraft descended to 4,100 feet").mode, "flight")
        self.assertEqual(R.classify("Air France confirmed plans to cut 2,900 jobs in 2015").mode, "news")
        self.assertEqual(R.classify("A storm formed over the airport with heavy rain and gusts").mode, "weather")
        self.assertEqual(R.classify("The aircraft climbed to 35,000 feet and the captain reported turbulence").mode, "flight")

    def test_years_are_exposed(self):
        self.assertEqual(R.extract_values("In 1966 it merged, and in 1972 it split.")["years"], [1966, 1972])
        self.assertEqual(R.extract_values("It descended to 1950 feet at 2000 kg of fuel.")["years"], [])
        self.assertEqual(R.extract_values("On 3 March 2015 it flew.")["years"], [2015])
        self.assertEqual(R.classify("In 1966 the governments formed it").values["years"], [1966])

    def test_far_year_in_script_is_story(self):
        lines = ["The airline carried 80 passengers.", "In 1947 a small company started flying.", "Today it announced a deal in 2024."]
        out = R.route_script(lines)
        self.assertEqual(out[1].mode, "story")
        self.assertNotEqual(out[2].mode, "story")

    def test_far_year_does_not_steal_flight(self):
        out = R.route_script(["The jet took off and climbed to 35,000 feet in 1990.", "Later it landed in 2024."])
        self.assertEqual(out[0].mode, "flight")

    def test_near_year_not_story(self):
        out = R.route_script(["Air France announced a deal in 2015.", "Air France announced a deal in 2024."])
        self.assertNotEqual(out[0].mode, "story")


class StoryCatalogTests(unittest.TestCase):
    def test_new_historic_airlines(self):
        for aid in ("malayan_airways", "malaysian_airways", "msa", "malaysia_airlines", "boac"):
            self.assertIsNotNone(C.get_airline(aid), aid)
        self.assertEqual(C.get_airline("boac")["defunct"], 1974)
        self.assertEqual(C.get_airline("msa")["founded"], 1966)
        self.assertEqual([m.entry["id"] for m in C.find_airlines("Malaysia-Singapore Airlines")], ["msa"])
        self.assertEqual([m.entry["id"] for m in C.find_airlines("Malaysia Airlines")], ["malaysia_airlines"])

    def test_field_shapes(self):
        ids = {e["id"] for e in C._data("airlines")[0]}
        for e in C._data("airlines")[0]:
            if "founded" in e:
                self.assertIsInstance(e["founded"], int)
            for ref in ([e["parent"]] if e.get("parent") else []) + list(e.get("successors") or []):
                self.assertIn(ref, ids, e["id"])
            for p in e.get("previous_names") or []:
                self.assertTrue(p["name"] and p["from"] <= p["to"])

    def test_lineage(self):
        self.assertEqual(C.lineage("singapore_airlines")["ancestors"], ["malayan_airways", "malaysian_airways", "msa"])
        self.assertEqual(C.lineage("malayan_airways")["descendants"], ["malaysian_airways", "msa", "singapore_airlines", "malaysia_airlines"])
        self.assertEqual(C.lineage("boac")["descendants"], ["british_airways"])
        self.assertEqual(C.lineage("nope"), {"ancestors": [], "descendants": []})

    def test_name_in_year(self):
        self.assertEqual(C.name_in_year("singapore_airlines", 1950), "Malayan Airways")
        self.assertEqual(C.name_in_year("singapore_airlines", 1965), "Malaysian Airways")
        self.assertEqual(C.name_in_year("singapore_airlines", 1970), "Malaysia-Singapore Airlines")
        self.assertEqual(C.name_in_year("singapore_airlines", 1972), "Singapore Airlines")
        self.assertEqual(C.name_in_year("malaysia_airlines", 2000), "Malaysian Airline System")
        self.assertEqual(C.name_in_year("malaysia_airlines", 2020), "Malaysia Airlines")
        self.assertIsNone(C.name_in_year("boac", 1980))
        self.assertIsNone(C.name_in_year("boac", 1930))
        self.assertEqual(C.name_in_year("klm", 1950), "KLM")


if __name__ == "__main__":
    unittest.main()


def test_aircraft_plurals_match():
    from aviation import catalog as C
    for text, want in (("flying Boeing 707s to London", "b707"), ("two A350s", "a350"), ("the 747s were retired", "b747")):
        assert [m.entry["id"] for m in C.find_aircraft(text) if m.entry][:1] == [want], text
