"""The Visual Director's new look: the style picker as a searchable gallery grouped into families, and a hero header on each style's page.

Plugged in from ui/style_pages.py; app.py is untouched. The workflow hooks stay exactly as they were:
  - app._style_cards keeps one card per style, keyed by the style's real name. Each card still has ._badge and takes
    configure(border_color=..., fg_color=...), which is all app._paint_style_cards uses.
  - a click still calls app._on_style_pick(name), so every style's own activate/deactivate, running-guard and saved state are unchanged.
  - app._style_page_icon / _style_page_name / _style_page_blurb / _style_page_head keep their names (style_pages.sync fills them).
Kids names and types follow docs/KIDS_STYLES_MAP.md (Channel > Style > Type)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk

from . import theme as T
from .style_registry import BUILT_ON
from .widgets import button_style

# (key, title, tint token, styles in order). A style no family names lands in "More", so a new style always shows.
FAMILIES: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("general", "General", "family_general", ("Normal video", "Story Motion", "Modern Tech News", "Overscaled", "Exp Solar")),
    ("history", "History & Maps", "family_history", ("pakMap", "Hybrid Map", "Explainer", "War Documentary", "Aviation", "City Timelapse",
                                                      "Voxel Map", "Roblox Cinema", "Enoch Template")),
    ("space", "Space & Science", "family_space", ("StarMap", "StarMap Cinema", "What If", "Ocean Predators", "Weather", "Health Cinema")),
    ("theory", "Theory Explainers", "family_theory", ("Rep Theory", "Cat Theory", "Carl Jung Theory", "Elder Health Theory", "Survival")),
    ("stories", "Stories & Hosts", "family_stories", ("Toon Tales", "Stickman", "Prepper Host", "Food Files", "Rules Horror")),
    ("kids", "Kids", "family_kids", ("Toy Vehicles", "Kids Stories", "Kids Learn")),
    ("products", "Products & Games", "family_products", ("Product Trailer", "Game Launch")),
)
MORE = ("more", "More", "family_more")

# what the card and the page header call a style when its engine name is not what people know it by (the key stays the real name)
DISPLAY: Dict[str, str] = {"Kids Stories": "Cartoon Shows"}
ENGINE_NOTE: Dict[str, str] = {"Kids Stories": "2D cartoon episodes · the Kids Stories page"}

# the kinds of video a style makes; "(command line)" marks a type that has no app controls yet (shown honestly, not hidden)
TYPES: Dict[str, Tuple[str, ...]] = {
    "Toy Vehicles": ("Colour Songs", "Toy Stories", "Truck Convoy (command line)", "Songs + Stories episode (command line)"),
    "Kids Stories": ("Ch1 Ms Molly · learning journeys, 1–5", "Ch2 Baby Talk with Ms Molly · baby speech, 0–3",
                     "Ch3 Ms Lina · play adventures, 2–6", "Urdu and Punjabi versions"),
    "Kids Learn": ("Lessons: words, numbers, colours, opposites, animals, shapes, letters, feelings",),
}

# family cards that are not styles yet: shown greyed so the family is complete, never clickable
COMING: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "kids": (("☆", "3D Kids Story", "Real 3D cast in Blender. Still being built: no page yet."),),
}

_PAD = 6


def _font(spec) -> ctk.CTkFont:
    return ctk.CTkFont(size=spec[0], weight=spec[1])


def family_of(name: str) -> Tuple[str, str, str]:
    for key, title, tint, names in FAMILIES:
        if name in names:
            return key, title, tint
    return MORE


def display_name(name: str) -> str:
    return DISPLAY.get(name, name)


def _tint(token: str) -> str:
    return T.get_token(token)


def _search_text(app: Any, name: str) -> str:
    icon, pitch, needs, suits = app.STYLE_CARDS.get(name, ("", "", "", ""))
    parts = [name, display_name(name), pitch, needs, suits, family_of(name)[1], " ".join(TYPES.get(name, ())), BUILT_ON.get(name, "")]
    return " ".join(parts).lower()


# ---- the cards ------------------------------------------------------------------------------------------------------------------

def _make_card(app: Any, parent: Any, name: str) -> ctk.CTkFrame:
    icon, pitch, needs, suits = app.STYLE_CARDS.get(name, ("□", "", "", ""))
    _key, family, tint = family_of(name)
    card = ctk.CTkFrame(parent, fg_color=T.BG, corner_radius=T.RADIUS_LG, border_width=2, border_color=T.BORDER, cursor="hand2")
    card.grid_columnconfigure(0, weight=1)

    cover = ctk.CTkFrame(card, fg_color=_tint(tint), corner_radius=T.RADIUS, height=64)
    cover.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 0))
    cover.grid_propagate(False)
    cover.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(cover, text=icon, font=_font(T.FONT_STYLE_ICON), text_color=T.ACCENT_TEXT, width=44).grid(
        row=0, column=0, rowspan=2, sticky="w", padx=(10, 0), pady=6)
    ctk.CTkLabel(cover, text=family.upper(), font=ctk.CTkFont(size=10, weight="bold"), text_color=T.MUTED, anchor="e").grid(
        row=0, column=1, sticky="ne", padx=10, pady=(8, 0))
    badge = ctk.CTkLabel(cover, text="  ✓ Current  ", font=ctk.CTkFont(size=10, weight="bold"), fg_color=T.ACCENT,
                         text_color=T.ACCENT_DARK, corner_radius=8, height=20)
    badge.grid(row=1, column=1, sticky="se", padx=10, pady=(0, 8))
    badge.grid_remove()

    title = ctk.CTkLabel(card, text=display_name(name), font=_font(T.FONT_CARD_TITLE), text_color=T.TEXT, anchor="w")
    title.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 0))
    wrap: List[ctk.CTkLabel] = []
    row = 2
    note = ENGINE_NOTE.get(name) or (f"Built on {BUILT_ON[name]}" if name in BUILT_ON else "")
    if note:
        lab = ctk.CTkLabel(card, text=note, font=_font(T.FONT_METADATA), text_color=T.ACCENT_TEXT, anchor="w", justify="left")
        lab.grid(row=row, column=0, sticky="ew", padx=14, pady=(1, 0))
        wrap.append(lab)
        row += 1
    lab = ctk.CTkLabel(card, text=pitch, font=_font(T.FONT_SECONDARY_LABEL), text_color=T.TEXT, anchor="w", justify="left")
    lab.grid(row=row, column=0, sticky="ew", padx=14, pady=(6, 0))
    wrap.append(lab)
    row += 1
    types = TYPES.get(name)
    if types:
        lab = ctk.CTkLabel(card, text="\n".join("• " + t for t in types), font=_font(T.FONT_METADATA), text_color=T.MUTED,
                           anchor="w", justify="left")
        lab.grid(row=row, column=0, sticky="ew", padx=14, pady=(6, 0))
        wrap.append(lab)
        row += 1
    card.grid_rowconfigure(row, weight=1)   # the needs line sits at the bottom, level across a row of cards
    lab = ctk.CTkLabel(card, text=f"Needs  {needs}", font=_font(T.FONT_METADATA), text_color=T.MUTED, anchor="sw", justify="left")
    lab.grid(row=row, column=0, sticky="sew", padx=14, pady=(8, 12))
    wrap.append(lab)

    def click(_e=None, n=name):
        app._on_style_pick(n)

    def hover(on: bool, c=card, n=name):
        try:
            if app._style_picker.get() != n:
                c.configure(border_color=T.ACCENT_HOV if on else T.BORDER)
        except Exception:
            pass

    def bind_all(w):
        w.bind("<Button-1>", click)
        w.bind("<Enter>", lambda _e: hover(True))
        w.bind("<Leave>", lambda _e: hover(False))
        for child in w.winfo_children():
            bind_all(child)

    bind_all(card)
    try:
        from . import tooltip

        tooltip.attach(card, f"Good for: {suits}")
    except Exception:
        pass
    card._badge = badge  # type: ignore[attr-defined]   # app._paint_style_cards shows it on the current style
    card._wrap = wrap  # type: ignore[attr-defined]
    return card


def _make_coming_card(parent: Any, family_tint: str, icon: str, title: str, text: str) -> ctk.CTkFrame:
    card = ctk.CTkFrame(parent, fg_color=T.PANEL_ALT, corner_radius=T.RADIUS_LG, border_width=1, border_color=T.BORDER)
    card.grid_columnconfigure(0, weight=1)
    cover = ctk.CTkFrame(card, fg_color=_tint(family_tint), corner_radius=T.RADIUS, height=64)
    cover.grid(row=0, column=0, sticky="ew", padx=_PAD, pady=(_PAD, 0))
    cover.grid_propagate(False)
    cover.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(cover, text=icon, font=_font(T.FONT_STYLE_ICON), text_color=T.MUTED, width=44).grid(
        row=0, column=0, rowspan=2, sticky="w", padx=(10, 0), pady=6)
    ctk.CTkLabel(cover, text="COMING", font=ctk.CTkFont(size=10, weight="bold"), text_color=T.MUTED, anchor="e").grid(
        row=0, column=1, sticky="ne", padx=10, pady=(8, 0))
    ctk.CTkLabel(card, text=title, font=_font(T.FONT_CARD_TITLE), text_color=T.MUTED, anchor="w").grid(
        row=1, column=0, sticky="ew", padx=14, pady=(10, 0))
    lab = ctk.CTkLabel(card, text=text, font=_font(T.FONT_SECONDARY_LABEL), text_color=T.MUTED, anchor="w", justify="left")
    lab.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 12))
    card._wrap = [lab]  # type: ignore[attr-defined]
    return card


# ---- the gallery: toolbar + families --------------------------------------------------------------------------------------------

def _build_toolbar(app: Any, grid: Any) -> None:
    bar = ctk.CTkFrame(grid, fg_color="transparent")
    bar.grid_columnconfigure(1, weight=1)
    app._vd_query = ctk.StringVar(value="")
    entry = ctk.CTkEntry(bar, textvariable=app._vd_query, placeholder_text="⌕  Search styles, topics or inputs", width=300,
                         height=T.CONTROL_H, font=_font(T.FONT_BODY))
    entry.grid(row=0, column=0, sticky="w")
    app._vd_search_entry = entry
    app._vd_count = ctk.CTkLabel(bar, text="", font=_font(T.FONT_METADATA), text_color=T.TEXT_TERTIARY, anchor="e")
    app._vd_count.grid(row=0, column=1, sticky="e", padx=(12, 0))
    families = ["All"] + [title for _k, title, _t, _n in FAMILIES]
    app._vd_family = ctk.StringVar(value="All")
    seg = ctk.CTkSegmentedButton(bar, values=families, variable=app._vd_family, font=_font(T.FONT_CONTROL_LABEL), height=T.CONTROL_H_SM,
                                 command=lambda _v: refresh(app))
    seg.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
    app._vd_query.trace_add("write", lambda *_a: refresh(app))
    # Pinned and recent styles, one click away (ui/prefs.py keeps them in settings.json).
    app._vd_quick = ctk.CTkFrame(bar, fg_color="transparent")
    app._vd_quick.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
    app._vd_quick_sig = None
    app._vd_toolbar = bar
    refresh_quick_picks(app)
    app._vd_empty = ctk.CTkLabel(grid, text="No style matches. Clear the search or pick All.", font=_font(T.FONT_BODY), text_color=T.MUTED)


def install(app: Any, block: Any) -> None:
    """Called once from style_pages.build: replace the picker's cards with the new ones (same dict, same keys) and add the toolbar."""
    grid = getattr(app, "_style_grid", None)
    cards = getattr(app, "_style_cards", None)
    if grid is None or cards is None:
        return
    current = None
    try:
        current = app._style_picker.get()
    except Exception:
        pass
    for name in list(cards):
        try:
            cards[name].destroy()
        except Exception:
            pass
        cards[name] = _make_card(app, grid, name)
    app._vd_coming = {fam: [_make_coming_card(grid, next(t for k, _ti, t, _n in FAMILIES if k == fam), *c) for c in items]
                      for fam, items in COMING.items()}
    _build_toolbar(app, grid)
    _restyle_picker_head(app, block)
    _restyle_page_head(app)
    app._vd_installed = True
    if current:
        try:
            app._paint_style_cards(current)
        except Exception:
            pass
    app._style_grouped_cols = None
    refresh(app)


