"""War Documentary in the app's style picker: the card, its controls and the render worker. Imported only when the style is picked.

The picker hooks in app.py are small and additive (see the `_war_*` methods there); everything the style does lives here.
Opt-in per session: nothing is saved by this module except what the render itself writes (the video and its .plan.json next to it) and,
for a scenes CSV, the footage its searches fetch (state/war/assets, listed in the Visuals tab; the next Render uses what the tab holds).

Scenes come from (1) a scenes CSV or JSON you choose (JSON: list of {text, start, end, words, footage, footage_meta}; footage paths may be
relative to the project; CSV: what "Copy the CSV prompt" asks for, untimed rows aligned to the voiceover, scene numbers kept), else (2) the voiceover's own transcript, cut into sentences, with the footage the project's scene manifest holds for the same
scene number when there is one. Without footage a scene gets a truthful map/card or no visual, never an unrelated clip.
A CSV run makes no Gemini call: the CSV's prompt column is the search.
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

STYLE_NAME = "War Documentary"
TAG = "[WAR DOCUMENTARY]"


def _m(app):
    return sys.modules[type(app).__module__]


# ---- scenes ---------------------------------------------------------------------------------------------------------------
def sentences_from_words(words: List[Any], total_s: float = 0.0) -> List[Dict[str, Any]]:
    """Scene dicts from word times [(word, start, end), ...]: a scene per sentence (a pause over 1.2 s also ends one); contiguous in time."""
    out: List[Dict[str, Any]] = []
    cur: List[dict] = []

    def flush() -> None:
        if cur:
            out.append({"scene_no": len(out) + 1, "text": " ".join(w["w"] for w in cur), "start": cur[0]["t0"], "end": cur[-1]["t1"],
                        "words": list(cur)})
            cur.clear()

    prev_end = None
    for item in words or []:
        try:
            w, t0, t1 = str(item[0]), float(item[1]), float(item[2])
        except (TypeError, ValueError, IndexError):
            continue
        if cur and prev_end is not None and t0 - prev_end > 1.2:
            flush()
        cur.append({"w": w, "t0": t0, "t1": t1})
        prev_end = t1
        if re.search(r"[.!?]['\")\]]*$", w) and len(cur) >= 4:
            flush()
    flush()
    for i, sc in enumerate(out):                    # contiguous: each scene runs to the next one's start; the last to the narration's end
        sc["end"] = out[i + 1]["start"] if i + 1 < len(out) else max(sc["end"], float(total_s or 0.0))
    if out:
        out[0]["start"] = 0.0
    return out


_CSV_TEXT = ("script_segment", "text", "narration", "script", "sentence", "vo_text")
_CSV_NO = ("scene_number", "scene_no", "scene", "no", "#")


def read_scenes_csv(path: str) -> List[dict]:
    """The CSV "Copy the CSV prompt" asks for (scene_number, script_segment, asset_type, prompt) -> scene dicts. Header names are case-insensitive;
    `,` `;` or tab separated; a ```csv fence pasted along with the AI's reply is ignored. start/end (seconds) are optional: all rows or none;
    untimed rows are aligned to the voiceover at Render. The scene number is kept, so footage the Visuals tab fetched for that scene is used."""
    import csv
    import io

    p = Path(path)
    raw = p.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")      # older Excel exports
    lines = [ln for ln in content.splitlines() if ln.strip() and not ln.strip().startswith("```")]
    if not lines:
        raise ValueError(f"{p.name} is empty")
    try:
        dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO("\n".join(lines)), dialect=dialect)
    cols = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}
    text_col = next((cols[a] for a in _CSV_TEXT if a in cols), None)
    if text_col is None:
        raise ValueError(f"{p.name} needs a script_segment (or text) column; its header is: {', '.join(reader.fieldnames or [])}")
    no_col = next((cols[a] for a in _CSV_NO if a in cols), None)
    start_col, end_col = cols.get("start"), cols.get("end")
    out: List[dict] = []
    for r in reader:
        text = (r.get(text_col) or "").strip()
        if not text:
            continue
        sc: Dict[str, Any] = {"text": text}
        no = (r.get(no_col) or "").strip() if no_col else ""
        sc["scene_no"] = int(no) if no.isdigit() else len(out) + 1
        for key in ("asset_type", "prompt", "footage"):
            if key in cols and (r.get(cols[key]) or "").strip():
                sc[key] = r[cols[key]].strip()
        if start_col and end_col and (r.get(start_col) or "").strip() and (r.get(end_col) or "").strip():
            try:
                sc["start"], sc["end"] = float(r[start_col]), float(r[end_col])
            except ValueError:
                raise ValueError(f"{p.name} scene {sc['scene_no']}: start/end must be seconds, got {r[start_col]!r} / {r[end_col]!r}") from None
        out.append(sc)
    if not out:
        raise ValueError(f"{p.name} has no scenes with narration text")
    if any("start" in x for x in out) and not all("start" in x for x in out):
        raise ValueError("start/end are filled on some rows but not all: fill them on every row, or clear them on all rows to align to the voiceover")
    return out


