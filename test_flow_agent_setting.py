#!/usr/bin/env python3
"""The app-wide "Fast Flow images (agent mode)" switch (Settings → Flow, saved in settings.json): off by default; on, Flow
image runs in every project ask for agent batches on the default Video Profile's accounts; off, the normal per-image path
on all signed-in accounts (unchanged)."""

from __future__ import annotations

import types
import unittest
from pathlib import Path


class TestFlowAgentSetting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.app = _app

    def _fake(self, settings, video_accounts=("acct-1", "acct-2")):
        App = self.app.VideoGeneratorApp
        fake = types.SimpleNamespace(_settings=settings, _workspace=None)
        fake.flow_image_model_var = types.SimpleNamespace(get=lambda: "BELUGA")
        fake.flow_image_aspect_var = types.SimpleNamespace(get=lambda: "IMAGE_ASPECT_RATIO_LANDSCAPE")
        fake._video_account_ids = lambda: list(video_accounts)
        for name in ("_current_image_flow_settings", "_flow_agent_images_on", "_image_flow_run_settings"):
            setattr(fake, name, types.MethodType(getattr(App, name), fake))
        return fake

    def test_off_by_default_means_normal_path(self):
        settings, accounts = self._fake({})._image_flow_run_settings()
        self.assertEqual(settings, {"model": "BELUGA", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"})
        self.assertIsNone(accounts)

    def test_on_uses_agent_with_video_accounts_with_or_without_a_project(self):
        fake = self._fake({"flow_agent_images": True})
        settings, accounts = fake._image_flow_run_settings()
        self.assertEqual(settings["generationMode"], "agent")
        self.assertEqual(settings["model"], "BELUGA")
        self.assertEqual(accounts, ["acct-1", "acct-2"])

    def test_switch_is_saved_app_wide(self):
        src = Path(self.app.__file__).read_text(encoding="utf-8")
        self.assertIn('self._settings["flow_agent_images"] = bool(agent_var.get())', src)
        self.assertNotIn("set_quality_settings(flow_agent_images", src)


if __name__ == "__main__":
    unittest.main()
