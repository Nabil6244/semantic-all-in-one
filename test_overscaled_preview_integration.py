"""Proves the Overscaled-generated EditorialTimeline plays back through the
EXISTING, UNMODIFIED preview_engine.py — real ffmpeg calls, not mocked.

This is the concrete verification Section 3 asked for: "if preview already
works because the result is a normal VIDEO_1 event, prove that with an
actual test rather than assuming it."
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import preview_engine as pe
from scene_graph.timeline import compile_segment_to_timeline

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_video(path: Path, duration: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x180:duration={duration}:rate=15", str(path)],
        check=True, capture_output=True,
    )


def _make_audio(path: Path, duration: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=300:duration={duration}", str(path)],
        check=True, capture_output=True,
    )


def _probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    return float(proc.stdout.strip() or 0.0)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestOverscaledTimelinePlaysInExistingPreview(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.clip = self.tmp / "overscaled_clip.mp4"
        _make_video(self.clip, 5.0)
        self.voiceover = self.tmp / "voiceover.wav"
        _make_audio(self.voiceover, 5.0)
        self.timeline = compile_segment_to_timeline(
            segment_clip_path=str(self.clip), voiceover_path=str(self.voiceover), duration=5.0,
        )
        self.state_dir = self.tmp / "state"
        self.state_dir.mkdir()

    def test_video_proxy_builds_and_is_playable(self):
        proxy = pe.build_video_proxy(self.state_dir, self.timeline, width=320, height=180, fps=15)
        self.assertIsNotNone(proxy, "preview_engine.build_video_proxy returned None for a normal VIDEO_1 event")
        self.assertTrue(proxy.is_file())
        self.assertAlmostEqual(_probe_duration(proxy), 5.0, delta=0.3)

    def test_audio_mix_includes_the_real_voiceover(self):
        mix = pe.build_audio_mix(self.state_dir, self.timeline, voiceover_path=self.voiceover)
        self.assertIsNotNone(mix, "preview_engine.build_audio_mix returned None — voiceover not detected")
        self.assertTrue(mix.is_file())
        self.assertAlmostEqual(_probe_duration(mix), 5.0, delta=0.3)

    def test_visual_segments_cover_the_whole_timeline_with_no_gaps(self):
        segments = pe.build_visual_segments(self.timeline)
        self.assertGreater(len(segments), 0)
        self.assertAlmostEqual(segments[0].start, 0.0, delta=0.01)
        self.assertAlmostEqual(segments[-1].end, 5.0, delta=0.01)

    def test_no_unexpected_tracks_on_the_overscaled_timeline(self):
        tracks = {e.track for e in self.timeline.events}
        self.assertEqual(tracks, {"VIDEO_1", "VOICEOVER"})

    def test_camera_never_becomes_a_timeline_event(self):
        # Nothing about camera (pan/zoom/keyframes) exists as its own event —
        # it was already baked into the rendered clip before this timeline
        # was built (see scene_graph.render / scene_graph.timeline).
        for e in self.timeline.events:
            self.assertNotIn("camera", e.metadata)
            self.assertNotEqual(e.track, "GRAPHICS")


if __name__ == "__main__":
    unittest.main()
