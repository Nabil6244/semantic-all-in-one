"""Regression tests for Windows-safe render-clip paths and concat_list.txt."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory

import video_generator as vg

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_test_clip(path: Path, seconds: float = 0.25, fps: int = 12) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _make_silent_audio(path: Path, seconds: float = 0.5) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", f"{seconds}",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


class TestWindowsSceneClipJoin(unittest.TestCase):
    def test_windows_render_dir_joins_scene_filename_with_separator(self):
        render_dir = r"C:\Users\yousa\Downloads\project\tmp\work\render_clips"
        scene_filename = "scene_0000.mp4"
        unsafe = render_dir + scene_filename
        self.assertEqual(
            unsafe,
            r"C:\Users\yousa\Downloads\project\tmp\work\render_clipsscene_0000.mp4",
        )

        joined = vg.scene_clip_path(
            render_dir, scene_filename, path_cls=PureWindowsPath
        )
        self.assertEqual(
            str(joined),
            r"C:\Users\yousa\Downloads\project\tmp\work\render_clips\scene_0000.mp4",
        )
        self.assertEqual(joined.name, "scene_0000.mp4")
        self.assertEqual(joined.parent.name, "render_clips")
        self.assertNotIn("render_clipsscene", str(joined))

    def test_windows_hidden_render_clips_dir_joins_the_same_way(self):
        work_dir = (
            r"C:\Users\yousa\Downloads\Semantic YT Studio"
            r"\Video_2026-09-09_027_Sounds_Your_Cat_Hears_That_You_Dont"
            r"\tmp\videogen_project_20260909_027_cv5zq_lm"
        )
        clips_dir = vg.render_clips_dir(work_dir, path_cls=PureWindowsPath)
        clip = vg.scene_clip_path(
            clips_dir, vg.scene_clip_filename(0), path_cls=PureWindowsPath
        )
        expected = work_dir + r"\._render_clips\scene_0000.mp4"
        self.assertEqual(str(clip), expected)
        self.assertNotIn("Donttmp", str(clip))
        self.assertNotIn("render_clipsscene", str(clip))


class TestConcatListFormatting(unittest.TestCase):
    def test_concat_line_uses_forward_slashes_not_windows_escapes(self):
        windows_clip = PureWindowsPath(
            r"C:\Users\yousa\work\._render_clips\scene_0000.mp4"
        )
        posix = windows_clip.as_posix()
        line = f"file '{vg._escape_ffmpeg_concat_filename(posix)}'"
        self.assertEqual(
            line,
            "file 'C:/Users/yousa/work/._render_clips/scene_0000.mp4'",
        )
        # Raw backslash-s is what FFmpeg concat would eat into "clipsscene".
        unsafe = f"file '{windows_clip}'"
        self.assertIn(r"\scene_0000.mp4", unsafe)
        self.assertNotIn("\\", line)

    def test_single_quotes_in_filename_are_escaped(self):
        escaped = vg._escape_ffmpeg_concat_filename("It's clip.mp4")
        self.assertEqual(escaped, r"It'\''s clip.mp4")
        self.assertEqual(
            vg._unescape_ffmpeg_concat_filename(escaped),
            "It's clip.mp4",
        )

    def test_concat_file_points_at_existing_scene_clip(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips_dir = vg.render_clips_dir(work)
            clip = vg.scene_clip_path(clips_dir, vg.scene_clip_filename(0))
            clips_dir.mkdir()
            clip.write_bytes(b"placeholder")
            concat_path = vg.concat_list_path_for(work)
            vg.write_ffmpeg_concat_list([clip], concat_path)

            text = concat_path.read_text(encoding="utf-8")
            self.assertIn("file '", text)
            self.assertIn("._render_clips/scene_0000.mp4", text)
            self.assertNotIn("render_clipsscene", text)
            self.assertNotRegex(text, r"\\scene_")

            listed = vg.parse_concat_list_clip_paths(concat_path)
            self.assertEqual(len(listed), 1)
            self.assertTrue(listed[0].is_file())
            self.assertEqual(listed[0].resolve(), clip.resolve())

            vg.validate_mux_inputs(
                concat_path, [clip], scene_numbers=["1"]
            )

    def test_validate_reports_missing_path_and_scene_number(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips_dir = vg.render_clips_dir(work)
            clips_dir.mkdir()
            existing = vg.scene_clip_path(clips_dir, vg.scene_clip_filename(0))
            existing.write_bytes(b"placeholder")
            missing = vg.scene_clip_path(clips_dir, vg.scene_clip_filename(1))
            concat_path = vg.write_ffmpeg_concat_list(
                [existing, missing], vg.concat_list_path_for(work)
            )
            with self.assertRaises(vg.ConcatMuxError) as ctx:
                vg.validate_mux_inputs(
                    concat_path,
                    [existing, missing],
                    scene_numbers=["1", "7"],
                )
            err = ctx.exception
            self.assertEqual(str(err.scene_number), "7")
            self.assertEqual(Path(err.missing_path).name, "scene_0001.mp4")
            self.assertIn("scene 7", str(err))
            self.assertIn("scene_0001.mp4", str(err))

    def test_validate_fails_if_concat_list_is_missing(self):
        with TemporaryDirectory() as tmp:
            missing_list = Path(tmp) / "concat_list.txt"
            with self.assertRaises(vg.ConcatMuxError) as ctx:
                vg.validate_mux_inputs(missing_list, [])
            self.assertIn("concat list missing", str(ctx.exception))


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestFinalMuxConcatInputs(unittest.TestCase):
    def test_final_mux_receives_valid_concat_inputs(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            clips_dir = vg.render_clips_dir(work)
            clip = vg.scene_clip_path(clips_dir, vg.scene_clip_filename(0))
            _make_test_clip(clip)
            audio = work / "vo.wav"
            _make_silent_audio(audio)
            concat_path = vg.write_ffmpeg_concat_list(
                [clip], vg.concat_list_path_for(work)
            )
            listed = vg.validate_mux_inputs(
                concat_path, [clip], scene_numbers=["1"]
            )
            self.assertTrue(listed[0].is_file())
            self.assertEqual(listed[0].resolve(), clip.resolve())

            out = work / "out.mp4"
            # Same concat+audio mux shape as render_video, without depending on cwd.
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_path),
                "-i", str(audio),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(out),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(
                result.returncode,
                0,
                msg=f"final mux failed:\n{result.stderr[-2000:]}",
            )
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)

    def test_shot_concat_list_is_windows_safe(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            a = work / "shot_a.mp4"
            b = work / "shot_b.mp4"
            _make_test_clip(a, seconds=0.2)
            _make_test_clip(b, seconds=0.2)
            out = work / "scene.mp4"
            vg._concat_shot_clips([a, b], out)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
