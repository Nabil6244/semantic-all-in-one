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

def sentences_from_words(words, total_s: float = 0.0):
    from health_cinema.app_section import sentences_from_words as f      # the same sentence cutter every narration-driven style uses
    return f(words, total_s)

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

def prompt_text(script: str = "") -> str:
    from app_csv_prompts import SCRIPT_PLACEHOLDER
    text = PROMPT_FILE.read_text(encoding="utf-8"); script = (script or "").strip()
    return text.replace(SCRIPT_PLACEHOLDER, script) if script else text

def copy_prompt(app) -> None:
    """"Copy the CSV prompt" for Rep Theory: the scenes CSV (text, chapter) its scenes file reads, with the project's script in it."""
    M = _m(app)
    for box in getattr(app, "_csv_prompt_script_boxes", []):
        try:
            if box.get("1.0", "end").strip() != getattr(box, "_csv_synced", None): app._on_csv_prompt_script_edited(box); break      # typed in but not yet left: the click must not lose it
        except Exception: pass
    script = app._main_script_text()
    try: text = prompt_text(script)
    except OSError as exc: M.messagebox.showerror("Copy the CSV prompt", f"The prompt file could not be read: {exc}"); return
    app.clipboard_clear(); app.clipboard_append(text)
    app._rt_status_var.set("Rep Theory prompt copied with your script. Paste it into any AI, save the reply as a .csv, then choose it as the Scenes file." if script else
                           "Rep Theory prompt copied. Paste it into any AI, replace its last line with your script, save the reply as a .csv, then choose it as the Scenes file.")

def build(app, parent, *, row: int) -> None:
    M = _m(app); ctk = M.ctk
    app._rt_scenes_var = ctk.StringVar(value=""); app._rt_status_var = ctk.StringVar(value=""); app._rt_title_var = ctk.StringVar(value=""); app._rt_preview_var = ctk.BooleanVar(value=False)
    app._rt_smart_var = ctk.BooleanVar(value=True); app._rt_3d_var = ctk.BooleanVar(value=True); app._rt_flow_var = ctk.BooleanVar(value=False); app._rt_variety_var = ctk.BooleanVar(value=True)
    app._rt_end_var = ctk.BooleanVar(value=False); app._rt_end_title = ctk.StringVar(value=""); app._rt_end_url = ctk.StringVar(value=""); app._rt_end_image = ctk.StringVar(value="")
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
    block.grid_remove()

def browse_scenes(app) -> None:
    M = _m(app); path = M.filedialog.askopenfilename(title="Choose the scenes file", filetypes=[("Scenes CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
    if path: app._rt_scenes_var.set(path)

def browse_end_image(app) -> None:
    M = _m(app); path = M.filedialog.askopenfilename(title="Choose the end-card picture", filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")])
    if path: app._rt_end_image.set(path)

def end_card_settings(app) -> dict:
    return {"enabled": bool(app._rt_end_var.get()), "title": app._rt_end_title.get().strip(), "url": app._rt_end_url.get().strip(), "image": app._rt_end_image.get().strip()}

def activate(app) -> None:
    if getattr(app, "_rt_running", False): return
    app._rt_block.grid(); app._rt_status_var.set("")
    import visual_bridge
    visual_bridge.restore(app, OWNER)      # the pictures of the last Generate scenes, back in the Visuals tab

def _inputs_key(app) -> tuple:
    """What Generate scenes listed pictures for: other inputs need Generate scenes again before Render."""
    return (app._rt_scenes_var.get().strip(), str(app._current_voiceover_path() or ""), bool(app._rt_smart_var.get()), bool(app._rt_3d_var.get()), bool(app._rt_variety_var.get()), app._rt_title_var.get().strip())

def needs_scenes(app) -> bool:
    """Flow pictures are the assets Rep Theory fetches: with them on, Generate scenes puts them in the Visuals tab first. Without them nothing is fetched."""
    return bool(app._rt_flow_var.get()) and getattr(app, "_rt_ready_key", None) != _inputs_key(app)

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
    hint = "The pictures are in the Visuals tab: change any there, then click Render Rep Theory." if app._rt_flow_var.get() else "Click Render Rep Theory: the visuals are planned from the narration, then rendered."
    app.stage_var.set("RENDER"); app.hint_var.set(hint); app._set_generate_btn(state="normal", text="Render Rep Theory")

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
    if wantflow:
        try: flow_settings, flow_accounts = app._image_flow_run_settings()      # the app's own Flow switches (agent / UI mode) and the video profile's accounts
        except Exception as exc: app._append_log(f"{TAG} Flow settings unavailable ({exc}); Flow pictures use agent mode defaults.\n")
    if want3d:
        from . import clip3d
        if not clip3d.available(): app._append_log(f"{TAG} 3D body model or renderer not found on this machine: scenes about body parts keep their usual look (see docs/rep_theory).\n")
    import visual_bridge
    media_only = needs_scenes(app); folder = visual_bridge.folder(OWNER, ws); inputs = _inputs_key(app)
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
                                          flow_mode=(flow_settings or {}).get("generationMode", "agent"), flow_settings=flow_settings, flow_accounts=flow_accounts, media_only=media_only, table=table)
            if media_only: result = dict(result, rows=fetch_pictures(manager, folder, result.get("requests") or [], app._rt_cancel.is_set, log))
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
                rows = result.get("rows") or []; visual_bridge.fill(app, OWNER, rows); app._rt_ready_key = inputs
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

def fetch_pictures(manager, folder: Path, requests: list, cancelled, log) -> list:
    """Generate scenes: one Visuals-tab row per picture. A picture already in the Rep Theory library is filed as done (nothing is generated twice);
    the rest are made through the app's AssetManager (its Flow provider, settings and accounts), into this style's own folder."""
    import shutil
    from asset_manager import AssetManifest
    from providers.base import SceneRow
    rows = [SceneRow(scene_number=str(r["no"]), script_segment=r["text"], asset_type="flow_image", prompt=r["prompt"]) for r in requests]
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
    if todo and not cancelled(): manager.resolve_all(rows)
    return rows
