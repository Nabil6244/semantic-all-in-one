"""The Visual Director page in two screens: the grouped style picker, and the chosen style's own page (a header with the style's
name and a Change style button, then only that style's controls). StarMap Cinema is its own card: the StarMap engine with its Cinema
option on, chosen by the card instead of a switch inside StarMap.

app.py only calls in here (build / layout / sync / picked / StarMap Cinema helpers); the styles' own switches, handlers and
saved state are unchanged."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from . import theme as T
from .style_registry import BUILT_ON, EXPLAINER, STARMAP_CINEMA, grouped
from .widgets import make_button

_RUNNING_FLAGS = ("_overscaled_running", "_pakmap_running", "_hybrid_running", "_starmap_running", "_weather_running", "_whatif_running",
                  "_war_running", "_health_running", "_pt_running")
_CINEMA_TAB_OLD, _CINEMA_TAB_NEW = "Cinema (What If visuals)", "Cinema options"


def build(app: Any, block: Any) -> None:
    """Called once at the end of app._build_style_picker: the page header (hidden until a style is picked) and the Back button."""
    app._style_block = block
    app._style_picker_titles = [w for w in block.winfo_children()
                                if isinstance(w, ctk.CTkLabel) and w.grid_info().get("row") in (1, 2)]
    head = ctk.CTkFrame(block, fg_color="transparent")
    head.grid_columnconfigure(1, weight=1)
    app._style_page_icon = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=22), text_color=T.ACCENT_TEXT, width=36)
    app._style_page_icon.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 8))
    app._style_page_name = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=20, weight="bold"), text_color=T.TEXT, anchor="w")
    app._style_page_name.grid(row=0, column=1, sticky="w")
    app._style_page_blurb = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w", justify="left",
                                         wraplength=640)
    app._style_page_blurb.grid(row=1, column=1, sticky="w", pady=(2, 0))
    app._style_change_btn = make_button(head, "Change style", lambda: change_style(app), size="sm", width=120)
    app._style_change_btn.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(12, 0))
    app._style_page_head = head
    app._style_back_btn = make_button(block, "Back", lambda: back(app), size="sm", width=140)
    app._style_browsing, app._style_browse_auto, app._style_back = True, True, False
    app._style_pages_project = object()   # no project seen yet: the first sync decides


def layout(app: Any, width: int) -> bool:
    """The cards under group titles (General, Maps, Space, ...). Returns True: app._layout_style_cards' flat grid is not used."""
    grid = getattr(app, "_style_grid", None)
    cards = getattr(app, "_style_cards", None)
    if grid is None or not cards:
        return False
    cols = 6 if width >= 1250 else 3 if width >= 620 else 2
    if getattr(app, "_style_grouped_cols", None) == cols:
        return True
    app._style_grouped_cols = cols
    app._style_grid_cols = cols
    for c in range(6):
        grid.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="style" if c < cols else "")
    labels = getattr(app, "_style_group_labels", None)
    if labels is None:
        labels = app._style_group_labels = {}
    row = 0
    for title, names in grouped(cards.keys()):
        lab = labels.get(title)
        if lab is None:
            lab = labels[title] = ctk.CTkLabel(grid, text=title.upper(), font=ctk.CTkFont(size=11, weight="bold"),
                                               text_color=T.TEXT_TERTIARY, anchor="w")
        lab.grid(row=row, column=0, columnspan=cols, sticky="w", padx=6, pady=(10 if row else 2, 0))
        row += 1
        for k, name in enumerate(names):
            cards[name].grid(row=row + k // cols, column=k % cols, sticky="nsew", padx=4, pady=4)
        row += (len(names) + cols - 1) // cols
    return True


def sync(app: Any, active: str) -> None:
    """Called at the end of app._sync_style_picker: the picker or the active style's page, and StarMap Cinema's options."""
    if not hasattr(app, "_style_page_head"):
        return
    ws = getattr(app, "_workspace", None)
    project = getattr(ws, "project_id", None) if ws is not None else None
    if project != app._style_pages_project:   # a project was opened or created: show its style's page (the picker when it has none)
        app._style_pages_project, app._style_browse_auto, app._style_back = project, True, False
    if app._style_browse_auto:
        app._style_browsing = active == "Normal video"
    browsing = app._style_browsing
    for w in app._style_picker_titles:
        w.grid() if browsing else w.grid_remove()
    app._style_grid.grid() if browsing else app._style_grid.grid_remove()
    if browsing:
        app._style_page_head.grid_remove()
        app._style_next.grid_configure(row=0)
        if app._style_back:
            app._style_back_btn.configure(text=f"Back to {active}")
            app._style_back_btn.grid(row=1, column=0, sticky="e", padx=16, pady=(18, 0))
        else:
            app._style_back_btn.grid_remove()
    else:
        app._style_back_btn.grid_remove()
        icon = app.STYLE_CARDS.get(active, ("",))[0]
        app._style_page_icon.configure(text=icon)
        app._style_page_name.configure(text=active)
        app._style_page_blurb.configure(text=app.STYLE_BLURBS.get(active, ""))
        app._style_page_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 0))
        app._style_next.grid_configure(row=1, pady=(12, 16))
    base_block = {STARMAP_CINEMA: "_starmap_block", EXPLAINER: "_hybrid_block"}.get(active)   # the engine's own controls
    if base_block and getattr(app, base_block, None) is not None:
        getattr(app, base_block).grid()
    _sync_starmap_cinema(app, active)
    _sync_hybrid_explainer(app, active)
    try:
        from . import story_motion_section
        story_motion_section.sync(app, active)
    except Exception:
        pass
    _tidy_style_blocks(app)
    from .style_kit import wrap_style
    wrap_style(app, active)


