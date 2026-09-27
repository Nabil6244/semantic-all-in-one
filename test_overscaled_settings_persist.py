"""The Overscaled style and the Local Visual Planner switch are saved WITH
the project and restored when it is reopened.

Reproduced: a project built with the planner (Exp Solar, plain narration
CSV) was re-rendered after the app had been restarted. The switch lived only
in the running app, so it silently came back OFF: the CSV went through the
Exp Solar CSV compiler, which reads titles/captions/groups from columns this
CSV doesn't have — the re-render had no chapter titles, no captions and one
image per scene, while the Visual Plan gave no hint anything had changed.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

_LIVE = r'''
import os, sys, csv, tempfile
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
def emit(n, ok, d=""): print(f"{'PASS' if ok else 'FAIL'}:{n}:{str(d)[:300]}")
from tkinter import messagebox
messagebox.showerror = messagebox.showinfo = lambda *a, **k: None
try:
    import app as _app
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace

def project(name, header, row):
    ws = ProjectWorkspace(project_id=name, title=name, seq=1, root=Path(tempfile.mkdtemp()) / name)
    ws.ensure_dirs()
    with open(ws.overscaled_csv_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerow(row)
    return ws

def open_project(ws):
    inst._overscaled_use_local_planner_var.set(False)   # whatever the app had before
    inst._overscaled_style_preset_id = "overscaled"
    inst._activate_workspace(ws, persist=False, clear_session=True)
    inst._bind_workspace_paths()

plain = project("plain", ["scene_number", "script_segment", "visual_hint", "asset_type", "prompt"],
                ["1", "The dam rises above the river.", "", "", ""])
open_project(plain)
emit("plain_narration_project_opens_with_planner_on", inst._overscaled_use_local_planner_var.get(), "")

# The user's own choices are saved and survive a reopen.
inst._overscaled_style_segmented.set("Exp Solar"); inst._on_overscaled_style_change("Exp Solar")
inst._overscaled_use_local_planner_var.set(False); inst._on_overscaled_local_planner_toggle()
open_project(plain)
emit("saved_choices_survive_reopen",
     inst._overscaled_style_preset_id == "exp_solar" and inst._overscaled_use_local_planner_var.get() is False
     and inst._overscaled_style_segmented.get() == "Exp Solar",
     f"style={inst._overscaled_style_preset_id} planner={inst._overscaled_use_local_planner_var.get()}")
inst._overscaled_use_local_planner_var.set(True); inst._on_overscaled_local_planner_toggle()
open_project(plain)
emit("planner_on_survives_reopen", inst._overscaled_use_local_planner_var.get() is True, "")

structured = project("structured", ["scene_number", "script_segment", "node_id", "asset_type", "prompt"],
                     ["1", "The dam rises.", "n1", "stock_image", "dam"])
open_project(structured)
emit("structured_csv_keeps_planner_off_by_default", inst._overscaled_use_local_planner_var.get() is False, "")
os._exit(0)
'''


class TestOverscaledSettingsPersistWithProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        script = Path(tempfile.mkdtemp()) / "_settings_live.py"
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

    def test_plain_narration_project_opens_with_planner_on(self):
        self._check("plain_narration_project_opens_with_planner_on")

    def test_saved_choices_survive_reopen(self):
        self._check("saved_choices_survive_reopen")

    def test_planner_on_survives_reopen(self):
        self._check("planner_on_survives_reopen")

    def test_structured_csv_keeps_planner_off_by_default(self):
        self._check("structured_csv_keeps_planner_off_by_default")


if __name__ == "__main__":
    unittest.main()
