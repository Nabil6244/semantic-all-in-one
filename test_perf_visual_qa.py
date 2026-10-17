"""Visual QA speed-ups must not change a single verdict.

1. visual_qa.technical: complete PNG / JPEG / WebP stills are probed from the
   header in-process instead of spawning ffprobe. Every (duration, width,
   height) must equal ffprobe's exactly, on every kind of still the app can
   meet, and anything uncertain must still go to ffprobe.
2. visual_qa.cache: the cache JSON is kept in memory for the run and written
   coalesced + atomically. Results must be identical, the file must always be
   valid JSON (crash, concurrent threads, concurrent processes), and outside
   writers / deletions must still be seen.

Run: /opt/miniconda3/bin/python3.13 -m unittest test_perf_visual_qa -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus  # noqa: E402
from visual_qa import cache as vqa_cache  # noqa: E402
from visual_qa import technical  # noqa: E402
from visual_qa.models import VisualQAResult, VisualQAStatus  # noqa: E402
from visual_qa.scorer import evaluate_scene_asset  # noqa: E402

HAVE_FF = bool(shutil.which("ffprobe") and shutil.which("ffmpeg"))


def ffprobe_reference(path: Path):
    """The pre-change probe, verbatim: what every file must still return."""
    proc = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if proc.returncode != 0:
        return None, 0, 0
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None, 0, 0
    streams = data.get("streams") or []
    w = h = 0
    if streams and isinstance(streams[0], dict):
        w = int(streams[0].get("width") or 0)
        h = int(streams[0].get("height") or 0)
    dur_raw = (data.get("format") or {}).get("duration")
    return (float(dur_raw) if dur_raw else None), w, h


# name -> expected to take the in-process fast path?
def build_media(d: Path) -> dict:
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(7)

    def rgb(w, h):
        return Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8))

    fast = {}

    def save(name, im, is_fast, **kw):
        im.save(d / name, **kw)
        fast[name] = is_fast

    save("rgb.png", rgb(640, 360), True)
    save("rgba.png", rgb(640, 360).convert("RGBA"), True)
    save("gray.png", rgb(320, 200).convert("L"), True)
    save("gray_alpha.png", rgb(300, 200).convert("LA"), True)
    save("palette.png", rgb(400, 225).convert("P"), True)
    save("bilevel.png", rgb(400, 225).convert("1"), True)
    save("gray16.png", Image.fromarray(rng.integers(0, 65535, (360, 640), dtype=np.uint16)), True)
    save("UPPER.PNG", rgb(200, 100), True)
    save("one.png", rgb(1, 1), True)
    save("q.jpg", rgb(640, 360), True, quality=85)
    save("prog.jpg", rgb(640, 360), True, quality=85, progressive=True)
    save("portrait.jpg", rgb(360, 640), True)
    save("gray.jpg", rgb(500, 300).convert("L"), True)
    save("cmyk.jpg", rgb(640, 360).convert("CMYK"), True)
    save("q100_444.jpeg", rgb(640, 360), True, quality=100, subsampling=0)
    save("UPPER.JPEG", rgb(640, 360), True)
    save("icc.jpg", rgb(640, 360), True, icc_profile=b"\0" * 200)
    for o in (3, 6, 8):
        im = rgb(640, 360)
        ex = im.getexif()
        ex[0x0112] = o
        save(f"exif_rot{o}.jpg", im, True, exif=ex)
    save("lossy.webp", rgb(640, 360), True, quality=80)
    save("lossless.webp", rgb(320, 180), True, lossless=True)
    save("alpha.webp", rgb(320, 180).convert("RGBA"), True)
    # -> ffprobe
    save("tiny.jpg", rgb(8, 8), False, quality=10)        # fits ffprobe's 2 KB probe: jpeg_pipe
    save("small.jpg", rgb(48, 48), False, quality=50)     # < 16 KiB guard
    frames = [rgb(160, 120) for _ in range(3)]
    frames[0].save(d / "anim.webp", save_all=True, append_images=frames[1:], duration=100)
    fast["anim.webp"] = False
    frames[0].save(d / "apng.png", save_all=True, append_images=frames[1:], duration=100)
    fast["apng.png"] = False
    frames[0].save(d / "anim.gif", save_all=True, append_images=frames[1:], duration=100)
    fast["anim.gif"] = False
    save("still.gif", rgb(160, 120), False)
    save("img.bmp", rgb(160, 120), False)
    save("img.tiff", rgb(160, 120), False)
    (d / "png_as.jpg").write_bytes((d / "rgb.png").read_bytes()); fast["png_as.jpg"] = False
    (d / "jpg_as.png").write_bytes((d / "q.jpg").read_bytes()); fast["jpg_as.png"] = False
    (d / "webp_as.png").write_bytes((d / "lossy.webp").read_bytes()); fast["webp_as.png"] = False
    b = (d / "rgb.png").read_bytes()
    (d / "trunc.png").write_bytes(b[: len(b) // 3]); fast["trunc.png"] = False
    (d / "header_only.png").write_bytes(b[:64]); fast["header_only.png"] = False
    b = (d / "q.jpg").read_bytes()
    (d / "trunc.jpg").write_bytes(b[: len(b) // 3]); fast["trunc.jpg"] = False
    (d / "trailing.jpg").write_bytes(b + b"\0\0junk"); fast["trailing.jpg"] = False
    b = (d / "lossy.webp").read_bytes()
    (d / "trunc.webp").write_bytes(b[: len(b) // 2]); fast["trunc.webp"] = False
    (d / "garbage.png").write_bytes(b"not an image at all" * 10); fast["garbage.png"] = False
    (d / "empty.png").write_bytes(b""); fast["empty.png"] = False
    (d / "sig_only.png").write_bytes(b"\x89PNG\r\n\x1a\n"); fast["sig_only.png"] = False
    ff = [shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi"]
    subprocess.run(ff + ["-i", "testsrc=size=640x360:rate=25:duration=1.2", "-pix_fmt", "yuv420p",
                         str(d / "clip.mp4")], check=True)
    fast["clip.mp4"] = False
    subprocess.run(ff + ["-i", "testsrc=size=360x640:rate=25:duration=0.5", str(d / "vertical.webm")], check=True)
    fast["vertical.webm"] = False
    subprocess.run(ff + ["-i", "testsrc=size=1280x720:rate=25:duration=1", "-frames:v", "1",
                         str(d / "ffmpeg_frame.png")], check=True)
    fast["ffmpeg_frame.png"] = True
    subprocess.run(ff + ["-i", "testsrc=size=1280x720:rate=25:duration=1", "-frames:v", "1", "-q:v", "2",
                         str(d / "ffmpeg_frame.jpg")], check=True)
    fast["ffmpeg_frame.jpg"] = (d / "ffmpeg_frame.jpg").stat().st_size >= technical._JPEG_MIN_FAST_BYTES
    (d / "clip_named.png").write_bytes((d / "clip.mp4").read_bytes()); fast["clip_named.png"] = False
    return fast


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class TestStillProbeMatchesFfprobe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.media = Path(cls._tmp.name) / "media"
        cls.media.mkdir()
        cls.fast = build_media(cls.media)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_probe_identical_to_ffprobe_for_every_file(self):
        for name in sorted(self.fast):
            with self.subTest(name):
                self.assertEqual(technical.probe_local_media(self.media / name),
                                 ffprobe_reference(self.media / name))

    def test_fast_path_taken_only_where_certain(self):
        for name, expected in sorted(self.fast.items()):
            with self.subTest(name):
                got = technical._probe_still_header(self.media / name)
                self.assertEqual(got is not None, expected, f"{name}: fast path {got}")

    def test_fast_path_does_not_spawn_ffprobe(self):
        with mock.patch.object(technical.subprocess, "run", side_effect=AssertionError("spawned")):
            self.assertEqual(technical.probe_local_media(self.media / "rgb.png"), (None, 640, 360))
            self.assertEqual(technical.probe_local_media(self.media / "q.jpg"), (0.04, 640, 360))

    def test_check_technical_identical_with_and_without_fast_path(self):
        for name in sorted(self.fast):
            for mt in (MediaType.IMAGE, MediaType.VIDEO):
                for arch in (False, True):
                    with self.subTest(f"{name}|{mt.value}|{arch}"):
                        new = technical.check_technical(self.media / name, mt, is_archival=arch)
                        with mock.patch.object(technical, "_probe_still_header", return_value=None):
                            ref = technical.check_technical(self.media / name, mt, is_archival=arch)
                        self.assertEqual(new.__dict__, ref.__dict__)

    def test_full_verdict_identical_with_and_without_fast_path(self):
        names = sorted(self.fast)

        def run(images: Path) -> dict:
            out = {}
            for i, name in enumerate(names, 1):
                dest = images / f"{i:03d}{Path(name).suffix}"
                shutil.copy2(self.media / name, dest)
                for mt in (MediaType.IMAGE, MediaType.VIDEO):
                    for src in (AssetSource.LOCAL, AssetSource.FLOW_IMAGE):
                        row = SceneRow(scene_number=str(i), script_segment="canyon river at dawn",
                                       asset_type=mt.value, prompt="canyon river")
                        res = AssetResult(scene_number=str(i), path=dest, media_type=mt, source=src,
                                          status=SceneStatus.READY)
                        qa = evaluate_scene_asset(row, res, coverage_plan={"narration_duration": 3.0},
                                                  enable_vision=False)
                        out[f"{name}|{mt.value}|{src.value}"] = qa.to_dict()
            return out

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as a, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as b:
            new = run(Path(a))
            with mock.patch.object(technical, "_probe_still_header", return_value=None):
                ref = run(Path(b))
        self.assertEqual(len(new), len(names) * 4)
        self.assertEqual(new, ref)

    def test_missing_ffprobe_still_raises_for_stills(self):
        with mock.patch.object(technical, "_ffprobe", side_effect=RuntimeError("ffprobe not available")):
            with self.assertRaises(RuntimeError):
                technical.probe_local_media(self.media / "rgb.png")

    def test_missing_file_unchanged(self):
        self.assertEqual(technical.probe_local_media(self.media / "nope.png"), (None, 0, 0))


def _qa(n: int, score: float = 0.5) -> VisualQAResult:
    return VisualQAResult(scene_number=str(n), asset_id=f"id{n}", overall_score=score,
                          status=VisualQAStatus.WEAK, warnings=[f"w{n}"])


class _CacheCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = Path(self._tmp.name)
        self.cache_file = self.dir / vqa_cache.CACHE_FILE
        self.assets = []
        for i in range(1, 301):
            p = self.dir / f"{i:03d}.png"
            p.write_bytes(b"x" * i)
            self.assets.append(p)

    def tearDown(self):
        vqa_cache.flush_cache(self.dir)
        self._tmp.cleanup()

    def disk(self) -> dict:
        return json.loads(self.cache_file.read_text(encoding="utf-8"))


class TestCacheSemantics(_CacheCase):
    def test_round_trip_matches_a_fresh_reread(self):
        for i, p in enumerate(self.assets[:50], 1):
            vqa_cache.store_cached(self.dir, p, str(i), _qa(i, 0.123456789), style_id="s")
        vqa_cache.flush_cache(self.dir)
        disk = self.disk()
        self.assertEqual(len(disk), 50)
        for i, p in enumerate(self.assets[:50], 1):
            got = vqa_cache.get_cached(self.dir, p, str(i), style_id="s")
            fp = vqa_cache._fingerprint(str(p.resolve()), str(i), "s",
                                        file_identity=vqa_cache._file_identity(p))
            self.assertEqual(got.to_dict(), VisualQAResult.from_dict(disk[fp]).to_dict())
            self.assertIsNone(vqa_cache.get_cached(self.dir, p, str(i), style_id="other"))

    def test_returned_result_is_independent_of_the_cache(self):
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        got = vqa_cache.get_cached(self.dir, self.assets[0], "1")
        got.warnings.append("mutated")
        self.assertEqual(vqa_cache.get_cached(self.dir, self.assets[0], "1").warnings, ["w1"])

    def test_first_store_is_on_disk_immediately_rest_within_the_interval(self):
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        self.assertEqual(len(self.disk()), 1)
        for i, p in enumerate(self.assets[1:20], 2):
            vqa_cache.store_cached(self.dir, p, str(i), _qa(i))
        time.sleep(vqa_cache.FLUSH_INTERVAL_S * 3 + 0.3)
        self.assertEqual(len(self.disk()), 20)
        self.assertEqual([p for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])

    def test_outside_writer_is_seen_and_merged(self):
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        self.assertIsNone(vqa_cache.get_cached(self.dir, self.assets[1], "2"))
        # another process / tool rewrites the file (non-atomically, like the old code)
        fp2 = vqa_cache._fingerprint(str(self.assets[1].resolve()), "2",
                                     file_identity=vqa_cache._file_identity(self.assets[1]))
        disk = self.disk()
        disk[fp2] = _qa(2).to_dict()
        time.sleep(0.01)
        self.cache_file.write_text(json.dumps(disk, indent=2), encoding="utf-8")
        self.assertEqual(vqa_cache.get_cached(self.dir, self.assets[1], "2").asset_id, "id2")
        vqa_cache.store_cached(self.dir, self.assets[2], "3", _qa(3))
        vqa_cache.flush_cache(self.dir)
        self.assertEqual(len(self.disk()), 3)

    def test_deleted_cache_file_drops_old_verdicts(self):
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        self.cache_file.unlink()
        self.assertIsNone(vqa_cache.get_cached(self.dir, self.assets[0], "1"))
        vqa_cache.store_cached(self.dir, self.assets[1], "2", _qa(2))
        vqa_cache.flush_cache(self.dir)
        self.assertEqual(len(self.disk()), 1)

    def test_corrupt_file_is_treated_as_empty_like_before(self):
        self.cache_file.write_text("{ not json", encoding="utf-8")
        self.assertIsNone(vqa_cache.get_cached(self.dir, self.assets[0], "1"))
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        vqa_cache.flush_cache(self.dir)
        self.assertEqual(len(self.disk()), 1)

    def test_save_cache_replaces_wholesale(self):
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        vqa_cache.store_cached(self.dir, self.assets[1], "2", _qa(2))
        vqa_cache.save_cache(self.dir, {"k": {"scene_number": "9"}})
        vqa_cache.flush_cache(self.dir)
        self.assertEqual(self.disk(), {"k": {"scene_number": "9"}})
        self.assertEqual(vqa_cache.load_cache(self.dir), {"k": {"scene_number": "9"}})

    def test_starmap_reader_sees_entries_after_flush(self):
        try:
            from starmap.media import _vqa_mismatch
        except ImportError:
            self.skipTest("starmap.media has no _vqa_mismatch in this tree")

        qa = VisualQAResult(scene_number="5", asset_id="777", semantic_match=0.2,
                            status=VisualQAStatus.FAIL, failure_reasons=["semantic mismatch"])
        vqa_cache.store_cached(self.dir, self.assets[0], "4", _qa(4))
        vqa_cache.store_cached(self.dir, self.assets[4], "5", qa)
        vqa_cache.flush_cache(self.dir)
        self.assertIn(("5", "777"), _vqa_mismatch(self.dir))

    def test_json_is_not_reparsed_per_call(self):
        calls = []
        real = vqa_cache.load_cache

        def counting(d):
            calls.append(d)
            return real(d)

        with mock.patch.object(vqa_cache, "load_cache", side_effect=counting):
            for i, p in enumerate(self.assets, 1):
                vqa_cache.get_cached(self.dir, p, str(i))
                vqa_cache.store_cached(self.dir, p, str(i), _qa(i))
            vqa_cache.flush_cache(self.dir)
        self.assertLessEqual(len(calls), 3, "cache JSON re-read per scene (O(n^2))")
        self.assertEqual(len(self.disk()), 300)


class TestCacheDurability(_CacheCase):
    def test_windows_locked_target_is_retried_then_replaced(self):
        # Windows: os.replace onto a file another handle has open raises PermissionError for a moment.
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        vqa_cache.flush_cache(self.dir)
        real = vqa_cache.os.replace
        calls = []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(13, "The process cannot access the file")
            return real(src, dst)

        vqa_cache.store_cached(self.dir, self.assets[1], "2", _qa(2))
        with mock.patch.object(vqa_cache.os, "replace", side_effect=flaky), \
                mock.patch.object(vqa_cache, "_REPLACE_BACKOFF_S", 0.0):
            vqa_cache.flush_cache(self.dir)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(self.disk()), 2)
        self.assertEqual([p for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])

    def test_windows_target_locked_for_good_falls_back_to_in_place_write(self):
        vqa_cache.store_cached(self.dir, self.assets[0], "1", _qa(1))
        with mock.patch.object(vqa_cache.os, "replace", side_effect=PermissionError(13, "locked")), \
                mock.patch.object(vqa_cache, "_REPLACE_BACKOFF_S", 0.0):
            vqa_cache.flush_cache(self.dir)  # must not raise: the old in-place write is used
        self.assertEqual(len(self.disk()), 1)
        self.assertEqual([p for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])

    def test_failed_write_leaves_previous_file_intact_and_no_tmp(self):
        for i, p in enumerate(self.assets[:5], 1):
            vqa_cache.store_cached(self.dir, p, str(i), _qa(i))
        vqa_cache.flush_cache(self.dir)
        before = self.cache_file.read_bytes()
        vqa_cache.store_cached(self.dir, self.assets[5], "6", _qa(6))
        with mock.patch.object(vqa_cache.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                vqa_cache.flush_cache(self.dir)
        self.assertEqual(self.cache_file.read_bytes(), before)
        self.assertEqual([p for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])
        vqa_cache.flush_cache(self.dir)  # still pending -> written now
        self.assertEqual(len(self.disk()), 6)

    def test_process_killed_mid_run_leaves_valid_cache(self):
        code = (
            "import sys, os; sys.path.insert(0, %r)\n"
            "from pathlib import Path\n"
            "from visual_qa.cache import store_cached\n"
            "from visual_qa.models import VisualQAResult\n"
            "d = Path(%r)\n"
            "for i in range(1, 301):\n"
            "    store_cached(d, d / f'{i:03d}.png', str(i), VisualQAResult(scene_number=str(i)))\n"
            "os._exit(1)  # crash: no atexit, no flush\n"
        ) % (str(ROOT), str(self.dir))
        subprocess.run([sys.executable, "-c", code], check=False, timeout=60)
        disk = self.disk()  # must parse
        self.assertGreaterEqual(len(disk), 1)
        self.assertLessEqual(len(disk), 300)
        self.assertEqual([p for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])

    def test_normal_exit_flushes_everything(self):
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from pathlib import Path\n"
            "from visual_qa.cache import store_cached\n"
            "from visual_qa.models import VisualQAResult\n"
            "d = Path(%r)\n"
            "for i in range(1, 301):\n"
            "    store_cached(d, d / f'{i:03d}.png', str(i), VisualQAResult(scene_number=str(i)))\n"
        ) % (str(ROOT), str(self.dir))
        subprocess.run([sys.executable, "-c", code], check=True, timeout=60)
        self.assertEqual(len(self.disk()), 300)

    def test_concurrent_threads_lose_nothing(self):
        def worker(lo, hi):
            for i in range(lo, hi):
                p = self.assets[i]
                vqa_cache.get_cached(self.dir, p, str(i + 1))
                vqa_cache.store_cached(self.dir, p, str(i + 1), _qa(i + 1))

        threads = [threading.Thread(target=worker, args=(k * 50, k * 50 + 50)) for k in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        vqa_cache.flush_cache(self.dir)
        self.assertEqual(len(self.disk()), 300)

    def test_concurrent_processes_never_corrupt_the_file(self):
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from pathlib import Path\n"
            "import visual_qa.cache as c\n"
            "from visual_qa.models import VisualQAResult\n"
            "c.FLUSH_INTERVAL_S = 0.0  # write on every store: maximum contention\n"
            "d = Path(%r); lo = int(sys.argv[1])\n"
            "for i in range(lo, lo + 100):\n"
            "    c.store_cached(d, d / f'{i:03d}.png', str(i), VisualQAResult(scene_number=str(i)))\n"
        ) % (str(ROOT), str(self.dir))
        procs = [subprocess.Popen([sys.executable, "-c", code, str(lo)]) for lo in (1, 101, 201)]
        bad = 0
        reads = 0
        while any(p.poll() is None for p in procs):
            if self.cache_file.exists():
                try:
                    json.loads(self.cache_file.read_text(encoding="utf-8"))
                    reads += 1
                except json.JSONDecodeError:
                    bad += 1
                except PermissionError:
                    pass  # Windows: the file is locked for the instant a writer replaces it; read again
        for p in procs:
            self.assertEqual(p.wait(timeout=60), 0)
        self.assertEqual(bad, 0, "a reader saw a half-written cache file")
        disk = self.disk()
        # Cross-process read-merge-write can still race (as before); it must
        # never corrupt, and the last writer's entries are all there.
        self.assertGreaterEqual(len(disk), 100)
        self.assertEqual([p for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])

    def test_sequential_processes_merge(self):
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from pathlib import Path\n"
            "from visual_qa.cache import store_cached\n"
            "from visual_qa.models import VisualQAResult\n"
            "d = Path(%r); lo = int(sys.argv[1])\n"
            "for i in range(lo, lo + 100):\n"
            "    store_cached(d, d / f'{i:03d}.png', str(i), VisualQAResult(scene_number=str(i)))\n"
        ) % (str(ROOT), str(self.dir))
        for lo in (1, 101, 201):
            subprocess.run([sys.executable, "-c", code, str(lo)], check=True, timeout=60)
        self.assertEqual(len(self.disk()), 300)


if __name__ == "__main__":
    unittest.main()
