"""What If render 024 (2026-10-19): overlapping text and graphics, an empty opening, and the second encode of the finished video.

  whatif/overlap.py        the frame-by-frame overlap check (whatif-engine/tools/overlap_audit.mjs) and its timing repairs
  compile._opening_never_empty   the first frames carry a graphic
  app_integration.mux_narration  the drawn video copied as it is, only the sound added
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from whatif import compile as wc            # noqa: E402
from whatif import overlap as ov            # noqa: E402


def metric(value, anchor, start, end):
    return {"type": "tm_metric", "value": value, "unit": "AU", "anchor": anchor, "size": "large", "start": start, "end": end, "fade_in": 0.05, "fade_out": 0.3}


def spec_of(layers, duration=12.0):
    return {"width": 1920, "height": 1080, "fps": 30, "duration": duration, "shots": [{"id": "s1", "start": 0, "end": duration, "kind": "plate"}],
            "layers": layers, "whatif": {"notes": []}}


def clash(a, b, start, end, at="", bt=""):
    return {"a": a, "b": b, "start": start, "end": end, "a_text": at, "b_text": bt, "area": 5000, "a_type": "", "b_type": ""}


class Resolve(unittest.TestCase):
    def test_the_later_graphic_takes_over_when_the_first_has_had_its_time(self):
        s = spec_of([metric("17", "upper_left", 1.0, 6.0), metric("3.6", "upper_left", 3.0, 8.0)])
        notes = []
        self.assertEqual(ov.resolve(s, [clash(0, 1, 3.0, 6.0, "17", "3.6")], notes), 1)
        self.assertLess(s["layers"][0]["end"], 3.0)
        self.assertEqual(s["layers"][1]["start"], 3.0)
        self.assertIn("the first ends as the second comes in", notes[0])

    def test_two_that_start_together_the_second_waits(self):
        s = spec_of([metric("17", "left", 2.0, 4.0), metric("3.6", "left", 2.5, 9.0)])
        ov.resolve(s, [clash(0, 1, 2.5, 4.0)], [])
        self.assertEqual(s["layers"][0]["end"], 4.0)
        self.assertGreater(s["layers"][1]["start"], 4.0)

    def test_no_room_for_both_the_second_is_left_out(self):
        s = spec_of([metric("17", "left", 2.0, 4.0), metric("3.6", "left", 2.5, 4.5)])
        notes = []
        ov.resolve(s, [clash(0, 1, 2.5, 4.0)], notes)
        self.assertEqual([L["value"] for L in s["layers"]], ["17"])
        self.assertIn("left out", notes[0])

    def test_an_instrument_steps_back_instead_of_moving_the_graphic(self):
        clock = {"type": "tm_clock", "mode": "light", "keys": [{"t": 0, "seconds": 0}]}
        s = spec_of([clock, metric("17", "upper_left", 2.0, 6.0)])
        ov.resolve(s, [clash(0, 1, 2.0, 6.0)], [])
        self.assertEqual(s["layers"][1]["start"], 2.0)
        self.assertEqual(s["layers"][0]["mute"], [[1.85, 6.15]])
        ov.resolve(s, [clash(0, 1, 6.5, 7.0)], [])          # a second window close by joins the first: one step back, no flicker
        self.assertEqual(s["layers"][0]["mute"], [[1.85, 7.15]])


@unittest.skipUnless(shutil.which("node"), "node not available")
class RealAudit(unittest.TestCase):
    def test_the_check_finds_the_overlap_and_the_repair_leaves_none(self):
        s = spec_of([metric("17", "upper_left", 1.0, 6.0), metric("3.6", "upper_left", 3.0, 8.0), metric("9", "lower_right", 2.0, 9.0)])
        self.assertEqual(len(ov.audit(s)), 1)
        lines = []
        ov.repair_overlaps(s, log=lines.append)
        self.assertEqual(ov.audit(s), [])
        self.assertTrue(any("1 overlap(s) found frame by frame, 1 repaired" in l for l in lines), lines)
        self.assertEqual(len(s["layers"]), 3)

    def test_a_spec_with_no_overlap_is_left_exactly_as_it_was(self):
        s = spec_of([metric("17", "upper_left", 1.0, 4.0), metric("3.6", "upper_left", 4.2, 8.0)])
        import copy

        before = copy.deepcopy(s)
        ov.repair_overlaps(s, log=lambda m: None)
        self.assertEqual(s["layers"], before["layers"])

    def test_a_check_that_cannot_run_never_stops_the_video(self):
        s = spec_of([metric("17", "upper_left", 1.0, 6.0)])

        def broken(_spec):
            raise RuntimeError("no node")

        lines = []
        self.assertIs(ov.repair_overlaps(s, log=lines.append, run_audit=broken), s)
        self.assertIn("overlap check skipped", lines[0])

    def test_engine_unit_tests(self):
        r = subprocess.run(["node", "--test", "test/overlap.test.mjs"], cwd=ROOT / "whatif-engine", capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])


class Opening(unittest.TestCase):
    def test_an_empty_opening_gets_the_first_graphic_early(self):
        layers = [{"type": "tm_clock"}, metric("230", "upper_left", 1.22, 5.2)]
        notes = []
        wc._opening_never_empty(layers, notes)
        self.assertEqual(layers[1]["start"], wc.OPENING_START_S)
        self.assertIn("never opens on an empty screen", notes[0])

    def test_a_graphic_already_there_or_none_soon_changes_nothing(self):
        for start in (0.4, 4.0):
            layers = [metric("230", "upper_left", start, 6.0)]
            wc._opening_never_empty(layers, [])
            self.assertEqual(layers[0]["start"], start)


class _WithFfmpeg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ff = str(ROOT / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
        if not Path(cls.ff).is_file():
            cls.ff = shutil.which("ffmpeg")
        if not cls.ff:
            raise unittest.SkipTest("ffmpeg not available")


class Mux(_WithFfmpeg):
    def test_the_picture_is_copied_and_the_sound_added(self):
        from whatif.app_integration import mux_narration

        d = Path(tempfile.mkdtemp())
        v, a, out = d / "v.mp4", d / "a.wav", d / "out" / "final.mp4"
        subprocess.run([self.ff, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=3", "-c:v", "libx264", "-crf", "18",
                        "-pix_fmt", "yuv420p", str(v)], check=True)
        subprocess.run([self.ff, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(a)], check=True)
        mux_narration(v, a, out, 3.0, ffmpeg=self.ff)
        probe = subprocess.run([self.ff.replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                                "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
        self.assertIn("h264,video", probe)
        self.assertIn("aac,audio", probe)
        # the video stream is the drawn one, byte for byte (no second encode)
        def packets(p):
            return subprocess.run([self.ff, "-v", "error", "-i", str(p), "-map", "0:v", "-c", "copy", "-f", "framemd5", "-"], capture_output=True, text=True).stdout.split("\n")[-5:]
        self.assertEqual(packets(v), packets(out))
        self.assertFalse((out.parent / "final.part.mp4").exists())

    def test_a_failed_mux_leaves_no_file_and_raises(self):
        from whatif.app_integration import mux_narration

        d = Path(tempfile.mkdtemp())
        with self.assertRaises(RuntimeError):
            mux_narration(d / "missing.mp4", d / "missing.wav", d / "final.mp4", 3.0, ffmpeg=self.ff)
        self.assertEqual(list(d.iterdir()), [])


class Wiring(unittest.TestCase):
    def test_generate_repairs_overlaps_before_the_spec_is_rendered_and_muxes_without_re_encoding(self):
        src = (ROOT / "whatif" / "app_integration.py").read_text(encoding="utf-8")
        i, j = src.index("repair_overlaps(spec, log)"), src.index('(work / "whatif_spec.json").write_text')
        self.assertLess(i, j)
        self.assertLess(src.index("mux_narration(silent, Path(narration), output_path"), src.index("_export_via_existing_renderer(SimpleNamespace"))

    def test_the_audit_tool_ships(self):
        from whatif.packaging import data_files

        self.assertTrue(any(s.endswith(str(Path("tools") / "overlap_audit.mjs")) for s, _d in data_files(ROOT)))


class LowResClips(_WithFfmpeg):
    """Render 024's Flow clips were 640x360 in a 1080p video: the compiler marks them so the cutter enlarges them with Lanczos + unsharp."""

    def _clip(self, w, h):
        d = Path(tempfile.mkdtemp())
        f = d / f"c{w}x{h}.mp4"
        subprocess.run([self.ff, "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30:duration=1", "-pix_fmt", "yuv420p", str(f)], check=True)
        return str(f)

    def test_a_360p_clip_is_marked_and_a_1080p_one_is_not(self):
        self.assertTrue(wc._low_res(self._clip(640, 360), 1080))
        self.assertFalse(wc._low_res(self._clip(1920, 1080), 1080))
        self.assertFalse(wc._low_res(self._clip(1280, 720), 1080))       # 720p is enlarged 1.5x only: Lanczos alone
        self.assertFalse(wc._low_res("/no/such/clip.mp4", 1080))

    def test_the_app_notes_a_360p_flow_profile_once(self):
        import types

        import app

        lines = []
        fake = types.SimpleNamespace(_default_video_profile=lambda: {"model": "abra", "resolution": "360p"}, _append_log=lines.append)
        app.VideoGeneratorApp._note_low_res_flow_video(fake)
        app.VideoGeneratorApp._note_low_res_flow_video(fake)
        self.assertEqual(len(lines), 1)
        self.assertIn("720p", lines[0])
        fake2 = types.SimpleNamespace(_default_video_profile=lambda: {"model": "abra", "resolution": "720p"}, _append_log=lines.append)
        app.VideoGeneratorApp._note_low_res_flow_video(fake2)
        self.assertEqual(len(lines), 1)


