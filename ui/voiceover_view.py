"""Voiceover tab: turn a script into a free voiceover (Microsoft Edge neural voices via edge-tts) and make it the project's voiceover.

Nothing starts until the user presses Generate (or Preview): choosing a voice, speed or pitch only remembers it. The work runs in a
background thread (edge_voiceover.py); this file only builds the page and moves results back to the UI thread. If the free service
fails the page says so and the user's own audio file (Audio & Effects) keeps working."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk

from . import theme as T
from .widgets import Card, make_button

# (label by use, voice id). Curated so the page opens instantly with no network call.
VOICES = [
    ("Documentary narrator - male, warm", "en-US-AndrewNeural"),
    ("Documentary narrator - male, British", "en-GB-RyanNeural"),
    ("Deep storyteller - male", "en-US-ChristopherNeural"),
    ("Calm explainer - male", "en-US-BrianNeural"),
    ("News anchor - male", "en-US-GuyNeural"),
    ("Clear educator - male", "en-US-EricNeural"),
    ("Natural narrator - female", "en-US-AvaNeural"),
    ("Friendly explainer - female", "en-US-EmmaNeural"),
    ("News anchor - female", "en-US-JennyNeural"),
    ("Documentary narrator - female, British", "en-GB-SoniaNeural"),
    ("Australian narrator - male", "en-AU-WilliamMultilingualNeural"),   # en-AU-WilliamNeural left the list
    ("Australian narrator - female", "en-AU-NatashaNeural"),
    ("Indian English narrator - male", "en-IN-PrabhatNeural"),
    ("Indian English narrator - female", "en-IN-NeerjaNeural"),
]


def _pair(*voices: tuple) -> list:
    return [(f"{name} - {who}", vid) for name, who, vid in voices]


# Other languages: every id checked against Microsoft's live voice list (2026-11-04). Punjabi has no voice there.
LANGUAGES = [
    ("English", VOICES),
    ("Urdu", _pair(("Asad", "male, Pakistan", "ur-PK-AsadNeural"), ("Uzma", "female, Pakistan", "ur-PK-UzmaNeural"),
                   ("Salman", "male, India", "ur-IN-SalmanNeural"), ("Gul", "female, India", "ur-IN-GulNeural"))),
    ("Hindi", _pair(("Madhur", "male", "hi-IN-MadhurNeural"), ("Swara", "female", "hi-IN-SwaraNeural"))),
    ("Arabic", _pair(("Hamed", "male, Saudi", "ar-SA-HamedNeural"), ("Zariyah", "female, Saudi", "ar-SA-ZariyahNeural"),
                     ("Shakir", "male, Egypt", "ar-EG-ShakirNeural"), ("Salma", "female, Egypt", "ar-EG-SalmaNeural"))),
    ("Pashto", _pair(("Gul Nawaz", "male", "ps-AF-GulNawazNeural"), ("Latifa", "female", "ps-AF-LatifaNeural"))),
    ("Persian", _pair(("Farid", "male", "fa-IR-FaridNeural"), ("Dilara", "female", "fa-IR-DilaraNeural"))),
    ("Bengali", _pair(("Pradeep", "male, Bangladesh", "bn-BD-PradeepNeural"), ("Nabanita", "female, Bangladesh", "bn-BD-NabanitaNeural"),
                      ("Bashkar", "male, India", "bn-IN-BashkarNeural"), ("Tanishaa", "female, India", "bn-IN-TanishaaNeural"))),
    ("Tamil", _pair(("Valluvar", "male", "ta-IN-ValluvarNeural"), ("Pallavi", "female", "ta-IN-PallaviNeural"))),
    ("Spanish", _pair(("Alvaro", "male, Spain", "es-ES-AlvaroNeural"), ("Elvira", "female, Spain", "es-ES-ElviraNeural"),
                      ("Jorge", "male, Mexico", "es-MX-JorgeNeural"), ("Dalia", "female, Mexico", "es-MX-DaliaNeural"))),
    ("Portuguese", _pair(("Antonio", "male, Brazil", "pt-BR-AntonioNeural"), ("Francisca", "female, Brazil", "pt-BR-FranciscaNeural"))),
    ("French", _pair(("Henri", "male", "fr-FR-HenriNeural"), ("Denise", "female", "fr-FR-DeniseNeural"))),
    ("German", _pair(("Conrad", "male", "de-DE-ConradNeural"), ("Katja", "female", "de-DE-KatjaNeural"))),
    ("Italian", _pair(("Diego", "male", "it-IT-DiegoNeural"), ("Elsa", "female", "it-IT-ElsaNeural"))),
    ("Dutch", _pair(("Maarten", "male", "nl-NL-MaartenNeural"), ("Colette", "female", "nl-NL-ColetteNeural"))),
    ("Polish", _pair(("Marek", "male", "pl-PL-MarekNeural"), ("Zofia", "female", "pl-PL-ZofiaNeural"))),
    ("Russian", _pair(("Dmitry", "male", "ru-RU-DmitryNeural"), ("Svetlana", "female", "ru-RU-SvetlanaNeural"))),
    ("Turkish", _pair(("Ahmet", "male", "tr-TR-AhmetNeural"), ("Emel", "female", "tr-TR-EmelNeural"))),
    ("Indonesian", _pair(("Ardi", "male", "id-ID-ArdiNeural"), ("Gadis", "female", "id-ID-GadisNeural"))),
    ("Malay", _pair(("Osman", "male", "ms-MY-OsmanNeural"), ("Yasmin", "female", "ms-MY-YasminNeural"))),
    ("Filipino", _pair(("Angelo", "male", "fil-PH-AngeloNeural"), ("Blessica", "female", "fil-PH-BlessicaNeural"))),
    ("Vietnamese", _pair(("Nam Minh", "male", "vi-VN-NamMinhNeural"), ("Hoai My", "female", "vi-VN-HoaiMyNeural"))),
    ("Thai", _pair(("Niwat", "male", "th-TH-NiwatNeural"), ("Premwadee", "female", "th-TH-PremwadeeNeural"))),
    ("Chinese (Mandarin)", _pair(("Yunxi", "male", "zh-CN-YunxiNeural"), ("Yunjian", "male, deep", "zh-CN-YunjianNeural"),
                                 ("Xiaoxiao", "female", "zh-CN-XiaoxiaoNeural"))),
    ("Japanese", _pair(("Keita", "male", "ja-JP-KeitaNeural"), ("Nanami", "female", "ja-JP-NanamiNeural"))),
    ("Korean", _pair(("InJoon", "male", "ko-KR-InJoonNeural"), ("SunHi", "female", "ko-KR-SunHiNeural"))),
    ("Swahili", _pair(("Rafiki", "male", "sw-KE-RafikiNeural"), ("Zuri", "female", "sw-KE-ZuriNeural"))),
]


NO_CLONE = "Off - use the voice above as it is"


def voices_for(language: str) -> list:
    """The (label, voice id) list of one language; English when the name is unknown."""
    return next((v for name, v in LANGUAGES if name == language), VOICES)


_SECONDS_PER_WORD = 0.4   # ~150 spoken words a minute


def adopt_project_voiceover(app: Any, var: Any, previous: str = "") -> None:
    """Fill a style page's own voice-over box with the project voiceover (the file made on the Voiceover tab or chosen on Audio &
    Effects) when the box is empty or still holds the previous project voiceover. Only remembers the path: nothing runs."""
    try:
        cur = (app.audio_var.get() or "").strip()
        if not cur or not Path(cur).is_file():
            return
        have = (var.get() or "").strip()
        if not have or (previous and have == previous):
            var.set(cur)
    except Exception:
        pass


def _share_with_styles(app: Any, previous: str) -> None:
    """After a new voiceover is set, update the style pages that are already built (the others adopt it when opened)."""
    for name in ("_pt_voice_var", "_rc_voice_var", "_vm_voice_var"):
        var = getattr(app, name, None)
        if var is not None:
            adopt_project_voiceover(app, var, previous)


def _find(name: str) -> str:
    root = Path(__file__).resolve().parent.parent
    base = Path(getattr(sys, "_MEIPASS", root)) if getattr(sys, "frozen", False) else root
    cand = base / "bin" / (name + (".exe" if sys.platform == "win32" else ""))
    if cand.is_file():
        return str(cand)
    return shutil.which(name) or name


def build(view: Any, app: Any) -> None:
    view._vo_busy = False
    view._vo_cancel = threading.Event()
    view._vo_lang_var = ctk.StringVar(value=LANGUAGES[0][0])
    view._vo_voice_var = ctk.StringVar(value=VOICES[0][0])
    view._vo_speed_var = ctk.DoubleVar(value=1.0)
    view._vo_pitch_var = ctk.IntVar(value=0)
    view._vo_status_var = ctk.StringVar(value="")
    view._vo_count_var = ctk.StringVar(value="0 words")
    view._vo_clone_var = ctk.StringVar(value=NO_CLONE)
    view._vo_clone_status = ctk.StringVar(value="")

    script = Card(view._body, title="Script", subtitle="The text to speak. Nothing starts until you press Generate.")
    script.grid(row=0, column=0, sticky="ew", pady=(0, 12))
    script.body.grid_columnconfigure(0, weight=1)
    view._vo_text = ctk.CTkTextbox(script.body, height=220, wrap="word")
    view._vo_text.grid(row=0, column=0, sticky="ew")
    view._vo_text.bind("<KeyRelease>", lambda _e: _update_count(view), add="+")
    row = ctk.CTkFrame(script.body, fg_color="transparent")
    row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
    make_button(row, "Use Script tab text", lambda: _from_script_tab(view, app), width=170).grid(row=0, column=0, padx=(0, 8))
    make_button(row, "Open text file...", lambda: _open_file(view), width=150).grid(row=0, column=1, padx=(0, 12))
    ctk.CTkLabel(row, textvariable=view._vo_count_var, text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(row=0, column=2)

    voice = Card(view._body, title="Semantic voices")
    voice.grid(row=1, column=0, sticky="ew", pady=(0, 12))
    voice.body.grid_columnconfigure(3, weight=1)
    ctk.CTkLabel(voice.body, text="Language", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
    ctk.CTkOptionMenu(voice.body, values=[name for name, _ in LANGUAGES], variable=view._vo_lang_var, width=330,
                      command=lambda _v: _language_changed(view)).grid(row=0, column=1, sticky="w", pady=4)
    ctk.CTkLabel(voice.body, text="Voice", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
    view._vo_voice_menu = ctk.CTkOptionMenu(voice.body, values=[v[0] for v in VOICES], variable=view._vo_voice_var, width=330)
    view._vo_voice_menu.grid(row=1, column=1, sticky="w", pady=4)
    ctk.CTkLabel(voice.body, text="Speed", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
    ctk.CTkSlider(voice.body, from_=0.8, to=1.3, number_of_steps=10, variable=view._vo_speed_var, width=260,
                  command=lambda _v: view._vo_speed_lbl.configure(text=f"{view._vo_speed_var.get():.2f}x")).grid(row=2, column=1, sticky="w", pady=4)
    view._vo_speed_lbl = ctk.CTkLabel(voice.body, text="1.00x", text_color=T.MUTED, font=ctk.CTkFont(size=12))
    view._vo_speed_lbl.grid(row=2, column=2, padx=8)
    ctk.CTkLabel(voice.body, text="Pitch", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w", padx=(0, 12), pady=4)
    ctk.CTkSlider(voice.body, from_=-20, to=20, number_of_steps=8, variable=view._vo_pitch_var, width=260,
                  command=lambda _v: view._vo_pitch_lbl.configure(text=f"{int(view._vo_pitch_var.get()):+d} Hz")).grid(row=3, column=1, sticky="w", pady=4)
    view._vo_pitch_lbl = ctk.CTkLabel(voice.body, text="+0 Hz", text_color=T.MUTED, font=ctk.CTkFont(size=12))
    view._vo_pitch_lbl.grid(row=3, column=2, padx=8)
    ctk.CTkLabel(voice.body, text="Write the script in the language you pick: the voice reads it as written, it does not translate.",
                 text_color=T.MUTED, font=ctk.CTkFont(size=11), anchor="w").grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))

    clone = Card(view._body, title="Clone a voice",
                 subtitle="Optional. Make the narration sound like a voice from a sample recording. It runs on this computer; the sample is never uploaded.")
    view._vo_clone_card = clone
    ctk.CTkLabel(clone.body, text="Narrate in", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
    view._vo_clone_menu = ctk.CTkOptionMenu(clone.body, values=[NO_CLONE], variable=view._vo_clone_var, width=330)
    view._vo_clone_menu.grid(row=0, column=1, sticky="w", pady=4)
    cb = ctk.CTkFrame(clone.body, fg_color="transparent")
    cb.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
    make_button(cb, "Add a voice from a recording...", lambda: _add_clone(view, app), width=230).grid(row=0, column=0, padx=(0, 8))
    make_button(cb, "Remove selected", lambda: _remove_clone(view), width=140).grid(row=0, column=1)
    ctk.CTkLabel(clone.body, text="Use 20-60 seconds of one person speaking clearly, with no music or background noise. Only clone a voice that is "
                 "yours or whose owner has agreed. The Voice above is still used for the words, pace and language; the clone changes how it sounds.",
                 text_color=T.MUTED, font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=620).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
    ctk.CTkLabel(clone.body, textvariable=view._vo_clone_status, text_color=T.MUTED, font=ctk.CTkFont(size=12), anchor="w", justify="left",
                 wraplength=620).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
    clone.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    _refresh_clones(view)

    go = Card(view._body, title="Generate",
              subtitle="Semantic voices: natural narration. The audio is made online at about 2-3x real time, so a 10-minute script takes a few minutes.")
    go.grid(row=3, column=0, sticky="ew", pady=(0, 12))
    view._vo_plan_var = ctk.StringVar(value="")
    ctk.CTkLabel(go.body, textvariable=view._vo_plan_var, text_color=T.ACCENT_TEXT, font=ctk.CTkFont(size=13, weight="bold"), anchor="w",
                 justify="left", wraplength=620).grid(row=0, column=0, sticky="w", pady=(0, 8))
    bar = ctk.CTkFrame(go.body, fg_color="transparent")
    bar.grid(row=1, column=0, sticky="w")
    view._vo_preview_btn = make_button(bar, "Preview first sentences", lambda: _start(view, app, preview=True), width=190)
    view._vo_preview_btn.grid(row=0, column=0, padx=(0, 8))
    view._vo_go_btn = ctk.CTkButton(bar, text="Generate voiceover", width=190, height=40, corner_radius=6, fg_color=T.ACCENT, hover_color=T.ACCENT_HOV,
                                    text_color=T.ACCENT_DARK, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: _start(view, app, preview=False))
    view._vo_go_btn.grid(row=0, column=1, padx=(0, 8))
    view._vo_stop_btn = make_button(bar, "Stop", lambda: view._vo_cancel.set(), width=90, state="disabled")
    view._vo_stop_btn.grid(row=0, column=2)
    view._vo_progress = ctk.CTkProgressBar(go.body, width=420)
    view._vo_progress.set(0)
    view._vo_progress.grid(row=2, column=0, sticky="w", pady=(10, 0))
    ctk.CTkLabel(go.body, textvariable=view._vo_status_var, text_color=T.MUTED, font=ctk.CTkFont(size=12), anchor="w", justify="left",
                 wraplength=620).grid(row=3, column=0, sticky="w", pady=(6, 0))

    for var in (view._vo_clone_var, view._vo_voice_var, view._vo_lang_var):
        var.trace_add("write", lambda *_a: _update_plan(view))
    _update_plan(view)

    view._vo_last = None      # the file the Play button plays (the last preview or voiceover made here)
    view._vo_play_proc = None
    view._vo_play_var = ctk.StringVar(value="Nothing to play yet. Generate or preview a voice first.")
    listen = Card(view._body, title="Listen", subtitle="Play the voiceover here before you use it.")
    listen.grid(row=4, column=0, sticky="ew", pady=(0, 12))
    lb = ctk.CTkFrame(listen.body, fg_color="transparent")
    lb.grid(row=0, column=0, sticky="w")
    view._vo_play_btn = make_button(lb, "\u25B6  Play", lambda: _play(view), width=130, state="disabled")
    view._vo_play_btn.grid(row=0, column=0, padx=(0, 8))
    view._vo_stopplay_btn = make_button(lb, "\u25A0  Stop playing", lambda: _stop_play(view), width=150, state="disabled")
    view._vo_stopplay_btn.grid(row=0, column=1, padx=(0, 8))
    view._vo_download_btn = make_button(lb, "\u2193  Download", lambda: _download(view), width=140, state="disabled")
    view._vo_download_btn.grid(row=0, column=2)
    ctk.CTkLabel(listen.body, textvariable=view._vo_play_var, text_color=T.MUTED, font=ctk.CTkFont(size=12), anchor="w", justify="left",
                 wraplength=620).grid(row=1, column=0, sticky="w", pady=(8, 0))
    view._vo_project_key = _project_key(app)
    existing = _existing_voiceover(app)
    if existing is not None:
        _set_last(view, existing, "Last voiceover in this project")
    view.bind("<Unmap>", lambda _e: _stop_play(view), add="+")   # leaving the tab stops the sound


def _clone_names() -> list:
    try:
        from voice_clone import engine
        return [n for n, _ in engine.list_voices()]
    except Exception:
        return []


def _update_plan(view: Any) -> None:
    """The line above Generate: which voice the next Generate will make."""
    try:
        clone = view._vo_clone_var.get()
        base = view._vo_voice_var.get()
        view._vo_plan_var.set(f"Next Generate: plain voice - {base}" if clone == NO_CLONE
                              else f"Next Generate: the voice of '{clone}'. ('{base}' only reads the words and sets the pace and accent.)")
    except Exception:
        pass


def _refresh_clones(view: Any, select: str = "") -> None:
    names = _clone_names()
    view._vo_clone_menu.configure(values=[NO_CLONE] + names)
    cur = select or view._vo_clone_var.get()
    view._vo_clone_var.set(cur if cur in names else NO_CLONE)


def _remove_clone(view: Any) -> None:
    name = view._vo_clone_var.get()
    if name == NO_CLONE:
        view._vo_clone_status.set("Pick a saved voice in the list first.")
        return
    from voice_clone import engine
    engine.delete_voice(name)
    view._vo_clone_var.set(NO_CLONE)
    _refresh_clones(view)
    view._vo_clone_status.set(f"Removed the voice '{name}'.")


def _add_clone(view: Any, app: Any) -> None:
    """Choose a recording, check it, name the voice and save its fingerprint. Nothing else starts."""
    if view._vo_busy:
        return
    from tkinter import filedialog, simpledialog

    path = filedialog.askopenfilename(title="Choose a recording of the voice to copy",
                                      filetypes=[("Audio or video", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4 *.mov *.mkv *.webm"), ("All files", "*.*")])
    if not path:
        return
    name = simpledialog.askstring("Name this voice", "A name for this cloned voice (for example your own name).\n\n"
                                  "Only continue if this is your voice or its owner agreed.", parent=view)
    if not name or not name.strip():
        return
    name = name.strip()
    view._vo_busy = True
    view._vo_clone_status.set("Checking the recording...")

    def ui(fn, *a):
        try:
            app.after(0, lambda: fn(*a))
        except Exception:
            pass

    def finish(msg, select=""):
        view._vo_busy = False
        view._vo_clone_status.set(msg)
        _refresh_clones(view, select)

    def work():
        try:
            from voice_clone import engine

            ff = _find("ffmpeg")
            ok, msg, audio = engine.check_sample(path, ff)
            if not ok:
                ui(finish, msg)
                return
            if not engine.ensure_torch(lambda t: ui(view._vo_clone_status.set, t)):
                ui(finish, "The voice cloner could not be set up (no internet, pip is blocked, or this is a packaged build).")
                return
            if not engine.ensure_models(lambda t: ui(view._vo_clone_status.set, t)):
                ui(finish, "The voice model could not be downloaded. Check the internet connection and try again.")
                return
            ui(view._vo_clone_status.set, "Learning the voice...")
            engine.make_voice(name, audio, engine.Cloner(ff))
            ui(finish, f"Saved the voice '{name}'. {msg} Pick it under 'Narrate in', then Generate.", name)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            ui(finish, f"Could not save the voice: {type(exc).__name__}: {str(exc)[:160]}")

    threading.Thread(target=work, daemon=True).start()


def _project_voiceover_path(ws: Any) -> Path:
    """audio/<project name>_voiceover.mp3 - named after the project, not the voice service."""
    import re

    name = re.sub(r'[\\/:*?"<>|#]+', " ", str(getattr(ws, "folder_name", "") or "project"))
    name = re.sub(r"\s+", "_", name).strip("_ ") or "project"
    return Path(ws.audio_dir) / f"{name}_voiceover.mp3"


def _project_key(app: Any) -> str:
    ws = getattr(app, "_workspace", None)
    return str(getattr(ws, "project_id", "") or getattr(ws, "root", "") or getattr(ws, "audio_dir", "") or "") if ws is not None else ""


def sync_project(view: Any, app: Any) -> None:
    """Every time the page is shown: if the project changed, drop the old project's voiceover, script text, progress and messages,
    and show this project's own voiceover (if it has one). Never runs anything and never touches a generation in progress."""
    if getattr(view, "_vo_busy", False):
        return
    key = _project_key(app)
    if key == getattr(view, "_vo_project_key", key):
        return
    view._vo_project_key = key
    _stop_play(view)
    view._vo_last = None
    view._vo_play_btn.configure(state="disabled")
    view._vo_download_btn.configure(state="disabled")
    view._vo_play_var.set("Nothing to play yet. Generate or preview a voice first.")
    view._vo_status_var.set("")
    view._vo_progress.set(0)
    view._vo_text.delete("1.0", "end")
    _update_count(view)
    existing = _existing_voiceover(app)
    if existing is not None:
        _set_last(view, existing, "Last voiceover in this project")


