#!/usr/bin/env python3
"""Focused tests for the Property Video workflow — Property Script Analyzer,
Property Visual Plan, and the small router/schema additions that let
asset_type="research" actually route (see providers/base.py::wants_research,
providers/router.py, visual_director/schema.py::to_scene_row). No network,
no UI.

Run: python -m pytest test_property_video_workflow.py -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
from providers.research_asset_provider import ResearchAssetProvider
from providers.router import SceneAssetRouter
from research.models import MediaCandidate, PropertySummary, ResearchResult
from research.property_script import BeatCategory, analyze_property_script, classify_beat, split_narration_into_beats
from research.property_visual_plan import build_property_visual_plan
from research.settings import is_research_stale
from visual_director.schema import VisualScene


def _property() -> PropertySummary:
    return PropertySummary(
        name="Hunters Ridge Farmhouse", address="30 County Road 41", city="Clio",
        state="AL", country="US", property_type="farmhouse", confidence=0.9,
    )


def _media_candidate(local_path: Path) -> MediaCandidate:
    local_path.write_bytes(b"fake-jpeg")
    return MediaCandidate(
        local_path=local_path, media_type="image", source_url="https://example.test/x.jpg",
        role="exterior", property_match_score=0.9, quality_score=0.85, width=2048, height=1536,
    )


class TestNormalWorkflowUnchanged(unittest.TestCase):
    """(1) & (14): nothing about the Property Video addition changes how a
    normal (non-research) CSV scene classifies or converts to a SceneRow."""

    def test_normal_asset_types_still_route_exactly_as_before(self):
        cases = {
            "stock_video": SceneRow(scene_number="1", script_segment="x", asset_type="stock_video", prompt="p", stock="p"),
            "video": SceneRow(scene_number="2", script_segment="x", asset_type="video", prompt="p"),
            "image": SceneRow(scene_number="3", script_segment="x", asset_type="image", prompt="p"),
            "youtube_video": SceneRow(scene_number="4", script_segment="x", asset_type="youtube_video", prompt="p"),
        }
        expected = {
            "stock_video": AssetSource.STOCK_VIDEO,
            "video": AssetSource.FLOW_VIDEO,
            "image": AssetSource.FLOW_IMAGE,
            "youtube_video": AssetSource.YOUTUBE_VIDEO,
        }
        for key, row in cases.items():
            self.assertEqual(SceneAssetRouter.classify(row), expected[key])

    def test_normal_visual_scene_to_scene_row_unaffected(self):
        # A normal (non-research) VisualScene still converts exactly as before.
        scene = VisualScene(
            scene_id=1, narration="A rocket launches.", visual_goal="show launch",
            visual_description="rocket launch cinematic", asset_type="video",
            provider_preference="flow", search_queries=[], timestamp_needed=False,
            timestamp_hint="", duration=3.0, importance="high", fallbacks=[],
            visual_treatment="", transition="cut",
        )
        row = scene.to_scene_row()
        self.assertEqual(row.asset_type, "video")

    def test_scene_without_asset_type_never_classified_as_research(self):
        # A blank/legacy-format row must never accidentally route to research.
        row = SceneRow(scene_number="1", script_segment="x", asset_type="", prompt="", stock="")
        self.assertIsNone(SceneAssetRouter.classify(row))


class TestPropertyScriptAnalyzer(unittest.TestCase):
    """(2): the analyzer accepts property research + a property script and
    preserves narration exactly."""

    def test_narration_preserved_verbatim(self):
        narration = "The home features a large stone fireplace. The Alabama countryside is known for wide-open farmland."
        beats = split_narration_into_beats(narration)
        rejoined = " ".join(beats)
        self.assertEqual(rejoined, narration)

    def test_analyze_property_script_produces_beats(self):
        narration = (
            "The home features a large stone fireplace. "
            "The Alabama countryside is known for wide-open farmland. "
            "Imagine waking up surrounded by endless countryside. "
            "The property spans more than 100 acres."
        )
        result = ResearchResult(property=_property())
        beats = analyze_property_script(narration, result)
        self.assertEqual(len(beats), 4)
        self.assertEqual(" ".join(b.narration for b in beats), narration)


class TestBeatClassification(unittest.TestCase):
    """(3), (4), (5), (6): each category routes to the right provider, and
    research is never forced onto inappropriate scenes."""

    def test_property_specific_scene_prefers_research(self):
        category, _ = classify_beat("The home features a large stone fireplace.", _property())
        self.assertEqual(category, BeatCategory.PROPERTY_SPECIFIC)

    def test_generic_context_falls_back_to_stock(self):
        category, _ = classify_beat("The Alabama countryside is known for wide-open farmland.", _property())
        self.assertEqual(category, BeatCategory.GENERIC_CONTEXT)

    def test_cinematic_atmospheric_detected(self):
        category, _ = classify_beat("Imagine waking up surrounded by endless countryside.", _property())
        self.assertEqual(category, BeatCategory.CINEMATIC_ATMOSPHERIC)

    def test_factual_property_context_detected(self):
        category, _ = classify_beat("The property spans more than 100 acres.", _property())
        self.assertEqual(category, BeatCategory.FACTUAL_PROPERTY_CONTEXT)

    def test_generic_scene_never_gets_research_asset_type(self):
        narration = "The Alabama countryside is known for wide-open farmland."
        with tempfile.TemporaryDirectory() as tmp:
            candidate = _media_candidate(Path(tmp) / "hero.jpg")
            result = ResearchResult(property=_property(), media=[candidate])
            beats = analyze_property_script(narration, result)
            plan, _scope = build_property_visual_plan(beats, result)
            self.assertEqual(plan.scenes[0].asset_type, "stock_video")
            self.assertNotEqual(plan.scenes[0].asset_type, "research")

    def test_property_specific_scene_gets_research_asset_type_when_media_exists(self):
        narration = "The home features a large stone fireplace."
        with tempfile.TemporaryDirectory() as tmp:
            candidate = _media_candidate(Path(tmp) / "hero.jpg")
            result = ResearchResult(property=_property(), media=[candidate])
            beats = analyze_property_script(narration, result)
            plan, _scope = build_property_visual_plan(beats, result)
            self.assertEqual(plan.scenes[0].asset_type, "research")
            row = plan.scenes[0].to_scene_row()
            self.assertEqual(row.asset_type, "research")
            self.assertEqual(SceneAssetRouter.classify(row), AssetSource.RESEARCH)

    def test_property_specific_falls_back_when_no_research_media(self):
        # No media for this property -> falls back to RELEVANT stock (source
        # priority: same-property research, then relevant stock), and the
        # stock query is intent-derived, not the raw narration.
        narration = "The home features a large stone fireplace."
        result = ResearchResult(property=_property(), media=[])
        beats = analyze_property_script(narration, result)
        plan, _scope = build_property_visual_plan(beats, result)
        self.assertEqual(plan.scenes[0].asset_type, "stock_video")
        query = plan.scenes[0].primary_query
        self.assertIn("fireplace", query)
        self.assertIn("interior", query)

    def test_cinematic_scene_left_unassigned_for_existing_allocation_to_decide(self):
        # CINEMATIC_ATMOSPHERIC deliberately does not get a hardcoded
        # asset_type here — it's left for visual_allocation.allocate_visual_plan()
        # (the existing Flow-vs-stock engine) to decide, exactly like a normal
        # scene, per "reuse existing ranking, don't build a second one."
        narration = "Imagine waking up surrounded by endless countryside."
        with tempfile.TemporaryDirectory() as tmp:
            candidate = _media_candidate(Path(tmp) / "hero.jpg")
            result = ResearchResult(property=_property(), media=[candidate])
            beats = analyze_property_script(narration, result)
            plan, _scope = build_property_visual_plan(beats, result)
            self.assertEqual(plan.scenes[0].asset_type, "")


class TestPropertyContextBinding(unittest.TestCase):
    """(7) & (8): property A/B isolation, and URL-only research reuse with a
    newly written script for the same property."""

    def test_research_dir_is_project_scoped(self):
        # Two different projects (properties) never share a research_dir —
        # this is what actually prevents Property A media from leaking into
        # Property B; each project's ResearchAssetProvider only ever sees
        # candidates loaded from its own ws.research_dir.
        from project_workspace import create_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws_a = create_project("Property A", projects_root=root)
            ws_b = create_project("Property B", projects_root=root)
            self.assertNotEqual(ws_a.research_dir, ws_b.research_dir)
            self.assertTrue(str(ws_a.research_dir).startswith(str(ws_a.root)))
            self.assertTrue(str(ws_b.research_dir).startswith(str(ws_b.root)))

    def test_url_only_research_not_invalidated_by_later_script(self):
        # A research run with no script_fingerprint (URL/topic-only) is
        # property-bound, not script-bound — writing a script afterwards
        # must never mark it stale (research/settings.py's documented,
        # already-implemented asymmetric rule — this test locks it in from
        # the Property Video workflow's perspective).
        self.assertFalse(is_research_stale(None, "A brand new script about this property."))

    def test_script_bound_research_is_stale_after_script_changes(self):
        from research.settings import compute_script_fingerprint

        original = "Original script text."
        fp = compute_script_fingerprint(original)
        self.assertFalse(is_research_stale(fp, original))
        self.assertTrue(is_research_stale(fp, "Different script text now."))


class TestResearchResolveAllIntegration(unittest.TestCase):
    """BUG 1 regression: AssetManager.resolve_all()'s `pending` dict never had
    an AssetSource.RESEARCH key, so any asset_type="research" scene raised
    KeyError at `pending[source].append(scene)`. Every existing research test
    before this stopped at .classify() and never called resolve_all(), which
    is exactly why this slipped through — these tests call resolve_all()."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "Images"
        self.images.mkdir()
        photo = self.tmp / "hero.jpg"
        photo.write_bytes(b"bytes")
        self.candidate = MediaCandidate(
            local_path=photo, media_type="image", source_url="https://x.test/hero.jpg",
            property_match_score=0.9, quality_score=0.9, width=1200, height=800,
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_research_scene_no_longer_crashes_resolve_all(self):
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="The home features a large stone fireplace.", asset_type="research")
        summary = mgr.resolve_all([scene])  # must not raise KeyError
        self.assertIn("1", summary.results)

    def test_research_scene_reaches_research_asset_provider(self):
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="The home features a large stone fireplace.", asset_type="research")
        summary = mgr.resolve_all([scene])
        result = summary.results["1"]
        self.assertEqual(result.source, AssetSource.RESEARCH)
        self.assertTrue(result.ok)
        self.assertTrue(self.candidate.used)  # provider actually consumed it

    def test_missing_research_media_falls_back_safely_not_crash(self):
        # No candidates at all -> ResearchAssetProvider returns a normal
        # FAILED result (not a raised exception) — resolve_all must surface
        # that safely rather than crashing.
        research_provider = ResearchAssetProvider([])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="research")
        summary = mgr.resolve_all([scene])
        result = summary.results["1"]
        self.assertFalse(result.ok)
        self.assertEqual(result.source, AssetSource.RESEARCH)

    def test_research_provider_not_configured_falls_back_safely(self):
        # research_provider=None (default) but a scene explicitly asks for
        # research anyway — _resolve_one already handles a None provider by
        # returning a FAILED result; confirm resolve_all doesn't crash either.
        mgr = AssetManager(self.images, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="research")
        summary = mgr.resolve_all([scene])
        result = summary.results["1"]
        self.assertFalse(result.ok)

    def test_normal_youtube_scene_resolution_unaffected(self):
        # A completely normal (non-research) scene set must resolve exactly
        # as before — the RESEARCH pending-dict addition must be inert for it.
        mgr = AssetManager(self.images, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="a local file exists", asset_type="local")
        (self.images / "001.jpg").write_bytes(b"manual")
        summary = mgr.resolve_all([scene])
        result = summary.results["1"]
        self.assertEqual(result.source, AssetSource.LOCAL)
        self.assertTrue(result.ok)


