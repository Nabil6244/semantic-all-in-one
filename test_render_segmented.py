"""Regression tests for the Overscaled/Exp Solar renderer's bounded,
segmented ffmpeg execution (scene_graph/render.py).

Reproduced before the fix, on macOS 1080p30 with real planner output:
  * a 10-minute project (484 ffmpeg inputs in ONE process) failed with
    "Error while opening decoder: Resource temporarily unavailable" — the
    4,096 threads-per-process limit (a 3-minute project already peaked at
    3,171 threads / 1.7 GB RSS);
  * the single command line was 35 KB at 3 minutes and 478 KB at 40 —
    over Windows' 32,767-character CreateProcess limit;
  * the layer work dir (hundreds of MB of PNGs on long projects) was left
    behind whenever the render failed.

These tests pin the fixed behavior: bounded per-process inputs/argv, exact
frame-for-frame equivalence between segmented and single-pass output (real
ffmpeg), deterministic frame-accurate layer visibility, and cleanup on
failure.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scene_graph.render as R
from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows
from scene_graph.layout import compute_layout
from scene_graph.style_presets import load_style_preset

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

_SENTENCES = [
    "Workers excavated the canyon floor with heavy machinery near the river.",
    "A cross-section diagram shows the turbine mechanism inside the dam.",
    "It remained there for decades.",
    "The system has three main components: pumps, valves, and pipes.",
    "Pumps move the water uphill each night.",
    "Valves control the flow at every junction.",
    "Pipes carry it to the city reservoirs.",
    "They built a second tunnel nearby.",
]


def _graph(n_rows: int):
    rows = [{"scene_number": str(i + 1), "script_segment": _SENTENCES[i % len(_SENTENCES)]} for i in range(n_rows)]
    result = generate_scene_graph_local_planner("seg", scene_rows_from_csv_rows(rows))
    assert result.ok, result.errors
    return result.scene_graph


def _media(graph, directory: Path) -> dict:
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    out = {}
    for i, node in enumerate(graph.nodes):
        path = directory / f"{i}.jpg"
        Image.new("RGB", (320, 180), ((i * 37) % 255, (i * 91) % 255, (i * 53) % 255)).save(path)
        out[node.id] = str(path)
    return out


class TestSegmentPlanning(unittest.TestCase):
    def _layers(self, n, spacing=1.0, length=3.0):
        return [R._Layer(["-i", f"/tmp/layer_{i}.png"], offset=i * spacing, duration=length) for i in range(n)]

    def test_graph_within_budget_renders_in_one_pass(self):
        layers = self._layers(10)
        self.assertEqual(R._plan_segments(layers, duration=20.0, fps=30), [(0.0, 20.0)])

    def test_over_budget_graph_is_cut_into_contiguous_frame_aligned_bounded_segments(self):
        layers = self._layers(400, spacing=0.7, length=6.0)
        duration = 400 * 0.7 + 6.0
        segments = R._plan_segments(layers, duration=duration, fps=30, max_inputs=40)
        self.assertGreater(len(segments), 1)
        self.assertEqual(segments[0][0], 0.0)
        self.assertEqual(segments[-1][1], duration)
        for (a_start, a_end), (b_start, _) in zip(segments, segments[1:]):
            self.assertEqual(a_end, b_start)
            self.assertAlmostEqual(a_end * 30, round(a_end * 30), places=6)  # frame-aligned cut
        for start, end in segments:
            self.assertLessEqual(len(R._layers_in(layers, start, end)), 40)

    def test_budget_is_read_at_call_time(self):
        # A module-level budget bound as a default argument could never be
        # tuned/patched (a real bug found while profiling this change).
        layers = self._layers(50)
        with mock.patch.object(R, "_MAX_SEGMENT_INPUTS", 10):
            self.assertGreater(len(R._plan_segments(layers, duration=60.0, fps=30)), 1)

    def test_layer_frame_ranges_hand_over_without_gap_or_overlap(self):
        first = R._Layer(["-i", "a.png"], offset=1.95, duration=2.8)
        second = R._Layer(["-i", "b.png"], offset=first.end, duration=1.0)
        a0, a1 = map(int, first.enable(0.0, 30)[len("between(n,"):-1].split(","))
        b0, _ = map(int, second.enable(0.0, 30)[len("between(n,"):-1].split(","))
        self.assertEqual(a1 + 1, b0)  # the next layer starts on the very next frame
        # The same layer lands on the same absolute frames inside a segment.
        shifted = first.enable(30 / 30, 30)
        s0, s1 = map(int, shifted[len("between(n,"):-1].split(","))
        self.assertEqual((s0 + 30, s1 + 30), (a0, a1))


class TestSegmentedRenderCommands(unittest.TestCase):
    """Command-level checks for a large graph (no ffmpeg needed)."""

    def test_every_ffmpeg_process_stays_within_input_and_argv_budgets(self):
        graph = _graph(160)  # ~10 minutes of narration: 480+ layers in one pass before
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            Path(cmd[-1]).write_bytes(b"x")
            return mock.Mock(returncode=0, stderr="", timed_out=False, stalled=False)

        with tempfile.TemporaryDirectory() as tmp:
            media = _media(graph, Path(tmp) / "media")
            layout = compute_layout(graph, resolved_media=media)
            with mock.patch.object(R, "run_ffmpeg", fake_run):
                R.render_overscaled_segment(
                    graph, layout, load_style_preset("overscaled"), out_path=Path(tmp) / "out.mp4",
                    resolved_media=media, resolution="1920x1080", fps=30, work_dir=Path(tmp) / "work",
                )
            self.assertFalse((Path(tmp) / "work").exists())
        renders = [c for c in commands if "-filter_complex" in c]
        self.assertGreater(len(renders), 1)
        self.assertIn("concat", commands[-1])
        for cmd in renders:
            self.assertLessEqual(cmd.count("-i") - 1, R._MAX_SEGMENT_INPUTS)
            self.assertLess(sum(len(str(a)) + 1 for a in cmd), 32767)
        # Still inputs decode single-threaded (thread-count budget).
        first_png = renders[0].index("-threads")
        self.assertEqual(renders[0][first_png + 1], "1")

    def test_work_dir_is_removed_when_the_render_fails(self):
        graph = _graph(4)
        with tempfile.TemporaryDirectory() as tmp:
            media = _media(graph, Path(tmp) / "media")
            layout = compute_layout(graph, resolved_media=media)
            failing = mock.Mock(return_value=mock.Mock(returncode=1, stderr="boom"))
            with mock.patch.object(R, "run_ffmpeg", failing):
                with self.assertRaises(RuntimeError):
                    R.render_overscaled_segment(
                        graph, layout, load_style_preset("overscaled"), out_path=Path(tmp) / "out.mp4",
                        resolved_media=media, work_dir=Path(tmp) / "work",
                    )
            self.assertFalse((Path(tmp) / "work").exists())


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg/ffprobe required")
class TestSegmentedRenderIsFrameExact(unittest.TestCase):
    """Real ffmpeg: the same graph rendered in one pass and in several
    segments must produce the same frames (decoded and compared)."""

    def _frames(self, path: Path, w: int, h: int):
        import numpy as np

        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True,
        ).stdout
        return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.int16)

    def test_segmented_equals_single_pass_and_has_no_blank_or_short_frames(self):
        graph = _graph(12)
        w, h = 480, 270
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            media = _media(graph, tmp / "media")
            layout = compute_layout(graph, resolved_media=media, canvas_width=w, canvas_height=h)
            style = load_style_preset("overscaled")
            outs = {}
            for name, budget in (("single", 10_000), ("segmented", 8)):
                with mock.patch.object(R, "_MAX_SEGMENT_INPUTS", budget):
                    outs[name] = R.render_overscaled_segment(
                        graph, layout, style, out_path=tmp / f"{name}.mp4", resolved_media=media,
                        resolution=f"{w}x{h}", fps=30, work_dir=tmp / f"w_{name}",
                    )
            single, segmented = self._frames(outs["single"], w, h), self._frames(outs["segmented"], w, h)
            expected_frames = R._first_frame(graph.duration, 30)
            self.assertEqual(len(single), expected_frames)
            self.assertEqual(len(segmented), expected_frames)
            worst = max(float(abs(a - b).mean()) for a, b in zip(single, segmented))
            self.assertLess(worst, 1.0, "segmented render must match the single pass frame for frame")
            # The final frame used to lose every overlay (fractional-duration
            # tail): it must still show content, not a bare white canvas.
            self.assertGreater(float(segmented[-1].std()), 2.0)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg/ffprobe required")
class TestFinalOutputValidation(unittest.TestCase):
    """generate_overscaled_video used to report success whenever the output
    file merely existed."""

    def _csv(self, tmp: Path) -> Path:
        import csv

        path = tmp / "plan.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["scene_number", "script_segment"])
            for i, text in enumerate(_SENTENCES[:4], start=1):
                w.writerow([str(i), text])
        return path

    def _voiceover(self, tmp: Path, seconds: float) -> Path:
        path = tmp / "vo.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f=220:d={seconds}", str(path)],
                       check=True)
        return path

    def test_valid_render_with_trailing_voiceover_silence_passes_and_is_probed(self):
        from scene_graph.app_integration import generate_overscaled_video

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            words, t = [], 0.0
            for text in _SENTENCES[:4]:
                for word in text.split():
                    words.append((word, t, t + 0.35))
                    t += 0.4
            vo = self._voiceover(tmp, t + 6.0)  # narration ends ~6 s before the file does
            with mock.patch("scene_graph.app_integration.resolve_scene_graph_media", return_value={}):
                result = generate_overscaled_video(
                    str(self._csv(tmp)), str(vo), str(tmp / "out.mp4"), resolution="320x180", fps=15,
                    work_dir=str(tmp / "work"), whisper_words=words, use_local_planner=True,
                )
            self.assertTrue(result.ok, result.errors)

    def test_file_without_audio_is_reported_as_a_failure(self):
        from scene_graph.app_integration import validate_rendered_output

        with tempfile.TemporaryDirectory() as tmp:
            silent = Path(tmp) / "silent.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=64x36:d=2",
                            "-c:v", "libx264", str(silent)], check=True)
            self.assertIn("audio", validate_rendered_output(silent, expected_duration_s=2.0))

    def test_truncated_file_is_reported_as_a_failure(self):
        from scene_graph.app_integration import validate_rendered_output

        with tempfile.TemporaryDirectory() as tmp:
            short = Path(tmp) / "short.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=64x36:d=2",
                            "-f", "lavfi", "-i", "sine=d=2", "-shortest", "-c:v", "libx264", str(short)], check=True)
            self.assertIn("duration", validate_rendered_output(short, expected_duration_s=30.0))
            self.assertIsNone(validate_rendered_output(short, expected_duration_s=2.0))
