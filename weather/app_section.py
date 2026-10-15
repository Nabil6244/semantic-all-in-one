"""The Weather card in the app (phase 1B). app.py only delegates here, through methods that import this module when they run, so
an app with Weather switched off never loads it (and a broken Weather install means "Weather is off", never a crashed app).

The card works like StarMap's: the plan is loaded from files an AI wrote (Copy the CSV prompt); its full-screen footage is rows of
the EXISTING Visual Plan table (replace, retry and skip there); the SHARED Generate button renders it. What Weather adds: Fetch data
(the National Weather Service snapshot the video is built from, checked for freshness again right before the render).

Per project, everything lives in <project>/weather/ (beats.csv, weather_layers.csv, resolved.json, weather.json, _work/)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

TAG = "[WEATHER]"
SETTING_ON = "weather_enabled"
SETTING_CONTACT = "weather_nws_contact"
SETTING_LIBRARY = "weather_library_dir"   # your own footage folder, used before stock (weather.footage_library)
STYLE_NAME = "Weather"
SETTING_SCHEDULE_ROOT = "weather_schedule_root"   # where the daily prep writes <root>/<date>/ (only once the user switches it on)
# the video formats: (label in the card, its CSV prompt in weather/prompts/)
FORMATS = {"forecast": ("Forecast", "forecast_csv_prompt.txt"), "news": ("News", "news_csv_prompt.txt"),
           "post": ("Post-Event", "post_event_csv_prompt.txt")}


FORMAT_ACTIONS = {"forecast": "Prepare today's forecast", "news": "Event footage…", "post": "Suggested reports…"}
SETTING_SUGGESTED = "weather_post_suggested"   # suggestion ids already taken (not offered again)


AUTO_LABEL = "Auto"   # the format / editing style read from the script (weather.autopick); an explicit pick always wins


def format_choice(app) -> str:
    """What the card's Format picker says: "auto", or a key of FORMATS."""
    label = app._weather_format_var.get() if hasattr(app, "_weather_format_var") else ""
    if label == AUTO_LABEL:
        return "auto"
    return next((k for k, (lab, _f) in FORMATS.items() if lab == label), "forecast")


def _script(app) -> str:
    try:
        return app._main_script_text() or ""
    except Exception:
        return ""


def current_format(app) -> str:
    """The format in use: the one picked, or (Auto) the one the script reads as (weather.autopick.detect_format)."""
    choice = format_choice(app)
    if choice != "auto":
        return choice
    from .autopick import detect_format

    return detect_format(_script(app))


def style_choice(app) -> str:
    """What the card's Editing style picker says: "auto", "classic" or "teamplate"."""
    from .teamplate import STYLES

    label = app._weather_style_var.get() if hasattr(app, "_weather_style_var") else ""
    if label == AUTO_LABEL:
        return "auto"
    from .newsdoc import KEY as ND_KEY, NAME as ND_NAME

    if label == ND_NAME:   # News Doc: its own footage-first edit (weather/newsdoc)
        return ND_KEY
    return next((k for k, lab in STYLES.items() if lab == label), "classic")


def current_style(app) -> str:
    """The editing style in use: "classic" (Weather) or "teamplate" (Weather Teamplate, weather.teamplate); Auto picks Teamplate for
    News and Post-Event, classic for a Forecast (weather.autopick.style_for)."""
    choice = style_choice(app)
    if choice != "auto":
        return choice
    from .autopick import style_for

    return style_for(current_format(app))


def library_dir(app) -> Optional[str]:
    d = str((app._settings or {}).get(SETTING_LIBRARY) or "").strip()
    return d if d and Path(d).is_dir() else None


def enabled(settings: Dict[str, Any]) -> bool:
    """Weather is off unless switched on in Settings with its password (weather/lock.py): the switch and the unlock token."""
    from . import lock

    return bool((settings or {}).get(SETTING_ON, False)) and lock.unlocked(settings)


def _m(app):
    """app.py's module (the theme colours, ctk, dialogs): found from the App class, so it works when app.py runs as __main__."""
    return sys.modules[type(app).__module__]


# ---- the project folder -------------------------------------------------------------------------------------------------

def project(app):
    from .generate import WeatherProject

    ws = app._workspace
    return WeatherProject(Path(ws.root) / "weather") if ws is not None else None


def images_dir(ws) -> Path:
    return Path(ws.root) / "weather" / "_work" / "media"


def _state_path(ws) -> Path:
    return Path(ws.root) / "weather" / "weather.json"


