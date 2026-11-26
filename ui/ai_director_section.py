"""AI Director: its own style page. A script (+ a voiceover, or the free Edge voice) -> an AI agent (Claude Code or Gemini CLI)
makes the whole video itself with the Video Kit (agent_kit/: 3D terrain and rock blocks, maps, real footage and animals,
graphics timed to the narration), headless, in this project's state folder -> the project's final video.

Generate = the agent runs from start to finish (it plans, checks its plan, writes and renders every scene, joins them);
its steps show in the log. Stop ends only the agent this page started. All work lives in agent_kit/runner.py, imported only
inside the button handlers. Nothing starts until Generate.

Each project remembers this page (state/ai_director/settings.json); the agent works in state/ai_director/<script name>/.
app.py only calls in here: activate / deactivate / resume_on_open / sync_cta / cta, and reads `_ad_block` / `_ad_running` / `_ad_active`."""

from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "AI Director"
# Style cards that open this same page with one look pack chosen (they show under their own name in the picker)
PRESETS = {"City Planning": "city_lens"}
TAG = "[AI DIRECTOR]"
AGENTS = {"Claude Code": "claude", "Gemini CLI": "gemini", "Antigravity CLI (Google AI Pro)": "antigravity"}
VOICES = {"My voiceover file (below)": "", "Andrew (US, calm man)": "en-US-AndrewNeural", "Brian (US)": "en-US-BrianNeural",
          "Guy (US)": "en-US-GuyNeural", "Jenny (US, warm woman)": "en-US-JennyNeural", "Aria (US)": "en-US-AriaNeural"}
# Tiers, mapped per AI in agent_kit/runner.py: Claude Sonnet / Opus, Antigravity Gemini Flash / top Gemini.
MODELS = {"Fast (Sonnet / Gemini Flash)": "fast", "Best drawings, slower (Opus / top Gemini)": "best", "My plan's default": ""}
PACKS = {"Teal documentary (3D + footage)": "doc_teal", "Cartoon history (drawn)": "history_toon",
         "Doodle night story (drawn)": "doodle_dark", "City planning (satellite maps)": "city_lens"}
SCOPES = {"Test: first 2 minutes": 2.0, "Test: first 5 minutes": 5.0, "Whole video": 0.0}
_ROOT = Path(__file__).resolve().parent.parent


def _runner():
    try:
        base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        return importlib.import_module("agent_kit.runner")
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("AI Director is not installed", f"The agent_kit folder could not be loaded:\n{type(exc).__name__}: {exc}")
        return None


