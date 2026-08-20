#!/usr/bin/env python3
"""Tests for project downloaded-asset cleanup (scan, confirm, protect, delete)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from downloaded_assets import (
    DeleteDownloadedResult,
    delete_downloaded_assets,
    format_bytes,
    is_protected_asset_name,
    scan_downloaded_assets,
)
from project_workspace import create_project


def _write(path: Path, data: bytes = b"x" * 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _write_manifest(ws, entries: dict) -> None:
    path = ws.assets_dir / ".asset_manifest.json"
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


class TestFormatBytes(unittest.TestCase):
    def test_size_units(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(2048), "2.0 KB")
        self.assertEqual(format_bytes(5 * 1024 * 1024), "5.0 MB")


class TestDownloadedAssetsCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vg_cleanup_"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.ws = create_project("Cleanup Test", projects_root=self.tmp)

    def _seed_pipeline_and_protected(self):
        # Pipeline canonical + mirrors
        yt = _write(self.ws.assets_dir / "001.mp4", b"Y" * 1000)
        stock = _write(self.ws.assets_dir / "002.mp4", b"S" * 2000)
        flow = _write(self.ws.assets_dir / "003.mp4", b"F" * 3000)
        _write(self.ws.youtube_dir / "scene_001.mp4", b"ym" * 50)
        _write(self.ws.stock_dir / "scene_002.mp4", b"sm" * 50)
        _write(self.ws.flow_dir / "scene_003.mp4", b"fm" * 50)
        _write(self.ws.tmp_dir / "videogen_work" / "clip.mp4", b"t" * 400)
        _write(self.ws.assets_dir / ".stock_used_assets.json", b'{"ids":[]}')

        # Protected / must keep
        manual = _write(self.ws.assets_dir / "004.mp4", b"M" * 1500)
        archive = _write(self.ws.assets_dir / "004_manual.mp4", b"A" * 800)
        local = _write(self.ws.assets_dir / "005.jpg", b"L" * 900)
        audio = _write(self.ws.audio_dir / "narration.wav", b"V" * 500)
        script = _write(self.ws.script_dir / "narration.txt", b"hello script")
        csv = _write(self.ws.csv_dir / "visual_plan.csv", b"scene_number,script_segment\n")
        final = _write(self.ws.final_dir / "Cleanup_Test.mp4", b"FINAL" * 100)
        meta = self.ws.root / "project.json"

        _write_manifest(
            self.ws,
            {
                "001": {
                    "source": "youtube_video",
                    "status": "complete",
                    "local_path": str(yt),
                },
                "002": {
                    "source": "stock_video",
                    "status": "complete",
                    "local_path": str(stock),
                },
                "003": {
                    "source": "flow_video",
                    "status": "complete",
                    "local_path": str(flow),
                },
                "004": {
                    "source": "manual",
                    "status": "complete",
                    "local_path": str(manual),
                },
                "005": {
                    "source": "local",
                    "status": "complete",
                    "local_path": str(local),
                },
            },
        )
        return {
            "yt": yt,
            "stock": stock,
            "flow": flow,
            "manual": manual,
            "archive": archive,
            "local": local,
            "audio": audio,
            "script": script,
            "csv": csv,
            "final": final,
            "meta": meta,
        }

    def test_size_calculation_counts_pipeline_only(self):
        self._seed_pipeline_and_protected()
        report = scan_downloaded_assets(self.ws)
        self.assertGreater(report.file_count, 0)
        # Manual/local/audio/final must not be in the inventory.
        names = {p.name for p in report.files}
        self.assertIn("001.mp4", names)
        self.assertIn("002.mp4", names)
        self.assertIn("003.mp4", names)
        self.assertIn("scene_001.mp4", names)
        self.assertIn("clip.mp4", names)
        self.assertNotIn("004.mp4", names)
        self.assertNotIn("004_manual.mp4", names)
        self.assertNotIn("005.jpg", names)
        self.assertNotIn("narration.wav", names)
        self.assertNotIn("Cleanup_Test.mp4", names)
        expected = sum(p.stat().st_size for p in report.files)
        self.assertEqual(report.total_bytes, expected)
        self.assertIn("·", report.button_label())
        self.assertIn(report.format_size(), report.button_label())

    def test_confirmation_flow_requires_confirm_flag(self):
        paths = self._seed_pipeline_and_protected()
        report = scan_downloaded_assets(self.ws)
        self.assertFalse(report.is_empty)

        # Without confirm — nothing deleted (confirmation gate).
        denied = delete_downloaded_assets(self.ws, confirm=False, report=report)
        self.assertIsInstance(denied, DeleteDownloadedResult)
        self.assertFalse(denied.confirmed)
        self.assertEqual(denied.deleted, [])
        self.assertTrue(paths["yt"].is_file())
        self.assertTrue((self.ws.youtube_dir / "scene_001.mp4").is_file())

        # With confirm — pipeline files go away.
        result = delete_downloaded_assets(self.ws, confirm=True, report=report)
        self.assertTrue(result.confirmed)
        self.assertGreater(len(result.deleted), 0)
        self.assertFalse(paths["yt"].is_file())
        self.assertFalse((self.ws.youtube_dir / "scene_001.mp4").is_file())

    def test_protected_files_survive_cleanup(self):
        paths = self._seed_pipeline_and_protected()
        self.assertTrue(is_protected_asset_name("004_manual.mp4"))
        self.assertTrue(is_protected_asset_name("004_replaced.mp4"))
        self.assertFalse(is_protected_asset_name("001.mp4"))

        delete_downloaded_assets(self.ws, confirm=True)
        for key in ("manual", "archive", "local", "audio", "script", "csv", "final", "meta"):
            self.assertTrue(paths[key].is_file(), key)
        self.assertTrue(self.ws.script_dir.is_dir())
        self.assertTrue(self.ws.audio_dir.is_dir())
        self.assertTrue(self.ws.final_dir.is_dir())

    def test_successful_deletion_clears_mirrors_and_tmp(self):
        self._seed_pipeline_and_protected()
        before = scan_downloaded_assets(self.ws)
        result = delete_downloaded_assets(self.ws, confirm=True, report=before)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.failed), 0)
        self.assertEqual(result.bytes_freed, before.total_bytes)
        after = scan_downloaded_assets(self.ws)
        self.assertTrue(after.is_empty)
        self.assertFalse((self.ws.flow_dir / "scene_003.mp4").exists())
        self.assertFalse((self.ws.tmp_dir / "videogen_work" / "clip.mp4").exists())
        # Manifest no longer claims deleted pipeline scenes.
        man = json.loads((self.ws.assets_dir / ".asset_manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("001", man)
        self.assertNotIn("002", man)
        self.assertNotIn("003", man)
        self.assertIn("004", man)
        self.assertIn("005", man)

    def test_partial_deletion_failures_are_reported(self):
        self._seed_pipeline_and_protected()
        report = scan_downloaded_assets(self.ws)
        blocked = report.files[0]
        real_unlink = Path.unlink

        def flaky_unlink(self, *args, **kwargs):
            if self.resolve() == blocked.resolve():
                raise PermissionError("locked by test")
            return real_unlink(self, *args, **kwargs)

        with mock.patch.object(Path, "unlink", flaky_unlink):
            result = delete_downloaded_assets(self.ws, confirm=True, report=report)

        self.assertTrue(result.confirmed)
        self.assertTrue(result.partial)
        self.assertEqual(len(result.failed), 1)
        self.assertEqual(result.failed[0][0].resolve(), blocked.resolve())
        self.assertIn("locked", result.failed[0][1])
        self.assertGreater(len(result.deleted), 0)
        # Blocked file still present; others removed.
        self.assertTrue(blocked.is_file())

    def test_confirmation_message_lists_scope(self):
        self._seed_pipeline_and_protected()
        msg = scan_downloaded_assets(self.ws).confirmation_message()
        self.assertIn("downloaded asset", msg.lower())
        self.assertIn("Kept:", msg)
        self.assertIn("narration", msg.lower())


if __name__ == "__main__":
    unittest.main()
