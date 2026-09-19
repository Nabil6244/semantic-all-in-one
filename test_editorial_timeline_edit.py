"""Regression tests for editorial_timeline_edit.py (Semantic YT Studio 2.0 —
Phase 2 interactive timeline). Pure data-transform logic — no Tk, no ffmpeg.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from editorial.timeline import EditorialTimeline, TimelineEvent
from editorial_timeline_edit import (
    add_event,
    delete_event,
    duplicate_event,
    find_event,
    insert_visual_clip,
    is_editable,
    is_freely_movable,
    load_timeline,
    move_event,
    move_visual_event_to_index,
    reconcile_timeline_into_decisions,
    reorder_visual_event,
    replace_event_source,
    save_timeline,
    scene_boundaries,
    set_event_property,
    snap_time,
    split_event,
    trim_event_end,
    trim_event_start,
    visual_sequence_order,
)


def _timeline():
    return EditorialTimeline(
        version=1,
        audio_end=20.0,
        events=[
            TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, scene_number="1"),
            TimelineEvent(event_id="v2", track="VIDEO_1", start=10.0, end=20.0, scene_number="2"),
            TimelineEvent(event_id="t1", track="TEXT", start=1.0, end=3.0, scene_number="1"),
            TimelineEvent(event_id="s1", track="SFX", start=5.0, end=5.5, scene_number="1"),
        ],
    )


class TestEditability(unittest.TestCase):
    def test_video_track_is_editable_but_not_freely_movable(self):
        tl = _timeline()
        v1 = find_event(tl, "v1")
        self.assertTrue(is_editable(v1))
        self.assertFalse(is_freely_movable(v1))

    def test_text_track_is_freely_movable(self):
        tl = _timeline()
        self.assertTrue(is_editable(find_event(tl, "t1")))
        self.assertTrue(is_freely_movable(find_event(tl, "t1")))


class TestMove(unittest.TestCase):
    def test_move_text_event_preserves_duration(self):
        tl = _timeline()
        ok = move_event(tl, "t1", 8.0, snap=False)
        self.assertTrue(ok)
        ev = find_event(tl, "t1")
        self.assertAlmostEqual(ev.start, 8.0)
        self.assertAlmostEqual(ev.end, 10.0)

    def test_move_video_event_is_rejected(self):
        """Free drag-to-anywhere is rejected for visual tracks — they ripple
        via trim/reorder instead (see TestVisualRipple)."""
        tl = _timeline()
        ok = move_event(tl, "v1", 5.0, snap=False)
        self.assertFalse(ok)
        ev = find_event(tl, "v1")
        self.assertEqual(ev.start, 0.0)

    def test_move_clamps_to_audio_end(self):
        tl = _timeline()
        move_event(tl, "t1", 19.0, snap=False)
        ev = find_event(tl, "t1")
        self.assertLessEqual(ev.end, 20.0)

    def test_move_missing_event_returns_false(self):
        tl = _timeline()
        self.assertFalse(move_event(tl, "nope", 5.0))

    def test_move_snaps_to_scene_boundary(self):
        tl = _timeline()
        # t1 is 2s long; moving near 9.9 should snap its start to 10.0
        # (a scene boundary) within the default 0.25s tolerance.
        move_event(tl, "t1", 9.9, snap=True)
        ev = find_event(tl, "t1")
        self.assertAlmostEqual(ev.start, 10.0)


class TestTrim(unittest.TestCase):
    def test_trim_start_shortens_from_the_left(self):
        tl = _timeline()
        ok = trim_event_start(tl, "t1", 2.0, snap=False)
        self.assertTrue(ok)
        self.assertAlmostEqual(find_event(tl, "t1").start, 2.0)

    def test_trim_start_rejects_crossing_the_end(self):
        tl = _timeline()
        ok = trim_event_start(tl, "t1", 2.99, snap=False)
        self.assertFalse(ok)

    def test_trim_end_lengthens_or_shortens_from_the_right(self):
        tl = _timeline()
        ok = trim_event_end(tl, "t1", 4.0, snap=False)
        self.assertTrue(ok)
        self.assertAlmostEqual(find_event(tl, "t1").end, 4.0)

    def test_trim_end_clamped_to_audio_end(self):
        tl = _timeline()
        trim_event_end(tl, "t1", 999.0, snap=False)
        self.assertLessEqual(find_event(tl, "t1").end, 20.0)

    def test_trim_video_track_start_later_ripples(self):
        """v1 [0,10), v2 [10,20). Trimming v1's start later by 2s shrinks
        v1 and ripples v2 (and everything after) 2s earlier."""
        tl = _timeline()
        ok = trim_event_start(tl, "v1", 2.0, snap=False)
        self.assertTrue(ok)
        self.assertAlmostEqual(find_event(tl, "v1").start, 2.0)
        self.assertAlmostEqual(find_event(tl, "v2").start, 8.0)
        self.assertAlmostEqual(find_event(tl, "v2").end, 18.0)

    def test_trim_video_track_start_earlier_rejected(self):
        """Trimming v1's start EARLIER would overlap nothing (v1 starts at
        0), but as a general rule extending a clip backward is rejected —
        only shortening (start moving later) is a safe ripple direction."""
        tl = _timeline()
        self.assertFalse(trim_event_start(tl, "v2", 8.0, snap=False))


class TestSplit(unittest.TestCase):
    def test_split_creates_two_contiguous_events(self):
        tl = _timeline()
        new_id = split_event(tl, "t1", 2.0)
        self.assertIsNotNone(new_id)
        first = find_event(tl, "t1")
        second = find_event(tl, new_id)
        self.assertAlmostEqual(first.end, 2.0)
        self.assertAlmostEqual(second.start, 2.0)
        self.assertAlmostEqual(second.end, 3.0)

    def test_split_too_close_to_edge_is_rejected(self):
        tl = _timeline()
        self.assertIsNone(split_event(tl, "t1", 1.02))

    def test_split_video_track_is_now_supported(self):
        tl = _timeline()
        new_id = split_event(tl, "v1", 5.0)
        self.assertIsNotNone(new_id)
        first, second = find_event(tl, "v1"), find_event(tl, new_id)
        self.assertAlmostEqual(first.end, 5.0)
        self.assertAlmostEqual(second.start, 5.0)
        self.assertAlmostEqual(second.end, 10.0)


class TestDelete(unittest.TestCase):
    def test_delete_removes_editable_event(self):
        tl = _timeline()
        self.assertTrue(delete_event(tl, "s1"))
        self.assertIsNone(find_event(tl, "s1"))

    def test_delete_video_event_ripples_close_the_gap(self):
        tl = _timeline()
        self.assertTrue(delete_event(tl, "v1"))
        self.assertIsNone(find_event(tl, "v1"))
        # v2 was [10,20) — deleting the 10s-long v1 ripples it to [0,10).
        v2 = find_event(tl, "v2")
        self.assertAlmostEqual(v2.start, 0.0)
        self.assertAlmostEqual(v2.end, 10.0)


class TestAdd(unittest.TestCase):
    def test_add_sfx_event(self):
        tl = _timeline()
        new_id = add_event(tl, track="SFX", start=12.0, end=12.5, scene_number="2")
        self.assertIsNotNone(new_id)
        self.assertIsNotNone(find_event(tl, new_id))

    def test_add_to_video_track_rejected(self):
        """add_event() is for freely-movable tracks; visual inserts use
        insert_visual_clip() so they ripple correctly."""
        tl = _timeline()
        self.assertIsNone(add_event(tl, track="VIDEO_1", start=0.0, end=1.0))

    def test_add_with_bad_range_rejected(self):
        tl = _timeline()
        self.assertIsNone(add_event(tl, track="SFX", start=5.0, end=5.0))


class TestVisualRipple(unittest.TestCase):
    def test_duplicate_video_event_ripples_later_clips(self):
        tl = _timeline()
        new_id = duplicate_event(tl, "v1")
        self.assertIsNotNone(new_id)
        dup = find_event(tl, new_id)
        self.assertAlmostEqual(dup.start, 10.0)
        self.assertAlmostEqual(dup.end, 20.0)
        v2 = find_event(tl, "v2")
        self.assertAlmostEqual(v2.start, 20.0)
        self.assertAlmostEqual(v2.end, 30.0)

    def test_reorder_visual_event_swaps_content_not_slots(self):
        tl = _timeline()
        find_event(tl, "v1").source = "clip_a.mp4"
        find_event(tl, "v2").source = "clip_b.mp4"
        ok = reorder_visual_event(tl, "v2", direction="earlier")
        self.assertTrue(ok)
        v1, v2 = find_event(tl, "v1"), find_event(tl, "v2")
        # Content traded places...
        self.assertEqual(v1.source, "clip_b.mp4")
        self.assertEqual(v2.source, "clip_a.mp4")
        # ...but timeline slots (and event_ids) stayed put — gap-free by
        # construction, no ripple math needed.
        self.assertAlmostEqual(v1.start, 0.0)
        self.assertAlmostEqual(v2.start, 10.0)

    def test_insert_visual_clip_ripples_and_lands_at_boundary(self):
        tl = _timeline()
        new_id = insert_visual_clip(
            tl, track="IMAGE", at_time=10.0, duration=5.0, scene_number="2",
        )
        self.assertIsNotNone(new_id)
        new_ev = find_event(tl, new_id)
        self.assertAlmostEqual(new_ev.start, 10.0)
        self.assertAlmostEqual(new_ev.end, 15.0)
        v2 = find_event(tl, "v2")
        self.assertAlmostEqual(v2.start, 15.0)
        self.assertAlmostEqual(v2.end, 25.0)

    def test_replace_event_source_keeps_timing(self):
        tl = _timeline()
        ok = replace_event_source(tl, "v1", new_source="broll_2.png")
        self.assertTrue(ok)
        ev = find_event(tl, "v1")
        self.assertEqual(ev.source, "broll_2.png")
        self.assertAlmostEqual(ev.start, 0.0)
        self.assertAlmostEqual(ev.end, 10.0)

    def test_set_event_property_direct_field(self):
        tl = _timeline()
        self.assertTrue(set_event_property(tl, "v1", scale=1.2))
        self.assertAlmostEqual(find_event(tl, "v1").scale, 1.2)

    def test_set_event_property_metadata_field(self):
        tl = _timeline()
        self.assertTrue(set_event_property(tl, "s1", volume=0.4, muted=True))
        ev = find_event(tl, "s1")
        self.assertAlmostEqual(ev.metadata["volume"], 0.4)
        self.assertTrue(ev.metadata["muted"])


def _three_clip_timeline():
    return EditorialTimeline(
        version=1,
        audio_end=15.0,
        events=[
            TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=5.0, source="a.png"),
            TimelineEvent(event_id="v2", track="VIDEO_1", start=5.0, end=10.0, source="b.png"),
            TimelineEvent(event_id="v3", track="VIDEO_1", start=10.0, end=15.0, source="c.png"),
        ],
    )


class TestDragToReorder(unittest.TestCase):
    """move_visual_event_to_index is what makes dragging a video/image clip
    on the timeline actually move it (a plain "clip can't be moved" bug
    report traced to this being missing — plain middle-drag was silently a
    no-op for visual tracks before this)."""

    def test_visual_sequence_order_matches_start_time(self):
        tl = _three_clip_timeline()
        self.assertEqual([e.event_id for e in visual_sequence_order(tl)], ["v1", "v2", "v3"])

    def test_move_first_clip_to_last_position(self):
        tl = _three_clip_timeline()
        ok = move_visual_event_to_index(tl, "v1", 2)
        self.assertTrue(ok)
        order = [e.event_id for e in visual_sequence_order(tl)]
        self.assertEqual(order, ["v2", "v3", "v1"])
        # Each clip keeps its own duration; positions are back-to-back with no gap.
        v2, v3, v1 = (find_event(tl, i) for i in order)
        self.assertAlmostEqual(v2.start, 0.0)
        self.assertAlmostEqual(v2.end, 5.0)
        self.assertAlmostEqual(v3.start, 5.0)
        self.assertAlmostEqual(v3.end, 10.0)
        self.assertAlmostEqual(v1.start, 10.0)
        self.assertAlmostEqual(v1.end, 15.0)

    def test_move_last_clip_to_first_position(self):
        tl = _three_clip_timeline()
        move_visual_event_to_index(tl, "v3", 0)
        self.assertEqual([e.event_id for e in visual_sequence_order(tl)], ["v3", "v1", "v2"])

    def test_move_middle_clip_stays_put_is_a_noop_on_order(self):
        tl = _three_clip_timeline()
        move_visual_event_to_index(tl, "v2", 1)
        self.assertEqual([e.event_id for e in visual_sequence_order(tl)], ["v1", "v2", "v3"])

    def test_out_of_range_index_clamps_instead_of_failing(self):
        tl = _three_clip_timeline()
        ok = move_visual_event_to_index(tl, "v1", 999)
        self.assertTrue(ok)
        self.assertEqual(visual_sequence_order(tl)[-1].event_id, "v1")

    def test_non_visual_track_rejected(self):
        tl = _timeline()  # has a TEXT event "t1"
        self.assertFalse(move_visual_event_to_index(tl, "t1", 0))

    def test_missing_event_rejected(self):
        tl = _three_clip_timeline()
        self.assertFalse(move_visual_event_to_index(tl, "nope", 0))


class TestReconcile(unittest.TestCase):
    def test_reconcile_rebuilds_shots_from_edited_timeline(self):
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(
                scene_number="1",
                required_duration=10.0,
                shots=[ShotSpec(shot_id="orig-shot", output_duration=10.0, source_path="a.png")],
            ),
        ]
        tl = EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(
                    event_id="edited-shot", track="VIDEO_1", start=0.0, end=6.0,
                    scene_number="1", source="a.png", scale=1.3,
                    metadata={"speed": 1.5, "source_start": 1.0},
                ),
            ],
        )
        out = reconcile_timeline_into_decisions(decisions, tl)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0].shots), 1)
        shot = out[0].shots[0]
        self.assertEqual(shot.shot_id, "edited-shot")
        self.assertAlmostEqual(shot.output_duration, 6.0)
        self.assertAlmostEqual(shot.scale, 1.3)
        self.assertAlmostEqual(shot.speed, 1.5)
        self.assertAlmostEqual(shot.source_start, 1.0)

    def test_reconcile_leaves_scene_unchanged_when_all_visuals_deleted(self):
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(
                scene_number="1", required_duration=10.0,
                shots=[ShotSpec(shot_id="orig-shot", output_duration=10.0, source_path="a.png")],
            ),
        ]
        tl = EditorialTimeline(audio_end=10.0, events=[])
        out = reconcile_timeline_into_decisions(decisions, tl)
        self.assertEqual(out[0].shots[0].shot_id, "orig-shot")


class TestSnapAndBoundaries(unittest.TestCase):
    def test_scene_boundaries_include_video_edges(self):
        tl = _timeline()
        bounds = scene_boundaries(tl)
        self.assertIn(0.0, bounds)
        self.assertIn(10.0, bounds)
        self.assertIn(20.0, bounds)

    def test_snap_time_within_tolerance(self):
        self.assertAlmostEqual(snap_time(9.9, [0.0, 10.0, 20.0]), 10.0)

    def test_snap_time_outside_tolerance_unchanged(self):
        self.assertAlmostEqual(snap_time(5.0, [0.0, 10.0, 20.0]), 5.0)

    def test_snap_time_no_bounds_unchanged(self):
        self.assertAlmostEqual(snap_time(5.0, []), 5.0)


class TestPersistence(unittest.TestCase):
    def test_load_timeline_missing_project_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            tl = load_timeline(Path(td))
            self.assertEqual(tl.events, [])

    def test_load_timeline_old_project_with_no_timeline_key_is_empty(self):
        """Backward compatibility (spec item T): a pre-Phase-2 project's
        editorial_plan.json has scenes but no "timeline" key at all — must
        get a valid, empty EditorialTimeline, never a crash or invented data."""
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "editorial_plan.json").write_text(
                json.dumps({"scenes": [{"scene_number": "1", "start": 0, "end": 5}]}),
                encoding="utf-8",
            )
            tl = load_timeline(state_dir)
            self.assertEqual(tl.events, [])
            self.assertEqual(tl.audio_end, 0.0)

    def test_save_then_load_round_trips(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            plan_path = state_dir / "editorial_plan.json"
            plan_path.write_text(json.dumps({"scenes": [{"scene_number": "1"}]}), encoding="utf-8")

            tl = _timeline()
            ok = save_timeline(state_dir, tl)
            self.assertTrue(ok)

            reloaded = load_timeline(state_dir)
            self.assertEqual(len(reloaded.events), len(tl.events))
            self.assertIsNotNone(find_event(reloaded, "t1"))

    def test_save_preserves_other_plan_fields(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            plan_path = state_dir / "editorial_plan.json"
            plan_path.write_text(
                json.dumps({"scenes": [{"scene_number": "1"}], "hook_window_s": 30}),
                encoding="utf-8",
            )
            save_timeline(state_dir, _timeline())
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(data["hook_window_s"], 30)
            self.assertIn("timeline", data)

    def test_save_without_existing_plan_is_a_safe_noop(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            ok = save_timeline(state_dir, _timeline())
            self.assertFalse(ok)
            self.assertFalse((state_dir / "editorial_plan.json").exists())


if __name__ == "__main__":
    unittest.main()


class TestSpeedConsistency(unittest.TestCase):
    """The renderer used to silently clamp speed to [0.8, 1.25] while the
    Inspector/preview allowed [0.25, 2.0] — a confirmed preview/export
    divergence. clamp_speed() is now the ONE range every layer uses."""

    def test_clamp_speed_matches_declared_range(self):
        from editorial_timeline_edit import MAX_SPEED, MIN_SPEED, clamp_speed

        self.assertAlmostEqual(clamp_speed(0.1), MIN_SPEED)
        self.assertAlmostEqual(clamp_speed(5.0), MAX_SPEED)
        self.assertAlmostEqual(clamp_speed(1.5), 1.5)
        self.assertAlmostEqual(clamp_speed(0.25), 0.25)
        self.assertAlmostEqual(clamp_speed(2.0), 2.0)

    def test_clamp_speed_handles_bad_input(self):
        from editorial_timeline_edit import clamp_speed

        self.assertAlmostEqual(clamp_speed(None), 1.0)
        self.assertAlmostEqual(clamp_speed("nonsense"), 1.0)

    def test_renderer_uses_shared_clamp_not_a_narrower_hardcoded_range(self):
        import inspect

        import video_generator as vg

        src = inspect.getsource(vg._render_editorial_shot)
        self.assertIn("clamp_speed", src)
        self.assertNotIn("min(1.25, max(0.8, speed))", src)

    def test_preview_engine_uses_shared_clamp(self):
        import inspect

        import preview_engine as pe

        src = inspect.getsource(pe.render_segment_clip)
        self.assertIn("clamp_speed", src)


class TestSfxAmbienceBridge(unittest.TestCase):
    """The critical fix this pass makes: SFX/AMBIENCE edits made in the
    Editor used to have ZERO effect on export, because export re-derived a
    fresh smart_editing plan every time instead of reading the operator's
    (possibly edited) timeline. materialize_sfx_ambience_events() puts the
    REAL planned events onto the timeline at first-cut time;
    sfx_ambience_events_for_export() reads them back (with edits) at
    export time."""

    def test_materialize_replaces_semantic_placeholders_with_real_events(self):
        from editorial_timeline_edit import materialize_sfx_ambience_events

        tl = EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(event_id="stub_sfx", track="SFX", start=1.0, end=1.5, metadata={"sfx_action": "subtle_hit"}),
            ],
        )
        materialize_sfx_ambience_events(
            tl,
            sfx_events=[{"start": 2.0, "end": 2.5, "volume": 0.9, "file": "whoosh/w1.wav"}],
            ambience_beds=[{"start": 0.0, "end": 10.0, "volume": 0.2, "file": "amb/city.wav", "profile": "city"}],
        )
        sfx = [e for e in tl.events if e.track == "SFX"]
        amb = [e for e in tl.events if e.track == "AMBIENCE"]
        self.assertEqual(len(sfx), 1)
        self.assertNotEqual(sfx[0].event_id, "stub_sfx")  # semantic placeholder is gone
        self.assertAlmostEqual(sfx[0].start, 2.0)
        self.assertEqual(sfx[0].metadata["file"], "whoosh/w1.wav")
        self.assertEqual(len(amb), 1)
        self.assertEqual(amb[0].metadata["profile"], "city")

    def test_materialize_with_no_plan_clears_sfx_ambience(self):
        from editorial_timeline_edit import materialize_sfx_ambience_events

        tl = EditorialTimeline(
            audio_end=5.0,
            events=[TimelineEvent(event_id="old", track="SFX", start=0, end=1)],
        )
        materialize_sfx_ambience_events(tl, sfx_events=[], ambience_beds=[])
        self.assertEqual([e for e in tl.events if e.track in ("SFX", "AMBIENCE")], [])

    def test_export_bridge_round_trips_operator_edits(self):
        from editorial_timeline_edit import (
            materialize_sfx_ambience_events,
            sfx_ambience_events_for_export,
            set_event_property,
        )

        tl = EditorialTimeline(audio_end=10.0)
        materialize_sfx_ambience_events(
            tl,
            sfx_events=[
                {"start": 1.0, "end": 1.5, "volume": 1.0, "file": "a.wav"},
                {"start": 3.0, "end": 3.5, "volume": 1.0, "file": "b.wav"},
            ],
            ambience_beds=[{"start": 0.0, "end": 10.0, "volume": 0.15, "file": "c.wav", "profile": "office"}],
        )
        sfx_events = [e for e in tl.events if e.track == "SFX"]
        # Operator deletes one SFX event and turns the volume down on the other.
        tl.events.remove(sfx_events[0])
        set_event_property(tl, sfx_events[1].event_id, volume=0.3)

        sfx, ambience = sfx_ambience_events_for_export(tl)
        self.assertEqual(len(sfx), 1)  # the deleted one really is gone from export
        self.assertAlmostEqual(sfx[0]["volume"], 0.3)  # the volume edit really reached export
        self.assertEqual(sfx[0]["file"], "b.wav")
        self.assertEqual(len(ambience), 1)
        self.assertEqual(ambience[0]["profile"], "office")

    def test_export_bridge_honors_muted_event(self):
        from editorial_timeline_edit import materialize_sfx_ambience_events, sfx_ambience_events_for_export, set_event_property

        tl = EditorialTimeline(audio_end=5.0)
        materialize_sfx_ambience_events(tl, sfx_events=[{"start": 1.0, "end": 1.5, "file": "a.wav"}])
        ev_id = [e for e in tl.events if e.track == "SFX"][0].event_id
        set_event_property(tl, ev_id, muted=True)
        sfx, _ = sfx_ambience_events_for_export(tl)
        self.assertEqual(sfx, [])

    def test_export_bridge_honors_track_level_mute(self):
        from editorial_timeline_edit import materialize_sfx_ambience_events, sfx_ambience_events_for_export

        tl = EditorialTimeline(audio_end=5.0)
        materialize_sfx_ambience_events(tl, sfx_events=[{"start": 1.0, "end": 1.5, "file": "a.wav"}])
        sfx, _ = sfx_ambience_events_for_export(tl, muted_tracks=frozenset({"SFX"}))
        self.assertEqual(sfx, [])

    def test_export_bridge_honors_solo(self):
        from editorial_timeline_edit import materialize_sfx_ambience_events, sfx_ambience_events_for_export

        tl = EditorialTimeline(audio_end=5.0)
        materialize_sfx_ambience_events(
            tl,
            sfx_events=[{"start": 1.0, "end": 1.5, "file": "a.wav"}],
            ambience_beds=[{"start": 0.0, "end": 5.0, "file": "b.wav"}],
        )
        sfx, ambience = sfx_ambience_events_for_export(tl, solo_tracks=frozenset({"AMBIENCE"}))
        self.assertEqual(sfx, [])
        self.assertEqual(len(ambience), 1)


class TestTrackMuteSoloPersistence(unittest.TestCase):
    def test_muted_solo_round_trip_through_to_dict(self):
        tl = EditorialTimeline(audio_end=5.0, muted_tracks=["MUSIC"], solo_tracks=["VOICEOVER"])
        data = tl.to_dict()
        self.assertEqual(data["muted_tracks"], ["MUSIC"])
        self.assertEqual(data["solo_tracks"], ["VOICEOVER"])
        restored = EditorialTimeline.from_dict(data)
        self.assertEqual(restored.muted_tracks, ["MUSIC"])
        self.assertEqual(restored.solo_tracks, ["VOICEOVER"])

    def test_old_timeline_without_mute_solo_keys_defaults_empty(self):
        restored = EditorialTimeline.from_dict({"version": 1, "audio_end": 5.0, "events": []})
        self.assertEqual(restored.muted_tracks, [])
        self.assertEqual(restored.solo_tracks, [])

    def test_save_load_round_trips_mute_solo(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "editorial_plan.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            tl = EditorialTimeline(audio_end=5.0, muted_tracks=["AMBIENCE"], solo_tracks=[])
            save_timeline(state_dir, tl)
            reloaded = load_timeline(state_dir)
            self.assertEqual(reloaded.muted_tracks, ["AMBIENCE"])


class TestTransitionReconciliation(unittest.TestCase):
    """An operator-picked real transition (Inspector -> TimelineEvent.
    transition_in + metadata["transition_duration"]) must reach the
    ShotSpec render_video() actually reads — this is what closes the loop
    from "Inspector control" to "genuinely affects the export"."""

    def test_transition_duration_reaches_shotspec(self):
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(
                scene_number="2", required_duration=5.0,
                shots=[ShotSpec(shot_id="orig", output_duration=5.0, source_path="b.png")],
            ),
        ]
        tl = EditorialTimeline(
            audio_end=5.0,
            events=[
                TimelineEvent(
                    event_id="v2", track="VIDEO_1", start=0.0, end=5.0,
                    scene_number="2", source="b.png",
                    transition_in="crossfade",
                    metadata={"transition_duration": 0.6},
                ),
            ],
        )
        out = reconcile_timeline_into_decisions(decisions, tl)
        shot = out[0].shots[0]
        self.assertEqual(shot.transition_in, "crossfade")
        self.assertAlmostEqual(shot.transition_duration, 0.6)

    def test_cut_transition_has_zero_duration_by_default(self):
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [EditDecision(scene_number="1", required_duration=3.0, shots=[ShotSpec(shot_id="o", output_duration=3.0)])]
        tl = EditorialTimeline(
            audio_end=3.0,
            events=[TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=3.0, scene_number="1")],
        )
        out = reconcile_timeline_into_decisions(decisions, tl)
        self.assertAlmostEqual(out[0].shots[0].transition_duration, 0.0)


class TestCloseReopenPersistence(unittest.TestCase):
    """Explicit close/reopen test: build a timeline touching every kind of
    operator edit this pass added (speed, transition, source offsets,
    track mute/solo, volume/fade metadata), save it, reload it as a FRESH
    EditorialTimeline object (simulating the project being closed and the
    app relaunched), and verify every field survived exactly."""

    def test_full_round_trip_of_every_edit_kind(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "editorial_plan.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")

            original = EditorialTimeline(
                audio_end=12.0,
                muted_tracks=["MUSIC"],
                solo_tracks=[],
                events=[
                    TimelineEvent(
                        event_id="v1", track="VIDEO_1", start=0.0, end=5.0,
                        scene_number="1", source="a.mp4", scale=1.2,
                        position_x=0.4, position_y=0.6,
                        transition_in="wipe",
                        metadata={
                            "speed": 1.5, "source_start": 0.5, "source_end": 4.0,
                            "transition_duration": 0.3, "hold_tail": True,
                        },
                    ),
                    TimelineEvent(
                        event_id="sfx1", track="SFX", start=6.0, end=6.5,
                        source="whoosh/w1.wav",
                        metadata={"file": "whoosh/w1.wav", "volume": 0.7, "muted": False},
                    ),
                    TimelineEvent(
                        event_id="vo1", track="VOICEOVER", start=0.0, end=12.0,
                        source="narration.wav",
                        metadata={"volume": 1.0, "fade_in": 0.2, "fade_out": 0.5},
                    ),
                ],
            )
            ok = save_timeline(state_dir, original)
            self.assertTrue(ok)

            # Simulate "close the app" by discarding every in-memory
            # reference and reloading purely from disk.
            del original
            reopened = load_timeline(state_dir)

            self.assertAlmostEqual(reopened.audio_end, 12.0)
            self.assertEqual(reopened.muted_tracks, ["MUSIC"])

            v1 = find_event(reopened, "v1")
            self.assertIsNotNone(v1)
            self.assertAlmostEqual(v1.scale, 1.2)
            self.assertAlmostEqual(v1.position_x, 0.4)
            self.assertEqual(v1.transition_in, "wipe")
            self.assertAlmostEqual(v1.metadata["speed"], 1.5)
            self.assertAlmostEqual(v1.metadata["source_start"], 0.5)
            self.assertAlmostEqual(v1.metadata["source_end"], 4.0)
            self.assertAlmostEqual(v1.metadata["transition_duration"], 0.3)
            self.assertTrue(v1.metadata["hold_tail"])

            sfx1 = find_event(reopened, "sfx1")
            self.assertEqual(sfx1.metadata["file"], "whoosh/w1.wav")
            self.assertAlmostEqual(sfx1.metadata["volume"], 0.7)

            vo1 = find_event(reopened, "vo1")
            self.assertAlmostEqual(vo1.metadata["fade_in"], 0.2)
            self.assertAlmostEqual(vo1.metadata["fade_out"], 0.5)

    def test_unrelated_editorial_plan_fields_survive_a_timeline_save(self):
        """Saving the operator timeline must never clobber the rest of
        editorial_plan.json (scenes, hook_window_s, etc.) — Section 23's
        "operator edits are user-owned data" cuts both ways: saving them
        must not destroy anything else either."""
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            plan_path = state_dir / "editorial_plan.json"
            plan_path.write_text(
                json.dumps({"scenes": [{"scene_number": "1"}], "hook_window_s": 30, "graphics_plan": {"specs": []}}),
                encoding="utf-8",
            )
            save_timeline(state_dir, EditorialTimeline(audio_end=5.0, events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0, end=5),
            ]))
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(data["hook_window_s"], 30)
            self.assertIn("graphics_plan", data)
            self.assertEqual(data["scenes"], [{"scene_number": "1"}])


class TestBrollReconciliation(unittest.TestCase):
    """VIDEO_2 events that genuinely overlap a primary shot become real
    picture-in-picture overlays (EditDecision.broll); VIDEO_2 events that
    don't overlap anything (the common auto-generated dual-shot case) stay
    ordinary sequential shots, unchanged from prior behavior."""

    def test_overlapping_video_2_becomes_broll_not_a_sequential_shot(self):
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(
                scene_number="1", required_duration=10.0,
                shots=[ShotSpec(shot_id="orig", output_duration=10.0, source_path="a.png")],
            ),
        ]
        tl = EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, scene_number="1", source="a.png"),
                TimelineEvent(
                    event_id="v2", track="VIDEO_2", start=3.0, end=6.0, scene_number="1", source="broll.mp4",
                    metadata={"source_start": 1.0, "speed": 1.0},
                ),
            ],
        )
        out = reconcile_timeline_into_decisions(decisions, tl)
        decision = out[0]
        self.assertEqual(len(decision.shots), 1)  # v2 pulled OUT of the sequential shots
        self.assertEqual(decision.shots[0].shot_id, "v1")
        self.assertEqual(len(decision.broll), 1)
        b = decision.broll[0]
        self.assertEqual(b["source_path"], "broll.mp4")
        self.assertAlmostEqual(b["overlay_start"], 3.0)
        self.assertAlmostEqual(b["overlay_duration"], 3.0)
        self.assertAlmostEqual(b["source_start"], 1.0)

    def test_non_overlapping_video_2_stays_a_sequential_shot(self):
        """The common case: build_timeline_from_decisions alternates
        VIDEO_1/VIDEO_2 labels for a purely sequential multi-shot scene —
        those must render exactly as before (no broll)."""
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(
                scene_number="1", required_duration=10.0,
                shots=[ShotSpec(shot_id="orig", output_duration=10.0, source_path="a.png")],
            ),
        ]
        tl = EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=5.0, scene_number="1", source="a.png"),
                TimelineEvent(event_id="v2", track="VIDEO_2", start=5.0, end=10.0, scene_number="1", source="b.png"),
            ],
        )
        out = reconcile_timeline_into_decisions(decisions, tl)
        decision = out[0]
        self.assertEqual(len(decision.shots), 2)
        self.assertEqual(decision.broll, [])

    def test_broll_overlay_start_is_relative_to_scene_not_absolute_timeline(self):
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(scene_number="2", required_duration=5.0, shots=[ShotSpec(shot_id="orig", output_duration=5.0)]),
        ]
        tl = EditorialTimeline(
            audio_end=15.0,
            events=[
                # Scene 2 starts at absolute t=10.0.
                TimelineEvent(event_id="v1", track="VIDEO_1", start=10.0, end=15.0, scene_number="2", source="a.png"),
                TimelineEvent(event_id="v2", track="VIDEO_2", start=12.0, end=14.0, scene_number="2", source="broll.mp4"),
            ],
        )
        out = reconcile_timeline_into_decisions(decisions, tl)
        b = out[0].broll[0]
        self.assertAlmostEqual(b["overlay_start"], 2.0)  # 12.0 - scene start (10.0), NOT the absolute 12.0


class TestVideo2IndependentOverlay(unittest.TestCase):
    """VIDEO_2 is a genuinely independent B-roll overlay track (see
    editorial_timeline_edit.OVERLAY_VISUAL_TRACKS): move/trim/split/delete/
    duplicate never ripple VIDEO_1/IMAGE, and are never rippled by them."""

    def _tl(self):
        return EditorialTimeline(
            version=1, audio_end=20.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=20.0, scene_number="1", source="a.mp4"),
                TimelineEvent(
                    event_id="b1", track="VIDEO_2", start=5.0, end=10.0, scene_number="1", source="broll.mp4",
                    metadata={"source_start": 0.0, "speed": 1.0},
                ),
            ],
        )

    def test_insert_video_2_overlay_does_not_ripple_video_1(self):
        tl = self._tl()
        new_id = insert_visual_clip(tl, track="VIDEO_2", at_time=2.0, duration=3.0, source="c.mp4")
        self.assertIsNotNone(new_id)
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.start, 0.0)
        self.assertAlmostEqual(v1.end, 20.0)  # unchanged — no ripple
        new_ev = find_event(tl, new_id)
        self.assertAlmostEqual(new_ev.start, 2.0)
        self.assertAlmostEqual(new_ev.end, 5.0)
        self.assertEqual(new_ev.scene_number, "1")  # auto-derived from overlapping primary

    def test_move_video_2_from_5_to_8_does_not_move_video_1(self):
        tl = self._tl()
        ok = move_event(tl, "b1", 8.0, snap=False)
        self.assertTrue(ok)
        b1 = find_event(tl, "b1")
        self.assertAlmostEqual(b1.start, 8.0)
        self.assertAlmostEqual(b1.end, 13.0)  # duration (5s) preserved
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.start, 0.0)
        self.assertAlmostEqual(v1.end, 20.0)

    def test_video_1_ripple_edit_does_not_move_video_2(self):
        tl = self._tl()
        trim_event_end(tl, "v1", 15.0, snap=False)  # shrink V1 — would ripple another primary clip, but there is none
        b1 = find_event(tl, "b1")
        self.assertAlmostEqual(b1.start, 5.0)
        self.assertAlmostEqual(b1.end, 10.0)  # VIDEO_2 never rippled by a primary edit

    def test_trim_video_2_left_edge_changes_start_and_source_start(self):
        tl = self._tl()
        ok = trim_event_start(tl, "b1", 7.0, snap=False)
        self.assertTrue(ok)
        b1 = find_event(tl, "b1")
        self.assertAlmostEqual(b1.start, 7.0)
        self.assertAlmostEqual(b1.end, 10.0)  # end untouched
        self.assertAlmostEqual(b1.metadata["source_start"], 2.0)  # advanced by the 2s trimmed off

    def test_trim_video_2_right_edge_changes_only_duration(self):
        tl = self._tl()
        ok = trim_event_end(tl, "b1", 12.0, snap=False)
        self.assertTrue(ok)
        b1 = find_event(tl, "b1")
        self.assertAlmostEqual(b1.start, 5.0)
        self.assertAlmostEqual(b1.end, 12.0)
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.end, 20.0)  # no ripple

    def test_split_video_2_creates_two_independent_overlay_clips(self):
        tl = self._tl()
        new_id = split_event(tl, "b1", 7.0)
        self.assertIsNotNone(new_id)
        first = find_event(tl, "b1")
        second = find_event(tl, new_id)
        self.assertEqual(first.track, "VIDEO_2")
        self.assertEqual(second.track, "VIDEO_2")
        self.assertAlmostEqual(first.end, 7.0)
        self.assertAlmostEqual(second.start, 7.0)
        self.assertAlmostEqual(second.end, 10.0)
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.end, 20.0)  # unaffected

    def test_delete_video_2_removes_only_that_clip(self):
        tl = self._tl()
        ok = delete_event(tl, "b1")
        self.assertTrue(ok)
        self.assertIsNone(find_event(tl, "b1"))
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.start, 0.0)
        self.assertAlmostEqual(v1.end, 20.0)  # no ripple-close

    def test_duplicate_video_2_creates_independent_second_overlay(self):
        tl = self._tl()
        new_id = duplicate_event(tl, "b1")
        self.assertIsNotNone(new_id)
        dup = find_event(tl, new_id)
        self.assertEqual(dup.track, "VIDEO_2")
        self.assertAlmostEqual(dup.start, 10.0)
        self.assertAlmostEqual(dup.end, 15.0)
        v1 = find_event(tl, "v1")
        self.assertAlmostEqual(v1.end, 20.0)  # unaffected

    def test_video_2_excluded_from_reorder_to_index_and_reorder_content_swap(self):
        tl = self._tl()
        self.assertEqual([e.event_id for e in visual_sequence_order(tl)], ["v1"])
        self.assertFalse(move_visual_event_to_index(tl, "b1", 0))
        self.assertFalse(reorder_visual_event(tl, "b1", direction="earlier"))

    def test_video_2_speed_change_does_not_reach_2x_silently_clamped_elsewhere(self):
        from editorial_timeline_edit import clamp_speed

        tl = self._tl()
        ok = set_event_property(tl, "b1", speed=clamp_speed(1.8))
        self.assertTrue(ok)
        self.assertAlmostEqual(find_event(tl, "b1").metadata["speed"], 1.8)

    def test_scene_number_resyncs_when_overlay_dragged_into_a_different_scene(self):
        tl = EditorialTimeline(
            version=1, audio_end=20.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, scene_number="1", source="a.mp4"),
                TimelineEvent(event_id="v2", track="VIDEO_1", start=10.0, end=20.0, scene_number="2", source="b.mp4"),
                TimelineEvent(
                    event_id="b1", track="VIDEO_2", start=2.0, end=5.0, scene_number="1", source="broll.mp4",
                    metadata={"source_start": 0.0, "speed": 1.0},
                ),
            ],
        )
        move_event(tl, "b1", 12.0, snap=False)
        self.assertEqual(find_event(tl, "b1").scene_number, "2")

    def test_broll_moved_then_exported_reflects_the_new_position(self):
        """The spec's exact end-to-end reconciliation scenario: VIDEO_1
        0-10, VIDEO_2 3-6 -> overlay at 3.0; move VIDEO_2 to 6-9 -> overlay
        must now report 6.0, not the old 3.0 — proving a drag genuinely
        propagates into what the renderer will composite."""
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [
            EditDecision(scene_number="1", required_duration=10.0, shots=[ShotSpec(shot_id="orig", output_duration=10.0)]),
        ]
        tl = EditorialTimeline(
            audio_end=10.0,
            events=[
                TimelineEvent(event_id="v1", track="VIDEO_1", start=0.0, end=10.0, scene_number="1", source="a.mp4"),
                TimelineEvent(
                    event_id="b1", track="VIDEO_2", start=3.0, end=6.0, scene_number="1", source="broll.mp4",
                    metadata={"source_start": 0.0, "speed": 1.0},
                ),
            ],
        )
        out_a = reconcile_timeline_into_decisions(decisions, tl)
        self.assertAlmostEqual(out_a[0].broll[0]["overlay_start"], 3.0)

        move_event(tl, "b1", 6.0, snap=False)
        out_b = reconcile_timeline_into_decisions(decisions, tl)
        self.assertAlmostEqual(out_b[0].broll[0]["overlay_start"], 6.0)
        self.assertNotEqual(out_a[0].broll[0]["overlay_start"], out_b[0].broll[0]["overlay_start"])
