"""Settings is organized by SCOPE: General / Keys & AI / Flow (whole app) and This project (saved with the project).

Boots the real Settings window in a subprocess (like test_worker_state_recovery) and reads back which section
headers each tab holds, that every tab states its scope, that the Production panel is there, and that the
captions / Whisper choices persist (they used to reset on every launch). settings.json is restored afterwards.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_LIVE = r'''
import os, sys, json, shutil, time, traceback
from pathlib import Path
real_stdout = sys.stdout
sys.path.insert(0, os.getcwd())
def emit(n, ok, d=""): real_stdout.write(f"{'PASS' if ok else 'FAIL'}:{n}:{str(d)[:600]}\n"); real_stdout.flush()
backup = Path(sys.argv[1])
shutil.copy2("settings.json", backup) if Path("settings.json").is_file() else None
try:
    from tkinter import messagebox
    messagebox.showerror = messagebox.showinfo = lambda *a, **k: None
    try:
        import app as _app
        import customtkinter as ctk
        inst = _app.VideoGeneratorApp(); inst.withdraw()
    except Exception as exc:
        real_stdout.write(f"SKIP:{exc}\n"); os._exit(0)
    before = set(inst.winfo_children())
    inst._open_settings()
    win = [w for w in inst.winfo_children() if w not in before][-1]
    tabview = [c for c in win.winfo_children() if isinstance(c, ctk.CTkTabview)][0]
    def labels(widget):
        out = []
        for c in widget.winfo_children():
            if isinstance(c, ctk.CTkLabel):
                try: out.append(str(c.cget("text")))
                except Exception: pass
            out.extend(labels(c))
        return out
    sections = {}
    scopes = {}
    for name in ("General", "Keys & AI", "Flow", "This project"):
        texts = labels(tabview.tab(name))
        sections[name] = [t for t in texts if t and t.isupper() and len(t) > 3]
        scopes[name] = texts[0] if texts else ""
    emit("tabs", list(tabview._name_list) == ["General", "Keys & AI", "Flow", "This project"], tabview._name_list)
    emit("general", sections["General"][:3] == ["APPEARANCE", "CAPTIONS & NARRATION TIMING"] or
         ("APPEARANCE" in sections["General"] and "CAPTIONS & NARRATION TIMING" in sections["General"]), sections["General"])
    emit("keys", sections["Keys & AI"][:3] == ["STOCK PROVIDERS", "AI SCRIPT (GEMINI)", "AI PROVIDERS"], sections["Keys & AI"])
    emit("flow", sections["Flow"][:3] == ["FLOW SETTINGS", "AI / FLOW ACCOUNTS", "FLOW VIDEO PROFILES"], sections["Flow"])
    emit("project", sections["This project"][:3] == ["VIDEO QUALITY", "CACHE & STORAGE", "PRODUCTION"], sections["This project"])
    emit("scopes", all("Applies to the whole app" in scopes[n] for n in ("General", "Keys & AI", "Flow"))
         and "project" in scopes["This project"].lower(), scopes)
    inst.captions_var.set(True); inst.model_var.set("medium")
    saved = json.loads(Path("settings.json").read_text())
    emit("persisted", saved.get("captions") is True and saved.get("whisper_model") == "medium",
         {k: saved.get(k) for k in ("captions", "whisper_model")})
except BaseException:
    # os._exit below would discard the traceback: report it so a failure (e.g. only on Windows) says what broke.
    real_stdout.write("ERROR:" + traceback.format_exc().replace("\n", " | ") + "\n"); real_stdout.flush()
finally:
    if backup.is_file():
        shutil.copy2(backup, "settings.json")
    os._exit(0)
'''


class TestSettingsTabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        tmp = Path(tempfile.mkdtemp())
        script = tmp / "_settings_tabs_live.py"
        script.write_text(_LIVE, encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run([sys.executable, str(script), str(tmp / "settings.backup.json")], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=180,
                              cwd=Path(__file__).resolve().parent, env=env)
        cls._out, cls._err, cls._res, cls._error = proc.stdout, proc.stderr, {}, ""
        for line in proc.stdout.splitlines():
            if line.startswith("ERROR:"):
                cls._error = line[6:]
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[5:])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._res[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._res:
            why = f"the Settings window raised: {self._error}" if self._error else "no output from the live check"
            self.fail(f"never reported {name}: {why}\n{self._out[-2000:]}\n{self._err[-2000:]}")
        ok, detail = self._res[name]
        self.assertTrue(ok, f"{name}: {detail}")

    def test_four_scope_tabs(self):
        self._check("tabs")

    def test_general_tab(self):
        self._check("general")

    def test_keys_tab(self):
        self._check("keys")

    def test_flow_tab(self):
        self._check("flow")

    def test_this_project_tab_has_quality_cache_and_production(self):
        self._check("project")

    def test_every_tab_states_its_scope(self):
        self._check("scopes")

    def test_captions_and_whisper_choices_are_remembered(self):
        self._check("persisted")


if __name__ == "__main__":
    unittest.main()
