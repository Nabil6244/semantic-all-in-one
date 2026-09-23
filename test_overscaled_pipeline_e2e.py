"""End-to-end Overscaled pipeline tests: voiceover sync, timeline compilation,
the full run_overscaled_pipeline orchestrator, and — the most important test
in this suite — a REAL render through the EXISTING, unmodified
video_generator.render_video(), proving:

    Overscaled CSV + voiceover -> SceneGraph -> layout -> composition ->
    camera -> EditorialTimeline -> existing FFmpeg export -> playable MP4

No Gemini, no network, no mocking of ffmpeg — real subprocess calls, real
files, real ffprobe verification.
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from editorial.timeline import EditorialTimeline
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline
from scene_graph.timeline import compile_segment_to_timeline
from scene_graph.voiceover_sync import retime_to_audio_duration, retime_to_whisper_words

FIXTURE = Path(__file__).resolve().parent / "overscaled_sample.csv"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _fixture_rows():
    with open(FIXTURE, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _make_sine_wav(path: Path, duration_s: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={max(0.5, duration_s):.2f}", str(path)],
        check=True, capture_output=True,
    )


def _probe(path: Path) -> dict:
    import json

    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    return json.loads(proc.stdout or "{}")


class TestVoiceoverSyncProportional(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_retimes_to_real_audio_duration(self):
        result = compile_overscaled_csv(_fixture_rows(), segment_id="seg")
        sg = result.scene_graph
        placeholder_duration = sg.duration

        wav = self.tmp / "vo.wav"
        _make_sine_wav(wav, 12.0)
        retimed = retime_to_audio_duration(sg, str(wav))

        self.assertAlmostEqual(retimed.duration, 12.0, delta=0.2)
        self.assertNotAlmostEqual(retimed.duration, placeholder_duration, delta=0.01)
        self.assertEqual(retimed.validate(), [])

    def test_missing_audio_file_leaves_graph_unchanged(self):
        result = compile_overscaled_csv(_fixture_rows(), segment_id="seg")
        sg = result.scene_graph
        retimed = retime_to_audio_duration(sg, str(self.tmp / "does_not_exist.wav"))
        self.assertEqual(retimed.duration, sg.duration)

    def test_ordering_of_events_preserved_after_rescale(self):
        result = compile_overscaled_csv(_fixture_rows(), segment_id="seg")
        sg = result.scene_graph
        wav = self.tmp / "vo.wav"
        _make_sine_wav(wav, 20.0)
        retimed = retime_to_audio_duration(sg, str(wav))
        appear_times = [n.appear_at for n in retimed.nodes]
        self.assertEqual(appear_times, sorted(appear_times))


class TestVoiceoverSyncWordAligned(unittest.TestCase):
    def test_beats_align_to_fake_whisper_words(self):
        rows = [
            {"scene_number": "1", "script_segment": "one two three", "node_id": "n1", "node_type": "image", "asset_type": "flow_image"},
            {"scene_number": "2", "script_segment": "four five", "node_id": "n2", "node_type": "image", "asset_type": "flow_image"},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        sg = result.scene_graph
        # Real words arrive much later/slower than the placeholder estimate.
        whisper_words = [
            ("one", 10.0, 10.3), ("two", 10.3, 10.6), ("three", 10.6, 11.0),
            ("four", 11.5, 11.8), ("five", 11.8, 12.2),
        ]
        retimed = retime_to_whisper_words(sg, whisper_words)
        beat1, beat2 = retimed.beats
        self.assertAlmostEqual(beat1.start, 10.0, delta=0.01)
        self.assertAlmostEqual(beat1.end, 11.0, delta=0.01)
        self.assertAlmostEqual(beat2.start, 11.5, delta=0.01)
        self.assertAlmostEqual(beat2.end, 12.2, delta=0.01)
        self.assertEqual(retimed.validate(), [])


class TestTimelineIntegration(unittest.TestCase):
    def test_compile_segment_to_timeline_uses_only_existing_track_types(self):
        timeline = compile_segment_to_timeline(
            segment_clip_path="/tmp/clip.mp4", voiceover_path="/tmp/vo.wav", duration=10.0,
        )
        self.assertIsInstance(timeline, EditorialTimeline)
        tracks = {e.track for e in timeline.events}
        self.assertEqual(tracks, {"VIDEO_1", "VOICEOVER"})
        video_event = next(e for e in timeline.events if e.track == "VIDEO_1")
        self.assertEqual(video_event.source, "/tmp/clip.mp4")
        self.assertEqual(video_event.end, 10.0)

    def test_timeline_round_trips_through_existing_to_dict_from_dict(self):
        timeline = compile_segment_to_timeline(
            segment_clip_path="/tmp/clip.mp4", voiceover_path="/tmp/vo.wav", duration=10.0,
        )
        restored = EditorialTimeline.from_dict(timeline.to_dict())
        self.assertEqual(restored.to_dict(), timeline.to_dict())


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestFullPipelineOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _resolved_media(self, sg):
        media_dir = self.tmp / "media"
        media_dir.mkdir(exist_ok=True)
        resolved = {}
        for i, node in enumerate(sg.nodes):
            if node.type == "video_loop":
                p = media_dir / f"{node.id}.mp4"
                subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2", str(p)],
                                check=True, capture_output=True)
            else:
                p = media_dir / f"{node.id}.png"
                Image.new("RGB", (640, 360), ((i * 47) % 255, (i * 91) % 255, (i * 137) % 255)).save(p)
            resolved[node.id] = str(p)
        return resolved

    def test_pipeline_produces_a_playable_clip_and_timeline(self):
        rows = _fixture_rows()
        # Placeholder-duration probe to build a matching-length voiceover.
        probe_sg = compile_overscaled_csv(rows, segment_id="aurora_bridge").scene_graph
        voiceover = self.tmp / "voiceover.wav"
        _make_sine_wav(voiceover, probe_sg.duration)

        resolved_media = self._resolved_media(probe_sg)
        out_dir = self.tmp / "out"
        result = run_overscaled_pipeline(
            rows, segment_id="aurora_bridge", title="The Aurora Bridge",
            voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1600, canvas_height=1000,
            resolution="640x360", fps=15,
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.segment_clip_path.is_file())
        self.assertTrue((out_dir / "overscaled_scene_graph.json").is_file())
        self.assertTrue((out_dir / "overscaled_layout.json").is_file())

        probe = _probe(result.segment_clip_path)
        self.assertAlmostEqual(float(probe["format"]["duration"]), result.scene_graph.duration, delta=0.5)

        tracks = {e.track for e in result.timeline.events}
        self.assertEqual(tracks, {"VIDEO_1", "VOICEOVER"})


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestRealExistingFFmpegExport(unittest.TestCase):
    """SECTION 37's acceptance test: Overscaled CSV + voiceover -> a real,
    playable final MP4, produced by the UNMODIFIED existing
    video_generator.render_video()."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmpdir.name)
        cls.old_cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old_cwd)
        cls._tmpdir.cleanup()

    def test_overscaled_csv_plus_voiceover_yields_real_final_mp4(self):
        import video_generator as vg

        rows = _fixture_rows()
        probe_sg = compile_overscaled_csv(rows, segment_id="aurora_bridge").scene_graph
        voiceover = self.root / "voiceover.wav"
        _make_sine_wav(voiceover, probe_sg.duration)

        media_dir = self.root / "media"
        media_dir.mkdir()
        resolved_media = {}
        for i, node in enumerate(probe_sg.nodes):
            if node.type == "video_loop":
                p = media_dir / f"{node.id}.mp4"
                subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2", str(p)],
                                check=True, capture_output=True)
            else:
                p = media_dir / f"{node.id}.png"
                Image.new("RGB", (640, 360), ((i * 47) % 255, (i * 91) % 255, (i * 137) % 255)).save(p)
            resolved_media[node.id] = str(p)

        out_dir = self.root / "overscaled_out"
        result = run_overscaled_pipeline(
            rows, segment_id="aurora_bridge", title="The Aurora Bridge",
            voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1600, canvas_height=1000,
            resolution="640x360", fps=15,
        )
        self.assertTrue(result.ok, result.errors)
        duration = result.scene_graph.duration
        clip_path = result.segment_clip_path

        # Existence-only stub for render_video's own missing-asset precondition
        # check — the REAL source rendered is EditDecision.shots[].source_path.
        work_dir = self.root / "work"
        work_dir.mkdir()
        Image.new("RGB", (16, 9), (0, 0, 0)).save(work_dir / "1.png")

        aligned_rows = [{"scene_number": "1", "start_time": 0.0, "script_segment": result.scene_graph.title}]
        decision_map = {
            "1": {
                "scene_number": "1", "required_duration": duration, "strategy": "SINGLE_SHOT",
                "shots": [{"shot_id": "s1", "output_duration": duration, "source_path": str(clip_path),
                           "transition_in": "cut", "transition_duration": 0.0}],
                "source_asset": str(clip_path),
            }
        }
        out_path = work_dir / "final_overscaled.mp4"
        os.chdir(work_dir)
        vg.render_video(
            aligned_rows, duration, work_dir, str(voiceover), str(out_path),
            "640x360", 15, zoom=False, visual_transitions=False,
            edit_decisions_by_scene=decision_map,
        )

        self.assertTrue(out_path.is_file(), "existing render_video() did not produce a final MP4")
        probe = _probe(out_path)
        stream_types = {s["codec_type"] for s in probe["streams"]}
        self.assertEqual(stream_types, {"video", "audio"}, "final MP4 is missing video or audio")
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        self.assertEqual((video_stream["width"], video_stream["height"]), (640, 360))
        self.assertAlmostEqual(float(probe["format"]["duration"]), duration, delta=0.5)


if __name__ == "__main__":
    unittest.main()