def _existing_voiceover(app: Any):
    ws = getattr(app, "_workspace", None)
    if ws is None:
        return None
    for p in (_project_voiceover_path(ws), Path(ws.audio_dir) / "voiceover_edge.mp3"):   # the second is the older name
        if p.is_file():
            return p
    return None


def _set_last(view: Any, path: Path, label: str) -> None:
    view._vo_last = Path(path)
    view._vo_play_btn.configure(state="normal")
    view._vo_download_btn.configure(state="normal")
    view._vo_play_var.set(f"{label}: {Path(path).name}")


def _download(view: Any) -> None:
    """Save a copy of the voiceover wherever the user chooses (the project's own copy stays where it is)."""
    from tkinter import filedialog

    src = view._vo_last
    if src is None or not Path(src).is_file():
        view._vo_play_var.set("The file is not there any more. Generate again.")
        return
    dest = filedialog.asksaveasfilename(title="Save a copy of the voiceover", defaultextension=".mp3", initialfile=Path(src).name,
                                        filetypes=[("MP3", "*.mp3")])
    if not dest:
        return
    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        view._vo_play_var.set(f"Could not save the copy: {exc}")
        return
    view._vo_play_var.set(f"Saved a copy: {dest}")


def _player_cmd(path: Path):
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", str(path)]
    ff = shutil.which("ffplay") or _find("ffplay")
    return [ff, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]


