"""Hybrid Map H1: the hand-authored plan, its validation, the compiler (lifetimes around footage, clip hand-over, pakMap rows) and the
generator. No AI, no network, no real providers."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hybrid.compile import HybridCompileError, compile_plan, layer_end, plan_to_rows, rows_to_csv, spec_extra, _clip_spans
from hybrid.generate import generate_hybrid_video
from hybrid.plan import HybridPlan, PlanError, validate_plan
from pakmap.schema import parse_csv

ROOT = Path(__file__).resolve().parent
HAS_NODE = shutil.which("node") is not None and (ROOT / "pakmap-engine" / "tools" / "validate_spec.mjs").exists()

PLAN = {
    "version": 1, "duration": 24.0,
    "settings": {"dissolve_s": 0.5, "return_grace_s": 0.8, "drift_pct_per_s": 0.5, "dissolve_centered": False},  # H1 timing: the dissolves sit inside the footage beat
    "beats": [
        {"id": "b1", "mode": "map", "start": 0, "end": 9, "purpose": "where we are",
         "camera": [{"action": "start", "place": "Kenya", "frame": "country"}, {"action": "fly_to", "t": 4, "dur": 2, "place": "Nairobi", "frame": "region"}],
         "layers": [
             {"id": "title", "type": "hud_title", "t": 0.3, "label": "PART 1", "sub": "THE EMPTY HALF"},
             {"id": "kenya", "type": "fill", "t": 0.5, "place": "Kenya", "role": "subject", "until": "after_footage"},
             {"id": "nbo", "type": "marker", "t": 3, "place": "Nairobi", "label": "NAIROBI", "until": "after_footage"},
             {"id": "pop", "type": "stat", "t": 6.4, "from": 40, "to": 47, "format": "0 MILLION PEOPLE", "sub": "KENYA"}]},
        {"id": "b2", "mode": "footage", "start": 9, "end": 15, "purpose": "what the highlands look like",
         "footage": {"clips": [{"asset": "stock_video:farmers in a field"}, {"asset": "media/market.jpg", "kenburns": True}]}},
        {"id": "b3", "mode": "map", "start": 15, "end": 24, "purpose": "back to the geography",
         "layers": [{"id": "rail", "type": "line", "t": 16, "kind": "rail", "places": ["Mombasa", "Nairobi"]},
                    {"id": "mba", "type": "marker", "t": 16.5, "place": "Mombasa", "label": "MOMBASA"}]},
    ],
}


def plan(**over) -> HybridPlan:
    d = copy.deepcopy(PLAN)
    for k, v in over.items():
        d[k] = v
    return HybridPlan.from_dict(d)


def lay(p: HybridPlan, lid: str):
    return next(l for b in p.beats for l in b.layers if l.id == lid)


class TestPlan(unittest.TestCase):
    def test_a_good_plan_has_no_problems_and_round_trips_through_json(self):
        p = plan()
        self.assertEqual(validate_plan(p), [])
        back = HybridPlan.from_dict(json.loads(json.dumps(p.to_dict())))
        self.assertEqual(back.to_dict(), p.to_dict())
        self.assertEqual([b.mode for b in back.beats], ["map", "footage", "map"])
        self.assertEqual(back.beats[1].clips[1].kenburns, True)

    def test_beats_must_tile_the_timeline(self):
        d = copy.deepcopy(PLAN)
        d["beats"][1]["start"] = 9.5
        self.assertTrue(any("no gap or overlap" in x for x in validate_plan(HybridPlan.from_dict(d))))
        d = copy.deepcopy(PLAN)
        d["beats"][2]["end"] = 26
        self.assertTrue(any("plan is 24s long" in x for x in validate_plan(HybridPlan.from_dict(d))))
        d = copy.deepcopy(PLAN)
        d["beats"][0]["end"] = 0
        self.assertTrue(any("ends (0s) before it starts" in x or "before it starts" in x for x in validate_plan(HybridPlan.from_dict(d))))

    def test_the_map_needs_exactly_one_start(self):
        d = copy.deepcopy(PLAN)
        d["beats"][0]["camera"] = d["beats"][0]["camera"][1:]
        self.assertTrue(any("exactly one camera 'start'" in x for x in validate_plan(HybridPlan.from_dict(d))))

    def test_the_camera_cannot_move_under_footage(self):
        d = copy.deepcopy(PLAN)
        d["beats"][0]["camera"][1] = {"action": "fly_to", "t": 8, "dur": 2, "place": "Nairobi", "frame": "region"}
        msgs = validate_plan(HybridPlan.from_dict(d))
        self.assertTrue(any("does not fit" in x and "cannot move under footage" in x for x in msgs), msgs)

    def test_layers_belong_to_map_beats_and_footage_beats_hold_only_clips(self):
        d = copy.deepcopy(PLAN)
        d["beats"][0]["layers"][2]["t"] = 10
        self.assertTrue(any("outside its map beat b1" in x for x in validate_plan(HybridPlan.from_dict(d))))
        d = copy.deepcopy(PLAN)
        d["beats"][1]["layers"] = [{"id": "x", "type": "marker", "t": 10, "place": "Nairobi", "label": "N"}]
        self.assertTrue(any("footage beat cannot hold map camera moves" in x for x in validate_plan(HybridPlan.from_dict(d))))
        d = copy.deepcopy(PLAN)
        d["beats"][1]["footage"]["clips"] = []
        self.assertTrue(any("needs at least one clip" in x for x in validate_plan(HybridPlan.from_dict(d))))

    def test_layer_mistakes_are_named(self):
        d = copy.deepcopy(PLAN)
        d["beats"][0]["layers"][2]["until"] = "forever"
        d["beats"][0]["layers"][1]["id"] = "nbo"
        d["beats"][0]["layers"][3] = {"id": "pop", "type": "stat", "t": 6.4}
        msgs = " | ".join(validate_plan(HybridPlan.from_dict(d)))
        self.assertIn("layer nbo: until must be one of", msgs)
        self.assertIn("layer id 'nbo' is used more than once", msgs)
        self.assertIn("layer pop: a stat is missing something it needs", msgs)

    def test_a_bad_file_says_what_is_wrong(self):
        with self.assertRaises(PlanError) as cm:
            HybridPlan.from_dict({"duration": 10, "beats": [{"id": "b", "mode": "video", "start": 0, "end": 10}], "extra": 1})
        self.assertIn("mode must be 'map' or 'footage'", " ".join(cm.exception.problems))
        self.assertIn("unknown plan field 'extra'", " ".join(cm.exception.problems))


class TestLifetimes(unittest.TestCase):
    """Layer ends are narration time; footage is 9-15 s with 0.5 s dissolves and a 0.8 s return grace."""

    def end(self, lid, **changes):
        p = plan()
        layer = lay(p, lid)
        for k, v in changes.items():
            setattr(layer, k, v)
        beat = next(b for b in p.beats if layer in b.layers)
        return layer_end(p, beat, layer)

    def test_a_layer_that_ends_with_its_beat_leaves_under_the_dissolve_not_before_it(self):
        self.assertEqual(self.end("pop"), 9.5)        # b1 ends at 9: it stays until the footage has covered it, then goes

    def test_a_layer_that_is_meant_to_persist_runs_to_the_end_of_the_next_map_beat(self):
        self.assertEqual(self.end("nbo"), 24.0)
        self.assertEqual(self.end("kenya"), 24.0)

    def test_a_planned_end_that_falls_deep_under_footage_is_held_just_after_the_map_returns(self):
        self.assertEqual(self.end("nbo", until=12), 15.8)
        self.assertEqual(self.end("pop", hold=8.0), 15.8)  # appears at 6.4 s + 8 s = 14.4 s, under the footage

    def test_ends_before_the_footage_or_after_it_are_left_alone(self):
        self.assertEqual(self.end("nbo", until=7.5), 7.5)
        self.assertEqual(self.end("nbo", until=20.0), 20.0)
        self.assertEqual(self.end("nbo", until="end"), 24.0)
        self.assertEqual(self.end("pop", until="beat_end", hold=2.0), 8.4)
        self.assertEqual(self.end("rail"), 24.0)       # a layer in the last map beat

    def test_the_grace_is_a_setting_and_cannot_run_into_the_next_footage(self):
        d = copy.deepcopy(PLAN)
        d["settings"]["return_grace_s"] = 0.0
        p = HybridPlan.from_dict(d)
        beat, layer = p.beats[0], lay(p, "nbo")
        layer.until = 12
        self.assertEqual(layer_end(p, beat, layer), 15.0)
        d["settings"]["return_grace_s"] = 5.0
        d["beats"].insert(2, {"id": "bx", "mode": "map", "start": 15, "end": 16, "layers": []})
        d["beats"][3]["start"] = 16
        d["beats"].insert(3, {"id": "f2", "mode": "footage", "start": 16, "end": 18, "footage": {"clips": [{"asset": "a.jpg"}]}})
        d["beats"][4]["start"] = 18
        p2 = HybridPlan.from_dict(d)
        l2 = lay(p2, "nbo"); l2.until = 12
        self.assertEqual(layer_end(p2, p2.beats[0], l2), 16.0)  # stops where the next footage starts

    def test_a_note_explains_a_held_layer(self):
        notes = []
        p = plan()
        layer = lay(p, "nbo"); layer.until = 12
        layer_end(p, p.beats[0], layer, notes)
        self.assertEqual(len(notes), 1)
        self.assertIn("held until 15.8s", notes[0])


class TestClips(unittest.TestCase):
    def spans(self, clips, start=9.0, end=15.0):
        d = copy.deepcopy(PLAN)
        d["beats"][1]["start"], d["beats"][1]["end"] = start, end
        d["beats"][1]["footage"]["clips"] = clips
        d["beats"][0]["end"] = start
        d["beats"][2]["start"] = end
        p = HybridPlan.from_dict(d)
        return _clip_spans(p, p.beats[1])

    def test_one_clip_fills_the_beat(self):
        self.assertEqual(self.spans([{"asset": "a.jpg"}]), [(9.0, 15.0)])

    def test_several_clips_share_the_beat_and_overlap_by_one_dissolve(self):
        s = self.spans([{"asset": "a.jpg"}, {"asset": "b.jpg"}])
        self.assertEqual(s, [(9.0, 12.25), (11.75, 15.0)])
        s3 = self.spans([{"asset": "a.jpg"}, {"asset": "b.jpg"}, {"asset": "c.jpg"}])
        self.assertAlmostEqual(s3[0][1] - s3[1][0], 0.5)
        self.assertAlmostEqual(s3[1][1] - s3[2][0], 0.5)
        self.assertEqual((s3[0][0], s3[-1][1]), (9.0, 15.0))

    def test_given_durations_are_used_and_the_last_clip_runs_to_the_end_of_the_beat(self):
        s = self.spans([{"asset": "a.jpg", "dur": 3}, {"asset": "b.jpg", "dur": 2}])
        self.assertEqual(s, [(9.0, 12.0), (11.5, 15.0)])


class TestCompile(unittest.TestCase):
    def test_rows_carry_the_plan_s_times_in_one_pakmap_item(self):
        rows, line_map, notes = plan_to_rows(plan())
        self.assertTrue(all(r.item_no == 1 for r in rows))      # one item: no per-item clear beat wipes the map around footage
        by_id = {r.layer_id: r for r in rows}
        self.assertEqual((by_id["nbo"].t_start, by_id["nbo"].t_end), (3.0, 24.0))
        self.assertEqual((by_id["pop"].t_start, by_id["pop"].t_end), (6.4, 9.5))
        self.assertEqual(by_id["nbo"].geo_ref, "Nairobi")
        self.assertEqual(by_id["rail"].geo_ref, "Mombasa;Nairobi")
        self.assertEqual(line_map[by_id["nbo"].line], "beat b1 · marker nbo")
        self.assertEqual([r.camera_action for r in rows if r.layer_type == "camera"], ["start", "fly_to", "drift"])

    def test_video_clips_loop_when_short_and_stills_do_not(self):
        rows, _, _ = plan_to_rows(plan())
        clips = [r for r in rows if r.layer_type == "media_full"]
        self.assertTrue(clips[0].params.get("loop"))          # stock_video:...
        self.assertNotIn("loop", clips[1].params)             # media/market.jpg
        d = copy.deepcopy(PLAN)
        d["beats"][1]["footage"]["clips"] = [{"asset": "media/b.mp4"}, {"asset": "youtube_video:river flood"}, {"asset": "flow_image:a map of a river"}]
        rows, _, _ = plan_to_rows(HybridPlan.from_dict(d))
        self.assertEqual([bool(r.params.get("loop")) for r in rows if r.layer_type == "media_full"], [True, True, False])

    def test_footage_rows_carry_the_hybrid_options(self):
        rows, _, _ = plan_to_rows(plan())
        clips = [r for r in rows if r.layer_type == "media_full"]
        self.assertEqual([(r.t_start, r.t_end) for r in clips], [(9.0, 12.25), (11.75, 15.0)])
        self.assertEqual(clips[0].params, {"dissolve_s": 0.5, "cover_ui": True, "kenburns": "auto", "fit": "slow", "loop": True})
        self.assertEqual(clips[1].params, {"dissolve_s": 0.5, "cover_ui": True, "xfade_prev": True, "kenburns": True, "fit": "slow"})
        self.assertEqual([r.asset_path for r in clips], ["stock_video:farmers in a field", "media/market.jpg"])

    def test_the_compiled_script_reads_back_identically(self):
        rows, _, _ = plan_to_rows(plan())
        back, warns = parse_csv("x.csv", text=rows_to_csv(rows))
        self.assertEqual(warns, [])
        key = lambda r: (r.layer_type, r.layer_id, r.t_start, r.t_end, r.geo_ref, r.asset_path, r.params, r.camera_action, r.item_no)  # noqa: E731
        self.assertEqual([key(r) for r in back], [key(r) for r in rows])

    def test_an_invalid_plan_is_refused_with_its_plain_problems(self):
        d = copy.deepcopy(PLAN)
        d["beats"][1]["start"] = 10
        with self.assertRaises(HybridCompileError) as cm:
            plan_to_rows(HybridPlan.from_dict(d))
        self.assertIn("no gap or overlap", cm.exception.problems[0])

    def test_a_clip_too_short_for_its_dissolves_is_refused(self):
        d = copy.deepcopy(PLAN)
        d["beats"][1]["end"], d["beats"][2]["start"] = 10, 10
        d["beats"][1]["footage"]["clips"] = [{"asset": "a.jpg"}, {"asset": "b.jpg"}, {"asset": "c.jpg"}]
        with self.assertRaises(HybridCompileError) as cm:
            plan_to_rows(HybridPlan.from_dict(d))
        self.assertIn("shorter than its two 0.5s dissolves", cm.exception.problems[0])

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_it_compiles_to_a_pakmap_spec_with_the_engine_rules_applied(self):
        res = compile_plan(plan(), width=1920, height=1080, fps=30)
        spec = res.spec
        self.assertEqual(spec["hybrid"], {"pause_overlays": True})
        self.assertEqual(spec["duration"], 24.0)
        ev = {e["id"]: e for e in spec["events"]}
        self.assertEqual((ev["b2_c1"]["type"], ev["b2_c1"]["cover_ui"], ev["b2_c2"]["xfade_prev"], ev["b2_c2"]["kenburns"]), ("media_full", True, True, True))
        self.assertEqual((ev["nbo"]["t_in"], ev["nbo"]["t_out"]), (3.0, 24.0))
        self.assertEqual([m["type"] for m in spec["camera"]["moves"]], ["fly_to"])
        self.assertEqual(spec["camera"]["drift"]["pct_per_s"], 0.5)
        self.assertEqual(res.report.errors, [])

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_a_place_that_cannot_be_found_names_the_beat_and_layer(self):
        d = copy.deepcopy(PLAN)
        d["beats"][0]["layers"][2]["place"] = "Nairobbi"
        with self.assertRaises(HybridCompileError) as cm:
            compile_plan(HybridPlan.from_dict(d), validate=False)
        self.assertTrue(cm.exception.problems[0].startswith("beat b1 · marker nbo:"), cm.exception.problems)

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_pakmap_itself_gets_no_hybrid_options(self):
        from pakmap.compile import compile_csv

        res = compile_csv(text="item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,camera_action,frame\n1,Kenya,camera,c,Kenya,,start,country\n1,Kenya,marker,m,Nairobi,NAIROBI,,\n",
                          words=[("Kenya", 0.5, 0.9)] + [("w%d" % i, 1 + i * 0.5, 1.3 + i * 0.5) for i in range(10)], validate=False)
        self.assertNotIn("hybrid", res.spec)


class TestGenerate(unittest.TestCase):
    def setUp(self):
        import struct, wave
        from test_pakmap_sourcing import FakeManifest, FakeProviders

        FakeManifest.store = {}
        self.FakeManifest, self.fake = FakeManifest, FakeProviders()
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        with wave.open(str(self.d / "vo.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000 * 24)
        self.specs = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_gen(self, p, **kw):
        from pakmap import app_integration as ai

        def fake_render(spec_, out, progress=None, cancel_check=None, log=print):
            self.specs.append(spec_)
            Path(out).write_bytes(b"x")
            return type("O", (), {"sidecar": {}})()

        with mock.patch("scene_graph.app_integration._export_via_existing_renderer", lambda g, s, *, voiceover_path, output_path, **k: Path(output_path).write_bytes(b"x")), \
             mock.patch("scene_graph.app_integration.validate_rendered_output", lambda *a, **k: None), \
             mock.patch.object(ai, "voiceover_duration", lambda path: 24.0), \
             mock.patch("pakmap.compile.check_with_engine", lambda s: ([], [], True)):
            return generate_hybrid_video(p, self.d / "vo.wav", self.d / "out.mp4", work_dir=self.d / "w", render=fake_render, sound_design=False,
                                         media_resolver=self.fake.resolve, media_find_file=self.fake.find, media_manifest_cls=self.FakeManifest, **kw)

    def test_a_plan_renders_with_the_hybrid_options_and_the_footage_comes_from_the_existing_visual_plan_machinery(self):
        r = self.run_gen(plan())
        self.assertTrue(r.ok, r.errors)
        spec = self.specs[0]
        self.assertEqual(spec["hybrid"], {"pause_overlays": True})
        ev = {e["id"]: e for e in spec["events"]}
        self.assertTrue(ev["b2_c1"]["media"].endswith("001.mp4"))          # stock_video:farmers in a field -> scene 1 of the Visual Plan folder
        self.assertEqual(ev["b2_c2"]["media"], "media/market.jpg")         # a local file is the author's own
        self.assertEqual([x["asset_type"] for x in self.fake.calls[0]], ["stock_video"])
        for name in ("hybrid_plan.json", "hybrid_script.csv"):
            self.assertTrue((self.d / "w" / name).is_file(), name)

    def test_the_providers_are_asked_for_clips_as_long_as_the_longest_slot_needs(self):
        seen = {}
        orig = self.fake.resolve

        def spy(rows, images_dir, **kw):
            seen.update(kw)
            return orig(rows, images_dir, **kw)

        self.fake.resolve = spy
        self.assertTrue(self.run_gen(plan()).ok)
        self.assertEqual(seen["youtube_clip_duration"], 4.0)          # the slot is 3.25 s: the floor is 4 s
        self.fake.resolve = spy
        d = copy.deepcopy(PLAN)
        d["beats"][1]["footage"]["clips"] = [{"asset": "stock_video:one long shot"}]
        self.assertTrue(self.run_gen(HybridPlan.from_dict(d)).ok)
        self.assertEqual(seen["youtube_clip_duration"], 6.0 + 0.0)    # a 6 s slot (H1 timing)

    def test_a_replaced_clip_is_what_gets_rendered(self):
        media = self.d / "w" / "media"
        media.mkdir(parents=True)
        (media / "001.png").write_bytes(b"mine")
        self.FakeManifest.store[str(media)] = {"1": {"status": "complete", "source": "manual", "user_override": True}}
        r = self.run_gen(plan())
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(self.fake.calls[0], [])
        self.assertTrue({e["id"]: e for e in self.specs[0]["events"]}["b2_c1"]["media"].endswith("001.png"))

    def test_a_plan_is_fitted_to_a_slightly_different_voiceover_but_not_to_the_wrong_one(self):
        from hybrid.generate import fit_to_audio

        p = plan()
        self.assertEqual(p.duration, 24.0)
        import struct, wave
        for secs, expect in ((23.6, 23.6), (24.0, 24.0), (30.0, 24.0)):
            f = self.d / f"vo_{secs}.wav"
            with wave.open(str(f), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * int(8000 * secs))
            q = fit_to_audio(p, f, log=lambda m: None)
            self.assertAlmostEqual(q.duration, expect, places=2)
            self.assertAlmostEqual(q.beats[-1].end, expect, places=2)
        self.assertEqual(p.duration, 24.0)   # the original plan is never changed

    def test_problems_come_back_naming_the_beat(self):
        d = copy.deepcopy(PLAN)
        d["beats"][1]["start"] = 10
        r = self.run_gen(HybridPlan.from_dict(d))
        self.assertFalse(r.ok)
        self.assertIn("beat b2", r.errors[0])
        self.assertEqual(self.specs, [])

    def test_a_missing_clip_stops_before_rendering(self):
        r = self.run_gen(plan(), )
        self.assertTrue(r.ok)
        self.fake = type(self.fake)(fail={"farmers in a field"})
        self.FakeManifest.store = {}
        shutil.rmtree(self.d / "w" / "media", ignore_errors=True)
        self.specs.clear()
        r = self.run_gen(plan())
        self.assertFalse(r.ok)
        self.assertEqual(r.unresolved, ["1"])
        self.assertEqual(self.specs, [])


CENTERED = copy.deepcopy(PLAN)
CENTERED["settings"] = {"dissolve_s": 0.5, "return_grace_s": 0.8, "drift_pct_per_s": 0.5}   # the default: dissolve_centered is on
CENTERED["beats"][2]["mode"] = "map_footage"
CENTERED["beats"][2]["support"] = {"asset": "stock_image:glacier", "place": "Nairobi", "label": "GLACIER", "t": 17.0}
CENTERED["beats"][1]["footage"]["clips"][0]["asset"] = "stock_video:farmers in a field"


class TestCentredDissolveAndCards(unittest.TestCase):
    """The H4 timing: a dissolve is centred on the beat boundary so it does not eat the footage beat's own time."""

    def p(self, **mut):
        d = copy.deepcopy(CENTERED)
        for k, v in mut.items():
            d[k] = v
        return HybridPlan.from_dict(d)

    def test_footage_is_on_screen_half_a_dissolve_before_and_after_its_beat(self):
        plan = self.p()
        self.assertEqual(plan.footage_windows(), [(8.75, 15.25)])
        self.assertEqual(_clip_spans(plan, plan.beats[1]), [(8.75, 12.25), (11.75, 15.25)])

    def test_at_the_start_or_end_of_the_video_there_is_no_half_dissolve_to_borrow(self):
        d = copy.deepcopy(CENTERED)
        d["beats"] = [{"id": "f1", "mode": "footage", "start": 0, "end": 6, "footage": {"clips": [{"asset": "a.jpg"}]}},
                      {"id": "m1", "mode": "map", "start": 6, "end": 18, "camera": [{"action": "start", "place": "Kenya", "frame": "country"}], "layers": []},
                      {"id": "f2", "mode": "footage", "start": 18, "end": 24, "footage": {"clips": [{"asset": "b.jpg"}]}}]
        self.assertEqual(HybridPlan.from_dict(d).footage_windows(), [(0, 6.25), (17.75, 24)])

    def test_a_layer_that_ends_with_its_beat_leaves_when_the_footage_has_fully_covered_it(self):
        plan = self.p()
        self.assertEqual(layer_end(plan, plan.beats[0], lay(plan, "pop")), 9.25)   # footage starts at 8.75 and is opaque 0.5 s later

    def test_a_held_layer_returns_with_the_map_and_leaves_after_the_grace(self):
        plan = self.p()
        layer = lay(plan, "nbo"); layer.until = 12
        self.assertEqual(layer_end(plan, plan.beats[0], layer), 16.05)               # the map is back at 15.25, plus 0.8 s

    def test_the_camera_stays_clear_of_the_centred_dissolves(self):
        d = copy.deepcopy(CENTERED)
        d["beats"][0]["camera"][1] = {"action": "fly_to", "t": 6.5, "dur": 2.4, "place": "Nairobi", "frame": "region"}   # ends at 8.9, footage starts at 8.75
        self.assertTrue(any("does not fit" in x for x in validate_plan(HybridPlan.from_dict(d))))
        d["beats"][0]["camera"][1]["dur"] = 2.2                                                                           # ends at 8.7
        self.assertEqual(validate_plan(HybridPlan.from_dict(d)), [])

    def test_a_dissolve_is_not_announced_with_a_sound_unless_the_beat_asks(self):
        rows, _, _ = plan_to_rows(self.p())
        self.assertEqual([r.sfx for r in rows if r.layer_type == "media_full"], ["none", "none"])
        d = copy.deepcopy(CENTERED)
        d["beats"][1]["transition_sound"] = "soft_transition"
        rows, _, _ = plan_to_rows(HybridPlan.from_dict(d))
        self.assertEqual([r.sfx for r in rows if r.layer_type == "media_full"], ["soft_transition", "none"])

    def test_footage_can_keep_the_overlays_above_it_when_the_beat_asks(self):
        d = copy.deepcopy(CENTERED)
        d["beats"][1]["keep_overlays"] = True
        rows, _, _ = plan_to_rows(HybridPlan.from_dict(d))
        self.assertTrue(all("cover_ui" not in r.params for r in rows if r.layer_type == "media_full"))
        rows, _, _ = plan_to_rows(self.p())
        self.assertTrue(all(r.params.get("cover_ui") for r in rows if r.layer_type == "media_full"))

    def test_a_map_footage_beat_gets_its_supporting_card_on_the_map(self):
        rows, line_map, _ = plan_to_rows(self.p())
        card = next(r for r in rows if r.layer_id == "b3_support")
        self.assertEqual((card.layer_type, card.asset_path, card.geo_ref, card.label_text, card.t_start), ("pip", "stock_image:glacier", "Nairobi", "GLACIER", 17.0))
        self.assertLessEqual(card.t_end, 24.0 - 0.4)
        self.assertEqual(line_map[card.line], "beat b3 · supporting card")

    def test_after_footage_ends_with_the_next_map_beat_even_when_that_beat_has_a_card(self):
        from hybrid.compile import layer_end
        d = copy.deepcopy(CENTERED)
        d["duration"] = 30.0
        d["beats"].append({"id": "b4", "mode": "map", "start": 24, "end": 30, "purpose": "and on", "layers": [{"id": "x", "type": "marker", "t": 25, "place": "Mombasa", "label": "MOMBASA"}]})
        plan = HybridPlan.from_dict(d)
        fill = next(l for l in plan.beats[0].layers if l.id == "kenya")
        self.assertEqual(plan.beats[2].mode, "map_footage")
        self.assertLess(layer_end(plan, plan.beats[0], fill), plan.duration)
        self.assertAlmostEqual(layer_end(plan, plan.beats[0], fill), plan.beats[2].end, places=2)

    def test_after_footage_with_no_footage_ahead_leaves_with_its_beat_not_at_the_end_of_the_video(self):
        from hybrid.compile import layer_end
        d = copy.deepcopy(CENTERED)
        d["beats"][2]["layers"] = [{"id": "m", "type": "marker", "t": 16.5, "place": "Mombasa", "label": "MOMBASA", "until": "after_footage"}]
        d["beats"][2]["mode"] = "map"
        d["beats"][2].pop("support", None)
        d["duration"] = 40.0
        d["beats"].append({"id": "b4", "mode": "map", "start": 24, "end": 40, "purpose": "later", "layers": [{"id": "x", "type": "marker", "t": 30, "place": "Kenya", "label": "KENYA"}]})
        plan = HybridPlan.from_dict(d)
        lay = plan.beats[2].layers[0]
        self.assertEqual(layer_end(plan, plan.beats[2], lay), plan.beats[2].end)   # no footage after it: not held to 40 s

    def test_a_card_waits_for_the_camera_to_land_so_it_is_not_dragged_off_the_screen(self):
        d = copy.deepcopy(CENTERED)
        d["beats"][2]["camera"] = [{"action": "fly_to", "place": "Nairobi", "frame": "region", "t": 16.3, "dur": 2.4}]
        rows, _, _ = plan_to_rows(HybridPlan.from_dict(d))
        card = next(r for r in rows if r.layer_id == "b3_support")
        self.assertAlmostEqual(card.t_start, 16.3 + 2.4 + 0.25, places=2)
        d["beats"][2]["camera"][0]["t"] = 21.0                       # a move so late that waiting would leave the card no time: it keeps its own time
        rows, _, _ = plan_to_rows(HybridPlan.from_dict(d))
        self.assertAlmostEqual(next(r for r in rows if r.layer_id == "b3_support").t_start, 17.0, places=2)

    def test_a_late_card_is_brought_forward_and_a_card_on_a_plain_map_beat_is_refused(self):
        d = copy.deepcopy(CENTERED)
        d["beats"][2]["support"]["t"] = 23.2
        rows, _, notes = plan_to_rows(HybridPlan.from_dict(d))  # spoken in the last words of its beat: brought forward, not refused
        self.assertLess(next(r for r in rows if r.layer_id == "b3_support").t_start, 23.2)
        self.assertTrue(any("brought forward" in n for n in notes))
        d = copy.deepcopy(CENTERED)
        d["beats"][2]["mode"] = "map"
        self.assertTrue(any("plain map beat has no supporting card" in x for x in validate_plan(HybridPlan.from_dict(d))))
        d = copy.deepcopy(CENTERED)
        d["beats"][2].pop("support")
        self.assertTrue(any("needs a supporting card" in x for x in validate_plan(HybridPlan.from_dict(d))))

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_the_whole_plan_compiles_and_the_renderer_accepts_it(self):
        res = compile_plan(self.p(), width=1920, height=1080, fps=30)
        ev = {e["id"]: e for e in res.spec["events"]}
        self.assertEqual((ev["b2_c1"]["t_in"], ev["b2_c2"]["t_out"]), (8.75, 15.25))
        self.assertEqual(ev["b3_support"]["type"], "pip")
        self.assertEqual(res.report.errors, [])

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_no_transition_sound_reaches_the_sound_plan(self):
        from pakmap.app_integration import plan_pakmap_sound
        from test_pakmap_audio import make_catalog

        res = compile_plan(self.p(), width=1920, height=1080, fps=30)
        with tempfile.TemporaryDirectory() as d:
            sound = plan_pakmap_sound(res.result, catalog=make_catalog(Path(d)))
        self.assertNotIn("soft_transition", [c.sound for c in sound.cues])

    def _two_footage_beats(self):
        d = copy.deepcopy(CENTERED)
        d["beats"] = [
            {"id": "m1", "mode": "map", "start": 0, "end": 8, "camera": [{"action": "start", "place": "Kenya", "frame": "country"}], "layers": [], "geo_intent": "x"},
            {"id": "f1", "mode": "footage", "start": 8, "end": 14, "footage": {"clips": [{"asset": "a.jpg"}]}, "footage_intent": "x"},
            {"id": "f2", "mode": "footage", "start": 14, "end": 20, "footage": {"clips": [{"asset": "b.jpg"}, {"asset": "c.jpg"}]}, "footage_intent": "y", "transition_sound": "soft_transition"},
            {"id": "m2", "mode": "map", "start": 20, "end": 24, "layers": [], "geo_intent": "z"}]
        return HybridPlan.from_dict(d)

    def test_footage_straight_after_footage_dissolves_over_it_and_never_over_the_map(self):
        # found by the real Director: two experience beats in a row made the renderer refuse two overlapping full-screen clips
        rows, _, _ = plan_to_rows(self._two_footage_beats())
        clips = [r for r in rows if r.layer_type == "media_full"]
        self.assertEqual([r.params.get("xfade_prev", False) for r in clips], [False, True, True])
        self.assertAlmostEqual(clips[0].t_end - clips[1].t_start, 0.5, places=6)       # exactly one dissolve of overlap
        self.assertEqual([r.sfx for r in clips], ["none", "none", "none"])               # a hand-over never announces itself, even if the beat asked for a sound

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_that_plan_passes_the_renderers_own_rules(self):
        res = compile_plan(self._two_footage_beats(), width=1920, height=1080, fps=30)
        self.assertEqual(res.report.errors, [])
        ev = [e for e in res.spec["events"] if e["type"] == "media_full"]
        self.assertEqual([bool(e.get("xfade_prev")) for e in ev], [False, True, True])

    def test_the_sfx_column_survives_the_compiled_script(self):
        rows, _, _ = plan_to_rows(self.p())
        back, warns = parse_csv("x.csv", text=rows_to_csv(rows))
        self.assertEqual([r.sfx for r in back if r.layer_type == "media_full"], ["none", "none"])


