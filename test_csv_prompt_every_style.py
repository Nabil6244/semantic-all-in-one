"""Every style that is made from a CSV shows a "Copy the CSV prompt" button on its page, and the button copies that style's own prompt
(live app in a subprocess, off screen; nothing is sent anywhere). Weather is checked in the code: it is locked behind its own switch."""
from __future__ import annotations
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# style -> words its prompt starts with (a style built on another engine copies that engine's prompt)
EXPECT = {
    "Story Motion": "film director and storyboard artist", "Modern Tech News": 'the "Normal" style', "Overscaled": 'the "Overscaled" style',
    "Exp Solar": 'the "Exp Solar" style', "pakMap": 'the "pakMap" style', "Hybrid Map": 'the "Hybrid Map" style', "StarMap": 'the "StarMap" style',
    "StarMap Cinema": 'the "StarMap" style', "What If": "science-explainer channel", "Explainer": "scene planner for a documentary video", "Rep Theory": "Rep Theory video",
    "Product Trailer": "concept trailer", "War Documentary": "war / geopolitics documentary", "Enoch Template": 'the "Enoch Template" styl',
    "Health Cinema": "long-form health video", "Normal video": 'the "Normal" style',
}

_SCRIPT = r'''
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
try:
    import app as _app
except ModuleNotFoundError as exc:
    open(sys.argv[1], "w").write(f"SKIP|{exc}\n"); os._exit(0)
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"; _app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    open(sys.argv[1], "w").write(f"SKIP|{exc}\n"); os._exit(0)
_app.messagebox.showinfo = lambda *a, **k: None; _app.messagebox.showerror = lambda *a, **k: None
tmp = Path(tempfile.mkdtemp()); ws = ProjectWorkspace(project_id="p1", title="T", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"): (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws; inst.update_idletasks(); root = inst._view_visual_director
RES = open(sys.argv[1], "w")
def placed(w):
    while w is not None and w is not root:
        try:
            if not w.winfo_manager(): return False
        except Exception: return False
        w = w.master
    return w is root
def button(w):
    for c in w.winfo_children():
        try: t = c.cget("text")
        except Exception: t = ""
        if t == "Copy the CSV prompt" and placed(c): return c
        r = button(c)
        if r is not None: return r
    return None
for n in sys.argv[2:] + ["Normal video"]:      # Normal last: on a fresh project its page opens behind the style picker
    try:
        inst._on_style_pick(n); inst._style_browsing = False; inst._sync_style_picker(); inst.update_idletasks()
        b = button(root); txt = "<no button>"
        if b is not None:
            inst.clipboard_clear(); inst.clipboard_append("<nothing copied>"); b.invoke(); inst.update_idletasks(); txt = inst.clipboard_get()
        RES.write(f"{n}|{' '.join(txt.split())[:300]}\n"); RES.flush()
    except Exception as exc:
        RES.write(f"{n}|ERROR {type(exc).__name__}: {exc}\n"); RES.flush()
os._exit(0)
'''


class EveryCsvStyleHasItsPromptButton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Path(tempfile.mkdtemp()); script = d / "_prompt_buttons.py"; out = d / "out.txt"; script.write_text(_SCRIPT, encoding="utf-8")
        names = [n for n in EXPECT if n != "Normal video"]
        subprocess.run([sys.executable, str(script), str(out)] + names, cwd=ROOT, timeout=600, capture_output=True)
        lines = out.read_text(encoding="utf-8").splitlines() if out.is_file() else []
        if lines and lines[0].startswith("SKIP|"): raise unittest.SkipTest(lines[0][5:])
        cls.got = {}
        for ln in lines:
            name, _, text = ln.partition("|"); cls.got[name] = text      # Normal video: its last (real page) result

    def test_each_style_copies_its_own_prompt(self):
        for name, words in EXPECT.items():
            with self.subTest(name):
                self.assertIn(name, self.got, "the style was never checked")
                self.assertIn(words, self.got[name], f"{name}: {self.got[name][:120]}")

    def test_weather_has_the_button_in_code(self):
        text = (ROOT / "weather" / "app_section.py").read_text(encoding="utf-8")
        self.assertIn('"Copy the CSV prompt", lambda: copy_prompt(app)', text)


if __name__ == "__main__":
    unittest.main()
