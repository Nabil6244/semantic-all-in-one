"""Voxel Map: its own style page (a story CSV, optional voice-over, resolution) with a Generate step that checks and plans the film and a
Render step that renders it (a block-world 3D map on the GPU: globe to ground, music, sound effects, voice). All the work lives in
voxelmap-engine/ (runner.py), imported only inside the button handlers. Nothing starts until Generate: picking files or options only
remembers them. The one download (elevation tiles for close-up terrain) is shown with its size and only happens after the user agrees.

Each project remembers this page (state/voxel_map/settings.json): reopening it comes back on the page with its files, options and, if
the files did not change, its planned film, so Render is ready. Finished terrain stays on disk, so Generate carries on from there.

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_vm_block` / `_vm_running` / `_vm_active`."""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import auto_render
from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Voxel Map"
TAG = "[VOXEL MAP]"
RESOLUTIONS = {"720p preview (1280x720)": 720, "1080p final (1920x1080)": 1080}
_ROOT = Path(__file__).resolve().parent.parent
OWNER = "voxel_map"      # its photo cards in the Visuals tab (visual_bridge)


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "voxelmap-engine"


def _cards():
    """voxelmap-engine/cards.py (photo cards), loaded once."""
    mod = sys.modules.get("vme_cards")
    if mod is None:
        spec = importlib.util.spec_from_file_location("vme_cards", _engine_dir() / "cards.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["vme_cards"] = mod
        spec.loader.exec_module(mod)
    return mod


def _assets_dir(app: Any) -> Path:
    import visual_bridge

    return visual_bridge.folder(OWNER, app._workspace)


def _story_with_cards(app: Any, o: dict, work: str, reqs: list) -> str:
    """The story CSV the engine reads: the user's rows + a card row for every picture the Visuals tab holds now (a picture swapped there is used).
    No cards, or none with a picture: the user's own CSV, unchanged."""
    if not reqs:
        return o["csv"]
    import visual_bridge

    cards = _cards()
    folder = _assets_dir(app)
    recs = visual_bridge.records(folder, visual_bridge.rows(app, OWNER) or cards.table_rows(reqs))
    paths = cards.paths_from(reqs, recs)
    if not paths:
        return o["csv"]
    return cards.write_story(o["csv"], str(Path(work) / "story_cards.csv"), reqs, paths, cards.credits(reqs, recs))


def _runner():
    """voxelmap-engine/runner.py (a folder name Python cannot import), loaded once; None with a message when it is missing."""
    mod = sys.modules.get("vme_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("vme_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["vme_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("vme_runner", None)
        messagebox.showerror("Voxel Map is not installed", f"The voxelmap-engine folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._vm_csv_var = ctk.StringVar(value="")
    app._vm_voice_var = ctk.StringVar(value="")
    app._vm_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._vm_status_var = ctk.StringVar(value="")
    app._vm_cancel = threading.Event()
    app._vm_running = getattr(app, "_vm_running", False)
    app._vm_planned = None   # {"csv", "voice", "res", "work"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._vm_block = block

    body = section(block, 0, 1, "Story", "a story CSV (plan / chapter / territory / label / beat rows)")
    app._path_row(0, "Story CSV", app._vm_csv_var, lambda: _browse(app, "csv"), parent=body,
                  placeholder_text="Choose the story CSV (format: voxelmap-engine/tools/story_prompt.md)")
    app._path_row(1, "Voice-over", app._vm_voice_var, lambda: _browse(app, "voice"), parent=body,
                  placeholder_text="Your narration (the camera moves fit its pauses). Without it the video has no sound.")
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=3, column=0, sticky="w", pady=(6, 0))
    app._vm_prompt_status = ctk.StringVar(value="")
    make_button(tools, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="sm", width=150).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._vm_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(body, text="Block-world map of real terrain, globe to ground. Samples: voxelmap-engine/samples/. "
                            "Close-up terrain needs a one-time elevation download: Generate shows its size and asks first.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._vm_res_var, width=220).grid(row=0, column=1, padx=(0, 16))

    body = section(block, 2, 3, "Generate, then Render", "Generate checks and plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._vm_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._vm_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._vm_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._vm_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._vm_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._vm_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._vm_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._vm_csv_var, app._vm_voice_var, app._vm_res_var):
        v.trace_add("write", lambda *_a: _save(app))


def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "voxel_map" / "settings.json" if ws is not None else None


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_vm_restoring", False) or getattr(app, "_vm_csv_var", None) is None:
        return
    try:
        planned = getattr(app, "_vm_planned", None)
        data = {"active": bool(getattr(app, "_vm_active", False)), "generating": bool(getattr(app, "_vm_generating", False)),
                "csv": app._vm_csv_var.get(), "voice": app._vm_voice_var.get(), "res_label": app._vm_res_var.get(), "planned": None}
        if planned:
            data["planned"] = {**planned, "sig_csv": _sig(planned["csv"]), "sig_voice": _sig(planned["voice"]) if planned["voice"] else None}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    """Put back this project's choices and, if its files did not change, its planned film. Starts nothing."""
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_vm_restored_for", None) or getattr(app, "_vm_running", False):
        return
    app._vm_restored_for = key
    app._vm_planned = None            # a plan belongs to one project
    d = _read_settings(app)
    if not d:
        return
    app._vm_restoring = True
    try:
        app._vm_csv_var.set(d.get("csv", "") or "")
        app._vm_voice_var.set(d.get("voice", "") or "")
        if d.get("res_label") in RESOLUTIONS:
            app._vm_res_var.set(d["res_label"])
        p = d.get("planned")
        if p and p.get("csv") and (Path(str(p.get("work", ""))) / "timeline.json").is_file():
            same_csv = p.get("sig_csv") is not None and _sig(p["csv"]) == p["sig_csv"]
            same_voice = (not p.get("voice")) or (p.get("sig_voice") is not None and _sig(p["voice"]) == p["sig_voice"])
            if same_csv and same_voice:
                app._vm_planned = {k: p.get(k) for k in ("csv", "voice", "res", "work", "cards")}
                app._vm_status_var.set("Restored: the film is planned. Click Render, or Generate to plan again.")
        if d.get("generating") and not app._vm_planned:
            app._vm_status_var.set("The last Generate did not finish. Click Generate: the terrain already built is kept and it carries on from there.")
    finally:
        app._vm_restoring = False


def resume_on_open(app: Any) -> None:
    """A project that was left on this page opens on it again."""
    if _read_settings(app).get("active"):
        app.after(0, lambda: app._on_style_pick(STYLE))


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    if kind == "csv":
        path = filedialog.askopenfilename(title="Choose the story CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._vm_csv_var
    else:
        path = filedialog.askopenfilename(title="Choose the voice-over", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._vm_voice_var
    if path:
        var.set(path)   # remembered only: nothing is read or planned until Generate
        app._vm_planned = None
        auto_render.stop(app, "vm")
        _save(app)
        _sync_buttons(app)



def copy_csv_prompt(app: Any) -> None:
    """Put the story-CSV writing prompt on the clipboard (paste it into any AI chat with your topic)."""
    p = _engine_dir().joinpath(*('tools', 'story_prompt.md'))
    status = app._vm_prompt_status
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        status.set(f"The CSV prompt is not there yet ({p.name}).")
        return
    try:
        app.clipboard_clear()
        app.clipboard_append(text)
        status.set("Copied. Paste it into your AI chat with your topic.")
    except Exception as exc:  # noqa: BLE001
        status.set(f"Could not copy: {exc}")


def activate(app: Any) -> None:
    if getattr(app, "_vm_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside, like Health Cinema and Product Trailer
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_vm_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._vm_active = True
    _restore(app)
    _save(app)
    from .voiceover_view import adopt_project_voiceover
    adopt_project_voiceover(app, app._vm_voice_var)   # the project voiceover (Voiceover tab / Audio & Effects) if this box is empty
    app._vm_block.grid()
    try:
        import visual_bridge

        visual_bridge.restore(app, OWNER)      # the photo cards of the last Generate, back in the Visuals tab
    except Exception:
        pass
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    """remember=False when a project is opening: the page was not left by choice, and the settings on disk may be another project's."""
    if getattr(app, "_vm_active", False):
        app._vm_active = False
        if remember:
            _save(app)
        try:
            import visual_bridge

            visual_bridge.clear(app, OWNER)
        except Exception:
            pass
        block = getattr(app, "_vm_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_vm_generate_btn", None) is None:
        return
    running = getattr(app, "_vm_running", False)
    app._vm_generate_btn.configure(state="disabled" if running else "normal")
    app._vm_render_btn.configure(state="normal" if (app._vm_planned and not running) else "disabled")
    waiting = auto_render.pending(app, "vm")      # Stop also cancels the auto-render countdown
    app._vm_stop_btn.configure(state="normal" if (running and not app._vm_cancel.is_set()) or waiting else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_vm_running", False):
        app._cta_action = "vm_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._vm_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._vm_planned:
        app._cta_action = "vm_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The film is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "vm_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a story CSV, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "vm_cancel":
        cancel(app)
    elif action == "vm_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if auto_render.stop(app, "vm", note="Auto-render cancelled: click Render when ready."):
        app._append_log(f"{TAG} Auto-render cancelled.\n")
        app._sync_primary_cta()
        return
    if not getattr(app, "_vm_running", False) or app._vm_cancel.is_set():
        return
    app._vm_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "voxel_map"
    d.mkdir(parents=True, exist_ok=True)
    return d


def options(app: Any) -> dict:
    return {"csv": app._vm_csv_var.get().strip(), "voice": app._vm_voice_var.get().strip(), "res": RESOLUTIONS.get(app._vm_res_var.get(), 720)}


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.after(0, lambda: (app._vm_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.after(0, lambda: app._append_log(m + "\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._vm_cancel.clear()
    app._vm_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._vm_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._vm_running = False
            if error:
                app._vm_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._vm_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_vm_running", False):
        return
    auto_render.stop(app, "vm")
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
    vm = _runner()
    if vm is None:
        return
    work = str(_work_dir(app) / "film")
    app._vm_planned = None
    _save(app)
    app._vm_status_var.set("Checking the story…")
    app._append_log(f"{TAG} Generate: checking the story\n")

    def job():
        c = vm.check(o["csv"], cancel=app._vm_cancel.is_set, log=_log(app))
        if c["errors"]:
            raise ValueError("The story has errors:\n" + "\n".join(c["errors"][:8]))
        return c

    def after_check(c) -> None:
        wb = c.get("world_build")
        if wb:      # the story's world is not built yet: build it around the story's places (one download), then check again
            if not messagebox.askyesno("Build the map world?", f"The story uses the world \"{wb['id']}\", which is not built yet.\n\n"
                                       f"Build it now around the story's places (lon {wb['bbox'][0]} to {wb['bbox'][2]}, lat {wb['bbox'][1]} to {wb['bbox'][3]})? "
                                       f"About {wb.get('download_mb_est', 0)} MB of elevation data to download, once; every later story there reuses it."):
                app._vm_status_var.set(f"Not started: world \"{wb['id']}\" is not built.")
                return
            app._vm_status_var.set(f"Building world \"{wb['id']}\"…")
            app._append_log(f"{TAG} building world {wb['id']} {wb['bbox']} ({wb.get('download_mb_est', 0)} MB)\n")
            _start(app, "voxel-map-world", lambda: (vm.build_world(wb, progress=_progress(app), cancel=app._vm_cancel.is_set, log=_log(app)), job())[1],
                   after_check)
            return
        tiles = c.get("detail_tiles") or {}
        if tiles.get("to_build"):
            mb = tiles.get("download_mb_est", 0)
            if not messagebox.askyesno("Download close-up terrain?", f"The close-up scenes need {tiles['to_build']} terrain tiles that are not built yet "
                                       f"(about {mb} MB to download, once). Download now?\n\nIf you stop or close the app, what is finished is kept and the next Generate carries on from there.\n\n"
                                       "No = plan anyway; those areas render with coarser terrain."):
                _plan(app, vm, o, work, prepare=False)
                return
            _plan(app, vm, o, work, prepare=True)
            return
        _plan(app, vm, o, work, prepare=False)

    _start(app, "voxel-map-check", job, after_check)


def _show_cards(app: Any, rows: list, ws: Any) -> None:
    """Main thread. The cards and whatever pictures they have so far, in the Visuals tab, while this project's page is still the one up."""
    import visual_bridge

    if app._workspace is ws and getattr(app, "_vm_active", False):
        visual_bridge.fill(app, OWNER, rows)


def _plan(app: Any, vm: Any, o: dict, work: str, *, prepare: bool) -> None:
    app._vm_status_var.set("Planning…")
    # photo cards: the CSV's own card rows, or cards planned from the narration; their pictures are fetched into the Visuals tab (no Gemini)
    reqs, manager, cards = [], None, None
    try:
        cards = _cards()
        reqs = cards.requests(o["csv"])
        if any(c.get("query") and not c.get("local") for c in reqs):
            manager = app._build_asset_manager(_assets_dir(app), [])      # built here: it reads Tk variables
    except Exception as exc:  # noqa: BLE001 - cards are an extra; the film is planned without them
        app._append_log(f"{TAG} photo cards skipped: {type(exc).__name__}: {exc}\n")
        reqs, manager = [], None
    holder: dict = {}
    ws = app._workspace
    listed = cards.table_rows(reqs) if reqs else []      # the cards are in the Visuals tab from the start; each picture appears as it lands
    if listed:
        _show_cards(app, listed, ws)

    def job():
        if prepare:
            vm.prepare(o["csv"], progress=_progress(app), cancel=app._vm_cancel.is_set, log=_log(app))
        story = o["csv"]
        if reqs:
            if manager is not None:
                holder["rows"] = cards.fetch(reqs, manager, _assets_dir(app), log=_log(app), cancel=app._vm_cancel.is_set, progress=_progress(app),
                                              on_picture=lambda: app.after(0, lambda: _show_cards(app, listed, ws)))
            else:
                holder["rows"] = cards.table_rows(reqs)
            story = _story_with_cards(app, o, work, reqs)
        return vm.plan(story, work, voiceover=o["voice"] or None, progress=_progress(app), cancel=app._vm_cancel.is_set, log=_log(app))

    def done(r) -> None:
        app._vm_planned = {"csv": o["csv"], "voice": o["voice"], "res": o["res"], "work": work, "cards": reqs}
        warn = f"  {len(r['warnings'])} notes (see the log)." if r["warnings"] else ""
        msg = (f"Planned {r['beats']} scenes, {r['duration']:.0f} s ({'camera timed to your voice-over' if r['voiceTimed'] else 'planned read, no voice-over: the video has no sound'}).{warn}")
        app._vm_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        auto_render.start(app, "vm", status_var=app._vm_status_var, still_ok=lambda p=app._vm_planned: _auto_render_ok(app, p),
                          render=lambda: on_render(app), tag=TAG)

    def end(_error: str) -> None:
        app._vm_generating = False
        if holder.get("rows"):
            _show_cards(app, holder["rows"], ws)      # check or change the pictures there; Render uses what the tab holds
        _save(app)

    app._vm_generating = True     # closed before this ends: reopening says Generate carries on from the finished terrain
    _save(app)
    _start(app, "voxel-map-plan", job, done, end)


def _auto_render_ok(app: Any, plan: dict) -> str:
    """Why the auto-render must not start ("" = it may): the same plan is still there, nothing runs, the options match it."""
    if app._vm_planned is not plan or app._workspace is None:
        return "the plan changed; click Generate again."
    if getattr(app, "_vm_running", False):
        return "another job is running."
    o = options(app)
    if (o["csv"], o["voice"], o["res"]) != (plan["csv"], plan["voice"], plan["res"]):
        return "the story or options changed after Generate; click Generate again."
    return ""


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_vm_running", False):
        return
    auto_render.stop(app, "vm")
    ws, plan = app._workspace, app._vm_planned
    if ws is None or not plan:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned film.")
        return
    vm = _runner()
    if vm is None:
        return
    o = options(app)
    if (o["csv"], o["voice"], o["res"]) != (plan["csv"], plan["voice"], plan["res"]):
        messagebox.showinfo("Click Generate first", "You changed the story or options after Generate. Click Generate again, then Render.")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._vm_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("voxel_map")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._vm_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        story = _story_with_cards(app, o, plan["work"], plan.get("cards") or [])      # the pictures the Visuals tab holds now
        return vm.render(story, plan["work"], voiceover=plan["voice"] or None, output=str(out_path), resolution=plan["res"],
                         progress=_progress(app), cancel=app._vm_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name}" + ("  (no voice-over: no sound)" if r.get("silent") else "")
        app._vm_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "voxel-map-render", job, done, end)
