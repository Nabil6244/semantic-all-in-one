"""Aviation: its own style page (voice-over, optional aviation scenes CSV) - airline business stories and flight reconstructions in one
look chosen per sentence from the narration (docs/aviation/PLAN.md). All the work lives in aviation/ (runner.py, planner.py ...),
imported only inside the button handlers.

Flow (like War Documentary): Generate scenes reads the narration (the CSV's rows aligned to the voice-over, or the voice-over's own
sentences), plans the film, fetches the footage the plan needs through the app's AssetManager into the Visuals tab (no Gemini: the CSV
or the narration's own names are the searches) and downloads the map terrain once. Render uses exactly what the Visuals tab holds and
reports to the Export page. Nothing starts until Generate: picking files only remembers them.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_av_block` / `_av_running` / `_av_active`."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, List, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Aviation"
TAG = "[AVIATION]"
OWNER = "aviation"          # its footage rows in the Visuals tab (visual_bridge.OWNERS)


def _m(app: Any):
    return sys.modules[type(app).__module__]


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._av_csv_var = ctk.StringVar(value="")
    app._av_voice_var = ctk.StringVar(value="")
    app._av_status_var = ctk.StringVar(value="")
    app._av_cancel = threading.Event()
    app._av_running = getattr(app, "_av_running", False)
    app._av_ready = None   # {"csv", "voice", "scenes_file"} of the last Generate scenes

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._av_block = block

    body = section(block, 0, 1, "Narration", "your voice-over, and optionally the aviation scenes CSV")
    app._path_row(0, "Voice-over", app._av_voice_var, lambda: _browse(app, "voice"), parent=body,
                  placeholder_text="The narration (mp3 / wav / m4a). Its words decide each scene's look.")
    app._path_row(1, "Scenes CSV", app._av_csv_var, lambda: _browse(app, "csv"), parent=body,
                  placeholder_text="Optional. Without it the scenes come from the voice-over's own sentences.")
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=3, column=0, sticky="w", pady=(6, 0))
    app._av_prompt_status = ctk.StringVar(value="")
    make_button(tools, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="sm", width=150).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._av_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(body, text="Business and news lines get fast real clips and blue article cards; flight, route and weather lines get the dark "
                            "flight map with the route, holds, storms and the fuel / clock display; aircraft lines get slow beauty shots.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Generate scenes, then Render", "Generate scenes fetches the footage into the Visuals tab; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._av_generate_btn = ctk.CTkButton(go, text="Generate scenes", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._av_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._av_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._av_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._av_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._av_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._av_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._av_csv_var, app._av_voice_var):
        v.trace_add("write", lambda *_a: _save(app))


# ---------------------------------------------------------------------------------------------------------------- remembering

def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "aviation" if ws is not None else None


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d is not None else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    d = _state_dir(app)
    if d is None or getattr(app, "_av_restoring", False) or getattr(app, "_av_csv_var", None) is None:
        return
    try:
        ready = getattr(app, "_av_ready", None)
        data = {"active": bool(getattr(app, "_av_active", False)), "csv": app._av_csv_var.get(), "voice": app._av_voice_var.get(), "ready": None}
        if ready:
            data["ready"] = {**ready, "sig_csv": _sig(ready["csv"]) if ready.get("csv") else None, "sig_voice": _sig(ready["voice"])}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_av_restored_for", None) or getattr(app, "_av_running", False):
        return
    app._av_restored_for = key
    app._av_ready = None
    d = _read_settings(app)
    if not d:
        return
    app._av_restoring = True
    try:
        app._av_csv_var.set(d.get("csv", "") or "")
        app._av_voice_var.set(d.get("voice", "") or "")
        r = d.get("ready")
        if r and r.get("voice") and Path(str(r.get("scenes_file", ""))).is_file() and _sig(r["voice"]) == r.get("sig_voice") and \
                (not r.get("csv") or _sig(r["csv"]) == r.get("sig_csv")):
            app._av_ready = {k: r.get(k) for k in ("csv", "voice", "scenes_file")}
            app._av_status_var.set("Restored: scenes are ready. Check the Visuals tab, then click Render.")
    finally:
        app._av_restoring = False
    try:
        import visual_bridge

        visual_bridge.restore(app, OWNER)      # this project's footage rows back in the Visuals tab
    except Exception:  # noqa: BLE001
        pass


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.after(0, lambda: app._on_style_pick(STYLE))


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    if kind == "csv":
        path = filedialog.askopenfilename(title="Choose the aviation scenes CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._av_csv_var
    else:
        path = filedialog.askopenfilename(title="Choose the voice-over", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._av_voice_var
    if path:
        var.set(path)   # remembered only: nothing is read, transcribed or planned until Generate scenes
        app._av_ready = None
        _save(app)
        _sync_buttons(app)


def copy_csv_prompt(app: Any) -> None:
    from aviation import csv_rows

    try:
        text = csv_rows.prompt_text()
        app.clipboard_clear()
        app.clipboard_append(text)
        app._av_prompt_status.set("Copied. Paste it into your AI chat, then paste your script after 'SCRIPT:'.")
    except Exception as exc:  # noqa: BLE001
        app._av_prompt_status.set(f"Could not copy: {exc}")


# ---------------------------------------------------------------------------------------------------------------- page on / off

def activate(app: Any) -> None:
    if getattr(app, "_av_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_av_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._av_active = True
    _restore(app)
    _save(app)
    app._av_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_av_active", False):
        app._av_active = False
        if remember:
            _save(app)
        block = getattr(app, "_av_block", None)
        if block is not None:
            block.grid_remove()
        try:
            import visual_bridge

            visual_bridge.clear(app, OWNER)
        except Exception:  # noqa: BLE001
            pass


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_av_generate_btn", None) is None:
        return
    running = getattr(app, "_av_running", False)
    app._av_generate_btn.configure(state="disabled" if running else "normal")
    app._av_render_btn.configure(state="normal" if (app._av_ready and not running) else "disabled")
    app._av_stop_btn.configure(state="normal" if running and not app._av_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_av_running", False):
        app._cta_action = "av_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._av_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._av_ready:
        app._cta_action = "av_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Scenes are ready. Check the Visuals tab, then click Render.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "av_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose the voice-over (and optionally the scenes CSV), then click Generate scenes.")
    app._set_generate_btn(state="normal", text="Generate scenes")


def cta(app: Any, action: str) -> None:
    if action == "av_cancel":
        cancel(app)
    elif action == "av_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_av_running", False) or app._av_cancel.is_set():
        return
    app._av_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


# ---------------------------------------------------------------------------------------------------------------- work

def _voice(app: Any) -> str:
    v = app._av_voice_var.get().strip()
    if not v:
        cur = app._current_voiceover_path()
        v = str(cur) if cur else ""
    return v


def _log(app: Any):
    return lambda m: app.after(0, lambda: app._append_log(f"{TAG} {m}\n"))


def _progress(app: Any, export: bool):
    def cb(frac: float, msg: str = "") -> None:
        k = max(0.0, min(1.0, frac))
        app.after(0, lambda: (app._av_status_var.set(f"{int(k * 100)}%  {msg}".strip()), app.progress.set(k),
                              export and app._export_progress(k, msg or "")))
    return cb


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._av_cancel.clear()
    app._av_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            from aviation.runner import Cancelled

            error = "Stopped." if (app._av_cancel.is_set() or isinstance(exc, Cancelled)) else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._av_running = False
            if error:
                app._av_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._av_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def _scenes(app: Any, csv_path: str, voice: str, log) -> tuple:
    """Timed scenes (+ aviation CSV rows or None) from the CSV aligned to the voice-over's words, or from its own sentences."""
    from cinematic_explainer.war.app_section import sentences_from_words
    from aviation import runner as RN

    ws = app._workspace
    words = app._pakmap_get_words(Path(voice), app.model_var.get().strip() or "base", getattr(ws, "state_dir", None), log)
    try:
        from pakmap.app_integration import voiceover_duration

        total = float(voiceover_duration(voice) or 0.0)
    except Exception:  # noqa: BLE001
        total = 0.0
    if csv_path:
        from health_cinema import scenes_csv

        scenes, rows = RN.scenes_from_csv(csv_path)
        timed, frac = scenes_csv.align_to_words(scenes, words, total)
        log(f"{len(timed)} scenes from the CSV, aligned to the voice-over: {scenes_csv.match_note(frac)}")
        for sc, base in zip(timed, scenes):            # keep the CSV's own columns on the timed scenes
            for k in ("asset_type", "prompt"):
                sc.setdefault(k, base.get(k, ""))
            sc.pop("words", None)
        return timed, rows
    scenes = sentences_from_words(words, total)
    if not scenes:
        raise RuntimeError("the voice-over has no words to plan from")
    for sc in scenes:
        sc.pop("words", None)
    log(f"{len(scenes)} scenes from the voice-over's sentences")
    return scenes, None


