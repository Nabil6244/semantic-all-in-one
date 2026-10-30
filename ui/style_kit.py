"""The pieces every style page is built from, so a video is made start to finish on the style's own page: numbered sections and the
Script and Render panels. The panels are new widgets on the same state the other pages use (app.script_box, the scene rows,
the main progress bar and status): a script typed here is the Script page's script, and the reverse. Nothing here renders anything."""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from . import theme as T
from .widgets import make_button

_POLL_MS = 700


def section(parent: Any, row: int, number: int, title: str, hint: str = "") -> ctk.CTkFrame:
    """A numbered step ("2  Script") with an optional one-line hint; returns the body frame to put the step's controls in."""
    box = ctk.CTkFrame(parent, fg_color=T.CARD, corner_radius=10, border_width=1, border_color=T.BORDER)
    box.grid(row=row, column=0, sticky="ew", pady=(0, 10))
    box.grid_columnconfigure(0, weight=1)
    head = ctk.CTkFrame(box, fg_color="transparent")
    head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
    ctk.CTkLabel(head, text=str(number), width=24, height=24, corner_radius=12, fg_color=T.ACCENT, text_color=T.ACCENT_DARK,
                 font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
    ctk.CTkLabel(head, text=title, font=ctk.CTkFont(size=14, weight="bold"), text_color=T.TEXT).pack(side="left", padx=(8, 0))
    if hint:
        ctk.CTkLabel(head, text=hint, font=ctk.CTkFont(size=11), text_color=T.MUTED).pack(side="left", padx=(12, 0))
    body = ctk.CTkFrame(box, fg_color="transparent")
    body.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 12))
    body.grid_columnconfigure(0, weight=1)
    return body


def _every(widget: Any, fn: Callable[[], None]) -> None:
    """Run fn now and every _POLL_MS while the widget exists (it skips the work while the widget is not on screen)."""
    def tick():
        try:
            if not widget.winfo_exists():
                return
        except Exception:
            return
        try:
            if widget.winfo_ismapped():
                fn()
        except Exception:
            pass   # one failed refresh must not stop the next ones
        widget.after(_POLL_MS, tick)
    tick()


# ---- Script: the Script page's text, edited here ---------------------------------------------------------------------------------

def script_panel(app: Any, parent: Any, *, row: int = 0, height: int = 150) -> ctk.CTkTextbox:
    box = ctk.CTkTextbox(parent, height=height, font=ctk.CTkFont(size=12), wrap="word")
    box.grid(row=row, column=0, sticky="ew")
    src = getattr(app, "script_box", None)
    state = {"last": None}

    def text_of(tb) -> str:
        return tb.get("1.0", "end-1c")

    def pull():   # the Script page changed it (or a project opened): show that here unless this box is being typed in
        if src is None or box.focus_get() is box._textbox:
            return
        t = text_of(src)
        if t != state["last"] and t != text_of(box):
            box.delete("1.0", "end")
            box.insert("1.0", t)
        state["last"] = t

    def push(_e=None):
        if src is None:
            return
        t = text_of(box)
        if t != text_of(src):
            src.delete("1.0", "end")
            src.insert("1.0", t)
            src.event_generate("<<Modified>>")
        state["last"] = t

    pending = {"id": None}

    def push_soon(_e=None):   # typing: copy once the typing pauses, not on every key (a long script is rewritten each time)
        if pending["id"] is not None:
            box.after_cancel(pending["id"])
        pending["id"] = box.after(400, lambda: (pending.update(id=None), push()))

    box._kit_push = push   # what pasting / leaving the box / a typing pause runs (tests call it directly)
    box.bind("<KeyRelease>", push_soon, add="+")
    box.bind("<<Paste>>", lambda e: box.after(10, push), add="+")
    box.bind("<FocusOut>", push, add="+")
    _every(box, pull)
    return box


# ---- Render: the style's own Generate button, with the app's progress and the finished video right under it --------------------------

def render_panel(app: Any, parent: Any, *, row: int = 0) -> None:
    bar = ctk.CTkProgressBar(parent, height=8, progress_color=T.ACCENT)
    bar.grid(row=row, column=0, sticky="ew", pady=(10, 0))
    bar.set(0)
    low = ctk.CTkFrame(parent, fg_color="transparent")
    low.grid(row=row + 1, column=0, sticky="ew", pady=(6, 0))
    low.grid_columnconfigure(0, weight=1)
    status = ctk.CTkLabel(low, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=560)
    status.grid(row=0, column=0, sticky="w")
    make_button(low, "Open video", app._open_output_folder, size="sm", width=110).grid(row=0, column=1, sticky="e")

    def refresh():
        try:
            bar.set(float(app.progress.get()))
        except Exception:
            pass
        try:
            status.configure(text=str(app.status_var.get()))
        except Exception:
            pass

    _every(bar, refresh)


# ---- every other style: its own controls (the Plan step) wrapped in the steps it does not already have ------------------------------
# What If builds the steps itself (whatif/app_section.py). The rest keep their cards untouched: the page puts Voiceover / Script (and
# for Normal video and its looks, the Plan) above the style's card and Render below it, each only where the card lacks it.

