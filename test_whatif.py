"""What If: the narration reader, the shot planner, the shot CSV, the spec compiler and the renderer's shot model."""
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

from whatif import compile as wc
from whatif import narration as nr
from whatif import planner
from whatif.shot_csv import PlanError, craft_model, read_shots, world_texture

ROOT = Path(__file__).resolve().parent


def timed(text, t=0.0, step=0.35):
    out = []
    for w in text.split():
        out.append((w, t, t + 0.3))
        t += step + (0.5 if w[-1] in ".?!," else 0.0)
    return out


class Narration(unittest.TestCase):
    def metrics(self, text):
        return nr.extract_metrics(nr.words_of(timed(text)))

    def test_numbers_units_and_words(self):
        m = self.metrics("The ground is 464 degrees Celsius, hot enough to melt lead.")
        self.assertEqual((m[0].kind, m[0].label), ("temperature", "464 °C"))
        m = self.metrics("Light takes eight minutes and twenty seconds to reach us from the Sun.")
        self.assertEqual(m[0].label, "8 MIN 20 S")
        m = self.metrics("It is 96.5% carbon dioxide.")
        self.assertEqual((m[0].kind, m[0].shown), ("percent", "96.5"))
        m = self.metrics("The air presses down about 90 times harder than on Earth.")
        self.assertEqual((m[0].kind, m[0].value), ("ratio", 90.0))

    def test_script_alignment_restores_decimals(self):
        # the app's transcript spells 4.2 as "4" "2" and drops the percent sign: the script's own form is put back
        raw = [("the", 0, .2), ("nearest", .2, .5), ("star", .5, .8), ("is", .8, 1), ("4", 1.0, 1.3), ("2", 1.3, 1.6), ("light", 1.7, 2), ("years", 2, 2.3), ("away", 2.3, 2.6)]
        words = nr.words_of(raw, "The nearest star is 4.2 light-years away.")
        self.assertIn("4.2", [w.text for w in words])
        m = nr.extract_metrics(words)
        self.assertEqual(m[0].label, "4.2 LIGHT-YEARS")

    def test_find_anchor(self):
        words = nr.words_of(timed("it is also 96.5 percent carbon dioxide"), "It is also 96.5 percent carbon dioxide")
        self.assertIsNotNone(nr.find_anchor(words, "also 96.5 percent", 0, 20))


class OpeningAndFlow(unittest.TestCase):
    """The first 20 s cut like the references (no shot over 5.5 s), and the Flow switch's three modes."""

    def plan(self, mode):
        script = ("The nearest star system to our sun is Alpha Centauri and its distance sounds almost harmless and quiet and small to us. "
                  "But a light-year is not a small step at all, it is an enormous gulf of empty dark space between the stars that surround us. "
                  "Light itself needs years to cross it and nothing we have ever built comes close to that kind of speed in any way.")
        raw = timed(script)
        csv_text = ("row,shot,vo_anchor,kind,asset,label\n"
                    "shot,1,The nearest star,image,nasa_image:Hubble image of Alpha Centauri A and B,ALPHA CENTAURI\n"
                    "shot,2,But a light-year,image,flow_image:a vast dark gulf between stars,\n"
                    "shot,3,Light itself needs,image,flow_image:a beam of light crossing space,\n")
        from whatif.app_integration import plan_from
        return plan_from(raw, script, raw[-1][2] + 0.4, "t", csv_text, flow_video=mode)

    def test_no_opening_shot_is_long_and_its_photo_fills_the_frame(self):
        p = self.plan("both")
        opening = [s for s in p.shots if s.start < planner.HOOK_S]
        self.assertTrue(all(s.length <= planner.HOOK_MAX_S + 0.01 for s in opening), [(s.id, round(s.length, 1)) for s in opening])
        self.assertIn(p.shots[0].kind, planner.MOVING, "the video opens on motion")
        photo = next(s for s in p.shots if s.cite[0] == "REAL IMAGE")
        self.assertTrue(photo.extra.get("full_bleed") and photo.start < planner.HOOK_S, "the photograph follows, filling the frame")
        self.assertNotIn("compose", [d for d in wc.compile_spec(p)["shots"] if d["id"] == photo.id][0])
        self.assertNotIn("landscape", p.shots[0].asset, "a star is drawn in space, not as a hazy landscape")

    def test_the_three_flow_modes(self):
        count = lambda p, src: sum(1 for s in p.shots if s.asset.startswith(src))  # noqa: E731
        images, both, videos = self.plan("images"), self.plan("both"), self.plan("videos")
        self.assertEqual(count(videos, "flow_image:"), 0)
        self.assertGreater(count(both, "flow_video:"), count(images, "flow_video:"))
        self.assertTrue(all(s.kind == "video" for s in both.shots if s.asset.startswith("flow_video:")))
        self.assertEqual(planner.flow_mode(True), "videos")
        self.assertEqual(planner.flow_mode(False), "images")

    def test_a_plate_with_nothing_drawn_on_it_never_reaches_the_screen(self):
        script = ("The Moon is about 384,000 kilometers away from us here. That is about as far as any human has ever traveled in all of history. "
                  "Beyond that point everything else is still waiting for us out there in the deep and silent dark of space today.")
        raw = timed(script)
        csv_text = ("row,shot,vo_anchor,kind,asset,texture,label,type,sub\n"
                    "shot,1,The Moon is,globe,,moon,THE MOON,,\n"
                    "shot,2,That is about,plate,,,,,\n"
                    "layer,2,That is about,,,,FARTHEST ANY HUMAN HAS TRAVELED,caption,~400000 KM\n"
                    "shot,3,Beyond that point,plate,,,,,\n")
        from whatif.app_integration import plan_from
        p = plan_from(raw, script, raw[-1][2] + 0.4, "t", csv_text, flow_video="both")
        axes = [L for L in p.layers if L["type"] == "tm_logaxis"]
        plates = [s for s in p.shots if s.kind == "plate"]
        self.assertTrue(axes and any(abs(m["v"] - 384000 / planner.LIGHT_KM_S) < 0.01 for m in axes[0]["marks"]), "the distance plate draws the scale")
        for s in plates:
            self.assertTrue(any(L["type"] in planner.DIAGRAMS and L["start"] <= s.start + 0.5 and s.end - 0.5 <= L["end"] for L in p.layers) or s.title,
                            f"{s.id} is an empty plate")

    def test_no_flow_video_shot_is_six_seconds_or_longer(self):
        script = ("Earth is our home and it has been for a very long time, a small blue world in the dark. " * 4 +
                  "The probe drifted past the giant planet for a very long time, slowly turning its camera towards the rings. "
                  "Then it kept falling away into the dark between the worlds, further than anything we had sent before.")
        raw = timed(script)
        csv_text = ("row,shot,vo_anchor,kind,asset,texture\n"
                    "shot,0,Earth is our,globe,,earth\n"
                    "shot,1,The probe drifted,video,flow_video:a probe drifting past a giant ringed planet,\n"
                    "shot,2,Then it kept,video,flow_video:a probe falling away into dark space,\n")
        from whatif.app_integration import plan_from
        p = plan_from(raw, script, raw[-1][2] + 0.4, "t", csv_text, flow_video="images")
        self.assertGreater(min(s.start for s in p.shots if s.asset.startswith("flow_video:")), planner.HOOK_S)
        clips = [s for s in p.shots if s.asset.startswith("flow_video:")]
        self.assertGreater(len(clips), 2, "the long clips were split")
        self.assertTrue(all(s.length <= planner.FLOW_VIDEO_MAX_S + 1e-6 for s in clips), [(s.id, round(s.length, 2)) for s in clips])
        self.assertEqual(len({s.asset for s in clips}), len(clips), "each clip of the same subject is framed differently")

    def test_the_visual_plan_lists_every_flow_choice_with_its_length(self):
        from whatif.app_integration import visual_dicts
        p = self.plan("both")
        rows = visual_dicts(p)
        flow = [s for s in p.shots if s.asset.startswith(("flow_image:", "flow_video:"))]
        self.assertEqual(sum(1 for r in rows if r["asset_type"] in ("flow_image", "flow_video")), len(flow))
        self.assertTrue(all(re.search(r"What If shot s\d+ · \d+\.\d s", r["script_segment"]) for r in rows), rows[0])

    def test_a_csv_distance_scale_takes_plain_distances(self):
        from whatif.narration import _light_s
        self.assertAlmostEqual(_light_s("400,000 km"), 1.334, places=2)
        self.assertAlmostEqual(_light_s("1 AU"), 499.0)
        self.assertAlmostEqual(_light_s("8 light-minutes"), 480.0)
        self.assertAlmostEqual(_light_s("9.5 trillion km") / 31557600, 1.0, places=1)

    def test_the_csv_prompt_asks_for_a_moving_opening_full_plates_and_number_free_anchors(self):
        prompt = (Path(__file__).parent / "composition_styles" / "whatif_csv_prompt.txt").read_text(encoding="utf-8")
        for must in ("Shot 1 MOVES", "MUST have a diagram", "WITHOUT a number", "flow_video:<a precise visual description", "UNDER 6 SECONDS"):
            self.assertIn(must, prompt)

    def test_a_spoken_number_the_transcript_cut_in_two_is_one_number(self):
        raw = [("about", 0.0, 0.3), ("4", 0.4, 0.6), ("37", 0.6, 0.9), ("light", 0.9, 1.1), ("years", 1.1, 1.4), ("and", 2.0, 2.2),
               ("384", 2.3, 2.6), ("0", 2.6, 2.9), ("kilometers", 2.9, 3.4), ("or", 4.0, 4.2), ("6", 4.3, 4.5), ("800", 4.5, 4.8), ("years", 4.8, 5.1)]
        shown = [m.shown for m in nr.extract_metrics(nr.words_of(raw, "about four point three seven light years and 384,000 kilometers or 6,800 years"))]
        self.assertEqual(shown, ["4.37", "384,000", "6,800"])


