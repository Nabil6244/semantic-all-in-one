"""The new shell's live parts: the Jobs drawer, the sidebar step ticks, recent styles and the Tools fold.

install(app) is called once at the end of app._build_ui. Everything here only READS app state (flags, vars, files)
on a slow timer, except two things the user clicks: Stop in the Jobs drawer (the style's own cancel) and the
Tools fold. Nothing starts until Generate still holds.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import customtkinter as ctk

from . import jobs as J
from . import prefs as P
from . import theme as T
from .widgets import make_button

POLL_MS = 1500           # jobs + step ticks
VISUALS_EVERY_S = 6.0    # the scene snapshot is the one costly read; refreshed less often


def install(app: Any) -> None:
    shell = getattr(app, "_shell", None)
    if shell is None:
        return
    shell.on_jobs = lambda: open_jobs_drawer(app)
    shell.on_tools_toggled = lambda is_open: P.put(app, P.TOOLS_OPEN_KEY, bool(is_open))
    if P.get(app, P.TOOLS_OPEN_KEY, True) is False:
        shell.set_tools_open(False, notify=False)
    _track_recent_styles(app)
    install_shortcuts(app)
    app._home_state = {"visuals_at": 0.0, "visuals_done": False}
    try:
        app.after(POLL_MS, lambda: _poll(app))
    except Exception:
        pass


# ---- keyboard shortcuts --------------------------------------------------------------------------------------------------------

MOD = "Command" if sys.platform == "darwin" else "Control"
MOD_LABEL = "\u2318" if sys.platform == "darwin" else "Ctrl+"


def _go(app: Any, key: str) -> str:
    try:
        app._shell.navigate(key)
    except Exception:
        pass
    return "break"


def _search_styles(app: Any) -> str:
    try:
        from . import style_pages

        app._shell.navigate("visual_director")
        style_pages.change_style(app)
        entry = getattr(app, "_vd_search_entry", None)
        if entry is not None:
            app.after_idle(entry.focus_set)
    except Exception:
        pass
    return "break"


def _settings(app: Any) -> str:
    fn = getattr(app, "_open_settings", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass
    return "break"


def shortcuts(app: Any) -> Dict[str, Any]:
    """{keysym: action}. Ctrl/Cmd + 0 Home, 1-7 the production steps, J Jobs, K search styles, comma Settings."""
    out: Dict[str, Any] = {"0": lambda: _go(app, "project")}
    for i, key in enumerate(T.STEP_KEYS, start=1):
        out[str(i)] = lambda k=key: _go(app, k)
    out["j"] = lambda: (open_jobs_drawer(app), "break")[1]
    out["k"] = lambda: _search_styles(app)
    out["comma"] = lambda: _settings(app)
    return out


def install_shortcuts(app: Any) -> None:
    for keysym, action in shortcuts(app).items():
        try:
            app.bind_all(f"<{MOD}-Key-{keysym}>", lambda _e, a=action: a(), add="+")
        except Exception:
            pass


# ---- recent styles --------------------------------------------------------------------------------------------------------------

def _track_recent_styles(app: Any) -> None:
    """Remember each style the user opens (the picker shows them first). Wraps the instance's _on_style_pick: every
    card click looks the method up on the instance, so all clicks pass through, and the pick itself is unchanged."""
    original = getattr(app, "_on_style_pick", None)
    if original is None or getattr(original, "_sy_recent", False):
        return

    def pick(name, *args, **kwargs):
        result = original(name, *args, **kwargs)
        try:
            if getattr(app, "_style_picker", None) is not None and app._style_picker.get() == name:
                P.note_recent_style(app, name)
                from . import visual_director as VD

                app.after_idle(lambda: VD.refresh_quick_picks(app))   # later: the clicked chip itself may be rebuilt
        except Exception:
            pass
        return result

    pick._sy_recent = True  # type: ignore[attr-defined]
    pick.__wrapped__ = original  # type: ignore[attr-defined]
    app._on_style_pick = pick


# ---- the timer ------------------------------------------------------------------------------------------------------------------

def _poll(app: Any) -> None:
    try:
        if not app.winfo_exists():
            return
    except Exception:
        return
    try:
        running = J.running(app)
        summary = running[0].label if len(running) == 1 else ""
        app._shell.set_jobs(len(running), summary)
        _refresh_steps(app)
        drawer = getattr(app, "_jobs_drawer", None)
        if drawer is not None and drawer.winfo_exists():
            drawer.refresh()
    except Exception:
        pass
    try:
        app.after(POLL_MS, lambda: _poll(app))
    except Exception:
        pass


def _file(value: Any) -> bool:
    try:
        raw = str(value or "").strip()
        return bool(raw) and Path(raw).is_file()
    except Exception:
        return False


def step_states(app: Any) -> Dict[str, bool]:
    """Which production steps are done for the open project. All False with no project open."""
    ws = getattr(app, "_workspace", None)
    out = {k: False for k in T.STEP_KEYS}
    if ws is None:
        return out
    rows = getattr(app, "_scene_rows", None) or []
    try:
        out["script"] = bool(rows) or Path(ws.script_path).is_file() or Path(ws.csv_path).is_file()
    except Exception:
        out["script"] = bool(rows)
    try:
        out["voiceover"] = _file(app.audio_var.get())
    except Exception:
        pass
    try:
        out["visual_director"] = bool(str(app._active_style() or "").strip()) and out["script"]
    except Exception:
        pass
    state = getattr(app, "_home_state", None) or {}
    now = time.monotonic()
    if rows and now - state.get("visuals_at", 0.0) >= VISUALS_EVERY_S:
        state["visuals_at"] = now
        try:
            snap = app._qa_snapshot()
            total = int(getattr(snap, "total", 0) or 0)
            state["visuals_done"] = total > 0 and int(getattr(snap, "ready", 0) or 0) >= total
        except Exception:
            state["visuals_done"] = False
    out["visual_plan"] = bool(rows) and bool(state.get("visuals_done"))
    try:
        sd = Path(ws.state_dir)
        out["audio"] = (sd / "smart_editing.json").is_file()
        out["graphics"] = (sd / "editorial_plan.json").is_file()
    except Exception:
        pass
    out["render"] = _file(getattr(app, "_last_output", ""))
    return out


def _refresh_steps(app: Any) -> None:
    for key, done in step_states(app).items():
        app._shell.set_step_done(key, done)


# ---- the Jobs drawer ------------------------------------------------------------------------------------------------------------

def open_path(path: str) -> None:
    """Show a file or folder in Finder / Explorer."""
    p = Path(path)
    target = p if p.is_dir() else p.parent
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)] if p.is_file() else ["open", str(target)])
        elif os.name == "nt":
            if p.is_file():
                subprocess.Popen(["explorer", "/select,", str(p)])
            else:
                os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception:
        pass


class JobsDrawer(ctk.CTkToplevel):
    """A small panel over the status bar: each running job with Stop, plus the last finished video."""

    def __init__(self, app: Any):
        super().__init__(app)
        self.app = app
        self.title("Jobs")
        self.configure(fg_color=T.PANEL)
        self.resizable(False, False)
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Running jobs", font=ctk.CTkFont(size=14, weight="bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        ctk.CTkLabel(self, text="Every style's work in one place. Stop ends a job the same way its own Stop button does.",
                     font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", justify="left", wraplength=340).grid(
            row=1, column=0, sticky="ew", padx=16)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="ew", padx=12, pady=(10, 4))
        self.body.grid_columnconfigure(0, weight=1)
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 12))
        foot.grid_columnconfigure(0, weight=1)
        self.last_btn = make_button(foot, "Show last video", self._show_last, variant="ghost", size="sm", width=130)
        self.last_btn.grid(row=0, column=0, sticky="w")
        make_button(foot, "Close", self.destroy, size="sm", width=80).grid(row=0, column=1, sticky="e")
        self._sig: Optional[tuple] = None
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()
        self._place()

    def _place(self) -> None:
        try:
            self.update_idletasks()
            btn = self.app._shell.jobs_btn
            w, h = max(380, self.winfo_reqwidth()), self.winfo_reqheight()
            x = btn.winfo_rootx() + btn.winfo_width() - w
            y = btn.winfo_rooty() - h - 8
            self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _show_last(self) -> None:
        last = str(getattr(self.app, "_last_output", "") or "")
        if last and Path(last).exists():
            open_path(last)

    def refresh(self) -> None:
        running = J.running(self.app)
        sig = tuple(j.flag for j in running)
        last_ok = _file(getattr(self.app, "_last_output", ""))
        try:
            self.last_btn.configure(state="normal" if last_ok else "disabled")
        except Exception:
            pass
        if sig == self._sig:
            return
        self._sig = sig
        for child in self.body.winfo_children():
            child.destroy()
        if not running:
            ctk.CTkLabel(self.body, text="Nothing is running. Generate on any style page starts a job.",
                         font=ctk.CTkFont(size=12), text_color=T.TEXT_TERTIARY, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=4, pady=10)
            return
        for i, job in enumerate(running):
            row = ctk.CTkFrame(self.body, fg_color=T.CARD, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="●", text_color=T.PROCESSING, font=ctk.CTkFont(size=10)).grid(
                row=0, column=0, padx=(10, 6), pady=8)
            ctk.CTkLabel(row, text=job.label, font=ctk.CTkFont(size=12, weight="bold"), text_color=T.TEXT, anchor="w").grid(
                row=0, column=1, sticky="ew")
            if job.stop is not None:
                make_button(row, "Stop", lambda j=job: self._stop(j), variant="danger", size="sm", width=64).grid(
                    row=0, column=2, padx=8, pady=6)

    def _stop(self, job: J.Job) -> None:
        try:
            if job.stop is not None:
                job.stop()
        except Exception as exc:  # noqa: BLE001
            try:
                self.app._append_log(f"[JOBS] Stop {job.label} failed: {exc}\n")
            except Exception:
                pass
        self._sig = None
        self.refresh()


def open_jobs_drawer(app: Any) -> None:
    drawer = getattr(app, "_jobs_drawer", None)
    try:
        if drawer is not None and drawer.winfo_exists():
            drawer.destroy()   # the button toggles it
            app._jobs_drawer = None
            return
    except Exception:
        pass
    app._jobs_drawer = JobsDrawer(app)
