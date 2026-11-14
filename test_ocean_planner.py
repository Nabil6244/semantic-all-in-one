"""Ocean style step 5: the reader + planner, tested on three different topics (docs/ocean/PATTERNS.md section 7)."""

import unittest

from ocean import planner as P
from ocean import reader as R
from ocean import stage as OS

SHARKS = """Picture this. You're floating off the coast of California and below you is a great white shark.
It has about 300 teeth. Except one afternoon in 2009, 17 of them vanished from the same island.
They didn't die, they fled. When most people think about what scares a great white, they bring up dolphins.
Shark researchers call it a myth. The first one is the most obvious. It's a bigger great white.
Researchers watched up to eight great whites feeding on a whale carcass. The smaller sharks hung back.
The second one is the seal. Seals mob sharks in groups. About 93% of attacks fail.
The next one is the orca. In November 1997, two orcas killed a great white off the Farallon Islands.
Within hours, every shark left the island. They stayed away for four hours, then a whole year.
Now imagine you're a diver at 12 m below the surface. Do you swim for the boat, hold still, or dive to the bottom?
Most divers survive by facing the shark. Which animal should we cover next? Let us know in the comments."""

SQUID = """Picture this. You're snorkeling over a reef at night and a squid hovers in front of your mask.
Now take that same animal and sink it. A few hundred meters down, its relatives grow one giant eye.
In the midnight zone there is no light at all. The vampire squid eats dead flakes falling from above.
It can live at 900 m deep. The bigfin squid was filmed at 6,212 m. Its arms are about 8 m long.
Scientists have only seen it a dozen times. Nobody knows how it hunts. The deep is changing fast."""

JELLY = """Picture this. A glowing jellyfish drifts past a coral wall. It has no brain and no heart.
Yet it has lived on Earth for 500 million years. Some can turn their age back to zero.
They drift with the current for weeks. A single bloom can cover 100 km of coast.
Fishermen hate them. Nobody planned for them. And they are spreading."""


def _scenes(text, wps=2.8):
    import re
    sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.replace("\n", " ")) if s.strip()]
    t, out = 0.0, []
    for i, s in enumerate(sents):
        d = len(s.split()) / wps
        out.append({"scene_no": i + 1, "text": s, "start": t, "end": t + d})
        t += d
    return out


def _cards(pl):
    return [c for s in pl.shots for c in s["cards"]]


