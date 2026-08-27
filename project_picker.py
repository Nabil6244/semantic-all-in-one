"""Reusable project-picker modal for Semantic YT Studio.

Public API (imported by app.py):

    ProjectPickerDialog
    project_dicts_from_workspaces
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from ui import theme as _ui_theme

__all__ = ["ProjectPickerDialog", "project_dicts_from_workspaces"]

# Single source: ui.theme
_BG = _ui_theme.BG
_PANEL = _ui_theme.PANEL
_CARD = _ui_theme.CARD
_CARD_HOVER = _ui_theme.CARD_HOVER
_BORDER = _ui_theme.BORDER
_TEXT = _ui_theme.TEXT
_MUTED = _ui_theme.MUTED
_ACCENT = _ui_theme.ACCENT
_ACCENT_HOV = _ui_theme.ACCENT_HOV
_ACCENT_DARK = _ui_theme.ACCENT_DARK

_EMPTY_HINT = "No projects yet — create one to start."
_TITLE_PLACEHOLDER = "Video title (optional)"


def project_dicts_from_workspaces(workspaces, last_id: str = "") -> list[dict]:
    """workspaces: iterable of objects with .project_id, .title, .display_seq()"""
    last = str(last_id or "")
    out: list[dict] = []
    for ws in workspaces or ():
        pid = str(getattr(ws, "project_id", "") or "")
        title = str(getattr(ws, "title", "") or "")
        seq = _workspace_display_seq(ws)
        out.append({
            "id": pid,
            "title": title,
            "display_seq": seq,
            "last_used": bool(last) and pid == last,
        })
    return out


def _workspace_display_seq(ws: Any):
    seq_attr = getattr(ws, "display_seq", None)
    if callable(seq_attr):
        try:
            seq = seq_attr()
        except TypeError:
            seq = seq_attr
    elif seq_attr is not None:
        seq = seq_attr
    else:
        seq = getattr(ws, "seq", "")
    if isinstance(seq, bool) or seq is None:
        return "" if seq is None else seq
    if isinstance(seq, int):
        return seq
    return seq


def _format_seq(display_seq) -> str:
    try:
        return f"{int(display_seq):03d}"
    except (TypeError, ValueError):
        text = str(display_seq or "").strip().lstrip("#")
        return text or "000"


def _seq_ints(projects: list[dict]) -> Optional[list[int]]:
    vals: list[int] = []
    for project in projects:
        try:
            vals.append(int(project.get("display_seq")))
        except (TypeError, ValueError):
            return None
    return vals


def _display_order(projects: list[dict]) -> list[dict]:
    """Keep caller order unless the list is clearly oldest-first (strictly rising seq)."""
    if len(projects) < 2:
        return list(projects)
    seqs = _seq_ints(projects)
    if seqs is None:
        return list(projects)
    if all(seqs[i] < seqs[i + 1] for i in range(len(seqs) - 1)):
        return list(reversed(projects))
    return list(projects)


class ProjectPickerDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        *,
        projects: list[dict],
        on_create,          # (title: str) -> None
        on_select,          # (project_id: str) -> None
        on_open_folder,     # () -> None
        on_settings=None,   # () -> None
        on_dismiss=None,    # () -> None
    ) -> None:
        super().__init__(master)
        self._on_create: Callable[[str], None] = on_create
        self._on_select: Callable[[str], None] = on_select
        self._on_open_folder: Callable[[], None] = on_open_folder
        self._on_settings = on_settings
        self._on_dismiss = on_dismiss
        self._acted = False
        self._closed = False
        self._wrap_labels: list[ctk.CTkLabel] = []

        self.title("Choose a project")
        self.configure(fg_color=_BG)
        self.minsize(420, 380)
        self.geometry("520x560")
        self.resizable(True, True)
        if master is not None:
            try:
                self.transient(master)
            except Exception:
                pass

        self.protocol("WM_DELETE_WINDOW", self._handle_dismiss)
        self.bind("<Escape>", lambda _e: self._handle_dismiss())
        self.bind("<Configure>", self._on_window_configure)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_create_card()
        self._build_project_list(list(projects or []))
        self._build_footer()

        self.after_idle(self._present)

    def _present(self) -> None:
        if self._closed:
            return
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass
        try:
            self._title_entry.focus()
        except Exception:
            pass

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Choose a project",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(
            header,
            text="Create a new video or reopen one you already started.",
            font=ctk.CTkFont(size=12),
            text_color=_MUTED,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 14))

        if self._on_settings is not None:
            ctk.CTkButton(
                header,
                text="⚙",
                width=36,
                height=32,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=_TEXT,
                hover_color=_CARD_HOVER,
                font=ctk.CTkFont(size=16),
                command=self._handle_settings,
            ).grid(row=0, column=1, rowspan=2, padx=(0, 16), pady=12, sticky="e")

        ctk.CTkFrame(self, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=1, column=0, sticky="ew",
        )

    def _build_create_card(self) -> None:
        card = ctk.CTkFrame(
            self, fg_color=_CARD, corner_radius=8, border_width=1, border_color=_BORDER,
        )
        card.grid(row=2, column=0, sticky="ew", padx=16, pady=(16, 8))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="CREATE NEW PROJECT",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_MUTED,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))

        self._title_entry = ctk.CTkEntry(
            card,
            height=36,
            placeholder_text=_TITLE_PLACEHOLDER,
            fg_color=_BG,
            border_color=_BORDER,
            text_color=_TEXT,
            placeholder_text_color=_MUTED,
        )
        self._title_entry.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(0, 8))
        self._title_entry.bind("<Return>", lambda _e: self._handle_create())

        ctk.CTkButton(
            card,
            text="Create",
            width=96,
            height=36,
            fg_color=_ACCENT,
            hover_color=_ACCENT_HOV,
            text_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._handle_create,
        ).grid(row=1, column=1, padx=(0, 14), pady=(0, 8))

        # Compact Brand / Style defaults (optional — Legacy keeps old projects identical).
        opts = ctk.CTkFrame(card, fg_color="transparent")
        opts.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))
        opts.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(opts, text="Brand", text_color=_MUTED, font=ctk.CTkFont(size=11)).grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self._create_brand_var = ctk.StringVar(value="None")
        try:
            from style_engine import brand_choices

            brand_labels = ["None"] + [name for _sid, name in brand_choices()]
            self._create_brand_ids = {"None": None}
            self._create_brand_ids.update({name: sid for sid, name in brand_choices()})
        except Exception:
            brand_labels = ["None"]
            self._create_brand_ids = {"None": None}
        ctk.CTkOptionMenu(
            opts, variable=self._create_brand_var, values=brand_labels, width=120,
            fg_color=_BG, button_color=_BORDER, button_hover_color=_ACCENT,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(opts, text="Style", text_color=_MUTED, font=ctk.CTkFont(size=11)).grid(
            row=0, column=2, sticky="w", padx=(0, 6)
        )
        self._create_style_var = ctk.StringVar(value="Legacy")
        try:
            from style_engine import style_choices

            style_labels = ["Legacy", "Auto"] + [name for _sid, name in style_choices()]
            self._create_style_ids = {"Legacy": ("", None), "Auto": ("auto", None)}
            self._create_style_ids.update(
                {name: ("manual", sid) for sid, name in style_choices()}
            )
        except Exception:
            style_labels = ["Legacy", "Auto"]
            self._create_style_ids = {"Legacy": ("", None), "Auto": ("auto", None)}
        ctk.CTkOptionMenu(
            opts, variable=self._create_style_var, values=style_labels, width=160,
            fg_color=_BG, button_color=_BORDER, button_hover_color=_ACCENT,
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=3, sticky="ew")

    def _build_project_list(self, projects: list[dict]) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.grid(row=3, column=0, sticky="nsew", padx=16, pady=(4, 8))
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            wrap,
            text="EXISTING PROJECTS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self._list = ctk.CTkScrollableFrame(
            wrap,
            fg_color=_PANEL,
            corner_radius=8,
            border_width=1,
            border_color=_BORDER,
            scrollbar_button_color=_BORDER,
            scrollbar_button_hover_color=_ACCENT,
        )
        self._list.grid(row=1, column=0, sticky="nsew")
        self._list.grid_columnconfigure(0, weight=1)
        self._list.bind("<Configure>", self._on_list_configure)

        ordered = _display_order(projects)
        if not ordered:
            empty = ctk.CTkLabel(
                self._list,
                text=_EMPTY_HINT,
                font=ctk.CTkFont(size=13),
                text_color=_MUTED,
                anchor="w",
                justify="left",
                wraplength=360,
            )
            empty.grid(row=0, column=0, sticky="ew", padx=12, pady=16)
            self._wrap_labels.append(empty)
            return

        for i, project in enumerate(ordered):
            self._add_project_row(i, project)

    def _add_project_row(self, index: int, project: dict) -> None:
        pid = str(project.get("id") or "")
        title = str(project.get("title") or "").strip() or "Untitled"
        seq = _format_seq(project.get("display_seq"))
        last_used = bool(project.get("last_used"))

        row = ctk.CTkFrame(
            self._list,
            fg_color=_CARD,
            corner_radius=6,
            border_width=1,
            border_color=_BORDER,
        )
        row.grid(row=index, column=0, sticky="ew", padx=8, pady=4)
        row.grid_columnconfigure(0, weight=1)
        row.configure(cursor="hand2")

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        text_col.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            text_col,
            text=f"#{seq}  {title}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_TEXT,
            anchor="w",
            justify="left",
            wraplength=360,
        )
        title_label.grid(row=0, column=0, sticky="ew")
        self._wrap_labels.append(title_label)

        hint = None
        if last_used:
            hint = ctk.CTkLabel(
                text_col,
                text="Last used",
                font=ctk.CTkFont(size=11),
                text_color=_MUTED,
                anchor="w",
            )
            hint.grid(row=1, column=0, sticky="w", pady=(2, 0))

        widgets = [row, text_col, title_label]
        if hint is not None:
            widgets.append(hint)
        for widget in widgets:
            widget.bind("<Button-1>", lambda _e, i=pid: self._handle_select(i))
            widget.bind("<Enter>", lambda _e, r=row: r.configure(fg_color=_CARD_HOVER))
            widget.bind("<Leave>", lambda _e, r=row: r.configure(fg_color=_CARD))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=0)
        footer.grid(row=4, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkFrame(footer, fg_color=_BORDER, height=1, corner_radius=0).grid(
            row=0, column=0, sticky="ew",
        )
        ctk.CTkButton(
            footer,
            text="Open folder…",
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=_BORDER,
            text_color=_TEXT,
            hover_color=_CARD_HOVER,
            font=ctk.CTkFont(size=12),
            command=self._handle_open_folder,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=12)

    def _on_window_configure(self, event) -> None:
        if event.widget is not self:
            return
        self._sync_wraplengths(max(200, int(event.width) - 72))

    def _on_list_configure(self, event) -> None:
        self._sync_wraplengths(max(160, int(event.width) - 40))

    def _sync_wraplengths(self, width: int) -> None:
        wrap = max(80, width)
        for label in self._wrap_labels:
            try:
                label.configure(wraplength=wrap)
            except Exception:
                pass

    def _handle_create(self) -> None:
        if self._acted:
            return
        title = (self._title_entry.get() or "").strip()
        self._acted = True
        brand_id = getattr(self, "_create_brand_ids", {}).get(self._create_brand_var.get())
        mode, style_id = getattr(self, "_create_style_ids", {}).get(
            self._create_style_var.get(), ("", None)
        )
        try:
            self._on_create(
                title,
                brand_kit_id=brand_id,
                style_mode=mode,
                style_id=style_id,
            )
        except TypeError:
            # Older callback signature — title only
            try:
                self._on_create(title)
            except Exception:
                self._acted = False
                raise
        except Exception:
            self._acted = False
            raise
        self._safe_destroy()

    def _handle_select(self, project_id: str) -> None:
        if self._acted:
            return
        self._acted = True
        try:
            self._on_select(str(project_id))
        except Exception:
            self._acted = False
            raise
        self._safe_destroy()

    def _handle_open_folder(self) -> None:
        if self._acted:
            return
        self._acted = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self._on_open_folder()
        finally:
            self._safe_destroy()

    def _handle_settings(self) -> None:
        if self._on_settings is None:
            return
        self._on_settings()

    def _handle_dismiss(self) -> None:
        if self._closed:
            return
        try:
            if self._on_dismiss is not None:
                self._on_dismiss()
        finally:
            self._safe_destroy()

    def _safe_destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