def _label(parent, text, row, col=0):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=row, column=col, padx=(0, 8), sticky="w")


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._ad_script_var = ctk.StringVar(value="")
    app._ad_voice_var = ctk.StringVar(value="")
    app._ad_edge_var = ctk.StringVar(value=list(VOICES)[1])
    app._ad_look_var = ctk.StringVar(value="")
    app._ad_pack_var = ctk.StringVar(value=next(iter(PACKS)))
    app._ad_model_var = ctk.StringVar(value=next(iter(MODELS)))
    app._ad_agent_var = ctk.StringVar(value=next(iter(AGENTS)))
    app._ad_scope_var = ctk.StringVar(value=next(iter(SCOPES)))
    app._ad_status_var = ctk.StringVar(value="")
    app._ad_cancel = threading.Event()
    app._ad_running = getattr(app, "_ad_running", False)

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._ad_block = block

    body = section(block, 0, 1, "Script and voice", "the AI times every scene to your voice")
    rows = ctk.CTkFrame(body, fg_color="transparent")
    rows.grid(row=0, column=0, sticky="ew")
    rows.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Script (.txt)", app._ad_script_var, lambda: _browse(app, "script"), parent=rows,
                  placeholder_text="the narration, plain text")
    app._path_row(1, "Voiceover (optional)", app._ad_voice_var, lambda: _browse(app, "voice"), parent=rows,
                  placeholder_text="mp3 / wav of the script read aloud; empty = a free Edge voice")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=1, column=0, sticky="w", pady=(8, 0))
    _label(out, "Voice", 0)
    ctk.CTkOptionMenu(out, values=list(VOICES), variable=app._ad_edge_var, width=260,
                      command=lambda v: _browse(app, "voice") if VOICES.get(v) == "" and not app._ad_voice_var.get().strip() else None,
                      ).grid(row=0, column=1, sticky="w")
    # The same file pick as the Voiceover row above, next to the voice menu where people look for it.
    make_button(out, "Upload voiceover", lambda: _browse(app, "voice"), size="sm", width=150).grid(row=0, column=2, padx=(10, 0), sticky="w")

    body = section(block, 1, 2, "Who makes it, and how it looks")
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=0, column=0, sticky="ew")
    out.grid_columnconfigure(1, weight=1)
    _label(out, "AI", 0)
    ai_row = ctk.CTkFrame(out, fg_color="transparent")
    ai_row.grid(row=0, column=1, sticky="w")
    ctk.CTkOptionMenu(ai_row, values=list(AGENTS), variable=app._ad_agent_var, width=250).grid(row=0, column=0, padx=(0, 10))
    make_button(ai_row, "Set up / sign in", lambda: _setup_agent(app), size="sm", width=140).grid(row=0, column=1, padx=(0, 8))
    make_button(ai_row, "Check", lambda: _check_agent(app), size="sm", width=80).grid(row=0, column=2)
    _label(out, "Model", 4)
    ctk.CTkOptionMenu(out, values=list(MODELS), variable=app._ad_model_var, width=260).grid(row=4, column=1, pady=(8, 0), sticky="w")
    _label(out, "Length", 1)
    ctk.CTkOptionMenu(out, values=list(SCOPES), variable=app._ad_scope_var, width=220).grid(row=1, column=1, pady=(8, 0), sticky="w")
    _label(out, "Look pack", 2)
    pack_row = ctk.CTkFrame(out, fg_color="transparent")
    pack_row.grid(row=2, column=1, pady=(8, 0), sticky="w")
    ctk.CTkOptionMenu(pack_row, values=list(PACKS), variable=app._ad_pack_var, width=260,
                      ).grid(row=0, column=0, sticky="w")
    app._ad_pack_thumb = ctk.CTkLabel(pack_row, text="", cursor="hand2")
    app._ad_pack_thumb.grid(row=0, column=1, padx=(14, 0))
    app._ad_pack_thumb.bind("<Button-1>", lambda _e: _open_pack_preview(app))
    ctk.CTkLabel(pack_row, text="click the picture\nto see the look", font=ctk.CTkFont(size=11), text_color=T.MUTED,
                 justify="left").grid(row=0, column=2, padx=(8, 0))
    _show_pack_preview(app)
    app._ad_pack_var.trace_add("write", lambda *_a: _show_pack_preview(app))   # also when a project's saved pick is restored
    _label(out, "Notes", 3)
    ctk.CTkEntry(out, textvariable=app._ad_look_var, height=34, width=520,
                 placeholder_text="optional: e.g. lots of maps, warm colours, little text").grid(row=3, column=1, pady=(8, 0), sticky="w")
    # Right under the AI picker: the answer of Set up / Check must show next to the buttons, not below the fold.
    app._ad_agent_note = ctk.CTkLabel(ai_row, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600)
    app._ad_agent_note.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    body = section(block, 2, 3, "Generate", "the AI plans, checks, draws, renders and joins the whole video by itself")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._ad_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                         text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_generate(app))
    app._ad_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._ad_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._ad_stop_btn.grid(row=0, column=1, padx=(0, 10))
    make_button(go, "Open work folder", lambda: _open_folder(app), size="sm", width=150).grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._ad_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    ctk.CTkLabel(body, text="Start with a 2-minute test: a whole 15-minute video takes the AI hours and many credits. The AI may only use "
                            "the Video Kit tools and write files in this project's work folder; it cannot run other commands.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600).grid(row=2, column=0, sticky="w", pady=(6, 0))
    render_panel(app, body, row=3)
    block.grid_remove()
    for v in (app._ad_script_var, app._ad_voice_var, app._ad_edge_var, app._ad_look_var, app._ad_pack_var, app._ad_model_var, app._ad_agent_var, app._ad_scope_var):
        v.trace_add("write", lambda *_a: _changed(app))


# ------------------------------------------------------------------ picks
def _picks(app: Any) -> dict:
    return {"script": app._ad_script_var.get().strip(), "voice": app._ad_voice_var.get().strip(), "edge": app._ad_edge_var.get(),
            "look": app._ad_look_var.get().strip(), "pack": app._ad_pack_var.get(), "model": app._ad_model_var.get(), "agent": app._ad_agent_var.get(),
            "scope": app._ad_scope_var.get()}


def _changed(app: Any) -> None:
    """A pick changed: remember it and show whether that AI is installed. Nothing starts here."""
    _agent_note(app)
    _save(app)


def _agent_note(app: Any) -> None:
    lbl = getattr(app, "_ad_agent_note", None)
    if lbl is None:
        return
    rn = _runner_quiet()
    agent = AGENTS.get(app._ad_agent_var.get(), "claude")
    if rn is None:
        lbl.configure(text="")
        return
    exe = rn.find_agent(agent)
    lbl.configure(text=(f"{app._ad_agent_var.get()} found: {exe}" if exe else rn.install_hint(agent)))


def _pack_dir(app: Any) -> Path:
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    return base / "agent_kit" / "looks" / PACKS.get(app._ad_pack_var.get(), "doc_teal")


def _show_pack_preview(app: Any) -> None:
    """The small 2 x 2 picture of the chosen look (agent_kit/looks/<pack>/thumb.png)."""
    lbl = getattr(app, "_ad_pack_thumb", None)
    if lbl is None:
        return
    try:
        from PIL import Image

        with Image.open(_pack_dir(app) / "thumb.png") as im:
            pic = im.convert("RGB")
        img = ctk.CTkImage(light_image=pic, dark_image=pic, size=(192, 108))
    except Exception:  # noqa: BLE001 - a look without a picture just shows none
        lbl.configure(image=None, text="")
        return
    lbl.configure(image=img, text="")
    lbl._img = img   # keep a reference


def _open_pack_preview(app: Any) -> None:
    """Open the full sheet (8 frames of a real video in this look) in the system viewer."""
    f = _pack_dir(app) / "preview.jpg"
    if not f.exists():
        return
    import os
    import subprocess

    if sys.platform == "win32":
        os.startfile(str(f))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(f)])


