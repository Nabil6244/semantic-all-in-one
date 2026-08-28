"""Visual QA + Auto-Fix tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from style_engine.visual_selection import scene_has_manual_authority
from visual_qa.coverage import score_duration_coverage
from visual_qa.fix_engine import FlowBudgetState, _flow_budget_from_allocation
from visual_qa.flow_qa import check_flow_temporal_quality
from visual_qa.models import VisualQAStatus, scene_preserves_source_authority, status_from_score
from visual_qa.repetition import score_repetition
from visual_qa.retry import recommended_action_for
from visual_qa.semantic import metadata_semantic_score
from visual_qa.technical import check_technical
from visual_qa.models import VisualQAResult


class TestTechnicalQA(unittest.TestCase):
    def test_missing_file_fails(self):
        rep = check_technical(Path("/nonexistent/file.mp4"), MediaType.VIDEO)
        self.assertFalse(rep.ok)
        self.assertEqual(rep.score, 0.0)

    def test_image_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "001.png"
            img.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
                b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            rep = check_technical(img, MediaType.IMAGE)
            self.assertTrue(rep.ok or rep.score > 0)


class TestCoverageQA(unittest.TestCase):
    def test_long_clip_passes(self):
        score, warnings, _ = score_duration_coverage(6.2, 8.1)
        self.assertGreaterEqual(score, 0.8)
        self.assertFalse(warnings)

    def test_short_clip_warns(self):
        score, warnings, _ = score_duration_coverage(6.0, 3.0)
        self.assertLess(score, 0.6)
        self.assertTrue(any("short" in w for w in warnings))


class TestSemanticMetadata(unittest.TestCase):
    def test_matching_title_scores_high(self):
        scene = SceneRow(
            scene_number="1",
            script_segment="Apollo 11 landed on the Moon in 1969.",
            asset_type="stock_video",
            prompt="apollo 11 moon landing",
        )
        result = AssetResult(
            "1",
            Path("001.mp4"),
            MediaType.VIDEO,
            AssetSource.STOCK_VIDEO,
            SceneStatus.READY,
            metadata={"title": "Apollo 11 Moon Landing", "description": "saturn v lunar surface"},
        )
        score, warnings = metadata_semantic_score(scene, result)
        self.assertGreater(score, 0.45)

    def test_generic_mismatch_scores_low(self):
        scene = SceneRow(
            scene_number="2",
            script_segment="Hydrothermal vents support unique deep-sea ecosystems.",
            asset_type="stock_video",
            prompt="hydrothermal vent ROV",
        )
        result = AssetResult(
            "2",
            Path("002.mp4"),
            MediaType.VIDEO,
            AssetSource.STOCK_VIDEO,
            SceneStatus.READY,
            metadata={"title": "ocean waves sunset", "description": "generic beach water"},
        )
        score, warnings = metadata_semantic_score(scene, result)
        self.assertLess(score, 0.55)


class TestRepetition(unittest.TestCase):
    def test_duplicate_asset_penalized(self):
        from style_engine.visual_selection import SelectionHistory

        hist = SelectionHistory()
        hist.record(provider="pexels", asset_id="abc123", title="ocean waves")
        score, warnings = score_repetition("abc123", "ocean waves", "", hist)
        self.assertLess(score, 0.7)
        self.assertTrue(any("duplicate" in w for w in warnings))


class TestManualAuthority(unittest.TestCase):
    def test_explicit_flow_video_preserved(self):
        row = SceneRow(
            scene_number="1",
            script_segment="Moon walk footage",
            asset_type="flow_video",
            prompt="astronauts walking on lunar surface",
        )
        self.assertTrue(scene_preserves_source_authority(row))
        self.assertTrue(scene_has_manual_authority(row))

    def test_empty_asset_type_not_manual(self):
        row = SceneRow(
            scene_number="2",
            script_segment="Automatic beat",
            asset_type="",
            prompt="",
        )
        self.assertFalse(scene_preserves_source_authority(row))


class TestRetryMapping(unittest.TestCase):
    def test_semantic_mismatch_suggests_alternative(self):
        qa = VisualQAResult(
            scene_number="3",
            status=VisualQAStatus.FAIL,
            overall_score=0.4,
            failure_reasons=["semantic mismatch"],
        )
        scene = SceneRow(scene_number="3", script_segment="x", asset_type="", prompt="apollo landing")
        action = recommended_action_for(qa, scene)
        self.assertEqual(action.value, "alternative")


class TestFlowBudget(unittest.TestCase):
    def test_reserve_blocks_unlimited_flow(self):
        state = FlowBudgetState(limit=10, used=10, reserve=1)
        self.assertFalse(state.can_regenerate_flow())

    def test_allocation_budget(self):
        state = _flow_budget_from_allocation({"ai_budget_limit": 20, "ai_assigned": 5}, 100)
        self.assertEqual(state.limit, 20)
        self.assertGreaterEqual(state.reserve, 1)


class TestFlowTemporal(unittest.TestCase):
    def test_identical_frames_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.jpg"
            p2 = Path(tmp) / "b.jpg"
            data = b"sameframe"
            p1.write_bytes(data)
            p2.write_bytes(data)
            score, warnings = check_flow_temporal_quality([p1, p2])
            self.assertLess(score, 0.5)
            self.assertTrue(warnings)


class TestStatusThresholds(unittest.TestCase):
    def test_pass_weak_fail(self):
        self.assertEqual(status_from_score(0.85), VisualQAStatus.PASS)
        self.assertEqual(status_from_score(0.7), VisualQAStatus.WEAK)
        self.assertEqual(status_from_score(0.4), VisualQAStatus.FAIL)


if __name__ == "__main__":
    unittest.main()
