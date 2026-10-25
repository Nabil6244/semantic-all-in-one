"""StarMap Cinema: two big texts that overlap in time and on screen are never drawn on top of each other (project 034: '1 ASTRONOMICAL UNIT'
over '49 MILLION KM')."""
import unittest

from starmap.cinema import declutter


def cap(a, z, anchor="ml"): return {"type": "tm_caption", "text": "X", "anchor": anchor, "start": a, "end": z}
def met(a, z, anchor="center"): return {"type": "tm_metric", "value": "49", "anchor": anchor, "start": a, "end": z}


class Declutter(unittest.TestCase):
    def run_it(self, *layers):
        spec = {"layers": list(layers)}
        notes = []
        declutter(spec, notes)
        return spec["layers"], notes

    def test_the_earlier_text_leaves_sooner_when_it_still_has_time(self):
        a, b = met(28.3, 33.3), cap(32.5, 36.5)
        out, notes = self.run_it(a, b)
        self.assertEqual((a["end"], b["start"]), (32.38, 32.5))
        self.assertTrue(notes)

    def test_the_later_text_arrives_later_when_the_earlier_is_short(self):
        a, b = met(10.0, 11.0), cap(10.5, 15.0)
        self.run_it(a, b)
        self.assertEqual((a["end"], b["start"]), (11.0, 11.12))

    def test_texts_in_different_places_are_left_alone(self):
        a, b = met(1, 5, "upper_right"), cap(2, 6, "bc")
        self.run_it(a, b)
        self.assertEqual((a["start"], a["end"], b["start"], b["end"]), (1, 5, 2, 6))

    def test_a_number_that_fits_nowhere_goes_but_a_caption_stays(self):
        a, b = cap(10.0, 11.0), met(10.2, 11.0)
        out, _ = self.run_it(a, b)
        self.assertIn(a, out)
        self.assertNotIn(b, out)

    def test_no_two_overlap_after(self):
        layers = [cap(0, 4), met(1, 5), cap(3, 8), met(6, 9)]
        out, _ = self.run_it(*layers)
        for i, x in enumerate(out):
            for y in out[i + 1:]:
                self.assertLessEqual(min(x["end"], y["end"]) - max(x["start"], y["start"]), 0.05)


if __name__ == "__main__":
    unittest.main()
