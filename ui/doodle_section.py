"""Doodle Survival: its own style page. A script (+ your voice or a free one) -> an AI you have signed in on this computer
(Gemini CLI or Claude Code) makes the whole video itself through the videokit tools, in the doodle_dark look: Scout the
mascot, every scene drawn new from its sentence, lit rooms, line-icon cards, the DAY tag, sound effects on the hooks.

One button: Make video. All work lives in doodle_ai/runner.py, imported only inside the button handler. Nothing starts
until the button is clicked. Each project remembers this page (state/doodle_ai/settings.json).
app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_ds_block` / `_ds_running` / `_ds_active`."""

from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Doodle Survival"
TAG = "[DOODLE]"
VOICES = {"Andrew (US)": "en-US-AndrewNeural", "Brian (US)": "en-US-BrianNeural", "Guy (US)": "en-US-GuyNeural",
          "Christopher (US)": "en-US-ChristopherNeural", "Eric (US)": "en-US-EricNeural"}
ENGINES = {"Gemini CLI (your Google account)": "gemini", "Claude Code (your Claude account)": "claude"}
_ROOT = Path(__file__).resolve().parent.parent


def _runner():
    try:
        base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        return importlib.import_module("doodle_ai.runner")
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Doodle Survival is not installed", f"The doodle_ai folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _label(parent, text, row, col=0):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=row, column=col, padx=(0, 8), sticky="w")


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._ds_script_var = ctk.StringVar(value="")
    app._ds_voice_var = ctk.StringVar(value="")
    app._ds_edge_var = ctk.StringVar(value=next(iter(VOICES)))
    app._ds_engine_var = ctk.StringVar(value=next(iter(ENGINES)))
    app._ds_status_var = ctk.StringVar(value="")
    app._ds_cancel = threading.Event()
    app._ds_running = getattr(app, "_ds_running", False)

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._ds_block = block

    body = section(block, 0, 1, "Narration", "a survival story script; the voice is yours or free")
    rows = ctk.CTkFrame(body, fg_color="transparent")
    rows.grid(row=0, column=0, sticky="ew")
    rows.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Script (.txt)", app._ds_script_var, lambda: _browse(app, "script"), parent=rows,
                  placeholder_text="The story as you want it read: 'On day one, the radio said stay inside…'")
    app._path_row(1, "Your voice", app._ds_voice_var, lambda: _browse(app, "voice"), parent=rows,
                  placeholder_text="Optional: your voiceover of that script; empty = a free voice below")
    vrow = ctk.CTkFrame(body, fg_color="transparent")
    vrow.grid(row=1, column=0, sticky="w", pady=(8, 0))
    _label(vrow, "Free voice", 0)
    ctk.CTkOptionMenu(vrow, values=list(VOICES), variable=app._ds_edge_var, width=180).grid(row=0, column=1)

    body = section(block, 1, 2, "Who makes it", "an AI signed in on this computer draws every scene itself")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="w")
    _label(out, "AI", 0)
    ctk.CTkOptionMenu(out, values=list(ENGINES), variable=app._ds_engine_var, width=300).grid(row=0, column=1, sticky="w")
    _label(out, "Notes for the AI", 1)
    app._ds_notes = ctk.CTkTextbox(out, width=440, height=70)
    app._ds_notes.grid(row=1, column=1, pady=(8, 0), sticky="w")
    ctk.CTkLabel(body, text="The AI reads the doodle_dark guide, aligns the voice, plans the scenes, draws each one new from its "
                            "sentence (Scout, lit rooms, line-icon cards, the DAY tag), checks stills, renders and joins with "
                            "music and effects. A 40 s video takes about 10–20 minutes. It uses your own Gemini or Claude account.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 0))

    body = section(block, 2, 3, "Make the video", "one button: the AI does every step")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._ds_make_btn = ctk.CTkButton(go, text="Make video", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                     text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_make(app))
    app._ds_make_btn.grid(row=0, column=0, padx=(0, 10))
    app._ds_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._ds_stop_btn.grid(row=0, column=1, padx=(0, 10))
    app._ds_open_btn = make_button(go, "Open project folder", lambda: _open_folder(app), size="sm", width=170, state="disabled")
    app._ds_open_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._ds_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._ds_script_var, app._ds_voice_var, app._ds_edge_var, app._ds_engine_var):
        v.trace_add("write", lambda *_a: _save(app))


