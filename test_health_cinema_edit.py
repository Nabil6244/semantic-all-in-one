"""Health Cinema high-end editing layer: pure-function motion/transitions, director rules, deterministic shots, cache keys, QC (no Three.js / network needed)."""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image, ImageChops
from health_cinema.edit import director, gfx, grade, media, motion as M, pipeline, qc, shots as S, transitions as T, typo
from health_cinema.planner import Scene

W, H = 640, 360
def sc(no, a, b, text, kind="text_card", visual=None, sents=None):
    return Scene(no, a, b, text, kind, "medical_cinema", visual=visual or {"text": text, "beats": [{"text": text, "t0": 0.0}]}, sentences=sents or [{"text": text, "start": a, "end": b}])

class Motion(unittest.TestCase):
    def test_ease_bounds_and_camera_continuity(self):
        for f in M.EASE.values(): self.assertAlmostEqual(f(0), 0, 2); self.assertAlmostEqual(f(1), 1, 2)
        cam = M.camera_path("push_in", 4.0, 0.15, (0.4, 0.5), 0.5)
        zs = [cam(t / 24.0 - 0.5)[0] for t in range(0, 24 * 5)]
        self.assertTrue(all(b >= a - 1e-9 for a, b in zip(zs, zs[1:])))
        self.assertLess(max(abs(b - a) for a, b in zip(zs, zs[1:])), 0.01)      # no zoom jumps
    def test_crop_stays_inside(self):
        for cx in (0, 0.5, 1): x0, y0, x1, y1 = M.crop_extent(1000, 500, 1.3, cx, cx); self.assertTrue(0 <= x0 and x1 <= 1000 and 0 <= y0 and y1 <= 500)

class Trans(unittest.TestCase):
    def test_all_transitions_endpoints_and_size(self):
        a, b = Image.new("RGB", (W, H), (200, 20, 20)), Image.new("RGB", (W, H), (20, 20, 200))
        for n in T.NAMES:
            tr = T.Transition(n, 12); o0 = T.apply(tr, a, b, 0.02); o1 = T.apply(tr, a, b, 0.98); self.assertEqual(o0.size, (W, H))
            if n != "cut":
                self.assertLess(sum(ImageChops.difference(o0, a).convert("L").getextrema()), 120, n); self.assertLess(sum(ImageChops.difference(o1, b).convert("L").getextrema()), 150, n)
    def test_deterministic(self):
        a, b = Image.new("RGB", (W, H), (90, 10, 10)), Image.new("RGB", (W, H), (10, 10, 90)); tr = T.Transition("bar_wipe", 12)
        self.assertEqual(T.apply(tr, a, b, 0.4).tobytes(), T.apply(tr, a, b, 0.4).tobytes())

class Typo(unittest.TestCase):
    def test_phrases_cover_sentence_and_snap_to_pause(self):
        ph = typo.build_phrases([{"text": "Every 40 seconds, someone in the United States has a stroke.", "start": 0.0, "end": 4.5}], [(1.34, 1.59)])
        self.assertAlmostEqual(ph[0].t1, 1.465, 2); self.assertEqual(" ".join(p.text for p in ph), "Every 40 seconds, someone in the United States has a stroke.")
        self.assertTrue(all(b >= a for p in ph for _, a, b in p.words))
    def test_emphasis_prefers_numbers(self): self.assertEqual(typo.emphasis_indices("Up to 80% of strokes are preventable".split(), 1), {2})

