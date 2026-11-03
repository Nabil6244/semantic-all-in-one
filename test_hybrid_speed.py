#!/usr/bin/env python3
"""Where a Hybrid run's time went (project 051, 2026-10-31), fixed for every style.

- An HD stock clip longer than 30 s keeps only its first 30 s (4K already did): whole 3-4 minute clips made one run fetch 1.9 GB.
  If the cut fails, the whole clip is downloaded as before; a cancelled download never falls back.
- Flow batches run alongside the stock downloads instead of after them.
- An explainer overlay whose frame fails to draw stops its ffmpeg (two were found waiting on their pipe two hours later).
- The map renderer encodes its pieces with x264 "faster" unless the spec asks otherwise.
Same results, less time (2026-11-04): place names are looked up by name instead of a scan of every region (project 004: 202 s -> 10 s
before the map is drawn), CSV rows find the narrator's words with cheap upper bounds first, and the channel name is laid on as its
corner only, read once (half the time, the same frames).
No network, no real ffmpeg for the stock and Flow tests.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from asset_manager import AssetManager
from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from providers.stock import base as stock_base
from providers.stock import downloader
from providers.stock.base import Candidate, StockProvider
from providers.stock.cache import StockCache
from providers.stock.pexels import PexelsBackend

ROOT = Path(__file__).resolve().parent


def _clip(duration):
    return Candidate(provider="pexels", asset_id="7", media_type=MediaType.VIDEO, url="https://x/hd.mp4",
                     width=1920, height=1080, duration=duration)


class TestHdClipKeepsFirstSeconds(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scene = SceneRow(scene_number="6", script_segment="x", asset_type="stock_video", stock="waves")
        self.provider = StockProvider(backends=[PexelsBackend("key")], cache=StockCache())   # HD: the 4K switch is off

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self):
        path = self.tmp / "006.mp4"
        path.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 200)
        return path

    def _run(self, candidate, partial_outcome=None):
        calls = []

        def partial(cand, images_dir, scene_number, seconds, *, max_bytes, should_stop=None, timeout_s=0):
            calls.append(("partial", seconds, max_bytes))
            if partial_outcome is not None:
                raise partial_outcome
            return self._write()

        def whole(cand, images_dir, scene_number, log=print, should_stop=None, *, max_bytes, url=""):
            calls.append(("whole", max_bytes))
            return self._write()

        logs = []
        with mock.patch.object(stock_base, "download_first_seconds", partial), \
             mock.patch.object(stock_base, "download_candidate", whole), \
             mock.patch.object(stock_base, "sniff_media_kind", return_value="video"):
            result = self.provider._download(self.scene, candidate, self.tmp, logs.append)
        return result, calls, logs

    def test_a_long_hd_clip_keeps_its_first_30s(self):
        result, calls, logs = self._run(_clip(218))
        self.assertEqual(result.status, SceneStatus.READY)
        self.assertEqual(calls, [("partial", downloader.UHD_KEEP_SECONDS, downloader.MAX_BYTES)])
        self.assertTrue(any("keeping the first 30s of a 218s clip" in m for m in logs))

    def test_a_short_clip_downloads_whole_as_before(self):
        _, calls, _ = self._run(_clip(12))
        self.assertEqual(calls, [("whole", downloader.MAX_BYTES)])

    def test_a_failed_cut_downloads_the_whole_clip(self):
        result, calls, logs = self._run(_clip(255), RuntimeError("ffmpeg could not save the first 30s"))
        self.assertEqual(result.status, SceneStatus.READY)
        self.assertEqual([c[0] for c in calls], ["partial", "whole"])
        self.assertTrue(any("downloading the whole clip" in m for m in logs))

    def test_a_cancelled_cut_never_falls_back(self):
        result, calls, _ = self._run(_clip(255), downloader.DownloadCancelled("download cancelled"))
        self.assertEqual(result.status, SceneStatus.FAILED)
        self.assertEqual([c[0] for c in calls], ["partial"])


class _Provider(AssetProvider):
    def __init__(self, source, media_type, on_resolve=None):
        self.source, self.media_type, self.on_resolve = source, media_type, on_resolve

    def resolve(self, scene, images_dir, log=print):
        if self.on_resolve:
            self.on_resolve(scene)
        ext = ".mp4" if self.media_type == MediaType.VIDEO else ".png"
        path = Path(images_dir) / f"{int(scene.scene_number):03d}{ext}"
        path.write_bytes(b"fake")
        return AssetResult(scene.scene_number, path, self.media_type, self.source, SceneStatus.READY,
                           metadata={"provider_asset_id": f"a{scene.scene_number}"})

    def regenerate(self, scene, images_dir, exclude=None, log=print):
        return self.resolve(scene, images_dir, log=log)


class TestFlowRunsAlongsideStock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rows(self):
        return [SceneRow.from_csv_row({"scene_number": "1", "script_segment": "a", "asset_type": "stock_video", "stock": "sea"}),
                SceneRow.from_csv_row({"scene_number": "2", "script_segment": "b", "asset_type": "image", "prompt": "a map"})]

    def test_flow_starts_before_the_stock_downloads_finish(self):
        flow_started = threading.Event()
        # the stock download only finishes once Flow has begun: run one after the other, this would wait forever
        stock = _Provider(AssetSource.STOCK_VIDEO, MediaType.VIDEO, on_resolve=lambda s: self.assertTrue(flow_started.wait(10)))
        flow = _Provider(AssetSource.FLOW_IMAGE, MediaType.IMAGE, on_resolve=lambda s: flow_started.set())
        mgr = AssetManager(self.tmp, stock_provider=stock, flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows())
        self.assertTrue(summary.ok, [r.error for r in summary.failed])
        self.assertEqual(summary.results["2"].source, AssetSource.FLOW_IMAGE)

    def test_a_flow_crash_still_reaches_the_caller(self):
        stock = _Provider(AssetSource.STOCK_VIDEO, MediaType.VIDEO)
        flow = _Provider(AssetSource.FLOW_IMAGE, MediaType.IMAGE)
        mgr = AssetManager(self.tmp, stock_provider=stock, flow_image_provider=flow, log=lambda *_: None)
        with mock.patch.object(mgr, "_resolve_flow_batch", side_effect=KeyboardInterrupt("stop")):
            with self.assertRaises(KeyboardInterrupt):
                mgr.resolve_all(self._rows())


class TestOverlayEncoderNeverLeftWaiting(unittest.TestCase):
    def test_a_failed_frame_stops_ffmpeg(self):
        from explainer.beats import overlay

        proc = mock.MagicMock()
        with mock.patch.object(overlay.subprocess, "Popen", return_value=proc), \
             mock.patch.object(overlay, "frame_key", return_value="k"), \
             mock.patch.object(overlay, "draw_frame", side_effect=ValueError("bad frame")):
            with self.assertRaises(ValueError):
                overlay.render_overlay({"start": 0.0, "end": 1.0}, "/tmp/never.mov")
        proc.kill.assert_called_once()
        proc.stdin.close.assert_not_called()


class TestMapPiecesEncodeFaster(unittest.TestCase):
    def test_default_preset_is_faster(self):
        src = (ROOT / "pakmap-engine" / "render.mjs").read_text(encoding="utf-8")
        self.assertIn("spec.x264_preset || 'faster'", src)
        self.assertNotIn("spec.x264_preset || 'medium'", src)


class TestPlaceLookupByName(unittest.TestCase):
    def test_the_name_index_finds_what_the_scan_found(self):
        from map_scene import places as P

        for ds in ("countries", "admin1"):
            feats = P._dataset(ds)
            for f in feats[::max(1, len(feats) // 150)]:
                for key in P._names(f):
                    scan = [g for g in feats if key in P._names(g)]
                    self.assertEqual([id(g) for g in P._match(ds, key)], [id(g) for g in scan], f"{ds}: {key}")

    def test_the_label_point_is_the_same_arithmetic(self):
        from map_scene import places as P

        segs = [((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (4.0, 3.0)), ((4.0, 3.0), (0.0, 0.0)), ((1.0, 1.0), (1.0, 1.0))]
        packed = [(x0, y0, x1 - x0, y1 - y0, ((x1 - x0) ** 2 + (y1 - y0) ** 2) or 1e-12) for (x0, y0), (x1, y1) in segs]
        for x, y in ((1.5, 0.7), (3.9, 2.0), (-2.0, 5.0), (1.0, 1.0)):
            self.assertEqual(P._nearest_segment(x, y, packed), min(P._dist_to_ring(x, y, [a, b]) for a, b in segs))


class TestNarrationMatchSameAnswers(unittest.TestCase):
    def test_same_and_nearest_answer_as_a_plain_ratio(self):
        import difflib

        from pakmap import anchor as A

        pairs = [("marchlyn", "marchlin"), ("llanberis", "lamberis"), ("generator", "generators"), ("dinorwig", "dinorwic"), ("mountain", "fountain"),
                 ("hydro", "hydra"), ("electric", "eclectic"), ("snowdonia", "snowdon")]
        for a, b in pairs:
            plain = a == b or A._stem(a) == A._stem(b) or difflib.SequenceMatcher(None, a, b).ratio() >= 0.84
            self.assertEqual(A.same(a, b), plain, (a, b))
        t = A.Transcript([(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("from a visitor center in lamberis the tour goes into elidir".split())])
        self.assertEqual(t.nearest("visitor centre in Llanberis"), ("visitor center in lamberis", 1.0))


class TestChannelNameCornerOnly(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_the_frames_match_the_whole_frame_overlay(self):
        from hybrid.generate import add_watermark, watermark_png

        d = Path(tempfile.mkdtemp())
        try:
            v = d / "v.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v)], check=True)
            wm = {"text": "My Channel"}
            png = watermark_png(wm, (640, 360), d / "full.png")
            old = d / "old.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(v), "-loop", "1", "-i", str(png), "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1:format=auto[v]",
                            "-map", "[v]", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(old)], check=True)
            self.assertEqual(add_watermark(v, wm, d), "")

            def frames(p):
                out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "framemd5", "-"], capture_output=True, text=True, check=True).stdout
                return [ln.split(",")[-1] for ln in out.splitlines() if ln and not ln.startswith("#")]

            self.assertEqual(frames(v), frames(old))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
