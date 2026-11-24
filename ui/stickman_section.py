"""Stickman: its own style page. A script (.txt) and/or a Stickman CSV -> code-drawn stick figures acting out every
line, with props, places, spoken-word captions, a music bed and effects. Five looks, 16:9 video or a native 9:16 Short.

Generate = voice (free Edge voice, or your file) + director + checker: a plan, nothing drawn. Render = the video in the
project's final folder. All the work lives in stickman/runner.py, imported only inside the button handlers. Nothing
starts until Generate: picking a file or an option only remembers it. No Gemini.

Each project remembers this page (state/stickman/settings.json, the plan in state/stickman/plan.json).

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_sm_block` / `_sm_running` / `_sm_active`."""

from __future__ import annotations

import importlib
import json
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Stickman"
TAG = "[STICKMAN]"
LOOKS = {"Auto (CSV look, else Ink Paper)": None, "Ink Paper": "ink_paper", "Chalk Dark": "chalk_dark", "Colour Pop": "colour_pop", "Retro TV": "retro_tv",
         "Night Thriller": "night_thriller", "Meme (Flow-painted rooms)": "meme"}
HOSTS = {"Auto (CSV, else none)": None, "No host": ""}     # + one entry per puppet folder (your pictures), filled on build


def _load_hosts() -> None:
    try:
        from stickman import host as _h
        for k, v in _h.hosts().items():
            HOSTS[f"{v} — host in the corner"] = k
    except Exception:  # noqa: BLE001
        pass
FORMATS = ("Video 16:9", "Short 9:16")
RESOLUTIONS = {"1080p final": False, "720p fast preview": True}
VOICES = {"Andrew (US)": "en-US-AndrewNeural", "Ava (US)": "en-US-AvaNeural", "Brian (US)": "en-US-BrianNeural",
          "Emma (US)": "en-US-EmmaNeural", "Guy (US)": "en-US-GuyNeural", "Ryan (UK)": "en-GB-RyanNeural",
          "Sonia (UK)": "en-GB-SoniaNeural"}
_ROOT = Path(__file__).resolve().parent.parent


