"""Health Cinema in the app's style picker: the card, its controls and the render worker. Imported only when the style is picked.

The picker hooks in app.py are small and additive (see the `_health_*` methods there); everything the style does lives in this package.
Opt-in per session: nothing is saved by this module except what the render itself writes (the video, its .health_cinema.json report, and cached
clips under <project>/state/health_cinema). 16:9 landscape only: Final is 1920x1080, Preview is 1280x720.

Scenes come from (1) a scenes JSON (list of {text, start, end, sources?, footage?, chapter?}) or scenes CSV (see scenes_csv.py; no timings needed, rows are aligned to the voiceover) you choose, else (2) the voiceover's own transcript cut
into sentences. Sources attached to a sentence are what lets a statistic or study appear as a card; without them the scene is flagged for review.
"""
from __future__ import annotations

import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import profiles as P

STYLE_NAME = "Health Cinema"
TAG = "[HEALTH CINEMA]"


def _m(app):
    return sys.modules[type(app).__module__]


def sentences_from_words(words: List[Any], total_s: float = 0.0) -> List[Dict[str, Any]]:
    """Sentence dicts from word times [(word, start, end), ...] (a pause over 1.2 s also ends one); contiguous in time."""
    out: List[Dict[str, Any]] = []
    cur: List[dict] = []

    def flush() -> None:
        if cur:
            out.append({"scene_no": len(out) + 1, "text": " ".join(w["w"] for w in cur), "start": cur[0]["t0"], "end": cur[-1]["t1"], "words": list(cur)})
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
    for i, sc in enumerate(out):
        sc["end"] = out[i + 1]["start"] if i + 1 < len(out) else max(sc["end"], float(total_s or 0.0))
    if out:
        out[0]["start"] = 0.0
    return out


def read_scenes_file(path: str, project_dir: Path) -> List[dict]:
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{Path(path).name} must hold a JSON list of scenes")
    for s in data:
        if not isinstance(s, dict) or "text" not in s or "start" not in s or "end" not in s:
            raise ValueError("every scene needs text, start and end")
    return data


