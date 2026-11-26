"""Reddit Shorts: its own style page. A Reddit-style story -> a 9:16 Short: the post card while the title is read, then big
word captions (the spoken word in yellow) over cartoon pictures that match the narration, each cut in on its words.

Generate = the free Edge voice + Flow pictures (free, made once per story). Render = the Short in the project's final folder.
All work lives in reddit_shorts/runner.py, imported only inside the button handlers. Nothing starts until Generate. No Gemini.

Each project remembers this page (state/reddit_shorts/settings.json, the plan in state/reddit_shorts/plan.json).
app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_rs_block` / `_rs_running` / `_rs_active`."""

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

STYLE = "Reddit Shorts"
TAG = "[REDDIT SHORTS]"
OWN = "My own story"
_ROOT = Path(__file__).resolve().parent.parent
VB_OWNER = "reddit_shorts"   # its Flow pictures in the Visuals tab (visual_bridge.OWNERS)


def _engine(name: str):
    try:
        base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        return importlib.import_module(f"reddit_shorts.{name}")
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Reddit Shorts is not installed", f"The reddit_shorts folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _builtins() -> dict:
    """{menu label: story id} of the ready-made stories (their pictures are painted once and shared by every project)."""
    st = _engine("stories")
    if st is None:
        return {}
    return {f"{i + 1:02d}. {s['title'][:70]}": s["id"] for i, s in enumerate(st.STORIES)}


def _voices() -> dict:
    s = _engine("story")
    return dict(s.VOICES) if s is not None else {"Andrew (US man)": "en-US-AndrewNeural"}


def _fill_visuals(app: Any, spec: dict) -> None:
    try:
        import visual_bridge

        if app._workspace is not None:
            visual_bridge.fill(app, VB_OWNER, visual_bridge.spec_rows(visual_bridge.folder(VB_OWNER, app._workspace), spec))
    except Exception as exc:  # noqa: BLE001 - the Visuals list never stops a video
        app._append_log(f"{TAG} Visuals tab: {type(exc).__name__}: {exc}\n")


def _label(parent, text, row, col=0):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=row, column=col, padx=(0, 8), pady=(8, 0), sticky="nw")


def _hint(parent, text, row):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=row, column=0, sticky="w", pady=(6, 0))


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._rs_builtin = _builtins()
    app._rs_voice_map = _voices()
    app._rs_story_var = ctk.StringVar(value=OWN)
    app._rs_title_var = ctk.StringVar(value="")
    app._rs_sub_var = ctk.StringVar(value="AmITheJerk")
    app._rs_cast_var = ctk.StringVar(value="")
    app._rs_voice_var = ctk.StringVar(value=next(iter(app._rs_voice_map)))
    app._rs_status_var = ctk.StringVar(value="")
    app._rs_cancel = threading.Event()
    app._rs_running = getattr(app, "_rs_running", False)
    app._rs_planned = None

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._rs_block = block

    body = section(block, 0, 1, "Story", "one of the ready stories, or paste your own")
    pick = ctk.CTkFrame(body, fg_color="transparent")
    pick.grid(row=0, column=0, sticky="ew")
    _label(pick, "Story", 0)
    ctk.CTkOptionMenu(pick, values=[OWN] + list(app._rs_builtin), variable=app._rs_story_var, width=520,
                      dynamic_resizing=False).grid(row=0, column=1, pady=(8, 0), sticky="w")
    own = ctk.CTkFrame(body, fg_color="transparent")
    own.grid(row=1, column=0, sticky="ew", pady=(6, 0))
    own.grid_columnconfigure(1, weight=1)
    app._rs_own = own
    _label(own, "Title", 0)
    ctk.CTkEntry(own, textvariable=app._rs_title_var, height=34,
                 placeholder_text="Am I the jerk for refusing to give my sister the house our grandma left me?").grid(row=0, column=1, sticky="ew", pady=(8, 0))
    _label(own, "Community", 1)
    ctk.CTkEntry(own, textvariable=app._rs_sub_var, height=34, width=260,
                 placeholder_text="AmITheJerk").grid(row=1, column=1, sticky="w", pady=(8, 0))
    _label(own, "Story", 2)
    app._rs_body_box = ctk.CTkTextbox(own, height=180, wrap="word")
    app._rs_body_box.grid(row=2, column=1, sticky="ew", pady=(8, 0))
    _label(own, "Characters", 3)
    ctk.CTkEntry(own, textvariable=app._rs_cast_var, height=34,
                 placeholder_text="Narrator: young woman, short brown hair, green sweater; Sister: long blonde hair, red coat").grid(row=3, column=1, sticky="ew", pady=(8, 0))
    _hint(body, "About 150 words make a 55 s Short. Write it as 'I' (the narrator). Characters is optional: name each person "
                "the way the story calls them (Narrator, Sister, Boss...) so every picture draws them the same; a person not "
                "in a moment is kept out of its picture. Ready stories already have hand-made picture moments.", 2)

    body = section(block, 1, 2, "Voice")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="w")
    _label(out, "Narrator", 0)
    ctk.CTkOptionMenu(out, values=list(app._rs_voice_map), variable=app._rs_voice_var, width=240).grid(row=0, column=1, pady=(8, 0), sticky="w")
    _hint(body, "Free Edge voice at a quick Shorts pace. Ready stories use their own voice.", 1)

    body = section(block, 2, 3, "Generate, then Render", "Generate makes the voice and the pictures; Render draws the Short")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._rs_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._rs_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._rs_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._rs_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._rs_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._rs_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._rs_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()
    for v in (app._rs_story_var, app._rs_title_var, app._rs_sub_var, app._rs_cast_var, app._rs_voice_var):
        v.trace_add("write", lambda *_a: _changed(app))
    app._rs_body_box.bind("<KeyRelease>", lambda _e: _changed(app))
    app._rs_body_box.bind("<<Paste>>", lambda _e: app.after(50, lambda: _changed(app)))
    _show_own(app)


