"""Regression tests for media_metadata_cache.py (Semantic YT Studio 2.0 — Batch 1).

Uses a mocked probe function (call counter) — no real ffprobe/subprocess —
to verify memoization keys correctly off (path, size, mtime) and always
fails open to "probe again" rather than ever returning a stale value for a
file that can't be identified.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import media_metadata_cache
from media_metadata_cache import cached_probe_duration


class _CountingProbe:
    def __init__(self, value=5.0):
        self.calls = 0
        self.value = value

    def __call__(self, path, *args, **kwargs):
        self.calls += 1
        return self.value


class TestMediaMetadataCache(unittest.TestCase):
    def setUp(self):
        media_metadata_cache.clear()

    def tearDown(self):
        media_metadata_cache.clear()

    def test_second_call_for_unchanged_file_is_a_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.mp4"
            p.write_bytes(b"abc")
            probe = _CountingProbe(3.5)
            r1 = cached_probe_duration(p, probe)
            r2 = cached_probe_duration(p, probe)
            self.assertEqual(r1, 3.5)
            self.assertEqual(r2, 3.5)
            self.assertEqual(probe.calls, 1)

    def test_changed_size_forces_reprobe(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.mp4"
            p.write_bytes(b"abc")
            probe = _CountingProbe(3.5)
            cached_probe_duration(p, probe)
            p.write_bytes(b"a much longer different content")
            probe.value = 9.9
            result = cached_probe_duration(p, probe)
            self.assertEqual(result, 9.9)
            self.assertEqual(probe.calls, 2)

    def test_changed_mtime_same_size_forces_reprobe(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.mp4"
            p.write_bytes(b"abc")
            probe = _CountingProbe(3.5)
            cached_probe_duration(p, probe)
            # Touch mtime forward without changing size.
            future = time.time() + 5
            import os

            os.utime(p, (future, future))
            probe.value = 7.7
            result = cached_probe_duration(p, probe)
            self.assertEqual(result, 7.7)
            self.assertEqual(probe.calls, 2)

    def test_missing_file_always_reprobes_never_caches(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "does_not_exist.mp4"
            probe = _CountingProbe(None)
            cached_probe_duration(p, probe)
            cached_probe_duration(p, probe)
            cached_probe_duration(p, probe)
            # A file that can't be stat()'d must skip caching entirely
            # (fail open to "always probe"), not be memoized as None forever.
            self.assertEqual(probe.calls, 3)

    def test_different_files_have_independent_cache_entries(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.mp4"
            p2 = Path(td) / "b.mp4"
            p1.write_bytes(b"1")
            p2.write_bytes(b"22")
            probe = _CountingProbe(1.0)
            cached_probe_duration(p1, probe)
            probe.value = 2.0
            cached_probe_duration(p2, probe)
            self.assertEqual(probe.calls, 2)
            probe.value = 999.0  # should not affect already-cached results
            self.assertEqual(cached_probe_duration(p1, probe), 1.0)
            self.assertEqual(cached_probe_duration(p2, probe), 2.0)
            self.assertEqual(probe.calls, 2)

    def test_probe_fn_receives_extra_args_and_kwargs(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.mp4"
            p.write_bytes(b"abc")
            seen = {}

            def probe(path, *args, **kwargs):
                seen["args"] = args
                seen["kwargs"] = kwargs
                return 1.0

            cached_probe_duration(p, probe, "extra_arg", log_failures=False)
            self.assertEqual(seen["args"], ("extra_arg",))
            self.assertEqual(seen["kwargs"], {"log_failures": False})

    def test_clear_and_size(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.mp4"
            p.write_bytes(b"abc")
            probe = _CountingProbe(1.0)
            cached_probe_duration(p, probe)
            self.assertEqual(media_metadata_cache.size(), 1)
            media_metadata_cache.clear()
            self.assertEqual(media_metadata_cache.size(), 0)


if __name__ == "__main__":
    unittest.main()
