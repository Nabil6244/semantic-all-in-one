"""pakMap place names and camera framing."""

import unittest

from pakmap.geo import GeoError, fit, merc_lat, merc_y, resolve, resolve_many, view_for


class TestResolve(unittest.TestCase):
    def test_coordinates_codes_and_names(self):
        p = resolve("-1.29, 36.82")
        self.assertEqual((p.kind, p.lat, p.lon), ("point", -1.29, 36.82))
        k = resolve("KEN")
        self.assertEqual((k.kind, k.iso, k.name), ("country", "KEN", "Kenya"))
        self.assertTrue(k.is_area and 33 < k.bbox[0] < 35 and 41 < k.bbox[2] < 42)
        self.assertEqual(resolve("Kenya").iso, "KEN")

    def test_cities_and_the_point_or_area_preference(self):
        city = resolve("Nairobi", "point")
        self.assertEqual(city.kind, "city")
        self.assertAlmostEqual(city.lon, 36.82, delta=0.05)
        self.assertEqual(resolve("Nairobi", "area").kind, "admin1")  # the county, for a fill
        moscow = resolve("Moscow", "point")
        self.assertEqual((moscow.kind, moscow.iso), ("city", "RUS"))
        self.assertAlmostEqual(moscow.lat, 55.75, delta=0.1)
        self.assertEqual(resolve("city:Moscow,RUS").iso, "RUS")
        self.assertEqual(resolve("Lodwar").kind, "city")  # not an area anywhere, so it can only be the city
        self.assertEqual(resolve("Kenya", "point").kind, "country")

    def test_named_regions_and_accents(self):
        self.assertEqual(resolve("Florida Panhandle").kind, "region")
        self.assertEqual(resolve("city:Bogota").iso, "COL")

    def test_waypoint_lists(self):
        pts = resolve_many("Mombasa; Nairobi ;Lodwar")
        self.assertEqual([p.name for p in pts], ["Mombasa", "Nairobi", "Lodwar"])
        self.assertTrue(all(p.kind == "city" for p in pts))

    def test_errors_say_what_to_do(self):
        with self.assertRaisesRegex(GeoError, r"did you mean Nairobi\?"):
            resolve("Nairobii")
        with self.assertRaisesRegex(GeoError, "lat,lon"):
            resolve("Atlantis")
        with self.assertRaisesRegex(GeoError, "not a valid lat,lon"):
            resolve("136.8,-1.2")
        with self.assertRaisesRegex(GeoError, "unknown country code 'ZZZ'"):
            resolve("ZZZ")
        with self.assertRaisesRegex(GeoError, "no city called"):
            resolve("city:Atlantis")
        with self.assertRaisesRegex(GeoError, "empty"):
            resolve("  ")


class TestFraming(unittest.TestCase):
    def test_mercator_round_trip(self):
        for lat in (-60, 0, 33, 70):
            self.assertAlmostEqual(merc_lat(merc_y(lat)), lat, places=6)

    def test_bigger_areas_zoom_out_and_the_centre_is_inside(self):
        small = fit((36.0, -2.0, 38.0, 0.0))
        big = fit((20.0, -10.0, 50.0, 20.0))
        self.assertGreater(small[2], big[2] + 2)
        self.assertAlmostEqual(small[0], 37.0, places=3)
        self.assertGreaterEqual(fit((0, 0, 360, 80))[2], 1.5)

    def test_the_shape_fits_inside_the_frame_with_room_to_spare(self):
        import math
        w, s, e, n = resolve("Kenya").bbox
        cx, cy, z = fit((w, s, e, n))
        width_px = (e - w) / 360 * 512 * 2 ** z
        height_px = (merc_y(s) - merc_y(n)) * 512 * 2 ** z
        self.assertLessEqual(width_px, 1920 * 0.66 + 1)
        self.assertLessEqual(height_px, 1080 * 0.66 + 1)
        self.assertTrue(math.isclose(max(width_px / (1920 * 0.64), height_px / (1080 * 0.64)), 1.0, rel_tol=0.05))

    def test_frames(self):
        ken = resolve("Kenya")
        self.assertEqual(view_for(ken, "globe")[2], 1.7)
        self.assertEqual(view_for(ken, "continental")[2], 3.3)
        self.assertAlmostEqual(view_for(ken)[2], fit(ken.bbox)[2], places=6)
        self.assertGreaterEqual(view_for(resolve("Florida Panhandle"), "region")[2], 5.0)
        self.assertEqual(view_for(resolve("Nairobi", "point"))[2], 8.4)  # a point sits at local scale


if __name__ == "__main__":
    unittest.main()
