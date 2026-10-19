"""NASA clips: a cut that is black from start to end is cut again from another part of the same video (What If render 024, 1:51-2:00:
the middle of a launch video was black, and the shot showed 8.8 s of black)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from providers.base import SceneRow, SceneStatus      # noqa: E402
from providers.nasa import provider as P             # noqa: E402
from providers.nasa.api_backend import NasaCandidate  # noqa: E402

FF = str(ROOT / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
if not Path(FF).is_file():
    FF = shutil.which("ffmpeg") or ""


def make_clip(path: Path, vf: str) -> Path:
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=3", "-vf", vf, "-pix_fmt", "yuv420p", str(path)],
                   check=True)
    return path


STARS = ",".join(f"drawbox=x={(i * 97) % 620}:y={(i * 53) % 340}:w=3:h=3:color=white:t=fill" for i in range(40))


class Windows(unittest.TestCase):
    def test_a_long_video_gets_other_windows_a_short_one_only_its_own(self):
        w = P.clip_windows(171.0, 6.0)
        self.assertEqual(w[0], P.compute_clip_window(P.compute_fallback_timestamp(171.0, 6.0), 171.0, 6.0))
        self.assertEqual(len(w), 4)
        self.assertTrue(all(abs(a[0] - b[0]) >= 6.0 for i, a in enumerate(w) for b in w[:i]))
        self.assertEqual(len(P.clip_windows(8.0, 6.0)), 1)
        self.assertEqual(len(P.clip_windows(None, 6.0)), 1)


@unittest.skipUnless(FF, "ffmpeg not available")
class Blank(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self._path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(Path(FF).parent) + os.pathsep + self._path      # the provider calls "ffmpeg" (the app puts its own first)

    def tearDown(self):
        os.environ["PATH"] = self._path

    def test_black_is_blank_and_a_star_field_is_not(self):
        self.assertTrue(P.is_blank_clip(make_clip(self.d / "b.mp4", "null")))
        self.assertFalse(P.is_blank_clip(make_clip(self.d / "s.mp4", STARS)))
        self.assertFalse(P.is_blank_clip(self.d / "missing.mp4"))

    def _provider(self, cuts):
        """A provider with one 171 s candidate whose cut at each start comes from `cuts` (start -> 'black' | 'stars')."""
        prov = P.NasaProvider(backend=mock.Mock(), clip_duration=6.0)
        cand = NasaCandidate(nasa_id="KSC-1", title="Launch", download_url="https://example.invalid/v.mp4", duration=171.0)
        prov._search = lambda scene, log, exclude: [cand]
        starts = []

        def fake_download(url, target, start, length, log=None, should_stop=None):
            starts.append(round(start, 2))
            return make_clip(Path(target), "null" if cuts(start) == "black" else STARS)

        return prov, starts, fake_download

    def test_a_black_cut_is_cut_again_from_another_part_and_the_good_one_kept(self):
        prov, starts, dl = self._provider(lambda s: "black" if s > 60 else "stars")
        lines = []
        with mock.patch.object(P, "download_clip", dl), mock.patch.object(P, "is_test_pattern", lambda p: False):
            r = prov._resolve(SceneRow(scene_number="16", script_segment="x", prompt="launch"), self.d, lines.append, set())
        self.assertEqual(r.status, SceneStatus.READY)
        self.assertEqual(starts, [81.5, 41.75])
        self.assertEqual(r.metadata["clip_start"], 41.75)
        self.assertTrue(any("is black at 82s" in l for l in lines), lines)
        self.assertFalse(P.is_blank_clip(r.path))

    def test_all_black_moves_on_and_reports_why(self):
        prov, starts, dl = self._provider(lambda s: "black")
        with mock.patch.object(P, "download_clip", dl), mock.patch.object(P, "is_test_pattern", lambda p: False):
            r = prov._resolve(SceneRow(scene_number="16", script_segment="x", prompt="launch"), self.d, lambda m: None, set())
        self.assertEqual(r.status, SceneStatus.FAILED)
        self.assertEqual(len(starts), 4)
        self.assertIn("black from start to end", r.error)
        self.assertFalse((self.d / "016.mp4").exists())


if __name__ == "__main__":
    unittest.main()
