"""View frames for the production workstation (read existing controller state only)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk

from . import theme as T
from .widgets import (
    Card,
    Divider,
    EmptyState,
    MetricRow,
    SectionHeader,
    SectionLabel,
    StatTile,
    StatusPill,
    make_button,
    segmented_style,
    switch_style,
)


class _BaseView(ctk.CTkFrame):
    """A page: header row (whatever the subclass grids at row 0) above one
    scrolling body. On wide windows both are held to a readable measure
    (T.CONTENT_MAX_W) and centred, so labels and values never drift to
    opposite edges of a 2,000 px screen."""

    key = "base"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, fg_color=T.PANEL_ALT, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=T.BORDER, scrollbar_button_hover_color=T.BORDER_STRONG,
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(0, 6))
        self._scroll.grid_columnconfigure(0, weight=1)
        self._body = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._body.grid(row=0, column=0, sticky="ew", padx=T.PAD_LG, pady=(0, T.PAD_LG))
        self._body.grid_columnconfigure(0, weight=1)
        self.content = self._body  # alias for legacy builders
        self._side_pad = None
        self.bind("<Configure>", self._fit_measure, add="+")

    def _fit_measure(self, event=None) -> None:
        width = int(getattr(event, "width", 0) or self.winfo_width())
        if width <= 1:
            return
        side = max(T.PAD_LG + 8, (width - T.CONTENT_MAX_W) // 2)
        if side == self._side_pad:
            return
        self._side_pad = side
        for child in self.grid_slaves(row=0):
            try:
                child.grid_configure(padx=side, pady=(22, 14))
            except Exception:
                pass
        # The scroll frame spans the full width (scrollbar at the window
        # edge); only its content is inset.
        self._body.grid_configure(padx=(max(0, side - 4), max(0, side - 12)))

    def on_show(self) -> None:
        """Refresh read-only displays. Never trigger production work."""
        pass


class ProjectView(_BaseView):
    """Overview: where the project stands and the one thing to do next."""

    key = "project"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        self._header = SectionHeader(self, "Overview", "Where this project stands, and what to do next.")
        self._header.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8))
        self._empty = EmptyState(
            self._body,
            "No project open",
            "Create a project or open an existing one to start planning scenes, generating visuals and rendering.",
            "Choose project",
            command=app._open_project_picker,
            icon="\u2302",
        )
        self._empty.grid(row=0, column=0, sticky="ew", pady=(24, 8))

        self._panel = ctk.CTkFrame(self._body, fg_color="transparent")
        self._panel.grid(row=1, column=0, sticky="ew")
        self._panel.grid_columnconfigure(0, weight=1)

        nxt = ctk.CTkFrame(self._panel, fg_color=T.ACCENT_SEL, corner_radius=T.RADIUS_LG,
                           border_width=1, border_color=T.ACCENT_BORDER)
        nxt.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        nxt.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(nxt, text="NEXT STEP", font=ctk.CTkFont(size=11, weight="bold"), text_color=T.ACCENT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(14, 0))
        ctk.CTkLabel(nxt, textvariable=app.hint_var, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=T.TEXT, anchor="w", justify="left", wraplength=620).grid(
            row=1, column=0, sticky="w", padx=18, pady=(2, 14))
        self._next_btn = make_button(nxt, "Continue", app._on_primary_cta, variant="primary", size="lg", width=170)
        self._next_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=18)

        tiles = ctk.CTkFrame(self._panel, fg_color="transparent")
        tiles.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        tiles.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="overview_tiles")
        self._tile_scenes = StatTile(tiles, "Visuals")
        self._tile_scenes.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._tile_voice = StatTile(tiles, "Voiceover")
        self._tile_voice.grid(row=0, column=1, sticky="ew", padx=6)
        self._tile_sound = StatTile(tiles, "Sound design")
        self._tile_sound.grid(row=0, column=2, sticky="ew", padx=6)
        self._tile_qa = StatTile(tiles, "Quality score")
        self._tile_qa.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        details = Card(self._panel, title="Project details")
        details.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self._metrics: list[MetricRow] = []
        for i, label in enumerate(("Project", "Narration", "Scenes", "Visual assets", "Ambience", "SFX",
                                   "Music", "Editorial score", "Last render")):
            row = MetricRow(details.body, label)
            row.grid(row=i, column=0, sticky="ew", pady=2)
            self._metrics.append(row)

        jump = Card(self._panel, title="Jump to")
        jump.grid(row=3, column=0, sticky="ew")
        links = ctk.CTkFrame(jump.body, fg_color="transparent")
        links.grid(row=0, column=0, sticky="w")
        for key, label in (("script", "Script"), ("visual_plan", "Visuals"), ("audio", "Audio & Effects"),
                           ("render", "Export")):
            make_button(links, f"{T.NAV_ICONS.get(key, '')}  {label}",
                        lambda k=key: app._shell.navigate(k) if getattr(app, "_shell", None) else None,
                        width=140).pack(side="left", padx=(0, 8))

    def on_show(self) -> None:
        ws = self.app._workspace
        if ws is None:
            self._empty.grid()
            self._panel.grid_remove()
            return
        self._empty.grid_remove()
        self._panel.grid()
        cta = getattr(self.app, "generate_btn", None)
        if cta is not None:
            try:
                self._next_btn.configure(text=cta.cget("text"), state=cta.cget("state"))
            except Exception:
                pass
        audio = self.app.audio_var.get().strip()
        audio_ok = bool(audio) and Path(audio).is_file()
        n_scenes = len(getattr(self.app, "_scene_rows", None) or [])
        snap = None
        try:
            if n_scenes:
                snap = self.app._qa_snapshot()
        except Exception:
            snap = None
        ready = getattr(snap, "ready", 0) if snap else 0
        total = getattr(snap, "total", n_scenes) if snap else n_scenes
        needs = getattr(snap, "needs_action", 0) if snap else 0
        ep = _load_json(ws.state_dir / "editorial_plan.json")
        qa = _load_json(ws.state_dir / "editorial_qa.json")
        beds = 0
        sfx = 0
        se = _load_json(ws.state_dir / "smart_editing.json")
        if se:
            plan = se.get("plan") or {}
            beds = len(plan.get("scene_ambience") or [])
            sfx = len(plan.get("sfx_events") or [])
        music = "None"
        if self.app.bg_var.get().strip() and Path(self.app.bg_var.get().strip()).is_file():
            music = Path(self.app.bg_var.get().strip()).name
        elif (ep.get("music") or {}).get("enabled"):
            music = "Ducked / planned"
        score = qa.get("score")
        verdict = qa.get("verdict") or "—"
        out = self.app._last_output or self.app.output_var.get() or "—"
        vals = [
            ws.title,
            Path(audio).name if audio_ok else "Not loaded",
            str(n_scenes) if n_scenes else "—",
            f"{ready}/{total}" if total else "—",
            f"{beds} beds" if beds else "—",
            f"{sfx} events" if sfx else "—",
            music,
            f"{score:.0f} {verdict}" if isinstance(score, (int, float)) else "—",
            Path(out).name if out and out != "—" else "—",
        ]
        for row, val in zip(self._metrics, vals):
            row.set_value(val)
        self._header.set_title(ws.title or "Overview")
        if total:
            self._tile_scenes.set(f"{ready}/{total}", f"{needs} need attention" if needs else "scenes ready",
                                  "fail" if needs else ("ok" if ready >= total else "warn"))
        else:
            self._tile_scenes.set("—", "No scenes yet")
        self._tile_voice.set("Loaded" if audio_ok else "Missing",
                             Path(audio).name[:28] if audio_ok else "Needed before render",
                             "ok" if audio_ok else "warn")
        if sfx or beds:
            self._tile_sound.set(f"{sfx + beds}", f"{sfx} sound effects \u00B7 {beds} ambience beds")
        else:
            self._tile_sound.set("—", "Planned at render")
        if isinstance(score, (int, float)):
            tone = "ok" if verdict == "PASS" else ("warn" if verdict == "WARN" else "fail")
            self._tile_qa.set(f"{score:.0f}", str(verdict), tone)
        else:
            self._tile_qa.set("—", "After the first render")


class ScriptView(ctk.CTkFrame):
    """Script input (paste / CSV / VO-aware) built by app._build_left_sections
    into ``self.content``. One scroll only — no nested scrollables."""

    key = "script"

    # app._stepper_index 0..4 -> these steps.
    STEPS = ("Script", "Scenes", "Visuals", "Voiceover", "Export")

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, fg_color=T.PANEL_ALT, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._header = SectionHeader(
            self, "Script", "Paste a narration script, import a visual-plan CSV, or plan from a voiceover.",
        )
        self._header.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(22, 10))
        self._workflow = ctk.CTkFrame(self, fg_color="transparent")
        self._workflow.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=(0, 10))
        self._step_labels = []
        self._step_badges = []
        for i, name in enumerate(self.STEPS):
            if i:
                ctk.CTkFrame(self._workflow, fg_color=T.BORDER, height=1, width=28, corner_radius=0).pack(
                    side="left", padx=8)
            badge = ctk.CTkLabel(
                self._workflow, text=str(i + 1), width=22, height=22, corner_radius=11,
                fg_color=T.CARD_HOVER, text_color=T.MUTED, font=ctk.CTkFont(size=11, weight="bold"),
            )
            badge.pack(side="left", padx=(0, 6))
            lbl = ctk.CTkLabel(
                self._workflow, text=name, font=ctk.CTkFont(size=12), text_color=T.MUTED,
            )
            lbl.pack(side="left")
            self._step_badges.append(badge)
            self._step_labels.append(lbl)
        # Plain host — _build_left_sections adds its own CTkScrollableFrame
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew", padx=0, pady=(0, T.PAD_SM))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self._side_pad = None
        self.bind("<Configure>", self._fit_measure, add="+")

    def _fit_measure(self, event=None) -> None:
        width = int(getattr(event, "width", 0) or self.winfo_width())
        if width <= 1:
            return
        side = max(T.PAD_LG + 8, (width - T.CONTENT_MAX_W) // 2)
        if side == self._side_pad:
            return
        self._side_pad = side
        self._header.grid_configure(padx=side)
        self._workflow.grid_configure(padx=side)
        self.content.grid_configure(padx=(max(0, side - 16), max(0, side - 20)))

    def on_show(self) -> None:
        idx = int(getattr(self.app, "_stepper_index", 0) or 0)
        for i, (badge, lbl) in enumerate(zip(self._step_badges, self._step_labels)):
            if i < idx:
                badge.configure(text="\u2713", fg_color=T.SUCCESS_BG, text_color=T.SUCCESS)
                lbl.configure(text_color=T.TEXT, font=ctk.CTkFont(size=12))
            elif i == idx:
                badge.configure(text=str(i + 1), fg_color=T.ACCENT, text_color=T.ACCENT_DARK)
                lbl.configure(text_color=T.TEXT, font=ctk.CTkFont(size=12, weight="bold"))
            else:
                badge.configure(text=str(i + 1), fg_color=T.CARD_HOVER, text_color=T.MUTED)
                lbl.configure(text_color=T.MUTED, font=ctk.CTkFont(size=12))


class BrandStyleView(_BaseView):
    """Compact Brand Kit + Video Style controls (no giant form)."""

    key = "brand_style"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(
            self, "Brand & Style", "Channel identity + production language",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD_SM, 4))

        form = Card(self._body)
        form.grid(row=0, column=0, sticky="ew", pady=4)
        form.grid_columnconfigure(1, weight=1)
        self._form = form

        # Brand Kit: explicit Off/On — optional; picker only when On
        ctk.CTkLabel(form, text="Brand Kit", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="w", padx=T.PAD, pady=(10, 4)
        )
        self._brand_enabled = ctk.BooleanVar(value=False)
        self._brand_switch = ctk.CTkSwitch(
            form,
            text="Off",
            variable=self._brand_enabled,
            onvalue=True,
            offvalue=False,
            command=self._on_brand_toggle,
            
            font=ctk.CTkFont(size=12),
        )
        self._brand_switch.grid(row=0, column=1, sticky="w", padx=T.PAD, pady=(10, 4))

        self._brand_kit_label = ctk.CTkLabel(
            form, text="Kit", text_color=T.MUTED, font=ctk.CTkFont(size=12),
        )
        self._brand_var = ctk.StringVar(value="Default")
        self._brand_menu = ctk.CTkOptionMenu(
            form, variable=self._brand_var, values=["Default"],
            command=lambda _v: self._on_selection_changed(),
        )

        ctk.CTkLabel(form, text="Video Style", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, sticky="w", padx=T.PAD, pady=4
        )
        self._mode_var = ctk.StringVar(value="Legacy (unchanged)")
        self._mode_menu = ctk.CTkOptionMenu(
            form,
            variable=self._mode_var,
            values=["Legacy (unchanged)", "Auto", "Manual", "Custom"],
            command=lambda _v: self._on_mode_changed(),
        )
        self._mode_menu.grid(row=2, column=1, sticky="ew", padx=T.PAD, pady=4)

        self._style_label = ctk.CTkLabel(
            form, text="Style", text_color=T.MUTED, font=ctk.CTkFont(size=12),
        )
        self._style_label.grid(row=3, column=0, sticky="w", padx=T.PAD, pady=4)
        self._style_var = ctk.StringVar(value="—")
        self._style_menu = ctk.CTkOptionMenu(
            form, variable=self._style_var, values=["—"],
            command=lambda _v: self._on_selection_changed(),
        )
        self._style_menu.grid(row=3, column=1, sticky="ew", padx=T.PAD, pady=4)

        self._hint = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED,
            justify="left", anchor="w",
        )
        self._hint.grid(row=4, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(0, 6))

        ctk.CTkLabel(form, text="Visual Preset", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=5, column=0, sticky="w", padx=T.PAD, pady=4
        )
        from visual_allocation.models import ALLOCATION_PRESET_LABELS

        self._alloc_preset_var = ctk.StringVar(value="Custom")
        self._alloc_preset_menu = ctk.CTkOptionMenu(
            form,
            variable=self._alloc_preset_var,
            values=list(ALLOCATION_PRESET_LABELS),
            command=lambda _v: self._on_allocation_preset_changed(),
        )
        self._alloc_preset_menu.grid(row=5, column=1, sticky="ew", padx=T.PAD, pady=4)

        ctk.CTkLabel(form, text="Visual Strategy", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=6, column=0, sticky="w", padx=T.PAD, pady=4
        )
        self._visual_strategy_var = ctk.StringVar(value="Automatic")
        self._visual_strategy_menu = ctk.CTkOptionMenu(
            form,
            variable=self._visual_strategy_var,
            values=["Automatic", "Video Heavy", "Balanced", "Image Heavy"],
            command=lambda _v: self._on_allocation_changed(),
        )
        self._visual_strategy_menu.grid(row=6, column=1, sticky="ew", padx=T.PAD, pady=4)

        ctk.CTkLabel(form, text="Flow Video Budget", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=7, column=0, sticky="w", padx=T.PAD, pady=4
        )
        self._ai_budget_var = ctk.StringVar(value="Normal")
        self._ai_budget_menu = ctk.CTkOptionMenu(
            form,
            variable=self._ai_budget_var,
            values=["Conservative", "Normal", "High", "Custom"],
            command=lambda _v: self._on_allocation_changed(),
        )
        self._ai_budget_menu.grid(row=7, column=1, sticky="ew", padx=T.PAD, pady=4)

        ctk.CTkLabel(form, text="Visual Coverage", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=8, column=0, sticky="w", padx=T.PAD, pady=(4, 4)
        )
        self._coverage_mode_var = ctk.StringVar(value="Automatic")
        self._coverage_mode_menu = ctk.CTkOptionMenu(
            form,
            variable=self._coverage_mode_var,
            values=["Automatic", "Minimize Repetition", "Cinematic Coverage", "Maximum Motion"],
            command=lambda _v: self._on_allocation_changed(),
        )
        self._coverage_mode_menu.grid(row=8, column=1, sticky="ew", padx=T.PAD, pady=(4, 4))

        self._alloc_preview = ctk.CTkLabel(
            form,
            text="Estimated mix: paste a script to preview. Flow images are free (not counted against video budget).",
            font=ctk.CTkFont(size=11),
            text_color=T.MUTED,
            justify="left",
            anchor="w",
        )
        self._alloc_preview.grid(row=9, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(0, 10))

        self._preview = Card(self._body)
        self._preview.grid(row=1, column=0, sticky="ew", pady=8)
        self._preview_title = ctk.CTkLabel(
            self._preview, text="STYLE", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T.MUTED, anchor="w",
        )
        self._preview_title.pack(anchor="w", padx=T.PAD, pady=(T.PAD, 0))
        self._preview_name = ctk.CTkLabel(
            self._preview, text="—", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=T.TEXT, anchor="w",
        )
        self._preview_name.pack(anchor="w", padx=T.PAD, pady=(2, 4))
        self._preview_body = ctk.CTkLabel(
            self._preview, text="", font=ctk.CTkFont(size=12), text_color=T.MUTED,
            justify="left", anchor="w",
        )
        self._preview_body.pack(anchor="w", padx=T.PAD, pady=(0, T.PAD))

        self._auto_card = Card(self._body)
        self._auto_card.grid(row=2, column=0, sticky="ew", pady=4)
        self._auto_line = ctk.CTkLabel(
            self._auto_card, text="", font=ctk.CTkFont(size=12), text_color=T.TEXT,
            justify="left", anchor="w",
        )
        self._auto_line.pack(anchor="w", padx=T.PAD, pady=(T.PAD, 4))
        btns = ctk.CTkFrame(self._auto_card, fg_color="transparent")
        btns.pack(anchor="w", padx=T.PAD, pady=(0, T.PAD))
        ctk.CTkButton(
            btns, text="Keep Auto", height=28, width=100,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._keep_auto,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btns, text="Choose Another", height=28, width=120,
            fg_color="transparent", border_width=1, border_color=T.BORDER,
            text_color=T.TEXT, hover_color=T.CARD_HOVER, font=ctk.CTkFont(size=12),
            command=self._switch_to_manual,
        ).pack(side="left")
        self._auto_card.grid_remove()

        self._id_by_brand_label: dict[str, str] = {}
        self._id_by_style_label: dict[str, str] = {}
        self._label_by_style_id: dict[str, str] = {}
        self._syncing = False

    def _refresh_menus(self) -> None:
        from style_engine import brand_choices, style_choices

        brands = [(name, sid) for sid, name in brand_choices()]
        if not brands:
            brands = [("Default", "default")]
        self._id_by_brand_label = {label: kid for label, kid in brands}
        self._brand_menu.configure(values=[b[0] for b in brands])

        styles = style_choices()
        self._id_by_style_label = {name: sid for sid, name in styles}
        self._label_by_style_id = {sid: name for sid, name in styles}
        labels = [name for sid, name in styles] or ["—"]
        self._style_menu.configure(values=labels)

    def _set_brand_ui_visible(self, on: bool) -> None:
        self._brand_switch.configure(text="On" if on else "Off")
        if on:
            self._brand_kit_label.grid(row=1, column=0, sticky="w", padx=T.PAD, pady=4)
            self._brand_menu.grid(row=1, column=1, sticky="ew", padx=T.PAD, pady=4)
        else:
            self._brand_kit_label.grid_remove()
            self._brand_menu.grid_remove()

    def _update_hint(self, mode: str) -> None:
        brand_on = bool(self._brand_enabled.get())
        if not mode:
            self._hint.configure(
                text="Legacy: Brand Kit and Video Style are unused. Existing behavior is preserved."
            )
        elif mode == "custom" and not brand_on:
            self._hint.configure(
                text="Custom applies brand overrides onto a base style — turn Brand Kit On, or use Manual."
            )
        elif mode == "custom" and brand_on:
            self._hint.configure(text="Custom: selected style + Brand Kit overrides.")
        elif mode == "auto":
            self._hint.configure(text="Auto picks a style from the script. Brand Kit is optional.")
        elif mode == "manual":
            self._hint.configure(text="Manual: you choose the style. Brand Kit is optional.")
        else:
            self._hint.configure(text="")

    def on_show(self) -> None:
        self._syncing = True
        try:
            self._refresh_menus()
            ws = self.app._workspace
            if ws is None:
                self._preview_name.configure(text="No project")
                self._preview_body.configure(text="Choose a project from the top bar.")
                self._auto_card.grid_remove()
                self._set_brand_ui_visible(False)
                self._hint.configure(text="")
                return
            vs = ws.video_style_settings()
            mode = str(vs.get("mode") or "")
            mode_label = {
                "": "Legacy (unchanged)",
                "auto": "Auto",
                "manual": "Manual",
                "custom": "Custom",
            }.get(mode, "Legacy (unchanged)")
            self._mode_var.set(mode_label)

            brand_id = str(vs.get("brand_kit_id") or "").strip()
            brand_on = bool(brand_id) and mode != ""
            self._brand_enabled.set(brand_on)
            self._set_brand_ui_visible(brand_on and mode != "")
            if brand_id and brand_id in {v for v in self._id_by_brand_label.values()}:
                label = next(
                    (lab for lab, kid in self._id_by_brand_label.items() if kid == brand_id),
                    next(iter(self._id_by_brand_label)),
                )
                self._brand_var.set(label)
            elif self._id_by_brand_label:
                self._brand_var.set(next(iter(self._id_by_brand_label)))

            sid = vs.get("style_id") or ""
            if sid and sid in self._label_by_style_id:
                self._style_var.set(self._label_by_style_id[sid])
            elif self._label_by_style_id:
                self._style_var.set(next(iter(self._label_by_style_id.values())))

            from visual_allocation.settings import load_allocation_settings

            alloc = load_allocation_settings(ws)
            rev_strat = {
                "automatic": "Automatic",
                "video_heavy": "Video Heavy",
                "balanced": "Balanced",
                "image_heavy": "Image Heavy",
            }
            rev_budget = {
                "conservative": "Conservative",
                "normal": "Normal",
                "high": "High",
                "custom": "Custom",
            }
            rev_cov = {
                "automatic": "Automatic",
                "minimize_repetition": "Minimize Repetition",
                "cinematic_coverage": "Cinematic Coverage",
                "maximum_motion": "Maximum Motion",
            }
            self._visual_strategy_var.set(rev_strat.get(alloc.visual_strategy, "Automatic"))
            self._ai_budget_var.set(rev_budget.get(alloc.ai_video_budget, "Normal"))
            self._coverage_mode_var.set(rev_cov.get(alloc.coverage_mode, "Automatic"))

            self._update_style_menu_state(mode)
            self._update_hint(mode)
            self._refresh_preview_and_auto(mode=mode, persist_auto=mode == "auto")
            self._refresh_allocation_preview()
        finally:
            self._syncing = False

    def _update_style_menu_state(self, mode: str) -> None:
        # Style picker: Manual/Custom always; Auto optional pin; Legacy unused
        enabled = mode in ("manual", "custom", "auto")
        state = "normal" if enabled else "disabled"
        try:
            self._style_menu.configure(state=state)
        except Exception:
            pass
        try:
            self._brand_switch.configure(state="normal" if mode else "disabled")
        except Exception:
            pass
        if not mode:
            self._set_brand_ui_visible(False)

    def _refresh_preview_and_auto(self, *, mode: str, persist_auto: bool = False) -> None:
        """Preview always matches the Style dropdown (or Auto detection)."""
        ws = self.app._workspace
        if ws is None:
            return
        self._update_preview_from_selection(mode=mode)

        resolved = None
        if mode == "auto":
            try:
                need_persist = persist_auto and not ws.style_resolution()
                resolved = self.app._resolve_project_style(persist=need_persist)
            except Exception:
                resolved = None
            # Keep Style menu in sync with what Auto is actually using
            if resolved is not None:
                applied = resolved.style_id
                if applied in self._label_by_style_id:
                    self._style_var.set(self._label_by_style_id[applied])
                self._render_style_preview(resolved.style)

        res_meta = ws.style_resolution() if ws else {}
        if mode == "auto" and (resolved or res_meta):
            conf = (resolved.confidence if resolved else res_meta.get("confidence")) or 0
            reason = (resolved.reason if resolved else res_meta.get("reason")) or ""
            detected = (
                (resolved.detected_style_id if resolved else None)
                or res_meta.get("detected_style_id")
                or res_meta.get("style_id")
                or "—"
            )
            name = self._label_by_style_id.get(str(detected), str(detected))
            alts = []
            if resolved is not None:
                alts = list(resolved.alternatives or [])
            elif isinstance(res_meta.get("alternatives"), list):
                alts = list(res_meta.get("alternatives") or [])
            alt_line = ""
            if alts:
                a0 = alts[0]
                aid = str(a0.get("style_id") or "")
                ascore = float(a0.get("score") or 0)
                aname = self._label_by_style_id.get(aid, aid)
                alt_line = f"\nAlternative: {aname} — {ascore * 100:.0f}%"
            self._auto_line.configure(
                text=(
                    f"VIDEO STYLE  AUTO\n"
                    f"Detected: {name}\n"
                    f"Confidence: {float(conf) * 100:.0f}%\n"
                    f"Why: {reason}"
                    f"{alt_line}"
                )
            )
            self._auto_card.grid()
        else:
            self._auto_card.grid_remove()

    def _update_preview_from_selection(self, *, mode: str) -> None:
        if not mode:
            self._preview_name.configure(text="Legacy heuristics")
            self._preview_body.configure(
                text="No Brand Kit / Video Style set.\nExisting automatic editorial behavior is preserved."
            )
            return
        sid = self._id_by_style_label.get(self._style_var.get()) or ""
        if not sid:
            self._preview_name.configure(text="—")
            self._preview_body.configure(text="Select a style to preview.")
            return
        try:
            from style_engine import load_style

            st = load_style(sid)
        except Exception:
            st = None
        if st is None:
            self._preview_name.configure(text="—")
            self._preview_body.configure(text="Style not found.")
            return
        self._render_style_preview(st)

    def _render_style_preview(self, st) -> None:
        intel = st.intelligence
        best = ", ".join(st.identity.best_for[:3]) if st.identity.best_for else "—"
        visual = intel.preview_visual or (", ".join(st.visual.camera.preferred[:3]) or "—")
        camera = intel.preview_camera or f"intensity {st.visual.camera.intensity:.2f}"
        pacing = intel.preview_pacing or f"{st.pacing.default} → hook {st.pacing.hook}"
        audio = intel.preview_audio or (
            f"Amb {st.audio.ambience_intensity:.2f} · SFX {st.audio.sfx_intensity:.2f}"
        )
        self._preview_name.configure(text=st.name.upper())
        self._preview_body.configure(
            text=(
                f"Visual\n{visual}\n\n"
                f"Camera\n{camera}\n\n"
                f"Pacing\n{pacing}\n\n"
                f"Audio\n{audio}\n\n"
                f"Best for\n{best}"
            )
        )

    def _mode_token(self) -> str:
        return {
            "Legacy (unchanged)": "",
            "Auto": "auto",
            "Manual": "manual",
            "Custom": "custom",
        }.get(self._mode_var.get(), "")

    def _on_brand_toggle(self) -> None:
        if self._syncing:
            return
        mode = self._mode_token()
        on = bool(self._brand_enabled.get())
        if not mode and on:
            # Turning brand on in Legacy → switch to Manual so settings are used
            self._mode_var.set("Manual")
            mode = "manual"
        self._set_brand_ui_visible(on and bool(mode))
        if on and self._id_by_brand_label and self._brand_var.get() not in self._id_by_brand_label:
            self._brand_var.set(next(iter(self._id_by_brand_label)))
        self._save_from_ui()
        self._update_hint(self._mode_token())
        self._refresh_preview_and_auto(mode=self._mode_token())

    def _on_mode_changed(self) -> None:
        if self._syncing:
            return
        mode = self._mode_token()
        if not mode:
            self._brand_enabled.set(False)
            self._set_brand_ui_visible(False)
        else:
            self._set_brand_ui_visible(bool(self._brand_enabled.get()))
        self._update_style_menu_state(mode)
        self._save_from_ui()
        self._update_hint(mode)
        self._refresh_preview_and_auto(mode=mode, persist_auto=mode == "auto")

    def _on_allocation_changed(self) -> None:
        if self._syncing:
            return
        if getattr(self, "_alloc_preset_var", None) is not None:
            self._alloc_preset_var.set("Custom")
        self._save_allocation_from_ui()
        self._refresh_allocation_preview()

    def _on_allocation_preset_changed(self) -> None:
        if self._syncing:
            return
        from visual_allocation.models import allocation_preset_settings

        preset = allocation_preset_settings(self._alloc_preset_var.get())
        if preset is None:
            self._refresh_allocation_preview()
            return
        rev_strat = {
            "automatic": "Automatic",
            "video_heavy": "Video Heavy",
            "balanced": "Balanced",
            "image_heavy": "Image Heavy",
        }
        rev_budget = {
            "conservative": "Conservative",
            "normal": "Normal",
            "high": "High",
            "custom": "Custom",
        }
        rev_cov = {
            "automatic": "Automatic",
            "minimize_repetition": "Minimize Repetition",
            "cinematic_coverage": "Cinematic Coverage",
            "maximum_motion": "Maximum Motion",
        }
        self._visual_strategy_var.set(rev_strat.get(preset.visual_strategy, "Automatic"))
        self._ai_budget_var.set(rev_budget.get(preset.ai_video_budget, "Normal"))
        self._coverage_mode_var.set(rev_cov.get(preset.coverage_mode, "Automatic"))
        self._save_allocation_from_ui()
        self._refresh_allocation_preview()

    def _refresh_allocation_preview(self) -> None:
        preview = getattr(self, "_alloc_preview", None)
        if preview is None:
            return
        try:
            from visual_allocation import estimate_allocation_mix
            from visual_director.director import script_word_count

            script = ""
            if hasattr(self.app, "script_box"):
                script = self.app.script_box.get("1.0", "end").strip()
            words = script_word_count(script)
            style_id = ""
            sid = self._id_by_style_label.get(self._style_var.get())
            if sid:
                style_id = sid
            mix = estimate_allocation_mix(
                words,
                self._allocation_settings_from_ui(),
                style_id=style_id,
            )
            preview.configure(text=f"Estimated mix: {mix}")
        except Exception:
            preview.configure(text="Estimated mix: unavailable")

    def _allocation_settings_from_ui(self):
        from visual_allocation.models import AllocationSettings

        strat_map = {
            "Automatic": "automatic",
            "Video Heavy": "video_heavy",
            "Balanced": "balanced",
            "Image Heavy": "image_heavy",
        }
        budget_map = {
            "Conservative": "conservative",
            "Normal": "normal",
            "High": "high",
            "Custom": "custom",
        }
        cov_map = {
            "Automatic": "automatic",
            "Minimize Repetition": "minimize_repetition",
            "Cinematic Coverage": "cinematic_coverage",
            "Maximum Motion": "maximum_motion",
        }
        return AllocationSettings(
            visual_strategy=strat_map.get(self._visual_strategy_var.get(), "automatic"),
            ai_video_budget=budget_map.get(self._ai_budget_var.get(), "normal"),
            coverage_mode=cov_map.get(self._coverage_mode_var.get(), "automatic"),
        )

    def _save_allocation_from_ui(self) -> None:
        ws = self.app._workspace
        if ws is None:
            return
        from visual_allocation.settings import save_allocation_settings

        save_allocation_settings(ws, self._allocation_settings_from_ui())

    def _on_selection_changed(self) -> None:
        if self._syncing:
            return
        self._save_from_ui()
        mode = self._mode_token()
        self._update_hint(mode)
        # Immediate preview sync — do not wait for navigation
        self._update_preview_from_selection(mode=mode)

    def _save_from_ui(self) -> None:
        ws = self.app._workspace
        if ws is None:
            return
        mode = self._mode_token()
        brand_on = bool(self._brand_enabled.get()) and bool(mode)
        brand_id = None
        if brand_on:
            brand_id = self._id_by_brand_label.get(self._brand_var.get())
        style_id = self._id_by_style_label.get(self._style_var.get())
        if mode == "":
            style_id = None
            brand_id = None
        ws.set_video_style_settings(mode=mode, style_id=style_id, brand_kit_id=brand_id)
        self._save_allocation_from_ui()
        try:
            self.app._refresh_cache_status()
        except Exception:
            pass

    def _keep_auto(self) -> None:
        ws = self.app._workspace
        if ws is None:
            return
        vs = ws.video_style_settings()
        brand_id = vs.get("brand_kit_id") if self._brand_enabled.get() else None
        ws.set_video_style_settings(
            mode="auto",
            style_id=vs.get("style_id"),
            brand_kit_id=brand_id,
        )
        self._mode_var.set("Auto")
        self.on_show()

    def _switch_to_manual(self) -> None:
        self._mode_var.set("Manual")
        self._on_mode_changed()


class ResearchView(_BaseView):
    """Manual Research: independent of Generate Assets — the user runs this
    whenever they want, and whatever it produces sits in project/research/
    for AssetManager to pick up as an additional candidate source the next
    time assets are generated. Topic is the only required input; script and
    URL(s) are optional refinements on top of it (4 supported modes)."""

    key = "research"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(
            self, "Research", "Find real, property-specific media for a script about a specific listing",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD_SM, 4))

        form = Card(self._body)
        form.grid(row=0, column=0, sticky="ew", pady=4)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Topic", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="w", padx=T.PAD, pady=(10, 4)
        )
        self._topic_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            form, textvariable=self._topic_var, placeholder_text="e.g. Hunters Ridge, Clio Alabama",
        ).grid(row=0, column=1, sticky="ew", padx=T.PAD, pady=(10, 4))

        ctk.CTkLabel(form, text="Script (optional)", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="nw", padx=T.PAD, pady=4
        )
        script_frame = ctk.CTkFrame(form, fg_color="transparent")
        script_frame.grid(row=1, column=1, sticky="ew", padx=T.PAD, pady=4)
        script_frame.grid_columnconfigure(0, weight=1)
        self._script_box = ctk.CTkTextbox(
            script_frame, height=70, 
        )
        self._script_box.grid(row=0, column=0, sticky="ew")
        self._script_path_label = ctk.CTkLabel(
            script_frame, text="", font=ctk.CTkFont(size=10), text_color=T.MUTED, anchor="w",
        )
        self._script_path_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        ctk.CTkButton(
            script_frame, text="Load from file…", height=26, width=120,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), command=self._on_load_script_file,
        ).grid(row=0, column=1, sticky="n", padx=(T.PAD_SM, 0))
        self._script_path = ""

        ctk.CTkLabel(form, text="Listings (optional)", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, sticky="nw", padx=T.PAD, pady=4
        )
        # Each listing is researched into its own directory and keeps its own
        # facts/media/errors, so one failing listing never invalidates another.
        # `_urls_var` is retained purely as the persistence/compat bridge for
        # the existing load/save/read paths — the list below is the real model.
        self._urls_var = ctk.StringVar(value="")
        self._listing_urls: list = []
        self._listing_status: dict = {}

        listings = ctk.CTkFrame(form, fg_color="transparent")
        listings.grid(row=2, column=1, sticky="ew", padx=T.PAD, pady=4)
        listings.grid_columnconfigure(0, weight=1)

        adder = ctk.CTkFrame(listings, fg_color="transparent")
        adder.grid(row=0, column=0, sticky="ew")
        adder.grid_columnconfigure(0, weight=1)
        self._new_listing_var = ctk.StringVar(value="")
        entry = ctk.CTkEntry(
            adder, textvariable=self._new_listing_var,
            placeholder_text="paste a listing URL, then Add (or press Enter)",
        )
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _e: self._on_add_listing())
        ctk.CTkButton(
            adder, text="Add", width=56, height=26,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), command=self._on_add_listing,
        ).grid(row=0, column=1, padx=(T.PAD_SM, 0))

        self._listing_rows = ctk.CTkFrame(listings, fg_color="transparent")
        self._listing_rows.grid(row=1, column=0, sticky="ew", pady=(T.PAD_SM, 0))
        self._listing_rows.grid_columnconfigure(0, weight=1)
        self._render_listing_rows()

        ctk.CTkLabel(form, text="Domain", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, sticky="w", padx=T.PAD, pady=4
        )
        self._domain_var = ctk.StringVar(value="Auto")
        self._domain_labels = ("Auto", "Real Estate", "Products", "Travel", "Cars", "News", "Science", "General")
        ctk.CTkOptionMenu(
            form, variable=self._domain_var, values=list(self._domain_labels),
        ).grid(row=3, column=1, sticky="ew", padx=T.PAD, pady=4)

        ctk.CTkLabel(form, text="Max media / property", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=4, column=0, sticky="w", padx=T.PAD, pady=4
        )
        self._max_media_var = ctk.StringVar(value="20")
        ctk.CTkEntry(
            form, textvariable=self._max_media_var, width=80,
        ).grid(row=4, column=1, sticky="w", padx=T.PAD, pady=4)

        button_row = ctk.CTkFrame(form, fg_color="transparent")
        button_row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(8, 4))
        self._start_btn = ctk.CTkButton(
            button_row, text="Start Research", height=34, width=150,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._on_start_research,
        )
        self._start_btn.pack(side="left")
        self._status_pill = StatusPill(button_row, text="Idle", tone="muted")
        self._status_pill.pack(side="left", padx=(T.PAD_SM, 0))

        self._status_label = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED,
            justify="left", anchor="w", wraplength=460,
        )
        self._status_label.grid(row=6, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(0, 8))

        # Result summary — populated after a run, hidden otherwise.
        self._summary = Card(self._body)
        self._summary.grid_columnconfigure(0, weight=1)
        self._summary_rows: list[MetricRow] = []
        for label in (
            "Property", "Research URL", "Confidence", "Sources found",
            "Usable media", "Newly downloaded", "Reused", "Low-quality / rejected",
        ):
            row = MetricRow(self._summary, label, "—")
            row.grid(sticky="ew", padx=T.PAD, pady=(T.PAD_SM, 0))
            self._summary_rows.append(row)

        # Folder/file actions — disabled whenever their target doesn't
        # exist yet (no research run, or nothing downloaded).
        folder_row = ctk.CTkFrame(self._summary, fg_color="transparent")
        folder_row.grid(sticky="ew", padx=T.PAD, pady=(T.PAD_SM, T.PAD_SM))
        self._open_research_btn = ctk.CTkButton(
            folder_row, text="Open Research Folder", height=28, width=150,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), state="disabled",
            command=lambda: self._open_path(self._research_folder_path()),
        )
        self._open_research_btn.pack(side="left")
        self._open_media_folder_btn = ctk.CTkButton(
            folder_row, text="Open Media Folder", height=28, width=140,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), state="disabled",
            command=lambda: self._open_path(self._media_folder_path()),
        )
        self._open_media_folder_btn.pack(side="left", padx=(T.PAD_SM, 0))
        self._open_media_btn = ctk.CTkButton(
            folder_row, text="Open Media", height=28, width=110,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), state="disabled",
            command=lambda: self._open_path(self._top_media_path),
        )
        self._open_media_btn.pack(side="left", padx=(T.PAD_SM, 0))
        self._top_media_path: Optional[Path] = None

        self._summary.grid_remove()

        # Property Script — separate step, only usable once a property has
        # been researched. Property Video only: this never touches the
        # normal Script Analyzer/Script view.
        self._property_script_card = Card(self._body)
        self._property_script_card.grid(row=2, column=0, sticky="ew", pady=(8, 4))
        self._property_script_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self._property_script_card, text="PROPERTY SCRIPT", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T.MUTED,
        ).grid(row=0, column=0, sticky="w", padx=T.PAD, pady=(10, 2))
        ctk.CTkLabel(
            self._property_script_card,
            text="Narration is preserved exactly — never rewritten. Each sentence is "
                 "classified and routed to researched property media, stock, or Flow.",
            font=ctk.CTkFont(size=11), text_color=T.MUTED, wraplength=460, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=T.PAD, pady=(0, 6))
        self._property_script_box = ctk.CTkTextbox(
            self._property_script_card, height=140, 
        )
        self._property_script_box.grid(row=2, column=0, sticky="ew", padx=T.PAD)
        analyze_row = ctk.CTkFrame(self._property_script_card, fg_color="transparent")
        analyze_row.grid(row=3, column=0, sticky="ew", padx=T.PAD, pady=(8, 10))
        self._property_analyze_btn = ctk.CTkButton(
            analyze_row, text="Analyze Property Script", height=32,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._on_analyze_property_script,
        )
        self._property_analyze_btn.pack(side="left")
        self._property_script_status = ctk.CTkLabel(
            analyze_row, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED,
        )
        self._property_script_status.pack(side="left", padx=(T.PAD_SM, 0))

        # Research engine: bundled and auto-configured by default (see
        # research/settings.py::load_engine_config) — no path to set up.
        # Collapsed behind "Advanced" since it's only ever needed to point at
        # a different engine checkout during development.
        engine_card = Card(self._body)
        engine_card.grid(row=3, column=0, sticky="ew", pady=(8, 4))
        engine_card.grid_columnconfigure(1, weight=1)

        engine_header = ctk.CTkFrame(engine_card, fg_color="transparent")
        engine_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(10, 0))
        engine_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            engine_header, text="RESEARCH ENGINE", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T.MUTED,
        ).grid(row=0, column=0, sticky="w")
        self._engine_status_label = ctk.CTkLabel(
            engine_header, text="", font=ctk.CTkFont(size=11), text_color=T.SUCCESS, anchor="w",
        )
        self._engine_status_label.grid(row=0, column=1, sticky="w", padx=(T.PAD_SM, 0))
        self._engine_advanced_open = False
        self._engine_advanced_toggle = ctk.CTkButton(
            engine_header, text="Advanced +", height=22, width=90,
            fg_color="transparent", hover_color=T.CARD_HOVER, text_color=T.MUTED,
            font=ctk.CTkFont(size=11), command=self._toggle_engine_advanced,
        )
        self._engine_advanced_toggle.grid(row=0, column=2, sticky="e")

        self._engine_advanced_block = ctk.CTkFrame(engine_card, fg_color="transparent")
        self._engine_advanced_block.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self._engine_advanced_block,
            text="Override with a different engine checkout (development only) — "
                 "leave both blank to use the bundled engine.",
            font=ctk.CTkFont(size=11), text_color=T.MUTED, wraplength=460, justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(8, 6))
        ctk.CTkLabel(self._engine_advanced_block, text="Engine folder", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", pady=4
        )
        self._engine_root_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            self._engine_advanced_block, textvariable=self._engine_root_var,
            placeholder_text="(bundled)",
        ).grid(row=1, column=1, sticky="ew", pady=4)
        ctk.CTkLabel(self._engine_advanced_block, text="Python interpreter", text_color=T.MUTED, font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, sticky="w", pady=4
        )
        self._engine_python_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            self._engine_advanced_block, textvariable=self._engine_python_var,
            placeholder_text="(bundled)",
        ).grid(row=2, column=1, sticky="ew", pady=4)
        ctk.CTkButton(
            self._engine_advanced_block, text="Save Engine Path", height=28, width=140,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), command=self._on_save_engine_path,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 10))
        self._engine_advanced_block.grid(row=1, column=0, columnspan=2, sticky="ew", padx=T.PAD)
        self._engine_advanced_block.grid_remove()

        # RealtyAPI key: Phase 1 storage only (see research/settings.py).
        # Deliberately lives HERE, in the Research tab, not the global
        # Settings (⚙) dialog where Pexels/Gemini keys live — RealtyAPI is
        # property-research-specific, not a general-purpose provider, and
        # nothing outside research/ code is meant to read it.
        realty_card = Card(self._body)
        realty_card.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        realty_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            realty_card, text="REALTYAPI", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T.MUTED,
        ).grid(row=0, column=0, sticky="w", padx=T.PAD, pady=(10, 2))
        ctk.CTkLabel(
            realty_card,
            text="Property listing data API — used to fetch high-resolution property "
                 "photos when Property Image Source below is set to RealtyAPI or Both.",
            font=ctk.CTkFont(size=11), text_color=T.MUTED, wraplength=460, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=T.PAD, pady=(0, 6))
        self._realtyapi_key_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            realty_card, textvariable=self._realtyapi_key_var, show="•", height=34,
            placeholder_text="RealtyAPI API key", 
        ).grid(row=2, column=0, sticky="ew", padx=T.PAD, pady=(0, 4))
        self._realtyapi_status_label = ctk.CTkLabel(
            realty_card, text="Not configured", font=ctk.CTkFont(size=12), text_color=T.MUTED,
        )
        self._realtyapi_status_label.grid(row=3, column=0, sticky="w", padx=T.PAD, pady=(0, 4))

        # Property Image Source — controls ONLY property-image acquisition
        # (see research/settings.py::load_property_image_source /
        # research/engine/app/research/property_researcher.py). Default
        # "Existing" makes zero RealtyAPI calls and is byte-for-byte the
        # same acquisition pipeline as before this switch existed.
        image_source_row = ctk.CTkFrame(realty_card, fg_color="transparent")
        image_source_row.grid(row=4, column=0, sticky="ew", padx=T.PAD, pady=(4, 4))
        ctk.CTkLabel(
            image_source_row, text="Property Image Source", text_color=T.MUTED, font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._image_source_labels = ("Existing", "RealtyAPI", "Both")
        self._image_source_var = ctk.StringVar(value="Existing")
        ctk.CTkOptionMenu(
            image_source_row, variable=self._image_source_var, values=list(self._image_source_labels),
            width=140,
        ).pack(side="left", padx=(T.PAD_SM, 0))

        ctk.CTkButton(
            realty_card, text="Save RealtyAPI Settings", height=28, width=170,
            fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
            font=ctk.CTkFont(size=11), command=self._on_save_realtyapi_key,
        ).grid(row=5, column=0, sticky="w", padx=T.PAD, pady=(0, 10))

        self._researching = False

    def _toggle_engine_advanced(self) -> None:
        self._engine_advanced_open = not self._engine_advanced_open
        if self._engine_advanced_open:
            self._engine_advanced_block.grid()
            self._engine_advanced_toggle.configure(text="Advanced −")
        else:
            self._engine_advanced_block.grid_remove()
            self._engine_advanced_toggle.configure(text="Advanced +")

    # ---------- lifecycle ----------

    _IMAGE_SOURCE_TOKEN_TO_LABEL = {"existing": "Existing", "realtyapi": "RealtyAPI", "both": "Both"}
    _IMAGE_SOURCE_LABEL_TO_TOKEN = {v: k for k, v in _IMAGE_SOURCE_TOKEN_TO_LABEL.items()}

    def on_show(self) -> None:
        from research.settings import (
            load_engine_config, load_project_research_settings, load_property_image_source,
        )

        global_settings = getattr(self.app, "_settings", {}) or {}
        # The override fields show only what's explicitly saved (blank means
        # "use the bundled engine") — load_engine_config's *effective* value
        # (which fills in the bundled default) only drives the status line.
        raw_root = str(global_settings.get("research_engine_root") or "")
        raw_python = str(global_settings.get("research_engine_python") or "")
        self._engine_root_var.set(raw_root)
        self._engine_python_var.set(raw_python)

        # RealtyAPI: only the explicitly-saved value is shown (never the
        # REALTYAPI_API_KEY env-var fallback) — same convention as Pexels
        # (self.pexels_key_var is seeded from settings only, not the env).
        raw_realtyapi_key = str(global_settings.get("realtyapi_api_key") or "")
        self._realtyapi_key_var.set(raw_realtyapi_key)
        self._realtyapi_status_label.configure(
            text="Configured" if raw_realtyapi_key.strip() else "Not configured"
        )
        image_source_token = load_property_image_source(global_settings)
        self._image_source_var.set(self._IMAGE_SOURCE_TOKEN_TO_LABEL.get(image_source_token, "Existing"))

        effective_root, _ = load_engine_config(global_settings)
        if raw_root or raw_python:
            self._engine_status_label.configure(text="Using custom engine path", text_color=T.MUTED)
        elif effective_root:
            self._engine_status_label.configure(text="Bundled — no setup needed", text_color=T.SUCCESS)
        else:
            self._engine_status_label.configure(
                text="Not available in this build — set a path below", text_color=T.WARNING,
            )

        ws = self.app._workspace
        if ws is None:
            return
        settings = load_project_research_settings(ws)
        self._topic_var.set(settings.topic)
        self._set_listing_urls(list(settings.urls))
        self._max_media_var.set(str(settings.max_media_per_property))
        label_by_domain = {
            "auto": "Auto", "real_estate": "Real Estate", "products": "Products",
            "travel": "Travel", "cars": "Cars", "news": "News", "science": "Science", "general": "General",
        }
        self._domain_var.set(label_by_domain.get(settings.domain, "Auto"))
        if settings.script_path:
            self._script_path = settings.script_path
            self._script_path_label.configure(text=Path(settings.script_path).name)

        # Reflect whatever's already on disk from a prior run (if this tab
        # wasn't just used to complete a fresh one) so the folder actions
        # are usable immediately on returning to the project.
        if (ws.research_dir / "research.json").is_file():
            self._summary.grid()
        self._refresh_folder_buttons()

    # ---------- folder / media actions ----------

    def _research_folder_path(self) -> Optional[Path]:
        ws = self.app._workspace
        return ws.research_dir if ws is not None else None

    def _media_folder_path(self) -> Optional[Path]:
        research_dir = self._research_folder_path()
        return (research_dir / "media") if research_dir is not None else None

    @staticmethod
    def _open_path(path: Optional[Path]) -> None:
        """Reveal a file/folder in the OS file manager — same
        platform-dispatch pattern already used elsewhere in this app
        (see app.py's _open_scene_asset and similar)."""
        if path is None or not path.exists():
            return
        import subprocess
        import sys

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform == "win32":
                import os

                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:  # noqa: BLE001 - opening a folder is never critical path
            pass

    def _refresh_folder_buttons(self, result: Optional[Any] = None) -> None:
        """Enables each button only when its target actually exists.
        `result` (a fresh ResearchResult, when called right after a run)
        gives the precise top-ranked file; otherwise falls back to
        whatever's already on disk (media/ is numbered 001, 002, ... in
        rank order by the engine, so the lowest-numbered file already
        existing is the same "top" file)."""
        research_dir = self._research_folder_path()
        media_dir = self._media_folder_path()

        self._open_research_btn.configure(state=("normal" if research_dir and research_dir.is_dir() else "disabled"))
        self._open_media_folder_btn.configure(state=("normal" if media_dir and media_dir.is_dir() else "disabled"))

        self._top_media_path = None
        if result is not None:
            for m in result.media:
                if m.local_path and Path(m.local_path).is_file():
                    self._top_media_path = Path(m.local_path)
                    break
        elif media_dir is not None and media_dir.is_dir():
            existing = sorted(p for p in media_dir.iterdir() if p.is_file())
            self._top_media_path = existing[0] if existing else None

        self._open_media_btn.configure(state=("normal" if self._top_media_path else "disabled"))

    # ---------- helpers ----------

    def _on_load_script_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(title="Select narration script", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            self._status_label.configure(text=f"Could not read file: {exc}")
            return
        self._script_box.delete("1.0", "end")
        self._script_box.insert("1.0", text)
        self._script_path = path
        self._script_path_label.configure(text=Path(path).name)

    def _on_save_engine_path(self) -> None:
        from research.settings import with_engine_config

        current = getattr(self.app, "_settings", {}) or {}
        root = self._engine_root_var.get().strip()
        python_path = self._engine_python_var.get().strip()
        updated = with_engine_config(current, root, python_path)
        self.app._settings = updated
        self.app._persist_global_settings()
        if root or python_path:
            self._status_label.configure(text="Custom engine path saved.")
            self._engine_status_label.configure(text="Using custom engine path", text_color=T.MUTED)
        else:
            self._status_label.configure(text="Engine path cleared — using the bundled engine again.")
            self._engine_status_label.configure(text="Bundled — no setup needed", text_color=T.SUCCESS)

    def _on_save_realtyapi_key(self) -> None:
        from research.settings import with_property_image_source, with_realtyapi_key

        current = getattr(self.app, "_settings", {}) or {}
        key = self._realtyapi_key_var.get().strip()
        image_source_token = self._IMAGE_SOURCE_LABEL_TO_TOKEN.get(self._image_source_var.get(), "existing")
        updated = with_realtyapi_key(current, key)
        updated = with_property_image_source(updated, image_source_token)
        self.app._settings = updated
        self.app._persist_global_settings()
        self._realtyapi_status_label.configure(text="Configured" if key else "Not configured")
        self._status_label.configure(
            text="RealtyAPI settings saved." if key else "RealtyAPI settings saved (no key set)."
        )

    _DOMAIN_TOKENS = {
        "Auto": "auto", "Real Estate": "real_estate", "Products": "products", "Travel": "travel",
        "Cars": "cars", "News": "news", "Science": "science", "General": "general",
    }

    def _on_start_research(self, only_urls=None) -> None:
        """`only_urls` re-researches just those listings (per-row Re-research);
        their directories are rebuilt and every other listing is left alone."""
        if self._researching:
            return
        ws = self.app._workspace
        if ws is None:
            self._status_label.configure(text="Open or create a project first.")
            return

        topic = self._topic_var.get().strip()
        if not topic:
            self._status_label.configure(text="Topic is required (script/URL(s) are optional refinements on top of it).")
            return

        script_text = self._script_box.get("1.0", "end").strip()
        urls = [u.strip() for u in self._urls_var.get().split(",") if u.strip()]
        if only_urls:
            urls = [u for u in only_urls if u]
        domain = self._DOMAIN_TOKENS.get(self._domain_var.get(), "auto")
        try:
            max_media = max(1, int(self._max_media_var.get().strip() or 20))
        except ValueError:
            max_media = 20

        from research.settings import (
            compute_script_fingerprint, load_engine_config, load_property_image_source,
            load_realtyapi_key, save_project_research_settings,
        )
        from research.models import ResearchSettings

        # Script-bound vs. property-bound (see research/settings.py): only a
        # research run that actually includes a script gets a fingerprint —
        # URL/topic-only runs stay valid regardless of a script written later.
        script_fingerprint = compute_script_fingerprint(script_text) if script_text.strip() else None

        save_project_research_settings(ws, ResearchSettings(
            topic=topic, script_path=self._script_path, urls=urls, domain=domain, max_media_per_property=max_media,
            script_fingerprint=script_fingerprint,
        ))

        global_settings = getattr(self.app, "_settings", {}) or {}
        engine_root, engine_python = load_engine_config(global_settings)
        # Property Image Source switch (Phase 2) — read from the persisted
        # setting, same as engine path above, not from a live/unsaved UI
        # value, so "Start Research" always matches what was actually saved.
        image_source = load_property_image_source(global_settings)
        realtyapi_key = load_realtyapi_key(global_settings) if image_source in ("realtyapi", "both") else ""

        self._researching = True
        self._start_btn.configure(state="disabled")
        self._status_pill.set_tone("Running…", "run")
        self._status_label.configure(text="Researching — this can take up to a few minutes.")
        self._summary.grid_remove()

        def worker():
            from research.library import property_dir, property_id_for
            from research.property_provider import PropertyResearchProvider

            provider = PropertyResearchProvider(engine_root, engine_python)

            # Each listing is researched INDEPENDENTLY into its own
            # directory, so its facts/media/errors stay isolated and one
            # listing's photos can never end up in another's scene. A single
            # URL (or none) keeps the original single-property behavior.
            if len(urls) > 1:
                results = []
                for url in urls:
                    pid = property_id_for(url=url)
                    out_dir = property_dir(ws.research_dir, pid)
                    res = provider.research(
                        topic, script=script_text or None, urls=[url], domain=domain,
                        max_media_per_property=max_media, output_dir=out_dir,
                        image_source=image_source, realtyapi_key=realtyapi_key,
                    )
                    res.property.property_id = pid
                    res.property.source_url = url
                    for media in res.media:
                        media.property_id = pid
                    results.append(res)
                self.after(0, lambda rs=results: self._on_multi_research_complete(rs))
                return

            result = provider.research(
                topic, script=script_text or None, urls=urls, domain=domain,
                max_media_per_property=max_media, output_dir=ws.research_dir,
                image_source=image_source, realtyapi_key=realtyapi_key,
            )
            if urls:
                result.property.source_url = urls[0]
            self.after(0, lambda: self._on_research_complete(result))

        import threading

        threading.Thread(target=worker, daemon=True).start()

    # ---------- multi-listing model ----------

    def _set_listing_urls(self, urls) -> None:
        """Single place that mutates the listing list, so the compat var,
        the stored per-listing status and the rendered rows never drift."""
        seen, clean = set(), []
        for raw in urls or []:
            u = str(raw).strip()
            if u and u not in seen:
                seen.add(u)
                clean.append(u)
        self._listing_urls = clean
        self._listing_status = {
            u: self._listing_status.get(u, ("pending", "muted")) for u in clean
        }
        # Existing read/save paths still go through _urls_var — keep it exact.
        self._urls_var.set(", ".join(clean))
        self._render_listing_rows()

    def _on_add_listing(self) -> None:
        url = self._new_listing_var.get().strip()
        if not url:
            return
        if url in self._listing_urls:
            self._new_listing_var.set("")
            return
        self._set_listing_urls(self._listing_urls + [url])
        self._new_listing_var.set("")
        self._persist_listing_urls()

    def _on_remove_listing(self, url: str) -> None:
        self._listing_status.pop(url, None)
        self._set_listing_urls([u for u in self._listing_urls if u != url])
        self._persist_listing_urls()

    def _persist_listing_urls(self) -> None:
        """Reuse the existing ResearchSettings.urls list — no schema change.
        Every other field is round-tripped from the stored settings so editing
        the listing list can never clobber topic/domain/max_media."""
        ws = getattr(self.app, "_workspace", None)
        if ws is None:
            return
        try:
            import dataclasses

            from research.settings import (
                load_project_research_settings,
                save_project_research_settings,
            )

            current = load_project_research_settings(ws)
            save_project_research_settings(
                ws, dataclasses.replace(current, urls=list(self._listing_urls)),
            )
        except Exception:
            pass  # persistence is a convenience; never block editing the list

    def _set_listing_status(self, url: str, text: str, tone: str = "muted") -> None:
        self._listing_status[url] = (text, tone)
        self._render_listing_rows()

    def _render_listing_rows(self) -> None:
        rows = self.__dict__.get("_listing_rows")
        if rows is None:
            return
        for child in rows.winfo_children():
            child.destroy()
        if not self._listing_urls:
            ctk.CTkLabel(
                rows, text="No listings added — research runs on the topic/script alone.",
                text_color=T.MUTED, font=ctk.CTkFont(size=11),
            ).grid(row=0, column=0, sticky="w")
            return
        for i, url in enumerate(self._listing_urls):
            text, tone = self._listing_status.get(url, ("pending", "muted"))
            row = ctk.CTkFrame(rows, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(0, weight=1)
            shown = url if len(url) <= 52 else url[:49] + "…"
            ctk.CTkLabel(
                row, text=shown, text_color=T.TEXT, font=ctk.CTkFont(size=11), anchor="w",
            ).grid(row=0, column=0, sticky="w")
            StatusPill(row, text=text, tone=tone).grid(row=0, column=1, padx=(T.PAD_SM, 0))
            ctk.CTkButton(
                row, text="Re-research", width=86, height=22,
                fg_color=T.BORDER, hover_color=T.ACCENT, text_color=T.TEXT,
                font=ctk.CTkFont(size=10),
                command=lambda u=url: self._on_reresearch_listing(u),
            ).grid(row=0, column=2, padx=(T.PAD_SM, 0))
            ctk.CTkButton(
                row, text="Remove", width=64, height=22,
                fg_color=T.BORDER, hover_color=T.DANGER, text_color=T.TEXT,
                font=ctk.CTkFont(size=10),
                command=lambda u=url: self._on_remove_listing(u),
            ).grid(row=0, column=3, padx=(T.PAD_SM, 0))
            self._listing_status.setdefault(url, (text, tone))

    def _on_reresearch_listing(self, url: str) -> None:
        """Rebuild ONLY this listing's directory; the others are untouched."""
        if getattr(self, "_researching", False):
            return
        self._set_listing_status(url, "researching…", "run")
        self._on_start_research(only_urls=[url])

    def _on_multi_research_complete(self, results) -> None:
        """Multi-listing summary. Each listing keeps its own status/errors —
        one listing failing never invalidates the others."""
        self._researching = False
        self._start_btn.configure(state="normal")

        ok_props = [r for r in results if r.ok and any(m.local_path for m in r.media)]
        failed = [r for r in results if not r.ok]
        total_media = sum(len([m for m in r.media if m.local_path]) for r in ok_props)

        # Per-listing status, so a row shows its OWN outcome rather than the
        # aggregate — one listing failing must stay visibly local to that row.
        for r in results:
            url = getattr(getattr(r, "property", None), "source_url", "") or ""
            if not url:
                continue
            n = len([m for m in r.media if m.local_path])
            if r.ok and n:
                self._listing_status[url] = (f"researched · {n} photos", "ok")
            elif r.ok:
                self._listing_status[url] = ("no usable media", "warn")
            else:
                reason = (r.error or "failed").strip().splitlines()[0][:40]
                self._listing_status[url] = (f"failed: {reason}", "fail")
        self._render_listing_rows()

        if not ok_props:
            self._status_pill.set_tone("Failed", "fail")
            first_error = next((r.error for r in results if r.error), None)
            self._status_label.configure(
                text=first_error or "No usable media found for any listing."
            )
            return

        tone = "warn" if failed else "ok"
        self._status_pill.set_tone(f"{len(ok_props)} listing(s)", tone)
        detail = f" · {len(failed)} failed" if failed else ""
        self._status_label.configure(
            text=f"{len(ok_props)} listing(s) researched · {total_media} usable media{detail}. "
                 "Each listing's media stays scoped to that listing."
        )

        names = ", ".join(
            (r.property.name or r.property.address or r.property.property_id or "—") for r in ok_props
        )
        values = [
            names,
            f"{len(ok_props)} listing(s)",
            "—",
            str(sum(len(r.sources) for r in ok_props)),
            str(total_media),
            "—",
            "—",
            str(sum(r.rejected_media_count for r in ok_props)) or "—",
        ]
        for row, value in zip(self._summary_rows, values):
            row.set_value(value)
        self._summary.grid()
        self._refresh_folder_buttons(ok_props[0])
        self.app._asset_manager = None

    def _on_research_complete(self, result) -> None:
        self._researching = False
        self._start_btn.configure(state="normal")

        # A per-row "Re-research" resolves through this single-listing path, so
        # the row's status must be settled here too or it would sit on
        # "researching…" forever.
        url = getattr(getattr(result, "property", None), "source_url", "") or ""
        if url and url in self._listing_status:
            n = len([m for m in result.media if m.local_path])
            if result.ok and n:
                self._listing_status[url] = (f"researched · {n} photos", "ok")
            elif result.ok:
                self._listing_status[url] = ("no usable media", "warn")
            else:
                reason = (result.error or "failed").strip().splitlines()[0][:40]
                self._listing_status[url] = (f"failed: {reason}", "fail")
            self._render_listing_rows()

        if not result.ok:
            self._status_pill.set_tone("Failed", "fail")
            self._status_label.configure(text=result.error or "Research failed.")
            return

        usable = [m for m in result.media if m.local_path]
        downloaded = len(usable)
        # Only shown when actually derivable from the manifest (download_note
        # is the engine's own classification, e.g. "duplicate_reused") — no
        # numbers are invented if that field is absent.
        reused = sum(1 for m in usable if m.download_note == "duplicate_reused")
        breakdown = f" · {reused} reused · {downloaded - reused} newly downloaded" if reused else ""

        if downloaded == 0:
            self._status_pill.set_tone("No media found", "warn")
            self._status_label.configure(
                text=result.error or "Research completed but found no usable media for this property."
            )
        elif result.property_ambiguous:
            # Topic/script-only discovery found more than one plausible
            # property close in confidence — never silently claim the one
            # shown below is definitely the intended one.
            self._status_pill.set_tone("Ambiguous", "warn")
            self._status_label.configure(
                text=f"{downloaded} usable media{breakdown}, but multiple similarly-plausible properties were "
                     f"discovered — verify '{result.property.name or result.property.address or 'the property below'}' "
                     "is the one you meant before using it, or supply the exact listing URL instead."
            )
        else:
            self._status_pill.set_tone("Done", "ok")
            self._status_label.configure(text=f"{downloaded} usable media{breakdown} for this property.")

        prop = result.property
        urls = [u.strip() for u in self._urls_var.get().split(",") if u.strip()]
        values = [
            prop.name or prop.address or "—",
            urls[0] if urls else "— (topic/script-based discovery)",
            f"{prop.confidence:.0%}" if prop.confidence else "—",
            str(len(result.sources)),
            str(downloaded),
            str(downloaded - reused),
            str(reused),
            str(result.rejected_media_count) if result.rejected_media_count else "—",
        ]
        for row, value in zip(self._summary_rows, values):
            row.set_value(value)
        self._summary.grid()
        self._refresh_folder_buttons(result)

        # Invalidate any already-built AssetManager so the next Generate
        # Assets run picks up the freshly-downloaded research candidates.
        self.app._asset_manager = None

    # ---------- Property Script ----------

    def _on_analyze_property_script(self) -> None:
        """Property Video workflow only — builds a Property Visual Plan from
        the pasted narration + whatever property research already exists for
        this project, then hands it to the exact same _apply_ai_plan() the
        normal Script Analyzer uses (CSV write, scene preview, view switch)
        so nothing downstream needs to know this came from a different
        analyzer."""
        ws = self.app._workspace
        if ws is None:
            self._property_script_status.configure(text="Open or create a project first.")
            return
        narration = self._property_script_box.get("1.0", "end").strip()
        if not narration:
            self._property_script_status.configure(text="Paste the property script first.")
            return

        from research.library import load_research_library
        from research.property_script import analyze_property_script
        from research.property_visual_plan import build_property_visual_plan

        library = load_research_library(ws.research_dir)
        if not library.properties:
            self._property_script_status.configure(
                text="No property research found yet — run Research Property above first."
            )
            return

        primary = library.properties[0]
        result = primary.result
        summaries = [p.result.property for p in library.properties if p.result]

        # Structured facts from the scraper (facts.json) feed the analyzer's
        # existing `property_facts` channel, so classification uses real
        # extracted listing facts rather than narration keyword heuristics.
        beats = analyze_property_script(
            narration, result,
            property_facts=library.facts_dict_for(primary.property_id),
            # Per-listing facts: without this every beat would be analyzed
            # against the FIRST listing's acreage/features, so a second
            # listing's beats would be classified using another property's
            # facts.
            facts_by_property={
                p.property_id: library.facts_dict_for(p.property_id)
                for p in library.properties if p.property_id
            },
            properties=summaries,
            default_property_id=primary.property_id,
        )
        plan, property_scope = build_property_visual_plan(
            beats, result, library=library,
            topic=(result.property.name or result.property.address or ""),
        )
        # Property scope rides alongside the plan (never in the CSV).
        self.app._pending_property_scope = property_scope

        counts: dict = {}
        for beat in beats:
            counts[beat.category.value] = counts.get(beat.category.value, 0) + 1
        self._property_script_status.configure(
            text=(
                f"{len(beats)} beats — property: {counts.get('property_specific', 0)}, "
                f"factual: {counts.get('factual_property_context', 0)}, "
                f"generic: {counts.get('generic_context', 0)}, "
                f"cinematic: {counts.get('cinematic_atmospheric', 0)}"
            )
        )

        self.app.script_box.delete("1.0", "end")
        self.app.script_box.insert("1.0", narration)
        self.app._apply_ai_plan(plan)


class VisualDirectorView(_BaseView):
    """Dedicated home for Exp Solar/Overscaled's Local Visual Planner
    workflow (CSV import, style selection, Local Visual Planner toggle) —
    moved out of the Script tab so this intelligence layer has room to grow
    (optional Gemini enhancement, manual overrides, prompt review, ...)
    without crowding the plain-CSV script workflow. The actual controls are
    built by app._build_overscaled_section(self.content, row=0) — this view
    only owns the header and the scrollable host frame."""

    key = "visual_director"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(
            self, "Visual Director",
            "Pick the kind of video you want to make. The cards say what each style needs and what it is good for.",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8))


class VisualPlanView(ctk.CTkFrame):
    """Scene table fills the view — toolbar lives inside the workspace builder."""

    key = "visual_plan"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, fg_color=T.PANEL_ALT, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        # Single host; no duplicate titles/summaries (workspace owns the toolbar).
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        # Only the scene table row expands — never the toolbar row.
        self.content.grid_rowconfigure(0, weight=0)
        self.content.grid_rowconfigure(1, weight=1)

    def on_show(self) -> None:
        try:
            self.app._refresh_scene_preview()
        except Exception:
            pass


class AudioView(_BaseView):
    key = "audio"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Audio & Effects", "Narration, plus the text, motion and sound added to the final video").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        # height=1: an empty frame otherwise keeps its default 200 px and left a
        # big blank gap above the narration card; it grows when the voice panel
        # is placed in it.
        self._host = ctk.CTkFrame(self._body, fg_color="transparent", height=1)
        self._host.grid(row=0, column=0, sticky="ew")
        self._host.grid_columnconfigure(0, weight=1)
        self.content = self._host  # voice panel may be reparented here

        info_card = Card(self._body, title="Narration", subtitle="The voiceover the video is timed to.")
        info_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self._info = info_card.body
        self._narr = MetricRow(self._info, "Voiceover file")
        self._narr.grid(row=0, column=0, sticky="ew", pady=3)
        self._amb = MetricRow(self._info, "Ambience beds")
        self._amb.grid(row=1, column=0, sticky="ew", pady=3)
        self._sfx = MetricRow(self._info, "Sound effects")
        self._sfx.grid(row=2, column=0, sticky="ew", pady=3)

        # Narration was display-only here, so there was no way to swap the
        # voiceover from the Audio view (Music already had "Change track").
        # Reuses the existing app._browse_audio(), which copies the file into
        # the project's audio/ folder and runs the usual voiceover-switch
        # confirmation — no new audio handling logic.
        audio_actions = ctk.CTkFrame(self._info, fg_color="transparent")
        audio_actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        make_button(audio_actions, "Choose voiceover…", self._on_choose_audio, width=150).pack(side="left")
        self._open_audio_btn = make_button(audio_actions, "Open folder", self._on_open_audio_folder,
                                           variant="ghost", width=110)
        self._open_audio_btn.pack(side="left", padx=(T.PAD_SM, 0))

        # Smart Editing: what the final video adds on top of the footage,
        # in three plain groups — what you SEE (text), how it MOVES, what you
        # HEAR. Every row says what it does; intensity is a Low/Medium/High
        # choice in one aligned column, greyed out while its feature is off.
        smart_card = Card(self._body, title="Smart editing",
                          subtitle="What the final video adds on top of your footage and narration.")
        smart_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        smart = smart_card.body

        self._intensity_controls = []
        grid_row = [2]

        def _next_row() -> int:
            grid_row[0] += 1
            return grid_row[0]

        def _group(title: str) -> None:
            if grid_row[0] > 2:
                Divider(smart).grid(row=_next_row(), column=0, sticky="ew", pady=(10, 0))
            SectionLabel(smart, title).grid(row=_next_row(), column=0, sticky="w", pady=(12, 4))

        def _feature(name: str, desc: str, enabled_var, intensity_var=None, on_intensity=None):
            row = ctk.CTkFrame(smart, fg_color="transparent")
            row.grid(row=_next_row(), column=0, sticky="ew", pady=5)
            row.grid_columnconfigure(1, weight=1)
            seg = None

            def _toggled() -> None:
                if seg is not None:
                    seg.configure(state="normal" if enabled_var.get() else "disabled")
                app._persist_smart_editing_settings()

            ctk.CTkSwitch(
                row, text="", width=46, variable=enabled_var, onvalue=True, offvalue=False,
                **switch_style(), command=_toggled,
            ).grid(row=0, column=0, rowspan=2, sticky="w")
            ctk.CTkLabel(
                row, text=name, font=ctk.CTkFont(size=13, weight="bold"), text_color=T.TEXT, anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=(10, 0))
            ctk.CTkLabel(
                row, text=desc, font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w",
                justify="left", wraplength=520,
            ).grid(row=1, column=1, sticky="w", padx=(10, 0))
            if intensity_var is not None:
                def _changed(_v, cb=on_intensity) -> None:
                    if cb is not None:
                        cb()
                    app._persist_smart_editing_settings()

                seg = ctk.CTkSegmentedButton(
                    row, values=["Low", "Medium", "High"], variable=intensity_var, width=210, height=28,
                    **segmented_style(), font=ctk.CTkFont(size=12), command=_changed,
                )
                seg.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))
                seg.configure(state="normal" if enabled_var.get() else "disabled")
                self._intensity_controls.append((enabled_var, seg))
            return row

        _group("ON-SCREEN TEXT")
        _feature("Smart Text Styles",
                 "Short lines from the narration: statements, questions and quotes. Intensity = how often.",
                 app.smart_text_effects_var, app.smart_text_intensity_var)
        _feature("Graphics", "Name lower-thirds, statistic cards and titles.", app.smart_graphics_var)
        _feature("Map Niche",
                 "Countdown fact tags (\u201c34. THE ROOF OF FLORIDA\u201d), the \u201c35 WILD FACTS\u201d hook "
                 "and yellow number / name callouts.",
                 app.smart_map_niche_var)

        _group("MOTION")
        _feature("Ken Burns Zoom", "Slow zoom on every still image. Intensity = how far (5% / 10% / 16%).",
                 app.zoom_var, app.ken_burns_intensity_var)
        _feature("Visual Transitions",
                 "Transitions between scenes, including the zoom-blur into maps and new facts. "
                 "Intensity = how many.",
                 app.smart_visual_transitions_var, app.smart_transitions_intensity_var)

        _group("SOUND")
        _feature("Sound Effects", "Whooshes, hits and pops on cuts and text. Intensity = how loud / how many.",
                 app.smart_sfx_var, app.smart_sfx_intensity_var)
        # Picking an ambience intensity step re-syncs the fine volume control
        # back to Auto, so the choice never silently does nothing.
        _feature("Scene Ambience", "A quiet background sound bed for each scene (water, city, nature\u2026).",
                 app.smart_scene_ambience_var, app.smart_ambience_intensity_var,
                 on_intensity=self._on_ambience_volume_auto_silent)

        # Fine ambience level, right under its feature. The intensity step is
        # the coarse control; this overrides it and reads back the real level.
        amb_row = ctk.CTkFrame(smart, fg_color="transparent")
        amb_row.grid(row=_next_row(), column=0, sticky="ew", padx=(56, 0), pady=(2, 4))
        amb_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            amb_row, text="Ambience level", font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self._amb_vol_slider = ctk.CTkSlider(
            amb_row, from_=0.0, to=1.0, number_of_steps=100,
            command=self._on_ambience_volume,
        )
        self._amb_vol_slider.grid(row=0, column=1, sticky="ew")
        self._amb_vol_value = ctk.CTkLabel(
            amb_row, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="e", width=86,
        )
        self._amb_vol_value.grid(row=0, column=2, sticky="e", padx=(10, 8))
        self._amb_vol_auto = make_button(amb_row, "Auto", self._on_ambience_volume_auto, size="sm", width=58)
        self._amb_vol_auto.grid(row=0, column=3, sticky="e")
        self._sync_ambience_volume()

    def _sync_ambience_volume(self) -> None:
        """Push the current setting into the slider + readout."""
        app = self.app
        slider = getattr(self, "_amb_vol_slider", None)
        if slider is None:
            return
        level = app.effective_ambience_volume()
        is_auto = app.ambience_volume_override() is None
        slider.set(level)
        self._amb_vol_value.configure(
            text=f"{level * 100:.0f}%" + (" · auto" if is_auto else ""),
        )
        self._amb_vol_auto.configure(
            text_color=T.MUTED if is_auto else T.TEXT,
            border_color=T.BORDER if is_auto else T.ACCENT,
        )

    def _on_ambience_volume(self, value: float) -> None:
        self.app.smart_ambience_volume_var.set(round(float(value), 3))
        self.app._persist_smart_editing_settings()
        self._sync_ambience_volume()

    def _on_ambience_volume_auto(self) -> None:
        self.app.reset_ambience_volume_to_auto()
        self._sync_ambience_volume()

    def _on_ambience_volume_auto_silent(self) -> None:
        """Drop the override without persisting — the caller persists after."""
        self.app.smart_ambience_volume_var.set(-1.0)
        self.after(0, self._sync_ambience_volume)

    def _on_choose_audio(self) -> None:
        """Pick a different voiceover, then refresh this view so the
        Narration row reflects the new file immediately."""
        self.app._browse_audio()
        self.on_show()

    def _on_open_audio_folder(self) -> None:
        ws = self.app._workspace
        if ws is None:
            return
        import subprocess
        import sys

        folder = ws.audio_dir
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            elif sys.platform == "win32":
                import os

                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception:  # noqa: BLE001 - opening a folder is never critical path
            pass

    def on_show(self) -> None:
        audio = self.app.audio_var.get().strip()
        self._narr.set_value(Path(audio).name if audio and Path(audio).is_file() else "Not loaded")
        ws = self.app._workspace
        beds = sfx = 0
        if ws is not None:
            se = _load_json(ws.state_dir / "smart_editing.json")
            plan = (se.get("plan") or {}) if se else {}
            beds = len(plan.get("scene_ambience") or [])
            sfx = len(plan.get("sfx_events") or [])
        self._amb.set_value(str(beds) if beds else "—")
        self._sfx.set_value(str(sfx) if sfx else "—")
        # A project switch reloads the smart-editing settings, so re-read them.
        self._sync_ambience_volume()
        # A switch flipped elsewhere (e.g. Ken Burns in Settings) re-greys its intensity here.
        for enabled_var, seg in getattr(self, "_intensity_controls", []):
            try:
                seg.configure(state="normal" if enabled_var.get() else "disabled")
            except Exception:
                pass


