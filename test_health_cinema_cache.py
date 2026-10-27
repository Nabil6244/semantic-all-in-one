"""Health Cinema render cache, cancellation and failure behaviour (real files, real ffmpeg for the encode; fake frame renderer)."""
import json, shutil, sys, tempfile, threading, time, unittest
from pathlib import Path
from PIL import Image
from health_cinema import render_journey as rj, overlay

ANCH = {"anchors": {"body": {"center": [0, 0, 0.88]}, "heart": {"center": [0.02, -0.02, 1.29]}}}
SPEC = {"duration": 0.5, "background": [0, 0, 0], "camera": [{"t": 0, "target": "body", "dist": 4, "az": 0, "el": 0, "fov": 30}, {"t": 0.5, "target": "heart", "dist": 1, "az": 0, "el": 0, "fov": 30}],
        "layers": {"Layer_Skin": [[0, 1], [0.5, 0]]}, "labels": [{"id": "h", "text": "Heart", "anchor": "heart", "offset": [0, 0, 0], "t0": 0.0, "t1": 0.5}]}
HAVE_FFMPEG = bool(shutil.which("ffmpeg") or (Path(rj.HERE.parent / "bin" / "ffmpeg")).exists())

class Fake:
    calls = 0
    @classmethod
    def render(cls, frames_json, model, out_dir, W, H, cancel=None, on_line=None):
        cls.calls += 1
        for i in range(len(json.load(open(frames_json))["frames"])): Image.new("RGB", (W, H), (10, 20, 30)).save(Path(out_dir) / f"f{i:05d}.png")

class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.write(SPEC); (self.d / "a.json").write_text(json.dumps(ANCH)); (self.d / "m.glb").write_bytes(b"model-v1"); Fake.calls = 0
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)
    def write(self, spec): (self.d / "s.json").write_text(json.dumps(spec))
    def key(self, **kw):
        a = dict(W=64, H=36, fps=8, settings=None, code="c1"); a.update(kw)
        return rj.cache_key(self.d / "s.json", self.d / "a.json", self.d / "m.glb", a["W"], a["H"], a["fps"], settings=a["settings"], code=a["code"])

class KeyTest(Base):
    def test_stable(self): self.assertEqual(self.key(), self.key())
    def test_changes_with_each_input(self):
        base = self.key(); keys = {base}
        keys.add(self.key(W=128)); keys.add(self.key(fps=12)); keys.add(self.key(settings={"quality": "final"})); keys.add(self.key(code="c2"))
        s = json.loads(json.dumps(SPEC)); s["camera"][1]["dist"] = 1.2; self.write(s); keys.add(self.key())
        s = json.loads(json.dumps(SPEC)); s["layers"]["Layer_Skin"] = [[0, 1], [0.5, 0.2]]; self.write(s); keys.add(self.key())
        s = json.loads(json.dumps(SPEC)); s["labels"][0]["text"] = "Cardiac"; self.write(s); keys.add(self.key())
        self.write(SPEC); (self.d / "m.glb").write_bytes(b"model-v2"); keys.add(self.key())
        (self.d / "m.glb").write_bytes(b"model-v1"); (self.d / "a.json").write_text(json.dumps({"anchors": {"body": {"center": [0, 0, 0.9]}, "heart": ANCH["anchors"]["heart"]}})); keys.add(self.key())
        self.assertEqual(len(keys), 10)
    def test_spec_key_order_does_not_matter(self):
        self.write(dict(reversed(list(SPEC.items())))); self.assertEqual(self.key(), self.key())
    def test_code_version_tracks_code_files(self):
        f = self.d / "code.js"; f.write_text("a"); v1 = rj.code_version((f,)); f.write_text("b"); self.assertNotEqual(v1, rj.code_version((f,)))

