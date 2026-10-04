"""The single Video style picker (Visual Director): one choice drives the styles' own switches and handlers, only the chosen style's
card is shown, the picker follows a style changed any other way, and a running render cannot be switched away from.

Live VideoGeneratorApp in a subprocess (same convention as test_pakmap_app_integration.py: in-process Tk construction corrupts the
shared root). No network, no rendering."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
OUT = sys.stdout

def emit(name, ok, detail=""):
    OUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); OUT.flush()

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
_app.messagebox.showinfo = lambda *a, **k: None
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()

def shown(w):
    return bool(w.grid_info())

def state():
    return (inst.generation_mode, inst._style_picker.get(), shown(inst._overscaled_block), shown(inst._pakmap_block), shown(inst._hybrid_block))

emit("starts_normal_with_no_style_card", state() == ("normal", "Normal video", False, False, False), str(state()))
emit("old_switches_are_hidden", not any(shown(w) for w in (inst._overscaled_switch, inst._pakmap_switch, inst._hybrid_switch, inst._overscaled_style_segmented)))

inst._on_style_pick("pakMap"); inst.update_idletasks()
emit("pakmap_picked", state() == ("pakmap", "pakMap", False, True, False) and inst._pakmap_enabled_var.get() and shown(inst._pakmap_controls), str(state()))

inst._on_style_pick("Hybrid Map"); inst.update_idletasks()
emit("hybrid_picked_and_pakmap_steps_aside", state() == ("hybrid", "Hybrid Map", False, False, True) and not inst._pakmap_enabled_var.get()
     and inst._hybrid_enabled_var.get(), str(state()))

inst._on_style_pick("Exp Solar"); inst.update_idletasks()
emit("exp_solar_picked", state() == ("overscaled", "Exp Solar", True, False, False) and inst._overscaled_style_preset_id == "exp_solar"
     and not inst._hybrid_enabled_var.get() and inst._overscaled_title_var.get() == "Exp Solar", str(state()))

inst._on_style_pick("Overscaled"); inst.update_idletasks()
emit("overscaled_picked", state() == ("overscaled", "Overscaled", True, False, False) and inst._overscaled_style_preset_id == "overscaled", str(state()))

inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("normal_picked_and_every_style_steps_aside", state() == ("normal", "Normal video", False, False, False)
     and not (inst._overscaled_enabled_var.get() or inst._pakmap_enabled_var.get() or inst._hybrid_enabled_var.get()), str(state()))

# a style switched on another way (the old handler, as opening a project does) is followed by the picker
inst._pakmap_enabled_var.set(True); inst._on_pakmap_toggle(); inst.update_idletasks()
emit("picker_follows_a_style_switched_elsewhere", state()[:2] == ("pakmap", "pakMap") and shown(inst._pakmap_block), str(state()))

# a running render cannot be switched away from
inst._pakmap_running = True
inst._on_style_pick("Hybrid Map"); inst.update_idletasks()
emit("running_render_keeps_its_style", state()[:2] == ("pakmap", "pakMap") and not inst._hybrid_enabled_var.get(), str(state()))
inst._pakmap_running = False
os._exit(0)
'''


class TestStylePicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_style_picker_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                              cwd=Path(__file__).resolve().parent)
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
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout[-1500:]}\nstderr:\n{self._stderr[-2500:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_picking_each_style(self):
        for n in ("starts_normal_with_no_style_card", "old_switches_are_hidden", "pakmap_picked", "hybrid_picked_and_pakmap_steps_aside",
                  "exp_solar_picked", "overscaled_picked", "normal_picked_and_every_style_steps_aside"):
            with self.subTest(n):
                self._check(n)

    def test_the_picker_follows_and_guards(self):
        for n in ("picker_follows_a_style_switched_elsewhere", "running_render_keeps_its_style"):
            with self.subTest(n):
                self._check(n)


if __name__ == "__main__":
    unittest.main()
