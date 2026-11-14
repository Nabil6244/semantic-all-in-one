"""Ocean: the picture follows the narration line by line (ocean/relations.py + the sentence scenes in ocean/cards_story.py),
the torch-lit dark set, polaroid photo rows for the Visuals tab and the ink thumbnail."""

import tempfile
import unittest
from pathlib import Path

from ocean import clips as CL
from ocean import planner as P
from ocean import reader as R
from ocean import relations as REL
from ocean import stage as OS
from ocean import thumbnail as TH

LINES = [
    "Picture this. You're hanging 20 m under the sea ice, and above you there is one bright square hole.",
    "The water is -1.5 degrees, colder than anything you've ever swum in.",
    "Your torch beam reaches a few metres into the dark, and then it just stops.",
    "Then a grey Greenland shark slides into the light and starts to circle you.",
    "Some of these sharks were already swimming before the United States existed.",
    "Its scientific name means small head, and everything else about it is huge.",
    "The biggest one ever measured was 5.5 m long.",
    "The 7 m monsters you read about online have never been verified.",
    "In 2012, researchers tagged six sharks near Baffin Island.",
    "Their cruising speed was about 1.2 km an hour. You walk faster than that.",
    "So how does the slowest shark in the sea catch anything?",
    "Scientists checked the stomachs of 45 sharks in Svalbard, and a third had eaten seal.",
    "One shark had two seals inside it, swallowed whole.",
    "Others had a reindeer in its stomach, and parts of a horse.",
    "Up here, seals sleep in the water to stay away from polar bears up on the ice.",
    "In 2013, two fishermen in Newfoundland pulled a moose out of one shark's mouth.",
    "Now, about those eyes.",
    "A small parasite hangs off each eye, and roughly nine in 10 sharks have one.",
    "Like other sharks, it can feel the electric fields your body gives off.",
    "If you panic, you use air about 3 times faster.",
]
EXPECT = {1: "temp_tag", 4: "year_anchor", 5: "latin_name", 6: "size_compare", 7: "ghost_size", 8: "map_pin",
          9: "hud_bars", 10: "question", 11: "icon_grid", 12: "stomach", 13: "stomach", 14: "above_below",
          15: "map_pin", 16: "anatomy", 17: "icon_grid", 18: "anatomy", 19: "hud_bars"}


def _scenes():
    t, out = 0.0, []
    for i, ln in enumerate(LINES):
        d = max(2.4, len(ln.split()) / 2.7)
        out.append({"scene_no": i + 1, "text": ln, "start": t, "end": t + d})
        t += d
    return out