_NORMAL = ("Normal video", "Story Motion", "Modern Tech News", "Enoch Template")
_OWN_VOICEOVER = ("War Documentary", "Health Cinema", "Rep Theory", "Weather", "What If")
_NO_SCRIPT = ("Overscaled", "Exp Solar", "War Documentary", "Health Cinema", "Rep Theory", "What If")
_OWN_RENDER_BUTTON = ("War Documentary", "Health Cinema", "Rep Theory", "What If")
_BLOCKS = {"Overscaled": "_overscaled_block", "Exp Solar": "_overscaled_block", "pakMap": "_pakmap_block", "Hybrid Map": "_hybrid_block",
           "Explainer": "_hybrid_block", "StarMap": "_starmap_block", "StarMap Cinema": "_starmap_block", "Weather": "_weather_block",
           "War Documentary": "_war_block", "Health Cinema": "_health_block", "Rep Theory": "_rt_block", "Story Motion": "_story_block"}
_TOP_ROW, _BLOCK_ROW, _BOTTOM_ROW = 20, 21, 22


def _normal_plan(app: Any, body: Any) -> None:
    modes = ["Paste script", "Import CSV", "VO-Aware plan"]
    seg = ctk.CTkSegmentedButton(body, values=modes, height=30, font=ctk.CTkFont(size=12),
                                 command=lambda v: (app._mode_seg.set(v), app._on_script_mode(v)))
    seg.grid(row=0, column=0, sticky="w")
    app._path_row(1, "Visual plan CSV", app.csv_var, app._browse_csv, parent=body, placeholder_text="Only for Import CSV: choose a visual-plan CSV")
    status = ctk.StringVar(value="")
    row = ctk.CTkFrame(body, fg_color="transparent")
    row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
    make_button(row, "Copy the CSV prompt", lambda: app._copy_csv_prompt("normal", status), size="sm", width=150).grid(row=0, column=0, padx=(0, 10))
    ctk.CTkLabel(row, textvariable=status, font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(row=0, column=1, sticky="w")
    _every(seg, lambda: seg.get() != app._mode_seg.get() and seg.set(app._mode_seg.get()))


def _generate_button(app: Any, body: Any) -> None:
    """The app's main button (Import voiceover / Generate scenes / Render / Stop: whatever comes next), here on the page."""
    btn = ctk.CTkButton(body, text="Generate", width=200, height=40, corner_radius=6, fg_color=T.ACCENT, text_color=T.ACCENT_DARK,
                        font=ctk.CTkFont(size=13, weight="bold"), command=app._on_primary_cta)
    btn.grid(row=0, column=0, sticky="w")

    def follow():
        try:
            text, state = app.generate_btn.cget("text"), app.generate_btn.cget("state")
            if btn.cget("text") != text or btn.cget("state") != state:
                btn.configure(text=text or "Generate", state=state)
        except Exception:
            pass

    _every(btn, follow)


def _build_wrap(app: Any, parent: Any, style: str):
    top = ctk.CTkFrame(parent, fg_color="transparent")
    top.grid_columnconfigure(0, weight=1)
    bottom = ctk.CTkFrame(parent, fg_color="transparent")
    bottom.grid_columnconfigure(0, weight=1)
    n, r = 0, 0
    if style not in _OWN_VOICEOVER:
        n += 1
        app._path_row(0, "", app.audio_var, lambda: app._browse_audio(stay=True), parent=section(top, r, n, "Voiceover", "the narration the video is cut to"),
                      placeholder_text="None yet: Browse to choose your voiceover")
        r += 1
    if style not in _NO_SCRIPT:
        n += 1
        script_panel(app, section(top, r, n, "Script", "the words of your voiceover (the same script as the Script page)"))
        r += 1
    if style in _NORMAL:
        n += 1
        _normal_plan(app, section(top, r, n, "Plan", "how the scenes are made"))
        r += 1
    else:   # the style's own card below is this step
        n += 1
        plan = ctk.CTkFrame(top, fg_color="transparent")
        plan.grid(row=r, column=0, sticky="ew")
        ctk.CTkLabel(plan, text=f"{n}  Plan, look and options: {style}", font=ctk.CTkFont(size=14, weight="bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=2, pady=(2, 6))
    n += 1
    go = section(bottom, 0, n, "Render")
    if style not in _OWN_RENDER_BUTTON:
        _generate_button(app, go)
    render_panel(app, go, row=1)
    return top, bottom


def wrap_style(app: Any, active: str) -> None:
    """Show the active style's steps around its card (built the first time the style is shown); hide every other style's."""
    content = getattr(getattr(app, "_view_visual_director", None), "content", None)
    if content is None:
        return
    wraps = app.__dict__.setdefault("_style_wraps", {})
    browsing = getattr(app, "_style_browsing", False)
    want = None if (browsing or active in ("What If", "Product Trailer")) else active   # both build their own steps
    for name, (top, bottom) in wraps.items():
        if name != want:
            top.grid_remove()
            bottom.grid_remove()
    if want is None:
        return
    if want not in wraps:
        wraps[want] = _build_wrap(app, content, want)
    top, bottom = wraps[want]
    top.grid(row=_TOP_ROW, column=0, sticky="ew", pady=(0, 2))
    block = getattr(app, _BLOCKS.get(want, ""), None)
    if block is not None and block.winfo_manager() == "grid":
        block.grid_configure(row=_BLOCK_ROW)
    bottom.grid(row=_BOTTOM_ROW, column=0, sticky="ew", pady=(10, 0))
