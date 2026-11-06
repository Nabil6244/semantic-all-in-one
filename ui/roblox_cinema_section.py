"""Roblox Cinema: its own style page (story CSV or pasted narration, optional voice-over, resolution) with a Generate step that plans the
film and a Render step that renders it (3D block-world scenes on the GPU, music, sound, voice). All the work lives in
roblox-cinema-engine/ (runner.py), imported only inside the button handlers. Nothing starts until Generate: picking files or options only
remembers them.

app.py only calls in here: activate / deactivate / sync_cta / cta, and reads `_rc_block` / `_rc_running` / `_rc_active`."""

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

STYLE = "Roblox Cinema"
TAG = "[ROBLOX CINEMA]"
RESOLUTIONS = {"720p preview (1280x720)": 720, "1080p final (1920x1080)": 1080}
# Story type: a history/war film, or a quiet modern horror story (engine lib/horror.mjs). A CSV plan row's own genre wins.
GENRES = {"History film": "history", "Horror story": "horror"}
PROMPTS = {"history": "story_prompt.md", "horror": "story_prompt_horror.md"}
OWNER = "roblox_cinema"   # its horror picture cards in the Visuals tab (visual_bridge)
_ROOT = Path(__file__).resolve().parent.parent


def _engine_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "roblox-cinema-engine"