def build(app, parent, *, row: int) -> None:
    M = _m(app)
    ctk = M.ctk
    app._health_scenes_var = ctk.StringVar(value="")
    app._health_status_var = ctk.StringVar(value="")
    app._health_profile_var = ctk.StringVar(value=P.get_profile(P.DEFAULT_PROFILE).name)
    app._health_preview_var = ctk.BooleanVar(value=False)
    app._health_youtube_var = ctk.BooleanVar(value=False)
    app._health_flow_var = ctk.BooleanVar(value=False)
    app._health_edit_var = ctk.StringVar(value="Classic")                    # Classic (default) / High-end; session-only like the other options here
    app._health_music_var = ctk.BooleanVar(value=True)                       # only used by High-end
    app._health_cancel = threading.Event()
    app._health_running = getattr(app, "_health_running", False)
    block = ctk.CTkFrame(parent, fg_color=M._CARD, corner_radius=10, border_width=1, border_color=M._BORDER)
    block.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    block.grid_columnconfigure(0, weight=1)
    app._health_block = block
    app._style_card_header(block, "Health Cinema",
                           "Full-length 16:9 health videos planned from your narration: cinematic 3D anatomy where an asset exists, evidence and statistic cards "
                           "with sources, and honest labels. Unsupported or unsourced claims are flagged for review. Nothing starts until you press Render.")
    controls = ctk.CTkFrame(block, fg_color="transparent")
    controls.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 12))
    controls.grid_columnconfigure(0, weight=1)
    app._path_row(0, "Voiceover", app.audio_var, lambda: app._browse_audio(stay=True), parent=controls, placeholder_text="None yet: use Import Voiceover")
    app._path_row(1, "Scenes file", app._health_scenes_var, lambda: browse_scenes(app), parent=controls,
                  placeholder_text="Optional: scenes CSV or JSON with sources; otherwise planned from the narration")
    opts = ctk.CTkFrame(controls, fg_color="transparent")
    opts.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    ctk.CTkLabel(opts, text="Profile", font=ctk.CTkFont(size=12), text_color=M._MUTED).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkOptionMenu(opts, values=list(P.profile_names()), variable=app._health_profile_var, width=240).grid(row=0, column=1, padx=(0, 16))
    ctk.CTkCheckBox(opts, text="Preview (1280x720)", variable=app._health_preview_var).grid(row=0, column=2, padx=(0, 16))
    ctk.CTkCheckBox(opts, text="Allow YouTube clips", variable=app._health_youtube_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    ctk.CTkCheckBox(opts, text="Allow Flow AI video (uses credits)", variable=app._health_flow_var).grid(row=1, column=2, sticky="w", pady=(8, 0))
    ctk.CTkLabel(opts, text="Edit", font=ctk.CTkFont(size=12), text_color=M._MUTED).grid(row=2, column=0, padx=(0, 8), pady=(8, 0))
    ctk.CTkSegmentedButton(opts, values=["Classic", "High-end"], variable=app._health_edit_var, command=lambda _v=None: sync_edit_options(app)).grid(
        row=2, column=1, sticky="w", pady=(8, 0))
    app._health_music_cb = ctk.CTkCheckBox(opts, text="Music (High-end)", variable=app._health_music_var)
    app._health_music_cb.grid(row=2, column=2, sticky="w", pady=(8, 0))
    sync_edit_options(app)
    go = ctk.CTkFrame(controls, fg_color="transparent")
    go.grid(row=3, column=0, sticky="ew", pady=(12, 0))
    app._health_render_btn = ctk.CTkButton(go, text="Render Health Cinema", width=230, height=40, corner_radius=6, fg_color=M._ACCENT, hover_color=M._ACCENT_HOV,
                                           font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render_click(app))
    app._health_render_btn.grid(row=0, column=0, padx=(0, 12))
    ctk.CTkLabel(go, text="Landscape 16:9 only. 3D anatomy needs the optional local asset; otherwise a text card is used.", font=ctk.CTkFont(size=11),
                 text_color=M._MUTED).grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(controls, textvariable=app._health_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=560,
                 justify="left").grid(row=4, column=0, sticky="ew", pady=(8, 0))
    block.grid_remove()


def sync_edit_options(app) -> None:
    cb = getattr(app, "_health_music_cb", None)           # Music only matters for High-end
    if cb is not None:
        cb.configure(state="normal" if app._health_edit_var.get() == "High-end" else "disabled")


def edit_kwargs(app) -> dict:
    """Extra run_health_cinema kwargs: empty for Classic (call unchanged); edit + music for High-end."""
    if app._health_edit_var.get() == "High-end":
        return {"edit": "high_end", "music": bool(app._health_music_var.get())}
    return {}


def browse_scenes(app) -> None:
    M = _m(app)
    path = M.filedialog.askopenfilename(title="Choose the scenes file", filetypes=[("Scenes CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
    if path:
        app._health_scenes_var.set(path)


def activate(app) -> None:
    if getattr(app, "_health_running", False):
        return
    app._health_block.grid()
    app._health_status_var.set("")


def deactivate(app) -> None:
    block = getattr(app, "_health_block", None)
    if block is not None:
        block.grid_remove()


def sync_cta(app) -> None:
    if getattr(app, "_health_running", False):
        app._cta_action = "health_cancel"
        app.stage_var.set("GENERATING")
        if app._health_cancel.is_set():
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
    app._cta_action = "health_render"
    app.stage_var.set("RENDER")
    app.hint_var.set("Click Render Health Cinema: the visuals are planned from the narration, then rendered.")
    app._set_generate_btn(state="normal", text="Render Health Cinema")


def cta(app, action: str) -> None:
    if action == "health_cancel":
        cancel(app)
    else:
        on_render_click(app)


def cancel(app) -> None:
    if not getattr(app, "_health_running", False) or app._health_cancel.is_set():
        return
    app._health_cancel.set()
    app._append_log(f"{TAG} Stop requested: finishing the current scene, then stopping.\n")
    app._sync_primary_cta()


def on_render_click(app) -> None:
    M = _m(app)
    if getattr(app, "_health_running", False):
        return
    ws = app._workspace
    if ws is None:
        M.messagebox.showerror("Cannot start", "Create or choose a project first.")
        return
    voiceover = app._current_voiceover_path()
    if voiceover is None:
        M.messagebox.showerror("Cannot start", "Select or import a voiceover first.")
        return
    scenes_path = app._health_scenes_var.get().strip()
    if scenes_path and not Path(scenes_path).is_file():
        M.messagebox.showerror("Cannot start", f"The scenes file was not found:\n{scenes_path}")
        return
    out_path = ws.next_final_path()
    app.output_var.set(str(out_path))
    project_dir = Path(ws.root)
    model = app.model_var.get().strip() or "base"
    state_dir = getattr(ws, "state_dir", None)
    profile = app._health_profile_var.get()
    quality = "preview" if app._health_preview_var.get() else "final"
    allow_youtube, allow_flow = bool(app._health_youtube_var.get()), bool(app._health_flow_var.get())
    extra = edit_kwargs(app)
    images_dir = project_dir / "state" / "health_cinema" / "assets"      # its own asset folder + manifest: never mixes with Normal video's Images/
    try:
        manager = app._build_asset_manager(images_dir, [])                # the app's own provider wiring and settings (built here: it reads Tk variables)
    except Exception as exc:  # noqa: BLE001
        M.messagebox.showerror("Cannot start", f"The app's asset sources could not be set up:\n{exc}")
        return
    app._health_cancel.clear()
    app._health_running = True
    app._health_status_var.set("Starting…")
    app._sync_primary_cta()

    def log(msg: str) -> None:
        app.after(0, lambda: app._append_log(f"{TAG} {msg}\n"))

    def progress(k: float, msg: str) -> None:
        app.after(0, lambda: app._health_status_var.set(f"{int(k * 100)}%  {msg}"))

    def worker() -> None:
        from . import engine

        result: Optional[dict] = None
        error = ""
        try:
            def narration_words():
                log("Reading the narration's word times…")
                words = app._pakmap_get_words(voiceover, model, state_dir, log)
                try:
                    from pakmap.app_integration import voiceover_duration

                    total = float(voiceover_duration(voiceover) or 0.0)
                except Exception:
                    total = 0.0
                return words, total

            if scenes_path and scenes_path.lower().endswith(".csv"):
                from . import scenes_csv

                sentences = scenes_csv.read_scenes_csv(scenes_path)
                log(f"{len(sentences)} scenes read from {Path(scenes_path).name}")
                if scenes_csv.needs_alignment(sentences):
                    words, total = narration_words()
                    sentences, frac = scenes_csv.align_to_words(sentences, words, total)
                    log(f"Scenes aligned to the voiceover: {scenes_csv.match_note(frac)}")
            elif scenes_path:
                sentences = read_scenes_file(scenes_path, project_dir)
            else:
                words, total = narration_words()
                sentences = sentences_from_words(words, total)
                if not sentences:
                    raise RuntimeError("the narration has no words to plan from")
                log(f"{len(sentences)} sentences read from the narration")
            from . import acquire

            acquirer = acquire.make_acquirer(lambda _dir, _rows: manager, images_dir, log, cancel=app._health_cancel.is_set)
            result = engine.run_health_cinema(project_dir, sentences, str(voiceover), str(out_path), profile=profile, quality=quality,
                                              cancel_check=app._health_cancel.is_set, progress_cb=progress, log=log, script_text=" ".join(s["text"] for s in sentences),
                                              settings=app._settings, acquirer=acquirer, allow_youtube=allow_youtube, allow_flow=allow_flow, **extra)
        except engine.Cancelled:
            error = "Stopped."
        except Exception as exc:  # noqa: BLE001 - shown to the user, never a silent failure
            error = f"{type(exc).__name__}: {exc}"

        def finish() -> None:
            app._health_running = False
            if error:
                app._health_status_var.set(error)
                app._append_log(f"{TAG} {error}\n")
            elif result:
                n = len(result.get("scenes") or [])
                review = len(result.get("review_flags") or [])
                acq = result.get("acquisition") or {}
                msg = f"Done: {out_path.name} ({n} scenes, {result['size'][0]}x{result['size'][1]}, {review} review flags, footage {acq.get('ok', 0)}/{acq.get('requested', 0)})"
                app._health_status_var.set(msg)
                app._append_log(f"{TAG} {msg}; report: {out_path}.health_cinema.json\n")
                app._append_log(f"{TAG} Not implemented yet: {', '.join(result.get('not_implemented') or [])}.\n")
                if review:
                    app._append_log(f"{TAG} {review} scene(s) flagged for review. {result.get('review_note')}\n")
                if result.get("rights_not_established"):
                    app._append_log(f"{TAG} WARNING: {result.get('rights_note')}\n")
                for line in (result.get("credits") or [])[:20]:
                    app._append_log(f"{TAG} credit: {line}\n")
            app._sync_primary_cta()

        app.after(0, finish)

    threading.Thread(target=worker, name="health-cinema-render", daemon=True).start()