def _setup_agent(app: Any) -> None:
    """One click: uses the Claude already on this computer (the Claude app's own copy) or installs Claude Code / Gemini CLI,
    then opens it in a Terminal window where its first start asks you to sign in. Nothing else starts."""
    rn = _runner()
    if rn is None:
        return
    agent = AGENTS.get(app._ad_agent_var.get(), "claude")
    try:
        rn.open_setup_terminal(agent)
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox
        messagebox.showerror("Set up", str(exc))
        return
    lbl = getattr(app, "_ad_agent_note", None)
    if lbl is not None:
        lbl.configure(text=("A Terminal window opened. In it type  /login  and press Return, sign in in the browser that opens, "
                            "then type  /exit . Back here, click Check." if agent == "claude" else
                            "A Terminal window opened. It installs Antigravity CLI; sign in with your Google (AI Pro) account in the "
                            "browser it opens, click Copy to Clipboard, paste the code into the Terminal window and press Return, "
                            "then type  /quit . Back here, click Check." if agent == "antigravity" else
                            "A Terminal window opened. Choose Login with Google and sign in, then type  /quit . Back here, click Check."))


def _check_agent(app: Any) -> None:
    """Ask the AI one tiny question in the background: shows whether it is installed and signed in."""
    rn = _runner()
    lbl = getattr(app, "_ad_agent_note", None)
    if rn is None or lbl is None:
        return
    name = app._ad_agent_var.get()
    agent = AGENTS.get(name, "claude")
    lbl.configure(text=f"Checking {name}…")

    def work() -> None:
        ok, msg = rn.check_ready(agent)
        app.after(0, lambda: lbl.configure(text=f"{name}: {msg}", text_color=(T.ACCENT if ok else T.MUTED)))

    threading.Thread(target=work, daemon=True).start()


