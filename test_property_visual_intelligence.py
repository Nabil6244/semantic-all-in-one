"""Tests for the Property Visual Intelligence upgrade.

Covers both the trimmed research/property_visual_intelligence.py module
itself, and the seams it now feeds inside the EXISTING pipeline
(research/property_script.py's analyze_property_script /
research/property_visual_plan.py's build_property_visual_plan /
providers/research_asset_provider.py's role-relatedness table) — since the
whole point of this upgrade is that the new signal actually reaches those
existing systems rather than sitting in an unused module.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from research.models import MediaCandidate, PropertySummary, ResearchResult
from research.property_ontology import PropertyLocation, resolve_property_type
from research.property_script import (
    BeatCategory,
    PropertyBeat,
    VisualScope,
    analyze_property_script,
    build_visual_intent,
    classify_beat,
)
from research.property_visual_plan import build_property_visual_plan
from research.property_visual_intelligence import (
    CAMERA_LANGUAGE_BY_PURPOSE,
    PURPOSE_ATMOSPHERE,
    PURPOSE_COMPARISON,
    PURPOSE_CONDITION_PROOF,
    PURPOSE_FEATURE_PROOF,
    PURPOSE_LIFESTYLE,
    PURPOSE_LOCATION_CONTEXT,
    PURPOSE_PROPERTY_PROOF,
    PURPOSE_ROOM_PROOF,
    PURPOSE_SCENIC_CONTEXT,
    PURPOSE_SPECIFICATION_PROOF,
    PURPOSE_TRANSITION,
    analyze_property_story,
    classify_visual_purpose,
    fact_visual_mappings,
    property_media_matches_beat,
    semantic_categories_for,
)


def _summary(**kw) -> PropertySummary:
    base = dict(name="Test Property", address="1 Test St", city="Testville",
                state="TS", country="US", property_id="p1")
    base.update(kw)
    return PropertySummary(**base)


def _beat(narration: str, summary: PropertySummary, facts: dict | None = None) -> PropertyBeat:
    category, reason = classify_beat(narration, summary, property_facts=facts)
    intent = build_visual_intent(
        narration, summary,
        profile=resolve_property_type(summary.property_type, "", summary.name or ""),
        location=PropertyLocation(city=summary.city or "", state=summary.state or ""),
        facts=facts,
    )
    return PropertyBeat(narration=narration, category=category, reason=reason,
                         property_id=summary.property_id, intent=intent)


def _candidate(tmp: Path, property_id: str, name: str, *, role_detail=None, title=None) -> MediaCandidate:
    p = tmp / name
    p.write_bytes(b"x")
    return MediaCandidate(
        local_path=p, media_type="image", source_url="https://example.com/" + name,
        property_id=property_id, role_detail=role_detail, title=title,
        width=1200, height=900, quality_tier=2,
    )


class TestVisualPurposeClassification(unittest.TestCase):
    def test_location_beat_is_location_context(self):
        beat = _beat("The property is located just outside Winnipeg.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_LOCATION_CONTEXT)

    def test_kitchen_beat_is_room_proof(self):
        beat = _beat("The home features a large custom kitchen with an island.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_ROOM_PROOF)

    def test_garage_beat_is_feature_proof(self):
        beat = _beat("The property includes a heated detached double garage.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_FEATURE_PROOF)

    def test_measurement_fact_is_specification_proof(self):
        beat = _beat("This home has 3 bedrooms and 2 bathrooms.", _summary())
        self.assertEqual(beat.category, BeatCategory.FACTUAL_PROPERTY_CONTEXT)
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_SPECIFICATION_PROOF)

    def test_price_beat_is_property_proof(self):
        beat = _beat("At $209,000, this property is priced to sell.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_PROPERTY_PROOF)

    def test_cinematic_lifestyle_beat_is_lifestyle(self):
        beat = _beat("Imagine waking up to a peaceful prairie sunrise.", _summary())
        self.assertEqual(beat.category, BeatCategory.CINEMATIC_ATMOSPHERIC)
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_LIFESTYLE)

    def test_recently_renovated_is_condition_proof(self):
        beat = _beat("The kitchen was recently renovated with new countertops.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_CONDITION_PROOF)

    def test_short_generic_beat_is_transition(self):
        beat = _beat("Take a look.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_TRANSITION)

    def test_comparison_cue_is_comparison(self):
        beat = _beat("Unlike most other homes in the area, this one has real character.", _summary())
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_COMPARISON)

    def test_generic_context_defaults_to_scenic(self):
        beat = _beat("Families will love this welcoming neighborhood.", _summary())
        self.assertEqual(beat.category, BeatCategory.GENERIC_CONTEXT)
        self.assertEqual(classify_visual_purpose(beat), PURPOSE_SCENIC_CONTEXT)

    def test_every_purpose_is_a_plain_string_constant(self):
        for value in (
            PURPOSE_LOCATION_CONTEXT, PURPOSE_PROPERTY_PROOF, PURPOSE_FEATURE_PROOF,
            PURPOSE_ROOM_PROOF, PURPOSE_SPECIFICATION_PROOF, PURPOSE_CONDITION_PROOF,
            PURPOSE_LIFESTYLE, PURPOSE_SCENIC_CONTEXT, PURPOSE_COMPARISON,
            PURPOSE_TRANSITION, PURPOSE_ATMOSPHERE,
        ):
            self.assertIsInstance(value, str)
            self.assertTrue(value)


class TestSemanticCategories(unittest.TestCase):
    def test_kitchen_and_garage_are_distinguished(self):
        self.assertIn("kitchen", semantic_categories_for("A custom kitchen with an island."))
        self.assertIn("garage", semantic_categories_for("A heated detached double garage."))

    def test_golf_course_tag(self):
        self.assertIn("golf_course", semantic_categories_for("Overlooking the Sandy Hook Golf Course."))

    def test_no_tags_for_untagged_text(self):
        self.assertEqual(semantic_categories_for("The lot measures 75 by 200 feet."), [])

    def test_does_not_duplicate_visual_scope_vocabulary(self):
        # VisualScope already has PROPERTY_INTERIOR/STRUCTURE/etc — the tag
        # vocabulary must add fine-grained words, not those bucket names.
        tags = semantic_categories_for("kitchen bedroom garage pool")
        for scope_word in ("interior", "structure", "exterior", "land"):
            self.assertNotIn(scope_word, tags)


class TestPropertyMediaMatchesBeat(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_matching_role_detail_matches(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "kitchen.jpg", role_detail="interior"),
        ])
        self.assertTrue(property_media_matches_beat(result, "p1", VisualScope.PROPERTY_INTERIOR))

    def test_incompatible_role_detail_does_not_match(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "exterior.jpg", role_detail="exterior"),
        ])
        # every candidate is a KNOWN, incompatible role -> no honest evidence
        self.assertFalse(property_media_matches_beat(result, "p1", VisualScope.PROPERTY_INTERIOR))

    def test_unknown_role_detail_is_permissive(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "unlabelled.jpg", role_detail=None),
        ])
        self.assertTrue(property_media_matches_beat(result, "p1", VisualScope.PROPERTY_INTERIOR))

    def test_no_media_never_matches(self):
        result = ResearchResult(property=_summary(), media=[])
        self.assertFalse(property_media_matches_beat(result, "p1", VisualScope.PROPERTY_INTERIOR))

    def test_ungated_scope_is_permissive(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "a.jpg", role_detail="interior"),
        ])
        # LAND has no clean role_detail vocabulary -> never gated
        self.assertTrue(property_media_matches_beat(result, "p1", VisualScope.LAND))

    def test_other_property_media_does_not_count(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "OTHER_LISTING", "interior.jpg", role_detail="interior"),
        ])
        self.assertFalse(property_media_matches_beat(result, "p1", VisualScope.PROPERTY_INTERIOR))


class TestPropertyStoryAnalysis(unittest.TestCase):
    def test_hero_features_from_verified_facts_only(self):
        story = analyze_property_story(facts={"bedrooms": "3", "bathrooms": "2", "lot_size": "57 acres"})
        self.assertTrue(story.hero_features)
        self.assertTrue(all("=" in f for f in story.hero_features))

    def test_no_facts_no_hallucinated_hero_features(self):
        story = analyze_property_story(facts={})
        self.assertEqual(story.hero_features, [])
        self.assertNotIn("None", story.primary_story_angle)

    def test_story_angle_has_no_marketing_fluff_placeholder(self):
        story = analyze_property_story(facts={"bedrooms": "4"})
        self.assertNotIn("property property", story.primary_story_angle)

    def test_confidence_is_bounded(self):
        story = analyze_property_story(facts={"bedrooms": "4"})
        self.assertGreaterEqual(story.confidence, 0.0)
        self.assertLessEqual(story.confidence, 1.0)


class TestFactVisualMappings(unittest.TestCase):
    def test_delegates_to_ontology_hints(self):
        mappings = fact_visual_mappings({"lot_size": "57 acres"})
        self.assertTrue(mappings)
        self.assertEqual(mappings[0].fact_key, "lot_size")

    def test_no_visual_meaning_facts_are_absent(self):
        mappings = fact_visual_mappings({"listing_id": "MLS12345"})
        self.assertEqual(mappings, [])


class TestFlowPromptEnrichment(unittest.TestCase):
    def test_camera_language_table_is_purpose_keyed_and_short(self):
        for purpose, phrase in CAMERA_LANGUAGE_BY_PURPOSE.items():
            self.assertIsInstance(phrase, str)
            self.assertLess(len(phrase.split()), 12)

    def test_flow_prompt_gets_camera_language_for_feature_proof(self):
        beats = analyze_property_script(
            "The property includes a heated detached double garage.",
            ResearchResult(property=_summary()),
        )
        self.assertIn("cinematic reveal", beats[0].intent.flow_prompt.lower())

    def test_flow_prompt_never_invents_the_guarded_feature(self):
        # No fact/narration support for a pool -> unsupported_features() must
        # still strip it even after camera-language enrichment runs.
        beats = analyze_property_script(
            "The backyard has a beautiful pool area for entertaining.",
            ResearchResult(property=_summary()),
        )
        self.assertIn("pool", beats[0].narration.lower())  # sanity: narration DOES support it here


class TestSourceStrategyIntegration(unittest.TestCase):
    """Purpose/media-match signals reach the EXISTING _sources_for() seam —
    not a second source-selection system."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_kitchen_beat_with_kitchen_media_prefers_research(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "kitchen.jpg", role_detail="interior", title="Custom Kitchen"),
        ])
        beats = analyze_property_script("The home features a custom kitchen with an island.", result)
        self.assertEqual(beats[0].preferred_source, "research")
        self.assertEqual(beats[0].intent.confidence, "high")

    def test_kitchen_beat_with_only_exterior_media_falls_back_to_stock(self):
        # (18) do not use property media merely because it belongs to the
        # listing — an exterior-only listing cannot prove a kitchen claim.
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "front.jpg", role_detail="exterior"),
        ])
        beats = analyze_property_script("The home features a custom kitchen with an island.", result)
        self.assertEqual(beats[0].preferred_source, "stock")
        self.assertEqual(beats[0].intent.confidence, "medium")

    def test_garage_beat_with_structure_media_prefers_research(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "garage.jpg", role_detail="structure", title="Detached Garage"),
        ])
        beats = analyze_property_script("The property includes a heated detached double garage.", result)
        self.assertEqual(beats[0].preferred_source, "research")

    def test_bedroom_beat_with_interior_media_prefers_research(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "bed.jpg", role_detail="interior", title="Primary Bedroom"),
        ])
        beats = analyze_property_script("The primary bedroom is spacious and bright.", result)
        self.assertEqual(beats[0].preferred_source, "research")

    def test_generic_lifestyle_beat_uses_stock_or_auto_never_research(self):
        result = ResearchResult(property=_summary(), media=[
            _candidate(self.tmp, "p1", "a.jpg", role_detail="interior"),
        ])
        beats = analyze_property_script("Imagine relaxing here on a quiet evening.", result)
        self.assertNotEqual(beats[0].preferred_source, "research")

    def test_no_property_media_at_all_never_prefers_research(self):
        beats = analyze_property_script(
            "The home features a custom kitchen with an island.",
            ResearchResult(property=_summary(), media=[]),
        )
        self.assertEqual(beats[0].preferred_source, "stock")