class TestIsolation(unittest.TestCase):
    """Dependency direction: hybrid -> pakmap -> shared infrastructure. Nothing underneath imports hybrid."""

    def test_no_other_style_or_shared_module_imports_hybrid(self):
        import re

        offenders = []
        for rel in ("pakmap", "pakmap-engine", "scene_graph", "map_scene", "providers", "visual_director", "editorial", "sfx", "smart_editing.py", "video_generator.py",
                    "asset_manager.py", "project_workspace.py"):
            path = ROOT / rel
            files = [path] if path.is_file() else ([p for p in path.rglob("*") if p.suffix in (".py", ".mjs", ".js") and "node_modules" not in p.parts] if path.is_dir() else [])
            for f in files:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"^\s*(from|import)\s+hybrid\b", text, re.M) or re.search(r"from ['\"]\.\./hybrid", text):
                    offenders.append(str(f.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_hybrid_only_reaches_for_the_shared_pieces_it_should(self):
        import re

        allowed = {"hybrid", "pakmap", "visual_director", "providers", "asset_manager", "video_generator", "smart_editing", "scene_graph", "pakmap_engine", "ai_router"}
        used = set()
        for f in (ROOT / "hybrid").glob("*.py"):
            for m in re.finditer(r"^\s*(?:from|import)\s+([a-zA-Z_][\w]*)", f.read_text(encoding="utf-8"), re.M):
                used.add(m.group(1))
        stdlib = {"__future__", "copy", "json", "re", "math", "statistics", "time", "pathlib", "dataclasses", "typing", "difflib", "os", "sys", "csv", "io", "tempfile", "shutil", "hashlib", "uuid"}
        self.assertEqual(sorted(used - stdlib - allowed), [])

    def test_the_packaged_build_ships_the_prompts_and_the_engine_module(self):
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn('hybrid_*_prompt.txt', spec)
        for name in ("hybrid_director_prompt.txt", "hybrid_critic_prompt.txt"):
            self.assertTrue((ROOT / "composition_styles" / name).is_file())
        from pakmap.packaging import engine_data_files

        shipped = {Path(src).name for src, _dest in engine_data_files(ROOT)}
        self.assertIn("hybrid.mjs", shipped)             # lib/*.mjs is shipped as a rule: the new Hybrid engine module goes with it

    def test_the_director_prompt_and_critic_prompt_are_their_own_documents(self):
        for name in ("hybrid_director_prompt.txt", "hybrid_critic_prompt.txt"):
            text = (ROOT / "composition_styles" / name).read_text(encoding="utf-8")
            self.assertNotIn("PakMap", text)
            self.assertNotIn("Fact Map", text)
            self.assertNotIn("Overscaled", text)


if __name__ == "__main__":
    unittest.main()