def _runner_quiet():
    try:
        return _runner_import()
    except Exception:  # noqa: BLE001
        return None


def _runner_import():
    base = Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    return importlib.import_module("agent_kit.runner")


def _state_dir(app: Any) -> Optional[Path]:
    ws = getattr(app, "_workspace", None)
    return Path(ws.state_dir) / "ai_director" if ws is not None else None


def _work_dir(app: Any, script: str) -> Optional[Path]:
    d = _state_dir(app)
    if d is None:
        return None
    name = re.sub(r"[^a-z0-9]+", "_", Path(script).stem.lower()).strip("_")[:40] or "video"
    return d / name


def _read_settings(app: Any) -> dict:
    d = _state_dir(app)
    try:
        f = d / "settings.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f is not None and f.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(app: Any) -> None:
    d = _state_dir(app)
    if d is None or getattr(app, "_ad_restoring", False) or getattr(app, "_ad_script_var", None) is None:
        return
    try:
        data = {"active": bool(getattr(app, "_ad_active", False)), "picks": _picks(app), "style": style_name(app)}
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "settings.tmp"
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(d / "settings.json")
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a failure
        pass


def _restore(app: Any) -> None:
    ws = getattr(app, "_workspace", None)
    key = str(getattr(ws, "state_dir", "")) if ws is not None else ""
    if key == getattr(app, "_ad_restored_for", None) or getattr(app, "_ad_running", False):
        return
    app._ad_restored_for = key
    d = _read_settings(app)
    if not d:
        return
    app._ad_restoring = True
    try:
        p = d.get("picks") or {}
        for var, k, allowed in ((app._ad_script_var, "script", None), (app._ad_voice_var, "voice", None), (app._ad_edge_var, "edge", VOICES),
                                (app._ad_look_var, "look", None), (app._ad_pack_var, "pack", PACKS), (app._ad_model_var, "model", MODELS), (app._ad_agent_var, "agent", AGENTS), (app._ad_scope_var, "scope", SCOPES)):
            v = p.get(k)
            if v is not None and (allowed is None or v in allowed):
                var.set(v)
    finally:
        app._ad_restoring = False


def style_name(app: Any) -> str:
    """The name this page shows as: AI Director, or the preset style card that opened it (City Planning)."""
    return getattr(app, "_ad_style", STYLE) or STYLE


def resume_on_open(app: Any) -> None:
    d = _read_settings(app)
    if d.get("active"):
        name = d.get("style") if d.get("style") in PRESETS else STYLE
        app.ui_call(lambda: app._on_style_pick(name))


def _browse(app: Any, what: str) -> None:
    from tkinter import filedialog

    if what == "script":
        path = filedialog.askopenfilename(title="Choose the script", filetypes=[("Text", "*.txt *.md"), ("All files", "*.*")])
        if path:   # remembered only: nothing is read until Generate
            app._ad_script_var.set(path)
    else:
        path = filedialog.askopenfilename(title="Choose the voiceover", filetypes=[("Audio", "*.mp3 *.wav *.m4a"), ("All files", "*.*")])
        if path:
            app._ad_voice_var.set(path)
            app._ad_edge_var.set(next(iter(VOICES)))


def _open_folder(app: Any) -> None:
    p = _picks(app)
    d = _work_dir(app, p["script"]) if p["script"] else _state_dir(app)
    if d is None:
        return
    d.mkdir(parents=True, exist_ok=True)
    import subprocess

    opener = "open" if sys.platform == "darwin" else ("explorer" if sys.platform.startswith("win") else "xdg-open")
    subprocess.Popen([opener, str(d)])


