"""Rep Theory in the app's style picker: the card, its controls and the render worker. Imported only when the style is picked.

Same shape as health_cinema/app_section.py: small additive hooks in app.py (`_reptheory_*`), everything else lives in this package. Opt-in per session; nothing starts until Render.
16:9 landscape only: Final is 1920x1080, Preview is 1280x720. Scenes come from a scenes JSON (list of {text, start, end, ...}) or CSV you choose (untimed CSV rows, as "Copy the CSV prompt" asks for, are aligned to the voiceover), else the voiceover's own transcript
cut into sentences (the app's word timings). The art ships with the app (assets/reptheory); a user library (~/RepTheoryAssets or REP_THEORY_ASSET_DIR) is optional and overrides it."""
from __future__ import annotations
import sys
import threading
from pathlib import Path
from typing import Optional

STYLE_NAME = "Rep Theory"
TAG = "[REP THEORY]"
OWNER = "reptheory"      # its Flow pictures in the Visuals tab (visual_bridge)

def _m(app): return sys.modules[type(app).__module__]

PAUSE_CUT_S, MIN_WORDS, MAX_SENTENCE_S = 0.45, 4, 10.0      # sentences from pauses, when the words carry no punctuation

def sentences_from_words(words, total_s: float = 0.0):
    """Sentences from the narration's word times. The app's Whisper words come back without punctuation (video_generator.transcribe_audio normalises them), so the
    shared cutter (health_cinema) only cut at pauses over 1.2 s: a smooth 22 s voiceover was ONE scene with one picture (pipeline check 2026-11-10).
    Without punctuation the narration is cut where the speaker pauses (0.45 s and up, between sentences and at commas), pieces under 4 words join the one
    before, and a piece over 10 s is cut again at its longest pause."""
    from health_cinema.app_section import sentences_from_words as f      # the same sentence cutter every narration-driven style uses
    import re as _re
    ws = []
    for it in words or []:
        try: ws.append((str(it[0]), float(it[1]), float(it[2])))
        except (TypeError, ValueError, IndexError): continue
    if not ws or any(_re.search(r"[.!?]['\")\]]*$", w) for w, _, _ in ws): return f(words, total_s)
    groups, cur = [], [ws[0]]
    for prev, w in zip(ws, ws[1:]):
        if w[1] - prev[2] >= PAUSE_CUT_S: groups.append(cur); cur = []
        cur.append(w)
    groups.append(cur); merged = []
    for g in groups:
        if merged and len(g) < MIN_WORDS: merged[-1] = merged[-1] + g
        else: merged.append(g)
    if len(merged) > 1 and len(merged[0]) < MIN_WORDS: merged[1] = merged[0] + merged[1]; merged.pop(0)
    out_g = []
    def split_long(g):
        if g[-1][2] - g[0][1] <= MAX_SENTENCE_S or len(g) < 2 * MIN_WORDS: out_g.append(g); return
        k = max(range(MIN_WORDS, len(g) - MIN_WORDS + 1), key=lambda i: g[i][1] - g[i - 1][2]); split_long(g[:k]); split_long(g[k:])
    for g in merged: split_long(g)
    marked = []
    for g in out_g: marked += [(w, a, b) for w, a, b in g[:-1]] + [(g[-1][0] + ".", g[-1][1], g[-1][2])]      # a full stop where the speaker paused: the shared cutter ends the sentence there
    return f(marked, total_s)

def read_scenes_file(path: str):
    import csv, json
    if path.lower().endswith(".json"):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list) or any(not isinstance(s, dict) or not {"text", "start", "end"} <= set(s) for s in data): raise ValueError("a scenes JSON is a list of {text, start, end, ...}")
        return data
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    if not rows or "text" not in {k.lower() for k in rows[0]}: raise ValueError("a scenes CSV needs a text column (and start, end, or the rows are aligned to the voiceover by the app)")
    out = []
    for r in rows:
        r = {k.lower().strip(): (v or "").strip() for k, v in r.items() if k}
        if r.get("start") and r.get("end"): out.append(dict(r, start=float(r["start"]), end=float(r["end"])))
        else: out.append({k: v for k, v in r.items() if k not in ("start", "end")})      # untimed (what "Copy the CSV prompt" asks for): aligned to the voiceover at Render
    if any("start" in x for x in out) and not all("start" in x for x in out): raise ValueError("start/end are filled on some rows but not all: fill them on every row, or clear them on all rows to align to the voiceover")
    return out

PROMPT_FILE = Path(__file__).with_name("scenes_csv_prompt.txt")      # bundled next to the package (packaging.prompt_files)

CAT_PROMPT_FILE = Path(__file__).with_name("cat_scenes_csv_prompt.txt")      # Cat Theory's own CSV prompt (cats, white canvas, no 3D)

JUNG_PROMPT_FILE = Path(__file__).with_name("jung_scenes_csv_prompt.txt")      # Carl Jung Theory's own CSV prompt (Jung paintings, ideas, sourced quotes)

