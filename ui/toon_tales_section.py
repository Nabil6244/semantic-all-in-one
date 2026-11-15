"""Toon Tales: its own style page. A story plan (plan.json written with the toon-tales skill), resolution, then
Generate (check the plan, paint any place that has no picture yet with Flow, after asking) and Render (Walt and Pip
puppets on the painted places in Blender, captions, overlays, music and sound -> the project's final folder).
All the work lives in toontales/runner.py, imported only inside the button handlers. Nothing starts until Generate:
picking a plan or an option only remembers it. No Gemini.

Each project remembers this page (state/toon_tales/settings.json): reopening comes back on it with its plan and, if the
plan did not change, Render ready.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_tt_block` / `_tt_running` / `_tt_active`."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Toon Tales"
TAG = "[TOON TALES]"
RESOLUTIONS = {"1080x1920 final": False, "540x960 quick draft": True}
_ROOT = Path(__file__).resolve().parent.parent


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "toontales"


def _runner():
    mod = sys.modules.get("tt_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("tt_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["tt_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("tt_runner", None)
        messagebox.showerror("Toon Tales is not installed", f"The toontales folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._tt_plan_var = ctk.StringVar(value="")
    app._tt_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._tt_status_var = ctk.StringVar(value="")
    app._tt_cancel = threading.Event()
    app._tt_running = getattr(app, "_tt_running", False)
    app._tt_planned = None   # {"plan", "draft"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._tt_block = block

    body = section(block, 0, 1, "Story", "a Toon Tales story plan (plan.json)")
    app._path_row(0, "Story plan", app._tt_plan_var, lambda: _browse(app), parent=body,
                  placeholder_text="Choose a plan.json (toontales/stories/<story>/plan.json)")
    ctk.CTkLabel(body, text="Walt and Pip act out a ~40 s 'How X worked' Short on painted places: hook card, punch-ins, yellow key-word "
                            "captions, reactions, a WAIT break, music that follows the story. Plans are written with Claude's toon-tales "
                            "skill; examples are in toontales/stories/. A new story's places are painted once with Flow (asks first).",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._tt_res_var, width=220).grid(row=0, column=1)

    body = section(block, 2, 3, "Generate, then Render", "Generate checks the plan and paints its places; Render makes the Short")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._tt_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._tt_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._tt_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._tt_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._tt_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._tt_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._tt_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._tt_plan_var, app._tt_res_var):
        v.trace_add("write", lambda *_a: _save(app))


def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "toon_tales" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_tt_restoring", False) or getattr(app, "_tt_plan_var", None) is None:
        return
    try:
        planned = getattr(app, "_tt_planned", None)
        data = {"active": bool(getattr(app, "_tt_active", False)), "plan": app._tt_plan_var.get(), "res_label": app._tt_res_var.get(),
                "planned": {**planned, "sig": _sig(planned["plan"])} if planned else None}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_tt_restored_for", None) or getattr(app, "_tt_running", False):
        return
    app._tt_restored_for = key
    app._tt_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._tt_restoring = True
    try:
        app._tt_plan_var.set(d.get("plan", "") or "")
        if d.get("res_label") in RESOLUTIONS:
            app._tt_res_var.set(d["res_label"])
        p = d.get("planned")
        if p and p.get("plan") and p.get("sig") is not None and _sig(p["plan"]) == p["sig"]:
            app._tt_planned = {"plan": p["plan"], "draft": p.get("draft", False)}
            app._tt_status_var.set("Restored: the story is checked and its places are painted. Click Render.")
    finally:
        app._tt_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.after(0, lambda: app._on_style_pick(STYLE))


def _browse(app: Any) -> None:
    from tkinter import filedialog

    start = _engine_dir() / "stories"
    path = filedialog.askopenfilename(title="Choose the story plan", initialdir=str(start) if start.is_dir() else None,
                                      filetypes=[("Story plan", "plan.json *.json"), ("All files", "*.*")])
    if path:
        app._tt_plan_var.set(path)   # remembered only: nothing is read until Generate
        app._tt_planned = None
        _save(app)
        _sync_buttons(app)


def activate(app: Any) -> None:
    if getattr(app, "_tt_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_tt_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._tt_active = True
    _restore(app)
    _save(app)
    app._tt_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_tt_active", False):
        app._tt_active = False
        if remember:
            _save(app)
        block = getattr(app, "_tt_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_tt_generate_btn", None) is None:
        return
    running = getattr(app, "_tt_running", False)
    app._tt_generate_btn.configure(state="disabled" if running else "normal")
    app._tt_render_btn.configure(state="normal" if (app._tt_planned and not running) else "disabled")
    app._tt_stop_btn.configure(state="normal" if running and not app._tt_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_tt_running", False):
        app._cta_action = "tt_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._tt_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._tt_planned:
        app._cta_action = "tt_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The story is ready. Click Render to make the Short.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "tt_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a story plan, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "tt_cancel":
        cancel(app)
    elif action == "tt_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_tt_running", False) or app._tt_cancel.is_set():
        return
    app._tt_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.after(0, lambda: (app._tt_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.after(0, lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._tt_cancel.clear()
    app._tt_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._tt_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._tt_running = False
            if error:
                app._tt_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._tt_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_tt_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    plan = app._tt_plan_var.get().strip()
    if not plan or not Path(plan).is_file():
        messagebox.showerror("Cannot start", "Choose the story plan first." if not plan else f"The story plan is not there: {plan}")
        return
    tt = _runner()
    if tt is None:
        return
    draft = RESOLUTIONS.get(app._tt_res_var.get(), False)
    app._tt_planned = None
    _save(app)
    app._tt_status_var.set("Checking the story…")
    app._append_log(f"{TAG} Generate: checking {Path(plan).parent.name}\n")

    def job():
        c = tt.check(plan)
        if c["errors"]:
            raise ValueError("The story plan has errors:\n" + "\n".join(c["errors"][:8]))
        return c

    def ready(c) -> None:
        app._tt_planned = {"plan": plan, "draft": draft}
        warn = f"  {len(c['warnings'])} notes (see the log)." if c["warnings"] else ""
        for w in c["warnings"]:
            app._append_log(f"{TAG} note: {w}\n")
        msg = f"\"{c['title']}\": {c['shots']} shots, ~{c['seconds']:.0f} s, {len(c['places'])} places.{warn} Click Render."
        app._tt_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    def after_check(c) -> None:
        if c["missing"]:
            if not messagebox.askyesno("Paint the story's places?", f"{len(c['missing'])} place(s) have no picture yet: "
                                       f"{', '.join(c['missing'])}.\n\nPaint them now with Flow? One picture each (Flow credits), "
                                       "made once and reused every time this story renders."):
                app._tt_status_var.set("Not ready: the places are not painted.")
                return
            app._tt_status_var.set("Painting the places with Flow…")
            _start(app, "toon-tales-paint", lambda: (tt.paint(plan, progress=_progress(app), cancel=app._tt_cancel.is_set,
                                                              log=_log(app)), tt.check(plan))[1], ready)
            return
        ready(c)

    _start(app, "toon-tales-check", job, after_check)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_tt_running", False):
        return
    ws, planned = app._workspace, app._tt_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a checked story.")
        return
    if app._tt_plan_var.get().strip() != planned["plan"]:
        messagebox.showinfo("Click Generate first", "You picked another story plan after Generate. Click Generate again, then Render.")
        return
    tt = _runner()
    if tt is None:
        return
    draft = RESOLUTIONS.get(app._tt_res_var.get(), False)
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._tt_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}{' (draft)' if draft else ''}\n")
    run = app._track_generation_start("toon_tales")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._tt_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return tt.render(planned["plan"], str(out_path), draft=draft, progress=_progress(app), cancel=app._tt_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s)."
        app._tt_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "toon-tales-render", job, done, end)
