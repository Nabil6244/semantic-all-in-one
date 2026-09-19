"""Unit tests for firstcut.save_first_cut_timeline — pure data-transform
logic, no Tk/app.py/ffmpeg involved."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import editorial_timeline_edit as tl_edit
from firstcut import save_first_cut_timeline


def _plan_with_timeline():
    return SimpleNamespace(
        timeline={
            "version": 1,
            "audio_end": 10.0,
            "events": [
                {"event_id": "v1", "track": "VIDEO_1", "start": 0.0, "end": 10.0, "source": "a.png"},
            ],
        }
    )


class TestSaveFirstCutTimeline(unittest.TestCase):
    def test_no_timeline_on_plan_returns_false(self):
        with tempfile.TemporaryDirectory() as td:
            plan = SimpleNamespace(timeline=None)
            self.assertFalse(save_first_cut_timeline(Path(td), plan))

    def test_empty_timeline_returns_false(self):
        with tempfile.TemporaryDirectory() as td:
            plan = SimpleNamespace(timeline={"version": 1, "audio_end": 0.0, "events": []})
            self.assertFalse(save_first_cut_timeline(Path(td), plan))

    def test_saves_timeline_and_editor_can_load_it(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "editorial_plan.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            ok = save_first_cut_timeline(state_dir, _plan_with_timeline())
            self.assertTrue(ok)
            loaded = tl_edit.load_timeline(state_dir)
            self.assertEqual(len(loaded.events), 1)
            self.assertEqual(loaded.events[0].event_id, "v1")

    def test_bg_path_adds_music_event_spanning_full_duration(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "editorial_plan.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            bg = state_dir / "music.mp3"
            bg.write_bytes(b"fake")
            ok = save_first_cut_timeline(state_dir, _plan_with_timeline(), bg_path=bg)
            self.assertTrue(ok)
            loaded = tl_edit.load_timeline(state_dir)
            music = [e for e in loaded.events if e.track == "MUSIC"]
            self.assertEqual(len(music), 1)
            self.assertAlmostEqual(music[0].start, 0.0)
            self.assertAlmostEqual(music[0].end, 10.0)
            self.assertEqual(music[0].source, str(bg))

    def test_missing_bg_path_adds_no_music_event(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            (state_dir / "editorial_plan.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            ok = save_first_cut_timeline(state_dir, _plan_with_timeline(), bg_path=state_dir / "nope.mp3")
            self.assertTrue(ok)
            loaded = tl_edit.load_timeline(state_dir)
            self.assertEqual([e for e in loaded.events if e.track == "MUSIC"], [])


if __name__ == "__main__":
    unittest.main()
