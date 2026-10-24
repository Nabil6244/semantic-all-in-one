"""Country views frame the mainland (not Alaska/Hawaii/overseas pieces), and stock pictures already used are the last choice."""
import unittest

from pakmap.geo import resolve, view_for


class CountryView(unittest.TestCase):
    def test_usa_centre_is_inside_the_lower_48(self):
        lon, lat, _ = view_for(resolve("United States"), "country")
        self.assertTrue(-125 < lon < -66 and 24 < lat < 50, (lon, lat))

    def test_france_not_in_the_atlantic(self):
        lon, lat, _ = view_for(resolve("France"), "country")
        self.assertTrue(-5 < lon < 10 and 41 < lat < 52, (lon, lat))

    def test_state_unchanged(self):
        loc = resolve("Texas")
        self.assertEqual(loc.view_bbox, loc.bbox)


if __name__ == "__main__":
    unittest.main()