class ReaderTest(unittest.TestCase):
    def test_numbers_and_kinds(self):
        f = R.read("In November 1997, 35 orcas attacked 9 sperm whales for four hours.")
        kinds = [(n.raw, n.kind) for n in f.numbers]
        self.assertIn(("1997", "year"), kinds)
        self.assertIn(("35", "count"), kinds)
        self.assertEqual(f.month, "NOV")
        self.assertEqual([n.kind for n in R.read("About 93% of them were gone.").numbers], ["percent"])
        self.assertEqual(R.read("It dives to 2,000 m below the surface.").numbers[0].kind, "depth")
        self.assertEqual(R.read("The smaller ones, 3 to 4 m long, hung back.").numbers[0].raw, "3-4 m")
        self.assertEqual(R.read("Seventeen of them vanished.").numbers[0].raw, "17")

    def test_animals_and_generic_names(self):
        f = R.read("Great whites hunt seals, but sharks avoid killer whales.")
        self.assertEqual(f.names, ["great_white", "seal", "shark", "orca"])
        self.assertEqual(f.animals[2][2].get("generic"), "shark")
        self.assertEqual(R.read("A vampire squid drifts.").animals[0][0], "vampire_squid")     # its own catalogue animal
        self.assertEqual([a[0] for a in R.read("A manta ray passed two tiger sharks.").animals], ["manta_ray", "tiger_shark"])

    def test_shapes(self):
        self.assertTrue(R.read("Researchers tagged 17 sharks.").study)
        self.assertEqual(R.read("The first one is the most obvious.").ordinal, 0)
        self.assertEqual(R.read("Do you swim for the boat, hold still, or dive to the bottom?").choice,
                         ["swim for boat", "hold still", "dive to bottom"])
        self.assertEqual(R.read("In the midnight zone there is no light.").set_hint, "abyss")
        self.assertEqual(R.read("It dives to 2,000 m below the surface.").set_hint, "depth_column")
        self.assertIsNotNone(R.read("Every shark fled the island.").flee)


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans = {}
        for name, text, chaps in (("sharks", SHARKS, (20.0, 45.0, 70.0)), ("squid", SQUID, (15.0,)), ("jelly", JELLY, ())):
            sc = _scenes(text)
            cls.plans[name] = (sc, P.plan(sc, chaps, channel="Test"))

    def test_shots_cover_the_whole_narration_without_holes(self):
        for name, (sc, pl) in self.plans.items():
            shots = [l for l in pl.layers if l["name"] == "ocean.lay_ocean"]
            self.assertAlmostEqual(shots[0]["start"], 0.0, places=2, msg=name)
            for a, b in zip(shots, shots[1:]):
                self.assertAlmostEqual(a["end"], b["start"], places=2, msg=name)
            self.assertAlmostEqual(shots[-1]["end"], sc[-1]["end"], places=2, msg=name)
            self.assertEqual(pl.layers[-1]["name"], "ocean.lay_captions", name)

    def test_shot_lengths_follow_the_reference(self):
        for name, (sc, pl) in self.plans.items():
            self.assertLessEqual(pl.report["shot_max_s"], 16.0, name)

    def test_number_cards(self):
        cards = _cards(self.plans["sharks"][1])
        for kind in ("number_hero", "calendar"):
            self.assertIn(kind, cards)
        one = lambda text: _cards(P.plan(_scenes("The water is calm today and nothing moves at all. " + text, wps=2.0)))
        self.assertIn("progress", one("About 93% of all attacks fail in the end."))
        self.assertIn("clock", one("They stayed away from the island for four hours."))
        self.assertIn("dot_grid", one("Out of 90 real attacks, only 5 seals were caught."))
        self.assertIn("calendar", one("Except one afternoon in 2009, they all vanished."))

    def test_story_cards(self):
        cards = _cards(self.plans["sharks"][1])
        self.assertIn("mystery", cards)
        self.assertIn("choose_move", cards)
        self.assertIn("comments", cards)
        if self.plans["sharks"][0][-1]["end"] >= P.END_CARD_MIN_S:     # the end screen only closes a full-length film
            self.assertEqual(cards[-1], "watch_next")

    def test_generic_sharks_become_the_great_white(self):
        sc, pl = self.plans["sharks"]
        names = {e["args"].get("name") for l in pl.layers if l["name"] == "ocean.lay_ocean"
                 for e in l["params"]["elements"] if e["kind"] == "animal" and not e["args"].get("silhouette")}
        self.assertIn("great_white", names)
        self.assertNotIn("shark", names)

    def test_flee_swims_off(self):
        sc, pl = self.plans["sharks"]
        exits = [e["exit"] for l in pl.layers if l["name"] == "ocean.lay_ocean" for e in l["params"]["elements"]
                 if e["kind"] == "animal" and e["t1"] is not None]
        self.assertTrue(any(x.startswith("slide") for x in exits))

    def test_deep_script_uses_deep_sets(self):
        sets = self.plans["squid"][1].report["sets"]
        self.assertTrue({"abyss", "depth_column"} & set(sets))

    def test_unknown_animals_still_move(self):
        sc, pl = self.plans["jelly"]
        self.assertLessEqual(pl.report["longest_still_s"], 6.0)
        els = [e for l in pl.layers if l["name"] == "ocean.lay_ocean" for e in l["params"]["elements"]]
        self.assertTrue(els)

    def test_captions_stay_off_text_cards(self):
        sc, pl = self.plans["sharks"]
        windows = []
        for l in pl.layers:
            if l["name"] != "ocean.lay_ocean":
                continue
            for e in l["params"]["elements"]:
                k = e["kind"][6:] if e["kind"].startswith("ocean_") else ""
                if k in P.TEXT_CARDS and e["t1"] is not None:
                    windows.append((l["start"] + e["t0"], l["start"] + e["t1"], k in P.SIDE_CARDS))
        for c in pl.captions:
            for a, b, side in windows:
                if side and c.get("kind") != "number":
                    continue                    # a corner card (calendar, clock) leaves room for a word caption
                over = min(c["t1"], b) - max(c["t0"], a)
                self.assertLessEqual(over, 0.41 * (c["t1"] - c["t0"]) + 1e-6, (c["key"], a, b))

    def test_gags_keep_their_gap(self):
        sc, pl = self.plans["sharks"]
        times = sorted(l["start"] + e["t0"] for l in pl.layers if l["name"] == "ocean.lay_ocean"
                       for e in l["params"]["elements"] if e["kind"][6:] in P.GAGS)
        for a, b in zip(times, times[1:]):
            self.assertGreaterEqual(b - a, P.GAG_GAP_S - 1e-6)

    def test_a_planned_frame_renders(self):
        sc, pl = self.plans["sharks"]
        shot = [l for l in pl.layers if l["name"] == "ocean.lay_ocean"][1]
        img = OS.lay_ocean(1.0, shot["end"] - shot["start"], shot["params"])
        self.assertEqual(img.size, (OS.W, OS.H))

    def test_empty_script(self):
        self.assertEqual(P.plan([]).report["shots"], 0)


if __name__ == "__main__":
    unittest.main()