ELDER_PROMPT_FILE = Path(__file__).with_name("elder_scenes_csv_prompt.txt")      # Elder Health Theory's own CSV prompt (older people, organs, whiteboard)

SURVIVAL_PROMPT_FILE = Path(__file__).with_name("survival_scenes_csv_prompt.txt")      # Survival's own CSV prompt (field-guide pictures, countdown / ranking / timeline cards)
SURVIVAL_SCRIPT_PROMPT_FILE = Path(__file__).with_name("survival_script_prompt.txt")      # Survival's script blueprint: six formats, openings, item grammar, endings (docs/survival/NICHE_STUDY.md)

def theme_of(app) -> str: return getattr(app, "_rt_theme", "") or ""      # "" Rep Theory, "cat" Cat Theory, "jung" Carl Jung Theory (app._on_style_pick sets it)

def style_name(app) -> str: return {"cat": "Cat Theory", "jung": "Carl Jung Theory", "elder": "Elder Health Theory", "survival": "Survival"}.get(theme_of(app), STYLE_NAME)

def is_cat(app) -> bool: return theme_of(app) in ("cat", "jung", "elder", "survival")      # a niche on this engine: Flow pictures always, never the 3D body

def prompt_text(script: str = "", cat=False) -> str:
    """The CSV prompt with the script in it. cat: True / "cat" for Cat Theory, "jung" for Carl Jung Theory, False / "" for Rep Theory."""
    from app_csv_prompts import SCRIPT_PLACEHOLDER
    f = {"jung": JUNG_PROMPT_FILE, "elder": ELDER_PROMPT_FILE, "survival": SURVIVAL_PROMPT_FILE, "cat": CAT_PROMPT_FILE, True: CAT_PROMPT_FILE}.get(cat, PROMPT_FILE)
    text = f.read_text(encoding="utf-8"); script = (script or "").strip()
    return text.replace(SCRIPT_PLACEHOLDER, script) if script else text

def copy_prompt(app) -> None:
    """"Copy the CSV prompt" for Rep Theory: the scenes CSV (text, chapter) its scenes file reads, with the project's script in it."""
    M = _m(app)
    for box in getattr(app, "_csv_prompt_script_boxes", []):
        try:
            if box.get("1.0", "end").strip() != getattr(box, "_csv_synced", None): app._on_csv_prompt_script_edited(box); break      # typed in but not yet left: the click must not lose it
        except Exception: pass
    script = app._main_script_text()
    try: text = prompt_text(script, cat=theme_of(app))
    except OSError as exc: M.messagebox.showerror("Copy the CSV prompt", f"The prompt file could not be read: {exc}"); return
    app.clipboard_clear(); app.clipboard_append(text)
    app._rt_status_var.set(f"{style_name(app)} prompt copied with your script. Paste it into any AI, save the reply as a .csv, then choose it as the Scenes file." if script else
                           f"{style_name(app)} prompt copied. Paste it into any AI, replace its last line with your script, save the reply as a .csv, then choose it as the Scenes file.")

GUIDE_PROMPT_FILE = Path(__file__).with_name("full_guide_prompt.txt")      # the "Full Guide" script blueprint (Step 6), bundled like the CSV prompt

def copy_script_prompt(app) -> None:
    """"Copy the script prompt": the Full Guide blueprint an AI fills in for any topic, so the script's sentences have shapes the app can draw."""
    M = _m(app)
    survival = theme_of(app) == "survival"      # Survival writes its own long-form scripts (survival_script_prompt.txt), not the fitness Full Guide
    try: text = (SURVIVAL_SCRIPT_PROMPT_FILE if survival else GUIDE_PROMPT_FILE).read_text(encoding="utf-8")
    except OSError as exc: M.messagebox.showerror("Copy the script prompt", f"The prompt file could not be read: {exc}"); return
    app.clipboard_clear(); app.clipboard_append(text)
    app._rt_status_var.set("Survival script prompt copied. Paste it into any AI, replace its last line with your topic, then use the script it writes.") if survival else app._rt_status_var.set("Full Guide script prompt copied. Paste it into any AI, replace its last line with your topic, then use the script it writes.")

SETTINGS_KEY = "reptheory_settings"
SETTINGS = {"scenes": "_rt_scenes_var", "title": "_rt_title_var", "preview": "_rt_preview_var", "smart": "_rt_smart_var", "3d": "_rt_3d_var", "flow": "_rt_flow_var",
            "variety": "_rt_variety_var", "end": "_rt_end_var", "end_title": "_rt_end_title", "end_url": "_rt_end_url", "end_image": "_rt_end_image"}

def save_settings(app) -> None:
    """The page's choices (scenes CSV, Flow pictures, 3D, smart planner, end card ...) and what the last Generate scenes was made from, saved in the project, so
    reopening the app shows the same page (2026-11-02: after a restart the CSV and the Flow switch were reset, and Render made 4 scenes with no pictures)."""
    ws = getattr(app, "_workspace", None)
    if ws is None or getattr(app, "_rt_restoring", False): return
    try:
        vals = {k: getattr(app, a).get() for k, a in SETTINGS.items() if hasattr(app, a)}
        rk = getattr(app, "_rt_ready_key", None); vals["ready_key"] = list(rk) if rk else None
        data = ws.read_meta()
        if data.get(SETTINGS_KEY) != vals: data[SETTINGS_KEY] = vals; ws._write_meta(data)
    except Exception: pass

