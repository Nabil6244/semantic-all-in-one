"""Product Trailer: its own style page (phone, colour, feature CSV, music, disclaimer, 1080p at 30/60 fps) with a Generate step that
builds the trailer spec and a Render step that renders it. All the work lives in the `product_trailer` package, imported only inside
the button handlers (a clear error when it is missing). Nothing starts until Generate: picking files or options only remembers them.

app.py only calls in here: activate / deactivate / sync_cta / cta, and reads `_pt_block` / `_pt_running` / `_pt_active`."""

from __future__ import annotations

import inspect
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from . import theme as T
from .style_kit import render_panel, section
from .widgets import make_button

STYLE = "Product Trailer"
TAG = "[PRODUCT TRAILER]"
FILM_TYPES = ("Trailer", "Reveal", "Review")
RESOLUTIONS = {"1080p (1920x1080)": (1920, 1080)}
DEFAULT_COLOURS = ("Titanium Black", "Titanium Silver", "Titanium Blue", "Titanium Gray", "Titanium White", "Gold", "Red", "Green")
DEFAULT_DISCLAIMER = ("This is a conceptual trailer made by a fan. It is not affiliated with, endorsed by or sponsored by the "
                      "manufacturer. Product names and trademarks belong to their owners.")
_ROOT = Path(__file__).resolve().parent.parent
OWNER = "product_trailer"      # its AI pictures and stock clips in the Visuals tab (visual_bridge)
FOOTAGE_BASE = 1000            # stock clips are Visuals rows 1001, 1002, ... so they never share a number with an AI scene


def _root() -> Path:
    return Path(getattr(sys, "_MEIPASS", _ROOT)) if getattr(sys, "frozen", False) else _ROOT


def _phones_path() -> Path:
    return _root() / "whatif-engine" / "data" / "phones.json"


def _prompt_path() -> Path:
    return _root() / "docs" / "product_trailer" / "CSV_prompt.txt"


def load_phones() -> Dict[str, List[str]]:
    """{phone name: [colours]} from whatif-engine/data/phones.json; {} when the file is missing or unreadable (another part of the
    work writes it). Accepts a list of names, a list of {name, colours/colors}, a {name: {...}} map or {"phones": [...]}."""
    try:
        data = json.loads(_phones_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict) and isinstance(data.get("phones"), (list, dict)):
        data = data["phones"]
    out: Dict[str, List[str]] = {}

    def colours_of(entry: Any) -> List[str]:
        if not isinstance(entry, dict):
            return []
        raw = entry.get("colours") or entry.get("colors") or []
        names = []
        for c in raw if isinstance(raw, (list, tuple)) else (raw.keys() if isinstance(raw, dict) else []):
            names.append(str(c.get("name") or c.get("id") or "") if isinstance(c, dict) else str(c))
        return [n for n in names if n]

    if isinstance(data, dict):
        for name, entry in data.items():
            label = entry.get("name", name) if isinstance(entry, dict) else name
            out[str(label)] = colours_of(entry)
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, str):
                out[entry] = []
            elif isinstance(entry, dict) and (entry.get("name") or entry.get("id")):
                out[str(entry.get("name") or entry.get("id"))] = colours_of(entry)
    return out


# ---- the page ---------------------------------------------------------------------------------------------------------------

