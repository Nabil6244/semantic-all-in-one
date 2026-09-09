"""Script Analyzer resilience: cache → Gemini → backup fallback."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from visual_director import (
    ANALYZER_VERSION,
    LLMError,
    StaticLLM,
    VisualDirector,
    VisualPlanError,
    analyzer_cache_key,
    deterministic_visual_plan,
    load_cached_plan,
    save_cached_plan,
)
from visual_director.cache import visual_plan_from_dict
from visual_director.schema import VisualPlan, VisualScene, assert_pipeline_compatible


def _valid_plan_payload(script: str, *, n: int = 4) -> dict:
    words = script.split() or ["story", "continues"]
    per = max(1, len(words) // n)
    scenes = []
    for i in range(n):
        start = i * per
        end = (i + 1) * per if i < n - 1 else len(words)
        narr = " ".join(words[start:end]) or f"Beat {i + 1} of the documentary."
        scenes.append(
            {
                "scene_id": i + 1,
                "narration": narr,
                "visual_goal": f"illustrate idea {i + 1}",
                "visual_description": (
                    f"Distinct documentary shot {i + 1}: subject framing "
                    f"variant {i}, daylight, no repeated composition."
                ),
                "asset_type": "stock_video",
                "provider_preference": "stock_video",
                "search_queries": [f"documentary beat {i + 1} exterior"],
                "timestamp_needed": False,
                "duration": 3.5,
                "importance": "medium",
                "fallbacks": ["stock_image"],
                "visual_treatment": "",
                "transition": "cut",
            }
        )
    return {"topic": "Test Doc", "scenes": scenes}


class _CountingLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.response


class _FailingLLM:
    def __init__(self, message: str):
        self.message = message
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        raise LLMError(self.message)


class TestGeminiSuccessAndCache(unittest.TestCase):
    def test_gemini_success(self):
        script = (
            "Factories hum across the harbor. Ships load containers at dawn. "
            "Workers inspect steel beams while cranes lift cargo skyward. "
            "Night falls and the port lights reflect on calm water."
        )
        llm = _CountingLLM(json.dumps(_valid_plan_payload(script)))
        with patch("visual_director.director.plan_segmentation_issue", return_value=None):
            plan = VisualDirector(llm=llm).plan(script, allow_fallback=False)
        self.assertEqual(getattr(plan, "analyzer_source", None), "gemini")
        self.assertEqual(llm.calls, 1)
        self.assertGreaterEqual(len(plan.scenes), 2)

    def test_cache_hit_skips_gemini(self):
        script = (
            "A river cuts through the valley. Villagers fish at sunrise. "
            "Markets open with spice and grain. Evening bells ring over rooftops."
        )
        payload = _valid_plan_payload(script)
        llm = _CountingLLM(json.dumps(payload))
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch("visual_director.director.plan_segmentation_issue", return_value=None):
                first = VisualDirector(llm=llm).plan(script, state_dir=state)
            self.assertEqual(llm.calls, 1)
            self.assertEqual(getattr(first, "analyzer_source", None), "gemini")
            second = VisualDirector(llm=llm).plan(script, state_dir=state)
            self.assertEqual(llm.calls, 1)  # no second Gemini call
            self.assertEqual(getattr(second, "analyzer_source", None), "cache")
            self.assertEqual(len(first.scenes), len(second.scenes))

    def test_cache_miss_calls_gemini(self):
        script = "Alpha sentence one. Beta sentence two. Gamma sentence three. Delta four."
        llm = _CountingLLM(json.dumps(_valid_plan_payload(script)))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("visual_director.director.plan_segmentation_issue", return_value=None):
                VisualDirector(llm=llm).plan(script, state_dir=Path(tmp))
            self.assertEqual(llm.calls, 1)

    def test_repeated_identical_script_does_not_call_gemini_again(self):
        script = (
            "Chapter one opens with fog over the docks. "
            "Chapter two follows the cargo inland by rail. "
            "Chapter three ends at a quiet warehouse at dusk."
        )
        llm = _CountingLLM(json.dumps(_valid_plan_payload(script)))
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch("visual_director.director.plan_segmentation_issue", return_value=None):
                VisualDirector(llm=llm).plan(script, state_dir=state)
                VisualDirector(llm=llm).plan(script, state_dir=state)
                VisualDirector(llm=llm).plan(script, state_dir=state)
            self.assertEqual(llm.calls, 1)

    def test_cache_invalidation_after_script_change(self):
        a = "First script about rivers and bridges across the city skyline at dawn."
        b = "Second script about deserts and caravans crossing dunes under moonlight."
        llm = _CountingLLM(json.dumps(_valid_plan_payload(a)))
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch("visual_director.director.plan_segmentation_issue", return_value=None):
                VisualDirector(llm=llm).plan(a, state_dir=state)
                llm.response = json.dumps(_valid_plan_payload(b))
                VisualDirector(llm=llm).plan(b, state_dir=state)
            self.assertEqual(llm.calls, 2)

    def test_cache_invalidation_after_analyzer_version_change(self):
        script = "Versioning matters for cache keys across analyzer releases and settings."
        key = analyzer_cache_key(script, analyzer_version=ANALYZER_VERSION)
        plan = deterministic_visual_plan(script)
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            save_cached_plan(state, key, plan, analyzer_version=ANALYZER_VERSION, source="gemini")
            hit = load_cached_plan(state, key, analyzer_version=ANALYZER_VERSION)
            self.assertIsNotNone(hit)
            miss = load_cached_plan(state, key, analyzer_version=ANALYZER_VERSION + 1)
            self.assertIsNone(miss)


class TestGeminiFailuresAndFallback(unittest.TestCase):
    def test_high_demand_uses_backup(self):
        script = (
            "Demand spikes across the grid. Engineers race to stabilize turbines. "
            "Cities dim their lights while crews restore power lines overnight."
        )
        llm = _FailingLLM("model is currently experiencing high demand")
        plan = VisualDirector(llm=llm).plan(script)
        self.assertEqual(getattr(plan, "analyzer_source", None), "backup")
        self.assertEqual(llm.calls, 1)
        self.assertGreaterEqual(len(plan.scenes), 2)
        self.assertTrue(any("backup_analyzer" in w for w in plan.warnings))

    def test_quota_failure_uses_backup(self):
        script = "Quota limits halt the studio. Editors wait. Then work resumes at midnight."
        llm = _FailingLLM("Gemini API error: RESOURCE_EXHAUSTED You exceeded your current quota")
        plan = VisualDirector(llm=llm).plan(script)
        self.assertEqual(getattr(plan, "analyzer_source", None), "backup")

    def test_timeout_uses_backup(self):
        script = "Timeouts hit the long documentary. Backup must keep production moving forward."
        llm = _FailingLLM("Gemini request failed: Read timed out")
        plan = VisualDirector(llm=llm).plan(script)
        self.assertEqual(getattr(plan, "analyzer_source", None), "backup")

    def test_malformed_response_uses_backup(self):
        script = (
            "Malformed JSON should not crash the workflow for a finished documentary. "
            "The backup analyzer must still emit a usable VisualPlan contract."
        )
        llm = StaticLLM("{{{not-json")
        plan = VisualDirector(llm=llm).plan(script)
        self.assertEqual(getattr(plan, "analyzer_source", None), "backup")
        self.assertGreaterEqual(len(plan.scenes), 2)

    def test_fallback_success_same_contract(self):
        script = (
            "Important discovery reveals evidence near the harbor factory. "
            "Scientists document the machine as workers gather by the river."
        )
        plan = deterministic_visual_plan(script, reason="quota")
        self.assertGreaterEqual(len(plan.scenes), 2)
        for i, s in enumerate(plan.scenes, start=1):
            self.assertEqual(s.scene_id, i)
            self.assertTrue(s.narration.strip())
            self.assertTrue(s.visual_goal.strip())
            self.assertTrue(s.search_queries)
            self.assertIn(s.importance, ("low", "medium", "high"))
        self.assertEqual(assert_pipeline_compatible(plan), [])
        # Round-trip like Option 3 consumers
        restored = visual_plan_from_dict(plan.to_dict())
        self.assertEqual(len(restored.scenes), len(plan.scenes))
        self.assertEqual(restored.scenes[0].narration, plan.scenes[0].narration)

    def test_both_analyzers_fail(self):
        script = "Both paths fail and the user gets a clear error."
        llm = _FailingLLM("high demand")
        with patch(
            "visual_director.fallback.deterministic_visual_plan",
            side_effect=RuntimeError("backup boom"),
        ):
            with self.assertRaises(VisualPlanError) as ctx:
                VisualDirector(llm=llm).plan(script)
        msg = str(ctx.exception)
        self.assertIn("both failed", msg.lower())
        self.assertNotIn("Traceback", msg)

    def test_backup_not_used_when_gemini_succeeds(self):
        script = (
            "Gemini returns a valid plan. Backup must not run silently. "
            "Coverage stays with the primary analyzer path."
        )
        llm = _CountingLLM(json.dumps(_valid_plan_payload(script)))
        with patch("visual_director.director.plan_segmentation_issue", return_value=None):
            with patch("visual_director.fallback.deterministic_visual_plan") as backup:
                plan = VisualDirector(llm=llm).plan(script)
                backup.assert_not_called()
        self.assertEqual(getattr(plan, "analyzer_source", None), "gemini")

    def test_backup_not_cached_so_gemini_is_retried(self):
        script = (
            "When Gemini is down we use backup, but the next run should retry Gemini "
            "instead of permanently locking the project onto the fallback plan."
        )
        fail = _FailingLLM("high demand")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            first = VisualDirector(llm=fail).plan(script, state_dir=state)
            self.assertEqual(getattr(first, "analyzer_source", None), "backup")
            ok = _CountingLLM(json.dumps(_valid_plan_payload(script)))
            with patch("visual_director.director.plan_segmentation_issue", return_value=None):
                second = VisualDirector(llm=ok).plan(script, state_dir=state)
            self.assertEqual(ok.calls, 1)
            self.assertEqual(getattr(second, "analyzer_source", None), "gemini")


class TestLongFormScale(unittest.TestCase):
    def test_long_script_many_beats(self):
        # ~8–10 minutes of narration material
        sentence = (
            "Steel containers move through the harbor while inspectors check seals "
            "and captains prepare for open water. "
        )
        script = sentence * 120
        plan = deterministic_visual_plan(script)
        self.assertGreater(len(plan.scenes), 20)
        self.assertEqual(assert_pipeline_compatible(plan), [])
        ids = [s.scene_id for s in plan.scenes]
        self.assertEqual(ids, list(range(1, len(ids) + 1)))

    def test_forty_minute_equivalent_workload(self):
        # ~150 wpm × 40 min ≈ 6000 words
        sentence = (
            "Across continents, supply chains connect factories, ports, rail yards, "
            "and neighborhood markets in a single continuous documentary narrative. "
        )
        script = sentence * 320  # ~5760+ words (~40 min at ~145 wpm)
        words = len(script.split())
        self.assertGreaterEqual(words, 5500)
        plan = deterministic_visual_plan(script)
        self.assertGreater(len(plan.scenes), 40)
        self.assertLess(len(plan.scenes), 500)  # sane density, not 1 word/beat
        # Contract checks without quadratic UI assumptions
        rows = plan.to_scene_rows()
        self.assertEqual(len(rows), len(plan.scenes))
        self.assertEqual(assert_pipeline_compatible(plan), [])

    def test_option3_receives_identical_semantic_beat_contract(self):
        script = (
            "Option three consumes VisualPlan scenes as semantic beats. "
            "Gemini and backup must share the same fields for alignment."
        )
        gemini_like = visual_plan_from_dict(_valid_plan_payload(script))
        backup = deterministic_visual_plan(script)
        required = (
            "scene_id",
            "narration",
            "visual_goal",
            "visual_description",
            "asset_type",
            "provider_preference",
            "search_queries",
            "duration",
            "importance",
            "fallbacks",
        )
        for plan in (gemini_like, backup):
            self.assertIsInstance(plan, VisualPlan)
            self.assertGreaterEqual(len(plan.scenes), 2)
            for scene in plan.scenes:
                self.assertIsInstance(scene, VisualScene)
                for field in required:
                    self.assertTrue(hasattr(scene, field), field)
            self.assertEqual(assert_pipeline_compatible(plan), [])

    def test_options_1_2_plan_api_unchanged(self):
        """plan(script) still works; new kwargs are optional."""
        script = (
            "Legacy callers pass only the script string and still receive a VisualPlan. "
            "Optional cache and fallback kwargs must not break that signature."
        )
        llm = _CountingLLM(json.dumps(_valid_plan_payload(script)))
        with patch("visual_director.director.plan_segmentation_issue", return_value=None):
            plan = VisualDirector(llm=llm).plan(script)
        self.assertGreaterEqual(len(plan.scenes), 2)


if __name__ == "__main__":
    unittest.main()
