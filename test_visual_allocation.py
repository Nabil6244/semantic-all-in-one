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
from visual_allocation.budget import (
    ai_budget_limit,
    flow_image_soft_cap,
    select_flow_image_scenes,
    select_flow_scenes,
    select_flow_video_scenes,
)
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
    def test_video_budget_never_exceeded(self):
        settings = AllocationSettings(ai_video_budget="normal")
        limit = ai_budget_limit(148, settings)
        scored = [(i, 0.9 - i * 0.001) for i in range(1, 149)]
        prelim = [
            {
                "scene": _scene(i, f"Beat {i} conceptual visualization.", provider="flow"),
                "need": "process",
                "role": "abstract",
                "prefer_video": True,
                "flow_score": 0.9 - i * 0.001,
            }
            for i in range(1, 149)
        ]
        chosen = select_flow_video_scenes(prelim, scored, limit)
        self.assertLessEqual(len(chosen), limit)

    def test_flow_image_can_exceed_video_budget(self):
        settings = AllocationSettings(visual_strategy="image_heavy", ai_video_budget="conservative")
        n = 40
        video_limit = ai_budget_limit(n, settings)
        image_cap = flow_image_soft_cap(n, settings)
        prelim = [
            {
                "scene": _scene(
                    i,
                    f"Conceptual metaphor layer {i} for the explainer.",
                    provider="flow",
                    desc=f"abstract diagram metaphor {i}",
                ),
                "need": "explanation",
                "role": "abstract",
                "prefer_video": False,
                "flow_score": 0.72 - i * 0.002,
            }
            for i in range(1, n + 1)
        ]
        scored = [(item["scene"].scene_id, item["flow_score"]) for item in prelim]
        videos = select_flow_video_scenes(prelim, scored, video_limit)
        images = select_flow_image_scenes(prelim, video_selected=videos, soft_cap=image_cap)
        self.assertLessEqual(len(videos), video_limit)
        self.assertGreater(len(images), len(videos))

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
    def test_balanced_assigns_flow_video_and_free_images(self):
        scenes = [
            _scene(
                i,
                f"Diagram explaining step {i} of the process with labels.",
                importance="medium",
                provider="flow",
                asset_type="image",
                desc=f"labeled diagram explainer step {i}",
            )
            for i in range(1, 9)
        ]
        scenes.extend(
            _scene(
                i,
                f"Rocket launch with fire and smoke beat {i}.",
                importance="high",
                provider="flow",
                desc=f"rocket launch cinematic {i}",
            )
            for i in range(9, 12)
        )
        plan = _plan(*scenes)
        bundle = allocate_visual_plan(
            plan,
            AllocationSettings(visual_strategy="balanced", ai_video_budget="normal"),
            None,
        )
        flow = [d for d in bundle.decisions if d.flow_selected]
        self.assertTrue(flow, "expected some Flow assignments")
        videos = [d for d in flow if d.asset_type == "video"]
        images = [d for d in flow if d.asset_type == "image"]
        self.assertTrue(videos, "balanced mode should still assign paid Flow video")
        self.assertTrue(images, "balanced mode should assign free Flow images")
        self.assertLessEqual(bundle.ai_assigned, bundle.ai_budget_limit)
        self.assertGreaterEqual(bundle.flow_image_assigned, len(images))


class TestLegacyAllocationMigration(unittest.TestCase):
    def test_v1_bundle_splits_video_and_image_counts(self):
        from visual_allocation.models import AllocationBundle

        raw = {
            "allocation_version": 1,
            "ai_budget_limit": 6,
            "ai_assigned": 4,
            "decisions": [
                {
                    "scene_id": 1,
                    "visual_kind": "video",
                    "asset_type": "video",
                    "provider_preference": "flow_video",
                    "flow_selected": True,
                },
                {
                    "scene_id": 2,
                    "visual_kind": "image",
                    "asset_type": "image",
                    "provider_preference": "flow_image",
                    "flow_selected": True,
                },
                {
                    "scene_id": 3,
                    "visual_kind": "image",
                    "asset_type": "image",
                    "provider_preference": "flow_image",
                    "flow_selected": True,
                },
            ],
        }
        bundle = AllocationBundle.from_dict(raw)
        self.assertEqual(bundle.ai_assigned, 1)
        self.assertEqual(bundle.flow_image_assigned, 2)


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



