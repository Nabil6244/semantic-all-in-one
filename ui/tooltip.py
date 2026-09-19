"""Polished, consistent tooltips (Premium UI/UX pass, spec item 11).

Appears after a short delay, disappears on leave/click, never steals focus
(a plain `overrideredirect` Toplevel), consistent styling from ui/theme.py.
Attach with `Tooltip(widget, "Split", shortcut="Ctrl+B")`.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from . import theme as T

_DELAY_MS = 500


class Tooltip:
    def __init__(self, widget, text: str, *, shortcut: Optional[str] = None):
        self.widget = widget
        self.text = text
        self.shortcut = shortcut
        self._after_id: Optional[str] = None
        self._win: Optional[ctk.CTkToplevel] = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def set_text(self, text: str, *, shortcut: Optional[str] = None) -> None:
        self.text = text
        self.shortcut = shortcut

    def _on_enter(self, _event=None) -> None:
        self._cancel_pending()
        self._after_id = self.widget.after(_DELAY_MS, self._show)

    def _on_leave(self, _event=None) -> None:
        self._cancel_pending()
        self._hide()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._win is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        try:
            win = ctk.CTkToplevel(self.widget)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            try:
                win.attributes("-alpha", 0.97)
            except Exception:
                pass
            frame = ctk.CTkFrame(
                win, fg_color=T.CARD, corner_radius=T.RADIUS,
                border_width=1, border_color=T.BORDER,
            )
            frame.pack()
            label_text = self.text
            ctk.CTkLabel(
                frame, text=label_text, font=ctk.CTkFont(size=T.FONT_SECONDARY_LABEL[0]),
                text_color=T.TEXT, anchor="w",
            ).pack(padx=8, pady=(6, 0 if self.shortcut else 6), anchor="w")
            if self.shortcut:
                ctk.CTkLabel(
                    frame, text=self.shortcut, font=ctk.CTkFont(size=T.FONT_METADATA[0]),
                    text_color=T.MUTED, anchor="w",
                ).pack(padx=8, pady=(0, 6), anchor="w")
            win.geometry(f"+{x}+{y}")
            self._win = win
        except Exception:
            self._win = None

    def _hide(self) -> None:
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


def attach(widget, text: str, *, shortcut: Optional[str] = None) -> Tooltip:
    """Convenience wrapper — keeps a reference on the widget itself so the
    Tooltip isn't garbage-collected while the widget is still alive."""
    tip = Tooltip(widget, text, shortcut=shortcut)
    widget._tooltip = tip  # noqa: SLF001 - intentional, simplest lifetime anchor
    return tip
