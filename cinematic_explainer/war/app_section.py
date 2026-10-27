"""War Documentary in the app's style picker: the card, its controls and the render worker. Imported only when the style is picked.

The picker hooks in app.py are small and additive (see the `_war_*` methods there); everything the style does lives here.
Opt-in per session: nothing is saved by this module except what the render itself writes (the video and its .plan.json next to it).

Scenes come from (1) a scenes JSON you choose (list of {text, start, end, words, footage, footage_meta}; footage paths may be relative to the
project), else (2) the voiceover's own transcript, cut into sentences, with the footage the project's scene manifest holds for the same
scene number when there is one. Without footage a scene gets a truthful map/card or no visual, never an unrelated clip.
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


def read_scenes_file(path: str, project_dir: Path) -> List[dict]:
    import json

    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{p.name} must hold a JSON list of scenes")
    return data


# ---- build / show / hide ---------------------------------------------------------------------------------------------------
def build(app, parent, *, row: int) -> None:
    M = _m(app)
    ctk = M.ctk
    app._war_scenes_var = ctk.StringVar(value="")
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
                  placeholder_text="Optional: scenes JSON with footage; otherwise planned from the narration")
    go = ctk.CTkFrame(controls, fg_color="transparent")
    go.grid(row=2, column=0, sticky="ew", pady=(12, 0))
    app._war_render_btn = ctk.CTkButton(go, text="Render War Documentary", width=230, height=40, corner_radius=6, fg_color=M._ACCENT,
                                        hover_color=M._ACCENT_HOV, font=ctk.CTkFont(size=13, weight="bold"), command=lambda: on_render_click(app))
    app._war_render_btn.grid(row=0, column=0, padx=(0, 12))
    ctk.CTkLabel(go, text="Without footage in the scenes, a scene gets a map or card, or no visual.", font=ctk.CTkFont(size=11),
                 text_color=M._MUTED).grid(row=0, column=1, sticky="w")
    ctk.CTkLabel(controls, textvariable=app._war_status_var, font=ctk.CTkFont(size=11), text_color=M._MUTED, anchor="w", wraplength=560,
                 justify="left").grid(row=3, column=0, sticky="ew", pady=(8, 0))
    bar = ctk.CTkFrame(controls, fg_color="transparent")
    bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
    bar.grid_columnconfigure(1, weight=1)
    M._make_button(bar, "Copy the CSV prompt", lambda: copy_csv_prompt(app), size="lg", width=150).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(bar, text="Paste it into any AI to get the footage CSV for your script.", font=ctk.CTkFont(size=11), text_color=M._MUTED,
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
    path = M.filedialog.askopenfilename(title="Choose the scenes file", filetypes=[("Scenes JSON", "*.json"), ("All files", "*.*")])
    if path:
        app._war_scenes_var.set(path)


def activate(app) -> None:
    if getattr(app, "_war_running", False):
        return
    app._war_block.grid()
    app._war_status_var.set("")


def deactivate(app) -> None:
    block = getattr(app, "_war_block", None)
    if block is not None:
        block.grid_remove()


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
    app.stage_var.set("RENDER")
    app.hint_var.set("Click Render War Documentary: the visuals are planned from the narration, then rendered.")
    app._set_generate_btn(state="normal", text="Render War Documentary")


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
    app._war_cancel.clear()
    app._war_running = True
    app._war_status_var.set("Starting…")
    app._sync_primary_cta()

    def log(msg: str) -> None:
        app.after(0, lambda: app._append_log(f"{TAG} {msg}\n"))

    def progress(k: float, msg: str) -> None:
        app.after(0, lambda: app._war_status_var.set(f"{int(k * 100)}%  {msg}"))

    def worker() -> None:
        from . import integration, segments

        result: Optional[dict] = None
        error = ""
        try:
            if scenes_path:
                scenes = read_scenes_file(scenes_path, project_dir)
            else:
                log("Reading the narration's word times…")
                words = app._pakmap_get_words(voiceover, model, state_dir, log)
                try:
                    from pakmap.app_integration import voiceover_duration

                    total = float(voiceover_duration(voiceover) or 0.0)
                except Exception:
                    total = 0.0
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
