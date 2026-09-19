"""Context-sensitive Inspector panel — Semantic YT Studio 2.0 CapCut-style
editor, right panel.

Bound to whatever clip is selected on TimelineCanvas. Every control writes
directly into the SAME TimelineEvent the canvas/preview already use (via
editorial_timeline_edit.set_event_property / replace_event_source /
reorder_visual_event), pushed through the SAME UndoStack, so Inspector edits
are real edits — they persist (editorial_timeline_edit.save_timeline) and
affect export (editorial_timeline_edit.reconcile_timeline_into_decisions)
exactly like a canvas drag does.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from . import theme as T
from .undo_stack import Command, UndoStack

try:
    import editorial_timeline_edit as tl_edit
except Exception:  # pragma: no cover
    tl_edit = None

AUDIO_TRACKS = ("VOICEOVER", "MUSIC", "AMBIENCE", "SFX")
VISUAL_TRACKS = ("VIDEO_1", "VIDEO_2", "IMAGE")
TEXT_LIKE_TRACKS = ("TEXT", "GRAPHICS")

# The real, genuinely-rendered transition vocabulary (video_generator.
# TRANSITION_TYPES / build_xfade_filter_complex) — NOT the old per-clip
# fade-to-color scheme's tokens (fade/dissolve/flash/soft), which stays as
# the automatic first-cut's DEFAULT but is never operator-facing here,
# since "Cut" is honest about being a hard cut and the others are real
# cross-clip blends, unlike the old set which all silently meant "fade to
# black at my own edges, no actual blending with my neighbor."
_REAL_TRANSITION_TYPES = ["cut", "crossfade", "dip_black", "dip_white", "wipe", "slide"]
_CAMERA_STYLES = ["static", "push_in", "pull_out", "subtle_drift"]


class InspectorPanel(ctk.CTkScrollableFrame):
    def __init__(
        self,
        master,
        *,
        undo_stack: Optional[UndoStack] = None,
        on_change: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.PANEL, label_text="Inspector")
        self._timeline = None
        self._event_id: Optional[str] = None
        self._undo = undo_stack
        self._on_change = on_change
        self.grid_columnconfigure(0, weight=1)
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.grid(row=0, column=0, sticky="nsew")
        self._body.grid_columnconfigure(0, weight=1)
        self._render_empty()

    def set_timeline(self, timeline) -> None:
        self._timeline = timeline
        self.show_event(None)

    def show_event(self, event_id: Optional[str]) -> None:
        self._event_id = event_id
        for w in self._body.winfo_children():
            w.destroy()
        if not event_id or self._timeline is None or tl_edit is None:
            self._render_empty()
            return
        ev = tl_edit.find_event(self._timeline, event_id)
        if ev is None:
            self._render_empty()
            return
        self._render_header(ev)
        self._render_timing(ev)
        if ev.track in VISUAL_TRACKS:
            self._render_visual_fields(ev)
        elif ev.track in AUDIO_TRACKS:
            self._render_audio_fields(ev)
        elif ev.track in TEXT_LIKE_TRACKS:
            self._render_text_fields(ev)

    # ---- section builders ----

    def _render_empty(self) -> None:
        ctk.CTkLabel(
            self._body, text="Select a clip on the timeline to edit its properties.",
            text_color=T.MUTED, font=ctk.CTkFont(size=12), wraplength=220, justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=16)

    def _section(self, title: str, row: int) -> ctk.CTkFrame:
        ctk.CTkLabel(
            self._body, text=title.upper(), font=ctk.CTkFont(size=10, weight="bold"),
            text_color=T.MUTED, anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=10, pady=(12, 2))
        frame = ctk.CTkFrame(self._body, fg_color="transparent")
        frame.grid(row=row + 1, column=0, sticky="ew", padx=10)
        frame.grid_columnconfigure(1, weight=1)
        return frame

    def _render_header(self, ev) -> None:
        f = self._section("Clip", 0)
        ctk.CTkLabel(f, text=ev.track, font=ctk.CTkFont(size=14, weight="bold"), text_color=T.TEXT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        if ev.scene_number:
            ctk.CTkLabel(f, text=f"Scene {ev.scene_number}", font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w").grid(
                row=1, column=0, columnspan=2, sticky="w"
            )
        name = Path(ev.source).name if ev.source else "(no media)"
        ctk.CTkLabel(f, text=name, font=ctk.CTkFont(size=11), text_color=T.MUTED, anchor="w", wraplength=220).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        if ev.track in VISUAL_TRACKS and tl_edit is not None:
            issues = [i for i in tl_edit.qc_issues(self._timeline) if str(i.get("scene_number")) == str(ev.scene_number)]
            if issues:
                ctk.CTkLabel(
                    f, text=f"⚠ {issues[0]['message']}", font=ctk.CTkFont(size=10),
                    text_color=T.DANGER, anchor="w", wraplength=220,
                ).grid(row=3, column=0, columnspan=2, sticky="w")

    def _render_timing(self, ev) -> None:
        f = self._section("Timing", 2)
        ctk.CTkLabel(f, text="Start", font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(row=0, column=0, sticky="w", pady=2)
        ctk.CTkLabel(f, text=f"{ev.start:.2f}s", font=ctk.CTkFont(size=11), text_color=T.TEXT).grid(row=0, column=1, sticky="e", pady=2)
        ctk.CTkLabel(f, text="End", font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(row=1, column=0, sticky="w", pady=2)
        ctk.CTkLabel(f, text=f"{ev.end:.2f}s", font=ctk.CTkFont(size=11), text_color=T.TEXT).grid(row=1, column=1, sticky="e", pady=2)
        ctk.CTkLabel(f, text="Duration", font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(row=2, column=0, sticky="w", pady=2)
        ctk.CTkLabel(f, text=f"{ev.duration:.2f}s", font=ctk.CTkFont(size=11), text_color=T.TEXT).grid(row=2, column=1, sticky="e", pady=2)
        if ev.track == "VIDEO_2":
            hint = "Independent B-roll overlay — drag it anywhere (it will not shift Video/Image), or drag an edge to trim it."
        elif ev.track in VISUAL_TRACKS:
            hint = "Drag the middle of this clip on the timeline to reorder it, or an edge to trim its duration."
        else:
            hint = "Drag this clip on the timeline to move it."
        ctk.CTkLabel(f, text=hint, font=ctk.CTkFont(size=10), text_color=T.MUTED, wraplength=220, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 6)
        )

    def _render_visual_fields(self, ev) -> None:
        f = self._section("Transform", 4)
        self._slider_row(f, 0, "Scale", ev.scale, 0.5, 3.0, lambda v: self._apply(scale=round(v, 3)))
        self._slider_row(f, 2, "Position X", ev.position_x, 0.0, 1.0, lambda v: self._apply(position_x=round(v, 3)))
        self._slider_row(f, 4, "Position Y", ev.position_y, 0.0, 1.0, lambda v: self._apply(position_y=round(v, 3)))

        f2 = self._section("Motion & Speed", 6)
        speed = float((ev.metadata or {}).get("speed") or 1.0)
        speed_lo = tl_edit.MIN_SPEED if tl_edit is not None else 0.25
        speed_hi = tl_edit.MAX_SPEED if tl_edit is not None else 2.0
        self._slider_row(f2, 0, "Speed", speed, speed_lo, speed_hi, lambda v: self._apply(speed=round(v, 2)))
        ctk.CTkLabel(f2, text="Camera", font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(row=2, column=0, sticky="w", pady=(6, 2))
        cam = ctk.CTkOptionMenu(
            f2, values=_CAMERA_STYLES, width=140,
            command=lambda v: self._apply(animation=v),
        )
        cam.set(ev.animation if ev.animation in _CAMERA_STYLES else "static")
        cam.grid(row=2, column=1, sticky="e", pady=(6, 2))

        f3 = self._section("Transition In", 8)
        real_types = list(_REAL_TRANSITION_TYPES)
        trans = ctk.CTkOptionMenu(
            f3, values=real_types, width=140,
            command=lambda v: self._on_transition_type(v),
        )
        current_type = ev.transition_in if ev.transition_in in real_types else "cut"
        trans.set(current_type)
        trans.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        self._transition_dur_row = f3
        current_dur = float((ev.metadata or {}).get("transition_duration") or 0.0)
        if current_dur <= 0.0:
            current_dur = 0.5
        if current_type != "cut":
            self._slider_row(
                f3, 2, "Duration (s)", current_dur, 0.15, 1.0,
                lambda v: self._apply(transition_duration=round(v, 2)),
            )
            if current_type in ("wipe", "slide"):
                # Only these two base types expose a direction — real,
                # actually-rendered ffmpeg xfade variants (wipeleft/right/
                # up/down, slideleft/right/up/down — see video_generator.
                # TRANSITION_DIRECTIONS), never a cosmetic-only choice.
                ctk.CTkLabel(f3, text="Direction", font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(
                    row=4, column=0, sticky="w", pady=(6, 2)
                )
                current_dir = str((ev.metadata or {}).get("transition_direction") or "left")
                dir_menu = ctk.CTkOptionMenu(
                    f3, values=["left", "right", "up", "down"], width=100,
                    command=lambda v: self._apply(transition_direction=v),
                )
                dir_menu.set(current_dir if current_dir in ("left", "right", "up", "down") else "left")
                dir_menu.grid(row=4, column=1, sticky="e", pady=(6, 2))
        else:
            ctk.CTkLabel(
                f3, text="A real crossfade/dip/wipe/slide between this clip and the "
                "next — pick a type to set its duration. \"Cut\" is a hard cut (default).",
                font=ctk.CTkFont(size=10), text_color=T.MUTED, wraplength=220, justify="left",
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))

        f4 = self._section("Media", 10)
        ctk.CTkButton(f4, text="Replace media…", height=28, command=self._replace_media).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4)
        )
        if ev.track == "VIDEO_2":
            # An independent overlay has no fixed "position in a sequence"
            # to swap content with (see editorial_timeline_edit's
            # PRIMARY_VISUAL_TRACKS-only reorder_visual_event) — drag it on
            # the timeline instead. Showing an earlier/later button here
            # that silently did nothing would be exactly the kind of fake
            # control the editor must never have.
            ctk.CTkLabel(
                f4, text="Drag this clip on the timeline to reposition it.",
                font=ctk.CTkFont(size=10), text_color=T.MUTED, wraplength=220, justify="left",
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        else:
            row = ctk.CTkFrame(f4, fg_color="transparent")
            row.grid(row=1, column=0, columnspan=2, sticky="ew")
            ctk.CTkButton(row, text="◀ Move earlier", height=26, width=100, command=lambda: self._reorder("earlier")).pack(side="left")
            ctk.CTkButton(row, text="Move later ▶", height=26, width=100, command=lambda: self._reorder("later")).pack(side="right")

    def _render_audio_fields(self, ev) -> None:
        f = self._section("Audio", 4)
        meta = ev.metadata or {}
        volume = float(meta.get("volume", 1.0))
        self._slider_row(f, 0, "Volume", volume, 0.0, 1.5, lambda v: self._apply(volume=round(v, 3)))
        muted_var = ctk.BooleanVar(value=bool(meta.get("muted", False)))
        ctk.CTkCheckBox(
            f, text="Muted", variable=muted_var, font=ctk.CTkFont(size=12),
            command=lambda: self._apply(muted=muted_var.get()),
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        self._slider_row(f, 3, "Fade in", float(meta.get("fade_in", 0.0)), 0.0, 3.0, lambda v: self._apply(fade_in=round(v, 2)))
        self._slider_row(f, 5, "Fade out", float(meta.get("fade_out", 0.0)), 0.0, 3.0, lambda v: self._apply(fade_out=round(v, 2)))

        f2 = self._section("Media", 7)
        ctk.CTkButton(f2, text="Replace audio…", height=28, command=self._replace_media).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4)
        )

    def _render_text_fields(self, ev) -> None:
        f = self._section("Content", 4)
        meta = ev.metadata or {}
        text_val = str(meta.get("text") or ev.source or "")
        box = ctk.CTkTextbox(f, height=60, font=ctk.CTkFont(size=12))
        box.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        box.insert("1.0", text_val)

        def commit_text(_e=None):
            self._apply(text=box.get("1.0", "end").strip())

        box.bind("<FocusOut>", commit_text)

        f2 = self._section("Appearance", 6)
        self._slider_row(f2, 0, "Opacity", float(ev.opacity), 0.0, 1.0, lambda v: self._apply(opacity=round(v, 3)))
        self._slider_row(f2, 2, "Scale", float(ev.scale), 0.5, 2.0, lambda v: self._apply(scale=round(v, 3)))
        self._slider_row(f2, 4, "Position X", float(ev.position_x), 0.0, 1.0, lambda v: self._apply(position_x=round(v, 3)))
        self._slider_row(f2, 6, "Position Y", float(ev.position_y), 0.0, 1.0, lambda v: self._apply(position_y=round(v, 3)))

    def _slider_row(self, parent, row, label, value, lo, hi, on_commit) -> None:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11), text_color=T.MUTED).grid(
            row=row, column=0, sticky="w", pady=(6, 0)
        )
        val_label = ctk.CTkLabel(parent, text=f"{value:.2f}", font=ctk.CTkFont(size=11), text_color=T.TEXT, width=40)
        val_label.grid(row=row, column=1, sticky="e", pady=(6, 0))
        slider = ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=200)
        slider.set(value)
        slider.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, 2))

        def _preview(v):
            val_label.configure(text=f"{float(v):.2f}")

        def _commit(v):
            on_commit(float(v))

        slider.configure(command=_preview)
        slider.bind("<ButtonRelease-1>", lambda _e: _commit(slider.get()))

    # ---- mutation helpers ----

    _DIRECT_FIELDS = frozenset({
        "opacity", "scale", "position_x", "position_y", "rotation", "crop",
        "z_index", "animation", "transition_in", "transition_out", "source",
    })

    def _apply(self, **fields) -> None:
        if self._timeline is None or self._event_id is None or tl_edit is None:
            return
        ev = tl_edit.find_event(self._timeline, self._event_id)
        if ev is None:
            return
        meta = ev.metadata or {}
        before = {
            k: getattr(ev, k, None) if k in self._DIRECT_FIELDS else meta.get(k)
            for k in fields
        }
        event_id = self._event_id

        def do():
            tl_edit.set_event_property(self._timeline, event_id, **fields)
            self._changed()

        def undo():
            tl_edit.set_event_property(self._timeline, event_id, **before)
            self._changed()

        if self._undo is not None:
            self._undo.push(Command(f"Edit {', '.join(fields)}", do=do, undo=undo))
        else:
            do()

    def _changed(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                pass

    def _on_transition_type(self, transition_type: str) -> None:
        """Picking "Cut" clears the duration (0 == the render pipeline's
        existing signal for "no real transition here" — see
        video_generator.render_video's real_transition_into_scene build).
        Picking any real type sets a sensible default (0.5s) if none was
        set yet. Re-shows the Inspector for this clip afterward so the
        duration slider appears/disappears to match."""
        event_id = self._event_id
        if transition_type == "cut":
            self._apply(transition_in="cut", transition_duration=0.0)
        else:
            ev = tl_edit.find_event(self._timeline, event_id) if (self._timeline and tl_edit) else None
            existing = float((ev.metadata or {}).get("transition_duration") or 0.0) if ev else 0.0
            self._apply(transition_in=transition_type, transition_duration=existing or 0.5)
        self.show_event(event_id)

    def _reorder(self, direction: str) -> None:
        if self._timeline is None or self._event_id is None or tl_edit is None:
            return
        event_id = self._event_id

        def do():
            tl_edit.reorder_visual_event(self._timeline, event_id, direction=direction)
            self._changed()

        def undo():
            other = "later" if direction == "earlier" else "earlier"
            tl_edit.reorder_visual_event(self._timeline, event_id, direction=other)
            self._changed()

        if self._undo is not None:
            self._undo.push(Command("Reorder clip", do=do, undo=undo))
        else:
            do()

    def _replace_media(self) -> None:
        if self._timeline is None or self._event_id is None or tl_edit is None:
            return
        ev = tl_edit.find_event(self._timeline, self._event_id)
        if ev is None:
            return
        is_visual = ev.track in VISUAL_TRACKS
        filetypes = (
            [("Media", "*.png *.jpg *.jpeg *.webp *.mp4 *.mov"), ("All files", "*.*")]
            if is_visual
            else [("Audio", "*.wav *.mp3 *.m4a *.aac"), ("All files", "*.*")]
        )
        path = filedialog.askopenfilename(title="Replace media", filetypes=filetypes)
        if not path:
            return
        old_source = ev.source
        event_id = self._event_id

        def do():
            tl_edit.replace_event_source(self._timeline, event_id, new_source=path)
            self._changed()
            self.show_event(event_id)

        def undo():
            tl_edit.replace_event_source(self._timeline, event_id, new_source=old_source)
            self._changed()
            self.show_event(event_id)

        if self._undo is not None:
            self._undo.push(Command("Replace media", do=do, undo=undo))
        else:
            do()
