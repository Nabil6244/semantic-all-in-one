"""Application shell: top bar + sidebar + page stack + inspector + status bar."""

from __future__ import annotations

from typing import Callable, Dict, Optional

import customtkinter as ctk

from . import icons as I
from . import theme as T
from . import tooltip as TT
from .widgets import Toast, button_style

# Pages that show the right-hand scene inspector.
INSPECTOR_VIEWS = frozenset({"visual_plan"})

_NAV_LABELS = {key: label for key, label, _group in T.NAV_ITEMS}


def _app_version() -> str:
    try:
        from app_version import APP_VERSION

        return str(APP_VERSION)
    except Exception:
        return ""


class AppShell(ctk.CTkFrame):
    """Production workstation chrome. The controller (app.py) owns the
    callbacks and the state behind the primary call-to-action."""

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
        on_toggle_theme: Optional[Callable[[], None]] = None,
        theme_label_var=None,
        save_state_var=None,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.BG, corner_radius=0, **kwargs)
        self._on_nav = on_nav
        self._active = "script"
        self._nav_btns: Dict[str, ctk.CTkButton] = {}
        self._nav_bars: Dict[str, ctk.CTkFrame] = {}
        self.views: Dict[str, ctk.CTkFrame] = {}
        self._factories: Dict[str, Callable[[], ctk.CTkFrame]] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar(
            project_chip_var=project_chip_var,
            stage_var=stage_var,
            hint_var=hint_var,
            qa_counter_var=qa_counter_var,
            logo_image=logo_image,
            on_switch_project=on_switch_project,
            on_settings=on_settings,
            on_close_instances=on_close_instances,
            on_primary_cta=on_primary_cta,
            on_toggle_issues=on_toggle_issues,
            on_toggle_theme=on_toggle_theme,
            theme_label_var=theme_label_var,
            save_state_var=save_state_var,
        )
        self._build_sidebar()
        self._build_center()
        self._build_inspector()
        self._build_statusbar(cache_var=cache_var, status_line_var=status_line_var)

    # ------------------------------------------------------------------
    # Top bar
    # ------------------------------------------------------------------

    def _build_topbar(self, **kw) -> None:
        top = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, height=T.TOPBAR_HEIGHT)
        top.grid(row=0, column=0, columnspan=3, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        self.topbar = top

        # Left: brand + project switcher.
        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=(14, 8), pady=9)
        if kw.get("logo_image") is not None:
            ctk.CTkLabel(left, image=kw["logo_image"], text="", fg_color="transparent").pack(
                side="left", padx=(0, 8)
            )
        self.brand_label = ctk.CTkLabel(
            left, text="Semantic YT Studio", font=ctk.CTkFont(size=13, weight="bold"), text_color=T.TEXT,
        )
        self.brand_label.pack(side="left", padx=(0, 12))
        self._brand_divider = ctk.CTkFrame(left, fg_color=T.BORDER, width=1, height=22, corner_radius=0)
        self._brand_divider.pack(side="left", padx=(0, 12))
        chip_style = button_style("ghost")
        chip_style.update(text_color=T.TEXT, font=ctk.CTkFont(size=13, weight="bold"), height=30)
        self.project_chip_label = ctk.CTkButton(
            left, textvariable=kw["project_chip_var"], command=kw["on_switch_project"], width=40,
            **chip_style,
        )
        self.project_chip_label.pack(side="left")
        self._chip_caret = ctk.CTkLabel(left, text="▾", text_color=T.MUTED, font=ctk.CTkFont(size=12))
        self._chip_caret.pack(side="left", padx=(0, 4))
        self._chip_caret.bind("<Button-1>", lambda _e: kw["on_switch_project"]())
        TT.attach(self.project_chip_label, "Switch or create a project")

        # Middle: current page + next-step guidance.
        mid = ctk.CTkFrame(top, fg_color="transparent")
        mid.grid(row=0, column=1, sticky="ew", padx=12)
        mid.grid_columnconfigure(2, weight=1)
        self.page_title = ctk.CTkLabel(
            mid, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=T.TEXT, anchor="w",
        )
        self.page_title.grid(row=0, column=0, sticky="w")
        self.stage_label = ctk.CTkLabel(
            mid, textvariable=kw["stage_var"], font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T.ACCENT, fg_color=T.ACCENT_SEL, corner_radius=10, height=20, padx=8,
        )
        self.stage_label.grid(row=0, column=1, sticky="w", padx=(10, 8))
        self.hint_label = ctk.CTkLabel(
            mid, textvariable=kw["hint_var"], font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w",
        )
        self.hint_label.grid(row=0, column=2, sticky="ew")

        # Right: status + utilities + the one primary action.
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=(8, 14), pady=9)
        issues_style = button_style("danger", "sm")
        issues_style.update(corner_radius=13, font=ctk.CTkFont(size=11, weight="bold"), height=28)
        self.issues_toggle_btn = ctk.CTkButton(
            right, textvariable=kw["qa_counter_var"], width=84, command=kw["on_toggle_issues"], **issues_style,
        )
        self.issues_toggle_btn.pack(side="left", padx=(0, 8))
        self.issues_toggle_btn.pack_forget()
        TT.attach(self.issues_toggle_btn, "Show the scenes that need attention")

        if kw.get("save_state_var") is not None:
            self.save_state_label = ctk.CTkLabel(
                right, textvariable=kw["save_state_var"], font=ctk.CTkFont(size=11), text_color=T.TEXT_TERTIARY,
            )
            self.save_state_label.pack(side="left", padx=(0, 10))

        self.close_instances_btn = ctk.CTkButton(
            right, text="Close browsers", width=112, command=kw["on_close_instances"],
            **button_style("ghost", "md"),
        )
        self.close_instances_btn.pack(side="left", padx=(0, 4))
        TT.attach(self.close_instances_btn, "Close every Flow Chrome window left open by generation or sign-in")

        icon_style = button_style("ghost", "md")
        icon_style.update(font=ctk.CTkFont(size=15), text_color=T.MUTED)
        if kw.get("on_toggle_theme") is not None:
            theme_kwargs = {}
            if kw.get("theme_label_var") is not None:
                theme_kwargs["textvariable"] = kw["theme_label_var"]
            else:
                theme_kwargs["text"] = I.icon("theme_dark")
            self.theme_btn = ctk.CTkButton(
                right, width=T.ICON_BTN_W + 4, command=kw["on_toggle_theme"], **icon_style, **theme_kwargs,
            )
            self.theme_btn.pack(side="left", padx=(0, 2))
            TT.attach(self.theme_btn, "Appearance: Dark / Light / System")

        self.settings_btn = ctk.CTkButton(
            right, text=I.icon("settings"), width=T.ICON_BTN_W + 4, command=kw["on_settings"], **icon_style,
        )
        self.settings_btn.pack(side="left", padx=(0, 10))
        TT.attach(self.settings_btn, "Settings")

        cta_style = button_style("primary", "lg")
        cta_style.update(height=34)
        self.generate_btn = ctk.CTkButton(
            right, text="Choose project", width=150, command=kw["on_primary_cta"], **cta_style,
        )
        self.generate_btn.pack(side="left")

        self.progress = ctk.CTkProgressBar(
            top, height=2, progress_color=T.ACCENT, fg_color=T.PANEL, corner_radius=0,
        )
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.progress.set(0)
        ctk.CTkFrame(top, fg_color=T.BORDER, height=1, corner_radius=0).grid(
            row=2, column=0, columnspan=3, sticky="ew")

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, width=T.SIDEBAR_WIDTH)
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        self.sidebar = side

        row = 0
        current_group = None
        self._group_headers: list = []
        for key, label, group in T.NAV_ITEMS:
            if group != current_group:
                header = ctk.CTkLabel(
                    side, text=T.NAV_GROUP_LABELS.get(group, group.upper()),
                    font=ctk.CTkFont(size=10, weight="bold"), text_color=T.TEXT_TERTIARY, anchor="w",
                )
                header.grid(row=row, column=0, sticky="ew", padx=(20, 12),
                            pady=(18 if current_group is None else 20, 6))
                self._group_headers.append(header)
                current_group = group
                row += 1
            item = ctk.CTkFrame(side, fg_color="transparent", height=34)
            item.grid(row=row, column=0, sticky="ew", padx=(0, 10), pady=1)
            item.grid_columnconfigure(1, weight=1)
            bar = ctk.CTkFrame(item, fg_color="transparent", width=3, height=20, corner_radius=2)
            bar.grid(row=0, column=0, sticky="w", padx=(0, 7))
            btn = ctk.CTkButton(
                item, text=f"{T.NAV_ICONS.get(key, '•')}   {label}", height=34, anchor="w",
                fg_color="transparent", hover_color=T.CARD_HOVER,
                text_color=T.MUTED, font=ctk.CTkFont(size=13),
                corner_radius=T.RADIUS,
                command=lambda k=key: self.navigate(k),
            )
            btn.grid(row=0, column=1, sticky="ew")
            self._nav_btns[key] = btn
            self._nav_bars[key] = bar
            row += 1

        side.grid_rowconfigure(row, weight=1)
        version = _app_version()
        self.version_label = ctk.CTkLabel(
            side, text=f"Version {version}" if version else "", font=ctk.CTkFont(size=10),
            text_color=T.TEXT_TERTIARY, anchor="w",
        )
        self.version_label.grid(row=row + 1, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkFrame(self, fg_color=T.BORDER, width=1, corner_radius=0).grid(
            row=1, column=0, sticky="nse")

    def _paint_nav(self) -> None:
        for k, btn in self._nav_btns.items():
            active = k == self._active
            btn.configure(
                fg_color=T.ACCENT_SEL if active else "transparent",
                text_color=T.TEXT if active else T.MUTED,
                hover_color=T.ACCENT_SEL if active else T.CARD_HOVER,
                font=ctk.CTkFont(size=13, weight="bold" if active else "normal"),
            )
            bar = self._nav_bars.get(k)
            if bar is not None:
                bar.configure(fg_color=T.ACCENT if active else "transparent")

    # ------------------------------------------------------------------
    # Centre, inspector, status bar
    # ------------------------------------------------------------------

    def _build_center(self) -> None:
        center = ctk.CTkFrame(self, fg_color=T.PANEL_ALT, corner_radius=0)
        center.grid(row=1, column=1, sticky="nsew")
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)
        self.center = center

        # One reusable toast over the page area, never stacking.
        self.toast = Toast(center)

    def notify(self, message: str, *, tone: str = "info") -> None:
        """Best-effort — a missing/failed toast host never blocks the
        action that triggered it."""
        try:
            self.toast.show(message, tone=tone)
        except Exception:
            pass

    def _build_inspector(self) -> None:
        insp = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, width=T.INSPECTOR_WIDTH)
        insp.grid(row=1, column=2, sticky="nsew")
        insp.grid_propagate(False)
        insp.grid_columnconfigure(1, weight=1)
        insp.grid_rowconfigure(1, weight=1)
        self.inspector = insp
        ctk.CTkFrame(insp, fg_color=T.BORDER, width=1, corner_radius=0).grid(
            row=0, column=0, rowspan=2, sticky="nsw")
        self.inspector_title = ctk.CTkLabel(
            insp, text="Scene inspector", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=T.TEXT, anchor="w",
        )
        self.inspector_title.grid(row=0, column=1, sticky="ew", padx=16, pady=(14, 4))
        self.inspector_body = ctk.CTkScrollableFrame(
            insp, fg_color="transparent",
            scrollbar_button_color=T.BORDER, scrollbar_button_hover_color=T.BORDER_STRONG,
        )
        self.inspector_body.grid(row=1, column=1, sticky="nsew", padx=4, pady=(0, 8))
        self.inspector_body.grid_columnconfigure(0, weight=1)

    def _build_statusbar(self, *, cache_var, status_line_var) -> None:
        bar = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0, height=T.STATUSBAR_HEIGHT)
        bar.grid(row=2, column=0, columnspan=3, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)
        self.statusbar = bar
        ctk.CTkFrame(bar, fg_color=T.BORDER, height=1, corner_radius=0).grid(
            row=0, column=0, columnspan=4, sticky="ew")
        self.status_dot = ctk.CTkLabel(bar, text="●", font=ctk.CTkFont(size=9), text_color=T.SUCCESS)
        self.status_dot.grid(row=1, column=0, sticky="w", padx=(14, 6), pady=5)
        self.cache_label = ctk.CTkLabel(
            bar, textvariable=cache_var, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w",
        )
        self.cache_label.grid(row=1, column=1, sticky="w", pady=5)
        self.status_line_label = ctk.CTkLabel(
            bar, textvariable=status_line_var, font=ctk.CTkFont(size=11), text_color=T.TEXT_TERTIARY,
            anchor="e",
        )
        self.status_line_label.grid(row=1, column=3, sticky="e", padx=14, pady=5)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def register_view(self, key: str, frame) -> None:
        """Register a page, or a zero-argument factory that builds it the
        first time it's needed (see ``view``)."""
        if callable(frame) and not isinstance(frame, ctk.CTkBaseClass) and not hasattr(frame, "winfo_exists"):
            self._factories[key] = frame
            return
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_remove()
        self.views[key] = frame

    def view(self, key: str):
        """The page for ``key``, building a lazily-registered one on first use."""
        if key not in self.views and key in self._factories:
            self.register_view(key, self._factories.pop(key)())
        return self.views.get(key)

    def navigate(self, key: str) -> None:
        if self.view(key) is None:
            return
        for k, fr in self.views.items():
            if k == key:
                fr.grid()
            else:
                fr.grid_remove()
        self._active = key
        # The inspector acts on the selected scene, which only the Visuals
        # page shows — elsewhere it was an empty panel, so hide it.
        if key in INSPECTOR_VIEWS:
            self.inspector.grid()
        else:
            self.inspector.grid_remove()
        self.page_title.configure(text=_NAV_LABELS.get(key, ""))
        self._paint_nav()
        self._on_nav(key)

    @property
    def active_view(self) -> str:
        return self._active

    def apply_theme_chrome(self) -> None:
        """Re-apply the state-dependent colours (active nav item, primary
        button) after a live theme switch; everything else is repainted by
        ui.theme.recolor_widget_tree."""
        try:
            self._paint_nav()
            self.progress.configure(progress_color=T.ACCENT, fg_color=T.PANEL)
        except Exception:
            # Live re-theming is a bonus on top of the persisted preference,
            # which always applies correctly on next launch — never raise.
            pass