class GroupAndAlignTest(unittest.TestCase):
    def test_counted_group_is_island_map_and_size_is_car(self):
        sc = _scenes("Researchers tracked 17 great whites at the Farallon Islands, and not one came back. "
                     "Nobody expected that, least of all the people who had studied them for years on end. "
                     "Picture how big they are. Each one is a 5-meter great white shark. "
                     "That is a lot of animal to scare away, and it happened in a single afternoon off the coast.", wps=2.6)
        pl = P.plan(sc)
        kinds = [e["kind"] for l in pl.layers if l["name"] == "ocean.lay_ocean" for e in l["params"]["elements"]]
        self.assertIn("ocean_island_map", kinds)
        self.assertIn("ocean_size_compare", kinds)

    def test_a_group_leaves_together(self):
        sc = _scenes("A group of great whites circled. Then an orca arrived.", wps=2.5)   # a counted group is the island map
        pl = P.plan(sc)
        shot = next(l for l in pl.layers if l["name"] == "ocean.lay_ocean" and
                    any(e["args"].get("name") == "orca" for e in l["params"]["elements"] if e["kind"] == "animal"))
        els = shot["params"]["elements"]
        whites = [e for e in els if e["kind"] == "animal" and e["args"].get("name") == "great_white" and not e["args"].get("silhouette")]
        orca = [e for e in els if e["kind"] == "animal" and e["args"].get("name") == "orca"]
        self.assertGreaterEqual(len(whites), 3)
        self.assertTrue(orca)
        for e in whites:                       # every great white of the group is gone by the time the orca is in
            self.assertIsNotNone(e["t1"])
            self.assertLessEqual(e["t1"], orca[0]["t0"] + 0.2)

    def test_script_words_keep_their_punctuation_on_the_spoken_times(self):
        from ocean import runner as RN
        spoken = [("Picture", 0.1, 0.3), ("this", 0.3, 0.6), ("In", 1.0, 1.1), ("two thousand nine", 1.1, 1.9),
                  ("two", 2.0, 2.2), ("orcas", 2.2, 2.6), ("arrived", 2.6, 3.0)]
        out = RN.align_script("Picture this. In 2009, two orcas arrived.", spoken)
        self.assertEqual([w[0] for w in out], ["Picture", "this.", "In", "2009,", "two", "orcas", "arrived."])
        self.assertAlmostEqual(out[3][1], 1.1)
        for a, b in zip(out, out[1:]):
            self.assertLessEqual(a[1], b[1])
        scenes = RN.scenes_from_words(out, 3.0)
        self.assertEqual(scenes[0]["text"].split(".")[0], "Picture this")


class NarrationMatchTest(unittest.TestCase):
    """The picture follows the line: 'two orcas arrived' shows two orcas when 'orcas' is said; the shark that fled is
    the one that leaves; animals are never added and removed in the same instant; a phrase caption every few seconds."""

    def setUp(self):
        lines = ["Picture this. You're floating off the coast of California, and below you is a great white shark.",
                 "It has about 300 teeth, and nothing in the ocean hunts it.",
                 "Except one animal. In 2009, two orcas arrived at the Farallon Islands.",
                 "Within hours, every great white fled.",
                 "Researchers tracked 17 sharks, and not one came back that year.",
                 "The first animal on our list is the orca."]
        t, sc = 0.0, []
        for ln in lines:
            d = len(ln.split()) / 2.7
            sc.append({"text": ln, "start": t, "end": t + d})
            t += d
        self.pl = P.plan(sc)
        self.els = [(l["start"], e) for l in self.pl.layers if l["name"] == "ocean.lay_ocean" for e in l["params"]["elements"]]

    def test_two_orcas_arrive_when_named(self):
        orcas = [(s0 + e["t0"]) for s0, e in self.els if e["kind"] == "animal" and e["args"].get("name") == "orca"
                 and not e["args"].get("silhouette")]
        self.assertGreaterEqual(len(orcas), 2)
        self.assertLess(min(orcas), 22.0)

    def test_nothing_flickers(self):
        for s0, e in self.els:
            if e["t1"] is not None:
                self.assertGreater(e["t1"] - e["t0"], 0.3, e)

    def test_shark_flees_orcas_stay(self):
        fled = [e for s0, e in self.els if e["kind"] == "animal" and e["args"].get("name") == "great_white"
                and str(e.get("exit", "")).startswith("slide")]
        self.assertTrue(fled)

    def test_number_card_line(self):
        hero = next(e for s0, e in self.els if e["kind"] == "ocean_number_hero")
        self.assertEqual(hero["args"]["number"], "~300 TEETH")       # its clause ends at the comma: the number stands alone
        self.assertEqual(hero["args"]["key"], "")

    def test_captions_often(self):
        self.assertGreaterEqual(len(self.pl.captions), 5)
