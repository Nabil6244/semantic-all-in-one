"""A video card whose clip is shorter than its time on screen must keep
playing (loop) for the whole window, instead of the video layer ending early
and leaving the card blank with its caption still showing."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scene_graph import render
from scene_graph.layout import NodeRect, SceneGraphLayout
from scene_graph.schema import SceneNode


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not available")
class TestVideoCardLoops(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.clip = Path(self._tmp.name) / "short.mp4"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
             "-t", "2", "-pix_fmt", "yuv420p", str(self.clip)],
            check=True,
        )
        self.node = SceneNode(id="v1", type="video_loop", appear_at=1.0)

    def tearDown(self):
        self._tmp.cleanup()

    def _layer(self, window):
        layout = SceneGraphLayout(
            canvas_width=1920, canvas_height=1080,
            node_rects={"v1": NodeRect(node_id="v1", x=100, y=100, width=640, height=360)},
            active_windows={"v1": window},
        )
        return render._node_video_layer(self.node, layout=layout, resolved_media={"v1": str(self.clip)})

    def test_short_clip_loops_for_the_whole_window(self):
        layer = self._layer((1.0, 7.0))
        self.assertIn("-stream_loop", layer.input_args)
        self.assertAlmostEqual(layer.duration, 6.0, places=3)
        t = layer.input_args[layer.input_args.index("-t") + 1]
        self.assertAlmostEqual(float(t), 6.0, places=3)

    def test_clip_longer_than_its_window_is_unchanged(self):
        layer = self._layer((1.0, 2.5))
        self.assertNotIn("-stream_loop", layer.input_args)
        self.assertAlmostEqual(layer.duration, 1.5, places=3)

    def test_map_clip_still_holds_its_last_frame_instead_of_looping(self):
        with patch.object(render, "is_map_node", return_value=True), \
                patch.object(render, "is_map_clip", return_value=True):
            layer = self._layer((1.0, 7.0))
        self.assertNotIn("-stream_loop", layer.input_args)
        self.assertIn("tpad=stop_mode=clone", layer.pre_filter)
        self.assertAlmostEqual(layer.duration, 6.0, places=1)


if __name__ == "__main__":
    unittest.main()