def read_scenes_file(path: str, project_dir: Path) -> List[dict]:
    import json

    p = Path(path)
    if p.suffix.lower() in (".csv", ".tsv", ".txt"):
        return read_scenes_csv(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{p.name} must hold a JSON list of scenes")
    return data


def needs_alignment(scenes: List[dict]) -> bool:
    return bool(scenes) and any("start" not in sc or "end" not in sc for sc in scenes)


# ---- CSV footage (fetched through the app's AssetManager, listed in the Visuals tab) ------------------------------------------
OWNER = "war"      # its CSV footage rows in the Visuals tab (visual_bridge)
FETCH_TYPES = ("stock_video", "youtube_video", "archive_video", "nasa_video", "commons_video", "flow_video")
AI_TYPES = ("flow_video",)
AI_CREDITS_PER_CLIP = 10          # Flow's price for one video clip
DEFAULT_AI_CAP = 15               # AI clips made per video at most, unless the user sets another number on the War page
AI_LOOK = ("cinematic documentary shot, desaturated muted colours, overcast moody light, shallow depth of field, slow camera move, "
           "35mm film grain, no text, no logos, no faces in close-up")
LOCAL_TYPES = ("local", "local_video")


def csv_rows(scenes: List[dict]) -> List[Any]:
    """Visuals-tab rows (the app's SceneRow) for the CSV scenes that ask for footage. `none` rows get a map or card from the narration and
    are left out; `local` rows are listed so the user can attach the clip there."""
    from providers.base import SceneRow

    rows = []
    for sc in scenes:
        at = str(sc.get("asset_type") or "").strip().lower()
        if at in FETCH_TYPES or at in LOCAL_TYPES:
            prompt = str(sc.get("prompt") or "").strip()
            if at == "nasa_video" and not prompt:
                prompt = str(sc.get("text") or "")[:80]
            if at in AI_TYPES and prompt and AI_LOOK not in prompt:
                prompt = f"{prompt.rstrip('. ')}. {AI_LOOK}"         # every AI clip in the same documentary look
            rows.append(SceneRow.from_csv_row({"scene_number": str(sc.get("scene_no")), "script_segment": str(sc.get("text") or ""),
                                               "asset_type": at, "prompt": prompt}))
    return rows


def ai_plan(scenes: List[dict], images_dir: Optional[Path], cap: int = DEFAULT_AI_CAP) -> Dict[str, Any]:
    """{make: [scene nos to generate], over: [scene nos past the cap], have: n already made}. Clips already in the Visuals table cost nothing."""
    import visual_bridge

    make: List[str] = []
    over: List[str] = []
    have = 0
    for r in csv_rows(scenes):
        if r.asset_type != "video" or not str(r.scene_number):
            continue
        if images_dir is not None and visual_bridge.records(images_dir, [r]):
            have += 1
        elif len(make) < max(0, int(cap)):
            make.append(str(r.scene_number))
        else:
            over.append(str(r.scene_number))
    return {"make": make, "over": over, "have": have, "credits": len(make) * AI_CREDITS_PER_CLIP}


def fetch_csv_footage(scenes: List[dict], manager: Any, images_dir: Path, log=lambda m: None, cancel=None,
                      ai_cap: int = DEFAULT_AI_CAP, fetch: bool = True) -> "tuple[List[dict], List[Any]]":
    """(scenes with `footage` set from the Visuals table, the table's rows). The CSV's own searches are fetched for the rows the table does not
    hold yet (a clip already there, or one the user picked, is kept); `none` rows are marked no_footage so no clip is put under their graphic.
    fetch=False (Render after Generate scenes) fetches nothing: the video uses exactly what the Visuals tab holds."""
    import visual_bridge
    from asset_manager import AssetManifest
    from . import integration

    rows = csv_rows(scenes)
    over = set(ai_plan(scenes, images_dir, ai_cap)["over"])
    if over:
        log(f"AI clip limit {ai_cap} reached: scenes {', '.join(sorted(over, key=lambda x: int(x) if x.isdigit() else 0))} use the map or cards instead")
    todo = []
    for r in (rows if fetch else []):
        if r.asset_type in LOCAL_TYPES or str(r.scene_number) in over or visual_bridge.records(images_dir, [r]):
            continue
        errs = manager.validate_rows([r])
        if errs:
            log(f"scene {r.scene_number}: not searched ({'; '.join(errs)})")
            continue
        todo.append(r)
    if todo:
        log(f"Fetching footage for {len(todo)} scenes with the CSV's searches…")
        Path(images_dir).mkdir(parents=True, exist_ok=True)
        stop = threading.Event()
        if cancel is not None:
            def watch() -> None:
                while not stop.wait(0.3):
                    if cancel():
                        try:
                            manager.request_cancel()
                        except Exception:
                            pass
                        return

            threading.Thread(target=watch, daemon=True, name="war-asset-cancel").start()
        try:
            manager.resolve_all(todo)
        except Exception as exc:  # noqa: BLE001 - a failed fetch leaves those scenes on maps/cards; the render still runs
            log(f"footage fetch stopped early: {type(exc).__name__}: {exc}")
        finally:
            stop.set()
    man = AssetManifest(Path(images_dir)) if Path(images_dir).is_dir() else None
    out: List[dict] = []
    got = 0
    for sc in scenes:
        sc = dict(sc)
        at = str(sc.get("asset_type") or "").strip().lower()
        if at == "none":
            sc["no_footage"] = True
        rec = (man.get(str(sc.get("scene_no"))) or {}) if man is not None and (at in FETCH_TYPES or at in LOCAL_TYPES) else {}
        foot, _why = integration.footage_from_record(rec, Path(images_dir)) if rec else (None, "")
        if foot:
            sc["footage"] = foot
            meta = integration.footage_meta_for(rec, sc.get("footage_meta"), scene_file=Path(foot).name)
            if rec.get("user_override") or rec.get("source") == "manual":
                meta["user_supplied"] = True       # picked in the Visuals tab: never swapped for another clip
            elif at in AI_TYPES:
                meta["ai_generated"] = True        # labelled "AI-generated illustration", never presented as footage of the event
            sc["footage_meta"] = meta
            got += 1
        out.append(sc)
    want = sum(1 for r in rows if r.asset_type not in LOCAL_TYPES)
    if rows:
        log(f"Footage from the CSV: {got} of {len(rows)} scenes have a clip" + (f" ({want} searched)" if want != len(rows) else ""))
    return out, rows


# ---- build / show / hide ---------------------------------------------------------------------------------------------------
def build(app, parent, *, row: int) -> None:
    M = _m(app)
    ctk = M.ctk
    app._war_scenes_var = ctk.StringVar(value="")
    app._war_scenes_var.trace_add("write", lambda *_: getattr(app, "_war_running", False) or app._sync_primary_cta())   # a new CSV: Generate scenes again
    app._war_ai_cap_var = ctk.StringVar(value=str((getattr(app, "_settings", None) or {}).get("war_ai_cap", DEFAULT_AI_CAP)))
    app._war_status_var = ctk.StringVar(value="")
    app._war_cancel = threading.Event()
    app._war_running = getattr(app, "_war_running", False)
    block = ctk.CTkFrame(parent, fg_color=M._CARD, corner_radius=10, border_width=1, border_color=M._BORDER)
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._war_block = block
    app._style_card_header(block, "War Documentary",
                           "Narration-driven war and geopolitics documentaries: maps, equipment cards, attributed statements and statistics, each "
                           "labelled confirmed, attributed, disputed, unverified or illustrative. Planned from your voiceover; nothing starts until you press Render.")
    controls = ctk.CTkFrame(block, fg_color="transparent")
    controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 12))
    controls.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Voiceover", app.audio_var, lambda: app._browse_audio(stay=True), parent=controls,
                  placeholder_text="None yet: use Import Voiceover")
    app._path_row(1, "Scenes file", app._war_scenes_var, lambda: browse_scenes(app), parent=controls,
                  placeholder_text="Optional: the scenes CSV (from Copy the CSV prompt) or JSON; otherwise planned from the narration")
    go = ctk.CTkFrame(controls, fg_color="transparent")
    go.grid(row=2, column=0, sticky="ew", pady=(12, 0))
    app._war_render_btn = ctk.CTkButton(go, text="Render War Documentary", width=230, height=40, corner_radius=6, fg_color=M._ACCENT,
                                        hover_color=M._ACCENT_HOV, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render_click(app))
    app._war_render_btn.grid(row=0, column=0, padx=(0, 12))
    cap = ctk.CTkFrame(go, fg_color="transparent")
    cap.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ctk.CTkLabel(cap, text="Max AI clips per video", font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")
    ctk.CTkEntry(cap, textvariable=app._war_ai_cap_var, width=52, height=26).grid(row=0, column=1, padx=(8, 8))
    ctk.CTkLabel(cap, text=f"{AI_CREDITS_PER_CLIP} Flow credits each; only for CSV rows marked flow_video. You are asked before any are made.",
                 font=ctk.CTkFont(size=11), text_color=M._MUTED).grid(row=0, column=2, sticky="w")
    ctk.CTkLabel(go, text="Without footage in the scenes, a scene gets a map or card, or no visual.", font=ctk.CTkFont(size=11),
                 text_color=M._MUTED).grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(controls, textvariable=app._war_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=560,
                 justify="left").grid(row=3, column=0, sticky="ew", pady=(8, 0))
    bar = ctk.CTkFrame(controls, fg_color="transparent")
    bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
    bar.grid_columnconfigure(1, weight=1)
    M._make_button(bar, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="lg", width=150).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(bar, text="Paste it into any AI, then choose the CSV it writes as the Scenes file.", font=ctk.CTkFont(size=11), text_color=M._MUTED,
                 anchor="w").grid(row=0, column=1, sticky="w", padx=(10, 0))
    app._build_csv_prompt_script_box(bar, row=1, columnspan=2)
    block.grid_remove()


def csv_prompt_text(script: str = "") -> str:
    """The War Documentary CSV prompt (cinematic_explainer/war/data/war_csv_prompt.txt) with the script in place of its placeholder."""
    text = (Path(__file__).resolve().parent / "data" / "war_csv_prompt.txt").read_text(encoding="utf-8")
    script = (script or "").strip()
    return text.replace("<<<PASTE THE SCRIPT HERE>>>", script) if script else text


def copy_csv_prompt(app) -> None:
    M = _m(app)
    for box in getattr(app, "_csv_prompt_script_boxes", []):
        try:
            if box.get("1.0", "end").strip() != getattr(box, "_csv_synced", None):
                app._on_csv_prompt_script_edited(box)   # typed in but not yet left: the click must not lose it
                break
        except Exception:
            pass
    script = app._main_script_text()
    try:
        text = csv_prompt_text(script)
    except OSError as exc:
        M.messagebox.showerror("Copy the CSV prompt", f"The prompt file could not be read: {exc}")
        return
    app.clipboard_clear()
    app.clipboard_append(text)
    app._war_status_var.set("War Documentary prompt copied with your script. Paste it into any AI to get the footage CSV." if script else
                            "War Documentary prompt copied. Paste it into any AI and replace its last line with your script.")


def browse_scenes(app) -> None:
    M = _m(app)
    path = M.filedialog.askopenfilename(title="Choose the scenes file", filetypes=[("Scenes CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
    if path:
        app._war_scenes_var.set(path)


def activate(app) -> None:
    if getattr(app, "_war_running", False):
        return
    app._war_block.grid()
    app._war_status_var.set("")
    import visual_bridge

    visual_bridge.restore(app, OWNER)      # the CSV footage of the last Generate scenes, back in the Visuals tab


def _is_csv(path: str) -> bool:
    return path.lower().endswith((".csv", ".tsv", ".txt"))


def _inputs_key(app) -> tuple:
    """What Generate scenes fetched for: a different scenes file or voiceover needs Generate scenes again before Render."""
    return (app._war_scenes_var.get().strip(), str(app._current_voiceover_path() or ""))


def needs_scenes(app) -> bool:
    """A scenes CSV asks for footage: Generate scenes puts it in the Visuals tab first, then Render uses what the tab holds."""
    return _is_csv(app._war_scenes_var.get().strip()) and getattr(app, "_war_ready_key", None) != _inputs_key(app)


def deactivate(app) -> None:
    block = getattr(app, "_war_block", None)
    if block is not None:
        block.grid_remove()
    try:
        import visual_bridge

        visual_bridge.clear(app, OWNER)
    except Exception:
        pass


# ---- primary button ---------------------------------------------------------------------------------------------------------
def sync_cta(app) -> None:
    if getattr(app, "_war_running", False):
        app._cta_action = "war_cancel"
        app.stage_var.set("GENERATING")
        if app._war_cancel.is_set():
            app.hint_var.set("Stopping…")
            app._set_generate_btn(state="disabled", text="Stopping…")
        else:
            app.hint_var.set("Rendering — click Stop to cancel.")
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
        app.hint_var.set("Select or import a voiceover to continue.")
        app._set_generate_btn(state="normal", text="Import Voiceover")
        return
    app._cta_action = "war_render"
    if needs_scenes(app):
        app.stage_var.set("PLAN")
        app.hint_var.set("Click Generate scenes: the CSV's footage is fetched into the Visuals tab for you to check before rendering.")
        _set_page_btn(app, "Generate scenes")
        app._set_generate_btn(state="normal", text="Generate scenes")
        return
    app.stage_var.set("RENDER")
    if _is_csv(app._war_scenes_var.get().strip()):
        app.hint_var.set("The clips are in the Visuals tab: change any there (Retry, Change source, Local clip), then click Render War Documentary.")
    else:
        app.hint_var.set("Click Render War Documentary: the visuals are planned from the narration, then rendered.")
    _set_page_btn(app, "Render War Documentary")
    app._set_generate_btn(state="normal", text="Render War Documentary")


def _set_page_btn(app, text: str) -> None:
    try:
        app._war_render_btn.configure(text=text)
    except Exception:
        pass


def cta(app, action: str) -> None:
    if action == "war_cancel":
        cancel(app)
    else:
        on_render_click(app)


def cancel(app) -> None:
    if not getattr(app, "_war_running", False) or app._war_cancel.is_set():
        return
    app._war_cancel.set()
    app._append_log(f"{TAG} Stop requested: finishing the current piece, then stopping.\n")
    app._sync_primary_cta()


# ---- render ---------------------------------------------------------------------------------------------------------------
def on_render_click(app) -> None:
    M = _m(app)
    if getattr(app, "_war_running", False):
        return
    ws = app._workspace
    if ws is None:
        M.messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    voiceover = app._current_voiceover_path()
    if voiceover is None:
        M.messagebox.showerror("Cannot start", "Select or import a voiceover first.")
        return
    scenes_path = app._war_scenes_var.get().strip()
    if scenes_path and not Path(scenes_path).is_file():
        M.messagebox.showerror("Cannot start", f"The scenes file was not found:\n{scenes_path}")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    project_dir = Path(ws.root)
    model = app.model_var.get().strip() or "base"
    state_dir = getattr(ws, "state_dir", None)
    manager = None
    images_dir = None
    ai_cap = DEFAULT_AI_CAP
    media_only = needs_scenes(app)       # first Generate scenes (the CSV's footage into the Visuals tab), then Render from what the tab holds
    inputs = _inputs_key(app)
    if _is_csv(scenes_path):
        import visual_bridge

        images_dir = visual_bridge.folder(OWNER, ws)
    if media_only:                       # the CSV's searches are fetched through the app's own providers
        try:
            ai_cap = max(0, int(str(app._war_ai_cap_var.get()).strip() or DEFAULT_AI_CAP))
        except ValueError:
            M.messagebox.showerror("Cannot start", "Max AI clips must be a whole number (0 for none).")
            return
        try:
            app._settings["war_ai_cap"] = ai_cap
            M.save_settings(app._settings)
        except Exception:
            pass
        try:
            plan_ai = ai_plan(read_scenes_file(scenes_path, project_dir), images_dir, ai_cap)
        except Exception as exc:  # noqa: BLE001
            M.messagebox.showerror("Cannot start", f"The scenes file could not be read:\n{exc}")
            return
        if plan_ai["make"]:                # Flow credits are spent only after the user says yes, with the count and cost in front of them
            msg = (f"This CSV asks for {len(plan_ai['make']) + len(plan_ai['over'])} AI clips"
                   + (f" ({plan_ai['have']} already made, free)" if plan_ai["have"] else "") + ".\n\n"
                   f"Make {len(plan_ai['make'])} now = {plan_ai['credits']} Flow credits."
                   + (f"\n{len(plan_ai['over'])} more are over your limit of {ai_cap} and will use the map or cards." if plan_ai["over"] else "")
                   + "\n\nYes: make them.  No: continue without new AI clips.")
            if not M.messagebox.askyesno("AI footage", msg):
                ai_cap = 0
        try:
            manager = app._build_asset_manager(images_dir, [])        # built here: it reads Tk variables
            manager.settings["gemini_enabled"] = False                  # the CSV directs the scenes: no Gemini call in this run
        except Exception as exc:  # noqa: BLE001
            M.messagebox.showerror("Cannot start", f"The app's asset sources could not be set up:\n{exc}")
            return
    app._war_cancel.clear()
    app._war_running = True
    app._war_status_var.set("Fetching the footage for the Visuals tab…" if media_only else "Starting…")
    run = None if media_only else app._track_generation_start("war")      # the Export page follows the render (not Generate scenes)
    app._sync_primary_cta()

    def log(msg: str) -> None:
        app.after(0, lambda: app._append_log(f"{TAG} {msg}\n"))

    def progress(k: float, msg: str) -> None:
        app.after(0, lambda: (app._war_status_var.set(f"{int(k * 100)}%  {msg}"), run is not None and app._export_progress(k, msg)))

    def return_rows(rows: List[Any]) -> None:
        def done() -> None:      # Generate scenes ends in the Visuals tab; nothing is rendered and the Export page is not touched
            import visual_bridge

            app._war_running = False
            visual_bridge.fill(app, OWNER, rows)
            app._war_ready_key = inputs
            ok = len(visual_bridge.records(images_dir, rows))
            msg = (f"Scenes ready: {ok} of {len(rows)} clips found. Check them in the Visuals tab, then click Render War Documentary."
                   if rows else "Scenes ready (no footage scenes to check). Click Render War Documentary.")
            app._war_status_var.set(msg)
            app._append_log(f"{TAG} {msg}\n")
            if rows:
                try:
                    app._goto_workflow_view("visual_plan")
                except Exception:
                    pass
            app._sync_primary_cta()

        app.after(0, done)

    def worker() -> None:
        from . import integration, segments

        result: Optional[dict] = None
        error = ""
        rows: List[Any] = []
        try:
            scenes = read_scenes_file(scenes_path, project_dir) if scenes_path else None
            if scenes is None or needs_alignment(scenes):
                log("Reading the narration's word times…")
                words = app._pakmap_get_words(voiceover, model, state_dir, log)
                try:
                    from pakmap.app_integration import voiceover_duration

                    total = float(voiceover_duration(voiceover) or 0.0)
                except Exception:
                    total = 0.0
            if scenes is not None and needs_alignment(scenes):     # untimed CSV rows (what "Copy the CSV prompt" asks for): the voiceover's real times
                from health_cinema import scenes_csv

                scenes, frac = scenes_csv.align_to_words(scenes, words, total)
                log(f"{len(scenes)} scenes from the CSV, aligned to the voiceover: {scenes_csv.match_note(frac)}")
            if scenes is not None and images_dir is not None:
                if media_only:
                    progress(0.0, "fetching the CSV's footage")
                scenes, rows = fetch_csv_footage(scenes, manager, images_dir, log, cancel=app._war_cancel.is_set, ai_cap=ai_cap, fetch=media_only)
                if app._war_cancel.is_set():
                    raise segments.RenderCancelled()
                if media_only:
                    return_rows(rows)
                    return
            elif scenes is None:
                scenes = sentences_from_words(words, total)
                if not scenes:
                    raise RuntimeError("the narration has no words to plan from")
                log(f"{len(scenes)} scenes planned from the narration")
            result = integration.run_war_documentary(str(project_dir), scenes, str(voiceover), str(out_path), cancel_check=app._war_cancel.is_set,
                                                     progress_cb=progress)
        except segments.RenderCancelled:
            error = "Stopped."
        except segments.MissingInput as exc:
            error = f"A footage file is missing: {exc}"
        except Exception as exc:  # noqa: BLE001 - shown to the user, never a silent failure
            error = f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._war_running = False
            if rows:
                import visual_bridge

                visual_bridge.fill(app, OWNER, rows)      # check or change the clips there; the next Render uses what the tab holds
            if run is not None:
                from export_state import run_outcome

                done = run_outcome(error, out_path if result else None)
                app._track_generation_end(run, done, output_path=out_path if done == "completed" else None, validated=done == "completed", message=error)
            if error:
                app._war_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            elif result:
                n = len(result.get("plan_log") or [])
                msg = f"Done: {out_path.name} ({n} scenes planned"
                if result.get("render", {}).get("fallback"):
                    msg += "; used the fallback renderer"
                msg += ")"
                app._war_status_var.set(msg)
                app._append_log(f"{TAG} {msg}; plan report: {result.get('report_path')}\n")
                for line in (result.get("credits") or [])[:20]:
                    app._append_log(f"{TAG} credit: {line}\n")
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name="war-documentary-render", daemon=True).start()