def _show_own(app: Any) -> None:
    own = getattr(app, "_rs_own", None)
    if own is not None:
        own.grid() if app._rs_story_var.get() == OWN else own.grid_remove()


# ------------------------------------------------------------------ picks
def _body(app: Any) -> str:
    box = getattr(app, "_rs_body_box", None)
    return box.get("1.0", "end").strip() if box is not None else ""


def _picks(app: Any) -> dict:
    return {"story": app._rs_story_var.get(), "title": app._rs_title_var.get().strip(), "sub": app._rs_sub_var.get().strip(),
            "body": _body(app), "cast": app._rs_cast_var.get().strip(), "voice": app._rs_voice_var.get()}


def _sig(app: Any) -> list:
    p = _picks(app)
    if p["story"] != OWN:
        return [p["story"]]
    return [p["story"], p["title"], p["sub"], p["body"], p["cast"], p["voice"]]


def _changed(app: Any) -> None:
    """A pick changed: remember it; a Generate made for other picks no longer counts. Nothing starts here."""
    _show_own(app)
    p = getattr(app, "_rs_planned", None)
    if p and p["sig"] != _sig(app) and not getattr(app, "_rs_restoring", False):
        app._rs_planned = None
        _sync_buttons(app)
        app._sync_primary_cta()
    _save(app)


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "reddit_shorts" if ws is not None else None


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    d = _state_dir(app)
    if d is None or getattr(app, "_rs_restoring", False) or getattr(app, "_rs_story_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_rs_active", False)), "picks": _picks(app), "planned": getattr(app, "_rs_planned", None)}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_rs_restored_for", None) or getattr(app, "_rs_running", False):
        return
    app._rs_restored_for = key
    app._rs_planned = None
    d = _read_settings(app)
    if not d:
        return
    app._rs_restoring = True
    try:
        p = d.get("picks") or {}
        for var, k, allowed in ((app._rs_story_var, "story", [OWN] + list(app._rs_builtin)), (app._rs_title_var, "title", None),
                                (app._rs_sub_var, "sub", None), (app._rs_cast_var, "cast", None), (app._rs_voice_var, "voice", app._rs_voice_map)):
            v = p.get(k)
            if v is not None and (allowed is None or v in allowed):
                var.set(v)
        if p.get("body") is not None:
            app._rs_body_box.delete("1.0", "end")
            app._rs_body_box.insert("1.0", p["body"])
        _show_own(app)
        pl = d.get("planned")
        if pl and pl.get("sig") == _sig(app) and Path(pl.get("plan", "")).is_file():
            app._rs_planned = pl
            app._rs_status_var.set("Restored: planned and ready. Click Render.")
    finally:
        app._rs_restoring = False


def resume_on_open(app: Any) -> None:
    if _read_settings(app).get("active"):
        app.ui_call(lambda: app._on_style_pick(STYLE))


