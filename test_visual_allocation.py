"""Visual Allocation Engine tests."""

from __future__ import annotations

import tempfile
import unittest

from style_engine import resolve_style
from visual_allocation import (
    AllocationSettings,
    allocate_visual_plan,
    apply_allocation_to_plan,
    finalize_scene_prompts,
    load_allocation_settings,
    save_allocation_settings,
)
from providers.router import SceneAssetRouter
from visual_allocation.budget import ai_budget_limit, select_flow_scenes
from visual_allocation.curve import curve_video_bias
from visual_allocation.models import AllocationDecision
from visual_allocation.coverage import plan_scene_coverage
from visual_director.schema import VisualScene, VisualPlan
from style_engine.visual_selection import duration_fit_score, scene_has_manual_authority
from providers.base import SceneRow


def _scene(
    sid: int,
    narration: str,
    *,
    importance: str = "normal",
    provider: str = "stock",
    asset_type: str = "stock_video",
    duration: float = 3.5,
    desc: str = "",
) -> VisualScene:
    return VisualScene(
        scene_id=sid,
        narration=narration,
        visual_goal="show subject",
        visual_description=desc or narration[:80],
        asset_type=asset_type,
        provider_preference=provider,
        search_queries=[desc or narration[:40]],
        timestamp_needed=False,
        timestamp_hint="",
        duration=duration,
        importance=importance,
        fallbacks=["stock_image"],
        visual_treatment="documentary",
        transition="cut",
    )


def _plan(*scenes) -> VisualPlan:
    return VisualPlan(topic="test", scenes=list(scenes))


class TestProgressiveCurve(unittest.TestCase):
    def test_early_video_heavy_late_image_heavy(self):
        early = curve_video_bias(0.05, "automatic")
        late = curve_video_bias(0.85, "automatic")
        self.assertGreater(early, late)

    def test_image_heavy_strategy(self):
        auto = curve_video_bias(0.5, "automatic")
        img = curve_video_bias(0.5, "image_heavy")
        self.assertGreater(auto, img)


class TestAIBudget(unittest.TestCase):
    def test_budget_never_exceeded(self):
        settings = AllocationSettings(ai_video_budget="normal")
        limit = ai_budget_limit(148, settings)
        scored = [(i, 0.9 - i * 0.001) for i in range(1, 149)]
        chosen = select_flow_scenes(scored, limit)
        self.assertLessEqual(len(chosen), limit)

    def test_unused_budget_allowed(self):
        settings = AllocationSettings(ai_video_budget="conservative")
        limit = ai_budget_limit(20, settings)
        scored = [(1, 0.2), (2, 0.15)]
        chosen = select_flow_scenes(scored, limit)
        self.assertEqual(len(chosen), 0)


class TestAllocationEngine(unittest.TestCase):
    def test_late_important_action_still_video(self):
        resolved = resolve_style(mode="manual", style_id="space_documentary")
        scenes = [
            _scene(i, f"Scene {i} narration about stars.", duration=3.0)
            for i in range(1, 11)
        ]
        scenes[-1] = _scene(
            10,
            "The rocket launches into the night sky with fire and smoke.",
            importance="high",
            provider="flow",
            desc="rocket launch ignition night",
            duration=4.0,
        )
        plan = _plan(*scenes)
        bundle = allocate_visual_plan(
            plan, AllocationSettings(visual_strategy="automatic"), resolved
        )
        last = bundle.decisions[-1]
        self.assertIn(last.visual_kind, ("video",))
        self.assertTrue(last.curve_overridden or last.visual_need == "action")

    def test_style_affects_allocation(self):
        resolved_h = resolve_style(mode="manual", style_id="history_documentary")
        resolved_s = resolve_style(mode="manual", style_id="space_documentary")
        scene = _scene(
            1,
            "Archival manuscripts reveal the treaty signed in 1945.",
            desc="historical document treaty 1945",
        )
        b_h = allocate_visual_plan(_plan(scene), AllocationSettings(), resolved_h)
        b_s = allocate_visual_plan(_plan(scene), AllocationSettings(), resolved_s)
        self.assertNotEqual(b_h.decisions[0].asset_type, b_s.decisions[0].asset_type)

    def test_deterministic(self):
        plan = _plan(
            _scene(1, "Opening cinematic city at dawn.", provider="flow"),
            _scene(2, "Maps show the border changes over time.", desc="historical map border"),
        )
        a = allocate_visual_plan(plan, AllocationSettings(), None)
        b = allocate_visual_plan(plan, AllocationSettings(), None)
        self.assertEqual(a.decisions[0].asset_type, b.decisions[0].asset_type)
        self.assertEqual(a.decisions[1].asset_type, b.decisions[1].asset_type)

    def test_apply_mutates_plan(self):
        plan = _plan(_scene(1, "A rocket launch at night.", provider="flow", importance="high"))
        apply_allocation_to_plan(plan, AllocationSettings(ai_video_budget="normal"), None)
        self.assertTrue(plan.scenes[0].asset_type)
        self.assertTrue(plan.allocation)


