"""Tests for SFX library import/validate tools."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
import wave
from pathlib import Path

from sfx.audio_probe import is_supported_audio, probe_audio
from sfx.catalog_io import load_catalog, normalize_entry, save_catalog
from sfx.importer import ImportOptions, import_manifest, import_sound_specs, init_library
from sfx.seed import ensure_sfx_library
from sfx.starter_catalog import STARTER_TARGETS, build_starter_catalog
from sfx.validator import validate_library


def _write_wav(path: Path, seconds: float = 0.2, sr: int = 48000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(seconds * sr))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * frames)


class TestStarterCatalog(unittest.TestCase):
    def test_starter_has_target_counts(self) -> None:
        catalog = build_starter_catalog()
        counts: dict[str, int] = {}
        for entry in catalog["sfx"]:
            counts[entry["category"]] = counts.get(entry["category"], 0) + 1
        self.assertEqual(sum(STARTER_TARGETS.values()), len(catalog["sfx"]))
        for category, expected in STARTER_TARGETS.items():
            self.assertEqual(counts.get(category, 0), expected, category)


class TestImport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "library"
        self.source = Path(self.tmp.name) / "curated"
        init_library(self.root, from_template=False, overwrite_catalog=True)
        save_catalog({"version": 1, "library_root": str(self.root), "sfx": []}, self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_import_updates_catalog_and_preserves_metadata(self) -> None:
        src = self.source / "whoosh_soft.wav"
        _write_wav(src, seconds=0.42)
        manifest = {
            "sounds": [
                {
                    "src": str(src),
                    "id": "whoosh_01",
                    "category": "whoosh",
                    "tags": ["soft", "sweep"],
                    "intensity": "low",
                    "source": "sonniss_gdc_2026",
                    "license": "Sonniss GDC 2026",
                    "commercial_use": True,
                    "attribution_required": False,
                }
            ]
        }
        manifest_path = self.source / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = import_manifest(
            manifest_path,
            ImportOptions(library_root=self.root, force=False, convert_wav=False),
        )
        self.assertEqual(result.imported, ["whoosh_01"])
        catalog = load_catalog(self.root)
        entry = next(e for e in catalog["sfx"] if e["id"] == "whoosh_01")
        self.assertEqual(entry["license"], "Sonniss GDC 2026")
        self.assertEqual(entry["source"], "sonniss_gdc_2026")
        self.assertAlmostEqual(entry["duration"], 0.42, places=2)
        self.assertTrue((self.root / entry["file"]).is_file())

    def test_duplicate_id_skipped_without_force(self) -> None:
        src_a = self.source / "a.wav"
        src_b = self.source / "b.wav"
        _write_wav(src_a)
        _write_wav(src_b)
        specs = [
            {
                "src": str(src_a),
                "id": "impact_01",
                "category": "impact",
                "tags": ["punch"],
                "intensity": "high",
                "source": "sonniss_gdc_2026",
                "license": "Sonniss GDC 2026",
                "commercial_use": True,
                "attribution_required": False,
            }
        ]
        import_sound_specs(specs, ImportOptions(library_root=self.root, convert_wav=False))
        specs[0]["src"] = str(src_b)
        result = import_sound_specs(specs, ImportOptions(library_root=self.root, convert_wav=False))
        self.assertIn("impact_01", "".join(result.skipped))

    def test_missing_license_rejected(self) -> None:
        src = self.source / "bad.wav"
        _write_wav(src)
        result = import_sound_specs(
            [{"src": str(src), "id": "ui_bad", "category": "ui", "tags": ["click"], "intensity": "low"}],
            ImportOptions(library_root=self.root, convert_wav=False),
        )
        self.assertTrue(result.errors)
        self.assertEqual(load_catalog(self.root)["sfx"], [])

    def test_supported_format_wav(self) -> None:
        src = self.source / "ok.wav"
        _write_wav(src)
        self.assertTrue(is_supported_audio(src))
        info = probe_audio(src)
        self.assertGreater(info.duration_seconds, 0)


class TestValidate(unittest.TestCase):
    def test_validate_reports_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_catalog(
                {
                    "version": 1,
                    "library_root": str(root),
                    "sfx": [
                        normalize_entry(
                            {
                                "id": "whoosh_01",
                                "file": "whoosh/whoosh_01.wav",
                                "category": "whoosh",
                                "tags": ["soft"],
                                "intensity": "low",
                                "duration": 0.4,
                                "source": "sonniss_gdc_2026",
                                "license": "Sonniss GDC 2026",
                                "commercial_use": True,
                                "attribution_required": False,
                            }
                        )
                    ],
                },
                root,
            )
            report = validate_library(root)
            self.assertGreater(report.missing_files, 0)
            self.assertFalse(report.ok)

    def test_validate_ok_for_imported_sound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "impact" / "impact_01.wav"
            _write_wav(wav, seconds=0.35)
            save_catalog(
                {
                    "version": 1,
                    "library_root": str(root),
                    "sfx": [
                        normalize_entry(
                            {
                                "id": "impact_01",
                                "file": "impact/impact_01.wav",
                                "category": "impact",
                                "tags": ["punch"],
                                "intensity": "high",
                                "duration": 0.35,
                                "source": "sonniss_gdc_2026",
                                "license": "Sonniss GDC 2026",
                                "commercial_use": True,
                                "attribution_required": False,
                            }
                        )
                    ],
                },
                root,
            )
            report = validate_library(root)
            self.assertTrue(report.ok)
            self.assertIn("✓", report.format_summary())

    def test_prune_removes_missing_keeps_valid(self) -> None:
        from sfx.catalog_io import prune_catalog

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wav = root / "whoosh" / "whoosh_01.wav"
            _write_wav(wav, seconds=0.4)
            save_catalog(
                {
                    "version": 1,
                    "library_root": str(root),
                    "sfx": [
                        normalize_entry(
                            {
                                "id": "whoosh_01",
                                "file": "whoosh/whoosh_01.wav",
                                "category": "whoosh",
                                "tags": ["soft"],
                                "intensity": "low",
                                "duration": 0.4,
                                "source": "Sonniss GDC",
                                "license": "Sonniss #GameAudioGDC Bundle License",
                                "commercial_use": True,
                                "attribution_required": False,
                            }
                        ),
                        normalize_entry(
                            {
                                "id": "whoosh_10",
                                "file": "whoosh/whoosh_10.wav",
                                "category": "whoosh",
                                "tags": ["soft"],
                                "intensity": "low",
                                "duration": 0.4,
                                "source": "Sonniss GDC",
                                "license": "Sonniss #GameAudioGDC Bundle License",
                                "commercial_use": True,
                                "attribution_required": False,
                            }
                        ),
                    ],
                },
                root,
            )
            catalog, removed = prune_catalog(root)
            self.assertEqual(removed, ["whoosh_10"])
            self.assertEqual([e["id"] for e in catalog["sfx"]], ["whoosh_01"])
            report = validate_library(root)
            self.assertTrue(report.ok)
            self.assertEqual(report.total_entries, 1)

    def test_import_curated_prunes_stale_placeholders(self) -> None:
        from sfx.importer import import_curated_library

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "library"
            curated = Path(tmp) / "curated"
            init_library(root, from_template=False, overwrite_catalog=True)
            wav = root / "impact" / "impact_01.wav"
            _write_wav(wav, seconds=0.3)
            save_catalog(
                {
                    "version": 1,
                    "library_root": str(root),
                    "sfx": [
                        normalize_entry(
                            {
                                "id": "impact_01",
                                "file": "impact/impact_01.wav",
                                "category": "impact",
                                "tags": ["punch"],
                                "intensity": "high",
                                "duration": 0.3,
                                "source": "Sonniss GDC",
                                "license": "Sonniss #GameAudioGDC Bundle License",
                                "commercial_use": True,
                                "attribution_required": False,
                            }
                        ),
                        normalize_entry(
                            {
                                "id": "riser_03",
                                "file": "riser/riser_03.wav",
                                "category": "riser",
                                "tags": ["tension"],
                                "intensity": "medium",
                                "duration": 0.8,
                                "source": "Sonniss GDC",
                                "license": "Sonniss #GameAudioGDC Bundle License",
                                "commercial_use": True,
                                "attribution_required": False,
                            }
                        ),
                    ],
                },
                root,
            )
            curated.mkdir(parents=True)
            result = import_curated_library(
                curated,
                ImportOptions(library_root=root, convert_wav=False),
            )
            ids = {e["id"] for e in load_catalog(root)["sfx"]}
            self.assertIn("impact_01", ids)
            self.assertNotIn("riser_03", ids)
            self.assertTrue(any("riser_03" in line for line in result.skipped))


class TestSfxSeed(unittest.TestCase):
    def test_ensure_sfx_library_copies_bundled_wavs_when_empty(self) -> None:
        from sfx.seed import bundled_sfx_source, ensure_sfx_library

        src = bundled_sfx_source()
        if src is None:
            self.skipTest("bundled SFX library not present in repo")

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "sfx"
            dest.mkdir()
            with unittest.mock.patch("sfx.seed.sfx_library_root", return_value=dest):
                root = ensure_sfx_library()
            self.assertEqual(root, dest)
            catalog = load_catalog(dest)
            self.assertGreater(len(catalog["sfx"]), 0)
            first = catalog["sfx"][0]
            self.assertTrue((dest / first["file"]).is_file())

    def test_ensure_sfx_library_skips_when_populated(self) -> None:
        from sfx import seed

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "sfx"
            init_library(dest, from_template=False, overwrite_catalog=True)
            wav = dest / "whoosh" / "existing.wav"
            _write_wav(wav)
            save_catalog(
                {
                    "version": 1,
                    "library_root": str(dest),
                    "sfx": [
                        normalize_entry(
                            {
                                "id": "whoosh_existing",
                                "file": "whoosh/existing.wav",
                                "category": "whoosh",
                                "tags": ["soft"],
                                "intensity": "low",
                                "duration": 0.2,
                            }
                        )
                    ],
                },
                dest,
            )
            with unittest.mock.patch.object(seed, "sfx_library_root", return_value=dest):
                with unittest.mock.patch.object(seed, "bundled_sfx_source") as mock_src:
                    ensure_sfx_library()
            mock_src.assert_not_called()


if __name__ == "__main__":
    unittest.main()
