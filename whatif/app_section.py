"""The What If card in the app. app.py only delegates here (methods that import this module when they run), so a broken What If
install never crashes the app.

The card works like StarMap's: the plan is the narration itself (the voiceover and the script on the Script page) with an OPTIONAL shot
CSV an AI wrote (Copy the CSV prompt); the shots' pictures and clips are rows of the EXISTING Visual Plan table (replace, retry and
skip there); the SHARED Generate button renders it. Per project, everything lives in <project>/whatif/ (shots.csv, whatif.json, _work/)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

TAG = "[WHAT IF]"
STYLE_NAME = "What If"
MODE = "whatif"
HERO_IMAGE, HERO_VIDEO, HERO_BOTH = "Flow images", "Flow videos", "Images + videos"
_HERO_STATE = {HERO_IMAGE: "image", HERO_VIDEO: "video", HERO_BOTH: "both"}


def _m(app):
    """app.py's module (theme colours, ctk, dialogs): found from the App class, so it works when app.py runs as __main__."""
    return sys.modules[type(app).__module__]


# ---- the project folder ----------------------------------------------------------------------------------------------------
def root(ws) -> Path:
    return Path(ws.root) / "whatif"


def csv_path(ws) -> Path:
    return root(ws) / "shots.csv"


def work_dir(ws) -> Path:
    return root(ws) / "_work"


def images_dir(ws) -> Path:
    return work_dir(ws) / "media"


def _state_path(ws) -> Path:
    return root(ws) / "whatif.json"