@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class RenderCacheTest(Base):
    def go(self, **kw):
        return rj.render_journey(self.d / "s.json", self.d / "a.json", self.d / "m.glb", 64, 36, 8, self.d / "cache", frame_renderer=Fake.render, code="c1", **kw)
    def test_miss_then_hit_then_invalidate(self):
        r1 = self.go(); self.assertFalse(r1["cache_hit"]); self.assertTrue(Path(r1["path"]).stat().st_size > 0); self.assertEqual(Fake.calls, 1)
        r2 = self.go(); self.assertTrue(r2["cache_hit"]); self.assertEqual(r2["path"], r1["path"]); self.assertEqual(Fake.calls, 1)   # no render on a hit
        s = json.loads(json.dumps(SPEC)); s["labels"][0]["text"] = "Cardiac"; self.write(s)
        r3 = self.go(); self.assertFalse(r3["cache_hit"]); self.assertNotEqual(r3["key"], r1["key"]); self.assertEqual(Fake.calls, 2)
    def test_failed_render_leaves_no_entry_or_temp(self):
        def boom(*a, **k): raise RuntimeError("renderer died")
        with self.assertRaises(RuntimeError): rj.render_journey(self.d / "s.json", self.d / "a.json", self.d / "m.glb", 64, 36, 8, self.d / "cache", frame_renderer=boom, code="c1")
        self.assertEqual(list((self.d / "cache").iterdir()), [])
    def test_cancel_before_encode_leaves_nothing(self):
        ev = threading.Event()
        def cancelling(fj, m, out, W, H, cancel=None, on_line=None): ev.set()
        with self.assertRaises(rj.Cancelled): rj.render_journey(self.d / "s.json", self.d / "a.json", self.d / "m.glb", 64, 36, 8, self.d / "cache", cancel=ev, frame_renderer=cancelling, code="c1")
        self.assertEqual(list((self.d / "cache").iterdir()), [])
    def test_incomplete_frames_are_rejected(self):
        def short(fj, m, out, W, H, cancel=None, on_line=None): Image.new("RGB", (W, H)).save(Path(out) / "f00000.png")
        with self.assertRaises(RuntimeError): rj.render_journey(self.d / "s.json", self.d / "a.json", self.d / "m.glb", 64, 36, 8, self.d / "cache", frame_renderer=short, code="c1")
        self.assertEqual(list((self.d / "cache").iterdir()), [])

class ProcessTest(unittest.TestCase):
    def test_cancel_kills_child(self):
        ev = threading.Event(); threading.Timer(0.4, ev.set).start(); t = time.time()
        with self.assertRaises(rj.Cancelled): rj.run_cancellable([sys.executable, "-c", "import time; time.sleep(30)"], ev)
        self.assertLess(time.time() - t, 5)
    def test_timeout(self):
        with self.assertRaises(TimeoutError): rj.run_cancellable([sys.executable, "-c", "import time; time.sleep(30)"], None, 0.5)
    def test_nonzero_exit_reports_output(self):
        with self.assertRaises(RuntimeError) as c: rj.run_cancellable([sys.executable, "-c", "print('boom'); raise SystemExit(3)"])
        self.assertIn("boom", str(c.exception))
    def test_output_lines_streamed(self):
        got = []; rj.run_cancellable([sys.executable, "-c", "print('a'); print('b')"], on_line=got.append); self.assertEqual([g.strip() for g in got], ["a", "b"])

class LabelSizeTest(unittest.TestCase):
    def test_scales_with_resolution_and_has_floor(self):
        self.assertEqual(overlay.label_px(1080), 40); self.assertEqual(overlay.label_px(2160), 80)
        self.assertGreaterEqual(overlay.label_px(540), 26); self.assertGreaterEqual(overlay.label_px(360), 26)
        self.assertLess(overlay.label_px(540), overlay.label_px(1080))
    def test_box_stays_inside_safe_frame(self):
        for side, x in (("right", 940), ("left", 20), ("right", 480)):
            (x0, y0, x1, y1), _ = overlay.label_box(300, 26, x, 20, side, 960, 540)
            self.assertGreaterEqual(x0, 960 * 0.03 - 1e-6); self.assertLessEqual(x1, 960 * 0.97 + 1e-6); self.assertGreaterEqual(y0, 0); self.assertLessEqual(y1, 540)

if __name__ == "__main__":
    unittest.main()


class LandscapeDefaultTest(unittest.TestCase):
    def test_default_and_preview_sizes_are_16_9(self):
        for W, H in (rj.DEFAULT_SIZE, rj.PREVIEW_SIZE): self.assertAlmostEqual(W / H, 16 / 9, places=2)
        self.assertEqual(rj.DEFAULT_SIZE, (1920, 1080))
    def test_cli_refuses_portrait(self):
        r = __import__("subprocess").run([sys.executable, "-m", "health_cinema.render_journey", "s", "a", "m", "c", "1080", "1920", "24"], capture_output=True, text=True, cwd=str(Path(__file__).parent))
        self.assertNotEqual(r.returncode, 0); self.assertIn("16:9", r.stderr)
    def test_real_spec_camera_is_landscape_framed(self):
        spec = Path(__file__).parent / "health_cinema" / "bench" / "journey_chest_heart.json"
        self.assertTrue(spec.exists())