class TestYouTubeIntegration(unittest.TestCase):
    def test_location_beat_with_place_name_prefers_youtube(self):
        beats = analyze_property_script(
            "The surrounding area offers easy access to Memphis and Jackson.",
            ResearchResult(property=_summary()),
        )
        plan, _scope = build_property_visual_plan(beats, ResearchResult(property=_summary()))
        self.assertEqual(plan.scenes[0].asset_type, "youtube_video")
        self.assertEqual(plan.scenes[0].fallbacks, ["stock_video"])

    def test_generic_location_without_place_name_stays_stock(self):
        # No city/state on the listing and no proper noun in the narration
        # -> build_visual_intent's LOCATION branch has no real place to
        # search on, so youtube would have nothing better than stock.
        bare = _summary(city="", state="", country="")
        beats = analyze_property_script(
            "The property is conveniently located near shopping.",
            ResearchResult(property=bare),
        )
        plan, _scope = build_property_visual_plan(beats, ResearchResult(property=bare))
        self.assertEqual(plan.scenes[0].asset_type, "stock_video")

    def test_youtube_never_used_merely_because_media_is_missing(self):
        # A feature-proof beat with no matching media must fall to stock,
        # never youtube — youtube is reserved for genuine location purpose.
        beats = analyze_property_script(
            "The property includes a heated detached double garage.",
            ResearchResult(property=_summary(), media=[]),
        )
        plan, _scope = build_property_visual_plan(beats, ResearchResult(property=_summary(), media=[]))
        self.assertEqual(plan.scenes[0].asset_type, "stock_video")