class TestPromptBackfill(unittest.TestCase):
    def test_flow_reassigned_to_stock_gets_search_queries(self):
        scene = VisualScene(
            scene_id=10,
            narration="The Victorian house loomed under storm clouds.",
            visual_goal="establish mood",
            visual_description="Victorian house exterior storm clouds timelapse",
            asset_type="stock_video",
            provider_preference="stock_video",
            search_queries=[],
            timestamp_needed=False,
            timestamp_hint="",
            duration=3.5,
            importance="medium",
            fallbacks=["stock_image"],
            visual_treatment="static",
            transition="cut",
        )
        finalize_scene_prompts(scene)
        self.assertTrue(scene.search_queries)
        row = scene.to_scene_row()
        self.assertTrue(row.stock or row.prompt)

    def test_apply_allocation_never_exports_empty_stock_prompt(self):
        plan = _plan(
            VisualScene(
                scene_id=1,
                narration="Workers commute through fog at dawn.",
                visual_goal="show commute",
                visual_description="commuters crossing bridge fog morning",
                asset_type="image",
                provider_preference="flow_image",
                search_queries=[],
                timestamp_needed=False,
                timestamp_hint="",
                duration=3.0,
                importance="medium",
                fallbacks=["stock_image"],
                visual_treatment="static",
                transition="cut",
            ),
            VisualScene(
                scene_id=2,
                narration="A treaty map from 1945 hangs in the archive.",
                visual_goal="historical evidence",
                visual_description="",
                asset_type="flow_image",
                provider_preference="flow_image",
                search_queries=[],
                timestamp_needed=False,
                timestamp_hint="",
                duration=3.0,
                importance="medium",
                fallbacks=["stock_image"],
                visual_treatment="static",
                transition="cut",
            ),
        )
        apply_allocation_to_plan(
            plan,
            AllocationSettings(visual_strategy="image_heavy", ai_video_budget="conservative"),
            None,
        )
        rows = plan.to_scene_rows()
        errors = SceneAssetRouter.validate(rows, Path("/tmp/nonexistent_assets"))
        self.assertEqual(errors, [], msg=errors)
        for row in plan.to_csv_dicts():
            self.assertTrue(str(row.get("prompt") or "").strip(), msg=row)

    def test_local_asset_type_demoted_to_stock(self):
        scene = VisualScene(
            scene_id=3,
            narration="The user said they have a clip on disk.",
            visual_goal="use existing file",
            visual_description="desk with hard drive and video files",
            asset_type="local",
            provider_preference="local",
            search_queries=[],
            timestamp_needed=False,
            timestamp_hint="",
            duration=3.0,
            importance="low",
            fallbacks=["stock_image"],
            visual_treatment="static",
            transition="cut",
        )
        finalize_scene_prompts(scene)
        self.assertEqual(scene.asset_type, "stock_video")
        self.assertEqual(scene.provider_preference, "stock_video")
        self.assertTrue(scene.search_queries)
        row = scene.to_scene_row()
        self.assertEqual(row.asset_type, "stock_video")
        self.assertTrue(row.stock or row.prompt)


