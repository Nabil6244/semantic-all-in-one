"""The Visuals page's scene rows in the Lovable mockup's look (2026-11-25): a 16:9 thumbnail, the scene number with its time
under it, two lines of narration, the source as a pill, the status as a tinted pill and roomier buttons.

app.py builds the rows (app._decorate_scene_row) and may only gain lines (test_weather_isolation), so this module wraps the
row builder, the status painter and the column header from outside and restyles the widgets they made. Same widgets, same
keys, same callbacks: nothing about what a row does changes. Installed from ui.home.install."""

from __future__ import annotations

import sys
from typing import Any

import customtkinter as ctk

from . import scene_list
from . import theme as T
from .widgets import segmented_style

THUMB_W, THUMB_H = 64, 36
NARRATION_CHARS = 140


def _pill(widget: Any, color: Any) -> None:
    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        widget.configure(fg_color=T.mix(color, T.CARD, 0.14))


def _thumb(app: Any, label: Any, scene_number: Any) -> None:
    """The same still-image thumbnail app.py loads, at the mockup's 16:9 size (video scenes keep the plain tile)."""
    mod = sys.modules.get(type(app).__module__)
    try:
        if not label.winfo_exists():
            return
        result = app._asset_results.get(mod._scene_key(scene_number))
        if result is None or not getattr(result, "ok", False):
            return
        img = mod._scene_thumbnail_image(result.path, size=THUMB_W)
        if img is not None:
            label.configure(image=img, text="")
    except Exception:
        pass


def restyle_row(app: Any, widgets: dict) -> None:
    row, scene = widgets.get("row"), widgets.get("scene")
    if row is None or scene is None:
        return
    row.configure(height=scene_list.SCENE_ROW_HEIGHT, corner_radius=8)
    row.grid_propagate(False)
    row.grid_rowconfigure(0, weight=1)
    for child in row.winfo_children():
        if isinstance(child, ctk.CTkFrame):   # the number cell: thumbnail + scene number
            for part in child.winfo_children():
                if isinstance(part, ctk.CTkLabel) and not part.cget("text"):
                    part.configure(width=THUMB_W, height=THUMB_H, corner_radius=6, fg_color=T.CARD_HOVER)
                    part.pack_configure(padx=(0, 8))
                    app.after_idle(lambda p=part, n=scene.scene_number: _thumb(app, p, n))
                elif isinstance(part, ctk.CTkLabel):
                    part.configure(font=ctk.CTkFont(size=13, weight="bold"))
            child.configure(width=THUMB_W + 44)
    time_label = widgets.get("time_label")
    if time_label is not None:
        time_label.configure(font=ctk.CTkFont(family="Menlo", size=10))
    badge = widgets.get("badge")
    if badge is not None:
        badge.configure(corner_radius=10, height=22, anchor="center", font=ctk.CTkFont(size=10, weight="bold"))
    status = widgets.get("status_label")
    if status is not None:
        status.configure(corner_radius=10, height=22, anchor="center", font=ctk.CTkFont(size=11, weight="bold"))
        _pill(status, status.cget("text_color"))
    narr_col = row.grid_slaves(row=0, column=3)
    if narr_col:
        text = " ".join(str(getattr(scene, "script_segment", "") or "").split())
        if len(text) > NARRATION_CHARS:
            text = text[:NARRATION_CHARS - 1].rstrip() + "…"
        narr = narr_col[0]
        narr.configure(text=text, font=ctk.CTkFont(size=12), justify="left", wraplength=280)
    vis_col = row.grid_slaves(row=0, column=4)
    if vis_col:
        vis_col[0].configure(font=ctk.CTkFont(size=11))
    for col in (6, 7, 8):
        for w in row.grid_slaves(row=0, column=col):
            w.configure(font=ctk.CTkFont(size=10))
    for name, btn in (widgets.get("buttons") or {}).items():
        try:
            btn.configure(height=26, corner_radius=6, font=ctk.CTkFont(size=11))
            if name == "source":
                btn.configure(text="Source", width=64)
            elif name == "open":
                btn.configure(width=54)
        except Exception:
            pass


def _restyle_header(app: Any) -> None:
    header = getattr(app, "_scene_header", None)
    if header is None:
        return
    widths = {"#": THUMB_W + 44, "Narration": 280, "Src": 72, "Status": 118}
    for w in header.winfo_children():
        if isinstance(w, ctk.CTkLabel):
            title = w.cget("text")
            w.configure(text=title.upper() if title else title, font=ctk.CTkFont(size=10, weight="bold"),
                        text_color=T.TEXT_TERTIARY)
            if title in widths:
                w.configure(width=widths[title])


# ---- filter pills + search ------------------------------------------------------------------------------------------------------

FILTERS = ("All", "Ready", "Queued", "Needs attention")
_ATTENTION = {"needs_action", "failed", "timeout", "cancelled"}


def category(status: str) -> str:
    """Which pill a row status belongs to ("" = only under All: skipped and continuation rows)."""
    if status in ("ready", "success"):
        return "Ready"
    if status in _ATTENTION:
        return "Needs attention"
    if status in ("skipped", "continues", "continuation"):
        return ""
    return "Queued"   # waiting / queued / anything still being fetched


def _haystack(scene: Any) -> str:
    parts = [str(getattr(scene, "scene_number", "") or "")]
    for attr in ("script_segment", "prompt", "stock", "visual_description"):
        parts.append(str(getattr(scene, attr, "") or ""))
    return " ".join(parts).lower()


