#!/usr/bin/env python3
"""The per-project "Accept Ultra HD (4K) footage" switch (step 1 of 4K support).

Off (default): stock picks and the 200 MB cap are exactly as before. On: Pexels/Pixabay pick the 4K file, the cap is 1 GB per
clip, and a 4K download that fails falls back to the same clip's HD file instead of failing the scene. No network.
"""

from __future__ import annotations

import inspect
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from project_workspace import create_project, load_project
from providers.base import MediaType, SceneRow, SceneStatus
from providers.stock import base as stock_base
from providers.stock import downloader
from providers.stock.base import Candidate, StockProvider
from providers.stock.cache import StockCache
from providers.stock.pexels import PexelsBackend
from providers.stock.pixabay import PixabayBackend

PEXELS_VIDEO = {
    "id": 101, "duration": 12, "url": "https://pexels/v/101", "user": {"name": "A"}, "video_pictures": [{"picture": ""}],
    "video_files": [
        {"link": "https://pexels/sd.mp4", "width": 960, "height": 540},
        {"link": "https://pexels/hd.mp4", "width": 1920, "height": 1080},
        {"link": "https://pexels/uhd.mp4", "width": 3840, "height": 2160},
        {"link": "https://pexels/8k.mp4", "width": 7680, "height": 4320},
    ],
}
PIXABAY_HIT = {
    "id": 7, "duration": 9, "user": "B", "pageURL": "https://pixabay/7", "tags": "river",
    "videos": {"large": {"url": "https://pixabay/large.mp4", "width": 3840, "height": 2160},
               "medium": {"url": "https://pixabay/medium.mp4", "width": 1920, "height": 1080}},
}


def _resp(payload):
    r = mock.Mock(status_code=200)
    r.json.return_value = payload
    r.raise_for_status = lambda: None
    return r


def _pexels(uhd):
    b = PexelsBackend("key")
    b.uhd = uhd
    b._session = mock.Mock(get=mock.Mock(return_value=_resp({"videos": [PEXELS_VIDEO]})))
    return b._search_videos("river", 5)[0]


def _pixabay(uhd):
    b = PixabayBackend("key")
    b.uhd = uhd
    b._session = mock.Mock(get=mock.Mock(return_value=_resp({"hits": [PIXABAY_HIT]})))
    return b._search_videos("river", 5)[0]


class TestProjectSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_off_by_default_saved_per_project_and_survives_reopening(self):
        a = create_project("A", projects_root=self.tmp, when=date(2026, 10, 6))
        b = create_project("B", projects_root=self.tmp, when=date(2026, 10, 6))
        self.assertFalse(a.quality_settings().get("uhd_footage", False))
        a.set_quality_settings(uhd_footage=True)
        self.assertTrue(load_project(a.root).quality_settings()["uhd_footage"])
        self.assertFalse(load_project(b.root).quality_settings().get("uhd_footage", False), "another project is not affected")
        a.set_quality_settings(uhd_footage=False)
        self.assertFalse(load_project(a.root).quality_settings()["uhd_footage"])


class TestPicking(unittest.TestCase):
    def test_pexels_off_is_unchanged(self):
        c = _pexels(False)
        self.assertEqual((c.url, c.width), ("https://pexels/hd.mp4", 1920))
        self.assertNotIn("hd_fallback", c.extra)

    def test_pexels_on_takes_4k_and_keeps_the_hd_file_as_fallback(self):
        c = _pexels(True)
        self.assertEqual((c.url, c.width, c.height), ("https://pexels/uhd.mp4", 3840, 2160), "4K, never the 8K file")
        self.assertEqual(c.extra["hd_fallback"], {"url": "https://pexels/hd.mp4", "width": 1920, "height": 1080})

    def test_pixabay_off_is_unchanged(self):
        c = _pixabay(False)
        self.assertEqual(c.url, "https://pixabay/large.mp4")
        self.assertNotIn("hd_fallback", c.extra)

    def test_pixabay_on_keeps_medium_as_fallback(self):
        c = _pixabay(True)
        self.assertEqual(c.url, "https://pixabay/large.mp4")
        self.assertEqual(c.extra["hd_fallback"]["url"], "https://pixabay/medium.mp4")


