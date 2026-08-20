"""Tests for Sonniss SFX curation and production import workflow."""

from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sfx.curator import (
    classify_candidate,
    curate_sonniss_library,
    find_candidates,
    shortlist_candidates,
)
from sfx.importer import ImportOptions, import_curated_library, init_library
from sfx.sonniss_license import SONNISS_LICENSE, SONNISS_SOURCE
from sfx.validator import validate_library
from smart_editing import (
    SmartEditingSettings,
    build_plan,
    get_sfx_catalog,
    mix_sfx_with_narration,
    reset_sfx_catalog_cache,
)


def _write_wav(path: Path, seconds: float = 0.3, sr: int = 48000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(seconds * sr))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * frames)


class TestCuration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / "source"
        self.curated = Path(self.tmp.name) / "curated"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_sonniss_like_tree(self) -> None:
        samples = {
            "whoosh/WHOOSH_Short_Fast_01.wav": 0.4,
            "whoosh/WHOOSH_Soft_Sweep_02.wav": 0.55,
            "impact/IMPACT_Medium_Punch_01.wav": 0.35,
            "impact/IMPACT_Deep_Hit_02.wav": 0.5,
            "ui/UI_Click_Button_01.wav": 0.12,
            "text/TEXT_Pop_Reveal_01.wav": 0.28,
            "transition/TRANSITION_Sweep_Fast_01.wav": 0.45,
            "riser/RISER_Short_Tension_01.wav": 0.9,
            "cinematic/CINEMATIC_Boom_Trailer_01.wav": 0.7,
            "technology/TECH_Digital_Activation_01.wav": 0.25,
            "ambience/AMBIENCE_Office_Room_01.wav": 2.5,
            "reject/MUSIC_Orchestra_Loop.wav": 3.0,
            "reject/DIALOGUE_Voice_Speech_01.wav": 1.0,
        }
        for rel, dur in samples.items():
            _write_wav(self.source / rel, seconds=dur)

    def test_classify_whoosh_by_filename(self) -> None:
        path = self.source / "pack" / "WHOOSH_Short_Fast_01.wav"
        _write_wav(path, seconds=0.4)
        cand = classify_candidate(path, "whoosh")
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand.category, "whoosh")
        self.assertGreater(cand.score, 0)

    def test_reject_music_and_dialogue(self) -> None:
        music = self.source / "MUSIC_Orchestra_Loop.wav"
        dialogue = self.source / "DIALOGUE_Voice_Speech.wav"
        _write_wav(music, seconds=2.0)
        _write_wav(dialogue, seconds=1.0)
        self.assertIsNone(classify_candidate(music, "whoosh"))
        self.assertIsNone(classify_candidate(dialogue, "ui"))

    def test_shortlist_respects_category_caps(self) -> None:
        self._seed_sonniss_like_tree()
        for i in range(15):
            _write_wav(self.source / "whoosh" / f"WHOOSH_Extra_{i:02d}.wav", seconds=0.35 + i * 0.01)
        by_category = find_candidates(self.source)
        shortlisted = shortlist_candidates(by_category)
        self.assertLessEqual(len(shortlisted["whoosh"]), 10)
        self.assertGreater(len(by_category["whoosh"]), len(shortlisted["whoosh"]))

    def test_curate_stages_sidecar_metadata(self) -> None:
        self._seed_sonniss_like_tree()
        report = curate_sonniss_library(self.source, self.curated)
        self.assertFalse(report.errors)
        self.assertGreater(len(report.staged_files), 0)
        sidecar = self.curated / "whoosh" / "whoosh_01.json"
        self.assertTrue(sidecar.is_file())
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertEqual(meta["source"], SONNISS_SOURCE)
        self.assertEqual(meta["license"], SONNISS_LICENSE)
        self.assertTrue(meta["commercial_use"])
        self.assertFalse(meta["attribution_required"])