class MusicView(_BaseView):
    key = "music"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Music", "An optional background track, automatically lowered under the narration.").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No music selected",
            "Add an optional background track. It is ducked automatically while the narrator speaks.",
            "Choose music…",
            command=self._browse,
            icon="\u266B",
        )
        self._empty.grid(row=0, column=0, sticky="ew", pady=(24, 0))
        self._card = Card(self._body, title="Background music")
        self._card.grid(row=1, column=0, sticky="ew")
        body = self._card.body
        self._track = MetricRow(body, "Track")
        self._track.grid(row=0, column=0, sticky="ew", pady=2)
        self._sections = MetricRow(body, "Sections")
        self._sections.grid(row=1, column=0, sticky="ew", pady=2)
        self._duck = MetricRow(body, "Ducking")
        self._duck.grid(row=2, column=0, sticky="ew", pady=2)
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="w", pady=(10, 0))
        make_button(actions, "Change track…", self._browse, width=130).pack(side="left")
        make_button(actions, "Remove", self._remove, variant="ghost", width=90).pack(side="left", padx=(6, 0))

    def _browse(self) -> None:
        self.app._browse_bg()
        self.on_show()

    def _remove(self) -> None:
        self.app.bg_var.set("")
        try:
            self.app._shell.notify("Background music removed", tone="info")
        except Exception:
            pass
        self.on_show()

    def on_show(self) -> None:
        path = self.app.bg_var.get().strip()
        has = bool(path) and Path(path).is_file()
        if not has:
            self._empty.grid()
            self._card.grid_remove()
            return
        self._empty.grid_remove()
        self._card.grid()
        self._track.set_value(Path(path).name)
        ws = self.app._workspace
        ep = _load_json(ws.state_dir / "editorial_plan.json") if ws else {}
        music = ep.get("music") or {}
        secs = music.get("sections") or ep.get("film", {}).get("sections") or []
        self._sections.set_value(
            ", ".join(s.get("role", "?") for s in secs[:5]) if secs else "—"
        )
        cues = music.get("cues") or []
        self._duck.set_value("Active" if cues else "Flat 0.15 (no envelope yet)")


