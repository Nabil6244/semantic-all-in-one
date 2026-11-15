"""Toon Tales in the real app (live app in a subprocess, same convention as test_kids_learn_app.py): the style card under Stories,
an opt-in page built only when picked, nothing starting until Generate, Generate asking before Flow paints missing places,
Generate -> Render through the primary button, the video tracked for Export, another plan after Generate asking for Generate
again, and Stop. The engine is stubbed (no Flow, no Blender); toontales/runner.py is exercised by its own run."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time, json
import faulthandler; faulthandler.dump_traceback_later(100, exit=True)
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
from ui import style_registry as R
emit("style_card", "Toon Tales" in R.STANDALONE and any("Toon Tales" in n for t, n in R.GROUPS if t == "Stories") and "Toon Tales" in R.EXTRA_CARDS)
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
    inst._window_exists = True
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
infos, asks = [], []
_app.messagebox.showinfo = lambda *a, **k: infos.append(a)
_app.messagebox.showerror = lambda *a, **k: emit("unexpected_error_box", False, str(a))
import tkinter.messagebox as _mb
_mb.askyesno = lambda *a, **k: (asks.append(a), True)[1]
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Toon Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()
shown = lambda w: bool(w.grid_info())

emit("section_not_built_at_start", getattr(inst, "_tt_block", None) is None)
inst._on_style_pick("Toon Tales"); inst.update_idletasks()
emit("picked", inst._active_style() == "Toon Tales" and shown(inst._tt_block), inst._active_style())
emit("cta_generate_first", inst._cta_action == "tt_generate", str(inst._cta_action))
emit("render_disabled_before_generate", str(inst._tt_render_btn.cget("state")) == "disabled")

from ui import toon_tales_section as K
calls = []
class Stub:
    painted = False
    def check(self, plan):
        calls.append(("check", plan))
        return {"ok": True, "title": "Test Story", "id": "t", "errors": [], "warnings": ["-- length: short"], "shots": 20,
                "seconds": 40.0, "places": ["a", "b"], "missing": [] if self.painted else ["b"]}
    def paint(self, plan, progress=None, cancel=None, log=None):
        calls.append(("paint", plan)); self.painted = True; progress(1.0, "painted")
    def render(self, plan, output, draft=False, progress=None, cancel=None, log=None):
        calls.append(("render", plan, draft))
        for k in range(50):
            if cancel(): raise RuntimeError("Stopped.")
            time.sleep(0.01)
        Path(output).write_bytes(b"\0" * 2048); progress(1.0, "done")
        return {"seconds": 40.0, "output": output}
sys.modules["tt_runner"] = Stub()

plan = Path("toontales/stories/revenge_trade/plan.json").resolve()
inst._tt_plan_var.set(str(plan)); inst.update_idletasks()
emit("choosing_starts_nothing", calls == [] and not inst._tt_running and inst._tt_planned is None)

def wait(cond, sec=20):
    st = {"t0": time.time(), "ok": False}
    def poll():
        if cond():
            st["ok"] = True; inst.quit()
        elif time.time() - st["t0"] > sec:
            inst.quit()
        else:
            inst.after(50, poll)
    inst.after(50, poll)
    inst.mainloop()
    return st["ok"]

K.cta(inst, inst._cta_action)
emit("generate_ran", wait(lambda: not inst._tt_running and inst._tt_planned is not None), str(calls))
emit("asked_before_painting", len(asks) == 1 and "Paint" in str(asks[0]), str(asks))
emit("painted_then_checked", [c[0] for c in calls] == ["check", "paint", "check"], str(calls))
emit("cta_render_after_generate", inst._cta_action == "tt_render", str(inst._cta_action))
settings = Path(ws.state_dir) / "toon_tales" / "settings.json"
emit("project_remembers", settings.is_file() and json.loads(settings.read_text())["planned"]["plan"] == str(plan))

other = Path("toontales/stories/moon_hoax/plan.json").resolve()
inst._tt_plan_var.set(str(other)); inst.update_idletasks()
K.on_render(inst)
emit("other_plan_asks_for_generate", any("Generate" in str(a) for a in infos) and not inst._tt_running)
inst._tt_plan_var.set(str(plan)); inst.update_idletasks()

K.on_render(inst)
emit("render_ran", wait(lambda: not inst._tt_running) and Path(inst.output_var.get()).is_file(), inst.output_var.get())
emit("render_used_the_plan", calls[-1][:2] == ("render", str(plan)) and calls[-1][2] is False, str(calls[-1:]))

K.on_render(inst); wait(lambda: inst._tt_running, 2); K.cancel(inst)
emit("stop", wait(lambda: not inst._tt_running) and "Stopped" in inst._tt_status_var.get(), inst._tt_status_var.get())

inst._on_style_pick("Kids Learn"); inst.update_idletasks()
emit("leaving_hides_the_page", not shown(inst._tt_block) and not inst._tt_active)
OUT.write("DONE\n"); OUT.flush()
os._exit(0)
'''


class ToonTalesAppTest(unittest.TestCase):
    def test_toon_tales_page_in_the_real_app(self):
        root = Path(__file__).resolve().parent
        r = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=str(root), capture_output=True, text=True, timeout=130)
        out = r.stdout
        if "SKIP:" in out:
            self.skipTest(out.split("SKIP:", 1)[1].splitlines()[0])
        fails = [ln for ln in out.splitlines() if ln.startswith("FAIL:")]
        self.assertIn("DONE", out, f"app script did not finish\nstdout:\n{out[-3000:]}\nstderr:\n{r.stderr[-3000:]}")
        self.assertEqual(fails, [], out)


if __name__ == "__main__":
    unittest.main()