# ------------------------------------------------------------------ page
def activate(app: Any, style: str = STYLE) -> None:
    if getattr(app, "_ad_running", False):
        return
    app._ad_style = style if style in PRESETS else STYLE
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_ad_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._ad_active = True
    _restore(app)
    pack = PRESETS.get(app._ad_style)
    if pack:   # the style card's own look, whatever this project picked last on the plain AI Director page
        app._ad_pack_var.set(next(k for k, v in PACKS.items() if v == pack))
    _save(app)
    _agent_note(app)
    app._ad_block.grid()
    _sync_buttons(app)


def deactivate(app: Any, *, remember: bool = True) -> None:
    if getattr(app, "_ad_active", False):
        app._ad_active = False
        if remember:
            _save(app)
        block = getattr(app, "_ad_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_ad_generate_btn", None) is None:
        return
    running = getattr(app, "_ad_running", False)
    app._ad_generate_btn.configure(state="disabled" if running else "normal")
    app._ad_stop_btn.configure(state="normal" if running and not app._ad_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_ad_running", False):
        app._cta_action = "ad_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._ad_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "The AI is making the video — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    app._cta_action = "ad_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose a script (and a voiceover), then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "ad_cancel":
        cancel(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_ad_running", False) or app._ad_cancel.is_set():
        return
    app._ad_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


def _log(app: Any):
    return lambda m: app.ui_call(lambda: app._append_log(f"{TAG} {m}\n"))


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_ad_running", False):
        return
    ws = app._workspace
    if ws is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    p = _picks(app)
    if not p["script"] or not Path(p["script"]).is_file():
        messagebox.showerror("Cannot start", "Choose the script (.txt) first.")
        return
    edge = VOICES.get(p["edge"], "")
    if p["voice"] and not Path(p["voice"]).is_file():
        messagebox.showerror("Cannot start", f"The voiceover is not there: {p['voice']}")
        return
    if not p["voice"] and not edge:
        messagebox.showerror("Cannot start", "Choose your voiceover file, or pick an Edge voice.")
        return
    rn = _runner()
    if rn is None:
        return
    agent = AGENTS.get(p["agent"], "claude")
    if not rn.find_agent(agent):
        messagebox.showerror(f"{p['agent']} is not installed", rn.install_hint(agent))
        return
    minutes = SCOPES.get(p["scope"], 2.0)
    if not minutes and not messagebox.askyesno("Make the whole video?", "The AI makes every scene of the whole script. A 15-minute "
                                               "video takes hours and many credits. A 2-minute test first is safer. Go ahead?"):
        return
    work = _work_dir(app, p["script"])
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._ad_cancel.clear()
    app._ad_running = True
    app._ad_status_var.set(f"{p['agent']} is making the video. Its steps show in the log.")
    app._append_log(f"{TAG} Generate with {p['agent']} ({p['scope']}) in {work}\n")
    run = app._track_generation_start("ai_director")
    app._sync_primary_cta()
    log = _log(app)

    def worker() -> None:
        error, final = "", None
        try:
            job = rn.prepare(work, p["script"], p["voice"], edge or "en-US-AndrewNeural", p["look"], minutes, log=log,
                             pack=PACKS.get(p.get("pack", ""), "doc_teal"),
                             model=MODELS.get(p.get("model", ""), "fast") if agent != "gemini" else "")
            final = rn.run(agent, job, log=log, cancel=app._ad_cancel.is_set)
            shutil.copyfile(final, out_path)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            error = "Stopped." if app._ad_cancel.is_set() else f"{exc}"

        def finish() -> None:
            from export_state import run_outcome

            app._ad_running = False
            msg = error or f"Done: {Path(out_path).name}. The AI's work (plan, scenes, clips) is in {work}."
            app._ad_status_var.set(msg)
            app._append_log(f"{TAG} {msg}\n")
            done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._ad_cancel.is_set())
            app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                      message=error or "")
            app._sync_primary_cta()

        app.ui_call(finish)

    threading.Thread(target=worker, name="ai-director", daemon=True).start()
