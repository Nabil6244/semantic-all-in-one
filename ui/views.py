"""View frames for the production workstation (read existing controller state only)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Optional

import customtkinter as ctk

from . import theme as T
from .widgets import Card, EmptyState, MetricRow, SectionHeader, StatusPill


class _BaseView(ctk.CTkFrame):
    key = "base"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, fg_color=T.PANEL_ALT, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._body = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=T.BORDER, scrollbar_button_hover_color=T.ACCENT,
        )
        self._body.grid(row=1, column=0, sticky="nsew", padx=T.PAD, pady=(0, T.PAD))
        self._body.grid_columnconfigure(0, weight=1)
        self.content = self._body  # alias for legacy builders

    def on_show(self) -> None:
        """Refresh read-only displays. Never trigger production work."""
        pass


class ProjectView(_BaseView):
    key = "project"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(
            self, "Project", "Production health at a glance",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8))
        self._empty = EmptyState(
            self._body,
            "No project open",
            "Choose a project to start planning, acquiring assets, and rendering.",
            "Choose project",
            command=app._open_project_picker,
        )
        self._empty.grid(row=0, column=0, sticky="ew", pady=8)
        self._panel = Card(self._body)
        self._panel.grid(row=1, column=0, sticky="ew", pady=8)
        self._panel.grid_columnconfigure(0, weight=1)
        self._metrics: list[MetricRow] = []
        for i, label in enumerate(
            (
                "Project",
                "Narration",
                "Scenes",
                "Visual assets",
                "Ambience",
                "SFX",
                "Music",
                "Editorial score",
                "Render",
            )
        ):
            row = MetricRow(self._panel, label)
            row.grid(row=i, column=0, sticky="ew", padx=T.PAD, pady=4)
            self._metrics.append(row)

    def on_show(self) -> None:
        ws = self.app._workspace
        if ws is None:
            self._empty.grid()
            self._panel.grid_remove()
            return
        self._empty.grid_remove()
        self._panel.grid()
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


class ScriptView(ctk.CTkFrame):
    """Hosts legacy script/CSV/voice builders. One scroll only — no nested scrollables."""

    key = "script"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, fg_color=T.PANEL_ALT, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        SectionHeader(
            self, "Script", "CSV import or Analyze Script",
        ).grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD_SM, 2))
        self._workflow = ctk.CTkFrame(self, fg_color="transparent")
        self._workflow.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=(0, 2))
        self._step_labels = []
        for i, name in enumerate(T.WORKFLOW_STEPS):
            if i:
                ctk.CTkLabel(self._workflow, text="·", text_color=T.BORDER, font=ctk.CTkFont(size=11)).pack(
                    side="left", padx=2
                )
            lbl = ctk.CTkLabel(
                self._workflow, text=name, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=T.MUTED,
            )
            lbl.pack(side="left")
            self._step_labels.append(lbl)
        # Plain host — _build_left_sections adds its own CTkScrollableFrame
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew", padx=0, pady=(0, T.PAD_SM))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def on_show(self) -> None:
        idx = int(getattr(self.app, "_stepper_index", 0) or 0)
        map_idx = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5}.get(idx, 0)
        for i, lbl in enumerate(self._step_labels):
            if i == map_idx:
                lbl.configure(text_color=T.ACCENT)
            elif i < map_idx:
                lbl.configure(text_color=T.STEPPER_DONE)
            else:
                lbl.configure(text_color=T.MUTED)


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
            progress_color=T.ACCENT,
            button_color=T.TEXT,
            button_hover_color=T.MUTED,
            font=ctk.CTkFont(size=12),
            text_color=T.TEXT,
        )
        self._brand_switch.grid(row=0, column=1, sticky="w", padx=T.PAD, pady=(10, 4))

        self._brand_kit_label = ctk.CTkLabel(
            form, text="Kit", text_color=T.MUTED, font=ctk.CTkFont(size=12),
        )
        self._brand_var = ctk.StringVar(value="Default")
        self._brand_menu = ctk.CTkOptionMenu(
            form, variable=self._brand_var, values=["Default"],
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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
            fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
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


class AssetsView(_BaseView):
    key = "assets"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Assets", "Acquire and recover scene media").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No scenes yet",
            "Import a CSV or Analyze Script to create a visual plan, then generate assets.",
            "Go to Script",
            command=lambda: app._shell.navigate("script") if getattr(app, "_shell", None) else None,
        )
        self._empty.grid(row=0, column=0, sticky="ew")
        self._card = Card(self._body)
        self._card.grid(row=1, column=0, sticky="ew", pady=8)
        self._card.grid_columnconfigure(0, weight=1)
        self._ready = MetricRow(self._card, "Ready")
        self._ready.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=4)
        self._needs = MetricRow(self._card, "Needs action")
        self._needs.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=4)
        self._proc = MetricRow(self._card, "Processing")
        self._proc.grid(row=2, column=0, sticky="ew", padx=T.PAD, pady=4)
        ctk.CTkButton(
            self._card, text="Generate Assets", height=32,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=app._on_generate,
        ).grid(row=3, column=0, sticky="w", padx=T.PAD, pady=(8, T.PAD))
        ctk.CTkButton(
            self._card, text="Open Issues", height=28,
            fg_color="transparent", border_width=1, border_color=T.BORDER,
            text_color=T.TEXT, hover_color=T.CARD_HOVER, font=ctk.CTkFont(size=12),
            command=app._toggle_issues,
        ).grid(row=4, column=0, sticky="w", padx=T.PAD, pady=(0, T.PAD))

    def on_show(self) -> None:
        rows = getattr(self.app, "_scene_rows", None) or []
        if not rows:
            self._empty.grid()
            self._card.grid_remove()
            return
        self._empty.grid_remove()
        self._card.grid()
        try:
            snap = self.app._qa_snapshot()
            self._ready.set_value(str(snap.ready))
            self._needs.set_value(str(snap.needs_action))
            self._proc.set_value("yes" if snap.processing else "no")
        except Exception:
            self._ready.set_value("—")


class AudioView(_BaseView):
    key = "audio"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Audio", "Narration + Smart Editing (SFX, transitions, ambience)").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._host = ctk.CTkFrame(self._body, fg_color="transparent")
        self._host.grid(row=0, column=0, sticky="ew")
        self._host.grid_columnconfigure(0, weight=1)
        self.content = self._host  # voice panel may be reparented here

        self._info = Card(self._body)
        self._info.grid(row=1, column=0, sticky="ew", pady=8)
        self._info.grid_columnconfigure(0, weight=1)
        self._narr = MetricRow(self._info, "Narration")
        self._narr.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=4)
        self._amb = MetricRow(self._info, "Ambience beds")
        self._amb.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=4)
        self._sfx = MetricRow(self._info, "SFX events")
        self._sfx.grid(row=2, column=0, sticky="ew", padx=T.PAD, pady=4)

        # Smart Editing lives on the Audio dashboard (not buried in Settings)
        smart = Card(self._body)
        smart.grid(row=2, column=0, sticky="ew", pady=4)
        smart.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            smart, text="SMART EDITING", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=T.PAD, pady=(T.PAD, 6))

        def _feature_row(row_i: int, label: str, enabled_var, intensity_var) -> None:
            ctk.CTkSwitch(
                smart, text=label, variable=enabled_var,
                onvalue=True, offvalue=False, progress_color=T.ACCENT, button_color=T.TEXT,
                text_color=T.TEXT, font=ctk.CTkFont(size=12),
                command=app._persist_smart_editing_settings,
            ).grid(row=row_i, column=0, sticky="w", padx=T.PAD, pady=2)
            ctk.CTkOptionMenu(
                smart, variable=intensity_var, values=["Low", "Medium", "High"],
                width=96, fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
                text_color=T.TEXT, dropdown_fg_color=T.CARD, dropdown_text_color=T.TEXT,
                command=lambda _v: app._persist_smart_editing_settings(),
            ).grid(row=row_i, column=1, sticky="e", padx=T.PAD, pady=2)

        _feature_row(1, "Text Effects", app.smart_text_effects_var, app.smart_text_intensity_var)
        _feature_row(2, "Sound Effects", app.smart_sfx_var, app.smart_sfx_intensity_var)
        _feature_row(3, "Visual Transitions", app.smart_visual_transitions_var, app.smart_transitions_intensity_var)
        _feature_row(4, "Scene Ambience", app.smart_scene_ambience_var, app.smart_ambience_intensity_var)

        ctk.CTkLabel(
            smart,
            text="Each feature has its own intensity. SFX, transitions, and ambience "
                 "are AI-picked when Gemini is configured.",
            font=ctk.CTkFont(size=11), text_color=T.MUTED, justify="left", anchor="w",
            wraplength=520,
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(6, 4))

        mode_row = ctk.CTkFrame(smart, fg_color="transparent")
        mode_row.grid(row=6, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=(2, T.PAD))
        ctk.CTkLabel(mode_row, text="Mode", font=ctk.CTkFont(size=12), text_color=T.TEXT).pack(
            side="left"
        )
        ctk.CTkOptionMenu(
            mode_row, variable=app.smart_mode_var, values=["Smart", "Automatic"],
            width=110, fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
            text_color=T.TEXT, dropdown_fg_color=T.CARD, dropdown_text_color=T.TEXT,
            command=lambda _v: app._persist_smart_editing_settings(),
        ).pack(side="left", padx=(8, 0))

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


class MusicView(_BaseView):
    key = "music"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Music", "Manual background track · optional editorial ducking").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No music selected",
            "Choose an optional background track. When present, Editorial Music Director ducks under narration.",
            "Browse music",
            command=app._browse_bg,
        )
        self._empty.grid(row=0, column=0, sticky="ew")
        self._card = Card(self._body)
        self._card.grid(row=1, column=0, sticky="ew")
        self._card.grid_columnconfigure(0, weight=1)
        self._track = MetricRow(self._card, "Track")
        self._track.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=4)
        self._sections = MetricRow(self._card, "Sections")
        self._sections.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=4)
        self._duck = MetricRow(self._card, "Ducking")
        self._duck.grid(row=2, column=0, sticky="ew", padx=T.PAD, pady=4)
        ctk.CTkButton(
            self._card, text="Change track", height=28,
            fg_color="transparent", border_width=1, border_color=T.BORDER,
            text_color=T.TEXT, hover_color=T.CARD_HOVER, font=ctk.CTkFont(size=12),
            command=app._browse_bg,
        ).grid(row=3, column=0, sticky="w", padx=T.PAD, pady=(8, T.PAD))

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
        SectionHeader(self, "Editorial", "Film bible from the last aligned plan (read-only)").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No Editorial Plan yet",
            "Render once (or run alignment) to build state/editorial_plan.json. Navigation never rebuilds it.",
            "Go to Render",
            command=lambda: app._shell.navigate("render") if getattr(app, "_shell", None) else None,
        )
        self._empty.grid(row=0, column=0, sticky="ew")
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
        card = Card(parent)
        card.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color=T.MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))
        body = ctk.CTkLabel(
            card, text="—", font=ctk.CTkFont(size=12), text_color=T.TEXT,
            anchor="nw", justify="left", wraplength=280,
        )
        body.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
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
    key = "render"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Render", "Production pipeline progress").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._phases = []
        card = Card(self._body)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        names = ("Preparation", "Assets", "Audio", "Visuals", "Encoding", "QA")
        for i, name in enumerate(names):
            ctk.CTkLabel(
                card, text=name, font=ctk.CTkFont(size=12), text_color=T.MUTED, anchor="w",
            ).grid(row=i, column=0, sticky="w", padx=T.PAD, pady=4)
            pill = StatusPill(card, "IDLE", "muted")
            pill.grid(row=i, column=1, sticky="e", padx=T.PAD, pady=4)
            self._phases.append(pill)
        self._op = MetricRow(card, "Current operation")
        self._op.grid(row=len(names), column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=4)
        self._out = MetricRow(card, "Output")
        self._out.grid(row=len(names) + 1, column=0, columnspan=2, sticky="ew", padx=T.PAD, pady=4)
        ctk.CTkButton(
            card, text="Render Video", height=34,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOV, text_color=T.ACCENT_DARK,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=app._on_generate,
        ).grid(row=len(names) + 2, column=0, sticky="w", padx=T.PAD, pady=(8, T.PAD))

    def on_show(self) -> None:
        running = bool(getattr(self.app, "_running", False))
        stage = (self.app.stage_var.get() or "").upper()
        # Map common stage strings onto phase pills (read-only).
        phase_map = {
            "SCRIPT": 0, "SCENES": 0, "PREP": 0, "PREPARATION": 0,
            "ASSETS": 1, "ASSET": 1,
            "AUDIO": 2, "VOICE": 2, "AMBIENCE": 2,
            "VISUAL": 3, "VISUALS": 3, "MIX": 3,
            "ENCODE": 4, "ENCODING": 4, "RENDER": 4,
            "QA": 5,
        }
        active_i = None
        for token, idx in phase_map.items():
            if token in stage:
                active_i = idx
                break
        for i, pill in enumerate(self._phases):
            if running and active_i is not None:
                if i < active_i:
                    pill.set_tone("DONE", "ok")
                elif i == active_i:
                    pill.set_tone("ACTIVE", "run")
                else:
                    pill.set_tone("IDLE", "muted")
            elif running:
                pill.set_tone("ACTIVE" if i <= 4 else "IDLE", "run" if i <= 4 else "muted")
            elif not running and self.app._last_output:
                pill.set_tone("DONE", "ok")
            else:
                pill.set_tone("IDLE", "muted")
        self._op.set_value(stage or ("Rendering…" if running else "Idle"))
        out = self.app._last_output or self.app.output_var.get() or "—"
        self._out.set_value(Path(out).name if out != "—" else "—")


class QAView(_BaseView):
    key = "qa"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, app, **kwargs)
        SectionHeader(self, "Editorial QA", "Post-render scorecard (never blocks export)").grid(
            row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 8)
        )
        self._empty = EmptyState(
            self._body,
            "No QA report",
            "After a successful render, state/editorial_qa.json is written with score and findings.",
            "Go to Render",
            command=lambda: app._shell.navigate("render") if getattr(app, "_shell", None) else None,
        )
        self._empty.grid(row=0, column=0, sticky="ew")
        self._head = Card(self._body)
        self._head.grid(row=1, column=0, sticky="ew")
        self._score = ctk.CTkLabel(
            self._head, text="—", font=ctk.CTkFont(size=28, weight="bold"), text_color=T.TEXT,
        )
        self._score.pack(anchor="w", padx=T.PAD, pady=(T.PAD, 0))
        self._verdict = StatusPill(self._head, "—", "muted")
        self._verdict.pack(anchor="w", padx=T.PAD, pady=(4, T.PAD))
        self._cats = Card(self._body)
        self._cats.grid(row=2, column=0, sticky="ew", pady=8)
        self._cat_rows: dict[str, MetricRow] = {}
        for i, name in enumerate(("Visual", "Audio", "Pacing", "Music", "Ambience", "Asset Health")):
            row = MetricRow(self._cats, name, "—")
            row.grid(row=i, column=0, sticky="ew", padx=T.PAD, pady=3)
            self._cat_rows[name] = row
        self._issues = ctk.CTkTextbox(
            self._body, height=180, fg_color=T.CARD, border_color=T.BORDER, border_width=1,
            text_color=T.TEXT, font=ctk.CTkFont(size=11),
        )
        self._issues.grid(row=3, column=0, sticky="ew", pady=4)

    def on_show(self) -> None:
        ws = self.app._workspace
        qa = _load_json(ws.state_dir / "editorial_qa.json") if ws else {}
        if not qa:
            self._empty.grid()
            self._head.grid_remove()
            self._cats.grid_remove()
            self._issues.grid_remove()
            return
        self._empty.grid_remove()
        self._head.grid()
        self._cats.grid()
        self._issues.grid()
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
                    f"Scene {i.get('scene_number')}  {i.get('timestamp', 0):.1f}s  "
                    f"[{i.get('severity')}] {i.get('message')}\n",
                )


def _load_json(path: Path) -> dict:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}
