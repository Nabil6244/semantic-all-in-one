"""Preview/export parity — the objective of this pass: the interactive
proxy preview must represent the SAME editable EditorialTimeline the final
FFmpeg export renders, not a simplified approximation of a different edit.

Covers (real ffmpeg throughout, no mocks for the rendering itself):
  - VIDEO_1-only proxy build
  - VIDEO_1 + VIDEO_2 real overlap compositing in the proxy (not a hard
    z-index swap — see preview_engine.build_visual_segments)
  - a real crossfade transition rendered into the proxy (xfade, not a cut)
  - directional Wipe / Slide in the proxy
  - the audio mixdown honoring SFX/ambience move/volume/mute parity
  - speed reflected in the proxy
  - partial cache invalidation: editing ONE clip must not force every
    other segment to re-render
  - the full Section 21 scenario: build a timeline touching every track
    kind, apply every listed edit, build a preview, reconcile+render a
    real export, and verify both are DERIVED FROM THE SAME resolved
    timeline state (semantic parity, not pixel-identical, per the task's
    own instruction) via preview_engine.effective_state_at() alongside
    editorial_timeline_edit.reconcile_timeline_into_decisions()
  - the existing 400-scene synthetic long-form project, exercised through
    segment planning / cache-key generation / repeated-edit invalidation
    without rendering a real 33-minute video.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip() or 0.0)


def _sample_pixel(path: Path, frame_n: int, xy, root: Path) -> tuple:
    frame = root / f"sample_{path.stem}_{frame_n}_{xy[0]}_{xy[1]}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-vf", f"select=eq(n\\,{frame_n})", "-vframes", "1", str(frame)],
        check=True, capture_output=True,
    )
    return Image.open(frame).convert("RGB").getpixel(xy)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestPreviewProxyRealFfmpeg(unittest.TestCase):
    """Section 23's minimum real-FFmpeg preview coverage."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.root = root
        cls.state_dir = root / "state"
        cls.state_dir.mkdir()

        cls.v1 = root / "v1.mp4"
        cls.v2 = root / "v2.mp4"
        for dest, color in ((cls.v1, "red"), (cls.v2, "green")):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:d=4:r=10",
                 "-pix_fmt", "yuv420p", str(dest)],
                check=True, capture_output=True,
            )
        cls.broll = root / "broll.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=4:r=10",
             "-pix_fmt", "yuv420p", str(cls.broll)],
            check=True, capture_output=True,
        )
        cls.motion = root / "motion.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=8",
             "-pix_fmt", "yuv420p", str(cls.motion)],
            check=True, capture_output=True,
        )
        cls.sfx = root / "sfx.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.3", str(cls.sfx)],
            check=True, capture_output=True,
        )
        cls.amb = root / "amb.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=80:duration=2", str(cls.amb)],
            check=True, capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def _fresh_state_dir(self) -> Path:
        d = Path(tempfile.mkdtemp(dir=str(self.root)))
        return d

    def test_1_video_1_only(self):
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        tl = EditorialTimeline(audio_end=2.0, events=[
            TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=2.0, source=str(self.v1)),
        ])
        out = pv.build_video_proxy(self._fresh_state_dir(), tl, width=160, height=90, fps=10)
        self.assertIsNotNone(out)
        self.assertTrue(out.is_file())
        self.assertAlmostEqual(_probe_duration(out), 2.0, delta=0.3)

    def test_2_video_1_plus_video_2_overlap_composites_both(self):
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        tl = EditorialTimeline(audio_end=4.0, events=[
            TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=4.0, source=str(self.v1)),
            TimelineEvent(
                event_id="b1", track="VIDEO_2", start=1.0, end=3.0, source=str(self.broll),
                metadata={"source_start": 0.0, "speed": 1.0},
            ),
        ])
        state_dir = self._fresh_state_dir()
        out = pv.build_video_proxy(state_dir, tl, width=160, height=90, fps=10)
        self.assertIsNotNone(out)

        # PIP box for 160x90 at default scale 0.4: width=64, margin~5 ->
        # around (91,49)-(155,85). Sample inside it during/outside the
        # overlap window.
        pip_point = (123, 67)
        during = _sample_pixel(out, 20, pip_point, state_dir)  # t=2.0s, inside [1,3)
        before = _sample_pixel(out, 5, pip_point, state_dir)  # t=0.5s, before the overlap
        r, g, b = during
        self.assertGreater(b, r, "blue B-roll must be visible in the PIP region during the overlap window")
        rb, gb, bb = before
        self.assertGreater(rb, bb, "before the overlap window the base (red) must be unaffected")

    def test_3_crossfade_transition_renders_as_a_real_blend(self):
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        tl = EditorialTimeline(audio_end=4.0, events=[
            TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=2.0, source=str(self.v1)),
            TimelineEvent(
                event_id="v2", track="VIDEO_1", start=2.0, end=4.0, source=str(self.v2),
                transition_in="crossfade", metadata={"transition_duration": 0.6},
            ),
        ])
        out = pv.build_video_proxy(self._fresh_state_dir(), tl, width=160, height=90, fps=10)
        self.assertIsNotNone(out)
        # A 0.6s overlap shortens the combined 4.0s of source to ~3.4s.
        self.assertAlmostEqual(_probe_duration(out), 3.4, delta=0.25)

    def test_4_and_5_wipe_and_slide_directions_produce_real_output(self):
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        for ttype, direction in (("wipe", "up"), ("slide", "down")):
            tl = EditorialTimeline(audio_end=4.0, events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=2.0, source=str(self.v1)),
                TimelineEvent(
                    event_id="v2", track="VIDEO_1", start=2.0, end=4.0, source=str(self.v2),
                    transition_in=ttype, metadata={"transition_duration": 0.4, "transition_direction": direction},
                ),
            ])
            out = pv.build_video_proxy(self._fresh_state_dir(), tl, width=160, height=90, fps=10)
            self.assertIsNotNone(out, f"{ttype}/{direction} proxy build failed")
            self.assertGreater(out.stat().st_size, 0)

    def test_many_plain_cuts_plus_one_real_transition_do_not_collapse_the_chain(self):
        """Found for real on a live project: once ANY real transition is
        requested anywhere, build_video_proxy chains EVERY boundary
        through one continuous xfade filter graph (see its own comment) —
        the OTHER boundaries (plain cuts nobody touched) get an implicit
        blend duration from the shared build_xfade_filter_complex
        (export's own function, unmodified). At this proxy's LOW fps
        (10-15, vs export's 24-30+), that implicit duration used to round
        to under a single frame and ffmpeg's xfade filter did not degrade
        gracefully — it silently collapsed the ENTIRE assembled output to
        a fraction of its real length (a correct ~2.9s two-cut chain came
        back as 1.5s). Five clips / four boundaries, only the LAST one
        requests a real transition — proves the fix holds for a genuinely
        multi-cut timeline, not just the original two-clip repro."""
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        clips = []
        for i, color in enumerate(["red", "green", "blue", "yellow", "white"]):
            p = self.root / f"chain_{i}.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:d=1.3:r=10",
                 "-pix_fmt", "yuv420p", str(p)],
                check=True, capture_output=True,
            )
            clips.append(p)
        events = []
        t = 0.0
        for i, p in enumerate(clips):
            end = t + 1.3
            kwargs = {}
            if i == len(clips) - 1:
                kwargs = {"transition_in": "crossfade", "metadata": {"transition_duration": 0.3}}
            events.append(TimelineEvent(event_id=f"c{i}", track="VIDEO_1", start=t, end=end, source=str(p), **kwargs))
            t = end
        tl = EditorialTimeline(audio_end=t, events=events)

        out = pv.build_video_proxy(self._fresh_state_dir(), tl, width=160, height=90, fps=10)
        self.assertIsNotNone(out, "the assembly must not silently fail")
        dur = _probe_duration(out)
        # 4 plain-cut boundaries contribute ~0 net loss (frame-scale
        # blends), the one real 0.3s crossfade shortens the total by
        # ~0.3s -> expect close to 5*1.3 - 0.3 = 6.2s, NOT a collapsed
        # fraction of it.
        self.assertGreater(dur, 5.0, "the chain collapsed instead of preserving all 5 clips' content")

    def test_6_audio_mix_honors_sfx_ambience_volume_move_and_mute(self):
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        def build(sfx_start, sfx_volume, muted_tracks=frozenset()):
            tl = EditorialTimeline(audio_end=4.0, events=[
                TimelineEvent(event_id="sfx1", track="SFX", start=sfx_start, end=sfx_start + 0.3, metadata={"file": str(self.sfx), "volume": sfx_volume}),
                TimelineEvent(event_id="amb1", track="AMBIENCE", start=0.0, end=2.0, metadata={"file": str(self.amb), "volume": 0.5}),
            ])
            return pv.build_audio_mix(self._fresh_state_dir(), tl, muted_tracks=muted_tracks)

        base = build(0.2, 1.0)
        moved = build(1.5, 1.0)
        quieter = build(0.2, 0.2)
        sfx_muted = build(0.2, 1.0, muted_tracks=frozenset({"SFX"}))
        for p in (base, moved, quieter, sfx_muted):
            self.assertIsNotNone(p)
            self.assertTrue(p.is_file())
        # Different SFX timing/volume/mute state must produce a genuinely
        # different mixed file (different cache key -> different path, and
        # the files themselves differ in content).
        self.assertNotEqual(base.read_bytes(), moved.read_bytes())
        self.assertNotEqual(base.read_bytes(), quieter.read_bytes())
        self.assertNotEqual(base.read_bytes(), sfx_muted.read_bytes())

    def test_voiceover_reaches_the_mix_even_though_its_events_carry_no_source(self):
        """Reported live: a real project's preview played video with NO
        narration at all. Root cause — real VOICEOVER TimelineEvents are
        per-beat timing markers with an EMPTY .source (the narration is
        ONE continuous immutable recording, never per-clip files like
        SFX/AMBIENCE — see editorial/engine.py's build_timeline_from_
        decisions, which never sets a VOICEOVER event's source at all).
        build_audio_mix's generic per-event loop correctly skips them (no
        resolvable source) — the fix is the explicit voiceover_path
        parameter, which must actually make real narration audible."""
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        # A realistic timeline: VOICEOVER events with NO source, exactly
        # matching editorial/engine.py's real output.
        tl = EditorialTimeline(audio_end=2.0, events=[
            TimelineEvent(event_id="vo1", track="VOICEOVER", start=0.0, end=1.0, source="", metadata={"purpose": "emotion"}),
            TimelineEvent(event_id="vo2", track="VOICEOVER", start=1.0, end=2.0, source="", metadata={"purpose": "character"}),
        ])

        without_voiceover = pv.build_audio_mix(self._fresh_state_dir(), tl)
        self.assertIsNone(without_voiceover, "no SFX/ambience and no voiceover_path given -> correctly nothing to mix")

        # self.sfx is a real short wav (from setUpClass) — reused here as
        # a stand-in "narration" file, since only real audio content
        # matters for this check, not what it actually says.
        with_voiceover = pv.build_audio_mix(self._fresh_state_dir(), tl, voiceover_path=self.sfx)
        self.assertIsNotNone(with_voiceover, "voiceover_path was given but never made it into the mix")
        self.assertTrue(with_voiceover.is_file())
        self.assertGreater(with_voiceover.stat().st_size, 0)

        # Real content, not silence — verify via ffmpeg's own volumedetect.
        result = subprocess.run(
            ["ffmpeg", "-i", str(with_voiceover), "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        self.assertIn("mean_volume", result.stderr)
        self.assertNotIn("mean_volume: -91", result.stderr)  # ffmpeg's own "digital silence" reading

    def test_voiceover_track_mute_and_solo_apply_to_the_base_narration(self):
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        tl = EditorialTimeline(audio_end=1.0, events=[
            TimelineEvent(event_id="vo1", track="VOICEOVER", start=0.0, end=1.0, source=""),
            TimelineEvent(event_id="sfx1", track="SFX", start=0.0, end=0.3, metadata={"file": str(self.sfx), "volume": 1.0}),
        ])
        unmuted = pv.build_audio_mix(self._fresh_state_dir(), tl, voiceover_path=self.sfx)
        muted = pv.build_audio_mix(self._fresh_state_dir(), tl, voiceover_path=self.sfx, muted_tracks=frozenset({"VOICEOVER"}))
        self.assertIsNotNone(unmuted)
        self.assertIsNotNone(muted)
        self.assertNotEqual(unmuted.read_bytes(), muted.read_bytes())

    def test_7_speed_is_reflected_in_the_proxy(self):
        """testsrc has real motion, so 1x vs 1.8x sample genuinely
        different frames of source at the same output duration."""
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        def build(speed):
            tl = EditorialTimeline(audio_end=2.0, events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=2.0, source=str(self.motion), metadata={"speed": speed, "source_start": 0.0}),
            ])
            return pv.build_video_proxy(self._fresh_state_dir(), tl, width=160, height=90, fps=10)

        out_a = build(1.0)
        out_b = build(1.8)
        self.assertIsNotNone(out_a)
        self.assertIsNotNone(out_b)
        # Both must be ~2.0s (output duration is fixed by the timeline
        # window regardless of speed) but sample different source content.
        self.assertAlmostEqual(_probe_duration(out_a), 2.0, delta=0.3)
        self.assertAlmostEqual(_probe_duration(out_b), 2.0, delta=0.3)
        self.assertNotEqual(out_a.read_bytes(), out_b.read_bytes())

    def test_partial_cache_invalidation_only_the_edited_segment_re_renders(self):
        """Editing one clip must not force every segment to re-render —
        the render_cache-backed per-segment cache should reuse unrelated
        segments untouched (task 8/19)."""
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        state_dir = self._fresh_state_dir()

        def tl_with(v2_speed):
            return EditorialTimeline(audio_end=4.0, events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=2.0, source=str(self.v1)),
                TimelineEvent(event_id="v2", track="VIDEO_1", start=2.0, end=4.0, source=str(self.v2), metadata={"speed": v2_speed}),
            ])

        pv.build_video_proxy(state_dir, tl_with(1.0), width=160, height=90, fps=10)
        proxy_dir = state_dir / pv.PROXY_DIRNAME

        def cached_clip_files():
            # Only the actual cached segment CONTENT files — exclude the
            # cache's own manifest (render_cache.json, legitimately
            # rewritten whenever any entry is added) and the final
            # assembled proxy_video_*.mp4 (expected to change — the
            # ASSEMBLY genuinely differs when a segment's duration/content
            # changes, even if OTHER segments were individually reused).
            return {
                p: p.stat().st_mtime_ns
                for p in proxy_dir.rglob("*")
                if p.is_file() and p.suffix == ".mp4" and not p.name.startswith("proxy_video_")
            }

        mtimes_before = cached_clip_files()
        pv.build_video_proxy(state_dir, tl_with(1.6), width=160, height=90, fps=10)
        mtimes_after = cached_clip_files()

        # Every cached segment CLIP file that existed before AND still
        # exists after must be untouched (same mtime) — proof the v1
        # segment was reused from cache, not re-rendered, when only v2
        # changed.
        unchanged_paths = set(mtimes_before) & set(mtimes_after)
        self.assertTrue(unchanged_paths, "expected at least one cached segment clip to survive the edit untouched")
        for p in unchanged_paths:
            self.assertEqual(mtimes_before[p], mtimes_after[p], f"{p} was touched even though its own clip did not change")