def load_state(ws) -> Dict[str, Any]:
    try:
        return json.loads(_state_path(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(app, active: Optional[bool] = None) -> None:
    ws = app._workspace
    if ws is None or not hasattr(app, "_whatif_sound_var"):
        return
    state = load_state(ws)
    state["sound_design"] = bool(app._whatif_sound_var.get())
    state["hero"] = _HERO_STATE.get(app._whatif_hero_var.get(), "both")
    if active is not None:
        state["active"] = bool(active)
    try:
        root(ws).mkdir(parents=True, exist_ok=True)
        _state_path(ws).write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError as exc:
        app._append_log(f"{TAG} Could not save the What If settings: {exc}\n")


def on_flow_mode(app) -> None:
    """The Flow switch decides each illustrated shot's source in the plan: a Visual Plan already listed is planned again, so its rows show
    the new Flow Image / Flow Video choices (each row can still be changed there one by one)."""
    save_state(app)
    if getattr(app, "_scene_rows_owner", None) == MODE and not (app._whatif_busy or app._whatif_running):
        app._append_log(f"{TAG} Flow pictures: {app._whatif_hero_var.get()}. Planning the shots again so the Visual Plan shows it.\n")
        check_plan(app)


def current_csv(app) -> Optional[Path]:
    ws = app._workspace
    return csv_path(ws) if ws is not None and csv_path(ws).is_file() else None


def flow_video(app) -> str:
    """How illustrated shots are made: "images", "videos", or "both" (moving pictures where motion matters: the opening, the long holds)."""
    return {"image": "images", "video": "videos"}.get(_HERO_STATE.get(app._whatif_hero_var.get(), "both"), "both")


# ---- the card ----------------------------------------------------------------------------------------------------------------
def build(app, parent, *, row: int) -> None:
    M = _m(app)
    ctk = M.ctk
    app._whatif_enabled_var = ctk.BooleanVar(value=False)
    app._whatif_sound_var = ctk.BooleanVar(value=bool(app._settings.get("pakmap_sound_design", True)))
    app._whatif_hero_var = ctk.StringVar(value=HERO_BOTH)
    app._whatif_status_var = ctk.StringVar(value="")
    app._whatif_file_var = ctk.StringVar(value="")
    app._whatif_running = False
    app._whatif_busy = False
    app._whatif_cancel = threading.Event()
    app._whatif_ok = None
    app._whatif_tracking = None
    app._whatif_run_manager = None
    app._whatif_plan = None

    block = ctk.CTkFrame(parent, fg_color=M._CARD, corner_radius=10, border_width=1, border_color=M._BORDER)
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._whatif_block = block
    app._style_card_header(block, "What If (science explainer)",
                           "Calm documentary explainers: hard cuts, a real photo or a clean illustration for every sentence, diagrams, a survival clock or "
                           "two clocks, and every number on screen a beat before it is said. Planned from your voiceover and script; an AI shot list is optional.")
    app._whatif_switch = ctk.CTkSwitch(block, text="Use What If for this project", variable=app._whatif_enabled_var, command=lambda: on_toggle(app),
                                       font=ctk.CTkFont(size=12), text_color=M._TEXT)
    app._whatif_switch.grid(row=1, column=0, sticky="w", padx=16, pady=(12, 14))
    controls = ctk.CTkFrame(block, fg_color="transparent")
    controls.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))
    controls.grid_columnconfigure(0, weight=1)
    app._whatif_controls = controls

    actions = ctk.CTkFrame(controls, fg_color="transparent")
    actions.grid(row=0, column=0, sticky="ew")
    ctk.CTkButton(actions, text="Plan the shots", width=130, height=36, corner_radius=6, fg_color=M._ACCENT, hover_color=M._ACCENT_HOV,
                  font=ctk.CTkFont(size=12, weight="bold"), command=lambda: check_plan(app)).grid(row=0, column=0, padx=(0, 8))
    for col, (text, cmd) in enumerate((("Load shot CSV (optional)…", lambda: browse(app)), ("Copy the CSV prompt", lambda: app._copy_csv_prompt("whatif", app._whatif_status_var)),
                                       ("Edit CSV", lambda: open_csv(app)))):
        ctk.CTkButton(actions, text=text, height=36, corner_radius=6, fg_color="transparent", border_width=1, border_color=M._BORDER, text_color=M._MUTED,
                      hover_color=M._ACCENT_SEL, font=ctk.CTkFont(size=12), command=cmd).grid(row=0, column=col + 1, padx=(0, 8))
    app._path_row(1, "Shot CSV", app._whatif_file_var, lambda: browse(app), parent=controls, placeholder_text="None: the shots are planned from the narration")

    opts = ctk.CTkFrame(controls, fg_color="transparent")
    opts.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    ctk.CTkLabel(opts, text="Pictures for illustrated shots", font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkSegmentedButton(opts, values=[HERO_IMAGE, HERO_BOTH, HERO_VIDEO], variable=app._whatif_hero_var, height=26, font=ctk.CTkFont(size=11),
                           command=lambda _v: on_flow_mode(app)).grid(row=0, column=1)
    ctk.CTkSwitch(opts, text="Sound effects + ambience", variable=app._whatif_sound_var, command=lambda: save_state(app),
                  font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(18, 0))
    app._whatif_plan_box = ctk.CTkTextbox(controls, height=210, font=ctk.CTkFont(family="Menlo", size=11), wrap="none")
    app._whatif_plan_box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
    app._whatif_plan_box.configure(state="disabled")
    ctk.CTkLabel(controls, textvariable=app._whatif_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=560,
                 justify="left").grid(row=4, column=0, sticky="ew", pady=(6, 0))
    controls.grid_remove()
    block.grid_remove()
    show_intro(app)


def set_text(app, text: str) -> None:
    box = app._whatif_plan_box
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.configure(state="disabled")


def show_intro(app) -> None:
    set_text(app, "No plan yet.\n\n1. Choose your voiceover and paste your script on the Script page.\n2. Click Plan the shots: the narration is cut into shots, "
                  "diagrams and callouts, and every picture is listed in the Visual Plan.\n3. Optional: Copy the CSV prompt, paste it with your script into any AI, "
                  "save the CSV it writes and Load it for a hand-directed shot list.\n4. Find or replace pictures in the Visual Plan, then Generate.")


# ---- switching ---------------------------------------------------------------------------------------------------------------
def deactivate(app) -> None:
    if not hasattr(app, "_whatif_enabled_var"):
        return
    was = app._whatif_enabled_var.get()
    app._whatif_enabled_var.set(False)
    app._whatif_controls.grid_remove()
    if app.generation_mode == MODE:
        app.generation_mode = "normal"
    clear_visual_plan(app)
    if was:
        save_state(app, active=False)


def activate(app) -> None:
    if getattr(app, "_whatif_running", False):
        return
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside and clears the shared table
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app._whatif_enabled_var.set(True)
    app._whatif_controls.grid()
    app.generation_mode = MODE
    app._set_scenes_empty_text()
    p = current_csv(app)
    app._whatif_file_var.set(str(p) if p else "")
    save_state(app, active=True)
    if app._workspace is not None and getattr(app, "_scene_rows_owner", None) != MODE:
        load_visual_plan(app, app._workspace)
    app._sync_primary_cta()


def on_toggle(app) -> None:
    if app._whatif_running:
        app._whatif_enabled_var.set(True)
        _m(app).messagebox.showinfo("Generation running", "Wait for the current generation to finish before switching style.")
        return
    if app._whatif_enabled_var.get():
        activate(app)
    else:
        deactivate(app)
        app._sync_primary_cta()


def restore(app, ws) -> None:
    """Reopening a project: the switches and (if What If was the project's style) the style itself."""
    if not hasattr(app, "_whatif_enabled_var"):
        return
    state = load_state(ws)
    app._whatif_ok = None
    app._whatif_plan = None
    app._whatif_sound_var.set(bool(state.get("sound_design", True)))
    app._whatif_hero_var.set({v: k for k, v in _HERO_STATE.items()}.get(state.get("hero"), HERO_BOTH))
    p = csv_path(ws) if csv_path(ws).is_file() else None
    app._whatif_file_var.set(str(p) if p else "")
    if state.get("active"):
        app._pakmap_deactivate()
        if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
            app._overscaled_enabled_var.set(False)
            app._overscaled_controls.grid_remove()
        app._whatif_enabled_var.set(True)
        app._whatif_controls.grid()
        app.generation_mode = MODE
        show_intro(app)
        load_visual_plan(app, ws)
    else:
        deactivate(app)
        show_intro(app)


# ---- the plan ----------------------------------------------------------------------------------------------------------------
def clear_visual_plan(app) -> None:
    if getattr(app, "_scene_rows_owner", None) != MODE:
        return
    app._scene_rows_owner = None
    app._scene_rows = []
    app._scene_preview_cache_sig = None
    app._render_scene_rows()


def _realign(app, ws, rows) -> None:
    """Saved files back on their own rows before the table is drawn (see media.realign_saved)."""
    try:
        from .media import realign_saved

        realign_saved(images_dir(ws), rows, log=lambda m: app._append_log(m + "\n"))
    except Exception as exc:
        app._append_log(f"{TAG} Could not check the saved pictures against the rows: {exc}\n")


def visual_plan_path(ws) -> Path:
    return root(ws) / "visual_plan.json"


def save_visual_plan(app) -> None:
    """The What If rows of the Visual Plan, as left (sources changed by hand included), in the project: reopening it shows them again
    and Generate uses them. Saved whenever the plan is listed and when a Generate starts."""
    import dataclasses

    ws = app._workspace
    if ws is None or getattr(app, "_scene_rows_owner", None) != MODE:
        return
    try:
        root(ws).mkdir(parents=True, exist_ok=True)
        data = {"flow": flow_video(app), "rows": [dataclasses.asdict(r) for r in app._scene_rows]}
        visual_plan_path(ws).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except (OSError, TypeError) as exc:
        app._append_log(f"{TAG} Could not save the Visual Plan: {exc}\n")


def load_visual_plan(app, ws) -> bool:
    """The saved Visual Plan back in the table (see save_visual_plan); False when the project has none."""
    from providers.base import SceneRow

    try:
        data = json.loads(visual_plan_path(ws).read_text(encoding="utf-8"))
        rows = [SceneRow(**r) for r in data.get("rows") or []]
    except (OSError, ValueError, TypeError):
        return False
    if not rows:
        return False
    # the rows were listed for one Flow mode: the switch goes back to it (set directly, so it does not plan the shots again)
    mode = {"images": HERO_IMAGE, "videos": HERO_VIDEO, "both": HERO_BOTH}.get(str(data.get("flow")))
    if mode and hasattr(app, "_whatif_hero_var"):
        app._whatif_hero_var.set(mode)
        save_state(app)
    app._scene_rows, app._scene_rows_owner, app._scene_preview_cache_sig = rows, MODE, None
    _realign(app, ws, rows)
    M = _m(app)
    keep = {M._scene_key(r.scene_number) for r in rows}
    app._asset_results = {k: v for k, v in app._asset_results.items() if k in keep}
    app._hydrate_overscaled_assets_from_manifest(images_dir(ws))
    app._render_scene_rows()
    app._refresh_assets_cta()
    app._whatif_status_var.set(f"Visual Plan restored ({len(rows)} pictures/clips). Change any source there, then Generate.")
    return True


def populate_visual_plan(app, plan=None, dicts=None) -> None:
    """Put the shots' pictures and clips in the EXISTING Visual Plan table (one row per asset shot). `dicts` are the rows already
    listed (Generate lists them on its own thread, before the fetch renumbers the shots)."""
    from providers.base import SceneRow

    dicts = list(dicts or [])
    if plan is not None and not dicts:
        try:
            from .app_integration import visual_dicts

            dicts = visual_dicts(plan)
        except Exception as exc:
            app._append_log(f"{TAG} The plan's pictures cannot be listed yet: {exc}\n")
    app._scene_rows = [SceneRow.from_csv_row(d) for d in dicts]
    app._scene_rows_owner = MODE
    app._scene_preview_cache_sig = None
    M = _m(app)
    keep = {M._scene_key(r.scene_number) for r in app._scene_rows}
    app._asset_results = {k: v for k, v in app._asset_results.items() if k in keep}
    if app._workspace is not None:
        _realign(app, app._workspace, app._scene_rows)
        app._hydrate_overscaled_assets_from_manifest(images_dir(app._workspace))
    app._render_scene_rows()
    app._refresh_assets_cta()
    save_visual_plan(app)


def browse(app) -> None:
    M = _m(app)
    if app._whatif_running or app._whatif_busy:
        M.messagebox.showinfo("What If", "Still working: wait for the current step to finish.")
        return
    if not app._require_workspace("load a What If shot CSV"):
        return
    path = M.filedialog.askopenfilename(title="Select a What If shot CSV", filetypes=[("What If shot CSV", "*.csv"), ("All files", "*.*")],
                                        initialdir=str(M._browse_start_dir()))
    if path:
        load_csv(app, path)


def load_csv(app, path: str) -> bool:
    from .shot_csv import is_whatif_csv

    M = _m(app)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        M.messagebox.showerror("Cannot read CSV", str(exc))
        return False
    if not is_whatif_csv(text):
        M.messagebox.showerror("Not a What If shot CSV", "The first row must be the What If header (row,shot,vo_anchor,kind,asset,...).\n\n"
                                                         "Use Copy the CSV prompt to have an AI write one.")
        return False
    ws = app._workspace
    try:
        root(ws).mkdir(parents=True, exist_ok=True)
        if Path(path).resolve() != csv_path(ws).resolve():
            shutil.copy2(path, csv_path(ws))
    except OSError as exc:
        M.messagebox.showerror("What If", f"Could not save the CSV in the project: {exc}")
        return False
    app._whatif_file_var.set(str(csv_path(ws)))
    app._whatif_ok = None
    if not app._whatif_enabled_var.get():
        app._whatif_enabled_var.set(True)
        on_toggle(app)
    app._whatif_status_var.set(f"Loaded {Path(path).name}")
    app._append_log(f"{TAG} Loaded {path}\n")
    if app._current_voiceover_path() is not None:
        check_plan(app)
    app._sync_primary_cta()
    return True


def open_csv(app) -> None:
    M = _m(app)
    p = current_csv(app)
    if p is None:
        M.messagebox.showinfo("What If", "Load a shot CSV first.")
        return
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        elif sys.platform == "win32":
            os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(p)])
        app._whatif_status_var.set("Edit and save the CSV, then Plan the shots again.")
    except Exception as exc:
        M.messagebox.showerror("What If", f"Could not open the CSV: {exc}")