def _restyle_picker_head(app: Any, block: Any) -> None:
    titles = list(getattr(app, "_style_picker_titles", []))
    if titles:
        titles[0].configure(text="Visual Director", font=_font(T.FONT_PAGE_TITLE))
        titles[0].grid_configure(padx=20, pady=(20, 0))
    if len(titles) > 1:
        titles[1].configure(text="Pick the kind of video to make. Each style keeps its own plan, and you can switch any time before "
                                 "rendering.", font=_font(T.FONT_SECONDARY_LABEL))
        titles[1].grid_configure(padx=20)
    grid = app._style_grid
    grid.grid_configure(padx=14, pady=(14, 20))
    nxt = getattr(app, "_style_next", None)
    if nxt is not None:   # the next-step banner: a calm card with an accent edge instead of a bright outline
        nxt.configure(fg_color=T.ACCENT_SEL, border_color=T.ACCENT_BORDER, corner_radius=T.RADIUS_LG)
        nxt.grid_configure(padx=20)


def _restyle_page_head(app: Any) -> None:
    """The chosen style's page: a tinted hero with an icon tile, the name, its family and engine, what it makes and what it needs."""
    head = getattr(app, "_style_page_head", None)
    if head is None:
        return
    head.configure(fg_color=T.get_token("family_general"), corner_radius=T.RADIUS_LG)
    app._style_page_icon.configure(font=_font(T.FONT_STYLE_ICON), width=60, height=60, corner_radius=T.RADIUS_LG, fg_color=T.CARD)
    app._style_page_icon.grid_configure(padx=(16, 14), pady=16, sticky="nw")
    app._style_page_name.configure(font=_font(T.FONT_PAGE_TITLE))
    app._style_page_name.grid_configure(pady=(16, 0))
    app._style_page_blurb.grid_configure(pady=(4, 0))
    app._style_change_btn.grid_configure(padx=16, pady=16)
    app._vd_page_tags = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=10, weight="bold"), text_color=T.MUTED, anchor="w")
    app._vd_page_tags.grid(row=2, column=1, sticky="w", pady=(8, 0))
    app._vd_page_types = ctk.CTkLabel(head, text="", font=_font(T.FONT_METADATA), text_color=T.TEXT, anchor="w", justify="left")
    app._vd_page_types.grid(row=3, column=1, sticky="w", pady=(6, 0))
    app._vd_pin_btn = ctk.CTkButton(head, text="\u2606  Pin", width=80, command=lambda: _toggle_pin(app),
                                    **button_style("ghost", "sm"))
    app._vd_pin_btn.grid(row=2, column=2, sticky="ne", padx=16, pady=(8, 0))
    app._vd_page_needs = ctk.CTkLabel(head, text="", font=_font(T.FONT_METADATA), text_color=T.MUTED, anchor="w", justify="left")
    app._vd_page_needs.grid(row=4, column=1, sticky="w", pady=(6, 16))


