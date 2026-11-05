"""Kids Learn: its own style page for preschool lessons (Ms Rachel-style format, original host). A lesson CSV, the host, set, voice,
music and sound effects; Generate speaks and plans the lesson, Render makes the video. All the work lives in cartoon3d-engine/
(runner.py, lesson.mjs) and kids_audio/, imported only inside the button handlers. Nothing starts until Generate: picking files or
options only remembers them.

app.py only calls in here: activate / deactivate / sync_cta / cta, and reads `_kl_block` / `_kl_running` / `_kl_active`."""

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

STYLE = "Kids Learn"
TAG = "[KIDS LEARN]"
RESOLUTIONS = {"720p preview (1280x720)": 720, "1080p final (1920x1080)": 1080}
_ROOT = Path(__file__).resolve().parent.parent


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "cartoon3d-engine"


def _runner():
    """cartoon3d-engine/runner.py (a folder name Python cannot import), loaded once; None with a message when it is missing."""
    mod = sys.modules.get("kl_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("kl_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["kl_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("kl_runner", None)
        messagebox.showerror("Kids Learn is not installed", f"The cartoon3d-engine folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


# Labels -> engine values. Kept here too so building the page never imports the engine.
HOSTS = {"3D host": "host3d", "Maya (simple)": "tutor"}
WORLDS = {"Playroom": "playroom", "Park": "park"}
MUSIC = {"Auto (matches the set)": "auto", "Playroom": "playroom", "Calm": "calm", "Sunny": "sunny", "Off": "off"}
VOICES = {"Jenny (US)": "en-US-JennyNeural", "Ana (US, child)": "en-US-AnaNeural", "Sonia (UK)": "en-GB-SoniaNeural"}
_VARS = ("csv", "vo", "host", "world", "voice", "music", "res")


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._kl_csv_var = ctk.StringVar(value="")
    app._kl_vo_var = ctk.StringVar(value="")
    app._kl_host_var = ctk.StringVar(value=next(iter(HOSTS)))
    app._kl_world_var = ctk.StringVar(value=next(iter(WORLDS)))
    app._kl_voice_var = ctk.StringVar(value=next(iter(VOICES)))
    app._kl_music_var = ctk.StringVar(value=next(iter(MUSIC)))
    app._kl_sfx_var = ctk.BooleanVar(value=True)
    app._kl_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._kl_status_var = ctk.StringVar(value="")
    app._kl_cancel = threading.Event()
    app._kl_running = getattr(app, "_kl_running", False)
    app._kl_planned = None   # the options of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._kl_block = block

    body = section(block, 0, 1, "Lesson", "a lesson CSV: one row per thing the host says")
    app._path_row(0, "Lesson CSV", app._kl_csv_var, lambda: _browse(app), parent=body,
                  placeholder_text="Choose the lesson CSV (type, text, object, color, count, word, gesture, emotion, pause)")
    app._path_row(1, "Voice-over", app._kl_vo_var, lambda: _browse(app, "vo"), parent=body,
                  placeholder_text="Optional: your recording of the lesson (the video follows it; without it the free voice reads the CSV)")
    ctk.CTkLabel(body, text="Row types: say, word, repeat, count, color, cheer, opposite, animal, shape, letter, feeling, chant. "
                            "With your voice-over, record the CSV lines in order; toys, cards and her mouth follow your words. "
                            "Samples: cartoon3d-engine/samples/first_words.csv and chant_lesson.csv.", font=ctk.CTkFont(size=11),
                 text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Look and sound")
    grid = ctk.CTkFrame(body, fg_color="transparent")
    grid.grid(row=0, column=0, sticky="w")
    for i, (label, var, values) in enumerate((("Host", app._kl_host_var, HOSTS), ("Set", app._kl_world_var, WORLDS), ("Voice", app._kl_voice_var, VOICES),
                                              ("Music", app._kl_music_var, MUSIC), ("Resolution", app._kl_res_var, RESOLUTIONS))):
        ctk.CTkLabel(grid, text=label, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=i // 2, column=(i % 2) * 2, padx=(0, 8), pady=3, sticky="w")
        ctk.CTkOptionMenu(grid, values=list(values), variable=var, width=220).grid(row=i // 2, column=(i % 2) * 2 + 1, padx=(0, 16), pady=3, sticky="w")
    ctk.CTkCheckBox(grid, text="Sound effects (pop, sparkle, chime, dings)", variable=app._kl_sfx_var).grid(row=2, column=2, columnspan=2, sticky="w", pady=3)
    ctk.CTkLabel(body, text="Music and sound effects are made on this computer (no downloads, no licences). The free Edge voice needs the internet.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 0))

    body = section(block, 2, 3, "Generate, then Render", "Generate speaks and plans the lesson; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._kl_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._kl_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._kl_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._kl_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._kl_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._kl_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._kl_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    _wire_persistence(app)
    block.grid_remove()


def _browse(app: Any, kind: str = "csv") -> None:
    from tkinter import filedialog

    if kind == "vo":
        path = filedialog.askopenfilename(title="Choose your voice-over", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._kl_vo_var
    else:
        path = filedialog.askopenfilename(title="Choose the lesson CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._kl_csv_var
    if path:
        var.set(path)   # remembered only: nothing is read, timed or spoken until Generate
        app._kl_planned = None
        _sync_buttons(app)


def options(app: Any) -> dict:
    return {"csv": app._kl_csv_var.get().strip(), "voiceover": app._kl_vo_var.get().strip(), "host": HOSTS.get(app._kl_host_var.get(), "host3d"), "world": WORLDS.get(app._kl_world_var.get(), "playroom"),
            "voice": VOICES.get(app._kl_voice_var.get(), "en-US-JennyNeural"), "music": MUSIC.get(app._kl_music_var.get(), "auto"),
            "sfx": bool(app._kl_sfx_var.get()), "resolution": RESOLUTIONS.get(app._kl_res_var.get(), 720)}


# ---- what a project keeps: its page choices and whether the lesson is planned -------------------------------------------------
# Saved to <project>/state/kids_learn/settings.json whenever a choice changes or Generate finishes. The plan is only put back while the
# lesson CSV is exactly as it was at Generate (size + saved time).

def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "kids_learn" / "settings.json" if ws is not None else None


def _save(app: Any) -> None:
    if getattr(app, "_kl_restoring", False):
        return
    f = _settings_file(app)
    if f is None:
        return
    try:
        labels = {k: getattr(app, f"_kl_{k}_var").get() for k in _VARS}
        planned = getattr(app, "_kl_planned", None)
        data = {"labels": labels, "sfx": bool(app._kl_sfx_var.get()),
                "planned": {**planned, "sig": _sig(planned["csv"]), "vo_sig": _sig(planned["voiceover"]) if planned.get("voiceover") else None} if planned else None}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_kl_restored_for", None) or getattr(app, "_kl_running", False) or getattr(app, "_kl_block", None) is None:
        return
    app._kl_restored_for = key
    app._kl_planned = None
    f = _settings_file(app)
    if f is None or not f.is_file():
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    app._kl_restoring = True
    try:
        for k, v in (d.get("labels") or {}).items():
            if k in _VARS and isinstance(v, str):
                getattr(app, f"_kl_{k}_var").set(v)
        app._kl_sfx_var.set(bool(d.get("sfx", True)))
        p = d.get("planned")
        same_vo = (not p.get("voiceover")) or (p.get("vo_sig") is not None and _sig(p["voiceover"]) == p["vo_sig"]) if p else False
        if p and p.get("csv") and p.get("sig") is not None and _sig(p["csv"]) == p["sig"] and same_vo:
            app._kl_planned = {k: v for k, v in p.items() if k not in ("sig", "vo_sig")}
            app._kl_status_var.set("Restored: the lesson is planned. Click Render, or Generate to plan again.")
    finally:
        app._kl_restoring = False


def _wire_persistence(app: Any) -> None:
    for v in (*(getattr(app, f"_kl_{k}_var") for k in _VARS), app._kl_sfx_var):
        v.trace_add("write", lambda *_a: _save(app))


# ---- page lifecycle (same shape as the other own-page styles) --------------------------------------------------------------------

def activate(app: Any) -> None:
    if getattr(app, "_kl_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_kl_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._kl_active = True
    _restore(app)
    from .voiceover_view import adopt_project_voiceover
    adopt_project_voiceover(app, app._kl_vo_var)      # the project voiceover (Voiceover tab / Audio & Effects) if this box is empty
    app._kl_block.grid()
    _sync_buttons(app)


def deactivate(app: Any) -> None:
    if getattr(app, "_kl_active", False):
        app._kl_active = False
        block = getattr(app, "_kl_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_kl_generate_btn", None) is None:
        return
    running = getattr(app, "_kl_running", False)
    app._kl_generate_btn.configure(state="disabled" if running else "normal")
    app._kl_render_btn.configure(state="normal" if (app._kl_planned and not running) else "disabled")
    app._kl_stop_btn.configure(state="normal" if running and not app._kl_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _restore(app)
    _sync_buttons(app)
    if getattr(app, "_kl_running", False):
        app._cta_action = "kl_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._kl_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._kl_planned:
        app._cta_action = "kl_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The lesson is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "kl_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a lesson CSV, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "kl_cancel":
        cancel(app)
    elif action == "kl_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_kl_running", False) or app._kl_cancel.is_set():
        return
    app._kl_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "kids_learn"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _progress(app: Any):
    last = {"t": 0.0}

    def cb(frac: float, msg: str = "") -> None:
        import time as _time
        if _time.monotonic() - last["t"] >= 30:      # a real log line every 30 s keeps the stall watchdog quiet
            last["t"] = _time.monotonic()
            app.after(0, lambda m=f"{int(frac * 100)}% {msg}".strip(): app._append_log(f"{TAG} {m}\n"))
        app.after(0, lambda: (app._kl_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._kl_cancel.clear()
    app._kl_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._kl_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._kl_running = False
            if error:
                app._kl_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._kl_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def _engine_opts(o: dict) -> dict:
    return {k: o[k] for k in ("host", "world", "voice", "music", "sfx", "resolution", "voiceover")}


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_kl_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    o = options(app)
    if not o["csv"] or not Path(o["csv"]).is_file():
        messagebox.showerror("Cannot start", "Choose the lesson CSV first." if not o["csv"] else f"The lesson CSV is not there: {o['csv']}")
        return
    if o["voiceover"] and not Path(o["voiceover"]).is_file():
        messagebox.showerror("Cannot start", f"The voice-over is not there: {o['voiceover']}")
        return
    kl = _runner()
    if kl is None:
        return
    if o["host"] == "host3d" and not kl.host_ready():
        messagebox.showerror("Cannot start", "The 3D host model is missing (cartoon3d-engine/assets/host/host.glb). Choose Maya, or restore the file.")
        return
    work = str(_work_dir(app))
    app._kl_status_var.set("Timing your voice-over and planning…" if o["voiceover"] else "Speaking and planning…")
    app._append_log(f"{TAG} Generate: {'timing your voice-over' if o['voiceover'] else 'speaking the lines'} and planning the lesson\n")

    def job():
        return kl.plan(o["csv"], work, progress=_progress(app), cancel=app._kl_cancel.is_set, log=lambda m: app.after(0, lambda: app._append_log(m + "\n")), **_engine_opts(o))

    def done(r) -> None:
        app._kl_planned = dict(o)
        _save(app)
        warn = f"  {len(r['warnings'])} notes (see the log)." if r["warnings"] else ""
        vo = r.get("voiceover") or {}
        heard = f" Your voice-over: {vo.get('lines_found')}/{vo.get('lines')} lines found." if vo else ""
        msg = f"Planned {r['lines']} lines, {r['duration']:.0f} s, {r['props']} toys, {r['cards']} word cards.{heard}{warn}"
        app._kl_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "kids-learn-plan", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_kl_running", False):
        return
    ws, plan = app._workspace, app._kl_planned
    if ws is None or not plan:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned lesson.")
        return
    if options(app) != plan or _sig(plan["csv"]) is None:
        messagebox.showinfo("Click Generate first", "You changed the lesson or its options after Generate. Click Generate again, then Render.")
        return
    kl = _runner()
    if kl is None:
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._kl_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("kids_learn")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._kl_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return kl.render(plan["csv"], str(_work_dir(app)), str(out_path), progress=_progress(app), cancel=app._kl_cancel.is_set,
                         log=lambda m: app.after(0, lambda: app._append_log(m + "\n")), **_engine_opts(plan))

    def done(r) -> None:
        a = r.get("audio") or {}
        msg = f"Done: {out_path.name}" + (f"  ({a.get('lufs')} LUFS, {a.get('sfx', 0)} sound effects)" if a else "")
        app._kl_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "kids-learn-render", job, done, end)
