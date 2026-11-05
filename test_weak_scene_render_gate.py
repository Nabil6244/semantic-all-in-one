"""Weak scenes never hard-block Render (Overscaled / Exp Solar).

Visual QA still grades every scene; a WEAK / FAIL / MANUAL_REVIEW scene (or a
row whose file is on disk but not confirmed READY) asks the user one YES/NO
question. Only a missing, empty or failed file blocks Render.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from scene_qa import CONTINUES, render_gate, weak_scenes_message
from scene_recovery import scene_key


def _row(n):
    return SceneRow(scene_number=str(n), script_segment=f"s{n}", asset_type="stock_image", stock=f"q{n}")


class RenderGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _file(self, n, data=b"x"):
        p = self.tmp / f"{n}.png"
        p.write_bytes(data)
        return p

    def _ready(self, n, vqa=None, data=b"x"):
        meta = {"visual_qa": vqa} if vqa else {}
        return AssetResult(str(n), self._file(n, data), MediaType.IMAGE, AssetSource.STOCK_IMAGE, SceneStatus.READY, metadata=meta)

    def test_message_singular_and_plural(self):
        self.assertEqual(weak_scenes_message(1), "1 weak scene detected. Do you still want to render the video?")
        self.assertEqual(weak_scenes_message(2), "2 weak scenes detected. Do you still want to render the video?")
        self.assertEqual(weak_scenes_message(5), "5 weak scenes detected. Do you still want to render the video?")

    def test_zero_weak(self):
        rows = [_row(i) for i in (1, 2)]
        results = {scene_key(i): self._ready(i, {"status": "PASS"}) for i in (1, 2)}
        self.assertEqual(render_gate(rows, {scene_key(i): "ready" for i in (1, 2)}, results), ([], []))

    def test_weak_and_manual_review_counted_once(self):
        rows = [_row(i) for i in range(1, 7)]
        results = {scene_key(1): self._ready(1, {"status": "PASS"}),
                   scene_key(2): self._ready(2, {"status": "WEAK", "recommended_action": "manual_review"}),
                   scene_key(3): self._ready(3, {"status": "WEAK"}),
                   scene_key(4): self._ready(4, {"status": "PASS", "recommended_action": "manual_review"}),
                   scene_key(5): self._ready(5, {"status": "FAIL"}),
                   scene_key(6): self._ready(6, {"status": "WEAK"})}
        weak, blocked = render_gate(rows, {scene_key(i): "ready" for i in range(1, 7)}, results)
        self.assertEqual(weak, [scene_key(i) for i in (2, 3, 4, 5, 6)])
        self.assertEqual(blocked, [])

    def test_unconfirmed_row_with_file_on_disk_is_weak(self):
        rows = [_row(1)]
        f = self._file(1)
        weak, blocked = render_gate(rows, {scene_key(1): "waiting"}, {}, lambda s: f)
        self.assertEqual((weak, blocked), ([scene_key(1)], []))

    def test_missing_asset_blocks(self):
        rows = [_row(1), _row(2)]
        results = {scene_key(1): self._ready(1, {"status": "WEAK"})}
        weak, blocked = render_gate(rows, {scene_key(1): "ready", scene_key(2): "needs_action"}, results,
                                    lambda s: self.tmp / "gone.png")
        self.assertEqual(blocked, [scene_key(2)])

    def test_corrupted_empty_asset_blocks(self):
        rows = [_row(1)]
        results = {scene_key(1): self._ready(1, data=b"")}
        self.assertEqual(render_gate(rows, {scene_key(1): "ready"}, results), ([], [scene_key(1)]))

    def test_skipped_and_continuation_rows_ignored(self):
        rows = [_row(1), _row(2)]
        self.assertEqual(render_gate(rows, {scene_key(1): "skipped", scene_key(2): CONTINUES}, {}), ([], []))


_LIVE = r"""
import os, sys, csv, tempfile
from pathlib import Path
from unittest import mock
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
def emit(n, ok, d=""): print(f"{'PASS' if ok else 'FAIL'}:{n}:{str(d)[:400]}")
from tkinter import messagebox
dialogs, answers = [], []
messagebox.showerror = lambda *a, **k: dialogs.append(("error",) + a)
messagebox.showinfo = lambda *a, **k: dialogs.append(("info",) + a)
def _ask(title, msg, **k):
    dialogs.append(("ask", title, msg)); return answers.pop(0)
messagebox.askyesno = _ask
try:
    import app as _app
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
from providers.base import SceneRow
from asset_manager import AssetManifest
from scene_graph.app_integration import OverscaledGenerationResult
tmp = Path(tempfile.mkdtemp())
inst._workspace = ProjectWorkspace(project_id="p", title="t", seq=1, root=tmp / "ws")
p = tmp / "plan.csv"
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["scene_number", "script_segment"]); w.writerow(["1", "A quiet observatory."])
inst._overscaled_use_local_planner_var.set(True)
inst._overscaled_csv_var.set(str(p)); inst._load_overscaled_csv(str(p))
voice = tmp / "vo.wav"; voice.write_bytes(b"RIFF")
inst._current_voiceover_path = lambda: voice
inst._get_flow_engine_manager = lambda: None
inst.after = lambda ms, fn=None, *a: fn(*a) if (fn and not (isinstance(ms, (int, float)) and ms >= 1000)) else None   # run short hops now; skip long timers (the 30 s heartbeat re-arms itself forever)
nav = []
inst._goto_workflow_view = lambda key: nav.append(key)
import threading as _th
_RealThread = _th.Thread
def _Inline(target=None, daemon=None, *a, **k):
    if a or k.get("args") or k.get("kwargs"):   # a thread pool's own worker: a real thread
        return _RealThread(target=target, daemon=daemon, *a, **k)
    class _T:
        def start(self): target()
    return _T()