def _play(view: Any) -> None:
    path = view._vo_last
    if path is None or not Path(path).is_file():
        view._vo_play_var.set("The file is not there any more. Generate again.")
        view._vo_play_btn.configure(state="disabled")
        return
    _stop_play(view)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606  (the default player; no console player is bundled on Windows)
            view._vo_play_var.set(f"Opened in your audio player: {Path(path).name}")
            return
        view._vo_play_proc = subprocess.Popen(_player_cmd(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001
        view._vo_play_var.set(f"No audio player could be started ({type(exc).__name__}). The file is at {path}")
        return
    view._vo_play_var.set(f"Playing: {Path(path).name}")
    view._vo_stopplay_btn.configure(state="normal")
    _watch_play(view)


def _watch_play(view: Any) -> None:
    proc = view._vo_play_proc
    if proc is None:
        return
    if proc.poll() is None:
        view.after(400, lambda: _watch_play(view))
        return
    view._vo_play_proc = None
    view._vo_stopplay_btn.configure(state="disabled")
    view._vo_play_var.set(f"Finished: {Path(view._vo_last).name}")


def _stop_play(view: Any) -> None:
    proc = getattr(view, "_vo_play_proc", None)
    view._vo_play_proc = None
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        view._vo_stopplay_btn.configure(state="disabled")
    except Exception:
        pass


def _language_changed(view: Any) -> None:
    """A new language shows its own voices and picks its first one. Only remembers the choice: nothing runs."""
    voices = voices_for(view._vo_lang_var.get())
    view._vo_voice_menu.configure(values=[v[0] for v in voices])
    view._vo_voice_var.set(voices[0][0])


def _voice_id(view: Any) -> str:
    voices = voices_for(view._vo_lang_var.get()) if hasattr(view, "_vo_lang_var") else VOICES
    label = view._vo_voice_var.get()
    return next((vid for lab, vid in voices if lab == label), voices[0][1])


def _text(view: Any) -> str:
    return view._vo_text.get("1.0", "end").strip()


def _update_count(view: Any) -> None:
    import edge_voiceover as ev
    n = ev.word_count(_text(view))
    mins = n * _SECONDS_PER_WORD / 60
    view._vo_count_var.set(f"{n:,} words, about {mins:.1f} min of speech")


def _from_script_tab(view: Any, app: Any) -> None:
    box = getattr(app, "script_box", None)
    text = box.get("1.0", "end").strip() if box is not None else ""
    if not text:
        view._vo_status_var.set("The Script tab has no text yet.")
        return
    view._vo_text.delete("1.0", "end")
    view._vo_text.insert("1.0", text)
    _update_count(view)


def _open_file(view: Any) -> None:
    from tkinter import filedialog

    path = filedialog.askopenfilename(title="Choose the script text", filetypes=[("Text", "*.txt *.md"), ("All files", "*.*")])
    if path:
        try:
            data = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            view._vo_status_var.set(f"Could not read the file: {exc}")
            return
        view._vo_text.delete("1.0", "end")
        view._vo_text.insert("1.0", data)
        _update_count(view)


def _set_busy(view: Any, busy: bool) -> None:
    view._vo_busy = busy
    state = "disabled" if busy else "normal"
    view._vo_go_btn.configure(state=state)
    view._vo_preview_btn.configure(state=state)
    view._vo_stop_btn.configure(state="normal" if busy else "disabled")


def _start(view: Any, app: Any, *, preview: bool) -> None:
    if view._vo_busy:
        return
    text = _text(view)
    if not text:
        view._vo_status_var.set("Paste or load the script first.")
        return
    ws = getattr(app, "_workspace", None)
    if preview:
        import edge_voiceover as ev
        text = " ".join(ev.split_sentences(text)[:3])
        out = Path(ws.audio_dir if ws is not None else Path.home()) / "voiceover_preview.mp3"
    elif ws is not None:
        ws.ensure_dirs()
        out = _project_voiceover_path(ws)
    else:
        from tkinter import filedialog

        chosen = filedialog.asksaveasfilename(title="Save the voiceover as", defaultextension=".mp3", filetypes=[("MP3", "*.mp3")])
        if not chosen:
            return
        out = Path(chosen)
    voice, speed, pitch = _voice_id(view), round(view._vo_speed_var.get(), 2), int(view._vo_pitch_var.get())
    clone_name = view._vo_clone_var.get()
    clone_name = "" if clone_name == NO_CLONE else clone_name
    view._vo_cancel.clear()
    view._vo_progress.set(0)
    view._vo_status_var.set("Starting...")
    _set_busy(view, True)

    def ui(fn, *a):
        try:
            app.after(0, lambda: fn(*a))
        except Exception:
            pass

    def work():
        try:
            import edge_voiceover as ev

            if not ev.ensure_installed(lambda t: ui(view._vo_status_var.set, t)):
                raise ImportError("edge-tts")

            def progress(done, total):
                if view._vo_cancel.is_set():
                    raise RuntimeError("stopped")
                ui(_progress, view, done, total)

            convert = None
            if clone_name:
                from voice_clone import engine

                se = dict(engine.list_voices()).get(clone_name)
                if not se:
                    raise RuntimeError(f"the saved voice '{clone_name}' is missing; add it again")
                if not engine.ensure_torch(lambda t: ui(view._vo_status_var.set, t)) or not engine.ensure_models(lambda t: ui(view._vo_status_var.set, t)):
                    raise RuntimeError("the voice cloner could not be set up")
                ui(view._vo_status_var.set, "Loading the cloner...")
                convert = engine.make_converter_for(se, engine.Cloner(_find("ffmpeg")))

            def cprogress(done, total):
                if view._vo_cancel.is_set():
                    raise RuntimeError("stopped")
                ui(_progress, view, done, total, "Copying the voice: piece")

            res = ev.synthesize(text, str(out), voice=voice, speed=speed, pitch_hz=pitch,
                                ffmpeg=_find("ffmpeg"), ffprobe=_find("ffprobe"), progress=progress,
                                convert=convert, convert_progress=cprogress)
            ui(_done, view, app, res, preview, ws is not None)
        except ImportError:
            ui(_fail, view, "The voices could not be set up (no internet, or pip is blocked). Connect and try again, or load your own audio on Audio & Effects.")
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            msg = "Stopped." if "stopped" in str(exc) else (
                f"The voice step failed: {type(exc).__name__}: {str(exc)[:160]}. Try again in a minute, or load your own audio on Audio & Effects.")
            ui(_fail, view, msg)

    threading.Thread(target=work, daemon=True).start()


def _progress(view: Any, done: int, total: int, what: str = "Making the voice: piece") -> None:
    view._vo_progress.set(done / max(1, total))
    view._vo_status_var.set(f"{what} {done} of {total}")


def _fail(view: Any, msg: str) -> None:
    _set_busy(view, False)
    view._vo_status_var.set(msg)


def _done(view: Any, app: Any, res: dict, preview: bool, has_project: bool) -> None:
    _set_busy(view, False)
    view._vo_progress.set(1)
    path = Path(res["path"])
    mins = res["duration"] / 60
    if preview:
        view._vo_status_var.set(f"Preview ready ({res['duration']:.0f} s).")
        _set_last(view, path, "Preview")
        _play(view)
        return
    _set_last(view, path, "Voiceover")
    if has_project and app._confirm_voiceover_switch(path, source="imported"):
        previous = (app.audio_var.get() or "").strip()
        app._set_active_voiceover(path, source="imported")
        _share_with_styles(app, previous)
        view._vo_status_var.set(f"Done: {mins:.1f} min voiceover saved and set as this project's voiceover ({path.name}). Word timings: {Path(res['words_path']).name}")
    else:
        view._vo_status_var.set(f"Done: {mins:.1f} min voiceover saved at {path}. It was not set as the project's voiceover.")


def _open_in_player(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass
