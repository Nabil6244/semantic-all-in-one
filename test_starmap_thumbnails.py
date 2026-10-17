"""Thumbnail candidates: the video's strongest moments, clean pictures, the title's words or the number."""

import unittest

from starmap.thumbnails import CLUTTER, _wrap, moments, punch


class Thumbnails(unittest.TestCase):
    def test_the_title_keeps_its_own_words(self):
        self.assertEqual(punch("THE JOURNEY OF VOYAGER 1: FROM EARTH TO INTERSTELLAR SPACE"), "JOURNEY OF VOYAGER 1")
        self.assertEqual(punch("How a tiny probe left the Sun's realm behind forever"), "TINY PROBE LEFT SUN'S")

    def test_a_number_never_stands_alone_on_a_line(self):
        self.assertEqual(_wrap("JOURNEY OF VOYAGER 1", 2), ["JOURNEY OF", "VOYAGER 1"])

    def test_the_moments_are_a_close_up_the_number_and_the_journey_never_under_footage(self):
        spec = {"footage": [{"start": 10, "end": 20}],
                "camera": {"moves": [{"t": 2, "dur": 5, "to": {"target": "jupiter", "fill": 0.6}},
                                     {"t": 12, "dur": 5, "to": {"target": "saturn", "fill": 0.9}},
                                     {"t": 30, "dur": 10, "to": {"path": {"trajectory": "v"}}}]},
                "layers": [{"type": "big_number", "value": 25, "unit": "BILLION KM", "start": 22, "end": 25}]}
        got = moments(spec)
        self.assertEqual([k for k, _, _ in got], ["hero", "number", "journey"])
        self.assertLess(got[0][1], 10, "the close-up under the footage is not used")
        self.assertEqual(got[1][2], "25 BILLION KM")
        self.assertIn("stat_chip", CLUTTER)


if __name__ == "__main__":
    unittest.main()