class TestFlowImagePriority(unittest.TestCase):
    """Flow image is the PREFERRED image source and is free: no cap may push an
    otherwise-eligible scene to stock. Stock image is a fallback only."""

    def _item(self, sid, need, *, role="context", prefer_video=False, flow_score=0.2, desc=""):
        return {
            "scene": _scene(sid, f"Scene {sid} narration line here.", desc=desc or f"scene {sid}"),
            "need": need,
            "role": role,
            "prefer_video": prefer_video,
            "flow_score": flow_score,
        }

    # --- selection layer ------------------------------------------------
    def test_normal_image_scene_selected_for_flow(self):
        prelim = [self._item(1, "explanation")]
        chosen = select_flow_image_scenes(prelim, video_selected=set(), soft_cap=1)
        self.assertIn(1, chosen, "an ordinary image-suitable scene must go to Flow image")

    def test_no_credit_cap_can_force_stock(self):
        """The old hard cap sent everything past the ceiling to stock. A free
        resource must not be rationed: every eligible scene stays on Flow."""
        prelim = [self._item(i, "explanation") for i in range(1, 61)]
        for cap in (0, 1, 3, 5):
            chosen = select_flow_image_scenes(prelim, video_selected=set(), soft_cap=cap)
            self.assertEqual(
                len(chosen), 60,
                f"soft_cap={cap} must not remove eligible scenes (got {len(chosen)})",
            )

    def test_practical_fit_floor_admits_ordinary_scenes(self):
        """Regression for the 0.38 floor that passed 1 of 131 eligible scenes."""
        prelim = [self._item(i, "context", flow_score=0.15) for i in range(1, 21)]
        chosen = select_flow_image_scenes(prelim, video_selected=set(), soft_cap=100)
        self.assertEqual(len(chosen), 20)

    def test_flow_video_scene_not_also_flow_image(self):
        prelim = [self._item(1, "explanation")]
        chosen = select_flow_image_scenes(prelim, video_selected={1}, soft_cap=10)
        self.assertEqual(chosen, set())

    def test_blocked_needs_never_selected_for_flow_image(self):
        for need in ("document", "map", "evidence", "timeline"):
            prelim = [self._item(1, need, flow_score=0.9)]
            chosen = select_flow_image_scenes(prelim, video_selected=set(), soft_cap=10)
            self.assertEqual(chosen, set(), f"need={need} must stay off Flow image")

    # --- end-to-end allocation -----------------------------------------
    def _plan(self, scenes):
        return VisualPlan(topic="t", scenes=list(scenes))

    def test_flow_image_preferred_over_stock_image(self):
        resolved = resolve_style(mode="manual", style_id="premium_documentary")
        settings = AllocationSettings(visual_strategy="image_heavy", ai_video_budget="conservative")
        scenes = [
            _scene(i, f"An explanation of the underlying idea, part {i}.",
                   asset_type="stock_image", desc=f"conceptual diagram {i}")
            for i in range(1, 41)
        ]
        bundle = allocate_visual_plan(self._plan(scenes), settings, resolved)
        types = [d.asset_type for d in bundle.decisions]
        flow_img = types.count("image")
        stock_img = types.count("stock_image")
        self.assertGreater(
            flow_img, stock_img,
            f"Flow image must win over stock image (flow={flow_img} stock={stock_img})",
        )

    def test_protected_documentary_scene_goes_to_stock_image(self):
        """IMAGE_NEED_OVERRIDE / IMAGE_NEED_BLOCK protection is unchanged: a
        factual/evidence scene must use real media, never a fabricated still."""
        from visual_allocation.allocator import IMAGE_NEED_OVERRIDE
        from visual_allocation.budget import IMAGE_NEED_BLOCK
        self.assertEqual(set(IMAGE_NEED_OVERRIDE), {"document", "map", "evidence", "timeline"})
        self.assertEqual(set(IMAGE_NEED_BLOCK), {"document", "map", "evidence", "timeline"})

        resolved = resolve_style(mode="manual", style_id="premium_documentary")
        settings = AllocationSettings(visual_strategy="image_heavy")
        scenes = [
            _scene(i,
                   "The declassified document and the original map were entered into evidence.",
                   asset_type="stock_image",
                   desc="archival document scan newspaper map")
            for i in range(1, 9)
        ]
        bundle = allocate_visual_plan(self._plan(scenes), settings, resolved)
        for dec in bundle.decisions:
            if dec.visual_need in IMAGE_NEED_OVERRIDE:
                self.assertNotEqual(
                    dec.asset_type, "image",
                    f"protected need={dec.visual_need} must not be AI-generated",
                )

    # --- fallback -------------------------------------------------------
    def test_flow_image_declares_stock_image_fallback(self):
        """Flow unavailable/failed -> stock image."""
        from visual_director.schema import parse_visual_plan
        plan = parse_visual_plan({
            "topic": "t",
            "scenes": [{
                "scene_id": i,
                "narration": f"A conceptual beat {i}.",
                "visual_goal": "show idea",
                "visual_description": f"abstract conceptual illustration {i}",
                "asset_type": "image",
                "provider_preference": "flow_image",
                "duration": 3.5,
            } for i in (1, 2)],
        })
        for scene in plan.scenes:
            self.assertEqual(scene.fallbacks, ["stock_image"])

    def test_flow_image_is_fallback_eligible(self):
        from asset_manager import _FALLBACK_ELIGIBLE_SOURCES
        from providers.base import AssetSource
        self.assertIn(AssetSource.FLOW_IMAGE, _FALLBACK_ELIGIBLE_SOURCES)
        self.assertNotIn(AssetSource.FLOW_VIDEO, _FALLBACK_ELIGIBLE_SOURCES)


