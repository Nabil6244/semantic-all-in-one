"""Unit tests for preview_engine.py's pure logic (segment building, cache
keys). No ffmpeg subprocess is spawned here — render_segment_clip/
build_video_proxy/build_audio_mix are exercised in test_phase2_ui.py style
integration only where ffmpeg is actually available.
"""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from editorial.timeline import EditorialTimeline, TimelineEvent
from preview_engine import (
    _audio_events,
    _segment_cache_key,
    build_visual_segments,
    is_video_source,
    resolve_audio_source,
)


class TestIsVideoSource(unittest.TestCase):
    def test_image_extensions_are_not_video(self):
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            self.assertFalse(is_video_source(f"a{ext}"))

    def test_other_extensions_are_video(self):
        self.assertTrue(is_video_source("clip.mp4"))
        self.assertTrue(is_video_source("clip.mov"))

    def test_empty_source_is_not_video(self):
        self.assertFalse(is_video_source(""))


class TestBuildVisualSegments(unittest.TestCase):
    def test_no_visual_events_yields_one_full_length_gap(self):
        """No video/image events yet (e.g. before asset generation) still
        yields a valid, gap-free segment list — a black filler for the
        whole duration — never an empty/undefined preview."""
        tl = EditorialTimeline(audio_end=10.0, events=[])
        segs = build_visual_segments(tl)
        self.assertEqual(len(segs), 1)
        self.assertTrue(segs[0].is_gap)
        self.assertAlmostEqual(segs[0].start, 0.0)
        self.assertAlmostEqual(segs[0].end, 10.0)

    def test_zero_duration_timeline_returns_empty(self):
        tl = EditorialTimeline(audio_end=0.0, events=[])
        self.assertEqual(build_visual_segments(tl), [])

    def test_single_contiguous_run_yields_matching_segments(self):
        tl = EditorialTimeline(
            audio_end=20.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, source="a.png"),
                TimelineEvent(event_id="v2", track="VIDEO_1", start=10.0, end=20.0, source="b.png"),
            ],
        )
        segs = build_visual_segments(tl)
        self.assertEqual(len(segs), 2)
        self.assertAlmostEqual(segs[0].start, 0.0)
        self.assertAlmostEqual(segs[0].end, 10.0)
        self.assertEqual(segs[0].event.event_id, "v1")
        self.assertAlmostEqual(segs[1].start, 10.0)
        self.assertEqual(segs[1].event.event_id, "v2")

    def test_gap_becomes_a_black_segment(self):
        tl = EditorialTimeline(
            audio_end=20.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=5.0, source="a.png"),
                TimelineEvent(event_id="v2", track="VIDEO_1", start=8.0, end=20.0, source="b.png"),
            ],
        )
        segs = build_visual_segments(tl)
        gap = [s for s in segs if s.is_gap]
        self.assertEqual(len(gap), 1)
        self.assertAlmostEqual(gap[0].start, 5.0)
        self.assertAlmostEqual(gap[0].end, 8.0)

    def test_genuinely_overlapping_video_2_becomes_a_real_overlay_not_a_hard_swap(self):
        """A VIDEO_2 that genuinely overlaps VIDEO_1 in time is now a real
        picture-in-picture OVERLAY on top of VIDEO_1 (composited via
        video_generator.composite_broll_overlay in render_segment_clip) —
        NOT a z-index hard-cut swap that replaces VIDEO_1 outright. This
        supersedes the old simplified z-index-wins behavior."""
        tl = EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, source="a.png", z_index=10),
                TimelineEvent(event_id="v2", track="VIDEO_2", start=4.0, end=10.0, source="b.png", z_index=11),
            ],
        )
        segs = build_visual_segments(tl)
        at_5s = [s for s in segs if s.start <= 5.0 < s.end]
        self.assertEqual(len(at_5s), 1)
        self.assertEqual(at_5s[0].event.event_id, "v1", "VIDEO_1 must remain the base, not be replaced")
        self.assertIsNotNone(at_5s[0].overlay)
        self.assertEqual(at_5s[0].overlay.event_id, "v2")
        # Before the overlap window (t<4), no overlay is active.
        before = [s for s in segs if s.start <= 2.0 < s.end]
        self.assertEqual(len(before), 1)
        self.assertIsNone(before[0].overlay)

    def test_segments_never_gap_or_overlap_each_other(self):
        tl = EditorialTimeline(
            audio_end=15.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=4.0, source="a.png"),
                TimelineEvent(event_id="v2", track="IMAGE", start=4.0, end=9.0, source="b.png"),
                TimelineEvent(event_id="v3", track="VIDEO_1", start=9.0, end=15.0, source="c.mp4"),
            ],
        )
        segs = build_visual_segments(tl)
        for prev, nxt in zip(segs, segs[1:]):
            self.assertAlmostEqual(prev.end, nxt.start)
        self.assertAlmostEqual(segs[0].start, 0.0)
        self.assertAlmostEqual(segs[-1].end, 15.0)


