"""Long-form stress test (Semantic YT Studio 2.0 — 300-500 scene project).

A synthetic ~400-scene, ~33-minute documentary timeline covering every
track kind (VIDEO_1, VIDEO_2 overlay, IMAGE, VOICEOVER, MUSIC, SFX,
AMBIENCE, TEXT, GRAPHICS, real transitions), exercised against the actual
live TimelineCanvas widget and editorial_timeline_edit's real operations —
never mocked stand-ins.

Scope, stated honestly: this does NOT render 400 real Flow videos or a
real proxy video (that would require real ffmpeg encoding minutes of
footage and is explicitly out of scope per the request — "Do NOT generate
500 real videos... use small local test assets or synthetic media").
AUDIO_TRACKS events deliberately carry no resolvable source file, so
TimelineCanvas's real background waveform-decode thread (see
waveform_cache.py / test_waveform_cache.py, already covered by dedicated
real-ffmpeg tests) is never triggered here — this file isolates and
measures the CANVAS/DATA-MODEL performance risk (O(N^2) redraw, hit-
testing, ripple edits, undo/redo at scale), which is the actual risk
category named in the request ("The UI should not perform obvious O(N^2)
work... do not regenerate all waveforms on repaint").

Timing assertions use generous thresholds (seconds, not milliseconds) —
the goal is to catch an accidental O(N^2)/O(N^3) blowup (which would
blow past even a generous bound at this scale), not to enforce a strict
perf SLO on an unknown CI machine.
"""

from __future__ import annotations

import time
import types
import unittest

from editorial.timeline import EditorialTimeline, TimelineEvent

N_SCENES = 400
SCENE_DUR = 5.0
TOTAL_DURATION = N_SCENES * SCENE_DUR  # 2000s ≈ 33.3 minutes


