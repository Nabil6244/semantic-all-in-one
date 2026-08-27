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
            ctk.CTkButton(
                self, text=action_label, height=32, width=160,
                fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
                font=ctk.CTkFont(size=12, weight="bold"), command=command,
            ).grid(row=2, column=0, sticky="w", padx=T.PAD_LG, pady=(0, T.PAD_LG))


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