def check_plan(app) -> None:
    """Plan the shots from the narration (and the CSV if there is one) and report; the pictures go to the Visual Plan. No rendering."""
    M = _m(app)
    if app._whatif_busy or app._whatif_running:
        return
    voiceover = app._current_voiceover_path()
    if voiceover is None:
        M.messagebox.showinfo("What If", "Choose the voiceover first: the shots are timed by the narrator's words.")
        return
    script = app._main_script_text() or ""
    if not script.strip():
        M.messagebox.showinfo("What If", "Paste your script on the Script page first: the shots are planned from what the narrator says.")
        return
    ws = app._workspace
    model, state_dir = app.model_var.get().strip() or "base", getattr(ws, "state_dir", None)
    p = current_csv(app)
    video = flow_video(app)
    title = getattr(ws, "title", "") or ""
    app._whatif_busy = True
    app._whatif_status_var.set("Planning the shots from the narration…")
    app._sync_primary_cta()
    log = lambda m: app.after(0, lambda: app._append_log(f"{m}\n"))  # noqa: E731

    def worker() -> None:
        plan = None
        try:
            from pakmap.app_integration import voiceover_duration

            from .app_integration import check_text, plan_from

            words = app._pakmap_get_words(voiceover, model, state_dir, log)
            dur = voiceover_duration(voiceover)
            csv_text = p.read_text(encoding="utf-8") if p else ""
            text, ok = check_text(words, script, dur, title, csv_text, flow_video=video)
            if ok:
                plan = plan_from(words, script, dur, title, csv_text, flow_video=video)
        except Exception as exc:
            text, ok = f"The plan could not be made: {exc}", False
        app.after(0, lambda: done(text, ok, plan))

    def done(text: str, ok: bool, plan) -> None:
        app._whatif_busy = False
        app._whatif_ok = ok
        app._whatif_plan = plan
        set_text(app, text)
        if ok and plan is not None:
            populate_visual_plan(app, plan)
        app._whatif_status_var.set("Plan ready: review the pictures in the Visual Plan (or let Generate find them), then Generate." if ok
                                   else "The plan has errors (see above): fix the CSV, save it, and Load it again.")
        app._sync_primary_cta()

    threading.Thread(target=worker, daemon=True).start()