class EditorialView(_BaseView):
    key = "editorial"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Editorial Stats", "How the last editorial plan paces, sounds and looks (read-only).").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No editorial plan yet",
            "The plan is built when you render (or align a voiceover). Its hook, pacing, audio and music "
            "choices show up here.",
            "Go to Export",
            command=lambda: app._shell.navigate("render") if getattr(app, "_shell", None) else None,
            icon="\u2261",
        )
        self._empty.grid(row=0, column=0, sticky="ew", pady=(24, 0))
        self._cards = ctk.CTkFrame(self._body, fg_color="transparent")
        self._cards.grid(row=1, column=0, sticky="ew")
        self._cards.grid_columnconfigure((0, 1), weight=1)
        self._hook = self._section_card(self._cards, "HOOK", 0, 0)
        self._visual = self._section_card(self._cards, "VISUAL", 0, 1)
        self._audio = self._section_card(self._cards, "AUDIO", 1, 0)
        self._music = self._section_card(self._cards, "MUSIC", 1, 1)
        self._pacing = self._section_card(self._cards, "PACING", 2, 0)
        self._qa = self._section_card(self._cards, "QA", 2, 1)

    def _section_card(self, parent, title, r, c):
        card = Card(parent, title=title if title == "QA" else title.title())
        card.grid(row=r, column=c, sticky="nsew", padx=(0 if c == 0 else 6, 6 if c == 0 else 0), pady=6)
        body = ctk.CTkLabel(
            card.body, text="—", font=ctk.CTkFont(size=12), text_color=T.MUTED,
            anchor="nw", justify="left", wraplength=380,
        )
        body.grid(row=0, column=0, sticky="ew")
        return body

    def on_show(self) -> None:
        ws = self.app._workspace
        ep = _load_json(ws.state_dir / "editorial_plan.json") if ws else {}
        qa = _load_json(ws.state_dir / "editorial_qa.json") if ws else {}
        scenes = ep.get("scenes") or []
        if not scenes:
            self._empty.grid()
            self._cards.grid_remove()
            return
        self._empty.grid_remove()
        self._cards.grid()
        hook_w = float(ep.get("hook_window_s") or 30)
        hook = [s for s in scenes if float(s.get("start") or 0) < hook_w]
        avg = (sum(float(s.get("attention_score") or 0) for s in hook) / len(hook)) if hook else 0
        self._hook.configure(
            text=f"Window {hook_w:.0f}s · {len(hook)} scenes\nAvg attention {avg:.2f}"
        )
        cams = Counter(str(s.get("camera_style") or "?") for s in scenes)
        self._visual.configure(
            text="\n".join(f"{k}: {v}" for k, v in cams.most_common(5)) or "—"
        )
        ambs = Counter(str(s.get("ambience_profile") or "?") for s in scenes)
        silent = sum(1 for s in scenes if s.get("allow_silence"))
        self._audio.configure(
            text=f"Profiles: {len(ambs)}\nSilence scenes: {silent}\n"
            + ", ".join(f"{k}={v}" for k, v in ambs.most_common(4))
        )
        music = ep.get("music") or {}
        secs = music.get("sections") or ep.get("film", {}).get("sections") or []
        self._music.configure(
            text=(" · ".join(s.get("role", "?") for s in secs) if secs else "No music plan")
            + (f"\n{len(music.get('cues') or [])} cues" if music.get("cues") else "")
        )
        tmap = sum(1 for s in scenes if s.get("transition_in") and s.get("transition_in") != "cut")
        dens = tmap / max(1, len(scenes) - 1)
        self._pacing.configure(text=f"Transitions {tmap} ({dens:.0%})\nScenes {len(scenes)}")
        score = qa.get("score")
        verdict = qa.get("verdict") or "—"
        self._qa.configure(
            text=f"{verdict}  {score:.0f}/100" if isinstance(score, (int, float)) else "No QA yet"
        )