class Planner(unittest.TestCase):
    SCRIPT = ("On the first of March 1982, a Soviet lander called Venera 13 touched down on Venus. Two hours and seven minutes later, it went silent. "
              "So how long could you survive there? The ground is 464 degrees Celsius, hot enough to melt lead. And the air presses down about 90 times "
              "harder than on Earth. Unprotected, you would die in seconds, and no one could survive that. At 55 kilometres up, it is 27 degrees, like a summer day. Voyager 1 is 25 billion kilometres from home. "
              "Light from the Sun takes eight minutes and twenty seconds to reach us. If you could live in the clouds of Venus, would you? Tell me in the comments.")

    def setUp(self):
        self.raw = timed(self.SCRIPT)
        self.dur = self.raw[-1][2] + 0.5
        self.plan = planner.plan(self.raw, self.SCRIPT, self.dur, "How Long Could You Survive on Venus?")

    def test_shots_cover_the_video_in_order(self):
        s = self.plan.shots
        self.assertEqual(s[0].start, 0.0)
        self.assertAlmostEqual(s[-1].end, self.dur, places=2)
        for a, b in zip(s, s[1:]):
            self.assertAlmostEqual(a.end, b.start, places=3)
        self.assertTrue(all(x.length >= 2.4 for x in s), [x.length for x in s])

    def test_pacing_is_the_references(self):
        # reference_targets.json: median hard shot 6-10 s, 4.6-7.5 cuts per minute
        r = planner.report(self.plan)
        self.assertGreaterEqual(r["median_shot_s"], 4.0)
        self.assertLessEqual(r["median_shot_s"], 11.0)

    def test_a_named_craft_is_that_craft_never_generic(self):
        voy = [s for s in self.plan.shots if "voyager" in s.text.lower()]
        self.assertTrue(voy and all(s.kind == "craft" and s.model == "voyager.glb" for s in voy))

    def test_ratio_and_light_time_become_diagrams(self):
        kinds = [L["type"] for L in self.plan.layers]
        self.assertTrue(any(s.kind == "plate" for s in self.plan.shots))
        self.assertTrue("tm_compare" in kinds or "tm_logaxis" in kinds)

    def test_spoken_numbers_appear_before_they_are_heard(self):
        words = {w.text: w.start for w in self.plan.words}
        for L in self.plan.layers:
            if L["type"] == "tm_metric" and L["value"].strip("≈ ").replace(",", "") == "464":
                self.assertLessEqual(L["start"], words["464"] + 1e-6)
                self.assertGreater(L["start"], words["464"] - 0.5)

    def test_cuts_follow_the_references_pause_policy(self):
        # measured on the references: 65-82 % of cuts land in a pause, 18-35 % inside speech (docs/whatif/reference_spec.md)
        sent = ("The probe fell through the thick orange clouds and the air pressed down on it with a weight that no machine had ever felt before, "
                "and every second the temperature rose a little more as it dropped towards the ground below.")
        script = " ".join([sent] * 14)
        raw = timed(script)
        # the planner's own cut rhythm (Flow images): this text pauses only every ~15 s, so 6 s Flow clips would have to cut in speech
        plan = planner.plan(raw, script, raw[-1][2] + 0.4, "", flow_video="images")
        r = planner.report(plan)
        self.assertGreaterEqual(len(plan.shots), 14)
        self.assertGreaterEqual(r["cuts_inside_speech_share"], 0.1)
        self.assertLessEqual(r["cuts_inside_speech_share"], 0.4)

    def test_mid_speech_cuts_land_on_content_words_never_on_a_stray_function_word(self):
        sent = "The probe fell through the thick orange clouds and the air pressed down on it with a weight no machine had ever felt."
        raw = timed(" ".join([sent] * 10))
        words = nr.words_of(raw)
        for t in planner._mid_candidates(words):
            w = next(x for x in words if abs(x.start - 0.04 - t) < 1e-6)
            self.assertNotIn(w.norm, nr.FILLER)

    def test_venera_gets_the_composed_hero_scene_not_a_generic_picture(self):
        f = planner.classify("Venera 13 touched down on the surface and the lander was hot")
        self.assertEqual((f["kind"], f["scene"]), ("hero", "venera_ground"))
        f = planner.classify("Venera 13 dropped under its parachute through the clouds")
        self.assertEqual(f["scene"], "venera_descent")
        self.assertEqual(planner.classify("Venera 13 sent home the first colour photographs")["kind"], "image")

    def test_survival_clock_opens_as_its_own_scene_then_moves_to_the_corner(self):
        sv = [L for L in self.plan.layers if L["type"] == "tm_survival"]
        self.assertTrue(sv and sv[0].get("intro"), "the card has an intro window")
        plates = [x for x in self.plan.shots if x.kind == "plate" and x.extra.get("lockup")]
        self.assertTrue(plates, "the intro is a plate shot that keeps the instruments on")
        self.assertAlmostEqual(plates[0].start, sv[0]["intro"]["start"], places=1)

    def test_survival_act_pinned(self):
        self.assertTrue(any(L["type"] == "tm_survival" for L in self.plan.layers))

    def test_no_subject_repeats_the_same_way_within_90s(self):
        seen = {}
        for s in self.plan.shots:
            key = s.model or s.texture
            if key:
                sig = (key, json.dumps(s.cam, sort_keys=True))
                for p, t in seen.get(key, []):
                    if s.start - t < planner.NO_REPEAT_S:
                        self.assertNotEqual(sig, p)
                seen.setdefault(key, []).append((sig, s.end))