def _runner():
    """roblox-cinema-engine/runner.py (a folder name Python cannot import), loaded once; None with a message when it is missing."""
    mod = sys.modules.get("rce_runner")
    if mod is not None:
        return mod
    try:
        spec = importlib.util.spec_from_file_location("rce_runner", _engine_dir() / "runner.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["rce_runner"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        sys.modules.pop("rce_runner", None)
        messagebox.showerror("Roblox Cinema is not installed", f"The roblox-cinema-engine folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _cards():
    """roblox-cinema-engine/cards.py (horror picture cards), loaded once."""
    mod = sys.modules.get("rce_cards")
    if mod is None:
        spec = importlib.util.spec_from_file_location("rce_cards", _engine_dir() / "cards.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["rce_cards"] = mod
        spec.loader.exec_module(mod)
    return mod


def _assets_dir(app: Any) -> Path:
    import visual_bridge

    return visual_bridge.folder(OWNER, app._workspace)


def _fetch_cards(app: Any, base: str, src: dict, after) -> None:
    """After Generate: the plan's picture cards go through the Visuals tab, then `after()` runs. No cards (every history film): the tab is left
    empty and `after()` runs at once. No Gemini; a picture that is not fetched only means the film shows the code-made card."""
    import visual_bridge

    reqs, manager, cards = [], None, None
    try:
        cards = _cards()
        reqs = cards.requests(base + ".mp4.plan.json", _assets_dir(app))
        if reqs and cards.missing(reqs, _assets_dir(app)):
            manager = app._build_asset_manager(_assets_dir(app), [])      # built here: it reads Tk variables
    except Exception as exc:  # noqa: BLE001 - cards are an extra; the film is planned without them
        app._append_log(f"{TAG} picture cards skipped: {type(exc).__name__}: {exc}\n")
    if not reqs:
        if getattr(app, "_scene_rows_owner", None) == OWNER or visual_bridge.load(_assets_dir(app)):
            visual_bridge.save(_assets_dir(app), [])
            visual_bridge.clear(app, OWNER)
        after()
        return
    log = lambda m: app.after(0, lambda: app._append_log(f"{TAG} {m}\n"))
    holder: dict = {"rows": cards.table_rows(reqs)}
    planned_msg = app._rc_status_var.get()

    def job():
        holder["rows"] = cards.fetch(reqs, manager, _assets_dir(app), base_dir=str(Path(src.get("csv") or base).parent), log=log, cancel=app._rc_cancel.is_set)

    def end(error: str) -> None:
        visual_bridge.fill(app, OWNER, holder["rows"])      # check or change the pictures there; Render uses what the tab holds
        msg = cards.summary(reqs, visual_bridge.records(_assets_dir(app), holder["rows"]))
        app._rc_status_var.set(f"{planned_msg}  {msg}" if not error else f"{error}  {msg}")
        app._append_log(f"{TAG} {msg}\n")
        if not error:
            after()

    app._rc_status_var.set(f"Fetching {len(reqs)} picture cards for the Visuals tab…")
    _start(app, "roblox-cinema-cards", job, lambda _r: None, end)


def _card_pictures(app: Any, plan: dict) -> Optional[str]:
    """The pictures the Visuals tab holds now, as the file the renderer reads; None when the film has no picture cards. Never stops a render."""
    try:
        import visual_bridge

        cards = _cards()
        reqs = cards.requests(plan["base"] + ".mp4.plan.json", _assets_dir(app))
        if not reqs:
            return None
        recs = visual_bridge.records(_assets_dir(app), visual_bridge.rows(app, OWNER) or cards.table_rows(reqs))
        return cards.write_pictures(plan["base"] + ".cards.json", reqs, recs)
    except Exception as exc:  # noqa: BLE001
        app.after(0, lambda: app._append_log(f"{TAG} picture cards: using the code-made ones ({type(exc).__name__}: {exc})\n"))
        return None


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._rc_csv_var = ctk.StringVar(value="")
    app._rc_voice_var = ctk.StringVar(value="")
    app._rc_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._rc_music_var = ctk.BooleanVar(value=True)
    app._rc_genre_var = ctk.StringVar(value=next(iter(GENRES)))
    app._rc_status_var = ctk.StringVar(value="")
    app._rc_cancel = threading.Event()
    app._rc_running = getattr(app, "_rc_running", False)
    app._rc_planned = None   # {"csv", "text_file", "voice", "res"} of the last Generate

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._rc_block = block

    body = section(block, 0, 1, "Story", "a story CSV, or paste plain narration (# lines start chapters)")
    app._path_row(0, "Story CSV", app._rc_csv_var, lambda: _browse(app, "csv"), parent=body,
                  placeholder_text="Choose the story CSV (plan / chapter / beat rows), or paste narration below")
    app._path_row(1, "Voice-over", app._rc_voice_var, lambda: _browse(app, "voice"), parent=body,
                  placeholder_text="Optional: your narration (the film is timed to its words; without it a planned read is used)")
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=3, column=0, sticky="w", pady=(6, 0))
    app._rc_prompt_status = ctk.StringVar(value="")
    ctk.CTkLabel(tools, text="Story type", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(tools, values=list(GENRES), variable=app._rc_genre_var, width=150).grid(row=0, column=1, padx=(0, 12))
    make_button(tools, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="sm", width=150).grid(row=0, column=2, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._rc_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(row=0, column=3, sticky="w")
    app._rc_text_box = ctk.CTkTextbox(body, height=120, font=ctk.CTkFont(size=12), wrap="word")
    app._rc_text_box.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    ctk.CTkLabel(body, text="Maps show present-day borders and approximate positions (the film says so on screen). "
                            "Sample: roblox-cinema-engine/samples/dday_1944.csv.", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 justify="left", wraplength=600).grid(row=4, column=0, sticky="w", pady=(4, 0))

    body = section(block, 1, 2, "Output")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._rc_res_var, width=220).grid(row=0, column=1, padx=(0, 16))
    ctk.CTkCheckBox(out, text="Music bed (Kevin MacLeod, CC BY 4.0, credited on screen)", variable=app._rc_music_var).grid(row=0, column=2)

    body = section(block, 2, 3, "Generate, then Render", "Generate plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._rc_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._rc_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._rc_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                       text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render(app), state="disabled")
    app._rc_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._rc_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._rc_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._rc_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    _wire_persistence(app)
    block.grid_remove()


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    if kind == "csv":
        path = filedialog.askopenfilename(title="Choose the story CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._rc_csv_var
    else:
        path = filedialog.askopenfilename(title="Choose the voice-over", filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._rc_voice_var
    if path:
        var.set(path)   # remembered only: nothing is read or planned until Generate
        app._rc_planned = None
        auto_render.stop(app, "rc")
        _sync_buttons(app)



def copy_csv_prompt(app: Any) -> None:
    """Put the story-CSV writing prompt on the clipboard (paste it into any AI chat with your topic)."""
    p = _engine_dir().joinpath('docs', PROMPTS.get(GENRES.get(app._rc_genre_var.get(), "history"), "story_prompt.md"))
    status = app._rc_prompt_status
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


# ---- what a project keeps: its page choices and its planned film --------------------------------------------------------------
# Saved to <project>/state/roblox_cinema/settings.json whenever a choice changes or Generate finishes, and put back when the project
# is (re)opened. The plan is only put back while the story and voice files are exactly as they were at Generate (size + saved time).

def _sig(path: str):
    try:
        st = Path(path).stat()
        return [str(Path(path).resolve()), st.st_size, st.st_mtime_ns]
    except Exception:  # noqa: BLE001
        return None


def _settings_file(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "roblox_cinema" / "settings.json" if ws is not None else None


def _save(app: Any) -> None:
    if getattr(app, "_rc_restoring", False) or getattr(app, "_rc_text_box", None) is None:
        return
    f = _settings_file(app)
    if f is None:
        return
    try:
        o = options(app)
        planned = getattr(app, "_rc_planned", None)
        data = {"csv": o["csv"], "voice": o["voice"], "text": o["text"], "res_label": app._rc_res_var.get(), "music": o["music"], "genre_label": app._rc_genre_var.get(), "planned": None}
        if planned:
            src = planned["src"]
            data["planned"] = {**planned, "sig_src": _sig(src.get("csv") or src.get("text_file") or ""), "sig_voice": _sig(planned["voice"]) if planned["voice"] else None}
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(f)
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    """Put back this project's page choices and, if nothing changed since, its planned film (so Render is ready after reopening)."""
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_rc_restored_for", None) or getattr(app, "_rc_running", False) or getattr(app, "_rc_text_box", None) is None:
        return
    app._rc_restored_for = key
    app._rc_planned = None            # a plan belongs to one project
    f = _settings_file(app)
    if f is None or not f.is_file():
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    app._rc_restoring = True
    try:
        app._rc_csv_var.set(d.get("csv", "") or "")
        app._rc_voice_var.set(d.get("voice", "") or "")
        if d.get("res_label") in RESOLUTIONS:
            app._rc_res_var.set(d["res_label"])
        app._rc_music_var.set(bool(d.get("music", True)))
        if d.get("genre_label") in GENRES:
            app._rc_genre_var.set(d["genre_label"])
        app._rc_text_box.delete("1.0", "end")
        if d.get("text"):
            app._rc_text_box.insert("1.0", d["text"])
        p = d.get("planned")
        if p and p.get("src") and Path(str(p.get("base", "")) + ".mp4.plan.json").is_file():
            src = p["src"]
            same_src = p.get("sig_src") is not None and _sig(src.get("csv") or src.get("text_file") or "") == p["sig_src"]
            same_voice = (not p.get("voice")) or (p.get("sig_voice") is not None and _sig(p["voice"]) == p["sig_voice"])
            if same_src and same_voice:
                app._rc_planned = {**{k: p[k] for k in ("src", "voice", "res", "music", "base")}, "genre": p.get("genre", "history")}
                app._rc_status_var.set("Restored: the film is planned. Click Render, or Generate to plan again.")
    finally:
        app._rc_restoring = False


def _wire_persistence(app: Any) -> None:
    for v in (app._rc_csv_var, app._rc_voice_var, app._rc_res_var, app._rc_music_var, app._rc_genre_var):
        v.trace_add("write", lambda *_a: _save(app))
    try:
        app._rc_text_box.bind("<KeyRelease>", lambda _e: _save(app))
    except Exception:  # noqa: BLE001
        pass


def activate(app: Any) -> None:
    if getattr(app, "_rc_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside, like Health Cinema and Product Trailer
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_rc_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._rc_active = True
    _restore(app)
    from .voiceover_view import adopt_project_voiceover
    adopt_project_voiceover(app, app._rc_voice_var)   # the project voiceover (Voiceover tab / Audio & Effects) if this box is empty
    app._rc_block.grid()
    try:
        import visual_bridge

        visual_bridge.restore(app, OWNER)      # the picture cards of the last Generate, back in the Visuals tab
    except Exception:  # noqa: BLE001
        pass
    _sync_buttons(app)


def deactivate(app: Any) -> None:
    if getattr(app, "_rc_active", False):
        app._rc_active = False
        try:
            import visual_bridge

            visual_bridge.clear(app, OWNER)
        except Exception:  # noqa: BLE001
            pass
        block = getattr(app, "_rc_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_rc_generate_btn", None) is None:
        return
    running = getattr(app, "_rc_running", False)
    app._rc_generate_btn.configure(state="disabled" if running else "normal")
    app._rc_render_btn.configure(state="normal" if (app._rc_planned and not running) else "disabled")
    waiting = auto_render.pending(app, "rc")      # Stop also cancels the auto-render countdown
    app._rc_stop_btn.configure(state="normal" if (running and not app._rc_cancel.is_set()) or waiting else "disabled")


def sync_cta(app: Any) -> None:
    _restore(app)                     # a different project was opened while this page is up
    _sync_buttons(app)
    if getattr(app, "_rc_running", False):
        app._cta_action = "rc_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._rc_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._rc_planned:
        app._cta_action = "rc_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The film is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "rc_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a story CSV (or paste narration), then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "rc_cancel":
        cancel(app)
    elif action == "rc_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if auto_render.stop(app, "rc", note="Auto-render cancelled: click Render when ready."):
        app._append_log(f"{TAG} Auto-render cancelled.\n")
        app._sync_primary_cta()
        return
    if not getattr(app, "_rc_running", False) or app._rc_cancel.is_set():
        return
    app._rc_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "roblox_cinema"
    d.mkdir(parents=True, exist_ok=True)
    return d


def options(app: Any) -> dict:
    return {"csv": app._rc_csv_var.get().strip(), "voice": app._rc_voice_var.get().strip(), "text": app._rc_text_box.get("1.0", "end-1c").strip(),
            "res": RESOLUTIONS.get(app._rc_res_var.get(), 720), "music": bool(app._rc_music_var.get()), "genre": GENRES.get(app._rc_genre_var.get(), "history")}


def _source(app: Any, o: dict) -> dict:
    """{csv | text_file} for the runner: a CSV that exists, or the pasted narration saved to the project's folder."""
    if o["csv"]:
        if not Path(o["csv"]).is_file():
            raise FileNotFoundError(f"The story CSV is not there: {o['csv']}")
        return {"csv": o["csv"]}
    if o["text"]:
        f = _work_dir(app) / "narration.txt"
        f.write_text(o["text"], encoding="utf-8")
        return {"text_file": str(f)}
    raise ValueError("Choose a story CSV or paste the narration first.")


def _progress(app: Any):
    last = {"t": 0.0}

    def cb(frac: float, msg: str = "") -> None:
        import time as _time
        if _time.monotonic() - last["t"] >= 30:      # a real log line every 30 s: shows the work is moving and keeps the stall watchdog quiet
            last["t"] = _time.monotonic()
            app.after(0, lambda m=f"{int(frac * 100)}% {msg}".strip(): app._append_log(f"{TAG} {m}\n"))
        app.after(0, lambda: (app._rc_status_var.set(f"{int(frac * 100)}%  {msg}".strip()), app.progress.set(max(0.0, min(1.0, frac))),
                              app._export_progress(max(0.0, min(1.0, frac)), msg or "")))
    return cb


def _start(app: Any, name: str, job, done, end=None) -> None:
    app._rc_cancel.clear()
    app._rc_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._rc_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._rc_running = False
            if error:
                app._rc_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._rc_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rc_running", False):
        return
    auto_render.stop(app, "rc")
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    rc = _runner()
    if rc is None:
        return
    o = options(app)
    try:
        src = _source(app, o)
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror("Cannot start", str(exc))
        return
    base = str(_work_dir(app) / "film")
    app._rc_status_var.set("Planning…")
    app._append_log(f"{TAG} Generate: planning the film\n")

    def job():
        return rc.plan(base, voiceover=o["voice"] or None, resolution=o["res"], genre=o["genre"], progress=_progress(app), cancel=app._rc_cancel.is_set,
                       log=lambda m: app.after(0, lambda: app._append_log(m + "\n")), **src)

    def done(r) -> None:
        app._rc_planned = {"src": src, "voice": o["voice"], "res": o["res"], "music": o["music"], "base": base, "genre": o["genre"]}
        _save(app)
        warn = f"  {len(r['warnings'])} notes (see the log)." if r["warnings"] else ""
        msg = f"Planned {r['scenes']} scenes, {r['duration']:.0f} s ({'timed to your voice-over' if r['voiceTimed'] else 'planned read, no voice-over'}).{warn}"
        app._rc_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")
        _fetch_cards(app, base, src, lambda: auto_render.start(app, "rc", status_var=app._rc_status_var, still_ok=lambda p=app._rc_planned: _auto_render_ok(app, p),
                                                               render=lambda: on_render(app), tag=TAG))

    _start(app, "roblox-cinema-plan", job, done)


def _auto_render_ok(app: Any, plan: dict) -> str:
    """Why the auto-render must not start ("" = it may): the same plan is still there, nothing runs, the options match it."""
    if app._rc_planned is not plan or app._workspace is None:
        return "the plan changed; click Generate again."
    if getattr(app, "_rc_running", False):
        return "another job is running."
    o = options(app)
    if (((o["csv"], o["voice"], o["res"], o["music"]) != (plan["src"].get("csv", ""), plan["voice"], plan["res"], plan["music"]) and o["csv"])
            or o["genre"] != plan.get("genre", "history")):
        return "the story or options changed after Generate; click Generate again."
    return ""


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_rc_running", False):
        return
    auto_render.stop(app, "rc")
    ws, plan = app._workspace, app._rc_planned
    if ws is None or not plan:
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned film.")
        return
    rc = _runner()
    if rc is None:
        return
    o = options(app)
    if ((o["csv"], o["voice"], o["res"], o["music"]) != (plan["src"].get("csv", ""), plan["voice"], plan["res"], plan["music"]) and o["csv"]) \
            or o["genre"] != plan.get("genre", "history"):
        messagebox.showinfo("Click Generate first", "You changed the story or options after Generate. Click Generate again, then Render.")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._rc_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render -> {out_path.name}\n")
    run = app._track_generation_start("roblox_cinema")

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._rc_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return rc.render(plan["base"], voiceover=plan["voice"] or None, output=str(out_path), resolution=plan["res"], music=plan["music"], genre=plan.get("genre", "history"), cards=_card_pictures(app, plan),
                         progress=_progress(app), cancel=app._rc_cancel.is_set, log=lambda m: app.after(0, lambda: app._append_log(m + "\n")), **plan["src"])

    def done(r) -> None:
        mix = (r.get("mix") or {}).get("final_file") or {}
        msg = f"Done: {out_path.name}" + (f"  ({mix.get('integrated_lufs')} LUFS)" if mix else "")
        app._rc_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "roblox-cinema-render", job, done, end)