_STYLE_BLOCKS = ("_overscaled_block", "_pakmap_block", "_hybrid_block", "_starmap_block", "_weather_block", "_whatif_block", "_war_block",
                 "_health_block", "_pt_block", "_story_block")


def _tidy_style_blocks(app: Any) -> None:
    """The page header above already names the style and the card chose it: each style card's own title/description and its
    "Use ... for this project" switch would only repeat that."""
    for name in ("_whatif_switch", "_weather_switch"):
        sw = getattr(app, name, None)
        if sw is not None and sw.winfo_manager():
            sw.grid_remove()
    for name in _STYLE_BLOCKS:
        block = getattr(app, name, None)
        if block is None:
            continue
        for w in block.winfo_children():   # _style_card_header: a frame at row 0 holding only the title and description labels
            kids = w.winfo_children()
            if (isinstance(w, ctk.CTkFrame) and w.winfo_manager() == "grid" and w.grid_info().get("row") in (0, "0") and len(kids) == 2
                    and all(isinstance(k, ctk.CTkLabel) for k in kids)):
                w.grid_remove()


def picked(app: Any, choice: str) -> None:
    """A card was clicked: leave the picker for that style's page (the style's own handler does the switching)."""
    app._style_browsing, app._style_browse_auto, app._style_back = False, False, False
    try:
        app.after_idle(app._sync_style_picker)
    except Exception:
        pass


def change_style(app: Any) -> None:
    if any(getattr(app, f, False) for f in _RUNNING_FLAGS):
        from tkinter import messagebox

        messagebox.showinfo("Generation running", "Wait for the current generation to finish before switching style.")
        return
    app._style_browsing, app._style_browse_auto, app._style_back = True, False, True
    app._sync_style_picker()


def back(app: Any) -> None:
    app._style_browsing, app._style_browse_auto, app._style_back = False, False, False
    app._sync_style_picker()


# ---- card-only styles: StarMap Cinema (StarMap + Cinema option) and Explainer (Hybrid Map + Explainer look) --------------------