class RelationsTest(unittest.TestCase):
    def test_reads(self):
        r = R.read("In Greenland, one shark had two harp seals inside it.").rel
        self.assertEqual(r.inside, ["seal"])
        self.assertEqual(R.read("Others had a reindeer in its stomach, and parts of a horse.").rel.inside, ["reindeer", "horse"])
        self.assertEqual(R.read("The water is -1.5 degrees.").rel.temp, "-1.5 °C")
        self.assertEqual(R.read("seals sleep in the water away from polar bears up on the ice").rel.above, ("polar_bear", "seal", "ice"))
        self.assertEqual(R.read("before the United States existed").rel.age[0], 1776)
        self.assertEqual(R.read("roughly nine in 10 of them").rel.fraction, (9, 10))
        self.assertEqual(R.read("In the Cretaceous, it would not survive.").rel.verdict, "dies")
        self.assertEqual(R.read("Now, about those eyes.").rel.part, "eye")
        self.assertEqual(R.read("It has about 300 teeth.").rel.part, "")            # a number line is not a close-up
        f = R.read("Their cruising speed was about 1.2 km an hour. You walk faster than that.")
        self.assertEqual([x[0] for x in f.rel.speed], ["IT", "YOU, WALKING"])
        self.assertFalse(f.numbers)                                              # the speed is not a length card too
        self.assertIsNotNone(REL.place_latlon("Newfoundland"))
        self.assertIsNone(REL.place_latlon("Picture"))

    def test_every_fact_line_gets_its_own_scene(self):
        sc = _scenes()
        pl = P.plan(sc)
        got = {}
        for ly in pl.layers:
            if ly["name"] != "ocean.lay_ocean":
                continue
            for e in ly["params"]["elements"]:
                k = e["kind"]
                if not k.startswith("ocean_") or k == "ocean_name_tag":
                    continue
                t0 = ly["start"] + e["t0"]
                i = max(j for j, s in enumerate(sc) if s["start"] - 0.05 <= t0)
                got.setdefault(i, k[6:])
        for i, kind in EXPECT.items():
            self.assertEqual(got.get(i), kind, LINES[i])
        sets = [s[1] for ly in pl.layers if ly["name"] == "ocean.lay_ocean" for s in ly["params"]["sets"]]
        self.assertIn("ice_hole", sets)
        self.assertIn("dark", sets)

    def test_land_animals_stay_in_the_cards(self):
        pl = P.plan(_scenes())
        names = {e["args"].get("name") for ly in pl.layers if ly["name"] == "ocean.lay_ocean"
                 for e in ly["params"]["elements"] if e["kind"] == "animal"}
        self.assertFalse(names & {"reindeer", "horse", "moose"})

    def test_era_film_ends_on_the_scoreboard(self):
        lines = ["A great white is the king of today's ocean.", "In the Cambrian, it would rule everything.",
                 "Then the Devonian, and armoured fish everywhere.", "Here it would survive, barely.",
                 "In the Jurassic, giant pliosaurs hunt.", "It would not survive a week.",
                 "In the Cretaceous, mosasaurs rule.", "It wouldn't stand a chance.", "So, the final count.",
                 "Which era would you pick?", "Let us know in the comments."]
        t, sc = 0.0, []
        for ln in lines:
            sc.append({"text": ln, "start": t, "end": t + 3.2})
            t += 3.2
        pl = P.plan(sc)
        kinds = [e["kind"] for ly in pl.layers if ly["name"] == "ocean.lay_ocean" for e in ly["params"]["elements"]]
        self.assertGreaterEqual(kinds.count("ocean_era"), 3)
        self.assertIn("ocean_scoreboard", kinds)
        board = next(e for ly in pl.layers if ly["name"] == "ocean.lay_ocean" for e in ly["params"]["elements"]
                     if e["kind"] == "ocean_scoreboard")
        self.assertEqual({k: board["args"][k] for k in ("rules", "survives", "dies")}, {"rules": 1, "survives": 1, "dies": 2})


class TorchTest(unittest.TestCase):
    def test_beam_finds_the_animal(self):
        st = OS.OceanStage()
        st.set(0.0, "dark")
        st.add("animal", 0.0, {"name": "diver", "width": 150, "face": "right", "torch": True}, pos=(170, 230))
        st.add("animal", 1.0, {"name": "great_white", "width": 500, "face": "left"}, pos=(820, 430))
        p = st.params()
        (_o, aim_before) = OS.torch_aim(p["elements"], 0.5)
        (_o, aim_after) = OS.torch_aim(p["elements"], 4.0)
        self.assertLess(abs(aim_after[0] - 820) + abs(aim_after[1] - 430), 40)
        self.assertGreater(abs(aim_before[0] - 820) + abs(aim_before[1] - 430), 40)
        img = OS.lay_ocean(4.0, 6.0, p).convert("L")
        sc = OS.L.scale()
        self.assertGreater(img.getpixel((int(820 * sc), int(430 * sc))), img.getpixel((int(820 * sc), int(80 * sc))) + 20)


class PhotosAndThumbTest(unittest.TestCase):
    def test_polaroid_rows_for_the_visuals_tab(self):
        sc = [{"text": "Two fishermen pulled a great white out and weighed it on the dock.", "start": 20.0, "end": 24.0}]
        pl = P.plan([{"text": "A great white swims.", "start": 0.0, "end": 20.0}] + sc)
        slots = CL.photo_slots(pl.layers)
        self.assertEqual(len(slots), 1)
        self.assertTrue(int(slots[0]["scene_no"]) > CL.PHOTO_SLOT_BASE)
        self.assertIn("underwater", slots[0]["query"])
        el = next(e for ly in pl.layers if ly["name"] == "ocean.lay_ocean" for e in ly["params"]["elements"]
                  if e["kind"] == "ocean_polaroid")
        self.assertEqual(el["args"]["photo_slot"], slots[0]["scene_no"])

    def test_thumbnail(self):
        self.assertEqual(TH.hook_for(["It circles you and follows you up."]), ("IT FOLLOWS ", "YOU.."))
        with tempfile.TemporaryDirectory() as d:
            out = TH.make("great_white", ("IT HUNTS ", "YOU.."), str(Path(d) / "t.jpg"))
            from PIL import Image
            im = Image.open(out)
            self.assertEqual(im.size, (1280, 720))


if __name__ == "__main__":
    unittest.main()
