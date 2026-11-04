"""UI product film (`#pace,ui`): blocks alternate light / dark and join with dissolves, the interface comes from the feature rows (any product, any words),
a list feature gets a scripted cursor, a lock / widget / app feature explodes into 3D layers, the film opens on the phone wall and an `icon:` look adds an
icon-construction block. Synthetic CSVs, no music, no network."""
import json
import tempfile
import unittest
from pathlib import Path

from product_trailer import build_spec
from product_trailer.uifilm import film_length, ui_for_feature

CSV = """#product: Nova X1
#colors,Titanium Blue,Silver
#pace,ui
#disclaimer: Concept film for testing.
order,feature,kicker,value,sub,look
1,control center,Redesigned,Quick Controls,"Wi-Fi, Bluetooth, Focus mode, Battery",
2,lock screen,The new,Lock Screen,Live widgets on the glass,
3,apps,Smarter,Home Screen,"Phone, Messages, Camera",icon:camera
4,battery,All-day,Battery,,rows:Low_Power|Optimised_Charging block:light
"""


def plan(text: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.csv"
        p.write_text(text, encoding="utf-8")
        return json.loads(Path(build_spec(p, out_dir=d)).read_text(encoding="utf-8"))


class UiFilm(unittest.TestCase):
    def setUp(self):
        self.spec = plan(CSV)
        self.shots = self.spec["shots"]

    def test_blocks_are_contiguous_and_the_length_is_the_block_sum(self):
        self.assertEqual(self.shots[0]["start"], 0.0)
        for a, b in zip(self.shots, self.shots[1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=3)
            self.assertGreater(b["end"], b["start"])
        self.assertAlmostEqual(self.spec["duration"], self.shots[-1]["end"], places=3)
        self.assertGreaterEqual(self.spec["duration"], 30)

    def test_sets_alternate_and_every_join_dissolves(self):
        sets = ["light" if s.get("backdrop") == "daylight" or s.get("tint") == "paper" else "dark" for s in self.shots if s["kind"] != "black"]
        self.assertGreaterEqual(sum(a != b for a, b in zip(sets, sets[1:])), 3, sets)
        for s in self.shots[1:]:
            self.assertGreater(s.get("dissolve_in", 0), 0)
        self.assertIn("blur", {s.get("dissolve_style") for s in self.shots})

    def test_the_opening_wall_and_the_icon_block(self):
        self.assertIn("wall", self.shots[0])
        self.assertTrue(any(L["type"] == "pt_iconbuild" and L["icon"] == "camera" for L in self.spec["layers"]))

    def test_demo_and_exploded_interfaces(self):
        demo = [s for s in self.shots if s.get("ui_style") == "demo"]
        exploded = [s for s in self.shots if s.get("layers3d")]
        self.assertTrue(demo and exploded)
        script = demo[0]["screen"]["ui"]["script"]
        self.assertTrue(script and all(0 < x["at"] < demo[0]["end"] - demo[0]["start"] for x in script))
        for s in demo + exploded:
            self.assertEqual(s["move"], "demo")
            self.assertLess(s["cam"]["z1"], s["cam"]["z0"])                 # the camera really dollies in

    def test_titles_type_on_every_block_and_look_tokens_win(self):
        words = [L for L in self.spec["layers"] if L["type"] == "pt_words"]
        self.assertGreaterEqual(len(words), 5)
        batt = next(s for s in self.shots if s.get("screen", {}).get("ui", {}).get("components", [{}])[0].get("text") == "Battery")
        rows = [r["label"] for r in batt["screen"]["ui"]["components"][1]["rows"]]
        self.assertEqual(rows, ["Low Power", "Optimised Charging"])
        self.assertEqual(batt["backdrop"], "daylight")

    def test_any_product_and_unknown_words_still_get_an_interface(self):
        ui, cat = ui_for_feature({"feature": "telepathy", "kicker": "", "value": "Mind Link", "sub": "", "look": ""}, accent="#123456")
        self.assertEqual(cat, "list")
        self.assertTrue(ui["components"] and ui["components"][1]["rows"])
        other = plan("#product: Pixel Fold Z\n#pace,ui\norder,feature,kicker,value,sub,look\n1,widgets,,Glance,Weather and calendar,\n")
        self.assertEqual(other["whatif"]["title"], "Pixel Fold Z")
        self.assertTrue(any(s.get("layers3d") for s in other["shots"]))

    def test_no_music_length_matches_the_plan(self):
        from product_trailer.csv_io import parse_csv_text

        self.assertAlmostEqual(film_length(parse_csv_text(CSV)), self.spec["duration"], places=2)


class AppPath(unittest.TestCase):
    def test_the_ui_film_type_reaches_the_ui_planner(self):
        from product_trailer import studio

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.csv"
            p.write_text(CSV.replace("#pace,ui\n", ""), encoding="utf-8")         # the app's type picks the pace, not the CSV
            r = studio.plan_film("UI Film", out_dir=d, csv=str(p), use_ai=True)
            spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
        self.assertEqual(spec["product_trailer"]["pace"], "ui")
        self.assertTrue(any(s.get("wall") for s in spec["shots"]))


NARRATION = ["Meet the Nova X1, a phone that feels brand new from the moment you pick it up.",
             "The redesigned Quick Controls put Wi-Fi, Bluetooth and Battery one tap away from anywhere.",
             "Then there is the new Lock Screen with live widgets and notifications right on the glass.",
             "And the smarter Home Screen keeps your favourite apps exactly where your thumb lands.",
             "This is the Nova X1, available this autumn in two finishes."]


def voice(lines, wps=2.6, pause=0.7):
    """Synthetic narrator word times: (word, start, end), a pause between sentences."""
    out, t = [], 0.3
    for ln in lines:
        for w in ln.split():
            out.append((w, round(t, 3), round(t + 0.8 / wps, 3)))
            t += 1 / wps
        t += pause
    return out, t + 0.3


class NarrationTimed(unittest.TestCase):
    def setUp(self):
        from product_trailer.csv_io import parse_csv_text
        from product_trailer.uifilm import plan_ui_timed

        self.words, self.dur = voice(NARRATION)
        self.spec = plan_ui_timed(parse_csv_text(CSV), self.words, self.dur)
        self.starts = {}
        W = self.words
        for i, ln in enumerate(NARRATION):
            first = ln.split()[0]
            self.starts[i] = next(t for w, t, _ in W[sum(len(x.split()) for x in NARRATION[:i]):] if w == first)

    def test_each_feature_block_starts_when_its_feature_is_said(self):
        demo = [s for s in self.spec["shots"] if s.get("ui_style")]
        self.assertGreaterEqual(len(demo), 3)
        for s, i in zip(demo, (1, 2, 3)):                # Quick Controls on sentence 2, Lock Screen on 3, Home Screen on 4
            self.assertLess(abs(s["start"] - self.starts[i]), 0.8, (s["id"], s["start"], self.starts[i]))
        self.assertEqual(self.spec["shots"][0].get("wall") is not None, True)          # the opening sentence plays over the wall
        self.assertEqual(self.spec["shots"][-2]["move"], "reveal")                      # the last sentence is the reveal (the card follows)

    def test_joins_sit_in_pauses_and_the_film_lasts_as_long_as_the_voice(self):
        for s in self.spec["shots"][1:]:
            inside = [w for w in self.words if w[1] < s["start"] < w[2]]
            self.assertFalse(inside, f"{s['id']} starts in the middle of the word {inside}")
        self.assertAlmostEqual(self.spec["shots"][-2]["end"], self.dur, places=2)

    def test_spoken_titles_and_named_rows_follow_the_voice(self):
        L = next(L for L in self.spec["layers"] if L["type"] == "pt_words" and L["text"] == "The new Lock Screen")
        self.assertEqual(len(L["times"]), 4)                                           # "The new Lock Screen" is said word for word
        self.assertTrue(all(b > a for a, b in zip(L["times"], L["times"][1:])))
        demo = next(s for s in self.spec["shots"] if s.get("ui_style") == "demo")
        taps = demo["screen"]["ui"]["script"]
        wifi = next(t for w, t, _ in self.words if w == "Wi-Fi,")
        self.assertTrue(any(abs(demo["start"] + x["at"] - wifi) < 0.4 for x in taps), taps)

    def test_the_app_routes_a_voiced_ui_film_to_the_timed_plan(self):
        from product_trailer import studio

        with tempfile.TemporaryDirectory() as d:
            p, v = Path(d) / "f.csv", Path(d) / "voice.wav"
            p.write_text(CSV, encoding="utf-8")
            v.write_bytes(b"RIFF")                                                     # only has to exist: its length is given
            r = studio.plan_film("UI Film", out_dir=d, csv=str(p), voiceover=str(v), words=self.words, voice_seconds=self.dur)
            spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
        self.assertTrue(spec["product_trailer"]["voiceover_timed"])
        self.assertEqual(spec["product_trailer"]["voiceover"], str(v))


class ReviewMix(unittest.TestCase):
    def test_software_sentences_get_interface_scenes(self):
        from product_trailer import director

        ui = director.scene_for("The new control center has Wi-Fi, Bluetooth and Focus mode toggles.", "Nova X1")
        self.assertEqual((ui["kind"], ui["rows"]), ("ui", ["Wi-Fi", "Bluetooth", "Focus mode"]))
        self.assertEqual(director.scene_for("Every app icon was redesigned.", "Nova X1")["kind"], "icon")
        self.assertEqual(director.scene_for("You can customise the wallpapers.", "Nova X1")["kind"], "wall")
        self.assertEqual(director.scene_for("The screen is brighter than before.", "Nova X1")["kind"], "macro")   # hardware keeps its 3D macro

    def test_a_timed_review_mixes_the_interface_beats_on_their_lines(self):
        from product_trailer import director, review, voiceover as vo

        script = "\n".join(["## Software"] + NARRATION[1:4] + ["## Camera", "The camera has a 200MP main sensor.", "[icon: camera | New Camera App]",
                                                                "The camera app was rebuilt from scratch."])
        parsed = director.auto_direct(review.parse_script(script), "Nova X1")
        lines = [it["text"] for ch in parsed["chapters"] for it in ch["items"] if it["kind"] == "line"]
        words, dur = voice(lines)
        pack = {"phone": "nova x1", "colours": ["Silver"], "scenes": []}
        spec = review.plan_review_timed(parsed, pack, {}, vo.align_lines(lines, words, dur), words)
        kinds = [s.get("ui_style") or s.get("tint") or s.get("object") or s["kind"] for s in spec["shots"]]
        self.assertIn("demo", kinds)
        self.assertIn("exploded", kinds)
        self.assertTrue(any(L["type"] == "pt_iconbuild" for L in spec["layers"]))
        self.assertTrue(any(L["type"] == "pt_subtitle" for L in spec["layers"]))          # the review keeps its subtitles and chapter cards
        self.assertTrue(any(L["type"] == "tm_title" for L in spec["layers"]))
        span = vo.align_lines(lines, words, dur)["spans"]
        lock = next(s for s in spec["shots"] if s.get("ui_style") == "exploded")
        self.assertLess(abs(lock["start"] - span[1][0]), 0.05)                               # the lock-screen beat starts on its sentence
        self.assertTrue(all(s.get("dissolve_in") for s in spec["shots"] if s.get("ui_style")))


if __name__ == "__main__":
    unittest.main()
