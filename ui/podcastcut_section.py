"""Motivation (built on podcast_cut/): its own style page. An existing long podcast (a YouTube link or a local file) becomes a 30-38 min
"The Only N Minutes You Need To ..." motivation cut: the best line first as a hook, a "<channel> presents" card, the kept
talk in the order it was said, the speaker's camera alternating with dark mood stock, one-line captions, a watermark and a
quiet music bed. Optionally 9:16 Shorts of the best quotes.

Generate: download the audio once, transcribe, pick the clips (or read your clip CSV: then it IS the plan), check them, lay
out the film, and search the literal stock shots (shark, ice bath ...), listed in the Visuals tab for review / Retry /
Change source. Render: only the video sections the camera shots use are downloaded, then the film is drawn in parallel
pieces; the titles, chapters, thumbnail (and Shorts) are saved next to the mp4. Nothing starts until Generate. No Gemini.
All the work lives in podcast_cut/ (runner.py), imported only inside the button handlers.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_pc_block` / `_pc_running` /
`_pc_active`."""

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

STYLE = "Motivation"
TAG = "[MOTIVATION]"
OWNER = "podcast_cut"       # its literal stock rows in the Visuals tab (visual_bridge.OWNERS)


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._pc_source_var = ctk.StringVar(value="")
    app._pc_minutes_var = ctk.StringVar(value="35")
    app._pc_channel_var = ctk.StringVar(value="")
    app._pc_speaker_var = ctk.StringVar(value="")
    app._pc_clips_var = ctk.StringVar(value="")
    app._pc_captions_var = ctk.BooleanVar(value=False)
    app._pc_shorts_var = ctk.StringVar(value="0")
    app._pc_preview_var = ctk.BooleanVar(value=False)
    app._pc_status_var = ctk.StringVar(value="")
    app._pc_cancel = threading.Event()
    app._pc_running = getattr(app, "_pc_running", False)
    app._pc_planned = None   # {"source", "work", "clips"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._pc_block = block

    body = section(block, 0, 1, "Podcast", "a YouTube link or a video / audio file of the full episode")
    app._path_row(0, "Podcast", app._pc_source_var, lambda: _browse(app), parent=body,
                  placeholder_text="Paste a YouTube link, or Browse for a video / audio file")
    ctk.CTkLabel(body, text="The talk is cut to the length you ask for: ads, plugs and housekeeping left out, the strongest line "
                            "played first as a hook, the rest in the order it was said. The speaker's camera alternates with dark "
                            "mood b-roll (only the seconds that are used are downloaded).",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(
        row=1, column=0, sticky="w", pady=(4, 0))
    app._path_row(2, "Clip CSV", app._pc_clips_var, lambda: _browse_clips(app), parent=body,
                  placeholder_text="Optional: your own clip list (n, role, start, end, text). Then nothing is picked")

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    for col, (label, var, width) in enumerate((("Minutes", app._pc_minutes_var, 60), ("Channel", app._pc_channel_var, 170),
                                                ("Speaker", app._pc_speaker_var, 170))):
        ctk.CTkLabel(out, text=label, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=col * 2, padx=(0, 6))
        ctk.CTkEntry(out, textvariable=var, width=width,
                     placeholder_text="from the title" if label == "Speaker" else "").grid(row=0, column=col * 2 + 1, padx=(0, 14))
    opts = ctk.CTkFrame(body, fg_color="transparent")
    opts.grid(row=1, column=0, sticky="w", pady=(8, 0))
    ctk.CTkLabel(opts, text="Shorts", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 6))
    ctk.CTkOptionMenu(opts, values=["0", "1", "2", "3"], variable=app._pc_shorts_var, width=70).grid(row=0, column=1, padx=(0, 14))
    ctk.CTkCheckBox(opts, text="Fast transcript (YouTube captions)", variable=app._pc_captions_var).grid(row=0, column=2, padx=(0, 14))
    ctk.CTkCheckBox(opts, text="720p preview", variable=app._pc_preview_var).grid(row=0, column=3)

    body = section(block, 2, 3, "Generate, then Render", "Generate picks the clips and plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._pc_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT,
                                         hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
                                         font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._pc_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._pc_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT,
                                       hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
                                       font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._pc_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._pc_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._pc_stop_btn.grid(row=0, column=2, padx=(0, 10))
    make_button(go, "Open the clip list", lambda: _open_clips(app), size="sm", width=140).grid(row=0, column=3)
    ctk.CTkLabel(body, textvariable=app._pc_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 justify="left", wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._pc_source_var, app._pc_minutes_var, app._pc_channel_var, app._pc_speaker_var, app._pc_clips_var,
              app._pc_captions_var, app._pc_shorts_var, app._pc_preview_var):
        v.trace_add("write", lambda *_a: _save(app))


# ---------------------------------------------------------------------------------------------------------------- remember

def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "podcast_cut" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_pc_restoring", False) or getattr(app, "_pc_source_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_pc_active", False)), "source": app._pc_source_var.get(),
                "minutes": app._pc_minutes_var.get(), "channel": app._pc_channel_var.get(), "speaker": app._pc_speaker_var.get(),
                "clips": app._pc_clips_var.get(), "captions": bool(app._pc_captions_var.get()), "shorts": app._pc_shorts_var.get(),
                "preview": bool(app._pc_preview_var.get()), "planned": getattr(app, "_pc_planned", None)}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_pc_restored_for", None) or getattr(app, "_pc_running", False):
        return
    app._pc_restored_for = key
    app._pc_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._pc_restoring = True
    try:
        app._pc_source_var.set(d.get("source", "") or "")
        app._pc_minutes_var.set(str(d.get("minutes", "35") or "35"))
        app._pc_channel_var.set(d.get("channel", "") or "")
        app._pc_speaker_var.set(d.get("speaker", "") or "")
        app._pc_clips_var.set(d.get("clips", "") or "")
        app._pc_captions_var.set(bool(d.get("captions", False)))
        app._pc_shorts_var.set(str(d.get("shorts", "0") or "0"))
        app._pc_preview_var.set(bool(d.get("preview", False)))
        p = d.get("planned")
        if p and p.get("source") == app._pc_source_var.get() and (Path(str(p.get("work", ""))) / "film.json").is_file():
            app._pc_planned = p
            app._pc_status_var.set("Restored: the film is planned. Click Render, or Generate to plan again.")
    finally:
        app._pc_restoring = False
    try:
        import visual_bridge

        visual_bridge.restore(app, OWNER)
    except Exception:  # noqa: BLE001
        pass


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose the podcast episode",
                                      filetypes=[("Video / audio", "*.mp4 *.mkv *.webm *.mov *.m4v *.mp3 *.m4a *.wav *.aac *.flac *.ogg *.opus"),
                                                 ("All files", "*.*")])
    if path:
        app._pc_source_var.set(path)   # remembered only: nothing is read until Generate
        app._pc_planned = None
        _save(app)
        _sync_buttons(app)


