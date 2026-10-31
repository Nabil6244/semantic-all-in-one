"""Analyse once, render many (Health Cinema): the plan decides the 3D scenes once for the whole video (meaning first, at most MAX_SAME_3D uses of one
scene, never twice in a row), files are read once through the asset index, the camera path is resolved once per clip, labels and captions are drawn
without full-frame layers, and scenes render in a bounded parallel queue that keeps their order. Same pictures, less work."""
import json
import os
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

from health_cinema import asset_index, clips, engine, journey, library, overlay, planner


def sent(text, t0, t1, **hint):
    return {"text": text, "start": t0, "end": t1, "visual": "3d", **hint}


def plan(rows, ready=lambda t: True):
    from health_cinema import direction
    s = [dict(r, scene_no=i + 1) for i, r in enumerate(rows)]
    return planner.plan_directed(s, "medical_cinema", direction.dscenes_from_rows(s), ready, allow_footage=True)["scenes"]


class PlanLevel(unittest.TestCase):
    def test_a_process_sentence_in_a_heart_row_gets_its_own_scene(self):
        sc = plan([sent("Cholesterol particles settle inside the artery wall.", 0, 12, organ="heart"),
                   sent("Tiny cell fragments called platelets swarm to the spot.", 12, 24, organ="heart")])
        self.assertEqual([s.visual["template"] for s in sc if s.kind == "anatomy_3d"], ["micro:plaque:orbit", "micro:clot:orbit"])

    def test_a_skin_scene_never_stands_in_for_a_wound_inside_an_artery(self):
        sc = plan([sent("It rushes to seal the wound.", 0, 12, organ="heart")])
        self.assertNotIn("cond:wound_healing", str([s.visual for s in sc]))

    def test_one_scene_at_most_three_times_and_never_twice_in_a_row(self):
        rows = []
        for i in range(10):      # ten separate heart rows, each with a footage row between so nothing merges them
            rows.append(sent(f"Your heart keeps working, beat {i}.", i * 30, i * 30 + 12, organ="heart"))
            rows.append({"text": f"Life goes on around you {i}.", "start": i * 30 + 12, "end": i * 30 + 30, "visual": "footage", "footage": "people walking city"})
        sc = plan(rows)
        tpls = [s.visual["template"] for s in sc if s.kind == "anatomy_3d"]
        self.assertLessEqual(tpls.count("heart_journey"), planner.MAX_SAME_3D)
        for a, b in zip(sc, sc[1:]):
            if a.kind == b.kind == "anatomy_3d": self.assertNotEqual(a.visual["template"], b.visual["template"])
        self.assertTrue(any("instead" in w for s in sc for w in s.decisions))

    def test_the_card_prompt_names_the_organ_not_the_template_id(self):
        sc = plan([sent("Your stomach makes acid.", 0, 12, organ="stomach")])
        self.assertNotIn(":", sc[0].visual["organ"])


class RenderPath(unittest.TestCase):
    def test_condition_templates_load_on_the_classic_path(self):
        self.assertEqual(clips._template_spec("cond:nerve_signal:orbit")["procedural"]["kit"], "conditions")

    def test_a_video_in_a_card_row_is_skipped_not_fatal(self):
        from health_cinema import illustrations as ILL
        d = tempfile.mkdtemp(); old = os.environ.get("HEALTH_CINEMA_ILLUSTRATION_DIR"); os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = d
        try:
            (Path(d) / "x.mp4").write_bytes(b"not a picture")
            ILL.register(Path(d) / "x.mp4", id="auto_vid", topic="x", view="m", kind="mechanism", prompt="p", source="supplied")
            from health_cinema import conditions as CN
            sp = CN.build_spec("cond:asthma:orbit"); logs = []
            self.assertEqual(clips.organ_cards([{"ref": "auto_vid", "auto": True}], sp, sp["anchor_overrides"], logs.append), [])
            self.assertIn("not a picture", logs[0])
        finally:
            os.environ.pop("HEALTH_CINEMA_ILLUSTRATION_DIR") if old is None else os.environ.__setitem__("HEALTH_CINEMA_ILLUSTRATION_DIR", old)