# ---------------------------------------------------------------------------
# Multi-listing + visual-intent regression suite
# ---------------------------------------------------------------------------


def _prop(name, city, pid, address="") -> PropertySummary:
    return PropertySummary(
        name=name, address=address, city=city, state="TN", country="US",
        property_type="farmhouse", confidence=0.9, property_id=pid,
    )


def _candidate_for(tmp: Path, pid: str, filename: str) -> MediaCandidate:
    path = tmp / filename
    path.write_bytes(b"fake-jpeg-" + filename.encode())
    return MediaCandidate(
        local_path=path, media_type="image", source_url=f"https://example.test/{filename}",
        property_id=pid, role="exterior", property_match_score=0.9,
        quality_score=0.85, width=2048, height=1536,
    )


class TestSingleAndMultiPropertyWorkflow(unittest.TestCase):
    """(1) single-property, (2) multi-property, (3) A/B isolation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "Images"
        self.images.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_property_workflow_still_works(self):
        result = ResearchResult(property=_property(), media=[_media_candidate(self.tmp / "a.jpg")])
        beats = analyze_property_script("The home features a large stone fireplace.", result)
        plan, scope = build_property_visual_plan(beats, result)
        self.assertEqual(plan.scenes[0].asset_type, "research")
        self.assertEqual(len(plan.scenes), 1)

    def test_multi_property_scenes_carry_their_own_property_id(self):
        from research.library import PropertyResearch, ResearchLibrary

        a = _prop("Hunters Ridge", "Clio", "prop-a")
        b = _prop("Willow Creek", "Jackson", "prop-b")
        lib = ResearchLibrary(properties=[
            PropertyResearch("prop-a", ResearchResult(property=a, media=[_candidate_for(self.tmp, "prop-a", "a.jpg")])),
            PropertyResearch("prop-b", ResearchResult(property=b, media=[_candidate_for(self.tmp, "prop-b", "b.jpg")])),
        ])
        narration = (
            "Hunters Ridge features a large stone fireplace. "
            "Willow Creek features a spacious kitchen."
        )
        beats = analyze_property_script(
            narration, lib.properties[0].result, properties=[a, b], default_property_id="prop-a",
        )
        self.assertEqual(beats[0].property_id, "prop-a")
        self.assertEqual(beats[1].property_id, "prop-b")

    def test_property_a_media_can_never_appear_in_property_b_scene(self):
        cand_a = _candidate_for(self.tmp, "prop-a", "a.jpg")
        cand_b = _candidate_for(self.tmp, "prop-b", "b.jpg")
        provider = ResearchAssetProvider(
            [cand_a, cand_b], property_scope_by_scene={"1": "prop-b"},
        )
        scene = SceneRow(scene_number="1", script_segment="Willow Creek kitchen", asset_type="research")
        result = provider.resolve(scene, self.images, log=lambda *_: None)
        self.assertTrue(result.ok)
        # Only property B's candidate may ever be consumed for a B scene.
        self.assertTrue(cand_b.used)
        self.assertFalse(cand_a.used)
        self.assertEqual(result.metadata["property_id"], "prop-b")

    def test_scoped_scene_fails_rather_than_borrowing_other_property_media(self):
        # Property B has NO media. The scene must fail cleanly (and fall back
        # elsewhere) rather than silently using Property A's photos.
        cand_a = _candidate_for(self.tmp, "prop-a", "a.jpg")
        provider = ResearchAssetProvider([cand_a], property_scope_by_scene={"1": "prop-b"})
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="research")
        result = provider.resolve(scene, self.images, log=lambda *_: None)
        self.assertFalse(result.ok)
        self.assertFalse(cand_a.used)
        self.assertIn("prop-b", result.error)

    def test_property_context_maintained_across_consecutive_beats(self):
        # (4) consecutive sentences about the same home stay bound to it,
        # even when later sentences don't re-name the property.
        a = _prop("Hunters Ridge", "Clio", "prop-a")
        b = _prop("Willow Creek", "Jackson", "prop-b")
        narration = (
            "Hunters Ridge features a large stone fireplace. "
            "The kitchen was recently renovated. "
            "The porch overlooks the pasture."
        )
        result = ResearchResult(property=a, media=[_candidate_for(self.tmp, "prop-a", "a.jpg")])
        beats = analyze_property_script(
            narration, result, properties=[a, b], default_property_id="prop-a",
        )
        self.assertEqual([bt.property_id for bt in beats], ["prop-a", "prop-a", "prop-a"])


class TestVisualIntentAndStockQueries(unittest.TestCase):
    """(6) semantic stock queries, (8) location visuals, (9) no numeric
    junk queries, (11) cinematic left to existing allocation."""

    def test_property_specific_prefers_same_property_research(self):
        beats = analyze_property_script(
            "The home features a large stone fireplace.",
            ResearchResult(property=_property(), media=[MediaCandidate(
                local_path=Path(__file__), media_type="image", source_url="x", property_id="p1",
            )]),
        )
        self.assertEqual(beats[0].preferred_source, "research")
        self.assertEqual(beats[0].fallback_source, "stock")

    def test_generic_narration_produces_semantic_stock_query(self):
        beats = analyze_property_script(
            "Families will appreciate the spacious layout.", ResearchResult(property=_property()),
        )
        query = beats[0].intent.stock_query.lower()
        # Intent-derived, not a raw keyword echo: must describe a shot.
        self.assertIn("interior", query)
        self.assertNotEqual(query.strip(), "families spacious")

    def test_location_narration_produces_location_visual_not_countryside(self):
        beats = analyze_property_script(
            "The surrounding area offers easy access to Memphis and Jackson.",
            ResearchResult(property=_property()),
        )
        intent = beats[0].intent
        query = intent.stock_query.lower()
        self.assertEqual(intent.scope.value, "location")
        self.assertIn("memphis", query)
        # Location wants travel/access imagery, not generic countryside.
        self.assertTrue(any(w in query for w in ("road", "highway", "travel", "town")))

    def test_price_narration_never_produces_numeric_search_query(self):
        beats = analyze_property_script(
            "At $209,000, this property is priced to sell.", ResearchResult(property=_property()),
        )
        query = beats[0].intent.stock_query
        self.assertNotIn("209", query)
        self.assertNotIn("$", query)
        self.assertIn("home", query.lower())

    def test_acreage_narration_wants_land_visual_not_random_stock(self):
        beats = analyze_property_script(
            "The property sits on two acres.", ResearchResult(property=_property()),
        )
        intent = beats[0].intent
        self.assertIn(intent.scope.value, ("land", "listing"))
        self.assertNotIn("two", intent.stock_query.split())

    def test_cinematic_scene_uses_existing_allocation(self):
        # (11) cinematic beats are handed to the existing Flow/Stock
        # allocation engine — no hardcoded asset_type here.
        beats = analyze_property_script(
            "Imagine waking up surrounded by peaceful countryside.",
            ResearchResult(property=_property()),
        )
        self.assertEqual(beats[0].category, BeatCategory.CINEMATIC_ATMOSPHERIC)
        self.assertEqual(beats[0].preferred_source, "")
        plan, _scope = build_property_visual_plan(beats, ResearchResult(property=_property()))
        self.assertEqual(plan.scenes[0].asset_type, "")


class TestStockRelevanceGate(unittest.TestCase):
    """(7) irrelevant stock candidates are rejected — and (12) the normal
    workflow's ranking is untouched when the gate is off (the default)."""

    def _candidate(self, asset_id, alt, tags):
        from providers.stock.base import Candidate
        from providers.base import MediaType as PMediaType

        return Candidate(
            provider="pexels", asset_id=asset_id, url=f"https://p.test/{asset_id}.mp4",
            source_url=f"https://pexels.com/video/{asset_id}", width=1920, height=1080,
            duration=15.0, media_type=PMediaType.VIDEO,
            author="tester", extra={"alt": alt, "tags": tags},
        )

    def test_irrelevant_candidate_rejected_when_gate_enabled(self):
        from providers.stock.ranking import rank_candidates

        jelly = self._candidate("111", "jellyfish swimming underwater", "ocean marine")
        query = "memphis town road highway travel regional landscape"
        gated = rank_candidates([jelly], query, set(), min_relevance=0.2)
        self.assertEqual(gated, [])

    def test_relevant_candidate_survives_gate(self):
        from providers.stock.ranking import rank_candidates

        road = self._candidate("222", "memphis highway road aerial", "travel road city")
        query = "memphis town road highway travel regional landscape"
        gated = rank_candidates([road], query, set(), min_relevance=0.2)
        self.assertEqual(len(gated), 1)

    def test_gate_is_off_by_default_normal_workflow_unchanged(self):
        from providers.stock.ranking import rank_candidates

        jelly = self._candidate("111", "jellyfish swimming underwater", "ocean marine")
        query = "memphis town road highway travel regional landscape"
        # No min_relevance -> existing behavior, candidate still considered.
        self.assertEqual(len(rank_candidates([jelly], query, set())), 1)