def _browse_clips(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose the clip CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
    if path:
        app._pc_clips_var.set(path)
        app._pc_planned = None
        _save(app)
        _sync_buttons(app)


def _open_clips(app: Any) -> None:
    p = getattr(app, "_pc_planned", None)
    f = Path(p["work"]) / "clips.csv" if p else None
    if f is None or not f.is_file():
        app._pc_status_var.set("Generate first: the clip list is written then (edit it and pick it as Clip CSV to change the cut).")
        return
    import os
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(f)])
        elif os.name == "nt":
            os.startfile(str(f))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(f)])
    except Exception as exc:  # noqa: BLE001
        app._pc_status_var.set(f"Could not open {f}: {exc}")


# ---------------------------------------------------------------------------------------------------------------- page on / off

def activate(app: Any) -> None:
    if getattr(app, "_pc_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_pc_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._pc_active = True
    _restore(app)
    _save(app)
    app._pc_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_pc_active", False):
        app._pc_active = False
        if remember:
            _save(app)
        block = getattr(app, "_pc_block", None)
        if block is not None:
            block.grid_remove()
        try:
            import visual_bridge

            visual_bridge.clear(app, OWNER)
        except Exception:  # noqa: BLE001
            pass


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_pc_generate_btn", None) is None:
        return
    running = getattr(app, "_pc_running", False)
    app._pc_generate_btn.configure(state="disabled" if running else "normal")
    app._pc_render_btn.configure(state="normal" if (app._pc_planned and not running) else "disabled")
    app._pc_stop_btn.configure(state="normal" if running and not app._pc_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_pc_running", False):
        app._cta_action = "pc_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._pc_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._pc_planned:
        app._cta_action = "pc_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The film is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "pc_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Paste a podcast link or pick a file, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "pc_cancel":
        cancel(app)
    elif action == "pc_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_pc_running", False) or app._pc_cancel.is_set():
        return
    app._pc_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


# ---------------------------------------------------------------------------------------------------------------- jobs

def _work_root(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "podcast_cut"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        k = max(0.0, min(1.0, frac))
        app.ui_latest("style_progress", lambda: (app._pc_status_var.set(f"{int(k * 100)}%  {msg}".strip()), app.progress.set(k),
                              app._export_progress(k, msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._pc_cancel.clear()
    app._pc_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._pc_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._pc_running = False
            if error:
                app._pc_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._pc_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def _minutes(app: Any) -> float:
    try:
        return max(3.0, min(90.0, float(app._pc_minutes_var.get().strip() or 35)))
    except ValueError:
        return 35.0


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_pc_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    src = app._pc_source_var.get().strip()
    from podcast_cut import fetch as F

    if not src or (not F.is_url(src) and not Path(src).expanduser().is_file()):
        messagebox.showerror("Cannot start", "Paste a YouTube link or pick the podcast file first." if not src
                             else f"The podcast file is not there: {src}")
        return
    clips_csv = app._pc_clips_var.get().strip()
    if clips_csv and not Path(clips_csv).is_file():
        messagebox.showerror("Cannot start", f"The clip CSV is not there: {clips_csv}")
        return
    minutes, channel, speaker = _minutes(app), app._pc_channel_var.get().strip(), app._pc_speaker_var.get().strip()
    captions, shorts = bool(app._pc_captions_var.get()), int(app._pc_shorts_var.get() or 0)
    model = (app.model_var.get().strip() if hasattr(app, "model_var") else "") or "small"
    work = F.workdir_for(src, root=_work_root(app))
    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, app._workspace)
    try:
        from cinematic_explainer.war.app_section import war_manager

        manager = war_manager(app._build_asset_manager(images_dir, []))      # built here: it reads Tk variables; Gemini off
    except Exception as exc:  # noqa: BLE001 - the mood library stands in for every literal shot
        manager = None
        app._append_log(f"{TAG} The app's stock sources could not be set up ({exc}); literal shots use mood clips.\n")
    app._pc_planned = None
    _save(app)
    app._pc_status_var.set("Getting the podcast…")
    app._append_log(f"{TAG} Generate: {src}\n")
    log = _log(app)

    def job():
        from podcast_cut import runner as RN

        r = RN.plan(src, target_min=minutes, clip_csv=clips_csv or None, captions=captions, model_size=model, workdir=work,
                    channel=channel, speaker=speaker, shorts=shorts, log=log, cancel=app._pc_cancel.is_set)
        if not r["ok"]:
            raise RuntimeError("The clip plan has errors: " + "; ".join(r["errors"][:3]) + f" (see {r['report']})")
        rows_found = 0
        cs = r["rows"]
        if cs and manager is not None:
            from cinematic_explainer.war.app_section import fetch_csv_footage

            M = sys.modules[type(app).__module__]
            live = hasattr(app, "_ui_queue")

            def on_start(scene, source):
                app._ui_queue.put(("scene_busy", (scene.scene_number, M._scene_busy_kind(source))))

            def on_done(scene, result):
                app._ui_queue.put(("scene_asset", (scene.scene_number, result)))

            _s, rows = fetch_csv_footage(cs, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
            if live:
                app.ui_call(lambda: visual_bridge.fill(app, OWNER, rows))
            app._style_fetch_manager = manager
            try:
                fetch_csv_footage(cs, manager, images_dir, log, cancel=app._pc_cancel.is_set, ai_cap=0, fetch=True,
                                  on_start=on_start if live else None, on_done=on_done if live else None,
                                  director=False, library=False)
            finally:
                app._style_fetch_manager = None
            got, rows = fetch_csv_footage(cs, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
            r["tab_rows"], rows_found = rows, sum(1 for sc in got if sc.get("footage"))
        r["rows_found"] = rows_found
        if app._pc_cancel.is_set():
            raise RN.Stopped("stopped")
        return r

    def done(r) -> None:
        film = r["film"] or {}
        app._pc_planned = {"source": src, "work": str(r["workdir"]), "clips": clips_csv}
        msg = (f"Planned a {r['length'] / 60:.1f} min cut in {len(r['clips'])} clips; {len(film.get('shots', []))} shots, camera "
               f"{film.get('camera_share', 0) * 100:.0f}% of the time. {r.get('rows_found', 0)} of {len(r['rows'])} literal stock "
               f"shots found (check them in the Visuals tab). Click Render.")
        if r["warnings"]:
            msg += f" {len(r['warnings'])} warning(s) in plan_report.txt."
        app._pc_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        if r.get("tab_rows"):
            visual_bridge.fill(app, OWNER, r["tab_rows"])
            try:
                app._goto_workflow_view("visual_plan")
            except Exception:  # noqa: BLE001
                pass
        _save(app)

    _start(app, "podcast-generate", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_pc_running", False):
        return
    ws, plan = app._workspace, app._pc_planned
    if ws is None or not plan:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned film.")
        return
    if app._pc_source_var.get().strip() != plan["source"]:
        messagebox.showinfo("Click Generate first", "You changed the podcast after Generate. Click Generate again, then Render.")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._pc_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("podcast_cut")
    preview, shorts = bool(app._pc_preview_var.get()), int(app._pc_shorts_var.get() or 0) > 0
    channel = app._pc_channel_var.get().strip()

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._pc_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, ws)

    def job():
        from podcast_cut import runner as RN

        film = RN.load_film(Path(plan["work"])) or {}
        found = {}
        if film.get("rows"):   # exactly what the Visuals tab holds now; nothing is fetched here
            from cinematic_explainer.war.app_section import fetch_csv_footage

            got, _rows = fetch_csv_footage(film["rows"], None, images_dir, _log(app), fetch=False, ai_cap=0, director=False,
                                           library=False)
            found = {int(sc["scene_no"]): sc["footage"] for sc in got if sc.get("footage")}
        return RN.render(Path(plan["work"]), Path(out_path), channel=channel, preview=preview, found=found, shorts=shorts,
                         progress=_progress(app), cancel=app._pc_cancel.is_set, log=_log(app))

    def done(r) -> None:
        extra = f" + {len(r['shorts'])} Short(s)" if r.get("shorts") else ""
        msg = (f"Done: {Path(out_path).name} ({r['seconds'] / 60:.1f} min){extra}. Titles, chapters and the thumbnail are saved "
               f"next to it. Suggested title: {r['titles'][0] if r.get('titles') else ''}")
        app._pc_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "podcast-render", job, done, end)
