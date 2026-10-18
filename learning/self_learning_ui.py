"""Learning window: Dashboard (status + analysis), Review Suggestions, Approved Rules. Analysis runs on a worker thread."""

from __future__ import annotations

import threading
from typing import Any, Dict

from . import csv_analyzer, packages, review

LIMITS = ("Analysed: Normal, Overscaled/Exp Solar, StarMap, What If and Hybrid (its saved plan.json). pakMap and Weather use other schemas and are not read. "
          "For StarMap, What If and Hybrid the CSV Generator has no planner, so approved rules there are guidance text added to the copied prompt, not automatic changes.",
          "Findings are associations between CSV structure and your own ratings, not proof of cause. Unrated projects are ignored, never counted as bad.",
          "A suggestion needs several independent rated projects of the same style before it appears; with little data this list is empty.")


def open_learning(app: Any) -> None:
    import customtkinter as ctk
    import ui.theme as T

    win = ctk.CTkToplevel(app)
    win.title("Learning")
    win.geometry("760x640")
    win.configure(fg_color=T.BG)
    win.transient(app)
    tabs = ctk.CTkTabview(win)
    tabs.pack(fill="both", expand=True, padx=10, pady=10)
    for name in ("Dashboard", "Review Suggestions", "Approved Rules"):
        tabs.add(name)
    state: Dict[str, Any] = {"thread": None, "cancel": None, "progress": (0.0, ""), "done": None}

    # ---- dashboard
    dash = tabs.tab("Dashboard")
    status_lbl = ctk.CTkLabel(dash, text="", justify="left", anchor="w", wraplength=700, text_color=T.TEXT)
    status_lbl.pack(fill="x", pady=(4, 6))
    row = ctk.CTkFrame(dash, fg_color="transparent")
    row.pack(fill="x")
    analyze_btn = ctk.CTkButton(row, text="Analyze Existing CSVs", width=190)
    analyze_btn.pack(side="left")
    cancel_btn = ctk.CTkButton(row, text="Cancel", width=80, fg_color="transparent", border_width=1, text_color=T.TEXT, state="disabled")
    cancel_btn.pack(side="left", padx=8)
    bar = ctk.CTkProgressBar(dash)
    bar.set(0)
    bar.pack(fill="x", pady=8)
    prog_lbl = ctk.CTkLabel(dash, text="", anchor="w", text_color=T.TEXT)
    prog_lbl.pack(fill="x")
    ctk.CTkLabel(dash, text="Limits of this data", font=ctk.CTkFont(weight="bold"), anchor="w", text_color=T.TEXT).pack(fill="x", pady=(10, 0))
    ctk.CTkLabel(dash, text="\n".join("• " + x for x in LIMITS), justify="left", anchor="w", wraplength=700, text_color=T.TEXT).pack(fill="x")

    def refresh_status() -> None:
        st = csv_analyzer.status()
        s = st["summary"] or {}
        n_sugg = len(review.suggestions())
        status_lbl.configure(text=(
            f"Last analysis: {st['last_run'] or 'never'}.  "
            f"{'New data since then: run the analysis again.' if st['stale'] else 'Up to date.'}\n"
            f"Projects scanned: {s.get('projects', 0)}; CSVs newly analysed: {s.get('analyzed_new', 0)}; unchanged: {s.get('unchanged', 0)}; "
            f"other-schema CSVs not read: {s.get('unsupported_schema', 0)}.\nSuggestions waiting for your review: {n_sugg}."))

    def start() -> None:
        if state["thread"] is not None and state["thread"].is_alive():
            return
        root = app._projects_root_path()
        cancel = threading.Event()
        state.update(cancel=cancel, done=None, progress=(0.0, "Starting"))
        analyze_btn.configure(state="disabled")
        cancel_btn.configure(state="normal")

        def work() -> None:
            try:
                state["done"] = csv_analyzer.scan_projects(root, cancel=cancel, progress=lambda f, m: state.__setitem__("progress", (f, m)))
            except Exception as exc:
                state["done"] = {"error": type(exc).__name__}
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
        prog_lbl.configure(text=m)
        d = state["done"]
        if d is None:
            return win.after(100, poll)
        analyze_btn.configure(state="normal")
        cancel_btn.configure(state="disabled")
        prog_lbl.configure(text="Cancelled; nothing was changed in your projects." if d.get("cancelled") else
                           (f"Analysis failed ({d['error']}). Your projects were not changed." if d.get("error") else "Analysis finished."))
        refresh_status()
        fill_suggestions()

    analyze_btn.configure(command=start)
    cancel_btn.configure(command=lambda: state["cancel"] and state["cancel"].set())

    # ---- suggestions
    sug = ctk.CTkScrollableFrame(tabs.tab("Review Suggestions"), fg_color="transparent")
    sug.pack(fill="both", expand=True)

    def fill_suggestions() -> None:
        for w in sug.winfo_children():
            w.destroy()
        items = review.suggestions()
        if not items:
            ctk.CTkLabel(sug, text="No suggestions yet. They appear when several independent rated projects of one style show the same pattern.",
                         wraplength=680, justify="left", text_color=T.TEXT).pack(anchor="w", pady=8)
        for c in items:
            box = ctk.CTkFrame(sug)
            box.pack(fill="x", pady=5, padx=2)
            ctk.CTkLabel(box, text=f"[{c['style_scope']}]  {c['text']}", wraplength=680, justify="left", anchor="w", text_color=T.TEXT).pack(fill="x", padx=8, pady=(6, 0))
            ctk.CTkLabel(box, text=f"Evidence: {c['pattern']}\nSamples: {c['evidence_count']}  ·  confidence {c['confidence']:.2f}  ·  expected benefit: {c['expected_benefit']}\n"
                                   f"Possible drawback: {c['side_effects']}", wraplength=680, justify="left", anchor="w", text_color=T.TEXT).pack(fill="x", padx=8)
            br = ctk.CTkFrame(box, fg_color="transparent")
            br.pack(anchor="e", padx=8, pady=6)
            for label, act in (("Approve", "approve"), ("Reject", "reject"), ("Later", "defer")):
                ctk.CTkButton(br, text=label, width=80, command=lambda cc=c, a=act: act_on(cc, a)).pack(side="left", padx=3)

    def act_on(c, a) -> None:
        review.decide(c, a)
        fill_suggestions()
        fill_approved()
        refresh_status()

    # ---- approved
    appr = ctk.CTkScrollableFrame(tabs.tab("Approved Rules"), fg_color="transparent")
    appr.pack(fill="both", expand=True)

    def fill_approved() -> None:
        for w in appr.winfo_children():
            w.destroy()
        data = review.approved()
        if not data:
            ctk.CTkLabel(appr, text="No approved rules. The CSV Generator behaves exactly as before.", text_color=T.TEXT).pack(anchor="w", pady=8)
        for scope, rules in data.items():
            head = ctk.CTkFrame(appr, fg_color="transparent")
            head.pack(fill="x", pady=(8, 0))
            ctk.CTkLabel(head, text=f"{scope}  (v{(packages.active_package(scope) or {}).get('version', '?')})", font=ctk.CTkFont(weight="bold"), text_color=T.TEXT).pack(side="left")
            ctk.CTkButton(head, text="Roll back to previous version", width=190, command=lambda s=scope: (review.rollback(s), fill_approved())).pack(side="right")
            for r in rules:
                rr = ctk.CTkFrame(appr, fg_color="transparent")
                rr.pack(fill="x")
                ctk.CTkLabel(rr, text=f"• {r['text']}  ({r['kind']}, {r['evidence_count']} samples)", wraplength=520, justify="left", anchor="w", text_color=T.TEXT).pack(side="left", fill="x", expand=True)
                ctk.CTkButton(rr, text="Disable", width=80, command=lambda s=scope, i=r["id"]: (review.disable(s, i), fill_approved())).pack(side="right")

    refresh_status()
    fill_suggestions()
    fill_approved()
    win.protocol("WM_DELETE_WINDOW", lambda: (state["cancel"] and state["cancel"].set(), win.destroy()))
