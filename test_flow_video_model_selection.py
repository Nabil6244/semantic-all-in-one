#!/usr/bin/env python3
"""The Video Profile's model (Settings → Flow) must reach the Flow GENERATE request for StarMap / What If runs, which
hand one `flow_settings` dict to both the image and the video provider. They used to pass the image settings only, so
the engine used its default video model (Veo 3.1 Fast) even with Omni ("abra") chosen."""

from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from providers.base import SceneRow


class TestFlowVideoModelSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.App = _app.VideoGeneratorApp

    def _fake_app(self, settings):
        fake = types.SimpleNamespace(_settings=settings, _workspace=None)
        fake.flow_image_model_var = types.SimpleNamespace(get=lambda: "BELUGA")
        fake.flow_image_aspect_var = types.SimpleNamespace(get=lambda: "IMAGE_ASPECT_RATIO_LANDSCAPE")
        fake._video_account_ids = lambda: ["acct-1"]
        for name in ("_current_image_flow_settings", "_flow_agent_images_on", "_flow_ui_mode_on",
                     "_flow_generation_mode", "_image_flow_run_settings",
                     "_get_video_profiles", "_default_video_profile", "_video_flow_settings", "_media_flow_run_settings"):
            setattr(fake, name, types.MethodType(getattr(self.App, name), fake))
        return fake

    def _sent_settings(self, flow_settings, media_kind="video"):
        from providers.flow.provider import FlowProvider

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": "/tmp/doesnotmatter"}
        captured = {}
        client.subscribe.side_effect = lambda fn: captured.setdefault("fn", fn) and (lambda: None)
        client.stop.side_effect = lambda: captured.get("fn") and captured["fn"]({"type": "GENERATE_DONE"})
        engine = types.SimpleNamespace(ensure_running=lambda: client)
        fp = FlowProvider(engine, media_kind=media_kind, flow_settings=flow_settings)
        scenes = [SceneRow(scene_number="3", script_segment="x", asset_type=media_kind, prompt="a rocket launch")]
        with tempfile.TemporaryDirectory() as tmp:
            try:
                fp.resolve_batch(scenes, Path(tmp), log=lambda *_: None, should_stop=lambda: True)
            except Exception:
                pass
        return client.generate.call_args.kwargs["settings"]

    def _profile_settings(self, model, agent=False):
        return {
            "flow_agent_images": agent,
            "default_video_profile_id": "default",
            "video_profiles": [{"id": "default", "name": "Default", "account_ids": [], "model": model,
                                "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE", "duration": 6, "resolution": "360p"}],
        }

    def test_chosen_video_model_reaches_the_flow_request(self):
        for agent in (False, True):
            with self.subTest(agent_mode=agent):
                flow_settings = self._fake_app(self._profile_settings("abra", agent))._media_flow_run_settings()
                sent = self._sent_settings(flow_settings)
                self.assertEqual(sent["mediaKind"], "video")
                self.assertEqual(sent["videoModel"], "abra")
                self.assertEqual(sent["videoDuration"], 6)
                self.assertEqual(sent["videoResolution"], "360p")

    def test_image_settings_are_unchanged_for_the_image_provider(self):
        flow_settings = self._fake_app(self._profile_settings("veo_3_1_t2v_lite", agent=True))._media_flow_run_settings()
        sent = self._sent_settings(flow_settings, media_kind="image")
        self.assertEqual(sent["model"], "BELUGA")
        self.assertEqual(sent["aspectRatio"], "IMAGE_ASPECT_RATIO_LANDSCAPE")
        self.assertEqual(sent["generationMode"], "agent")

    def test_starmap_and_whatif_runs_use_the_combined_settings(self):
        root = Path(__file__).resolve().parent
        self.assertIn("flow_settings = self._media_flow_run_settings()", (root / "app.py").read_text(encoding="utf-8"))
        self.assertIn("flow_settings = app._media_flow_run_settings()",
                      (root / "whatif" / "app_section.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
