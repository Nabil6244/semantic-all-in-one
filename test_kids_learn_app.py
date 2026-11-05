"""Kids Learn in the real app (live app in a subprocess, same convention as test_rules_horror_app.py): the style card, an opt-in page that
builds only when picked, nothing starting until Generate, Generate -> Render through the primary button, the finished video tracked for
Export, options changed after Generate asking for Generate again, and Stop. The engine is stubbed here (no voice service, no GPU);
cartoon3d-engine/runner.py and the lesson renderer have their own checks."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time, json, threading
import faulthandler; faulthandler.dump_traceback_later(100, exit=True)   # a hang prints every thread's stack and ends, instead of eating the CI time limit
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
emit("style_card", "Kids Learn" in R.STANDALONE and any("Kids Learn" in names for _t, names in R.GROUPS) and "Kids Learn" in R.EXTRA_CARDS)
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
    # Windows: CustomTkinter's first mainloop() sets the title-bar colour and calls update(), which never returns while the app's
    # after(0) animation runs, so the test hung there on Windows CI. The window counts as shown already, which skips that step.
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

emit("section_not_built_at_start", getattr(inst, "_kl_block", None) is None)
inst._on_style_pick("Kids Learn"); inst.update_idletasks()
emit("picked", inst._active_style() == "Kids Learn" and shown(inst._kl_block) and inst.generation_mode == "normal", inst._active_style())
emit("cta_generate_first", inst._cta_action == "kl_generate", str(inst._cta_action))
emit("render_disabled_before_generate", str(inst._kl_render_btn.cget("state")) == "disabled")

# a stub engine: records calls, writes a tiny file for Render
from ui import kids_learn_section as K
calls = []
class Stub:
    def host_ready(self): return True
    def plan(self, csv, work, progress=None, cancel=None, log=print, **o):
        calls.append(("plan", csv, o)); progress(1.0, "Planned"); return {"duration": 12.0, "lines": 3, "props": 1, "cards": 1, "warnings": [], "plan_file": ""}
    def render(self, csv, work, output, progress=None, cancel=None, log=print, **o):
        calls.append(("render", csv, o))
        for k in range(50):
            if cancel(): raise RuntimeError("stopped")
            time.sleep(0.01)
        Path(output).write_bytes(b"\0" * 2048); progress(1.0, "Done")
        return {"output": output, "frames": 10, "wall_s": 1.0, "audio": {"lufs": -14.0, "sfx": 4}, "errors": []}
sys.modules["kl_runner"] = Stub()

csv = Path("cartoon3d-engine/samples/first_words.csv").resolve()
vo = tmp / "my_voice.wav"
import subprocess as _sp
_sp.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "2", str(vo)], check=True)
inst._kl_csv_var.set(str(csv)); inst._kl_vo_var.set(str(vo)); inst._kl_music_var.set("Calm"); inst.update_idletasks()
emit("choosing_starts_nothing", calls == [] and not inst._kl_running and inst._kl_planned is None)

def wait(cond, sec=20):
    # mainloop with a poll: the app keeps an after(0) animation going, so a bare update() loop never returns (as in test_rules_horror_app.py)
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

inst._on_primary_cta() if hasattr(inst, "_on_primary_cta") else K.cta(inst, inst._cta_action)
emit("generate_ran", wait(lambda: not inst._kl_running and inst._kl_planned is not None), str(calls))
emit("options_reach_engine", calls and calls[0][2].get("music") == "calm" and calls[0][2].get("host") == "host3d", str(calls[:1]))
emit("voiceover_reaches_engine", calls and calls[0][2].get("voiceover") == str(vo), str(calls[:1]))
emit("cta_render_after_generate", inst._cta_action == "kl_render", str(inst._cta_action))
settings = Path(ws.state_dir) / "kids_learn" / "settings.json"
emit("project_remembers", settings.is_file() and json.loads(settings.read_text())["planned"]["csv"] == str(csv))

inst._kl_world_var.set("Park"); inst.update_idletasks()
K.on_render(inst)
emit("changed_options_ask_for_generate", any("Generate" in str(a) for a in infos) and not inst._kl_running)
inst._kl_world_var.set("Playroom"); inst.update_idletasks()

K.on_render(inst)
emit("render_ran", wait(lambda: not inst._kl_running) and Path(inst.output_var.get()).is_file(), inst.output_var.get())
emit("render_used_the_plan", [c[0] for c in calls] == ["plan", "render"])

K.on_render(inst); wait(lambda: inst._kl_running, 2); K.cancel(inst)
emit("stop", wait(lambda: not inst._kl_running) and "Stopped" in inst._kl_status_var.get(), inst._kl_status_var.get())

inst._on_style_pick("Roblox Cinema") if "Roblox Cinema" in R.STANDALONE else None; inst.update_idletasks()
emit("leaving_hides_the_page", not shown(inst._kl_block) and not inst._kl_active)
OUT.write("DONE\n"); OUT.flush()
os._exit(0)
'''


class KidsLearnAppTest(unittest.TestCase):
    def test_kids_learn_page_in_the_real_app(self):
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
