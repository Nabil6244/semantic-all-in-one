"""City Timelapse: its own style page (a story CSV, music, optional voice-over, resolution) with a Generate step that checks and
plans the film and a Render step that renders it (a low-poly city growing over centuries on real ground, music bed, -14 LUFS).
All the work lives in citygrow-engine/ (runner.py), imported only inside the button handlers. Nothing starts until Generate:
picking files or options only remembers them. The one download (elevation tiles and OpenStreetMap water and streets for a city
that has no world yet) is shown with its size and only happens after the user agrees. No Gemini, no paid API.

Each project remembers this page (state/city_timelapse/settings.json): reopening it comes back on the page with its files and
options and, if the story did not change, its planned film, so Render is ready.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_ct_block` / `_ct_running` / `_ct_active`."""

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

STYLE = "City Timelapse"
TAG = "[CITY TIMELAPSE]"
RESOLUTIONS = {"1080p final (1920x1080)": 1080, "720p preview (1280x720)": 720}
MUSIC = {"From the story (default: Ascending the Vale)": None, "Ascending the Vale": "ascending_the_vale", "Echoes of Time": "echoes_of_time_v2",
         "Despair and Triumph": "despair_and_triumph", "Lost Frontier": "lost_frontier", "Long Note Four": "long_note_four",
         "Dark Fog": "dark_fog", "Interloper": "interloper", "Stormfront": "stormfront"}
_ROOT = Path(__file__).resolve().parent.parent


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "citygrow-engine"


