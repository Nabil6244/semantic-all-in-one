"""Prepper Host: its own style page. A Prepper Host CSV (or a script) -> a talking-host prepper explainer: the same AI host
in every picture (Flow reference pictures), split screen / round host cam / b-roll with camera moves, product photo cards,
math rows that count up, checklists, bars, big numbers, chapter bumpers, the host's name bar, a subscribe pop, a thumbnail.

Generate = voice (free Edge voice, or your file) + director + Flow pictures (free; talking clips only if picked, they use
Flow video credits once per host). Render = the video + thumbnail in the project's final folder. All work lives in
prepper_host/runner.py, imported only inside the button handlers. Nothing starts until Generate. No Gemini.

Each project remembers this page (state/prepper_host/settings.json, the plan in state/prepper_host/plan.json).
app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_ph_block` / `_ph_running` / `_ph_active`."""

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

STYLE = "Prepper Host"
TAG = "[PREPPER HOST]"
VOICES = {"Andrew (US)": "en-US-AndrewNeural", "Brian (US)": "en-US-BrianNeural", "Guy (US)": "en-US-GuyNeural",
          "Christopher (US)": "en-US-ChristopherNeural", "Eric (US)": "en-US-EricNeural"}
TALKING = {"Host picture with a slow push (free)": False, "Talking clips from Flow (uses video credits, made once)": True,
           "Flow voice: he speaks his own lines, lips match (one Flow clip per host line)": "flow"}
SOUND = {"Voice + effects": "fx", "Voice only (like the reference)": "voice", "Voice + effects + soft music": "music"}
RESOLUTIONS = {"1080p final": False, "720p fast preview": True}
HOSTS = {"Dale (rancher, olive jacket)": "dale"}
_ROOT = Path(__file__).resolve().parent.parent


def _load_hosts() -> None:
    try:
        from prepper_host import host as _h
        for n in _h.names():
            if n not in HOSTS.values():
                HOSTS[n.title()] = n
    except Exception:  # noqa: BLE001
        pass


