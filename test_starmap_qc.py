"""Render QC finds frozen stretches and near-black footage in a finished StarMap video, and names the beat (a report only)."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from starmap.qc import check_render


def _video(path: Path) -> None:
    # 0-2 s moving test pattern, 2-4.5 s one frozen frame, 4.5-6 s black
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=2",
                    "-f", "lavfi", "-i", "color=c=gray:size=320x180:rate=30:duration=2.5",
                    "-f", "lavfi", "-i", "color=c=black:size=320x180:rate=30:duration=1.5",
                    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(path)], check=True)


class RenderQC(unittest.TestCase):
    def test_reports_frozen_stretches_and_dark_footage_by_beat(self):
        d = Path(tempfile.mkdtemp())
        _video(d / "v.mp4")
        beats = [SimpleNamespace(id="b1", start=0.0, end=2.0), SimpleNamespace(id="b2", start=2.0, end=4.5), SimpleNamespace(id="b3", start=4.5, end=6.0)]
        found = check_render(d / "v.mp4", {"footage": [{"start": 4.5, "end": 6.0}]}, beats)
        frozen = [f for f in found if f.reason.startswith("frozen")]
        self.assertEqual(frozen[0].beat, "b2")
        self.assertAlmostEqual(frozen[0].start, 2.0, delta=0.1)
        self.assertTrue(any(f.beat == "b3" and "dark" in f.reason for f in found), [f.text() for f in found])
        self.assertFalse([f for f in found if f.beat == "b1"], "the moving pattern is never reported")


if __name__ == "__main__":
    unittest.main()
