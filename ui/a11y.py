"""Keyboard access for CustomTkinter buttons.

A CTkButton is drawn on a Tk canvas, and Tk's Tab traversal skips canvases
that have no key bindings, so no button in the app could be reached or pressed
from the keyboard, and nothing showed which control had focus.

install() makes every CTkButton built afterwards:
  * reachable with Tab / Shift+Tab (only while it is visible and enabled),
  * pressed with Space or Return (same as a click: the button's own command),
  * outlined with a focus ring (ACCENT_TEXT, readable in both themes) while focused.
Mouse behaviour and looks are unchanged when the button is not focused.
Text boxes: Tab / Shift+Tab move focus instead of typing a tab character.
"""

from __future__ import annotations

from . import theme as T

_INSTALLED = False
RING_WIDTH = T.FOCUS_RING_WIDTH


def _is_enabled(btn) -> bool:
    try:
        return str(btn.cget("state")) != "disabled"
    except Exception:
        return False


def enable_keyboard(btn) -> None:
    """Make one CTkButton focusable, Space/Return-activated and focus-ringed."""
    canvas = getattr(btn, "_canvas", None)
    if canvas is None or getattr(btn, "_sy_keyboard", False):
        return
    btn._sy_keyboard = True
    # A callable takefocus lets Tab skip disabled buttons (Tk asks it each time). When -takefocus is a script,
    # Tk's FocusOK trusts its answer and skips its own visibility test, so check viewable here too: otherwise
    # buttons on hidden pages joined the Tab order and Tab got stuck on them.
    def can_focus(*_a) -> int:
        try:
            return 1 if _is_enabled(btn) and canvas.winfo_viewable() else 0
        except Exception:
            return 0

    canvas.configure(takefocus=can_focus)

    def activate(_event=None):
        if _is_enabled(btn):
            btn.invoke()
        return "break"  # Space/Return on a focused button must not also reach window bindings

    for seq in ("<space>", "<Return>", "<KP_Enter>"):
        canvas.bind(seq, activate)

    def ring_on(_event=None):
        # Focus-visible: only keyboard focus shows the ring. On macOS a click also focuses the canvas.
        if getattr(btn, "_sy_ring", None) is not None or getattr(btn, "_sy_pointer", False):
            return
        try:
            btn._sy_ring = (btn.cget("border_width"), btn.cget("border_color"))
            btn.configure(border_width=max(RING_WIDTH, int(btn._sy_ring[0] or 0)), border_color=T.ACCENT_TEXT)
        except Exception:
            btn._sy_ring = None

    def ring_off(_event=None):
        saved = getattr(btn, "_sy_ring", None)
        if saved is None:
            return
        btn._sy_ring = None
        try:
            btn.configure(border_width=saved[0], border_color=saved[1])
        except Exception:
            pass

    def pointer_down(_event=None):
        btn._sy_pointer = True
        ring_off()

    def focus_out(_event=None):
        btn._sy_pointer = False
        ring_off()

    canvas.bind("<FocusIn>", ring_on, add="+")
    canvas.bind("<FocusOut>", focus_out, add="+")
    canvas.bind("<ButtonPress-1>", pointer_down, add="+")


def install() -> bool:
    """Patch CTkButton once so every button built afterwards gets keyboard access."""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from customtkinter import CTkButton
    except Exception:
        return False
    original_init = CTkButton.__init__

    def init_with_keyboard(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            enable_keyboard(self)
        except Exception:
            pass  # never let accessibility wiring break building a button

    init_with_keyboard._sy_original = original_init  # type: ignore[attr-defined]
    CTkButton.__init__ = init_with_keyboard
    _install_textbox_tab()
    _INSTALLED = True
    return True


def _focus_step(widget, forward: bool) -> str:
    target = widget.tk_focusNext() if forward else widget.tk_focusPrev()
    if target is not None:
        target.focus_set()
    return "break"


def _install_textbox_tab() -> None:
    """Tk's Text widget inserts a tab character on Tab, so keyboard focus could enter a text box (the
    script, CSV paste, prompt boxes) and never leave it. Tab characters mean nothing in those boxes:
    Tab / Shift+Tab now move focus like every other field. Pasted text is untouched."""
    from customtkinter import CTkTextbox

    original_init = CTkTextbox.__init__

    def init_with_tab_focus(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            inner = self._textbox
            inner.bind("<Tab>", lambda _e: _focus_step(inner, True))
            inner.bind("<Shift-Tab>", lambda _e: _focus_step(inner, False))
            inner.bind("<ISO_Left_Tab>", lambda _e: _focus_step(inner, False))  # Shift+Tab on X11
        except Exception:
            pass

    init_with_tab_focus._sy_original = original_init  # type: ignore[attr-defined]
    CTkTextbox.__init__ = init_with_tab_focus
