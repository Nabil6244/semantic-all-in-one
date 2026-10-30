"""Story Motion: the style page's own box (Check plan, a few options; the CSV prompt button is the Plan step's). The style is the Normal video engine with the story pipeline on
(shots that follow the narration, layered depth parallax, links, the quality audit): picking the card sets `app._story_motion_active` and saves "story_motion" in project.json (reopening keeps it); nothing runs until Generate. All the work lives in story_pipeline / story_check; this file is only the page.

app.py / style_pages call: sync(app, active), is_active(app), pipeline_settings(app)."""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any, Dict

import customtkinter as ctk

from . import theme as T
from .widgets import make_button

STYLE = "Story Motion"
STRENGTH = {"Calm": "low", "Normal": "medium", "Strong": "high"}
_PROMPT_DOC = Path(__file__).resolve().parents[1] / "docs" / "story" / "dense_csv_prompt.md"


def is_active(app: Any) -> bool:
    """The project's saved choice when a project is open (so reopening it keeps Story Motion), else the session flag."""
    ws = getattr(app, "_workspace", None)
    if ws is not None and hasattr(ws, "story_motion"):
        try:
            return bool(ws.story_motion())
        except Exception:
            pass
    return getattr(app, "_story_motion_active", False) is True      # exactly True: a stand-in object whose attributes are all truthy must not switch the prompt


def remember(app: Any, on: bool) -> None:
    """Save the pick in the open project (project.json "story_motion"); no project open = session flag only."""
    ws = getattr(app, "_workspace", None)
    if ws is not None and hasattr(ws, "set_story_motion"):
        try:
            ws.set_story_motion(bool(on))
        except Exception:
            pass


def prompt_text() -> str:
    """The CSV generator prompt: the code block of docs/story/dense_csv_prompt.md."""
    m = re.search(r"```\n(.*?)\n```", _PROMPT_DOC.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else ""


def pipeline_settings(app: Any) -> Dict[str, Any]:
    """What story_pipeline.build_story gets from this page (merged over the app settings)."""
    o = _opts(app)
    out: Dict[str, Any] = {"story_video": True, "story_dry_run": False, "story_audit": bool(o["audit"]),
                           "story_motion_intensity": STRENGTH.get(o["strength"], "medium"), "story_motion_parallax": bool(o["parallax"])}
    # the motion clips are CPU work and there are hundreds (492 shots for a 24-minute video): one at a time took about two hours; a setting of
    # story_workers in settings.json wins over this default (cores minus 2, at most 8)
    out["story_workers"] = int(getattr(app, "_settings", {}).get("story_workers") or max(1, min(8, (os.cpu_count() or 2) - 2)))
    # real image-to-video is OFF unless settings.json says story_ai_video_live: true (default: shots are only recorded and counted)
    for k in ("story_ai_video_live", "story_ai_video_max", "story_ai_video_live_max", "story_ai_video_start_image"):
        if k in getattr(app, "_settings", {}):
            out[k] = app._settings[k]
    if not o["links"]:
        out["story_shot_link_ratio"] = 0.0
        out["story_cuts_only"] = True
    return out


def _opts(app: Any) -> Dict[str, Any]:
    v = getattr(app, "_story_vars", None)
    if not v:
        return {"strength": "Normal", "parallax": True, "links": True, "audit": True}
    return {"strength": v["strength"].get(), "parallax": v["parallax"].get(), "links": v["links"].get(), "audit": v["audit"].get()}


def build(app: Any, parent: Any, *, row: int = 9) -> None:
    app._story_vars = {"strength": ctk.StringVar(value="Normal"), "parallax": ctk.BooleanVar(value=True), "links": ctk.BooleanVar(value=True),
                       "audit": ctk.BooleanVar(value=True)}
    app._story_status_var = ctk.StringVar(value="")
    block = ctk.CTkFrame(parent, fg_color=T.CARD, border_width=1, border_color=T.BORDER, corner_radius=8)
    block.grid(row=row, column=0, sticky="ew", pady=(12, 0))
    block.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(block, text="Story Motion", font=ctk.CTkFont(size=14, weight="bold"), text_color=T.TEXT, anchor="w").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))
    ctk.CTkLabel(block, text="Every row of your CSV is one picture. The app directs each shot from what the narration says: a camera move that fits it (push, track, tilt, reveal, "
                             "parallax), environment effects where they belong, and transitions that follow the story. Nothing starts until Generate; Check plan below only reads your CSV.",
                 font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=640).grid(row=1, column=0, sticky="w", padx=16, pady=(2, 8))
    tools = ctk.CTkFrame(block, fg_color="transparent")
    tools.grid(row=2, column=0, sticky="ew", padx=16)
    make_button(tools, "Check plan", lambda: on_check_plan(app), size="sm", width=120).grid(row=0, column=0, padx=(0, 12))
    ctk.CTkLabel(tools, textvariable=app._story_status_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(row=0, column=1, sticky="w")
    opts = ctk.CTkFrame(block, fg_color="transparent")
    opts.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 0))
    ctk.CTkLabel(opts, text="Motion", font=ctk.CTkFont(size=12), text_color=T.TEXT).grid(row=0, column=0, padx=(0, 8))
    ctk.CTkSegmentedButton(opts, values=list(STRENGTH), variable=app._story_vars["strength"]).grid(row=0, column=1, padx=(0, 18))
    ctk.CTkCheckBox(opts, text="Depth parallax", variable=app._story_vars["parallax"], font=ctk.CTkFont(size=12)).grid(row=0, column=2, padx=(0, 14))
    ctk.CTkCheckBox(opts, text="Soft transitions (off = hard cuts only)", variable=app._story_vars["links"], font=ctk.CTkFont(size=12)).grid(row=0, column=3, padx=(0, 14))
    ctk.CTkCheckBox(opts, text="Quality check after render", variable=app._story_vars["audit"], font=ctk.CTkFont(size=12)).grid(row=0, column=4)
    app._story_plan_box = ctk.CTkTextbox(block, height=170, font=ctk.CTkFont(family="Menlo", size=11), wrap="word")
    app._story_plan_box.grid(row=4, column=0, sticky="ew", padx=16, pady=(10, 14))
    app._story_plan_box.configure(state="disabled")
    app._story_block = block