def _rows_for_json(rows) -> Optional[List[dict]]:
    if rows is None:
        return None
    return [{k: v for k, v in r.items() if k != "cls"} for r in rows]


def _ask(app: Any, title: str, message: str) -> bool:
    """A yes / no question on the main thread while the worker waits (Stop answers no)."""
    from tkinter import messagebox

    ev, box = threading.Event(), {}

    def q() -> None:
        try:
            box["yes"] = bool(messagebox.askyesno(title, message))
        finally:
            ev.set()

    app.after(0, q)
    while not ev.wait(0.3):
        if app._av_cancel.is_set():
            return False
    return box.get("yes", False)


def _flow_image_rows(scenes: List[dict], have: List[Any]) -> List[Any]:
    """Visuals-tab rows for Flow image scenes (War's row builder lists only footage types)."""
    from providers.base import SceneRow

    listed = {str(getattr(r, "scene_number", "")) for r in have}
    return [SceneRow.from_csv_row({"scene_number": str(sc["scene_no"]), "script_segment": sc.get("text", ""), "asset_type": "flow_image",
                                   "prompt": sc.get("prompt", "")})
            for sc in scenes if sc.get("asset_type") == "flow_image" and str(sc["scene_no"]) not in listed]


def _aviation_prompts(vrows: List[Any], scenes: List[dict]) -> None:
    """War's row builder gives Flow rows War's own look; the Visuals tab's Retry must remake them in the aviation look."""
    from aviation import flow as FL

    by_no = {str(sc["scene_no"]): sc for sc in scenes}
    for r in vrows:
        sc = by_no.get(str(getattr(r, "scene_number", "")))
        at = getattr(r, "asset_type", "")
        at = str(getattr(at, "value", at)).lower()          # the row's type may be an enum
        if sc and (at in ("flow_video", "flow_image") or str(sc.get("asset_type")) in ("flow_video", "flow_image")):
            try:
                r.prompt = FL.prompt_for(sc)
            except Exception:  # noqa: BLE001 - a row keeps its prompt
                pass


