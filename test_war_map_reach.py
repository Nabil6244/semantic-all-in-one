"""War maps reach every named place (Spiderweb, 2026-11-09): strategic bases deep in Russia pin by name, one pin per spot, far-apart places
framed together (never a 25 km close-up of one colour fill), number words shown as digits."""
import unittest
from types import SimpleNamespace

from cinematic_explainer.war import catalog as C, direction as D, map_events as ME, maps_tactical as MT, semantics as S


class Reach(unittest.TestCase):
    def test_strategic_bases_and_far_cities_resolve(self):
        for name in ("Olenya", "Belaya", "Dyagilevo", "Shaykovka", "Ukrainka air base", "Engels air base", "Murmansk", "Irkutsk", "Vladivostok",
                     "Tehran", "Taipei", "Kupiansk"):
            pt, why = MT.resolve_place(name)
            self.assertIsNotNone(pt, f"{name}: {why}")
        self.assertGreater(MT.resolve_place("Belaya")[0]["lon"], 100)

    def test_sites_and_places_have_unique_ids(self):
        ids = [e["id"] for e in C._entries("places.json")]
        self.assertEqual(len(ids), len(set(ids)))
        sites = [s["id"] for s in ME._site_index().values()]
        self.assertTrue(sites)

    def test_town_and_its_base_are_one_pin(self):
        when = lambda n: 1.0 if n in ("Olenya", "Belaya") else None      # noqa: E731
        out = D._distinct_places([{"name": "Siberia"}, {"name": "Olenya"}, {"name": "Belaya"}, {"name": "Olenya Air Base"},
                                  {"name": "Belaya Air Base"}], when)
        self.assertEqual([p["name"] for p in out], ["Olenya", "Belaya"])

    def test_far_apart_places_are_framed_together(self):
        self.assertTrue(D._far_apart(["Murmansk", "Irkutsk"]))
        self.assertFalse(D._far_apart(["Bakhmut", "Soledar"]))
        A = SimpleNamespace(time_at=lambda i: i / 15.0)
        text = "Fires broke out in Murmansk and in Irkutsk."
        p = D._narrate_map({"theme": "tactical", "places": [{"name": "Murmansk"}, {"name": "Irkutsk"}], "routes": []}, text, A, 0.0)
        self.assertEqual(len(p["focus"]), 1)
        self.assertNotIn("close_steps", p)

    def test_near_places_still_get_close_ups(self):
        A = SimpleNamespace(time_at=lambda i: i / 15.0)
        p = D._narrate_map({"theme": "tactical", "places": [{"name": "Bakhmut"}, {"name": "Soledar"}], "routes": []},
                           "Fighting moved from Bakhmut to Soledar.", A, 0.0)
        self.assertIn(True, p.get("close_steps") or [])

    def test_wide_view_allows_russia_wide_spans(self):
        self.assertGreaterEqual(MT.MAX_SPAN_DEG, 120)

    def test_number_words_with_a_scale(self):
        n = S.find_numbers("more than four thousand kilometres from Ukraine")[0][0]
        self.assertEqual((n.value, n.unit), (4000.0, "kilometres"))
        self.assertEqual(D._chip_title(n), "4,000")
        self.assertEqual(D._chip_title(S.find_numbers("four air bases were hit")[0][0]), "4")
        self.assertEqual(D._chip_title(S.find_numbers("41 aircraft were hit")[0][0]), "41")


if __name__ == "__main__":
    unittest.main()