def sync(app: Any, active: str) -> None:
    """Called from style_pages.sync: build the box the first time the card is shown, show it only on this style's page."""
    if active != STYLE or getattr(app, "_style_browsing", False):
        block = getattr(app, "_story_block", None)
        if block is not None:
            block.grid_remove()
        return
    if getattr(app, "_story_block", None) is None:
        content = getattr(getattr(app, "_view_visual_director", None), "content", None)
        if content is None:
            return
        build(app, content)
    app._story_block.grid()


def copy_prompt(app: Any) -> None:
    try:
        text = prompt_text()
        app.clipboard_clear()
        app.clipboard_append(text)
        app._story_status_var.set("Copied. Paste it into Gemini with your script, save the reply as a .csv, then load it above.")
    except Exception as exc:  # noqa: BLE001
        app._story_status_var.set(f"Could not copy the prompt ({exc}).")


def _show(app: Any, text: str) -> None:
    box = app._story_plan_box
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.configure(state="disabled")


def on_check_plan(app: Any) -> None:
    path = (app.csv_var.get() or "").strip() if hasattr(app, "csv_var") else ""
    if not path or not Path(path).is_file():
        _show(app, "Load your dense CSV first (the Plan step above: Import CSV, then Browse).")
        return
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except Exception as exc:  # noqa: BLE001
        _show(app, f"Could not read the CSV: {exc}")
        return
    words = None
    ws = getattr(app, "_workspace", None)
    try:
        import json
        wf = Path(ws.state_dir) / "narration_words.json" if ws is not None else None
        if wf is not None and wf.is_file():
            words = json.loads(wf.read_text(encoding="utf-8")).get("words")
    except Exception:
        words = None
    try:
        import story_check
        rep = story_check.check_csv(rows, words)
        app._story_status_var.set("Plan checked." if rep["ok"] else "Fix the errors below, then check again.")
        _show(app, rep["text"])
    except Exception as exc:  # noqa: BLE001
        _show(app, f"Check plan failed: {exc}")