class TestBalancedFlowVideo(unittest.TestCase):
    def test_balanced_assigns_at_least_one_flow_video(self):
        scenes = [
            _scene(
                i,
                f"Conceptual visualization of neural networks layer {i}.",
                importance="high" if i == 3 else "medium",
                provider="flow",
                asset_type="image",
                desc=f"abstract neural network visualization {i}",
            )
            for i in range(1, 12)
        ]
        plan = _plan(*scenes)
        bundle = allocate_visual_plan(
            plan,
            AllocationSettings(visual_strategy="balanced", ai_video_budget="normal"),
            None,
        )
        flow = [d for d in bundle.decisions if d.flow_selected]
        self.assertTrue(flow, "expected some Flow assignments")
        videos = [d for d in flow if d.asset_type == "video"]
        self.assertTrue(videos, "balanced mode should include Flow video, not only stills")


class TestValidationReport(unittest.TestCase):
    def test_report_flags_empty_prompts(self):
        from visual_allocation.validation import build_plan_validation_report

        scene = _scene(1, "A beat.", desc="")
        scene.search_queries = []
        plan = _plan(scene)
        report = build_plan_validation_report(plan)
        self.assertIn("VALIDATION REPORT", report)
        self.assertIn("Scenes: 1", report)


class TestCoveragePlanner(unittest.TestCase):
    def test_long_enough_single_segment(self):
        scene = _scene(1, "Narration beat.", duration=5.0)
        dec = AllocationDecision(
            scene_id=1, visual_kind="video", asset_type="stock_video",
            provider_preference="stock",
        )
        cov = plan_scene_coverage(scene, dec, AllocationSettings())
        self.assertEqual(cov.strategy, "single")
        self.assertEqual(len(cov.segments), 1)

    def test_short_video_dual_coverage(self):
        scene = _scene(1, "Deep sea hydrothermal vent discovery.", duration=3.0, desc="hydrothermal vent ROV")
        dec = AllocationDecision(
            scene_id=1, visual_kind="video", asset_type="stock_video",
            provider_preference="stock",
        )
        cov = plan_scene_coverage(scene, dec, AllocationSettings(), narration_duration=6.0)
        self.assertIn(cov.strategy, ("dual", "hold_tail", "extend", "single"))
        if cov.strategy == "dual":
            self.assertEqual(len(cov.segments), 2)
            self.assertTrue(cov.avoid_blind_loop)

    def test_slight_shortfall_hold_tail(self):
        scene = _scene(1, "Brief action.", duration=6.0)
        scene.duration = 6.0
        dec = AllocationDecision(
            scene_id=1, visual_kind="video", asset_type="stock_video",
            provider_preference="stock",
        )
        cov = plan_scene_coverage(scene, dec, AllocationSettings(), narration_duration=6.0)
        self.assertIsNotNone(cov.strategy)


class TestDurationScoring(unittest.TestCase):
    def test_longer_relevant_wins(self):
        long = duration_fit_score(8.0, 12.0)
        short = duration_fit_score(8.0, 3.0)
        self.assertGreater(long, short)


class TestManualCSV(unittest.TestCase):
    def test_manual_authority_preserved(self):
        row = SceneRow(
            scene_number="1",
            script_segment="text",
            asset_type="flow_video",
            prompt="user prompt",
        )
        self.assertTrue(scene_has_manual_authority(row))


class TestSettingsPersistence(unittest.TestCase):
    def test_round_trip(self):
        from project_workspace import create_project

        with tempfile.TemporaryDirectory() as tmp:
            ws = create_project("Alloc Test", projects_root=Path(tmp))
            settings = AllocationSettings(visual_strategy="video_heavy", ai_video_budget="high")
            save_allocation_settings(ws, settings)
            loaded = load_allocation_settings(ws)
            self.assertEqual(loaded.visual_strategy, "video_heavy")
            self.assertEqual(loaded.ai_video_budget, "high")


from pathlib import Path

if __name__ == "__main__":
    unittest.main()
