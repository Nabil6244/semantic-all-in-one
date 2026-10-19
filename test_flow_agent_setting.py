#!/usr/bin/env python3
"""Settings → Flow switches: Fast Flow images (agent) and Flow UI mode (default on)."""

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
        for name in (
            "_current_image_flow_settings",
            "_flow_agent_images_on",
            "_flow_ui_mode_on",
            "_flow_generation_mode",
            "_image_flow_run_settings",
            "_get_video_profiles",
            "_default_video_profile",
            "_video_flow_settings",
        ):
            if hasattr(App, name):
                setattr(fake, name, types.MethodType(getattr(App, name), fake))
        return fake

    def test_ui_mode_on_by_default(self):
        fake = self._fake({})
        self.assertTrue(fake._flow_ui_mode_on())
        settings, accounts = fake._image_flow_run_settings()
        self.assertEqual(settings["generationMode"], "ui")
        self.assertIsNone(accounts)

    def test_ui_mode_off_uses_rpc(self):
        settings, accounts = self._fake({"flow_ui_mode": False})._image_flow_run_settings()
        self.assertEqual(settings["generationMode"], "rpc")
        self.assertIsNone(accounts)

    def test_agent_wins_over_ui_for_images(self):
        fake = self._fake({"flow_agent_images": True, "flow_ui_mode": True})
        settings, accounts = fake._image_flow_run_settings()
        self.assertEqual(settings["generationMode"], "agent")
        self.assertEqual(accounts, ["acct-1", "acct-2"])

    def test_video_uses_ui_by_default_never_agent(self):
        fake = self._fake({
            "flow_agent_images": True,
            "default_video_profile_id": "default",
            "video_profiles": [{
                "id": "default", "name": "Default", "account_ids": [],
                "model": "abra", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "duration": 8, "resolution": "720p",
            }],
        })
        video = fake._video_flow_settings()
        self.assertEqual(video["generationMode"], "ui")

    def test_switches_are_saved_app_wide(self):
        src = Path(self.app.__file__).read_text(encoding="utf-8")
        self.assertIn('self._settings["flow_agent_images"] = bool(agent_var.get())', src)
        self.assertIn('self._settings["flow_ui_mode"] = bool(ui_mode_var.get())', src)
        self.assertIn("Flow UI mode (images & videos)", src)
        self.assertNotIn("set_quality_settings(flow_agent_images", src)


if __name__ == "__main__":
    unittest.main()
