"""Senior Trivia: its own style page. A Senior Trivia CSV -> a calm, long quiz show for American viewers 60+ (rounds with
painted vintage pictures, a countdown, the answer reveal and a fun fact; or an old-items picture quiz), with the host Hal in
5-6 Flow talking clips.

Generate = Flow pictures (free) + Hal's clips (Flow video credits, made once per line) + the free Edge announcer voice +
the timeline. Render = the video in the project's final folder. All work lives in senior_trivia/runner.py, imported only
inside the button handlers. Nothing starts until Generate. A CSV run makes no Gemini calls.

Each project remembers this page (state/senior_trivia/settings.json, the plan in state/senior_trivia/plan.json).
app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_st_block` / `_st_running` / `_st_active`."""

from __future__ import annotations

import importlib
import json
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Senior Trivia"
TAG = "[SENIOR TRIVIA]"
VOICES = {"Andrew (US, calm man)": "en-US-AndrewNeural", "Brian (US)": "en-US-BrianNeural", "Guy (US)": "en-US-GuyNeural",
          "Jenny (US, warm woman)": "en-US-JennyNeural", "Aria (US)": "en-US-AriaNeural"}
HOST = {"Hal in talking clips (Flow video credits, made once)": True, "No host clips (his lines over a picture)": False}
RESOLUTIONS = {"1080p final": False, "720p fast preview": True}
_ROOT = Path(__file__).resolve().parent.parent
VB_OWNER = "senior_trivia"   # its Flow pictures in the Visuals tab (visual_bridge.OWNERS)


def _fill_visuals(app: Any, spec: dict) -> None:
    try:
        import visual_bridge

        if app._workspace is not None:
            visual_bridge.fill(app, VB_OWNER, visual_bridge.spec_rows(visual_bridge.folder(VB_OWNER, app._workspace), spec))
    except Exception as exc:  # noqa: BLE001 - the Visuals list never stops a video
        app._append_log(f"{TAG} Visuals tab: {type(exc).__name__}: {exc}\n")


def _runner():
    try:
        base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        return importlib.import_module("senior_trivia.runner")
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Senior Trivia is not installed", f"The senior_trivia folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _label(parent, text, row, col=0):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=row, column=col, padx=(0, 8), sticky="w")


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._st_csv_var = ctk.StringVar(value="")
    app._st_title_var = ctk.StringVar(value="")
    app._st_edge_var = ctk.StringVar(value=next(iter(VOICES)))
    app._st_host_var = ctk.StringVar(value=next(iter(HOST)))
    app._st_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._st_status_var = ctk.StringVar(value="")
    app._st_cancel = threading.Event()
    app._st_running = getattr(app, "_st_running", False)
    app._st_planned = None

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._st_block = block

    body = section(block, 0, 1, "Quiz", "a Senior Trivia CSV (senior_trivia/csv_prompt.txt writes one)")
    rows = ctk.CTkFrame(body, fg_color="transparent")
    rows.grid(row=0, column=0, sticky="ew")
    rows.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Senior Trivia CSV", app._st_csv_var, lambda: _browse(app), parent=rows,
                  placeholder_text="type, round, question, options, answer, fact, picture, fact_picture, line, seconds")
    ctk.CTkEntry(rows, textvariable=app._st_title_var, height=34,
                 placeholder_text="Title on screen (optional): empty = the intro row's title").grid(row=1, column=0, sticky="ew", pady=(8, 0))
    ctk.CTkLabel(body, text="Rows in order: intro, host, round, question (4 options, the right letter, a fun fact, a picture), "
                            "check after each round, bonus, outro, host goodbye, thumbnail. Or item rows for an old-items "
                            "picture quiz. The checker lists any wrong answer, duplicate or thin round in the log.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 0))

    body = section(block, 1, 2, "Voice, host and look")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="w")
    _label(out, "Announcer", 0)
    ctk.CTkOptionMenu(out, values=list(VOICES), variable=app._st_edge_var, width=240).grid(row=0, column=1, sticky="w")
    _label(out, "Host", 1)
    ctk.CTkOptionMenu(out, values=list(HOST), variable=app._st_host_var, width=380).grid(row=1, column=1, pady=(8, 0), sticky="w")
    _label(out, "Resolution", 2)
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._st_res_var, width=180).grid(row=2, column=1, pady=(8, 0), sticky="w")
    ctk.CTkLabel(body, text="Hal is only ever shown in his own talking clips (never a still); a line whose clip Flow could not "
                            "make plays over its scene picture. Pictures are made once and kept for later episodes.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=1, column=0, sticky="w", pady=(6, 0))

    body = section(block, 2, 3, "Generate, then Render", "Generate makes the pictures, Hal's clips, the voice and the timing; Render draws the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._st_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._st_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._st_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._st_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._st_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._st_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._st_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._st_csv_var, app._st_title_var, app._st_edge_var, app._st_host_var, app._st_res_var):
        v.trace_add("write", lambda *_a: _changed(app))


# ------------------------------------------------------------------ picks
def _fsig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _picks(app: Any) -> dict:
    return {"csv": app._st_csv_var.get().strip(), "title": app._st_title_var.get().strip(), "edge": app._st_edge_var.get(),
            "host": app._st_host_var.get(), "res": app._st_res_var.get()}


def _sig(app: Any) -> list:
    p = _picks(app)
    return [p["title"], p["edge"], p["host"], p["res"], _fsig(p["csv"]) if p["csv"] else None]


def _changed(app: Any) -> None:
    """A pick changed: remember it; a Generate made for other picks no longer counts. Nothing starts here."""
    p = getattr(app, "_st_planned", None)
    if p and p["sig"] != _sig(app) and not getattr(app, "_st_restoring", False):
        app._st_planned = None
        _sync_buttons(app)
        app._sync_primary_cta()
    _save(app)


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "senior_trivia" if ws is not None else None


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    d = _state_dir(app)
    if d is None or getattr(app, "_st_restoring", False) or getattr(app, "_st_csv_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_st_active", False)), "picks": _picks(app), "planned": getattr(app, "_st_planned", None)}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_st_restored_for", None) or getattr(app, "_st_running", False):
        return
    app._st_restored_for = key
    app._st_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._st_restoring = True
    try:
        p = d.get("picks") or {}
        for var, k, allowed in ((app._st_csv_var, "csv", None), (app._st_title_var, "title", None), (app._st_edge_var, "edge", VOICES),
                                (app._st_host_var, "host", HOST), (app._st_res_var, "res", RESOLUTIONS)):
            v = p.get(k)
            if v is not None and (allowed is None or v in allowed):
                var.set(v)
        pl = d.get("planned")
        if pl and pl.get("sig") == _sig(app) and Path(pl.get("plan", "")).is_file():
            app._st_planned = pl
            app._st_status_var.set("Restored: planned and ready. Click Render.")
    finally:
        app._st_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