# ---- Generate ----------------------------------------------------------------------------------------------------------------
def sync_cta(app) -> None:
    if app._whatif_busy:
        app._cta_action = "none"
        app._set_generate_btn(state="disabled", text="Working…")
        return
    if app._whatif_running:
        app._cta_action = "whatif_cancel"
        app.stage_var.set("GENERATING")
        if app._whatif_cancel.is_set():
            app.hint_var.set("Stopping…")
            app._set_generate_btn(state="disabled", text="Stopping…")
        else:
            app.hint_var.set("Generating — click Stop to cancel.")
            app._set_generate_btn(state="normal", text="Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._current_voiceover_path() is None:
        app._cta_action = "import_audio"
        app.stage_var.set("PLAN")
        app.hint_var.set("Select or import a voiceover to continue.")
        app._set_generate_btn(state="normal", text="Import Voiceover")
        return
    app._cta_action = "generate"
    app.stage_var.set("GENERATE")
    app.hint_var.set("Ready — click Generate to render the What If video." if app._whatif_ok is not False
                     else "The last plan had problems: fix the CSV and Plan the shots again.")
    app._set_generate_btn(state="normal", text="Generate")


def cancel(app) -> None:
    if not app._whatif_running or app._whatif_cancel.is_set():
        return
    app._whatif_cancel.set()
    app._append_log(f"{TAG} Stop requested — cancelling the current step…\n")
    manager = getattr(app, "_whatif_run_manager", None)
    if manager is not None:
        try:
            manager.request_cancel()
        except Exception as exc:
            app._append_log(f"{TAG} Could not signal the picture batch to stop: {exc}\n")
    try:
        from hardware.process_registry import get_registry

        from .engine_runner import OWNER

        get_registry().terminate_owned(owner=OWNER)
    except Exception as exc:
        app._append_log(f"{TAG} Could not stop the running renderer: {exc}\n")
    app._sync_primary_cta()


def run_generation(app) -> None:
    """The What If branch of the SHARED _on_generate() entry point (generation_mode == "whatif")."""
    M = _m(app)
    if app._whatif_running or app._whatif_busy:
        return
    if app._workspace is None:
        M.messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    voiceover_path = app._current_voiceover_path()
    if voiceover_path is None:
        M.messagebox.showerror("Cannot start", "Select or import a voiceover first.")
        return
    script = app._main_script_text() or ""
    if not script.strip():
        M.messagebox.showerror("Cannot start", "Paste your script on the Script page first: the shots are planned from what the narrator says.")
        return
    ws = app._workspace
    output_path = ws.next_final_path()
    app.output_var.set(str(output_path))
    whisper_model = app.model_var.get().strip() or "base"
    whisper_state_dir = getattr(ws, "state_dir", None)
    sound_design = bool(app._whatif_sound_var.get())
    video = flow_video(app)
    pixel_scale = app._export_pixel_scale()
    title = getattr(ws, "title", "") or ""
    pexels_api_key = app.pexels_key_var.get().strip() or os.environ.get("PEXELS_API_KEY", "")
    plan_rows = list(app._scene_rows) if getattr(app, "_scene_rows_owner", None) == MODE else None
    save_visual_plan(app)                  # the rows as the author left them, for the next time the project is opened
    imgs = images_dir(ws)
    csv_file = current_csv(app)
    flow_engine_manager, flow_video_account_ids, flow_settings = None, None, None
    # Flow credits: asked once per run for what is new (pictures already saved, or replaced in the Visual Plan, are reused)
    try:
        from asset_manager import AssetManifest as _Manifest
        man = _Manifest(imgs) if imgs.is_dir() else None
        new_flow = [r for r in (plan_rows or []) if M.SceneAssetRouter.classify(r) in (M.AssetSource.FLOW_IMAGE, M.AssetSource.FLOW_VIDEO)
                    and not (man is not None and (man.get(r.scene_number) or {}).get("status") == "complete")]
    except Exception:
        new_flow = []
    if new_flow:
        if not M.messagebox.askyesno("Generate pictures with Flow?",
                                     f"{len(new_flow)} picture(s)/clip(s) in this plan will be generated with Flow:\n\n"
                                     + "\n".join(f"- {(r.prompt or r.stock)[:70]}" for r in new_flow[:6]) + ("\n- ..." if len(new_flow) > 6 else "")
                                     + "\n\nPictures already saved (or replaced in the Visual Plan) are reused. Continue?"):
            return
    if new_flow or plan_rows is None:
        flow_engine_manager = app._get_flow_engine_manager()
        flow_video_account_ids = app._video_account_ids()
        try:
            flow_settings = app._media_flow_run_settings()
        except Exception:
            flow_settings = None

    app._whatif_cancel.clear()
    app._whatif_running = True
    app._whatif_tracking = app._track_generation_start(MODE)
    app._whatif_run_manager = None
    app._sync_primary_cta()
    app._whatif_status_var.set("Starting What If generation…")
    app._append_log("Starting What If generation…\n")

    def progress_cb(message: str, fraction: float) -> None:
        def apply() -> None:
            app._whatif_status_var.set(f"{message} ({int(fraction * 100)}%)")
            app.hint_var.set(f"{message} ({int(fraction * 100)}%)")
        app.after(0, apply)

    def thread_safe_log(message: str) -> None:
        app.after(0, lambda: app._append_log(f"{message}\n"))

    def _scene_start(scene, source) -> None:
        kind = "waiting" if source in (M.AssetSource.FLOW_IMAGE, M.AssetSource.FLOW_VIDEO) else M._scene_busy_kind(source)
        app._ui_queue.put(("scene_busy", (scene.scene_number, kind)))

    def _scene_generating(scene) -> None:
        app._ui_queue.put(("scene_busy", (scene.scene_number, "generating")))

    def _scene_complete(scene, result) -> None:
        app._ui_queue.put(("scene_asset", (scene.scene_number, result)))

    def _on_plan(plan) -> None:
        if plan_rows is not None:       # the author's Visual Plan is already there (and may hold their replacements): keep it
            return
        from .app_integration import visual_dicts

        dicts = visual_dicts(plan)      # listed here, on the worker thread, before the fetch touches the shots
        app.after(0, lambda: populate_visual_plan(app, dicts=dicts))
        thread_safe_log(f"{TAG} {len(dicts)} picture(s)/clip(s) in this plan; they are listed in the Visual Plan")

    def _manager_ready(manager) -> None:
        app._apply_footage_quality(manager)
        app._asset_manager = manager
        app._whatif_run_manager = manager

    def worker() -> None:
        from pakmap.app_integration import PakmapResult

        from .app_integration import generate_whatif_video

        prun = app._production_begin(MODE)
        try:
            try:
                words = app._pakmap_get_words(voiceover_path, whisper_model, whisper_state_dir, thread_safe_log)
            except Exception as exc:
                result = PakmapResult(False, [f"Could not transcribe the narration: {exc}"])
            else:
                result = generate_whatif_video(
                    voiceover_path, output_path, work_dir=work_dir(ws), whisper_words=words, images_dir=imgs, script=script, csv_path=csv_file, title=title,
                    scene_rows=plan_rows, sound_design=sound_design, pixel_scale=pixel_scale, flow_video=video, progress_cb=progress_cb, log=thread_safe_log,
                    cancel_check=app._whatif_cancel.is_set,
                    media_callbacks=dict(on_scene_start=_scene_start, on_scene_complete=_scene_complete, on_scene_generating=_scene_generating,
                                         on_manager_ready=_manager_ready),
                    pexels_api_key=pexels_api_key, flow_engine_manager=flow_engine_manager, flow_settings=flow_settings,
                    flow_video_account_ids=flow_video_account_ids, on_plan=_on_plan,
                )
        except Exception as exc:
            missing = getattr(exc, "filename", None)
            result = PakmapResult(False, [f"Unexpected error: {exc!r}" + (f" — {missing}" if missing else "")])
        app._production_end(prun, result, app._whatif_cancel.is_set())
        app.after(0, lambda: finish(result))

    def finish(result) -> None:
        app._whatif_running = False
        cancelled = bool(getattr(result, "cancelled", False)) or app._whatif_cancel.is_set()
        app._whatif_cancel.clear()
        run, app._whatif_tracking = app._whatif_tracking, None
        app._track_generation_end(run, "cancelled" if (cancelled and not result.ok) else ("completed" if result.ok else "failed"),
                                  output_path=result.output_path, validated=True, message="\n".join(str(e) for e in (result.errors or [])))
        if cancelled and not result.ok:
            app._whatif_status_var.set("Cancelled")
            app._append_log(f"{TAG} Generation cancelled. Nothing was exported; Generate again to restart.\n")
            app._sync_primary_cta()
            return
        if result.ok:
            app._whatif_status_var.set(f"Done: {result.output_path}")
            app._append_log(f"{TAG} Final video: {result.output_path}\n")
            for credit in result.credits:
                app._append_log(f"{TAG} Credit to include: {credit}\n")
            for w in result.warnings:
                app._append_log(f"{TAG} note: {w}\n")
            app._last_output = str(result.output_path)
            try:
                app._show_preview(str(result.output_path))
            except Exception:
                pass
            left = list(getattr(result, "unresolved", None) or [])
            extra = (f"\n\n{len(left)} picture(s)/clip(s) could not be fetched; those shots use a fallback (scene {', '.join(left[:8])}"
                     f"{' …' if len(left) > 8 else ''}). Fix them in the Visual Plan tab and Generate again to add them." if left else "")
            if left:
                app._refresh_qa_ui(immediate=True)
            M.messagebox.showinfo("What If video ready", f"Saved to:\n{result.output_path}\n\nCredits for the video description are saved next to it ('… - credits.txt')." + extra)
        else:
            app._append_log(f"{TAG} Generation failed:\n" + "\n".join(result.errors) + "\n")
            set_text(app, "Generation stopped:\n\n" + "\n".join(f"  {e}" for e in result.errors))
            app._whatif_status_var.set("Failed — see the plan box and the log")
            app._show_error_dialog("Generation failed", M.overscaled_failure_summary(result.errors), "\n".join(result.errors) or "Unknown error")
        app._sync_primary_cta()

    threading.Thread(target=worker, daemon=True).start()
