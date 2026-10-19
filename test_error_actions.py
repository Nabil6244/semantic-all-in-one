"""The "Generation failed" dialog offers a fix prompt (not Retry) for CSV/plan errors. Lines are copied from real project logs."""
import os
import unittest

from ui.error_actions import fix_prompt, is_plan_error, plan_problems

REAL_PLAN_ERRORS = [
    "row 31: vo_anchor 'North Carolina classifies Lake' is only spoken before the previous row's words (145.3s): rows must follow the script in order",
    "beats.csv beat b32: clip 'stock_video:heavy rain falling on a quiet residential street' does not match what the narration describes",
    "beat b24: a footage beat cannot hold map camera moves, layers or a supporting card (they belong to a map beat)",
    "beat b1 · camera start: can't find 'Southern California'. Use a country, state, county or named region",
    "footage b2_1: 0.1 s is too short (minimum 2 s)",
    "layer b27_marker1: appears at 246.56s, outside its map beat b27 (248.7-258.64s); layers cannot appear under footage",
]
REAL_OTHER_ERRORS = [
    "StarMap render failed: page.evaluate: Target page, context or browser has been closed",
    "What If render failed: page.evaluate: Error: video shot s52: frame missing at 348.57 s",
    "HTTPSConnectionPool(host='api.openverse.org', port=443): Read timed out. (read timeout=20)",
    "Timed out waiting for the Flow engine to finish generating.",
    "No space left on device",
]


class PlanErrorDetection(unittest.TestCase):
    def test_real_plan_errors_are_plan_errors(self):
        for line in REAL_PLAN_ERRORS:
            self.assertTrue(is_plan_error([line]), line)
        self.assertTrue(is_plan_error(["\n".join(REAL_PLAN_ERRORS)]))

    def test_engine_network_disk_errors_keep_retry(self):
        for line in REAL_OTHER_ERRORS:
            self.assertFalse(is_plan_error([line]), line)

    def test_mixed_failure_keeps_retry(self):
        self.assertFalse(is_plan_error(["\n".join(REAL_PLAN_ERRORS[:2] + REAL_OTHER_ERRORS[:1])]))

    def test_empty_is_not_a_plan_error(self):
        self.assertFalse(is_plan_error([]))
        self.assertFalse(is_plan_error(["", "  "]))


class FixPrompt(unittest.TestCase):
    def test_prompt_lists_every_problem_and_the_rules(self):
        p = fix_prompt("Weather", ["\n".join(REAL_PLAN_ERRORS)])
        self.assertIn("Weather CSV", p)
        for line in REAL_PLAN_ERRORS:
            self.assertIn(line, p)
        self.assertIn("vo_anchor must be words the narrator really says", p)

    def test_long_lists_are_capped(self):
        many = [f"row {i}: vo_anchor 'x' is not in the narration" for i in range(100)]
        p = fix_prompt("What If", many, limit=10)
        self.assertEqual(sum(1 for l in p.splitlines() if l.startswith("- row")), 10)
        self.assertIn("90 more", p)
        self.assertEqual(len(plan_problems(many)), 100)


class NeedsAttention(unittest.TestCase):
    def test_real_stop_texts(self):
        from ui.error_actions import needs_attention

        self.assertTrue(needs_attention(["2 picture(s)/clip(s) need attention: scene 13, 44"]))   # What If #022/#023
        self.assertTrue(needs_attention(["1 picture(s)/clip(s) still need attention (scene 85)"]))
        self.assertFalse(needs_attention(REAL_OTHER_ERRORS + REAL_PLAN_ERRORS))
        self.assertFalse(needs_attention([]))


class DialogWiring(unittest.TestCase):
    def test_error_dialog_uses_the_decision(self):
        with open(os.path.join(os.path.dirname(__file__), "app.py"), encoding="utf-8") as fh:
            src = fh.read()
        body = src[src.index("def _show_error_dialog"):src.index("def _show_preview")]
        self.assertIn("is_plan_error", body)
        self.assertIn("Copy fix prompt", body)
        self.assertIn('text="Retry"', body)   # other failures keep Retry


if __name__ == "__main__":
    unittest.main()
