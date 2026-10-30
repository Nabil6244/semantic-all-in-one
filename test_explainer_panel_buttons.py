"""The Explainer page shows only its own buttons (explainer/ui_options.sync), its one Copy the CSV prompt copies the scene prompt, and
Load beat CSV keeps a scene CSV for Direct with Explainer instead of importing it as a Hybrid plan (explainer/ui_options.take_scene_csv)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from explainer import ui_options as U


class Var:
    def __init__(self, v=None): self.v = v
    def get(self): return self.v
    def set(self, v): self.v = v


class Widget:
    def __init__(self, text=""): self.shown, self.opts = True, {"text": text}
    def grid(self): self.shown = True
    def grid_remove(self): self.shown = False
    def configure(self, **kw): self.opts.update(kw)
    def cget(self, k): return self.opts[k]


class Controls:
    def __init__(self, label): self.label = label
    def grid_slaves(self, row, column): return [self.label] if (row, column) == (3, 0) else []


def fake_app(explainer_on):
    a = type("App", (), {})()
    a._hybrid_explainer_var = Var(explainer_on)
    a._hybrid_status_var, a._hybrid_file_var = Var(""), Var("")
    a._hybrid_plan_btn, a._hybrid_copy_graphics_btn, a._hybrid_explainer_btn = Widget(), Widget(), Widget()
    a._hybrid_copy_csv_btn = Widget("Copy the CSV prompt")
    label = Widget("Load beat CSV: your own plan, written by any AI with the CSV prompt.")
    actions = Widget(); actions.master = Controls(label)
    a._hybrid_explainer_opt_row = Widget(); a._hybrid_explainer_opt_row.master = actions
    a.copied = []
    a._copy_csv_prompt = lambda style, status_var=None, graphics=None: a.copied.append(style)
    return a, label


SCENE_CSV = "row,scene,vo_anchor,id,name,look,place\ncast,,,c1,Ali,a man in his 40s,\nscene,1,In 1850 the city,,,,Lahore\nscene,2,Then the river,,,,Ravi\n"


class ExplainerPanelButtons(unittest.TestCase):
    def test_explainer_on_shows_only_its_own_buttons(self):
        a, label = fake_app(True)
        U.sync(a)
        self.assertFalse(a._hybrid_plan_btn.shown, "Write plan with AI makes a Hybrid plan")
        self.assertFalse(a._hybrid_copy_graphics_btn.shown)
        self.assertTrue(a._hybrid_explainer_btn.shown and a._hybrid_explainer_opt_row.shown)
        a._hybrid_copy_csv_btn.opts["command"]()
        self.assertEqual(a.copied, ["explainer_scenes"])
        self.assertIn("Direct with Explainer", label.cget("text"))

    def test_switching_back_to_hybrid_restores_its_buttons_and_prompt(self):
        a, label = fake_app(True)
        U.sync(a)
        a._hybrid_explainer_var.set(False)
        U.sync(a)
        self.assertTrue(a._hybrid_plan_btn.shown and a._hybrid_copy_graphics_btn.shown)
        self.assertFalse(a._hybrid_explainer_btn.shown or a._hybrid_explainer_opt_row.shown)
        a._hybrid_copy_csv_btn.opts["command"]()
        self.assertEqual(a.copied, ["hybrid"])
        self.assertTrue(label.cget("text").startswith("Load beat CSV: your own plan"))

    def test_a_scene_csv_is_kept_for_direct_with_explainer(self):
        a, _ = fake_app(True)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "scenes.csv"; p.write_text("﻿" + SCENE_CSV, encoding="utf-8")
            self.assertTrue(U.take_scene_csv(a, str(p)))
            self.assertEqual(a._hybrid_file_var.get(), str(p))
            self.assertIn("2 scene(s)", a._hybrid_status_var.get())

    def test_a_scene_csv_with_the_explainer_off_is_not_imported_as_hybrid(self):
        a, _ = fake_app(False)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "scenes.csv"; p.write_text(SCENE_CSV, encoding="utf-8")
            self.assertTrue(U.take_scene_csv(a, str(p)))
            self.assertEqual(a._hybrid_file_var.get(), "")
            self.assertIn("Turn on the Explainer look", a._hybrid_status_var.get())

    def test_any_other_file_goes_to_the_hybrid_import(self):
        a, _ = fake_app(True)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "beats.csv"; p.write_text("beat,start,vo_anchor\n1,0,Hello\n", encoding="utf-8")
            self.assertFalse(U.take_scene_csv(a, str(p)))
            self.assertFalse(U.take_scene_csv(a, str(Path(d) / "missing.csv")))
        self.assertEqual(a._hybrid_file_var.get(), "")


if __name__ == "__main__":
    unittest.main()