def _runner():
    try:
        base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        return importlib.import_module("stickman.runner")
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Stickman is not installed", f"The stickman folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _label(parent, text, row, col=0):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=row, column=col, padx=(0, 8), sticky="w")


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._sm_script_var = ctk.StringVar(value="")
    app._sm_csv_var = ctk.StringVar(value="")
    app._sm_voice_var = ctk.StringVar(value="")
    app._sm_edge_var = ctk.StringVar(value=next(iter(VOICES)))
    app._sm_look_var = ctk.StringVar(value=next(iter(LOOKS)))
    app._sm_format_var = ctk.StringVar(value=FORMATS[0])
    app._sm_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    _load_hosts()
    app._sm_host_var = ctk.StringVar(value=next(iter(HOSTS)))
    app._sm_status_var = ctk.StringVar(value="")
    app._sm_cancel = threading.Event()
    app._sm_running = getattr(app, "_sm_running", False)
    app._sm_planned = None   # {"sig": picks signature, "plan": path} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._sm_block = block

    body = section(block, 0, 1, "Narration", "a script, a Stickman CSV, or both")
    rows = ctk.CTkFrame(body, fg_color="transparent")
    rows.grid(row=0, column=0, sticky="ew")
    rows.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Script (.txt)", app._sm_script_var, lambda: _browse(app, "script"), parent=rows,
                  placeholder_text="The narration; a first line without a full stop is the title")
    app._path_row(1, "Stickman CSV", app._sm_csv_var, lambda: _browse(app, "csv"), parent=rows,
                  placeholder_text="Optional: line, action, props, place, text, camera, sfx (empty cells = the director decides)")
    app._path_row(2, "Your voice", app._sm_voice_var, lambda: _browse(app, "voice"), parent=rows,
                  placeholder_text="Optional: your voiceover file; empty = a free voice below")
    vrow = ctk.CTkFrame(body, fg_color="transparent")
    vrow.grid(row=1, column=0, sticky="w", pady=(8, 0))
    _label(vrow, "Free voice", 0)
    ctk.CTkOptionMenu(vrow, values=list(VOICES), variable=app._sm_edge_var, width=180).grid(row=0, column=1)
    ctk.CTkLabel(body, text="Each spoken line becomes one beat: its words pick the pose (40), a prop (77) and the place (8); "
                            "every word darkens as it is said. A CSV row can set any of these by hand.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(6, 0))

    body = section(block, 1, 2, "Look and format")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="w")
    _label(out, "Look", 0)
    ctk.CTkOptionMenu(out, values=list(LOOKS), variable=app._sm_look_var, width=180).grid(row=0, column=1, padx=(0, 16))
    _label(out, "Format", 0, 2)
    ctk.CTkSegmentedButton(out, values=list(FORMATS), variable=app._sm_format_var).grid(row=0, column=3, padx=(0, 16))
    _label(out, "Resolution", 1)
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._sm_res_var, width=180).grid(row=1, column=1, pady=(8, 0), sticky="w")
    _label(out, "Host", 2)
    ctk.CTkOptionMenu(out, values=list(HOSTS), variable=app._sm_host_var, width=260).grid(row=2, column=1, columnspan=3, pady=(8, 0), sticky="w")
    ctk.CTkLabel(body, text="Host: your picture talks in the corner while the stickmen act (any look). Meme: Flow paints each room "
                            "once on Generate and keeps it for later videos; a room Flow cannot paint is drawn instead.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 0))

    body = section(block, 2, 3, "Generate, then Render", "Generate plans every beat; Render draws the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._sm_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._sm_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._sm_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._sm_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._sm_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._sm_stop_btn.grid(row=0, column=2, padx=(0, 10))
    app._sm_csv_btn = make_button(go, "Save plan as CSV", lambda: save_csv(app), size="sm", width=150, state="disabled")
    app._sm_csv_btn.grid(row=0, column=3)
    ctk.CTkLabel(body, textvariable=app._sm_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._sm_script_var, app._sm_csv_var, app._sm_voice_var, app._sm_edge_var, app._sm_look_var,
              app._sm_format_var, app._sm_res_var, app._sm_host_var):
        v.trace_add("write", lambda *_a: _changed(app))


# ------------------------------------------------------------------ picks
def _fsig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _picks(app: Any) -> dict:
    return {"script": app._sm_script_var.get().strip(), "csv": app._sm_csv_var.get().strip(), "voice": app._sm_voice_var.get().strip(),
            "edge": app._sm_edge_var.get(), "look": app._sm_look_var.get(), "format": app._sm_format_var.get(), "res": app._sm_res_var.get(),
            "host": app._sm_host_var.get()}


def _sig(app: Any) -> list:
    p = _picks(app)
    return [p["edge"], p["look"], p["format"], p["res"], p.get("host")] + [_fsig(p[k]) if p[k] else None for k in ("script", "csv", "voice")]


def _changed(app: Any) -> None:
    """A pick changed: remember it; a Generate made for other picks no longer counts. Nothing starts here."""
    p = getattr(app, "_sm_planned", None)
    if p and p["sig"] != _sig(app) and not getattr(app, "_sm_restoring", False):
        app._sm_planned = None
        _sync_buttons(app)
        app._sync_primary_cta()
    _save(app)


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "stickman" if ws is not None else None


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    d = _state_dir(app)
    if d is None or getattr(app, "_sm_restoring", False) or getattr(app, "_sm_script_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_sm_active", False)), "picks": _picks(app), "planned": getattr(app, "_sm_planned", None)}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_sm_restored_for", None) or getattr(app, "_sm_running", False):
        return
    app._sm_restored_for = key
    app._sm_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._sm_restoring = True
    try:
        p = d.get("picks") or {}
        for var, k, allowed in ((app._sm_script_var, "script", None), (app._sm_csv_var, "csv", None), (app._sm_voice_var, "voice", None),
                                (app._sm_edge_var, "edge", VOICES), (app._sm_look_var, "look", LOOKS),
                                (app._sm_format_var, "format", FORMATS), (app._sm_res_var, "res", RESOLUTIONS),
                                (app._sm_host_var, "host", HOSTS)):
            v = p.get(k)
            if v is not None and (allowed is None or v in allowed):
                var.set(v)
        pl = d.get("planned")
        if pl and pl.get("sig") == _sig(app) and Path(pl.get("plan", "")).is_file():
            app._sm_planned = pl
            app._sm_status_var.set("Restored: planned and ready. Click Render.")
    finally:
        app._sm_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    types = {"script": [("Script", "*.txt"), ("All files", "*.*")], "csv": [("Stickman CSV", "*.csv"), ("All files", "*.*")],
             "voice": [("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")]}[kind]
    path = filedialog.askopenfilename(title={"script": "Choose the script", "csv": "Choose the Stickman CSV",
                                             "voice": "Choose your voiceover"}[kind], filetypes=types)
    if path:   # remembered only: nothing is read until Generate
        {"script": app._sm_script_var, "csv": app._sm_csv_var, "voice": app._sm_voice_var}[kind].set(path)


