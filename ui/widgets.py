"""Reusable CustomTkinter building blocks for the production shell.

Every page is assembled from these, so buttons, cards, pills and empty
states look and behave the same everywhere. Colours always come from
ui.theme tokens (never literals), which is what lets a live dark/light
switch repaint them.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from . import theme as T


def font(spec, **overrides) -> ctk.CTkFont:
    size, weight = spec
    return ctk.CTkFont(size=overrides.get("size", size), weight=overrides.get("weight", weight))


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

_BUTTON_HEIGHT = {"sm": T.CONTROL_H_SM, "md": T.CONTROL_H, "lg": T.CONTROL_H_LG}
_BUTTON_FONT = {"sm": 11, "md": 12, "lg": 13}


def button_style(variant: str = "secondary", size: str = "md") -> dict:
    """CTkButton kwargs for one of the four button roles:

    primary   — the one main action of a page (filled accent)
    secondary — ordinary actions (outlined)
    ghost     — low-emphasis/toolbar actions (no border)
    danger    — destructive actions (outlined red)
    """
    base = dict(
        height=_BUTTON_HEIGHT.get(size, T.CONTROL_H),
        corner_radius=T.RADIUS,
        font=ctk.CTkFont(size=_BUTTON_FONT.get(size, 12), weight="bold" if variant == "primary" else "normal"),
        text_color_disabled=T.TEXT_TERTIARY,
    )
    if variant == "primary":
        base.update(fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK, border_width=0)
    elif variant == "ghost":
        base.update(fg_color="transparent", hover_color=T.CARD_HOVER, text_color=T.MUTED, border_width=0)
    elif variant == "danger":
        base.update(fg_color="transparent", hover_color=T.DANGER_BG, text_color=T.DANGER,
                    border_width=1, border_color=T.DANGER)
    else:
        base.update(fg_color=T.CARD, hover_color=T.CARD_HOVER, text_color=T.TEXT,
                    border_width=1, border_color=T.BORDER_STRONG)
    return base


def make_button(master, text: str, command: Optional[Callable] = None, *, variant: str = "secondary",
                size: str = "md", **kwargs) -> ctk.CTkButton:
    style = button_style(variant, size)
    style.update(kwargs)
    return ctk.CTkButton(master, text=text, command=command, **style)


# ---------------------------------------------------------------------------
# Headings, text, dividers
# ---------------------------------------------------------------------------


class SectionHeader(ctk.CTkFrame):
    """Page heading: large title, one-line description, optional actions on
    the right (``header.actions`` is a frame to pack buttons into)."""

    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._title = ctk.CTkLabel(
            self, text=title, font=font(T.FONT_PAGE_TITLE), text_color=T.TEXT, anchor="w",
        )
        self._title.grid(row=0, column=0, sticky="w")
        self._subtitle = None
        if subtitle:
            self._subtitle = ctk.CTkLabel(
                self, text=subtitle, font=font(T.FONT_BODY), text_color=T.MUTED,
                anchor="w", justify="left", wraplength=720,
            )
            self._subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.actions = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        self.actions.grid(row=0, column=1, rowspan=2, sticky="e")

    def set_title(self, title: str) -> None:
        self._title.configure(text=title)


class SectionLabel(ctk.CTkLabel):
    """Small uppercase caption that names a group of controls."""

    def __init__(self, master, text: str, **kwargs):
        kwargs.setdefault("text_color", T.TEXT_TERTIARY)
        super().__init__(master, text=text.upper(), font=font(T.FONT_SECTION_TITLE), anchor="w", **kwargs)


class Divider(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=T.BORDER, height=1, corner_radius=0, **kwargs)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def _tone_colors(tone: str):
    tone = (tone or "muted").lower()
    return {
        "ok": (T.SUCCESS, T.SUCCESS_BG),
        "pass": (T.SUCCESS, T.SUCCESS_BG),
        "success": (T.SUCCESS, T.SUCCESS_BG),
        "warn": (T.WARNING, T.WARNING_BG),
        "warning": (T.WARNING, T.WARNING_BG),
        "fail": (T.DANGER, T.DANGER_BG),
        "error": (T.DANGER, T.DANGER_BG),
        "run": (T.PROCESSING, T.ACCENT_SEL),
        "info": (T.ACCENT, T.ACCENT_SEL),
        "muted": (T.MUTED, T.CARD_HOVER),
    }.get(tone, (T.MUTED, T.CARD_HOVER))


class StatusPill(ctk.CTkLabel):
    """Rounded, tinted status badge (PASS / WARN / RUNNING / IDLE ...)."""

    def __init__(self, master, text: str = "—", tone: str = "muted", **kwargs):
        fg, bg = _tone_colors(tone)
        kwargs.setdefault("height", 22)
        super().__init__(
            master, text=text, font=ctk.CTkFont(size=11, weight="bold"),
            text_color=fg, fg_color=bg, corner_radius=11, padx=10, pady=0, **kwargs,
        )

    def set_tone(self, text: str, tone: str = "muted") -> None:
        fg, bg = _tone_colors(tone)
        self.configure(text=text, text_color=fg, fg_color=bg)


class MetricRow(ctk.CTkFrame):
    """Label/value pair for a details list. Values stay next to their
    labels (fixed label column), not pushed to the far edge of the card."""

    LABEL_W = 168

    def __init__(self, master, label: str, value: str = "—", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self, text=label, font=font(T.FONT_CONTROL_LABEL), text_color=T.MUTED,
            anchor="w", width=self.LABEL_W,
        ).grid(row=0, column=0, sticky="w")
        self._value = ctk.CTkLabel(
            self, text=value, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=T.TEXT, anchor="w", justify="left",
        )
        self._value.grid(row=0, column=1, sticky="w")

    def set_value(self, value: str) -> None:
        self._value.configure(text=value)


class StatTile(ctk.CTkFrame):
    """Dashboard tile: a big number/word with a caption and an optional
    tone dot, used on Overview/Export/QA."""

    def __init__(self, master, caption: str, value: str = "—", **kwargs):
        super().__init__(master, fg_color=T.CARD, corner_radius=T.RADIUS_LG,
                         border_width=1, border_color=T.BORDER, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._caption = ctk.CTkLabel(self, text=caption.upper(), font=font(T.FONT_SECTION_TITLE),
                                     text_color=T.TEXT_TERTIARY, anchor="w")
        self._caption.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))
        self._value = ctk.CTkLabel(self, text=value, font=ctk.CTkFont(size=20, weight="bold"),
                                   text_color=T.TEXT, anchor="w")
        self._value.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 2))
        self._detail = ctk.CTkLabel(self, text="", font=font(T.FONT_METADATA), text_color=T.MUTED,
                                    anchor="w", justify="left")
        self._detail.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 12))

    def set(self, value: str, detail: str = "", tone: str = "") -> None:
        color = _tone_colors(tone)[0] if tone else T.TEXT
        self._value.configure(text=value, text_color=color)
        self._detail.configure(text=detail)


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


class Card(ctk.CTkFrame):
    """Surface for one group of content. With ``title`` it gets a header
    row; put content in ``card.body`` (or directly in the card when no
    title is given, as legacy call sites do)."""

    def __init__(self, master, title: str = "", subtitle: str = "", **kwargs):
        super().__init__(
            master, fg_color=T.CARD, corner_radius=T.RADIUS_LG,
            border_width=1, border_color=T.BORDER, **kwargs,
        )
        self.body = self
        if title:
            self.grid_columnconfigure(0, weight=1)
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
            head.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(head, text=title, font=font(T.FONT_CARD_TITLE), text_color=T.TEXT,
                         anchor="w").grid(row=0, column=0, sticky="w")
            if subtitle:
                ctk.CTkLabel(head, text=subtitle, font=font(T.FONT_SECONDARY_LABEL), text_color=T.MUTED,
                             anchor="w", justify="left", wraplength=640).grid(row=1, column=0, sticky="w",
                                                                              pady=(2, 0))
            self.header_actions = ctk.CTkFrame(head, fg_color="transparent", width=1, height=1)
            self.header_actions.grid(row=0, column=1, rowspan=2, sticky="e")
            self.body = ctk.CTkFrame(self, fg_color="transparent")
            self.body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(10, 14))
            self.body.grid_columnconfigure(0, weight=1)


class EmptyState(ctk.CTkFrame):
    """Friendly placeholder for a page/section with nothing to show yet:
    icon, title, one sentence of guidance and the action that fixes it."""

    def __init__(
        self,
        master,
        title: str,
        body: str,
        action_label: str = "",
        command: Optional[Callable[[], None]] = None,
        *,
        secondary_label: str = "",
        secondary_command: Optional[Callable[[], None]] = None,
        icon: str = "◌",
        **kwargs,
    ):
        super().__init__(
            master, fg_color=T.CARD, corner_radius=T.RADIUS_LG,
            border_width=1, border_color=T.BORDER, **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text=icon, width=48, height=48, corner_radius=24, fg_color=T.ACCENT_SEL,
            text_color=T.ACCENT, font=ctk.CTkFont(size=20),
        ).grid(row=0, column=0, pady=(28, 10))
        self._title = ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color=T.TEXT,
        )
        self._title.grid(row=1, column=0, padx=T.PAD_LG)
        self._body = ctk.CTkLabel(
            self, text=body, font=font(T.FONT_BODY), text_color=T.MUTED,
            justify="center", wraplength=460,
        )
        self._body.grid(row=2, column=0, padx=T.PAD_LG, pady=(4, 0))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, pady=(16, 28))
        if action_label and command:
            make_button(actions, action_label, command, variant="primary", width=150).pack(side="left")
            if secondary_label and secondary_command:
                make_button(actions, secondary_label, secondary_command, width=140).pack(
                    side="left", padx=(T.SPACE_SM, 0))

    def set_text(self, title: Optional[str] = None, body: Optional[str] = None) -> None:
        if title is not None:
            self._title.configure(text=title)
        if body is not None:
            self._body.configure(text=body)


class CollapsibleSection(ctk.CTkFrame):
    """A named, collapsible group of controls — expanded by default,
    remembers its state only for its own lifetime."""

    def __init__(self, master, title: str, *, expanded: bool = True, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._expanded = expanded

        from . import icons as I

        header = ctk.CTkButton(
            self, text=f"{I.icon('chevron_down' if expanded else 'chevron_right')}  {title}",
            height=T.CONTROL_H, anchor="w", corner_radius=T.RADIUS,
            fg_color="transparent", hover_color=T.CARD_HOVER,
            text_color=T.MUTED, font=font(T.FONT_SECTION_TITLE),
            command=self._toggle,
        )
        header.grid(row=0, column=0, sticky="ew")
        self._header = header
        self._title = title

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="ew", padx=(T.SPACE_MD, 0))
        self.body.grid_columnconfigure(0, weight=1)
        if not expanded:
            self.body.grid_remove()

    def _toggle(self) -> None:
        from . import icons as I

        self._expanded = not self._expanded
        if self._expanded:
            self.body.grid()
        else:
            self.body.grid_remove()
        glyph = I.icon("chevron_down" if self._expanded else "chevron_right")
        self._header.configure(text=f"{glyph}  {self._title}")

    @property
    def expanded(self) -> bool:
        return self._expanded


class Toast(ctk.CTkFrame):
    """Transient, auto-dismissing feedback ("Saved", "Export started").
    One instance per host is reused, so quick successive actions never
    stack up notifications."""

    _GLYPH = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✕"}

    def __init__(self, master, **kwargs):
        super().__init__(
            master, fg_color=T.CARD, corner_radius=T.RADIUS_LG,
            border_width=1, border_color=T.BORDER_STRONG, **kwargs,
        )
        self._icon = ctk.CTkLabel(self, text="", width=22, height=22, corner_radius=11,
                                  font=ctk.CTkFont(size=12, weight="bold"))
        self._icon.pack(side="left", padx=(12, 8), pady=10)
        self._label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT,
        )
        self._label.pack(side="left", padx=(0, 16), pady=10)
        self._after_id = None

    def show(self, message: str, *, tone: str = "info", duration_ms: int = 2600) -> None:
        fg, bg = _tone_colors(tone)
        self._icon.configure(text=self._GLYPH.get(tone, self._GLYPH["info"]), text_color=fg, fg_color=bg)
        self._label.configure(text=message, text_color=T.TEXT)
        try:
            self.place(relx=0.5, rely=1.0, anchor="s", y=-20)
            self.lift()
        except Exception:
            pass
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.after(duration_ms, self._hide)

    def _hide(self) -> None:
        self._after_id = None
        try:
            self.place_forget()
        except Exception:
            pass


def switch_style() -> dict:
    """CTkSwitch look: accent track when on, grey when off, always-white knob.

    Colours are (light, dark) pairs, not single hexes: CustomTkinter flips
    pairs itself on an appearance change, and the live re-theme leaves them
    alone. A plain "#FFFFFF" knob was remapped to the dark *card* colour on a
    light -> dark switch (white is also the light card colour), which made
    the knob vanish and the track look cut off."""
    def pair(token: str) -> tuple:
        return (T.LIGHT[token], T.DARK[token])

    return dict(
        switch_width=40, switch_height=22,
        progress_color=pair("accent"), fg_color=pair("border_strong"),
        button_color=("#FFFFFF", "#FFFFFF"), button_hover_color=("#F2F3F7", "#F2F3F7"),
    )


def segmented_style() -> dict:
    """CTkSegmentedButton colours matching the rest of the controls."""
    return dict(
        fg_color=T.PANEL_ALT, selected_color=T.ACCENT, selected_hover_color=T.ACCENT_HOV,
        unselected_color=T.CARD, unselected_hover_color=T.CARD_HOVER,
        text_color=T.TEXT, text_color_disabled=T.TEXT_TERTIARY, corner_radius=T.RADIUS,
    )
