"""StarMap phase 4: the beat CSV (timed by the narrator's words), the catalog and mission pack, the compiler to an engine
spec, Check plan, and the prompt (whose worked example is the shipped sample, which must itself obey the prompt)."""

import csv
import io
import re
import unittest
from pathlib import Path

from pakmap.words import estimate_words
from starmap import Catalog, CatalogError, PlanError, check_csv, compile_plan, is_starmap_csv, read_plan
from starmap.beat_csv import COLUMNS
from starmap.compile import stat_parts, strip_private
from starmap.prompt import build_prompt

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "starmap" / "samples"
SCRIPT = (SAMPLES / "apollo11_script.txt").read_text(encoding="utf-8")
SAMPLE = (SAMPLES / "apollo11_beats.csv").read_text(encoding="utf-8")
WORDS = estimate_words(SCRIPT, words_per_second=2.5)
MEDIA = __import__("json").loads((SAMPLES / "apollo11_media.json").read_text(encoding="utf-8"))
HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,date,label,sub,text,value_from,value_to,format,anchor,until,hold,asset,dur,why"


def csv_of(*rows):
    """A CSV from dicts (so tests never miscount commas)."""
    cols = HEAD.split(",")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue()


class SampleAndPrompt(unittest.TestCase):
    def test_the_sample_loads_clean_and_compiles(self):
        rep = check_csv(SAMPLE, WORDS, media=MEDIA)
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.warnings, [])
        self.assertEqual(rep.to_find, [])
        spec = rep.compiled.spec
        types = [L["type"] for L in spec["layers"]]
        for t in ("atmosphere", "trajectory", "title", "marker", "spacecraft", "orbit", "stat_chip", "distance", "region", "caption",
                  "photo_card", "body_labels", "mission_clock"):
            self.assertIn(t, types)
        self.assertEqual(len(spec["footage"]), 2)
        self.assertEqual(spec["footage"][0]["image"], "nasa-6900540.jpg")
        clocks = [L for L in spec["layers"] if L["type"] == "mission_clock"]
        self.assertEqual([L.get("met_zero") for L in clocks], ["1969-07-16T13:32:00Z"], "Apollo 11's own mission clock")
        # every layer type the compiler writes is one the engine registers
        index = (HERE / "starmap-engine" / "layers" / "index.mjs").read_text(encoding="utf-8")
        engine_types = set(re.findall(r"import (\w+) from", index))
        self.assertTrue(set(types) <= engine_types, set(types) - engine_types)

    def test_the_sample_obeys_its_own_prompt(self):
        """Joined beat texts are the script word for word; each beat's vo_anchor is its first words; every row's anchor is in
        its own beat's text."""
        rows = list(csv.DictReader(io.StringIO(SAMPLE)))
        beats = [r for r in rows if r["row"] == "beat"]
        self.assertEqual(" ".join(r["text"] for r in beats).split(), SCRIPT.split())
        for r in beats:
            self.assertTrue(r["text"].startswith(r["vo_anchor"]), r["beat"])
        text = {r["beat"]: r["text"] for r in beats}
        for r in rows:
            if r["row"] in ("layer", "card") and r["vo_anchor"]:
                self.assertIn(r["vo_anchor"], text[r["beat"]], f"{r['beat']} {r['type']}")

    def test_the_prompt_is_filled_with_the_sample_and_the_pack(self):
        p = build_prompt("apollo11", "My script.")
        self.assertNotIn("<<<", p)
        self.assertIn(SAMPLE.strip(), p)
        self.assertIn("translunar_coast (tli to loi)", p)
        self.assertIn("landing (1969-07-20 20:17 UTC)", p)
        self.assertTrue(p.rstrip().endswith("My script."))
        self.assertIn(HEAD, p, "the header the prompt asks for")
        for col in HEAD.split(","):
            self.assertIn(col, COLUMNS)
        p0 = build_prompt(None)
        self.assertIn("DATASETS (found by the app automatically; nothing is selected)", p0)
        self.assertIn("apollo11.lm (EAGLE", p0, "every dataset's vocabulary, qualified, with no pack chosen")
        self.assertNotIn("mission pack", p0.lower())


