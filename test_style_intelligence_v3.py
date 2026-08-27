"""Style Intelligence 3.0 + smart visual selection tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from providers.base import SceneRow
from providers.media_quality.scoring import ScoreBreakdown
from style_engine import (
    SelectionHistory,
    build_scene_visual_profile,
    build_selection_context,
    expand_search_strategies,
    load_style,
    resolve_style,
    scene_has_manual_authority,
    smart_media_queries,
    smart_selection_score,
    style_choices,
    visual_role_score,
)
from style_engine.loader import clear_loader_caches


def _scene(**kwargs) -> SceneRow:
    defaults = {
        "scene_number": "1",
        "script_segment": "",
        "asset_type": "stock_video",
        "prompt": "",
        "stock": "",
    }
    defaults.update(kwargs)
    return SceneRow(**defaults)


class TestBuiltinStylesV3(unittest.TestCase):
    EXPECTED_IDS = (
        "history_documentary",
        "premium_documentary",
        "ai_narration",
        "space_documentary",
        "ocean_marine_documentary",
        "science_documentary",
        "nature_wildlife_documentary",
        "true_crime_documentary",
        "technology_documentary",
        "future_tech_documentary",
        "geopolitics_documentary",
        "business_economics_documentary",
        "biography_documentary",
        "military_war_documentary",
        "ancient_history_documentary",
        "mystery_documentary",
        "educational_explainer",
        "news_current_affairs",
    )

    def setUp(self):
        clear_loader_caches()

    def test_every_builtin_style_loads(self):
        ids = {sid for sid, _ in style_choices()}
        for sid in self.EXPECTED_IDS:
            self.assertIn(sid, ids, msg=f"missing style {sid}")
            style = load_style(sid)
            self.assertIsNotNone(style)
            self.assertGreaterEqual(style.version, 2)
            self.assertTrue(style.visual_roles.weights or style.search_guidance.prefer_terms)

    def test_style_json_round_trip_v3_fields(self):
        style = load_style("history_documentary")
        again = type(style).from_dict(style.to_dict())
        self.assertEqual(again.search_guidance.evidence_bias, "high")
        self.assertIn("archival_evidence", again.visual_roles.weights)


class TestVisualProfile(unittest.TestCase):
    def test_history_archival_role(self):
        scene = _scene(
            script_segment="Archival manuscripts and maps reveal the Roman Empire's expansion.",
            prompt="roman empire map archival",
            search_queries=["roman empire map", "roman archival"],
            visual_description="historical map evidence",
        )
        resolved = resolve_style(mode="manual", style_id="history_documentary")
        profile = build_scene_visual_profile(scene, resolved)
        self.assertIn(profile.visual_role, ("archival_evidence", "map", "event", "timeline"))
        self.assertEqual(profile.evidence_level, "high")

    def test_space_scientific_role(self):
        scene = _scene(
            script_segment="NASA's spacecraft orbited Jupiter while telescopes mapped the planet.",
            prompt="Jupiter NASA mission",
            search_queries=["Jupiter NASA", "spacecraft orbit"],
        )
        resolved = resolve_style(mode="manual", style_id="space_documentary")
        profile = build_scene_visual_profile(scene, resolved)
        self.assertIn(profile.visual_role, ("scientific_visualization", "scale", "object"))

    def test_manual_csv_authority(self):
        scene = _scene(
            asset_type="stock_video",
            prompt="exact user query",
            script_segment="Some narration.",
        )
        self.assertTrue(scene_has_manual_authority(scene))
        auto = _scene(
            asset_type="stock_video",
            prompt="query",
            search_queries=["expanded query"],
            script_segment="Narration.",
        )
        self.assertFalse(scene_has_manual_authority(auto))


class TestSearchStrategies(unittest.TestCase):
    def test_apollo_expansion(self):
        scene = _scene(
            script_segment="In 1969, America watched as Apollo 11 carried humans to the Moon.",
            prompt="Apollo 11 launch archival footage",
            search_queries=["Apollo 11 launch archival footage"],
            visual_description="Saturn V launch",
        )
        resolved = resolve_style(mode="manual", style_id="space_documentary")
        profile = build_scene_visual_profile(scene, resolved)
        strategies = expand_search_strategies(scene, profile, resolved.style, manual=False)
        joined = " ".join(strategies).lower()
        self.assertIn("apollo", joined)
        self.assertGreater(len(strategies), 2)

    def test_manual_keeps_user_query(self):
        scene = _scene(
            asset_type="stock_video",
            prompt="exact user keywords only",
            stock="exact user keywords only",
            script_segment="Narration about topic.",
        )
        resolved = resolve_style(mode="manual", style_id="history_documentary")
        queries = smart_media_queries(scene, resolved)
        self.assertEqual(queries[0], "exact user keywords only")


class TestCandidateScoring(unittest.TestCase):
    def test_history_prefers_archival_over_generic(self):
        resolved = resolve_style(mode="manual", style_id="history_documentary")
        ctx = build_selection_context(
            _scene(
                script_segment="The Great Depression transformed American life in the 1930s.",
                prompt="Great Depression breadline",
                search_queries=["Great Depression breadline"],
            ),
            resolved,
            SelectionHistory(),
        )
        archival = smart_selection_score(
            query="Great Depression breadline",
            script_segment=ctx.profile.topic or "Great Depression",
            title="1930s breadline archival photograph",
            description="historical depression era footage",
            width=1280,
            height=720,
            provider="archive",
            asset_id="a1",
            is_archival=True,
            context=ctx,
        )
        generic = smart_selection_score(
            query="Great Depression breadline",
            script_segment="Great Depression",
            title="modern businessman in office",
            description="corporate stock video",
            width=1920,
            height=1080,
            provider="pexels",
            asset_id="b1",
            context=ctx,
        )
        self.assertGreater(archival.relevance, 0)
        self.assertGreater(archival.style_fit_score, generic.style_fit_score)

    def test_space_prefers_nasa_mission(self):
        resolved = resolve_style(mode="manual", style_id="space_documentary")
        ctx = build_selection_context(
            _scene(
                script_segment="Apollo 11 astronauts walked on the Moon in 1969.",
                prompt="Apollo 11 moon landing NASA",
            ),
            resolved,
        )
        nasa = smart_selection_score(
            query="Apollo 11 moon landing",
            script_segment="Apollo 11 astronauts Moon 1969",
            title="Apollo 11 NASA mission footage moon landing",
            description="spacecraft lunar surface",
            width=854,
            height=480,
            provider="nasa",
            asset_id="n1",
            is_archival=True,
            context=ctx,
        )
        waves = smart_selection_score(
            query="Apollo 11 moon landing",
            script_segment="Apollo 11 astronauts Moon",
            title="ocean waves sunset",
            description="generic beach broll",
            width=1920,
            height=1080,
            provider="pexels",
            asset_id="p1",
            context=ctx,
        )
        self.assertGreater(nasa.final_selection_score, waves.final_selection_score)

    def test_ai_narration_explanatory_intent(self):
        style = load_style("ai_narration")
        role = visual_role_score(
            "process",
            "step by step diagram demonstration mechanism",
            style,
        )
        self.assertGreater(role, 0.3)

    def test_premium_cinematic_intent(self):
        style = load_style("premium_documentary")
        role = visual_role_score(
            "establishing",
            "cinematic establishing shot atmospheric landscape",
            style,
        )
        self.assertGreater(role, 0.2)

    def test_repetition_penalty(self):
        resolved = resolve_style(mode="manual", style_id="premium_documentary")
        history = SelectionHistory()
        history.record(provider="pexels", asset_id="x1", title="mountain landscape aerial")
        history.record(provider="pexels", asset_id="x2", title="mountain valley landscape")
        ctx = build_selection_context(
            _scene(script_segment="Mountains shape the region.", prompt="mountain landscape"),
            resolved,
            history,
        )
        repeat = smart_selection_score(
            query="mountain landscape",
            title="mountain landscape aerial cinematic",
            description="landscape mountains valley",
            width=1920,
            height=1080,
            provider="pexels",
            asset_id="x3",
            context=ctx,
        )
        self.assertGreater(repeat.concept_repetition_penalty, 0)

    def test_provider_not_dominant(self):
        resolved = resolve_style(mode="manual", style_id="history_documentary")
        ctx = build_selection_context(
            _scene(
                script_segment="Roman empire maps.",
                prompt="roman map",
            ),
            resolved,
        )
        off_topic_pexels = smart_selection_score(
            query="roman map",
            script_segment="Roman empire maps",
            title="random unrelated subject",
            width=1920,
            height=1080,
            provider="pexels",
            asset_id="p1",
            context=ctx,
        )
        on_topic_archive = smart_selection_score(
            query="roman map",
            script_segment="Roman empire maps",
            title="roman empire historical map document",
            width=960,
            height=640,
            provider="archive",
            asset_id="a1",
            is_archival=True,
            context=ctx,
        )
        self.assertGreater(on_topic_archive.relevance, off_topic_pexels.relevance)


class TestScoreBreakdown(unittest.TestCase):
    def test_final_selection_score_alias(self):
        b = ScoreBreakdown(relevance=2.0, quality=0.8, visual_role_score=0.5)
        self.assertEqual(b.final_selection_score, b.total)


if __name__ == "__main__":
    unittest.main()
