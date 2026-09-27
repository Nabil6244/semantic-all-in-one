"""Overscaled/Exp Solar cancellation.

Before: the Overscaled/Exp Solar path had no cancel at all — the primary
button sat disabled on "Generating…" for the whole run (tens of minutes on a
long-form render), and nothing could stop media resolution or the ffmpeg
encode. Now a Stop request is honoured at every stage boundary (each render
segment included), the running encoder is terminated through the existing
process registry, temp files are removed, and the UI reports "Cancelled"
(not an error) and becomes usable again.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import scene_graph.render as R
from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows
from scene_graph.layout import compute_layout
from scene_graph.style_presets import load_style_preset

_HAS_FFMPEG = bool(shutil.which("ffmpeg"))
_TEXT = [
    "Workers excavated the canyon floor with heavy machinery near the river.",
    "A cross-section diagram shows the turbine mechanism inside the dam.",
    "The system has three main components: pumps, valves, and pipes.",
    "Pumps move the water uphill each night.",
]


def _graph(n):
    rows = [{"scene_number": str(i + 1), "script_segment": _TEXT[i % len(_TEXT)]} for i in range(n)]
    return generate_scene_graph_local_planner("seg", scene_rows_from_csv_rows(rows)).scene_graph


class TestRendererHonoursCancel(unittest.TestCase):
    def test_cancel_between_segments_stops_and_cleans_up(self):
        graph = _graph(40)
        calls = []
        state = {"cancel": False}

        def fake_run(cmd, **kwargs):
            calls.append(state["cancel"])  # was Stop already pressed when this segment started?
            Path(cmd[-1]).write_bytes(b"x")
            state["cancel"] = True  # user presses Stop while the first segment(s) encode
            return mock.Mock(returncode=0, stderr="", timed_out=False, stalled=False)

        with tempfile.TemporaryDirectory() as tmp:
            layout = compute_layout(graph)
            with mock.patch.object(R, "run_ffmpeg", fake_run), mock.patch.object(R, "_MAX_SEGMENT_INPUTS", 10):
                with self.assertRaises(R.RenderCancelled):
                    R.render_overscaled_segment(
                        graph, layout, load_style_preset("overscaled"), out_path=Path(tmp) / "o.mp4",
                        work_dir=Path(tmp) / "work", cancel_check=lambda: state["cancel"],
                    )
            # Segments already running when Stop arrives may finish (they are
            # killed by the Stop button's process-registry call in the app);
            # none may START after it.
            self.assertTrue(calls)
            self.assertNotIn(True, calls, "a segment started after Stop")
            self.assertLessEqual(len(calls), R._segment_workers(10**6))
            self.assertFalse((Path(tmp) / "work").exists())

    def test_killed_encoder_is_reported_as_cancelled_not_failed(self):
        # ffmpeg exits 0 after SIGTERM and may leave a partial file: the stop
        # must still be reported as cancelled, never accepted as a result.
        graph = _graph(3)
        state = {"cancel": False}

        def killed(cmd, **kwargs):
            state["cancel"] = True
            Path(cmd[-1]).write_bytes(b"partial")
            return mock.Mock(returncode=0, stderr="Exiting normally, received signal 15.", timed_out=False, stalled=False)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(R, "run_ffmpeg", killed):
                with self.assertRaises(R.RenderCancelled):
                    R.render_overscaled_segment(
                        graph, compute_layout(graph), load_style_preset("overscaled"),
                        out_path=Path(tmp) / "o.mp4", work_dir=Path(tmp) / "w",
                        cancel_check=lambda: state["cancel"],
                    )

    def test_watchdog_killed_encoder_is_a_failure_even_with_exit_code_zero(self):
        graph = _graph(3)

        def stalled(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"partial")
            return mock.Mock(returncode=0, stderr="", timed_out=False, stalled=True)

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(R, "run_ffmpeg", stalled):
                with self.assertRaises(RuntimeError):
                    R.render_overscaled_segment(
                        graph, compute_layout(graph), load_style_preset("overscaled"),
                        out_path=Path(tmp) / "o.mp4", work_dir=Path(tmp) / "w",
                    )


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg required")
class TestRealEncoderIsStopped(unittest.TestCase):
    def test_stop_terminates_the_running_ffmpeg_and_leaves_nothing_behind(self):
        from hardware.process_registry import get_registry

        graph = _graph(16)
        stop = threading.Event()
        outcome = {}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"

            def run():
                try:
                    R.render_overscaled_segment(
                        graph, compute_layout(graph), load_style_preset("overscaled"),
                        out_path=Path(tmp) / "o.mp4", resolution="1920x1080", fps=30, work_dir=work,
                        cancel_check=stop.is_set,
                    )
                    outcome["result"] = "finished"
                except R.RenderCancelled:
                    outcome["result"] = "cancelled"
                except Exception as exc:  # pragma: no cover - reported below
                    outcome["result"] = f"error: {exc}"

            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            deadline = time.time() + 120
            while time.time() < deadline and not any(
                r.owner == "overscaled_render" for r in get_registry().list_active()
            ):
                time.sleep(0.2)
            self.assertTrue(any(r.owner == "overscaled_render" for r in get_registry().list_active()),
                            "encoder never started")
            stopped_at = time.time()
            stop.set()
            get_registry().terminate_owned(owner="overscaled_render")  # what the Stop button does
            worker.join(timeout=60)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcome.get("result"), "cancelled")
            self.assertLess(time.time() - stopped_at, 30)
            self.assertFalse([r for r in get_registry().list_active() if r.owner == "overscaled_render"])
            self.assertFalse(work.exists())


class TestIntegrationBoundary(unittest.TestCase):
    def test_stop_during_media_resolution_never_starts_the_render(self):
        import csv

        from scene_graph.app_integration import generate_overscaled_video

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            csv_path = tmp / "p.csv"
            with open(csv_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["scene_number", "script_segment"])
                w.writerow(["1", _TEXT[0]])
            vo = tmp / "vo.wav"
            vo.write_bytes(b"RIFF")
            stop = threading.Event()

            def resolve(*args, **kwargs):
                stop.set()  # Stop pressed while assets were being fetched
                return {}

            pipeline = mock.Mock()
            with mock.patch("scene_graph.app_integration.resolve_scene_graph_media", resolve), \
                    mock.patch("scene_graph.app_integration.run_overscaled_pipeline", pipeline):
                result = generate_overscaled_video(
                    str(csv_path), str(vo), str(tmp / "o.mp4"), use_local_planner=True, cancel_check=stop.is_set,
                )
            self.assertTrue(result.cancelled)
            self.assertFalse(result.ok)
            pipeline.assert_not_called()


_LIVE = r"""
import os, sys, csv, tempfile
from pathlib import Path
from unittest import mock
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
def emit(n, ok, d=""): print(f"{'PASS' if ok else 'FAIL'}:{n}:{str(d)[:400]}")
from tkinter import messagebox
dialogs = []
messagebox.showerror = lambda *a, **k: dialogs.append(("error",) + a)
messagebox.showinfo = lambda *a, **k: dialogs.append(("info",) + a)
try:
    import app as _app
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
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

