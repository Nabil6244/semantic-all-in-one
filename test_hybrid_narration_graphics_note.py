"""Hybrid Map says in the log whether 'Add graphics from the narration' was on for the render and how many it added (project 21 rendered with it off and
nothing said so), and the switch is remembered per project (project.json hybrid_settings.auto_graphics)."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from hybrid_gfx_note import narration_graphics_line, restored_switch


def _report(*notes):
    return SimpleNamespace(events=[SimpleNamespace(note=n) for n in notes])


class TestNote(unittest.TestCase):
    def test_off_says_so_and_names_the_switch(self):
        line = narration_graphics_line(False, _report("", ""))
        self.assertIn("OFF", line)
        self.assertIn("Add graphics from the narration", line)

    def test_on_counts_what_it_added(self):
        line = narration_graphics_line(True, _report("added from the narration", "", "added from the narration"))
        self.assertIn("ON", line)
        self.assertIn("2 added", line)

    def test_on_with_nothing_found_says_none_were_found(self):
        self.assertIn("none", narration_graphics_line(True, _report("")).lower())

    def test_no_report_is_still_a_line_never_a_crash(self):
        self.assertIn("ON", narration_graphics_line(True, None))


class TestRemembered(unittest.TestCase):
    def test_a_saved_choice_wins_over_the_app_default(self):
        self.assertIs(restored_switch({"auto_graphics": True}, False), True)
        self.assertIs(restored_switch({"auto_graphics": False}, True), False)

    def test_a_project_that_never_chose_starts_from_the_app_setting(self):
        self.assertIs(restored_switch({}, True), True)
        self.assertIs(restored_switch({"sound_design": True}, False), False)


class TestAppWiring(unittest.TestCase):
    src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")

    def test_the_log_line_follows_the_final_video_line(self):
        a = self.src.index('[HYBRID] Final video: {result.output_path}')
        b = self.src.index("narration_graphics_line(hybrid_auto_gfx, result.report)")
        self.assertTrue(0 < b - a < 400)

    def test_the_switch_is_saved_and_restored_per_project(self):
        self.assertIn("auto_graphics=bool(self._hybrid_auto_gfx_var.get())", self.src)
        self.assertIn("restored_switch(saved, bool(self._settings.get(\"hybrid_auto_templates\", False)))", self.src)


if __name__ == "__main__":
    unittest.main()