def load_state(ws) -> Dict[str, Any]:
    try:
        return json.loads(_state_path(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(app, **changes) -> None:
    ws = app._workspace
    if ws is None:
        return
    state = {**load_state(ws), **{k: v for k, v in changes.items() if v is not None}}
    try:
        _state_path(ws).parent.mkdir(parents=True, exist_ok=True)
        _state_path(ws).write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError as exc:
        app._append_log(f"{TAG} Could not save the Weather settings: {exc}\n")


# ---- reading what an AI wrote ---------------------------------------------------------------------------------------------

def _is_layers_csv(text: str) -> bool:
    """True when `text` starts with a weather_layers.csv header (it names at least beat, id and type)."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    return {"beat", "id", "type"} <= {c.strip().lower() for c in first.split(",")}


def split_plan_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """(beats.csv text, weather_layers.csv text) from what the CSV prompt asks an AI to write: the one-file plan (split_one_file),
    or the older answer with both files, each after its marker line (=== beats.csv === / === weather_layers.csv ===, each on a
    line of its own). A file that is only one of them is recognised by its header. A part whose header is not that file's is
    None (a file that only mentions the markers, like code, is not a plan)."""
    from hybrid.beat_csv import is_beat_csv

    from .sidecar import COLUMNS

    t = str(text).lstrip("\ufeff")
    one = split_one_file(t)
    if one is not None:
        return one
    lines = t.splitlines()
    marks = [(i, ln.strip()) for i, ln in enumerate(lines) if ln.strip() in ("=== beats.csv ===", "=== weather_layers.csv ===")]
    if marks:
        parts: Dict[str, str] = {}
        for k, (i, name) in enumerate(marks):
            body = [ln for ln in lines[i + 1:marks[k + 1][0] if k + 1 < len(marks) else len(lines)]
                    if ln.strip() and not ln.strip().startswith("```")]
            if body:
                parts[name] = "\n".join(body) + "\n"
        beats, layers = parts.get("=== beats.csv ==="), parts.get("=== weather_layers.csv ===")
        return (beats if beats and is_beat_csv(beats) else None), (layers if layers and _is_layers_csv(layers) else None)
    first = t.strip().splitlines()[0].strip().lower() if t.strip() else ""
    if is_beat_csv(t):
        return t, None
    if first.replace(" ", "").split(",")[:3] == list(COLUMNS[:3]):
        return None, t
    return None, None


WEATHER_ROWS = ("weather", "weather_layer", "wx")   # the row kind of a weather layer in the one-file plan


def split_one_file(text: str) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """The one-file plan: a beat CSV whose header also has data_source (and extra), with the weather layers as row=weather rows.
    None when `text` is not one. Words around the CSV (a chat answer) and code fences are dropped. Each file keeps every row in
    its place (the other file's rows left blank), so a problem's row number is that row in the one file."""
    import csv
    import io

    from .sidecar import COLUMNS

    lines = str(text).lstrip("﻿").splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().lower().replace(" ", "").startswith("beat,row,")), None)
    if start is None:
        return None
    body = []
    for ln in lines[start:]:
        if ln.strip().startswith("```"):
            break   # the end of the fenced CSV: what follows is the chat's words
        body.append(ln)
    rows = list(csv.reader(io.StringIO("\n".join(body))))
    head = [c.strip().lower() for c in rows[0]]
    if "data_source" not in head:
        return None
    kind = head.index("row")
    beat_cols = [i for i, h in enumerate(head) if h != "data_source"]

    def write(out_rows) -> str:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(out_rows)
        return buf.getvalue()

    beats, layers, any_layer = [[head[i] for i in beat_cols]], [list(COLUMNS)], False
    for cells in rows[1:]:
        cell = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(head) if h}
        if (cells[kind].strip().lower() if kind < len(cells) else "") in WEATHER_ROWS:
            layers.append([cell.get(c, "") for c in COLUMNS])
            beats.append([])
            any_layer = True
        else:
            beats.append([cells[i] if i < len(cells) else "" for i in beat_cols])
            layers.append([])
    return write(beats), (write(layers) if any_layer else None)


# ---- the card -------------------------------------------------------------------------------------------------------------

def build(app, parent, *, row: int) -> None:
    code_is_old()   # remembers the code as it is now: a later update is reported (warn_if_old)
    M = _m(app)
    ctk = M.ctk
    app._weather_enabled_var = ctk.BooleanVar(value=False)
    app._weather_sound_var = ctk.BooleanVar(value=bool(app._settings.get("pakmap_sound_design", True)))
    app._weather_status_var = ctk.StringVar(value="")
    app._weather_file_var = ctk.StringVar(value="")
    app._weather_running = False
    app._weather_busy = False
    app._weather_cancel = threading.Event()
    app._weather_ok = None
    app._weather_tracking = None
    app._weather_run_manager = None

    block = ctk.CTkFrame(parent, fg_color=M._CARD, corner_radius=10, border_width=1, border_color=M._BORDER)
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._weather_block = block
    app._style_card_header(block, "Weather (US forecast)",
                           "A US forecast over the satellite map: city temperatures, the 5-day strip, current conditions and warnings from the "
                           "National Weather Service, with full-screen footage between. You record the voiceover; every number comes from the data.")
    app._weather_switch = ctk.CTkSwitch(block, text="Use Weather for this project", variable=app._weather_enabled_var,
                                        command=lambda: on_toggle(app), font=ctk.CTkFont(size=12), text_color=M._TEXT)
    app._weather_switch.grid(row=1, column=0, sticky="w", padx=16, pady=(12, 14))
    controls = ctk.CTkFrame(block, fg_color="transparent")
    controls.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))
    controls.grid_columnconfigure(0, weight=1)
    app._weather_controls = controls

    def step(r: int, n: str, title: str) -> None:   # a numbered section heading: 1 Style, 2 Script and plan, 3 Check and make
        head = ctk.CTkFrame(controls, fg_color="transparent")
        head.grid(row=r, column=0, sticky="ew", pady=(14 if r else 0, 6))
        head.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(head, text=n, width=22, height=22, corner_radius=11, fg_color=M._ACCENT, text_color="white",
                     font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(head, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color=M._TEXT).grid(row=0, column=1, sticky="w")
        ctk.CTkFrame(head, height=1, fg_color=M._BORDER).grid(row=0, column=2, sticky="ew", padx=(10, 0))

    def segment_row(r: int, label: str) -> Any:
        f = ctk.CTkFrame(controls, fg_color="transparent")
        f.grid(row=r, column=0, sticky="w", pady=(0, 6))
        ctk.CTkLabel(f, text=label, width=96, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED).pack(side="left")
        return f

    def ghost(parent, text: str, cmd, width: int, height: int = 34) -> Any:
        return ctk.CTkButton(parent, text=text, width=width, height=height, corner_radius=6, fg_color="transparent", border_width=1,
                             border_color=M._BORDER, text_color=M._MUTED, hover_color=M._ACCENT_SEL, font=ctk.CTkFont(size=12), command=cmd)

    # 1  Style: decides what the buttons below do, so it comes first
    step(0, "1", "Style")
    from .teamplate import STYLES
    from .newsdoc import NAME as ND_NAME

    app._weather_style_var = ctk.StringVar(value=AUTO_LABEL)
    style_row = segment_row(1, "Editing style")
    ctk.CTkSegmentedButton(style_row, values=[AUTO_LABEL] + list(STYLES.values()) + [ND_NAME], variable=app._weather_style_var,
                           command=lambda _v: on_style(app)).pack(side="left")
    app._weather_format_var = ctk.StringVar(value=AUTO_LABEL)
    fmt_row = segment_row(2, "Format")
    ctk.CTkSegmentedButton(fmt_row, values=[AUTO_LABEL] + [lab for lab, _f in FORMATS.values()], variable=app._weather_format_var,
                           command=lambda _v: on_format(app)).pack(side="left")
    # one button for what this format adds: Forecast writes today's plan, News finds event footage, Post-Event suggests reports
    app._weather_format_btn = ghost(fmt_row, FORMAT_ACTIONS[current_format(app)], lambda: format_action(app), 190, 28)
    app._weather_format_btn.configure(font=ctk.CTkFont(size=11))
    app._weather_format_btn.pack(side="left", padx=(10, 0))
    app._weather_hint_var = ctk.StringVar(value="")
    ctk.CTkLabel(controls, textvariable=app._weather_hint_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=640,
                 justify="left").grid(row=3, column=0, sticky="w", pady=(2, 0))

    # 2  Script and plan
    step(4, "2", "Script and plan")
    app._weather_method_var = ctk.StringVar(value=METHOD_SCRIPT)
    app._weather_method_row = segment_row(5, "Plan from")
    ctk.CTkSegmentedButton(app._weather_method_row, values=[METHOD_SCRIPT, METHOD_CSV], variable=app._weather_method_var,
                           command=lambda _v: on_method(app)).pack(side="left")
    app._build_csv_prompt_script_box(controls, row=6, pady=(0, 0))
    actions = ctk.CTkFrame(controls, fg_color="transparent")
    actions.grid(row=7, column=0, sticky="w", pady=(10, 0))
    app._weather_load_btn = ctk.CTkButton(actions, text="Load plan…", width=140, height=34, corner_radius=6, fg_color=M._ACCENT,
                                          hover_color=M._ACCENT_HOV, font=ctk.CTkFont(size=12, weight="bold"), command=lambda: browse(app))
    app._weather_load_btn.grid(row=0, column=0, padx=(0, 8))
    app._weather_csv_btn = ghost(actions, "Copy the CSV prompt", lambda: copy_prompt(app), 170)
    app._weather_csv_btn.grid(row=0, column=1, padx=(0, 8))
    app._weather_script_btn = ghost(actions, "Copy the script prompt", lambda: copy_script_prompt(app), 170)
    app._weather_script_btn.grid(row=0, column=2, padx=(0, 8))
    ghost(actions, "Fetch data", lambda: fetch(app), 110).grid(row=0, column=3, padx=(0, 8))
    app._path_row(8, "Loaded plan", app._weather_file_var, lambda: browse(app), parent=controls,
                  placeholder_text="No CSV: the plan is made from your script and voiceover (or click Load plan)")
    name_row = ctk.CTkFrame(controls, fg_color="transparent")
    name_row.grid(row=9, column=0, sticky="ew", pady=(8, 0))
    name_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(name_row, text="Channel name", width=96, font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED, anchor="w").grid(
        row=0, column=0, sticky="w")
    ctk.CTkEntry(name_row, textvariable=app._pakmap_channel_var, height=32,
                 placeholder_text="Shown bottom right of the video (leave empty for none)").grid(row=0, column=1, sticky="ew")

    # 3  Check and make
    step(10, "3", "Check and make")
    more = ctk.CTkFrame(controls, fg_color="transparent")
    more.grid(row=11, column=0, sticky="ew")
    more.grid_columnconfigure(3, weight=1)
    for col, (text, cmd) in enumerate((("Check plan", lambda: check_plan(app)), ("Quick preview", lambda: run_generation(app, preview=True)),
                                       ("Open plan folder", lambda: open_folder(app)))):
        ghost(more, text, cmd, 130, 30).grid(row=0, column=col, padx=(0, 6))
    ctk.CTkSwitch(more, text="Sound effects + ambience", variable=app._weather_sound_var, command=lambda: save_state(app, sound_design=bool(app._weather_sound_var.get())),
                  font=ctk.CTkFont(size=11)).grid(row=0, column=3, sticky="e")
    app._weather_plan_box = ctk.CTkTextbox(controls, height=210, font=ctk.CTkFont(family="Menlo", size=11), wrap="none")
    app._weather_plan_box.grid(row=12, column=0, sticky="ew", pady=(10, 0))
    app._weather_plan_box.configure(state="disabled")
    ctk.CTkLabel(controls, textvariable=app._weather_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=640,
                 justify="left").grid(row=13, column=0, sticky="ew", pady=(6, 0))
    sync_style_ui(app)
    controls.grid_remove()
    app._weather_switch.grid_remove()   # the style picker replaces the per-card switches


METHOD_SCRIPT, METHOD_CSV = "Script + voiceover", "Story CSV"
HINTS = {
    "newsdoc": "News Doc makes a graphics-heavy news documentary from your script and voiceover. Optional: switch Plan from to Story CSV "
               "to choose each sentence's shot, footage search and graphic yourself (Copy the CSV prompt, then Load story CSV).",
    "teamplate": "Weather Teamplate: footage-first, hard cuts every ~5 s. Cities: Dallas, Houston, Chicago, New York, Los Angeles, Miami. "
                 "Fetch data gets the National Weather Service forecast; fetch again if it is more than 6 hours old at render time.",
    "": "Cities: Dallas, Houston, Chicago, New York, Los Angeles, Miami. Fetch data gets the National Weather Service forecast for the "
        "plan; fetch again (and re-record any changed line) if it is more than 6 hours old at render time.",
}


def _story_csv_paths(app):
    from .newsdoc import story_csv

    root = project(app).root
    return root / story_csv.FILE, root / (story_csv.FILE + ".off")


def sync_style_ui(app) -> None:
    """Buttons, hint and the Plan from switch follow the editing style (News Doc has its own story CSV)."""
    if not hasattr(app, "_weather_method_row"):
        return
    from .newsdoc import KEY as ND_KEY

    nd = current_style(app) == ND_KEY
    app._weather_hint_var.set(HINTS.get(current_style(app) if nd or current_style(app) == "teamplate" else "", HINTS[""]))
    if nd:
        app._weather_method_row.grid()
        try:
            on_file = _story_csv_paths(app)[0].is_file()
        except Exception:
            on_file = False
        if on_file:
            app._weather_method_var.set(METHOD_CSV)
        csv_mode = app._weather_method_var.get() == METHOD_CSV
        app._weather_load_btn.configure(text="Load story CSV…" if csv_mode else "Load plan…")
        app._weather_csv_btn.configure(text="Copy the CSV prompt", state="normal" if csv_mode else "disabled")
    else:
        app._weather_method_row.grid_remove()
        app._weather_load_btn.configure(text="Load plan…")
        app._weather_csv_btn.configure(text="Copy the CSV prompt", state="normal")


def on_method(app) -> None:
    """News Doc: plan from the script + voiceover alone, or let a story CSV set each sentence. Switching back to the script keeps the
    CSV aside (newsdoc_story.csv.off) so switching to Story CSV again brings it back."""
    if project(app) is None:
        app._weather_status_var.set("Open or create a project first.")
        sync_style_ui(app)
        return
    try:
        on, off = _story_csv_paths(app)
        if app._weather_method_var.get() == METHOD_SCRIPT:
            if on.is_file():
                on.replace(off)
                app._weather_file_var.set("")
            app._weather_status_var.set("News Doc plans every sentence from your script and voiceover. Check plan, then Generate.")
        else:
            if not on.is_file() and off.is_file():
                off.replace(on)
                app._weather_file_var.set(str(on))
                app._weather_status_var.set("Your earlier story CSV is back in use. Check plan, then Generate.")
            elif not on.is_file():
                app._weather_status_var.set("Story CSV: put your script in the box, Copy the CSV prompt, paste it into Claude, save the CSV it "
                                            "writes, then Load story CSV.")
    except OSError as exc:
        app._weather_status_var.set(f"The story CSV could not be switched: {exc}")
    app._weather_ok = None
    sync_style_ui(app)


def set_text(app, text: str) -> None:
    box = app._weather_plan_box
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.configure(state="disabled")


def show_intro(app) -> None:
    set_text(app, "No plan yet.\n\n1. Record your voiceover and choose it on the Script page.\n2. Click Copy the CSV prompt, paste it with your "
                  "script into Claude (or any AI), save the one CSV it writes.\n3. Click Load plan, then Fetch data.\n"
                  "4. Check plan, find or replace the footage in the Visual Plan, then Generate.\n\nThe NWS asks every app for a contact: "
                  "set yours in Settings > General > Weather.")


AUTO_PLAN_TEXT = ("No CSV: Weather makes the plan from your script and voiceover.\n\n"
                  "1. Put your script on the Script page and choose your voiceover.\n"
                  "2. Click Generate. Weather reads the story, picks the format and editing style (Auto), finds the event and its official "
                  "data, makes the map and footage beats, checks them and renders.\n\n"
                  "Check plan shows the plan first; Quick preview renders a fast low-quality copy. To use your own plan instead, click "
                  "Load plan (a CSV always wins).\n\nThe script should say the full date and the state in its first sentences.")


def is_auto(p) -> bool:
    """A Weather project with no CSV plan: the plan is made from the script and the voiceover (weather.intel.beats)."""
    return p is not None and not p.beats_csv.is_file()


def has_plan(app) -> bool:
    """A beat plan, with weather layers — or without them when Weather Intelligence is on (it finds the data graphics itself)."""
    p = project(app)
    if p is None:
        return False
    from .intel.engine import enabled as intel_on

    if not p.beats_csv.is_file():
        return intel_on(p)   # no CSV: the plan is made from the script and the voiceover
    return p.layers_csv.is_file() or intel_on(p)


def voiceover_words(app, p, voiceover, model: str, state_dir, log) -> list:
    """The voiceover's word times, transcribed ONCE per recording: saved in the project (weather/_work/voiceover_words.json,
    tied to the file's size, time and the Whisper model), so Check plan, Generate and Retry start in seconds, even after a
    restart. A new or re-recorded voiceover is transcribed again."""
    import json

    vo = Path(voiceover)
    try:
        st = vo.stat()
        key = f"{vo.name}:{st.st_size}:{st.st_mtime_ns}:{model}"
    except OSError:
        key = ""
    cache = Path(p.root) / "_work" / "voiceover_words.json"
    if key:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("key") == key and data.get("words"):
                log(f"{TAG} Using the saved transcript of your voiceover (no need to transcribe it again).")
                return [(str(w), float(a), float(b)) for w, a, b in data["words"]]
        except (OSError, ValueError, TypeError):
            pass
    log(f"{TAG} Transcribing your voiceover with Whisper ({model})… this takes a few minutes, only the first time.")
    words = app._pakmap_get_words(vo, model, state_dir, log)
    if key and words:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps({"key": key, "words": [list(w) for w in words]}), encoding="utf-8")
            tmp.replace(cache)
            log(f"{TAG} Transcript saved: the next Check plan or Generate starts right away.")
        except OSError:
            pass
    return words


SCRIPT_MARK = "script_from_app.txt"   # in weather/_work: the script text the app last wrote to weather/script.txt


def sync_script(app, p) -> Optional[str]:
    """A project with no CSV is planned from weather/script.txt (weather.intel.beats): the Script page's text is written there.
    A script.txt the user wrote (not the one the app wrote last) is never replaced. Returns a note, or None. Main thread only."""
    if not is_auto(p):
        return None
    text = _script(app).strip()
    if not text:
        return None
    path, mark = p.root / "script.txt", p.root / "_work" / SCRIPT_MARK
    try:
        current = path.read_text(encoding="utf-8").strip() if path.is_file() else None
        if current == text:
            return None
        written = mark.read_text(encoding="utf-8").strip() if mark.is_file() else None
        if current is not None and current != written:
            return "weather/script.txt is your own file, so it is used instead of the Script page"
        mark.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        mark.write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        return f"the script could not be saved for the plan ({exc}); the voiceover's words are used instead"
    return None


def run_intelligence(p, words, voiceover, fmt: str, contact: str, log, fixed: list) -> None:
    """Weather Intelligence before Check plan / Generate: it reads the story, finds the event and its data, and adds the graphics
    the plan is missing (intel/auto_plan.json; the plan files are never changed). With the engine off (weather.json
    "intelligence": false) the older automatic storm data (weather.autodata) runs instead."""
    from pakmap.app_integration import voiceover_duration

    from .intel.engine import enabled as intel_on, prepare_project

    if not intel_on(p):
        from .autodata import ensure_storm_data

        ensure_storm_data(p, fmt, fixed)
        return
    res = prepare_project(p, words, voiceover_duration(voiceover), fmt=fmt, contact=contact, voiceover=Path(voiceover), log=log)
    if res is not None:
        from .intel.report import summary_lines

        fixed += summary_lines(res)


def show_summary(app) -> None:
    p = project(app)
    if is_auto(p):
        set_text(app, AUTO_PLAN_TEXT)
        return
    lines = []
    try:
        from .autofix import repair_layers

        rows = repair_layers(p.layers_csv.read_text(encoding="utf-8"), []) if p.layers_csv.is_file() else []
        beats_text = p.beats_csv.read_text(encoding="utf-8")
        beats = [ln for ln in beats_text.splitlines()[1:] if ",beat," in ln]
        footage = sum(1 for ln in beats if ",footage," in ln)
        lines.append(f"Plan: {len(beats)} beat(s), {footage} of them full-screen footage; {len(rows)} weather layer(s).")
        kinds: Dict[str, int] = {}
        for r in rows:
            kinds[r.type] = kinds.get(r.type, 0) + 1
        lines.append("Weather layers: " + (", ".join(f"{n} {k}" for k, n in kinds.items()) if kinds else
                                           "none in the plan: Weather Intelligence finds the event's data graphics at Check plan"))
    except Exception as exc:
        lines.append(f"The plan could not be read: {exc}")
    lines.append("")
    lines.append(data_status(app))
    lines.append("")
    lines.append("Click Check plan to time it against the narration and check every row.")
    set_text(app, "\n".join(lines))


def data_status(app) -> str:
    from datetime import datetime, timezone

    p = project(app)
    if p is None or not p.resolved_json.is_file():
        return "Weather data: not fetched yet (click Fetch data)."
    try:
        from .resolve import Snapshot
        from .tz import parse_iso

        snap = Snapshot.from_json(p.resolved_json.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        ages = [(k, (now - parse_iso(f["issued"])).total_seconds() / 3600) for k, f in snap.forecasts.items()]
        oldest = max((a for _, a in ages), default=0.0)
        state = "fresh" if oldest <= 6 else "TOO OLD to render: fetch again"
        return (f"Weather data: fetched {snap.prepared[:16].replace('T', ' ')} UTC; {len(snap.forecasts)} forecast(s), {len(snap.observations)} "
                f"observation(s), {len(snap.alerts)} alert area(s); oldest forecast {oldest:.1f} h ({state}).")
    except Exception as exc:
        return f"Weather data: could not be read ({exc}); fetch again."


# ---- style switching ------------------------------------------------------------------------------------------------------

def deactivate(app) -> None:
    """Another style takes over: Weather steps aside (its plan stays in the project)."""
    if not hasattr(app, "_weather_enabled_var"):
        return
    was = app._weather_enabled_var.get()
    app._weather_enabled_var.set(False)
    app._weather_controls.grid_remove()
    if app.generation_mode == "weather":
        app.generation_mode = "normal"
    clear_visual_plan(app)
    if was:
        save_state(app, active=False)


def activate(app) -> None:
    if getattr(app, "_weather_running", False):
        return
    app._pakmap_deactivate()          # also steps Hybrid and StarMap aside and clears the shared table
    if hasattr(app, "_overscaled_enabled_var") and app._overscaled_enabled_var.get():
        app._overscaled_enabled_var.set(False)
        app._overscaled_controls.grid_remove()
    app._weather_enabled_var.set(True)
    app._weather_controls.grid()
    app.generation_mode = "weather"
    app._set_scenes_empty_text()
    if has_plan(app):
        app._weather_file_var.set("" if is_auto(project(app)) else str(project(app).root))
        show_summary(app)
    else:
        show_intro(app)
    save_state(app, active=True)
    app._sync_primary_cta()


def on_toggle(app) -> None:
    if app._weather_running:
        app._weather_enabled_var.set(True)
        _m(app).messagebox.showinfo("Generation running", "Wait for the current generation to finish before switching style.")
        return
    if app._weather_enabled_var.get():
        activate(app)
    else:
        deactivate(app)
        app._sync_primary_cta()


def restore(app, ws) -> None:
    """Reopening a project: Weather's sound switch and (if Weather was the project's style) the style itself."""
    if not hasattr(app, "_weather_enabled_var"):
        return
    app._weather_ok = None
    state = load_state(ws)
    if "sound_design" in state:
        app._weather_sound_var.set(bool(state["sound_design"]))
    saved_fmt = state.get("format")
    app._weather_format_var.set(FORMATS[saved_fmt][0] if saved_fmt in FORMATS else AUTO_LABEL)
    if hasattr(app, "_weather_style_var"):
        from .teamplate import STYLES

        from .newsdoc import KEY as ND_KEY, NAME as ND_NAME

        saved = str(state.get("edit_style") or "").strip().lower()
        if saved in STYLES:
            app._weather_style_var.set(STYLES[saved])
        elif saved == ND_KEY:
            app._weather_style_var.set(ND_NAME)
        elif saved == "auto" or not project(app).beats_csv.is_file():
            app._weather_style_var.set(AUTO_LABEL)
        else:   # a CSV project saved before Auto existed keeps the style it had
            app._weather_style_var.set(STYLES["classic"])
    app._weather_format_btn.configure(text=FORMAT_ACTIONS[current_format(app)])
    if hasattr(app, "_weather_method_var"):
        app._weather_method_var.set(METHOD_SCRIPT)
        sync_style_ui(app)
    app._weather_file_var.set(str(project(app).root) if has_plan(app) and not is_auto(project(app)) else "")
    if state.get("active"):
        activate(app)
    else:
        deactivate(app)
        show_intro(app)


# ---- the Visual Plan table (the plan's footage) --------------------------------------------------------------------------

def populate_visual_plan(app, plan=None) -> None:
    """Put the plan's footage (Hybrid footage beats and cards) in the EXISTING Visual Plan table, one row per clip."""
    from providers.base import SceneRow

    M = _m(app)
    dicts = []
    if plan is not None:
        try:
            from hybrid.app_integration import visual_dicts

            dicts = visual_dicts(plan)
        except Exception as exc:
            app._append_log(f"{TAG} The plan's footage cannot be listed yet: {exc}\n")
    app._scene_rows = [SceneRow.from_csv_row(d) for d in dicts]
    app._scene_rows_owner = "weather"
    app._scene_preview_cache_sig = None
    keep = {M._scene_key(r.scene_number) for r in app._scene_rows}
    app._asset_results = {k: v for k, v in app._asset_results.items() if k in keep}
    if app._workspace is not None:
        app._hydrate_overscaled_assets_from_manifest(images_dir(app._workspace))
    app._render_scene_rows()
    app._refresh_assets_cta()


def footage_rows(app, p, words, voiceover_path, lib_dir, edit_style):
    """Generate without Check plan first: the footage rows of the plan about to be rendered (the same plan the generator builds),
    shown in the Visual Plan table so the clips appear there as they arrive. None when the plan cannot be built yet (the generator
    then reports the plan's problems itself)."""
    try:
        from hybrid.app_integration import visual_dicts
        from pakmap.app_integration import voiceover_duration
        from providers.base import SceneRow

        from .generate import plan_layers

        plan = plan_layers(p, words, voiceover_duration(voiceover_path), library_dir=lib_dir, edit_style=edit_style)[0]
        rows = [SceneRow.from_csv_row(d) for d in visual_dicts(plan)]
    except Exception:
        return None
    app.after(0, lambda: populate_visual_plan(app, plan))
    return rows or None


def clear_visual_plan(app) -> None:
    if getattr(app, "_scene_rows_owner", None) != "weather":
        return
    app._scene_rows_owner = None
    app._scene_rows = []
    app._scene_preview_cache_sig = None
    app._render_scene_rows()


def scene_status(app) -> dict:
    return {str(r.scene_number): app._row_status_from_result(r) for r in getattr(app, "_scene_rows", [])
            if getattr(app, "_scene_rows_owner", None) == "weather"}


# ---- actions -----------------------------------------------------------------------------------------------------------------

def browse(app) -> None:
    M = _m(app)
    if app._weather_running or app._weather_busy:
        M.messagebox.showinfo(STYLE_NAME, "Still working: wait for the current step to finish.")
        return
    if not app._require_workspace("load a Weather plan"):
        return
    paths = M.filedialog.askopenfilenames(title="Select the Weather plan (the one CSV Claude wrote, or beats.csv + weather_layers.csv)",
                                          filetypes=[("Weather plan", "*.csv *.txt"), ("All files", "*.*")], initialdir=str(M._browse_start_dir()))
    if paths:
        load_plan(app, list(paths))


def load_newsdoc_csv(app, text: str) -> bool:
    """News Doc's story CSV: checked (rows it cannot read are named), saved as weather/newsdoc_story.csv. Optional: without it
    News Doc plans everything itself; with it, what each row fills in is used for that sentence."""
    M = _m(app)
    from .newsdoc import story_csv

    notes: list = []
    rows = story_csv.parse(text, notes)
    if not rows:
        M.messagebox.showerror(STYLE_NAME, "This is not a News Doc story CSV (its header needs vo_anchor and shot).\n\n"
                                           "With News Doc selected, Copy the CSV prompt gives Claude the format.")
        return False
    p = project(app)
    p.root.mkdir(parents=True, exist_ok=True)
    (p.root / story_csv.FILE).write_text(text, encoding="utf-8")
    app._weather_file_var.set(str(p.root / story_csv.FILE))
    set_text(app, f"News Doc story CSV loaded: {len(rows)} row(s).\n\n" + ("\n".join(f"  {n}" for n in notes) + "\n\n" if notes else "") +
             "Each row's shot, search and graphic are used for its sentence; everything else is chosen automatically, and every News "
             "Doc graphic is still in the video. Click Check plan to see it, then Generate.")
    app._weather_status_var.set("News Doc story CSV loaded. Check plan or Generate.")
    if hasattr(app, "_weather_method_var"):
        app._weather_method_var.set(METHOD_CSV)
        sync_style_ui(app)
    app._sync_primary_cta()
    return True


def load_plan(app, paths) -> bool:
    """Copy the plan into the project (<project>/weather/beats.csv and weather_layers.csv), then check it if the narration is ready."""
    M = _m(app)
    beats = layers = one_file = None
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="cp1252", errors="replace")
        except OSError as exc:
            M.messagebox.showerror("Cannot read the plan", str(exc))
            return False
        from .newsdoc import KEY as ND_KEY
        from .newsdoc import story_csv

        if current_style(app) == ND_KEY or (story_csv.is_story_csv(text) and split_one_file(text) is None):
            return load_newsdoc_csv(app, text)   # News Doc's optional story CSV (weather/newsdoc_story.csv)
        b, lay = split_plan_text(text)
        if split_one_file(text) is not None:
            one_file = text
        beats, layers = b or beats, lay or layers
    from .intel.engine import enabled as intel_on

    p = project(app)
    if beats is not None and layers is None and p is not None and intel_on(p):
        layers = ""   # no weather rows: Weather Intelligence finds the data graphics itself
    if beats is None or layers is None:
        if one_file is not None or (beats is not None and len(paths) == 1):
            msg = ("This file has the story (beat rows) but no weather graphics: no row says weather in the row column.\n\n"
                   "Use Copy the CSV prompt in the Weather panel (not the Hybrid Map prompt), give it to Claude, and load the CSV it writes.")
        elif beats is None and layers is None:
            msg = ("This is not a Weather plan: its first line must be the header that starts beat,row,vo_anchor.\n\n"
                   "Use Copy the CSV prompt in the Weather panel, give it to Claude, and load the CSV it writes.")
        else:
            missing = " and ".join(n for n, v in (("beats.csv", beats), ("weather_layers.csv", layers)) if v is None)
            msg = (f"The {missing} part is missing.\n\nLoad the whole plan: one CSV made with Copy the CSV prompt, "
                   "or select beats.csv and weather_layers.csv together.")
        M.messagebox.showerror("Not a complete Weather plan", msg)
        return False
    try:
        p.root.mkdir(parents=True, exist_ok=True)
        p.beats_csv.write_text(beats, encoding="utf-8")
        if layers:
            p.layers_csv.write_text(layers, encoding="utf-8")
        elif p.layers_csv.is_file():
            # the previous plan's weather rows belong to that plan: kept beside it, never deleted
            p.layers_csv.replace(p.root / "weather_layers.previous.csv")
        if one_file is not None:
            (p.root / "plan.csv").write_text(one_file, encoding="utf-8")
    except OSError as exc:
        M.messagebox.showerror(STYLE_NAME, f"Could not save the plan in the project: {exc}")
        return False
    app._weather_file_var.set(str(p.root))
    app._weather_ok = None
    if not app._weather_enabled_var.get():
        app._weather_enabled_var.set(True)
        activate(app)
    show_summary(app)
    app._weather_status_var.set("Plan loaded. Next: Fetch data, then Check plan.")
    app._append_log(f"{TAG} Loaded the plan from {', '.join(Path(x).name for x in paths)}\n")
    if app._current_voiceover_path() is not None and (p.resolved_json.is_file() or not p.layers_csv.is_file()):
        check_plan(app)
    app._sync_primary_cta()
    return True


SCRIPT_FORMATS = {"forecast": "FORECAST", "news": "NEWS", "post": "POST-EVENT"}


def script_prompt_text(fmt: str) -> str:
    """weather/prompts/script_prompt.txt with the format filled in (the topic and length are the user's)."""
    text = (Path(__file__).resolve().parent / "prompts" / "script_prompt.txt").read_text(encoding="utf-8")
    return text.replace("<<<FORECAST, NEWS or POST-EVENT>>>", SCRIPT_FORMATS.get(fmt, "NEWS"))


def copy_script_prompt(app) -> None:
    """The prompt that makes Claude write a script this style can show (dates, states, places, data sentences)."""
    M = _m(app)
    try:
        from .newsdoc import KEY as ND_KEY

        text = (script_prompt_text(current_format(app)) if current_style(app) != ND_KEY else
                (Path(__file__).resolve().parent / "prompts" / "newsdoc_script_prompt.txt").read_text(encoding="utf-8"))
    except OSError as exc:
        M.messagebox.showerror("Copy the script prompt", f"The prompt file could not be read: {exc}")
        return
    app.clipboard_clear()
    app.clipboard_append(text)
    app._weather_status_var.set("Script prompt copied. Paste it into Claude, add your topic and length at the end, then record the "
                                "script it writes and use Copy the CSV prompt.")


def copy_prompt(app, event: Optional[str] = None) -> None:
    """The Weather CSV prompt with the project's script (and the cities) in it."""
    M = _m(app)
    for box in getattr(app, "_csv_prompt_script_boxes", []):
        try:
            if box.get("1.0", "end").strip() != getattr(box, "_csv_synced", None):
                app._on_csv_prompt_script_edited(box)
                break
        except Exception:
            pass
    from .cities import cities

    fmt = current_format(app)
    from .newsdoc import KEY as ND_KEY

    if current_style(app) == ND_KEY:   # News Doc: its own story CSV (one row per sentence)
        try:
            prompt = (Path(__file__).resolve().parent / "prompts" / "newsdoc_csv_prompt.txt").read_text(encoding="utf-8")
        except OSError as exc:
            M.messagebox.showerror("Copy the CSV prompt", f"The prompt file could not be read: {exc}")
            return
        script = app._main_script_text()
        app.clipboard_clear()
        app.clipboard_append(prompt.rstrip() + "\n\nSCRIPT:\n" + (script or "(paste the script here)") + "\n")
        app._weather_status_var.set("News Doc CSV prompt copied with your script. Paste it into Claude, save the CSV it writes, then Load plan.")
        return
    try:
        prompt = (Path(__file__).resolve().parent / "prompts" / FORMATS[fmt][1]).read_text(encoding="utf-8")
        if current_style(app) == "teamplate":   # Weather Teamplate: footage-first beats (same CSV columns)
            prompt = prompt.rstrip() + "\n\n" + (Path(__file__).resolve().parent / "prompts" / "teamplate_csv_addendum.txt").read_text(encoding="utf-8")
    except OSError as exc:
        M.messagebox.showerror("Copy the CSV prompt", f"The prompt file could not be read: {exc}")
        return
    script = app._main_script_text()
    names = ", ".join(c.key for c in cities().values())
    given = (f"CITIES YOU MAY USE: {names}" if fmt == "forecast"
             else event or "THE EVENT: (not given: read the event's name, date, states and places from the script's first sentences)")
    text = prompt.rstrip() + f"\n\n{given}\n\nSCRIPT:\n" + (script or "(paste the script here)") + "\n"
    app.clipboard_clear()
    app.clipboard_append(text)
    app._weather_status_var.set("Weather prompt copied with your script. Paste it into Claude, save the CSV it writes, then Load plan."
                                if script else "Weather prompt copied. Paste it into any AI, put your script after SCRIPT:, then Load plan.")


def open_folder(app) -> None:
    M = _m(app)
    p = project(app)
    if p is None:
        return
    p.root.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(p.root)])
        elif sys.platform == "win32":
            os.startfile(str(p.root))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(p.root)])
        app._weather_status_var.set("Edit plan.csv there and save, then Load plan and pick it again (or edit beats.csv / "
                                    "weather_layers.csv and click Check plan).")
    except Exception as exc:
        M.messagebox.showerror(STYLE_NAME, f"Could not open the folder: {exc}")


