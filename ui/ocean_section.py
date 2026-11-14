"""Ocean Predators: its own style page (a voice-over and a channel name) with a Generate step that reads the narration and
plans the film, and a Render step that renders it: flat 2D sea animals acting each sentence in one moving underwater
world, number / study / joke cards, orange keyword captions, pops and whooshes and a music bed under the voice (-14 LUFS),
and (optional, on by default) a short real clip about every 40 s, graded into the blue world with a credit line. The clips
are searched through the app's own stock sources at Generate and listed in the Visuals tab (review / Retry / Change source);
Render uses exactly what the tab holds and fetches nothing. All the work lives in ocean/ (runner.py, clips.py), imported only
inside the button handlers. Nothing starts until Generate: picking files or options only remembers them. No Flow, no Gemini.

Each project remembers this page (state/ocean/settings.json): reopening it comes back on the page with its choices and, if
the voice-over did not change, its planned film, so Render is ready.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_oc_block` / `_oc_running` /
`_oc_active`."""

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

STYLE = "Ocean Predators"
TAG = "[OCEAN]"
OWNER = "ocean"             # its real-clip rows in the Visuals tab (visual_bridge.OWNERS)


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._oc_voice_var = ctk.StringVar(value="")
    app._oc_channel_var = ctk.StringVar(value="Ocean")
    app._oc_clips_var = ctk.BooleanVar(value=True)
    app._oc_status_var = ctk.StringVar(value="")
    app._oc_cancel = threading.Event()
    app._oc_running = getattr(app, "_oc_running", False)
    app._oc_planned = None   # {"voice", "channel", "work"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._oc_block = block

    body = section(block, 0, 1, "Voice-over", "the narration the film is planned from")
    app._path_row(0, "Voice-over", app._oc_voice_var, lambda: _browse(app), parent=body,
                  placeholder_text="Optional: empty uses this project's voice-over")
    ctk.CTkLabel(body, text="Flat 2D sea animals act every sentence in one moving underwater world: the animals you name swim in, "
                            "numbers become cards, studies a paper card, 'what would you do' the diver's view, with orange keyword "
                            "captions. Works best with second-person, list-style narration ('Picture this. You're…', 'The first one is…').",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(
        row=1, column=0, sticky="w", pady=(4, 0))
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=2, column=0, sticky="w", pady=(6, 0))
    app._oc_prompt_status = ctk.StringVar(value="")
    make_button(tools, "Copy the script prompt", lambda: copy_script_prompt(app), size="sm", width=170).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._oc_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(
        row=0, column=1, sticky="w")

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Channel name (end card)", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkEntry(out, textvariable=app._oc_channel_var, width=220).grid(row=0, column=1, padx=(0, 16))
    ctk.CTkCheckBox(out, text="Real clips (stock, credited; checked in the Visuals tab)", variable=app._oc_clips_var).grid(
        row=0, column=2)

    body = section(block, 2, 3, "Generate, then Render", "Generate reads the voice-over and plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._oc_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT,
                                         hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
                                         font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._oc_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._oc_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT,
                                       hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
                                       font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._oc_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._oc_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._oc_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._oc_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 justify="left", wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._oc_voice_var, app._oc_channel_var, app._oc_clips_var):
        v.trace_add("write", lambda *_a: _save(app))


# ---------------------------------------------------------------------------------------------------------------- remember

def _make_missing_art(app: Any, plan: Optional[dict], log) -> tuple:
    """Painted pictures for animals this script names that the shared library lacks (ocean/art_flow.py): made once with
    Flow, kept in assets/ocean/art/ for every later video. A failure never stops Generate: that animal keeps its code
    drawing. Returns (made, still missing)."""
    from ocean import art_flow as AF

    need = AF.needs_for_plan(plan)
    if not need:
        return 0, 0
    log(f"{len(need)} animal picture(s) not in the library yet: " + ", ".join(f"{n.replace('_', ' ')} ({p})" for n, p in need)
        + ". Making them once with Flow (free images); every later video reuses them.")
    try:
        mgr = app._get_flow_engine_manager() if hasattr(app, "_get_flow_engine_manager") else None
        res = AF.generate(need, log=log, manager=mgr, should_stop=app._oc_cancel.is_set)
    except Exception as exc:  # noqa: BLE001 - the code drawing stands in
        log(f"Flow could not make the animal pictures ({exc}); those animals use the backup drawing this time.")
        return 0, len(need)
    made = sum(1 for x in res if x.get("status") == "made")
    from ocean import animals as A
    A._draw_cached.cache_clear()
    return made, len(need) - made