images = inst._workspace.overscaled_images_dir; images.mkdir(parents=True, exist_ok=True)

def setup(weak_vqa_rows=(), mismatched_rows=(), missing_rows=()):
    inst._scene_rows = [SceneRow(scene_number=str(i), script_segment=f"line {i}", asset_type="stock_image", stock=f"query {i}") for i in (1, 2, 3)]
    inst._scene_rows_owner = "overscaled"
    inst._asset_results.clear(); inst._busy_scenes.clear(); inst._qa.busy.clear()
    (images / ".asset_manifest.json").unlink(missing_ok=True)
    m = AssetManifest(images)
    for i in (1, 2, 3):
        f = images / f"{i}.png"
        if i in missing_rows:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(b"png")
        rec = {"status": "complete", "local_path": str(f), "source": "stock_image",
               "stock_query": ("old query" if i in mismatched_rows else f"query {i}")}
        if i in weak_vqa_rows:
            rec["visual_qa"] = {"status": "WEAK", "recommended_action": "manual_review"}
        m.set(str(i), rec)
    inst._hydrate_overscaled_assets_from_manifest()

def run(answer_list):
    calls = []
    def fake(*a, **k):
        calls.append(k.get("media_only"))
        return OverscaledGenerationResult(ok=True, errors=[]) if k.get("media_only") else OverscaledGenerationResult(ok=False, errors=["test stop"])
    dialogs.clear(); answers[:] = list(answer_list); nav.clear()
    with mock.patch("scene_graph.app_integration.generate_overscaled_video", side_effect=fake), \
            mock.patch("video_generator.transcribe_audio", side_effect=RuntimeError("no whisper")), \
            mock.patch("threading.Thread", _Inline):
        inst._run_overscaled_generation()
    return calls, [d for d in dialogs if d[0] == "ask"]

# Generate scenes: 2 rows unconfirmed (files on disk, table never matched them) -> popup, YES renders with the cached files
setup(mismatched_rows=(2, 3))
calls, asks = run([True])
emit("fetch_then_yes_renders", calls == [True, False] and len(asks) == 1, f"calls={calls} asks={asks}")
emit("popup_wording_plural", asks and asks[0][2] == "2 weak scenes detected. Do you still want to render the video?", asks)

# NO -> nothing rendered, nothing deleted, back to the Visual Plan
setup(mismatched_rows=(2, 3))
calls, asks = run([False])
emit("no_cancels_render", calls == [True] and len(asks) == 1 and not inst._overscaled_running, f"calls={calls}")
emit("no_keeps_files", all((images / f"{i}.png").is_file() for i in (1, 2, 3)), "")
emit("no_returns_to_visual_plan", nav == ["visual_plan"] and "Render cancelled" in inst._overscaled_status_var.get(),
     f"nav={nav} status={inst._overscaled_status_var.get()}")

# Missing file -> technical block, no popup
setup(mismatched_rows=(2,), missing_rows=(3,))
calls, asks = run([])
emit("missing_file_blocks_without_popup", calls == [True] and not asks and "need attention" in inst._overscaled_status_var.get(),
     f"calls={calls} asks={asks} status={inst._overscaled_status_var.get()}")

# Render click, all ready, 0 weak -> renders directly, no popup
setup()
calls, asks = run([])
emit("zero_weak_renders_directly", calls == [False] and not asks, f"calls={calls} asks={asks}")

# Render click, all ready, 1 VQA WEAK+MANUAL_REVIEW scene -> one popup counting it once
setup(weak_vqa_rows=(2,))
calls, asks = run([False])
emit("render_click_weak_no", calls == [] and len(asks) == 1 and not inst._overscaled_running, f"calls={calls}")
emit("popup_wording_singular", asks and asks[0][2] == "1 weak scene detected. Do you still want to render the video?", asks)
setup(weak_vqa_rows=(2,))
calls, asks = run([True])
emit("render_click_weak_yes", calls == [False] and len(asks) == 1, f"calls={calls}")
os._exit(0)
"""


class WeakSceneRenderLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_weak_live.py"
        script.write_text(_LIVE, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180,
                              cwd=Path(__file__).resolve().parent)
        cls._out, cls._err, cls._res = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[5:])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._res[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._res:
            self.fail(f"never reported {name}\n{self._out}\n{self._err[-2000:]}")
        ok, detail = self._res[name]
        self.assertTrue(ok, f"{name}: {detail}")

    def test_fetch_then_yes_renders(self):
        self._check("fetch_then_yes_renders")
        self._check("popup_wording_plural")

    def test_no_cancels_keeps_files_and_returns(self):
        self._check("no_cancels_render")
        self._check("no_keeps_files")
        self._check("no_returns_to_visual_plan")

    def test_missing_file_blocks_without_popup(self):
        self._check("missing_file_blocks_without_popup")

    def test_zero_weak_renders_directly(self):
        self._check("zero_weak_renders_directly")

    def test_render_click_weak(self):
        self._check("render_click_weak_no")
        self._check("popup_wording_singular")
        self._check("render_click_weak_yes")


if __name__ == "__main__":
    unittest.main()