def _runner():
    try:
        base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        return importlib.import_module("prepper_host.runner")
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Prepper Host is not installed", f"The prepper_host folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _label(parent, text, row, col=0):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=row, column=col, padx=(0, 8), sticky="w")


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._ph_csv_var = ctk.StringVar(value="")
    app._ph_script_var = ctk.StringVar(value="")
    app._ph_voice_var = ctk.StringVar(value="")
    app._ph_edge_var = ctk.StringVar(value=next(iter(VOICES)))
    _load_hosts()
    app._ph_host_var = ctk.StringVar(value=next(iter(HOSTS)))
    app._ph_talk_var = ctk.StringVar(value=next(iter(TALKING)))
    app._ph_sound_var = ctk.StringVar(value=next(iter(SOUND)))
    app._ph_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._ph_status_var = ctk.StringVar(value="")
    app._ph_cancel = threading.Event()
    app._ph_running = getattr(app, "_ph_running", False)
    app._ph_planned = None

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._ph_block = block

    body = section(block, 0, 1, "Narration", "a Prepper Host CSV (best) or a script")
    rows = ctk.CTkFrame(body, fg_color="transparent")
    rows.grid(row=0, column=0, sticky="ew")
    rows.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Prepper Host CSV", app._ph_csv_var, lambda: _browse(app, "csv"), parent=rows,
                  placeholder_text="line, shot, visual, product, title, rows, chapter (prepper_host/csv_prompt.txt writes one)")
    app._path_row(1, "Or a script (.txt)", app._ph_script_var, lambda: _browse(app, "script"), parent=rows,
                  placeholder_text="Only if there is no CSV: each sentence becomes a host / split / b-roll shot")
    app._path_row(2, "Your voice", app._ph_voice_var, lambda: _browse(app, "voice"), parent=rows,
                  placeholder_text="Optional: your voiceover file; empty = a free voice below")
    vrow = ctk.CTkFrame(body, fg_color="transparent")
    vrow.grid(row=1, column=0, sticky="w", pady=(8, 0))
    _label(vrow, "Free voice", 0)
    ctk.CTkOptionMenu(vrow, values=list(VOICES), variable=app._ph_edge_var, width=180).grid(row=0, column=1)
    ctk.CTkLabel(body, text="Every CSV line is one shot: host, split, pip, broll, product, compare, data, checklist, bars, big or "
                            "chapter (empty = the director picks). Numbers become cards that build as they are said; named "
                            "products become photo cards.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(6, 0))

    body = section(block, 1, 2, "Host and look")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="w")
    _label(out, "Host", 0)
    ctk.CTkOptionMenu(out, values=list(HOSTS), variable=app._ph_host_var, width=240).grid(row=0, column=1, padx=(0, 16), sticky="w")
    _label(out, "Host on screen", 1)
    ctk.CTkOptionMenu(out, values=list(TALKING), variable=app._ph_talk_var, width=380).grid(row=1, column=1, pady=(8, 0), sticky="w")
    _label(out, "Sound", 2)
    ctk.CTkOptionMenu(out, values=list(SOUND), variable=app._ph_sound_var, width=260).grid(row=2, column=1, pady=(8, 0), sticky="w")
    _label(out, "Resolution", 3)
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._ph_res_var, width=180).grid(row=3, column=1, pady=(8, 0), sticky="w")
    ctk.CTkLabel(body, text="The host keeps the same face in every picture: Flow gets his reference pictures each time. Pictures "
                            "are made once and kept for later videos; a picture Flow cannot make is replaced by a stand-in, "
                            "so the video never stops.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 0))

    body = section(block, 2, 3, "Generate, then Render", "Generate plans the shots and makes the pictures; Render draws the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._ph_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._ph_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._ph_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._ph_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._ph_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._ph_stop_btn.grid(row=0, column=2, padx=(0, 10))
    app._ph_csv_btn = make_button(go, "Save plan as CSV", lambda: save_csv(app), size="sm", width=150, state="disabled")
    app._ph_csv_btn.grid(row=0, column=3)
    ctk.CTkLabel(body, textvariable=app._ph_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._ph_csv_var, app._ph_script_var, app._ph_voice_var, app._ph_edge_var, app._ph_host_var, app._ph_talk_var,
              app._ph_sound_var, app._ph_res_var):
        v.trace_add("write", lambda *_a: _changed(app))


# ------------------------------------------------------------------ picks
def _fsig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _picks(app: Any) -> dict:
    return {"csv": app._ph_csv_var.get().strip(), "script": app._ph_script_var.get().strip(), "voice": app._ph_voice_var.get().strip(),
            "edge": app._ph_edge_var.get(), "host": app._ph_host_var.get(), "talk": app._ph_talk_var.get(),
            "sound": app._ph_sound_var.get(), "res": app._ph_res_var.get()}


def _sig(app: Any) -> list:
    p = _picks(app)
    return [p["edge"], p["host"], p["talk"], p["sound"], p["res"]] + [_fsig(p[k]) if p[k] else None for k in ("csv", "script", "voice")]


def _changed(app: Any) -> None:
    """A pick changed: remember it; a Generate made for other picks no longer counts. Nothing starts here."""
    p = getattr(app, "_ph_planned", None)
    if p and p["sig"] != _sig(app) and not getattr(app, "_ph_restoring", False):
        app._ph_planned = None
        _sync_buttons(app)
        app._sync_primary_cta()
    _save(app)


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "prepper_host" if ws is not None else None


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    d = _state_dir(app)
    if d is None or getattr(app, "_ph_restoring", False) or getattr(app, "_ph_csv_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_ph_active", False)), "picks": _picks(app), "planned": getattr(app, "_ph_planned", None)}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_ph_restored_for", None) or getattr(app, "_ph_running", False):
        return
    app._ph_restored_for = key
    app._ph_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._ph_restoring = True
    try:
        p = d.get("picks") or {}
        for var, k, allowed in ((app._ph_csv_var, "csv", None), (app._ph_script_var, "script", None), (app._ph_voice_var, "voice", None),
                                (app._ph_edge_var, "edge", VOICES), (app._ph_host_var, "host", HOSTS), (app._ph_talk_var, "talk", TALKING),
                                (app._ph_sound_var, "sound", SOUND), (app._ph_res_var, "res", RESOLUTIONS)):
            v = p.get(k)
            if v is not None and (allowed is None or v in allowed):
                var.set(v)
        pl = d.get("planned")
        if pl and pl.get("sig") == _sig(app) and Path(pl.get("plan", "")).is_file():
            app._ph_planned = pl
            app._ph_status_var.set("Restored: planned and ready. Click Render.")
    finally:
        app._ph_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    types = {"csv": [("Prepper Host CSV", "*.csv"), ("All files", "*.*")], "script": [("Script", "*.txt"), ("All files", "*.*")],
             "voice": [("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")]}[kind]
    path = filedialog.askopenfilename(title={"csv": "Choose the Prepper Host CSV", "script": "Choose the script",
                                             "voice": "Choose your voiceover"}[kind], filetypes=types)
    if path:   # remembered only: nothing is read until Generate
        {"csv": app._ph_csv_var, "script": app._ph_script_var, "voice": app._ph_voice_var}[kind].set(path)


