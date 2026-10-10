"""StarMap's body registry grows by data: Jupiter's four large moons are places (positions from astronomy-engine's
JupiterMoons), a planet's system view frames it with its moon, the prompt offers what the registry holds, and the plan
check warns when the camera sits on a planet while the narration is about its moon, or one shot fills the map time.
Existing places and sample plans are unchanged."""

import json
import subprocess
import unittest
from pathlib import Path

from starmap.catalog import Catalog, CatalogError
from starmap.check import check_csv
from starmap.prompt import body_names, build_prompt

ROOT = Path(__file__).resolve().parent
MOONS = ("io", "europa", "ganymede", "callisto")
HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,date,label,sub,text,value_from,value_to,format,anchor,until,hold,asset,dur,why,extra"


def plan_csv(beats):
    import csv
    import io

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    cols = HEAD.split(",")
    w.writerow(cols)
    w.writerow(["plan", "plan"] + [""] * 6 + ["2026-10-10", "EUROPA"] + [""] * (len(cols) - 10))
    for i, (place, frame, text, extra) in enumerate(beats, 1):
        row = dict.fromkeys(cols, "")
        row.update(beat=f"b{i}", row="beat", vo_anchor=" ".join(text.split()[:3]), mode="map", place=place, frame=frame,
                   text=text, why="why", extra=extra.strip('"').replace('""', '"'))
        w.writerow([row[c] for c in cols])
    return out.getvalue()


def words_for(text):
    out, t = [], 0.0
    for w in text.split():
        out.append((w, t, t + 0.35))
        t += 0.4
    return out


def check(beats):
    text = " ".join(b[2] for b in beats)
    return check_csv(plan_csv(beats), words=words_for(text))