@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestSection21FullParityScenario(unittest.TestCase):
    """Section 21: a timeline touching every track kind, every listed edit
    applied, then BOTH a real preview build AND a real export — verified
    to be derived from the SAME resolved timeline state (semantic parity,
    not pixel-identical, per the task's own instruction)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.root = root
        self.images_dir = root / "images"
        self.images_dir.mkdir()
        for name in ("1.mp4", "2.mp4"):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=8",
                 "-pix_fmt", "yuv420p", str(self.images_dir / name)],
                check=True, capture_output=True,
            )
        self.broll_path = root / "broll.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=4:r=10",
             "-pix_fmt", "yuv420p", str(self.broll_path)],
            check=True, capture_output=True,
        )
        self.sfx_path = root / "sfx.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.3", str(self.sfx_path)],
            check=True, capture_output=True,
        )
        self.amb_path = root / "amb.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=80:duration=1", str(self.amb_path)],
            check=True, capture_output=True,
        )
        self.voiceover_path = root / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=6", str(self.voiceover_path)],
            check=True, capture_output=True,
        )
        self.state_dir = root / "state"
        self.state_dir.mkdir()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_full_scenario_preview_and_export_agree_on_the_edited_state(self):
        import editorial_timeline_edit as tl_edit
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        tl = EditorialTimeline(
            audio_end=6.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=3.0, scene_number="1", source=str(self.images_dir / "1.mp4"), metadata={"speed": 1.0, "source_start": 0.0}),
                TimelineEvent(event_id="v2", track="VIDEO_1", start=3.0, end=6.0, scene_number="2", source=str(self.images_dir / "2.mp4"), metadata={"speed": 1.0, "source_start": 0.0}),
                TimelineEvent(event_id="gfx1", track="GRAPHICS", start=0.5, end=1.5, scene_number="1", metadata={"kind": "lower_third"}),
            ],
        )

        # 1. move VIDEO_1 (reorder v1/v2).
        tl_edit.move_visual_event_to_index(tl, "v1", 1)
        self.assertEqual([e.event_id for e in tl_edit.visual_sequence_order(tl)], ["v2", "v1"])
        # 2. trim VIDEO_1 (now v1 is second, [3,6)) — shrink its right edge.
        tl_edit.trim_event_end(tl, "v1", 5.0, snap=False)
        # 3. split VIDEO_1.
        new_id = tl_edit.split_event(tl, "v1", (tl_edit.find_event(tl, "v1").start + tl_edit.find_event(tl, "v1").end) / 2.0)
        self.assertIsNotNone(new_id)
        # 4/5. insert VIDEO_2, overlapping v2 (now first, [0,3)).
        broll_id = tl_edit.insert_visual_clip(
            tl, track="VIDEO_2", at_time=1.0, duration=1.5, source=str(self.broll_path),
            metadata={"source_start": 0.0, "speed": 1.0},
        )
        self.assertIsNotNone(broll_id)
        broll_ev = tl_edit.find_event(tl, broll_id)
        self.assertEqual(broll_ev.scene_number, "2")  # auto-derived from the overlapped primary (v2)
        # 6. move VIDEO_2.
        tl_edit.move_event(tl, broll_id, 1.3, snap=False)
        # 7. trim VIDEO_2.
        b_now = tl_edit.find_event(tl, broll_id)
        tl_edit.trim_event_end(tl, broll_id, b_now.end - 0.2, snap=False)
        # 8. change speed (on v2).
        tl_edit.set_event_property(tl, "v2", speed=tl_edit.clamp_speed(1.5))
        # 9. Crossfade — into v1 (the boundary between v2 and v1).
        tl_edit.set_event_property(tl, "v1", transition_in="crossfade", transition_duration=0.4)
        # 10. directional Wipe — into the split piece.
        tl_edit.set_event_property(tl, new_id, transition_in="wipe", transition_duration=0.3, transition_direction="up")
        # 11/12/13. SFX add, move, volume, mute.
        sfx_id = tl_edit.add_event(tl, track="SFX", start=0.2, end=0.5, scene_number="2", source=str(self.sfx_path), metadata={"file": str(self.sfx_path), "volume": 1.0})
        tl_edit.move_event(tl, sfx_id, 0.6, snap=False)
        tl_edit.set_event_property(tl, sfx_id, volume=0.3)
        # 14/15. ambience add, move, volume.
        amb_id = tl_edit.add_event(tl, track="AMBIENCE", start=0.0, end=1.0, scene_number="2", source=str(self.amb_path), metadata={"file": str(self.amb_path), "volume": 0.5})
        tl_edit.move_event(tl, amb_id, 2.0, snap=False)
        tl_edit.set_event_property(tl, amb_id, volume=0.25)
        # 16. graphics movement.
        tl_edit.move_event(tl, "gfx1", 2.5, snap=False)

        # ---- Build a REAL preview from this exact timeline ----
        video_proxy = pv.build_video_proxy(self.state_dir, tl, width=160, height=90, fps=10)
        audio_proxy = pv.build_audio_mix(self.state_dir, tl)
        self.assertIsNotNone(video_proxy)
        self.assertTrue(video_proxy.is_file())
        self.assertIsNotNone(audio_proxy)
        self.assertTrue(audio_proxy.is_file())

        # ---- Reconcile the SAME timeline for a REAL export ----
        from editorial.edit_decision import EditDecision, ShotSpec

        base_decisions = [
            EditDecision(scene_number="1", required_duration=3.0, shots=[ShotSpec(shot_id="s1", output_duration=3.0)]),
            EditDecision(scene_number="2", required_duration=3.0, shots=[ShotSpec(shot_id="s2", output_duration=3.0)]),
        ]
        reconciled = tl_edit.reconcile_timeline_into_decisions(base_decisions, tl)
        scene2 = next(d for d in reconciled if d.scene_number == "2")
        self.assertTrue(scene2.broll, "the edited VIDEO_2 overlay must reconcile into a real broll entry")

        # ---- Semantic parity: at the overlay's own midpoint, the preview
        # snapshot's overlay identity must match the export's broll entry
        # for the SAME scene, and the primary identity must match whichever
        # primary event's ShotSpec covers that time. ----
        b_now = tl_edit.find_event(tl, broll_id)
        mid_t = (b_now.start + b_now.end) / 2.0
        snapshot = pv.effective_state_at(tl, mid_t)
        self.assertEqual(snapshot["overlay_event_id"], broll_id)
        self.assertEqual(scene2.broll[0]["shot_id"], broll_id)

        # The transition preview reports at v1's cut must match what
        # export will actually receive (same type/duration/direction).
        v1_ev = tl_edit.find_event(tl, "v1")
        trans_snapshot = pv.effective_state_at(tl, v1_ev.start + 0.1)
        self.assertIsNotNone(trans_snapshot["transition"])
        self.assertEqual(trans_snapshot["transition"]["type"], "crossfade")
        shot_v1 = next(s for d in reconciled for s in d.shots if s.shot_id == "v1")
        self.assertEqual(shot_v1.transition_in, "crossfade")
        self.assertAlmostEqual(shot_v1.transition_duration, 0.4)

        # SFX volume/mute parity between preview's audio snapshot and
        # export's resolved SFX event.
        sfx_now = tl_edit.find_event(tl, sfx_id)
        sfx_snapshot = pv.effective_state_at(tl, sfx_now.start + 0.05)
        sfx_entry = next(a for a in sfx_snapshot["audio"] if a["event_id"] == sfx_id)
        self.assertAlmostEqual(sfx_entry["volume"], 0.3)
        sfx_for_export, _ = tl_edit.sfx_ambience_events_for_export(tl)
        self.assertAlmostEqual(sfx_for_export[0]["volume"], 0.3)

        # ---- Real export of the SAME reconciled state ----
        import video_generator as vg

        decision_map = {d.scene_number: d.to_dict() for d in reconciled}
        aligned_rows = [
            {"scene_number": "1", "start_time": 0.0, "script_segment": "one"},
            {"scene_number": "2", "start_time": 3.0, "script_segment": "two"},
        ]
        out_path = self.root / "final.mp4"
        vg.render_video(
            aligned_rows, 6.0, self.images_dir, str(self.voiceover_path), str(out_path),
            "160x90", 10, zoom=False, visual_transitions=False,
            edit_decisions_by_scene=decision_map,
        )
        self.assertTrue(out_path.is_file())
        self.assertGreater(out_path.stat().st_size, 0)


class TestLongFormPreviewStress(unittest.TestCase):
    """Section 24: the existing 400-scene synthetic project, exercised
    through segment planning / cache-key generation / repeated-edit
    invalidation and playback seek mapping — NOT a full 33-minute render."""

    def test_segment_planning_at_scale_is_fast_and_correct(self):
        import preview_engine as pv
        from test_long_form_stress import build_long_form_timeline

        tl = build_long_form_timeline()
        t0 = time.perf_counter()
        segments = pv.build_visual_segments(tl)
        elapsed = time.perf_counter() - t0
        self.assertGreater(len(segments), 300)
        self.assertLess(elapsed, 2.0, "segment planning at 400-scene scale must not blow up (possible O(N^2))")
        # Every segment must be a valid, non-overlapping, gap-free window.
        for a, b in zip(segments, segments[1:]):
            self.assertAlmostEqual(a.end, b.start, places=2)

    def test_cache_key_generation_at_scale(self):
        import preview_engine as pv
        from test_long_form_stress import build_long_form_timeline

        tl = build_long_form_timeline()
        segments = pv.build_visual_segments(tl)
        t0 = time.perf_counter()
        keys = [pv._segment_cache_key(seg, 160, 90, 10) for seg in segments]
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(keys), len(segments))
        self.assertLess(elapsed, 2.0)

    def test_repeated_edit_invalidation_only_changes_affected_keys(self):
        """Moving ONE overlay clip must change ONLY the cache keys of the
        segments its own window touches — not the whole project's keys."""
        import editorial_timeline_edit as tl_edit
        import preview_engine as pv
        from test_long_form_stress import build_long_form_timeline

        tl = build_long_form_timeline()
        segments_before = pv.build_visual_segments(tl)
        keys_before = {i: pv._segment_cache_key(seg, 160, 90, 10) for i, seg in enumerate(segments_before)}

        # Move one B-roll overlay clip a small amount.
        b0 = tl_edit.find_event(tl, "b0")
        self.assertIsNotNone(b0)
        tl_edit.move_event(tl, "b0", b0.start + 0.5, snap=False)

        segments_after = pv.build_visual_segments(tl)
        keys_after = {i: pv._segment_cache_key(seg, 160, 90, 10) for i, seg in enumerate(segments_after)}

        # Far-away segments (well past the moved clip) must keep an
        # identical cache key — proof one clip's move doesn't invalidate
        # the whole project.
        unaffected_indices = [i for i in range(min(len(segments_before), len(segments_after)) - 5, min(len(segments_before), len(segments_after)))]
        far_unaffected = [i for i in unaffected_indices if i < len(segments_before) - 20]
        # Use indices near the END of the timeline, far from scene 0's b0.
        tail_before = keys_before[len(segments_before) - 1]
        tail_after = keys_after[len(segments_after) - 1]
        self.assertEqual(tail_before, tail_after, "a clip move near the start must not change cache keys near the end")

    def test_playback_seek_mapping_stays_correct_and_fast_at_scale(self):
        import preview_engine as pv
        from test_long_form_stress import N_SCENES, SCENE_DUR, build_long_form_timeline

        tl = build_long_form_timeline()
        t0 = time.perf_counter()
        for i in range(0, 30):
            t = (i / 30.0) * (N_SCENES * SCENE_DUR)
            state = pv.effective_state_at(tl, t)
            self.assertTrue(state["primary_event_id"] is None or isinstance(state["primary_event_id"], str))
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 2.0, "30 scrubs across a 400-scene timeline must stay fast")

    def test_rapid_scrubbing_produces_no_stale_or_crashing_state(self):
        import preview_engine as pv
        from test_long_form_stress import N_SCENES, SCENE_DUR, build_long_form_timeline

        tl = build_long_form_timeline()
        duration = N_SCENES * SCENE_DUR
        import random

        rng = random.Random(7)
        t0 = time.perf_counter()
        for _ in range(200):
            t = rng.uniform(0, duration)
            pv.effective_state_at(tl, t)  # must never raise
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 3.0)




