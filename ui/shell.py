"""Application shell: sidebar + topbar + center stack + inspector + status bar."""

from __future__ import annotations

from typing import Callable, Dict, Optional

import customtkinter as ctk

from . import theme as T


class AppShell(ctk.CTkFrame):
    """Production workstation chrome. Controller owns callbacks and CTA."""

    def __init__(
        self,
        master,
        *,
        on_nav: Callable[[str], None],
        on_switch_project: Callable[[], None],
        on_settings: Callable[[], None],
        on_close_instances: Callable[[], None],
        on_primary_cta: Callable[[], None],
        on_toggle_issues: Callable[[], None],
        project_chip_var,
        stage_var,
        hint_var,
        qa_counter_var,
        status_line_var,
        cache_var,
        logo_image=None,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.BG, **kwargs)
        self._on_nav = on_nav
        self._active = "script"
        self._nav_btns: Dict[str, ctk.CTkButton] = {}
        self.views: Dict[str, ctk.CTkFrame] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar(
            project_chip_var=project_chip_var,
            stage_var=stage_var,
            cache_var=cache_var,
            qa_counter_var=qa_counter_var,
            logo_image=logo_image,
            on_switch_project=on_switch_project,
            on_settings=on_settings,
            on_close_instances=on_close_instances,
            on_primary_cta=on_primary_cta,
            on_toggle_issues=on_toggle_issues,
        )
        self._build_sidebar()
        self._build_center()
        self._build_inspector()
        self._build_statusbar(hint_var=hint_var, status_line_var=status_line_var)

    def _build_topbar(self, **kw) -> None:
        top = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, height=T.TOPBAR_HEIGHT)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        self.topbar = top

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)
        if kw.get("logo_image") is not None:
            ctk.CTkLabel(left, image=kw["logo_image"], text="", fg_color="transparent").pack(
                side="left", padx=(0, 8)
            )
        chip = ctk.CTkFrame(
            left, fg_color=T.CARD, corner_radius=T.RADIUS, border_width=1, border_color=T.BORDER,
        )
        chip.pack(side="left", padx=(0, 6))
        self.project_chip_label = ctk.CTkLabel(
            chip, textvariable=kw["project_chip_var"],
            font=ctk.CTkFont(size=13, weight="bold"), text_color=T.TEXT,
        )
        self.project_chip_label.pack(side="left", padx=10, pady=6)
        ctk.CTkButton(
            left, text="Switch", width=72, height=28,
            fg_color="transparent", border_width=1, border_color=T.BORDER,
            text_color=T.TEXT, hover_color=T.CARD_HOVER, font=ctk.CTkFont(size=12),
            command=kw["on_switch_project"],
        ).pack(side="left")

        mid = ctk.CTkFrame(top, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="ew", padx=8)
        mid.grid_columnconfigure(0, weight=1)
        self.stage_label = ctk.CTkLabel(
            mid, textvariable=kw["stage_var"],
            font=ctk.CTkFont(size=12, weight="bold"), text_color=T.ACCENT, anchor="w",
        )
        self.stage_label.grid(row=0, column=0, sticky="w")
        self.cache_label = ctk.CTkLabel(
            mid, textvariable=kw["cache_var"],
            font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
        )
        self.cache_label.grid(row=1, column=0, sticky="w")

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=(8, 12), pady=8)
        self.issues_toggle_btn = ctk.CTkButton(
            right, textvariable=kw["qa_counter_var"], width=88, height=28,
            fg_color="transparent", border_width=1, border_color=T.DANGER,
            text_color=T.DANGER, hover_color=T.DANGER_BG,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=kw["on_toggle_issues"],
        )
        self.issues_toggle_btn.pack(side="left", padx=(0, 6))
        self.issues_toggle_btn.pack_forget()

        ctk.CTkButton(
            right, text="Close instances", width=118, height=28,
            fg_color="transparent", border_width=1, border_color=T.BORDER,
            text_color=T.TEXT, hover_color=T.CARD_HOVER, font=ctk.CTkFont(size=11),
            command=kw["on_close_instances"],
        ).pack(side="left", padx=(0, 6))

        self.generate_btn = ctk.CTkButton(
            right, text="Choose project", width=140, height=30,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=kw["on_primary_cta"],
        )
        self.generate_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            right, text="⚙", width=34, height=30,
            fg_color="transparent", border_width=1, border_color=T.BORDER,
            text_color=T.TEXT, hover_color=T.CARD_HOVER, font=ctk.CTkFont(size=15),
            command=kw["on_settings"],
        ).pack(side="left")

        self.progress = ctk.CTkProgressBar(
            top, height=3, progress_color=T.ACCENT, fg_color=T.BORDER, corner_radius=1,
        )
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.progress.set(0)

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, width=T.SIDEBAR_WIDTH)
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        self.sidebar = side
        ctk.CTkLabel(
            side, text="WORKSPACE", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        for i, (key, label) in enumerate(T.NAV_ITEMS):
            btn = ctk.CTkButton(
                side, text=label, height=28, anchor="w",
                fg_color="transparent", hover_color=T.CARD_HOVER,
                text_color=T.MUTED, font=ctk.CTkFont(size=12),
                corner_radius=T.RADIUS,
                command=lambda k=key: self.navigate(k),
            )
            btn.grid(row=i + 1, column=0, sticky="ew", padx=6, pady=0)
            self._nav_btns[key] = btn

    def _build_center(self) -> None:
        center = ctk.CTkFrame(self, fg_color=T.PANEL_ALT, corner_radius=0)
        center.grid(row=1, column=1, sticky="nsew")
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)
        self.center = center

    def _build_inspector(self) -> None:
        insp = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, width=T.INSPECTOR_WIDTH)
        insp.grid(row=1, column=2, sticky="nsew")
        insp.grid_propagate(False)
        insp.grid_columnconfigure(0, weight=1)
        insp.grid_rowconfigure(1, weight=1)
        self.inspector = insp
        ctk.CTkLabel(
            insp, text="INSPECTOR", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        self.inspector_body = ctk.CTkScrollableFrame(
            insp, fg_color="transparent",
            scrollbar_button_color=T.BORDER, scrollbar_button_hover_color=T.ACCENT,
        )
        self.inspector_body.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 6))
        self.inspector_body.grid_columnconfigure(0, weight=1)

    def _build_statusbar(self, *, hint_var, status_line_var) -> None:
        bar = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, height=T.STATUSBAR_HEIGHT)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        self.statusbar = bar
        ctk.CTkLabel(
            bar, textvariable=hint_var, font=ctk.CTkFont(size=11),
            text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkLabel(
            bar, textvariable=status_line_var, font=ctk.CTkFont(size=11),
            text_color=T.TEXT, anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=12, pady=8)

    def register_view(self, key: str, frame: ctk.CTkFrame) -> None:
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_remove()
        self.views[key] = frame

    def navigate(self, key: str) -> None:
        if key not in self.views:
            return
        for k, fr in self.views.items():
            if k == key:
                fr.grid()
            else:
                fr.grid_remove()
        self._active = key
        for k, btn in self._nav_btns.items():
            if k == key:
                btn.configure(fg_color=T.ACCENT_SEL, text_color=T.TEXT, border_width=1, border_color=T.ACCENT_BORDER)
            else:
                btn.configure(fg_color="transparent", text_color=T.MUTED, border_width=0)
        self._on_nav(key)

    @property
    def active_view(self) -> str:
        return self._active
