#!/usr/bin/env python3
"""The per-project "Fast Flow images (agent mode)" switch: off by default; on, Flow image runs ask for agent batches on
the default Video Profile's accounts; off, the normal per-image path on all signed-in accounts (unchanged)."""

from __future__ import annotations

import tempfile
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

    def _fake(self, workspace, video_accounts=("acct-1", "acct-2")):
        App = self.app.VideoGeneratorApp
        fake = types.SimpleNamespace(_workspace=workspace)
        fake.flow_image_model_var = types.SimpleNamespace(get=lambda: "BELUGA")
        fake.flow_image_aspect_var = types.SimpleNamespace(get=lambda: "IMAGE_ASPECT_RATIO_LANDSCAPE")
        fake._video_account_ids = lambda: list(video_accounts)
        for name in ("_current_image_flow_settings", "_flow_agent_images_on", "_image_flow_run_settings"):
            setattr(fake, name, types.MethodType(getattr(App, name), fake))
        return fake

        tmp = tempfile.mkdtemp()
        return ProjectWorkspace.create(Path(tmp), "Agent test") if hasattr(ProjectWorkspace, "create") else None

    def test_no_project_means_normal_path(self):
        settings, accounts = self._fake(None)._image_flow_run_settings()
        self.assertEqual(settings, {"model": "BELUGA", "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"})
        self.assertIsNone(accounts)

    def test_switch_off_by_default_and_on_uses_agent_with_video_accounts(self):
        quality = {}
        ws = types.SimpleNamespace(quality_settings=lambda: dict(quality))
        fake = self._fake(ws)
        settings, accounts = fake._image_flow_run_settings()
        self.assertNotIn("generationMode", settings)
        self.assertIsNone(accounts)
        quality["flow_agent_images"] = True
        settings, accounts = fake._image_flow_run_settings()
        self.assertEqual(settings["generationMode"], "agent")
        self.assertEqual(settings["model"], "BELUGA")
        self.assertEqual(accounts, ["acct-1", "acct-2"])

    def test_switch_is_saved_with_the_project(self):
        from project_workspace import ProjectWorkspace

        src = Path(self.app.__file__).read_text(encoding="utf-8")
        self.assertIn("set_quality_settings(flow_agent_images=agent_var.get())", src)
        self.assertTrue(hasattr(ProjectWorkspace, "set_quality_settings"))


if __name__ == "__main__":
    unittest.main()