def _browse(app: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose the Senior Trivia CSV", filetypes=[("Senior Trivia CSV", "*.csv"), ("All files", "*.*")])
    if path:   # remembered only: nothing is read until Generate
        app._st_csv_var.set(path)


# ------------------------------------------------------------------ page
def activate(app: Any) -> None:
    if getattr(app, "_st_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_st_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._st_active = True
    _restore(app)
    _save(app)
    try:
        import visual_bridge

        visual_bridge.restore(app, VB_OWNER)
    except Exception:  # noqa: BLE001
        pass
    app._st_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_st_active", False):
        app._st_active = False
        try:
            import visual_bridge

            visual_bridge.clear(app, VB_OWNER)
        except Exception:  # noqa: BLE001
            pass
        if remember:
            _save(app)
        block = getattr(app, "_st_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_st_generate_btn", None) is None:
        return
    running = getattr(app, "_st_running", False)
    app._st_generate_btn.configure(state="disabled" if running else "normal")
    app._st_render_btn.configure(state="normal" if (app._st_planned and not running) else "disabled")
    app._st_stop_btn.configure(state="normal" if running and not app._st_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_st_running", False):
        app._cta_action = "st_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._st_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._st_planned:
        app._cta_action = "st_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Planned. Click Render to draw the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "st_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a Senior Trivia CSV, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "st_cancel":
        cancel(app)
    elif action == "st_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_st_running", False) or app._st_cancel.is_set():
        return
    app._st_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.ui_latest("style_progress", lambda: (app._st_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._st_cancel.clear()
    app._st_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._st_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._st_running = False
            if error:
                app._st_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._st_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_st_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    p = _picks(app)
    if not p["csv"]:
        messagebox.showerror("Cannot start", "Choose a Senior Trivia CSV first.")
        return
    if not Path(p["csv"]).is_file():
        messagebox.showerror("Cannot start", f"The CSV is not there: {p['csv']}")
        return
    rn = _runner()
    if rn is None:
        return
    app._st_planned = None
    _save(app)
    sig = _sig(app)
    plan_path = _state_dir(app) / "plan.json"
    app._st_status_var.set("Generating: pictures, Hal's clips, the voice and the timing…")
    app._append_log(f"{TAG} Generate: pictures, host clips, voice\n")

    def job():
        spec = rn.plan(p["csv"], voice=VOICES.get(p["edge"], "en-US-AndrewNeural"), host_clips=HOST.get(p["host"], True),
                       title=p["title"] or None, preview=RESOLUTIONS.get(p["res"], False), log=_log(app), cancel=app._st_cancel.is_set)
        rn.save(spec, plan_path)
        return spec

    def ready(spec) -> None:
        app._st_planned = {"sig": sig, "plan": str(plan_path)}
        _fill_visuals(app, spec)
        qs = sum(1 for s in spec["segs"] if s["kind"] in ("question", "item"))
        clips = sum(1 for s in spec["segs"] if s["kind"] == "host" and s.get("clip"))
        hosts = sum(1 for s in spec["segs"] if s["kind"] == "host")
        made, need = len(spec["assets"]["pictures"]), len(spec["pictures"])
        miss = f"; {need - made} picture(s) not made yet (text cards; Generate again to retry)" if made < need else ""
        notes = f"; {len(spec['problems'])} CSV note(s) in the log" if spec.get("problems") else ""
        msg = (f"{qs} questions, ~{spec['duration'] / 60:.1f} min, Hal in {clips}/{hosts} clip(s), {made}/{need} pictures"
               f"{miss}{notes}. Click Render.")
        app._st_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "senior-trivia-plan", job, ready)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_st_running", False):
        return
    ws, planned = app._workspace, app._st_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a plan.")
        return
    if planned["sig"] != _sig(app):
        messagebox.showinfo("Click Generate first", "You changed the CSV or options after Generate. Click Generate again, then Render.")
        return
    rn = _runner()
    if rn is None:
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._st_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("senior_trivia")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._st_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    import visual_bridge

    vb_dir, vb_rows = visual_bridge.folder(VB_OWNER, ws), visual_bridge.rows(app, VB_OWNER)   # read on the main thread

    def job():
        spec = rn.refresh_assets(rn.load(planned["plan"]))
        n = visual_bridge.apply_spec(vb_dir, vb_rows, spec) if vb_rows else 0
        if n:
            _log(app)(f"{n} picture(s) from the Visuals tab")
        return rn.render(spec, str(out_path), progress=_progress(app), cancel=app._st_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name} ({r['seconds'] / 60:.1f} min)."
        app._st_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "senior-trivia-render", job, done, end)