def _candidate(fallback=True):
    extra = {"hd_fallback": {"url": "https://x/hd.mp4", "width": 1920, "height": 1080}} if fallback else {}
    return Candidate(provider="pexels", asset_id="101", media_type=MediaType.VIDEO, url="https://x/uhd.mp4",
                     width=3840, height=2160, duration=10, extra=extra)


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scene = SceneRow(scene_number="2", script_segment="x", asset_type="stock_video", stock="river")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _provider(self, uhd):
        p = StockProvider(backends=[PexelsBackend("key")], cache=StockCache())
        p.set_uhd(uhd)
        return p

    def _run(self, provider, candidate, outcomes):
        """outcomes: one per download_candidate call — an exception to raise, or None to write the file."""
        calls = []

        def fake(cand, images_dir, scene_number, log=print, should_stop=None, *, max_bytes, url=""):
            calls.append({"url": url or cand.url, "max_bytes": max_bytes})
            o = outcomes.pop(0)
            if o is not None:
                raise o
            path = Path(images_dir) / "002.mp4"
            path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 200)
            return path

        logs = []
        with mock.patch.object(stock_base, "download_candidate", fake), mock.patch.object(stock_base, "sniff_media_kind", return_value="video"):
            result = provider._download(self.scene, candidate, self.tmp, logs.append)
        return result, calls, logs

    def test_cap_is_200mb_off_and_1gb_on(self):
        _, calls, _ = self._run(self._provider(False), _candidate(fallback=False), [None])
        self.assertEqual(calls[0]["max_bytes"], 200 * 1024 * 1024)
        _, calls, _ = self._run(self._provider(True), _candidate(), [None])
        self.assertEqual(calls[0]["max_bytes"], 1024 * 1024 * 1024)

    def test_a_4k_file_over_the_cap_falls_back_to_the_hd_file(self):
        too_big = IOError("stock asset exceeded 1024MB, aborted")
        result, calls, logs = self._run(self._provider(True), _candidate(), [too_big, None])
        self.assertEqual(result.status, SceneStatus.READY)
        self.assertEqual([c["url"] for c in calls], ["https://x/uhd.mp4", "https://x/hd.mp4"])
        self.assertEqual(calls[1]["max_bytes"], 200 * 1024 * 1024)
        self.assertEqual((result.metadata["width"], result.metadata["height"]), (1920, 1080), "records the file actually used")
        self.assertTrue(any("using the 1920x1080 file instead" in m for m in logs))

    def test_a_broken_4k_download_also_falls_back(self):
        result, calls, _ = self._run(self._provider(True), _candidate(), [ConnectionError("reset"), None])
        self.assertEqual(result.status, SceneStatus.READY)
        self.assertEqual(len(calls), 2)

    def test_a_cancelled_download_never_falls_back(self):
        result, calls, _ = self._run(self._provider(True), _candidate(), [downloader.DownloadCancelled("download cancelled")])
        self.assertEqual(result.status, SceneStatus.FAILED)
        self.assertEqual(len(calls), 1)

    def test_no_fallback_fails_as_before(self):
        result, calls, _ = self._run(self._provider(False), _candidate(fallback=False), [IOError("HTTP 500")])
        self.assertEqual(result.status, SceneStatus.FAILED)
        self.assertIn("Download failed: HTTP 500", result.error)
        self.assertEqual(len(calls), 1)

    def test_both_files_failing_reports_both(self):
        result, _, _ = self._run(self._provider(True), _candidate(), [IOError("too big"), IOError("HTTP 404")])
        self.assertEqual(result.status, SceneStatus.FAILED)
        self.assertIn("too big", result.error)
        self.assertIn("HTTP 404", result.error)


