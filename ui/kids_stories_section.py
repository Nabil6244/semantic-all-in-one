"""Kids Stories: its own style page for the 2D cartoon channels (Ms Molly, Channel 3 play adventures with Ms Lina...).
Claude writes each episode and packs it into one .kidstory file (cartoon2d/kidstory.py); the owner picks that file here.
Generate voices every line and checks the story rules; Render draws the video (several pieces at once), mixes music and
sounds and puts the mp4 in the project's final folder. All the work lives in cartoon2d/runner.py, imported only inside
the button handlers. Nothing starts until Generate: picking a file or an option only remembers it. No Gemini, no Flow.

Each project remembers this page (state/kids_stories/settings.json).

app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_ks_block` / `_ks_running` / `_ks_active`."""

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

STYLE = "Kids Stories"
TAG = "[KIDS STORIES]"
RESOLUTIONS = {"Final quality": False, "Fast (quicker encode, a little larger)": True}
_ROOT = Path(__file__).resolve().parent.parent


VB_OWNER = "kids_stories"   # the pack's background pictures in the Visuals tab (visual_bridge.OWNERS)
_PIC = (".png", ".jpg", ".jpeg", ".webp")


def _files(work) -> dict:
    """{name: (picture, prompt)} for the backgrounds Generate unpacked into <work>/bg."""
    bg = Path(work) / "bg"
    if not bg.is_dir():
        return {}
    return {f.stem: (str(f), f"Story background: {f.stem.replace('_', ' ')}") for f in sorted(bg.iterdir())
            if f.suffix.lower() in _PIC and ".orig" not in f.stem}


def _fill_visuals(app: Any, work) -> None:
    """Main thread: the story's pictures into the Visuals tab (Retry / Change source / Local clip there are used at Render)."""
    try:
        import visual_bridge

        files = _files(work)
        if app._workspace is not None and files:
            visual_bridge.fill(app, VB_OWNER, visual_bridge.file_rows(visual_bridge.folder(VB_OWNER, app._workspace), files))
    except Exception as exc:  # noqa: BLE001 - the Visuals list never stops a video
        app._append_log(f"{TAG} Visuals tab: {type(exc).__name__}: {exc}\n")


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "cartoon2d"


