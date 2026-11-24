"""The style page's right-hand column (from the Lovable mockup, 2026-11-24): where the video stands in three steps, the app's
progress and status, the last lines of the log and the finished video. Read-only: it shows app state and never starts work.
Shown only on a style page (not the style picker) and only when the window is wide enough for two columns."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import customtkinter as ctk

from . import theme as T
from .widgets import make_button

WIDTH = 340
MIN_VIEW_W = 1180    # narrower than this, the page stays one column (its own Render step still shows progress)
_POLL_MS = 1000
_LOG_LINES = 12
STEPS = ("Inputs", "Generate scenes", "Render")


def _file(value: Any) -> bool:
    try:
        raw = str(value or "").strip()
        return bool(raw) and Path(raw).is_file()
    except Exception:
        return False


def step_index(app: Any) -> int:
    """0 = inputs still needed, 1 = ready to generate scenes, 2 = scenes made / ready to render, 3 = rendered."""
    rows = getattr(app, "_scene_rows", None) or []
    try:
        has_input = _file(app.audio_var.get()) or bool(app.script_box.get("1.0", "end-1c").strip()) or bool(rows)
    except Exception:
        has_input = bool(rows)
    if _file(getattr(app, "_last_output", "")) and rows:
        return 3
    if rows:
        return 2
    return 1 if has_input else 0


def _card(parent: Any, row: int, title: str) -> ctk.CTkFrame:
    box = ctk.CTkFrame(parent, fg_color=T.CARD, corner_radius=T.RADIUS_LG, border_width=1, border_color=T.BORDER)
    box.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    box.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=T.TEXT, anchor="w").grid(
        row=0, column=0, sticky="w", padx=16, pady=(14, 8))
    body = ctk.CTkFrame(box, fg_color="transparent")
    body.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
    body.grid_columnconfigure(0, weight=1)
    return body


class StyleSidePanel(ctk.CTkFrame):
    def __init__(self, master: Any, app: Any, **kwargs: Any):
        super().__init__(master, fg_color="transparent", width=WIDTH, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self._sig: dict = {}

        steps = _card(self, 0, "Steps")
        self._step_badges: List[ctk.CTkLabel] = []
        self._step_labels: List[ctk.CTkLabel] = []
        for i, name in enumerate(STEPS):
            badge = ctk.CTkLabel(steps, text=str(i + 1), width=26, height=26, corner_radius=13, fg_color=T.CARD_HOVER,
                                 text_color=T.MUTED, font=ctk.CTkFont(size=12, weight="bold"))
            badge.grid(row=i, column=0, sticky="w", pady=3)
            lab = ctk.CTkLabel(steps, text=name, font=ctk.CTkFont(size=13), text_color=T.MUTED, anchor="w")
            lab.grid(row=i, column=1, sticky="w", padx=(10, 0))
            self._step_badges.append(badge)
            self._step_labels.append(lab)
        steps.grid_columnconfigure(1, weight=1)

        prog = _card(self, 1, "Progress")
        ctk.CTkLabel(prog, text="CURRENT STEP", font=ctk.CTkFont(size=11, weight="bold"), text_color=T.TEXT_TERTIARY,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self._status = ctk.CTkLabel(prog, text="Ready", font=ctk.CTkFont(size=13, weight="bold"), text_color=T.TEXT,
                                    anchor="w", justify="left", wraplength=WIDTH - 40)
        self._status.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._bar = ctk.CTkProgressBar(prog, height=6, corner_radius=3, fg_color=T.CARD_HOVER, progress_color=T.ACCENT,
                                       border_width=0)
        self._bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self._bar.set(0)
        self._pct = ctk.CTkLabel(prog, text="", font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w")
        self._pct.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self._log = ctk.CTkTextbox(prog, height=190, wrap="none", fg_color=T.BG, border_width=1, border_color=T.BORDER,
                                   corner_radius=T.RADIUS, text_color=T.MUTED,
                                   font=ctk.CTkFont(family="Menlo", size=11))
        self._log.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._log.configure(state="disabled")

        out = _card(self, 2, "Output")
        self._thumb = ctk.CTkLabel(out, text="▶", height=150, corner_radius=T.RADIUS, fg_color=T.CARD_HOVER,
                                   text_color=T.TEXT_TERTIARY, font=ctk.CTkFont(size=28), cursor="hand2")
        self._thumb.grid(row=0, column=0, sticky="ew")
        self._thumb.bind("<Button-1>", lambda _e: self._open())
        self._out_name = ctk.CTkLabel(out, text="No video yet", font=ctk.CTkFont(family="Menlo", size=11),
                                      text_color=T.MUTED, anchor="w")
        self._out_name.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        make_button(out, "⌂  Open folder", self._open, size="sm").grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.after(200, self._tick)

    def _open(self) -> None:
        fn = getattr(self.app, "_open_output_folder", None)
        if callable(fn):
            fn()

    def _changed(self, key: str, value: Any) -> bool:
        if self._sig.get(key) == value:
            return False
        self._sig[key] = value
        return True

    def refresh(self) -> None:
        app = self.app
        idx = step_index(app)
        if self._changed("step", idx):
            for i, (badge, lab) in enumerate(zip(self._step_badges, self._step_labels)):
                if i < idx:
                    badge.configure(text="✓", fg_color=T.SUCCESS_BG, text_color=T.SUCCESS)
                    lab.configure(text_color=T.TEXT, font=ctk.CTkFont(size=13))
                elif i == idx:
                    badge.configure(text=str(i + 1), fg_color=T.ACCENT, text_color=T.ACCENT_DARK)
                    lab.configure(text_color=T.TEXT, font=ctk.CTkFont(size=13, weight="bold"))
                else:
                    badge.configure(text=str(i + 1), fg_color=T.CARD_HOVER, text_color=T.MUTED)
                    lab.configure(text_color=T.MUTED, font=ctk.CTkFont(size=13))
        try:
            status = str(app.status_var.get())
        except Exception:
            status = ""
        if self._changed("status", status):
            self._status.configure(text=status or "Ready")
        try:
            value = float(app.progress.get())
        except Exception:
            value = 0.0
        if self._changed("pct", round(value, 3)):
            self._bar.set(value)
            self._pct.configure(text=f"{value * 100:.0f}%" if value > 0 else "Nothing running")
        box = getattr(app, "log_box", None)
        if box is not None:
            try:
                tail = box.get(f"end-{_LOG_LINES + 1}l", "end-1c")
            except Exception:
                tail = ""
            if self._changed("log", tail):
                self._log.configure(state="normal")
                self._log.delete("1.0", "end")
                self._log.insert("1.0", tail)
                self._log.see("end")
                self._log.configure(state="disabled")
        out = str(getattr(app, "_last_output", "") or "")
        if self._changed("out", (out, _file(out))):     # the file can appear or vanish under the same path
            self._out_name.configure(text=Path(out).name if out else "No video yet")
            self._thumb.configure(text_color=T.ACCENT_TEXT if _file(out) else T.TEXT_TERTIARY)

    def _tick(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return  # the panel is gone
        try:
            if self.winfo_ismapped():
                self.refresh()
        except Exception:
            pass   # one failed refresh must not stop the next ones
        self.after(_POLL_MS, self._tick)


def wanted(app: Any, view_width: int) -> bool:
    """Two columns only on a style page (not while browsing the picker) and only on a wide window."""
    return view_width >= MIN_VIEW_W and not getattr(app, "_style_browsing", True)