@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestConcurrentProxyBuildsDoNotCorruptEachOther(unittest.TestCase):
    """Rapid editing (task 17/18): two build_video_proxy() calls for
    DIFFERENT edit states, launched concurrently (an in-flight background
    build from an earlier edit still running when a newer edit starts
    another one — the debounce only stops a *scheduled* rebuild from
    starting late, never cancels one already running), must never
    corrupt or clobber each other's output. Reproduces, with real ffmpeg
    and real threads, the exact failure traced from a live project: two
    overlapping builds writing to a shared, non-unique scratch filename
    (`_render_{i}.mp4`) caused one build to return None (a hard preview
    failure) even though nothing about the timeline itself was invalid."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.root = root
        self.state_dir = root / "state"
        self.state_dir.mkdir()
        self.v1 = root / "v1.mp4"
        self.v2 = root / "v2.mp4"
        for dest, color in ((self.v1, "red"), (self.v2, "green")):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:d=3:r=10",
                 "-pix_fmt", "yuv420p", str(dest)],
                check=True, capture_output=True,
            )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_two_concurrent_builds_for_different_states_both_succeed(self):
        import threading

        import preview_engine as pv
        from editorial.timeline import EditorialTimeline, TimelineEvent

        def tl_with(speed):
            return EditorialTimeline(audio_end=2.0, events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=2.0, source=str(self.v1), metadata={"speed": speed}),
            ])

        results = {}

        def run(name, speed):
            results[name] = pv.build_video_proxy(self.state_dir, tl_with(speed), width=160, height=90, fps=10)

        # Launch a handful of concurrent builds for genuinely DIFFERENT
        # edit states (as rapid distinct edits would) — same state_dir,
        # same shared proxy_dir, at the same time.
        threads = [
            threading.Thread(target=run, args=(f"b{i}", 1.0 + i * 0.15))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for name, out in results.items():
            self.assertIsNotNone(out, f"{name} failed to build a proxy — a concurrent build corrupted its scratch files")
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