class RenderView(_BaseView):
    """Export: is the project ready, one button that does the right next
    thing, and live progress while a run is going."""

    key = "render"

    # (label, progress fraction at which the step is finished) — the same
    # bands app.STAGE_PROGRESS writes into the top progress bar.
    _STEPS = (
        ("Preparing", 0.05),
        ("Visual assets", 0.25),
        ("Voiceover alignment", 0.50),
        ("Editorial plan", 0.70),
        ("Rendering scenes", 0.95),
        ("Final mix", 1.0),
    )

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Export", "Render the final video and follow its progress.").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._tick_id = None

        # Readiness + the one action.
        ready_card = Card(self._body, title="Ready to export",
                          subtitle="Everything the render needs, and what to do next.")
        ready_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        body = ready_card.body
        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew")
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="export_tiles")
        self._scenes_tile = StatTile(tiles, "Scenes")
        self._scenes_tile.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._voice_tile = StatTile(tiles, "Voiceover")
        self._voice_tile.grid(row=0, column=1, sticky="ew", padx=6)
        self._output_tile = StatTile(tiles, "Last output")
        self._output_tile.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self._action_btn = make_button(actions, "Render Video", app._on_primary_cta, variant="primary",
                                       size="lg", width=180)
        self._action_btn.pack(side="left")
        self._open_video_btn = make_button(actions, "\u25B6  Play video", app._open_in_player, width=130)
        self._open_video_btn.pack(side="left", padx=(8, 0))
        self._open_folder_btn = make_button(actions, "Open output folder", app._open_output_folder,
                                            variant="ghost", width=150)
        self._open_folder_btn.pack(side="left", padx=(4, 0))
        self._hint = ctk.CTkLabel(body, textvariable=app.hint_var, font=ctk.CTkFont(size=12),
                                  text_color=T.MUTED, anchor="w", justify="left", wraplength=640)
        self._hint.grid(row=2, column=0, sticky="w", pady=(10, 0))

        # Pipeline progress.
        prog_card = Card(self._body, title="Progress")
        prog_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        pb = prog_card.body
        pb.grid_columnconfigure(0, weight=0)
        pb.grid_columnconfigure(1, weight=1)
        self._phases = []
        for i, (name, _end) in enumerate(self._STEPS):
            dot = ctk.CTkLabel(pb, text="\u25CB", width=18, font=ctk.CTkFont(size=13), text_color=T.TEXT_TERTIARY)
            dot.grid(row=i, column=0, sticky="w", pady=3)
            lbl = ctk.CTkLabel(pb, text=name, font=ctk.CTkFont(size=13), text_color=T.MUTED, anchor="w")
            lbl.grid(row=i, column=1, sticky="w", padx=(8, 0), pady=3)
            pill = StatusPill(pb, "Waiting", "muted")
            pill.grid(row=i, column=2, sticky="e", pady=3)
            self._phases.append((dot, lbl, pill))
        self._bar = ctk.CTkProgressBar(pb, height=6, corner_radius=3, progress_color=T.ACCENT, fg_color=T.BORDER)
        self._bar.grid(row=len(self._STEPS), column=0, columnspan=3, sticky="ew", pady=(12, 6))
        self._bar.set(0)
        ctk.CTkLabel(
            pb, textvariable=app._export_progress_var, font=ctk.CTkFont(size=12), text_color=T.MUTED,
            justify="left", anchor="w",
        ).grid(row=len(self._STEPS) + 1, column=0, columnspan=3, sticky="w")
        # Kept for tests/legacy readers: the operation/output rows.
        self._op = MetricRow(pb, "Status")
        self._op.grid(row=len(self._STEPS) + 2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._out = MetricRow(pb, "Output file")
        self._out.grid(row=len(self._STEPS) + 3, column=0, columnspan=3, sticky="ew", pady=(2, 0))

        settings_card = Card(self._body, title="Output settings")
        settings_card.grid(row=2, column=0, sticky="ew")
        sb = settings_card.body
        self._resolution_row = MetricRow(sb, "Resolution")
        self._resolution_row.grid(row=0, column=0, sticky="ew", pady=2)
        self._fps_row = MetricRow(sb, "Frame rate")
        self._fps_row.grid(row=1, column=0, sticky="ew", pady=2)
        self._encoder_row = MetricRow(sb, "Video encoder")
        self._encoder_row.grid(row=2, column=0, sticky="ew", pady=2)

    # -- live refresh while the page is visible -------------------------

    def on_show(self) -> None:
        self._resolution_row.set_value("1920 \u00D7 1080")
        self._fps_row.set_value("30 fps")
        try:
            import video_generator as vg

            argv = vg._cpu_encode_argv()
            enc = argv[argv.index("-c:v") + 1] if "-c:v" in argv else "—"
        except Exception:
            enc = "—"
        self._encoder_row.set_value(enc)
        self._refresh()
        self._schedule()

    def _schedule(self) -> None:
        if self._tick_id is not None:
            return

        def tick() -> None:
            self._tick_id = None
            try:
                visible = self.winfo_ismapped()
            except Exception:
                return
            if visible:
                self._refresh()
                self._schedule()

        self._tick_id = self.after(700, tick)

    def _refresh(self) -> None:
        app = self.app
        running = bool(getattr(app, "_running", False))
        # Action button mirrors the top bar's primary action (same label,
        # same handler) so it can never say "Render" and do something else.
        cta = getattr(app, "generate_btn", None)
        if cta is not None:
            try:
                text = cta.cget("text")
                stop = text.strip().lower().startswith("stop")
                self._action_btn.configure(
                    text=text, state=cta.cget("state"),
                    fg_color="transparent" if stop else T.ACCENT,
                    hover_color=T.DANGER_BG if stop else T.ACCENT_HOV,
                    text_color=T.DANGER if stop else T.ACCENT_DARK,
                    border_width=1 if stop else 0, border_color=T.DANGER,
                )
            except Exception:
                pass

        snap = None
        try:
            if getattr(app, "_scene_rows", None):
                snap = app._qa_snapshot()
        except Exception:
            snap = None
        if snap is not None and snap.total:
            tone = "ok" if snap.ready >= snap.total else ("fail" if snap.needs_action else "warn")
            detail = f"{snap.needs_action} need attention" if snap.needs_action else (
                "All visuals ready" if snap.ready >= snap.total else "Visuals still missing")
            self._scenes_tile.set(f"{snap.ready}/{snap.total}", detail, tone)
        else:
            self._scenes_tile.set("—", "No scenes yet", "")
        audio = app.audio_var.get().strip()
        if audio and Path(audio).is_file():
            self._voice_tile.set("Loaded", Path(audio).name[:34], "ok")
        else:
            self._voice_tile.set("Missing", "Add it on Audio & Effects", "warn")
        out = app._last_output or app.output_var.get().strip() or ""
        has_out = bool(out) and Path(out).is_file()
        self._output_tile.set(Path(out).name[:26] if has_out else "None yet",
                              "Ready to play" if has_out else "Render to create one", "ok" if has_out else "")
        self._open_video_btn.configure(state="normal" if has_out else "disabled")
        self._open_folder_btn.configure(state="normal" if app._workspace is not None else "disabled")

        try:
            frac = float(app.progress.get())
        except Exception:
            frac = 0.0
        finished = not running and has_out and frac >= 0.99
        self._bar.set(frac if running else (1.0 if finished else 0.0))
        for i, (dot, lbl, pill) in enumerate(self._phases):
            end = self._STEPS[i][1]
            start = self._STEPS[i - 1][1] if i else 0.0
            if running and frac >= end:
                state = "done"
            elif running and frac >= start:
                state = "active"
            elif not running and has_out and frac >= 0.99:
                state = "done"
            else:
                state = "idle"
            if state == "done":
                dot.configure(text="\u2713", text_color=T.SUCCESS)
                lbl.configure(text_color=T.TEXT)
                pill.set_tone("Done", "ok")
            elif state == "active":
                dot.configure(text="\u25CF", text_color=T.ACCENT)
                lbl.configure(text_color=T.TEXT)
                pill.set_tone("Running", "run")
            else:
                dot.configure(text="\u25CB", text_color=T.TEXT_TERTIARY)
                lbl.configure(text_color=T.MUTED)
                pill.set_tone("Waiting", "muted")
        status = (app.status_var.get() or "").strip() if hasattr(app, "status_var") else ""
        self._op.set_value(status or ("Working\u2026" if running else "Idle"))
        self._out.set_value(Path(out).name if out else "—")


class GraphicsView(_BaseView):
    """Graphics placed by the Motion Design Engine (titles, lower thirds,
    statistics, callouts): turn each one on/off or edit its text. Edits are
    saved to the project's editorial timeline, which the next render reads."""

    key = "graphics"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(
            self, "Graphics",
            "Titles, lower thirds, statistics and callouts placed automatically. Turn any off or edit its text.",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 4))

        self._empty = EmptyState(
            self._body, "No graphics yet",
            "Graphics are placed automatically when you render with the Graphics switch on "
            "(Audio & Effects). After a render they appear here for review.",
            "Open Audio & Effects",
            command=lambda: app._shell.navigate("audio") if getattr(app, "_shell", None) else None,
            icon="\u2726",
        )
        self._empty.grid(row=0, column=0, sticky="ew", pady=(24, 0))

        self._list = ctk.CTkFrame(self._body, fg_color="transparent")
        self._list.grid(row=1, column=0, sticky="ew")
        self._list.grid_columnconfigure(0, weight=1)
        self._list.grid_remove()
        self._timeline = None
        self._rows: list = []

    def _reload(self) -> dict:
        import editorial_timeline_edit as tl_edit

        ws = self.app._workspace
        if ws is None:
            return {}
        self._timeline = tl_edit.load_timeline(ws.state_dir)
        return {"ws": ws}

    def _graphic_events(self):
        if self._timeline is None:
            return []
        return [e for e in self._timeline.events if (e.metadata or {}).get("graphic")]

    def on_show(self) -> None:
        ctx = self._reload()
        events = self._graphic_events()
        if not ctx or not events:
            self._empty.grid()
            self._list.grid_remove()
            return
        self._empty.grid_remove()
        self._list.grid()
        for w in self._rows:
            w.destroy()
        self._rows = []
        for ev in sorted(events, key=lambda e: e.start):
            self._rows.append(self._build_row(ev))

    def _build_row(self, ev):
        meta = ev.metadata or {}
        row = Card(self._list)
        row.grid(sticky="ew", pady=4)
        row.grid_columnconfigure(1, weight=1)
        disabled = bool(meta.get("disabled"))

        var = ctk.BooleanVar(value=not disabled)
        ctk.CTkSwitch(
            row, text="", variable=var, width=40, **switch_style(),
            command=lambda: self._toggle(ev.event_id, var),
        ).grid(row=0, column=0, rowspan=2, padx=(14, 6), pady=10)

        role = str(meta.get("role") or ev.track)
        text_overlay = meta.get("text_overlay") or {}
        preview = text_overlay.get("text") or (ev.source.split("|")[0] if ev.source else role)
        label_var = ctk.StringVar(value=str(preview)[:60])
        pretty_role = role.replace("_", " ").title()
        ctk.CTkLabel(
            row, text=f"{pretty_role}  \u00B7  scene {ev.scene_number or '—'}  \u00B7  {ev.start:.1f}s \u2013 {ev.end:.1f}s",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(4, 14), pady=(10, 2))
        entry = ctk.CTkEntry(
            row, textvariable=label_var, height=30, 
        )
        entry.grid(row=1, column=1, sticky="ew", padx=(4, 14), pady=(0, 12))
        entry.bind("<Return>", lambda _e, eid=ev.event_id, v=label_var: self._rename(eid, v))
        entry.bind("<FocusOut>", lambda _e, eid=ev.event_id, v=label_var: self._rename(eid, v))
        if disabled:
            entry.configure(state="disabled")
        return row

    def _toggle(self, event_id: str, var) -> None:
        import editorial_timeline_edit as tl_edit

        ev = tl_edit.find_event(self._timeline, event_id)
        if ev is None:
            return
        ev.metadata = dict(ev.metadata or {})
        ev.metadata["disabled"] = not bool(var.get())
        self._persist()
        self.on_show()

    def _rename(self, event_id: str, label_var) -> None:
        import editorial_timeline_edit as tl_edit

        ev = tl_edit.find_event(self._timeline, event_id)
        if ev is None:
            return
        ev.metadata = dict(ev.metadata or {})
        overlay = dict(ev.metadata.get("text_overlay") or {})
        if overlay.get("text") == label_var.get():
            return  # focus left without a change — nothing to save
        overlay["text"] = label_var.get()
        ev.metadata["text_overlay"] = overlay
        self._persist()
        try:
            self.app._shell.notify("Graphic text saved", tone="success")
        except Exception:
            pass

    def _persist(self) -> None:
        import editorial_timeline_edit as tl_edit

        ws = self.app._workspace
        if ws is None or self._timeline is None:
            return
        if hasattr(self.app, "_mark_saving"):
            self.app._mark_saving()
        ok = tl_edit.save_timeline(ws.state_dir, self._timeline)
        if ok and hasattr(self.app, "_mark_saved"):
            self.app._mark_saved()


