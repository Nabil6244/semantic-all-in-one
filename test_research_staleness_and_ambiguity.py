#!/usr/bin/env python3
"""Focused tests for:
- script-fingerprint staleness protection (research/settings.py +
  app.py::_build_research_provider)
- property_ambiguous surfacing through package_importer -> ResearchResult

Run: python -m pytest test_research_staleness_and_ambiguity.py -v
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.models import ResearchSettings
from research.package_importer import load_research_result
from research.settings import (
    compute_script_fingerprint,
    is_research_stale,
    load_project_research_settings,
    save_project_research_settings,
)


class FingerprintTests(unittest.TestCase):
    def test_same_text_same_fingerprint(self):
        a = compute_script_fingerprint("Hunters Ridge is a 116-acre farmhouse near Clio, Alabama.")
        b = compute_script_fingerprint("Hunters Ridge is a 116-acre farmhouse near Clio, Alabama.")
        self.assertEqual(a, b)

    def test_different_text_different_fingerprint(self):
        a = compute_script_fingerprint("Hunters Ridge is a 116-acre farmhouse.")
        b = compute_script_fingerprint("Hunters Ridge is a 200-acre farmhouse.")
        self.assertNotEqual(a, b)

    def test_trailing_whitespace_does_not_change_fingerprint(self):
        a = compute_script_fingerprint("Hunters Ridge farmhouse.")
        b = compute_script_fingerprint("Hunters Ridge farmhouse.\n\n  ")
        self.assertEqual(a, b)

    def test_empty_text_still_produces_a_fingerprint(self):
        self.assertTrue(compute_script_fingerprint(""))


class StalenessRuleTests(unittest.TestCase):
    def test_url_only_research_never_stale(self):
        # no stored fingerprint at all (URL/topic-only run) -> never stale,
        # regardless of what the current script says.
        self.assertFalse(is_research_stale(None, "a brand new script"))
        self.assertFalse(is_research_stale("", "a brand new script"))

    def test_script_bound_research_stale_on_mismatch(self):
        stored = compute_script_fingerprint("original script text")
        self.assertTrue(is_research_stale(stored, "a completely different script"))

    def test_script_bound_research_fresh_on_exact_match(self):
        stored = compute_script_fingerprint("original script text")
        self.assertFalse(is_research_stale(stored, "original script text"))

    def test_script_bound_research_fresh_despite_trailing_whitespace_edit(self):
        stored = compute_script_fingerprint("original script text")
        self.assertFalse(is_research_stale(stored, "original script text  \n"))


class SettingsRoundtripTests(unittest.TestCase):
    def test_script_fingerprint_roundtrips(self):
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
        fp = compute_script_fingerprint("some script")
        save_project_research_settings(ws, ResearchSettings(topic="x", script_fingerprint=fp))
        loaded = load_project_research_settings(ws)
        self.assertEqual(loaded.script_fingerprint, fp)

    def test_missing_fingerprint_loads_as_none(self):
        class FakeWorkspace:
            def read_meta(self):
                return {"research_media": {"topic": "x"}}  # no script_fingerprint key

        loaded = load_project_research_settings(FakeWorkspace())
        self.assertIsNone(loaded.script_fingerprint)


class BuildResearchProviderStalenessTests(unittest.TestCase):
    """Integration-level: exercises app.VideoGeneratorApp._build_research_provider
    directly against a real temp project layout, without the GUI."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.research_dir = self.tmp / "research"
        self.research_dir.mkdir()
        self.script_dir = self.tmp / "script"
        self.script_dir.mkdir()

        media_dir = self.research_dir / "media"
        media_dir.mkdir()
        photo = media_dir / "001.jpg"
        photo.write_bytes(b"fake-bytes")

        research_json = {
            "property": {"identity": {"property_name": "Hunters Ridge", "city": "Clio", "state": "AL"}, "confidence": 0.9},
            "sources": [],
            "media": [{"local_path": str(photo), "media_type": "image", "source_url": "https://x.test/a.jpg"}],
            "statistics": {"property_ambiguous": False},
        }
        (self.research_dir / "research.json").write_text(json.dumps(research_json), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_app_instance(self):
        import app as app_module

        instance = app_module.VideoGeneratorApp.__new__(app_module.VideoGeneratorApp)
        return instance

    def _fake_workspace(self, script_fingerprint):
        research_dir = self.research_dir
        script_path = self.script_dir / "narration.txt"

        class FakeWorkspace:
            def read_meta(self):
                return {"research_media": {"script_fingerprint": script_fingerprint}} if script_fingerprint else {}

        ws = FakeWorkspace()
        ws.research_dir = research_dir
        ws.script_path = script_path
        return ws

    def test_url_only_research_stays_available_regardless_of_script(self):
        ws = self._fake_workspace(script_fingerprint=None)
        ws.script_path.write_text("a brand new script written after research", encoding="utf-8")

        app = self._make_app_instance()
        provider = app._build_research_provider(ws)

        self.assertIsNotNone(provider)
        self.assertTrue(provider.has_unused_candidates())

    def test_script_bound_research_unavailable_when_script_changed(self):
        fp = compute_script_fingerprint("the original narration script")
        ws = self._fake_workspace(script_fingerprint=fp)
        ws.script_path.write_text("a totally different narration script", encoding="utf-8")

        app = self._make_app_instance()
        provider = app._build_research_provider(ws)

        self.assertIsNone(provider)

    def test_script_bound_research_available_when_script_unchanged(self):
        original = "the original narration script"
        fp = compute_script_fingerprint(original)
        ws = self._fake_workspace(script_fingerprint=fp)
        ws.script_path.write_text(original, encoding="utf-8")

        app = self._make_app_instance()
        provider = app._build_research_provider(ws)

        self.assertIsNotNone(provider)


class PropertyAmbiguousImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_package(self, ambiguous: bool):
        research_json = {
            "property": {"identity": {"property_name": "X"}, "confidence": 0.5},
            "sources": [],
            "media": [],
            "statistics": {"property_ambiguous": ambiguous},
        }
        (self.tmp / "research.json").write_text(json.dumps(research_json), encoding="utf-8")

    def test_ambiguous_flag_surfaced_true(self):
        self._write_package(ambiguous=True)
        result = load_research_result(self.tmp)
        self.assertTrue(result.property_ambiguous)

    def test_ambiguous_flag_surfaced_false(self):
        self._write_package(ambiguous=False)
        result = load_research_result(self.tmp)
        self.assertFalse(result.property_ambiguous)

    def test_missing_statistics_defaults_to_not_ambiguous(self):
        research_json = {"property": {"identity": {}}, "sources": [], "media": []}
        (self.tmp / "research.json").write_text(json.dumps(research_json), encoding="utf-8")
        result = load_research_result(self.tmp)
        self.assertFalse(result.property_ambiguous)


if __name__ == "__main__":
    unittest.main()
