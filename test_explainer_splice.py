"""Explainer splice: the map engine leaves the picture clips blank and the one final encode lays them back in, frame for frame (explainer/splice.py)."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from explainer import splice
from explainer.beats import overlay as OV

W, H, FPS = 1920, 1080, 30
HAVE_FF = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
HAVE_NODE = shutil.which("node") is not None


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def frame_means(path, n):
    """Mean luma of each of the first n frames."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", str(n), "-vf", "scale=32:18,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    px = 32 * 18
    return [sum(r.stdout[i * px:(i + 1) * px]) / px for i in range(len(r.stdout) // px)]


@unittest.skipUnless(HAVE_FF, "ffmpeg not installed")
class SpliceComposite(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        # the map render: grey, with a black span (the engine's blank frames) at frames 30-89
        ff("-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}:r={FPS}:d=4", "-vf", "drawbox=enable='between(n,30,89)':c=black:t=fill",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuvj420p", str(self.d / "map.mp4"))
        # the clip: its brightness climbs with its frame number, so the frame shown says which clip frame it is
        ff("-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d=2", "-vf", "geq=lum='min(255,20+3*N)':cb=128:cr=128",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "1", "-pix_fmt", "yuv420p", str(self.d / "baked_x.mp4"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_blank_span_shows_the_clip_frame_for_frame(self):
        holes = [{"from": 30, "to": 90, "media": str(self.d / "baked_x.mp4"), "t_in": 1.0, "start_s": 0.0}]
        out = self.d / "out.mp4"
        self.assertEqual(OV.composite_chunked(self.d / "map.mp4", [], out, holes=holes, final=True), 0)
        got = frame_means(out, 120)
        self.assertEqual(len(got), 120)
        clip = frame_means(self.d / "baked_x.mp4", 60)
        for k in range(60):                       # video frame 30+k is clip frame k
            self.assertAlmostEqual(got[30 + k], clip[k], delta=2.5, msg=f"frame {30 + k}")
        for i in list(range(0, 30)) + list(range(90, 120)):
            self.assertGreater(got[i], 100, msg=f"frame {i} should be the map")

    def test_a_span_split_by_chunks_keeps_its_place_in_the_clip(self):
        holes = [{"from": 30, "to": 90, "media": str(self.d / "baked_x.mp4"), "t_in": 1.0, "start_s": 0.0}]
        old = OV.CHUNK_MAX_S, OV.PLAIN_MAX_S
        OV.CHUNK_MAX_S, OV.PLAIN_MAX_S = 0.5, 0.5      # many small chunks: each cut must start at the right clip frame
        try:
            out = self.d / "out2.mp4"
            self.assertEqual(OV.composite_chunked(self.d / "map.mp4", [], out, holes=holes, final=True), 0)
        finally:
            OV.CHUNK_MAX_S, OV.PLAIN_MAX_S = old
        got, clip = frame_means(out, 120), frame_means(self.d / "baked_x.mp4", 60)
        for k in range(60):
            self.assertAlmostEqual(got[30 + k], clip[k], delta=2.5, msg=f"frame {30 + k}")

    def test_a_span_with_no_clip_is_refused(self):
        self.assertNotEqual(OV.composite_chunked(self.d / "map.mp4", [], self.d / "o.mp4", holes=[{"from": 30, "to": 90, "media": ""}], final=True), 0)

    def test_choose_lists_only_long_enough_own_clips(self):
        ff("-f", "lavfi", "-i", f"color=c=red:s={W}x{H}:r={FPS}:d=1", "-c:v", "libx264", "-preset", "ultrafast", str(self.d / "still_short.mp4"))
        ev = lambda m, a, b, **k: {"type": "media_full", "media": str(self.d / m), "t_in": a, "t_out": b, "kenburns": False, "cover_ui": True, **k}
        spec = {"fps": FPS, "width": W, "height": H, "events": [ev("baked_x.mp4", 1, 3), ev("still_short.mp4", 3, 5), ev("map.mp4", 5, 6),
                                                                  ev("baked_x.mp4", 7, 8, loop=True)]}
        self.assertEqual(splice.choose(spec), 1)    # still_short is shorter than its slot, map.mp4 is not ours; baked_x's loop use is skipped by the engine itself
        self.assertEqual(spec["footage_holes"], [str(self.d / "baked_x.mp4")])


@unittest.skipUnless(HAVE_NODE, "node not installed")
class EngineHoles(unittest.TestCase):
    def test_hole_runs_follow_the_shortcut_rules(self):
        js = """
import { holeRuns } from './pakmap-engine/lib/footage_pass.mjs';
const ev = (id, a, b, x = {}) => ({ id, type: 'media_full', media: '/c/' + id + '.mp4', t_in: a, t_out: b, cover_ui: true, kenburns: false, dissolve_s: 0, ...x });
const spec = { fps: 10, hybrid: {}, footage_holes: ['/c/a.mp4', '/c/b.mp4'], events: [ev('a', 0, 1), ev('b', 1, 2), ev('c', 2, 3),
  { id: 'g', type: 'map_template', over_footage: true, t_in: 1.5, t_out: 1.7 }] };
console.log(JSON.stringify(holeRuns(spec, spec.events, 30)));
console.log(JSON.stringify(holeRuns({ ...spec, footage_holes: [] }, spec.events, 30)));
"""
        r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, cwd=str(Path(__file__).parent))
        self.assertEqual(r.returncode, 0, r.stderr)
        runs, none = [json.loads(x) for x in r.stdout.strip().splitlines()]
        self.assertEqual(none, [])
        self.assertEqual([(x["id"], x["from"], x["to"]) for x in runs], [("a", 0, 10), ("b", 10, 15), ("b", 17, 20)])   # c is not listed; g is drawn over b


if __name__ == "__main__":
    unittest.main()