def sync_page_head(app: Any, active: str) -> None:
    """Called from style_pages.sync after it filled the header: the family tint, tags, types and needs for this style."""
    if not getattr(app, "_vd_installed", False):
        return
    _key, family, tint = family_of(active)
    try:
        app._style_page_head.configure(fg_color=_tint(tint))
        app._style_page_name.configure(text=display_name(active))
        _icon, _pitch, needs, suits = app.STYLE_CARDS.get(active, ("", "", "", ""))
        tags = [family.upper()]
        if active in ENGINE_NOTE:
            tags.append(ENGINE_NOTE[active].upper())
        elif active in BUILT_ON:
            tags.append(f"BUILT ON {BUILT_ON[active].upper()}")
        app._vd_page_tags.configure(text="   •   ".join(tags))
        types = TYPES.get(active)
        if types:
            app._vd_page_types.configure(text="Makes:  " + "   •   ".join(types))
            app._vd_page_types.grid()
        else:
            app._vd_page_types.grid_remove()
        _paint_pin(app, active)
        app._vd_page_needs.configure(text=f"Needs:  {needs}" + (f"      Good for:  {suits}" if suits else ""))
        width = max(320, app._style_page_head.winfo_width() - 260)
        for lab in (app._style_page_blurb, app._vd_page_types, app._vd_page_needs):
            lab.configure(wraplength=width)
    except Exception:
        pass