# ------------------------------------------------------------------ page
def activate(app: Any) -> None:
    if getattr(app, "_sm_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_sm_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._sm_active = True
    _restore(app)
    _save(app)
    app._sm_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_sm_active", False):
        app._sm_active = False
        if remember:
            _save(app)
        block = getattr(app, "_sm_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_sm_generate_btn", None) is None:
        return
    running = getattr(app, "_sm_running", False)
    app._sm_generate_btn.configure(state="disabled" if running else "normal")
    app._sm_render_btn.configure(state="normal" if (app._sm_planned and not running) else "disabled")
    app._sm_stop_btn.configure(state="normal" if running and not app._sm_cancel.is_set() else "disabled")
    app._sm_csv_btn.configure(state="normal" if (app._sm_planned and not running) else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_sm_running", False):
        app._cta_action = "sm_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._sm_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._sm_planned:
        app._cta_action = "sm_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Planned. Click Render to draw the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "sm_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a script or a Stickman CSV, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "sm_cancel":
        cancel(app)
    elif action == "sm_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_sm_running", False) or app._sm_cancel.is_set():
        return
    app._sm_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.ui_latest("style_progress", lambda: (app._sm_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._sm_cancel.clear()
    app._sm_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._sm_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._sm_running = False
            if error:
                app._sm_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._sm_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_sm_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    p = _picks(app)
    if not p["script"] and not p["csv"]:
        messagebox.showerror("Cannot start", "Choose the script (.txt) or a Stickman CSV first.")
        return
    for k, what in (("script", "script"), ("csv", "Stickman CSV"), ("voice", "voice file")):
        if p[k] and not Path(p[k]).is_file():
            messagebox.showerror("Cannot start", f"The {what} is not there: {p[k]}")
            return
    rn = _runner()
    if rn is None:
        return
    app._sm_planned = None
    _save(app)
    sig = _sig(app)
    plan_path = _state_dir(app) / "plan.json"
    app._sm_status_var.set("Planning: voice, beats, poses, props and places…")
    app._append_log(f"{TAG} Generate: planning the beats\n")
    shorts, preview = p["format"] == FORMATS[1], RESOLUTIONS.get(p["res"], False)

    def job():
        r = rn.plan(p["script"] or None, csv_path=p["csv"] or None, voice_file=p["voice"] or None, edge_voice=VOICES.get(p["edge"]),
                    look=LOOKS.get(p["look"]), host=HOSTS.get(p["host"]), cancel=app._sm_cancel.is_set,
                    shorts=shorts, preview=preview, log=_log(app))
        rn.save(r["spec"], plan_path)
        return r

    def ready(r) -> None:
        app._sm_planned = {"sig": sig, "plan": str(plan_path)}
        extra = f", {len(r['problems'])} CSV note(s) in the log" if r["problems"] else ""
        head = f"\"{r['title']}\": " if r["title"] else ""
        fixed = f", the checker fixed {len(r['notes'])}" if r["notes"] else ""
        host = f", host {r['host']}" if r.get("host") else ""
        rooms = f", {len(r['unpainted'])} room(s) drawn (Flow had no picture)" if r.get("unpainted") else ""
        msg = f"{head}{r['beats']} beats, ~{r['seconds']:.0f} s, {r['look'].replace('_', ' ')}{host}{fixed}{extra}{rooms}. Click Render."
        app._sm_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "stickman-plan", job, ready)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_sm_running", False):
        return
    ws, planned = app._workspace, app._sm_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a plan.")
        return
    if planned["sig"] != _sig(app):
        messagebox.showinfo("Click Generate first", "You changed the script, CSV, voice, look or format after Generate. Click Generate again, then Render.")
        return
    rn = _runner()
    if rn is None:
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._sm_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("stickman")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._sm_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return rn.render(rn.load(planned["plan"]), str(out_path), progress=_progress(app), cancel=app._sm_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s)."
        app._sm_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "stickman-render", job, done, end)


def save_csv(app: Any) -> None:
    """The planned beats as a Stickman CSV in the project, to tune by hand and Generate again."""
    planned = getattr(app, "_sm_planned", None)
    rn = _runner()
    if not planned or rn is None:
        return
    try:
        from stickman import csvplan

        dest = _state_dir(app) / "plan.csv"
        dest.write_text(csvplan.from_plan(rn.load(planned["plan"])), encoding="utf-8")
        app._sm_status_var.set(f"Saved {dest}. Edit it, choose it as the Stickman CSV, then Generate again.")
        app._append_log(f"{TAG} plan saved as CSV: {dest}\n")
    except Exception as exc:  # noqa: BLE001
        app._sm_status_var.set(f"Could not save the CSV: {type(exc).__name__}: {exc}")
