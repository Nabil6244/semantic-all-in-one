"""Phase 2: the covered metros and the story picker (fixed rules, explained), on a real snapshot of the 20 metros and the national
alerts (weather/testdata/automation/coverage_20261012.json, fetched 2026-10-12 22:46 UTC) with alerts added where a rule needs one."""

import copy
import json
import unittest
from pathlib import Path

from weather.automation.coverage import REGIONS, all_cities, by_region, metro, metros
from weather.automation.fetch import NATIONAL, summarise_alerts, target_date
from weather.automation.story import pick_story
from weather.resolve import Snapshot

ROOT = Path(__file__).resolve().parent
AUTO = ROOT / "weather" / "testdata" / "automation"


def snapshot():
    return Snapshot.from_json((AUTO / "coverage_20261012.json").read_text(encoding="utf-8"))


def alert(event, states, metros_=(), centre=(35.0, -97.0), i=0):
    return {"id": f"urn:test:{event}:{i}", "event": event, "severity": "Severe", "certainty": "Likely", "urgency": "Expected",
            "area": "test area", "sent": "2026-10-12T20:00:00+00:00", "expires": "2026-10-13T20:00:00+00:00", "ends": "",
            "sender": "NWS test", "states": list(states), "land": bool(states), "metros": list(metros_), "centre": list(centre)}


def with_alerts(snap, *alerts):
    s = copy.deepcopy(snap)
    s.extra[NATIONAL]["alerts"] = list(s.extra[NATIONAL]["alerts"]) + list(alerts)
    return s


class Coverage(unittest.TestCase):
    def test_twenty_metros_in_six_regions_with_valid_zones_and_two_stations(self):
        from weather.tz import ZONES

        ms = metros()
        self.assertEqual(len(ms), 20)
        self.assertEqual([m.rank for m in ms], list(range(1, 21)))
        self.assertEqual(set(m.region for m in ms), set(REGIONS))
        for m in ms:
            self.assertIn(m.city.tz, ZONES, m.key)
            self.assertEqual(len(m.city.stations), 2, m.key)
            self.assertRegex(m.city.grid, r"^[A-Z]{3} \d+,\d+$")
            self.assertRegex(m.county_fips, r"^\d{5}$")
            self.assertTrue(m.office_spoken)
            self.assertTrue(24 < m.city.lat < 49 and -125 < m.city.lon < -66, m.key)
        self.assertEqual(sum(len(v) for v in by_region().values()), 20)

    def test_phase1_cities_keep_their_entries_and_find_city_knows_every_metro(self):
        from weather.cities import cities, find_city

        import weather.layers.trend  # noqa: F401  (loading the layer types adds the metros to find_city)

        self.assertEqual(find_city("Boston, MA").grid, "BOX 71,101")
        self.assertEqual(find_city("Washington, DC").stations[0], "KDCA")
        for m in metros():
            self.assertEqual(find_city(m.key).key, m.key)
        self.assertEqual(all_cities()["dallas,TX"], cities()["dallas,TX"])
        with self.assertRaises(KeyError):
            metro("Gotham, NY")

    def test_the_metros_agree_with_cities_json_where_both_name_a_city(self):
        raw = json.loads((ROOT / "weather" / "data" / "cities.json").read_text(encoding="utf-8"))["cities"]
        for c in raw:
            m = metro(f"{c['name']}, {c['state']}")
            self.assertEqual((m.city.lat, m.city.lon, m.city.tz, m.city.grid, m.city.stations), (c["lat"], c["lon"], c["tz"], c["grid"], c["stations"]))


class NationalAlerts(unittest.TestCase):
    def test_a_county_alert_covers_the_metro_in_that_county_and_marine_alerts_are_not_land(self):
        fc = {"features": [
            {"properties": {"id": "a", "event": "Flood Warning", "areaDesc": "Harris, TX", "geocode": {"UGC": ["TXC201"], "SAME": ["048201"]}}, "geometry": None},
            {"properties": {"id": "b", "event": "Small Craft Advisory", "areaDesc": "Galveston Bay", "geocode": {"UGC": ["GMZ335"], "SAME": ["077335"]}}, "geometry": None},
            {"properties": {"id": "c", "event": "Tornado Warning", "areaDesc": "Dallas, TX", "geocode": {"UGC": ["TXC113"], "SAME": []}},
             "geometry": {"type": "Polygon", "coordinates": [[[-97.0, 32.6], [-96.6, 32.6], [-96.6, 33.0], [-97.0, 33.0], [-97.0, 32.6]]]}},
        ]}
        a, b, c = summarise_alerts(fc, metros())
        self.assertEqual((a["metros"], a["states"], a["land"]), (["Houston, TX"], ["TX"], True))
        self.assertIsNotNone(a["centre"])  # from the county shape
        self.assertEqual((b["land"], b["metros"]), (False, []))
        self.assertEqual(c["metros"], ["Dallas, TX"])  # inside its own polygon
        self.assertAlmostEqual(c["centre"][0], 32.76, places=1)

    def test_the_forecast_day_is_the_first_day_every_city_still_has(self):
        snap = snapshot()
        self.assertEqual(target_date(snap).isoformat(), "2026-10-13")   # 22:46 UTC: the East is on Tuesday, the West still on Monday