class ShotCsv(unittest.TestCase):
    def test_library_names(self):
        self.assertEqual(craft_model("voyager"), "voyager.glb")
        self.assertEqual(world_texture("venus")[0], "2k_venus_atmosphere.jpg")
        with self.assertRaises(ValueError):
            craft_model("venera")

    def test_sample_csv_loads_as_written(self):
        text = (ROOT / "whatif" / "samples" / "venus_shots.csv").read_text()
        raw = timed((ROOT / "whatif" / "samples" / "venus_script.txt").read_text().replace("\n", " "))
        shots, rows, info, notes = read_shots(text, raw, raw[-1][2])
        self.assertEqual([s.kind for s in shots][:3], ["image", "image", "globe"])
        self.assertEqual(shots[-1].end, raw[-1][2])
        self.assertTrue(rows)

    def test_a_bad_row_is_reported_by_row(self):
        text = "row,shot,vo_anchor,kind,asset,model,texture\nshot,s1,,flying,,,\n"
        with self.assertRaises(PlanError) as cm:
            read_shots(text, [], 10)
        self.assertIn("row 2", cm.exception.problems[0])


class RemainingGaps(unittest.TestCase):
    def test_deep_field_sentence_becomes_the_earth_and_disc_diagram(self):
        script = ("We have talked about the planets for a long time and the sun and the moon and many other things in our own small corner of space. "
                  "Beyond them lie billions of galaxies, so far away that their light will never reach us, however long we wait. "
                  "And that is where the story ends for today.")
        raw = timed(script)
        p = planner.plan(raw, script, raw[-1][2] + 0.4, "")
        plates = [x for x in p.shots if x.kind == "plate" and x.asset.startswith("nasa_image:")]
        self.assertTrue(plates, "a plate that fetches the deep-field photograph")
        self.assertEqual(plates[0].cite, ("DIAGRAM", "GALAXIES: NASA, ESA, CSA, STSCI"))
        disc = [L for L in p.layers if L["type"] == "tm_discmap"]
        self.assertTrue(disc and disc[0]["earth"] == "EARTH")
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            plates[0].file = str(Path(d) / "jwst.jpg")
            Path(plates[0].file).write_bytes(b"")
            spec = wc.compile_spec(p)
        self.assertTrue([L for L in spec["layers"] if L["type"] == "tm_discmap"][0]["image"].endswith("jwst.jpg"))

    def test_discmap_and_annotate_rows_in_a_shot_csv(self):
        import csv
        import io

        from whatif.shot_csv import COLUMNS, layers_from_rows

        def csv_text(rows):
            buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=COLUMNS); w.writeheader()
            for r in rows: w.writerow(r)
            return buf.getvalue()
        raw = timed("The soil probe tested a lens cap and not the ground of Venus at all, as we shall see now in this long sentence about it.")
        text = csv_text([dict(row="plan"), dict(row="shot", shot="s1", vo_anchor="The soil probe", kind="image", asset="nasa_image:Venera 14 panorama", label="VENERA 14"),
                         dict(row="layer", vo_anchor="a lens cap", type="annotate", label="A LENS CAP", sub="EJECTED FROM ITS CAMERA", extra='{"x": 0.73, "y": 0.36}'),
                         dict(row="layer", vo_anchor="Venus at all", type="diagram", id="discmap", label="EARTH", text="nasa_image:JWST deep field")])
        shots, rows, info, notes = read_shots(text, raw, raw[-1][2])
        layers, plates = layers_from_rows(rows, shots, raw, "")
        ann = [L for L in layers if L["type"] == "tm_annotate"][0]
        self.assertEqual((ann["x"], ann["y"], ann["label"]), (0.73, 0.36, "A LENS CAP"))
        self.assertTrue(plates and plates[0].asset == "nasa_image:JWST deep field" and plates[0].cite[0] == "DIAGRAM")
        with self.assertRaises(PlanError) as cm:
            read_shots(csv_text([dict(row="plan"), dict(row="shot", shot="s1", kind="image", asset="nasa_image:x"), dict(row="layer", type="annotate", label="x")]), [], 10)
        self.assertIn("annotate row needs", cm.exception.problems[0])

    def test_light_clock_follows_the_light_times_the_narrator_gives_and_the_years(self):
        script = ("In 1977 you leave Earth aboard Voyager and eleven hours later you are 1.3 light-seconds from home. Jupiter comes in 1979, "
                  "when light needs 37 light-minutes to reach you. By 1980 you are at Saturn, 85 light-minutes away, and in 1990 you are 5 light-hours out.")
        raw = timed(script)
        p = planner.plan(raw, script, raw[-1][2] + 0.4, "")
        clocks = [L for L in p.layers if L["type"] == "tm_clock" and L.get("mode") == "light"]
        self.assertTrue(clocks)
        secs = [k["seconds"] for k in clocks[0]["keys"]]
        self.assertEqual(secs, sorted(secs))
        self.assertGreaterEqual(secs[-1], 3600)
        self.assertIn("1979", [n["text"] for n in clocks[0]["notes"]])
        none = planner.plan(timed("Mars is cold. The air is thin. Rovers drive over rocks."), "Mars is cold. The air is thin. Rovers drive over rocks.", 8, "")
        self.assertFalse([L for L in none.layers if L.get("mode") == "light"])

    def test_gauge_zones_only_from_what_the_narrator_says(self):
        said = ("The probe fell, 55 kilometres up, then at 48 kilometres, then at 30 kilometres above the ground. The acid clouds run from 48 to 70 kilometres. "
                "The haze lies between 30 and 48 kilometres.")
        words = nr.words_of(timed(said))
        zones = nr.gauge_zones(words, nr.sentences(words))
        self.assertEqual([(z["label"], z["from"], z["to"]) for z in zones], [("ACID CLOUDS", 48.0, 70.0), ("HAZE", 30.0, 48.0)])
        silent = nr.words_of(timed("The probe fell, 55 kilometres up, then at 48 kilometres, then at 30 kilometres above the ground."))
        self.assertEqual(nr.gauge_zones(silent, nr.sentences(silent)), [])

    def test_airship_and_drive_ship_are_composed_hero_scenes(self):
        self.assertEqual(planner.classify("A crewed airship could float above the clouds of Venus")["scene"], "cloud_airship")
        self.assertEqual(planner.classify("Your ship keeps accelerating at one g and its engines never stop pushing")["scene"], "ship_engine")
        from whatif.shot_csv import HERO_SCENES
        self.assertIn("ship_engine", HERO_SCENES)