def _paint_pin(app: Any, name: str) -> None:
    btn = getattr(app, "_vd_pin_btn", None)
    if btn is None:
        return
    from . import prefs as P

    pinned = name in P.names(app, P.PINNED_KEY)
    try:
        btn.configure(text="\u2605  Pinned" if pinned else "\u2606  Pin", text_color=T.ACCENT_TEXT if pinned else T.MUTED)
    except Exception:
        pass


def _toggle_pin(app: Any) -> None:
    from . import prefs as P

    try:
        name = app._style_picker.get()
    except Exception:
        return
    if not name:
        return
    P.toggle_pinned(app, name)
    _paint_pin(app, name)
    refresh_quick_picks(app)


def refresh_quick_picks(app: Any) -> None:
    """The chip row under the search box: pinned styles (starred) then recent ones. Hidden when there are none yet."""
    row = getattr(app, "_vd_quick", None)
    if row is None:
        return
    from . import prefs as P

    cards = getattr(app, "_style_cards", {}) or {}
    pinned = [n for n in P.names(app, P.PINNED_KEY) if n in cards]
    recent = [n for n in P.names(app, P.RECENT_KEY) if n in cards and n not in pinned]
    picks = (pinned + recent)[:8]
    sig = (tuple(picks), tuple(pinned))
    if getattr(app, "_vd_quick_sig", None) == sig:
        return
    app._vd_quick_sig = sig
    for child in row.winfo_children():
        child.destroy()
    if not picks:
        row.grid_remove()
        return
    row.grid()
    ctk.CTkLabel(row, text="QUICK PICK", font=ctk.CTkFont(size=10, weight="bold"), text_color=T.TEXT_TERTIARY).grid(
        row=0, column=0, padx=(2, 10))
    style = button_style("secondary", "sm")
    style.update(corner_radius=13, height=26)
    for i, name in enumerate(picks, start=1):
        text = ("\u2605  " if name in pinned else "") + display_name(name)
        ctk.CTkButton(row, text=text, width=40, command=lambda n=name: app._on_style_pick(n), **style).grid(
            row=0, column=i, padx=(0, 6))


