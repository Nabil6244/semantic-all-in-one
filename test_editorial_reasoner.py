"""Tests for AI Editorial Director / EditorialReasoner (mocked — no live Gemini)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from editorial.builder import build_editorial_plan
from editorial.engine import EditorialEngine, compile_editorial_plan
from editorial.intent import (
    CONF_MEDIUM,
    EditorialIntent,
    ROLE_TO_PLANNER,
)
from editorial.persistence import load_cached_plan, save_editorial_plan
from editorial.reasoner import (
    NullEditorialReasoner,
    StaticEditorialReasoner,
    apply_intents_to_scenes,
    enrich_plan_with_editorial_ai,
    intent_fingerprint,
    parse_intent_payload,
    reasoner_mode,
)
from editorial.schema import EDITORIAL_PLAN_VERSION, EditorialPlan, EditorialScene
from editorial.shot_planner import plan_edit_decision
from editorial.complements import AssetCandidate


def _png(path: Path, color=(40, 80, 120)) -> Path:
    Image.new("RGB", (320, 180), color).save(path)
    return path


def _plan_two() -> EditorialPlan:
    rows = [
        {
            "scene_number": "1",
            "script_segment": "America needs thousands of new transformers.",
            "asset_type": "stock_video",
            "prompt": "factory",
        },
        {
            "scene_number": "2",
            "script_segment": "Demand is expected to rise by 25 percent.",
            "asset_type": "stock_image",
            "prompt": "chart",
        },
    ]
    aligned = [
        {
            "scene_number": "1",
            "script_segment": rows[0]["script_segment"],
            "start_time": 0.0,
            "end_time": 5.0,
        },
        {
            "scene_number": "2",
            "script_segment": rows[1]["script_segment"],
            "start_time": 5.0,
            "end_time": 9.0,
        },
    ]
    plan = build_editorial_plan(rows, aligned, 9.0)
    plan.scenes[0].actual_asset_duration = 3.0
    return plan


class TestIntentSchema(unittest.TestCase):
    def test_valid_ai_output_normalized(self) -> None:
        raw = {
            "scene_number": "1",
            "visual_role": "CAUSE_EFFECT",
            "visual_strategy": "PROCESS_SEQUENCE",
            "evidence_level": "MEDIUM",
            "shot_strategy": "MULTI",
            "pacing": "NORMAL",
            "reveal": False,
            "text_strategy": "NONE",
            "sound_strategy": "AMBIENCE",
            "emotional_state": "UNDERSTANDING",
            "confidence": 0.91,
            "preferred_asset_ids": ["001", "001_b"],
        }
        intent = EditorialIntent.from_dict(raw)
        self.assertEqual(intent.visual_role, "cause_effect")
        self.assertEqual(intent.visual_strategy, "process_sequence")
        self.assertEqual(intent.shot_strategy, "multi")
        self.assertEqual(intent.planner_visual_role(), "cause_effect")
        self.assertTrue(intent.prefer_dual())
        self.assertAlmostEqual(intent.confidence, 0.91)

    def test_invalid_enums_fall_back(self) -> None:
        intent = EditorialIntent.from_dict(
            {
                "scene_number": "2",
                "visual_role": "NOT_A_ROLE",
                "pacing": "warp_speed",
                "text_strategy": "emoji_rain",
                "confidence": 50,
            }
        )
        self.assertEqual(intent.visual_role, "context")
        self.assertEqual(intent.pacing, "normal")
        self.assertEqual(intent.text_strategy, "none")
        self.assertAlmostEqual(intent.confidence, 0.5)

    def test_parse_payload_drops_unknown_scenes(self) -> None:
        payload = {
            "intents": [
                {"scene_number": "1", "visual_role": "process", "confidence": 0.9},
                {"scene_number": "99", "visual_role": "reveal", "confidence": 0.9},
                {"scene_number": "2", "visual_role": "data", "confidence": 0.2},
            ]
        }
        out = parse_intent_payload(payload, valid_scenes=["1", "2"])
        self.assertIn("1", out)
        self.assertNotIn("99", out)
        self.assertNotIn("2", out)  # low confidence dropped


class TestReasonerModes(unittest.TestCase):
    def test_ai_disabled_without_key(self) -> None:
        self.assertEqual(reasoner_mode({}), "AI_DISABLED")
        self.assertEqual(reasoner_mode({"editorial_ai": False, "gemini_api_key": "x"}), "AI_DISABLED")

    def test_null_reasoner_empty(self) -> None:
        plan = _plan_two()
        out = NullEditorialReasoner().reason(plan)
        self.assertEqual(out, {})

    def test_static_reasoner_applies(self) -> None:
        plan = _plan_two()
        intents = {
            "1": EditorialIntent(
                scene_number="1",
                visual_role="process",
                visual_strategy="process_sequence",
                shot_strategy="dual",
                pacing="fast",
                confidence=0.9,
                source="ai",
            )
        }
        reasoner = StaticEditorialReasoner(intents=intents)
        got = enrich_plan_with_editorial_ai(plan, reasoner=reasoner, force=True)
        self.assertIn("1", got)
        self.assertEqual(plan.scenes[0].pacing_bias, "fast")
        self.assertTrue(plan.editorial_intents)

    def test_intent_cache_fingerprint(self) -> None:
        plan = _plan_two()
        fp1 = intent_fingerprint(plan)
        fp2 = intent_fingerprint(plan)
        self.assertEqual(fp1, fp2)
        plan.scenes[0].narration_excerpt = "Changed narration entirely."
        self.assertNotEqual(fp1, intent_fingerprint(plan))

    def test_cached_intents_skip_second_call(self) -> None:
        plan = _plan_two()
        intents = {
            "1": EditorialIntent(
                scene_number="1",
                visual_role="evidence",
                confidence=0.88,
                source="ai",
            )
        }
        reasoner = StaticEditorialReasoner(intents=intents)
        enrich_plan_with_editorial_ai(plan, reasoner=reasoner, force=True)
        self.assertEqual(reasoner.calls, 1)
        enrich_plan_with_editorial_ai(plan, reasoner=reasoner, force=False)
        self.assertEqual(reasoner.calls, 1)  # cache hit


class TestIntentBiasesPlanner(unittest.TestCase):
    def test_ai_disabled_deterministic_unchanged(self) -> None:
        plan = _plan_two()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "001.png")
            _png(root / "002.png")
            a = compile_editorial_plan(plan, images_dir=root, skip_ai=True)
            b = compile_editorial_plan(
                _plan_two(),
                images_dir=root,
                gemini_settings={"editorial_ai": False},
            )
            self.assertEqual(
                [d["strategy"] for d in a.edit_decisions],
                [d["strategy"] for d in b.edit_decisions],
            )

    def test_process_intent_prefers_dual_when_complements(self) -> None:
        scene = EditorialScene(
            scene_number="1",
            start=0,
            end=8,
            duration=8,
            narration_excerpt="Rising demand forces utilities to order more transformers.",
            purpose="explanation",
            asset_type_intent="stock_video",
            actual_asset_duration=3.0,
            visual_description="transformer factory",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = _png(root / "001.png")
            comp = _png(root / "001_b.png", (9, 9, 9))
            candidates = [
                AssetCandidate(
                    asset_id="001",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformer factory",
                ),
                AssetCandidate(
                    asset_id="001_b",
                    path=comp,
                    visual_role="action",
                    query_hint="transformer transportation electricity demand utilities",
                    asset_class="stock_image",
                ),
            ]
            intent = EditorialIntent(
                scene_number="1",
                visual_role="cause_effect",
                visual_strategy="cause_effect",
                shot_strategy="dual",
                pacing="normal",
                evidence_level="medium",
                preferred_asset_ids=["001_b"],
                confidence=0.92,
                source="ai",
            )
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
                intent=intent,
            )
            self.assertEqual(d.strategy, "DUAL_ASSET")
            self.assertEqual(d.visual_role, "cause_effect")

    def test_reflective_intent_prefers_single(self) -> None:
        scene = EditorialScene(
            scene_number="1",
            start=0,
            end=5,
            duration=5,
            narration_excerpt="It was a quiet turning point.",
            purpose="emotion",
            asset_type_intent="stock_video",
            actual_asset_duration=6.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            primary = _png(Path(tmp) / "001.png")
            intent = EditorialIntent(
                scene_number="1",
                visual_role="atmosphere",
                shot_strategy="single",
                pacing="reflective",
                text_strategy="none",
                sound_strategy="silence",
                confidence=0.9,
            )
            d = plan_edit_decision(scene, media_path=primary, intent=intent)
            self.assertIn(d.strategy, ("SINGLE_SHOT", "IMAGE_MOTION"))
            self.assertEqual(len(d.shots), 1)

    def test_engine_with_static_reasoner(self) -> None:
        plan = _plan_two()
        raw = json.dumps(
            {
                "intents": [
                    {
                        "scene_number": "1",
                        "visual_role": "process",
                        "visual_strategy": "process_sequence",
                        "shot_strategy": "multi",
                        "pacing": "build",
                        "evidence_level": "medium",
                        "text_strategy": "none",
                        "sound_strategy": "ambience",
                        "emotional_state": "understanding",
                        "confidence": 0.87,
                        "reasoning": "Show manufacturing process.",
                    },
                    {
                        "scene_number": "2",
                        "visual_role": "data",
                        "visual_strategy": "evidence",
                        "shot_strategy": "single",
                        "pacing": "impact",
                        "evidence_level": "high",
                        "text_strategy": "statistic",
                        "graphic_strategy": "chart",
                        "sound_strategy": "impact",
                        "emotional_state": "impact",
                        "reveal": True,
                        "reveal_phase": "reveal",
                        "confidence": 0.93,
                        "reasoning": "Emphasize the 25% statistic.",
                    },
                ]
            }
        )
        reasoner = StaticEditorialReasoner(raw_json=raw)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "001.png")
            _png(root / "002.png")
            engine = EditorialEngine(plan)
            engine.compile(images_dir=root, reasoner=reasoner)
            self.assertTrue(plan.editorial_intents)
            kinds = {e.kind for e in engine.events}
            self.assertIn("statistic", kinds)
            self.assertIn("reveal", kinds)
            d2 = next(d for d in engine.decisions if d.scene_number == "2")
            self.assertEqual(d2.reveal_phase, "reveal")


class TestVersionCompatibility(unittest.TestCase):
    def test_plan_version_is_current(self) -> None:
        self.assertEqual(EDITORIAL_PLAN_VERSION, 6)

    def test_old_cache_invalidated(self) -> None:
        plan = _plan_two()
        plan.version = EDITORIAL_PLAN_VERSION
        plan.audio_key = "a"
        plan.settings_key = "s"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            save_editorial_plan(state, plan)
            path = state / "editorial_plan.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["version"] = 4
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertIsNone(load_cached_plan(state, audio_key="a", settings_key="s"))


class TestApplyIntents(unittest.TestCase):
    def test_low_confidence_ignored(self) -> None:
        plan = _plan_two()
        before = plan.scenes[0].purpose
        apply_intents_to_scenes(
            plan,
            {
                "1": EditorialIntent(
                    scene_number="1",
                    visual_role="reveal",
                    confidence=0.3,
                )
            },
        )
        self.assertEqual(plan.scenes[0].purpose, before)

    def test_role_mapping_table(self) -> None:
        self.assertEqual(ROLE_TO_PLANNER["document"], "claim_evidence")
        self.assertEqual(ROLE_TO_PLANNER["data"], "statistic")


if __name__ == "__main__":
    unittest.main()