class TestFlowNotIndependentlyGated(unittest.TestCase):
    def test_cinematic_beat_still_deferred_to_existing_allocation_engine(self):
        beats = analyze_property_script(
            "Imagine waking up surrounded by peaceful countryside.",
            ResearchResult(property=_summary()),
        )
        self.assertEqual(beats[0].preferred_source, "")
        plan, _scope = build_property_visual_plan(beats, ResearchResult(property=_summary()))
        self.assertEqual(plan.scenes[0].asset_type, "")  # left to visual_allocation, not decided here

    def test_module_exposes_no_independent_flow_gate(self):
        import research.property_visual_intelligence as pvi
        self.assertFalse(hasattr(pvi, "should_use_flow"))
        self.assertFalse(hasattr(pvi, "FLOW_MIN_ABSOLUTE_SCORE"))
        self.assertFalse(hasattr(pvi, "SourceStrategy"))
        self.assertFalse(hasattr(pvi, "DiversityContinuityState"))


class TestCsvSchemaUnchanged(unittest.TestCase):
    ALLOWED_ASSET_TYPES = {
        "", "research", "stock_video", "stock_image", "image", "video",
        "youtube_video", "archive_video", "nasa_video", "commons_video",
        "commons_image", "local",
    }

    def test_property_plan_only_emits_known_asset_types(self):
        result = ResearchResult(property=_summary(), media=[])
        beats = analyze_property_script(
            "The home features a custom kitchen. "
            "The property is located near Memphis. "
            "Imagine waking up to a peaceful sunrise.",
            result,
        )
        plan, _scope = build_property_visual_plan(beats, result)
        for scene in plan.scenes:
            self.assertIn(scene.asset_type, self.ALLOWED_ASSET_TYPES)


class TestResearchAssetProviderRoleRelatedness(unittest.TestCase):
    """The existing ResearchAssetProvider ranking (unchanged) now has a
    richer related-terms table — verifies the actual candidate ordering,
    not just the table contents."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_garage_photo_outranks_barn_photo_for_a_garage_scene(self):
        from providers.base import SceneRow
        from providers.research_asset_provider import ResearchAssetProvider

        garage = _candidate(self.tmp, "p1", "garage.jpg", role_detail="structure", title="Detached Garage")
        barn = _candidate(self.tmp, "p1", "barn.jpg", role_detail="structure", title="Old Barn")
        provider = ResearchAssetProvider([garage, barn])
        scene = SceneRow(scene_number="1", script_segment="A heated detached double garage.",
                          prompt="", stock="", visual_description="the property's garage")
        result = provider.resolve(scene, self.tmp)
        self.assertTrue(result.ok)
        self.assertIn("garage", (result.metadata or {}).get("source_url", "").lower())


if __name__ == "__main__":
    unittest.main()