def matches(app: Any, scene: Any) -> bool:
    state = getattr(app, "_vl_filter", None) or {}
    pick, query = state.get("pick", "All"), state.get("query", "").strip().lower()
    if pick != "All":
        try:
            status = app._row_status_from_result(scene)
        except Exception:
            status = ""
        if category(status) != pick:
            return False
    if query and query not in _haystack(scene):
        return False
    return True


def apply_filter(app: Any, only_key: Any = None) -> None:
    """Show the rows that match the pill and the search, hide the rest (rows keep their place: grid_remove remembers it)."""
    widgets_by_key = getattr(app, "_scene_row_widgets", None) or {}
    items = [(only_key, widgets_by_key.get(only_key))] if only_key is not None else list(widgets_by_key.items())
    for _key, widgets in items:
        if not widgets:
            continue
        row, scene = widgets.get("row"), widgets.get("scene")
        if row is None or scene is None:
            continue
        try:
            if matches(app, scene):
                if not row.winfo_manager():
                    row.grid()
            elif row.winfo_manager():
                row.grid_remove()
        except Exception:
            pass
    _schedule_count(app)


def _schedule_count(app: Any) -> None:
    state = getattr(app, "_vl_filter", None)
    if not state or state.get("count_id"):
        return

    def run():
        state["count_id"] = None
        rows = getattr(app, "_scene_rows", None) or []
        shown = sum(1 for s in rows if matches(app, s))
        label = state.get("count_label")
        if label is not None:
            filtered = state.get("pick") != "All" or state.get("query", "").strip()
            label.configure(text=f"{shown} of {len(rows)} scenes" if filtered else f"{len(rows)} scenes")

    try:
        state["count_id"] = app.after(150, run)
    except Exception:
        state["count_id"] = None


def build_filter_bar(app: Any) -> None:
    wrap = getattr(app, "_scenes_wrap", None)
    if wrap is None or getattr(app, "_vl_filter", None):
        return
    state: dict = {"pick": "All", "query": "", "count_id": None}
    app._vl_filter = state
    bar = ctk.CTkFrame(wrap, fg_color="transparent")
    bar.grid_columnconfigure(1, weight=1)
    seg = ctk.CTkSegmentedButton(bar, values=list(FILTERS), height=30, font=ctk.CTkFont(size=12), **segmented_style())
    seg.set("All")
    seg.grid(row=0, column=0, sticky="w")
    state["count_label"] = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="e")
    state["count_label"].grid(row=0, column=1, sticky="e", padx=(12, 10))
    query = ctk.StringVar(value="")
    entry = ctk.CTkEntry(bar, textvariable=query, width=220, height=30, placeholder_text="\u2315  Search scenes",
                         font=ctk.CTkFont(size=12))
    entry.grid(row=0, column=2, sticky="e")

    def on_pick(value: str) -> None:
        state["pick"] = value
        apply_filter(app)

    pending = {"id": None}

    def on_type(*_a) -> None:   # filter once typing pauses, not on every key of a 300-scene plan
        if pending["id"] is not None:
            try:
                app.after_cancel(pending["id"])
            except Exception:
                pass

        def run():
            pending["id"] = None
            state["query"] = query.get()
            apply_filter(app)

        pending["id"] = app.after(200, run)

    seg.configure(command=on_pick)
    query.trace_add("write", on_type)
    entry.bind("<Escape>", lambda _e: query.set(""))
    state["bar"], state["seg"], state["entry"] = bar, seg, entry


def _sync_bar(app: Any) -> None:
    state = getattr(app, "_vl_filter", None)
    if not state:
        return
    bar = state["bar"]
    if getattr(app, "_scene_rows", None):
        bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(10, 6))   # row 1 = the "No scenes yet" cell, never both at once
    else:
        bar.grid_remove()


def install(app: Any) -> None:
    if getattr(app, "_visuals_look_installed", False) or not hasattr(app, "_decorate_scene_row"):
        return
    app._visuals_look_installed = True
    mod = sys.modules.get(type(app).__module__)
    decorate, set_status, header = app._decorate_scene_row, app._set_scene_status, app._build_scene_list_header
    render, window = getattr(app, "_render_scene_rows", None), getattr(app, "_refresh_scene_window", None)
    try:
        build_filter_bar(app)
    except Exception:
        pass

    def decorate_row(i, scene, grid_row=None):
        decorate(i, scene, grid_row)
        try:
            widgets = app._scene_row_widgets.get(mod._scene_key(scene.scene_number))
            if widgets:
                restyle_row(app, widgets)
                state = getattr(app, "_vl_filter", None) or {}
                if state.get("pick", "All") != "All" or state.get("query", "").strip():
                    apply_filter(app, mod._scene_key(scene.scene_number))   # batch-built rows filter as they arrive
        except Exception:
            pass   # the plain row still works

    def paint_status(scene_number, status):
        set_status(scene_number, status)
        try:
            widgets = app._scene_row_widgets.get(mod._scene_key(scene_number)) or {}
            label = widgets.get("status_label")
            if label is not None:
                _pill(label, label.cget("text_color"))
            if (getattr(app, "_vl_filter", None) or {}).get("pick", "All") != "All":
                apply_filter(app, mod._scene_key(scene_number))   # a row that became Ready leaves the Queued view
        except Exception:
            pass

    def build_header():
        header()
        try:
            _restyle_header(app)
        except Exception:
            pass

    def render_rows():
        render()
        try:
            _sync_bar(app)
            apply_filter(app)
        except Exception:
            pass

    def refresh_window(force=False):
        window(force)
        try:
            apply_filter(app)
        except Exception:
            pass

    app._decorate_scene_row = decorate_row
    if callable(render):
        app._render_scene_rows = render_rows
    if callable(window):
        app._refresh_scene_window = refresh_window
    app._set_scene_status = paint_status
    app._build_scene_list_header = build_header