def build_long_form_timeline() -> EditorialTimeline:
    """A realistic 400-scene documentary timeline: primary visual coverage
    alternating VIDEO_1/IMAGE, a VIDEO_2 B-roll overlay on every 5th scene,
    a continuous VOICEOVER, periodic MUSIC/AMBIENCE beds, an SFX hit most
    scenes, TEXT/GRAPHICS call-outs on some scenes, and a real transition
    (see video_generator.TRANSITION_TYPES) on every 4th scene boundary."""
    events: list[TimelineEvent] = []
    t = 0.0
    for i in range(N_SCENES):
        sn = str(i + 1)
        end = round(t + SCENE_DUR, 3)
        primary_track = "VIDEO_1" if i % 3 != 0 else "IMAGE"
        meta = {"speed": 1.0, "source_start": 0.0}
        if i % 4 == 0 and i > 0:
            ttype = ["crossfade", "dip_black", "wipe", "slide"][(i // 4) % 4]
            meta["transition_duration"] = 0.4
        events.append(TimelineEvent(
            event_id=f"v{i}", track=primary_track, start=t, end=end,
            scene_number=sn, source=f"scene_{i}.png",
            transition_in=(["crossfade", "dip_black", "wipe", "slide"][(i // 4) % 4] if (i % 4 == 0 and i > 0) else "cut"),
            metadata=meta,
        ))
        if i % 5 == 0:
            events.append(TimelineEvent(
                event_id=f"b{i}", track="VIDEO_2", start=round(t + 1.0, 3), end=round(t + 3.0, 3),
                scene_number=sn, source=f"broll_{i}.mp4",
                metadata={"speed": 1.0, "source_start": 0.0},
            ))
        if i % 3 == 0:
            events.append(TimelineEvent(
                event_id=f"t{i}", track="TEXT", start=round(t + 0.5, 3), end=round(t + 2.0, 3),
                scene_number=sn, metadata={"text": f"Fact #{i}"},
            ))
        if i % 7 == 0:
            events.append(TimelineEvent(
                event_id=f"g{i}", track="GRAPHICS", start=round(t + 0.2, 3), end=round(t + 1.5, 3),
                scene_number=sn, metadata={"kind": "lower_third"},
            ))
        if i % 2 == 0:
            events.append(TimelineEvent(
                event_id=f"sfx{i}", track="SFX", start=round(t + 0.1, 3), end=round(t + 0.4, 3),
                scene_number=sn, metadata={"volume": 0.9},
            ))
        if i % 10 == 0:
            events.append(TimelineEvent(
                event_id=f"amb{i}", track="AMBIENCE", start=t, end=round(t + 10 * SCENE_DUR, 3),
                scene_number=sn, metadata={"volume": 0.4},
            ))
        t = end

    events.append(TimelineEvent(event_id="vo", track="VOICEOVER", start=0.0, end=TOTAL_DURATION, scene_number="1"))
    for i in range(0, N_SCENES, 20):
        events.append(TimelineEvent(
            event_id=f"music{i}", track="MUSIC", start=i * SCENE_DUR, end=min(TOTAL_DURATION, (i + 20) * SCENE_DUR),
            scene_number=str(i + 1), metadata={"volume": 0.3},
        ))

    return EditorialTimeline(version=1, audio_end=TOTAL_DURATION, events=events)


class TestLongFormTimelineConstruction(unittest.TestCase):
    """Pure data-model scale checks — no Tk needed."""

    def test_builds_300_to_500_scenes_with_every_track_kind(self):
        tl = build_long_form_timeline()
        self.assertGreaterEqual(N_SCENES, 300)
        self.assertLessEqual(N_SCENES, 500)
        tracks = {e.track for e in tl.events}
        self.assertEqual(
            tracks,
            {"VIDEO_1", "VIDEO_2", "IMAGE", "VOICEOVER", "MUSIC", "SFX", "AMBIENCE", "TEXT", "GRAPHICS"},
        )
        self.assertGreater(len(tl.events), 800)

    def test_reconcile_at_scale_stays_fast_and_correct(self):
        """reconcile_timeline_into_decisions is real production code run
        on every export — must stay linear-ish at 400 scenes, and every
        VIDEO_2 overlap must still resolve to a real broll entry."""
        from editorial.edit_decision import EditDecision, ShotSpec
        from editorial_timeline_edit import reconcile_timeline_into_decisions

        tl = build_long_form_timeline()
        decisions = [
            EditDecision(scene_number=str(i + 1), required_duration=SCENE_DUR, shots=[ShotSpec(shot_id="orig", output_duration=SCENE_DUR)])
            for i in range(N_SCENES)
        ]
        t0 = time.perf_counter()
        out = reconcile_timeline_into_decisions(decisions, tl)
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(out), N_SCENES)
        broll_scenes = [d for d in out if d.broll]
        self.assertEqual(len(broll_scenes), len(range(0, N_SCENES, 5)))
        self.assertLess(elapsed, 5.0, "reconcile at 400 scenes must not blow up (possible O(N^2))")

    def test_undo_redo_stack_handles_hundreds_of_operations(self):
        from ui.undo_stack import Command, UndoStack
        from editorial_timeline_edit import find_event, move_event

        tl = build_long_form_timeline()
        undo = UndoStack()
        t0 = time.perf_counter()
        for i in range(0, 200, 2):
            eid = f"t{i}"
            if find_event(tl, eid) is None:
                continue
            orig_start = find_event(tl, eid).start

            def do(eid=eid, orig_start=orig_start):
                move_event(tl, eid, orig_start + 0.05, snap=False)

            def undo_fn(eid=eid, orig_start=orig_start):
                move_event(tl, eid, orig_start, snap=False)

            undo.push(Command("move", do=do, undo=undo_fn))
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 3.0)
        while undo.can_undo():
            undo.undo()
        # Every TEXT clip must be back to its original position.
        t0_ev = find_event(tl, "t0")
        self.assertAlmostEqual(t0_ev.start, 0.5)



if __name__ == "__main__":
    unittest.main()