class TestProductionImport(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.library = Path(self.tmp.name) / "library"
        self.curated = Path(self.tmp.name) / "curated"
        init_library(self.library, from_template=False, overwrite_catalog=True)
        from sfx.catalog_io import save_catalog

        save_catalog({"version": 1, "library_root": str(self.library), "sfx": []}, self.library)

    def tearDown(self) -> None:
        self.tmp.cleanup()
        reset_sfx_catalog_cache()

    def test_import_curated_populates_library(self) -> None:
        cat_dir = self.curated / "impact"
        src = cat_dir / "impact_01.wav"
        _write_wav(src, seconds=0.35)
        (cat_dir / "impact_01.json").write_text(
            json.dumps(
                {
                    "id": "impact_01",
                    "category": "impact",
                    "tags": ["punch"],
                    "intensity": "high",
                    "source": SONNISS_SOURCE,
                    "license": SONNISS_LICENSE,
                    "commercial_use": True,
                    "attribution_required": False,
                }
            ),
            encoding="utf-8",
        )
        result = import_curated_library(
            self.curated,
            ImportOptions(library_root=self.library, convert_wav=False),
        )
        self.assertEqual(result.imported, ["impact_01"])
        report = validate_library(self.library)
        self.assertTrue(report.ok)
        self.assertEqual(report.total_entries, 1)


class TestSmartEditingWithLibrary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.library = Path(self.tmp.name) / "library"
        reset_sfx_catalog_cache()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        reset_sfx_catalog_cache()

    def _install_minimal_library(self) -> None:
        from smart_editing import write_test_sfx_library

        write_test_sfx_library(self.library)

    def test_ai_script_and_csv_paths_select_local_sfx(self) -> None:
        self._install_minimal_library()
        reset_sfx_catalog_cache()
        rows = [
            {"scene_number": "1", "script_segment": "This is IMPORTANT news about AI technology."},
            {"scene_number": "2", "script_segment": "The number 100 percent growth is huge."},
        ]
        aligned = [
            {"scene_number": "1", "start_time": 0.0, "end_time": 4.0},
            {"scene_number": "2", "start_time": 4.2, "end_time": 8.0},
        ]
        whisper = [
            ("this", 0.0, 0.2),
            ("is", 0.2, 0.35),
            ("important", 0.35, 0.8),
            ("news", 0.8, 1.1),
            ("about", 1.1, 1.4),
            ("ai", 1.4, 1.7),
            ("technology", 1.7, 2.2),
            ("the", 4.2, 4.4),
            ("number", 4.4, 4.8),
            ("100", 4.8, 5.2),
            ("percent", 5.2, 5.6),
            ("growth", 5.6, 6.0),
            ("is", 6.0, 6.2),
            ("huge", 6.2, 6.6),
        ]
        settings = SmartEditingSettings(text_effects=True, sound_effects=True, intensity="medium")
        with patch("smart_editing.sfx_library_root", return_value=self.library):
            get_sfx_catalog(root=self.library, force_reload=True)
            plan = build_plan(rows, aligned, whisper, settings)
        self.assertTrue(plan.text_effects)
        self.assertTrue(plan.sfx_events)
        for ev in plan.sfx_events:
            self.assertIn("sfx_id", ev)
            self.assertIn("file", ev)

    def test_intensity_volume_scaling(self) -> None:
        self._install_minimal_library()
        rows = [{"scene_number": "1", "script_segment": "IMPORTANT update today."}]
        aligned = [{"scene_number": "1", "start_time": 0.0, "end_time": 5.0}]
        whisper = [("important", 0.2, 0.7), ("update", 0.7, 1.1), ("today", 1.1, 1.5)]
        volumes = {}
        with patch("smart_editing.sfx_library_root", return_value=self.library):
            get_sfx_catalog(root=self.library, force_reload=True)
            for intensity in ("low", "medium", "high"):
                plan = build_plan(
                    rows,
                    aligned,
                    whisper,
                    SmartEditingSettings(text_effects=True, sound_effects=True, intensity=intensity),
                )
                self.assertTrue(plan.sfx_events, intensity)
                volumes[intensity] = plan.sfx_events[0]["volume"]
        self.assertLess(volumes["low"], volumes["medium"])
        self.assertLess(volumes["medium"], volumes["high"])
        self.assertGreaterEqual(volumes["medium"], 0.30)
        self.assertLessEqual(volumes["high"], 0.55)

    def test_mix_preserves_narration_when_no_sfx(self) -> None:
        narration = Path(self.tmp.name) / "narration.wav"
        out = Path(self.tmp.name) / "mixed.wav"
        _write_wav(narration, seconds=1.0)
        mix_sfx_with_narration(narration, [], out, sfx_root=self.library)
        self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
