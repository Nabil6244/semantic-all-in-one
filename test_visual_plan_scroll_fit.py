"""The Visual Plan table never goes blank after the plan shrinks while scrolled down (live 2026-10-21, What If #027: 108 scenes,
an empty table for the rest of the run). Real app in a subprocess (same convention as test_starmap_app_integration.py)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, os.getcwd())
_OUT = open(sys.argv[1], "w", buffering=1)          # the app takes over stdout: results go to a file
print = lambda *a, **k: _OUT.write(" ".join(str(x) for x in a) + "\n")
try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from providers.base import SceneRow
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.geometry("1400x900+0+0"); inst.update(); inst._goto_workflow_view("visual_plan"); inst.update()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        inst.update(); time.sleep(0.01)

def rows(n, tag):
    return [SceneRow(scene_number=str(i + 1), script_segment=f"line {i + 1}", asset_type="stock_image", prompt=f"{tag} {i + 1}") for i in range(n)]

def shown():
    c = inst._scenes_list._parent_canvas
    top, h, n = c.canvasy(0), c.winfo_height(), 0
    for w in inst._scene_row_widgets.values():
        r = w.get("row")
        if r is not None and r.winfo_ismapped() and r.winfo_y() + r.winfo_height() > top and r.winfo_y() < top + h:
            n += 1
    return n

for big, small in ((300, 108), (108, 20)):
    inst._scene_rows = rows(big, "a"); inst._render_scene_rows(); pump(1.5)
    inst._scenes_list._parent_canvas.yview_moveto(1.0); pump(0.4)
    inst._scene_rows = rows(small, "b"); inst._render_scene_rows(); pump(2)
    print(f"{'PASS' if shown() > 0 else 'FAIL'}:shrink_{big}_to_{small}:{shown()} rows on screen")
inst._scene_rows = []; inst._render_scene_rows(); pump(0.5)
inst._scene_rows = rows(108, "c"); inst._render_scene_rows(); pump(2)
print(f"{'PASS' if shown() > 0 else 'FAIL'}:cleared_then_relisted:{shown()} rows on screen")
os._exit(0)
'''


class VisualPlanScrollFit(unittest.TestCase):
    def test_the_table_is_never_blank_after_the_plan_shrinks(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            script = Path(d) / "probe.py"
            script.write_text(_SCRIPT, encoding="utf-8")
            report = Path(d) / "report.txt"
            try:
                subprocess.run([sys.executable, str(script), str(report)], cwd=str(Path(__file__).resolve().parent),
                               capture_output=True, text=True, timeout=240)
            except subprocess.TimeoutExpired:
                self.fail("the app did not finish the probe in 240 s")
            out = report.read_text(encoding="utf-8") if report.is_file() else ""
        if out.startswith("SKIP:"):
            self.skipTest(out.strip())
        results = [ln for ln in out.splitlines() if ln.startswith(("PASS:", "FAIL:"))]
        self.assertEqual(len(results), 3, out[-2000:])
        for ln in results:
            self.assertTrue(ln.startswith("PASS:"), ln)


if __name__ == "__main__":
    unittest.main()