class TestSegmentCacheKey(unittest.TestCase):
    def test_same_inputs_same_key(self):
        tl = EditorialTimeline(audio_end=10.0, events=[TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=5.0, source="")])
        segs = build_visual_segments(tl)
        k1 = _segment_cache_key(segs[0], 480, 270, 15)
        k2 = _segment_cache_key(segs[0], 480, 270, 15)
        self.assertEqual(k1, k2)

    def test_different_duration_different_key(self):
        seg_a = build_visual_segments(EditorialTimeline(audio_end=5.0, events=[TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=5.0, source="")]))[0]
        seg_b = build_visual_segments(EditorialTimeline(audio_end=7.0, events=[TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=7.0, source="")]))[0]
        self.assertNotEqual(
            _segment_cache_key(seg_a, 480, 270, 15),
            _segment_cache_key(seg_b, 480, 270, 15),
        )


class TestAudioEvents(unittest.TestCase):
    """_audio_events() now validates the source actually resolves to a real
    file (via resolve_audio_source) rather than just checking truthiness —
    real project files, so the fixture uses real (empty) temp files rather
    than fake "vo.wav"-style paths that were never openable anyway."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._vo = Path(self._tmpdir.name) / "vo.wav"
        self._mu = Path(self._tmpdir.name) / "mu.wav"
        self._am = Path(self._tmpdir.name) / "am.wav"
        for p in (self._vo, self._mu, self._am):
            p.write_bytes(b"")

    def tearDown(self):
        self._tmpdir.cleanup()

    def _timeline(self):
        return EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(event_id="vo", track="VOICEOVER", start=0.0, end=10.0, source=str(self._vo)),
                TimelineEvent(event_id="mu", track="MUSIC", start=0.0, end=10.0, source=str(self._mu)),
                TimelineEvent(event_id="am", track="AMBIENCE", start=0.0, end=10.0, source=str(self._am), metadata={"muted": True}),
            ],
        )

    def test_muted_event_metadata_excluded(self):
        events = _audio_events(self._timeline())
        ids = {e.event_id for e in events}
        self.assertIn("vo", ids)
        self.assertIn("mu", ids)
        self.assertNotIn("am", ids)

    def test_muted_track_excluded(self):
        events = _audio_events(self._timeline(), muted_tracks=frozenset({"MUSIC"}))
        ids = {e.event_id for e in events}
        self.assertNotIn("mu", ids)
        self.assertIn("vo", ids)

    def test_solo_track_excludes_others(self):
        events = _audio_events(self._timeline(), solo_tracks=frozenset({"VOICEOVER"}))
        ids = {e.event_id for e in events}
        self.assertEqual(ids, {"vo"})

    def test_events_without_source_excluded(self):
        tl = EditorialTimeline(audio_end=5.0, events=[TimelineEvent(event_id="x", track="SFX", start=0, end=1, source="")])
        self.assertEqual(_audio_events(tl), [])


class TestResolveAudioSource(unittest.TestCase):
    """The SFX/AMBIENCE bridge (editorial_timeline_edit.
    materialize_sfx_ambience_events) stores a catalog-RELATIVE path — this
    is the function that turns that back into something ffmpeg can open,
    matching smart_editing._resolve_sfx_file's own resolution contract."""

    def test_absolute_existing_source_passes_through(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.wav"
            p.write_bytes(b"")
            ev = TimelineEvent(event_id="e", track="VOICEOVER", start=0, end=1, source=str(p))
            self.assertEqual(resolve_audio_source(ev), str(p))

    def test_missing_absolute_source_returns_empty(self):
        ev = TimelineEvent(event_id="e", track="MUSIC", start=0, end=1, source="/nonexistent/x.wav")
        self.assertEqual(resolve_audio_source(ev), "")

    def test_sfx_catalog_relative_path_resolves_against_library_root(self):
        import smart_editing

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "whoosh").mkdir()
            (root / "whoosh" / "w1.wav").write_bytes(b"")
            orig = smart_editing.sfx_library_root
            smart_editing.sfx_library_root = lambda: root
            try:
                ev = TimelineEvent(
                    event_id="s", track="SFX", start=0, end=1, source="whoosh/w1.wav",
                    metadata={"file": "whoosh/w1.wav"},
                )
                resolved = resolve_audio_source(ev)
                self.assertEqual(resolved, str(root / "whoosh" / "w1.wav"))
            finally:
                smart_editing.sfx_library_root = orig

    def test_sfx_unresolvable_catalog_path_returns_empty(self):
        ev = TimelineEvent(event_id="s", track="SFX", start=0, end=1, metadata={"file": "nope/nope.wav"})
        self.assertEqual(resolve_audio_source(ev), "")