def _make_flow(app: Any, scenes: List[dict], manager: Any, images_dir: Path, log, on_start, on_done) -> None:
    """Flow videos / images for the scenes that ask for them, after the user agrees to the credit cost. Aviation's own prompts (one shared
    flight-simulator look); already-made shots are kept and cost nothing. No: those scenes go back to the map or cards."""
    import visual_bridge
    from aviation import flow as FL
    from providers.base import SceneRow

    want = [sc for sc in scenes if sc.get("asset_type") in ("flow_video", "flow_image")]
    if not want:
        return
    rows = [SceneRow.from_csv_row({"scene_number": str(sc["scene_no"]), "script_segment": sc.get("text", ""),
                                   "asset_type": sc["asset_type"], "prompt": FL.prompt_for(sc)}) for sc in want]
    have = {str(r.scene_number) for r in rows if visual_bridge.records(images_dir, [r])}
    cost = FL.credits(want, have)
    todo = [r for r in rows if str(r.scene_number) not in have]
    if not todo:
        return
    if cost["videos"] and not _ask(app, "Flow shots", FL.question(cost)):
        for sc in want:
            if str(sc["scene_no"]) not in have:
                sc["asset_type"] = "none"                  # the map or a card shows these lines
        log("Flow shots skipped: those scenes use the map or cards")
        return
    errs = manager.validate_rows(todo)
    if errs:
        log("Flow rows not made: " + "; ".join(errs)[:300])
        return
    log(f"making {cost['videos']} Flow video(s) and {cost['images']} Flow image(s)…")
    app._style_fetch_manager = manager
    try:
        manager.resolve_all(todo, on_scene_start=on_start, on_scene_complete=on_done)
    except Exception as exc:  # noqa: BLE001 - a Flow failure leaves those scenes to the map or cards
        log(f"Flow stopped early: {type(exc).__name__}: {exc}")
    finally:
        app._style_fetch_manager = None


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_av_running", False):
        return
    ws = app._workspace
    if ws is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    voice, csv_path = _voice(app), app._av_csv_var.get().strip()
    if not voice or not Path(voice).is_file():
        messagebox.showerror("Cannot start", "Choose the voice-over first." if not voice else f"The voice-over is not there: {voice}")
        return
    if csv_path and not Path(csv_path).is_file():
        messagebox.showerror("Cannot start", f"The scenes CSV is not there: {csv_path}")
        return
    import visual_bridge
    from cinematic_explainer.war.app_section import war_manager

    images_dir = visual_bridge.folder(OWNER, ws)
    try:
        manager = war_manager(app._build_asset_manager(images_dir, []))      # built here: it reads Tk variables; Gemini off
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror("Cannot start", f"The app's asset sources could not be set up:\n{exc}")
        return
    app._av_ready = None
    _save(app)
    app._av_status_var.set("Reading the narration…")
    app._append_log(f"{TAG} Generate scenes\n")
    log = _log(app)
    M = _m(app)

    def job():
        from aviation import planner as P
        from aviation import runner as RN
        from cinematic_explainer.war.app_section import fetch_csv_footage

        scenes, rows = _scenes(app, csv_path, voice, log)
        if app._av_cancel.is_set():
            raise RN.Cancelled()
        if rows and any(r.get("url") for r in rows):
            n_pages = RN.prepare_pages(rows, _state_dir(app) / "pages", log)
            log(f"{n_pages} article / report page(s) captured for the cards")
        plan = P.plan(scenes, rows)
        from aviation import flow as FL

        n_flow = FL.assign(scenes, plan, rows)            # aircraft shots between map beats, the cockpit for crew lines
        if n_flow:
            log(f"{n_flow} Flow aircraft / cockpit shots placed between the map beats")
        RN.request_footage(scenes, plan)
        n_need = sum(1 for s in scenes if s.get("asset_type") not in ("", "none"))
        log(f"planned {len(scenes)} scenes: {n_need} need footage; looks: " +
            ", ".join(f"{m} {plan.modes.count(m)}" for m in sorted(set(plan.modes), key=plan.modes.count, reverse=True)))

        def listed(rows_):
            app.after(0, lambda: visual_bridge.fill(app, OWNER, rows_))

        def on_start(scene, source):
            app._ui_queue.put(("scene_busy", (scene.scene_number, M._scene_busy_kind(source))))

        def on_done(scene, result):
            app._ui_queue.put(("scene_asset", (scene.scene_number, result)))

        live = hasattr(app, "_ui_queue")
        for sc, mode in zip(scenes, plan.modes):
            sc["mode"] = mode
        for sc, r in zip(scenes, rows or []):
            if r and r.get("airline"):
                sc["airline"] = r["airline"]               # the CSV's airline: a clip's title must name it (or its parent)
            if r and r.get("aircraft"):
                sc["aircraft"] = r["aircraft"]             # the CSV's aircraft type: a clip's title must name it
        # YouTube rows: the aviation footage director (title rules + storyboard frame checks before any capture; extra burst clips)
        from aviation import director as AD

        _scenes_out, vrows = fetch_csv_footage(scenes, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
        if live:
            listed(vrows)                                  # every scene is in the Visuals tab before the first download
        rep_ = AD.run(scenes, images_dir, _state_dir(app), log=log, cancel=app._av_cancel.is_set)
        if app._av_cancel.is_set():
            raise RN.Cancelled()
        n_fb = FL.fallback(scenes, rep_.get("unfilled") or [], plan, rows)
        if n_fb:
            log(f"{n_fb} scene(s) without a good YouTube clip get a Flow shot instead")
        _make_flow(app, scenes, manager, images_dir, log, on_start if live else None, on_done if live else None)
        if app._av_cancel.is_set():
            raise RN.Cancelled()
        # every other fetching row (stock, local ...) through the app's own providers; YouTube and Flow rows are done above
        others = [sc for sc in scenes if str(sc.get("asset_type") or "").lower() not in ("youtube_video", "flow_video", "flow_image")]
        app._style_fetch_manager = manager
        try:
            fetch_csv_footage(others, manager, images_dir, log, cancel=app._av_cancel.is_set, ai_cap=0, fetch=True,
                              listed=None, on_start=on_start if live else None, on_done=on_done if live else None,
                              director=False, library=False)
        finally:
            app._style_fetch_manager = None
        _scenes_out, vrows = fetch_csv_footage(scenes, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
        vrows = vrows + _flow_image_rows(scenes, vrows)
        _aviation_prompts(vrows, scenes)                  # Retry in the Visuals tab remakes Flow shots in the aviation look
        if app._av_cancel.is_set():
            raise RN.Cancelled()
        _progress(app, False)(0.9, "map terrain")
        n_maps = RN.prefetch_maps(plan, log, cancel=app._av_cancel.is_set)
        f = _state_dir(app) / "scenes.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"scenes": scenes, "rows": _rows_for_json(rows)}, indent=1, default=str), encoding="utf-8")
        return {"rows": vrows, "file": str(f), "maps": n_maps, "need": n_need}

    def done(r) -> None:
        visual_bridge.fill(app, OWNER, r["rows"])
        app._av_ready = {"csv": csv_path, "voice": voice, "scenes_file": r["file"]}
        ok = len(visual_bridge.records(images_dir, r["rows"]))
        msg = (f"Scenes ready: {ok} of {r['need']} clips found, {r['maps']} flight map(s) ready. "
               "Check the clips in the Visuals tab, then click Render.")
        app._av_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)
        if r["rows"]:
            try:
                app._goto_workflow_view("visual_plan")
            except Exception:  # noqa: BLE001
                pass

    _start(app, "aviation-generate", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_av_running", False):
        return
    ws, ready = app._workspace, app._av_ready
    if ws is None or not ready:
        messagebox.showerror("Cannot start", "Click Generate scenes first: Render uses the scenes and clips it prepared.")
        return
    if (app._av_csv_var.get().strip(), _voice(app)) != (ready["csv"], ready["voice"]):
        messagebox.showinfo("Click Generate scenes first", "You changed the voice-over or the CSV after Generate scenes. Click Generate scenes again, then Render.")
        return
    import visual_bridge

    images_dir = visual_bridge.folder(OWNER, ws)
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._av_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("aviation")
    log = _log(app)

    def end(error: str) -> None:
        from export_state import run_outcome

        done_ = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._av_cancel.is_set())
        app._track_generation_end(run, done_, output_path=out_path if done_ == "completed" else None, validated=done_ == "completed",
                                  message=error or ("" if done_ != "failed" else "Render finished, but no video was written."))

    def job():
        from aviation import planner as P
        from aviation import runner as RN
        from cinematic_explainer.war.app_section import fetch_csv_footage

        data = json.loads(Path(ready["scenes_file"]).read_text(encoding="utf-8"))
        scenes, rows = data["scenes"], data.get("rows")
        # exactly what the Visuals tab holds now (the user's Retry / Change source / Local clip included); nothing is fetched
        scenes, _vrows = fetch_csv_footage(scenes, None, images_dir, log, fetch=False, ai_cap=0, director=False, library=False)
        RN.attach_images(scenes, images_dir)
        RN.mark_clips(scenes)                             # lines without a clip get aviation graphics / text cards
        plan = P.plan(scenes, rows)
        work = _state_dir(app) / "render"
        from aviation import director as AD

        try:
            extras = json.loads((_state_dir(app) / AD.EXTRAS).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            extras = {}
        return RN.render_film(plan, scenes, ready["voice"], str(out_path), work=str(work), progress=_progress(app, True),
                              cancel=app._av_cancel.is_set, log=log, extras=extras)

    def done(r) -> None:
        extra = f", {r['missing_footage']} slots used fact cards (no clip)" if r.get("missing_footage") else ""
        msg = f"Done: {Path(out_path).name} ({r['duration']:.0f} s, {r['clips']} clip slices{extra})."
        app._av_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "aviation-render", job, done, end)
