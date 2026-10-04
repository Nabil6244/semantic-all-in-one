"""Bulk Retry / Change Source on Flow scenes shows each scene as it finishes.

Real report: images were generated and saved (log: "Scene 2 -> saved 002.png",
manifest: complete) but their rows stayed on PROCESSING, because the bulk worker
only sent each scene's result to the screen after the WHOLE Flow batch returned
-- i.e. after the slowest scene (one stuck behind detection timeouts) was done.

Live VideoGeneratorApp in a subprocess (same convention as
test_select_by_source.py: in-process Tk construction corrupts the shared root).
The Flow batch is replaced by a fake that finishes scene A, then blocks until
the test releases it before finishing scene B.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_LIVE_CHECK_SCRIPT = r'''
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
REAL_STDOUT = sys.stdout  # the app's bulk worker swaps sys.stdout while it runs


def emit(name, ok, detail=""):
    REAL_STDOUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n")
    REAL_STDOUT.flush()


try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

from project_workspace import ProjectWorkspace
from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus

try:
    inst = _app.VideoGeneratorApp()
    inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
images_dir = inst._scene_action_images_dir()

scenes = [
    SceneRow(scene_number="2", script_segment="a", asset_type="image", prompt="pa"),
    SceneRow(scene_number="3", script_segment="b", asset_type="image", prompt="pb"),
]
inst._scene_rows = scenes
for i, scene in enumerate(scenes):
    inst._decorate_scene_row(i, scene, grid_row=i)

release_b = threading.Event()
a_done = threading.Event()


def _result(scene):
    path = Path(images_dir) / f"{int(scene.scene_number):03d}.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 96)
    return AssetResult(scene.scene_number, path, MediaType.IMAGE, AssetSource.FLOW_IMAGE, SceneStatus.READY)


class FakeManager:
    def retry_flow_batch(self, batch, on_scene_generating=None, on_scene_complete=None):
        results = {}
        for scene in batch:
            if on_scene_generating:
                on_scene_generating(scene)
        a, b = batch
        results[a.scene_number] = _result(a)
        if on_scene_complete:
            on_scene_complete(a, results[a.scene_number])
        a_done.set()
        release_b.wait(timeout=20)          # scene B is still "generating"
        results[b.scene_number] = _result(b)
        if on_scene_complete:
            on_scene_complete(b, results[b.scene_number])
        return results


inst._ensure_asset_manager = lambda _dir: FakeManager()
inst._mirror_result_into_workspace = lambda *a, **k: None

emit("batch_started", inst._start_flow_batch(list(scenes)) is True)


def pump(until, tries=400):
    import time
    for _ in range(tries):
        inst._poll_queue()
        if until():
            return True
        time.sleep(0.02)
    return False


key_a, key_b = _app._scene_key("2"), _app._scene_key("3")
a_cleared = a_done.wait(timeout=10) and pump(lambda: key_a not in inst._busy_scenes)
emit("finished_scene_leaves_processing_while_batch_still_running", bool(a_cleared),
     f"busy={sorted(inst._busy_scenes)}")
emit("finished_scene_is_ready_on_screen",
     key_a in inst._asset_results and inst._asset_results[key_a].ok
     and inst._row_status_from_result(scenes[0]) == "ready",
     str(inst._row_status_from_result(scenes[0])))
emit("slow_scene_still_processing", key_b in inst._busy_scenes, f"busy={sorted(inst._busy_scenes)}")
emit("batch_still_marked_running", bool(getattr(inst, "_flow_retry_batch_busy", False)))

release_b.set()
b_cleared = pump(lambda: key_b not in inst._busy_scenes and not getattr(inst, "_flow_retry_batch_busy", True))
emit("slow_scene_ready_when_it_finishes", bool(b_cleared) and inst._asset_results[key_b].ok,
     f"busy={sorted(inst._busy_scenes)}")
emit("each_scene_counted_once", inst._qa.busy == {}, str(inst._qa.busy))

REAL_STDOUT.flush()
os._exit(0)
'''


class TestBulkRetryPublishesEachScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script_path = Path(tempfile.mkdtemp()) / "_bulk_retry_live_check.py"
        script_path.write_text(_LIVE_CHECK_SCRIPT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=120,
            cwd=Path(__file__).resolve().parent,
        )
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._results:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout}\nstderr:\n{self._stderr[-2500:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2500:]}")

    def test_finished_scene_is_shown_while_the_batch_is_still_running(self):
        self._check("batch_started")
        self._check("finished_scene_leaves_processing_while_batch_still_running")
        self._check("finished_scene_is_ready_on_screen")

    def test_unfinished_scene_keeps_processing_until_it_is_done(self):
        self._check("slow_scene_still_processing")
        self._check("batch_still_marked_running")
        self._check("slow_scene_ready_when_it_finishes")

    def test_nothing_is_left_busy_afterwards(self):
        self._check("each_scene_counted_once")


if __name__ == "__main__":
    unittest.main()