class Catalogs(unittest.TestCase):
    def setUp(self):
        self.cat = Catalog("apollo11")

    def test_dates(self):
        d = self.cat.date
        self.assertEqual(d("landing"), "1969-07-20T20:17:40Z")
        self.assertEqual(d("landing-00:12:40"), "1969-07-20T20:05:00Z")
        self.assertEqual(d("tli+02:00"), "1969-07-16T18:16:16Z")
        self.assertEqual(d("T+102:45:40"), "1969-07-20T20:17:40Z")
        self.assertEqual(d("2024-04-08T18:00:00Z"), "2024-04-08T18:00:00Z")
        with self.assertRaisesRegex(CatalogError, "unknown date 'landng'"):
            d("landng")

    def test_places(self):
        p = self.cat.place("Tranquility Base")
        self.assertEqual((p.kind, p.body, p.lon, p.lat), ("site", "moon", 23.473, 0.674))
        self.assertEqual(self.cat.place("the launch pad").label, "KENNEDY SPACE CENTER")
        self.assertEqual(self.cat.place("Earth+Moon").ref, "earth+moon")
        self.assertEqual(self.cat.place("the Milky Way").ref, "milkyway")
        self.assertEqual(self.cat.place("mars@77.45,18.44").ref, "mars@77.45,18.44")
        self.assertEqual(self.cat.place("jezero").body, "mars")
        with self.assertRaisesRegex(CatalogError, "did you mean 'tranquility base'"):
            self.cat.place("tranquility bas")
        with self.assertRaisesRegex(CatalogError, "longitude,latitude"):
            self.cat.place("moon@north pole")
        self.assertEqual(self.cat.craft_id("Eagle"), "apollo11.lm")
        with self.assertRaisesRegex(CatalogError, "unknown dataset .apollo99."):
            Catalog("apollo99")

    def test_stat_formats(self):
        self.assertEqual(stat_parts("#,##0 KM"), (0, "", "KM"))
        self.assertEqual(stat_parts("0.0 KM/S"), (1, "", "KM/S"))
        self.assertEqual(stat_parts("$#,##0"), (0, "$", ""))


class Errors(unittest.TestCase):
    def base(self, **b1):
        return {"beat": "b1", "row": "beat", "vo_anchor": "In July 1969, three", "mode": "map", "place": "earth", "frame": "body", **b1}

    def problems(self, text, words=WORDS):
        rep = check_csv(text, words)
        self.assertFalse(rep.ok)
        return " | ".join(rep.errors)

    def test_every_problem_names_its_row(self):
        text = csv_of(
            self.base(),
            {"beat": "b1", "row": "layer", "vo_anchor": "three astronauts", "type": "sticker"},
            {"beat": "b1", "row": "clip", "asset": "stock_video:x"},
            {"beat": "b2", "row": "beat", "vo_anchor": "A Saturn V rocket", "mode": "footage"},
            {"beat": "b3", "row": "beat", "vo_anchor": "Within twelve minutes Apollo", "mode": "map", "place": "earth", "frame": "huge"},
            {"beat": "b4", "row": "beat", "vo_anchor": "Then the third stage", "mode": "orbit"})
        p = self.problems(text)
        self.assertIn("row 3: layer type must be one of", p)
        self.assertIn("row 4: clips belong to footage beats", p)
        self.assertIn("row 6: frame must be one of", p)
        self.assertIn("row 7: mode must be one of", p)

    def test_words_the_narrator_never_says(self):
        p = self.problems(csv_of(self.base(), {"beat": "b2", "row": "beat", "vo_anchor": "and then the aliens came", "mode": "footage"},
                                 {"beat": "b2", "row": "clip", "asset": "file:x.jpg"}))
        self.assertIn("row 3: vo_anchor 'and then the aliens came' is not in the narration", p)

    def test_unknown_places_events_and_craft(self):
        p = self.problems(csv_of(dict(self.base(), place="tranquility bas", date="landng"),
                                 {"beat": "b1", "row": "layer", "vo_anchor": "three astronauts", "type": "craft", "id": "saturn"}))
        self.assertIn("unknown place 'tranquility bas'", p)

    def test_unknown_event_and_craft_in_a_valid_beat(self):
        text = csv_of({"beat": "plan", "row": "plan", "id": "apollo11"}, dict(self.base(), date="landng"),
                      {"beat": "b1", "row": "layer", "vo_anchor": "three astronauts", "type": "craft", "id": "saturn"})
        p = self.problems(text)
        self.assertIn("row 4: unknown craft 'saturn'", p)
        self.assertIn("row 3: unknown date 'landng'", p)

    def test_a_footage_beat_needs_clips_and_a_card_beat_needs_cards(self):
        p = self.problems(csv_of(self.base(mode="map_footage"), {"beat": "b2", "row": "beat", "vo_anchor": "A Saturn V rocket", "mode": "footage"}))
        self.assertIn("map_footage beat b1 has no card rows", p)
        self.assertIn("footage beat b2 has no clip rows", p)

    def test_not_a_starmap_csv(self):
        self.assertFalse(is_starmap_csv("beat,row,vo_anchor,mode,type,id,place,frame,label\n"))   # Hybrid's beat CSV
        self.assertTrue(is_starmap_csv(HEAD + "\n"))
        with self.assertRaises(PlanError):
            read_plan("a,b,c\n1,2,3\n")


