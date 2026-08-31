"""
Flow no longer accepts a requested duration (Google dropped videoLengthSeconds
from the video-generation endpoint — see flow-engine/lib/flow-api.js and
flow-engine/test/video-duration.test.js for the request-shape side of this).

This file covers the render-layer half of that cleanup: a delivered Flow clip
that is longer (or shorter) than the scene needs must be trimmed/looped by the
renderer, never regenerated. `_render_scene_clip` never imports or calls any
Flow code — it only ever receives an already-downloaded local file — so "no
regeneration on a duration mismatch" is structurally guaranteed here, and the
tripwire below proves it rather than assuming it.

No Flow API calls, no network, no credits: the "delivered clip" is a local
ffmpeg testsrc pattern standing in for a real (cached) Flow download, since
the code path is provider-agnostic once it holds a video file on disk.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import video_generator as vg
from providers.media_clip.ffmpeg_clip import probe_duration

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_test_clip(path: Path, seconds: float, fps: int = 12) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=size=320x180:rate={fps}:duration={seconds}",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


class _NoFlowImports:
    """Tripwire: fail the test if anything under this block imports Flow code.

    Duration mismatches must be an editing decision, not a generation one —
    this proves _render_scene_clip touches no Flow module while trimming.
    """

    BLOCKED_PREFIXES = ("providers.flow", "flow_engine")

    def __enter__(self):
        self._blocked = [
            name for name in list(sys.modules)
            if any(name == p or name.startswith(p + ".") for p in self.BLOCKED_PREFIXES)
        ]
        for name in self._blocked:
            sys.modules.pop(name, None)
        self._orig_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def guarded_import(name, *args, **kwargs):
            if any(name == p or name.startswith(p + ".") for p in self.BLOCKED_PREFIXES):
                raise AssertionError(f"unexpected import of Flow module during render/trim: {name}")
            return self._orig_import(name, *args, **kwargs)

        if isinstance(__builtins__, dict):
            __builtins__["__import__"] = guarded_import
        else:
            __builtins__.__import__ = guarded_import
        return self

    def __exit__(self, *exc):
        if isinstance(__builtins__, dict):
            __builtins__["__import__"] = self._orig_import
        else:
            __builtins__.__import__ = self._orig_import


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestFlowClipIsTrimmedNotRegenerated(unittest.TestCase):
    """A delivered clip longer than the scene needs gets cut down by the
    renderer alone — the over-length is an editing fact, not a signal to
    call Flow again."""

    def test_a_longer_clip_is_trimmed_to_the_scene_duration(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "delivered.mp4"
            out = tmp_path / "scene_001.mp4"
            # Stand-in for "Flow generated 8.0s but the scene only needs 1.5s".
            _make_test_clip(source, seconds=3.0)

            scene_duration = 1.5
            fps = 12
            with _NoFlowImports():
                vg._render_scene_clip(
                    img_path=source,
                    out_path=out,
                    duration=scene_duration,
                    width=320,
                    height=180,
                    fps=fps,
                    zoom=False,
                    zoom_in=True,
                    zoom_amount=0.10,
                )

            self.assertTrue(out.is_file(), "renderer must produce a trimmed clip, not fail")
            measured = probe_duration(str(out))
            self.assertIsNotNone(measured)
            expected = round(scene_duration * fps) / fps  # exact-frame-count rounding in _render_scene_clip
            self.assertAlmostEqual(measured, expected, delta=0.15)

    def test_a_shorter_clip_is_looped_to_fill_the_scene_not_regenerated(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "delivered.mp4"
            out = tmp_path / "scene_001.mp4"
            # Stand-in for "Flow generated 2.0s but the scene needs 4.0s".
            _make_test_clip(source, seconds=2.0)

            scene_duration = 4.0
            fps = 12
            with _NoFlowImports():
                vg._render_scene_clip(
                    img_path=source,
                    out_path=out,
                    duration=scene_duration,
                    width=320,
                    height=180,
                    fps=fps,
                    zoom=False,
                    zoom_in=True,
                    zoom_amount=0.10,
                )

            self.assertTrue(out.is_file())
            measured = probe_duration(str(out))
            self.assertIsNotNone(measured)
            expected = round(scene_duration * fps) / fps
            self.assertAlmostEqual(measured, expected, delta=0.15)


if __name__ == "__main__":
    unittest.main()
