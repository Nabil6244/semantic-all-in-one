"""Ocean style step 4: the card pack (docs/ocean/PATTERNS.md section 5)."""

import unittest

from PIL import ImageChops, ImageStat

from aviation import stage as AV
from ocean import cards as K
from ocean import stage as OS

SAMPLE = {
    "number_hero": {"number": "16", "line": "didn't come back", "key": "until next year"},
    "dot_grid": {"total": 90, "marked": 5, "left": ["90", "real attacks"], "right": ["5", "seals caught"]},
    "icon_rows": {"animal": "orca", "count": 40, "title": "fewer than 80", "sub": "southern residents"},
    "standoff": {"left": ["35", "orcas"], "right": ["9", "sperm whales"]},
    "progress": {"value": 93, "note": "of the old numbers"},
    "bar_race": {"title": "top speed (km/h)", "rows": [["Orca", 56, "56"], ["Great white", 40, "40"], ["Seal", 30, "30"]]},
    "meters": {"title": "1,500 m", "rows": [["light", 0.05], ["food", 0.2], ["oxygen", 0.9]]},
    "counter": {"number": "0", "label": "apex predators left"},
    "calendar": {"month": "Nov", "day": "4", "line": "Off California"},
    "clock": {"hours": 0.5},
    "size_bar": {"label": "~16 m", "length": 500},
    "callout": {"text": "massive shoulders"},
    "name_tag": {"text": "Otodus chubutensis", "sub": "the evil twin"},
    "name_chips": {"chips": [["O. obliquus", "grandpa"], ["O. angustidens", "dad"]], "lit": 1},
    "strata": {"rows": ["~7.6 million yrs", "~14.5 million yrs"], "key": "12 million years"},
    "mystery": {"slots": ["humpback", "", ""], "animals": ["humpback", "sperm_whale", ""], "lit": 1},
    "paper": {"journal": "Marine Biology, 2016", "title": "Whales that interfere when orcas hunt", "authors": "A. Author et al."},
    "choose_move": {"options": ["fight", "outlast", "hide", "swim away"], "selected": 1},
    "quiz": {"title": "does the humpback...", "options": [["eat them?", "x"], ["need them?", ""]]},
    "playbook": {"title": "the orca playbook", "step": "1. separate"},
    "crime_tape": {},
    "wanted": {"animal": "orca", "crime": "for biting a humpback calf", "reward": "one very long grudge"},
    "halo": {}, "bunting": {},
    "shop": {"title": "Megalodon tooth, 5 inch", "price": "$249.99", "animal": "tooth"},
    "diver_hud": {"depth": "12 m", "air": 0.6, "tip": "rise slowly, facing it"},
    "duel": {"left": ["orca", "predator"], "right": ["humpback", "victim"]},
    "silhouettes": {"title": "flight species", "rows": [["humpback", "fin whale"], ["dolphin", "minke whale"]]},
    "comments": {"text": "what about the leopard seal?"},
    "watch_next": {"channel": "Ocean", "line": "more apex predators"},
    "island_map": {"count": 16, "label": "tagged sharks", "animal": "great_white", "year": "2009", "dur": 6.0, "leave": 2.5},
    "size_compare": {"animal": "great_white", "metres": 5.0, "label": "5 M", "ref_label": "CAR 4.5 M"},
}


def _alpha(img):
    return ImageStat.Stat(img.getchannel("A")).sum[0]


class CardsTest(unittest.TestCase):
    def test_sample_covers_every_kind(self):
        self.assertEqual(set(SAMPLE), set(K.KINDS))

    def test_every_card_draws_something(self):
        for name, args in SAMPLE.items():
            img = K.KINDS[name](dict(args))
            self.assertEqual(img.mode, "RGBA", name)
            self.assertGreater(img.width, 40, name)
            self.assertGreater(_alpha(img), 0, name)

    def test_cards_survive_empty_args(self):
        for name, fn in K.KINDS.items():
            self.assertGreater(fn({}).width, 0, name)

    def test_animated_cards_grow_with_k(self):
        for name in K.ANIMATED:
            start = K.KINDS[name](dict(SAMPLE[name], _k=0.05))
            end = K.KINDS[name](dict(SAMPLE[name], _k=1.0))
            if start.size == end.size:
                self.assertGreater(sum(ImageStat.Stat(ImageChops.difference(start, end)).mean), 0.01, name)

    def test_count_up_keeps_prefix_and_suffix(self):
        self.assertEqual(K._count("~93%", 1.0), "~93%")
        self.assertEqual(K._count("~93%", 0.0), "~0%")
        self.assertEqual(K._count("1,500 m", 0.0), "0 m")
        self.assertEqual(K._count("abc", 0.5), "abc")

    def test_mystery_shows_names_only_when_revealed(self):
        hidden = K.mystery({"slots": ["", "", ""]})
        shown = K.mystery({"slots": ["humpback", "sperm whale", "pilot whale"]})
        self.assertEqual(hidden.size, shown.size)
        self.assertGreater(sum(ImageStat.Stat(ImageChops.difference(hidden, shown)).mean), 0.5)

    def test_crime_tape_is_full_frame(self):
        self.assertEqual(K.crime_tape({}).size, (1280, 720))


class StageCardsTest(unittest.TestCase):
    def test_cards_are_stage_kinds_and_animate_on_the_stage(self):
        st = OS.OceanStage()
        st.set(0.0, "open_water")
        st.add("ocean_progress", 0.0, SAMPLE["progress"], pos=(640, 360), enter="none", anim=2.0)
        p = st.params()
        early, late = OS.lay_ocean(0.3, 5, p), OS.lay_ocean(3.0, 5, p)
        self.assertGreater(sum(ImageStat.Stat(ImageChops.difference(early.convert("RGB"), late.convert("RGB"))).mean), 0.05)
        for name in K.KINDS:
            self.assertIn("ocean_" + name, AV._FACTORIES)


if __name__ == "__main__":
    unittest.main()