class TestEffectiveStateAt(unittest.TestCase):
    """The PREVIEW SEMANTIC SNAPSHOT helper — deterministic, no ffmpeg
    needed — used to verify preview/export parity without pixel diffs."""

    def _tl(self):
        return EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(
                    event_id="v1", track="VIDEO_1", start=0.0, end=6.0, source="a.mp4",
                    metadata={"source_start": 1.0, "speed": 1.0},
                ),
                TimelineEvent(
                    event_id="v2", track="VIDEO_1", start=6.0, end=10.0, source="b.mp4",
                    transition_in="crossfade", metadata={"transition_duration": 0.5, "speed": 1.0},
                ),
                TimelineEvent(
                    event_id="b1", track="VIDEO_2", start=1.0, end=3.0, source="broll.mp4",
                    metadata={"source_start": 0.0, "speed": 2.0},
                ),
                TimelineEvent(event_id="sfx1", track="SFX", start=0.5, end=1.0, metadata={"file": "/x/s.wav", "volume": 0.6}),
                TimelineEvent(event_id="voA", track="VOICEOVER", start=0.0, end=10.0, source="/x/vo.wav", metadata={"volume": 1.0}),
            ],
        )

    def test_primary_and_overlay_identity_during_overlap(self):
        from preview_engine import effective_state_at

        with unittest.mock.patch("preview_engine.resolve_audio_source", side_effect=lambda e: str(e.source or (e.metadata or {}).get("file") or "")):
            state = effective_state_at(self._tl(), 2.0)
        self.assertEqual(state["primary_event_id"], "v1")
        self.assertEqual(state["overlay_event_id"], "b1")

    def test_no_overlay_outside_overlap_window(self):
        from preview_engine import effective_state_at

        with unittest.mock.patch("preview_engine.resolve_audio_source", side_effect=lambda e: str(e.source or (e.metadata or {}).get("file") or "")):
            state = effective_state_at(self._tl(), 4.5)
        self.assertEqual(state["primary_event_id"], "v1")
        self.assertIsNone(state["overlay_event_id"])

    def test_overlay_effective_source_time_respects_its_own_speed(self):
        from preview_engine import effective_state_at

        with unittest.mock.patch("preview_engine.resolve_audio_source", side_effect=lambda e: str(e.source or (e.metadata or {}).get("file") or "")):
            state = effective_state_at(self._tl(), 2.0)  # 1.0s into b1's own [1,3) window
        self.assertAlmostEqual(state["overlay_speed"], 2.0)
        self.assertAlmostEqual(state["overlay_effective_source_time"], 2.0)  # 1.0s elapsed * 2x speed

    def test_transition_state_active_only_inside_its_window_at_a_real_cut(self):
        from preview_engine import effective_state_at

        with unittest.mock.patch("preview_engine.resolve_audio_source", side_effect=lambda e: str(e.source or (e.metadata or {}).get("file") or "")):
            during = effective_state_at(self._tl(), 6.2)  # just after the v1->v2 cut, inside 0.5s crossfade
            after = effective_state_at(self._tl(), 7.0)  # well past the transition window
        self.assertIsNotNone(during["transition"])
        self.assertEqual(during["transition"]["type"], "crossfade")
        self.assertAlmostEqual(during["transition"]["duration"], 0.5)
        self.assertIsNone(after["transition"])

    def test_active_audio_reflects_volume_and_excludes_muted_tracks(self):
        from preview_engine import effective_state_at

        with unittest.mock.patch("preview_engine.resolve_audio_source", side_effect=lambda e: str(e.source or (e.metadata or {}).get("file") or "")):
            state = effective_state_at(self._tl(), 0.7)
            muted_state = effective_state_at(self._tl(), 0.7, muted_tracks=frozenset({"SFX"}))
        sfx_entries = [a for a in state["audio"] if a["track"] == "SFX"]
        self.assertEqual(len(sfx_entries), 1)
        self.assertAlmostEqual(sfx_entries[0]["volume"], 0.6)
        self.assertFalse(any(a["track"] == "SFX" for a in muted_state["audio"]))


if __name__ == "__main__":
    unittest.main()
