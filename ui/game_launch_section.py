"""Game Launch: its own style page. A game's official trailers side by side with the real places they copy ("Game vs Real"):
split screens, a satellite map of the game's regions, chapter cards, a synthwave bed, plus optional Shorts (one per chapter)
and a thumbnail. Made for a big game launch (GTA 6's Leonida vs real Florida was the first).

Input: a scenes CSV (one row per shot, game_launch/plan.py says the columns) and the folder with the game's trailer files.
Generate checks the CSV, reads each trailer's cuts, makes the voice lines (free Edge voices) and lists the real-life clips in
the Visuals tab (a file the CSV names is filed there as is; search words are fetched through the app's stock sources).
Render uses exactly what the Visuals tab holds. Nothing starts until Generate: picking files only remembers them. No Gemini.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_gl_block` / `_gl_running` / `_gl_active`."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Game Launch"
TAG = "[GAME LAUNCH]"
OWNER = "game_launch"       # its real-clip rows in the Visuals tab (visual_bridge.OWNERS)
VOICES = {"Andrew (US, male)": "en-US-AndrewNeural", "Guy (US, male)": "en-US-GuyNeural",
          "Christopher (US, male)": "en-US-ChristopherNeural", "Aria (US, female)": "en-US-AriaNeural",
          "Jenny (US, female)": "en-US-JennyNeural", "Ryan (UK, male)": "en-GB-RyanNeural"}
_ROOT = Path(__file__).resolve().parent.parent


def _example_csv() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "game_launch" / "example_scenes.csv"


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._gl_csv_var = ctk.StringVar(value="")
    app._gl_trailers_var = ctk.StringVar(value="")
    app._gl_voice_var = ctk.StringVar(value=next(iter(VOICES)))
    app._gl_vo_var = ctk.StringVar(value="")       # the user's own recording (mp3/wav); used instead of the Edge voice when set
    app._gl_shorts_var = ctk.BooleanVar(value=True)
    app._gl_thumb_var = ctk.BooleanVar(value=True)
    app._gl_thumb_text_var = ctk.StringVar(value="")
    app._gl_foot_var = ctk.StringVar(value="")
    app._gl_status_var = ctk.StringVar(value="")
    app._gl_cancel = threading.Event()
    app._gl_running = getattr(app, "_gl_running", False)
    app._gl_planned = None

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._gl_block = block

    body = section(block, 0, 1, "Scenes", "the scenes CSV and the game's trailer files")
    app._path_row(0, "Scenes CSV", app._gl_csv_var, lambda: _browse_csv(app), parent=body,
                  placeholder_text="One row per shot: narration, shot, game_clip, game_at, real, left/right, title, place")
    app._path_row(1, "Trailers folder", app._gl_trailers_var, lambda: _browse_trailers(app), parent=body,
                  placeholder_text="The folder with the official trailer videos the CSV names")
    links = ctk.CTkFrame(body, fg_color="transparent")
    links.grid(row=2, column=0, sticky="w", pady=(4, 0))
    make_button(links, "Example CSV", lambda: _open_example(app), size="sm", width=120).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkLabel(body, text="Shots: game (trailer), real (real life), split (game | real with LEFT = RIGHT labels), title, chapter, "
                            "map (place = Name=Real@lat,lon, or all). Real footage is search words (fetched into the Visuals tab) "
                            "or a video file. Trailer shots never cross the trailer's own cuts; trailer audio is muted.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=3, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Voice and extras")
    app._path_row(0, "My voiceover (optional)", app._gl_vo_var, lambda: _browse_vo(app), parent=body,
                  placeholder_text="Your own mp3/wav of the whole script (or a Voiceover-tab clone): used instead of the voice below")
    opts = ctk.CTkFrame(body, fg_color="transparent")
    opts.grid(row=1, column=0, sticky="ew", pady=(6, 0))
    ctk.CTkLabel(opts, text="Voice", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8), sticky="w")
    ctk.CTkOptionMenu(opts, values=list(VOICES), variable=app._gl_voice_var, width=220).grid(row=0, column=1, sticky="w")
    ctk.CTkCheckBox(opts, text="Shorts (one per chapter, 9:16)", variable=app._gl_shorts_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ctk.CTkCheckBox(opts, text="Thumbnail (game | real)", variable=app._gl_thumb_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ctk.CTkLabel(opts, text="Thumbnail text", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=3, column=0, padx=(0, 8), pady=(8, 0), sticky="w")
    ctk.CTkEntry(opts, textvariable=app._gl_thumb_text_var, width=260, placeholder_text="e.g. IT'S REAL FLORIDA").grid(row=3, column=1, pady=(8, 0), sticky="w")
    ctk.CTkLabel(opts, text="Shorts footer", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=4, column=0, padx=(0, 8), pady=(6, 0), sticky="w")
    ctk.CTkEntry(opts, textvariable=app._gl_foot_var, width=260, placeholder_text="e.g. GTA 6 · NOV 19").grid(row=4, column=1, pady=(6, 0), sticky="w")

    body = section(block, 2, 3, "Generate, then Render", "Generate prepares the voice, trailer cuts and real clips; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._gl_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._gl_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._gl_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._gl_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._gl_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._gl_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._gl_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._gl_csv_var, app._gl_trailers_var, app._gl_vo_var, app._gl_voice_var, app._gl_shorts_var, app._gl_thumb_var,
              app._gl_thumb_text_var, app._gl_foot_var):
        v.trace_add("write", lambda *_a: _save(app))


# ---------------------------------------------------------------------------------------------------------------- remember

def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "game_launch" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_gl_restoring", False) or getattr(app, "_gl_csv_var", None) is None:
        return
    try:
        planned = getattr(app, "_gl_planned", None)
        data = {"active": bool(getattr(app, "_gl_active", False)), "csv": app._gl_csv_var.get(), "trailers": app._gl_trailers_var.get(),
                "voiceover": app._gl_vo_var.get(), "voice": app._gl_voice_var.get(), "shorts": bool(app._gl_shorts_var.get()), "thumb": bool(app._gl_thumb_var.get()),
                "thumb_text": app._gl_thumb_text_var.get(), "foot": app._gl_foot_var.get(),
                "planned": {**planned, "sig": _sig(planned["csv"])} if planned else None}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_gl_restored_for", None) or getattr(app, "_gl_running", False):
        return
    app._gl_restored_for = key
    app._gl_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._gl_restoring = True
    try:
        app._gl_csv_var.set(d.get("csv", "") or "")
        app._gl_trailers_var.set(d.get("trailers", "") or "")
        app._gl_vo_var.set(d.get("voiceover", "") or "")
        if d.get("voice") in VOICES:
            app._gl_voice_var.set(d["voice"])
        app._gl_shorts_var.set(bool(d.get("shorts", True)))
        app._gl_thumb_var.set(bool(d.get("thumb", True)))
        app._gl_thumb_text_var.set(d.get("thumb_text", "") or "")
        app._gl_foot_var.set(d.get("foot", "") or "")
        p = d.get("planned")
        if p and p.get("csv") and p.get("sig") is not None and _sig(p["csv"]) == p["sig"] and (Path(p.get("work", "")) / "game_launch_plan.json").is_file():
            app._gl_planned = {k: p.get(k) for k in ("csv", "trailers", "voice", "work")}
            app._gl_status_var.set("Restored: the scenes are prepared. Click Render, or Generate to prepare again.")
    finally:
        app._gl_restoring = False
    try:
        import visual_bridge

        visual_bridge.restore(app, OWNER)
    except Exception:  # noqa: BLE001
        pass


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse_csv(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose the scenes CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
    if path:
        app._gl_csv_var.set(path)          # remembered only: nothing is read until Generate
        app._gl_planned = None
        _save(app)
        _sync_buttons(app)


def _browse_vo(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose your voiceover of the whole script",
                                      filetypes=[("Audio", "*.mp3 *.wav *.m4a"), ("All files", "*.*")])
    if path:
        app._gl_vo_var.set(path)           # remembered only: it is cut into the CSV's lines on Generate
        app._gl_planned = None
        _save(app)
        _sync_buttons(app)


def _browse_trailers(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askdirectory(title="Choose the folder with the trailer videos")
    if path:
        app._gl_trailers_var.set(path)
        app._gl_planned = None
        _save(app)
        _sync_buttons(app)


def _open_example(app: Any) -> None:
    import subprocess

    f = _example_csv()

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(f)])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(f)])
        else:
            subprocess.Popen(["xdg-open", str(f.parent)])
    except Exception as exc:  # noqa: BLE001
        app._append_log(f"{TAG} Example CSV: {f} ({exc})\n")


# ---------------------------------------------------------------------------------------------------------------- page on / off

def activate(app: Any) -> None:
    if getattr(app, "_gl_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_gl_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._gl_active = True
    _restore(app)
    _save(app)
    app._gl_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_gl_active", False):
        app._gl_active = False
        if remember:
            _save(app)
        block = getattr(app, "_gl_block", None)
        if block is not None:
            block.grid_remove()
        try:
            import visual_bridge

            visual_bridge.clear(app, OWNER)
        except Exception:  # noqa: BLE001
            pass


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_gl_generate_btn", None) is None:
        return
    running = getattr(app, "_gl_running", False)
    app._gl_generate_btn.configure(state="disabled" if running else "normal")
    app._gl_render_btn.configure(state="normal" if (app._gl_planned and not running) else "disabled")
    app._gl_stop_btn.configure(state="normal" if running and not app._gl_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_gl_running", False):
        app._cta_action = "gl_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._gl_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._gl_planned:
        app._cta_action = "gl_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The scenes are ready (check the real clips in the Visuals tab). Click Render.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "gl_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose the scenes CSV and the trailers folder, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "gl_cancel":
        cancel(app)
    elif action == "gl_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_gl_running", False) or app._gl_cancel.is_set():
        return
    app._gl_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


# ---------------------------------------------------------------------------------------------------------------- jobs

def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "game_launch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        k = max(0.0, min(1.0, frac))
        app.ui_latest("style_progress", lambda: (app._gl_status_var.set(f"{int(k * 100)}%  {msg}".strip()), app.progress.set(k),
                              app._export_progress(k, msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._gl_cancel.clear()
    app._gl_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._gl_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._gl_running = False
            if error:
                app._gl_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._gl_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_gl_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    csv_path = app._gl_csv_var.get().strip()
    trailers = app._gl_trailers_var.get().strip()
    if not csv_path or not Path(csv_path).is_file():
        messagebox.showerror("Cannot start", "Choose the scenes CSV first." if not csv_path else f"The scenes CSV is not there: {csv_path}")
        return
    if not trailers or not Path(trailers).is_dir():
        messagebox.showerror("Cannot start", "Choose the folder with the trailer videos first.")
        return
    from game_launch import plan as GP
    from game_launch import runner as GR

    c = GR.check(csv_path, trailers)
    if c["errors"]:
        messagebox.showerror("The scenes CSV has problems", "\n".join(c["errors"][:12]))
        return
    voice = VOICES.get(app._gl_voice_var.get(), GR.DEFAULT_VOICE)
    vo = app._gl_vo_var.get().strip()
    if vo and not Path(vo).is_file():
        messagebox.showerror("Cannot start", f"Your voiceover file is not there: {vo}\nChoose it again, or clear the box to use a free voice.")
        return
    work = str(_work_dir(app) / "film")
    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, app._workspace)
    scenes = GP.visual_scenes(c["plan"])
    files = GP.local_files(c["plan"])
    manager = None
    if len(scenes) > len(files):                     # some real clips are search words: the app's stock sources fetch them
        try:
            from cinematic_explainer.war.app_section import war_manager

            manager = war_manager(app._build_asset_manager(images_dir, []))      # built here: it reads Tk variables; Gemini off
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Cannot start", f"The app's clip sources could not be set up:\n{exc}")
            return
    app._gl_planned = None
    _save(app)
    app._gl_status_var.set("Preparing…")
    app._append_log(f"{TAG} Generate: {c['lines']} lines, {c['shots']} shots, {c['real']} real clips\n")
    log = _log(app)

    def job():
        r = GR.prepare(csv_path, trailers, work, voice, log=log, cancel=app._gl_cancel.is_set, progress=_progress(app), voiceover=vo)
        for no, f in files.items():                  # the CSV's own clip files go in the Visuals tab as they are
            visual_bridge.seed(images_dir, str(no), f, "csv_file", stock=Path(f).stem)
        r["rows"], r["found"] = [], 0
        if scenes:
            from cinematic_explainer.war.app_section import fetch_csv_footage

            _s, rows = fetch_csv_footage(scenes, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
            if hasattr(app, "_ui_queue"):
                app.ui_call(lambda: visual_bridge.fill(app, OWNER, rows))
            if manager is not None:
                app._style_fetch_manager = manager
                try:
                    fetch_csv_footage(scenes, manager, images_dir, log, cancel=app._gl_cancel.is_set, ai_cap=0, fetch=True,
                                      director=False, library=False)
                finally:
                    app._style_fetch_manager = None
            got, rows = fetch_csv_footage(scenes, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
            r["rows"], r["found"] = rows, sum(1 for sc in got if sc.get("footage"))
        if app._gl_cancel.is_set():
            raise GR.Cancelled()
        return r

    def done(r) -> None:
        app._gl_planned = {"csv": csv_path, "trailers": trailers, "voice": voice, "work": work}
        notes = f" {len(r['warnings'])} note(s) in the log." if r.get("warnings") else ""
        for w in r.get("warnings") or []:
            app._append_log(f"{TAG} note: {w}\n")
        msg = (f"Prepared {r['shots']} shots over ~{r['seconds']:.0f} s ({r['splits']} side by side, {r['maps']} maps, "
               f"{r['chapters']} chapters). {r['found']} of {r['real']} real clips in the Visuals tab.{notes} Click Render.")
        app._gl_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        if r.get("rows"):
            visual_bridge.fill(app, OWNER, r["rows"])
        _save(app)

    _start(app, "game-launch-generate", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_gl_running", False):
        return
    ws, planned = app._workspace, app._gl_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the prepared scenes.")
        return
    if app._gl_csv_var.get().strip() != planned["csv"] or _sig(planned["csv"]) is None:
        messagebox.showinfo("Click Generate first", "The scenes CSV changed after Generate. Click Generate again, then Render.")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._gl_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("game_launch")
    shorts, thumb = bool(app._gl_shorts_var.get()), bool(app._gl_thumb_var.get())
    thumb_text, foot = app._gl_thumb_text_var.get().strip(), app._gl_foot_var.get().strip()

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._gl_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, ws)

    def job():
        from game_launch import plan as GP
        from game_launch import runner as GR

        data = GR.load(planned["work"]) or {}
        scenes = GP.visual_scenes(data.get("plan") or {"lines": []})
        found = {}
        if scenes:      # exactly what the Visuals tab holds now (Retry / Change source / Local clip included); nothing is fetched
            from cinematic_explainer.war.app_section import fetch_csv_footage

            got, _rows = fetch_csv_footage(scenes, None, images_dir, _log(app), fetch=False, ai_cap=0, director=False, library=False)
            found = {int(sc["scene_no"]): sc["footage"] for sc in got if sc.get("footage")}
        return GR.render(planned["work"], str(out_path), found, shorts=shorts, thumbnail=thumb, thumb_text=thumb_text,
                         short_foot=foot, progress=_progress(app), cancel=app._gl_cancel.is_set, log=_log(app))

    def done(r) -> None:
        extra = []
        if r.get("shorts"):
            extra.append(f"{len(r['shorts'])} Shorts")
        if r.get("thumbnail"):
            extra.append("a thumbnail")
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s)" + (f", plus {' and '.join(extra)} next to it." if extra else ".")
        app._gl_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "game-launch-render", job, done, end)