class Registry(unittest.TestCase):
    def setUp(self):
        self.cat = Catalog()

    def test_moons_are_places_with_their_planet(self):
        for m in MOONS:
            p = self.cat.place(m)
            self.assertEqual((p.kind, p.body), ("body", m))
            entry = next(w for w in self.cat.world if w["id"] == m)
            self.assertEqual(entry["parent"], "jupiter")
            self.assertTrue(entry.get("texture") or entry.get("color"), "a texture or a declared colour fallback")
        pair = self.cat.place("jupiter+europa")
        self.assertEqual((pair.kind, pair.body, pair.other), ("pair", "jupiter", "europa"))
        self.assertEqual(self.cat.place("Ganímedes").body, "ganymede")

    def test_unknown_bodies_still_say_so(self):
        with self.assertRaises(CatalogError) as e:
            self.cat.place("titan")
        self.assertIn("unknown place", str(e.exception))

    def test_every_body_has_a_surface_or_fallback(self):
        tex = ROOT / "starmap-engine" / "assets" / "textures"
        for w in self.cat.world:
            if w.get("texture"):
                self.assertTrue((tex / w["texture"]).is_file(), w["id"])

    def test_positions_from_the_shipped_library(self):
        js = ("import('./lib/ephemeris.mjs').then(m => console.log(JSON.stringify(['io','europa','ganymede','callisto'].map("
              "b => [1950, 2026, 2100].map(y => Math.round(Math.hypot(...m.offsetOf(b, new Date(y + '-06-01')))))))))")
        out = subprocess.run(["node", "-e", js], cwd=ROOT / "starmap-engine", capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        dists = json.loads(out.stdout)
        for (lo, hi), row in zip(((410e3, 435e3), (660e3, 690e3), (1.06e6, 1.08e6), (1.85e6, 1.90e6)), dists):
            for d in row:
                self.assertTrue(lo <= d <= hi, (row, lo, hi))


class SystemView(unittest.TestCase):
    def test_a_planet_system_frames_its_moon_and_a_moon_frames_its_planet(self):
        from starmap.beat_csv import read_plan
        from starmap.compile import compile_plan

        beats = [("jupiter", "system", "Jupiter rules its moons from far away", ""),
                 ("europa", "system", "Europa circles the giant planet", ""),
                 ("europa", "body", "Europa is covered in ice", "")]
        text = " ".join(b[2] for b in beats)
        comp = compile_plan(read_plan(plan_csv(beats), words_for(text)), Catalog(), resolve_media=False)
        cam = comp.spec["camera"]
        targets = [cam["start"]["target"]] + [m["to"]["target"] for m in cam["moves"]]
        self.assertIn("jupiter+europa", targets)
        self.assertIn("europa", targets)


class Prompt(unittest.TestCase):
    def test_the_prompt_offers_what_the_registry_holds(self):
        names = body_names(Catalog())
        for b in ("mercury", "venus", "uranus", "neptune", "europa (moon of jupiter)", "io (moon of jupiter)"):
            self.assertIn(b, names)
        text = build_prompt()
        self.assertNotIn("<<<BODIES>>>", text)
        self.assertIn("place=europa, not jupiter", text)


class ShortPrompt(unittest.TestCase):
    """The app's "Copy the CSV prompt" gives the short prompt for a script about space itself (no built-in mission named),
    and the full one for a mission story, a chosen mission pack, or no script."""

    def test_which_prompt(self):
        eu = "Europa is one of Jupiter's largest moons. Beneath its ice there may be an ocean."
        short = build_prompt(script=eu)
        self.assertTrue(short.startswith("Write the StarMap BEAT PLAN"))
        self.assertIn(eu, short)
        self.assertIn("europa (moon of jupiter)", short)
        self.assertNotIn("<<<", short)
        full = "You are writing the BEAT PLAN"
        self.assertTrue(build_prompt(script="In July 1969, Apollo 11 landed on the Moon.").startswith(full))
        self.assertTrue(build_prompt().startswith(full))
        self.assertTrue(build_prompt(pack="apollo11", script=eu).startswith(full))

    def test_the_short_prompt_ships(self):
        self.assertIn(ROOT / "composition_styles" / "starmap_short_prompt.txt",
                      list((ROOT / "composition_styles").glob("*_prompt.txt")), "VideoGenerator.spec packages *_prompt.txt")


class PlanChecks(unittest.TestCase):
    def shots(self, rep):
        return [w for w in rep.warnings if "same shot" in w or "of the map time" in w]

    def named(self, rep):
        return [w for w in rep.warnings if "narration names" in w]

    def test_planet_shown_while_the_story_is_its_moon(self):
        rep = check([("jupiter", "system", "Meet Europa one of the largest moons", ""),
                     ("jupiter", "body", "Europa hides an ocean under ice", "")])
        self.assertEqual(len(self.named(rep)), 2, rep.warnings)
        self.assertIn("place=europa", self.named(rep)[0])

    def test_context_shots_and_the_solar_view_are_fine(self):
        rep = check([("jupiter", "system", "Meet Europa one of the largest moons", '"{""context"": ""europa""}"'),
                     ("sun", "solar", "Earth and Jupiter are far apart", ""),
                     ("europa", "body", "Europa hides an ocean under ice", "")])
        self.assertEqual(self.named(rep), [], rep.warnings)

    def test_a_stuck_camera_is_flagged_but_a_held_one_is_not(self):
        lines = ["Clouds race around the giant planet", "Storms larger than Earth churn below", "Its rings are faint and dusty",
                 "Radiation fills the space around it"]
        stuck = check([("jupiter", "body", t, "") for t in lines])
        self.assertTrue(self.shots(stuck), stuck.warnings)
        held = check([("jupiter", "body", t, '"{""hold"": true}"') for t in lines])
        self.assertFalse([w for w in self.shots(held) if "in a row" in w], held.warnings)
        varied = check([("jupiter", "system", lines[0], ""), ("jupiter", "body", lines[1], ""),
                        ("europa", "body", lines[2], ""), ("europa", "close", lines[3], "")])
        self.assertFalse([w for w in self.shots(varied) if "in a row" in w], varied.warnings)


if __name__ == "__main__":
    unittest.main()