class OnceNotPerFrame(unittest.TestCase):
    def test_the_camera_path_resolved_once_gives_the_same_frames(self):
        A = {"organ": {"min": [-0.05, -0.04, 1.0], "max": [0.05, 0.04, 1.2], "center": [0, 0, 1.1]}}
        spec = {"duration": 6.0, "camera": [{"t": 0, "target": "organ", "fill": 0.5, "az": -20, "el": 8, "fov": 30}, {"t": 6, "target": "organ", "fill": 0.8, "az": 20, "el": 10, "fov": 30}]}
        path = journey.camera_path(spec, A)
        for t in (0.0, 1.7, 3.3, 6.0):
            self.assertEqual(journey._cam_state(spec, A, t, path=path), journey._cam_state(spec, A, t))

    def test_files_are_read_once_and_again_only_when_they_change(self):
        p = Path(tempfile.mkdtemp()) / "a.json"; p.write_text('{"v": 1}')
        r0 = asset_index.STATS["json_reads"]
        self.assertEqual(asset_index.load_json(p), {"v": 1}); self.assertEqual(asset_index.load_json(p), {"v": 1})
        self.assertEqual(asset_index.STATS["json_reads"] - r0, 1)
        time.sleep(0.01); p.write_text('{"v": 22}')
        self.assertEqual(asset_index.load_json(p), {"v": 22})

    def test_template_readiness_comes_from_the_index_while_files_are_unchanged(self):
        d = Path(tempfile.mkdtemp()); f = d / "m.glb"; f.write_bytes(b"x"); calls = []
        old = asset_index.INDEX; asset_index.INDEX = d / "idx.json"; asset_index._ready = None
        try:
            chk = lambda: calls.append(1) or True
            self.assertTrue(asset_index.template_ready("t", (str(f),), chk)); self.assertTrue(asset_index.template_ready("t", (str(f),), chk))
            self.assertEqual(len(calls), 1)
            time.sleep(0.01); f.write_bytes(b"changed")
            asset_index.template_ready("t", (str(f),), chk); self.assertEqual(len(calls), 2)
        finally:
            asset_index.INDEX = old; asset_index._ready = None

    def test_captions_are_the_same_pixels_from_the_cached_crop(self):
        from PIL import Image, ImageChops
        from health_cinema import graphics
        im = Image.new("RGB", (1280, 720), (20, 30, 60))
        a = graphics.draw_caption(im.copy(), "The clot grows and grows", 720, alpha=1.0); b = overlay._caption(im.copy(), "The clot grows and grows", 1.0)
        self.assertEqual(ImageChops.difference(a, b).getbbox(), None)

    def test_a_frame_without_labels_is_returned_as_it_is(self):
        from PIL import Image
        im = Image.new("RGB", (64, 36)); self.assertIs(overlay.draw_labels(im, [], 36), im)


class Scheduler(unittest.TestCase):
    def test_parallel_render_keeps_scene_order_and_runs_3d_and_cpu_work_together(self):
        seen, active, peak = [], [0], [0]; lock = threading.Lock()
        def fake(sc, *a, **k):
            with lock: active[0] += 1; peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock: active[0] -= 1; seen.append(sc.scene_no)
            return {"path": f"/clip{sc.scene_no}.mp4", "cache_hit": False, "used_kind": sc.kind, "fallback": ""}
        old = clips.render_scene; clips.render_scene = fake
        try:
            scenes = [types.SimpleNamespace(scene_no=i, kind="anatomy_3d" if i % 3 == 0 else "footage", flags=[]) for i in range(1, 10)]
            tm = {}; ev = threading.Event()
            out = engine.render_scenes(scenes, {}, None, {}, None, Path(tempfile.mkdtemp()), "preview", ev, lambda: False, lambda m: None, lambda k, m: None, None, tm)
        finally:
            clips.render_scene = old
        self.assertEqual([r["path"] for r in out], [f"/clip{i}.mp4" for i in range(1, 10)])
        self.assertGreater(peak[0], 1); self.assertIn("scene_seconds_by_kind", tm)

    def test_a_failing_scene_stops_the_queue(self):
        def boom(sc, *a, **k): raise RuntimeError("bad scene")
        old = clips.render_scene; clips.render_scene = boom
        try:
            scenes = [types.SimpleNamespace(scene_no=i, kind="footage", flags=[]) for i in range(1, 4)]
            with self.assertRaises(RuntimeError):
                engine.render_scenes(scenes, {}, None, {}, None, Path(tempfile.mkdtemp()), "preview", threading.Event(), lambda: False, lambda m: None, lambda k, m: None, None, {})
        finally:
            clips.render_scene = old


if __name__ == "__main__":
    unittest.main()