class Compile(unittest.TestCase):
    def test_real_photographs_are_letterboxed_and_cited_like_the_reference(self):
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        s = planner.Shot(id="s1", start=0, end=6, kind="image", asset="nasa_image:Venera 14 panorama", name="VENERA 14", cite=("REAL IMAGE", ""),
                         file=tmp.name, credit="NASA/NSSDCA/COURTESY OF THE USSR")
        plan = planner.ShotPlan(shots=[s], layers=[], duration=6, words=[])
        spec = wc.compile_spec(plan)
        self.assertEqual(spec["shots"][0]["compose"], "letterbox")
        seg = [L for L in spec["layers"] if L["type"] == "tm_cite"][0]["segments"][0]
        self.assertEqual(seg["kind"], "REAL PHOTO")
        self.assertEqual(seg["text"], "VENERA 14 · NASA/NSSDCA/COURTESY OF THE USSR")

    def test_a_picture_gone_from_disk_falls_back_instead_of_stopping_the_video(self):
        import tempfile

        s = planner.Shot(id="s1", start=0, end=6, kind="image", asset="commons_image:Voyager 1 Family Portrait", name="VOYAGER 1",
                         text="Voyager 1 took the family portrait", file="/nonexistent/cleared_cache/p.jpg")
        with tempfile.TemporaryDirectory() as d:
            spec = wc.compile_spec(planner.ShotPlan(shots=[s], layers=[], duration=6, words=[]), media_dir=Path(d) / "media")
        self.assertNotIn(spec["shots"][0]["kind"], ("image", "video"))
        self.assertTrue(any("no longer on disk" in n for n in spec["whatif"]["notes"]))

    def test_two_shots_of_the_same_clip_play_as_one_never_restarting(self):
        """Project #013 5:51: a split shot's halves got the same clip and the second restarted it at frame 0 (a jump back, then the
        move again); a picture's push restarted the same way."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            clip = Path(d) / "a.mp4"
            clip.write_bytes(b"same clip")
            copy_ = Path(d) / "b.mp4"
            copy_.write_bytes(b"same clip")                      # a copy under another number (what the twin reuse makes)
            shots = [planner.Shot(id="s1", start=0, end=2.5, kind="video", file=str(clip), asset="flow_video:x"),
                     planner.Shot(id="s2", start=2.5, end=6.8, kind="video", file=str(copy_), asset="flow_video:x -- medium view")]
            spec = wc.compile_spec(planner.ShotPlan(shots=shots, layers=[], duration=6.8, words=[]), media_dir=Path(d) / "m")
        self.assertEqual([(s["start"], s["end"]) for s in spec["shots"]], [(0, 6.8)])

    def test_hero_shots_reach_the_spec(self):
        s = planner.Shot(id="s1", start=0, end=6, kind="hero", scene="venera_ground", cam={"size": 0.26})
        spec = wc.compile_spec(planner.ShotPlan(shots=[s], layers=[], duration=6, words=[]))
        self.assertEqual((spec["shots"][0]["kind"], spec["shots"][0]["scene"]), ("hero", "venera_ground"))

    def test_missing_pictures_fall_back_meaningfully(self):
        script = "Venus is the hottest planet. The surface is dark and silent for a long time without any change at all."
        raw = timed(script)
        p = planner.plan(raw, script, raw[-1][2] + 0.4, "t")
        spec = wc.compile_spec(p)
        kinds = {s["kind"] for s in spec["shots"]}
        self.assertFalse(kinds & {"image", "video"}, "a shot with no file must not stay an image")
        self.assertTrue(any("could be had" in n for n in spec["whatif"]["notes"]) or kinds <= {"globe", "plate", "craft"})
        self.assertIn("tm_cite", [L["type"] for L in spec["layers"]])


class Media(unittest.TestCase):
    def test_a_nasa_miss_is_never_filled_by_stock_but_by_a_labelled_illustration(self):
        from types import SimpleNamespace

        from whatif import media

        calls = []

        def fake(plan, images_dir, **kw):
            calls.append((kw.get("mission"), [c.asset for b in plan.beats for c in b.clips]))
            media_ = {}
            for b in plan.beats:
                for c in b.clips:
                    if c.asset.startswith("flow_image:"):
                        media_[f"row:{c.row}"] = {"file": f"/x/{c.row}.png", "credit": "AI ILLUSTRATION"}
            return SimpleNamespace(media=media_, unresolved=[], notes=[], credits=[])

        s = planner.Shot(id="s1", start=0, end=6, kind="image", asset="nasa_image:Venera 13 first colour photo", name="VENERA 13", text="Venera 13 sent home the first colour photos")
        media.fetch([s], Path("/tmp/x"), fetcher=fake, log=lambda m: None)
        self.assertTrue(calls[0][0], "the mission is named, so NASA's answer stands (no stock search)")
        self.assertTrue(s.asset.startswith("flow_image:") and s.cite[0] == "AI ILLUSTRATION" and s.file.endswith(".png"))
        p = planner.Shot(id="s2", start=0, end=6, kind="image", asset="nasa_image:the team in mission control", name="", text="the engineers in the control room cheered")
        media.fetch([p], Path("/tmp/x"), fetcher=fake, log=lambda m: None)
        self.assertEqual(p.file, "", "people are never illustrated")


    def test_each_fetch_pass_gets_its_own_scene_numbers_so_files_never_overwrite(self):
        """A Flow 001.png from the AI pass once replaced (and deleted) the NASA 001.jpg of the first pass: FileNotFoundError at render."""
        from types import SimpleNamespace

        from starmap.media import media_rows
        from whatif import media

        passes = []

        def fake(plan, images_dir, **kw):
            passes.append(([m.scene_number for m in media_rows(plan)], "scene_rows" in kw))
            return SimpleNamespace(media={f"row:{b.clips[0].row}": {"file": f"/x/{b.clips[0].row}.jpg"} for b in plan.beats
                                          if b.clips[0].asset.startswith("nasa_image:Earth")}, unresolved=[], notes=[], credits=[])

        shots = [planner.Shot(id=f"s{n}", start=n * 6, end=n * 6 + 6, kind="image", asset=a, name=nm, text=tx) for n, (a, nm, tx) in enumerate([
            ("nasa_image:Earth from Apollo 17", "EARTH", "the blue marble"),
            ("nasa_image:Voyager 1 view of Saturn", "VOYAGER 1", "Voyager passed Saturn"),
            ("nasa_image:Sirius A and B", "", "Sirius shines brightest")])]
        media.fetch(shots, Path("/tmp/x"), fetcher=fake, log=lambda m: None, scene_rows=["the Visual Plan"])
        numbers = [n for nums, _ in passes for n in nums]
        self.assertGreater(len(passes), 1)
        self.assertEqual(len(numbers), len(set(numbers)), f"scene numbers reused across passes: {passes}")
        self.assertEqual([has for _, has in passes], [True] + [False] * (len(passes) - 1), "only the first pass reads the Visual Plan")
        self.assertEqual(shots[0].file, "/x/1.jpg")


    def test_saved_files_under_shifted_numbers_go_back_on_their_rows(self):
        """Project #013: rows renumbered after a source change; 14 made assets were filed one number off and showed as missing."""
        import json
        import tempfile

        from providers.base import SceneRow
        from whatif import media

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            def rec(n, src, text, ext):
                p = d / f"{n:03d}.{ext}"
                p.write_bytes(b"x")
                return {"status": "complete", "source": src, "prompt": text, "local_path": str(p)}
            man = {"001": rec(1, "nasa_image", "old picture", "jpg"), "002": rec(2, "nasa_image", "Pluto close up", "jpg"),
                   "003": rec(3, "flow_image", "an icy body in space -- medium view", "png")}
            (d / ".asset_manifest.json").write_text(json.dumps(man))
            rows = [SceneRow.from_csv_row({"scene_number": "1", "asset_type": "stock_image", "prompt": "Pluto close up"}),
                    SceneRow.from_csv_row({"scene_number": "2", "asset_type": "flow_image", "prompt": "an icy body in space"}),
                    SceneRow.from_csv_row({"scene_number": "3", "asset_type": "flow_image", "prompt": "an icy body in space -- medium view"})]
            self.assertEqual(media.realign_saved(d, rows, log=lambda m: None), 2)
            got = json.loads((d / ".asset_manifest.json").read_text())
            self.assertEqual(got["001"]["prompt"], "Pluto close up")              # its NASA picture, from number 2
            self.assertEqual(got["002"]["prompt"], "an icy body in space")        # the split twin's picture, under its own text
            self.assertEqual(got["003"]["prompt"], "an icy body in space -- medium view")   # the donor keeps its own
            self.assertEqual(media.realign_saved(d, rows, log=lambda m: None), 0)


