"""Brand Kit + Style Intelligence 2.0 tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from editorial.builder import build_editorial_plan
from editorial.persistence import cache_settings_key
from editorial.schema import ALLOWED_PURPOSES
from style_engine import (
    BrandKit,
    VideoStyle,
    apply_resolved_style,
    asset_preference_rank,
    build_content_profile,
    detect_style,
    load_brand_kit,
    load_style,
    merge_brand_overrides,
    resolve_style,
    score_styles,
    style_choices,
)
from style_engine.loader import clear_loader_caches
from style_engine.profile import load_cached_profile, save_cached_profile


def _mini_rows():
    return [
        {
            "scene_number": "1",
            "script_segment": "In the ancient Roman empire, maps told the story.",
            "asset_type": "stock_image",
            "prompt": "roman map archival",
        },
        {
            "scene_number": "2",
            "script_segment": "Evidence from the manuscripts confirms the timeline.",
            "asset_type": "stock_video",
            "prompt": "old manuscript",
        },
        {
            "scene_number": "3",
            "script_segment": "And still the empire expanded westward.",
            "asset_type": "youtube_video",
            "prompt": "historical documentary",
        },
    ]


def _aligned(rows):
    out = []
    t = 0.0
    for r in rows:
        dur = 3.0
        out.append(
            {
                "scene_number": r["scene_number"],
                "script_segment": r["script_segment"],
                "start_time": t,
                "end_time": t + dur,
            }
        )
        t += dur
    return out, t


def _top_style(script: str):
    style, conf, reason, alts, profile, scores = detect_style(script=script)
    return style, conf, reason, alts, profile, scores


class TestStyleJsonRoundTrip(unittest.TestCase):
    def test_builtin_styles_load(self):
        clear_loader_caches()
        choices = style_choices()
        ids = {sid for sid, _ in choices}
        self.assertGreaterEqual(len(ids), 4)
        for sid in (
            "history_documentary",
            "premium_documentary",
            "ai_narration",
            "space_documentary",
        ):
            self.assertIn(sid, ids)
            style = load_style(sid)
            self.assertIsNotNone(style)
            self.assertTrue(style.intelligence.weights)
            again = VideoStyle.from_dict(style.to_dict())
            self.assertEqual(again.id, sid)
            self.assertEqual(again.name, style.name)

    def test_brand_kit_round_trip(self):
        kit = load_brand_kit("default")
        self.assertIsNotNone(kit)
        again = BrandKit.from_dict(kit.to_dict())
        self.assertEqual(again.id, "default")
        self.assertEqual(again.accent_color, kit.accent_color)


class TestResolverModes(unittest.TestCase):
    def test_legacy_none(self):
        self.assertIsNone(resolve_style(mode=""))
        self.assertIsNone(resolve_style(project_meta={}))
        self.assertIsNone(resolve_style(project_meta={"video_style": {"mode": ""}}))

    def test_manual_overrides_auto(self):
        r = resolve_style(mode="manual", style_id="space_documentary")
        self.assertIsNotNone(r)
        self.assertEqual(r.mode, "manual")
        self.assertEqual(r.style_id, "space_documentary")
        self.assertEqual(r.confidence, 1.0)

    def test_auto_no_gemini(self):
        rows = _mini_rows()
        r = resolve_style(mode="auto", rows=rows, script=rows[0]["script_segment"] * 3)
        self.assertIsNotNone(r)
        self.assertEqual(r.mode, "auto")
        self.assertTrue(r.style_id)
        self.assertGreater(r.confidence, 0.2)
        self.assertTrue(r.reason)
        self.assertTrue(r.alternatives is not None)

    def test_auto_space_topic(self):
        style, conf, reason, *_ = _top_style(
            "Across the cosmos, galaxies collide while telescopes map nebulae and black holes."
        )
        self.assertEqual(style.id, "space_documentary")
        self.assertGreater(conf, 0.3)
        self.assertTrue(reason)

    def test_custom_brand_override(self):
        brand = BrandKit(
            id="test_brand",
            name="Test",
            overrides={"audio": {"sfx_intensity": 0.99}},
            ai_prompt_additions="always show brand colors",
        )
        r = resolve_style(
            mode="custom",
            style_id="premium_documentary",
            brand_kit=brand,
        )
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.style.audio.sfx_intensity, 0.99, places=2)
        self.assertIn("brand colors", r.style.ai_visual_prompt.style)
        # Core intelligence weights preserved (brand does not wipe them)
        self.assertTrue(r.style.intelligence.weights)


class TestStyleIntelligenceScoring(unittest.TestCase):
    def test_history_script_highest(self):
        style, conf, *_ = _top_style(
            "During the final years of the Roman Empire, archival manuscripts and maps "
            "reveal how wars reshaped ancient civilizations across centuries."
        )
        self.assertEqual(style.id, "history_documentary")
        self.assertGreater(conf, 0.4)

    def test_space_script_highest(self):
        style, conf, *_ = _top_style(
            "Across billions of years, stars are born in nebulae; planets orbit and "
            "galaxies expand while spacecraft study orbital physics."
        )
        self.assertEqual(style.id, "space_documentary")
        self.assertGreater(conf, 0.4)

    def test_ai_narration_script_highest(self):
        style, conf, *_ = _top_style(
            "Imagine waking up tomorrow and discovering the secret nobody talks about. "
            "In this video, here's why step by step tips will change how you think."
        )
        self.assertEqual(style.id, "ai_narration")
        self.assertGreater(conf, 0.4)

    def test_premium_or_narration_arctic(self):
        style, conf, reason, alts, profile, scores = _top_style(
            "The disappearance of the Arctic ice is reshaping landscapes and wildlife "
            "in an immersive cinematic investigation of climate atmosphere."
        )
        self.assertIn(style.id, ("premium_documentary", "ai_narration"))
        self.assertGreater(conf, 0.35)
        self.assertTrue(reason)
        self.assertGreaterEqual(len(scores), 2)

    def test_nasa_alone_not_forced_space(self):
        # Broader history context with NASA mention should not auto-lock Space.
        style, conf, *_ = _top_style(
            "During the Cold War, archival documents show how NASA funding battles "
            "in Congress reflected empire-era politics and historical treaties."
        )
        self.assertEqual(style.id, "history_documentary")

    def test_ambiguous_fallback_stable(self):
        a, ca, *_ = _top_style("Hello world. This is a short note.")
        b, cb, *_ = _top_style("Hello world. This is a short note.")
        self.assertEqual(a.id, b.id)
        self.assertAlmostEqual(ca, cb, places=3)

    def test_mixed_topic_sensible_confidence(self):
        style, conf, reason, alts, profile, scores = _top_style(
            "Historians study Roman maps while scientists explain quantum molecules "
            "and YouTube explainers imagine waking up to discover secrets."
        )
        self.assertTrue(style.id)
        self.assertGreater(conf, 0.3)
        self.assertLessEqual(conf, 1.0)
        ids = [s["style_id"] for s in scores]
        self.assertEqual(len(ids), len(set(ids)))

    def test_gemini_optional_enrichment_hook(self):
        # Without STYLE_GEMINI_ENRICH, profile is local-only even if settings passed.
        style, conf, reason, alts, profile, scores = detect_style(
            script="Across billions of years, stars are born in nebulae and galaxies.",
            gemini_settings={"gemini_api_key": "fake-key"},
        )
        self.assertEqual(style.id, "space_documentary")
        self.assertGreater(conf, 0.3)

    def test_content_profile_cache_invalidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            p1 = build_content_profile(script="Roman Empire archival manuscripts history")
            save_cached_profile(state, p1)
            loaded = load_cached_profile(state, p1.source_hash)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.domain, p1.domain)
            # Different script → different hash → cache miss
            p2 = build_content_profile(script="Stars nebulae galaxies spacecraft orbit")
            self.assertNotEqual(p1.source_hash, p2.source_hash)
            self.assertIsNone(load_cached_profile(state, p2.source_hash))


class TestApplyAndPlan(unittest.TestCase):
    def test_legacy_plan_unchanged_without_style(self):
        rows = _mini_rows()
        aligned, end = _aligned(rows)
        a = build_editorial_plan(rows, aligned, end, resolved_style=None)
        b = build_editorial_plan(rows, aligned, end, resolved_style=None)
        self.assertEqual(
            [s.camera_style for s in a.scenes],
            [s.camera_style for s in b.scenes],
        )
        self.assertEqual(
            [s.pacing_bias for s in a.scenes],
            [s.pacing_bias for s in b.scenes],
        )
        self.assertFalse(getattr(a, "style", None))

    def test_styles_diverge_materially(self):
        rows = _mini_rows()
        aligned, end = _aligned(rows)
        cams = {}
        pacing = {}
        amb = {}
        purposes = {}
        variety = {}
        for sid in (
            "history_documentary",
            "premium_documentary",
            "ai_narration",
            "space_documentary",
        ):
            resolved = resolve_style(mode="manual", style_id=sid)
            plan = build_editorial_plan(rows, aligned, end, resolved_style=resolved)
            cams[sid] = tuple(s.camera_style for s in plan.scenes)
            pacing[sid] = tuple(s.pacing_bias for s in plan.scenes)
            amb[sid] = tuple(round(s.ambience_intensity, 3) for s in plan.scenes)
            purposes[sid] = tuple(s.purpose for s in plan.scenes)
            variety[sid] = tuple(s.visual_variety_key for s in plan.scenes)
            self.assertTrue(getattr(plan, "style", None))
            meta = plan.style
            self.assertEqual(meta.get("style_id"), sid)
            self.assertIn("style_influences", meta)
            for s, row in zip(plan.scenes, rows):
                self.assertEqual(s.asset_type_intent, row["asset_type"])
        distinct = {cams[k] + pacing[k] + amb[k] for k in cams}
        self.assertGreaterEqual(len(distinct), 3)
        # Variety families differ by style
        families = {v[0].split(":")[0] for v in variety.values() if v}
        self.assertGreaterEqual(len(families), 3)

    def test_style_changes_scene_purposes(self):
        rows = [
            {
                "scene_number": "1",
                "script_segment": "Imagine Earth compared with Jupiter at true scale.",
                "asset_type": "image",
                "prompt": "scale",
            },
            {
                "scene_number": "2",
                "script_segment": "This changed everything for the mission.",
                "asset_type": "video",
                "prompt": "reveal",
            },
        ]
        aligned, end = _aligned(rows)
        space = resolve_style(mode="manual", style_id="space_documentary")
        plan_s = build_editorial_plan(rows, aligned, end, resolved_style=space)
        self.assertIn(plan_s.scenes[0].purpose, ("scale", "comparison", "explanation", "hook"))

        ai = resolve_style(mode="manual", style_id="ai_narration")
        plan_a = build_editorial_plan(rows, aligned, end, resolved_style=ai)
        self.assertIn(plan_a.scenes[1].purpose, ("reveal", "hook", "emotion"))

    def test_asset_preferences_non_destructive(self):
        r = resolve_style(mode="manual", style_id="history_documentary")
        self.assertGreater(asset_preference_rank(r, "stock_image"), asset_preference_rank(r, "video"))
        rows = _mini_rows()
        aligned, end = _aligned(rows)
        plan = build_editorial_plan(rows, aligned, end, resolved_style=r)
        for s, row in zip(plan.scenes, rows):
            self.assertEqual(s.asset_type_intent, row["asset_type"])

    def test_brand_override_precedence(self):
        base = load_style("ai_narration")
        brand = BrandKit(
            id="b",
            overrides={"audio": {"ambience_intensity": 0.11}},
        )
        merged = merge_brand_overrides(base, brand)
        self.assertAlmostEqual(merged.audio.ambience_intensity, 0.11, places=2)
        # Editorial intelligence not wiped
        self.assertEqual(
            merged.intelligence.variety_family,
            base.intelligence.variety_family,
        )

    def test_cache_key_includes_style(self):
        rows = _mini_rows()
        k0 = cache_settings_key(rows)
        k1 = cache_settings_key(
            rows,
            style_fingerprint={
                "mode": "manual",
                "style_id": "ai_narration",
                "style_version": 2,
                "brand_kit_id": None,
                "brand_version": None,
            },
        )
        k2 = cache_settings_key(
            rows,
            style_fingerprint={
                "mode": "manual",
                "style_id": "space_documentary",
                "style_version": 2,
                "brand_kit_id": None,
                "brand_version": None,
            },
        )
        self.assertNotEqual(k0, k1)
        self.assertNotEqual(k1, k2)

    def test_new_purposes_allowed(self):
        for p in (
            "reveal",
            "comparison",
            "scale",
            "process",
            "timeline",
            "location",
            "character",
            "reflection",
        ):
            self.assertIn(p, ALLOWED_PURPOSES)


class TestProjectMeta(unittest.TestCase):
    def test_video_style_settings_round_trip(self):
        from project_workspace import create_project

        with tempfile.TemporaryDirectory() as tmp:
            ws = create_project("Style Meta", projects_root=Path(tmp))
            self.assertEqual(ws.video_style_settings()["mode"], "")
            ws.set_video_style_settings(
                mode="auto", style_id="premium_documentary", brand_kit_id="default"
            )
            got = ws.video_style_settings()
            self.assertEqual(got["mode"], "auto")
            self.assertEqual(got["style_id"], "premium_documentary")
            self.assertEqual(got["brand_kit_id"], "default")
            ws.set_style_resolution(
                {
                    "style_id": "premium_documentary",
                    "confidence": 0.8,
                    "reason": "test",
                    "alternatives": [{"style_id": "ai_narration", "score": 0.5}],
                }
            )
            self.assertEqual(ws.style_resolution()["reason"], "test")
            self.assertEqual(ws.style_resolution()["alternatives"][0]["style_id"], "ai_narration")


if __name__ == "__main__":
    unittest.main()