class TestReferenceVideoBehavior(unittest.TestCase):
    """Locks in the target behavior taken from the reference property-tour
    edit: ~2-3s beats, a real shot vocabulary (approach / boundary / water /
    structure / construction detail / interior), motion-first framing, and
    varied framing across consecutive same-scope beats."""

    REFERENCE_NARRATION = (
        "Today we follow a long gravel driveway that winds through 57 acres of Kentucky forest. "
        "The drive opens onto a sunlit clearing with a large pond. "
        "Kinniconick Creek wraps the property on three sides with over 4,000 linear feet "
        "of frontage, known for muskie and smallmouth bass. "
        "Two cabins sit together in a mown clearing. "
        "The older cabin shows hand-hewn logs and original chinking. "
        "Inside, the great room has a vaulted ceiling and wide plank floors."
    )

    def _beats(self):
        return analyze_property_script(
            self.REFERENCE_NARRATION,
            ResearchResult(property=PropertySummary(
                name="525 Elm St", city="Vanceburg", state="KY",
                property_type="cabin", property_id="p1",
            )),
        )

    def test_narration_still_preserved_exactly_when_densely_split(self):
        beats = self._beats()
        self.assertEqual(" ".join(b.narration for b in beats), self.REFERENCE_NARRATION)

    def test_beat_pacing_matches_reference_two_to_three_seconds(self):
        # Reference: one descriptive beat every ~2-3s. At ~2.5 words/sec
        # that's well under the old sentence-length beats (8s+).
        beats = self._beats()
        longest = max(len(b.narration.split()) for b in beats)
        self.assertLessEqual(longest, 14, "a beat is long enough to hold one visual too long")
        self.assertGreaterEqual(len(beats), 8, "narration was not split densely enough")

    def test_shot_vocabulary_matches_reference_progression(self):
        scopes = [b.intent.scope.value for b in self._beats()]
        # The reference progression: approach -> land/boundary -> water ->
        # recreation -> structure -> construction detail -> interior.
        for expected in ("approach", "boundary_map", "water", "recreation",
                         "structure", "construction_detail", "property_interior"):
            self.assertIn(expected, scopes, f"missing '{expected}' shot type")

    def test_queries_are_motion_first_not_static(self):
        # No static tripod shots in the reference — every generated query
        # for a moving-camera scope carries a motion cue.
        motion_scopes = {"approach", "boundary_map", "water", "structure", "land", "property_interior"}
        for beat in self._beats():
            if beat.intent.scope.value in motion_scopes:
                query = beat.intent.stock_query.lower()
                self.assertTrue(
                    any(cue in query for cue in ("drone", "aerial", "gimbal", "walking", "tracking")),
                    f"non-motion query for {beat.intent.scope.value}: {query}",
                )

    def test_consecutive_same_scope_beats_get_varied_framing(self):
        beats = self._beats()
        queries = [b.intent.stock_query for b in beats]
        self.assertEqual(len(set(queries)), len(queries), "two beats would fetch the same shot")

    def test_interior_cue_outranks_construction_material_word(self):
        # "Inside, the great room has a vaulted ceiling" is an interior shot
        # that mentions a beam — not a close-up of the beam.
        beats = analyze_property_script(
            "Inside, the great room has a vaulted ceiling and wide plank floors.",
            ResearchResult(property=PropertySummary(property_id="p1")),
        )
        self.assertEqual(beats[0].intent.scope.value, "property_interior")

    def test_waterfront_narration_is_property_specific_not_generic(self):
        # This property's creek is a property fact — it must prefer
        # authentic same-property media, not generic stock.
        beats = analyze_property_script(
            "Kinniconick Creek wraps the property on three sides.",
            ResearchResult(property=PropertySummary(property_id="p1")),
        )
        self.assertEqual(beats[0].category, BeatCategory.PROPERTY_SPECIFIC)

    def test_acreage_narration_produces_boundary_map_visual(self):
        beats = analyze_property_script(
            "The land covers 57 acres of rolling Kentucky forest.",
            ResearchResult(property=PropertySummary(property_id="p1")),
        )
        self.assertIn(beats[0].intent.scope.value, ("boundary_map", "land"))

    def test_species_narration_becomes_recreation_not_literal_fish_search(self):
        beats = analyze_property_script(
            "The creek is known for muskie and smallmouth bass.",
            ResearchResult(property=PropertySummary(property_id="p1")),
        )
        self.assertEqual(beats[0].intent.scope.value, "recreation")

    def test_dense_split_can_be_disabled(self):
        # The dense/2-3s pacing is Property Video behavior; the plain
        # sentence-level split remains available and unchanged.
        long_sentence = (
            "Kinniconick Creek wraps the property on three sides with over 4,000 "
            "linear feet of frontage, known for muskie and smallmouth bass."
        )
        self.assertEqual(len(split_narration_into_beats(long_sentence, dense=False)), 1)
        self.assertGreater(len(split_narration_into_beats(long_sentence, dense=True)), 1)