# While running, the primary button is an enabled Stop — not a dead "Generating…".
stale_manager = mock.Mock()          # left over from an earlier run
inst._asset_manager = stale_manager
inst._overscaled_run_manager = None  # Stop pressed before this run built its own
inst._overscaled_running = True
inst._sync_primary_cta()
emit("running_shows_enabled_stop", inst._cta_action == "overscaled_cancel", inst._cta_action)
killed = []
with mock.patch("hardware.process_registry.ProcessRegistry.terminate_owned",
                lambda self, **k: killed.append(k) or 1):
    inst._on_primary_cta()
emit("stop_sets_event_and_kills_encoder",
     inst._overscaled_cancel.is_set() and killed and killed[0].get("owner") == "overscaled_render", killed)
emit("stopping_state_is_shown", inst._cta_action != "overscaled_cancel", inst._cta_action)
emit("earlier_runs_manager_is_not_cancelled", not stale_manager.request_cancel.called, "")
inst._overscaled_running = False; inst._overscaled_cancel.clear()

# A full run that ends cancelled restores the UI with no error dialog.
class _Inline:
    def __init__(self, target=None, daemon=None, **k): self.t = target
    def start(self): self.t()
from scene_graph.app_integration import OverscaledGenerationResult
real_after = inst.after
inst.after = lambda ms, fn=None, *a: fn(*a) if fn else None
dialogs.clear()
run_manager = mock.Mock()
def fake_generate(*args, **kwargs):
    kwargs["on_manager_ready"](run_manager)   # this run's manager comes up...
    inst._on_overscaled_cancel()              # ...and the user presses Stop
    return OverscaledGenerationResult(ok=False, errors=["Cancelled"], cancelled=True)
try:
    with mock.patch("scene_graph.app_integration.generate_overscaled_video", side_effect=fake_generate), \
            mock.patch("video_generator.transcribe_audio", side_effect=RuntimeError("no whisper")), \
            mock.patch("threading.Thread", _Inline):
        inst._run_overscaled_generation()
finally:
    inst.after = real_after
emit("cancelled_run_restores_ui_without_error_dialog",
     not inst._overscaled_running and not any(d[0] == "error" for d in dialogs)
     and inst._overscaled_status_var.get() == "Cancelled" and inst._cta_action != "overscaled_cancel",
     f"running={inst._overscaled_running} dialogs={dialogs} status={inst._overscaled_status_var.get()}")
emit("next_run_starts_with_a_clear_stop_flag", not inst._overscaled_cancel.is_set(), "")
emit("this_runs_manager_is_cancelled_then_cleared",
     run_manager.request_cancel.called and run_manager.reset_cancel.called and inst._overscaled_run_manager is None,
     f"cancel={run_manager.request_cancel.called} reset={run_manager.reset_cancel.called}")
os._exit(0)
"""


class TestStopButtonLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        script = Path(tempfile.mkdtemp()) / "_stop_live.py"
        script.write_text(_LIVE, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120,
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

    def test_running_shows_enabled_stop(self):
        self._check("running_shows_enabled_stop")

    def test_stop_sets_event_and_kills_encoder(self):
        self._check("stop_sets_event_and_kills_encoder")

    def test_stopping_state_is_shown(self):
        self._check("stopping_state_is_shown")

    def test_cancelled_run_restores_ui_without_error_dialog(self):
        self._check("cancelled_run_restores_ui_without_error_dialog")

    def test_next_run_starts_with_a_clear_stop_flag(self):
        self._check("next_run_starts_with_a_clear_stop_flag")

    def test_earlier_runs_manager_is_not_cancelled(self):
        self._check("earlier_runs_manager_is_not_cancelled")

    def test_this_runs_manager_is_cancelled_then_cleared(self):
        self._check("this_runs_manager_is_cancelled_then_cleared")


if __name__ == "__main__":
    unittest.main()
