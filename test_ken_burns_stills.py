#!/usr/bin/env python3
"""The global Ken Burns switch has the last word on still images.

Editorial camera styles (static / hold / push_in / pull_out / subtle_drift)
only steer the kind or direction of motion. They must neither freeze a still
while the switch is ON (static / hold used to) nor make it move while the
switch is OFF (push_in / pull_out / subtle_drift used to). Video clips are
untouched. The render cache must also actually hit on a second identical run.

Behavioural: real stills are rendered through ``render_video`` and the zoom is
measured from the first and last frame of the output.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

import video_generator as vg

W, H, FPS, DUR = 320, 180, 10, 2.0


def _noise_still(path: Path) -> None:
    rng = np.random.default_rng(7)
    small = rng.integers(0, 255, (18, 32, 3), dtype=np.uint8)
    Image.fromarray(small).resize((W, H), Image.NEAREST).save(path)


def _frame(video: Path, which: str, out: Path) -> np.ndarray:
    sel = "eq(n\\,0)" if which == "first" else "eq(n\\,%d)" % (int(DUR * FPS) - 1)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select={sel}", "-vframes", "1", str(out)],
        check=True,
    )
    return np.asarray(Image.open(out).convert("L"), float)


def _best_zoom(src: np.ndarray, dst: np.ndarray) -> float:
    """Magnification of ``src`` (centre crop, scaled up) that best matches ``dst``."""
    base = Image.fromarray(src.astype("uint8"))
    best = (None, 1.0)
    for z in np.arange(1.0, 1.35, 0.01):
        cw, ch = W / z, H / z
        crop = np.asarray(
            base.resize((W, H), Image.BICUBIC, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)),
            float,
        )
        err = np.abs(crop - dst).mean()
        if best[0] is None or err < best[0]:
            best = (err, float(z))
    return best[1]


def zoom_in_and_out(video: Path, scratch: Path) -> tuple[float, float]:
    """(how far the last frame is a zoom-IN of the first, how far the first is a zoom-IN of the last)."""
    first = _frame(video, "first", scratch / "f.png")
    last = _frame(video, "last", scratch / "l.png")
    return _best_zoom(first, last), _best_zoom(last, first)


def measured_zoom(video: Path, scratch: Path) -> float:
    """Amount of motion in either direction (1.0 = none)."""
    return max(zoom_in_and_out(video, scratch))


class _RenderCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.images = cls.root / "images"
        cls.images.mkdir()
        _noise_still(cls.images / "1.png")
        cls.audio = cls.root / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={DUR}", str(cls.audio)],
            check=True,
        )
        cls.work = cls.root / "work"
        cls.work.mkdir()
        cls._cwd = os.getcwd()
        os.chdir(cls.work)
        cls._n = 0

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)
        cls._tmp.cleanup()

    def _render(self, *, zoom, camera=None, zoom_amount=0.10, edit_decision=None, images=None, cache=None) -> Path:
        type(self)._n += 1
        out = self.work / f"out_{type(self)._n}.mp4"
        kwargs = {}
        if edit_decision is not None:
            kwargs["edit_decisions_by_scene"] = {"1": edit_decision}
        if cache is not None:
            kwargs["render_cache_state_dir"] = cache
        with redirect_stdout(io.StringIO()):
            vg.render_video(
                [{"scene_number": "1", "start_time": 0.0, "script_segment": "one"}],
                DUR,
                images or self.images,
                str(self.audio),
                str(out),
                f"{W}x{H}",
                FPS,
                zoom=zoom,
                zoom_amount=zoom_amount,
                visual_transitions=False,
                camera_by_scene={"1": camera} if camera else None,
                **kwargs,
            )
        self.assertTrue(out.is_file())
        return out

    def _zoom_of(self, out: Path) -> float:
        return measured_zoom(out, self.work)

    def _edit_decision(self, camera_style: str) -> dict:
        # IMAGE_MOTION forces the editorial shot renderer (not the legacy path).
        return {
            "scene_number": "1",
            "required_duration": DUR,
            "strategy": "IMAGE_MOTION",
            "shots": [
                {
                    "shot_id": "1_s0",
                    "output_duration": DUR,
                    "source_path": str(self.images / "1.png"),
                    "camera_style": camera_style,
                    "scale": 1.0,
                    "transition_in": "cut",
                    "transition_duration": 0.0,
                }
            ],
            "source_asset": str(self.images / "1.png"),
        }


class TestKenBurnsOnStillsMove(_RenderCase):
    def test_on_static_still_moves(self):
        self.assertGreaterEqual(self._zoom_of(self._render(zoom=True, camera="static")), 1.06)

    def test_on_hold_still_moves(self):
        self.assertGreaterEqual(self._zoom_of(self._render(zoom=True, camera="hold")), 1.06)

    def test_on_push_in_zooms_in(self):
        zoomed_in, zoomed_out = zoom_in_and_out(self._render(zoom=True, camera="push_in"), self.work)
        self.assertGreaterEqual(zoomed_in, 1.06)
        self.assertLessEqual(zoomed_out, 1.01)

    def test_on_pull_out_moves_and_keeps_its_direction(self):
        zoomed_in, zoomed_out = zoom_in_and_out(self._render(zoom=True, camera="pull_out"), self.work)
        self.assertLessEqual(zoomed_in, 1.01, "a pull-out must not end tighter than it started")
        self.assertGreaterEqual(zoomed_out, 1.06, "a pull-out must start tighter than it ends")

    def test_on_static_still_moves_in_the_editorial_shot_path_too(self):
        out = self._render(zoom=True, edit_decision=self._edit_decision("static"))
        self.assertGreaterEqual(self._zoom_of(out), 1.06)

    def test_on_hold_still_moves_in_the_editorial_shot_path_too(self):
        out = self._render(zoom=True, edit_decision=self._edit_decision("hold"))
        self.assertGreaterEqual(self._zoom_of(out), 1.06)


class TestKenBurnsOffStillsStayStatic(_RenderCase):
    def test_off_push_in_stays_static(self):
        self.assertLessEqual(self._zoom_of(self._render(zoom=False, camera="push_in")), 1.01)

    def test_off_pull_out_stays_static(self):
        self.assertLessEqual(self._zoom_of(self._render(zoom=False, camera="pull_out")), 1.01)

    def test_off_subtle_drift_stays_static(self):
        self.assertLessEqual(self._zoom_of(self._render(zoom=False, camera="subtle_drift")), 1.01)

    def test_off_static_stays_static(self):
        self.assertLessEqual(self._zoom_of(self._render(zoom=False, camera="static")), 1.01)

    def test_off_push_in_stays_static_in_the_editorial_shot_path_too(self):
        out = self._render(zoom=False, edit_decision=self._edit_decision("push_in"))
        self.assertLessEqual(self._zoom_of(out), 1.01)


class TestIntensityStillDiffers(_RenderCase):
    def test_low_medium_high_keep_their_existing_amounts(self):
        low = self._zoom_of(self._render(zoom=True, camera="push_in", zoom_amount=0.05))
        med = self._zoom_of(self._render(zoom=True, camera="push_in", zoom_amount=0.10))
        high = self._zoom_of(self._render(zoom=True, camera="push_in", zoom_amount=0.16))
        self.assertLess(low, med)
        self.assertLess(med, high)
        self.assertAlmostEqual(low, 1.05, delta=0.03)
        self.assertAlmostEqual(med, 1.10, delta=0.03)
        self.assertAlmostEqual(high, 1.16, delta=0.03)


class TestVideoClipsUnchanged(_RenderCase):
    def test_video_scene_renders_identically_with_the_switch_on_or_off(self):
        vid_dir = self.root / "vid"
        vid_dir.mkdir()
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             f"testsrc2=size={W}x{H}:rate={FPS}:duration={DUR}", "-pix_fmt", "yuv420p", str(vid_dir / "1.mp4")],
            check=True,
        )

        def video_hash(zoom, camera):
            out = self._render(zoom=zoom, camera=camera, images=vid_dir)
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(out), "-map", "0:v:0", "-f", "md5", "-"],
                capture_output=True, text=True, check=True,
            )
            return r.stdout.strip()

        for camera in ("static", "push_in"):
            self.assertEqual(video_hash(True, camera), video_hash(False, camera), camera)


class TestStillCameraMotionResolution(unittest.TestCase):
    def test_switch_on_every_editorial_style_moves(self):
        for style in ("static", "hold", "push_in", "pull_out", "subtle_drift", None, "STATIC", "Push In"):
            with self.subTest(style=style):
                self.assertTrue(vg._still_camera_motion(style, index=0, zoom=True)[0])

    def test_switch_off_no_editorial_style_moves(self):
        for style in ("static", "hold", "push_in", "pull_out", "subtle_drift", None):
            with self.subTest(style=style):
                self.assertFalse(vg._still_camera_motion(style, index=0, zoom=False)[0])

    def test_editorial_direction_is_preserved(self):
        self.assertTrue(vg._still_camera_motion("push_in", index=1, zoom=True)[1])
        self.assertFalse(vg._still_camera_motion("pull_out", index=0, zoom=True)[1])
        self.assertEqual(vg._still_camera_motion("subtle_drift", index=0, zoom=True)[2], "subtle_drift")

    def test_editorial_camera_motion_itself_is_unchanged(self):
        # The editor preview / editorial plan still read the raw style meaning.
        self.assertEqual(vg._camera_motion("static", index=0, zoom=True), (False, False, "static"))
        self.assertEqual(vg._camera_motion("push_in", index=0, zoom=False)[0], True)


class TestRenderCacheActuallyHits(_RenderCase):
    def test_second_identical_render_is_a_cache_hit(self):
        state = self.root / "state"
        state.mkdir()
        self.logs = []
        real = vg._render_scene_clip
        with mock.patch.object(vg, "_render_scene_clip", wraps=real) as spy:
            out1 = self._render_quiet(state)
            first_calls = spy.call_count
            out2 = self._render_quiet(state)
            second_calls = spy.call_count - first_calls
        log = "".join(self.logs)
        self.assertNotIn("Render cache lookup skipped", log)
        self.assertEqual(first_calls, 1)
        self.assertEqual(second_calls, 0, "the second identical render must reuse the cached clip")
        self.assertTrue(out1.is_file() and out2.is_file())

    def test_changing_the_switch_is_a_cache_miss(self):
        state = self.root / "state2"
        state.mkdir()
        self.logs = []
        real = vg._render_scene_clip
        with mock.patch.object(vg, "_render_scene_clip", wraps=real) as spy:
            self._render_quiet(state, zoom=True)
            self._render_quiet(state, zoom=False)
        self.assertEqual(spy.call_count, 2, "Ken Burns ON and OFF must not share a cached clip")

    def _render_quiet(self, state, zoom=True):
        type(self)._n += 1
        out = self.work / f"cache_{type(self)._n}.mp4"
        buf = io.StringIO()
        with redirect_stdout(buf):
            vg.render_video(
                [{"scene_number": "1", "start_time": 0.0, "script_segment": "one"}],
                DUR, self.images, str(self.audio), str(out), f"{W}x{H}", FPS,
                zoom=zoom, visual_transitions=False, camera_by_scene={"1": "static"},
                render_cache_state_dir=state,
            )
        self.logs.append(buf.getvalue())
        return out


if __name__ == "__main__":
    unittest.main()
