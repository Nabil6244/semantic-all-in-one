"""First-login About & Ownership acknowledgement modal (matches app theme).

Onboarding-style, deliberately not styled as a warning: heading, short intro,
scrollable agreement, personalised acknowledgement, checkbox, Continue.
Continue stays disabled until the checkbox is ticked, and the dialog only
closes once Supabase confirms the write.
"""
from __future__ import annotations

import textwrap
import threading
from typing import Callable, Optional

import customtkinter as ctk

from ui import theme as _ui_theme

from . import terms as _terms
from .auth_client import AuthError, AuthSession

_BG = _ui_theme.BG
_CARD = _ui_theme.CARD
_BORDER = _ui_theme.BORDER
_TEXT = _ui_theme.TEXT
_MUTED = _ui_theme.MUTED
_ACCENT = _ui_theme.ACCENT
_ACCENT_HOV = _ui_theme.ACCENT_HOV
_ACCENT_DARK = _ui_theme.ACCENT_DARK
_DANGER = _ui_theme.DANGER


class TermsDialog(ctk.CTkToplevel):
    """Modal acknowledgement. ``on_accept()`` only after the write succeeds."""

    def __init__(
        self,
        master,
        *,
        session: AuthSession,
        on_accept: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        save_fn: Optional[Callable[[AuthSession], None]] = None,
    ):
        super().__init__(master)
        self._session = session
        self._on_accept = on_accept
        self._on_cancel = on_cancel
        # Injectable so tests never touch the network.
        self._save = save_fn or _terms.save_acknowledgement
        self._busy = False
        self._closed = False

        self.title(_terms.TITLE)
        self.geometry("760x720")
        self.minsize(640, 560)
        self.configure(fg_color=_BG)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        name = getattr(session, "display_name", "") or ""

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=_ui_theme.PAD_LG, pady=(_ui_theme.PAD_LG, 0))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text=_terms.welcome_heading(name), text_color=_TEXT,
            font=ctk.CTkFont(size=22, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head, text=_terms.INTRO, text_color=_MUTED,
            font=ctk.CTkFont(size=12), anchor="w", justify="left", wraplength=680,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        body = ctk.CTkScrollableFrame(self, fg_color=_CARD, border_color=_BORDER, border_width=1)
        body.grid(row=2, column=0, sticky="nsew", padx=_ui_theme.PAD_LG, pady=_ui_theme.PAD)
        body.grid_columnconfigure(0, weight=1)
        self._fill_agreement(body, name)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=_ui_theme.PAD_LG, pady=(0, _ui_theme.PAD_LG))
        foot.grid_columnconfigure(0, weight=1)

        self._agree_var = ctk.BooleanVar(value=False)
        # CTkCheckBox has no wraplength, so the canonical label is wrapped for
        # display here rather than being shortened in licensing.terms.
        ctk.CTkCheckBox(
            foot, text=textwrap.fill(_terms.CHECKBOX_LABEL, 76),
            variable=self._agree_var,
            command=self._sync_continue, text_color=_TEXT,
            font=ctk.CTkFont(size=12),
            fg_color=_ACCENT, hover_color=_ACCENT_HOV, border_color=_BORDER,
        ).grid(row=0, column=0, sticky="w")

        self._status = ctk.CTkLabel(
            foot, text="", text_color=_DANGER, font=ctk.CTkFont(size=12),
            anchor="w", justify="left", wraplength=620,
        )
        self._status.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self._continue = ctk.CTkButton(
            foot, text="Continue", height=38, command=self._on_continue,
            fg_color=_ACCENT, hover_color=_ACCENT_HOV, text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._continue.grid(row=2, column=0, sticky="ew", pady=(_ui_theme.PAD, 0))
        self._sync_continue()

        self.after(60, self._grab)

    # ---------- content ----------
    def _fill_agreement(self, parent, name: str) -> None:
        r = 0
        for heading, paragraphs in _terms.SECTIONS:
            ctk.CTkLabel(
                parent, text=heading, text_color=_TEXT, anchor="w",
                font=ctk.CTkFont(size=15, weight="bold"),
            ).grid(row=r, column=0, sticky="w", padx=_ui_theme.PAD, pady=(_ui_theme.PAD, 4))
            r += 1
            for para in paragraphs:
                highlight = para == _terms.OWNERSHIP_HIGHLIGHT
                ctk.CTkLabel(
                    parent, text=para,
                    # Noticeable, but not an alarm colour.
                    text_color=_TEXT if highlight else _MUTED,
                    font=ctk.CTkFont(size=12, weight="bold" if highlight else "normal"),
                    anchor="w", justify="left", wraplength=640,
                ).grid(row=r, column=0, sticky="w", padx=_ui_theme.PAD, pady=(0, 6))
                r += 1

        ctk.CTkLabel(
            parent, text=_terms.acknowledgement_lead(name), text_color=_TEXT, anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=r, column=0, sticky="w", padx=_ui_theme.PAD, pady=(_ui_theme.PAD, 4))
        r += 1
        for point in _terms.ACKNOWLEDGEMENT_POINTS:
            ctk.CTkLabel(
                parent, text=f"•  {point}", text_color=_MUTED, anchor="w",
                justify="left", wraplength=630, font=ctk.CTkFont(size=12),
            ).grid(row=r, column=0, sticky="w", padx=_ui_theme.PAD, pady=(0, 5))
            r += 1
        ctk.CTkLabel(
            parent, text=_terms.LEGAL_NOTE, text_color=_TEXT, anchor="w",
            justify="left", wraplength=640, font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=r, column=0, sticky="w", padx=_ui_theme.PAD, pady=(_ui_theme.PAD, _ui_theme.PAD))

    # ---------- behaviour ----------
    def _grab(self) -> None:
        try:
            self.lift(); self.focus_force(); self.grab_set()
        except Exception:
            pass

    def _sync_continue(self) -> None:
        ready = bool(self._agree_var.get()) and not self._busy
        self._continue.configure(state="normal" if ready else "disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._continue.configure(text="Saving…" if busy else "Continue")
        self._sync_continue()

    def _on_continue(self) -> None:
        if self._busy or not self._agree_var.get():
            return
        if not getattr(self._session, "user_id", ""):
            self._status.configure(text="You must be signed in to continue.")
            return
        self._status.configure(text="")
        self._set_busy(True)

        def work():
            try:
                self._save(self._session)
            except AuthError as exc:
                self.after(0, lambda m=exc.message: self._fail(m))
            except Exception as exc:
                self.after(0, lambda m=str(exc): self._fail(m or "Could not save."))
            else:
                self.after(0, self._succeed)

        threading.Thread(target=work, daemon=True).start()

    def _fail(self, message: str) -> None:
        # Stay on the screen: a failed write must never look like acceptance.
        self._set_busy(False)
        self._status.configure(
            text=f"{message}\nYour acknowledgement was not saved. Please try again."
        )

    def _succeed(self) -> None:
        self._closed = True
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self._on_accept:
            self._on_accept()

    def _on_close(self) -> None:
        if self._busy or self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self._on_cancel:
            self._on_cancel()