def fetch(app) -> None:
    """Fetch the National Weather Service data the plan needs (resolved.json), in the background."""
    M = _m(app)
    if app._weather_busy or app._weather_running:
        return
    if not has_plan(app):
        M.messagebox.showinfo(STYLE_NAME, "Load the plan first: the data fetched is what its weather layers need.")
        return
    contact = str(app._settings.get(SETTING_CONTACT) or "").strip()
    if not contact and current_format(app) == "forecast":   # News / Post-Event archives need no NWS contact
        M.messagebox.showinfo(STYLE_NAME, "The National Weather Service asks every app for a contact (your email address or website).\n\n"
                                          "Type yours in Settings > General > Weather, then click Fetch data again.")
        return
    p = project(app)
    from .intel.engine import load_auto_plan

    if not p.layers_csv.is_file() and load_auto_plan(p) is None:
        app._weather_status_var.set("The plan has no weather rows: Check plan runs Weather Intelligence, which finds the event's data "
                                    "and fetches it.")
        if app._current_voiceover_path() is not None:
            check_plan(app)
        return
    app._weather_busy = True
    app._weather_status_var.set("Fetching the National Weather Service data…")
    app._sync_primary_cta()

    def worker() -> None:
        try:
            from .generate import fetch as do_fetch

            snap = do_fetch(p, contact)
            msg, ok = None, True
            notes = list(snap.notes)
        except Exception as exc:
            msg, ok, notes = str(getattr(exc, "problems", None) and "; ".join(exc.problems) or exc), False, []
        app.after(0, lambda: done(ok, msg, notes))

    def done(ok: bool, msg: Optional[str], notes) -> None:
        app._weather_busy = False
        app._weather_ok = None
        for n in notes:
            app._append_log(f"{TAG} {n}\n")
        if ok:
            show_summary(app)
            left = sum(1 for n in notes if "is left out of this video" in n)
            app._weather_status_var.set("Data fetched. Next: Check plan (it needs the voiceover), then Generate." if not left else
                                        f"Data fetched; {left} graphic(s) could not be downloaded and are left out (see the log). "
                                        "Fetch data again to retry them, or go on: Check plan, then Generate.")
            if app._current_voiceover_path() is not None:
                check_plan(app)
        else:
            app._weather_status_var.set(f"Fetch failed: {msg}")
            app._append_log(f"{TAG} Fetch failed: {msg}\n")
        app._sync_primary_cta()

    threading.Thread(target=worker, daemon=True).start()


