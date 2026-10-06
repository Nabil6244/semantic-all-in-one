#!/usr/bin/env python3
"""The curated ambience library (2026-10-06): every scene profile has its own real beds, a newer bundled catalog replaces
an installed one, and saved plans that point at removed beds are re-picked from their stored profile."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import smart_editing as se
from sfx import seed
from sfx.ambience_profiles import PROFILE_SECONDARY_TAGS

BUNDLE = Path(__file__).resolve().parent / "assets" / "bundled-sfx"


def _catalog() -> se.SfxCatalog:
    return se.SfxCatalog.load(BUNDLE, BUNDLE / "catalog.json")


class TestCuratedAmbience(unittest.TestCase):
    def test_every_profile_has_at_least_two_own_beds_and_files_exist(self):
        cat = _catalog()
        amb = cat._by_category["ambience"]
        for profile in PROFILE_SECONDARY_TAGS:
            own = [e for e in amb if e.tags and e.tags[0] == profile]
            self.assertGreaterEqual(len(own), 2, profile)
        for e in amb:
            self.assertTrue(e.resolved_path(cat.root).is_file(), e.file)

    def test_each_profile_picks_one_of_its_own_beds(self):
        cat = _catalog()
        settings = se.SmartEditingSettings()
        for profile in PROFILE_SECONDARY_TAGS:
            for scene in ("1", "2", "3", "7"):
                e = se._pick_ambience_entry(cat, profile, settings, scene_number=scene, avoid_ids=[])
                self.assertEqual(e.tags[0], profile, f"{profile} scene {scene} got {e.id}")

    def test_no_non_ambience_recordings(self):
        raw = json.loads((BUNDLE / "catalog.json").read_text(encoding="utf-8"))
        names = " ".join(str(e.get("source_file", "")) for e in raw["sfx"] if e["category"] == "ambience").lower()
        for bad in ("water polo", "league match", "paintball", "quadcopter", "metal box", "shimmer", "unidentified",
                    "fireworks", "church bells", "putting out fire"):
            self.assertNotIn(bad, names)
        self.assertGreaterEqual(raw["version"], 3)

    def test_beds_are_levelled_low(self):
        raw = json.loads((BUNDLE / "catalog.json").read_text(encoding="utf-8"))
        for e in raw["sfx"]:
            if e["category"] == "ambience":
                self.assertLessEqual(e["loudness_lufs"], -34.0, e["id"])


class TestInstallUpgrade(unittest.TestCase):
    def test_newer_bundled_catalog_replaces_installed_one(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            dest = tmp / "lib"
            (dest / "ambience").mkdir(parents=True)
            (dest / "catalog.json").write_text(json.dumps({"version": 1, "sfx": [
                {"id": "ambience_26", "file": "ambience/ambience_26.wav", "category": "ambience", "tags": ["water"]}]}))
            with mock.patch.object(seed, "sfx_library_root", return_value=dest):
                seed.ensure_sfx_library()
            installed = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(installed["version"], 3)
            self.assertTrue(any(e["id"].startswith("amb_water_") for e in installed["sfx"]))
            self.assertTrue((dest / "ambience" / "amb_water_01.opus").is_file())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upgrade_replaces_a_file_whose_sound_changed(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            dest = tmp / "lib"
            shutil.copytree(BUNDLE, dest)
            raw = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
            raw["version"] = int(raw["version"]) - 1
            (dest / "catalog.json").write_text(json.dumps(raw))
            (dest / "ambience" / "amb_city_01.opus").write_bytes(b"old louder bed")
            with mock.patch.object(seed, "sfx_library_root", return_value=dest):
                seed.ensure_sfx_library()
            self.assertEqual((dest / "ambience" / "amb_city_01.opus").read_bytes(),
                             (BUNDLE / "ambience" / "amb_city_01.opus").read_bytes())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_same_version_keeps_installed_catalog(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            dest = tmp / "lib"
            shutil.copytree(BUNDLE, dest)
            marker = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
            marker["note"] = "user copy"
            (dest / "catalog.json").write_text(json.dumps(marker))
            with mock.patch.object(seed, "sfx_library_root", return_value=dest):
                seed.ensure_sfx_library()
            self.assertEqual(json.loads((dest / "catalog.json").read_text(encoding="utf-8")).get("note"), "user copy")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestStaleBedRefresh(unittest.TestCase):
    def test_removed_beds_are_repicked_from_their_profile_and_timing_kept(self):
        cat = _catalog()
        beds = [
            {"scene_number": "1", "profile": "water", "start": 0.0, "end": 5.0, "volume": 0.3, "sfx_id": "ambience_26",
             "file": "ambience/ambience_26.wav"},
            {"scene_number": "2", "profile": "room", "start": 5.0, "end": 9.0, "volume": 0.25, "sfx_id": "amb_room_01",
             "file": "ambience/amb_room_01.opus"},
        ]
        out, changed = se.refresh_stale_ambience(beds, cat, se.SmartEditingSettings())
        self.assertTrue(changed)
        self.assertTrue(out[0]["sfx_id"].startswith("amb_water_"))
        self.assertEqual((out[0]["start"], out[0]["end"], out[0]["volume"]), (0.0, 5.0, 0.3))
        self.assertEqual(out[1]["sfx_id"], "amb_room_01", "a bed still in the library is kept")

    def test_empty_library_leaves_beds_alone(self):
        beds = [{"scene_number": "1", "profile": "water", "sfx_id": "ambience_26"}]
        out, changed = se.refresh_stale_ambience(beds, se.SfxCatalog(Path("/nonexistent"), []), se.SmartEditingSettings())
        self.assertFalse(changed)
        self.assertEqual(out, beds)


if __name__ == "__main__":
    unittest.main()
