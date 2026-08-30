"""SFX runtime is format-agnostic: catalog metadata is the source of truth,
never the file extension. WAV must keep working alongside opus/flac."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sfx.audio_probe import SUPPORTED_SUFFIXES, is_supported_audio, probe_audio
from sfx.catalog_io import normalize_entry
from smart_editing import SfxCatalog

REPO = Path(__file__).resolve().parent
FFMPEG = REPO / "bin" / "ffmpeg"


class TestFormatAgnosticProbe(unittest.TestCase):
    def test_opus_and_flac_are_supported(self):
        for ext in (".wav", ".flac", ".opus", ".ogg", ".m4a"):
            self.assertTrue(is_supported_audio(f"x{ext}"), ext)

    def test_unrelated_container_still_rejected(self):
        self.assertFalse(is_supported_audio("x.mp4"))
        self.assertFalse(is_supported_audio("x.txt"))

    def test_wav_stays_supported(self):
        self.assertIn(".wav", SUPPORTED_SUFFIXES)

    def test_bundled_ffprobe_is_preferred_over_path(self):
        """A packaged build has no system ffprobe; shutil.which alone would
        make every non-WAV asset unreadable."""
        from sfx.audio_probe import _ffprobe_binary

        resolved = _ffprobe_binary()
        self.assertIsNotNone(resolved)
        if (REPO / "bin" / "ffprobe").is_file():
            self.assertIn("bin", str(resolved))


@unittest.skipUnless(FFMPEG.is_file(), "bundled ffmpeg required")
class TestRealAssetProbing(unittest.TestCase):
    """Duration/sample-rate/channels come from the ASSET, never the filename."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, name, args):
        out = self.tmp / name
        subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-ac", "2", "-ar", "48000"] + args + [str(out)],
                       check=True, capture_output=True, timeout=120)
        return out

    def test_probe_wav(self):
        info = probe_audio(self._make("a.wav", ["-c:a", "pcm_s16le"]))
        self.assertAlmostEqual(info.duration_seconds, 2.0, delta=0.2)
        self.assertEqual(info.sample_rate, 48000)
        self.assertEqual(info.channels, 2)

    def test_probe_opus(self):
        info = probe_audio(self._make("a.opus", ["-c:a", "libopus", "-b:a", "128k"]))
        self.assertAlmostEqual(info.duration_seconds, 2.0, delta=0.3)
        self.assertEqual(info.channels, 2)

    def test_probe_flac(self):
        info = probe_audio(self._make("a.flac", ["-c:a", "flac"]))
        self.assertAlmostEqual(info.duration_seconds, 2.0, delta=0.2)

    def test_missing_asset_fails_safely(self):
        with self.assertRaises(FileNotFoundError):
            probe_audio(self.tmp / "nope.opus")

    def test_corrupt_asset_fails_safely_not_crash(self):
        bad = self.tmp / "bad.opus"
        bad.write_bytes(b"not audio at all")
        with self.assertRaises((ValueError, RuntimeError)):
            probe_audio(bad)

    def test_ffmpeg_can_mix_an_opus_asset(self):
        src = self._make("mix.opus", ["-c:a", "libopus", "-b:a", "128k"])
        r = subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error",
                            "-i", str(src), "-f", "lavfi", "-i", "sine=f=220:d=1",
                            "-filter_complex",
                            "[0:a][1:a]amix=inputs=2:duration=shortest:normalize=0[a]",
                            "-map", "[a]", "-f", "null", "-"],
                           capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0)

    def test_ffmpeg_can_seek_and_trim_an_opus_asset(self):
        src = self._make("seek.opus", ["-c:a", "libopus", "-b:a", "128k"])
        r = subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error",
                            "-ss", "0.5", "-t", "0.5", "-i", str(src), "-f", "null", "-"],
                           capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0)


class TestCatalogDrivenResolution(unittest.TestCase):
    """The extension must never determine the semantic category."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _catalog(self, entries):
        (self.tmp / "catalog.json").write_text(
            json.dumps({"version": 2, "sfx": entries}), encoding="utf-8")
        return SfxCatalog.load(self.tmp)

    def test_opus_entry_resolves_and_keeps_its_category(self):
        (self.tmp / "impact").mkdir()
        (self.tmp / "impact" / "impact_001.opus").write_bytes(b"x")
        cat = self._catalog([{"id": "impact_001", "file": "impact/impact_001.opus",
                              "category": "impact", "duration": 1.0}])
        e = cat.entries[0]
        self.assertEqual(e.category, "impact")
        self.assertTrue(e.resolved_path(cat.root).is_file())

    def test_wav_entry_still_resolves(self):
        (self.tmp / "whoosh").mkdir()
        (self.tmp / "whoosh" / "whoosh_001.wav").write_bytes(b"x")
        cat = self._catalog([{"id": "whoosh_001", "file": "whoosh/whoosh_001.wav",
                              "category": "whoosh", "duration": 1.0}])
        self.assertEqual(cat.entries[0].category, "whoosh")
        self.assertTrue(cat.entries[0].resolved_path(cat.root).is_file())

    def test_mixed_format_catalog_loads(self):
        for cat_name, fname in (("impact", "impact_001.opus"), ("whoosh", "whoosh_001.wav")):
            (self.tmp / cat_name).mkdir(exist_ok=True)
            (self.tmp / cat_name / fname).write_bytes(b"x")
        cat = self._catalog([
            {"id": "impact_001", "file": "impact/impact_001.opus", "category": "impact", "duration": 1.0},
            {"id": "whoosh_001", "file": "whoosh/whoosh_001.wav", "category": "whoosh", "duration": 1.0},
        ])
        self.assertEqual(len(cat.entries), 2)
        self.assertEqual({e.category for e in cat.entries}, {"impact", "whoosh"})

    def test_missing_file_reports_unresolved_not_crash(self):
        cat = self._catalog([{"id": "gone_001", "file": "impact/gone_001.opus",
                              "category": "impact", "duration": 1.0}])
        self.assertFalse(cat.entries[0].resolved_path(cat.root).is_file())

    def test_synthesised_path_follows_catalog_format(self):
        self.assertTrue(normalize_entry({"id": "i1", "category": "impact"})["file"].endswith(".wav"))
        self.assertTrue(normalize_entry({"id": "i1", "category": "impact",
                                         "format": "opus"})["file"].endswith(".opus"))

    def test_no_source_library_path_leaks(self):
        """A runtime catalog must never carry a developer/source absolute path."""
        bundled = REPO / "assets" / "bundled-sfx" / "catalog.json"
        if not bundled.is_file():
            self.skipTest("no bundled catalog")
        for e in json.loads(bundled.read_text())["sfx"]:
            f = e.get("file", "")
            self.assertFalse(Path(f).is_absolute(), f)
            self.assertNotIn("..", Path(f).parts, f)
            for leak in ("videogen-sfx-source", "/tmp/", "/Users/", "C:\\"):
                self.assertNotIn(leak, json.dumps(e), f"{e.get('id')} leaks {leak}")


if __name__ == "__main__":
    unittest.main()
