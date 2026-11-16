"""One Flow engine per app: styles making Flow pictures inside the app use the app's engine manager (a second manager killed the app's
engine as 'foreign': War Flow pictures never reached the video, 2026-11-16)."""

import unittest
from pathlib import Path

import flow_shared_engine as SE

ROOT = Path(__file__).resolve().parent
STYLE_FILES = ["cinematic_explainer/war/flow_pictures.py", "health_cinema/bodymap_flow.py", "aviation/sticker_flow.py", "reptheory/beat_art.py",
               "reptheory/art.py", "ocean/art_flow.py", "ocean/beat_flow.py"]


class SharedEngine(unittest.TestCase):
    def tearDown(self):
        SE.register_shared(None)

    def test_the_registered_app_manager_is_returned(self):
        app_mgr = object()
        SE.register_shared(lambda: app_mgr)
        self.assertIs(SE.shared_or_new(), app_mgr)

    def test_without_the_app_a_fresh_manager(self):
        SE.register_shared(None)
        self.assertEqual(type(SE.shared_or_new(log=lambda m: None)).__name__, "FlowEngineManager")

    def test_a_broken_getter_falls_back(self):
        SE.register_shared(lambda: (_ for _ in ()).throw(RuntimeError("gone")))
        self.assertEqual(type(SE.shared_or_new(log=lambda m: None)).__name__, "FlowEngineManager")

    def test_no_style_makes_its_own_manager(self):
        for f in STYLE_FILES:
            text = (ROOT / f).read_text(encoding="utf-8")
            self.assertNotIn("FlowEngineManager(", text, f)
            self.assertIn("shared_or_new(", text, f)
        self.assertIn("def _get_flow_engine_manager(self)", (ROOT / "app.py").read_text(encoding="utf-8"))   # what _app_getter finds

    def test_the_running_app_window_is_found(self):
        import tkinter
        app_mgr = object()
        old = getattr(tkinter, "_default_root", None)
        tkinter._default_root = type("App", (), {"_get_flow_engine_manager": lambda self: app_mgr})()
        try:
            self.assertIs(SE.shared_or_new(), app_mgr)
        finally:
            tkinter._default_root = old


if __name__ == "__main__":
    unittest.main()
