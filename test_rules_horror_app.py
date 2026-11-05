"""Rules Horror in the real app (live app in a subprocess, same convention as test_war_app_section.py): opt-in page, Generate lists the Flow pictures in the
Visuals tab, a picture put there reaches the film, Render makes a real video, Export state is tracked, and the whole run makes no network connection
(so zero Gemini calls). Voice-over words are stubbed (no Whisper) and the voice is silence."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time, socket, json, subprocess
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
OUT = sys.stdout
def emit(name, ok, detail=""):
    OUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); OUT.flush()

outside = []
_orig = socket.socket.connect
def _guard(self, addr, *a, **k):
    host = addr[0] if isinstance(addr, tuple) else str(addr)
    if isinstance(addr, tuple) and host not in ("127.0.0.1", "localhost", "::1"):
        outside.append(str(addr))
        raise OSError("blocked by the test: no outside network")
    return _orig(self, addr, *a, **k)
socket.socket.connect = _guard

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
_app.messagebox.showerror = lambda *a, **k: emit("unexpected_error_box", False, str(a))
tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
inst.update_idletasks()
shown = lambda w: bool(w.grid_info())

emit("section_not_built_at_start", getattr(inst, "_rh_block", None) is None)
inst._on_style_pick("Rules Horror"); inst.update_idletasks()
emit("picked", inst._active_style() == "Rules Horror" and shown(inst._rh_block) and inst.generation_mode == "normal", inst._active_style())
emit("cta_generate_first", inst._cta_action == "rh_generate", str(inst._cta_action))
emit("render_disabled_before_generate", str(inst._rh_render_btn.cget("state")) == "disabled")

# files: the sample CSV, a silent 30 s voice, stubbed words spread evenly over the lines
from rules_horror.csv_io import read_csv
csv = Path("rules_horror/samples/tall_deer.csv").resolve()
voice = tmp / "voice.wav"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "30", str(voice)], check=True)
rows = read_csv(csv)["rows"]
words, t = [], 0.3
per = 29.0 / sum(len(r["line"].split()) for r in rows)
for r in rows:
    for w in r["line"].split():
        words.append((w.lower().strip(".,"), t, t + per * 0.9)); t += per
inst._pakmap_get_words = lambda *a, **k: words
inst._rh_csv_var.set(str(csv)); inst._rh_voice_var.set(str(voice))
inst._rh_res_var.set("720p preview (1280x720)"); inst._rh_fps_var.set("24")
emit("picking_files_plans_nothing", inst._rh_spec_path is None and not getattr(inst, "_scene_rows", None))

def wait(flag="_rh_running", limit=300):
    # mainloop with a poll: the app keeps an after(0) animation going, so a bare update() loop never gets back to the test
    st = {"t0": time.time(), "ok": False}
    def poll():
        if not getattr(inst, flag) and time.time() - st["t0"] > 0.5:
            st["ok"] = True; inst.quit()
        elif time.time() - st["t0"] > limit:
            inst.quit()
        else:
            inst.after(100, poll)
    inst.after(100, poll)
    inst.mainloop()
    return st["ok"]

inst._on_primary_cta()
emit("generate_finished", wait(), "")
spec_path = inst._rh_spec_path
emit("spec_written", bool(spec_path) and Path(spec_path).is_file(), str(spec_path))
import visual_bridge
vrows = visual_bridge.rows(inst, "rules_horror")
emit("visuals_lists_the_flow_pictures", len(vrows) >= 3 and inst._scene_rows_owner == "rules_horror", f"{len(vrows)}")
emit("cta_render_after_generate", inst._cta_action == "rh_render", str(inst._cta_action))
_st = inst._rh_status_var.get()
emit("auto_look_shown", inst._rh_look_var.get().startswith("Auto") and " in " in _st.split(":")[0] and json.loads(Path(spec_path).read_text(encoding="utf-8"))["rh"]["scheme"] in ("mono", "dark", "colour", "deep"), _st[:90])
spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
emit("no_picture_layers_yet", not any(l["type"] == "rh_picture" for l in spec["layers"]))

# a picture put in the Visuals tab reaches the film on the next Generate
from PIL import Image, ImageDraw
img = Image.new("RGB", (1376, 768), (0, 0, 0)); ImageDraw.Draw(img).rectangle([600, 100, 780, 700], fill=(255, 255, 255))
png = tmp / "deer.png"; img.save(png)
folder = visual_bridge.folder("rules_horror", ws)
first = next(r for r in vrows if r.script_segment.startswith("deer:"))
visual_bridge.seed(folder, str(first.scene_number), str(png), "manual", prompt=first.prompt)
inst._rh_table_snapshot = visual_bridge.snapshot(folder, inst._scene_rows)
inst._rh_spec_path = None; inst._sync_primary_cta()
inst._on_primary_cta()
emit("generate_again_finished", wait(), "")
spec = json.loads(Path(inst._rh_spec_path).read_text(encoding="utf-8"))
emit("picture_reaches_the_film", any(l["type"] == "rh_picture" for l in spec["layers"]) and any((Path(inst._rh_spec_path).parent / "media").glob("p*.png")))

# a change in the table after Generate must send the user back to Generate
told = []
_app.messagebox.showinfo = lambda *a, **k: told.append(a)
other = next(r for r in vrows if r.script_segment.startswith("closeup:"))
visual_bridge.seed(folder, str(other.scene_number), str(png), "manual", prompt=other.prompt)
inst._on_primary_cta(); inst.update_idletasks()
emit("table_change_asks_for_generate", bool(told) and not inst._rh_running, str(told)[:80])
inst._rh_table_snapshot = visual_bridge.snapshot(folder, inst._scene_rows)
_app.messagebox.showinfo = lambda *a, **k: None

inst._on_primary_cta()
emit("render_finished", wait(limit=420), "")
out = Path(inst.output_var.get())
emit("video_written", out.is_file() and out.stat().st_size > 20000, str(out))
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip() or 0)
emit("video_length_matches_voice", abs(dur - 30.0) < 1.0, f"{dur}")
emit("no_outside_network", not outside, str(outside[:3]))

inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("leaving_hides_the_page", not shown(inst._rh_block) and not inst._rh_active)
inst._on_style_pick("Rules Horror"); inst._rh_running = True
inst._on_style_pick("Normal video"); inst.update_idletasks()
emit("running_keeps_its_style", inst._active_style() == "Rules Horror")
inst._rh_running = False
os._exit(0)
'''


class TestRulesHorrorApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_rh_app_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
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

    def test_page_and_flow_of_buttons(self):
        for n in ("section_not_built_at_start", "picked", "cta_generate_first", "render_disabled_before_generate", "picking_files_plans_nothing",
                  "generate_finished", "spec_written", "visuals_lists_the_flow_pictures", "cta_render_after_generate", "auto_look_shown", "no_picture_layers_yet"):
            with self.subTest(n):
                self._check(n)

    def test_pictures_and_render(self):
        for n in ("generate_again_finished", "picture_reaches_the_film", "table_change_asks_for_generate", "render_finished", "video_written",
                  "video_length_matches_voice", "no_outside_network"):
            with self.subTest(n):
                self._check(n)

    def test_leaving(self):
        for n in ("leaving_hides_the_page", "running_keeps_its_style"):
            with self.subTest(n):
                self._check(n)


if __name__ == "__main__":
    unittest.main()