def _runner():
    mod = sys.modules.get("ks_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("ks_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["ks_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("ks_runner", None)
        messagebox.showerror("Kids Stories is not installed", f"The cartoon2d folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._ks_plan_var = ctk.StringVar(value="")
    app._ks_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._ks_status_var = ctk.StringVar(value="")
    app._ks_cancel = threading.Event()
    app._ks_running = getattr(app, "_ks_running", False)
    app._ks_planned = None   # {"source", "work", "sig"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._ks_block = block

    body = section(block, 0, 1, "Story file", "a .kidstory file written for you")
    frow = ctk.CTkFrame(body, fg_color="transparent")
    frow.grid(row=0, column=0, sticky="ew")
    frow.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Story file", app._ks_plan_var, lambda: _browse(app), parent=frow,
                  placeholder_text="Choose a story (*.kidstory)")
    ctk.CTkLabel(frow, text="One file holds the whole episode: every line, who says it, the places and their pictures, the "
                            "rides, games, title cards and the goal counter. The cast (Ms Lina, Tobi, Rosie, Fizz, Pip, Dot, "
                            "Nia, Poppy, Ms Molly...) and all sounds are in the app; the voices are free.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Video", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._ks_res_var, width=280).grid(row=0, column=1)

    body = section(block, 2, 3, "Generate, then Render", "Generate voices the lines and checks the story; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._ks_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._ks_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._ks_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._ks_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._ks_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._ks_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._ks_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._ks_plan_var, app._ks_res_var):
        v.trace_add("write", lambda *_a: _changed(app))


def _source(app: Any) -> str:
    return app._ks_plan_var.get().strip()


def _changed(app: Any) -> None:
    """A pick changed: remember it; a Generate made for another file no longer counts. Nothing starts here."""
    p = getattr(app, "_ks_planned", None)
    if p and p["source"] != _source(app) and not getattr(app, "_ks_restoring", False):
        app._ks_planned = None
        _sync_buttons(app)
        app._sync_primary_cta()                      # the main button goes back to Generate
    _save(app)


def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "kids_stories" / "settings.json" if ws is not None else None


def _work_dir(app: Any, source: str) -> Path:
    """Where a story is unpacked, voiced and drawn: in the project, one folder per story (its voice cache is kept)."""
    return Path(app._workspace.state_dir) / "kids_stories" / (Path(source).stem or "story")


def _read_settings(app: Any) -> dict:
    f = _settings_file(app)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    """Remember the page for this project. Picks only: nothing is read or started here."""
    f = _settings_file(app)
    if f is None or getattr(app, "_ks_restoring", False) or getattr(app, "_ks_plan_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_ks_active", False)), "plan": app._ks_plan_var.get(),
                "res_label": app._ks_res_var.get(), "planned": getattr(app, "_ks_planned", None)}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_ks_restored_for", None) or getattr(app, "_ks_running", False):
        return
    app._ks_restored_for = key
    app._ks_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._ks_restoring = True
    try:
        app._ks_plan_var.set(d.get("plan", "") or "")
        if d.get("res_label") in RESOLUTIONS:
            app._ks_res_var.set(d["res_label"])
        p = d.get("planned")
        if (p and p.get("source") and p.get("sig") is not None and _sig(p["source"]) == p["sig"]
                and (Path(p.get("work", "")) / "build" / "audio" / "timeline.json").is_file()):
            app._ks_planned = p
            app._ks_status_var.set("Restored: voiced and checked. Click Render.")
    finally:
        app._ks_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse(app: Any) -> None:
    from tkinter import filedialog

    start = _engine_dir() / "stories"
    path = filedialog.askopenfilename(title="Choose the story", initialdir=str(start) if start.is_dir() else None,
                                      filetypes=[("Kids story", "*.kidstory"), ("All files", "*.*")])
    if path:
        app._ks_plan_var.set(path)   # remembered only: nothing is read until Generate


def activate(app: Any) -> None:
    if getattr(app, "_ks_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_ks_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._ks_active = True
    try:
        import visual_bridge

        visual_bridge.restore(app, VB_OWNER)      # this project's story pictures back in the Visuals tab
    except Exception:  # noqa: BLE001
        pass
    _restore(app)
    _save(app)
    app._ks_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_ks_active", False):
        app._ks_active = False
        try:
            import visual_bridge

            visual_bridge.clear(app, VB_OWNER)
        except Exception:  # noqa: BLE001
            pass
        if remember:
            _save(app)
        block = getattr(app, "_ks_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_ks_generate_btn", None) is None:
        return
    running = getattr(app, "_ks_running", False)
    app._ks_generate_btn.configure(state="disabled" if running else "normal")
    app._ks_render_btn.configure(state="normal" if (app._ks_planned and not running) else "disabled")
    app._ks_stop_btn.configure(state="normal" if running and not app._ks_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_ks_running", False):
        app._cta_action = "ks_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._ks_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._ks_planned:
        app._cta_action = "ks_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Voiced and checked. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "ks_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a story file (.kidstory), then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "ks_cancel":
        cancel(app)
    elif action == "ks_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_ks_running", False) or app._ks_cancel.is_set():
        return
    app._ks_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.ui_latest("style_progress", lambda: (app._ks_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._ks_cancel.clear()
    app._ks_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._ks_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._ks_running = False
            if error:
                app._ks_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._ks_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ks_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    source = _source(app)
    if not source or not Path(source).is_file():
        messagebox.showerror("Cannot start", "Choose the story file first." if not source else f"The story file is not there: {source}")
        return
    ks = _runner()
    if ks is None:
        return
    work = _work_dir(app, source)
    app._ks_planned = None
    _save(app)
    app._ks_status_var.set("Voicing and checking…")
    app._append_log(f"{TAG} Generate: {Path(source).name}\n")

    def job():
        return ks.generate(source, str(work), progress=_progress(app), cancel=app._ks_cancel.is_set, log=_log(app))

    def ready(g) -> None:
        app._ks_planned = {"source": source, "work": str(work), "sig": _sig(source)}
        _fill_visuals(app, work)
        m, sec = divmod(int(round(g["seconds"])), 60)
        msg = f"\"{g['title']}\": {g['lines']} lines, {m}:{sec:02d} long, {len(g['cast'])} characters."
        if g["problems"]:
            msg += f" The story checker found {len(g['problems'])} thing(s) (see the log); you can still Render."
            for pr in g["problems"]:
                app._append_log(f"{TAG} {pr}\n")
        else:
            msg += " Story rules OK."
        app._ks_status_var.set(msg + " Click Render.")
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "kids-stories-generate", job, ready)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ks_running", False):
        return
    ws, planned = app._workspace, app._ks_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a voiced and checked story.")
        return
    if _source(app) != planned["source"] or _sig(planned["source"]) != planned["sig"]:
        messagebox.showinfo("Click Generate first", "The story file changed after Generate. Click Generate again, then Render.")
        return
    ks = _runner()
    if ks is None:
        return
    draft = RESOLUTIONS.get(app._ks_res_var.get(), False)
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._ks_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}{' (fast)' if draft else ''}\n")
    run = app._track_generation_start("kids_stories")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._ks_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    import visual_bridge

    vb_dir, vb_rows = visual_bridge.folder(VB_OWNER, ws), visual_bridge.rows(app, VB_OWNER)   # read on the main thread

    def job():
        n = visual_bridge.apply_files(vb_dir, vb_rows, _files(planned["work"])) if vb_rows else 0
        if n:
            _log(app)(f"{TAG} {n} picture(s) from the Visuals tab")
        return ks.render(planned["work"], str(out_path), draft=draft, progress=_progress(app), cancel=app._ks_cancel.is_set,
                         log=_log(app))

    def done(r) -> None:
        m, sec = divmod(int(round(r["seconds"])), 60)
        msg = f"Done: {out_path.name} ({m}:{sec:02d})."
        app._ks_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "kids-stories-render", job, done, end)
