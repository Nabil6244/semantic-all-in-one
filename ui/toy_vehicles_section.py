"""Toy Vehicles: its own style page. Two modes: Songs (a colour list -> sung colour song, one 3D toy scene per colour)
and Stories (a story or episode file -> narrated adventure with character voices). Resolution, then Generate (checks
the colours or the story) and Render (Blender toy scenes, voices, music and sound -> the project's final folder).
All the work lives in toycolors/runner.py, imported only inside the button handlers. Nothing starts until Generate:
picking a file or an option only remembers it. No Gemini.

Each project remembers this page (state/toy_vehicles/settings.json).

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_tv_block` / `_tv_running` / `_tv_active`."""

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

STYLE = "Toy Vehicles"
TAG = "[TOY VEHICLES]"
RESOLUTIONS = {"1920x1080 final": False, "1280x720 fast preview": True}
MODES = ("Songs", "Stories")
_ROOT = Path(__file__).resolve().parent.parent


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "toycolors"


def _runner():
    mod = sys.modules.get("tv_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("tv_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["tv_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("tv_runner", None)
        messagebox.showerror("Toy Vehicles is not installed", f"The toycolors folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._tv_mode_var = ctk.StringVar(value=MODES[0])
    app._tv_colours_var = ctk.StringVar(value="red, yellow, green, blue, orange")
    app._tv_plan_var = ctk.StringVar(value="")
    app._tv_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._tv_status_var = ctk.StringVar(value="")
    app._tv_cancel = threading.Event()
    app._tv_running = getattr(app, "_tv_running", False)
    app._tv_planned = None   # {"mode", "source", "draft"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._tv_block = block

    body = section(block, 0, 1, "What to make", "a colour song or a story")
    mrow = ctk.CTkFrame(body, fg_color="transparent")
    mrow.grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(mrow, text="Mode", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkSegmentedButton(mrow, values=list(MODES), variable=app._tv_mode_var,
                           command=lambda _v: _show_mode(app)).grid(row=0, column=1)
    app._tv_songs_row = ctk.CTkFrame(body, fg_color="transparent")
    app._tv_songs_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
    app._tv_songs_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(app._tv_songs_row, text="Colours", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkEntry(app._tv_songs_row, textvariable=app._tv_colours_var).grid(row=0, column=1, sticky="ew")
    ctk.CTkLabel(app._tv_songs_row, text="One sung verse per colour (red, orange, yellow, green, blue): a toy vehicle changes colour in "
                                         "a surprise egg, a paint pour, a garage, a magic portal, new wheels or a convoy.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
    app._tv_story_row = ctk.CTkFrame(body, fg_color="transparent")
    app._tv_story_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    app._tv_story_row.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Story file", app._tv_plan_var, lambda: _browse(app), parent=app._tv_story_row,
                  placeholder_text="Choose a story or episode (toycolors/stories/*.json)")
    ctk.CTkLabel(app._tv_story_row, text="Zip, Hooky, Splash and friends: a narrator and a voice for each toy, actions like drive in, stuck "
                                         "in mud, tow, wash, race, ramp jump, flat tyre, hide and seek, and the colour-song scenes. An "
                                         "episode file joins several adventures with a title card each.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._tv_res_var, width=220).grid(row=0, column=1)

    body = section(block, 2, 3, "Generate, then Render", "Generate checks the colours or the story; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._tv_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._tv_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._tv_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._tv_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._tv_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._tv_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._tv_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    _show_mode(app)
    for v in (app._tv_mode_var, app._tv_colours_var, app._tv_plan_var, app._tv_res_var):
        v.trace_add("write", lambda *_a: _changed(app))


def _show_mode(app: Any) -> None:
    songs = app._tv_mode_var.get() == "Songs"
    app._tv_songs_row.grid() if songs else app._tv_songs_row.grid_remove()
    app._tv_story_row.grid_remove() if songs else app._tv_story_row.grid()


def _source(app: Any) -> str:
    return app._tv_colours_var.get().strip() if app._tv_mode_var.get() == "Songs" else app._tv_plan_var.get().strip()


def _changed(app: Any) -> None:
    """A pick changed: remember it; a Generate made for other picks no longer counts. Nothing starts here."""
    p = getattr(app, "_tv_planned", None)
    if p and (p["mode"] != app._tv_mode_var.get() or p["source"] != _source(app)) and not getattr(app, "_tv_restoring", False):
        app._tv_planned = None
        _sync_buttons(app)
        app._sync_primary_cta()                      # the main button goes back to Generate
    _save(app)


def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "toy_vehicles" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_tv_restoring", False) or getattr(app, "_tv_plan_var", None) is None:
        return
    try:
        planned = getattr(app, "_tv_planned", None)
        sig = _sig(planned["source"]) if planned and planned["mode"] == "Stories" else None
        data = {"active": bool(getattr(app, "_tv_active", False)), "mode": app._tv_mode_var.get(),
                "colours": app._tv_colours_var.get(), "plan": app._tv_plan_var.get(), "res_label": app._tv_res_var.get(),
                "planned": {**planned, "sig": sig} if planned else None}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_tv_restored_for", None) or getattr(app, "_tv_running", False):
        return
    app._tv_restored_for = key
    app._tv_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._tv_restoring = True
    try:
        if d.get("mode") in MODES:
            app._tv_mode_var.set(d["mode"])
        app._tv_colours_var.set(d.get("colours") or app._tv_colours_var.get())
        app._tv_plan_var.set(d.get("plan", "") or "")
        if d.get("res_label") in RESOLUTIONS:
            app._tv_res_var.set(d["res_label"])
        p = d.get("planned")
        if p and p.get("source") and (p["mode"] == "Songs" or (p.get("sig") is not None and _sig(p["source"]) == p["sig"])):
            app._tv_planned = {"mode": p["mode"], "source": p["source"], "draft": p.get("draft", False)}
            app._tv_status_var.set("Restored: checked and ready. Click Render.")
        _show_mode(app)
    finally:
        app._tv_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.after(0, lambda: app._on_style_pick(STYLE))


def _browse(app: Any) -> None:
    from tkinter import filedialog

    start = _engine_dir() / "stories"
    path = filedialog.askopenfilename(title="Choose the story or episode", initialdir=str(start) if start.is_dir() else None,
                                      filetypes=[("Story", "*.json"), ("All files", "*.*")])
    if path:
        app._tv_plan_var.set(path)   # remembered only: nothing is read until Generate


def activate(app: Any) -> None:
    if getattr(app, "_tv_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_tv_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._tv_active = True
    _restore(app)
    _save(app)
    app._tv_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_tv_active", False):
        app._tv_active = False
        if remember:
            _save(app)
        block = getattr(app, "_tv_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_tv_generate_btn", None) is None:
        return
    running = getattr(app, "_tv_running", False)
    app._tv_generate_btn.configure(state="disabled" if running else "normal")
    app._tv_render_btn.configure(state="normal" if (app._tv_planned and not running) else "disabled")
    app._tv_stop_btn.configure(state="normal" if running and not app._tv_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_tv_running", False):
        app._cta_action = "tv_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._tv_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._tv_planned:
        app._cta_action = "tv_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Ready. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "tv_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Pick Songs (colours) or Stories (a story file), then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "tv_cancel":
        cancel(app)
    elif action == "tv_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_tv_running", False) or app._tv_cancel.is_set():
        return
    app._tv_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.after(0, lambda: (app._tv_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.after(0, lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._tv_cancel.clear()
    app._tv_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._tv_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._tv_running = False
            if error:
                app._tv_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._tv_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_tv_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    mode, source = app._tv_mode_var.get(), _source(app)
    if mode == "Stories" and (not source or not Path(source).is_file()):
        messagebox.showerror("Cannot start", "Choose the story file first." if not source else f"The story file is not there: {source}")
        return
    tv = _runner()
    if tv is None:
        return
    draft = RESOLUTIONS.get(app._tv_res_var.get(), False)
    app._tv_planned = None
    _save(app)
    app._tv_status_var.set("Checking…")
    app._append_log(f"{TAG} Generate: checking the {mode.lower()}\n")

    def job():
        c = tv.check(mode, source)
        if c["errors"]:
            raise ValueError("Not ready:\n" + "\n".join(c["errors"][:8]))
        return c

    def ready(c) -> None:
        app._tv_planned = {"mode": mode, "source": source, "draft": draft}
        msg = f"\"{c['title']}\": {c['shots']} {'verses' if mode == 'Songs' else 'shots'}, ~{c['seconds']:.0f} s. Click Render."
        app._tv_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "toy-vehicles-check", job, ready)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_tv_running", False):
        return
    ws, planned = app._workspace, app._tv_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a checked song or story.")
        return
    if (app._tv_mode_var.get(), _source(app)) != (planned["mode"], planned["source"]):
        messagebox.showinfo("Click Generate first", "You changed the colours or the story after Generate. Click Generate again, then Render.")
        return
    tv = _runner()
    if tv is None:
        return
    draft = RESOLUTIONS.get(app._tv_res_var.get(), False)
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._tv_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}{' (720p preview)' if draft else ''}\n")
    run = app._track_generation_start("toy_vehicles")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._tv_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return tv.render(planned["mode"], planned["source"], str(out_path), draft=draft, progress=_progress(app),
                         cancel=app._tv_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s)."
        app._tv_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "toy-vehicles-render", job, done, end)