# ------------------------------------------------------------------ page
def activate(app: Any) -> None:
    if getattr(app, "_rs_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_rs_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._rs_active = True
    _restore(app)
    _save(app)
    try:
        import visual_bridge

        visual_bridge.restore(app, VB_OWNER)
    except Exception:  # noqa: BLE001
        pass
    app._rs_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_rs_active", False):
        app._rs_active = False
        try:
            import visual_bridge

            visual_bridge.clear(app, VB_OWNER)
        except Exception:  # noqa: BLE001
            pass
        if remember:
            _save(app)
        block = getattr(app, "_rs_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_rs_generate_btn", None) is None:
        return
    running = getattr(app, "_rs_running", False)
    app._rs_generate_btn.configure(state="disabled" if running else "normal")
    app._rs_render_btn.configure(state="normal" if (app._rs_planned and not running) else "disabled")
    app._rs_stop_btn.configure(state="normal" if running and not app._rs_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_rs_running", False):
        app._cta_action = "rs_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._rs_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._rs_planned:
        app._cta_action = "rs_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("Planned. Click Render to draw the Short.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "rs_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Pick a ready story or paste your own, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "rs_cancel":
        cancel(app)
    elif action == "rs_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_rs_running", False) or app._rs_cancel.is_set():
        return
    app._rs_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _progress(app: Any):
    def cb(frac: float, msg: str = "") -> None:
        app.ui_latest("style_progress", lambda: (app._rs_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._rs_cancel.clear()
    app._rs_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._rs_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._rs_running = False
            if error:
                app._rs_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._rs_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def make_story(app: Any, p: dict) -> dict:
    """The picks -> a story dict (raises ValueError with a message for the user)."""
    st = _engine("story")
    if st is None:
        raise ValueError("reddit_shorts could not be loaded")
    if p["story"] != OWN:
        sid = app._rs_builtin.get(p["story"])
        if not sid:
            raise ValueError("Pick a story from the list.")
        return st.builtin(sid)
    return st.custom(p["title"], p["body"], sub=p["sub"], voice=app._rs_voice_map.get(p["voice"], "en-US-AndrewNeural"), cast=p["cast"])


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rs_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    p = _picks(app)
    try:
        story = make_story(app, p)
    except ValueError as exc:
        messagebox.showerror("Cannot start", str(exc))
        return
    rn = _engine("runner")
    if rn is None:
        return
    app._rs_planned = None
    _save(app)
    sig = _sig(app)
    sd = _state_dir(app)
    plan_path = sd / "plan.json"
    work = sd / story["id"]
    app._rs_status_var.set("Generating: the voice, then the pictures in Flow…")
    app._append_log(f"{TAG} Generate: {story['title']}\n")
    index = list(app._rs_builtin.values()).index(story["id"]) if story.get("builtin") else 0

    def job():
        spec = rn.plan(story, work, music_index=index, log=_log(app), cancel=app._rs_cancel.is_set)
        rn.save(spec, plan_path)
        return spec

    def ready(spec) -> None:
        app._rs_planned = {"sig": sig, "plan": str(plan_path)}
        _fill_visuals(app, spec)
        made, need = len(spec["assets"]["pictures"]), len(spec["pictures"])
        miss = f"; {need - made} picture(s) not made yet (plain frames; Generate again to retry)" if made < need else ""
        msg = f"{spec['duration']:.0f} s Short, {made}/{need} pictures{miss}. Click Render."
        app._rs_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _save(app)

    _start(app, "reddit-shorts-plan", job, ready)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rs_running", False):
        return
    ws, planned = app._workspace, app._rs_planned
    if ws is None or not planned:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs a plan.")
        return
    if planned["sig"] != _sig(app):
        messagebox.showinfo("Click Generate first", "You changed the story or voice after Generate. Click Generate again, then Render.")
        return
    rn = _engine("runner")
    if rn is None:
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._rs_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("reddit_shorts")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._rs_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    import visual_bridge

    vb_dir, vb_rows = visual_bridge.folder(VB_OWNER, ws), visual_bridge.rows(app, VB_OWNER)   # read on the main thread

    def job():
        spec = rn.refresh_assets(rn.load(planned["plan"]))
        n = visual_bridge.apply_spec(vb_dir, vb_rows, spec) if vb_rows else 0
        if n:
            _log(app)(f"{n} picture(s) from the Visuals tab")
        return rn.render(spec, str(out_path), progress=_progress(app), cancel=app._rs_cancel.is_set, log=_log(app))

    def done(r) -> None:
        msg = f"Done: {out_path.name} ({r['seconds']:.0f} s)."
        app._rs_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "reddit-shorts-render", job, done, end)
