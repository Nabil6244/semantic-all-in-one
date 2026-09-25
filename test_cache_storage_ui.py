"""Cache & Storage Settings UI + project-switch isolation wiring.

Structural (inspect.getsource) coverage, matching the existing convention
in test_phase2_ui.py / test_overscaled_ui_integration.py: verifies the
wiring exists without booting the full Tk GUI. Data-level clearing
behavior (freed bytes, protected files) is covered by test_cache_manager.py.
"""

from __future__ import annotations

import inspect
import unittest


def _load_app_module():
    import app as _app

    return _app


class TestCacheStorageSettingsWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def test_open_settings_has_a_cache_storage_section(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._open_settings)
        self.assertIn("CACHE & STORAGE", src)
        self.assertIn("Clear Temporary Cache", src)
        self.assertIn("Clear Preview/Proxy Cache", src)
        self.assertIn("Clear Generated Asset Cache", src)
        self.assertIn("Clear All Cache", src)
        self.assertIn("Current Project Cache", src)

    def test_settings_reuses_cache_manager_not_a_new_cache_system(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._open_settings)
        self.assertIn("import cache_manager", src)
        # "Clear Generated Asset Cache" must reuse the EXISTING downloaded-
        # assets cleanup entry point (confirmation dialog, manifest/QA/
        # asset-manager bookkeeping already handled there) — not a second,
        # parallel implementation.
        self.assertIn("self._on_cleanup_downloaded_assets()", src)

    def test_clear_all_cache_requires_confirmation(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._open_settings)
        idx = src.index("Clear All Cache")
        # The confirm dialog is wired right next to the "Clear All Cache"
        # handler — a coarse but effective structural guard against ever
        # wiring the destructive multi-project clear without one.
        window = src[max(0, idx - 1200):idx]
        self.assertIn("askyesno", window)


class TestProjectSwitchResetsSessionState(unittest.TestCase):
    """2. Switching A -> B must not expose A's cached/session state —
    verifies the EXISTING _activate_workspace reset branch (unchanged by
    this feature) actually covers the state a stale cache reference could
    hide in: the asset manager, in-memory asset results, and the visual
    plan/scene rows."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.app = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def test_activate_workspace_resets_asset_manager_and_results_on_switch(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._activate_workspace)
        self.assertIn("clear_session", src)
        self.assertIn("self._asset_manager = None", src)
        self.assertIn("self._asset_results.clear()", src)
        self.assertIn("self._visual_plan = None", src)

    def test_activate_workspace_rebinds_paths_to_the_new_workspace(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._activate_workspace)
        self.assertIn("self._bind_workspace_paths()", src)


if __name__ == "__main__":
    unittest.main()