def _var(app: Any, name: str) -> bool:
    var = getattr(app, name, None)
    try:
        return bool(var is not None and var.get())
    except Exception:
        return False


def active_variant(app: Any, mode: str) -> str:
    """The card-only style the current mode is showing, or ""."""
    if mode == "starmap" and _var(app, "_starmap_cinema_var"):
        return STARMAP_CINEMA
    if mode == "hybrid" and _var(app, "_hybrid_explainer_var"):
        return EXPLAINER
    if mode == "normal" and getattr(app, "_story_motion_active", False):   # ui/story_motion_section.py: per session, nothing saved
        return "Story Motion"
    return ""


def _set_look(app: Any, mode: str, on: bool) -> None:
    """StarMap / StarMap Cinema and Hybrid Map / Explainer share one engine and one plan: only the look option changes."""
    if mode == "starmap" and getattr(app, "_starmap_cinema_var", None) is not None:
        app._starmap_cinema_var.set(bool(on))
        app._save_starmap_cinema()
    elif mode == "hybrid" and getattr(app, "_hybrid_explainer_var", None) is not None:
        app._hybrid_explainer_var.set(bool(on))
        app._on_hybrid_explainer_changed()


_PAIRS = {"StarMap": ("starmap", False), STARMAP_CINEMA: ("starmap", True), "Hybrid Map": ("hybrid", False), EXPLAINER: ("hybrid", True)}


def pick_variant(app: Any, choice: str):
    """-> (choice for the app's own handler, done). Sets the look for StarMap/Hybrid and their card-only styles; when the engine is
    already the active one, switching the look is all there is to do (done=True)."""
    app._story_motion_active = choice == "Story Motion"
    if choice == "Story Motion":   # Normal video with the story pipeline on (ui/story_motion_section.py)
        return ("Normal video", False) if getattr(app, "generation_mode", "normal") != "normal" else (choice, True)
    if choice not in _PAIRS:
        return choice, False
    mode, on = _PAIRS[choice]
    _set_look(app, mode, on)
    if getattr(app, "generation_mode", "normal") == mode:
        return choice, True
    return BUILT_ON.get(choice, choice), False


def _sync_hybrid_explainer(app: Any, active: str) -> None:
    btn = getattr(app, "_hybrid_explainer_btn", None)
    if btn is None:
        return
    if not hasattr(app, "_hybrid_explainer_widgets"):
        app._hybrid_explainer_widgets = [w for w in btn.master.winfo_children() if w.grid_info().get("row") in (2, 3, 4)]
    for w in app._hybrid_explainer_widgets:
        if active == EXPLAINER and not isinstance(w, ctk.CTkSwitch):   # the card is the switch now
            w.grid()
        else:
            w.grid_remove()


def _sync_starmap_cinema(app: Any, active: str) -> None:
    tabs = getattr(app, "_starmap_cinema_tabs", None)
    if tabs is None:
        return
    if active != STARMAP_CINEMA:
        tabs.grid_remove()
        return
    if not getattr(app, "_starmap_cinema_tidied", False):   # the card is the switch now: hide it, and say what the box is
        app._starmap_cinema_tidied = True
        try:
            tabs.rename(_CINEMA_TAB_OLD, _CINEMA_TAB_NEW)
        except Exception:
            pass
        for tab_name in (_CINEMA_TAB_NEW, _CINEMA_TAB_OLD):
            try:
                tab = tabs.tab(tab_name)
            except Exception:
                continue
            for w in tab.winfo_children():
                if isinstance(w, ctk.CTkSwitch):
                    w.grid_remove()
                elif isinstance(w, ctk.CTkLabel) and "Off = Classic StarMap" in str(w.cget("text")):
                    w.configure(text="The What If documentary look on top of StarMap. Untick a box to leave that piece out. "
                                     "For the classic look, pick the StarMap card instead.")
            break
    tabs.grid()
