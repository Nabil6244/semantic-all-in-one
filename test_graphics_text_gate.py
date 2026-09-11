"""Graphics/lower-thirds must follow Smart Editing → Text Effects."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app import editorial_timeline_for_render


class EditorialTimelineRenderGateTests(unittest.TestCase):
    def test_text_effects_off_suppresses_timeline_graphics(self):
        plan = SimpleNamespace(timeline={"events": [{"track": "TEXT", "text": "Hello"}]})
        self.assertIsNone(
            editorial_timeline_for_render(plan, text_effects=False),
        )

    def test_text_effects_on_passes_dict_timeline(self):
        timeline = {"events": [{"track": "GRAPHICS", "text": "Stat"}]}
        plan = SimpleNamespace(timeline=timeline)
        self.assertIs(editorial_timeline_for_render(plan, text_effects=True), timeline)

    def test_non_dict_or_missing_timeline_is_none(self):
        self.assertIsNone(editorial_timeline_for_render(None, text_effects=True))
        self.assertIsNone(
            editorial_timeline_for_render(SimpleNamespace(timeline=None), text_effects=True),
        )
        self.assertIsNone(
            editorial_timeline_for_render(SimpleNamespace(timeline="nope"), text_effects=True),
        )


if __name__ == "__main__":
    unittest.main()
