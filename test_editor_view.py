"""Regression tests for the render-pipeline wiring behind the CapCut-style
Editor (app.py's firstcut/reconciliation integration).

Structural (inspect.getsource), matching the existing convention in
test_phase2_ui.py's TestAppPhase2Wiring: verifies the wiring exists without
booting a second live Tk root (this file intentionally does NOT construct
VideoGeneratorApp() — a second live app instance in the same pytest process
corrupts the first one's named Tk images, e.g. "image \"pyimage2\" doesn't
exist" errors that made TestLiveWidgetSmoke's own tests start skipping).
Live widget coverage for ui/editor_view.py itself lives in
test_phase2_ui.py's TestLiveWidgetSmoke class instead, sharing its one Tk
root. The render-pipeline reconciliation LOGIC (not just that it's wired
in) is covered behaviorally by test_editorial_timeline_edit.py's
TestReconcile — _run_pipeline itself needs a full asset/whisper/ffmpeg run
to exercise live, which is impractical/unsafe to do in a unit test.
"""

from __future__ import annotations

import inspect
import unittest


def _load_app_module():
    import app as _app

    return _app


class TestFirstCutWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def test_run_pipeline_reconciles_operator_timeline_before_render(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._run_pipeline)
        self.assertIn("reconcile_timeline_into_decisions", src)
        self.assertIn('mode != "firstcut"', src)

    def test_run_pipeline_has_firstcut_early_return(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._run_pipeline)
        self.assertIn('mode == "firstcut"', src)
        self.assertIn("save_first_cut_timeline", src)
        self.assertIn('"firstcut_complete"', src)

    def test_firstcut_complete_navigates_to_editor(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._on_firstcut_complete)
        self.assertIn('self._shell.navigate("editor")', src)

    def test_assets_complete_auto_builds_first_cut_when_audio_ready(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._on_assets_complete)
        self.assertIn("build_first_cut_async", src)


if __name__ == "__main__":
    unittest.main()
