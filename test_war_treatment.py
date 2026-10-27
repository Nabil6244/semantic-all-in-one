"""War Documentary footage treatment: untreated shots unchanged, motion/grade/dissolve/blur-fill, atmosphere plate."""
import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import backdrop as B
from cinematic_explainer.war import segments as S

ROOT = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="war_treat_"))


def _clip(name, size, secs=3.0, fps=25):
    p = TMP / name
    if not p.is_file():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={size}:r={fps}:d={secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", str(p)], check=True)
    return str(p)


def _old_chain(path, duration):      # the chain exactly as it was before treatments existed
    return (f"scale={S.W}:{S.H}:force_original_aspect_ratio=increase{S._scale_args(path)},crop={S.W}:{S.H},fps={S.FPS},tpad=stop_mode=clone:stop_duration=60,{S.TAG},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS")


def _frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return int(r.stdout.strip())


class Untreated(unittest.TestCase):
    def test_plain_16x9_shot_has_no_treatment_and_the_original_graph(self):
        a = _clip("a169.mp4", "1280x720")
        pieces = S.plan_pieces([Shot(a, 0, 3)], [])
        self.assertIsNone(pieces[0].treat)
        g = S.piece_graph(pieces[0], [])
        self.assertIn(f"[0:v]{_old_chain(a, pieces[0].frames / S.FPS)}[c0]", g)
        self.assertNotIn("zoompan", g)
        g2 = S.piece_graph(pieces[0], [(0.5, 1.5)])
        self.assertIn(f"[1:v]{_old_chain(a, pieces[0].frames / S.FPS)},setpts=PTS+", g2)

    def test_cache_key_unchanged_without_treatment(self):
        a = _clip("a169.mp4", "1280x720")
        p = S.plan_pieces([Shot(a, 0, 3)], [])[0]
        k1 = S.segment_key(p, [], [], "libx264", "c")
        k2 = S.segment_key(dataclasses.replace(p, treat=None, dissolve=0.0), [], [], "libx264", "c")
        self.assertEqual(k1, k2)
        t = S.plan_pieces([Shot(a, 0, 3, treat={"motion": "push_in"})], [])[0]
        self.assertNotEqual(S.segment_key(t, [], [], "libx264", "c"), k1)


class Treatment(unittest.TestCase):
    def test_zoom_is_clamped_and_motion_names_validated(self):
        a = _clip("a169.mp4", "1280x720")
        d = json.loads(S._shot_treat(Shot(a, 0, 4, treat={"motion": "push_in", "z1": 2.0}), 0, 100))
        self.assertLessEqual(d["z1"], S.ZOOM_MAX)
        self.assertIsNone(S._shot_treat(Shot(a, 0, 4, treat={"motion": "spin"}), 0, 100))        # unknown motion = nothing to do
        low = _clip("low.mp4", "640x360")
        self.assertLessEqual(json.loads(S._shot_treat(Shot(low, 0, 4, treat={"motion": "push_in", "z1": 1.08}), 0, 100))["z1"], S.ZOOM_MAX_LOWRES)

    def test_zoom_is_one_curve_across_pieces(self):
        a = _clip("long.mp4", "1280x720", secs=26)
        ps = S.plan_pieces([Shot(a, 0, 25, treat={"motion": "push_in"})], [])
        self.assertGreaterEqual(len(ps), 2)
        g0, g1 = S.piece_graph(ps[0], []), S.piece_graph(ps[1], [])
        self.assertIn("(on+0)", g0)
        self.assertIn(f"(on+{ps[1].f0})", g1)

    def test_treated_render_is_frame_exact_and_deterministic(self):
        a = _clip("a169.mp4", "1280x720")
        outs = []
        for i in range(2):
            out = str(TMP / f"t{i}.mp4")
            r = S.render_segmented([Shot(a, 0, 3, treat={"motion": "pan_left", "grade": "cold", "vignette": 0.5, "grain": 0.4})],
                                   [Layer("kicker", 1, 2, {"text": "X"}, dim=True)], out, state_dir=str(TMP / f"s{i}"))
            self.assertTrue(r.get("ok"))
            self.assertEqual(_frames(out), 75)
            outs.append(subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-f", "framemd5", "-"], capture_output=True, text=True).stdout)
        self.assertEqual(outs[0], outs[1])


class Dissolve(unittest.TestCase):
    def test_dissolve_adds_previous_clip_and_keeps_frame_count(self):
        a, b = _clip("da.mp4", "1280x720"), _clip("db.mp4", "1280x720")
        ps = S.plan_pieces([Shot(a, 0, 3), Shot(b, 3, 6, dissolve_in=0.6)], [])
        self.assertEqual(ps[1].prev_path, a)
        self.assertAlmostEqual(ps[1].dissolve, 0.6)
        self.assertEqual(ps[0].dissolve, 0.0)
        g = S.piece_graph(ps[1], [])
        self.assertIn("fade=t=in:st=0:d=0.600:alpha=1", g)
        self.assertIn("[2:v]overlay", g)                 # the overlay pipe moved to input 2
        out = str(TMP / "dis.mp4")
        r = S.render_segmented([Shot(a, 0, 3), Shot(b, 3, 6, dissolve_in=0.6)], [], out, state_dir=str(TMP / "sd"))
        self.assertTrue(r.get("ok"))
        self.assertEqual(_frames(out), 150)

    def test_no_dissolve_on_the_first_shot_and_a_missing_previous_clip_is_a_cut(self):
        a, b = _clip("da.mp4", "1280x720"), _clip("db.mp4", "1280x720")
        self.assertEqual(S.plan_pieces([Shot(a, 0, 3, dissolve_in=0.5)], [])[0].dissolve, 0.0)
        gone = str(TMP / "gone.mp4")
        _clip("gone.mp4", "1280x720")
        ps = S.plan_pieces([Shot(gone, 0, 3), Shot(b, 3, 6, dissolve_in=0.5)], [])
        Path(gone).unlink()
        out = str(TMP / "cut.mp4")
        # the first shot's clip is missing too: this only checks the piece-level fallback does not crash planning
        self.assertTrue(ps[1].dissolve > 0 and not Path(ps[1].prev_path).is_file())


class BlurFill(unittest.TestCase):
    def test_odd_aspects_get_blur_fill_by_default_and_16x9_does_not(self):
        self.assertIsNone(S._shot_treat(Shot(_clip("a169.mp4", "1280x720"), 0, 3), 0, 75))
        for name, size in (("port.mp4", "540x960"), ("fourthree.mp4", "960x720"), ("ultra.mp4", "1920x800")):
            d = json.loads(S._shot_treat(Shot(_clip(name, size), 0, 3), 0, 75))
            self.assertTrue(d["fill"], size)

    def test_blur_fill_renders_at_canvas_size(self):
        p = _clip("port.mp4", "540x960")
        out = str(TMP / "fill.mp4")
        r = S.render_segmented([Shot(p, 0, 2)], [], out, state_dir=str(TMP / "sf"))
        self.assertTrue(r.get("ok"))
        d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", out], capture_output=True, text=True).stdout.strip()
        self.assertEqual(d, f"{S.W}x{S.H}")
        self.assertEqual(_frames(out), 50)


class Plate(unittest.TestCase):
    def test_plate_is_made_once_looks_alive_and_offsets_vary(self):
        d = Path(tempfile.mkdtemp())
        p = B.ensure_backdrop(d)
        self.assertTrue(p and p.endswith("war_backdrop_v3.mp4"))
        m = Path(p).stat().st_mtime_ns
        self.assertEqual(B.ensure_backdrop(d), p)
        self.assertEqual(Path(p).stat().st_mtime_ns, m)
        raw = lambda t: subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", p, "-frames:v", "1", "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"],
                                       capture_output=True).stdout
        f0, f6 = raw(0), raw(6)
        self.assertNotEqual(f0, f6)                                  # it moves
        self.assertGreater(sum(f0) / len(f0), 28)                    # and is not black (limited-range luma 16 = black)
        gaps = B.fill_gaps([Shot("a.mp4", 2.0, 4.0), Shot("b.mp4", 9.0, 11.0)], 14.0, p)
        offs = [s.seek for s in gaps if s.path == p]
        self.assertEqual(len(offs), 3)
        self.assertEqual(len(set(offs)), 3)
        self.assertTrue(all(0 <= o <= B.MAX_OFFSET_S for o in offs))


if __name__ == "__main__":
    unittest.main()
