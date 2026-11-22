"""Kids Stories in the real app (live app in a subprocess, same convention as test_toy_vehicles_app.py): the style card
under Kids, an opt-in page built only when picked, nothing starting until Generate, Generate -> Render through the primary
button, the video tracked, the project remembering a voiced story, a changed file asking for Generate again, and Stop.
The engine is stubbed for the page; then cartoon2d/kidstory.py packs, checks and unpacks a real story, and
script_runner.command / dispatch run a script the way the installed app does (no child Python)."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time, json, shutil
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
emit("style_card", "Kids Stories" in R.STANDALONE and any("Kids Stories" in n for t, n in R.GROUPS if t == "Kids") and "Kids Stories" in R.EXTRA_CARDS)
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
    inst._window_exists = True
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
infos = []
_app.messagebox.showinfo = lambda *a, **k: infos.append(a)
_app.messagebox.showerror = lambda *a, **k: emit("unexpected_error_box", False, str(a))
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Kids Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()
shown = lambda w: bool(w.grid_info())

emit("section_not_built_at_start", getattr(inst, "_ks_block", None) is None)
inst._on_style_pick("Kids Stories"); inst.update_idletasks()
emit("picked", inst._active_style() == "Kids Stories" and shown(inst._ks_block), inst._active_style())
emit("cta_generate_first", inst._cta_action == "ks_generate", str(inst._cta_action))

from ui import kids_stories_section as K
real = K._runner()
calls = []
class Stub:
    def generate(self, source, work, progress=None, cancel=None, log=None):
        calls.append(("generate", source))
        tl = Path(work) / "build" / "audio" / "timeline.json"
        tl.parent.mkdir(parents=True, exist_ok=True); tl.write_text("{}")
        return {"title": "T", "lines": 9, "seconds": 58.0, "cast": ["lina", "tobi"], "problems": ["PROBLEM no setback"]}
    def render(self, work, output, draft=False, progress=None, cancel=None, log=None):
        calls.append(("render", work, draft))
        for k in range(50):
            if cancel(): raise RuntimeError("Stopped.")
            time.sleep(0.01)
        Path(output).write_bytes(b"\0" * 2048); progress(1.0, "done")
        return {"seconds": 58.0, "path": output}
sys.modules["ks_runner"] = Stub()

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

story = tmp / "ep.kidstory"
shutil.copy("cartoon2d/stories/ch3_ep01_playground.kidstory", story)
inst._ks_plan_var.set(str(story)); inst.update_idletasks()
emit("picking_starts_nothing", calls == [] and not inst._ks_running and inst._ks_planned is None)
K.cta(inst, inst._cta_action)
emit("generate", wait(lambda: not inst._ks_running and inst._ks_planned is not None) and calls[-1] == ("generate", str(story)), str(calls))
emit("checker_note_shown", "1 thing" in inst._ks_status_var.get(), inst._ks_status_var.get())
emit("cta_render_after_generate", inst._cta_action == "ks_render", str(inst._cta_action))
settings = Path(ws.state_dir) / "kids_stories" / "settings.json"
emit("project_remembers", settings.is_file() and json.loads(settings.read_text())["planned"]["source"] == str(story))
inst._ks_res_var.set("Fast (quicker encode, a little larger)"); inst.update_idletasks()
K.cta(inst, inst._cta_action)
emit("render", wait(lambda: not inst._ks_running) and Path(inst.output_var.get()).is_file() and calls[-1][0] == "render" and calls[-1][2] is True, str(calls[-1:]))

K.on_render(inst); wait(lambda: inst._ks_running, 2); K.cancel(inst)
emit("stop", wait(lambda: not inst._ks_running) and "Stopped" in inst._ks_status_var.get(), inst._ks_status_var.get())

inst._ks_restored_for = None; inst._ks_planned = None
K._restore(inst)
emit("restored_ready", inst._ks_planned is not None and inst._ks_planned["source"] == str(story))
story.touch(); os.utime(story, (time.time() + 5, time.time() + 5))
K.on_render(inst)
emit("changed_file_needs_generate", any("Generate" in a[0] for a in infos), str(infos[-1:]))

inst._on_style_pick("Kids Learn"); inst.update_idletasks()
emit("leaving_hides_the_page", not shown(inst._ks_block) and not inst._ks_active)

c = real.check(str(story))
emit("real_check", c["errors"] == [] and c["lines"] == 154 and "tobi" in c["cast"], str(c)[:200])
bad = tmp / "bad.kidstory"; bad.write_text("not a zip")
emit("real_check_bad_file", real.check(str(bad))["errors"], "")
import importlib; sys.path.insert(0, "cartoon2d"); ks = importlib.import_module("kidstory")
rp = ks.unpack(str(story), tmp / "work")
r = json.loads(rp.read_text())
emit("unpack_paths", all(Path(p["background"]).is_file() for p in r["places"].values()) and Path(r["script"]).is_file()
     and Path(r["places"]["slide"]["background"] + ".depth.npy").is_file(), "")
import script_runner as SR
emit("command_from_source", SR.command("cartoon2d/render.py", ["a"])[1:] == ["cartoon2d/render.py", "a"])
OUT.write("DONE\n"); OUT.flush()
os._exit(0)
'''


class KidsStoriesAppTest(unittest.TestCase):
    def test_kids_stories_page_in_the_real_app(self):
        root = Path(__file__).resolve().parent
        r = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=str(root), capture_output=True, text=True, timeout=130)
        out = r.stdout
        if "SKIP:" in out:
            self.skipTest(out.split("SKIP:", 1)[1].splitlines()[0])
        fails = [ln for ln in out.splitlines() if ln.startswith("FAIL:")]
        self.assertIn("DONE", out, f"app script did not finish\nstdout:\n{out[-3000:]}\nstderr:\n{r.stderr[-3000:]}")
        self.assertEqual(fails, [], out)

    def test_run_script_dispatch_like_the_installed_app(self):
        """`<app> --run-script tool.py args` runs the tool with no window (each render piece in the installed app)."""
        root = Path(__file__).resolve().parent
        r = subprocess.run([sys.executable, "app.py", "--run-script", "cartoon2d/kidstory.py", "check",
                            "cartoon2d/stories/ch3_ep01_playground.kidstory"], cwd=str(root), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn('"errors": []', r.stdout)


if __name__ == "__main__":
    unittest.main()