class TestDownloaderCap(unittest.TestCase):
    """The real download_candidate: the cap passed in is the one enforced, and `url` overrides the candidate's."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, size, seen):
        def get(url, stream, timeout):
            seen.append(url)
            r = mock.MagicMock()
            r.__enter__.return_value = r
            r.headers = {"Content-Type": "video/mp4"}
            r.raise_for_status = lambda: None
            r.iter_content = lambda chunk_size: iter([b"x" * 1024] * (size // 1024))
            return r
        return get

    def test_cap_enforced_and_url_override(self):
        seen = []
        with mock.patch.object(downloader.requests, "get", self._get(8 * 1024, seen)):
            with self.assertRaises(IOError):
                downloader.download_candidate(_candidate(), self.tmp, "2", max_bytes=4 * 1024)
            self.assertFalse(any(self.tmp.iterdir()), "nothing half-written is left")
            path = downloader.download_candidate(_candidate(), self.tmp, "2", max_bytes=16 * 1024, url="https://x/hd.mp4")
        self.assertEqual(path.name, "002.mp4")
        self.assertEqual(seen, ["https://x/uhd.mp4", "https://x/hd.mp4"])


class TestSwitchPropagation(unittest.TestCase):
    def test_set_uhd_reaches_every_backend_and_forgets_old_searches(self):
        cache = StockCache()
        p = StockProvider(backends=[PexelsBackend("k"), PixabayBackend("k")], cache=cache)
        cache.set_search("pexels", "river", ["old"], "video")
        p.set_uhd(True)
        self.assertTrue(all(b.uhd for b in p.backends))
        self.assertIsNone(cache.get_search("pexels", "river", "video"), "results picked for HD are not reused for 4K")
        p.set_uhd(False)
        self.assertFalse(any(b.uhd for b in p.backends))


class TestAppWiring(unittest.TestCase):
    """Structural, like test_cache_storage_ui.py: the switch is in Settings and reaches every manager before fetching."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls.App = _app.VideoGeneratorApp

    def test_settings_has_both_switches_per_project(self):
        src = inspect.getsource(self.App._open_settings)
        self.assertIn("VIDEO QUALITY (THIS PROJECT)", src)
        self.assertIn("Accept Ultra HD (4K) footage", src)
        self.assertIn("Export in 4K", src)
        self.assertIn("set_quality_settings(uhd_footage=", src)

    def test_every_manager_gets_the_switch(self):
        self.assertIn("set_uhd(self._uhd_footage_on())", inspect.getsource(self.App._build_asset_manager))
        self.assertIn("_apply_footage_quality", inspect.getsource(self.App._ensure_asset_manager))
        src = inspect.getsource(self.App)
        for callback in ("_overscaled_run_manager = manager", "_hybrid_run_manager = manager", "_pakmap_run_manager = manager"):
            i = src.index(callback)
            self.assertIn("_apply_footage_quality(manager)", src[i - 300:i], callback)

    def test_apply_reads_the_open_project(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ws = create_project("Q", projects_root=tmp, when=date(2026, 10, 6))
            fake = mock.Mock(_workspace=ws)
            fake._uhd_footage_on = lambda: self.App._uhd_footage_on(fake)
            stock = StockProvider(backends=[PexelsBackend("k")], cache=StockCache())
            manager = mock.Mock(stock_provider=stock)
            self.App._apply_footage_quality(fake, manager)
            self.assertFalse(stock.uhd)
            ws.set_quality_settings(uhd_footage=True)
            self.App._apply_footage_quality(fake, manager)
            self.assertTrue(stock.uhd)
            fake._workspace = None
            self.App._apply_footage_quality(fake, manager)
            self.assertFalse(stock.uhd, "no project open: off")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