def refresh_data(p, contact: str, fmt: str, log) -> None:
    """Fetch the weather data again when it is missing or too old to render from, so Check plan and Generate never stop for it.
    Runs in a worker thread (the settings it needs are read before). Without a contact a Forecast cannot fetch: the render then
    says so plainly."""
    from datetime import datetime, timezone

    from .generate import fetch as do_fetch, load_snapshot
    from .resolve import check_fresh

    try:
        check_fresh(load_snapshot(p), datetime.now(timezone.utc))
        return
    except Exception:
        pass
    if not contact and fmt == "forecast":
        return
    log(f"{TAG} The weather data was missing or older than 6 hours: fetching it again…")
    try:
        snap = do_fetch(p, contact)
        for n in snap.notes:
            log(f"{TAG} {n}")
        log(f"{TAG} Fresh weather data fetched. If a number you say in the narration changed a lot, re-record that line.")
    except Exception as exc:
        log(f"{TAG} Could not fetch the weather data again: {exc}")


def check_plan(app) -> None:
    """Time the plan against the narration, check every row and the data's freshness, list the footage (no rendering)."""
    M = _m(app)
    if app._weather_busy or app._weather_running:
        return
    if not has_plan(app):
        M.messagebox.showinfo(STYLE_NAME, "Load the plan first.")
        return
    voiceover = app._current_voiceover_path()
    if voiceover is None:
        M.messagebox.showinfo(STYLE_NAME, "Choose the voiceover first: the plan is timed by your words.")
        return
    ws, p = app._workspace, project(app)
    model, state_dir = app.model_var.get().strip() or "base", getattr(ws, "state_dir", None)
    style = current_style(app)
    contact, fmt, lib = str(app._settings.get(SETTING_CONTACT) or "").strip(), current_format(app), library_dir(app)
    script_note = sync_script(app, p)
    app._weather_busy = True
    app._weather_status_var.set("Checking the plan against the narration…")
    app._sync_primary_cta()
    log = lambda m: app.after(0, lambda: app._append_log(f"{m}\n"))  # noqa: E731

    def worker() -> None:
        plan, ok = None, False
        warn_if_old(log)
        from .newsdoc import KEY as ND_KEY

        if style == ND_KEY:
            plan, text, ok = newsdoc_check(app, p, voiceover, model, state_dir, fmt, contact, log, script_note)
            app.after(0, lambda: done(text, ok, plan))
            return
        try:
            from pakmap.app_integration import voiceover_duration

            from .footage import footage_beats

            words = voiceover_words(app, p, voiceover, model, state_dir, log)
            fixed: list = [script_note] if script_note else []
            run_intelligence(p, words, voiceover, fmt, contact, log, fixed)
            refresh_data(p, contact, fmt, log)
            # the dry run: every stage Generate runs before it fetches a clip or draws a frame (weather/preflight.py), so every
            # reason Generate would stop is listed here at once, with every repair it made
            from .preflight import preflight

            dry = preflight(p, words, voiceover_duration(voiceover), edit_style=style, library_dir=lib, voiceover_path=voiceover)
            fixed += [n for n in dry.notes if n not in fixed]
            if dry.plan is None:
                raise PlanStops(dry)
            plan, rows, payload = dry.plan, dry.rows, dry.payload
            bad = [f"[{stage}] {m}" for stage, m in dry.stops]
            head = [f"Plan OK: {len(plan.beats)} beat(s) ({footage_beats(plan)} full-screen footage), {len(rows)} weather layer(s), "
                    f"{len(payload.report.lines)} number(s) on screen.", data_status(app), ""]
            if is_auto(p):
                from .teamplate import NAME

                head = [f"Automatic plan (no CSV): format {FORMATS[fmt][0]}, editing style {NAME if style == 'teamplate' else 'Weather'}."] + head
            from .selfcheck import as_text, checks

            head += ["Checks before the render:", as_text(checks(plan, payload)), ""]
            if fixed:
                head += ["Fixed for you (nothing to do):"] + [f"  {x}" for x in fixed] + [""]
            if bad:
                head = ["Generate would stop on these (the tool should have repaired them: report them so they get fixed):"] + \
                       [f"  {b}" for b in bad] + [""] + head
            text, ok = "\n".join(head) + payload.report.to_text(), not bad
        except Exception as exc:
            probs = getattr(exc, "problems", None) or [str(exc)]
            text = "The plan has problems:\n\n" + "\n".join(f"  {x}" for x in probs)
        app.after(0, lambda: done(text, ok, plan))

    def done(text: str, ok: bool, plan) -> None:
        app._weather_busy = False
        app._weather_ok = ok
        set_text(app, text)
        if plan is not None:
            populate_visual_plan(app, plan)
        app._weather_status_var.set("Plan OK: find or replace the footage in the Visual Plan (or let Generate find it), then Generate." if ok
                                    else "The plan has problems (see above): fix the files (Open plan folder), or Fetch data again.")
        app._sync_primary_cta()

    threading.Thread(target=worker, daemon=True).start()