def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._pt_phone_var = ctk.StringVar(value="")
    app._pt_colour_var = ctk.StringVar(value=DEFAULT_COLOURS[0])
    app._pt_csv_var = ctk.StringVar(value="")
    app._pt_music_var = ctk.StringVar(value="")
    app._pt_voice_var = ctk.StringVar(value="")
    app._pt_disclaimer_var = ctk.BooleanVar(value=True)
    app._pt_res_var = ctk.StringVar(value=next(iter(RESOLUTIONS)))
    app._pt_fps_var = ctk.StringVar(value="30")
    app._pt_type_var = ctk.StringVar(value="Trailer")
    app._pt_ai_var = ctk.BooleanVar(value=False)
    app._pt_style_var = ctk.StringVar(value="Mixed (auto)")
    app._pt_footage_var = ctk.BooleanVar(value=True)
    app._pt_status_var = ctk.StringVar(value="")
    app._pt_cancel = threading.Event()
    app._pt_running = getattr(app, "_pt_running", False)
    app._pt_spec_path = None
    app._pt_phones = {}

    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._pt_block = block

    # 1  Product
    body = section(block, 0, 1, "Product", "the phone and its colour")
    line = ctk.CTkFrame(body, fg_color="transparent")
    line.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(line, text="Phone", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    app._pt_phone_box = ctk.CTkComboBox(line, values=[], variable=app._pt_phone_var, width=280,
                                        command=lambda _v=None: _phone_picked(app))
    app._pt_phone_box.grid(row=0, column=1, padx=(0, 16))
    ctk.CTkLabel(line, text="Colour", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=2, padx=(0, 8))
    app._pt_colour_box = ctk.CTkComboBox(line, values=list(DEFAULT_COLOURS), variable=app._pt_colour_var, width=200)
    app._pt_colour_box.grid(row=0, column=3)

    # 2  Features and music
    body = section(block, 1, 2, "Features and music", "one feature per row; music is optional")
    app._path_row(0, "Feature CSV", app._pt_csv_var, lambda: _browse(app, "csv"), parent=body,
                  placeholder_text="Choose the feature CSV (order, feature, kicker, value, sub, look)")
    app._path_row(1, "Music", app._pt_music_var, lambda: _browse(app, "music"), parent=body,
                  placeholder_text="Optional: a music track (cuts follow its beat)")
    app._path_row(2, "Voice-over", app._pt_voice_var, lambda: _browse(app, "voice"), parent=body,
                  placeholder_text="Optional: your narration (a Review is timed to it; music then sits far below it)")
    tools = ctk.CTkFrame(body, fg_color="transparent")
    tools.grid(row=3, column=0, sticky="ew", pady=(6, 0))
    app._pt_prompt_status = ctk.StringVar(value="")
    make_button(tools, "Copy CSV prompt", lambda: copy_csv_prompt(app), size="sm", width=150).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(tools, textvariable=app._pt_prompt_status, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 text="").grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(body, text="Paste the prompt into any AI chat with your phone's specs; save its answer as a .csv and choose it above "
                            "(docs/product_trailer/CSV_prompt.txt).", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 justify="left", wraplength=600).grid(row=4, column=0, sticky="w", pady=(4, 0))

    # 3  End card and output
    body = section(block, 2, 3, "End card and output")
    ctk.CTkCheckBox(body, text="Disclaimer card at the end", variable=app._pt_disclaimer_var,
                    command=lambda: _sync_disclaimer(app)).grid(row=0, column=0, sticky="w")
    app._pt_disclaimer_box = ctk.CTkTextbox(body, height=64, font=ctk.CTkFont(size=12), wrap="word")
    app._pt_disclaimer_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
    app._pt_disclaimer_box.insert("1.0", DEFAULT_DISCLAIMER)
    out = ctk.CTkFrame(body, fg_color="transparent")
    out.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    ctk.CTkLabel(out, text="Resolution", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(out, values=list(RESOLUTIONS), variable=app._pt_res_var, width=180).grid(row=0, column=1, padx=(0, 16))
    ctk.CTkLabel(out, text="Frame rate", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=2, padx=(0, 8))
    ctk.CTkSegmentedButton(out, values=["30", "60"], variable=app._pt_fps_var).grid(row=0, column=3)
    ctk.CTkLabel(out, text="60 fps takes about twice as long to render.", font=ctk.CTkFont(size=11),
                 text_color=T.MUTED).grid(row=0, column=4, padx=(12, 0))

    # 4  Film type and AI scenes
    body = section(block, 3, 4, "Film type and AI scenes", "Trailer, Reveal (about 3 min) or Review (a script with chapters, charts and subtitles)")
    kind = ctk.CTkFrame(body, fg_color="transparent")
    kind.grid(row=0, column=0, sticky="ew")
    ctk.CTkLabel(kind, text="Film type", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkSegmentedButton(kind, values=list(FILM_TYPES), variable=app._pt_type_var, command=lambda _v=None: _type_picked(app)).grid(row=0, column=1)
    ctk.CTkLabel(kind, text="Review look", font=ctk.CTkFont(size=12), text_color=T.MUTED).grid(row=0, column=2, padx=(16, 8))
    ctk.CTkSegmentedButton(kind, values=["Mixed (auto)", "Cinematic", "Infographic"], variable=app._pt_style_var).grid(row=0, column=3)
    ctk.CTkCheckBox(body, text="Mixed look: download matching stock footage for real-world sentences (Pexels / Pixabay keys)", variable=app._pt_footage_var).grid(
        row=1, column=1, sticky="w", padx=(16, 0), pady=(8, 0))
    ctk.CTkCheckBox(body, text="Use AI scenes made in Flow (pictures are free; clips are only planned)", variable=app._pt_ai_var).grid(
        row=1, column=0, sticky="w", pady=(8, 0))
    app._pt_script_label = ctk.CTkLabel(body, text="Review narration: paste plain text (one sentence per shot), or choose a review CSV above (columns: text, visual, chapter). Chapters and these directives are optional. Between lines: [intro: t] [lineup: caption | room | pose] [macro: caption | move] [bigtype: TEXT] [chip: LABEL | caption] [bars: ...] [curve: ...] [compare: ...] [stat: value | label] [xray: caption] [fold: caption] [flat: TITLE | Name=60W@95 | ...] [gauge: TITLE | unit | max | A=1 | B=2] [tweet: Author @handle | text | phrase] [outro: name]",
                                        font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=600)
    app._pt_script_label.grid(row=2, column=0, sticky="w", pady=(8, 0))
    app._pt_script_box = ctk.CTkTextbox(body, height=120, font=ctk.CTkFont(size=12), wrap="word")
    app._pt_script_box.grid(row=3, column=0, sticky="ew", pady=(4, 0))
    ai = ctk.CTkFrame(body, fg_color="transparent")
    ai.grid(row=4, column=0, sticky="w", pady=(8, 0))
    make_button(ai, "Plan AI scenes", lambda: on_plan_scenes(app), size="sm", width=150).grid(row=0, column=0, padx=(0, 10))
    app._pt_make_scenes_btn = make_button(ai, "Make AI scenes in Flow", lambda: on_make_scenes(app), size="sm", width=200)
    app._pt_make_scenes_btn.grid(row=0, column=1)
    ctk.CTkLabel(body, text="Make AI scenes uses your Flow account for pictures only (0 credits) and renders the phone's reference pictures first. "
                            "A scene Flow cannot make becomes a 3D shot.", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
                 justify="left", wraplength=600).grid(row=5, column=0, sticky="w", pady=(4, 0))

    # 5  Generate, then Render
    body = section(block, 4, 5, "Generate, then Render", "Generate plans the film; Render makes the video")
    go = ctk.CTkFrame(body, fg_color="transparent")
    go.grid(row=0, column=0, sticky="w")
    app._pt_generate_btn = ctk.CTkButton(go, text="Generate", width=170, height=40, corner_radius=6, fg_color=T.ACCENT,
                                         hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"),
                                         command=lambda: on_generate(app))
    app._pt_generate_btn.grid(row=0, column=0, padx=(0, 10))
    app._pt_render_btn = ctk.CTkButton(go, text="Render", width=170, height=40, corner_radius=6, fg_color=T.ACCENT,
                                       hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"),
                                       command=lambda: on_render(app), state="disabled")
    app._pt_render_btn.grid(row=0, column=1, padx=(0, 10))
    app._pt_stop_btn = make_button(go, "Stop", lambda: cancel(app), size="sm", width=90, state="disabled")
    app._pt_stop_btn.grid(row=0, column=2)
    ctk.CTkLabel(body, textvariable=app._pt_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left",
                 wraplength=600).grid(row=1, column=0, sticky="ew", pady=(8, 0))
    render_panel(app, body, row=2)
    block.grid_remove()


def _sync_disclaimer(app: Any) -> None:
    box = getattr(app, "_pt_disclaimer_box", None)
    if box is not None:
        box.configure(state="normal" if app._pt_disclaimer_var.get() else "disabled")


def _phone_picked(app: Any) -> None:
    colours = app._pt_phones.get(app._pt_phone_var.get().strip()) or []
    app._pt_colour_box.configure(values=colours or list(DEFAULT_COLOURS))
    if colours and app._pt_colour_var.get() not in colours:
        app._pt_colour_var.set(colours[0])


def _refresh_phones(app: Any) -> None:
    """Read phones.json each time the page is opened (it may appear later); a missing file only leaves the box free text."""
    app._pt_phones = load_phones()
    try:
        app._pt_phone_box.configure(values=sorted(app._pt_phones))
    except Exception:
        pass


def _browse(app: Any, kind: str) -> None:
    from tkinter import filedialog

    if kind == "csv":
        path = filedialog.askopenfilename(title="Choose the feature CSV", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        var = app._pt_csv_var
    elif kind == "voice":
        path = filedialog.askopenfilename(title="Choose the voice-over",
                                          filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._pt_voice_var
    else:
        path = filedialog.askopenfilename(title="Choose the music track",
                                          filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")])
        var = app._pt_music_var
    if path:
        var.set(path)   # remembered only: nothing is read or planned until Generate
        app._pt_spec_path = None
        _sync_buttons(app)


def copy_csv_prompt(app: Any) -> None:
    p = _prompt_path()
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        app._pt_prompt_status.set(f"The CSV prompt is not there yet ({p.name}).")
        return
    try:
        app.clipboard_clear()
        app.clipboard_append(text)
        app._pt_prompt_status.set("Copied. Paste it into your AI chat.")
    except Exception as exc:  # noqa: BLE001
        app._pt_prompt_status.set(f"Could not copy: {exc}")


# ---- activation and the app's main button -----------------------------------------------------------------------------------

def activate(app: Any) -> None:
    if getattr(app, "_pt_running", False):
        return
    app._war_deactivate()
    app._health_deactivate()
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside, like Health Cinema
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app.generation_mode = "normal"
    if getattr(app, "_pt_block", None) is None:
        build(app, app._view_visual_director.content, row=9)
    app._pt_active = True
    _refresh_phones(app)
    _load_options(app)
    app._pt_block.grid()
    _sync_buttons(app)
    import visual_bridge

    visual_bridge.restore(app, OWNER)      # the pictures and clips of the last Make AI scenes / Generate, back in the Visuals tab


def deactivate(app: Any) -> None:
    if getattr(app, "_pt_active", False):
        app._pt_active = False
        import visual_bridge

        visual_bridge.clear(app, "product_trailer")
        block = getattr(app, "_pt_block", None)
        if block is not None:
            block.grid_remove()


def _sync_buttons(app: Any) -> None:
    if getattr(app, "_pt_generate_btn", None) is None:
        return
    running = getattr(app, "_pt_running", False)
    ready = bool(app._pt_spec_path and Path(app._pt_spec_path).is_file())
    app._pt_generate_btn.configure(state="disabled" if running else "normal")
    app._pt_render_btn.configure(state="normal" if (ready and not running) else "disabled")
    app._pt_stop_btn.configure(state="normal" if running and not app._pt_cancel.is_set() else "disabled")


def sync_cta(app: Any) -> None:
    _sync_buttons(app)
    if getattr(app, "_pt_running", False):
        app._cta_action = "pt_cancel"
        app.stage_var.set("GENERATING")
        stopping = app._pt_cancel.is_set()
        app.hint_var.set("Stopping…" if stopping else "Working — click Stop to cancel.")
        app._set_generate_btn(state="disabled" if stopping else "normal", text="Stopping…" if stopping else "Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"
        app.stage_var.set("SETUP")
        app.hint_var.set("Choose a project to get started.")
        app._set_generate_btn(state="normal", text="Choose project")
        return
    if app._pt_spec_path and Path(app._pt_spec_path).is_file():
        app._cta_action = "pt_render"
        app.stage_var.set("RENDER")
        app.hint_var.set("The trailer is planned. Click Render to make the video.")
        app._set_generate_btn(state="normal", text="Render")
        return
    app._cta_action = "pt_generate"
    app.stage_var.set("PLAN")
    app.hint_var.set("Choose the phone and a feature CSV, then click Generate.")
    app._set_generate_btn(state="normal", text="Generate")


def cta(app: Any, action: str) -> None:
    if action == "pt_cancel":
        cancel(app)
    elif action == "pt_render":
        on_render(app)
    else:
        on_generate(app)


def cancel(app: Any) -> None:
    if not getattr(app, "_pt_running", False) or app._pt_cancel.is_set():
        return
    app._pt_cancel.set()
    app._append_log(f"{TAG} Stop requested.\n")
    app._sync_primary_cta()


# ---- Generate / Render (off the UI thread) ----------------------------------------------------------------------------------

def _package():
    try:
        import product_trailer  # noqa: F401 - written by another part of the work; loaded only when a button is pressed
    except Exception as exc:  # noqa: BLE001
        from tkinter import messagebox

        messagebox.showerror("Product Trailer is not installed",
                             f"The product_trailer package could not be loaded:\n{type(exc).__name__}: {exc}")
        return None
    return product_trailer


def _work_dir(app: Any) -> Path:
    d = Path(app._workspace.state_dir) / "product_trailer"
    d.mkdir(parents=True, exist_ok=True)
    return d


def options(app: Any) -> Dict[str, Any]:
    w, h = RESOLUTIONS.get(app._pt_res_var.get(), (1920, 1080))
    return {"phone": app._pt_phone_var.get().strip(), "colour": app._pt_colour_var.get().strip(), "csv": app._pt_csv_var.get().strip(),
            "music": app._pt_music_var.get().strip(), "voiceover": app._pt_voice_var.get().strip(), "disclaimer_on": bool(app._pt_disclaimer_var.get()),
            "disclaimer": app._pt_disclaimer_box.get("1.0", "end-1c").strip(), "width": w, "height": h,
            "fps": 60 if app._pt_fps_var.get() == "60" else 30,
            "film_type": app._pt_type_var.get() if app._pt_type_var.get() in FILM_TYPES else "Trailer", "use_ai": bool(app._pt_ai_var.get()), "style": {"Infographic": "infographic", "Cinematic": "cinematic"}.get(app._pt_style_var.get(), "mixed"), "footage": bool(app._pt_footage_var.get()),
            "script": app._pt_script_box.get("1.0", "end-1c").strip()}


def _load_options(app: Any) -> None:
    """The last Generate's choices for this project (read only; nothing is planned)."""
    ws = getattr(app, "_workspace", None)
    if ws is None:
        return
    try:
        o = json.loads((Path(ws.state_dir) / "product_trailer" / "options.json").read_text(encoding="utf-8"))
    except Exception:
        return
    for key, var in (("phone", app._pt_phone_var), ("colour", app._pt_colour_var), ("csv", app._pt_csv_var), ("music", app._pt_music_var), ("voiceover", app._pt_voice_var)):
        if o.get(key) and not var.get():
            var.set(o[key])
    spec = o.get("spec_path")
    if spec and Path(spec).is_file() and not app._pt_spec_path:
        app._pt_spec_path = spec


def _call(fn, *args, **kwargs):
    """Call fn with only the keyword arguments it accepts (phone / colour / disclaimer reach build_spec when it takes them)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(*args, **kwargs)
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return fn(*args, **kwargs)
    return fn(*args, **{k: v for k, v in kwargs.items() if k in params})


def _spec_path_of(result: Any, out_dir: Path) -> Path:
    if isinstance(result, (str, Path)):
        return Path(result)
    if isinstance(result, dict):
        for key in ("spec_path", "path", "spec"):
            v = result.get(key)
            if isinstance(v, (str, Path)) and Path(v).suffix:
                return Path(v)
        path = out_dir / "spec.json"
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return path
    path = getattr(result, "spec_path", None)
    if path:
        return Path(path)
    raise RuntimeError(f"build_spec returned {type(result).__name__}, not a spec path")


def _start(app: Any, name: str, job, done, end=None) -> None:
    """end(error): called last, on the main thread, whatever happened ("" when the job finished)."""
    app._pt_cancel.clear()
    app._pt_running = True
    app._sync_primary_cta()

    def worker() -> None:
        result, error = None, ""
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - shown to the user, never a silent failure
            error = "Stopped." if app._pt_cancel.is_set() else f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._pt_running = False
            if error:
                app._pt_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            else:
                try:
                    done(result)
                except Exception as exc:  # noqa: BLE001
                    app._pt_status_var.set(f"{type(exc).__name__}: {exc}")
            if end is not None:
                end(error)
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name=name, daemon=True).start()


def _progress_cb(app: Any, export: bool = False):
    def cb(*args, **kwargs) -> None:
        frac = next((a for a in args if isinstance(a, (int, float))), kwargs.get("fraction"))
        msg = next((a for a in args if isinstance(a, str)), kwargs.get("message", ""))
        text = (f"{int(float(frac) * 100) if float(frac) <= 1 else int(frac)}%  " if frac is not None else "") + (msg or "")
        try:
            k = float(frac) if frac is not None else None
            app.after(0, lambda: (app._pt_status_var.set(text.strip()),
                                  k is not None and app.progress.set(k if k <= 1 else k / 100.0),
                                  export and k is not None and app._export_progress(k if k <= 1 else k / 100.0, msg or "")))
        except Exception:
            pass
    return cb


def on_generate(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_pt_running", False):
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    o = options(app)
    review_film = o["film_type"] == "Review"
    if review_film:
        if not o["script"] and not (o["csv"] and Path(o["csv"]).is_file()):
            messagebox.showerror("Cannot start", "Paste the narration (plain text is fine), or choose a review CSV, first.")
            return
    elif not o["csv"] or not Path(o["csv"]).is_file():
        messagebox.showerror("Cannot start", "Choose the feature CSV first." if not o["csv"] else f"The feature CSV was not found:\n{o['csv']}")
        return
    if o["music"] and not Path(o["music"]).is_file():
        messagebox.showerror("Cannot start", f"The music file was not found:\n{o['music']}")
        return
    if o["voiceover"] and not Path(o["voiceover"]).is_file():
        messagebox.showerror("Cannot start", f"The voice-over file was not found:\n{o['voiceover']}")
        return
    pt = _package()
    if pt is None:
        return
    out_dir = _work_dir(app)
    app._pt_status_var.set(f"Planning the {o['film_type'].lower()}…")
    app._append_log(f"{TAG} Generate: {o['film_type']}{' + AI scenes' if o['use_ai'] else ''}, {o['width']}x{o['height']} @ {o['fps']} fps\n")
    new_modes = review_film or o["use_ai"] or o["film_type"] == "Reveal" or bool(o["voiceover"])
    whisper_model = (app.model_var.get().strip() if hasattr(app, "model_var") else "") or "base"
    if o["use_ai"]:
        _visuals_into_results(app, out_dir)      # the AI pictures as the Visuals tab holds them
    footage_chosen = _footage_chosen(app)       # and the stock clips
    planned: Dict[str, Any] = {}

    def job():
        if new_modes:   # Reveal, Review and AI scenes go through the film back end; a plain Trailer keeps the original call
            from product_trailer import studio

            words = None
            if review_film and o["voiceover"]:   # a Review is timed to the narrator: read the voice-over's word times (cached, else Whisper)
                app.after(0, lambda: app._pt_status_var.set("Reading the voice-over…"))
                try:
                    words = app._pakmap_get_words(Path(o["voiceover"]), whisper_model, getattr(app._workspace, "state_dir", None),
                                                  lambda m: app.after(0, lambda m=m: app._append_log(f"{TAG} {m}\n")))
                except Exception as exc:  # noqa: BLE001 -- the lines are then spread evenly over the voice-over's length
                    app.after(0, lambda exc=exc: app._append_log(f"{TAG} Could not read the voice-over words ({exc}); lines spread evenly.\n"))
            r = studio.plan_film(o["film_type"], out_dir=out_dir, csv=o["csv"] or None, script=o["script"], phone=o["phone"], colour=o["colour"],
                                 music=o["music"] or None, disclaimer=o["disclaimer"], disclaimer_on=o["disclaimer_on"], width=o["width"],
                                 height=o["height"], fps=o["fps"], use_ai=o["use_ai"], voiceover=o["voiceover"] or None, words=words, style=o["style"],
                                 footage_chosen=footage_chosen, **_ai_args(app, o))
            planned.update(r)
            app.after(0, lambda: app._pt_status_var.set(r["summary"]))
            for n in r.get("notes", [])[:20]:
                app._append_log(f"{TAG} {n}\n")
            return r["spec_path"]
        return _call(pt.build_spec, o["csv"], music_path=o["music"] or None, out_dir=str(out_dir), width=o["width"], height=o["height"],
                     fps=o["fps"], seed=None, product_name=o["phone"] or None, phone=o["phone"] or None, colour=o["colour"] or None,
                     color=o["colour"] or None, disclaimer=(o["disclaimer"] if o["disclaimer_on"] else None),
                     disclaimer_on=o["disclaimer_on"])

    def done(result) -> None:
        spec = _spec_path_of(result, out_dir)
        app._pt_spec_path = str(spec)
        try:
            (out_dir / "options.json").write_text(json.dumps({**o, "spec_path": str(spec)}, indent=2), encoding="utf-8")
        except Exception:
            pass
        if planned.get("footage"):
            _show_in_visuals(app, footage_rows=_footage_rows(app, planned["footage"]))
        else:
            _show_in_visuals(app)
        app._pt_status_var.set(f"Planned: {spec.name}. Its pictures and clips are in the Visuals tab; click Render to make the video.")
        app._append_log(f"{TAG} Spec written: {spec}\n")

    _start(app, "product-trailer-generate", job, done)


def on_render(app: Any) -> None:
    from tkinter import messagebox

    if getattr(app, "_pt_running", False):
        return
    ws = app._workspace
    if ws is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    spec = app._pt_spec_path
    if not spec or not Path(spec).is_file():
        messagebox.showerror("Cannot start", "Click Generate first: Render needs the planned trailer.")
        return
    import visual_bridge

    rows = visual_bridge.rows(app, OWNER)
    if rows and visual_bridge.snapshot(visual_bridge.folder(OWNER, ws), rows) != getattr(app, "_pt_table_snapshot", None):
        messagebox.showinfo("Click Generate first", "You changed pictures or clips in the Visuals tab. Click Generate to put them in the trailer, then Render.")
        return
    pt = _package()
    if pt is None:
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    app._pt_status_var.set("Rendering…")
    app._append_log(f"{TAG} Render: {Path(spec).name} -> {out_path.name}\n")
    cb = _progress_cb(app, export=True)
    run = app._track_generation_start(OWNER)      # the Export page follows the render

    def end(error: str) -> None:
        from export_state import run_outcome

        done = run_outcome(error, out_path if Path(out_path).is_file() else None, stopped=app._pt_cancel.is_set())
        app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed",
                                  message=error or ("" if done != "failed" else "Render finished, but no video was written."))

    def job():
        return pt.render(str(spec), str(out_path), progress=cb, cancel=app._pt_cancel.is_set)   # render() calls it: pass the check, not the Event

    def done(_result) -> None:
        if app._pt_cancel.is_set():
            app._pt_status_var.set("Stopped.")
            return
        msg = f"Done: {out_path.name}" if Path(out_path).is_file() else "Render finished, but no video was written."
        app._pt_status_var.set(msg)
        app._append_log(f"{TAG} {msg}\n")

    _start(app, "product-trailer-render", job, done, end)


# ---- film type and AI scenes ------------------------------------------------------------------------------------------------

def _ai_args(app: Any, o: Dict[str, Any]) -> Dict[str, Any]:
    """The AI scene-writer (Gemini, then Groq, from the Settings keys) and the stock-footage keys, for the Mixed look only. Without keys the built-in rules are used."""
    if o.get("style") != "mixed":
        return {}
    settings = dict(getattr(app, "_settings", {}) or {})
    out: Dict[str, Any] = {"log": lambda m: app.after(0, lambda m=m: app._append_log(f"{TAG} {m}\n"))}
    try:
        from product_trailer import llm_director

        if settings.get("gemini_api_key") or settings.get("groq_api_key"):
            out["llm_run"] = llm_director.router_run(settings, getattr(app._workspace, "state_dir", None))
    except Exception as exc:  # noqa: BLE001 -- the rules still work
        out["log"](f"The AI scene-writer could not start ({type(exc).__name__}); using the built-in rules.")
    if o.get("footage") and (settings.get("pexels_api_key") or settings.get("pixabay_api_key")):
        out["stock_settings"] = settings
    return out


def _type_picked(app: Any) -> None:
    """Only a hint: the Review type reads the script box, Trailer and Reveal read the feature CSV. Nothing is planned."""
    review_film = app._pt_type_var.get() == "Review"
    app._pt_status_var.set("Review: paste the narration as plain text below (or choose a review CSV); chapters are optional." if review_film else "")


def _scene_pack(app: Any, o: Dict[str, Any]):
    from product_trailer import studio

    return studio.plan_pack(o["film_type"], csv=o["csv"] or None, script=o["script"], phone=o["phone"], colour=o["colour"],
                            disclaimer=o["disclaimer"], disclaimer_on=o["disclaimer_on"])


def _source_ready(app: Any, o: Dict[str, Any]) -> bool:
    from tkinter import messagebox

    if o["film_type"] == "Review":
        if not o["script"] and not (o["csv"] and Path(o["csv"]).is_file()):
            messagebox.showerror("Cannot start", "Paste the narration (plain text is fine), or choose a review CSV, first.")
            return False
    elif not o["csv"] or not Path(o["csv"]).is_file():
        messagebox.showerror("Cannot start", "Choose the feature CSV first.")
        return False
    return True


def on_plan_scenes(app: Any) -> None:
    """Show which scenes would be AI pictures, AI clips or 3D, and what it costs. Nothing is sent anywhere."""
    if getattr(app, "_pt_running", False) or _package() is None:
        return
    o = options(app)
    if not _source_ready(app, o):
        return

    def job():
        from product_trailer import scenepack, studio

        pack, _ = _scene_pack(app, o)
        return scenepack.describe(pack) + "\n" + studio.estimate_text(pack)

    def done(text) -> None:
        app._pt_status_var.set(str(text).splitlines()[-1])
        app._append_log(f"{TAG} AI scene plan:\n{text}\n")

    app._pt_status_var.set("Planning the AI scenes…")
    _start(app, "product-trailer-plan-scenes", job, done)


def on_make_scenes(app: Any) -> None:
    """Make the AI pictures in Flow (images only, 0 credits): references first, then one request per reference set. Asks first."""
    from tkinter import messagebox

    if getattr(app, "_pt_running", False) or _package() is None:
        return
    if app._workspace is None:
        messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    o = options(app)
    if not _source_ready(app, o):
        return
    out_dir = _work_dir(app)
    try:
        pack, _ = _scene_pack(app, o)
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror("Cannot plan the scenes", f"{type(exc).__name__}: {exc}")
        return
    from product_trailer import studio

    if not messagebox.askokcancel("Make AI scenes in Flow",
                                  f"{studio.estimate_text(pack)}\n\nThis renders the phone's reference pictures, then asks Flow (your Flow account) for the pictures. "
                                  "No clips are made. Continue?"):
        return
    manager = app._get_flow_engine_manager()
    app._append_log(f"{TAG} Make AI scenes: {pack['estimate']['ai_images']} pictures\n")

    def job():
        client = manager.ensure_running()
        return studio.make_scenes(pack, out_dir, client, phone=o["phone"] or pack.get("phone", ""), log=lambda m: app._append_log(f"{TAG} {m}\n"))

    def done(results) -> None:
        ok = sum(1 for r in results.values() if r["status"] == "done")
        _show_in_visuals(app, ai_rows=_ai_rows_after_make(app, pack, results))
        app._pt_status_var.set(f"AI scenes: {ok} of {len(results)} made and listed in the Visuals tab (change any there). Tick 'Use AI scenes' and click Generate; the rest become 3D shots.")
        try:
            app._goto_workflow_view("visual_plan")
        except Exception:  # noqa: BLE001
            pass

    app._pt_status_var.set("Making the AI scenes in Flow…")
    _start(app, "product-trailer-make-scenes", job, done)


# ---- the Visuals tab: AI pictures (rows = scene n) and stock clips (rows = FOOTAGE_BASE + n) ----------------------------------------------

def _visual_rows(app: Any, footage: bool) -> List:
    import visual_bridge

    return [r for r in visual_bridge.rows(app, OWNER) if (int(str(r.scene_number)) > FOOTAGE_BASE) == footage]


def _show_in_visuals(app: Any, ai_rows: Optional[List] = None, footage_rows: Optional[List] = None) -> None:
    """Main thread. One kind of rows is replaced; the other kind already in the table is kept."""
    import visual_bridge

    ai = ai_rows if ai_rows is not None else _visual_rows(app, False)
    ft = footage_rows if footage_rows is not None else _visual_rows(app, True)
    visual_bridge.fill(app, OWNER, list(ai) + list(ft))
    app._pt_table_snapshot = visual_bridge.snapshot(visual_bridge.folder(OWNER, app._workspace), app._scene_rows)


def _ai_rows_after_make(app: Any, pack: Dict[str, Any], results: Dict[Any, Any]) -> List:
    """The AI scenes Flow was asked for, filed in this style's Visuals folder (each picture keeps its own file)."""
    import visual_bridge
    from providers.base import SceneRow

    folder = visual_bridge.folder(OWNER, app._workspace)
    rows = []
    for sc in pack.get("scenes") or []:
        if sc.get("source") != "ai_still":
            continue
        n = int(sc["n"])
        rows.append(SceneRow(scene_number=str(n), script_segment=str(sc.get("caption") or sc.get("feature") or sc.get("type") or ""), asset_type="flow_image", prompt=str(sc.get("prompt") or "")))
        r = results.get(n) or results.get(str(n)) or {}
        if r.get("status") == "done":
            visual_bridge.seed(folder, str(n), r.get("path") or "", "flow_image", prompt=rows[-1].prompt, provider="flow")
    return rows


def _visuals_into_results(app: Any, out_dir: Path) -> None:
    """Before Generate: the AI pictures the Visuals tab holds (Retry / Change source / Local clip there) become the film's pictures."""
    import visual_bridge
    from product_trailer import studio

    rows = _visual_rows(app, False)
    if not rows:
        return
    results = studio.load_results(out_dir)
    for n, rec in visual_bridge.records(visual_bridge.folder(OWNER, app._workspace), rows).items():
        results[n] = {"status": "done", "path": rec["path"]}
    studio.save_results(out_dir, results)


def _footage_chosen(app: Any) -> Dict[int, Dict[str, str]]:
    import visual_bridge

    rows = _visual_rows(app, True)
    recs = visual_bridge.records(visual_bridge.folder(OWNER, app._workspace), rows)
    by_no = {int(str(r.scene_number)): r for r in rows}
    return {no - FOOTAGE_BASE: {"query": by_no[no].stock, "path": rec["path"]} for no, rec in recs.items()}


def _footage_rows(app: Any, items: List[Dict[str, Any]]) -> List:
    import visual_bridge
    from providers.base import SceneRow

    folder = visual_bridge.folder(OWNER, app._workspace)
    rows = []
    for it in items:
        no = str(FOOTAGE_BASE + int(it["n"]))
        rows.append(SceneRow(scene_number=no, script_segment=str(it.get("text") or it["query"]), asset_type="stock_video", stock=str(it["query"])))
        if it.get("path"):
            visual_bridge.seed(folder, no, it["path"], "stock_video", stock=str(it["query"]))
    return rows
