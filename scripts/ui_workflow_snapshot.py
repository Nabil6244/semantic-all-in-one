#!/usr/bin/env python3
"""Records what the app's workflows hang on, so a redesign can be checked against it (test_ui_workflow_smoke.py).

Builds the real app off screen and writes one JSON with:
  views    - every nav page key that has a page
  styles   - per style: the main button's action (Generate / Render ...), the running flags after picking it (must stay off),
             and the callback of every button on its page (bound method name, or the names a lambda calls)
  pages    - per nav page: the callbacks of its buttons
  vars     - every app attribute holding a Tk variable (what settings and saved state bind to)
  widgets  - every app attribute holding a widget (what handlers and tests reach for)

A redesign may add to any of these but must not lose anything. Button text is recorded for reading only, never compared.

  python scripts/ui_workflow_snapshot.py --json out.json
  python scripts/ui_workflow_snapshot.py --update        # rewrite test_fixtures/ui_workflow_baseline.json (an intended change)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BASELINE = ROOT / "test_fixtures" / "ui_workflow_baseline.json"


def _callback_id(cmd) -> str:
    if cmd is None:
        return ""
    fn = getattr(cmd, "__func__", cmd)
    name = getattr(fn, "__qualname__", "") or type(cmd).__name__
    if "<lambda>" in name or "<locals>" in name:
        code = getattr(fn, "__code__", None)
        called = sorted(n for n in (code.co_names if code else ()) if not n.startswith("__"))
        owner = (getattr(fn, "__module__", "") or "") + "." + name.split(".<locals>")[0].split(".<lambda>")[0]
        return f"{owner}:" + ",".join(called)
    return name


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _laid_out(widget, root) -> bool:
    """Shown on the page: the widget and every parent up to the page are gridded/packed/placed (the window itself is withdrawn,
    so winfo_ismapped is always False here)."""
    w = widget
    while w is not None and w is not root:
        try:
            if not w.winfo_manager():
                return False
        except Exception:
            return False
        w = w.master
    return True


def _buttons(root, visible_only: bool) -> dict:
    import customtkinter as ctk

    out = {}
    for w in _walk(root):
        if not isinstance(w, ctk.CTkButton):
            continue
        if visible_only and not _laid_out(w, root):
            continue
        cid = _callback_id(getattr(w, "_command", None))
        if cid:
            try:
                text = str(w.cget("text"))
            except Exception:
                text = ""
            out.setdefault(cid, text)
    return out


def _running_flags(inst) -> list:
    return sorted(n for n, v in vars(inst).items() if n.endswith("_running") and v is True)


def capture() -> dict:
    from tkinter import messagebox
    import tkinter as tk

    for name in ("showerror", "showinfo", "showwarning"):
        setattr(messagebox, name, lambda *a, **k: None)
    for name in ("askyesno", "askokcancel", "askyesnocancel"):
        setattr(messagebox, name, lambda *a, **k: False)
    import app as app_mod
    import ui.theme as T

    iso = Path(tempfile.mkdtemp()) / "settings.json"
    app_mod._settings_path = lambda: iso           # never touch the real settings.json
    inst = app_mod.VideoGeneratorApp()
    inst.withdraw()
    inst.update_idletasks()
    for child in inst.winfo_children():             # project picker / login dialog
        if type(child).__name__.endswith("Toplevel") or child.winfo_class() == "Toplevel":
            try:
                child.destroy()
            except Exception:
                pass
    inst.update_idletasks()

    from project_workspace import ProjectWorkspace   # a throwaway open project, so each style's page shows its real buttons

    ws = ProjectWorkspace(project_id="p1", title="T", seq=1, root=Path(tempfile.mkdtemp()) / "proj")
    for d in ("csv", "assets", "audio", "logs", "final", "flow", "state"):
        (ws.root / d).mkdir(parents=True, exist_ok=True)
    inst._workspace = ws
    inst.update_idletasks()

    snap = {"views": [], "styles": {}, "pages": {}, "vars": [], "widgets": []}
    snap["views"] = [k for k, _l, _g in T.NAV_ITEMS if inst._shell.view(k) is not None]
    for key in snap["views"]:
        print(f"page: {key}", file=sys.stderr, flush=True)
        inst._shell.navigate(key)
        inst.update_idletasks()
        snap["pages"][key] = _buttons(inst._shell.view(key), visible_only=False)

    inst._shell.navigate("visual_director")
    inst.update_idletasks()
    for style in inst.STYLE_CHOICES:
        print(f"style: {style}", file=sys.stderr, flush=True)
        try:
            inst._on_style_pick(style)
            inst._style_browsing = False
            inst._sync_style_picker()
            inst._sync_primary_cta()
            inst.update_idletasks()
        except Exception as exc:  # noqa: BLE001
            snap["styles"][style] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        snap["styles"][style] = {
            "cta": str(getattr(inst, "_cta_action", "")),
            "running": _running_flags(inst),
            "buttons": _buttons(inst._shell.view("visual_director"), visible_only=True),
        }

    for name, value in sorted(vars(inst).items()):
        if isinstance(value, tk.Variable):
            snap["vars"].append(name)
        elif isinstance(value, tk.Misc):
            snap["widgets"].append(name)
    try:
        inst.destroy()
    except Exception:
        pass
    return snap


def lost(baseline: dict, current: dict) -> dict:
    """What the baseline has that the current app no longer has. Empty = no workflow lost."""
    out = {}
    for key in ("views", "vars", "widgets"):
        gone = sorted(set(baseline.get(key, [])) - set(current.get(key, [])))
        if gone:
            out[key] = gone
    for page, btns in baseline.get("pages", {}).items():
        gone = sorted(set(btns) - set(current.get("pages", {}).get(page, {})))
        if gone:
            out[f"page:{page}"] = gone
    for style, b in baseline.get("styles", {}).items():
        c = current.get("styles", {}).get(style)
        if c is None:
            out[f"style:{style}"] = ["style missing"]
            continue
        if "error" in c:
            out[f"style:{style}"] = [c["error"]]
            continue
        problems = []
        if b.get("cta") != c.get("cta"):
            problems.append(f"main button action {b.get('cta')!r} -> {c.get('cta')!r}")
        if c.get("running"):
            problems.append(f"started on pick: {c['running']}")
        problems += [f"button gone: {cid} ({b['buttons'][cid]!r})" for cid in sorted(set(b.get("buttons", {})) - set(c.get("buttons", {})))]
        if problems:
            out[f"style:{style}"] = problems
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = ap.parse_args()
    snap = capture()
    text = json.dumps(snap, indent=1, sort_keys=True)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    if args.update:
        BASELINE.write_text(text + "\n", encoding="utf-8")
        print(f"baseline written: {BASELINE}")
    errors = {s: v["error"] for s, v in snap["styles"].items() if "error" in v}
    print(json.dumps({"views": len(snap["views"]), "styles": len(snap["styles"]), "vars": len(snap["vars"]),
                      "widgets": len(snap["widgets"]), "errors": errors}, indent=1))
    sys.stdout.flush()
    os._exit(0)   # engines may leave worker threads; the snapshot is written


if __name__ == "__main__":
    main()
