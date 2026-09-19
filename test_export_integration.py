"""The critical A/B export test (explicitly required): prove that an
operator's timeline edit genuinely changes the exported MP4, and that an
UNEDITED re-render is stable/reproducible. This calls the REAL
render_video() -> real ffmpeg -> real final.mp4, not a mock.

This is the single most important regression guard in this codebase for
the "editor looks editable but export silently ignores it" failure class —
see editorial_timeline_edit.py's reconcile_timeline_into_decisions and
video_generator.py's xfade transition support, both exercised here through
the actual render path rather than through helper-function unit tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import video_generator as vg

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip() or 0.0)


def _hash_video_stream(path: Path) -> str:
    """A content hash of just the decoded video frames (not container
    metadata/timestamps, which can differ between two otherwise-identical
    encodes) — a robust way to tell "really the same pixels" from "really
    different pixels" without exact byte-for-byte comparison."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v", "-f", "md5", "-"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestExportABDivergence(unittest.TestCase):
    """EXPORT A -> edit timeline (add a real transition) -> EXPORT B ->
    verify B reflects the edit and a re-render of A's exact decisions is
    stable (doesn't drift on its own)."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.images_dir = root / "images"
        cls.images_dir.mkdir()
        Image.new("RGB", (160, 90), (200, 40, 40)).save(cls.images_dir / "1.png")
        Image.new("RGB", (160, 90), (40, 160, 60)).save(cls.images_dir / "2.png")

        cls.audio_path = root / "voiceover.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
             str(cls.audio_path)],
            check=True, capture_output=True,
        )
        cls.work_dir = root / "work"
        cls.work_dir.mkdir()
        cls.old_cwd = os.getcwd()
        os.chdir(cls.work_dir)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old_cwd)
        cls._tmpdir.cleanup()

    def _aligned_rows(self):
        return [
            {"scene_number": "1", "start_time": 0.0, "script_segment": "one"},
            {"scene_number": "2", "start_time": 2.0, "script_segment": "two"},
        ]

    def _base_decision_map(self) -> dict:
        return {
            "1": {
                "scene_number": "1", "required_duration": 2.0, "strategy": "SINGLE_SHOT",
                "shots": [{"shot_id": "s1", "output_duration": 2.0, "source_path": str(self.images_dir / "1.png"), "transition_in": "cut", "transition_duration": 0.0}],
                "source_asset": str(self.images_dir / "1.png"),
            },
            "2": {
                "scene_number": "2", "required_duration": 2.0, "strategy": "SINGLE_SHOT",
                "shots": [{"shot_id": "s2", "output_duration": 2.0, "source_path": str(self.images_dir / "2.png"), "transition_in": "cut", "transition_duration": 0.0}],
                "source_asset": str(self.images_dir / "2.png"),
            },
        }

    def _render(self, decision_map: dict, out_name: str) -> Path:
        out_path = Path(self.work_dir) / out_name
        vg.render_video(
            self._aligned_rows(), 4.0, self.images_dir, str(self.audio_path), str(out_path),
            "160x90", 10, zoom=False, visual_transitions=False,
            edit_decisions_by_scene=decision_map,
        )
        self.assertTrue(out_path.is_file(), f"{out_name} was not produced")
        return out_path

    def test_edit_changes_export_and_unedited_rerender_is_stable(self):
        # EXPORT A: baseline, hard cut between the two scenes.
        out_a = self._render(self._base_decision_map(), "export_a.mp4")
        dur_a = _probe_duration(out_a)
        hash_a = _hash_video_stream(out_a)

        # Edit: request a real 0.4s crossfade INTO scene 2 (the boundary
        # between scene 1's clip and scene 2's clip) — exactly what the
        # Inspector's transition control now writes.
        decisions_b = self._base_decision_map()
        decisions_b["2"]["shots"][0]["transition_in"] = "crossfade"
        decisions_b["2"]["shots"][0]["transition_duration"] = 0.4
        out_b = self._render(decisions_b, "export_b.mp4")
        dur_b = _probe_duration(out_b)
        hash_b = _hash_video_stream(out_b)

        # B must actually differ from A — both in overall duration (the
        # 0.4s overlap shortens the combined video) and in pixel content
        # (frames near the boundary are now blended, not a hard cut).
        self.assertNotEqual(hash_a, hash_b, "export B has IDENTICAL video content to A — the transition edit did not reach export")
        self.assertLess(dur_b, dur_a - 0.1, "a crossfade transition should shorten total video duration by ~its own length")

        # Re-render A's EXACT original decisions again — must reproduce A,
        # not drift (proves rendering is deterministic given the same
        # editorial state, i.e. nothing was silently mutated by the B render).
        out_a2 = self._render(self._base_decision_map(), "export_a2.mp4")
        hash_a2 = _hash_video_stream(out_a2)
        self.assertEqual(hash_a, hash_a2, "re-rendering the SAME (unedited) decisions produced different output")

    def test_operator_reconciliation_path_produces_the_same_divergence(self):
        """Same test, but going through the REAL operator path: an
        EditorialTimeline mutated via editorial_timeline_edit.set_event_property,
        reconciled via reconcile_timeline_into_decisions — not a hand-built
        decision dict. This is what actually runs inside app.py's render
        pipeline."""
        import dataclasses

        import editorial_timeline_edit as tl_edit
        from editorial.edit_decision import EditDecision, ShotSpec
        from editorial.timeline import EditorialTimeline, TimelineEvent

        base_decisions = [
            EditDecision(scene_number="1", required_duration=2.0, shots=[
                ShotSpec(shot_id="s1", output_duration=2.0, source_path=str(self.images_dir / "1.png")),
            ]),
            EditDecision(scene_number="2", required_duration=2.0, shots=[
                ShotSpec(shot_id="s2", output_duration=2.0, source_path=str(self.images_dir / "2.png")),
            ]),
        ]

        def decision_map_from(decisions):
            return {d.scene_number: d.to_dict() for d in decisions}

        out_a = self._render(decision_map_from(base_decisions), "export_op_a.mp4")
        hash_a = _hash_video_stream(out_a)

        timeline = EditorialTimeline(
            audio_end=4.0,
            events=[
                TimelineEvent(event_id="s1", track="VIDEO_1", start=0.0, end=2.0, scene_number="1", source=str(self.images_dir / "1.png")),
                TimelineEvent(event_id="s2", track="VIDEO_1", start=2.0, end=4.0, scene_number="2", source=str(self.images_dir / "2.png")),
            ],
        )
        tl_edit.set_event_property(timeline, "s2", transition_in="crossfade", transition_duration=0.4)
        reconciled = tl_edit.reconcile_timeline_into_decisions(base_decisions, timeline)
        out_b = self._render(decision_map_from(reconciled), "export_op_b.mp4")
        hash_b = _hash_video_stream(out_b)

        self.assertNotEqual(hash_a, hash_b, "reconcile_timeline_into_decisions's output did not change the real export")


def _hash_audio_stream(path: Path) -> str:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-f", "md5", "-"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestFullEditABCExport(unittest.TestCase):
    """Section 16's extended A/B/C export test: every edit category in one
    real timeline — VIDEO_2 position AND duration, a real transition, SFX
    move AND volume, ambience move, speed, and a track-level mute — then
    a real save_timeline/load_timeline round trip (simulating close and
    reopen) before a THIRD render, proving persistence reproduces the
    edited state exactly rather than reverting to A or losing anything.

    EXPORT A: unedited baseline.
    EXPORT B: every edit applied (still in memory).
    EXPORT C: same timeline, but read back from disk after a save/reload —
    must match B (not A) in both video and audio content.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.images_dir = root / "images"
        cls.images_dir.mkdir()

        # testsrc has real motion (unlike a flat color), so a speed change
        # actually samples different frames -> a genuinely different hash.
        # Named to match their scene_number — render_video()'s own
        # missing_images_for_scenes() pre-check requires a matching file in
        # images_dir even though edit_decisions carries the real source
        # path explicitly (see video_generator.find_image_for_scene).
        cls.v1_src = cls.images_dir / "1.mp4"
        cls.v2_src = cls.images_dir / "2.mp4"
        for dest, seed in ((cls.v1_src, 1), (cls.v2_src, 2)):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=10:duration=8:decimals=2",
                 "-pix_fmt", "yuv420p", str(dest)],
                check=True, capture_output=True,
            )
        cls.broll_src = root / "broll.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=4:r=10",
             "-pix_fmt", "yuv420p", str(cls.broll_src)],
            check=True, capture_output=True,
        )
        cls.narration_path = root / "narration.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=6", str(cls.narration_path)],
            check=True, capture_output=True,
        )
        cls.sfx_path = root / "sfx.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1200:duration=0.3", str(cls.sfx_path)],
            check=True, capture_output=True,
        )
        cls.amb_path = root / "amb.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=80:duration=6", str(cls.amb_path)],
            check=True, capture_output=True,
        )
        cls.music_path = root / "music.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=600:duration=6", str(cls.music_path)],
            check=True, capture_output=True,
        )

        cls.work_dir = root / "work"
        cls.work_dir.mkdir()
        cls.old_cwd = os.getcwd()
        os.chdir(cls.work_dir)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.old_cwd)
        cls._tmpdir.cleanup()

    def _build_timeline(self):
        from editorial.timeline import EditorialTimeline, TimelineEvent

        return EditorialTimeline(
            audio_end=6.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=3.0, scene_number="1", source=str(self.v1_src), metadata={"speed": 1.0, "source_start": 0.0}),
                TimelineEvent(event_id="v2", track="VIDEO_1", start=3.0, end=6.0, scene_number="2", source=str(self.v2_src), metadata={"speed": 1.0, "source_start": 0.0}),
                TimelineEvent(event_id="b1", track="VIDEO_2", start=0.5, end=1.5, scene_number="1", source=str(self.broll_src), metadata={"speed": 1.0, "source_start": 0.0}),
                TimelineEvent(event_id="sfx1", track="SFX", start=0.2, end=0.5, scene_number="1", metadata={"file": str(self.sfx_path), "volume": 1.0}),
                TimelineEvent(event_id="amb1", track="AMBIENCE", start=0.0, end=6.0, scene_number="1", metadata={"file": str(self.amb_path), "volume": 0.5}),
                TimelineEvent(event_id="music1", track="MUSIC", start=0.0, end=6.0, scene_number="1", metadata={"volume": 0.4}),
            ],
        )

    def _render_from_timeline(self, timeline, name: str) -> tuple[Path, Path]:
        """Reconcile the timeline (video) + bridge (audio), mix real SFX/
        ambience into the narration, then run the real FFmpeg renderer —
        exactly app.py's render pipeline, at unit-test scale."""
        import editorial_timeline_edit as tl_edit
        from editorial.edit_decision import EditDecision, ShotSpec
        import smart_editing

        base_decisions = [
            EditDecision(scene_number="1", required_duration=3.0, shots=[ShotSpec(shot_id="s1", output_duration=3.0)]),
            EditDecision(scene_number="2", required_duration=3.0, shots=[ShotSpec(shot_id="s2", output_duration=3.0)]),
        ]
        reconciled = tl_edit.reconcile_timeline_into_decisions(base_decisions, timeline)
        decision_map = {d.scene_number: d.to_dict() for d in reconciled}

        sfx_events, ambience_beds = tl_edit.sfx_ambience_events_for_export(
            timeline, muted_tracks=set(timeline.muted_tracks), solo_tracks=set(timeline.solo_tracks),
        )
        mixed_audio = self.work_dir / f"{name}_mixed.wav"
        smart_editing.mix_sfx_with_narration(
            self.narration_path, sfx_events, mixed_audio, ambience_beds=ambience_beds,
        )

        aligned_rows = [
            {"scene_number": "1", "start_time": 0.0, "script_segment": "one"},
            {"scene_number": "2", "start_time": 3.0, "script_segment": "two"},
        ]
        out_path = self.work_dir / f"{name}_final.mp4"
        import video_generator as vg

        vg.render_video(
            aligned_rows, 6.0, self.images_dir, str(mixed_audio), str(out_path),
            "160x90", 10, zoom=False, visual_transitions=False,
            edit_decisions_by_scene=decision_map,
        )
        self.assertTrue(out_path.is_file())
        return out_path, mixed_audio

    def test_every_edit_category_reaches_export_and_survives_reload(self):
        import editorial_timeline_edit as tl_edit

        # ---- EXPORT A: unedited baseline ----
        tl_a = self._build_timeline()
        out_a, mixed_a = self._render_from_timeline(tl_a, "a")
        vhash_a = _hash_video_stream(out_a)
        ahash_a = _hash_audio_stream(mixed_a)
        dur_a = _probe_duration(out_a)

        # ---- Apply every edit category from Section 16 ----
        tl_b = self._build_timeline()
        # VIDEO_2 position AND duration: move b1 from scene 1 into scene 2's
        # window, then trim its right edge to shrink it.
        tl_edit.move_event(tl_b, "b1", 4.0, snap=False)
        tl_edit.trim_event_end(tl_b, "b1", 4.7, snap=False)  # shrink from 1.0s to 0.7s
        b1 = tl_edit.find_event(tl_b, "b1")
        self.assertEqual(b1.scene_number, "2", "moved overlay must reconcile into scene 2, not vanish from scene 1")
        # Real transition into scene 2.
        tl_edit.set_event_property(tl_b, "v2", transition_in="crossfade", transition_duration=0.4)
        # SFX move + volume.
        tl_edit.move_event(tl_b, "sfx1", 3.5, snap=False)
        tl_edit.set_event_property(tl_b, "sfx1", volume=0.2)
        # Ambience move (trim its start later, shortening the bed).
        tl_edit.trim_event_start(tl_b, "amb1", 1.0, snap=False)
        # Speed change on a REAL motion source (v1) — must sample
        # different frames of testsrc, producing a real pixel difference.
        tl_edit.set_event_property(tl_b, "v1", speed=tl_edit.clamp_speed(1.8))
        # Track-level mute — MUSIC must be entirely absent from B's mix.
        tl_b.muted_tracks = ["MUSIC"]

        out_b, mixed_b = self._render_from_timeline(tl_b, "b")
        vhash_b = _hash_video_stream(out_b)
        ahash_b = _hash_audio_stream(mixed_b)
        dur_b = _probe_duration(out_b)

        self.assertNotEqual(vhash_a, vhash_b, "none of the video-affecting edits (B-roll, transition, speed) reached export")
        self.assertNotEqual(ahash_a, ahash_b, "none of the audio-affecting edits (SFX move/volume, ambience trim, MUSIC mute) reached export")
        self.assertNotEqual(dur_a, dur_b, "the crossfade transition should have changed total video duration")

        # ---- Simulate close & reopen: save to disk, discard, reload ----
        with tempfile.TemporaryDirectory() as state_td:
            state_dir = Path(state_td)
            (state_dir / "editorial_plan.json").write_text('{"scenes": []}', encoding="utf-8")
            self.assertTrue(tl_edit.save_timeline(state_dir, tl_b))
            del tl_b
            tl_c = tl_edit.load_timeline(state_dir)

        # ---- EXPORT C: from the RELOADED timeline ----
        out_c, mixed_c = self._render_from_timeline(tl_c, "c")
        vhash_c = _hash_video_stream(out_c)
        ahash_c = _hash_audio_stream(mixed_c)
        dur_c = _probe_duration(out_c)

        self.assertEqual(vhash_b, vhash_c, "reloading the saved timeline must reproduce B's exact video, not drift")
        self.assertEqual(ahash_b, ahash_c, "reloading the saved timeline must reproduce B's exact audio, not drift")
        self.assertAlmostEqual(dur_b, dur_c, delta=0.05)
        self.assertNotEqual(vhash_c, vhash_a, "C must reflect the persisted EDITED state, never silently revert to A")


if __name__ == "__main__":
    unittest.main()