def newsdoc_check(app, p, voiceover, model, state_dir, fmt, contact, log, script_note):
    """Check plan for News Doc: its whole plan (story, event data, news footage, shots, graphics) without rendering."""
    try:
        from pakmap.app_integration import voiceover_duration

        from .newsdoc import NAME
        from .newsdoc.generate import plan_newsdoc

        words = voiceover_words(app, p, voiceover, model, state_dir, log)
        nd, payload, notes, got = plan_newsdoc(p, words, voiceover_duration(voiceover), fmt=fmt, contact=contact, voiceover=Path(voiceover), log=log)
        sh = nd.shares()
        from collections import Counter

        kinds = Counter(o.kind for o in nd.overlays)
        maps = [s for s in nd.shots if s.kind == "map"]
        head = [f"{NAME} plan: {len(nd.shots)} shots — news {sh['news']:.0%}, b-roll {sh['stock']:.0%}, map {sh['map']:.0%} "
                f"({sum(s.t1 - s.t0 for s in maps):.0f} s of {nd.hybrid.duration:.0f} s, limit 10 %), full-screen graphics {sh['fullscreen_graphics']:.0%}.",
                "Graphics: " + (", ".join(f"{n} {k}" for k, n in kinds.most_common()) or "none"),
                "Map shots: " + ("; ".join(f"{s.t0:.0f}-{s.t1:.0f}s ({', '.join(s.rows) or 'the region'})" for s in maps) or "none"), ""]
        if got.searches:
            head += ["News searches: " + "; ".join(got.searches), ""]
        if script_note:
            notes = [script_note] + list(notes)
        if notes:
            head += ["Notes (nothing to do):"] + [f"  {x}" for x in notes] + [""]
        return nd.hybrid, "\n".join(head) + payload.report.to_text(), True
    except Exception as exc:
        return None, f"The News Doc plan could not be made: {exc}", False


