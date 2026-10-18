"""CSV Generator window (customtkinter). Generation runs on a worker thread; the window polls it. Generating never imports anything:
"Use in this project" is a separate, explicit step that goes through the app's normal import code."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .engine import SUPPORTED_STYLES, UNSUPPORTED_STYLES, GenerationOptions, GenerationResult, generate, style_scope_mode

_TYPE_LABELS = {"stock_video": "Stock video", "stock_image": "Stock image", "image": "AI image (Flow)", "video": "AI video (Flow)",
                "youtube_video": "YouTube clips", "nasa_video": "NASA video", "archive_video": "Archive video"}
_DEFAULT_ON = ("stock_video", "stock_image")
_PRESET = {"overscaled": "overscaled", "exp_solar": "exp_solar"}


def open_generator(app: Any) -> None:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox

    import ui.theme as T
    win = ctk.CTkToplevel(app)
    win.title("CSV Generator (local, no AI API)")
    win.geometry("820x720")
    win.configure(fg_color=T.BG)
    win.transient(app)
    state: Dict[str, Any] = {"result": None, "thread": None, "cancel": None, "progress": (0.0, ""), "done": None}

    ctk.CTkLabel(win, text="Generate a CSV from your script — offline, rule-based", font=ctk.CTkFont(size=15, weight="bold"),
                 text_color=T.TEXT).pack(anchor="w", padx=14, pady=(12, 0))
    ctk.CTkLabel(win, text="A starting plan from rules and keywords, not an AI model: review every scene. Nothing is imported until you choose to use it.",
                 text_color=T.TEXT, wraplength=780, justify="left").pack(anchor="w", padx=14)
    top = ctk.CTkFrame(win, fg_color="transparent")
    top.pack(fill="x", padx=14, pady=6)
    names = {v: k for k, v in SUPPORTED_STYLES.items()}
    style_var = ctk.StringVar(value="Normal")
    ctk.CTkOptionMenu(top, values=list(names), variable=style_var, width=170).pack(side="left")
    note_var = ctk.StringVar(value="")
    ctk.CTkLabel(top, textvariable=note_var, text_color=T.TEXT, wraplength=520, justify="left").pack(side="left", padx=10)
    ctk.CTkLabel(top, text="Pakmap, Hybrid, StarMap, What If and Weather use their own planners.", text_color=T.TEXT).pack(side="right")
    script_box = ctk.CTkTextbox(win, height=150)
    script_box.pack(fill="x", padx=14)
    try:
        script_box.insert("1.0", app._main_script_text())
    except Exception:
        pass
    opts = ctk.CTkFrame(win, fg_color="transparent")
    opts.pack(fill="x", padx=14, pady=4)
    type_vars = {}
    for k, label in _TYPE_LABELS.items():
        v = ctk.BooleanVar(value=k in _DEFAULT_ON)
        ctk.CTkCheckBox(opts, text=label, variable=v, text_color=T.TEXT).pack(side="left", padx=4)
        type_vars[k] = v
    row2 = ctk.CTkFrame(win, fg_color="transparent")
    row2.pack(fill="x", padx=14)
    ctk.CTkLabel(row2, text="Words per scene", text_color=T.TEXT).pack(side="left")
    words_var = ctk.StringVar(value="45")
    ctk.CTkEntry(row2, textvariable=words_var, width=60).pack(side="left", padx=6)
    gen_btn = ctk.CTkButton(row2, text="Generate", width=110)
    gen_btn.pack(side="right")
    cancel_btn = ctk.CTkButton(row2, text="Cancel", width=80, fg_color="transparent", border_width=1, text_color=T.TEXT, state="disabled")
    cancel_btn.pack(side="right", padx=6)
    bar = ctk.CTkProgressBar(win)
    bar.set(0)
    bar.pack(fill="x", padx=14, pady=(8, 2))
    status = ctk.CTkLabel(win, text="", text_color=T.TEXT, anchor="w", justify="left", wraplength=780)
    status.pack(fill="x", padx=14)
    issues_box = ctk.CTkTextbox(win, height=110)
    issues_box.pack(fill="x", padx=14, pady=4)
    preview = ctk.CTkTextbox(win, wrap="none")
    preview.pack(fill="both", expand=True, padx=14, pady=4)
    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(fill="x", padx=14, pady=(0, 12))
    save_btn = ctk.CTkButton(btns, text="Save CSV…", width=110, state="disabled")
    save_btn.pack(side="right")
    use_btn = ctk.CTkButton(btns, text="Use in this project", width=150, state="disabled")
    use_btn.pack(side="right", padx=8)

    def style_key() -> str:
        return names[style_var.get()]

    def describe_style(*_a) -> None:
        note_var.set("Same four columns as the Claude prompt: scene_number, script_segment, asset_type, prompt."
                     + (" (Enoch editorial rules are not applied.)" if style_key() == "enoch_template" else ""))
    style_var.trace_add("write", describe_style)
    describe_style()

    def start() -> None:
        if state["thread"] is not None and state["thread"].is_alive():
            return
        try:
            target = max(12, min(200, int(words_var.get())))
        except ValueError:
            status.configure(text="Words per scene must be a number.")
            return
        enabled = [k for k, v in type_vars.items() if v.get()] or list(_DEFAULT_ON)
        script = script_box.get("1.0", "end").strip()
        style = style_key()
        scope = None
        try:
            from learning.scope import resolve_scope
            scope = resolve_scope(app, style_scope_mode(style))       # approved knowledge of THIS style only, if any
        except Exception:
            pass
        cancel = threading.Event()
        state.update(cancel=cancel, result=None, done=None, progress=(0.0, "Starting"))
        gen_btn.configure(state="disabled")
        cancel_btn.configure(state="normal")
        for b in (use_btn, save_btn):
            b.configure(state="disabled")

        def work() -> None:
            try:
                state["done"] = generate(script, style, GenerationOptions(target_words=target, enabled_types=enabled), scope=scope, cancel=cancel,
                                         progress=lambda f, m: state.__setitem__("progress", (f, m)))
            except Exception as exc:       # the window must never be left busy
                state["done"] = GenerationResult(style, (), [], [], [], [f"Generation failed ({type(exc).__name__})."])
        t = threading.Thread(target=work, daemon=True)
        state["thread"] = t
        t.start()
        poll()

    def poll() -> None:
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        f, m = state["progress"]
        bar.set(f)
        status.configure(text=m)
        res: Optional[GenerationResult] = state["done"]
        if res is None:
            return win.after(100, poll)
        state["result"] = res
        gen_btn.configure(state="normal")
        cancel_btn.configure(state="disabled")
        issues_box.delete("1.0", "end")
        preview.delete("1.0", "end")
        if res.cancelled:
            status.configure(text="Cancelled. Nothing was changed.")
            return
        issues_box.insert("1.0", "\n".join(str(i) for i in res.issues) or "No validation problems.")
        if res.applied_knowledge:
            issues_box.insert("end", "\n\nApproved style knowledge applied: " + "; ".join(res.applied_knowledge))
        issues_box.insert("end", "\n\n" + " ".join(res.notes))
        if res.rows:
            preview.insert("1.0", res.csv_text)
            save_btn.configure(state="normal")
        use_btn.configure(state="normal" if res.ok else "disabled")
        status.configure(text=f"{len(res.rows)} scenes. " + ("Valid: review, then use it." if res.ok else "Fix the errors above (edit the script or options), then generate again."))

    def cancel() -> None:
        if state["cancel"] is not None:
            state["cancel"].set()
        cancel_btn.configure(state="disabled")

    def current_csv_text() -> str:
        text = preview.get("1.0", "end").strip()
        return text + "\n" if text else ""

    def save() -> None:
        p = filedialog.asksaveasfilename(parent=win, defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="generated_scenes.csv")
        if p:
            Path(p).write_text(current_csv_text(), encoding="utf-8", newline="")

    def use() -> None:
        res = state["result"]
        ws = getattr(app, "_workspace", None)
        if res is None or not res.ok or ws is None:
            messagebox.showinfo("CSV Generator", "Open a project first and generate a valid plan.", parent=win)
            return
        style = res.style
        try:
            ws.ensure_dirs()
            out = ws.csv_dir / f"generated_{style}_{int(time.time())}.csv"
            out.write_text(current_csv_text(), encoding="utf-8", newline="")
            if style in _PRESET:
                if getattr(app, "_overscaled_style_preset_id", "") != _PRESET[style]:
                    messagebox.showinfo("CSV Generator", f"Saved to {out}.\nSwitch the Overscaled panel to {SUPPORTED_STYLES[style]}, then load this file there.", parent=win)
                    return
                app._overscaled_csv_var.set(str(out))
                app._load_overscaled_csv(str(out))
            else:
                if ws.csv_path.is_file() and not messagebox.askyesno("Replace the project's CSV?", "This project already has a CSV. Replace it with the generated one?", parent=win):
                    return
                app._import_claude_csv_path(out, source_label="generated")
            win.destroy()
        except Exception as exc:
            messagebox.showerror("CSV Generator", f"Could not send the CSV to the project: {type(exc).__name__}", parent=win)

    gen_btn.configure(command=start)
    cancel_btn.configure(command=cancel)
    save_btn.configure(command=save)
    use_btn.configure(command=use)
    win.protocol("WM_DELETE_WINDOW", lambda: (cancel(), win.destroy()))
