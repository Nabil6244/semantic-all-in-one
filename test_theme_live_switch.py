"""Regression test: switching Dark <-> Light used to repaint only the shell
chrome (top bar / sidebar). Every view's own widgets — the Visual Plan table,
log box, inspector, dialogs — kept the previous palette baked in, and app.py's
import-time color copies (_BG, _ROW_ALT, SOURCE_BADGE, STATUS_COLOR, ...)
kept building NEW rows in the old palette: a half-dark/half-light window with
white-on-white button text. CustomTkinter's own appearance mode was also
hardcoded to "Dark" at startup regardless of the saved theme.

Runs the real app in a subprocess (same convention as the other live UI
tests) and scans EVERY widget's color options after each switch.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ui import theme as T


class TestRoleAwareRemap(unittest.TestCase):
    def test_light_white_maps_to_text_or_surface_by_role(self):
        maps = T.color_remaps(T.LIGHT, T.DARK)
        # "#FFFFFF" is BOTH light surface and text-on-accent.
        self.assertEqual(maps["text"]["#FFFFFF"], T.DARK["accent_on_accent"])
        self.assertEqual(maps["fill"]["#FFFFFF"], T.DARK["surface"])

    def test_ui_tokens_win_over_timeline_clip_tokens(self):
        maps = T.color_remaps(T.DARK, T.LIGHT)
        self.assertEqual(maps["fill"][T.DARK["accent"].upper()], T.LIGHT["accent"])

    def test_nested_palette_tables_are_remapped(self):
        remap = T.color_remap(T.DARK, T.LIGHT, "text")
        table = {"x": ("Label", T.DARK["text_secondary"], "transparent")}
        self.assertEqual(T.remap_color_value(table, remap)["x"],
                         ("Label", T.LIGHT["text_secondary"], "transparent"))


_LIVE = r'''
import os, sys, csv, tempfile
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())

def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{str(detail)[:600]}")

from ui import theme as T
T._write_saved_mode = lambda mode: None      # never touch the user's settings.json
T.set_mode("dark")
from tkinter import messagebox
messagebox.showerror = messagebox.showinfo = lambda *a, **k: None
try:
    import app as _app
    import customtkinter as ctk
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)

tmp = Path(tempfile.mkdtemp())
p = tmp / "plan.csv"
with open(p, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["scene_number", "script_segment"])
    for i in range(1, 6):
        w.writerow([str(i), f"Workers excavated the canyon number {i} with heavy machinery."])
inst._overscaled_use_local_planner_var.set(True)
inst._overscaled_csv_var.set(str(p))
inst._load_overscaled_csv(str(p))

OPTS = T._CTK_COLOR_OPTIONS + T._TK_COLOR_OPTIONS

def leftovers(bad):
    found, stack = [], [inst]
    while stack:
        w = stack.pop()
        for o in OPTS:
            try:
                v = w.cget(o)
            except Exception:
                continue
            if isinstance(v, str) and v.upper() in bad:
                found.append(f"{type(w).__name__}.{o}={v}")
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass
    return found

dark_only = {v.upper() for v in T.DARK.values()} - {v.upper() for v in T.LIGHT.values()}
light_only = {v.upper() for v in T.LIGHT.values()} - {v.upper() for v in T.DARK.values()}

emit("starts_dark_with_dark_palette", ctk.get_appearance_mode() == "Dark" and not leftovers(light_only),
     leftovers(light_only)[:5])

inst._apply_theme_mode("light")
left = leftovers(dark_only)
emit("light_switch_leaves_no_dark_palette_anywhere", not left, f"{len(left)} {left[:8]}")
emit("ctk_appearance_follows_light", ctk.get_appearance_mode() == "Light", ctk.get_appearance_mode())
row = inst._scene_row_widgets.get("001", {})
badge = row.get("badge")
emit("visual_plan_rows_rebuilt_in_light_palette",
     badge is not None and badge.cget("text_color").upper() == T.LIGHT["text_secondary"].upper()
     and _app._MUTED == T.LIGHT["text_secondary"] and _app.STATUS_COLOR["ready"] == T.LIGHT["success"],
     f"badge={badge.cget('text_color') if badge else None} muted={_app._MUTED}")
gen = inst._shell.generate_btn
emit("accent_button_text_stays_white_in_light", gen.cget("text_color").upper() == "#FFFFFF", gen.cget("text_color"))

inst._apply_theme_mode("dark")
left = leftovers(light_only)
emit("dark_switch_back_leaves_no_light_palette", not left, f"{len(left)} {left[:8]}")
emit("accent_button_text_stays_white_after_switch_back",
     gen.cget("text_color").upper() == "#FFFFFF", gen.cget("text_color"))
sys.stdout.flush(); os._exit(0)
'''


class TestThemeLiveSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        script = Path(tempfile.mkdtemp()) / "_theme_live.py"
        script.write_text(_LIVE, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120,
                              cwd=Path(__file__).resolve().parent)
        cls._out, cls._err, cls._res = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[5:])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._res[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._res:
            self.fail(f"never reported {name}\n{self._out}\n{self._err[-2000:]}")
        ok, detail = self._res[name]
        self.assertTrue(ok, f"{name}: {detail}")

    def test_starts_dark(self):
        self._check("starts_dark_with_dark_palette")

    def test_light_switch_recolors_every_widget(self):
        self._check("light_switch_leaves_no_dark_palette_anywhere")

    def test_ctk_appearance_follows_theme(self):
        self._check("ctk_appearance_follows_light")

    def test_visual_plan_rows_rebuilt_in_new_palette(self):
        self._check("visual_plan_rows_rebuilt_in_light_palette")

    def test_accent_button_text_stays_white(self):
        self._check("accent_button_text_stays_white_in_light")

    def test_switch_back_to_dark_is_clean(self):
        self._check("dark_switch_back_leaves_no_light_palette")

    def test_accent_text_white_after_switch_back(self):
        self._check("accent_button_text_stays_white_after_switch_back")


if __name__ == "__main__":
    unittest.main()