class TestUnchangedBehaviour(unittest.TestCase):
    """Everything outside Flow-image routing must be untouched."""

    def test_flow_video_budget_unchanged(self):
        for mode, n, expect in (
            ("conservative", 100, 5), ("normal", 100, 12),
            ("high", 100, 18), ("conservative", 10, 2), ("high", 10, 12),
        ):
            self.assertEqual(ai_budget_limit(n, AllocationSettings(ai_video_budget=mode)), expect)

    def test_flow_video_selection_still_capped(self):
        settings = AllocationSettings(ai_video_budget="conservative")
        limit = ai_budget_limit(148, settings)
        scored = [(i, 0.9) for i in range(1, 149)]
        prelim = [
            {"scene": _scene(i, f"Action scene {i}."), "need": "action",
             "role": "abstract", "prefer_video": True, "flow_score": 0.9}
            for i in range(1, 149)
        ]
        chosen = select_flow_video_scenes(prelim, scored, limit)
        self.assertLessEqual(len(chosen), limit, "Flow VIDEO stays credit-capped")
        self.assertEqual(len(chosen), limit)

    def test_stock_video_routing_unchanged(self):
        from visual_allocation.allocator import _documentary_asset_type
        self.assertEqual(_documentary_asset_type("action", "context", "", True), "stock_video")
        self.assertEqual(_documentary_asset_type("context", "context", "", True), "stock_video")
        self.assertEqual(_documentary_asset_type("context", "context", "", False), "stock_image")
        self.assertEqual(_documentary_asset_type("map", "map", "", True), "stock_image")

    def test_youtube_and_doc_routing_unchanged(self):
        from visual_allocation.allocator import ASSET_TO_PROVIDER
        self.assertEqual(ASSET_TO_PROVIDER["youtube_video"], "youtube")
        self.assertEqual(ASSET_TO_PROVIDER["image"], "flow_image")
        self.assertEqual(ASSET_TO_PROVIDER["stock_image"], "stock_image")
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="1", script_segment="x",
                         asset_type="youtube_video", prompt="q")
            ).value,
            "youtube_video",
        )

    def test_youtube_default_fallbacks_unchanged(self):
        from visual_director.schema import parse_visual_plan
        plan = parse_visual_plan({
            "topic": "t",
            "scenes": [{
                "scene_id": i, "narration": f"n{i}", "visual_goal": "g",
                "visual_description": "d", "asset_type": "youtube_video",
                "provider_preference": "youtube",
                "search_queries": [f"archival footage {i}", f"historic film reel {i}"],
                "prompt": f"q{i}", "duration": 3.5,
            } for i in (1, 2)],
        })
        for scene in plan.scenes:
            self.assertEqual(scene.fallbacks, ["archive", "stock_video", "flow_image"])

    def test_research_routing_unchanged(self):
        from providers.base import AssetSource
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="1", script_segment="x",
                         asset_type="research", prompt="q")
            ),
            AssetSource.RESEARCH,
        )

from pathlib import Path

if __name__ == "__main__":
    unittest.main()
