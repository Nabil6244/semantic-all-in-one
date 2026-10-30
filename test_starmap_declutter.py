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


class ChipsAndTemplates(unittest.TestCase):
    def run_it(self, *layers):
        spec = {"layers": list(layers)}
        declutter(spec, [])
        return spec["layers"]

    def test_a_corner_chip_yields_to_a_template_headline_on_the_same_ground(self):
        chip = {"type": "stat_chip", "value": 100, "label": "X", "corner": "bl", "start": 10.0, "end": 16.0}
        tpl = {"type": "tm_template", "template": {"items": [{"p": "number", "at": [0.03, 0.885], "size": 52, "maxw": 0.6}]}, "start": 12.0, "end": 17.0}
        out = self.run_it(chip, tpl)
        self.assertIn(tpl, out)
        self.assertLessEqual(chip["end"], 12.0 - 0.12 + 1e-6)

    def test_a_chip_in_the_other_corner_is_left_alone(self):
        chip = {"type": "stat_chip", "value": 100, "label": "X", "corner": "br", "start": 10.0, "end": 16.0}
        tpl = {"type": "tm_template", "template": {"items": [{"p": "text", "at": [0.035, 0.11], "size": 30, "maxw": 0.3}]}, "start": 12.0, "end": 17.0}
        self.run_it(chip, tpl)
        self.assertEqual((chip["start"], chip["end"], tpl["start"], tpl["end"]), (10.0, 16.0, 12.0, 17.0))


class Slivers(unittest.TestCase):
    def test_a_sliver_of_map_between_two_shots_is_closed_and_a_flash_card_goes(self):
        from starmap.cinema import close_slivers
        a, b = {"id": "a", "start": 10.0, "end": 15.0}, {"id": "b", "start": 15.3, "end": 20.0}
        chip = {"type": "stat_chip", "value": 1, "label": "X", "start": 30.0, "end": 31.5}
        spec = {"footage": [a, b], "layers": [chip], "camera": {"moves": [{"t": 15.1, "dur": 0}]}}
        close_slivers(spec, [])
        self.assertEqual(a["end"], 15.3)
        self.assertEqual(spec["layers"], [])

    def test_a_camera_cut_just_before_a_shot_is_covered_by_the_shot(self):
        from starmap.cinema import close_slivers
        b = {"id": "b", "start": 15.96, "end": 21.0}
        spec = {"footage": [b], "layers": [], "camera": {"moves": [{"t": 15.68, "dur": 0}]}}
        close_slivers(spec, [])
        self.assertEqual(b["start"], 15.68)


class HandOvers(unittest.TestCase):
    def test_two_full_screen_layers_that_meet_cut_instead_of_fading_through_the_map(self):
        from starmap.cinema import close_slivers
        a = {"type": "cinema_globe", "start": 1.0, "end": 6.0, "fade_in": 0.55, "fade_out": 0.6}
        b = {"type": "cinema_plate", "start": 6.5, "end": 9.0, "fade_in": 0.55, "fade_out": 0.6}
        close_slivers({"footage": [], "layers": [a, b], "camera": {"moves": []}}, [])
        self.assertEqual((a["end"], a["fade_out"], b["fade_in"]), (6.5, 0.0, 0.0))

    def test_a_clip_handing_over_to_a_globe_is_one_cut(self):
        from starmap.cinema import close_slivers
        f = {"id": "f", "start": 1.0, "end": 5.0}
        g = {"type": "cinema_globe", "start": 5.3, "end": 9.0, "fade_in": 0.55, "fade_out": 0.6}
        close_slivers({"footage": [f], "layers": [g], "camera": {"moves": []}}, [])
        self.assertEqual((f["end"], f.get("transition_out"), g["fade_in"]), (5.3, "cut", 0.0))
