"""Toy Vehicles in the real app (live app in a subprocess, same convention as test_toon_tales_app.py): the style card under
Kids, an opt-in page built only when picked, both modes (Songs from a colour list, Stories from a story file), nothing
starting until Generate, Generate -> Render through the primary button, the video tracked, a changed pick asking for
Generate again, and Stop. The engine is stubbed (no Blender); toycolors/runner.check is exercised for real at the end."""
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
emit("style_card", "Toy Vehicles" in R.STANDALONE and any("Toy Vehicles" in n for t, n in R.GROUPS if t == "Kids") and "Toy Vehicles" in R.EXTRA_CARDS)
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
ws = ProjectWorkspace(project_id="p1", title="Toy Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()
shown = lambda w: bool(w.grid_info())

emit("section_not_built_at_start", getattr(inst, "_tv_block", None) is None)
inst._on_style_pick("Toy Vehicles"); inst.update_idletasks()
emit("picked", inst._active_style() == "Toy Vehicles" and shown(inst._tv_block), inst._active_style())
emit("cta_generate_first", inst._cta_action == "tv_generate", str(inst._cta_action))
emit("songs_mode_first", inst._tv_mode_var.get() == "Songs" and shown(inst._tv_songs_row) and not shown(inst._tv_story_row))

from ui import toy_vehicles_section as K
calls = []
class Stub:
    def check(self, mode, source):
        calls.append(("check", mode, source))
        return {"ok": True, "errors": [], "title": "T", "seconds": 40.0, "shots": 5}
    def render(self, mode, source, output, draft=False, progress=None, cancel=None, log=None):
        calls.append(("render", mode, source, draft))
        for k in range(50):
            if cancel(): raise RuntimeError("Stopped.")
            time.sleep(0.01)
        Path(output).write_bytes(b"\0" * 2048); progress(1.0, "done")
        return {"seconds": 40.0, "output": output}
real = K._runner()
sys.modules["tv_runner"] = Stub()

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

inst._tv_colours_var.set("red, blue"); inst.update_idletasks()
emit("typing_starts_nothing", calls == [] and not inst._tv_running and inst._tv_planned is None)
K.cta(inst, inst._cta_action)
emit("generate_songs", wait(lambda: not inst._tv_running and inst._tv_planned is not None) and calls[-1] == ("check", "Songs", "red, blue"), str(calls))
emit("cta_render_after_generate", inst._cta_action == "tv_render", str(inst._cta_action))
K.cta(inst, inst._cta_action)
emit("render_songs", wait(lambda: not inst._tv_running) and Path(inst.output_var.get()).is_file() and calls[-1][:2] == ("render", "Songs"), str(calls[-1:]))

story = str(Path("toycolors/stories/zip_mud.json").resolve())
inst._tv_mode_var.set("Stories"); K._show_mode(inst); inst._tv_plan_var.set(story); inst.update_idletasks()
emit("story_mode_shows_file", shown(inst._tv_story_row) and not shown(inst._tv_songs_row))
emit("changed_pick_needs_generate", inst._tv_planned is None and inst._cta_action == "tv_generate", str(inst._cta_action))
K.on_generate(inst)
emit("generate_story", wait(lambda: not inst._tv_running and inst._tv_planned is not None) and calls[-1] == ("check", "Stories", story), str(calls[-1:]))
settings = Path(ws.state_dir) / "toy_vehicles" / "settings.json"
emit("project_remembers", settings.is_file() and json.loads(settings.read_text())["planned"]["source"] == story)
inst._tv_res_var.set("1280x720 fast preview"); inst.update_idletasks()
K.on_render(inst)
emit("render_story_preview", wait(lambda: not inst._tv_running) and calls[-1] == ("render", "Stories", story, True), str(calls[-1:]))

K.on_render(inst); wait(lambda: inst._tv_running, 2); K.cancel(inst)
emit("stop", wait(lambda: not inst._tv_running) and "Stopped" in inst._tv_status_var.get(), inst._tv_status_var.get())

inst._on_style_pick("Kids Learn"); inst.update_idletasks()
emit("leaving_hides_the_page", not shown(inst._tv_block) and not inst._tv_active)

c = real.check("Stories", story)
emit("real_check_story", c["ok"] and c["shots"] == 11, str(c))
c = real.check("Songs", "red, purple")
emit("real_check_bad_colour", not c["ok"] and "purple" in c["errors"][0], str(c))
OUT.write("DONE\n"); OUT.flush()
os._exit(0)
'''


class ToyVehiclesAppTest(unittest.TestCase):
    def test_toy_vehicles_page_in_the_real_app(self):
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