class QAView(_BaseView):
    key = "qa"

    _CATEGORIES = ("Visual", "Audio", "Pacing", "Music", "Ambience", "Asset Health")

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Quality Check",
                      "An automatic scorecard of the last render. It never blocks export.").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No quality report yet",
            "The report is written after each successful render: an overall score, a verdict "
            "and the scenes worth a second look.",
            "Go to Export",
            command=lambda: app._shell.navigate("render") if getattr(app, "_shell", None) else None,
            icon="\u2713",
        )
        self._empty.grid(row=0, column=0, sticky="ew", pady=(24, 0))

        self._head = Card(self._body)
        self._head.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self._head.grid_columnconfigure(1, weight=1)
        self._score = ctk.CTkLabel(
            self._head, text="—", font=ctk.CTkFont(size=40, weight="bold"), text_color=T.TEXT,
        )
        self._score.grid(row=0, column=0, rowspan=2, sticky="w", padx=(20, 14), pady=16)
        ctk.CTkLabel(self._head, text="OVERALL SCORE", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=T.TEXT_TERTIARY, anchor="w").grid(row=0, column=1, sticky="sw", pady=(18, 0))
        self._verdict = StatusPill(self._head, "—", "muted")
        self._verdict.grid(row=1, column=1, sticky="nw", pady=(4, 18))

        cats = Card(self._body, title="By category")
        cats.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self._cats = cats
        grid = ctk.CTkFrame(cats.body, fg_color="transparent")
        grid.grid(row=0, column=0, sticky="ew")
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="qa_cats")
        self._cat_rows: dict = {}
        for i, name in enumerate(self._CATEGORIES):
            cell = ctk.CTkFrame(grid, fg_color=T.PANEL_ALT, corner_radius=T.RADIUS)
            cell.grid(row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
            cell.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(cell, text=name, font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w").grid(
                row=0, column=0, sticky="w", padx=12, pady=10)
            pill = StatusPill(cell, "—", "muted")
            pill.grid(row=0, column=1, sticky="e", padx=10)
            self._cat_rows[name] = _PillValue(pill)

        issues_card = Card(self._body, title="Findings")
        issues_card.grid(row=3, column=0, sticky="ew")
        self._issues_card = issues_card
        self._issues = ctk.CTkTextbox(
            issues_card.body, height=200, 
            font=ctk.CTkFont(size=12),
        )
        self._issues.grid(row=0, column=0, sticky="ew")

    def on_show(self) -> None:
        ws = self.app._workspace
        qa = _load_json(ws.state_dir / "editorial_qa.json") if ws else {}
        if not qa:
            self._empty.grid()
            self._head.grid_remove()
            self._cats.grid_remove()
            self._issues_card.grid_remove()
            return
        self._empty.grid_remove()
        self._head.grid()
        self._cats.grid()
        self._issues_card.grid()
        score = qa.get("score")
        verdict = str(qa.get("verdict") or "—")
        self._score.configure(text=f"{score:.0f}" if isinstance(score, (int, float)) else "—")
        tone = "pass" if verdict == "PASS" else ("warn" if verdict == "WARN" else "fail")
        self._verdict.set_tone(verdict, tone)
        issues = qa.get("issues") or []
        by_cat = Counter(str(i.get("category") or "other") for i in issues)
        mapping = {
            "Visual": ("camera", "repetition", "hook"),
            "Audio": ("levels",),
            "Pacing": ("transitions", "timeline"),
            "Music": ("music",),
            "Ambience": ("ambience",),
            "Asset Health": ("assets", "black_frozen", "coverage"),
        }
        for label, keys in mapping.items():
            hit = [i for i in issues if i.get("category") in keys]
            if not hit:
                self._cat_rows[label].set_value("PASS")
            elif any(i.get("severity") == "FAIL" for i in hit):
                self._cat_rows[label].set_value("FAIL")
            else:
                self._cat_rows[label].set_value("WARN")
        self._issues.delete("1.0", "end")
        if not issues:
            self._issues.insert("1.0", "No issues detected.\n")
        else:
            for i in issues[:40]:
                self._issues.insert(
                    "end",
                    f"{i.get('severity', '—'):<5}  Scene {i.get('scene_number')}  \u00B7  "
                    f"{float(i.get('timestamp') or 0):.1f}s  \u00B7  {i.get('message')}\n",
                )


class _PillValue:
    """MetricRow-compatible wrapper (set_value) around a StatusPill."""

    _TONES = {"PASS": "ok", "WARN": "warn", "FAIL": "fail"}

    def __init__(self, pill: StatusPill):
        self.pill = pill

    def set_value(self, value: str) -> None:
        self.pill.set_tone(value, self._TONES.get(str(value).upper(), "muted"))


def _load_json(path: Path) -> dict:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


class AboutOwnershipView(_BaseView):
    """Permanent About & Ownership reference page.

    Renders the SAME content as the first-login acknowledgement (both read
    licensing.terms), so the two can never drift apart. Read-only: the
    acknowledgement itself is made once, at login.
    """

    key = "about"

    def __init__(self, master, app):
        super().__init__(master, app)
        from licensing import terms as _terms

        SectionHeader(
            self,
            _terms.TITLE,
            "Application, development ownership, and YouTube channel/project arrangements",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, T.PAD_SM))

        # Brand lockup at the top of the ownership page — this is the page that
        # talks about the product and who built it, so it earns the wordmark.
        from ui import branding as _branding

        _wordmark = _branding.wordmark_image(44)
        if _wordmark is not None:
            _brand = Card(self._body)
            _brand.grid(row=0, column=0, sticky="ew", pady=(0, T.PAD))
            _brand.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(_brand, image=_wordmark, text="", fg_color="transparent").grid(
                row=0, column=0, sticky="w", padx=T.PAD, pady=T.PAD
            )

        body = self._body
        row = 1 if _wordmark is not None else 0

        account = Card(body)
        account.grid(row=row, column=0, sticky="ew", pady=(0, T.PAD))
        account.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            account, text="Account", text_color=T.TEXT, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=T.PAD, pady=(T.PAD, T.PAD_SM))
        self._account_row = MetricRow(account, "Signed in as", "—")
        self._account_row.grid(row=1, column=0, sticky="ew", padx=T.PAD)
        self._terms_row = MetricRow(account, "Terms version", _terms.CURRENT_TERMS_VERSION)
        self._terms_row.grid(row=2, column=0, sticky="ew", padx=T.PAD, pady=(0, T.PAD))
        row += 1

        for heading, paragraphs in _terms.SECTIONS:
            card = Card(body)
            card.grid(row=row, column=0, sticky="ew", pady=(0, T.PAD))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card, text=heading, text_color=T.TEXT, anchor="w",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=T.PAD, pady=(T.PAD, T.PAD_SM))
            for i, para in enumerate(paragraphs, start=1):
                highlight = para == _terms.OWNERSHIP_HIGHLIGHT
                ctk.CTkLabel(
                    card, text=para,
                    # Noticeable, deliberately not an alarm colour.
                    text_color=T.TEXT if highlight else T.MUTED,
                    font=ctk.CTkFont(size=12, weight="bold" if highlight else "normal"),
                    anchor="w", justify="left", wraplength=720,
                ).grid(row=i, column=0, sticky="w", padx=T.PAD,
                       pady=(0, T.PAD if i == len(paragraphs) else 6))
            row += 1

        ack = Card(body)
        ack.grid(row=row, column=0, sticky="ew", pady=(0, T.PAD))
        ack.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            ack, text="User Acknowledgement", text_color=T.TEXT, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=T.PAD, pady=(T.PAD, T.PAD_SM))
        for i, point in enumerate(_terms.ACKNOWLEDGEMENT_POINTS, start=1):
            ctk.CTkLabel(
                ack, text=f"\u2022  {point}", text_color=T.MUTED, anchor="w",
                justify="left", wraplength=710, font=ctk.CTkFont(size=12),
            ).grid(row=i, column=0, sticky="w", padx=T.PAD, pady=(0, 5))
        ctk.CTkLabel(
            ack, text=_terms.LEGAL_NOTE, text_color=T.TEXT, anchor="w",
            justify="left", wraplength=710, font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=len(_terms.ACKNOWLEDGEMENT_POINTS) + 1, column=0, sticky="w",
               padx=T.PAD, pady=(T.PAD_SM, T.PAD))

    def on_show(self) -> None:
        """Display name only — never email, tokens or internal ids."""
        session = getattr(self.app, "_auth_session", None)
        name = (getattr(session, "display_name", "") or "").strip() if session else ""
        self._account_row.set_value(name or "—")