# ------------------------------------------------------------------ page
def activate(app: Any) -> None:
    if getattr(app, "_ph_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_ph_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._ph_active = True
    _restore(app)
    _save(app)
    app._ph_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_ph_active", False):
        app._ph_active = False
        if remember:
            _save(app)
        block = getattr(app, "_ph_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_ph_generate_btn", None) is None:
        return
    running = getattr(app, "_ph_running", False)
    app._ph_generate_btn.configure(state="disabled" if running else "normal")
    app._ph_render_btn.configure(state="normal" if (app._ph_planned and not running) else "disabled")
    app._ph_stop_btn.configure(state="normal" if running and not app._ph_cancel.is_set() else "disabled")
    app._ph_csv_btn.configure(state="normal" if (app._ph_planned and not running) else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_ph_running", False):
        app._cta_action = "ph_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._ph_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._ph_planned:
        app._cta_action = "ph_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Planned. Click Render to draw the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "ph_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a Prepper Host CSV or a script, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "ph_cancel":
        cancel(app)
    elif action == "ph_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_ph_running", False) or app._ph_cancel.is_set():
        return
    app._ph_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.ui_latest("style_progress", lambda: (app._ph_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._ph_cancel.clear()
    app._ph_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._ph_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._ph_running = False
            if error:
                app._ph_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._ph_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ph_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    p = _picks(app)
    if not p["csv"] and not p["script"]:
        messagebox.showerror("Cannot start", "Choose a Prepper Host CSV (or a script) first.")
        return
    for k, what in (("csv", "Prepper Host CSV"), ("script", "script"), ("voice", "voice file")):
        if p[k] and not Path(p[k]).is_file():
            messagebox.showerror("Cannot start", f"The {what} is not there: {p[k]}")
            return
    rn = _runner()
    if rn is None:
        return
    app._ph_planned = None
    _save(app)
    sig = _sig(app)
    plan_path = _state_dir(app) / "plan.json"
    app._ph_status_var.set("Planning: voice, shots, cards; Flow makes the pictures…")
    app._append_log(f"{TAG} Generate: voice, shots and pictures\n")

    def job():
        r = rn.plan(csv_path=p["csv"] or None, script=p["script"] or None, voice_file=p["voice"] or None,
                    edge_voice=VOICES.get(p["edge"]), host=HOSTS.get(p["host"], "dale"), talking=TALKING.get(p["talk"], False),
                    preview=RESOLUTIONS.get(p["res"], False), sound=SOUND.get(p["sound"], "fx"), log=_log(app),
                    cancel=app._ph_cancel.is_set)
        rn.save(r["spec"], plan_path)
        return r

    def ready(r) -> None:
        app._ph_planned = {"sig": sig, "plan": str(plan_path)}
        kinds = ", ".join(f"{n} {k}" for k, n in sorted(r["kinds"].items(), key=lambda x: -x[1]))
        miss = f"; {r['missing']} picture(s) Flow did not make yet (stand-ins; Generate again to retry)" if r["missing"] else ""
        notes = f"; {len(r['problems'])} CSV note(s) in the log" if r["problems"] else ""
        talk = ", talking host" if r.get("talking") else ""
        msg = f"{r['shots']} shots, ~{r['seconds']:.0f} s ({kinds}){talk}{miss}{notes}. Click Render."
        app._ph_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "prepper-host-plan", job, ready)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ph_running", False):
        return
    ws, planned = app._workspace, app._ph_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a plan.")
        return
    if planned["sig"] != _sig(app):
        messagebox.showinfo("Click Generate first", "You changed the CSV, script, voice or options after Generate. Click Generate again, then Render.")
        return
    rn = _runner()
    if rn is None:
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._ph_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("prepper_host")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._ph_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return rn.render(rn.load(planned["plan"]), str(out_path), progress=_progress(app), cancel=app._ph_cancel.is_set, log=_log(app))

    def done(r) -> None:
        thumb = f" Thumbnail: {Path(r['thumbnail']).name}." if r.get("thumbnail") else ""
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s).{thumb}"
        app._ph_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "prepper-host-render", job, done, end)


def save_csv(app: Any) -> None:
    """The planned shots as a Prepper Host CSV in the project, to tune by hand and Generate again."""
    planned = getattr(app, "_ph_planned", None)
    rn = _runner()
    if not planned or rn is None:
        return
    try:
        from prepper_host import csvplan

        dest = _state_dir(app) / "plan.csv"
        dest.write_text(csvplan.from_plan(rn.load(planned["plan"])), encoding="utf-8")
        app._ph_status_var.set(f"Saved {dest}. Edit it, choose it as the Prepper Host CSV, then Generate again.")
        app._append_log(f"{TAG} plan saved as CSV: {dest}\n")
    except Exception as exc:  # noqa: BLE001
        app._ph_status_var.set(f"Could not save the CSV: {type(exc).__name__}: {exc}")