class PlanStops(Exception):
    """Check plan: the dry run stopped before it had a plan (its stops are the problems)."""

    def __init__(self, dry):
        super().__init__("; ".join(m for _s, m in dry.stops))
        self.problems = [m for _s, m in dry.stops] + ([""] + ["Fixed on the way:"] + [f"  {n}" for n in dry.notes] if dry.notes else [])



# ---- old code: the app was started before the tool was updated ------------------------------------------------------------------

_CODE_DIRS = ("weather", "hybrid", "pakmap", "weather-engine", "pakmap-engine", "providers")


def _code_stamp() -> float:
    """The newest change time of the tool's code (Python and the renderers)."""
    root = Path(__file__).resolve().parent.parent
    newest = 0.0
    for d in _CODE_DIRS:
        for f in (root / d).rglob("*"):
            if f.suffix in (".py", ".mjs") and "node_modules" not in f.parts:
                try:
                    newest = max(newest, f.stat().st_mtime)
                except OSError:
                    pass
    for f in ("asset_manager.py", "video_generator.py", "app.py"):
        try:
            newest = max(newest, (root / f).stat().st_mtime)
        except OSError:
            pass
    return newest


_STARTED_STAMP: Optional[float] = None


def code_is_old() -> bool:
    """True when the tool's code changed after this app started (its fixes are not loaded until the app is restarted)."""
    global _STARTED_STAMP
    try:
        if _STARTED_STAMP is None:
            _STARTED_STAMP = _code_stamp()
            return False
        return _code_stamp() > _STARTED_STAMP + 1.0
    except Exception:
        return False


def warn_if_old(log) -> None:
    if code_is_old():
        log("[WEATHER] NOTE: the tool was updated after this app started; restart the app to use the latest fixes "
            "(this run uses the code that was loaded when the app opened).")


# ---- the shared Generate button --------------------------------------------------------------------------------------------

def sync_cta(app) -> None:
    if app._weather_busy:
        app._cta_action = "none"
        app._set_generate_btn(state="disabled", text="Working…")
        return
    if app._weather_running:
        app._cta_action = "weather_cancel"
        app.stage_var.set("GENERATING")
        if app._weather_cancel.is_set():
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
        app.hint_var.set("Record your voiceover, then select or import it to continue.")
        app._set_generate_btn(state="normal", text="Import Voiceover")
        return
    if not has_plan(app):
        app._cta_action = "weather_load"
        app.stage_var.set("PLAN")
        app.hint_var.set("Load your Weather plan (Copy the CSV prompt in the Weather panel gives any AI the instructions).")
        app._set_generate_btn(state="normal", text="Load plan")
        return
    if not is_auto(project(app)) and not project(app).resolved_json.is_file():
        app._cta_action = "weather_fetch"
        app.stage_var.set("PLAN")
        app.hint_var.set("Fetch the National Weather Service data for the plan.")
        app._set_generate_btn(state="normal", text="Fetch data")
        return
    app._cta_action = "generate"
    app.stage_var.set("GENERATE")
    app.hint_var.set("Ready — click Generate to render the Weather video." if app._weather_ok is not False
                     else "The last Check plan found problems: fix them first (Generate will stop on them).")
    app._set_generate_btn(state="normal", text="Generate")


def cancel(app) -> None:
    if not app._weather_running or app._weather_cancel.is_set():
        return
    app._weather_cancel.set()
    app._append_log(f"{TAG} Stop requested — cancelling the current step…\n")
    manager = getattr(app, "_weather_run_manager", None)
    if manager is not None:
        try:
            manager.request_cancel()
        except Exception as exc:
            app._append_log(f"{TAG} Could not signal the footage batch to stop: {exc}\n")
    try:
        from hardware.process_registry import get_registry

        from .render import OWNER

        get_registry().terminate_owned(owner=OWNER)
    except Exception as exc:
        app._append_log(f"{TAG} Could not stop the running renderer: {exc}\n")
    app._sync_primary_cta()


