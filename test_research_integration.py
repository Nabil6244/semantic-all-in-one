#!/usr/bin/env python3
"""Focused tests for the research/ integration layer + ResearchAssetProvider +
AssetManager's new RESEARCH fallback — no network, no subprocess actually
invoked (mocked), no customtkinter UI exercised.

Run: python -m pytest test_research_integration.py -v
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
from providers.research_asset_provider import ResearchAssetProvider
from research.models import MediaCandidate, PropertySummary, ResearchResult, ResearchSettings
from research.package_importer import empty_result, load_research_result
from research.property_provider import PropertyResearchProvider


def _write_research_package(output_dir: Path, *, with_manifest: bool = True) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "media").mkdir(exist_ok=True)
    (output_dir / "metadata").mkdir(exist_ok=True)

    img1 = output_dir / "media" / "001.jpg"
    img1.write_bytes(b"fake-jpeg-bytes-1")
    img2 = output_dir / "media" / "002.jpg"
    img2.write_bytes(b"fake-jpeg-bytes-2")

    research_json = {
        "research_id": "research_test001",
        "property": {
            "identity": {
                "canonical_address": "30 County Road 41, Clio, AL, 36017, US",
                "property_name": "Hunters Ridge",
                "city": "Clio", "state": "AL", "country": "US",
            },
            "confidence": 0.94,
        },
        "sources": [{"source_id": "source_001", "source_url": "https://example.test/listing", "is_same_property": True}],
        "media": [],
    }
    (output_dir / "research.json").write_text(json.dumps(research_json), encoding="utf-8")

    if with_manifest:
        manifest = {
            "property": research_json["property"],
            "media": [
                {
                    "local_path": "media/001.jpg", "media_type": "image", "role": "exterior",
                    "source_url": "https://example.test/hero.jpg", "source_id": "source_001",
                    "property_match_score": 0.95, "relevance_score": 0.8, "script_relevance": 0.9,
                    "quality_score": 0.88, "width": 1884, "height": 1420,
                    "license_status": "restricted", "license_evidence": "© 2026",
                },
                {
                    "local_path": "media/002.jpg", "media_type": "image", "role": "kitchen",
                    "source_url": "https://example.test/kitchen.jpg", "source_id": "source_001",
                    "property_match_score": 0.7, "relevance_score": 0.3, "script_relevance": 0.2,
                    "quality_score": 0.5, "width": 1200, "height": 800,
                    "license_status": "unknown", "license_evidence": None,
                },
            ],
        }
        (output_dir / "metadata" / "media_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class PackageImporterTests(unittest.TestCase):
    """A. Property match / B. media contamination — the importer only ever
    surfaces what the engine already gated and put on disk; it never invents
    media or re-implements the property-match gate itself."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_loads_property_identity_and_media_from_manifest(self):
        _write_research_package(self.tmp)
        result = load_research_result(self.tmp)
        self.assertTrue(result.ok)
        self.assertEqual(result.property.name, "Hunters Ridge")
        self.assertEqual(result.property.city, "Clio")
        self.assertAlmostEqual(result.property.confidence, 0.94)
        self.assertEqual(len(result.media), 2)
        self.assertTrue(all(Path(m.local_path).is_file() for m in result.media))

    def test_missing_research_json_returns_empty_not_exception(self):
        result = load_research_result(self.tmp / "does_not_exist")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.media, [])

    def test_media_entries_pointing_at_missing_files_are_dropped(self):
        _write_research_package(self.tmp)
        # Simulate a manifest entry whose file never actually got downloaded.
        manifest_path = self.tmp / "metadata" / "media_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["media"].append({
            "local_path": "media/999.jpg", "media_type": "image", "role": "gallery",
            "source_url": "https://example.test/ghost.jpg", "property_match_score": 0.9,
            "quality_score": 0.9, "license_status": "unknown",
        })
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = load_research_result(self.tmp)
        # Only the two files that actually exist on disk are surfaced.
        self.assertEqual(len(result.media), 2)

    def test_falls_back_to_research_json_media_without_manifest(self):
        _write_research_package(self.tmp, with_manifest=False)
        # No manifest -> general (non-property) run shape; media[] in
        # research.json is empty in this fixture, so nothing is surfaced.
        result = load_research_result(self.tmp)
        self.assertTrue(result.ok)
        self.assertEqual(result.media, [])

    def test_empty_result_helper_marks_not_ok_only_with_error(self):
        self.assertFalse(empty_result(error="boom").ok)
        self.assertTrue(empty_result().ok)


