#!/usr/bin/env python3
"""A finished scene turns READY quickly (Saad's Mac, 2026-11-04).

- Finished Flow images are placed (copy + Visual QA + manifest) by several threads at once, for agent AND normal batches:
  with one, images from six accounts queued behind each other's QA and each waited ~10 minutes. Each scene is placed once.
- A map clip never goes to vision QA (our engine draws it from the place name); a "map ready" scene sat 5 minutes before.
- A vision QA call that hangs is cut off at a hard cap and the scene is scored without it.
No real engine, Flow or Gemini call is used.
"""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from providers.flow.provider import FlowProvider
from test_flow_agent_connection import AGENT, FakeClient, FakeManager, _png, _scenes
from visual_qa import semantic


class TestFlowPlacementParallel(unittest.TestCase):
    def _run(self, flow_settings):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c1 = FakeClient(root)
            active, peak, calls = [0], [0], []
            lock = threading.Lock()

            def engine(settings):
                for i in range(4):
                    f = root / "a" / f"{i + 1:03d}.png"
                    _png(f)
                    msg = {"type": "BATCH_PROGRESS", "index": i, "status": "done", "path": str(f)}
                    c1.deliver(msg)
                    c1.deliver({"type": "PROMPT_RESULT", "index": i, "status": "done", "path": str(f)})  # same scene twice
                c1.deliver({"type": "GENERATE_DONE", "outputDir": settings["outputDir"]})
            c1.on_generate = engine

            def slow_ready(scene, result):
                with lock:
                    calls.append(scene.scene_number)
                    active[0] += 1
                    peak[0] = max(peak[0], active[0])
                time.sleep(0.4)      # stands in for Visual QA
                with lock:
                    active[0] -= 1

            t0 = time.monotonic()
            res = FlowProvider(FakeManager(c1), media_kind="image", flow_settings=flow_settings).resolve_batch(
                _scenes(4), root, log=lambda *_: None, on_scene_ready=slow_ready)
            return res, sorted(calls), peak[0], time.monotonic() - t0

    def test_agent_batch_places_several_at_once_and_each_scene_once(self):
        res, calls, peak, _ = self._run(AGENT)
        self.assertEqual(calls, ["1", "2", "3", "4"])
        self.assertGreater(peak, 1, "placement runs in parallel")
        self.assertTrue(all(r.status == SceneStatus.READY for r in res.values()))

    def test_normal_batch_places_several_at_once_and_each_scene_once(self):
        res, calls, peak, _ = self._run({"model": "BELUGA"})
        self.assertEqual(calls, ["1", "2", "3", "4"])
        self.assertGreater(peak, 1, "placement runs in parallel")
        self.assertTrue(all(r.status == SceneStatus.READY for r in res.values()))


class TestVisionQaNeverHoldsAScene(unittest.TestCase):
    def test_a_map_clip_never_goes_to_vision(self):
        scene = SceneRow(scene_number="7", script_segment="Texas", asset_type="map", prompt="USA > Texas")
        res = AssetResult("7", Path("007.mp4"), MediaType.VIDEO, AssetSource.MAP, SceneStatus.READY)
        self.assertFalse(semantic.needs_vision_inspection(scene, res, semantic=0.1, technical=0.1))

    def test_a_hung_vision_call_is_cut_off_and_scored_without_it(self):
        with TemporaryDirectory() as tmp:
            frame = Path(tmp) / "f.jpg"
            frame.write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
            scene = SceneRow(scene_number="1", script_segment="a cat", asset_type="image", prompt="cat")
            release = threading.Event()

            def hang(*_a, **_k):
                release.wait(10)
                raise RuntimeError("released")
            with mock.patch.object(semantic, "_VISION_TIMEOUT_S", 0.3), mock.patch("requests.post", side_effect=hang):
                t0 = time.monotonic()
                out = semantic.vision_semantic_score(scene, [frame], settings={"gemini_api_key": "k"})
                took = time.monotonic() - t0
            release.set()
            self.assertEqual(out, (None, []))
            self.assertLess(took, 7.0)


if __name__ == "__main__":
    unittest.main()
