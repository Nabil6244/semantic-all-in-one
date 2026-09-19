"""Lightweight reusable CustomTkinter widgets for the production shell."""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from . import theme as T


class SectionHeader(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=T.TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        if subtitle:
            ctk.CTkLabel(
                self,
                text=subtitle,
                font=ctk.CTkFont(size=11),
                text_color=T.MUTED,
                anchor="w",
            ).grid(row=1, column=0, sticky="w", pady=(2, 0))


class StatusPill(ctk.CTkLabel):
    def __init__(self, master, text: str = "—", tone: str = "muted", **kwargs):
        color = {
            "ok": T.SUCCESS,
            "pass": T.SUCCESS,
            "warn": T.WARNING,
            "fail": T.DANGER,
            "run": T.PROCESSING,
            "muted": T.MUTED,
        }.get(tone.lower(), T.MUTED)
        super().__init__(
            master,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color,
            fg_color=T.CARD,
            corner_radius=T.RADIUS,
            padx=8,
            pady=2,
            **kwargs,
        )

    def set_tone(self, text: str, tone: str = "muted") -> None:
        color = {
            "ok": T.SUCCESS,
            "pass": T.SUCCESS,
            "warn": T.WARNING,
            "fail": T.DANGER,
            "run": T.PROCESSING,
            "muted": T.MUTED,
        }.get(tone.lower(), T.MUTED)
        self.configure(text=text, text_color=color)


class MetricRow(ctk.CTkFrame):
    def __init__(self, master, label: str, value: str = "—", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self, text=label, font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._value = ctk.CTkLabel(
            self, text=value, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=T.TEXT, anchor="e",
        )
        self._value.grid(row=0, column=1, sticky="e")

    def set_value(self, value: str) -> None:
        self._value.configure(text=value)


class EmptyState(ctk.CTkFrame):
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
        **kwargs,
    ):
        super().__init__(
            master, fg_color=T.CARD, corner_radius=T.RADIUS,
            border_width=1, border_color=T.BORDER, **kwargs,
        )
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=14, weight="bold"),
            text_color=T.TEXT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=T.PAD_LG, pady=(T.PAD_LG, 4))
        ctk.CTkLabel(
            self, text=body, font=ctk.CTkFont(size=12), text_color=T.MUTED,
            anchor="w", justify="left", wraplength=420,
        ).grid(row=1, column=0, sticky="w", padx=T.PAD_LG, pady=(0, T.PAD))
        if action_label and command:
            actions = ctk.CTkFrame(self, fg_color="transparent")
            actions.grid(row=2, column=0, sticky="w", padx=T.PAD_LG, pady=(0, T.PAD_LG))
            ctk.CTkButton(
                actions, text=action_label, height=32, width=160,
                fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
                font=ctk.CTkFont(size=12, weight="bold"), command=command,
            ).pack(side="left")
            if secondary_label and secondary_command:
                ctk.CTkButton(
                    actions, text=secondary_label, height=32, width=140,
                    fg_color="transparent", border_width=1, border_color=T.BORDER,
                    text_color=T.TEXT, hover_color=T.CARD_HOVER,
                    font=ctk.CTkFont(size=12), command=secondary_command,
                ).pack(side="left", padx=(T.SPACE_SM, 0))


class CollapsibleSection(ctk.CTkFrame):
    """A named, collapsible group of controls (Inspector sections, spec
    item 8) — expanded by default, remembers state only for its own
    lifetime (no new persistence layer)."""

    def __init__(self, master, title: str, *, expanded: bool = True, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._expanded = expanded

        from . import icons as I

        header = ctk.CTkButton(
            self, text=f"{I.icon('chevron_down' if expanded else 'chevron_right')}  {title}",
            height=T.CONTROL_H, anchor="w",
            fg_color="transparent", hover_color=T.CARD_HOVER,
            text_color=T.MUTED, font=ctk.CTkFont(size=T.FONT_SECTION_TITLE[0], weight="bold"),
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
    """Transient, auto-dismissing status feedback (spec item 20) — "Saved",
    "Clip duplicated", "Export started" etc. One instance is reused per
    host (see ToastHost) rather than stacking many, so quick successive
    actions never flood the screen."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master, fg_color=T.CARD, corner_radius=T.RADIUS,
            border_width=1, border_color=T.ACCENT_BORDER, **kwargs,
        )
        self._label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=T.FONT_STATUS[0], weight="bold"),
            text_color=T.TEXT,
        )
        self._label.pack(padx=T.SPACE_LG, pady=T.SPACE_SM)
        self._after_id = None

    def show(self, message: str, *, tone: str = "info", duration_ms: int = 2600) -> None:
        color = {
            "info": T.TEXT, "success": T.SUCCESS, "warning": T.WARNING, "error": T.DANGER,
        }.get(tone, T.TEXT)
        self._label.configure(text=message, text_color=color)
        try:
            self.place(relx=0.5, rely=1.0, anchor="s", y=-16)
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


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=T.CARD,
            corner_radius=T.RADIUS,
            border_width=1,
            border_color=T.BORDER,
            **kwargs,
        )