def run_generation(app, preview: bool = False) -> None:
    """The Weather branch of the SHARED _on_generate() entry point (generation_mode == "weather"). `preview`: Quick preview — the
    same plan rendered fast (12 frames a second, no sound design) to weather/_work/preview.mp4, not to the project's final folder."""
    M = _m(app)
    if app._weather_running or app._weather_busy:
        return
    if app._workspace is None:
        M.messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    if not has_plan(app):
        M.messagebox.showerror("Cannot start", "There is no Weather plan yet: click Load plan.")
        return
    voiceover_path = app._current_voiceover_path()
    if voiceover_path is None:
        M.messagebox.showerror("Cannot start", "Select or import your voiceover first.")
        return
    ws, p = app._workspace, project(app)
    output_path = (p.work_dir / "preview.mp4") if preview else ws.next_final_path()
    if not preview:
        app.output_var.set(str(output_path))
    script_note = sync_script(app, p)
    whisper_model = app.model_var.get().strip() or "base"
    whisper_state_dir = getattr(ws, "state_dir", None)
    watermark = app._pakmap_watermark()
    sound_design = bool(app._weather_sound_var.get()) and not preview
    pixel_scale = 1 if preview else app._export_pixel_scale()
    speed = {"fps": 12} if preview else {}
    title = getattr(ws, "title", "") or ""
    pexels_api_key = app.pexels_key_var.get().strip() or os.environ.get("PEXELS_API_KEY", "")
    plan_rows = list(app._scene_rows) if getattr(app, "_scene_rows_owner", None) == "weather" else None
    media_dir = images_dir(ws)
    lib_dir = library_dir(app)
    edit_style = current_style(app)

    app._weather_cancel.clear()
    app._weather_running = True
    app._weather_tracking = app._track_generation_start("weather")
    app._weather_run_manager = None
    app._sync_primary_cta()
    app._weather_status_var.set("Starting the quick preview…" if preview else "Starting Weather generation…")
    app._append_log("Starting the Weather quick preview (12 fps, no sound design)…\n" if preview else "Starting Weather generation…\n")
    if script_note:
        app._append_log(f"{TAG} {script_note}\n")

    def progress_cb(message: str, fraction: float) -> None:
        def apply() -> None:
            app._weather_status_var.set(f"{message} ({int(fraction * 100)}%)")
            app.hint_var.set(f"{message} ({int(fraction * 100)}%)")
        app.after(0, apply)

    def thread_safe_log(message: str) -> None:
        app.after(0, lambda: app._append_log(f"{message}\n"))

    def _scene_start(scene, source) -> None:
        app._ui_queue.put(("scene_busy", (scene.scene_number, M._scene_busy_kind(source))))

    def _scene_generating(scene) -> None:
        app._ui_queue.put(("scene_busy", (scene.scene_number, "generating")))

    def _scene_complete(scene, result) -> None:
        app._ui_queue.put(("scene_asset", (scene.scene_number, result)))

    def _manager_ready(manager) -> None:
        app._apply_footage_quality(manager)
        app._asset_manager = manager
        app._weather_run_manager = manager

    gen_contact, gen_format = str(app._settings.get(SETTING_CONTACT) or "").strip(), current_format(app)

    def worker() -> None:
        from pakmap.app_integration import PakmapResult

        from .generate import generate_forecast_video

        prun = app._production_begin("weather")
        warn_if_old(thread_safe_log)
        try:
            try:
                words = voiceover_words(app, p, voiceover_path, whisper_model, whisper_state_dir, thread_safe_log)
            except Exception as exc:
                result = PakmapResult(False, [f"Could not transcribe the narration: {exc}"])
            else:
                from .newsdoc import KEY as ND_KEY

                if edit_style == ND_KEY:   # News Doc plans, fetches and draws on its own (weather/newsdoc)
                    from .newsdoc.generate import generate_newsdoc_video

                    result = generate_newsdoc_video(
                        p, voiceover_path, output_path, whisper_words=words, log=thread_safe_log, fmt=gen_format, contact=gen_contact,
                        progress_cb=progress_cb, cancel_check=app._weather_cancel.is_set, watermark=watermark, title=title,
                        sound_design=sound_design, pixel_scale=pixel_scale, pexels_api_key=pexels_api_key, media_dir=media_dir,
                        media_callbacks=dict(on_scene_start=_scene_start, on_scene_complete=_scene_complete, on_scene_generating=_scene_generating,
                                             on_manager_ready=_manager_ready), **speed)
                    app._production_end(prun, result, app._weather_cancel.is_set())
                    app.after(0, lambda: finish(result))
                    return
                added: list = []
                run_intelligence(p, words, voiceover_path, gen_format, gen_contact, thread_safe_log, added)
                for n in added:
                    thread_safe_log(f"{TAG} {n}")
                refresh_data(p, gen_contact, gen_format, thread_safe_log)
                rows = plan_rows or footage_rows(app, p, words, voiceover_path, lib_dir, edit_style)
                result = generate_forecast_video(
                    p, voiceover_path, output_path, whisper_words=words, log=thread_safe_log, watermark=watermark, title=title,
                    sound_design=sound_design, pixel_scale=pixel_scale, progress_cb=progress_cb, cancel_check=app._weather_cancel.is_set,
                    pexels_api_key=pexels_api_key, scene_rows=rows, media_dir=media_dir, library_dir=lib_dir, edit_style=edit_style,
                    media_callbacks=dict(on_scene_start=_scene_start, on_scene_complete=_scene_complete, on_scene_generating=_scene_generating,
                                         on_manager_ready=_manager_ready), **speed,
                )
        except Exception as exc:
            result = PakmapResult(False, [f"Unexpected error: {exc!r}"])
        app._production_end(prun, result, app._weather_cancel.is_set())
        app.after(0, lambda: finish(result))

    def finish(result) -> None:
        app._weather_running = False
        cancelled = bool(getattr(result, "cancelled", False)) or app._weather_cancel.is_set()
        app._weather_cancel.clear()
        run, app._weather_tracking = app._weather_tracking, None
        app._track_generation_end(run, "cancelled" if (cancelled and not result.ok) else ("completed" if result.ok else "failed"),
                                  output_path=result.output_path, validated=True, message="\n".join(str(e) for e in (result.errors or [])))
        if cancelled and not result.ok:
            app._weather_status_var.set("Cancelled")
            app._append_log(f"{TAG} Generation cancelled. Nothing was exported; Generate again to restart.\n")
            app._sync_primary_cta()
            return
        if result.ok:
            app._weather_status_var.set(f"Done: {result.output_path}")
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
            if preview:
                M.messagebox.showinfo("Quick preview ready", f"Saved to:\n{result.output_path}\n\nA fast, low-quality copy to check the plan "
                                                             "(12 frames a second, no sound design). Click Generate for the real video.")
            else:
                M.messagebox.showinfo("Weather video ready", f"Saved to:\n{result.output_path}\n\nNext to it: the credits ('… - credits.txt') and every "
                                                             "number on screen with its source ('….numbers.txt').")
        else:
            app._append_log(f"{TAG} Generation failed:\n" + "\n".join(result.errors) + "\n")
            set_text(app, "Generation stopped:\n\n" + "\n".join(f"  {e}" for e in result.errors))
            if getattr(result, "unresolved", None):
                app._weather_status_var.set(f"{len(result.unresolved)} clip(s) need attention — fix them in the Visual Plan tab, then Generate again")
                app._refresh_qa_ui(immediate=True)
                app._goto_workflow_view("visual_plan")
            elif any("not fresh enough" in str(e) for e in result.errors):
                app._weather_status_var.set("The weather data is too old: click Fetch data, re-record any line whose numbers changed, then Generate.")
            else:
                app._weather_status_var.set("Failed — see the plan box and the log")
            app._show_error_dialog("Generation failed", M.overscaled_failure_summary(result.errors), "\n".join(result.errors) or "Unknown error")
        app._sync_primary_cta()

    threading.Thread(target=worker, daemon=True).start()


# ---- Settings > General ---------------------------------------------------------------------------------------------------

def on_format(app) -> None:
    """Forecast / News / Post-Event: which CSV prompt the card copies (the plan files and the render are the same for all three)."""
    fmt = current_format(app)
    save_state(app, format=format_choice(app))
    if hasattr(app, "_weather_format_btn"):
        app._weather_format_btn.configure(text=FORMAT_ACTIONS[fmt])
    auto = f"Auto: Weather reads your script and picks the format (now: {FORMATS[fmt][0]}). " if format_choice(app) == "auto" else ""
    app._weather_status_var.set(auto + {
        "forecast": "Forecast: Copy the CSV prompt (or Prepare today's forecast to have the app write the script and plan from the data).",
        "news": "News: one event (a hurricane, an outbreak, a flood) with its radar, track, cone, warnings and counters. Copy the CSV prompt "
                "and give the AI the event's name, dates and places with your script.",
        "post": "Post-Event: what an event left behind (rain totals, records, river crests, before/after from space, a timeline). Copy the "
                "CSV prompt and give the AI the event's name, dates and places with your script.",
    }[fmt])


def format_action(app) -> None:
    {"forecast": prepare_today, "news": event_footage, "post": suggested_reports}[current_format(app)](app)


def suggested_reports(app) -> None:
    """Post-Event: events whose warnings are over and whose data is in (weather.post.feed + suggest), newest first. Picking one copies
    the Post-Event prompt with the event filled in; nothing is fetched for the video until the user loads a plan."""
    M = _m(app)
    if app._weather_busy:
        return
    contact = str(app._settings.get(SETTING_CONTACT) or "").strip()
    if not contact:
        M.messagebox.showinfo(STYLE_NAME, "The suggestions read the National Weather Service's warnings, and it asks every app for a contact.\n\n"
                                          "Type yours in Settings > General > Weather, then try again.")
        return
    app._weather_busy = True
    app._weather_status_var.set("Looking for events that are over and whose data is in (NWS warnings, SPC storm reports)…")

    def worker() -> None:
        try:
            from datetime import datetime, timezone

            from .layers import http_text
            from .nws import NwsClient
            from .post.feed import suggestions

            found, problems = suggestions(NwsClient(contact), http_text, datetime.now(timezone.utc),
                                          already=list(app._settings.get(SETTING_SUGGESTED) or []))
            out = (found, problems, None)
        except Exception as exc:
            out = ([], [], str(exc))
        app.after(0, lambda: done(*out))

    def done(found, problems, err) -> None:
        app._weather_busy = False
        if err:
            app._weather_status_var.set(f"Suggestions failed: {err}")
            return
        for pr in problems:
            app._append_log(f"{TAG} {pr}\n")
        if not found:
            app._weather_status_var.set("No event is ready for a post-event report right now (none over, big enough and not offered before).")
            return
        app._weather_status_var.set(f"{len(found)} event(s) ready for a post-event report.")
        show_suggestions(app, found)

    threading.Thread(target=worker, daemon=True).start()


def show_suggestions(app, found) -> None:
    from .post.feed import event_text

    M = _m(app)
    ctk = M.ctk
    win = ctk.CTkToplevel(app)
    win.title("Weather · Suggested post-event reports")
    win.geometry("760x520")
    body = ctk.CTkScrollableFrame(win, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=10, pady=10)

    def take(s) -> None:
        app._settings[SETTING_SUGGESTED] = list(app._settings.get(SETTING_SUGGESTED) or []) + [s.id]
        try:
            M.save_settings(app._settings)
        except Exception:
            pass
        copy_prompt(app, event=event_text(s))
        win.destroy()

    for s in found[:20]:
        f = ctk.CTkFrame(body, fg_color=M._CARD, corner_radius=8, border_width=1, border_color=M._BORDER)
        f.pack(fill="x", pady=4)
        ctk.CTkLabel(f, text=s.title, font=ctk.CTkFont(size=12, weight="bold"), text_color=M._TEXT, anchor="w").pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(f, text=f"{s.warnings} warning(s) · {s.reports} storm report(s) · " + "; ".join(s.why), font=ctk.CTkFont(size=11),
                     text_color=M._MUTED, anchor="w", wraplength=680, justify="left").pack(anchor="w", padx=12)
        ctk.CTkButton(f, text="Make this report (copy the prompt)", width=230, command=lambda s=s: take(s)).pack(anchor="w", padx=12, pady=(4, 8))