def restore_settings(app) -> bool:
    """The project's saved choices back on the page. False when the project has none yet (a new project keeps the defaults)."""
    ws = getattr(app, "_workspace", None)
    if ws is None: return False
    try: vals = ws.read_meta().get(SETTINGS_KEY)
    except Exception: return False
    if not isinstance(vals, dict): return False
    app._rt_restoring = True
    try:
        for k, a in SETTINGS.items():
            if k in vals and hasattr(app, a):
                try: getattr(app, a).set(vals[k])
                except Exception: pass
        rk = vals.get("ready_key"); app._rt_ready_key = tuple(rk) if rk else None
    finally: app._rt_restoring = False
    return True

DEFAULTS = {"scenes": "", "title": "", "preview": False, "smart": True, "3d": True, "flow": True, "variety": True, "end": False, "end_title": "", "end_url": "", "end_image": ""}

def on_workspace(app) -> None:
    """A project was opened (or the page shown): its saved choices on the page, or the defaults for a project that has none, so one project's CSV never carries over
    into another (2026-11-02: the project's choices were saved but only restored when the style was switched, so reopening the app showed an empty page)."""
    ws = getattr(app, "_workspace", None)
    if ws is None or not hasattr(app, "_rt_scenes_var"): return
    if not restore_settings(app):
        app._rt_restoring = True
        try:
            for k, a in SETTINGS.items():
                if hasattr(app, a): getattr(app, a).set(DEFAULTS[k])
            app._rt_ready_key = None
        finally: app._rt_restoring = False
    app._rt_restored_for = str(getattr(ws, "root", ""))

def on_workspace_safe(app) -> None:
    """on_workspace for app.py's project switch: a failure here never stops a project from opening."""
    try: on_workspace(app)
    except Exception: pass

