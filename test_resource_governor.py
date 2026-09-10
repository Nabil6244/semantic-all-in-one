"""Resource governor, FFmpeg runner, and diagnostics tests."""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from hardware.diagnostics import build_diagnostics_report, format_diagnostics_text
from hardware.governor import get_governor, reset_governor_for_tests
from hardware.process_registry import get_registry, reset_registry_for_tests
from providers.ffmpeg_runner import default_timeout_for_duration, encode_argv, run_ffmpeg


class TestResourceGovernor(unittest.TestCase):
    def setUp(self) -> None:
        reset_governor_for_tests()
        reset_registry_for_tests()

    def test_platform_and_arch_are_separate(self) -> None:
        p = get_governor().profile()
        self.assertIn(p.system, ("Darwin", "Windows", "Linux"))
        self.assertTrue(p.architecture)
        # Never conflate arch with OS.
        if p.system == "Darwin" and p.architecture.lower() in ("arm64", "aarch64"):
            self.assertTrue(p.is_apple_silicon)
            self.assertTrue(p.is_macos)
        if p.system == "Windows":
            self.assertTrue(p.is_windows)
            self.assertFalse(p.is_apple_silicon)

    def test_budgets_are_bounded(self) -> None:
        b = get_governor().budget()
        self.assertGreaterEqual(b.download, 1)
        self.assertLessEqual(b.download, 8)
        self.assertGreaterEqual(b.ffmpeg, 1)
        self.assertLessEqual(b.ffmpeg, 4)
        self.assertGreaterEqual(b.flow_accounts, 1)
        self.assertLessEqual(b.flow_accounts, 10)
        self.assertLessEqual(b.flow_accounts, 8)  # default host should stay conservative

    def test_long_form_tightens_caps(self) -> None:
        normal = get_governor().budget(long_form=False)
        longf = get_governor().budget(long_form=True)
        self.assertLessEqual(longf.download, normal.download)
        self.assertLessEqual(longf.ffmpeg, normal.ffmpeg)
        self.assertLessEqual(longf.flow_accounts, normal.flow_accounts)

    def test_lease_acquire_release(self) -> None:
        g = get_governor()
        g.refresh_profile()
        # Force tiny ffmpeg cap via env for this process.
        old = os.environ.get("VIDEOGEN_FFMPEG_WORKERS")
        os.environ["VIDEOGEN_FFMPEG_WORKERS"] = "1"
        try:
            reset_governor_for_tests()
            g = get_governor()
            self.assertTrue(g.try_acquire("ffmpeg"))
            self.assertFalse(g.try_acquire("ffmpeg"))
            g.release("ffmpeg")
            self.assertTrue(g.try_acquire("ffmpeg"))
            g.release("ffmpeg")
        finally:
            if old is None:
                os.environ.pop("VIDEOGEN_FFMPEG_WORKERS", None)
            else:
                os.environ["VIDEOGEN_FFMPEG_WORKERS"] = old
            reset_governor_for_tests()

    def test_encode_argv_preserves_quality_by_default(self) -> None:
        args = encode_argv(quality="documentary")
        self.assertIn("libx264", args)
        self.assertIn("-crf", args)

    def test_diagnostics_report(self) -> None:
        report = build_diagnostics_report()
        self.assertEqual(report["architecture"], platform.machine() or report["architecture"])
        self.assertIn("budget", report)
        text = format_diagnostics_text(report)
        self.assertIn("PLATFORM", text)
        self.assertIn("BUDGET", text)


class TestFFmpegRunner(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") or Path("bin/ffmpeg").exists(), "ffmpeg missing")
    def test_run_ffmpeg_short_encode(self) -> None:
        reset_registry_for_tests()
        ff = str(Path("bin/ffmpeg")) if Path("bin/ffmpeg").exists() else "ffmpeg"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.mp4"
            cmd = [
                ff, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=0.3",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "0.3",
                str(out),
            ]
            result = run_ffmpeg(cmd, owner="test", media_duration_s=0.3, stall_s=60, label="unit")
            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.timed_out)
            self.assertFalse(result.stalled)
            self.assertTrue(out.exists())
            self.assertEqual(get_registry().list_active(), [])

    def test_timeout_helper_bounds(self) -> None:
        self.assertGreaterEqual(default_timeout_for_duration(1.0), 120.0)
        self.assertLessEqual(default_timeout_for_duration(10_000.0), 45 * 60)


class TestWindowsPathRobustness(unittest.TestCase):
    """Path API regressions for spaces / unicode / parentheses (cross-platform)."""

    def test_scene_clip_path_with_spaces_and_parens(self) -> None:
        import video_generator as vg
        from pathlib import PureWindowsPath

        render_dir = r"C:\Users\yousa\Videos\Project (Final)\tmp\render_clips"
        name = vg.scene_clip_filename(12)
        joined = vg.scene_clip_path(render_dir, name, path_cls=PureWindowsPath)
        self.assertEqual(joined.name, "scene_0012.mp4")
        self.assertEqual(joined.parent.name, "render_clips")
        self.assertNotIn("render_clipsscene", str(joined))
        self.assertIn("(Final)", str(joined))

    def test_concat_list_unicode_and_spaces(self) -> None:
        import video_generator as vg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "渲染 clips (final)"
            root.mkdir(parents=True)
            a = root / "scene 01.mp4"
            b = root / "scene (2).mp4"
            a.write_bytes(b"x")
            b.write_bytes(b"y")
            list_path = root / "concat_list.txt"
            vg.write_ffmpeg_concat_list([a, b], list_path)
            text = list_path.read_text(encoding="utf-8")
            self.assertIn("file '", text)
            # Relative POSIX paths — no raw Windows backslash escapes for \s.
            self.assertNotRegex(text, r"(?<!\\)\\scene")
            self.assertIn("scene 01.mp4", text.replace("\\'", "'"))
            self.assertIn("scene (2).mp4", text.replace("\\'", "'"))

    def test_long_filename_join(self) -> None:
        import video_generator as vg
        from pathlib import PureWindowsPath

        long_leaf = "A" * 80 + " documentary segment"
        work = PureWindowsPath(r"C:\Users\yousa\Downloads") / long_leaf / "tmp"
        clips = vg.render_clips_dir(work, path_cls=PureWindowsPath)
        clip = vg.scene_clip_path(clips, vg.scene_clip_filename(0), path_cls=PureWindowsPath)
        self.assertTrue(str(clip).endswith(r"\._render_clips\scene_0000.mp4"))
        self.assertNotIn("tmpscene", str(clip))


if __name__ == "__main__":
    unittest.main()
