"""Phase 1 style pages: the grouped picker, each style on its own page with Change style, and StarMap Cinema / Explainer as their own
cards (StarMap / Hybrid Map with their look on). Live app in a subprocess, like test_style_picker.py. No network, no rendering."""

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

inst.update_idletasks()
def page():  # (active, picker grid shown, page header shown)
    inst._sync_style_picker(); inst.update_idletasks(); return (inst._active_style(), shown(inst._style_grid), shown(inst._style_page_head))
emit("starts_on_the_grouped_picker", page() == ("Normal video", True, False) and {"General", "Maps", "Space", "Explainers"} <= set(inst._style_group_labels), str(page()))
emit("new_cards_exist", {"StarMap Cinema", "Explainer"} <= set(inst._style_cards), str(sorted(inst._style_cards)))
inst._on_style_pick("Hybrid Map")
emit("hybrid_page_without_explainer", page() == ("Hybrid Map", False, True) and not inst._hybrid_explainer_var.get()
     and not shown(inst._hybrid_explainer_btn), str(page()))
inst._on_style_pick("Explainer")
emit("explainer_is_its_own_style", page() == ("Explainer", False, True) and inst.generation_mode == "hybrid" and inst._hybrid_explainer_var.get() and shown(inst._hybrid_block)
     and shown(inst._hybrid_explainer_btn) and not any(shown(w) for w in inst._hybrid_explainer_widgets if isinstance(w, _app.ctk.CTkSwitch)), str(page()))
inst._on_style_pick("StarMap")
emit("starmap_page_without_cinema", page() == ("StarMap", False, True) and not inst._starmap_cinema_var.get() and not shown(inst._starmap_cinema_tabs), str(page()))
inst._on_style_pick("StarMap Cinema")
emit("starmap_cinema_is_its_own_style", page() == ("StarMap Cinema", False, True) and inst.generation_mode == "starmap" and inst._starmap_cinema_var.get() and shown(inst._starmap_block)
     and shown(inst._starmap_cinema_tabs), str(page()))
inst._style_change_btn.invoke()
emit("change_style_shows_the_picker_and_keeps_the_style", page() == ("StarMap Cinema", True, False) and shown(inst._style_back_btn), str(page()))
inst._style_back_btn.invoke()
emit("back_returns_to_the_page", page() == ("StarMap Cinema", False, True), str(page()))
inst._starmap_running = True
inst._style_change_btn.invoke()
emit("change_style_blocked_while_rendering", page() == ("StarMap Cinema", False, True), str(page()))
inst._starmap_running = False
inst._on_style_pick("Normal video")
emit("normal_video_has_a_page_too", page() == ("Normal video", False, True), str(page()))
inst._on_style_pick("What If"); page()
def _labels(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, _app.ctk.CTkLabel):
            out.append(str(c.cget("text")))
        out += _labels(c)
    return out
_lab = _labels(inst._whatif_block)
emit("whatif_page_has_its_steps", all(t in _lab for t in ("Voiceover", "Script", "Plan", "Sound & look", "Render")) and "Pictures" not in _lab, str([t for t in _lab if t in ("Voiceover", "Script", "Plan", "Pictures", "Sound & look", "Render")]))
_kit = inst._whatif_script_kit
_kit.insert("1.0", "A script typed on the style page."); _kit._kit_push(); inst.update_idletasks()
emit("script_on_the_page_is_the_script_page_script", inst.script_box.get("1.0", "end-1c") == "A script typed on the style page.", repr(inst.script_box.get("1.0", "end-1c")[:60]))
_bad = []
for st in ("Normal video", "Modern Tech News", "Overscaled", "Exp Solar", "pakMap", "Hybrid Map", "Explainer", "StarMap", "StarMap Cinema",
           "War Documentary", "Health Cinema"):
    inst._on_style_pick(st); p = page()
    w = inst._style_wraps.get(st)
    if p[0] != st or w is None or not (shown(w[0]) and shown(w[1])):
        _bad.append((st, p, w is not None)); continue
    lab = _labels(w[0]) + _labels(w[1])
    blk = getattr(inst, {"Overscaled": "_overscaled_block", "Exp Solar": "_overscaled_block", "pakMap": "_pakmap_block",
                  "Hybrid Map": "_hybrid_block", "Explainer": "_hybrid_block", "StarMap": "_starmap_block", "StarMap Cinema": "_starmap_block",
                  "War Documentary": "_war_block", "Health Cinema": "_health_block"}.get(st, "_none"), None)
    own_vo = st in ("War Documentary", "Health Cinema")
    ok = "Pictures" not in lab and "Render" in lab and (("Voiceover" in lab) != own_vo)
    if blk is not None:
        ok = ok and shown(blk) and int(w[0].grid_info()["row"]) < int(blk.grid_info()["row"]) < int(w[1].grid_info()["row"])
    if not ok:
        _bad.append((st, [t for t in lab if t in ("Voiceover", "Script", "Plan", "Pictures", "Render")]))
emit("every_style_page_has_its_steps_around_its_card", not _bad, str(_bad)[:600])
inst._on_style_pick("Normal video"); page()
inst._workspace = ProjectWorkspace(project_id="p2", title="Other", seq=2, root=tmp / "proj2"); inst._sync_style_picker()
emit("a_new_project_opens_on_the_picker", page() == ("Normal video", True, False), str(page()))
os._exit(0)
'''


class TestStylePages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_style_pages_check.py"
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

    def test_style_pages(self):
        for n in ('starts_on_the_grouped_picker', 'new_cards_exist', 'hybrid_page_without_explainer', 'explainer_is_its_own_style', 'starmap_page_without_cinema', 'starmap_cinema_is_its_own_style', 'change_style_shows_the_picker_and_keeps_the_style', 'back_returns_to_the_page', 'change_style_blocked_while_rendering', 'normal_video_has_a_page_too', 'whatif_page_has_its_steps', 'script_on_the_page_is_the_script_page_script', 'every_style_page_has_its_steps_around_its_card', 'a_new_project_opens_on_the_picker'):
            with self.subTest(n):
                self._check(n)


if __name__ == "__main__":
    unittest.main()