def _visible(app: Any) -> List[Tuple[str, str, List[Any]]]:
    """(family title, tint, widgets) for each family with something to show under the current search and family filter."""
    cards = app._style_cards
    query = (app._vd_query.get() if hasattr(app, "_vd_query") else "").strip().lower()
    fam_pick = app._vd_family.get() if hasattr(app, "_vd_family") else "All"
    placed = set()
    out = []
    groups = [(k, title, tint, tuple(n for n in names if n in cards)) for k, title, tint, names in FAMILIES]
    for _k, _t, _ti, names in groups:
        placed.update(names)
    more = tuple(n for n in cards if n not in placed)
    if more:
        groups.append((MORE[0], MORE[1], MORE[2], more))
    words = query.split()
    for key, title, tint, names in groups:
        if fam_pick != "All" and fam_pick != title:
            continue
        shown: List[Any] = [cards[n] for n in names if all(w in _search_text(app, n) for w in words)]
        if not words:
            shown += getattr(app, "_vd_coming", {}).get(key, [])
        if shown:
            out.append((title, tint, shown))
    return out


def refresh(app: Any) -> None:
    app._style_grouped_cols = None
    try:
        layout(app, app._style_grid.winfo_width())
    except Exception:
        pass


def layout(app: Any, width: int) -> bool:
    """Lay the gallery out for this width: toolbar, then each family's title and its cards. True = handled (the old flat grid is unused)."""
    if not getattr(app, "_vd_installed", False):
        return False
    grid = app._style_grid
    if not _view_shown(grid):
        # Hidden page (the app opens on another one): the grid's width is then its own cards' width, so wrapping the
        # cards to it shrank them, which shrank the grid, which wrapped them again: ~110 relayouts over ~6 s of lag
        # after the window opened (2026-11-23). Lay out for a fixed width until the page is shown with its real width.
        width = 1100
    width = width if width and width > 50 else 1100
    cols = 4 if width >= 1060 else 3 if width >= 760 else 2
    key = (cols, app._vd_query.get(), app._vd_family.get())
    if getattr(app, "_style_grouped_cols", None) == key:
        _wrap_cards(app, width, cols)
        return True
    app._style_grouped_cols = key
    app._style_grid_cols = cols
    for c in range(6):
        grid.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="vdstyle" if c < cols else "")
    for w in list(app._style_cards.values()) + [c for cs in getattr(app, "_vd_coming", {}).values() for c in cs]:
        w.grid_remove()
    labels = getattr(app, "_style_group_labels", None)
    if labels is None:
        labels = app._style_group_labels = {}
    for lab in labels.values():
        lab.grid_remove()
    app._vd_empty.grid_remove()
    app._vd_toolbar.grid(row=0, column=0, columnspan=cols, sticky="ew", padx=4, pady=(0, 6))
    row = 1
    groups = _visible(app)
    total = sum(1 for _t, _ti, ws in groups for w in ws if w in app._style_cards.values())
    app._vd_count.configure(text=f"{total} of {len(app._style_cards)} styles")
    for title, tint, widgets in groups:
        lab = labels.get(title)
        if lab is None:
            lab = labels[title] = ctk.CTkLabel(grid, text="", font=_font(T.FONT_SECTION_TITLE), text_color=T.TEXT_TERTIARY, anchor="w")
        n = sum(1 for w in widgets if w in app._style_cards.values())
        lab.configure(text=f"{title.upper()}   ·   {n}")
        lab.grid(row=row, column=0, columnspan=cols, sticky="w", padx=6, pady=(18 if row > 1 else 8, 2))
        row += 1
        for k, w in enumerate(widgets):
            w.grid(row=row + k // cols, column=k % cols, sticky="nsew", padx=5, pady=5)
        row += (len(widgets) + cols - 1) // cols
    if not groups:
        app._vd_empty.grid(row=row, column=0, columnspan=cols, pady=40)
    _wrap_cards(app, width, cols)
    return True


def _view_shown(grid: Any) -> bool:
    """True when the scroll area holding the gallery is on screen with a real width (it sets the grid's width then)."""
    import tkinter

    w = grid
    try:
        while w is not None:
            if isinstance(w, tkinter.Canvas):
                return bool(w.winfo_ismapped()) and w.winfo_width() > 50
            w = w.master
    except Exception:
        return True
    return True


def _wrap_cards(app: Any, width: int, cols: int) -> None:
    """Re-wrap the card texts for this width, once the width has settled. Re-wrapping on every resize event made each
    card change size, which resized the grid again: ~20 rounds and 125k resize events froze the window for ~5 s while
    it opened (2026-11-23). Now one re-wrap runs 120 ms after the last width change, snapped to 8 px steps."""
    pending = getattr(app, "_vd_wrap_after", None)
    if pending is not None:
        try:
            app.after_cancel(pending)
        except Exception:
            pass

    def run():
        app._vd_wrap_after = None
        _apply_wrap(app, width, cols)

    try:
        app._vd_wrap_after = app.after(120, run)
    except Exception:
        _apply_wrap(app, width, cols)


def _apply_wrap(app: Any, width: int, cols: int) -> None:
    card_w = max(160, int((width - 10 * cols) / cols))
    wl = (card_w - 32) // 8 * 8
    if getattr(app, "_vd_wrap", None) == wl:
        return
    app._vd_wrap = wl
    for w in list(app._style_cards.values()) + [c for cs in getattr(app, "_vd_coming", {}).values() for c in cs]:
        for lab in getattr(w, "_wrap", ()):
            try:
                lab.configure(wraplength=wl)
            except Exception:
                pass
