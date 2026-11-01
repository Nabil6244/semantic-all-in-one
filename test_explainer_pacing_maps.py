"""Explainer scenes of 3 to 4 s (7-8 s felt slow), map cameras that close in, strong colours that arrive with the camera, and rivers that are not taken for provinces."""

import unittest

from explainer.beats import framing as FR
from explainer.director import plan as PL
from explainer.director import select as SEL
from explainer.director.options import DirectorOptions


def _words(text, start=0.0, step=0.32, pause_after=()):
    out, t = [], start
    for i, w in enumerate(text.split()):
        out.append((w, round(t, 3), round(t + step - 0.04, 3)))
        t += step + (0.6 if i in pause_after else 0.0)
    return out


STORY = ("long ago a great city stood on the coast where merchants came from every corner of the known world to trade their goods "
         "and the harbour was so busy that ships waited for days before they could unload their cargo on the crowded docks "
         "the people of the city grew rich and built enormous temples with statues that rose high above the narrow streets "
         "but over many centuries the ground beneath the city slowly sank and the water rose until the sea covered everything")


class Pacing(unittest.TestCase):
    def test_defaults_are_three_to_four_second_scenes(self):
        opt = DirectorOptions()
        self.assertLessEqual(opt.max_beat_s, 4.5)
        self.assertLessEqual(opt.split_over_s, 5.0)

    def test_long_sentences_become_short_beats(self):
        words = _words(STORY)
        dur = words[-1][2] + 0.5
        res = PL.direct(words, None, DirectorOptions(), duration=dur, materialize=False)
        durs = [b["end"] - b["start"] for b in res.plan["beats"]]
        self.assertTrue(all(d <= 5.0 + 1e-6 for d in durs), durs)
        self.assertLess(sorted(durs)[len(durs) // 2], 4.5, durs)

    def test_a_short_piece_folds_into_the_neighbour_that_stays_shorter(self):
        from explainer.director.segment import Sent
        s = lambda i, a, b: Sent(i, a, b, "x", False, [i])
        sents = [s(0, 0.0, 2.9), s(1, 3.0, 4.7), s(2, 4.8, 8.6)]          # 3.0 s, then a 1.8 s piece, then 3.8 s + tail
        beats = SEL.group(sents, 9.0, DirectorOptions())
        self.assertEqual([round(b.end - b.start, 1) for b in beats], [4.8, 4.2])


class Rivers(unittest.TestCase):
    def test_water_named_provinces(self):
        self.assertTrue(SEL._water_named_province("Nile", "River Nile"))
        self.assertTrue(SEL._water_named_province("Nile River", "River Nile"))
        self.assertTrue(SEL._water_named_province("Red Sea", "Al Bahr al Ahmar"))
        self.assertFalse(SEL._water_named_province("Bavaria", "Bayern"))
        self.assertFalse(SEL._water_named_province("Texas", "Texas"))

    def test_nile_is_not_a_map_place(self):
        ok, ignored = SEL.resolve_places(["Nile", "Egypt"])
        self.assertIn("Egypt", ok)
        self.assertNotIn("Nile", ok)

    def test_one_label_for_nile_and_nile_river(self):
        self.assertTrue(PL._same_feature("Nile River", "Nile"))
        self.assertTrue(PL._same_feature("Mediterranean Sea", "Mediterranean"))
        self.assertFalse(PL._same_feature("Egypt", "Nile"))


class MapCamera(unittest.TestCase):
    def test_strong_colours_first(self):
        self.assertNotIn("accent", PL.FILL_PALETTE[:5])
        self.assertEqual(PL.FILL_PALETTE[0], "red")

    def test_land_and_sea_centre_on_land_without_a_globe_view(self):
        cam = FR.plan_camera([{"name": "Egypt", "t": 1.0}, {"name": "Mediterranean", "t": 2.0}], 0.0, 4.5, True)
        self.assertEqual(cam["start"]["place"], "Egypt")
        self.assertGreaterEqual(cam["view"][2], FR.MIN_SINGLE_ZOOM)

    def test_short_map_beat_still_pushes_in(self):
        cam = FR.plan_camera([{"name": "Egypt", "t": 1.0}], 10.0, 13.4, False)
        pushes = [m for m in cam["moves"] if m["action"] == "push_in"]
        self.assertEqual(len(pushes), 1, cam)
        self.assertLessEqual(pushes[0]["t"] + pushes[0]["dur"], 13.4 - 0.3 + 1e-6)

    def test_push_in_passes_the_framing_check(self):
        cam = FR.plan_camera([{"name": "Egypt", "t": 1.2}], 0.0, 3.6, True)
        beat = {"id": "e1", "mode": "map", "start": 0.0, "end": 3.6,
                "camera": [{"action": "start", **cam["start"]}] + cam["moves"],
                "layers": [{"id": "e1_fill1", "type": "fill", "t": 3.0, "place": "Egypt", "role": "red"}]}
        self.assertTrue(any(m["action"] == "push_in" for m in cam["moves"]))
        self.assertEqual(FR.check_framing({"beats": [beat]}), [])

    def test_lead_country_is_coloured_when_the_camera_lands(self):
        text = ("A great harbour city once traded with every corner of the known world. For thousands of years the great river shaped every part of life along the coast of Egypt. "
                "Merchants from Greece sailed across the sea to buy grain and linen. The temples were filled with gold and the streets with traders. "
                "Then over many centuries the ground sank and the water slowly rose. Today divers explore the ruins in Egypt where the city once stood.")
        words = _words(text.lower().replace(".", ""))
        dur = words[-1][2] + 0.4
        res = PL.direct(words, text, DirectorOptions(), duration=dur, materialize=False)
        maps = [b for b in res.plan["beats"] if b.get("mode") in ("map", "map_footage")]
        filled = [b for b in maps if any(l["type"] == "fill" and l["place"] == "Egypt" for l in b.get("layers", []))]
        self.assertTrue(filled, maps)
        for b in filled:
            fill = next(l for l in b["layers"] if l["type"] == "fill")
            egypt_said = next(w[1] for w in words if w[0] == "egypt" and w[1] >= b["start"])
            self.assertLess(fill["t"], egypt_said, b)          # coloured before the name, as soon as the camera is there
            self.assertLessEqual(fill["t"] - b["start"], 1.0, b)


if __name__ == "__main__":
    unittest.main()