class PropertyResearchProviderFailureTests(unittest.TestCase):
    """F. Research failure must never raise into the caller."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unconfigured_engine_path_returns_failed_result_not_exception(self):
        provider = PropertyResearchProvider(engine_root="", engine_python="")
        result = provider.research("some topic", output_dir=self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("not configured", result.error)

    def test_no_topic_script_or_url_returns_failed_result(self):
        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        result = provider.research("", output_dir=self.tmp)
        self.assertFalse(result.ok)

    def test_subprocess_exception_is_caught(self):
        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=OSError("no such file")):
            result = provider.research("Hunters Ridge Alabama", output_dir=self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("failed to run", result.error)

    def test_nonzero_exit_code_returns_failed_result(self):
        class FakeProc:
            returncode = 1
            stdout = ""
            stderr = "engine crashed"

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", return_value=FakeProc()):
            result = provider.research("Hunters Ridge Alabama", output_dir=self.tmp)
        self.assertFalse(result.ok)
        self.assertIn("engine crashed", result.error)

    def test_successful_run_loads_the_written_package(self):
        class FakeProc:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            # Simulate the engine writing its package into --output.
            output_dir = Path(cmd[cmd.index("--output") + 1])
            _write_research_package(output_dir)
            return FakeProc()

        provider = PropertyResearchProvider(engine_root=str(self.tmp), engine_python="python3")
        with patch("research.property_provider.hidden_subprocess.run", side_effect=fake_run):
            result = provider.research(
                "Hunters Ridge", urls=["https://example.test/listing"],
                domain="real_estate", output_dir=self.tmp / "out",
            )
        self.assertTrue(result.ok)
        self.assertEqual(len(result.media), 2)


class ResearchAssetProviderTests(unittest.TestCase):
    """B. Media contamination boundary + basic resolve() behavior."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images_dir = self.tmp / "images"
        self.images_dir.mkdir()
        self.media_dir = self.tmp / "media"
        self.media_dir.mkdir()
        self.photo = self.media_dir / "hero.jpg"
        self.photo.write_bytes(b"fake-bytes")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _candidate(self, **overrides):
        defaults = dict(
            local_path=self.photo, media_type="image", source_url="https://example.test/hero.jpg",
            title="Front exterior", role="exterior", property_match_score=0.9, script_relevance=0.8,
            quality_score=0.85, license_status="restricted", width=1200, height=800,
        )
        defaults.update(overrides)
        return MediaCandidate(**defaults)

    def test_no_candidates_fails_gracefully(self):
        provider = ResearchAssetProvider([])
        scene = SceneRow(scene_number="1", script_segment="The farmhouse exterior.")
        result = provider.resolve(scene, self.images_dir)
        self.assertFalse(result.ok)
        self.assertIn("No unused research media", result.error)

    def test_missing_file_on_disk_is_never_offered(self):
        ghost = self._candidate(local_path=self.tmp / "does_not_exist.jpg")
        provider = ResearchAssetProvider([ghost])
        scene = SceneRow(scene_number="1", script_segment="The farmhouse exterior.")
        result = provider.resolve(scene, self.images_dir)
        self.assertFalse(result.ok)

    def test_resolves_and_copies_file_into_images_dir(self):
        provider = ResearchAssetProvider([self._candidate()])
        scene = SceneRow(scene_number="7", script_segment="A view of the farmhouse exterior.")
        result = provider.resolve(scene, self.images_dir)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.RESEARCH)
        self.assertTrue(result.path.is_file())
        self.assertEqual(result.path.name, "007.jpg")

    def test_used_candidate_is_not_offered_again(self):
        candidate = self._candidate()
        provider = ResearchAssetProvider([candidate])
        scene1 = SceneRow(scene_number="1", script_segment="exterior")
        scene2 = SceneRow(scene_number="2", script_segment="exterior")
        r1 = provider.resolve(scene1, self.images_dir)
        r2 = provider.resolve(scene2, self.images_dir)
        self.assertTrue(r1.ok)
        self.assertFalse(r2.ok)  # only candidate was already consumed
        self.assertTrue(candidate.used)

    def test_has_unused_candidates_reflects_state(self):
        candidate = self._candidate()
        provider = ResearchAssetProvider([candidate])
        self.assertTrue(provider.has_unused_candidates())
        provider.resolve(SceneRow(scene_number="1", script_segment="x"), self.images_dir)
        self.assertFalse(provider.has_unused_candidates())


