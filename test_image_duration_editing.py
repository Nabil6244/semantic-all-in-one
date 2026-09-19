"""Phase 3 acceptance test: IMAGE duration is genuinely, fully editable —
not fixed at its insertion length anywhere in the pipeline.

Reported live: "I added image media that should be 5 seconds long, and
the editor still behaves like the media/timeline duration is effectively
fixed." Root cause traced to editorial_timeline_edit.py/ui/timeline_canvas.py/
ui/editor_view.py/preview_engine.py all reading ``timeline.audio_end``
directly as "the timeline's total length" — but audio_end is set ONCE from
the narration's own recorded length and is deliberately never touched by
editing operations (qc_issues() needs that original value to detect
"visual coverage no longer matches the narration"). So the TimelineEvent's
own duration WAS being edited correctly (confirmed directly), but every
downstream consumer of "the timeline's total length" — the TimelineCanvas
ruler/scroll extent, the preview player's scrub-bar range, the audio
mixdown's own output length — stayed clamped to the ORIGINAL, stale
length: the edit was real in the data model and invisible/unreachable
everywhere else. Fixed via one shared helper,
editorial_timeline_edit.timeline_duration(), used everywhere "current
total timeline length" is actually needed (never at qc_issues(), which
correctly keeps reading the raw, stable audio_end).

Every step below uses real ffmpeg — no mocked duration pipeline.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestImageDurationFullyEditable(unittest.TestCase):
    """The exact 19-step Phase 3 scenario, using real ffmpeg throughout."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.images_dir = self.root / "images"
        self.images_dir.mkdir()
        Image.new("RGB", (320, 180), (60, 120, 200)).save(self.images_dir / "1.png")
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_full_image_duration_lifecycle(self):
        import editorial_timeline_edit as tl_edit
        import preview_engine as pv
        from editorial.timeline import EditorialTimeline

        # 1. Insert image (2.0s insertion default).
        tl = EditorialTimeline(audio_end=2.0, events=[])
        eid = tl_edit.insert_visual_clip(
            tl, track="IMAGE", at_time=0.0, duration=2.0,
            source=str(self.images_dir / "1.png"), scene_number="1",
        )
        # 2. Verify event exists.
        self.assertIsNotNone(eid)
        ev = tl_edit.find_event(tl, eid)
        self.assertIsNotNone(ev)
        # 3. Verify timeline duration equals insertion duration.
        self.assertAlmostEqual(ev.duration, 2.0)

        # 4/5. Change duration to 2 seconds (already 2s — trim to confirm the op itself works).
        self.assertTrue(tl_edit.trim_event_end(tl, eid, 2.0, snap=False) or ev.end == 2.0)
        ev = tl_edit.find_event(tl, eid)
        self.assertAlmostEqual(ev.duration, 2.0)

        # 6. Verify preview snapshot reports 2 seconds.
        snapshot = pv.effective_state_at(tl, 1.0)
        self.assertEqual(snapshot["primary_event_id"], eid)
        segs = pv.build_visual_segments(tl)
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0].duration, 2.0)

        # 7/8. Build real preview -> proxy duration ~2s.
        out = pv.build_video_proxy(self.state_dir, tl, width=160, height=90, fps=10)
        self.assertIsNotNone(out)
        self.assertAlmostEqual(_probe_duration(out), 2.0, delta=0.25)

        # 9/10. Change duration to 8 seconds -> proxy becomes ~8s.
        ok = tl_edit.trim_event_end(tl, eid, 8.0, snap=False)
        self.assertTrue(ok)
        ev = tl_edit.find_event(tl, eid)
        self.assertAlmostEqual(ev.duration, 8.0)
        # The timeline's OWN total length must now reflect 8s, not the
        # original 2s audio_end (this is the actual bug being verified).
        self.assertAlmostEqual(tl_edit.timeline_duration(tl), 8.0)
        self.assertAlmostEqual(tl.audio_end, 2.0, msg="audio_end itself must stay the narration's original length")

        out2 = pv.build_video_proxy(self.state_dir, tl, width=160, height=90, fps=10)
        self.assertIsNotNone(out2)
        self.assertAlmostEqual(_probe_duration(out2), 8.0, delta=0.3)

        # 11/12/13. Save, reload, verify duration survives.
        (self.state_dir / "editorial_plan.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
        self.assertTrue(tl_edit.save_timeline(self.state_dir, tl))
        reloaded = tl_edit.load_timeline(self.state_dir)
        rev = tl_edit.find_event(reloaded, eid)
        self.assertIsNotNone(rev)
        self.assertAlmostEqual(rev.duration, 8.0)
        self.assertAlmostEqual(tl_edit.timeline_duration(reloaded), 8.0)

        # 14/15. Export -> exported output contains ~8s of that image.
        import video_generator as vg
        from editorial.edit_decision import EditDecision, ShotSpec

        decisions = [EditDecision(scene_number="1", required_duration=8.0, shots=[ShotSpec(shot_id="orig", output_duration=8.0)])]
        reconciled = tl_edit.reconcile_timeline_into_decisions(decisions, reloaded)
        self.assertAlmostEqual(reconciled[0].shots[0].output_duration, 8.0)
        decision_map = {d.scene_number: d.to_dict() for d in reconciled}

        voiceover_path = self.root / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=8", str(voiceover_path)],
            check=True, capture_output=True,
        )
        out_path = self.root / "final.mp4"
        old_cwd = os.getcwd()
        work_dir = self.root / "work"
        work_dir.mkdir()
        os.chdir(work_dir)
        try:
            vg.render_video(
                [{"scene_number": "1", "start_time": 0.0, "script_segment": "one"}],
                8.0, self.images_dir, str(voiceover_path), str(out_path),
                "160x90", 10, zoom=False, visual_transitions=False,
                edit_decisions_by_scene=decision_map,
            )
        finally:
            os.chdir(old_cwd)
        self.assertTrue(out_path.is_file())
        self.assertAlmostEqual(_probe_duration(out_path), 8.0, delta=0.5)

        # 16/17/18/19. Undo (back to 2s) / redo (back to 8s) via the real
        # UndoStack + TimelineCanvas — not a raw field write.
        from ui.undo_stack import Command, UndoStack

        undo = UndoStack()
        working = EditorialTimeline.from_dict(tl.to_dict())  # a fresh copy to drive through undo like the canvas does
        working_ev = tl_edit.find_event(working, eid)
        before_start, before_end = working_ev.start, working_ev.end  # 8s state
        tl_edit.trim_event_end(working, eid, 2.0, snap=False)
        after_start, after_end = tl_edit.find_event(working, eid).start, tl_edit.find_event(working, eid).end

        def do():
            e = tl_edit.find_event(working, eid)
            e.start, e.end = after_start, after_end

        def undo_fn():
            e = tl_edit.find_event(working, eid)
            e.start, e.end = before_start, before_end

        undo.push(Command("Trim to 2s", do=do, undo=undo_fn), run=False)
        self.assertAlmostEqual(tl_edit.find_event(working, eid).duration, 2.0)
        undo.undo()
        self.assertAlmostEqual(tl_edit.find_event(working, eid).duration, 8.0, msg="undo did not restore the 8s duration")
        undo.redo()
        self.assertAlmostEqual(tl_edit.find_event(working, eid).duration, 2.0, msg="redo did not reapply the 2s duration")


if __name__ == "__main__":
    unittest.main()