def on_style(app) -> None:
    """Weather / Weather Teamplate: how the same plan is edited (the plan files, the data and the narration are the same)."""
    from .teamplate import NAME

    style = current_style(app)
    save_state(app, edit_style=style_choice(app))
    app._weather_ok = None
    # the other style's footage list numbers its clips differently: never hand it to this style's render
    clear_visual_plan(app)
    from .newsdoc import KEY as ND_KEY

    sync_style_ui(app)
    if style == ND_KEY:
        app._weather_status_var.set("News Doc: footage first, like a TV-news documentary — local news reports of the event, b-roll, place and "
                                    "yellow tags, big numbers, quote cards, checklists and charts; the satellite map with the storm's data "
                                    "only at its strongest moments (at most 10 % of the video). Click Check plan to see it, then Generate.")
        return
    app._weather_status_var.set(
        f"{NAME}: hard cuts on a ~5 s shot rhythm, keyword title cards over a darkened frame, count-up numbers, orange place tags and a "
        "darker map. Same plan, data and narration; click Check plan to see the footage it will use." if style == "teamplate" else
        "Weather: the map-first edit with the HUD title, dissolves between the map and footage, and camera flights between places.")


def event_footage(app) -> None:
    """News / Post-Event: the clip screen (find, check, approve, label, download, put in beats). Forecast uses stock b-roll instead."""
    M = _m(app)
    if app._workspace is None:
        return
    if current_format(app) == "forecast":
        M.messagebox.showinfo(STYLE_NAME, "Event footage is for News and Post-Event videos. A forecast uses general weather b-roll "
                                          "(your own footage folder first, then stock).")
        return
    from .clip_review import open_window

    open_window(app)


def prepare_today(app) -> None:
    """Forecast only: the app writes today's script and plan from the National Weather Service data (weather.automation.prep) into the
    project; the user records script.txt. A script.txt the user edited is never replaced."""
    M = _m(app)
    if app._weather_busy or app._weather_running:
        return
    if current_format(app) != "forecast":
        M.messagebox.showinfo(STYLE_NAME, "Prepare today's forecast writes a Forecast. Pick the Forecast format first.")
        return
    contact = str(app._settings.get(SETTING_CONTACT) or "").strip()
    if not contact:
        M.messagebox.showinfo(STYLE_NAME, "The National Weather Service asks every app for a contact (your email address or website).\n\n"
                                          "Type yours in Settings > General > Weather, then try again.")
        return
    p = project(app)
    if p is None:
        return
    if p.beats_csv.is_file() and not M.messagebox.askyesno(STYLE_NAME, "This project already has a Weather plan. Replace it with today's "
                                                                        "forecast? (A script.txt you edited is kept.)"):
        return
    app._weather_busy = True
    app._weather_status_var.set("Preparing today's forecast from the National Weather Service data (about a minute)…")
    app._sync_primary_cta()
    log = lambda m: app.after(0, lambda: app._append_log(f"{TAG} {m}\n"))  # noqa: E731

    def worker() -> None:
        try:
            from .automation.prep import prep

            res = prep(p.root, contact, library_dir=library_dir(app), log=log)
            out = (True, res.summary, list(res.notes))
        except Exception as exc:
            out = (False, str(exc), [])
        app.after(0, lambda: done(*out))

    def done(ok: bool, msg: str, notes) -> None:
        app._weather_busy = False
        app._weather_ok = None
        for n in notes:
            app._append_log(f"{TAG} {n}\n")
        if ok:
            app._weather_file_var.set(str(p.root))
            box = getattr(app, "script_box", None)
            script = p.root / "script.txt"
            try:
                if box is not None and not box.get("1.0", "end").strip() and script.is_file():
                    box.insert("1.0", script.read_text(encoding="utf-8"))
                    app._refresh_csv_prompt_script_boxes()
            except Exception:
                pass
            show_summary(app)
            app._weather_status_var.set(f"{msg} Record the script ({script}), add the voiceover, then Check plan and Generate.")
            app._append_log(f"{TAG} {msg}\n")
        else:
            app._weather_status_var.set(f"Prepare failed: {msg}")
            app._append_log(f"{TAG} Prepare failed: {msg}\n")
        app._sync_primary_cta()

    threading.Thread(target=worker, daemon=True).start()


def build_settings(app, body, save_settings) -> None:
    """The Weather switch and the NWS contact, at the end of Settings > General (app-wide)."""
    M = _m(app)
    ctk = M.ctk
    ctk.CTkLabel(body, text="WEATHER (BETA)", font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED).pack(anchor="w", padx=20, pady=(20, 4))
    on = ctk.BooleanVar(value=enabled(app._settings))
    contact = ctk.StringVar(value=str(app._settings.get(SETTING_CONTACT) or ""))

    def save(*_a) -> None:
        app._settings[SETTING_CONTACT] = contact.get().strip()
        try:
            save_settings(app._settings)
        except Exception:
            pass

    def toggle() -> None:
        """On needs the password (weather/lock.py); off never does. The rest of the section shows only while Weather is on."""
        from . import lock

        if on.get():
            if not lock.has_password():
                on.set(False)
                M.messagebox.showinfo(STYLE_NAME, "No Weather password is set yet. Set one in a terminal:\n\n.venv310/bin/python -m weather.lock")
                return
            from tkinter import simpledialog

            pw = simpledialog.askstring(STYLE_NAME, "Password to show the Weather style:", show="*", parent=body.winfo_toplevel())
            if pw is None or not lock.check(pw):
                on.set(False)
                if pw is not None:
                    M.messagebox.showerror(STYLE_NAME, "Wrong password. Weather stays hidden.")
                return
            app._settings[SETTING_ON], app._settings[lock.SETTING_TOKEN] = True, lock.token()
            rest.pack(anchor="w", fill="x", after=switch)
        else:
            app._settings[SETTING_ON] = False
            app._settings.pop(lock.SETTING_TOKEN, None)
            rest.pack_forget()
        save()

    switch = ctk.CTkSwitch(body, text="Show the Weather style (locked: asks for the password)", variable=on, command=toggle,
                           font=ctk.CTkFont(size=12))
    switch.pack(anchor="w", padx=20, pady=(0, 4))
    rest = ctk.CTkFrame(body, fg_color="transparent")
    if on.get():
        rest.pack(anchor="w", fill="x")
    row = ctk.CTkFrame(rest, fg_color="transparent")
    row.pack(anchor="w", padx=20, pady=(4, 0), fill="x")
    ctk.CTkLabel(row, text="NWS contact", font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED).pack(side="left", padx=(0, 8))
    entry = ctk.CTkEntry(row, textvariable=contact, height=30, placeholder_text="your email or website (the NWS asks every app for one)")
    entry.pack(side="left", fill="x", expand=True)
    entry.bind("<FocusOut>", save)
    contact.trace_add("write", save)
    lib = ctk.StringVar(value=str(app._settings.get(SETTING_LIBRARY) or ""))

    def save_lib(*_a) -> None:
        app._settings[SETTING_LIBRARY] = lib.get().strip()
        try:
            save_settings(app._settings)
        except Exception:
            pass

    def pick_lib() -> None:
        d = M.filedialog.askdirectory(title="Your weather footage folder (clips named by what they show: rain, storm, snow, sunny…)")
        if d:
            lib.set(d)
            save_lib()

    lrow = ctk.CTkFrame(rest, fg_color="transparent")
    lrow.pack(anchor="w", padx=20, pady=(6, 0), fill="x")
    ctk.CTkLabel(lrow, text="Your footage", font=ctk.CTkFont(size=11, weight="bold"), text_color=M._MUTED).pack(side="left", padx=(0, 8))
    lentry = ctk.CTkEntry(lrow, textvariable=lib, height=30, placeholder_text="optional: a folder of your own clips, used before stock")
    lentry.pack(side="left", fill="x", expand=True)
    lentry.bind("<FocusOut>", save_lib)
    ctk.CTkButton(lrow, text="Choose…", width=80, height=30, command=pick_lib).pack(side="left", padx=(6, 0))
    sched_root = str(app._settings.get(SETTING_SCHEDULE_ROOT) or (Path.home() / "Weather"))
    sched = ctk.BooleanVar(value=bool(app._settings.get(SETTING_SCHEDULE_ROOT)))

    def toggle_schedule() -> None:
        """Installs or removes the OS task ONLY here, on the user's click."""
        from .automation import schedule

        try:
            if sched.get():
                if not contact.get().strip():
                    sched.set(False)
                    M.messagebox.showinfo(STYLE_NAME, "Type your NWS contact first: the daily prep sends it to the National Weather Service.")
                    return
                msg = schedule.install(sched_root, contact.get().strip())
                app._settings[SETTING_SCHEDULE_ROOT] = sched_root
            else:
                msg = schedule.uninstall()
                app._settings.pop(SETTING_SCHEDULE_ROOT, None)
            save_settings(app._settings)
            app._append_log(f"{TAG} {msg}\n")
        except Exception as exc:
            sched.set(not sched.get())
            M.messagebox.showerror(STYLE_NAME, f"The daily prep could not be switched: {exc}")

    ctk.CTkSwitch(rest, text=f"Prepare the forecast every morning (5:30 AM Central, into {sched_root})", variable=sched,
                  command=toggle_schedule, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=20, pady=(8, 0))
    ctk.CTkLabel(body, text="Turning Weather on or off takes effect the next time the app starts. Off: the app is exactly as before.",
                 font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", justify="left", wraplength=430).pack(anchor="w", padx=20, pady=(4, 0))