def _runner():
    """citygrow-engine/runner.py (a folder name Python cannot import), loaded once; None with a message when it is missing."""
    mod = sys.modules.get("ctl_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("ctl_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["ctl_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("ctl_runner", None)
        messagebox.showerror("City Timelapse is not installed", f"The citygrow-engine folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._ct_csv_var = ctk.StringVar(value="")
    app._ct_voice_var = ctk.StringVar(value="")
    app._ct_music_var = ctk.StringVar(value=next(iter(MUSIC)))
    app._ct_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._ct_status_var = ctk.StringVar(value="")
    app._ct_cancel = threading.Event()
    app._ct_running = getattr(app, "_ct_running", False)
    app._ct_planned = None   # {"csv", "voice", "music", "res", "work"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._ct_block = block

    body = section(block, 0, 1, "Story", "a story CSV (plan / era / district / landmark / event rows)")
    app._path_row(0, "Story CSV", app._ct_csv_var, lambda: _browse(app, "csv"), parent=body,
                  placeholder_text="Choose the story CSV (format: citygrow-engine/tools/story_prompt.md)")
    app._path_row(1, "Voice-over", app._ct_voice_var, lambda: _browse(app, "voice"), parent=body,
                  placeholder_text="Optional. The format is music only; a voice-over is laid on top with the music ducking under it.")
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=3, column=0, sticky="w", pady=(6, 0))
    app._ct_prompt_status = ctk.StringVar(value="")
    make_button(tools, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="sm", width=150).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._ct_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(body, text="A low-poly 3D city growing over the centuries on its real ground and water. Samples: citygrow-engine/samples/. "
                            "A city's first Generate builds its world once (elevation + OpenStreetMap streets and water): it shows the size and asks first.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Music", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(MUSIC), variable=app._ct_music_var, width=280).grid(row=0, column=1, padx=(0, 16))
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=2, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._ct_res_var, width=220).grid(row=0, column=3)

    body = section(block, 2, 3, "Generate, then Render", "Generate checks and plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._ct_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._ct_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._ct_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._ct_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._ct_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._ct_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._ct_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._ct_csv_var, app._ct_voice_var, app._ct_music_var, app._ct_res_var):
        v.trace_add("write", lambda *_a: _save(app))


def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "city_timelapse" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_ct_restoring", False) or getattr(app, "_ct_csv_var", None) is None:
        return
    try:
        planned = getattr(app, "_ct_planned", None)
        data = {"active": bool(getattr(app, "_ct_active", False)), "csv": app._ct_csv_var.get(), "voice": app._ct_voice_var.get(),
                "music_label": app._ct_music_var.get(), "res_label": app._ct_res_var.get(), "planned": None}
        if planned:
            data["planned"] = {**planned, "sig_csv": _sig(planned["csv"])}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    """Put back this project's choices and, if its story did not change, its planned film. Starts nothing."""
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_ct_restored_for", None) or getattr(app, "_ct_running", False):
        return
    app._ct_restored_for = key
    app._ct_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._ct_restoring = True
    try:
        app._ct_csv_var.set(d.get("csv", "") or "")
        app._ct_voice_var.set(d.get("voice", "") or "")
        if d.get("music_label") in MUSIC:
            app._ct_music_var.set(d["music_label"])
        if d.get("res_label") in RESOLUTIONS:
            app._ct_res_var.set(d["res_label"])
        p = d.get("planned")
        if p and p.get("csv") and (Path(str(p.get("work", ""))) / "timeline.json").is_file():
            if p.get("sig_csv") is not None and _sig(p["csv"]) == p["sig_csv"]:
                app._ct_planned = {k: p.get(k) for k in ("csv", "voice", "music", "res", "work")}
                app._ct_status_var.set("Restored: the film is planned. Click Render, or Generate to plan again.")
    finally:
        app._ct_restoring = False


def resume_on_open(app: Any) -> None:
    """A project that was left on this page opens on it again."""
    if _read_settings(app).get("active"):
        app.after(0, lambda: app._on_style_pick(STYLE))


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    if kind == "csv":
        path = filedialog.askopenfilename(title="Choose the story CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._ct_csv_var
    else:
        path = filedialog.askopenfilename(title="Choose the voice-over", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._ct_voice_var
    if path:
        var.set(path)   # remembered only: nothing is read or planned until Generate
        app._ct_planned = None
        _save(app)
        _sync_buttons(app)


def copy_csv_prompt(app: Any) -> None:
    """Put the story-CSV writing prompt on the clipboard (paste it into any AI chat with your city)."""
    p = _engine_dir() / "tools" / "story_prompt.md"
    status = app._ct_prompt_status
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        status.set(f"The CSV prompt is not there yet ({p.name}).")
        return
    try:
        app.clipboard_clear()
        app.clipboard_append(text)
        status.set("Copied. Paste it into your AI chat with your city.")
    except Exception as exc:  # noqa: BLE001
        status.set(f"Could not copy: {exc}")


def activate(app: Any) -> None:
    if getattr(app, "_ct_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_ct_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._ct_active = True
    _restore(app)
    _save(app)
    app._ct_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    """remember=False when a project is opening: the page was not left by choice, and the settings on disk may be another project's."""
    if getattr(app, "_ct_active", False):
        app._ct_active = False
        if remember:
            _save(app)
        block = getattr(app, "_ct_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_ct_generate_btn", None) is None:
        return
    running = getattr(app, "_ct_running", False)
    app._ct_generate_btn.configure(state="disabled" if running else "normal")
    app._ct_render_btn.configure(state="normal" if (app._ct_planned and not running) else "disabled")
    app._ct_stop_btn.configure(state="normal" if running and not app._ct_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_ct_running", False):
        app._cta_action = "ct_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._ct_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._ct_planned:
        app._cta_action = "ct_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The film is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "ct_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a story CSV, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "ct_cancel":
        cancel(app)
    elif action == "ct_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_ct_running", False) or app._ct_cancel.is_set():
        return
    app._ct_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "city_timelapse"
    d.mkdir(parents=True, exist_ok=True)
    return d


def options(app: Any) -> dict:
    return {"csv": app._ct_csv_var.get().strip(), "voice": app._ct_voice_var.get().strip(), "music": MUSIC.get(app._ct_music_var.get()),
            "res": RESOLUTIONS.get(app._ct_res_var.get(), 1080)}


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.after(0, lambda: (app._ct_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.after(0, lambda: app._append_log(m + "\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._ct_cancel.clear()
    app._ct_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._ct_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._ct_running = False
            if error:
                app._ct_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._ct_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ct_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    o = options(app)
    if not o["csv"] or not Path(o["csv"]).is_file():
        messagebox.showerror("Cannot start", "Choose the story CSV first." if not o["csv"] else f"The story CSV is not there: {o['csv']}")
        return
    if o["voice"] and not Path(o["voice"]).is_file():
        messagebox.showerror("Cannot start", f"The voice-over is not there: {o['voice']}")
        return
    ct = _runner()
    if ct is None:
        return
    work = str(_work_dir(app) / "film")
    app._ct_planned = None
    _save(app)
    app._ct_status_var.set("Checking the story…")
    app._append_log(f"{TAG} Generate: checking the story\n")

    def job():
        c = ct.check(o["csv"], cancel=app._ct_cancel.is_set, log=_log(app))
        if c["errors"]:
            raise ValueError("The story has errors:\n" + "\n".join(c["errors"][:8]))
        return c

    def after_check(c) -> None:
        wb = c.get("world_build")
        if wb:      # the city has no world yet: build it once (one download), then check again
            if not messagebox.askyesno("Build the city's world?", f"The story's city \"{wb['id']}\" has no world yet.\n\n"
                                       f"Build it now: {wb['size']:.0f} km square around {wb['center'][1]:.4f}, {wb['center'][0]:.4f}? "
                                       f"About {wb.get('download_mb_est', 0)} MB of elevation data plus OpenStreetMap streets and water, downloaded once; "
                                       "every later story of this city reuses it."):
                app._ct_status_var.set(f"Not started: the world \"{wb['id']}\" is not built.")
                return
            app._ct_status_var.set(f"Building the world \"{wb['id']}\"…")
            _start(app, "city-timelapse-world", lambda: (ct.build_world(wb, progress=_progress(app), cancel=app._ct_cancel.is_set, log=_log(app)), job())[1],
                   after_check)
            return
        _plan(app, ct, o, work)

    _start(app, "city-timelapse-check", job, after_check)


def _plan(app: Any, ct: Any, o: dict, work: str) -> None:
    app._ct_status_var.set("Planning…")

    def job():
        return ct.plan(o["csv"], work, progress=_progress(app), cancel=app._ct_cancel.is_set, log=_log(app))

    def done(r) -> None:
        app._ct_planned = {"csv": o["csv"], "voice": o["voice"], "music": o["music"], "res": o["res"], "work": work}
        warn = f"  {len(r['warnings'])} notes (see the log)." if r["warnings"] else ""
        msg = f"Planned {r['eras']} eras, {r['duration']:.0f} s, {r['lots']:,} house lots, {r['landmarks']} landmarks.{warn} Click Render."
        app._ct_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "city-timelapse-plan", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ct_running", False):
        return
    ws, plan = app._workspace, app._ct_planned
    if ws is None or not plan:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned film.")
        return
    ct = _runner()
    if ct is None:
        return
    o = options(app)
    if (o["csv"], o["voice"]) != (plan["csv"], plan["voice"]):
        messagebox.showinfo("Click Generate first", "You changed the story or voice-over after Generate. Click Generate again, then Render.")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._ct_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("city_timelapse")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._ct_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return ct.render(plan["csv"], plan["work"], output=str(out_path), resolution=o["res"], voiceover=plan["voice"] or None,
                         music=o["music"], progress=_progress(app), cancel=app._ct_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s). Credits saved next to it."
        app._ct_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "city-timelapse-render", job, done, end)
