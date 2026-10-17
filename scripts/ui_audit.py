#!/usr/bin/env python3
"""Automated UI audit: build the real app, visit every view in every style, and
measure what a screenshot review would look for, from the live widget tree.

Checks (per visible widget):
  contrast   text colour vs the colour actually behind it (WCAG ratio; 4.5:1
             normal text, 3:1 for bold >= 14 px)
  clipped    a label/button whose text needs more width than it was given
  offscreen  a control that ends past the window's right edge (needs scrolling
             it does not have)
  font       a font size outside the design scale in ui/theme.py

Runs at several window sizes and in both themes. settings.json is backed up and
restored, nothing else is written. Prints a JSON summary; exits 0 always (it
is a measuring tool; test_ui_audit.py turns selected checks into assertions).

Usage: python scripts/ui_audit.py [--sizes 1100x700,1440x900] [--themes dark,light]
       [--styles all|"Normal video,Hybrid Map"] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))



def _font_scale() -> set:
    """Every size named by a FONT_* token in ui/theme.py, plus 10 (small badges)."""
    import ui.theme as T
    return {v[0] for k, v in vars(T).items() if k.startswith("FONT_") and isinstance(v, tuple)} | {10}


def _rgb(tk_root, color: str):
    try:
        r, g, b = tk_root.winfo_rgb(color)
        return r / 65535, g / 65535, b / 65535
    except Exception:
        return None


def _lum(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mode_pick(value, light: bool):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0] if light else value[1]
    return value


def effective_bg(widget, light: bool):
    """The colour painted behind `widget`: walk up until something has a real fill."""
    w = widget
    while w is not None:
        fg = getattr(w, "_fg_color", None)
        fg = _mode_pick(fg, light)
        if isinstance(fg, str) and fg and fg != "transparent":
            return fg
        bg = getattr(w, "_bg_color", None)
        bg = _mode_pick(bg, light)
        if isinstance(bg, str) and bg and bg != "transparent" and w is not widget:
            return bg
        if not hasattr(w, "_fg_color"):
            try:
                c = w.cget("background") if "background" in w.keys() else None
                if c:
                    return c
            except Exception:
                pass
        w = w.master
    return None


def _path(widget) -> str:
    return str(widget)


def shown_text(widget) -> str:
    """What the widget displays. With a textvariable, CTk's cget("text") returns its placeholder default, so read the
    inner Tk label, which is what is actually painted."""
    for inner_name in ("_label", "_text_label"):
        inner = getattr(widget, inner_name, None)
        if inner is not None:
            try:
                return str(inner.cget("text") or "")
            except Exception:
                pass
    try:
        return str(widget.cget("text") or "")
    except Exception:
        return ""


def _describe(widget) -> str:
    name = type(widget).__name__
    text = shown_text(widget)[:40]
    return f"{name}:{text!r}" if text else name


def audit_visible(app, light: bool) -> dict:
    import customtkinter as ctk

    findings = defaultdict(list)
    fonts = Counter()
    win_w = app.winfo_width()
    win_x = app.winfo_rootx()
    stack = [app]
    seen = 0
    while stack:
        w = stack.pop()
        try:
            if not w.winfo_ismapped():
                continue
        except Exception:
            continue
        seen += 1
        stack.extend(w.winfo_children())
        if isinstance(w, (ctk.CTkLabel, ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkSwitch, ctk.CTkRadioButton)):
            text = shown_text(w)
            if text in ("CTkLabel", "CTkButton", "CTkCheckBox", "CTkSwitch", "CTkRadioButton"):
                findings["default_text"].append(f"{type(w).__name__} at {w} shows CustomTkinter's placeholder text")
            font = getattr(w, "_font", None)
            size, weight = None, "normal"
            if isinstance(font, ctk.CTkFont):
                size, weight = abs(int(font.cget("size"))), font.cget("weight")
            elif isinstance(font, tuple) and len(font) >= 2:
                size = abs(int(font[1]))
                weight = "bold" if "bold" in font[2:] else "normal"
            if size:
                fonts[size] += 1
                if size not in _font_scale() and text.strip():
                    findings["font"].append(f"{_describe(w)} size={size}")
            if text.strip() and getattr(w, "_image", None) is None:
                tc = _mode_pick(getattr(w, "_text_color", None), light)
                if isinstance(w, ctk.CTkButton):
                    bg = _mode_pick(w._fg_color, light)
                elif isinstance(w, (ctk.CTkCheckBox, ctk.CTkSwitch, ctk.CTkRadioButton)):
                    bg = effective_bg(w.master, light)  # its fg is the box/track; the label sits on the parent
                else:
                    bg = effective_bg(w, light)
                if isinstance(bg, str) and bg == "transparent":
                    bg = effective_bg(w.master, light)
                state = ""
                try:
                    state = str(w.cget("state"))
                except Exception:
                    pass
                if isinstance(w, ctk.CTkButton) and state == "disabled":
                    tc = _mode_pick(getattr(w, "_text_color_disabled", tc), light)
                a, b = (_rgb(app, tc) if isinstance(tc, str) else None), (_rgb(app, bg) if isinstance(bg, str) else None)
                if a and b and state != "disabled":
                    ratio = contrast(a, b)
                    need = 3.0 if (weight == "bold" and (size or 0) >= 14) or (size or 0) >= 18 else 4.5
                    if ratio < need:
                        findings["contrast"].append(f"{_describe(w)} {tc} on {bg} = {ratio:.2f} (need {need})")
                # clipped text: the layout gave the painted label less width than it asked for. Tk's own
                # numbers (reqwidth vs width) include the real fallback font for glyphs such as \u2699 / \u2600;
                # CTkFont.measure() does not, and over-reported those on Windows.
                try:
                    inner = getattr(w, "_text_label", None) or getattr(w, "_label", None)
                    if inner is not None and not getattr(w, "_wraplength", 0):
                        need_px, have = inner.winfo_reqwidth(), inner.winfo_width()
                        if have > 1 and need_px > have + 2:
                            findings["clipped"].append(f"{_describe(w)} needs {need_px}px has {have}px")
                except Exception:
                    pass
        if isinstance(w, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkOptionMenu, ctk.CTkComboBox, ctk.CTkSegmentedButton)):
            try:
                right = w.winfo_rootx() + w.winfo_width() - win_x
                if right > win_w + 1 and w.winfo_width() > 1:
                    findings["offscreen"].append(f"{_describe(w)} ends at {right}px of {win_w}px")
            except Exception:
                pass
    return {"widgets": seen, "findings": {k: sorted(set(v)) for k, v in findings.items()}, "fonts": dict(fonts)}


def _new_toplevels(inst, before: set) -> list:
    return [w for w in inst.winfo_children() if w.winfo_class() == "Toplevel" and str(w) not in before]


def audit_dialogs(inst, theme: str, light: bool) -> dict:
    """Open each dialog that needs no project, audit it (every Settings tab), close it."""
    out = {}

    def no_engine(*_a, **_k):
        raise RuntimeError("ui_audit: Flow engine disabled")

    inst._get_flow_engine_manager = no_engine  # opening dialogs must never start Node or a browser
    openers = {
        "settings": inst._open_settings,
        "project_picker": inst._open_project_picker,
        "error_dialog": lambda: inst._show_error_dialog(
            "Render failed", "The export stopped at scene 14 of 40. Finished scenes are kept.",
            "Traceback (most recent call last):\n  File \"render.py\", line 1\nRuntimeError: example"),
    }
    for name, opener in openers.items():
        before = {str(w) for w in inst.winfo_children()}
        try:
            opener()
            inst.update()
        except Exception as exc:
            out[f"{theme}|dialog|{name}"] = {"error": f"open failed: {exc}"}
            continue
        for win in _new_toplevels(inst, before):
            win.update()
            tabview = next((w for w in _walk(win) if type(w).__name__ == "CTkTabview"), None)
            tabs = list(tabview._name_list) if tabview is not None else [None]
            for tab in tabs:
                if tab is not None:
                    tabview.set(tab)
                    win.update()
                key = f"{theme}|dialog|{name}" + (f"|{tab}" if tab else "")
                out[key] = audit_visible(win, light)
            try:
                win.destroy()
            except Exception:
                pass
        inst.update()
    return out


def _walk(root):
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())


def build_app():
    from tkinter import messagebox

    for name in ("showerror", "showinfo", "showwarning"):
        setattr(messagebox, name, lambda *a, **k: None)
    for name in ("askyesno", "askokcancel", "askyesnocancel"):
        setattr(messagebox, name, lambda *a, **k: False)
    import app as app_mod

    inst = app_mod.VideoGeneratorApp()
    inst.update()
    for child in inst.winfo_children():  # project picker / login dialog
        if child.winfo_class() == "Toplevel" or type(child).__name__.endswith("Toplevel"):
            try:
                child.destroy()
            except Exception:
                pass
    inst.update()
    return app_mod, inst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1100x700,1440x900")
    ap.add_argument("--themes", default="dark,light")
    ap.add_argument("--styles", default="all")
    ap.add_argument("--json", default="")
    ap.add_argument("--dialogs", action="store_true", help="also open Settings (each tab), the project picker and the error dialog")
    args = ap.parse_args()

    settings = ROOT / "settings.json"
    backup = Path(tempfile.mkdtemp()) / "settings.json"
    had = settings.is_file()
    if had:
        shutil.copy2(settings, backup)
    report = {}
    try:
        app_mod, inst = build_app()
        import ui.theme as T

        views = [k for k, _label, _g in T.NAV_ITEMS if inst._shell.view(k) is not None]
        styles = list(inst.STYLE_CHOICES) if args.styles == "all" else [s.strip() for s in args.styles.split(",")]
        for theme in args.themes.split(","):
            inst._apply_theme_mode(theme)
            inst.update()
            light = T.active_appearance() == "light"
            for size in args.sizes.split(","):
                inst.geometry(f"{size}+20+20")
                inst.update()
                for style in styles:
                    try:
                        inst._on_style_pick(style)
                    except Exception as exc:
                        report[f"{theme}|{size}|{style}"] = {"error": f"style pick failed: {exc}"}
                        continue
                    for view in views:
                        inst._shell.navigate(view)
                        inst.update()
                        report[f"{theme}|{size}|{style}|{view}"] = audit_visible(inst, light)
            if args.dialogs:
                report.update(audit_dialogs(inst, theme, light))
        inst.destroy()
    finally:
        if had:
            shutil.copy2(backup, settings)

    totals = Counter()
    unique = defaultdict(set)
    for key, r in report.items():
        for kind, items in r.get("findings", {}).items():
            totals[kind] += len(items)
            for it in items:
                unique[kind].add((key.split("|")[-1], it))
    summary = {
        "screens": len(report),
        "totals": dict(totals),
        "unique": {k: len(v) for k, v in unique.items()},
        "examples": {k: sorted(v)[:60] for k, v in unique.items()},
        "errors": {k: v["error"] for k, v in report.items() if "error" in v},
    }
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "report": report}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