class AssetManagerResearchFallbackTests(unittest.TestCase):
    """C. Existing pipeline unaffected when research is disabled / available
    when enabled. D. Manual CSV authority always wins."""

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
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_research_disabled_classify_unchanged(self):
        mgr = AssetManager(self.images, log=lambda *_: None)  # research_provider=None (default)
        scene = SceneRow(scene_number="1", script_segment="no explicit asset_type")
        self.assertEqual(mgr.classify(scene), AssetSource.LOCAL)

    def test_research_enabled_fills_gap_when_csv_blank(self):
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="no explicit asset_type")
        self.assertEqual(mgr.classify(scene), AssetSource.RESEARCH)

    def test_manual_csv_authority_always_wins_over_research(self):
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="a", asset_type="image", prompt="a cinematic scene")
        # explicit asset_type must route to its own source, never RESEARCH
        self.assertEqual(mgr.classify(scene), AssetSource.FLOW_IMAGE)

    def test_manual_local_file_wins_over_research(self):
        # simulate a manually-placed file for scene 1
        (self.images / "001.jpg").write_bytes(b"manual")
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="no explicit asset_type")
        self.assertEqual(mgr.classify(scene), AssetSource.LOCAL)

    def test_research_provider_registered_in_provider_for(self):
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        self.assertIs(mgr._provider_for(AssetSource.RESEARCH), research_provider)

    def test_exhausted_research_falls_back_to_local(self):
        research_provider = ResearchAssetProvider([self.candidate])
        mgr = AssetManager(self.images, research_provider=research_provider, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x")
        self.assertEqual(mgr.classify(scene), AssetSource.RESEARCH)
        research_provider.resolve(scene, self.images)  # consume the only candidate
        self.assertEqual(mgr.classify(scene), AssetSource.LOCAL)


class BudgetIsolationTests(unittest.TestCase):
    """E. Research media must never consume Flow video-credit budget."""

    def test_budget_module_has_no_knowledge_of_research(self):
        import visual_allocation.budget as budget_module
        source = Path(budget_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RESEARCH", source)
        self.assertNotIn("research", source.lower())

    def test_asset_source_research_not_in_flow_related_sources(self):
        # Flow budget only ever reasons about FLOW_VIDEO/FLOW_IMAGE — confirm
        # the new enum member isn't accidentally aliased onto either.
        self.assertNotEqual(AssetSource.RESEARCH, AssetSource.FLOW_VIDEO)
        self.assertNotEqual(AssetSource.RESEARCH, AssetSource.FLOW_IMAGE)


class ResearchSettingsPersistenceTests(unittest.TestCase):
    def test_load_project_research_settings_defaults_when_missing(self):
        from research.settings import load_project_research_settings

        class FakeWorkspace:
            def read_meta(self):
                return {}

        settings = load_project_research_settings(FakeWorkspace())
        self.assertEqual(settings.topic, "")
        self.assertEqual(settings.domain, "auto")
        self.assertEqual(settings.max_media_per_property, 20)

    def test_save_and_load_roundtrip(self):
        from research.settings import load_project_research_settings, save_project_research_settings

        store = {}

        class FakeWorkspace:
            def read_meta(self):
                return dict(store)

            def to_dict(self):
                return {"project_id": "p1"}

            def _write_meta(self, data):
                store.clear()
                store.update(data)

        ws = FakeWorkspace()
        save_project_research_settings(ws, ResearchSettings(topic="Hunters Ridge", domain="real_estate", max_media_per_property=15))
        loaded = load_project_research_settings(ws)
        self.assertEqual(loaded.topic, "Hunters Ridge")
        self.assertEqual(loaded.domain, "real_estate")
        self.assertEqual(loaded.max_media_per_property, 15)

    def test_engine_config_roundtrip(self):
        from research.settings import load_engine_config, with_engine_config

        settings = with_engine_config({}, "/path/to/engine", "/path/to/python")
        root, python_path = load_engine_config(settings)
        self.assertEqual(root, "/path/to/engine")
        self.assertEqual(python_path, "/path/to/python")


if __name__ == "__main__":
    unittest.main()
