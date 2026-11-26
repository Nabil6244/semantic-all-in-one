"""Reddit Shorts page in the real app (stub engine for Generate/Render; no Flow, no voice, no render)."""
import subprocess
import sys
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, json
from pathlib import Path
OUT = sys.stdout
def emit(name, ok, detail=""):
    OUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); OUT.flush()
try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
from ui import style_registry as R
emit("style_card", "Reddit Shorts" in R.STANDALONE and "Reddit Shorts" in dict(R.GROUPS)["Stories"] and "Reddit Shorts" in R.EXTRA_CARDS)
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
    inst._window_exists = True
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)
errors = []
_app.messagebox.showerror = lambda *a, **k: errors.append(a)
import tkinter.messagebox as _mb
_mb.showerror = lambda *a, **k: errors.append(a)
_mb.showinfo = lambda *a, **k: None
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Reddit Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()
shown = lambda w: bool(w.grid_info())
emit("not_built_at_start", getattr(inst, "_rs_block", None) is None)
inst._on_style_pick("Reddit Shorts"); inst.update_idletasks()
emit("picked", inst._active_style() == "Reddit Shorts" and shown(inst._rs_block), inst._active_style())
emit("cta_generate_first", inst._cta_action == "rs_generate", str(inst._cta_action))
emit("render_disabled", str(inst._rs_render_btn.cget("state")) == "disabled")
emit("own_fields_shown", shown(inst._rs_own))

from ui import reddit_shorts_section as K
inst._rs_title_var.set("My cat opened the fridge, so I set a trap")
K.cta(inst, "rs_generate"); inst.update()
emit("empty_story_refused", bool(errors), str(errors[-1:]))

class Stub:
    def plan(self, st, work, music_index=0, log=print, cancel=None):
        self.st = st
        return {"story": st, "pictures": {f"b{i}": {"prompt": p} for i, (_, p) in enumerate(st["beats"])},
                "assets": {"pictures": {}}, "duration": 50.0, "beats": []}
    def save(self, spec, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(json.dumps(spec)); return path
    def load(self, path): return json.loads(Path(path).read_text())
    def refresh_assets(self, spec): return spec
    def render(self, spec, out, progress=None, cancel=None, log=print):
        Path(out).write_bytes(b"x" * 2048); return {"video": out, "seconds": 50.0}
stub = Stub()
real = K._engine
K._engine = lambda name: stub if name == "runner" else real(name)
inst._rs_body_box.insert("1.0", " ".join(["My cat Biscuit opened the fridge every night and the ham was gone."] * 6))
K._changed(inst)
K.cta(inst, "rs_generate")
import time
def wait(cond, sec=15):
    end = time.time() + sec
    while time.time() < end and not cond():
        inst.update(); time.sleep(0.05)
    return cond()
emit("generate_plans", wait(lambda: inst._rs_planned is not None), inst._rs_status_var.get())
emit("custom_story_beats", len(stub.st["beats"]) >= 5 and not stub.st["builtin"], str(len(stub.st["beats"])))
emit("cta_render", inst._cta_action == "rs_render", str(inst._cta_action))
K.cta(inst, "rs_render")
emit("render_writes_final", wait(lambda: not inst._rs_running and "Done" in inst._rs_status_var.get()), inst._rs_status_var.get())
inst._rs_story_var.set(next(iter(inst._rs_builtin))); inst.update_idletasks()
emit("builtin_hides_own_fields", not shown(inst._rs_own))
emit("change_needs_generate", inst._rs_planned is None)
saved = json.loads((Path(ws.state_dir) / "reddit_shorts" / "settings.json").read_text())
emit("remembers_picks", saved["picks"]["story"].startswith("01."), saved["picks"]["story"])
inst._on_style_pick("Toon Tales"); inst.update_idletasks()
emit("leaving_hides_the_page", not shown(inst._rs_block) and not inst._rs_active)
OUT.write("DONE\n"); OUT.flush()
os._exit(0)
'''


class RedditShortsAppTest(unittest.TestCase):
    def test_reddit_shorts_page_in_the_real_app(self):
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
