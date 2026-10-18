"""pakMap / Hybrid Map renders in pieces: drawn at the same time, joined into the same frames one render makes, and reused when
nothing that shapes them changed (pakmap.engine_runner._render_in_segments, pakmap-engine/lib/segments.mjs)."""

import pathlib
import subprocess
import tempfile
import unittest

from pakmap.engine_runner import SEGMENT_DIR, _groups, render_spec
from test_pakmap_generate import _can_render


def _frame_md5s(video: pathlib.Path) -> list:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "framemd5", "-"], capture_output=True, text=True).stdout
    return [ln.split(",")[-1].strip() for ln in out.splitlines() if ln[:1].isdigit()]


class TestGroups(unittest.TestCase):
    def test_pieces_are_shared_out_in_order_by_cost(self):
        segs = [{"key": str(i), "cost": c} for i, c in enumerate([10, 10, 10, 10, 1, 1])]
        g = _groups(segs, 2)
        self.assertEqual([s["key"] for grp in g for s in grp], [str(i) for i in range(6)])
        self.assertEqual(len(g), 2)
        self.assertEqual([len(x) for x in g], [2, 4])

    def test_never_more_renderers_than_pieces(self):
        self.assertEqual(len(_groups([{"key": "a", "cost": 5}], 4)), 1)


@unittest.skipUnless(_can_render(), "needs node, ffmpeg, Playwright and the engine's packages")
class TestSegmentedRender(unittest.TestCase):
    def spec(self, label="PART 1", **kw):
        d = 6
        s = {"width": 320, "height": 180, "fps": 5, "duration": d, "crf": 0, "x264_preset": "ultrafast",
             "camera": {"start": {"lon": 20, "lat": 40, "zoom": 3}, "drift": {"pct_per_s": 0.5}, "moves": []},
             "events": [{"id": "h", "type": "hud_title", "t_in": 0.2, "t_out": d, "label": label},
                        {"id": "m", "type": "marker", "lon": 21, "lat": 40, "label": "TOWN", "t_in": 0.8, "t_out": 2.6},
                        {"id": "c", "type": "caption", "text": "LATER", "t_in": 4.2, "t_out": 5.6}],
             "overlays": {"borders": False, "fills": []}, "segment_s": 1, "segment_min_s": 1}
        s.update(kw)
        return s

    def test_pieces_join_into_the_frames_of_one_render_and_are_reused(self):
        d = pathlib.Path(tempfile.mkdtemp())
        one = render_spec(self.spec(segments_enabled=False), d / "one" / "v.mp4", imagery=False)
        logs = []
        seen = []
        many = render_spec(self.spec(), d / "many" / "v.mp4", imagery=False, parts=2, log=logs.append, progress=lambda a, b: seen.append((a, b)))
        self.assertEqual(many.frames, one.frames)
        self.assertGreater(many.sidecar["pieces"]["total"], 2)
        self.assertEqual(many.sidecar["pieces"]["renderers"], 2)
        self.assertEqual(_frame_md5s(d / "many" / "v.mp4"), _frame_md5s(d / "one" / "v.mp4"))   # lossless: the drawn frames themselves
        self.assertEqual(seen[-1], (30, 30))
        self.assertFalse(any("one piece instead" in m for m in logs), logs)
        # the marker (0.8-2.6 s) is never split between pieces
        stored = sorted((d / "many" / SEGMENT_DIR).glob("*.json"))
        self.assertEqual(len(stored), many.sidecar["pieces"]["total"])

        # nothing changed: every piece is reused, no renderer starts
        again = render_spec(self.spec(), d / "many" / "v.mp4", imagery=False, parts=2)
        self.assertEqual(again.sidecar["pieces"]["reused"], again.sidecar["pieces"]["total"])
        self.assertEqual(again.sidecar["pieces"]["renderers"], 0)
        self.assertEqual(_frame_md5s(d / "many" / "v.mp4"), _frame_md5s(d / "one" / "v.mp4"))

        # the title text changes: only the pieces it is on screen in are drawn again (it spans the whole video here: all of them);
        # the caption changes: only its pieces
        edited = self.spec()
        edited["events"][2]["text"] = "CHANGED"
        third = render_spec(edited, d / "many" / "v.mp4", imagery=False, parts=2)
        self.assertGreater(third.sidecar["pieces"]["reused"], 0)
        self.assertLess(third.sidecar["pieces"]["reused"], third.sidecar["pieces"]["total"])
        ref = render_spec(dict(edited, segments_enabled=False), d / "ref" / "v.mp4", imagery=False)
        self.assertEqual(_frame_md5s(d / "many" / "v.mp4"), _frame_md5s(d / "ref" / "v.mp4"))
        self.assertEqual(len(list((d / "many" / SEGMENT_DIR).iterdir())), 2 * third.sidecar["pieces"]["total"], "only this render's pieces are kept")

    def test_a_short_video_is_drawn_in_one_piece(self):
        d = pathlib.Path(tempfile.mkdtemp())
        r = render_spec(self.spec(segment_s=30, segment_min_s=10), d / "v.mp4", imagery=False)
        self.assertNotIn("pieces", r.sidecar)
        self.assertFalse((d / SEGMENT_DIR).exists())


if __name__ == "__main__":
    unittest.main()