class StoryRules(unittest.TestCase):
    def test_the_real_day_is_a_heavy_rain_story_from_the_utah_and_arizona_flood_watches(self):
        st = pick_story(snapshot())
        self.assertEqual(st.kind, "heavy_rain")
        self.assertEqual(st.states, ["UT", "AZ"])
        self.assertEqual(st.events, ["Flood Watch"])
        self.assertEqual(st.lead_city, "Phoenix, AZ")   # nearest covered city to the watches
        why = st.why_text
        for words in ("Tropical: no hurricane", "Severe: 0 tornado warning", "Extreme heat/cold: 0 heat", "Lead: heavy rain and flooding: 3 flood watch"):
            self.assertIn(words, why)

    def test_the_ranking_tropical_beats_severe_beats_heat_beats_rain(self):
        base = snapshot()
        flood = alert("Flash Flood Warning", ["TX"], ["Houston, TX"], (29.7, -95.4))
        heat = [alert("Excessive Heat Warning", ["AZ"], ["Phoenix, AZ"], (33.4, -112.0), i) for i in range(3)]
        severe = [alert("Tornado Watch", ["OK"], [], (35.5, -97.5), i) for i in range(2)]
        trop = alert("Hurricane Warning", ["FL"], ["Miami, FL"], (25.8, -80.2))
        self.assertEqual(pick_story(with_alerts(base, flood)).kind, "heavy_rain")
        self.assertEqual(pick_story(with_alerts(base, flood, *heat)).kind, "extreme_temp")
        self.assertEqual(pick_story(with_alerts(base, flood, *heat, *severe)).kind, "severe")
        st = pick_story(with_alerts(base, flood, *heat, *severe, trop))
        self.assertEqual((st.kind, st.lead_city, st.states), ("tropical", "Miami, FL", ["FL"]))
        self.assertIn("this rule comes first", st.why_text)

    def test_severe_needs_an_outbreak_not_one_watch(self):
        base = snapshot()
        self.assertNotEqual(pick_story(with_alerts(base, alert("Tornado Watch", ["KS"]))).kind, "severe")
        tw = [alert("Tornado Warning", ["KS"], [], (38.0, -98.0), i) for i in range(3)]
        st = pick_story(with_alerts(base, *tw))
        self.assertEqual(st.kind, "severe")
        self.assertIn("3 tornado warning(s)", st.why_text)
        self.assertEqual(st.lead_city, "Dallas, TX")   # the covered city nearest central Kansas
        sw = [alert("Severe Thunderstorm Warning", ["MN"], [], (45.0, -93.3), i) for i in range(10)]
        self.assertEqual(pick_story(with_alerts(base, *sw)).lead_city, "Minneapolis, MN")

    def test_alerts_outside_the_lower_48_and_over_water_do_not_lead(self):
        base = snapshot()
        st = pick_story(with_alerts(base, alert("Hurricane Warning", ["HI"]), alert("Hurricane Warning", [])))
        self.assertEqual(st.kind, "heavy_rain")

    def test_extreme_temperatures_from_the_forecast_alone_need_several_cities(self):
        s = copy.deepcopy(snapshot())
        on = target_date(s).isoformat()
        def set_high(key, v):
            for d in s.forecasts[key]["days"]:
                if d["start"][:10] == on:
                    d["high"]["value"] = v
        s.extra[NATIONAL]["alerts"] = []
        set_high("Phoenix, AZ", 104)
        set_high("Dallas, TX", 101)
        self.assertNotEqual(pick_story(s).kind, "extreme_temp")
        set_high("Houston, TX", 100)
        st = pick_story(s)
        self.assertEqual((st.kind, st.lead_city), ("extreme_temp", "Phoenix, AZ"))
        self.assertIn("highs of 100°F or more in", st.why_text)

    def test_a_routine_day_leads_with_the_city_that_has_the_most_to_say(self):
        s = copy.deepcopy(snapshot())
        s.extra[NATIONAL]["alerts"] = []
        st = pick_story(s)
        self.assertEqual(st.kind, "routine")
        self.assertEqual(st.lead_city, "Boston, MA")    # the highest chance of rain on the day or the night after (57%)
        self.assertIn("highest chance of rain or snow (57%)", st.why_text)

    def test_the_same_data_always_picks_the_same_story(self):
        a, b = pick_story(snapshot()), pick_story(snapshot())
        self.assertEqual(a.to_dict(), b.to_dict())


if __name__ == "__main__":
    unittest.main()