def copy_script_prompt(app: Any) -> None:
    """The narration prompt (ocean/script_prompt.md): the channel's script shape, to paste into an AI chat with a topic."""
    p = Path(__file__).resolve().parent.parent / "ocean" / "script_prompt.md"
    try:
        text = p.read_text(encoding="utf-8")
        app.clipboard_clear()
        app.clipboard_append(text)
        app._oc_prompt_status.set("Copied. Paste it into your AI chat, put your topic in, then voice the script.")
    except Exception as exc:  # noqa: BLE001
        app._oc_prompt_status.set(f"Could not copy: {exc}")


def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "ocean" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_oc_restoring", False) or getattr(app, "_oc_voice_var", None) is None:
        return
    try:
        planned = getattr(app, "_oc_planned", None)
        data = {"active": bool(getattr(app, "_oc_active", False)), "voice": app._oc_voice_var.get(),
                "channel": app._oc_channel_var.get(), "clips": bool(app._oc_clips_var.get()), "planned": None}
        if planned:
            data["planned"] = {**planned, "sig_voice": _sig(planned["voice"])}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    """Put back this project's choices and, if its voice-over did not change, its planned film. Starts nothing."""
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_oc_restored_for", None) or getattr(app, "_oc_running", False):
        return
    app._oc_restored_for = key
    app._oc_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._oc_restoring = True
    try:
        app._oc_voice_var.set(d.get("voice", "") or "")
        app._oc_channel_var.set(d.get("channel", "") or "Ocean")
        app._oc_clips_var.set(bool(d.get("clips", True)))
        p = d.get("planned")
        if p and p.get("voice") and (Path(str(p.get("work", ""))) / "plan.json").is_file():
            if p.get("sig_voice") is not None and _sig(p["voice"]) == p["sig_voice"]:
                app._oc_planned = {k: p.get(k) for k in ("voice", "channel", "work")}
                app._oc_status_var.set("Restored: the film is planned. Click Render, or Generate to plan again.")
    finally:
        app._oc_restoring = False
    try:
        import visual_bridge

        visual_bridge.restore(app, OWNER)      # this project's clip rows back in the Visuals tab
    except Exception:  # noqa: BLE001
        pass


def resume_on_open(app: Any) -> None:
    """A project that was left on this page opens on it again."""
    if _read_settings(app).get("active"):
        app.after(0, lambda: app._on_style_pick(STYLE))


