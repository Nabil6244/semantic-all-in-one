"""3D shots must be about what the narration is about: a world named as a yardstick or a setting, or a common word that is also a craft's name,
does not become a model or globe (What If and StarMap Cinema both read whatif.planner._world/_craft and whatif.variety.CARRY)."""
import unittest

from whatif import planner as pl
from whatif import variety


class WorldRelevance(unittest.TestCase):
    def test_yardstick_is_not_the_subject(self):
        for t in ("It pulls 230 times Earth's gravity.", "The pressure is 22 times Earth's air pressure.", "A planet far bigger than Earth.",
                  "Hotter than Venus, like Mars but wetter."):
            self.assertIsNone(pl._world(t), t)

    def test_inside_the_world_is_not_a_globe(self):
        for t in ("Jupiter's clouds close over the probe.", "Deeper inside Jupiter the pressure crushes everything.", "You fall through the atmosphere of Venus."):
            self.assertIsNone(pl._world(t), t)

    def test_world_seen_from_outside_still_a_globe(self):
        self.assertEqual(pl._world("Jupiter is the largest planet.")[1], "JUPITER")
        self.assertEqual(pl._world("Mars orbits at about one and a half units")[1], "MARS")

    def test_sunlight_is_not_the_sun(self):
        self.assertIsNone(pl._world("The sunlight fades."))


class CraftRelevance(unittest.TestCase):
    def test_common_words_are_not_craft(self):
        for t in ("This insight changed everything.", "She won with perseverance.", "The Vikings sailed west.", "A pioneer of physics.",
                  "Hubble's law says galaxies recede.", "Peter Parker looked up.", "Ferdinand Magellan sailed around the world."):
            self.assertIsNone(pl._craft(t), t)

    def test_real_craft_still_found(self):
        for t, n in (("The InSight lander listened.", "INSIGHT"), ("Perseverance rover landed in 2021.", "PERSEVERANCE"), ("Viking 1 landed.", "VIKING LANDER"),
                     ("Pioneer 10 flew past.", "PIONEER 10"), ("The Parker Solar Probe dives.", "PARKER SOLAR PROBE"), ("Hubble took the picture.", "HUBBLE SPACE TELESCOPE"),
                     ("Magellan mapped Venus.", "MAGELLAN")):
            self.assertEqual((pl._craft(t) or ("", ""))[1], n, t)


class CarryAndRepeat(unittest.TestCase):
    def test_the_probe_inside_a_descent_is_not_carried(self):
        self.assertIsNone(variety.CARRY.search("The probe falls under its parachute through the clouds."))
        self.assertTrue(variety.CARRY.search("The probe kept going."))


if __name__ == "__main__":
    unittest.main()
