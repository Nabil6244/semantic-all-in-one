"""One source vocabulary across the Visual Plan badge, header counts and the
Change Source dialog — and the dialog shows what the scene uses NOW and with
which text (a stock search query vs a Flow prompt).

Before: stock image and stock video shared one "Stock" badge (the user could
not tell which Generate would fetch), Flow read "AI Image/AI Video" on the
badge but "Flow Image/Flow Video" in Change Source, the dialog labelled
YouTube "Youtube", and it never said what the current source/prompt was.
"""

from __future__ import annotations

import unittest

from providers.base import SceneRow


class TestSourceTerminology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc))
        cls.app = _app

    def _badge(self, **row):
        return self.app.scene_source_badge(SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", **row}))[0]

    def test_badges_distinguish_every_generate_source(self):
        self.assertEqual(self._badge(asset_type="flow_image", prompt="p"), "Flow Image")
        self.assertEqual(self._badge(asset_type="flow_video", prompt="p"), "Flow Video")
        self.assertEqual(self._badge(asset_type="stock_image", prompt="q"), "Stock Image")
        self.assertEqual(self._badge(asset_type="stock_video", prompt="q"), "Stock Video")
        self.assertEqual(self._badge(asset_type="youtube_video", prompt="q"), "YouTube")

    def test_header_counts_use_the_same_words_as_the_badge(self):
        AS = self.app.AssetSource
        for source in (AS.FLOW_IMAGE, AS.FLOW_VIDEO, AS.STOCK_IMAGE, AS.STOCK_VIDEO, AS.YOUTUBE_VIDEO):
            self.assertEqual(self.app.VideoGeneratorApp._source_mix_bucket(source), self.app.SOURCE_BADGE[source][0])

    def test_dialog_options_use_badge_words_and_mark_the_current_one(self):
        self.assertEqual(self.app.source_option_label("youtube"), "YouTube")
        self.assertEqual(self.app.source_option_label("flow_image", "Flow Image"), "Flow Image  (current)")
        self.assertEqual(self.app.source_option_label("stock_video", "Flow Image"), "Stock Video")

    def test_dialog_labels_text_by_kind(self):
        stock = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "asset_type": "stock_image",
                                       "prompt": "hoover dam construction"})
        flow = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "asset_type": "flow_image",
                                      "prompt": "aerial view of a dam at dusk"})
        self.assertEqual(self.app.scene_visual_text_summary(stock), "Search: hoover dam construction")
        self.assertEqual(self.app.scene_visual_text_summary(flow), "Prompt: aerial view of a dam at dusk")


if __name__ == "__main__":
    unittest.main()


class TestFailureSummaries(unittest.TestCase):
    """Failure dialogs used to show "\\n".join(errors) — after a render
    failure that is up to ~2,000 characters of raw ffmpeg stderr."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc))
        cls.summary = staticmethod(_app.overscaled_failure_summary)

    def test_encoder_failure_is_actionable_and_hides_stderr(self):
        raw = "Overscaled pipeline failed: Overscaled render failed (segment 3/12) (rc=1): " + "x" * 2000
        text = self.summary([raw])
        self.assertIn("Generate again", text)
        self.assertLess(len(text), 220)
        self.assertNotIn("xxxx", text)

    def test_each_known_failure_has_a_specific_next_step(self):
        cases = {
            "media resolution failed: timeout": "Retry",
            "voiceover file not found: /x.wav": "voiceover",
            "each row needs its own scene_number; repeated: 2": "scene number",
            "final video failed validation: no audio stream": "incomplete",
        }
        for error, expected in cases.items():
            self.assertIn(expected, self.summary([error]), error)

    def test_unknown_error_keeps_its_first_line_short(self):
        self.assertEqual(self.summary(["Something odd happened\nTraceback ..."]), "Something odd happened")