def _browse(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose the voice-over",
                                      filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
    if path:
        app._oc_voice_var.set(path)   # remembered only: nothing is read or planned until Generate
        app._oc_planned = None
        _save(app)
        _sync_buttons(app)


# ---------------------------------------------------------------------------------------------------------------- page on / off

def activate(app: Any) -> None:
    if getattr(app, "_oc_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_oc_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._oc_active = True
    _restore(app)
    _save(app)
    app._oc_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    """remember=False when a project is opening: the page was not left by choice, and the settings may be another project's."""
    if getattr(app, "_oc_active", False):
        app._oc_active = False
        if remember:
            _save(app)
        block = getattr(app, "_oc_block", None)
        if block is not None:
            block.grid_remove()
        try:
            import visual_bridge

            visual_bridge.clear(app, OWNER)
        except Exception:  # noqa: BLE001
            pass


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_oc_generate_btn", None) is None:
        return
    running = getattr(app, "_oc_running", False)
    app._oc_generate_btn.configure(state="disabled" if running else "normal")
    app._oc_render_btn.configure(state="normal" if (app._oc_planned and not running) else "disabled")
    app._oc_stop_btn.configure(state="normal" if running and not app._oc_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_oc_running", False):
        app._cta_action = "oc_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._oc_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._oc_planned:
        app._cta_action = "oc_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The film is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "oc_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Add the voice-over, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "oc_cancel":
        cancel(app)
    elif action == "oc_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_oc_running", False) or app._oc_cancel.is_set():
        return
    app._oc_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


# ---------------------------------------------------------------------------------------------------------------- jobs

def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "ocean"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _voice(app: Any) -> str:
    v = app._oc_voice_var.get().strip()
    if not v:
        cur = app._current_voiceover_path()
        v = str(cur) if cur else ""
    return v


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        k = max(0.0, min(1.0, frac))
        app.after(0, lambda: (app._oc_status_var.set(f"{int(k * 100)}%  {msg}".strip()), app.progress.set(k),
                              app._export_progress(k, msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.after(0, lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._oc_cancel.clear()
    app._oc_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._oc_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._oc_running = False
            if error:
                app._oc_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._oc_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_oc_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    voice = _voice(app)
    if not voice or not Path(voice).is_file():
        messagebox.showerror("Cannot start", "Add the voice-over first." if not voice else f"The voice-over is not there: {voice}")
        return
    channel = app._oc_channel_var.get().strip() or "Ocean"
    want_clips = bool(app._oc_clips_var.get())
    work = str(_work_dir(app) / "film")
    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, app._workspace)
    manager = None
    if want_clips:
        try:
            from cinematic_explainer.war.app_section import war_manager

            manager = war_manager(app._build_asset_manager(images_dir, []))      # built here: it reads Tk variables; Gemini off
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Cannot start", f"The app's clip sources could not be set up:\n{exc}\n\n"
                                                 "Untick 'Real clips' to make the film from drawings only.")
            return
    app._oc_planned = None
    _save(app)
    app._oc_status_var.set("Reading the voice-over…")
    app._append_log(f"{TAG} Generate: reading the voice-over\n")
    log = _log(app)

    def job():
        from ocean import runner as RN

        ws = app._workspace
        words = app._pakmap_get_words(Path(voice), app.model_var.get().strip() or "base", getattr(ws, "state_dir", None), log)
        if app._oc_cancel.is_set():
            raise RN.Cancelled()
        try:
            from pakmap.app_integration import voiceover_duration

            total = float(voiceover_duration(voice) or 0.0)
        except Exception:  # noqa: BLE001
            total = 0.0
        scenes = RN.scenes_from_words(words, total)
        log(f"{len(scenes)} sentences from the voice-over")
        r = RN.plan_film(scenes, work, channel, log, real_clips=want_clips)
        r["rows"], r["found"] = [], 0
        r["art_made"], r["art_missing"] = _make_missing_art(app, RN.load_plan(work), log)
        cs = RN.clip_scenes(RN.load_plan(work)) if want_clips else []
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
                app.after(0, lambda: visual_bridge.fill(app, OWNER, rows))   # every slot is listed before the first download
            app._style_fetch_manager = manager
            try:
                fetch_csv_footage(cs, manager, images_dir, log, cancel=app._oc_cancel.is_set, ai_cap=0, fetch=True,
                                  on_start=on_start if live else None, on_done=on_done if live else None,
                                  director=False, library=False)
            finally:
                app._style_fetch_manager = None
            got, rows = fetch_csv_footage(cs, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
            r["rows"], r["found"] = rows, sum(1 for sc in got if sc.get("footage"))
        if app._oc_cancel.is_set():
            raise RN.Cancelled()
        return r

    def done(r) -> None:
        app._oc_planned = {"voice": voice, "channel": channel, "work": work}
        clips = f" {r['found']} of {r['clips']} real clips found (check them in the Visuals tab)." if r.get("clips") else ""
        art = ""
        if r.get("art_made") or r.get("art_missing"):
            art = f" {r.get('art_made', 0)} new animal picture(s) made with Flow" + (
                f", {r['art_missing']} not made (backup drawing used)" if r.get("art_missing") else "") + "."
        msg = (f"Planned {r['shots']} shots over {r['duration']:.0f} s: {r['cards']} cards, {r['captions']} captions, "
               f"{r['chapters']} chapters, {r['species']} animals.{art}{clips} Click Render.")
        app._oc_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        if r.get("rows"):
            visual_bridge.fill(app, OWNER, r["rows"])
            try:
                app._goto_workflow_view("visual_plan")
            except Exception:  # noqa: BLE001
                pass
        _save(app)

    _start(app, "ocean-generate", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_oc_running", False):
        return
    ws, plan = app._workspace, app._oc_planned
    if ws is None or not plan:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned film.")
        return
    if _voice(app) != plan["voice"]:
        messagebox.showinfo("Click Generate first", "You changed the voice-over after Generate. Click Generate again, then Render.")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._oc_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("ocean")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._oc_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, ws)

    def job():
        from ocean import runner as RN

        found = {}
        cs = RN.clip_scenes(RN.load_plan(plan["work"]))
        if cs:      # exactly what the Visuals tab holds now (the user's Retry / Change source / Local clip included); nothing is fetched
            from cinematic_explainer.war.app_section import fetch_csv_footage

            got, _rows = fetch_csv_footage(cs, None, images_dir, _log(app), fetch=False, ai_cap=0, director=False, library=False)
            found = {str(sc["scene_no"]): {"path": sc["footage"], "meta": sc.get("footage_meta")} for sc in got if sc.get("footage")}
        return RN.render_film(plan["work"], plan["voice"], str(out_path), found=found, progress=_progress(app),
                              cancel=app._oc_cancel.is_set, log=_log(app))

    def done(r) -> None:
        clips = f", {r['clips']} real clips" if r.get("clips") else ""
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s{clips}). Chapter list and credits saved next to it."
        app._oc_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "ocean-render", job, done, end)