def build(app, parent, *, row: int) -> None:
    M = _m(app); ctk = M.ctk
    app._rt_scenes_var = ctk.StringVar(value=""); app._rt_status_var = ctk.StringVar(value=""); app._rt_title_var = ctk.StringVar(value=""); app._rt_preview_var = ctk.BooleanVar(value=False)
    app._rt_smart_var = ctk.BooleanVar(value=True); app._rt_3d_var = ctk.BooleanVar(value=True); app._rt_flow_var = ctk.BooleanVar(value=True); app._rt_variety_var = ctk.BooleanVar(value=True)
    app._rt_end_var = ctk.BooleanVar(value=False); app._rt_end_title = ctk.StringVar(value=""); app._rt_end_url = ctk.StringVar(value=""); app._rt_end_image = ctk.StringVar(value="")
    for attr in SETTINGS.values(): getattr(app, attr).trace_add("write", lambda *_a: save_settings(app))      # every choice on this page is kept with the project
    app._rt_cancel = threading.Event(); app._rt_running = getattr(app, "_rt_running", False)
    block = ctk.CTkFrame(parent, fg_color=M._CARD, corner_radius=10, border_width=1, border_color=M._BORDER); block.grid(row=row, column=0, sticky="ew", pady=(0, 12)); block.grid_columnconfigure(0, weight=1)
    app._rt_block = block
    app._style_card_header(block, "Rep Theory", "Gym, calisthenics and fitness explainers on a near-black canvas: original manga-style trainee art, anatomy highlights, props with orange rings, "
                           "equations, tier lists. Visuals follow your narration; numbers and rankings are only what you say. Nothing starts until you press Render.")
    controls = ctk.CTkFrame(block, fg_color="transparent"); controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 12)); controls.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Voiceover", app.audio_var, lambda: app._browse_audio(stay=True), parent=controls, placeholder_text="None yet: use Import Voiceover")
    app._path_row(1, "Scenes file", app._rt_scenes_var, lambda: browse_scenes(app), parent=controls, placeholder_text="Optional: scenes CSV (from Copy the CSV prompt) or JSON; otherwise planned from the narration")
    opts = ctk.CTkFrame(controls, fg_color="transparent"); opts.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    ctk.CTkLabel(opts, text="Section label", font=ctk.CTkFont(size=12), text_color=M._MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkEntry(opts, textvariable=app._rt_title_var, width=260, placeholder_text="e.g. Grip · No Gym").grid(row=0, column=1, padx=(0, 16))
    ctk.CTkCheckBox(opts, text="Preview (1280x720)", variable=app._rt_preview_var).grid(row=0, column=2)
    from . import elder_art as EA      # Elder Health Theory only: the main person (an uploaded picture, a new person every video, or this channel's own cast); remembered, nothing runs
    try: pv, own, sex = EA.per_video(), EA.own_picture(), EA.own_sex()
    except Exception: pv, own, sex = False, None, "f"
    app._rt_elder_new_var = ctk.BooleanVar(value=pv); app._rt_elder_pic_var = ctk.StringVar(value=""); app._rt_elder_sex_var = ctk.StringVar(value="Woman" if sex == "f" else "Man")
    box = app._rt_elder_box = ctk.CTkFrame(opts, fg_color="transparent"); box.grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0)); box.grid_columnconfigure(5, weight=1)
    ctk.CTkLabel(box, text="Main person", font=ctk.CTkFont(size=12), text_color=M._MUTED).grid(row=0, column=0, padx=(0, 8), sticky="w")
    ctk.CTkButton(box, text="Upload picture", width=120, command=lambda: upload_elder_picture(app)).grid(row=0, column=1, padx=(0, 6))
    app._rt_elder_clear = ctk.CTkButton(box, text="Remove", width=70, command=lambda: remove_elder_picture(app)); app._rt_elder_clear.grid(row=0, column=2, padx=(0, 6))
    ctk.CTkSegmentedButton(box, values=["Woman", "Man"], variable=app._rt_elder_sex_var, command=lambda v: EA.set_own_sex("m" if v == "Man" else "f")).grid(row=0, column=3, padx=(0, 12))
    app._rt_elder_new_cb = ctk.CTkCheckBox(box, text="New main person every video", variable=app._rt_elder_new_var, command=lambda: (EA.set_per_video(app._rt_elder_new_var.get()), _elder_pic_state(app)))
    app._rt_elder_new_cb.grid(row=0, column=4, padx=(0, 12))
    ctk.CTkLabel(box, textvariable=app._rt_elder_pic_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=520, justify="left").grid(row=1, column=0, columnspan=6, sticky="ew", pady=(4, 0))
    _elder_pic_state(app)
    if theme_of(app) != "elder": box.grid_remove()
    mix = ctk.CTkFrame(controls, fg_color="transparent"); mix.grid(row=3, column=0, sticky="ew", pady=(10, 0))      # what each scene may be drawn with (long videos: keep all on)
    for i, (txt, var) in enumerate((("Scene per idea (smart planner)", app._rt_smart_var), ("3D muscle clips", app._rt_3d_var), ("Flow pictures", app._rt_flow_var), ("Mix looks for long videos", app._rt_variety_var))): ctk.CTkCheckBox(mix, text=txt, variable=var).grid(row=0, column=i, padx=(0, 16), sticky="w")
    end = ctk.CTkFrame(controls, fg_color="transparent"); end.grid(row=4, column=0, sticky="ew", pady=(10, 0)); end.grid_columnconfigure(1, weight=1)      # optional product end card: off by default, the ending is then unchanged
    ctk.CTkCheckBox(end, text="Product end card (5 s)", variable=app._rt_end_var).grid(row=0, column=0, padx=(0, 12), sticky="w")
    ctk.CTkEntry(end, textvariable=app._rt_end_title, placeholder_text="Title (default: section label)").grid(row=0, column=1, columnspan=2, sticky="ew")
    ctk.CTkEntry(end, textvariable=app._rt_end_url, placeholder_text="URL").grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(6, 0))
    ctk.CTkEntry(end, textvariable=app._rt_end_image, placeholder_text="Picture (optional)").grid(row=1, column=2, columnspan=2, sticky="ew", pady=(6, 0))
    ctk.CTkButton(end, text="Browse", width=70, command=lambda: browse_end_image(app)).grid(row=1, column=4, padx=(8, 0), pady=(6, 0))
    go = ctk.CTkFrame(controls, fg_color="transparent"); go.grid(row=5, column=0, sticky="ew", pady=(12, 0))
    app._rt_render_btn = ctk.CTkButton(go, text="Render Rep Theory", width=230, height=40, corner_radius=6, fg_color=M._ACCENT, hover_color=M._ACCENT_HOV, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render_click(app))
    app._rt_render_btn.grid(row=0, column=0, padx=(0, 12))
    ctk.CTkLabel(go, text="Landscape 16:9 only. The trainee, bottle, forearm and bar-hang pictures ship with the app.", font=ctk.CTkFont(size=11), text_color=M._MUTED).grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(controls, textvariable=app._rt_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=560, justify="left").grid(row=6, column=0, sticky="ew", pady=(8, 0))
    bar = ctk.CTkFrame(controls, fg_color="transparent"); bar.grid(row=7, column=0, sticky="ew", pady=(10, 0)); bar.grid_columnconfigure(1, weight=1)      # same "Copy the CSV prompt" as the other styles
    M._make_button(bar, "Copy the CSV prompt", lambda: copy_prompt(app), size="lg", width=150).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(bar, text="Paste it into any AI, then choose the CSV it writes as the Scenes file.", font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w").grid(row=0, column=1, sticky="w", padx=(10, 0))
    app._build_csv_prompt_script_box(bar, row=1, columnspan=2)
    M._make_button(bar, "Copy the script prompt", lambda: copy_script_prompt(app), size="lg", width=150).grid(row=2, column=0, sticky="w", pady=(8, 0))
    ctk.CTkLabel(bar, text="A Full Guide script for any topic, written in the shapes the app can draw.", font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w").grid(row=2, column=1, sticky="w", padx=(10, 8), pady=(8, 0))
    block.grid_remove()

def browse_scenes(app) -> None:
    M = _m(app); path = M.filedialog.askopenfilename(title="Choose the scenes file", filetypes=[("Scenes CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
    if path: app._rt_scenes_var.set(path)

def browse_end_image(app) -> None:
    M = _m(app); path = M.filedialog.askopenfilename(title="Choose the end-card picture", filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
    if path: app._rt_end_image.set(path)

def _elder_pic_state(app) -> None:
    """The Elder page's main-person line: which person the pictures will show, and Remove / the switch only when they apply."""
    from . import elder_art as EA
    own = EA.own_picture()
    app._rt_elder_pic_var.set("Your uploaded picture is the main person in every video (Flow keeps that face)." if own else
                              ("A new main person is made for every video." if app._rt_elder_new_var.get() else "This channel's own cast: four people made once for this app, kept across videos.")
                              + " Optional: upload a picture to use your own person.")
    try:
        app._rt_elder_clear.configure(state="normal" if own else "disabled"); app._rt_elder_new_cb.configure(state="disabled" if own else "normal")
    except Exception: pass

def upload_elder_picture(app) -> None:
    from . import elder_art as EA
    M = _m(app); path = M.filedialog.askopenfilename(title="Choose a picture of the main person", filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
    if not path: return
    err = EA.set_own_picture(path)
    if err: app._rt_status_var.set(err)
    else: app._rt_status_var.set("Main person picture saved. It is used for the next Generate scenes.")
    _elder_pic_state(app)

def remove_elder_picture(app) -> None:
    from . import elder_art as EA
    EA.clear_own_picture(); app._rt_status_var.set("Main person picture removed: the app's own people are used again."); _elder_pic_state(app)

def end_card_settings(app) -> dict:
    return {"enabled": bool(app._rt_end_var.get()), "title": app._rt_end_title.get().strip(), "url": app._rt_end_url.get().strip(), "image": app._rt_end_image.get().strip()}

def activate(app) -> None:
    if getattr(app, "_rt_running", False): return
    app._rt_block.grid(); app._rt_status_var.set("")
    box = getattr(app, "_rt_elder_box", None)      # the Elder Health switch shows only on that style
    if box is not None: box.grid() if theme_of(app) == "elder" else box.grid_remove()
    try: app._rt_render_btn.configure(text=f"Render {style_name(app)}")      # Rep Theory or Cat Theory
    except Exception: pass
    on_workspace(app)      # this project's own choices (scenes CSV, Flow pictures ...), as they were when it was last used
    import visual_bridge
    visual_bridge.restore(app, OWNER)      # the pictures of the last Generate scenes, back in the Visuals tab

def _inputs_key(app) -> tuple:
    """What Generate scenes listed pictures for: other inputs need Generate scenes again before Render."""
    return (app._rt_scenes_var.get().strip(), str(app._current_voiceover_path() or ""), bool(app._rt_smart_var.get()), bool(app._rt_3d_var.get()), bool(app._rt_variety_var.get()), app._rt_title_var.get().strip())

def needs_scenes(app) -> bool:
    """Flow pictures are the assets Rep Theory fetches: with them on, Generate scenes puts them in the Visuals tab first. Without them nothing is fetched."""
    return (bool(app._rt_flow_var.get()) or is_cat(app)) and getattr(app, "_rt_ready_key", None) != _inputs_key(app)      # Cat Theory always uses Flow pictures

def deactivate(app) -> None:
    block = getattr(app, "_rt_block", None)
    if block is not None: block.grid_remove()

def sync_cta(app) -> None:
    if getattr(app, "_rt_running", False):
        app._cta_action = "rt_cancel"; app.stage_var.set("GENERATING")
        if app._rt_cancel.is_set(): app.hint_var.set("Stopping…"); app._set_generate_btn(state="disabled", text="Stopping…")
        else: app.hint_var.set("Rendering — click Stop to cancel."); app._set_generate_btn(state="normal", text="Stop")
        return
    if app._workspace is None:
        app._cta_action = "picker"; app.stage_var.set("SETUP"); app.hint_var.set("Choose a project to get started."); app._set_generate_btn(state="normal", text="Choose project"); return
    if app._current_voiceover_path() is None:
        app._cta_action = "import_audio"; app.stage_var.set("PLAN"); app.hint_var.set("Select or import a voiceover to continue."); app._set_generate_btn(state="normal", text="Import Voiceover"); return
    app._cta_action = "rt_render"
    if needs_scenes(app): app.stage_var.set("PLAN"); app.hint_var.set("Click Generate scenes: the Flow pictures are made into the Visuals tab for you to check before rendering."); app._set_generate_btn(state="normal", text="Generate scenes"); return
    hint = f"The pictures are in the Visuals tab: change any there, then click Render {style_name(app)}." if (app._rt_flow_var.get() or is_cat(app)) else "Click Render Rep Theory: the visuals are planned from the narration, then rendered."
    app.stage_var.set("RENDER"); app.hint_var.set(hint); app._set_generate_btn(state="normal", text=f"Render {style_name(app)}")

def cta(app, action: str) -> None:
    cancel(app) if action == "rt_cancel" else on_render_click(app)

def cancel(app) -> None:
    if not getattr(app, "_rt_running", False) or app._rt_cancel.is_set(): return
    app._rt_cancel.set(); app._append_log(f"{TAG} Stop requested: stopping after the current frame.\n"); app._sync_primary_cta()

def on_render_click(app) -> None:
    M = _m(app)
    if getattr(app, "_rt_running", False): return
    ws = app._workspace
    if ws is None: M.messagebox.showerror("Cannot start", "Create or choose a project first."); return
    voiceover = app._current_voiceover_path()
    if voiceover is None: M.messagebox.showerror("Cannot start", "Select or import a voiceover first."); return
    scenes_path = app._rt_scenes_var.get().strip()
    if scenes_path and not Path(scenes_path).is_file(): M.messagebox.showerror("Cannot start", f"The scenes file was not found:\n{scenes_path}"); return
    out_path = ws.next_final_path(); app.output_var.set(str(out_path)); project_dir = Path(ws.root); model = app.model_var.get().strip() or "base"; state_dir = getattr(ws, "state_dir", None)
    quality = "preview" if app._rt_preview_var.get() else "final"; title = app._rt_title_var.get().strip(); end_card = end_card_settings(app)
    smart, want3d, wantflow, mixlooks = bool(app._rt_smart_var.get()), bool(app._rt_3d_var.get()), bool(app._rt_flow_var.get()), bool(app._rt_variety_var.get()); flow_settings, flow_accounts = None, None
    if is_cat(app): want3d, wantflow = False, True      # Cat Theory: no 3D body; every picture is a cat drawn through Flow (the gym trainee library never shows)
    if wantflow:
        try: flow_settings, flow_accounts = app._image_flow_run_settings()      # the app's own Flow switches (agent / UI mode) and the video profile's accounts
        except Exception as exc: app._append_log(f"{TAG} Flow settings unavailable ({exc}); Flow pictures use agent mode defaults.\n")
    if want3d:
        from . import clip3d
        if not clip3d.available(): app._append_log(f"{TAG} 3D body model or renderer not found on this machine: scenes about body parts keep their usual look (see docs/rep_theory).\n")
    import visual_bridge
    if getattr(app, "_rt_restored_for", None) != str(getattr(ws, "root", "")): on_workspace(app)      # never Generate / Render with another project's (or empty) choices
    media_only = needs_scenes(app); folder = visual_bridge.folder(OWNER, ws); inputs = _inputs_key(app)
    held = visual_bridge.rows(app, OWNER)
    made_from = getattr(app, "_rt_ready_key", None)      # what the last Generate scenes was made from: a script-only run (no CSV) holds its own pictures, nothing to choose
    if not media_only and held and not app._rt_scenes_var.get().strip() and (made_from is None or made_from[0]):      # the Visuals tab holds a CSV's pictures but no CSV is chosen: the render would plan different scenes and use none of them
        M.messagebox.showerror("Choose the scenes file", f"The Visuals tab holds {len(held)} pictures made from a scenes CSV, but no scenes file is chosen.\n\nChoose the same scenes CSV, then Render."); return
    table = visual_bridge.records(folder, visual_bridge.rows(app, OWNER)) if (wantflow and not media_only) else None
    manager = None
    if media_only:
        try: manager = app._build_asset_manager(folder, [])      # the app's own Flow wiring and settings (built here: it reads Tk variables)
        except Exception as exc: M.messagebox.showerror("Cannot start", f"The app's asset sources could not be set up:\n{exc}"); return
    app._rt_cancel.clear(); app._rt_running = True; app._rt_status_var.set("Making the Flow pictures for the Visuals tab…" if media_only else "Starting…")
    run = None if media_only else app._track_generation_start(OWNER); app._sync_primary_cta()      # the Export page follows the render (not Generate scenes)
    def log(msg: str) -> None: app.after(0, lambda: app._append_log(f"{TAG} {msg}\n"))
    def progress(k: float, msg: str) -> None: app.after(0, lambda: (app._rt_status_var.set(f"{int(k * 100)}%  {msg}"), run is not None and app._export_progress(k, msg)))
    def worker() -> None:
        from . import engine
        result: Optional[dict] = None; error = ""
        try:
            if scenes_path:
                sentences = read_scenes_file(scenes_path)
                if sentences and "start" not in sentences[0]:      # an untimed scenes CSV: its rows take the voiceover's own word times
                    from health_cinema import scenes_csv
                    log("Aligning the scenes CSV to the voiceover…"); words = app._pakmap_get_words(voiceover, model, state_dir, log)
                    try:
                        from pakmap.app_integration import voiceover_duration
                        total = float(voiceover_duration(voiceover) or 0.0)
                    except Exception: total = 0.0
                    sentences, frac = scenes_csv.align_to_words(sentences, words, total); log(f"Scenes aligned to the voiceover: {scenes_csv.match_note(frac)}")
            else:
                log("Reading the narration's word times…"); words = app._pakmap_get_words(voiceover, model, state_dir, log)
                try:
                    from pakmap.app_integration import voiceover_duration
                    total = float(voiceover_duration(voiceover) or 0.0)
                except Exception: total = 0.0
                sentences = sentences_from_words(words, total)
                if not sentences: raise RuntimeError("the narration has no words to plan from")
                log(f"{len(sentences)} sentences read from the narration")
            result = engine.run_rep_theory(project_dir, sentences, str(voiceover), str(out_path), quality=quality, title=title, cancel_check=app._rt_cancel.is_set, progress_cb=progress, log=log, end_card=end_card, planner="beats" if smart else "legacy", per_beat=smart, illustrate=wantflow, clips3d=want3d, variety=mixlooks and smart,
                                          flow_mode=(flow_settings or {}).get("generationMode", "agent"), flow_settings=flow_settings, flow_accounts=flow_accounts, media_only=media_only, table=table, theme=theme_of(app))
            if media_only:
                def listed(rows) -> None:      # shown at once, each row's state then follows the manifest (as Health Cinema does)
                    app.after(0, lambda: (visual_bridge.fill(app, OWNER, rows), app._rt_status_var.set(f"Scenes listed in the Visuals tab; making their pictures through Flow...")))
                def one_done(*_a, **_k) -> None:      # each finished picture appears in the tab as it lands
                    def refresh():
                        try: app._hydrate_overscaled_assets_from_manifest(folder); app._render_scene_rows(); app._refresh_assets_cta()
                        except Exception: pass
                    app.after(0, refresh)
                result = dict(result, rows=fetch_pictures(manager, folder, result.get("requests") or [], app._rt_cancel.is_set, log, on_listed=listed, on_done=one_done))
        except engine.Cancelled: error = "Stopped."
        except Exception as exc: error = f"{type(exc).__name__}: {exc}"      # shown to the user, never a silent failure
        def finish() -> None:
            app._rt_running = False
            if not media_only:
                from export_state import run_outcome
                done = run_outcome(error, out_path if result else None)
                app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed", message=error)
            if error: app._rt_status_var.set(error); app._append_log(f"{TAG} {error}\n")
            elif result and result.get("media_only"):
                rows = result.get("rows") or []; visual_bridge.fill(app, OWNER, rows); app._rt_ready_key = inputs; save_settings(app)
                ok = len(visual_bridge.records(folder, rows))
                msg = f"Scenes ready: {ok} of {len(rows)} Flow pictures made. Check them in the Visuals tab, then click Render Rep Theory." if rows else "Scenes ready (no scene wants a Flow picture). Click Render Rep Theory."
                app._rt_status_var.set(msg); app._append_log(f"{TAG} {msg}\n")
                if rows:
                    try: app._goto_workflow_view("visual_plan")
                    except Exception: pass
            elif result:
                msg = f"Done: {out_path.name} ({len(result['scenes'])} scenes, {result['size'][0]}x{result['size'][1]}, {result['video_seconds']}s)"; app._rt_status_var.set(msg)
                app._append_log(f"{TAG} {msg}; report: {out_path}.rep_theory.json\n{TAG} Not implemented yet: {', '.join(result.get('not_implemented') or [])}.\n")
            app._sync_primary_cta()
        app.after(0, finish)
    threading.Thread(target=worker, name="rep-theory-render", daemon=True).start()

def fetch_pictures(manager, folder: Path, requests: list, cancelled, log, on_listed=None, on_done=None) -> list:
    """Generate scenes: one Visuals-tab row per picture. A picture already in the Rep Theory library is filed as done (nothing is generated twice);
    the rest are made through the app's AssetManager (its Flow provider, settings and accounts), into this style's own folder."""
    import shutil
    from asset_manager import AssetManifest
    from providers.base import SceneRow
    rows = [SceneRow(scene_number=str(r["no"]), script_segment=r["text"], asset_type="image", prompt=r["prompt"]) for r in requests]
    if not rows: return rows
    folder.mkdir(parents=True, exist_ok=True); man = AssetManifest(folder)
    for r, row in zip(requests, rows):
        rec = man.get(row.scene_number) or {}
        if r.get("cached") and not (rec.get("status") == "complete" and rec.get("user_override")) and Path(r["cached"]).is_file():
            dst = folder / f"{int(row.scene_number):03d}{Path(r['cached']).suffix or '.png'}"
            if not dst.is_file(): shutil.copyfile(r["cached"], dst)
            man.set(row.scene_number, {"scene_number": row.scene_number, "status": "complete", "source": "flow_image", "type": "image", "local_path": str(dst), "prompt": row.prompt, "provider": "flow"})
    todo = [row for row in rows if (man.get(row.scene_number) or {}).get("status") != "complete"]
    log(f"{len(rows) - len(todo)} picture(s) already in the library; {len(todo)} to make through Flow")
    if on_listed: on_listed(rows)      # the scenes are in the Visuals tab now, before Flow makes the pictures (54 pictures took minutes with an empty tab)
    fp = getattr(manager, "flow_image_provider", None); ref_nos = {str(r["no"]) for r in requests if r.get("refs")}; refs = []
    if todo and ref_nos & {row.scene_number for row in todo} and fp is not None and not cancelled():      # Elder Health Theory: the host's reference picture first (made once), then their pictures with it attached
        from . import beat_art as BA, art as A
        from providers.flow.provider import FlowProvider
        def make_one(pr):
            one = FlowProvider(fp.engine_manager, media_kind="image", account_ids=fp.account_ids, flow_settings=dict(fp.flow_settings))
            import tempfile; r1 = (one.resolve_batch([SceneRow(scene_number="1", script_segment="reference", asset_type="image", prompt=pr)], Path(tempfile.mkdtemp(prefix="rt_ref_")), log=log) or {}).get("1")
            return getattr(r1, "path", None) if r1 is not None else None
        refs = A.flow_ref_copies(BA._refs_for([r["prompt"] for r in requests if r.get("refs")], make_one, log))
        if not refs: log("no reference picture for the main person: their pictures are drawn from the description alone")
    def run(batch, with_refs=False):
        if not batch or cancelled(): return
        old = dict(fp.flow_settings) if (with_refs and fp is not None) else None
        if old is not None: fp.flow_settings = dict(old, referenceImages=refs)
        try: manager.resolve_all(batch, on_scene_complete=on_done) if on_done else manager.resolve_all(batch)
        finally:
            if old is not None: fp.flow_settings = old
    if todo and not cancelled():
        if refs: run([row for row in rows if row.scene_number not in ref_nos]); run([row for row in rows if row.scene_number in ref_nos], with_refs=True)
        else: run(rows)
    failed = [row for row in rows if (man.get(row.scene_number) or {}).get("status") != "complete" and "cancel" not in str((man.get(row.scene_number) or {}).get("error", "")).lower()]
    if failed and not cancelled():      # refused by Flow (or failed): once more in a safer wording; pictures already made are never redone
        from .beat_art import safe_prompt
        log(f"{len(failed)} picture(s) refused or failed; trying each once more in a safer wording (scenes {', '.join(r.scene_number for r in failed)})")
        for row in failed: row.prompt = safe_prompt(row.prompt)
        if refs: run([r for r in failed if r.scene_number not in ref_nos]); run([r for r in failed if r.scene_number in ref_nos], with_refs=True)
        else: run(failed)
        still = [r.scene_number for r in failed if (man.get(r.scene_number) or {}).get("status") != "complete"]
        if still: log(f"refused again: scenes {', '.join(still)} keep their card or text (or use Change source / Use local clip in the Visuals tab)")
    qc_nos = {str(r["no"]) for r in requests if r.get("qc")}
    if qc_nos and not cancelled():      # Elder Health Theory's quality check (elder_art.check, pixels only): redrawn once in stronger wording; the first picture is kept unless the new one is better
        from . import elder_art as EA
        redo = []
        for row in rows:
            rec = man.get(row.scene_number) or {}
            if row.scene_number in qc_nos and rec.get("status") == "complete" and not rec.get("user_override") and rec.get("local_path") and Path(rec["local_path"]).is_file():
                probs = EA.check(rec["local_path"])
                if probs:
                    keep = Path(rec["local_path"]).with_name(Path(rec["local_path"]).stem + ".qc_first" + Path(rec["local_path"]).suffix); shutil.copyfile(rec["local_path"], keep)
                    redo.append((row, dict(rec), probs, keep)); row.prompt = EA.stronger(row.prompt, probs)
        if redo:
            log(f"quality check: {len(redo)} picture(s) redrawn once ({'; '.join(sorted({p for _, _, ps, _ in redo for p in ps}))})")
            batch = [x[0] for x in redo]
            ctx = fp.confirming_resubmit() if fp is not None else None
            if ctx: ctx.__enter__()
            try:
                if refs: run([r for r in batch if r.scene_number not in ref_nos]); run([r for r in batch if r.scene_number in ref_nos], with_refs=True)
                else: run(batch)
            finally:
                if ctx: ctx.__exit__(None, None, None)
            for row, old, probs, keep in redo:
                rec = man.get(row.scene_number) or {}; new = rec.get("local_path")
                if not (rec.get("status") == "complete" and new and Path(new).is_file() and len(EA.check(new)) < len(probs)):      # no better: the first picture back
                    shutil.copyfile(keep, old["local_path"]); man.set(row.scene_number, old); row.prompt = old.get("prompt", row.prompt)
                try: keep.unlink()
                except OSError: pass
    return rows
