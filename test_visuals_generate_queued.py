#!/usr/bin/env python3
"""Visuals tab: a QUEUED row (never tried) can be made from the scene inspector. The retry button reads Generate and is enabled for it,
alone or in a selection, and a selection's queued and failed rows go through the recovery queue; ready rows are never touched."""

from __future__ import annotations

import types
import unittest


class TestGenerateQueued(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.app = _app
        from ui import visuals_generate as V
        cls.V = V

    def fake(self, statuses):
        f = types.SimpleNamespace(calls=[], logs=[], _busy_scenes=set(), _retry_pumping=False, _recovery_queue=[], _recovery_total=0, _recovery_done=0)
        f._qa_snapshot = lambda: types.SimpleNamespace(statuses={self.app._scene_key(k): v for k, v in statuses.items()})
        f._row_status_from_result = lambda s: "ready"
        f._generation_blocks_scene_actions = lambda: False
        f._scene_action = lambda action, scene: f.calls.append((action, scene.scene_number))
        f._append_log = f.logs.append
        f._set_qa_bulk_progress = lambda t="": None
        f._pump_retry_queue = lambda: f.calls.append(("pump", [s.scene_number for _a, s in f._recovery_queue]))
        return f

    def rows(self, *nums):
        return [types.SimpleNamespace(scene_number=n) for n in nums]

    def test_one_queued_row_is_generated(self):
        f = self.fake({"14": "waiting"})
        self.assertTrue(self.V.generate_waiting_scenes(f, self.rows("14")))
        self.assertEqual(f.calls, [("retry", "14")])

    def test_a_selection_makes_queued_and_failed_rows_but_not_ready_ones(self):
        f = self.fake({"14": "waiting", "30": "waiting", "8": "needs_action", "5": "ready"})
        self.assertTrue(self.V.generate_waiting_scenes(f, self.rows("14", "30", "8", "5")))
        self.assertEqual(f.calls, [("pump", ["14", "30", "8"])]); self.assertEqual(f._recovery_total, 3)

    def test_no_queued_row_leaves_the_failed_scene_retry_as_it_was(self):
        f = self.fake({"8": "needs_action", "5": "ready"})
        self.assertFalse(self.V.generate_waiting_scenes(f, self.rows("8", "5"))); self.assertEqual(f.calls, [])

    def test_the_button_reads_generate_for_queued_rows(self):
        f = self.fake({}); texts = []
        f.details_retry_btn = types.SimpleNamespace(configure=lambda **k: texts.append(k["text"]))
        self.V.label_generate_button(f, True); self.V.label_generate_button(f, False)
        self.assertEqual(texts, ["Generate", "Regenerate"])

    def test_the_inspector_enables_it_for_queued_rows(self):
        import inspect
        src = inspect.getsource(self.app.VideoGeneratorApp._update_details_panel)
        self.assertIn('if status == "waiting" and not busy:', src); self.assertIn("if waiting_n and not any_busy:", src)
        self.assertIn('if action == "retry" and generate_waiting_scenes(self, scenes):', inspect.getsource(self.app.VideoGeneratorApp._details_action))


if __name__ == "__main__":
    unittest.main()
