#!/usr/bin/env python3
"""The per-project "Accept Ultra HD (4K) footage" switch (steps 1-3 of 4K support).

Off (default): stock picks and the 200 MB cap are exactly as before. On: Pexels/Pixabay pick the 4K file, the cap is 1 GB per
clip, and a 4K download that fails falls back to the same clip's HD file instead of failing the scene. A 4K clip longer than
30 s keeps only its first 30 s (read, not re-encoded), and a run warns when the disk looks too small. No internet: the
partial-download tests use a local web server. With the switch on, ranking prefers sharper files when relevance ties,
Pexels photos download full size, and every READY scene shows its real resolution.
"""

from __future__ import annotations

import functools
import http.server
import inspect
import json
import shutil
import subprocess
import tempfile
import threading
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


class TestDownloaderCleansUpLikeWindows(unittest.TestCase):
    """Windows cannot delete a file that is still open. The downloader must close the .part file before deleting it, or a
    cap / stop / dropped connection leaves it behind (this failed on the Windows CI before the fix)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, chunks, **kw):
        import builtins
        import pathlib

        open_paths = set()
        real_open, real_unlink = builtins.open, pathlib.Path.unlink

        class Tracked:
            def __init__(self, path, *a, **k):
                self.path, self.f = str(Path(path)), real_open(path, *a, **k)
                open_paths.add(self.path)

            def __enter__(self):
                return self.f

            def __exit__(self, *exc):
                self.f.close()
                open_paths.discard(self.path)

        def windows_unlink(path, missing_ok=False):
            if str(path) in open_paths:
                raise PermissionError(f"[WinError 32] The process cannot access the file: {path}")
            return real_unlink(path, missing_ok=missing_ok)

        def get(url, stream, timeout):
            r = mock.MagicMock()
            r.__enter__.return_value = r
            r.headers = {"Content-Type": "video/mp4"}
            r.raise_for_status = lambda: None
            r.iter_content = lambda chunk_size: iter(chunks)
            return r

        with mock.patch.object(downloader.requests, "get", get), mock.patch("providers.stock.downloader.open", Tracked, create=True), \
                mock.patch.object(pathlib.Path, "unlink", windows_unlink):
            return downloader.download_candidate(_candidate(), self.tmp, "2", **kw)

    def test_over_the_cap(self):
        with self.assertRaises(IOError) as ctx:
            self._run([b"x" * 1024] * 8, max_bytes=4 * 1024)
        self.assertIn("exceeded", str(ctx.exception), "the real reason, not a file-in-use error")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_stopped(self):
        with self.assertRaises(downloader.DownloadCancelled):
            self._run([b"x" * 1024] * 8, should_stop=lambda: True)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_connection_dropped_mid_download(self):
        def chunks():
            yield b"x" * 1024
            raise ConnectionError("connection reset")

        with self.assertRaises(ConnectionError):
            self._run(chunks())
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_a_good_download_still_lands(self):
        self.assertEqual(self._run([b"x" * 1024] * 2).name, "002.mp4")


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
        # The section lives in the "This project" tab (saved with the project, not app-wide).
        self.assertIn('body = tab_bodies["This project"]', src)
        self.assertLess(src.index('body = tab_bodies["This project"]'), src.index('text="VIDEO QUALITY"'))
        self.assertIn("Accept Ultra HD (4K) footage", src)
        self.assertIn('text="Export in 4K"', src)
        self.assertIn("set_quality_settings(uhd_footage=", src)
        self.assertIn("set_quality_settings(export_4k=", src)
        self.assertNotIn('state="disabled", font', src, "the export switch is live now")

    def test_4k_export_reaches_every_style(self):
        for fn in (self.App._run_hybrid_generation, self.App._run_pakmap_generation, self.App._run_overscaled_generation):
            src = inspect.getsource(fn)
            self.assertIn("pixel_scale = self._export_pixel_scale()", src, fn.__name__)
            self.assertIn("pixel_scale=pixel_scale", src, fn.__name__)
        src = inspect.getsource(self.App)
        self.assertIn('"resolution": "3840x2160" if self._export_pixel_scale() == 2 else "1920x1080"', src, "normal style config")
        self.assertIn('resolution=config.get("resolution") or "1920x1080"', src, "normal style render call")
        tmp = Path(tempfile.mkdtemp())
        try:
            ws = create_project("E", projects_root=tmp, when=date(2026, 10, 6))
            fake = mock.Mock(_workspace=ws)
            self.assertEqual(self.App._export_pixel_scale(fake), 1)
            ws.set_quality_settings(export_4k=True)
            self.assertEqual(self.App._export_pixel_scale(fake), 2)
            fake._workspace = None
            self.assertEqual(self.App._export_pixel_scale(fake), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_badges_warn_below_4k_when_the_project_exports_4k(self):
        src = inspect.getsource(self.App._show_scene_resolution)
        self.assertIn("2160 if self._export_pixel_scale() == 2 else 1080", src)
        self.assertIn("export_height=export_height", src)

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


HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height",
                          "-select_streams", "v:0", "-of", "json", str(path)], capture_output=True, text=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return float(d["format"]["duration"]), s["codec_name"], s["width"], s["height"]


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe needed")
class TestFirstSecondsDownload(unittest.TestCase):
    """download_first_seconds against a real (local) web server, like a stock CDN."""

    @classmethod
    def setUpClass(cls):
        cls.site = Path(tempfile.mkdtemp())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=120",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        str(cls.site / "long.mp4")], check=True)
        cls.served = []

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def copyfile(self, source, outputfile):   # count what the client actually reads
                total = 0
                try:
                    while chunk := source.read(16 * 1024):
                        outputfile.write(chunk)
                        total += len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                cls.served.append(total)

        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(cls.site)))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.site, ignore_errors=True)

    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        type(self).served.clear()

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def _cand(self, name="long.mp4"):
        return Candidate(provider="pexels", asset_id="1", media_type=MediaType.VIDEO, url=f"{self.base}/{name}",
                         width=640, height=360, duration=120)

    def test_keeps_30s_unchanged_and_reads_only_part_of_the_file(self):
        path = downloader.download_first_seconds(self._cand(), self.out, "2", 30)
        self.assertEqual(path.name, "002.mp4")
        dur, codec, w, h = _probe(path)
        self.assertAlmostEqual(dur, 30, delta=0.6)
        self.assertEqual((codec, w, h), ("h264", 640, 360), "copied, not re-encoded or resized")
        full = (self.site / "long.mp4").stat().st_size
        self.assertLess(sum(self.served), full * 0.5, "only about the first quarter of the file is downloaded")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["002.mp4"])

    def test_stop_cancels_and_leaves_nothing(self):
        with self.assertRaises(downloader.DownloadCancelled):
            downloader.download_first_seconds(self._cand(), self.out, "2", 30, should_stop=lambda: True)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_size_cap_aborts_and_leaves_nothing(self):
        with self.assertRaises(IOError) as ctx:
            downloader.download_first_seconds(self._cand(), self.out, "2", 30, max_bytes=50 * 1024)
        self.assertIn("exceeded", str(ctx.exception))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_a_missing_file_is_an_error_not_an_empty_clip(self):
        with self.assertRaises(RuntimeError):
            downloader.download_first_seconds(self._cand("missing.mp4"), self.out, "2", 30)
        self.assertEqual(list(self.out.iterdir()), [])


class TestPartialAndDiskInProvider(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scene = SceneRow(scene_number="2", script_segment="x", asset_type="stock_video", stock="river")
        self.p = StockProvider(backends=[PexelsBackend("key")], cache=StockCache())
        self.p.set_uhd(True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, candidate, partial_outcome=None, free=1 << 50):
        calls = []

        def write(name="002.mp4"):
            path = self.tmp / name
            path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 200)
            return path

        def fake_full(cand, images_dir, scene_number, log=print, should_stop=None, *, max_bytes, url=""):
            calls.append(("full", url or cand.url))
            return write()

        def fake_partial(cand, images_dir, scene_number, seconds, *, max_bytes, should_stop=None):
            calls.append(("first", cand.url, seconds))
            if partial_outcome is not None:
                raise partial_outcome
            return write()

        with mock.patch.object(stock_base, "download_candidate", fake_full), \
                mock.patch.object(stock_base, "download_first_seconds", fake_partial), \
                mock.patch.object(stock_base._dl, "free_bytes", return_value=free), \
                mock.patch.object(stock_base, "sniff_media_kind", return_value="video"):
            result = self.p._download(self.scene, candidate, self.tmp, lambda m: None)
        return result, calls

    def _cand(self, duration):
        c = _candidate()
        c.duration = duration
        return c

    def test_a_long_4k_clip_keeps_its_first_30s(self):
        result, calls = self._run(self._cand(48))
        self.assertEqual(calls, [("first", "https://x/uhd.mp4", 30.0)])
        self.assertEqual(result.metadata["duration"], 30.0)

    def test_a_short_clip_is_downloaded_whole(self):
        result, calls = self._run(self._cand(20))
        self.assertEqual(calls, [("full", "https://x/uhd.mp4")])
        self.assertEqual(result.metadata["duration"], 20)

    def test_switch_off_never_cuts(self):
        self.p.set_uhd(False)
        _, calls = self._run(self._cand(48))
        self.assertEqual(calls[0][0], "full")

    def test_a_failed_partial_download_falls_back_to_the_hd_file(self):
        result, calls = self._run(self._cand(48), partial_outcome=RuntimeError("ffmpeg could not save"))
        self.assertEqual(calls[-1], ("full", "https://x/hd.mp4"))
        self.assertEqual((result.metadata["width"], result.metadata["height"]), (1920, 1080))

    def test_low_disk_goes_straight_to_the_hd_file(self):
        result, calls = self._run(self._cand(48), free=2 * 1024 ** 3)
        self.assertEqual(calls, [("full", "https://x/hd.mp4")], "no 4K attempt with under 3 GB free")
        self.assertEqual(result.status, SceneStatus.READY)


class TestDiskWarning(unittest.TestCase):
    def test_space_needed(self):
        self.assertEqual(downloader.uhd_space_needed(0), 2 * 1024 ** 3)
        self.assertEqual(downloader.uhd_space_needed(10), 10 * 300 * 1024 ** 2 + 2 * 1024 ** 3)

    def test_free_bytes_of_a_folder_not_created_yet(self):
        self.assertGreater(downloader.free_bytes(Path(tempfile.gettempdir()) / "no" / "such" / "dir"), 0)

    def test_generate_checks_first_and_counts_only_stock_video_rows(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available: {exc}")
        App = _app.VideoGeneratorApp
        self.assertIn("if not self._uhd_disk_ok():", inspect.getsource(App._on_generate).split("generation_mode")[0])
        rows = [SceneRow(scene_number=str(i), script_segment="x", asset_type=t, stock="q")
                for i, t in enumerate(["stock_video", "stock_video", "stock_image", "stock", "flow_image"], 1)]
        fake = mock.Mock(_workspace=mock.Mock(root=Path(tempfile.gettempdir())), _scene_rows=rows, _uhd_footage_on=lambda: True)
        with mock.patch("providers.stock.downloader.free_bytes", return_value=1 << 50):
            self.assertTrue(App._uhd_disk_ok(fake))
        with mock.patch("providers.stock.downloader.free_bytes", return_value=1024 ** 3), \
                mock.patch.object(_app.messagebox, "askyesno", return_value=False) as ask:
            self.assertFalse(App._uhd_disk_ok(fake), "the user said no")
        self.assertIn("3 stock video clip(s)", ask.call_args[0][1])
        fake._uhd_footage_on = lambda: False
        self.assertTrue(App._uhd_disk_ok(fake), "switch off: never asks")


class TestRankingPrefersSharperFiles(unittest.TestCase):
    def _q(self, w, h, uhd, media="video"):
        from providers.media_quality.scoring import quality_score

        return quality_score(width=w, height=h, download_url="https://x/a.mp4", provider="pexels", media_type=media, duration=10, uhd=uhd)

    def test_off_is_unchanged_and_on_climbs_to_4k(self):
        self.assertGreater(self._q(1920, 1080, False), self._q(3840, 2160, False), "off: the old HD preference stays")
        self.assertLess(self._q(1920, 1080, True), self._q(2560, 1440, True))
        self.assertLess(self._q(2560, 1440, True), self._q(3840, 2160, True))
        self.assertEqual(self._q(3840, 2160, True), self._q(7680, 4320, True), "nothing extra past 4K")
        self.assertLessEqual(self._q(3840, 2160, True) - self._q(1920, 1080, True), 0.26, "a tie-breaker only")
        self.assertLess(self._q(1280, 720, True), self._q(1920, 1080, True))

    def _cands(self, tags_4k="river aerial", tags_hd="river aerial"):
        mk = lambda i, w, h, tags: Candidate(provider="pexels", asset_id=str(i), media_type=MediaType.VIDEO, url=f"https://x/{i}.mp4",  # noqa: E731
                                             width=w, height=h, duration=12, extra={"tags": tags})
        return [mk(1, 1920, 1080, tags_hd), mk(2, 3840, 2160, tags_4k)]

    def test_equal_relevance_picks_4k_only_when_on(self):
        from providers.stock.ranking import rank_candidates

        scene = SceneRow(scene_number="1", script_segment="a river from above", asset_type="stock_video", stock="river aerial")
        self.assertEqual(rank_candidates(self._cands(), "river aerial", set(), scene=scene, uhd=False)[0].width, 1920)
        self.assertEqual(rank_candidates(self._cands(), "river aerial", set(), scene=scene, uhd=True)[0].width, 3840)

    def test_relevance_still_beats_resolution(self):
        from providers.stock.ranking import rank_candidates

        scene = SceneRow(scene_number="1", script_segment="x", asset_type="stock_video", stock="river aerial")
        ranked = rank_candidates(self._cands(tags_4k="office desk laptop"), "river aerial", set(), scene=scene, uhd=True)
        self.assertEqual(ranked[0].width, 1920, "a relevant 1080p clip beats an unrelated 4K one")

    def test_provider_passes_its_switch_to_ranking(self):
        self.assertIn("uhd=self.uhd", inspect.getsource(StockProvider._pick))


class TestPexelsPhotos(unittest.TestCase):
    PHOTO = {"id": 5, "width": 5800, "height": 3673, "photographer": "C", "url": "https://pexels/p/5", "alt": "river",
             "src": {"original": "https://pexels/orig.jpeg", "large2x": "https://pexels/l2x.jpeg", "large": "https://pexels/l.jpeg", "tiny": ""}}

    def _photo(self, uhd):
        b = PexelsBackend("key")
        b.uhd = uhd
        b._session = mock.Mock(get=mock.Mock(return_value=_resp({"photos": [self.PHOTO]})))
        return b._search_photos("river", 5)[0]

    def test_off_keeps_large2x(self):
        c = self._photo(False)
        self.assertEqual(c.url, "https://pexels/l2x.jpeg")
        self.assertNotIn("hd_fallback", c.extra)

    def test_on_takes_the_full_size_photo_with_large2x_as_fallback(self):
        c = self._photo(True)
        self.assertEqual(c.url, "https://pexels/orig.jpeg")
        fb = c.extra["hd_fallback"]
        self.assertEqual(fb["url"], "https://pexels/l2x.jpeg")
        self.assertEqual((fb["width"], fb["height"]), (1880, 1191), "large2x fits inside 1880x1300")


class TestResolutionTag(unittest.TestCase):
    def setUp(self):
        import media_size

        self.ms = media_size
        media_size.clear()
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tags(self):
        cases = {(3840, 2160): "4K", (4096, 2160): "4K", (3840, 1600): "4K", (5800, 3673): "4K", (2560, 1440): "1440p",
                 (1920, 1080): "1080p", (1920, 1072): "1080p", (1080, 1920): "1080p", (1880, 1191): "1080p",
                 (1280, 720): "720p ⚠", (854, 480): "SD ⚠"}
        for (w, h), want in cases.items():
            self.assertEqual(self.ms.resolution_tag(w, h), want, (w, h))
        self.assertEqual(self.ms.resolution_tag(1920, 1080, export_height=2160), "1080p ⚠", "a 4K export would flag 1080p")

    def test_reads_the_real_file_and_follows_changes(self):
        from PIL import Image

        p = self.tmp / "001.png"
        Image.new("RGB", (1280, 720)).save(p)
        self.assertEqual(self.ms.probe_size(p), (1280, 720))
        Image.new("RGB", (3840, 2160)).save(p)
        self.assertEqual(self.ms.probe_size(p), (3840, 2160), "a replaced file is measured again")
        self.assertIsNone(self.ms.probe_size(self.tmp / "missing.png"))
        (self.tmp / "junk.mp4").write_bytes(b"not a video")
        self.assertIsNone(self.ms.probe_size(self.tmp / "junk.mp4"))

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe needed")
    def test_reads_video_size(self):
        p = self.tmp / "002.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=10:duration=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True)
        self.assertEqual(self.ms.probe_size(p), (1280, 720))

    def test_visual_plan_shows_it_on_ready_rows(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available: {exc}")
        App = _app.VideoGeneratorApp
        self.assertIn("self._show_scene_resolution(scene_number, label)", inspect.getsource(App._set_scene_status))
        src = inspect.getsource(App._show_scene_resolution)
        self.assertIn("gen != self._scene_render_gen", src, "never paints onto a rebuilt list")
        self.assertIn('cget("text") != ready_text', src, "never overwrites a newer status")
        self.assertIn('("Status", 118)', inspect.getsource(App), "header matches the wider status column")


def _ink_bbox(img):
    """Bounding box of everything drawn on a transparent image."""
    return img.getchannel("A").getbbox()


class TestNormalStyleCaptions(unittest.TestCase):
    def test_captions_keep_their_look_at_4k(self):
        import video_generator as vg
        from PIL import Image

        tmp = Path(tempfile.mkdtemp())
        try:
            hd = Image.open(vg.render_caption_overlay("A caption line to read on screen", tmp / "hd.png", 1920, 1080))
            uhd = Image.open(vg.render_caption_overlay("A caption line to read on screen", tmp / "uhd.png", 3840, 2160))
            (x0, y0, x1, y1), (u0, v0, u1, v1) = _ink_bbox(hd), _ink_bbox(uhd)
            self.assertAlmostEqual((u1 - u0) / (x1 - x0), 2.0, delta=0.08, msg="twice as wide at 4K")
            self.assertAlmostEqual((v1 - v0) / (y1 - y0), 2.0, delta=0.15, msg="twice as tall at 4K")
            self.assertAlmostEqual(v1 / 2, y1, delta=4, msg="same place on screen")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestOverscaledScale(unittest.TestCase):
    def _layout(self):
        from scene_graph.layout import NodeRect, SceneGraphLayout

        return SceneGraphLayout(
            canvas_width=1920, canvas_height=1080,
            node_rects={"n1": NodeRect(node_id="n1", x=100.0, y=200.0, width=640.0, height=360.0)},
            active_windows={"n1": (0.0, 5.0)}, checklist_band_px=110.0,
            edge_routes={"e1": [(10.0, 20.0), (30.0, 40.0)]}, edge_label_positions={"e1": (5.0, 6.0)},
            caption_positions={"n1": (0.0, 12.0)}, title_x_px=300.0,
            node_ken_burns={"n1": {"zoom_end": 1.08, "pan_x": 0.02, "pan_y": -0.01}},
        )

    def test_scale_layout_doubles_geometry_only(self):
        from scene_graph.layout import SceneGraphLayout, scale_layout

        base = self._layout()
        self.assertIs(scale_layout(base, 1.0), base)
        big = scale_layout(base, 2.0)
        self.assertEqual((big.canvas_width, big.canvas_height, big.ui_scale), (3840, 2160, 2.0))
        r = big.node_rects["n1"]
        self.assertEqual((r.x, r.y, r.width, r.height), (200.0, 400.0, 1280.0, 720.0))
        self.assertEqual(big.checklist_band_px, 220.0)
        self.assertEqual(big.edge_routes["e1"], [(20.0, 40.0), (60.0, 80.0)])
        self.assertEqual((big.edge_label_positions["e1"], big.caption_positions["n1"], big.title_x_px), ((10.0, 12.0), (0.0, 24.0), 600.0))
        self.assertEqual(big.active_windows, base.active_windows, "timing is unchanged")
        self.assertEqual(big.node_ken_burns, base.node_ken_burns, "Ken Burns values are fractions")
        self.assertEqual(SceneGraphLayout.from_dict(big.to_dict()).ui_scale, 2.0)
        self.assertNotIn("ui_scale", base.to_dict(), "a 1080p layout file is unchanged")

    def test_drawing_scale_doubles_fixed_sizes_and_defaults_to_one(self):
        from scene_graph.composition import _UI_SCALE, render_checklist_strip_frame, render_title_reveal_frame, ui_scale

        self.assertEqual(_UI_SCALE.get(), 1.0)
        hd = render_title_reveal_frame("The Dream", canvas_size=(1920, 1080), top_margin=60, progress=1.0)
        with ui_scale(2.0):
            uhd = render_title_reveal_frame("The Dream", canvas_size=(3840, 2160), top_margin=120, progress=1.0)
            strip_uhd = render_checklist_strip_frame(["One", "Two"], 0, canvas_size=(3840, 2160), band_height=220, margin_px=120)
        self.assertEqual(_UI_SCALE.get(), 1.0, "the scale ends with the block")
        strip_hd = render_checklist_strip_frame(["One", "Two"], 0, canvas_size=(1920, 1080), band_height=110, margin_px=60)
        for a, b in ((_ink_bbox(hd), _ink_bbox(uhd)), (_ink_bbox(strip_hd), _ink_bbox(strip_uhd))):
            self.assertAlmostEqual((b[2] - b[0]) / (a[2] - a[0]), 2.0, delta=0.06)
            self.assertAlmostEqual((b[3] - b[1]) / (a[3] - a[1]), 2.0, delta=0.12)

    def test_pipeline_and_export_get_the_scale(self):
        from scene_graph import app_integration, pipeline

        self.assertEqual(app_integration._scaled_resolution("1920x1080", 2), "3840x2160")
        self.assertEqual(app_integration._scaled_resolution("1920x1080", 1), "1920x1080")
        self.assertIn("pixel_scale=pixel_scale", inspect.getsource(app_integration.generate_overscaled_video))
        self.assertIn("_scaled_resolution(resolution, pixel_scale)", inspect.getsource(app_integration.generate_overscaled_video))
        self.assertIn("scale_layout(layout", inspect.getsource(pipeline.run_overscaled_pipeline))


if __name__ == "__main__":
    unittest.main()
