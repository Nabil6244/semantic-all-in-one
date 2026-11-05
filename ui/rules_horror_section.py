"""Rules Horror: its own style page (a story CSV, a voice-over, resolution) with a Generate step that places the story on the voice and lists the Flow
pictures it wants in the Visuals tab, an optional "Make pictures in Flow" step (images only, asks first) and a Render step. All the work lives in the
`rules_horror` package, imported only inside the button handlers. A CSV run makes zero Gemini calls (the words come from the local Whisper).
Nothing starts until Generate: picking files or options only remembers them.

app.py only calls in here: activate / deactivate / sync_cta / cta, and reads `_rh_block` / `_rh_running` / `_rh_active`."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Rules Horror"
TAG = "[RULES HORROR]"
OWNER = "rules_horror"
LOOKS = {"Auto: best of the 9 references": "auto", "Line art (house)": "line_house", "Line art (pet)": "line_pet", "Line art (exam)": "line_exam",
         "Navy cartoon (travel)": "night_flight", "Navy cartoon (cinema)": "night_cinema", "Bright colour (mall)": "bright_mall",
         "Bright colour (store)": "bright_store", "Bright colour (school)": "bright_school", "Underwater teal": "deep_water", "Follows the story": "story", "Night colour": "dark", "Lit colour": "colour", "White on black": "mono"}
LOOK_NAMES = {v: k for k, v in LOOKS.items()}
RESOLUTIONS = {"720p preview (1280x720)": (1280, 720), "1080p final (1920x1080)": (1920, 1080)}
_ROOT = Path(__file__).resolve().parent.parent


def _root() -> Path:
    return Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT


def prompt_path() -> Path:
    return _root() / "rules_horror" / "prompt.txt"


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._rh_csv_var = ctk.StringVar(value="")
    app._rh_voice_var = ctk.StringVar(value="")
    app._rh_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._rh_fps_var = ctk.StringVar(value="30")
    app._rh_look_var = ctk.StringVar(value="Auto: best of the 9 references")
    app._rh_status_var = ctk.StringVar(value="")
    app._rh_prompt_status = ctk.StringVar(value="")
    app._rh_cancel = threading.Event()
    app._rh_running = getattr(app, "_rh_running", False)
    app._rh_spec_path = None
    app._rh_table_snapshot = None

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._rh_block = block

    body = section(block, 0, 1, "Story and voice-over", "a story CSV and the narration; nothing starts until Generate")
    app._path_row(0, "Story CSV", app._rh_csv_var, lambda: _browse(app, "csv"), parent=body,
                  placeholder_text="Choose the story CSV (order, section, line, set, shot, subject, pose, action, tag, value, prompt)")
    app._path_row(1, "Voice-over", app._rh_voice_var, lambda: _browse(app, "voice"), parent=body,
                  placeholder_text="Choose the narration (cuts and captions follow its words)")
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=2, column=0, sticky="ew", pady=(6, 0))
    make_button(tools, "Copy the script prompt", lambda: copy_prompt(app), size="sm", width=170).grid(row=0, column=0, padx=(0, 10))
    make_button(tools, "Copy the convert-my-script prompt", lambda: copy_prompt(app, convert=True), size="sm", width=250).grid(row=0, column=1, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._rh_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(row=0, column=2, sticky="w")
    ctk.CTkLabel(body, text="Paste the prompt into any AI chat. It writes the story to record and the matching CSV. Save the CSV, record the story, "
                            "then choose both above. Already have a script? Use the convert-my-script prompt and paste your script after it (rules_horror/prompt.txt, prompt_convert.txt).", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 justify="left", wraplength=600).grid(row=3, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._rh_res_var, width=220).grid(row=0, column=1, padx=(0, 16))
    ctk.CTkLabel(out, text="Frame rate", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=2, padx=(0, 8))
    ctk.CTkSegmentedButton(out, values=["24", "30"], variable=app._rh_fps_var).grid(row=0, column=3, padx=(0, 16))
    ctk.CTkLabel(out, text="Look", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=4, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(LOOKS), variable=app._rh_look_var, width=230).grid(row=0, column=5)

    body = section(block, 2, 3, "Flow pictures (optional)", "the creature's poses and the reveal close-ups")
    fl = ctk.CTkFrame(body, fg_color="transparent")
    fl.grid(row=0, column=0, sticky="w")
    app._rh_make_btn = make_button(fl, "Make pictures in Flow", lambda: on_make_pictures(app), size="sm", width=190)
    app._rh_make_btn.grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(body, text="Click Generate first: it lists the pictures in the Visuals tab. Flow makes images only (no credits for clips) and asks first. "
                            "Any picture Flow cannot make is drawn in code (a tall figure with red eyes), and the video still renders. "
                            "You can retry, change source or choose a local file for any picture in the Visuals tab.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(4, 0))

    body = section(block, 3, 4, "Generate, then Render", "Generate plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._rh_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._rh_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._rh_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._rh_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._rh_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._rh_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._rh_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    if kind == "csv":
        path = filedialog.askopenfilename(title="Choose the story CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._rh_csv_var
    else:
        path = filedialog.askopenfilename(title="Choose the voice-over", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._rh_voice_var
    if path:
        var.set(path)       # remembered only: nothing is read or planned until Generate
        app._rh_spec_path = None
        _sync_buttons(app)


def copy_prompt(app: Any, convert: bool = False) -> None:
    try:
        from rules_horror import prompts

        text = prompts.convert_prompt() if convert else prompts.story_prompt()
        app.clipboard_clear()
        app.clipboard_append(text)
        app._rh_prompt_status.set("Copied. Paste it into your AI chat" + (", then paste your script after it." if convert else "."))
    except Exception as exc:  # noqa: BLE001
        app._rh_prompt_status.set(f"Could not copy: {exc}")


# ---- activation and the app's main button -------------------------------------------------------------------------------

def activate(app: Any) -> None:
    if getattr(app, "_rh_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside, like the other standalone styles
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_rh_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._rh_active = True
    from .voiceover_view import adopt_project_voiceover
    adopt_project_voiceover(app, app._rh_voice_var)
    _load_options(app)
    app._rh_block.grid()
    _sync_buttons(app)
    import visual_bridge

    visual_bridge.restore(app, OWNER)


def deactivate(app: Any) -> None:
    if getattr(app, "_rh_active", False):
        app._rh_active = False
        import visual_bridge

        visual_bridge.clear(app, OWNER)
        block = getattr(app, "_rh_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_rh_generate_btn", None) is None:
        return
    running = getattr(app, "_rh_running", False)
    ready = bool(app._rh_spec_path and Path(app._rh_spec_path).is_file())
    app._rh_generate_btn.configure(state="disabled" if running else "normal")
    app._rh_render_btn.configure(state="normal" if (ready and not running) else "disabled")
    app._rh_make_btn.configure(state="normal" if (ready and not running) else "disabled")
    app._rh_stop_btn.configure(state="normal" if running and not app._rh_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_rh_running", False):
        app._cta_action = "rh_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._rh_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._rh_spec_path and Path(app._rh_spec_path).is_file():
        app._cta_action = "rh_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The film is planned. Check the Visuals tab, then click Render.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "rh_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose the story CSV and the voice-over, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "rh_cancel":
        cancel(app)
    elif action == "rh_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_rh_running", False) or app._rh_cancel.is_set():
        return
    app._rh_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


# ---- helpers ------------------------------------------------------------------------------------------------------------------

def _package():
    try:
        import rules_horror  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Rules Horror is not installed", f"The rules_horror package could not be loaded:\n{type(exc).__name__}: {exc}")
        return None
    return rules_horror


def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "rules_horror"
    d.mkdir(parents=True, exist_ok=True)
    return d


def options(app: Any) -> Dict[str, Any]:
    w, h = RESOLUTIONS.get(app._rh_res_var.get(), (1280, 720))
    return {"csv": app._rh_csv_var.get().strip(), "voice": app._rh_voice_var.get().strip(), "width": w, "height": h,
            "fps": 24 if app._rh_fps_var.get() == "24" else 30, "scheme": LOOKS.get(app._rh_look_var.get(), "auto")}


def _load_options(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    if ws is None:
        return
    try:
        o = json.loads((Path(ws.state_dir) / "rules_horror" / "options.json").read_text(encoding="utf-8"))
    except Exception:
        return
    for key, var in (("csv", app._rh_csv_var), ("voice", app._rh_voice_var)):
        if o.get(key) and not var.get():
            var.set(o[key])
    look = next((k for k, v in LOOKS.items() if v == o.get("scheme")), None)      # the Look menu remembers the last choice
    if look:
        app._rh_look_var.set(look)
    spec = o.get("spec_path")
    if spec and Path(spec).is_file() and not app._rh_spec_path:
        app._rh_spec_path = spec


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._rh_cancel.clear()
    app._rh_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never a silent failure
            error = "Stopped." if app._rh_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._rh_running = False
            if error:
                app._rh_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._rh_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def _progress_cb(app: Any, export: bool = False):
    def cb(*args, **kwargs) -> None:
        nums = [a for a in args if isinstance(a, (int, float))]
        k = None
        if len(nums) >= 2 and nums[1]:
            k = min(1.0, float(nums[0]) / float(nums[1]))
        elif nums:
            k = min(1.0, float(nums[0]) if nums[0] <= 1 else float(nums[0]) / 100.0)
        msg = next((a for a in args if isinstance(a, str)), "")
        text = (f"{int(k * 100)}%  " if k is not None else "") + (msg or "Rendering…")
        try:
            app.after(0, lambda: (app._rh_status_var.set(text.strip()), k is not None and app.progress.set(k),
                                  export and k is not None and app._export_progress(k, msg or "")))
        except Exception:
            pass
    return cb


# ---- the Visuals tab: one row per Flow picture the story wants -----------------------------------------------------------------

def _rows_for(reqs: List[Dict[str, Any]]) -> List:
    from providers.base import SceneRow

    return [SceneRow(scene_number=str(r["n"]), script_segment=f"{r['key']}", asset_type="image", prompt=str(r["prompt"])) for r in reqs]


def _show_in_visuals(app: Any, reqs: List[Dict[str, Any]]) -> None:
    import visual_bridge

    visual_bridge.fill(app, OWNER, _rows_for(reqs))
    app._rh_table_snapshot = visual_bridge.snapshot(visual_bridge.folder(OWNER, app._workspace), app._scene_rows)


def _pictures(app: Any, reqs: List[Dict[str, Any]]) -> Dict[str, str]:
    """{key: file} for the pictures the Visuals tab holds now (whatever the user retried or replaced there is what the film uses)."""
    import visual_bridge
    from rules_horror import assets

    rows = visual_bridge.rows(app, OWNER)
    if not rows:
        return {}
    return assets.picture_map(reqs, visual_bridge.records(visual_bridge.folder(OWNER, app._workspace), rows))


# ---- Generate / Make pictures / Render ------------------------------------------------------------------------------------------

def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rh_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    o = options(app)
    if not o["csv"] or not Path(o["csv"]).is_file():
        messagebox.showerror("Cannot start", "Choose the story CSV first." if not o["csv"] else f"The story CSV was not found:\n{o['csv']}")
        return
    if not o["voice"] or not Path(o["voice"]).is_file():
        messagebox.showerror("Cannot start", "Choose the voice-over first." if not o["voice"] else f"The voice-over was not found:\n{o['voice']}")
        return
    rh = _package()
    if rh is None:
        return
    from rules_horror import assets, runner
    from rules_horror.csv_io import read_csv

    import visual_bridge

    out_dir = _work_dir(app)
    reqs = assets.requests(read_csv(o["csv"]))
    old = assets.load_index(visual_bridge.folder(OWNER, app._workspace))
    if [r["key"] for r in old] != [r["key"] for r in reqs] or not visual_bridge.rows(app, OWNER):
        assets.save_index(visual_bridge.folder(OWNER, app._workspace), reqs)
        _show_in_visuals(app, reqs)           # the pictures the story wants, listed in the Visuals tab (kept when the story is unchanged)
    pictures = _pictures(app, reqs)
    whisper_model = (app.model_var.get().strip() if hasattr(app, "model_var") else "") or "base"
    app._rh_status_var.set("Planning the film…")
    app._append_log(f"{TAG} Generate: {o['width']}x{o['height']} @ {o['fps']} fps, {len(pictures)} of {len(reqs)} Flow pictures ready\n")

    def job():
        app.after(0, lambda: app._rh_status_var.set("Reading the voice-over…"))
        words = app._pakmap_get_words(Path(o["voice"]), whisper_model, getattr(app._workspace, "state_dir", None),
                                      lambda m: app.after(0, lambda m=m: app._append_log(f"{TAG} {m}\n")))
        return runner.generate(o["csv"], o["voice"], out_dir, words=list(words), width=o["width"], height=o["height"], fps=o["fps"], pictures=pictures, scheme=o.get("scheme", "auto"),
                               log=lambda m: app.after(0, lambda m=m: app._append_log(f"{TAG} {m}\n")))

    def done(r) -> None:
        app._rh_spec_path = r["spec_path"]
        try:
            (out_dir / "options.json").write_text(json.dumps({**o, "spec_path": r["spec_path"]}, indent=2), encoding="utf-8")
        except Exception:
            pass
        for n in r["notes"] + r["warnings"]:
            app._append_log(f"{TAG} {n}\n")
        s = r["stats"]
        warn = f" {len(r['warnings'])} warning(s) in the log." if r["warnings"] else ""
        look = LOOK_NAMES.get(s.get("look", ""), "")
        if look:
            app._append_log(f"{TAG} Look: {look} ({s.get('cuts_per_min')} cuts/min, {s.get('punch_ins', 0)} punch-ins)\n")
        app._rh_status_var.set(f"Planned{' in ' + look if look else ''}: {s['shots']} shots, median {s['median_shot_s']} s.{warn} {len(reqs)} picture(s) listed in the Visuals tab; click Render.")
        _show_in_visuals(app, reqs)

    _start(app, "rules-horror-generate", job, done)


def on_make_pictures(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rh_running", False) or _package() is None:
        return
    import visual_bridge
    from rules_horror import assets

    folder = visual_bridge.folder(OWNER, app._workspace)
    reqs = assets.load_index(folder)
    if not reqs:
        messagebox.showinfo("Click Generate first", "Generate lists the pictures the story wants; then Flow can make them.")
        return
    have = {n: rec["path"] for n, rec in visual_bridge.records(folder, visual_bridge.rows(app, OWNER)).items()}
    todo = [r for r in reqs if r["n"] not in have]
    if not todo:
        messagebox.showinfo("Nothing to make", "Every picture is already in the Visuals tab.")
        return
    if not messagebox.askokcancel("Make pictures in Flow", f"{len(todo)} picture(s) will be made in Flow with your Flow account (images only, no clips). "
                                                           "A picture Flow cannot make is drawn in code instead. Continue?"):
        return
    manager = app._get_flow_engine_manager()
    app._rh_status_var.set("Making the pictures in Flow…")
    app._append_log(f"{TAG} Make pictures: {len(todo)} request(s)\n")

    def job():
        client = manager.ensure_running()
        return assets.make(reqs, Path(app._workspace.state_dir) / "rules_horror" / "flow", client, skip=have, cancel=app._rh_cancel.is_set,
                           log=lambda m: app.after(0, lambda m=m: app._append_log(f"{TAG} {m}\n")))

    def done(results) -> None:
        for r in reqs:
            res = results.get(r["n"]) or {}
            if res.get("status") == "done" and r["n"] not in have:
                visual_bridge.seed(folder, str(r["n"]), res["path"], "flow_image", prompt=r["prompt"], provider="flow")
        _show_in_visuals(app, reqs)
        ok = sum(1 for v in results.values() if v.get("status") == "done")
        app._rh_status_var.set(f"{ok} of {len(reqs)} pictures are ready in the Visuals tab. Click Generate again to put them in the film, then Render.")
        app._rh_spec_path = None
        try:
            app._goto_workflow_view("visual_plan")
        except Exception:  # noqa: BLE001
            pass

    _start(app, "rules-horror-pictures", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rh_running", False):
        return
    ws = app._workspace
    if ws is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    spec = app._rh_spec_path
    if not spec or not Path(spec).is_file():
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned film.")
        return
    import visual_bridge

    rows = visual_bridge.rows(app, OWNER)
    if rows and visual_bridge.snapshot(visual_bridge.folder(OWNER, ws), rows) != getattr(app, "_rh_table_snapshot", None):
        messagebox.showinfo("Click Generate first", "You changed pictures in the Visuals tab. Click Generate to put them in the film, then Render.")
        return
    if _package() is None:
        return
    from rules_horror import runner

    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._rh_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render: {Path(spec).name} -> {out_path.name}\n")
    cb = _progress_cb(app, export=True)
    run = app._track_generation_start(OWNER)

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._rh_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return runner.render_planned(spec, out_path, progress=cb, cancel=app._rh_cancel.is_set,
                                     log=lambda m: app.after(0, lambda m=m: app._append_log(f"{TAG} {m}\n")))

    def done(_result) -> None:
        if app._rh_cancel.is_set():
            app._rh_status_var.set("Stopped.")
            return
        msg = f"Done: {out_path.name}" if Path(out_path).is_file() else "Render finished, but no video was written."
        app._rh_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "rules-horror-render", job, done, end)
