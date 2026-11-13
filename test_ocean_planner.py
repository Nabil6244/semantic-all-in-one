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
        self.assertEqual(R.read("A vampire squid drifts.").animals[0][2]["color"], [120, 40, 70])

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
                    windows.append((l["start"] + e["t0"], l["start"] + e["t1"]))
        for c in pl.captions:
            for a, b in windows:
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