class Loudness(unittest.TestCase):
    def test_final_audio_is_set_to_the_references_loudness(self):
        import shutil
        import tempfile

        from whatif.sound import TARGET_LUFS, measure_loudness, normalize_loudness

        if not shutil.which("ffmpeg"):
            self.skipTest("no ffmpeg")
        d = tempfile.mkdtemp()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=10:c=pink:a=0.05", "-af", "tremolo=f=3:d=0.9", "-ar", "48000", f"{d}/a.wav"], check=True)
        out = normalize_loudness(f"{d}/a.wav", f"{d}/b.wav")
        m = measure_loudness(out)
        self.assertAlmostEqual(m["lufs"], TARGET_LUFS, delta=1.0)
        self.assertLessEqual(m["peak"], -1.0)

    def test_normalising_a_broken_file_returns_the_source(self):
        from whatif.sound import normalize_loudness

        self.assertEqual(normalize_loudness("/nonexistent.wav", "/tmp/x.wav"), "/nonexistent.wav")


class Packaging(unittest.TestCase):
    def test_every_file_the_renderer_loads_ships(self):
        from whatif.packaging import data_files, python_modules

        files = data_files(ROOT)
        names = {Path(f).name for f, _ in files}
        for need in ("render.mjs", "page.js", "tm_theme.mjs", "voyager.glb", "2k_venus_atmosphere.jpg", "JetBrainsMono-Bold.ttf", "DRACOLoader.js",
                     "draco_decoder.wasm", "whatif_csv_prompt.txt"):
            self.assertIn(need, names)
        self.assertIn("whatif.planner", python_modules(ROOT))

    def test_every_model_the_planner_names_exists(self):
        for _pat, model, _name in planner.CRAFT:
            self.assertTrue((ROOT / "whatif-engine" / "assets" / "models" / model).is_file(), model)
        for _pat, tex, _name, _atm in planner.WORLDS:
            self.assertTrue((ROOT / "whatif-engine" / "assets" / "textures" / tex).is_file(), tex)


