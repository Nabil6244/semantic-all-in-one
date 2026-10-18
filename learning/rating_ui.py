"""Native (customtkinter) rating prompt and history list. Logic lives in rating_flow; saving runs off the UI thread."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from . import events as ev
from . import rating_flow as rf

_TAG_LABELS = {"wrong_visuals": "Wrong visuals", "repetitive_scenes": "Repetitive scenes", "bad_transitions": "Bad transitions",
               "weak_graphics": "Weak graphics", "poor_pacing": "Poor pacing", "excellent_result": "Excellent result"}
_CAT_LABELS = {"visual_relevance": "Visual relevance to narration", "footage_selection": "Footage selection",
               "animations_graphics": "Animations and graphics", "typography_transitions": "Typography and transitions", "pacing": "Pacing"}


def schedule_prompt(app: Any, output_path: Any = None) -> None:
    """After a completed full render: wait for the tracker's output validation, then offer the prompt once."""
    app.after(3000, lambda: maybe_prompt(app, output_path))


def maybe_prompt(app: Any, output_path: Any = None) -> None:
    try:
        from pathlib import Path
        if getattr(app, "_running", False):
            return app.after(5000, lambda: maybe_prompt(app, output_path))
        ws = getattr(app, "_workspace", None)
        if ws is None or (output_path and not Path(str(output_path)).is_file()):
            return
        h = rf.pending_prompt_target(ws.project_id)
        if h and not rf._ledger.default_ledger().get_meta("rating_prompted:" + h["render_key"]):
            rf._ledger.default_ledger().set_meta("rating_prompted:" + h["render_key"], "1")    # one automatic prompt per render
            RatingDialog(app, h)
    except Exception:
        pass


class RatingDialog:
    def __init__(self, app: Any, h: Dict[str, Any], on_done=None):
        import customtkinter as ctk
        import ui.theme as T
        self.app, self.h, self.on_done, self.ctk = app, h, on_done, ctk
        prev = ((h.get("rating") or {}).get("payload")) or {}
        self.win = win = ctk.CTkToplevel(app)
        win.title("Rate your video")
        win.geometry("460x560")
        win.configure(fg_color=T.BG)
        win.transient(app)
        ctk.CTkLabel(win, text="How was your finished video?", font=ctk.CTkFont(size=16, weight="bold"), text_color=T.TEXT).pack(padx=16, pady=(14, 4), anchor="w")
        self.rating = int(prev.get("rating") or 0)
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(padx=16, anchor="w")
        self.stars = []
        for i in range(1, 6):
            b = ctk.CTkButton(row, text="☆", width=44, height=44, font=ctk.CTkFont(size=24), fg_color="transparent",
                              command=lambda n=i: self._set(n))
            b.pack(side="left", padx=2)
            self.stars.append(b)
        self._set(self.rating)
        self.cats = {}
        for k, label in _CAT_LABELS.items():
            r = ctk.CTkFrame(win, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=1)
            ctk.CTkLabel(r, text=label, anchor="w", text_color=T.TEXT).pack(side="left")
            m = ctk.CTkOptionMenu(r, values=["—", "1", "2", "3", "4", "5"], width=70)
            m.set(str((prev.get("categories") or {}).get(k, "—")))
            m.pack(side="right")
            self.cats[k] = m
        tf = ctk.CTkFrame(win, fg_color="transparent")
        tf.pack(fill="x", padx=16, pady=(8, 0))
        self.tags = {}
        for i, (k, label) in enumerate(_TAG_LABELS.items()):
            c = ctk.CTkCheckBox(tf, text=label, text_color=T.TEXT)
            if k in (prev.get("tags") or []):
                c.select()
            c.grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=2)
            self.tags[k] = c
        self.comment = ctk.CTkEntry(win, placeholder_text="Optional comment (stays on this computer)")
        if prev.get("comment"):
            self.comment.insert(0, prev["comment"])
        self.comment.pack(fill="x", padx=16, pady=10)
        self.status = ctk.CTkLabel(win, text="", text_color=T.DANGER, wraplength=420, justify="left")
        self.status.pack(padx=16, anchor="w")
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=10)
        self.save_btn = ctk.CTkButton(bar, text="Save", width=100, command=self._save)
        self.save_btn.pack(side="right")
        ctk.CTkButton(bar, text="Skip", width=80, fg_color="transparent", border_width=1, text_color=T.TEXT, command=self._skip).pack(side="right", padx=8)

    def _set(self, n: int) -> None:
        self.rating = n
        for i, b in enumerate(self.stars, 1):
            b.configure(text="★" if i <= n else "☆")

    def _skip(self) -> None:
        rf.skip(self.h["render_key"])
        self.win.destroy()

    def _save(self) -> None:
        if not self.rating:
            self.status.configure(text="Choose 1–5 stars first, or press Skip.")
            return
        cats = {k: int(m.get()) for k, m in self.cats.items() if m.get().isdigit()}
        tags = [k for k, c in self.tags.items() if c.get()]
        comment = self.comment.get()
        self.save_btn.configure(state="disabled")
        box: Dict[str, Any] = {}

        def work() -> None:
            box["r"] = rf.submit(self.h, self.rating, categories=cats, tags=tags, comment=comment)

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll() -> None:
            try:
                if not self.win.winfo_exists():
                    return                      # window closed while saving: the save still completes in its thread
            except Exception:
                return
            if t.is_alive():
                return self.win.after(80, poll)
            r = box.get("r")
            if r is not None and r.ok:
                if self.on_done:
                    self.on_done()
                self.win.destroy()
            else:
                self.save_btn.configure(state="normal")
                self.status.configure(text="Your rating could not be saved. Nothing was lost on screen: press Save to try again.")
        poll()


def open_history(app: Any) -> None:
    import customtkinter as ctk
    import ui.theme as T
    ws = getattr(app, "_workspace", None)
    win = ctk.CTkToplevel(app)
    win.title("Rate finished videos")
    win.geometry("560x420")
    win.configure(fg_color=T.BG)
    win.transient(app)
    body = ctk.CTkScrollableFrame(win, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=12, pady=12)

    def fill() -> None:
        for w in body.winfo_children():
            w.destroy()
        hist = rf.render_history(ws.project_id) if ws is not None else []
        if not hist:
            ctk.CTkLabel(body, text="No finished renders recorded for this project yet.", text_color=T.TEXT).pack(anchor="w")
        for h in hist:
            r = (h["rating"] or {}).get("payload") or {}
            when = h["occurred_at"][:16].replace("T", " ")
            state = "check failed" if h["validation_failed"] else (f"★ {r['rating']}  (revision {r['revision']})" if r else "not rated")
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"{when}  ·  {h['style_scope']}  ·  {state}", anchor="w", text_color=T.TEXT).pack(side="left")
            ctk.CTkButton(row, text="Revise" if r else "Rate", width=70, command=lambda hh=h: RatingDialog(app, hh, on_done=fill)).pack(side="right")

    fill()