class Director(unittest.TestCase):
    def scenes(self):
        return [sc(1, 0, 6.2, "Every 40 seconds, someone in the United States has a stroke.", "counter_card", {"interval": 40, "unit": "seconds", "context": "Every 40 seconds, someone in the United States has a stroke.", "event": "strokes"}),
                sc(2, 6.2, 12.3, "Up to 80% of strokes are preventable.", "bar_card", {"value": 80.0, "qualifier": "Up to", "context": "Up to 80% of strokes are preventable."}),
                sc(3, 12.3, 20.0, "He sits and reads. He looks up. He waits for the afternoon to end.", "footage", {"path": "/x/a.mp4"}),
                sc(4, 20.0, 24.0, "His left side never fully recovers.", "footage", {"path": "/x/b.mp4"}),
                sc(5, 24.0, 27.0, "What happened was not eye strain.")]
    def test_plan_is_contiguous_and_varied(self):
        p = director.build(self.scenes(), (255, 96, 80), src_duration=lambda path: 30.0); sh = p["shots"]
        self.assertEqual(sh[0]["t0"], 0.0)
        for a, b in zip(sh, sh[1:]): self.assertAlmostEqual(a["t1"], b["t0"], 3)
        moves = [s["camera"]["move"] for s in sh if s["kind"] == "footage"]; self.assertTrue(all(a != b for a, b in zip(moves, moves[1:])))
        self.assertEqual(len(p["transitions"]), len(sh) - 1); self.assertTrue(any(t.name == "cut" for t in p["transitions"]))
        self.assertLessEqual(len(p["cues"]), 6)
    def test_long_footage_scene_is_split_with_a_closer_second_shot(self):
        p = director.build(self.scenes(), (255, 96, 80), src_duration=lambda path: 30.0); f = [s for s in p["shots"] if s["scene_no"] == 3]
        self.assertEqual(len(f), 2); self.assertGreater(f[1]["camera"].get("base", 1.0), f[0]["camera"].get("base", 1.0)); self.assertEqual(f[0]["src_in"] + 0 < f[1]["src_in"], True)
    def test_plan_qc_flags_missing_source_and_has_no_crash(self):
        p = director.build(self.scenes(), (255, 96, 80), src_duration=lambda path: 30.0); codes = {c["code"] for c in qc.plan_checks(p)}; self.assertIn("figure_without_source", codes)

class Shots(unittest.TestCase):
    def test_data_shots_deterministic_and_nonblank(self):
        spec = {"kind": "counter", "t0": 0, "t1": 6, "accent": (255, 96, 80), "seed": 1, "gfx": {"interval": 40, "unit": "seconds", "context": "Someone has a stroke.", "event": "strokes"}}
        a = S.KINDS["counter"](spec, W, H, 12); b = S.KINDS["counter"](spec, W, H, 12)
        fa = [a.frame(t, 0) for t in (0.5, 3.0)]; fb = [b.frame(t, 0) for t in (0.5, 3.0)]
        self.assertEqual([x.tobytes() for x in fa], [x.tobytes() for x in fb]); self.assertNotEqual(fa[0].tobytes(), fa[1].tobytes()); self.assertGreater(max(fa[1].convert("L").getextrema()), 120)
    def test_cache_key_ignores_absolute_time_but_not_content(self):
        s1 = {"kind": "bar", "t0": 6.0, "t1": 12.0, "gfx": {"value": 80}, "accent": [1, 2, 3], "scene_no": 2, "why": ["x"]}; s2 = dict(s1, t0=9.0, t1=15.0, scene_no=3); s3 = dict(s1, gfx={"value": 70})
        k = lambda s: pipeline.shot_key(s, 1920, 1080, "c"); self.assertEqual(k(s1), k(s2)); self.assertNotEqual(k(s1), k(s3)); self.assertNotEqual(k(s1), pipeline.shot_key(s1, 1280, 720, "c"))
    def test_render_shot_exact_frames(self):
        d = Path(tempfile.mkdtemp()); spec = {"kind": "statement", "t0": 0, "t1": 1.0, "accent": (255, 96, 80), "seed": 1, "gfx": {"beats": [{"text": "Hello there", "t0": 0.0}]}}
        out = d / "s.mp4"; S.render_shot(spec, W, H, out, 12); r = media.read_frames_exact(str(out), W, H, 0, 24 + 24); self.assertEqual(len(list(r)), 48)

class Grade(unittest.TestCase):
    def test_exposure_gain_bounds_and_grain_deterministic(self):
        self.assertEqual(grade.exposure_gain(0.01), 1.45); self.assertEqual(grade.exposure_gain(0.9), 0.75)
        im = Image.new("RGB", (W, H), (100, 100, 100)); self.assertEqual(grade.grain(im, 3).tobytes(), grade.grain(im, 3).tobytes())

if __name__ == "__main__": unittest.main()