class Timing(unittest.TestCase):
    def test_rows_spoken_outside_their_beat_join_the_beat(self):
        text = csv_of({"beat": "b1", "row": "beat", "vo_anchor": "In July 1969, three", "mode": "map", "place": "earth", "frame": "body"},
                      {"beat": "b1", "row": "layer", "vo_anchor": "Apollo 11 was circling", "type": "caption", "text": "EARLY"},
                      {"beat": "b2", "row": "beat", "vo_anchor": "A Saturn V rocket", "mode": "footage"},
                      {"beat": "b2", "row": "clip", "asset": "file:x.jpg"})
        plan = read_plan(text, WORDS)
        self.assertEqual(plan.beats[0].layers[0].t, 0.0)
        self.assertTrue(any("outside beat b1" in n for n in plan.notes))

    def test_dates_fast_forward_between_neighbours_and_jump_under_footage(self):
        rep = check_csv(SAMPLE, WORDS, media=MEDIA)
        plan, keys = rep.plan, rep.compiled.spec["clock"]["keys"]
        b = {x.id: x for x in plan.beats}
        # b1 (launch-00:05) is followed by footage: it holds in real time until the footage, the jump happens under it
        self.assertEqual(keys[0], {"t": 0.0, "utc": "1969-07-16T13:27:00Z"})
        self.assertEqual(keys[1]["t"], round(b["b2"].start, 3))
        self.assertEqual(keys[1]["utc"][:16], "1969-07-16T13:27")
        # b3 -> b4 -> b5 are neighbours: the clock runs from one event to the next across them
        self.assertEqual([k["utc"] for k in keys[2:5]], ["1969-07-16T13:43:49Z", "1969-07-16T16:16:16Z", "1969-07-19T17:21:50Z"])

    def test_camera_glides_only_when_the_view_changes(self):
        """Beat views in order (follow shots of a beat's visual action ride along a craft between them); b7 keeps b6's view."""
        spec = check_csv(SAMPLE, WORDS, media=MEDIA).compiled.spec
        moves = [m for m in spec["camera"]["moves"] if not m["to"].get("follow")]
        seen = [spec["camera"]["start"]["target"]] + [m["to"]["target"] for m in moves]
        targets = [x for k, x in enumerate(seen) if k and x != seen[k - 1]]     # the views it glides to (creeping in keeps the view)
        self.assertEqual(spec["camera"]["start"]["target"], "earth@-80.604,28.608")
        self.assertEqual([t for t in targets if "@" not in t or t == "moon@23.473,0.674"], ["earth", "earth+moon", "moon", "moon@23.473,0.674"])
        follows = [m for m in spec["camera"]["moves"] if m["to"].get("follow")]
        self.assertTrue(follows and all(m["to"]["follow"]["trajectory"].startswith("apollo11_") for m in follows), "the camera follows the craft")
        orbit = next(m for m in moves if m["to"]["target"] == "moon")
        self.assertGreaterEqual(orbit["to"]["el_deg"], 45, "an orbit beat looks down on the orbit")

    def test_the_camera_never_sits_still_through_a_beat(self):
        """A beat with no move of its own creeps in slowly (a held camera reads as stuck), the same view again included."""
        spec = check_csv(SAMPLE, WORDS, media=MEDIA).compiled.spec
        moves = sorted(spec["camera"]["moves"], key=lambda m: m["t"])
        busy = [(m["t"], m["t"] + m["dur"]) for m in moves]
        footage = [(f["start"], f["end"]) for f in spec["footage"]]
        t, still = 0.0, 0.0
        while t < spec["duration"]:
            if not any(a <= t < b for a, b in busy + footage):
                still += 0.1
            t += 0.1
        self.assertLess(still, 0.15 * spec["duration"], "the camera is moving (or under footage) most of the time")

    def test_media_to_find_is_listed_not_fatal_in_check(self):
        rep = check_csv(SAMPLE, WORDS)
        self.assertTrue(rep.ok)
        self.assertEqual(len(rep.to_find), 3)
        self.assertIn("OK once the pictures and clips are found", rep.to_text())

    def test_compiled_spec_is_clean_for_the_engine(self):
        plan = read_plan(SAMPLE, WORDS)
        spec = strip_private(compile_plan(plan, Catalog("apollo11"), media=MEDIA, watermark={"text": "My Channel"}).spec)
        self.assertFalse(any("_row" in L for L in spec["layers"]))
        self.assertEqual(spec["watermark"], {"text": "My Channel"})
        crafts = [L["id"] for L in spec["layers"] if L["type"] == "spacecraft"]
        self.assertEqual(crafts, ["apollo11.csm", "apollo11.csm~2", "apollo11.csm~3", "apollo11.lm"], "each appearance of a craft is its own layer")
        dist = next(L for L in spec["layers"] if L["type"] == "distance")
        self.assertEqual(dist["between"], ["earth", "apollo11.csm~2"], "the craft on screen at that moment")


