"""Sky Sim physics: computed readouts match the numbers shown in the Lightbound reference videos (2026-11-14 study)."""
import math
import unittest

from skysim import physics as ph


class ReferenceReadouts(unittest.TestCase):
    def test_sun_from_mercury(self):  # "0.39 AU · 58 MILLION KM / 2.6× BIGGER / 6.7× AS BRIGHT / 3 MIN 13 S"
        r = ph.sun_from_planet('Mercury')
        self.assertEqual(ph.fmt_distance(r['distance_m'], 'au'), '0.39 AU')
        self.assertEqual(ph.fmt_distance(r['distance_m']), '57.9 million km')  # reference rounds to 58
        self.assertEqual(ph.fmt_ratio(r['size_x']), '2.6×')
        self.assertEqual(ph.fmt_ratio(r['brightness_x']), '6.7×')
        self.assertEqual(ph.fmt_duration(r['light_s']), '3 min 13 s')

    def test_sun_from_uranus(self):  # "19.2 AU · 2.9 BILLION KM / 5% OF WHAT WE SEE / 1/369 AS BRIGHT / 2.7 HOURS"
        r = ph.sun_from_planet('uranus')
        self.assertEqual(ph.fmt_distance(r['distance_m'], 'au'), '19.2 AU')
        self.assertEqual(ph.fmt_distance(r['distance_m']), '2.9 billion km')
        self.assertEqual(ph.fmt_ratio(r['size_x']), '5%')
        self.assertEqual(ph.fmt_ratio(r['brightness_x']), '1/368')  # reference rounds 19.2 AU -> 1/369
        self.assertEqual(ph.fmt_duration(r['light_s']), '2.7 hours')

    def test_planets_as_moon(self):  # Mars 2× / 5×, Jupiter 40× / 7,300×, Neptune 740× the full Moon
        mars, jup, nep = (ph.planet_as_moon(p) for p in ('mars', 'jupiter', 'neptune'))
        self.assertEqual(ph.fmt_ratio(mars['size_x']), '2×')
        self.assertAlmostEqual(mars['brightness_x'], 5.3, delta=0.4)
        self.assertEqual(ph.fmt_ratio(jup['size_x']), '40×')
        self.assertAlmostEqual(jup['brightness_x'], 7300, delta=150)
        self.assertAlmostEqual(nep['brightness_x'], 740, delta=15)

    def test_parent_from_moon(self):  # Phobos: 9,380 km, ~6,000 km above Mars, 42° · 81× our Moon; Ferdinand 0.14°, a quarter
        p = ph.parent_from_moon('phobos')
        self.assertEqual(ph.fmt_angle(p['angular_deg']), '42°')
        self.assertAlmostEqual(p['moon_x'], 81, delta=1.5)
        self.assertAlmostEqual(p['altitude_m'] / 1000, 6000, delta=50)
        f = ph.parent_from_moon('ferdinand')
        self.assertEqual(ph.fmt_angle(f['angular_deg']), '0.14°')
        self.assertEqual(ph.fmt_ratio(f['moon_x'], 'our Moon'), 'a quarter of our Moon')
        self.assertEqual(ph.fmt_distance(f['distance_m']), '20.9 million km')

    def test_ton618(self):  # horizon ~800 AU, matches the Sun at ~187 ly
        b = ph.black_hole_at('TON 618', ph.parse_distance('187 ly'))
        self.assertAlmostEqual(b['horizon_au'], 800, delta=15)
        self.assertAlmostEqual(b['sun_match_ly'], 187, delta=3)
        self.assertAlmostEqual(b['flux_x'], 1.0, delta=0.05)
        far = ph.black_hole_at('ton618', ph.parse_distance('10.8 billion ly'))
        self.assertEqual(ph.heat_stage(far['flux_x']), 'night')
        self.assertEqual(ph.heat_stage(ph.black_hole_at('ton618', ph.parse_distance('50 ly'))['flux_x']), 'burn')
        self.assertEqual(ph.heat_stage(ph.black_hole_at('ton618', ph.parse_distance('0.1 ly'))['flux_x']), 'melt')

    def test_smallest_star_at_sun_distance(self):  # "a tenth the width of the Moon"
        s = ph.star_in_place_of_sun('2mass_j0523')
        self.assertAlmostEqual(s['moon_x'], 0.09, delta=0.01)

    def test_earth_temperature_with_sun(self):  # Sun gives ~15 °C
        self.assertAlmostEqual(ph.star_in_place_of_sun('sun')['earth_temp_c'], 15, delta=4)
        self.assertLess(ph.star_in_place_of_sun('proxima_centauri')['earth_temp_c'], -150)

    def test_miller_clocks(self):  # 1 hour = 7 years
        k = ph.dilation_factor(3600, 7 * ph.YEAR)
        self.assertAlmostEqual(k, 61362, delta=1)
        self.assertEqual(ph.fmt_clock(351), '00:05:51')
        self.assertEqual(ph.fmt_far_clock(351 * k), '249 d 6 h')

    def test_journey_light_seconds(self):  # "714,370 km / 2.4 light-seconds"
        d = ph.parse_distance('714,370 km')
        self.assertEqual(ph.fmt_distance(d), '714,370 km')
        self.assertEqual(ph.fmt_light_time(ph.light_time_s(d)), '2.4 light-seconds')


class Parsing(unittest.TestCase):
    def test_distances(self):
        self.assertAlmostEqual(ph.parse_distance('10.8e9 ly'), ph.parse_distance('10.8 billion ly'))
        self.assertAlmostEqual(ph.parse_distance('0.39 AU'), 0.39 * ph.AU)
        self.assertAlmostEqual(ph.parse_distance('1,000 light-years'), 1000 * ph.LY)
        self.assertAlmostEqual(ph.parse_distance(9380), 9.38e6)
        with self.assertRaises(ValueError):
            ph.parse_distance('far away')

    def test_formats(self):
        self.assertEqual(ph.fmt_distance(ph.parse_distance('10.8 billion ly')), '10.8 billion ly')
        self.assertEqual(ph.fmt_distance(ph.parse_distance('1000 ly')), '1,000 ly')
        self.assertEqual(ph.fmt_distance(ph.parse_distance('0.1 ly')), '0.1 ly')
        self.assertEqual(ph.fmt_temp(-130.4), '−130 °C')
        self.assertEqual(ph.fmt_temp(15.2), '15 °C')
        self.assertEqual(ph.angular_size_deg(1, 0.5), 180.0)
        self.assertTrue(math.isclose(ph.SUN_FROM_EARTH_DEG, 0.533, abs_tol=0.002))


if __name__ == '__main__':
    unittest.main()