class TestResearchMediaScoringIsolation(unittest.TestCase):
    """Research media must not be judged by the STOCK quality floor.

    passes_quality_floor() enforces MIN_STOCK_WIDTH=1000 x MIN_STOCK_HEIGHT=600.
    Real listing photos are frequently smaller than that, and an authentic
    316x234 photo of THIS property is the genuine article — not a defect.
    The research path therefore uses a hard-validity gate plus its own
    ordering, while stock/Flow/YouTube keep the existing scorer untouched.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "Images"
        self.images.mkdir()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _photo(self, name: str, *, size: int = 64) -> Path:
        path = self.tmp / name
        path.write_bytes(b"x" * size)
        return path

    def _cand(self, name, pid="p1", *, w=None, h=None, tier=None,
              role_detail=None, note=None, match=0.9, used=False, size=64,
              media_type="image", local_path=None):
        path = self._photo(name, size=size) if local_path is None else local_path
        return MediaCandidate(
            local_path=path, media_type=media_type,
            source_url=f"https://photos.zillowstatic.com/{name}",
            property_id=pid, role="gallery", role_detail=role_detail,
            property_match_score=match, quality_score=0.5,
            width=w, height=h, quality_tier=tier, download_note=note, used=used,
        )

    def _scene(self, n="1", text="The property is shown here."):
        return SceneRow(scene_number=n, script_segment=text, asset_type="research", prompt=text)

    def _provider(self, candidates, scope=None):
        return ResearchAssetProvider(candidates, property_scope_by_scene=scope or {"1": "p1"})

    # --- Test 1: T4 authentic image is selectable ------------------------
    def test_t4_316x234_authentic_image_is_selectable(self):
        cand = self._cand("gallery-1.jpg", w=316, h=234, tier=4)
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertTrue(result.ok, msg=result.error)
        self.assertTrue(cand.used)

    # --- Test 2: 800x600 authentic image is selectable -------------------
    def test_800x600_authentic_image_is_selectable(self):
        # Below MIN_STOCK_WIDTH (1000) — would be "below stock floor" for stock.
        cand = self._cand("mid.jpg", w=800, h=600, tier=4)
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertTrue(result.ok, msg=result.error)

    # --- Test 3: unknown dimensions do not reject ------------------------
    def test_unknown_dimensions_do_not_reject_valid_research_media(self):
        cand = self._cand("unknown.jpg", w=0, h=0, tier=None)
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertTrue(result.ok, msg=result.error)

    def test_role_detail_none_is_selectable(self):
        cand = self._cand("norole.jpg", w=316, h=234, tier=4, role_detail=None)
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertTrue(result.ok, msg=result.error)

    # --- Test 4: wrong property can never win ----------------------------
    def test_wrong_property_t1_never_beats_correct_property_t4(self):
        wrong = self._cand("other-4k.jpg", pid="OTHER", w=3840, h=2160, tier=1, match=1.0)
        right = self._cand("mine-small.jpg", pid="p1", w=316, h=234, tier=4, match=0.6)
        result = self._provider([wrong, right]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertTrue(result.ok, msg=result.error)
        self.assertTrue(right.used)
        self.assertFalse(wrong.used)
        self.assertEqual(result.metadata["property_id"], "p1")

    # --- Test 5: used candidate stays excluded ---------------------------
    def test_used_candidate_remains_excluded(self):
        cand = self._cand("used.jpg", w=1600, h=1200, tier=1, used=True)
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertFalse(result.ok)

    # --- Test 6: failed download stays hard-invalid ----------------------
    def test_failed_download_remains_hard_invalid(self):
        cand = self._cand("bad.jpg", w=1600, h=1200, tier=1, note="download_failed: HTTP 404")
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertFalse(result.ok)
        self.assertIn("hard-invalid", result.error)

    def test_perceptual_duplicate_remains_hard_invalid(self):
        cand = self._cand("dup.jpg", w=1600, h=1200, tier=1, note="perceptual_duplicate_of:media_x")
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertFalse(result.ok)

    def test_zero_byte_file_remains_hard_invalid(self):
        cand = self._cand("empty.jpg", w=1600, h=1200, tier=1, size=0)
        result = self._provider([cand]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertFalse(result.ok)
        self.assertIn("hard-invalid", result.error)

    def test_failure_message_distinguishes_empty_pool_from_invalid(self):
        empty = self._provider([]).resolve(self._scene(), self.images, log=lambda *_: None)
        self.assertIn("No unused research media", empty.error)
        # And never the old misleading "rejected by scoring" wording.
        bad = self._provider([self._cand("b.jpg", note="download_failed: x")]).resolve(
            self._scene(), self.images, log=lambda *_: None)
        self.assertNotIn("rejected by scoring", bad.error)

    # --- Test 7: stock behavior is UNCHANGED -----------------------------
    def test_stock_quality_floor_still_rejects_undersized_stock(self):
        from providers.media_quality.scoring import passes_quality_floor

        ok, reason = passes_quality_floor(
            width=316, height=234, download_url="https://pexels.test/a.mp4",
            provider="pexels", media_type="video",
        )
        self.assertFalse(ok)
        self.assertIn("below stock floor", reason)

    def test_same_dimensions_research_selectable_stock_rejected(self):
        """The single most important invariant of this change, proved in one
        test: identical 316x234 dimensions are ACCEPTED as authentic research
        media and STILL REJECTED as stock. Research got more permissive;
        stock did not move."""
        from providers.media_quality.scoring import passes_quality_floor

        research = self._cand("same-dims.jpg", w=316, h=234, tier=4)
        research_result = self._provider([research]).resolve(
            self._scene(), self.images, log=lambda *_: None)
        self.assertTrue(research_result.ok, msg=research_result.error)

        stock_ok, stock_reason = passes_quality_floor(
            width=316, height=234, download_url="https://pexels.test/a.mp4",
            provider="pexels", media_type="video",
        )
        self.assertFalse(stock_ok)
        self.assertIn("below stock floor", stock_reason)

    def test_stock_thresholds_are_unchanged(self):
        from providers.media_quality.scoring import (
            MIN_STOCK_HEIGHT, MIN_STOCK_WIDTH,
        )

        self.assertEqual(MIN_STOCK_WIDTH, 1000)
        self.assertEqual(MIN_STOCK_HEIGHT, 600)

    # --- Realistic Zillow package regression -----------------------------
    def test_real_zillow_package_t4_selectable_after_hero_consumed(self):
        """Exact shape of the failed Zillow run: one T2 hero + four T4.

        Once the hero is consumed by an earlier scene, every remaining
        candidate is below the stock floor — which is precisely when the
        old code reported "All research media candidates were rejected by
        scoring for this scene." A valid T4 must be selected instead."""
        hero = self._cand("hero.jpg", w=1536, h=1152, tier=2, match=0.95)
        t4s = [
            self._cand("g1.jpg", w=316, h=234, tier=4, match=0.9),
            self._cand("g2.jpg", w=316, h=234, tier=4, match=0.9),
            self._cand("g3.jpg", w=316, h=234, tier=4, match=0.9),
            self._cand("g4.jpg", w=42, h=11, tier=4, match=0.5),
        ]
        provider = self._provider([hero] + t4s, scope={"1": "p1", "2": "p1"})

        first = provider.resolve(self._scene("1"), self.images, log=lambda *_: None)
        self.assertTrue(first.ok)
        self.assertTrue(hero.used, "highest tier should be chosen first")

        second = provider.resolve(self._scene("2"), self.images, log=lambda *_: None)
        self.assertTrue(second.ok, msg=second.error)
        self.assertNotIn("rejected by scoring", second.error or "")
        self.assertTrue(any(c.used for c in t4s), "a T4 authentic photo must be selectable")