if __name__ == "__main__":
    unittest.main()


class LinesRingsAndTheUniverse(unittest.TestCase):
    """Lines that show a number's meaning, scale rings, pointers, the universe frame and the galaxy landmarks."""

    ROWS = [
        dict(beat="b1", row="beat", start="0", mode="map", place="earth+moon", frame="system"),
        dict(beat="b1", row="layer", t="1", type="distance", place="earth;moon", sub="EARTH TO MOON"),
        dict(beat="b1", row="layer", t="1", type="line", id="light", place="moon;earth", label="1.3 light-seconds"),
        dict(beat="b2", row="beat", start="6", mode="map", place="sun", frame="solar"),
        dict(beat="b2", row="layer", t="6.5", type="rings", place="sun", text="1 light-hour; 1 light-year=ONE LIGHT-YEAR", until="b3"),
        dict(beat="b3", row="beat", start="12", mode="map", place="milky way", frame="galaxy"),
        dict(beat="b3", row="layer", t="12.5", type="line", id="measure", place="milky way", label="100000 light-years"),
        dict(beat="b4", row="beat", start="18", mode="map", place="sun", frame="universe"),
        dict(beat="b4", row="layer", t="18.5", type="pointer", place="sun"),
        dict(beat="b5", row="beat", start="24", mode="map", place="sun+alpha centauri", frame="system", extra='{"fit": 2.4}'),
    ]

    @classmethod
    def csv_text(cls, rows):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    def compile(self):
        plan = read_plan(self.csv_text(self.ROWS), duration=30)
        return strip_private(compile_plan(plan, Catalog("apollo11")).spec)

    def test_rows_become_engine_layers(self):
        spec = self.compile()
        links = [L for L in spec["layers"] if L["type"] == "link"]
        light = next(L for L in links if L["style"] == "light")
        self.assertEqual((light["between"], light["label"]), (["moon", "earth"], "1.3 LIGHT-SECONDS"))
        self.assertEqual(next(L for L in links if L["style"] == "measure" and "across" in L)["across"], "milkyway")
        # the distance's own measuring line steps aside: a light line already joins the Earth and the Moon then
        self.assertFalse([L for L in links if L.get("between") and set(L["between"]) == {"earth", "moon"} and L["style"] == "measure"])
        rings = next(L for L in spec["layers"] if L["type"] == "rings")
        self.assertEqual(rings["around"], "sun")
        self.assertEqual([r["label"] for r in rings["rings"]], ["1 LIGHT-HOUR", "ONE LIGHT-YEAR"])
        self.assertAlmostEqual(rings["rings"][0]["radius"]["km"], 3600 * 299792.458)
        self.assertEqual(rings["rings"][1]["radius"], {"ly": 1.0})
        self.assertEqual(next(L for L in spec["layers"] if L["type"] == "pointer")["label"], "YOU ARE HERE")
        self.assertIn("galaxy_guide", [L["type"] for L in spec["layers"]])

    def test_the_universe_frame_and_a_wider_pair(self):
        spec = self.compile()
        shots = {m["to"]["target"]: m["to"] for m in spec["camera"]["moves"]}
        self.assertGreater(shots["sun"]["distance"].get("ly", 0), 1e10, "the universe frame sees the observable universe whole")
        self.assertEqual(shots["sun+alphacentauri"]["fit"], 2.4)

    def test_a_distance_alone_draws_its_measuring_line(self):
        plan = read_plan(self.csv_text(self.ROWS[:2]), duration=6)
        links = [L for L in compile_plan(plan, Catalog("apollo11")).spec["layers"] if L["type"] == "link"]
        self.assertEqual([(L["style"], L["between"]) for L in links], [("measure", ["earth", "moon"])])

    def test_ring_sizes(self):
        from starmap.compile import ring_radius

        self.assertEqual(ring_radius("13 billion light-years"), {"ly": 13e9})
        self.assertEqual(ring_radius("100 AU"), {"au": 100})
        self.assertAlmostEqual(ring_radius("8 light-minutes")["km"], 8 * 60 * 299792.458)
        with self.assertRaises(CatalogError):
            ring_radius("far away")
