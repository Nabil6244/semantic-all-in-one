#!/usr/bin/env python3
"""The app's Flow image model choices match the ids Flow uses today (captured live 2026-10-06).

Nano Banana 2 = BELUGA, Nano Banana 2 Lite = HARBOR_SEAL, Nano Banana Pro = GEM_PIX_2. NARWHAL (the old Nano Banana 2) is
retired — Google answers it with a bare gRPC 5 / NOT_FOUND — so a saved NARWHAL setting must load as BELUGA.
"""

from __future__ import annotations

import inspect
import unittest


class TestFlowImageModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.app = _app

    def test_current_ids_and_labels(self):
        self.assertEqual(dict(self.app.FLOW_IMAGE_MODELS),
                         {"HARBOR_SEAL": "NB 2 Lite", "BELUGA": "NB 2", "GEM_PIX_2": "NB Pro"})

    def test_nano_banana_2_is_the_default_choice(self):
        self.assertEqual(self.app.FLOW_IMAGE_MODELS[1][0], "BELUGA")

    def test_retired_id_is_not_offered_and_maps_to_its_replacement(self):
        self.assertNotIn("NARWHAL", dict(self.app.FLOW_IMAGE_MODELS))
        self.assertEqual(self.app.RETIRED_FLOW_IMAGE_MODELS, {"NARWHAL": "BELUGA"})

    def test_saved_settings_are_converted_when_loaded(self):
        src = inspect.getsource(self.app.VideoGeneratorApp._init_ui_vars)
        self.assertIn("RETIRED_FLOW_IMAGE_MODELS.get(_saved_model, _saved_model)", src)


if __name__ == "__main__":
    unittest.main()
