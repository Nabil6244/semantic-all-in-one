"""CustomTkinter installer UI: status + single progress bar + cancel."""

from __future__ import annotations

import threading
from typing import Optional

import customtkinter as ctk

from installer.pipeline import (
    build_plan,
    friendly_error,
    run_install,
)
from installer.platform import UnsupportedPlatformError, detect_platform


class InstallerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Video Generator Setup")
        self.geometry("520x220")
        self.resizable(False, False)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self._cancel = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._done = False

        self._status = ctk.CTkLabel(
            self,
            text="Preparing installer…",
            anchor="w",
            wraplength=480,
        )
        self._status.pack(fill="x", padx=24, pady=(28, 12))

        self._bar = ctk.CTkProgressBar(self, width=470, height=16)
        self._bar.set(0)
        self._bar.pack(padx=24, pady=8)

        self._pct = ctk.CTkLabel(self, text="0%", anchor="e")
        self._pct.pack(fill="x", padx=24)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(16, 20))

        self._cancel_btn = ctk.CTkButton(
            btn_row, text="Cancel", width=100, command=self._on_cancel
        )
        self._cancel_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._start)

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status.configure(text=text))

    def _set_progress(self, value: float) -> None:
        def apply() -> None:
            self._bar.set(value)
            self._pct.configure(text=f"{int(round(value * 100))}%")

        self.after(0, apply)

    def _on_cancel(self) -> None:
        if self._done:
            self.destroy()
            return
        self._cancel.set()
        self._set_status("Cancelling…")
        self._cancel_btn.configure(state="disabled")

    def _start(self) -> None:
        try:
            detect_platform()
        except UnsupportedPlatformError as exc:
            self._fail(str(exc))
            return

        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self) -> None:
        try:
            plan = build_plan()
            run_install(
                plan,
                status=self._set_status,
                progress=self._set_progress,
                should_stop=self._cancel.is_set,
            )
            self.after(0, self._succeed)
        except Exception as exc:
            msg = friendly_error(exc)
            if self._cancel.is_set() and "cancel" in msg.lower():
                self.after(0, self.destroy)
                return
            self.after(0, lambda m=msg: self._fail(m))

    def _succeed(self) -> None:
        self._done = True
        self._set_status("Installation complete. You can close this window and launch the app.")
        self._set_progress(1.0)
        self._cancel_btn.configure(text="Close", state="normal")

    def _fail(self, message: str) -> None:
        self._done = True
        self._set_status(message)
        self._cancel_btn.configure(text="Close", state="normal")
        try:
            from tkinter import messagebox

            messagebox.showerror("Video Generator Setup", message)
        except Exception:
            pass


def run_ui() -> None:
    app = InstallerApp()
    app.mainloop()
