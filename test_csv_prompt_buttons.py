#!/usr/bin/env python3
"""Every style panel's "Copy the CSV prompt": the style's own prompt with the project's script in it, and the panels' script
boxes are the Script page's script (typing in one updates it; a box that is only out of date never overwrites it)."""

from __future__ import annotations

import types
import unittest


class _Box:
    """A stand-in for a CTkTextbox."""

    def __init__(self, text=""):
        self.text = text

    def get(self, *_a):
        return self.text + "\n"

    def delete(self, *_a):
        self.text = ""

    def insert(self, _i, t):
        self.text = t


class TestCopyCsvPrompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.app = _app

    def _fake(self, script="", preset="overscaled"):
        App = self.app.VideoGeneratorApp
        fake = types.SimpleNamespace(_workspace=None, script_box=_Box(script), _overscaled_style_preset_id=preset, copied=[])
        fake.clipboard_clear = lambda: fake.copied.clear()
        fake.clipboard_append = lambda t: fake.copied.append(t)
        fake.focus_get = lambda: None
        fake._sync_script_watermark = lambda: None
        fake.status_var = types.SimpleNamespace(set=lambda v: setattr(fake, "status", v))
        for name in ("_copy_csv_prompt", "_main_script_text", "_refresh_csv_prompt_script_boxes", "_on_csv_prompt_script_edited"):
            setattr(fake, name, types.MethodType(getattr(App, name), fake))
        fake._csv_prompt_script_boxes = []
        return fake

    def test_each_style_copies_its_own_prompt_with_the_script(self):
        from app_csv_prompts import SCRIPT_PLACEHOLDER, build_prompt

        for style, marker in (("normal", "scene_number,script_segment,asset_type,prompt"), ("pakmap", "item_no,vo_anchor"),
                              ("hybrid", "beat,row,vo_anchor"), ("overscaled", "node_type,role,asset_type")):
            fake = self._fake("Hudson Bay is huge.")
            fake._copy_csv_prompt(style)
            self.assertIn(marker, fake.copied[0], style)
            self.assertTrue(fake.copied[0].rstrip().endswith("Hudson Bay is huge."), style)
            self.assertNotIn(SCRIPT_PLACEHOLDER, fake.copied[0])
            self.assertIn("with your script", fake.status)
        self.assertIn(SCRIPT_PLACEHOLDER, build_prompt("normal", ""))

    def test_overscaled_panel_copies_exp_solar_when_that_look_is_chosen(self):
        fake = self._fake("x y z", preset="exp_solar")
        fake._copy_csv_prompt("overscaled")
        self.assertIn("relationship_to", fake.copied[0])
        self.assertIn("Exp Solar", fake.status)

    def test_without_a_script_the_placeholder_stays(self):
        fake = self._fake("")
        fake._copy_csv_prompt("normal")
        self.assertTrue(fake.copied[0].rstrip().endswith("<<<PASTE THE SCRIPT HERE>>>"))
        self.assertIn("replace its last line", fake.status)

    def test_typing_in_a_panel_updates_the_script_page_and_other_panels(self):
        fake = self._fake("old script")
        a, b = _Box("old script"), _Box("old script")
        a._csv_synced = b._csv_synced = "old script"
        fake._csv_prompt_script_boxes = [a, b]
        a.text = "new script"
        fake._copy_csv_prompt("normal")   # clicked Copy without leaving the box first
        self.assertEqual(fake.script_box.text, "new script")
        self.assertEqual(b.text, "new script")
        self.assertTrue(fake.copied[0].rstrip().endswith("new script"))

    def test_an_out_of_date_panel_never_overwrites_a_newer_script(self):
        fake = self._fake("old script")
        a = _Box("old script")
        a._csv_synced = "old script"
        fake._csv_prompt_script_boxes = [a]
        fake.script_box.text = "script written by the AI writer"   # changed elsewhere, the panel was not refreshed
        fake._copy_csv_prompt("normal")
        self.assertEqual(fake.script_box.text, "script written by the AI writer")
        self.assertTrue(fake.copied[0].rstrip().endswith("script written by the AI writer"))


if __name__ == "__main__":
    unittest.main()