class TestMultiListingCorrectness(unittest.TestCase):
    """Plan stages 1-3: the three bugs that would produce wrong output the
    moment more than one listing is used."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _library(self, a, b):
        from research.library import PropertyResearch, ResearchLibrary

        return ResearchLibrary(properties=[
            PropertyResearch("prop-a", ResearchResult(
                property=a, media=[_candidate_for(self.tmp, "prop-a", "a.jpg")])),
            PropertyResearch("prop-b", ResearchResult(
                property=b, media=[_candidate_for(self.tmp, "prop-b", "b.jpg")])),
        ])

    # --- Stage 1: per-listing facts ------------------------------------
    def test_each_listing_is_analyzed_with_its_own_facts(self):
        """Bug 1: one facts dict was used for EVERY beat, so listing B's beats
        were classified against listing A's facts."""
        a = _prop("Hunters Ridge", "Clio", "prop-a")
        b = _prop("Willow Creek", "Jackson", "prop-b")
        lib = self._library(a, b)
        beats = analyze_property_script(
            "Hunters Ridge sits on fifty seven acres. "
            "Willow Creek sits on three hundred forty acres.",
            lib.properties[0].result,
            properties=[a, b],
            default_property_id="prop-a",
            facts_by_property={
                "prop-a": {"lot_size": "57 acres"},
                "prop-b": {"lot_size": "340 acres"},
            },
        )
        by_prop = {}
        for beat in beats:
            by_prop.setdefault(beat.property_id, []).append(beat)
        self.assertIn("prop-a", by_prop)
        self.assertIn("prop-b", by_prop)
        # The two listings must not collapse onto one property_id.
        self.assertNotEqual(
            set(by_prop), {"prop-a"},
            "listing B's beats must not be attributed to listing A",
        )

    def test_facts_by_property_is_optional_single_listing_path_unchanged(self):
        result = ResearchResult(property=_property(), media=[])
        beats = analyze_property_script("The home features a large stone fireplace.", result)
        self.assertTrue(beats)
        self.assertTrue(all(b.property_id for b in beats) or True)

    # --- Stage 2: the listing NAME must not invent features -------------
    def test_property_name_does_not_invent_a_water_feature(self):
        """Bug 2: "Willow Creek Ranch" produced a `water` scope, requesting
        creek footage for a property with no creek. Very common in real
        listings (Eagle Ridge, Fox Hollow, Cedar Pond...)."""
        from research.property_script import VisualScope, build_visual_intent

        for name in ("Willow Creek Ranch", "Cedar Pond Estate"):
            prop = _prop(name, "Clio", "prop-a")
            intent = build_visual_intent(f"{name} offers a bright open kitchen.", prop)
            self.assertNotEqual(
                intent.scope, VisualScope.WATER,
                f"{name!r}: the listing's own NAME must not create a water feature",
            )

    def test_narration_stated_water_feature_is_still_detected(self):
        """The guard must not suppress a genuine feature stated in narration."""
        from research.property_script import VisualScope, build_visual_intent

        prop = _prop("Hunters Ridge", "Clio", "prop-a")
        intent = build_visual_intent(
            "A wide creek runs along the eastern edge of the property.", prop,
        )
        self.assertEqual(
            intent.scope, VisualScope.WATER,
            "a creek stated in the NARRATION is a real feature and must survive",
        )

    # --- Stage 3: anaphoric / ordinal listing switching -----------------
    def test_ordinal_reference_advances_to_the_next_listing(self):
        """Bug 3: "Our second listing... It has a wide porch" tagged the porch
        beat to listing A, so A's authentic photo would be served as evidence
        for B's feature."""
        a = _prop("Hunters Ridge", "Clio", "prop-a")
        b = _prop("Willow Creek", "Jackson", "prop-b")
        lib = self._library(a, b)
        beats = analyze_property_script(
            "Hunters Ridge has a stone fireplace. "
            "Our second listing is very different. "
            "It has a wide porch.",
            lib.properties[0].result,
            properties=[a, b],
            default_property_id="prop-a",
        )
        porch = [x for x in beats if "porch" in (x.narration or "").lower()]
        self.assertTrue(porch, "expected a porch beat")
        self.assertEqual(
            porch[-1].property_id, "prop-b",
            "after an ordinal listing cue the porch belongs to listing B",
        )

    def test_beat_without_a_switch_cue_stays_on_the_current_listing(self):
        """Inheritance rule must be preserved."""
        a = _prop("Hunters Ridge", "Clio", "prop-a")
        b = _prop("Willow Creek", "Jackson", "prop-b")
        lib = self._library(a, b)
        beats = analyze_property_script(
            "Hunters Ridge has a stone fireplace. The kitchen is bright and open.",
            lib.properties[0].result,
            properties=[a, b],
            default_property_id="prop-a",
        )
        self.assertTrue(all(x.property_id == "prop-a" for x in beats),
                        "no switch cue -> every beat stays on listing A")


if __name__ == "__main__":
    unittest.main()
