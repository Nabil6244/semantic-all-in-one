"""Tests for waveform_cache.py — real audio decode + disk cache, no fake
waveform data. Uses real ffmpeg to generate and decode test tones."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import waveform_cache as wc

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


class TestFileIdentityAndCacheKey(unittest.TestCase):
    def test_missing_file_returns_none_for_get_or_build(self):
        with tempfile.TemporaryDirectory() as td:
            result = wc.get_or_build_waveform(Path(td), Path(td) / "nope.wav")
            self.assertIsNone(result)

    def test_cache_key_deterministic(self):
        k1 = wc._cache_key(("a", 1, 2), 400)
        k2 = wc._cache_key(("a", 1, 2), 400)
        self.assertEqual(k1, k2)

    def test_cache_key_changes_with_buckets(self):
        k1 = wc._cache_key(("a", 1, 2), 400)
        k2 = wc._cache_key(("a", 1, 2), 200)
        self.assertNotEqual(k1, k2)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestRealWaveformDecode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmpdir.name)
        cls.audio = cls.root / "tone.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-ar", "44100", str(cls.audio)],
            check=True, capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_real_decode_produces_bounded_peaks(self):
        peaks = wc.get_or_build_waveform(self.root / "state1", self.audio, buckets=50)
        self.assertIsNotNone(peaks)
        self.assertGreater(len(peaks), 0)
        for lo, hi in peaks:
            self.assertGreaterEqual(lo, -1.0)
            self.assertLessEqual(hi, 1.0)
            self.assertLessEqual(lo, hi)

    def test_result_is_disk_cached(self):
        state_dir = self.root / "state2"
        wc.get_or_build_waveform(state_dir, self.audio, buckets=50)
        cache_files = list((state_dir / wc.WAVEFORM_DIRNAME).glob("*.json"))
        self.assertEqual(len(cache_files), 1)

    def test_corrupt_cache_file_triggers_rebuild_not_crash(self):
        state_dir = self.root / "state3"
        wc.get_or_build_waveform(state_dir, self.audio, buckets=50)
        cache_file = next((state_dir / wc.WAVEFORM_DIRNAME).glob("*.json"))
        cache_file.write_text("{not valid json", encoding="utf-8")
        peaks = wc.get_or_build_waveform(state_dir, self.audio, buckets=50)
        self.assertIsNotNone(peaks)
        self.assertGreater(len(peaks), 0)

    def test_changed_file_invalidates_cache(self):
        state_dir = self.root / "state4"
        audio2 = self.root / "tone_copy.wav"
        shutil.copy2(self.audio, audio2)
        peaks_a = wc.get_or_build_waveform(state_dir, audio2, buckets=50)
        # Mutate the file (different content+mtime) — must not silently
        # reuse the stale cached peaks for the old content.
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", "-ar", "44100", str(audio2)],
            check=True, capture_output=True,
        )
        cache_files_before = set((state_dir / wc.WAVEFORM_DIRNAME).glob("*.json"))
        peaks_b = wc.get_or_build_waveform(state_dir, audio2, buckets=50)
        cache_files_after = set((state_dir / wc.WAVEFORM_DIRNAME).glob("*.json"))
        self.assertNotEqual(len(peaks_a), 0)
        self.assertGreater(len(cache_files_after), len(cache_files_before), "changed file should get its own cache entry, not reuse the old one")


if __name__ == "__main__":
    unittest.main()