class NoBlankScreens(unittest.TestCase):
    """Video 013 (Earth to Alpha Centauri): a gauge hidden on the only plate it was on, bare plate tails after a diagram, a 9 s black shot."""

    INTRO = "Earth is our home and it has been for a very long time, a small blue world in the dark. " * 4
    HEAD = "row,shot,vo_anchor,kind,asset,texture,label,text,type,id,value_from,value_to,hold\n"

    def plan(self, script, rows):
        from whatif.app_integration import plan_from
        raw = timed(self.INTRO + script)
        return plan_from(raw, self.INTRO + script, raw[-1][2] + 0.4, "t", self.HEAD + "shot,0,Earth is our,globe,,earth,,,,,,,\n" + rows,
                         flow_video="images")

    def test_a_gauge_alone_on_its_plate_stays_on_for_the_whole_plate(self):
        p = self.plan("The probe kept going outward past every planet we know. Six billion kilometers is about forty A.U. from the Sun, "
                      "and that places it far beyond the last of the giant planets and their moons. Then the story changes again for good.",
                      "shot,1,The probe kept,image,flow_image:a probe in dark space,,,,,,,,\n"
                      "shot,2,Six billion kilometers,plate,,,,,,,,,\n"
                      "layer,2,Six billion kilometers,,,,DISTANCE FROM THE SUN,NEPTUNE=30 AU; VOYAGER 1=40 AU,hud,gauge,0,50,\n"
                      "shot,3,Then the story,image,flow_image:a probe drifting on,,,,,,,,\n")
        gauge = next(L for L in p.layers if L["type"] == "tm_gauge")
        plate = next(s for s in p.shots if s.kind == "plate")
        self.assertIs(gauge["hide_on_plates"], False, "the plate's only content is drawn")
        self.assertAlmostEqual(gauge["end"], plate.end, places=2)
        self.assertEqual(planner.empty_plates(p.shots, p.layers), [])

    def test_a_gauge_still_steps_back_over_a_diagram_plate(self):
        shots = [planner.Shot(id="s1", start=0, end=6, kind="plate")]
        layers = [{"type": "tm_gauge", "start": 0, "end": 6}, {"type": "tm_bars", "start": 0, "end": 6}]
        self.assertEqual(planner.show_lone_instruments(shots, layers, []), 0)
        self.assertNotIn("hide_on_plates", layers[0])

    def test_a_bare_plate_tail_joins_the_diagram_before_it(self):
        p = self.plan("Shrink the Sun to a grapefruit and the planets spread out over a very long and empty field around it. "
                      "Neptune is a pea out near the far end of that field and the next star is another grapefruit a whole continent away from us. "
                      "Then the story changes again for good.",
                      "shot,1,Shrink the Sun,image,flow_image:a grapefruit on a field,,,,,,,,\n"
                      "shot,2,Neptune is a,plate,,,,,,,,,\n"
                      "layer,2,Neptune is a,,,,SCALE MODEL,EARTH=15; NEPTUNE=450,diagram,bars,,,5.5\n"
                      "shot,3,Then the story,image,flow_image:a probe drifting on,,,,,,,,\n")
        plates = [s for s in p.shots if s.kind == "plate"]
        self.assertEqual(len(plates), 1, [(s.id, s.start, s.end, s.title) for s in plates])
        bars = next(L for L in p.layers if L["type"] == "tm_bars")
        self.assertAlmostEqual(bars["end"], plates[0].end, places=2)
        self.assertTrue(any("joins the diagram" in n for n in p.notes))

    def test_the_plan_check_reports_a_plate_with_only_a_caption_under_a_corner_clock(self):
        shots = [planner.Shot(id="s1", start=10, end=16, kind="plate")]
        layers = [{"type": "tm_clock", "mode": "dual", "start": 0, "end": 100}, {"type": "tm_caption", "start": 10, "end": 16}]
        self.assertEqual([s.id for s in planner.empty_plates(shots, layers)], ["s1"])
        layers.append({"type": "tm_gauge", "start": 10, "end": 16})
        self.assertEqual(len(planner.empty_plates(shots, layers)), 1, "a gauge that steps back over plates draws nothing there")
        layers[-1]["hide_on_plates"] = False
        self.assertEqual(planner.empty_plates(shots, layers), [])

    def test_a_long_black_shot_is_a_breath_and_a_picture_takes_the_rest(self):
        p = self.plan("Soon afterward the cameras were switched off for good to save power and memory on the long trip out. "
                      "Everything we have learned about the outer dark since then has come from its other instruments alone. "
                      "Then the story changes again for good.",
                      "shot,1,Soon afterward the,black,,,,,,,,,\n"
                      "shot,2,Then the story,image,flow_image:a probe drifting on,,,,,,,,\n")
        black = next(s for s in p.shots if s.kind == "black")
        self.assertLessEqual(black.length, planner.BLACK_MAX_S + 1e-6)
        after = next(s for s in p.shots if abs(s.start - black.end) < 1e-3)
        self.assertIn(after.kind, ("image", "video", "globe", "craft", "hero"), "the rest of the silence is a picture of what is said")
        self.assertLessEqual(planner.report(p)["longest_black_s"], 3.0)
        self.assertEqual(planner.report(p)["empty_plates"], 0)

    def test_a_short_rest_of_black_goes_to_the_next_shot(self):
        shots = [planner.Shot(id="s1", start=10, end=14, kind="black"), planner.Shot(id="s2", start=14, end=20, kind="image")]
        out = planner.breathe_black(shots, [], [], [])
        self.assertEqual([(s.kind, s.start, s.end) for s in out], [("black", 10, 12.8), ("image", 12.8, 20)])

    def test_a_title_card_on_black_keeps_its_ground(self):
        shots = [planner.Shot(id="s1", start=10, end=14.5, kind="black"), planner.Shot(id="s2", start=14.5, end=20, kind="image")]
        out = planner.breathe_black(shots, [], [{"type": "tm_title", "start": 10.0, "end": 13.5}], [])
        self.assertEqual(out[0].end, 14.5, "a card of 3.5 s and a beat: the rest is under a second, left as it is")

    def test_and_a_half_is_one_and_a_half(self):
        text = "Its outer edge may stretch to about one and a half light-years."
        m = nr.extract_metrics(nr.words_of(timed(text), text))
        self.assertEqual((m[0].shown, m[0].unit), ("1.5", "LIGHT-YEARS"))

    def test_the_csv_prompt_keeps_black_to_a_breath(self):
        prompt = (ROOT / "composition_styles" / "whatif_csv_prompt.txt").read_text(encoding="utf-8")
        self.assertIn("kind black is ONLY a short silence", prompt)


class Engine(unittest.TestCase):
    def test_the_page_numbers_its_shots_so_clip_frames_can_be_found(self):
        """Clip frames are served at /footage/<shot index>/<k>.jpg; without s.i the page asked for /footage/undefined/... (video shot s52 failed)."""
        page = (Path(__file__).parent / "whatif-engine" / "page.js").read_text(encoding="utf-8")
        self.assertIn("/footage/${s.i}/", page)
        self.assertRegex(page, r"spec\.shots\.forEach\(\(s, i\) => \{ s\.i = i; \}\)")

    def test_engine_unit_tests(self):
        node = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
        if not node:
            self.skipTest("no node")
        r = subprocess.run([node, "--test", "test/shots.test.mjs"], cwd=ROOT / "whatif-engine", capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])


