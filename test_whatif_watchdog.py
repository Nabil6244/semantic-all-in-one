"""A frozen page never hangs a What If render: render #016 waited 11 minutes on one picture (and would have waited 6 hours).
The frame watchdog restarts the browser and the render goes on from the frame that froze. Real Chromium; skipped without one."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _can_render() -> bool:
    try:
        from providers.flow.engine_manager import _find_flow_engine_dir
        from providers.playwright_chromium import is_playwright_chromium_installed, system_chrome_available

        has_playwright = (Path(_find_flow_engine_dir()) / "node_modules" / "playwright").is_dir()
        return has_playwright and (is_playwright_chromium_installed() or system_chrome_available())
    except Exception:
        return False


SPEC = {"width": 640, "height": 360, "fps": 10, "duration": 2.0, "look": {}, "layers": [], "whatif": {"title": "t", "notes": []},
        "shots": [{"id": "s1", "start": 0.0, "end": 2.0, "kind": "plate", "tint": "cool", "title": "TEST", "sub": "", "cite": ["DIAGRAM", ""]}]}


@unittest.skipUnless(_can_render(), "needs Playwright's Chromium (or Chrome) installed; never downloaded by a test")
class FrameWatchdog(unittest.TestCase):
    def test_a_frozen_frame_restarts_the_browser_and_every_frame_is_made(self):
        from map_scene.render import _ffmpeg
        from whatif.engine_runner import render_spec

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WHATIF_TEST_FREEZE_AT": "5", "WHATIF_FRAME_TIMEOUT_MS": "4000"}):
            out = Path(d) / "out.mp4"
            # 20 frames take seconds: a hang fails here in 4 min with the engine's own error, not the runner's 20-min cut-off
            outcome = render_spec(dict(SPEC, media_dir=d), out, log=lambda m: None, timeout_s=240)
            frames = subprocess.run([str(Path(_ffmpeg()).with_name("ffprobe")) if Path(_ffmpeg()).is_file() else "ffprobe", "-v", "error",
                                     "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                                    capture_output=True, text=True).stdout.strip().strip(",")
        self.assertEqual(frames, "20")
        self.assertTrue(any("restarting the browser and continuing from this frame" in w for w in outcome.warnings or []), outcome.warnings)


class PartRanges(unittest.TestCase):
    """The parallel render's split: whole video covered once, joins only at shot cuts, no tiny parts."""

    def test_parts_cut_at_shot_starts_and_cover_every_frame(self):
        from whatif.engine_runner import MIN_PART_FRAMES, part_ranges

        shots = [{"start": t} for t in (0, 31.3, 58.0, 97.7, 140.2, 171.9, 233.4, 260.0)]
        r = part_ranges({"fps": 30, "duration": 300.0, "shots": shots}, 3)
        self.assertEqual((r[0][0], r[-1][1]), (0, 9000))
        self.assertTrue(all(a[1] == b[0] for a, b in zip(r, r[1:])), r)
        cut_frames = {int(round(s["start"] * 30)) for s in shots}
        self.assertTrue(all(a in cut_frames for a, _b in r[1:]), r)
        self.assertTrue(all(b - a >= MIN_PART_FRAMES for a, b in r), r)

    def test_a_short_video_is_one_part(self):
        from whatif.engine_runner import part_ranges

        self.assertEqual(part_ranges({"fps": 30, "duration": 40.0, "shots": [{"start": 0}, {"start": 20}]}, 4), [[0, 1200]])

    def test_the_parts_setting_wins(self):
        from whatif.engine_runner import render_parts

        with mock.patch.dict(os.environ, {"WHATIF_RENDER_PARTS": "1"}):
            self.assertEqual(render_parts({"width": 1920, "height": 1080}), 1)


@unittest.skipUnless(_can_render(), "needs Playwright's Chromium (or Chrome) installed; never downloaded by a test")
class ParallelQuality(unittest.TestCase):
    def test_parts_joined_are_the_same_pictures_as_one_render(self):
        """Lossless encode (crf 0), so any difference would be in the drawing itself: there must be none."""
        from map_scene.render import _ffmpeg
        from whatif import engine_runner as er

        spec = dict(SPEC, duration=3.0, crf=0, shots=[dict(SPEC["shots"][0], end=1.5), dict(SPEC["shots"][0], id="s2", start=1.5, end=3.0, title="TWO")])
        with tempfile.TemporaryDirectory() as d:
            spec["media_dir"] = d
            er._render_once(dict(spec), Path(d) / "one.mp4", log=lambda m: None)
            er._render_parallel(spec, Path(d) / "parts.mp4", [[0, 15], [15, 30]], progress=None, cancel_check=None, log=lambda m: None,
                                timeout_s=600, software_gl=False)
            md5 = lambda f: [ln.split(",")[-1].strip() for ln in subprocess.run([_ffmpeg(), "-v", "error", "-i", str(f), "-f", "framemd5", "-"],
                                                                                 capture_output=True, text=True).stdout.splitlines() if not ln.startswith("#")]
            one, parts = md5(Path(d) / "one.mp4"), md5(Path(d) / "parts.mp4")
        self.assertEqual(len(one), 30)
        self.assertEqual(one, parts)


if __name__ == "__main__":
    unittest.main()