class EmptyClips(_WithFfmpeg):
    """Render 024, 1:51-2:00: a NASA clip that was black from start to end showed 8.8 s of black under its text."""

    def _clip(self, vf):
        d = Path(tempfile.mkdtemp())
        f = d / "c.mp4"
        subprocess.run([self.ff, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=3", "-vf", vf, "-pix_fmt", "yuv420p", str(f)], check=True)
        return str(f)

    def test_a_black_clip_is_empty_and_a_dark_star_field_is_not(self):
        self.assertTrue(wc._empty_clip(self._clip("null")))
        stars = ",".join(f"drawbox=x={(i * 97) % 620}:y={(i * 53) % 340}:w=3:h=3:color=white:t=fill" for i in range(40))
        self.assertFalse(wc._empty_clip(self._clip(stars)))
        self.assertFalse(wc._empty_clip("/no/such/clip.mp4"))

    def test_the_compiler_gives_a_black_clip_its_fallback(self):
        from whatif.planner import Shot, ShotPlan

        black = self._clip("null")
        shot = Shot(id="s1", start=0.0, end=4.0, kind="video", text="The launch at dawn.", file=black, asset="nasa_video:launch")
        plan = ShotPlan(shots=[shot], layers=[], duration=4.0, title="t")
        spec = wc.compile_spec(plan, media_dir=None)
        self.assertNotEqual(spec["shots"][0]["kind"], "video")
        self.assertTrue(any("black from start to end" in n for n in spec["whatif"]["notes"]), spec["whatif"]["notes"])


if __name__ == "__main__":
    unittest.main()
