"""Clicking Render Video moves the app to the Export page.

The Export page ("render" in the shell) shows the live progress of a render,
so a render that starts while the user is on Visuals / Voiceover / Script must
take them there. Generate Assets (no render) and a start that is refused
(validation error) must NOT move the page.

Subprocess-isolated live VideoGeneratorApp, same convention as
test_select_by_source.py (in-process Tk construction corrupts the shared root).
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
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())


def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}")


try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

from providers.base import SceneRow

try:
    inst = _app.VideoGeneratorApp()
    inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

audio = Path(tempfile.mkdtemp()) / "vo.wav"
audio.write_bytes(b"RIFF")

# Everything Generate does before it starts working is stubbed; only the
# navigation decision is under test.
inst._revalidate_license = lambda: (True, None)
inst._run_pipeline = lambda *a, **k: None
inst._track_generation_start = lambda *a, **k: None


def press_generate(*, allow_render, validate_error=None):
    inst._running = False
    # Set right before the click: switching pages refreshes some of this state.
    inst.audio_var.set(str(audio))
    inst._scene_rows = [SceneRow(scene_number="1", script_segment="a", asset_type="video", prompt="p")]
    inst._qa_snapshot = lambda: SimpleNamespace(allow_render=allow_render, visual_fail_blocking=0, visual_fail=0, visual_weak=0)
    inst._validate = lambda require_audio=False: ({}, validate_error)
    with mock.patch.object(_app.messagebox, "showerror", lambda *a, **k: None):
        inst._on_generate()
    inst._running = False


def start_on(view):
    inst._shell.navigate(view)
    return inst._shell.active_view


emit("starts_on_visuals", start_on("visual_plan") == "visual_plan", inst._shell.active_view)
press_generate(allow_render=True)
emit("render_opens_export_page", inst._shell.active_view == "render", inst._shell.active_view)

start_on("audio")
press_generate(allow_render=True)
emit("render_from_audio_opens_export_page", inst._shell.active_view == "render", inst._shell.active_view)

start_on("visual_plan")
press_generate(allow_render=False)
emit("generate_assets_stays_on_page", inst._shell.active_view == "visual_plan", inst._shell.active_view)

start_on("visual_plan")
press_generate(allow_render=True, validate_error="bad input")
emit("refused_start_stays_on_page", inst._shell.active_view == "visual_plan", inst._shell.active_view)

start_on("render")
press_generate(allow_render=True)
emit("already_on_export_stays_there", inst._shell.active_view == "render", inst._shell.active_view)

sys.stdout.flush()
os._exit(0)
'''


class TestRenderOpensExportPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script_path = Path(tempfile.mkdtemp()) / "_render_opens_export_live_check.py"
        script_path.write_text(_LIVE_CHECK_SCRIPT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=90,
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
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout}\nstderr:\n{self._stderr[-2000:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_render_opens_the_export_page(self):
        self._check("starts_on_visuals")
        self._check("render_opens_export_page")
        self._check("render_from_audio_opens_export_page")

    def test_generate_assets_does_not_move_the_page(self):
        self._check("generate_assets_stays_on_page")

    def test_refused_start_does_not_move_the_page(self):
        self._check("refused_start_stays_on_page")

    def test_already_on_export_stays_there(self):
        self._check("already_on_export_stays_there")


if __name__ == "__main__":
    unittest.main()
