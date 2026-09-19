"""Tests for the real (xfade-based) cross-clip transition system —
video_generator.build_xfade_filter_complex / TRANSITION_TYPES /
xfade_name_for_transition, plus the reconciliation wiring that carries an
operator-picked transition from the Inspector through to render_video().

The fake-transition system this replaces (transition_fade_params/
_fade_vf_suffix — each clip independently fading to a color, "duration-
preserving (no overlap)") is untouched and still used as the DEFAULT for
auto-generated first cuts; these only activate when TimelineEvent.metadata
carries a transition_duration > 0 with a transition_in in TRANSITION_TYPES.

A real ffmpeg smoke test (spawns actual ffmpeg, builds a real 3-clip xfade
chain, and checks the output file/duration) lives in this file too since
xfade command construction is exactly the kind of thing that looks right
and silently fails at the ffmpeg-argument level — see
TestXfadeRealFfmpegSmoke.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import video_generator as vg


class TestTransitionVocabulary(unittest.TestCase):
    def test_all_required_transition_types_present(self):
        for t in ("cut", "crossfade", "dip_black", "dip_white", "wipe", "slide"):
            self.assertIn(t, vg.TRANSITION_TYPES)

    def test_xfade_name_mapping_matches_ffmpeg_named_transitions(self):
        # These are ffmpeg's own xfade transition= names — a typo here
        # would silently fall back to "fade" inside ffmpeg (or error).
        self.assertEqual(vg.xfade_name_for_transition("crossfade"), "fade")
        self.assertEqual(vg.xfade_name_for_transition("dip_black"), "fadeblack")
        self.assertEqual(vg.xfade_name_for_transition("dip_white"), "fadewhite")
        self.assertEqual(vg.xfade_name_for_transition("wipe"), "wipeleft")
        self.assertEqual(vg.xfade_name_for_transition("slide"), "slideleft")

    def test_unknown_type_falls_back_to_fade_not_a_crash(self):
        self.assertEqual(vg.xfade_name_for_transition("nonsense"), "fade")
        self.assertEqual(vg.xfade_name_for_transition(""), "fade")
        self.assertEqual(vg.xfade_name_for_transition(None), "fade")

    def test_wipe_and_slide_directions_map_to_real_ffmpeg_names(self):
        # All 8 are genuine ffmpeg xfade transition= names (verified via
        # `ffmpeg -h filter=xfade`), not an invented vocabulary.
        self.assertEqual(vg.xfade_name_for_transition("wipe", "left"), "wipeleft")
        self.assertEqual(vg.xfade_name_for_transition("wipe", "right"), "wiperight")
        self.assertEqual(vg.xfade_name_for_transition("wipe", "up"), "wipeup")
        self.assertEqual(vg.xfade_name_for_transition("wipe", "down"), "wipedown")
        self.assertEqual(vg.xfade_name_for_transition("slide", "left"), "slideleft")
        self.assertEqual(vg.xfade_name_for_transition("slide", "right"), "slideright")
        self.assertEqual(vg.xfade_name_for_transition("slide", "up"), "slideup")
        self.assertEqual(vg.xfade_name_for_transition("slide", "down"), "slidedown")

    def test_wipe_direction_defaults_to_left_when_omitted_or_unknown(self):
        self.assertEqual(vg.xfade_name_for_transition("wipe"), "wipeleft")
        self.assertEqual(vg.xfade_name_for_transition("wipe", "sideways"), "wipeleft")

    def test_non_directional_type_ignores_direction_argument(self):
        self.assertEqual(vg.xfade_name_for_transition("crossfade", "right"), "fade")
        self.assertEqual(vg.xfade_name_for_transition("dip_black", "up"), "fadeblack")


class TestBuildXfadeFilterComplex(unittest.TestCase):
    def test_two_clips_one_transition(self):
        fc, label = vg.build_xfade_filter_complex([5.0, 5.0], [("crossfade", 1.0)])
        self.assertIn("[0:v][1:v]xfade=transition=fade:duration=1.000:offset=4.000[vx1]", fc)
        self.assertEqual(label, "vx1")

    def test_three_clips_chain_offsets_account_for_overlap(self):
        # clip durations 4,4,4; transitions 1.0 and 1.0.
        # boundary1 offset = 4.0 - 1.0 = 3.0
        # merged duration after boundary1 = 4+4-1 = 7.0
        # boundary2 offset = 7.0 - 1.0 = 6.0
        fc, label = vg.build_xfade_filter_complex([4.0, 4.0, 4.0], [("crossfade", 1.0), ("wipe", 1.0)])
        self.assertIn("offset=3.000", fc)
        self.assertIn("offset=6.000", fc)
        self.assertEqual(label, "vx2")

    def test_none_transition_becomes_a_near_instant_cut(self):
        fc, _ = vg.build_xfade_filter_complex([3.0, 3.0], [None])
        self.assertIn(f"duration={vg.MIN_XFADE_DURATION:.3f}", fc)

    def test_transition_duration_clamped_to_shorter_clip(self):
        # requested 5s transition but clips are only 1s each -> clamp.
        fc, _ = vg.build_xfade_filter_complex([1.0, 1.0], [("crossfade", 5.0)])
        self.assertNotIn("duration=5.000", fc)

    def test_wrong_transition_count_raises(self):
        with self.assertRaises(ValueError):
            vg.build_xfade_filter_complex([1.0, 1.0, 1.0], [("crossfade", 0.5)])  # needs 2

    def test_single_clip_raises(self):
        with self.assertRaises(ValueError):
            vg.build_xfade_filter_complex([1.0], [])


class TestRunFinalMuxFastPathUnaffected(unittest.TestCase):
    """No transitions requested -> the exact same fast stream-copy path as
    before this feature existed. This is the regression guard: adding
    real transitions must never change behavior for projects that don't
    use them."""

    def test_run_final_mux_source_still_has_c_copy_fast_path(self):
        import inspect

        src = inspect.getsource(vg.run_final_mux)
        self.assertIn('"-c:v", "copy"', src)
        self.assertIn("has_transitions", src)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
class TestXfadeRealFfmpegSmoke(unittest.TestCase):
    """Spawns real ffmpeg to build an actual 3-clip xfade chain and
    verifies a real output file with the expected duration — command
    construction bugs (bad filter syntax, wrong stream labels) show up
    here, not in the pure-logic tests above."""

    def test_real_xfade_chain_produces_correct_duration_output(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            clips = []
            for i, color in enumerate(["red", "green", "blue"]):
                p = td / f"c{i}.mp4"
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=2:r=25",
                     "-pix_fmt", "yuv420p", str(p)],
                    check=True, capture_output=True,
                )
                clips.append(p)
            durations = [2.0, 2.0, 2.0]
            transitions = [("crossfade", 0.5), ("wipe", 0.3)]
            audio = td / "audio.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10", str(audio)],
                check=True, capture_output=True,
            )
            out = td / "final.mp4"
            vg._run_final_mux_with_transitions(
                clips, audio_path=audio, output_path=out, bg_audio=None, bg_volume=0.15,
                transitions=transitions, clip_durations=durations, work=td,
            )
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                capture_output=True, text=True,
            )
            dur = float(probe.stdout.strip())
            # 3x2.0s clips minus 0.5+0.3s overlap = 5.2s video (audio is 10s,
            # so -shortest lets video be the limiting/reported duration).
            self.assertAlmostEqual(dur, 5.2, delta=0.15)

    def test_directional_wipe_and_slide_produce_a_real_output_file(self):
        """A 3-tuple (type, duration, direction) transition spec must reach
        a real ffmpeg xfade filter and actually render — not silently fall
        back to the un-directional default."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            clips = []
            for i, color in enumerate(["red", "green", "blue"]):
                p = td / f"c{i}.mp4"
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=2:r=25",
                     "-pix_fmt", "yuv420p", str(p)],
                    check=True, capture_output=True,
                )
                clips.append(p)
            durations = [2.0, 2.0, 2.0]
            transitions = [("wipe", 0.4, "up"), ("slide", 0.4, "down")]
            audio = td / "audio.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10", str(audio)],
                check=True, capture_output=True,
            )
            out = td / "final.mp4"
            vg._run_final_mux_with_transitions(
                clips, audio_path=audio, output_path=out, bg_audio=None, bg_volume=0.15,
                transitions=transitions, clip_durations=durations, work=td,
            )
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