# ------------------------------------------------------------------ remembering
def _picks(app: Any) -> dict:
    notes = app._ds_notes.get("1.0", "end").strip() if getattr(app, "_ds_notes", None) is not None else ""
    return {"script": app._ds_script_var.get().strip(), "voice": app._ds_voice_var.get().strip(), "edge": app._ds_edge_var.get(),
            "engine": app._ds_engine_var.get(), "notes": notes}


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "doodle_ai" if ws is not None else None


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    d = _state_dir(app)
    if d is None or getattr(app, "_ds_restoring", False) or getattr(app, "_ds_script_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_ds_active", False)), "picks": _picks(app), "last": getattr(app, "_ds_last", None)}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_ds_restored_for", None) or getattr(app, "_ds_running", False):
        return
    app._ds_restored_for = key
    d = _read_settings(app)
    if not d:
        return
    app._ds_restoring = True
    try:
        p = d.get("picks") or {}
        for var, k, allowed in ((app._ds_script_var, "script", None), (app._ds_voice_var, "voice", None),
                                (app._ds_edge_var, "edge", VOICES), (app._ds_engine_var, "engine", ENGINES)):
            v = p.get(k)
            if v is not None and (allowed is None or v in allowed):
                var.set(v)
        app._ds_notes.delete("1.0", "end")
        app._ds_notes.insert("1.0", p.get("notes") or "")
        app._ds_last = d.get("last")
    finally:
        app._ds_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    types = {"script": [("Script", "*.txt"), ("All files", "*.*")], "voice": [("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")]}[kind]
    path = filedialog.askopenfilename(title={"script": "Choose the script", "voice": "Choose your voiceover"}[kind], filetypes=types)
    if path:   # remembered only: nothing is read until Make video
        {"script": app._ds_script_var, "voice": app._ds_voice_var}[kind].set(path)


def _open_folder(app: Any) -> None:
    last = getattr(app, "_ds_last", None) or {}
    p = last.get("project")
    if p and Path(p).is_dir():
        import subprocess

        opener = "open" if sys.platform == "darwin" else ("explorer" if sys.platform.startswith("win") else "xdg-open")
        subprocess.Popen([opener, p])


# ------------------------------------------------------------------ page
def activate(app: Any) -> None:
    if getattr(app, "_ds_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_ds_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._ds_active = True
    _restore(app)
    _save(app)
    app._ds_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_ds_active", False):
        app._ds_active = False
        if remember:
            _save(app)
        block = getattr(app, "_ds_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_ds_make_btn", None) is None:
        return
    running = getattr(app, "_ds_running", False)
    app._ds_make_btn.configure(state="disabled" if running else "normal")
    app._ds_stop_btn.configure(state="normal" if running and not app._ds_cancel.is_set() else "disabled")
    last = getattr(app, "_ds_last", None) or {}
    app._ds_open_btn.configure(state="normal" if last.get("project") else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_ds_running", False):
        app._cta_action = "ds_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._ds_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "The AI is making the video — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    app._cta_action = "ds_make"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a script, pick the AI, then click Make video.")
    app._set_generate_btn(state="normal", text="Make video")


def cta(app: Any, action: str) -> None:
    if action == "ds_cancel":
        cancel(app)
    else:
        on_make(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_ds_running", False) or app._ds_cancel.is_set():
        return
    app._ds_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def on_make(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ds_running", False):
        return
    ws = app._workspace
    if ws is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    p = _picks(app)
    if not p["script"] or not Path(p["script"]).is_file():
        messagebox.showerror("Cannot start", "Choose the script (.txt) first.")
        return
    if p["voice"] and not Path(p["voice"]).is_file():
        messagebox.showerror("Cannot start", f"The voice file is not there: {p['voice']}")
        return
    rn = _runner()
    if rn is None:
        return
    engine = ENGINES.get(p["engine"], "gemini")
    if not rn.find_cli(engine):
        messagebox.showinfo("Install the AI first", rn.install_hint(engine))
        return
    project = _state_dir(app) / time.strftime("video_%Y%m%d_%H%M%S")
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._ds_last = {"project": str(project)}
    _save(app)
    app._ds_status_var.set(f"Starting {engine}…")
    app._append_log(f"{TAG} Make video with {engine} -> {out_path.name} (work folder {project})\n")
    run = app._track_generation_start("doodle_ai")
    app._ds_cancel.clear()
    app._ds_running = True
    app._sync_primary_cta()

    def log(m: str) -> None:
        app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))

    def progress(frac: float, msg: str = "") -> None:
        app.ui_latest("style_progress", lambda: (app._ds_status_var.set(f"{int(frac * 100)}%  {msg}".strip()),
                                                 app.progress.set(max(0.0, min(1.0, frac))), app._export_progress(max(0.0, min(1.0, frac)), msg or "")))

    def worker() -> None:
        result, error = None, ""
        try:
            result = rn.make(project=str(project), script=p["script"], voice_file=p["voice"] or None, edge_voice=VOICES.get(p["edge"], "en-US-AndrewNeural"),
                             engine=engine, notes=p["notes"], out_path=str(out_path), log=log, progress=progress, cancel=app._ds_cancel.is_set)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._ds_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            from export_state import run_outcome

            app._ds_running = False
            if error:
                app._ds_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                msg = f"Done: {Path(result['final']).name} ({result['seconds']:.0f} s). Work files: {project}"
                app._ds_status_var.set(msg)
                app._append_log(f"{TAG} {msg}\n")
            done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._ds_cancel.is_set())
            app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                      message=error or ("" if done != "failed" else "The AI finished, but no video was written."))
            _save(app)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name="doodle-ai-make", daemon=True).start()