class Templates(unittest.TestCase):
    """The template library (whatif-engine/templates, whatif/templates.py): V4's visuals and the suggested ones, as CSV rows and in auto mode."""

    @staticmethod
    def csv_text(rows):
        import csv
        import io

        from whatif.shot_csv import COLUMNS
        buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=COLUMNS); w.writeheader()
        for r in rows:
            w.writerow(r)
        return buf.getvalue()

    def rows(self, rows, script):
        from whatif.shot_csv import layers_from_rows
        raw = timed(script)
        shots, items, info, notes = read_shots(self.csv_text([dict(row="plan")] + rows), raw, raw[-1][2])
        return layers_from_rows(items, shots, raw, script)

    def test_the_library_is_complete_and_valid(self):
        from whatif import templates as tpl
        lib = tpl.load_library()
        self.assertGreaterEqual(len(lib), 70)
        for must in ("target_section", "photon_orbit", "two_clocks_ratio", "pov_split", "river_walkway", "spacetime_axes", "warp_well", "singularity_equation",
                     "deep_time_axis", "squeeze_object", "eht_pair", "stage_header", "end_question", "size_ladder", "cosmic_calendar", "vital_monitor", "myth_fact"):
            self.assertIn(must, lib)
        self.assertEqual([p for t in lib.values() for p in tpl.validate(t)], [])

    def test_a_template_row_becomes_one_layer_with_its_plate_and_the_csv_values(self):
        script = "Down here time itself slows. One hour for you is one hundred hours on Earth, and the gap keeps growing as you sink lower."
        layers, plates = self.rows([dict(row="shot", shot="s1", vo_anchor="Down here time", kind="image", asset="flow_image:a probe"),
                                    dict(row="layer", vo_anchor="One hour for", type="template", id="two_clocks_ratio", label="Earth", value_from="2", value_to="100", hold="8")], script)
        L = [x for x in layers if x["type"] == "tm_template"][0]
        self.assertEqual(L["template"]["id"], "two_clocks_ratio")
        self.assertEqual((L["slots"]["ratio_to"], L["slots"]["ratio_from"], L["slots"]["left"]), (100, 2, "EARTH"))
        self.assertAlmostEqual(L["end"] - L["start"], 8.0, places=2)
        self.assertTrue(plates and plates[0].kind == "plate" and plates[0].cite[0] == "ILLUSTRATION")
        self.assertTrue(L["plate"])

    def test_cues_are_the_moments_the_narrator_says_the_words(self):
        from whatif import templates as tpl
        script = "Light bends around it. Get too close and even light falls in, crossing the event horizon for ever."
        words = nr.words_of(timed(script), script)
        it = type("Row", (), {"id": "light_bends", "hold": 8, "extra": {}, **{c: None for c in tpl.COLUMNS}})()
        L, plate = tpl.layer_for(it, 0.0, 8.0, words)
        close = next(w.start for w in words if w.norm.startswith("close"))
        self.assertAlmostEqual(L["cues"]["close"], close, places=2)
        self.assertIn("horizon", L["cues"])

    def test_an_overlay_template_needs_no_plate_and_does_not_fill_one(self):
        script = "Stage two. The photon sphere, where light itself can orbit, is the last place you could still turn back home."
        layers, plates = self.rows([dict(row="shot", shot="s1", vo_anchor="Stage two", kind="hero", model="blackhole_ring"),
                                    dict(row="layer", vo_anchor="Stage two", type="template", id="stage_header", label="The photon sphere", sub="Stage 2")], script)
        L = [x for x in layers if x["type"] == "tm_template"][0]
        self.assertEqual(plates, [])
        self.assertFalse(planner._draws_on_plate(L))
        self.assertEqual(L["slots"]["label"], "THE PHOTON SPHERE")

    def test_bad_template_rows_are_named(self):
        script = "Something happens here that the narrator describes at length for the sake of this test sentence."
        with self.assertRaises(PlanError) as cm:
            self.rows([dict(row="shot", shot="s1", vo_anchor="Something happens", kind="image", asset="flow_image:x"),
                       dict(row="layer", type="template", id="two_clock_ratio")], script)
        self.assertIn("did you mean two_clocks_ratio", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            self.rows([dict(row="shot", shot="s1", vo_anchor="Something happens", kind="image", asset="flow_image:x"),
                       dict(row="layer", type="template", id="squeeze_object", label="THE SUN")], script)
        self.assertIn("value_from", str(cm.exception))

    def test_pairs_lists_and_photo_slots(self):
        script = "Here is how big things get, from a person to a mountain to the planet itself, step after step, all the way up."
        layers, plates = self.rows([dict(row="shot", shot="s1", vo_anchor="Here is how", kind="image", asset="flow_image:x"),
                                    dict(row="layer", type="template", id="size_ladder", text="YOU=1.7 m; EVEREST=8.8 km|8800; EARTH=12,742 km|12742000"),
                                    dict(row="layer", type="template", id="eht_pair", extra='{"slots": {"photo": "nasa_image:EHT Sagittarius A*"}}', t="6")], script)
        ladder = [x for x in layers if x.get("template", {}).get("id") == "size_ladder"][0]
        self.assertEqual([i["name"] for i in ladder["slots"]["items"]], ["YOU", "EVEREST", "EARTH"])
        self.assertEqual(ladder["slots"]["items"][1]["num"], 8800)
        pair = [x for x in layers if x.get("template", {}).get("id") == "eht_pair"][0]
        self.assertNotIn("photo", pair["slots"])
        self.assertIn("nasa_image:EHT Sagittarius A*", [p.asset for p in plates])

    def test_mission_rows_are_one_card_that_counts(self):
        script = ("We set off for the centre of the galaxy. Now we are falling fast towards the edge. "
                  "Here we hover close above it. And finally we cross the edge and keep on falling inwards.")
        layers, _ = self.rows([dict(row="shot", shot="s1", vo_anchor="We set off", kind="hero", model="blackhole_lensing"),
                               dict(row="layer", vo_anchor="We set off", type="hud", id="mission", label="Distance to the edge", value_to="27000", format="light-years",
                                    sub="from Earth", text="APPROACH", extra='{"kicker": "Mission · Sgr A*"}'),
                               dict(row="shot", shot="s2", vo_anchor="Now we are", kind="hero", model="blackhole_disc"),
                               dict(row="layer", vo_anchor="Now we are", type="hud", id="mission", label="Distance to the edge", value_to="208", format="million km", sub="falling", text="APPROACH"),
                               dict(row="shot", shot="s3", vo_anchor="Here we hover", kind="hero", model="blackhole_horizon"),
                               dict(row="layer", vo_anchor="Here we hover", type="hud", id="mission", value_to="2215", format="km", sub="hovering", text="EDGE"),
                               dict(row="shot", shot="s4", vo_anchor="And finally we", kind="hero", model="blackhole_ring")], script)
        cards = [x for x in layers if x["type"] == "tm_mission"]
        self.assertEqual(len(cards), 1)
        keys = cards[0]["keys"]
        self.assertEqual([k["value"] for k in keys], [27000, 208, 2215])
        self.assertEqual([k["stage"] for k in keys], [0, 0, 2])
        self.assertEqual(cards[0]["kicker"], "MISSION · SGR A*")
        self.assertEqual(keys[1]["unit"], "MILLION KM")

    def test_black_holes_are_ray_traced_hero_shots(self):
        f = planner.classify("Imagine falling towards a black hole, its disc of hot gas swirling around it.")
        self.assertEqual((f["kind"], f["scene"]), ("hero", "blackhole_top"))
        self.assertEqual(planner.classify("Light bends around the black hole and the stars behind it warp.")["scene"], "blackhole_lensing")
        self.assertEqual(planner.classify("Now you hover just above the event horizon.")["scene"], "blackhole_horizon")
        self.assertNotEqual(planner.classify("A black hole sits at the centre.", flow_video=True)["kind"], "hero")   # all-Flow-video mode keeps its pictures
        self.assertEqual(planner.classify("The first photo of a black hole was released in 2019.")["kind"], "image")       # the EHT photo stays a real image

    def test_auto_mode_draws_concepts_and_never_template_data(self):
        from whatif import templates as tpl
        self.assertIsNotNone(tpl.match("Gravity slows time, because mass warps the fabric of space."))
        for data_tpl in ("deep_time_axis", "size_ladder", "layer_cutaway", "discovery_timeline", "composition_donut"):
            self.assertNotIn(data_tpl, [t["id"] for t in tpl.auto_candidates()])
        script = ("Our journey begins far away from everything we know, out in the dark, quiet and cold, drifting for a long while. " * 3 +
                  "Near a black hole, light bends around it and even the stars behind it are moved out of place for anyone watching. "
                  "That is just the start of how strange it gets, and there is so much more of this journey still waiting for us out there.")
        raw = timed(script)
        p = planner.plan(raw, script, raw[-1][2] + 1)
        tl = [L for L in p.layers if L["type"] == "tm_template"]
        self.assertTrue(tl, p.notes)
        self.assertIn(tl[0]["template"]["id"], ("light_bends", "star_lensing"))
        plate = [s for s in p.shots if s.kind == "plate" and s.start <= tl[0]["start"] + 0.1 < s.end]
        self.assertTrue(plate)
        self.assertEqual(planner.empty_plates(p.shots, p.layers), [])

    def test_the_prompt_lists_every_template_and_the_journey_pattern(self):
        import app_csv_prompts
        from whatif import templates as tpl
        text = app_csv_prompts.build_prompt("whatif")
        self.assertNotIn(app_csv_prompts.TEMPLATE_PLACEHOLDER, text)
        for tid in tpl.load_library():
            self.assertIn(f"  {tid}: ", text)
        for must in ("hud      id = mission", "blackhole_lensing", "A JOURNEY VIDEO", "type is one of"):
            self.assertIn(must, text)

    def test_the_templates_ship_with_the_app(self):
        from whatif.packaging import data_files
        shipped = [s for s, _ in data_files(ROOT)]
        self.assertTrue(any(s.endswith(os.path.join("templates", "physics", "warp_well.json")) for s in shipped))
        self.assertTrue(any(s.endswith(os.path.join("lib", "blackhole.mjs")) for s in shipped))


class NeverStops(unittest.TestCase):
    """A bad shot CSV is repaired or its bad rows left out (whatif/heal.py); it never stops Generate (whatif/stress.py: 0 of 1,200)."""

    def test_common_ai_mistakes_are_repaired(self):
        from whatif.heal import heal
        text = ("row;shot;vo_anchor;kind;asset;model;texture;label;sub;text;type;id;value_from;value_to;format;anchor;until;hold;why;extra;t;end\n"
                "plan;;;;;;;T;;;;;;;;;;;;;;\n"
                "Scene;1;The nearest star;photo;nasa:Alpha Centauri;;;;;;;;;;;;;;;;;\n"
                "layer;1;hours on Earth;;;;;;;;visual;two_clock_ratio;2;100 hours;;;;;;{'tint': 'warm'};;\n"
                "shot;2;But a light-year;scene;;black_hole_disc;;;;;;;;;;;;;;;;\n")
        healed, notes = heal(text)
        rows = list(__import__("csv").reader(__import__("io").StringIO(healed)))
        self.assertEqual([r[0] for r in rows[1:]], ["plan", "shot", "layer", "shot"])
        self.assertEqual(rows[2][3:5], ["image", "nasa_image:Alpha Centauri"])
        self.assertEqual((rows[3][10], rows[3][11], rows[3][13]), ("template", "two_clocks_ratio", "100"))
        self.assertEqual(json.loads(rows[3][19]), {"tint": "warm"})
        self.assertEqual((rows[4][3], rows[4][5]), ("hero", "blackhole_disc"))
        self.assertTrue(any("semicolons" in n for n in notes))

    def test_bad_rows_are_left_out_and_the_rest_is_used(self):
        from whatif.app_integration import plan_from
        script = "The nearest star is far away. But a light-year is enormous. Nothing we built is that fast at all, not even close to it."
        raw = timed(script)
        text = ("row,shot,vo_anchor,kind,asset,label,type,id,text,extra\n"
                "plan,,,,,,,,,\n"
                "shot,1,The nearest star,image,nasa_image:Alpha Centauri,,,,,\n"
                "layer,1,far away,,,,diagram,compare,ONLY ONE SIDE=1,\n"
                "layer,1,far away,,,,sparkle,,,\n"
                "shot,2,But a light-year,image,flow_image:a dark gulf,,,,,\n"
                "shot,3,Nothing we built,craft,,,,,,\n")
        p = plan_from(raw, script, raw[-1][2] + 1, "", text)
        self.assertGreaterEqual(len([s for s in p.shots if s.kind in ("image", "video")]), 2)
        self.assertTrue(any("left out" in n for n in p.notes), p.notes)

    def test_a_csv_with_no_usable_shot_falls_back_to_the_narration(self):
        from whatif.app_integration import plan_from
        script = "The nearest star is far away from us. But a light-year is enormous and nothing we built is that fast."
        raw = timed(script)
        for text in ("", "hello world", "row,shot\nlayer,1\n", "\ufeffrow,kind\nshot,photo\n"):
            p = plan_from(raw, script, raw[-1][2] + 1, "", text)
            self.assertTrue(p.shots)

    def test_stress_sample_never_stops(self):
        from whatif import stress
        base = stress.journey_base()
        with __import__("tempfile").TemporaryDirectory() as tmp:
            for seed in range(40):
                r = stress.run_one((base, seed, tmp))
                self.assertIsNone(r["stop"], (seed, r["what"], r["stop"]))

    def test_any_saved_encoding_and_layout_is_accepted(self):
        from whatif.heal import looks_usable, read_text
        import tempfile
        text = "row;shot;vo_anchor;kind;asset;label\nplan;;;;;Café\nshot;1;The nearest star;photo;nasa:Alpha Centauri;CAFÉ\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "shots.csv"
            p.write_bytes(text.encode("cp1252"))
            back = read_text(p)
        self.assertIn("CAFÉ", back)
        self.assertTrue(looks_usable(back))
        self.assertFalse(looks_usable("hello world"))

    def test_non_finite_numbers_never_reach_the_renderer(self):
        from whatif.heal import _number
        for bad in ("nan", "inf", "1e400", "-inf"):
            self.assertEqual(_number(bad)[0], "")
        self.assertEqual(_number("1,200")[0], "1200")
        self.assertEqual(_number("4.2 km"), ("4.2", False))


if __name__ == "__main__":
    unittest.main()
