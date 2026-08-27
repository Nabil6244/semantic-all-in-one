"""Blocking CustomTkinter login modal (matches app theme)."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import customtkinter as ctk

from ui import theme as _ui_theme

from .auth_client import AuthClient, AuthError, AuthSession

_BG = _ui_theme.BG
_CARD = _ui_theme.CARD
_BORDER = _ui_theme.BORDER
_TEXT = _ui_theme.TEXT
_MUTED = _ui_theme.MUTED
_ACCENT = _ui_theme.ACCENT
_ACCENT_HOV = _ui_theme.ACCENT_HOV
_ACCENT_DARK = _ui_theme.ACCENT_DARK
_DANGER = _ui_theme.DANGER


class LoginDialog(ctk.CTkToplevel):
    """Modal login. ``on_success(session)`` when signed in; cancel/close → ``on_cancel()``."""

    def __init__(
        self,
        master,
        *,
        auth_client: Optional[AuthClient] = None,
        on_success: Optional[Callable[[AuthSession], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        message: str = "",
    ):
        super().__init__(master)
        self._client = auth_client or AuthClient()
        self._on_success = on_success
        self._on_cancel = on_cancel
        self._busy = False
        self._closed = False

        self.title("Sign in")
        # Tall enough for title + fields + full-height Sign in on Retina / scaled Macs.
        self.geometry("440x440")
        self.minsize(400, 420)
        self.configure(fg_color=_BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        try:
            self.transient(master)
        except Exception:
            pass
        try:
            self.grab_set()
        except Exception:
            pass

        frame = ctk.CTkFrame(self, fg_color=_CARD, corner_radius=12, border_width=1, border_color=_BORDER)
        frame.pack(fill="both", expand=True, padx=24, pady=24)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        # Footer first in visual priority: always keep Sign in at full height
        # (packing it last used to crush the button when the window was short).
        footer = ctk.CTkFrame(frame, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 20))

        self._btn = ctk.CTkButton(
            footer,
            text="Sign in",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            command=self._submit,
        )
        self._btn.pack(fill="x", ipady=4)

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # Spacer row absorbs leftover height so fields don't squash the button.
        spacer = ctk.CTkFrame(frame, fg_color="transparent", height=1)
        spacer.grid(row=1, column=0, sticky="nsew")

        ctk.CTkLabel(
            body,
            text="Semantic YT Studio",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=_TEXT,
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            body,
            text="Sign in with the account you were given.",
            font=ctk.CTkFont(size=12),
            text_color=_MUTED,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self._status = ctk.StringVar(value=message or "")
        self._status_label = ctk.CTkLabel(
            body,
            textvariable=self._status,
            font=ctk.CTkFont(size=12),
            text_color=_DANGER,
            wraplength=360,
            justify="left",
            height=24,
        )
        self._status_label.pack(anchor="w", padx=20, pady=(0, 8))

        ctk.CTkLabel(body, text="Email", font=ctk.CTkFont(size=11), text_color=_MUTED).pack(
            anchor="w", padx=20
        )
        self._email = ctk.CTkEntry(
            body,
            height=40,
            placeholder_text="you@example.com",
            fg_color=_BG,
            border_color=_BORDER,
            text_color=_TEXT,
        )
        self._email.pack(fill="x", padx=20, pady=(4, 12))

        ctk.CTkLabel(body, text="Password", font=ctk.CTkFont(size=11), text_color=_MUTED).pack(
            anchor="w", padx=20
        )
        self._password = ctk.CTkEntry(
            body,
            height=40,
            show="•",
            placeholder_text="Password",
            fg_color=_BG,
            border_color=_BORDER,
            text_color=_TEXT,
        )
        self._password.pack(fill="x", padx=20, pady=(4, 8))
        self._password.bind("<Return>", lambda _e: self._submit())

        self.after(50, self._email.focus_set)
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        try:
            self._btn.configure(state=state, text="Signing in…" if busy else "Sign in")
            self._email.configure(state=state)
            self._password.configure(state=state)
        except Exception:
            pass

    def _submit(self) -> None:
        if self._busy or self._closed:
            return
        if not self._client.configured:
            self._status.set("App is not configured for login.")
            return
        email = self._email.get().strip()
        password = self._password.get()
        self._status.set("")
        self._set_busy(True)

        def work():
            try:
                session = self._client.login(email, password)
                self.after(0, lambda: self._finish_ok(session))
            except AuthError as exc:
                msg = exc.message
                self.after(0, lambda m=msg: self._finish_err(m))
            except Exception as exc:
                msg = str(exc) or "Sign in failed"
                self.after(0, lambda m=msg: self._finish_err(m))

        threading.Thread(target=work, daemon=True).start()

    def _finish_ok(self, session: AuthSession) -> None:
        if self._closed:
            return
        self._set_busy(False)
        self._closed = True
        cb = self._on_success
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if cb:
            cb(session)

    def _finish_err(self, message: str) -> None:
        if self._closed:
            return
        self._set_busy(False)
        self._status.set(message or "Invalid login")

    def _cancel(self) -> None:
        if self._busy:
            return
        self._closed = True
        cb = self._on_cancel
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if cb:
            cb()
