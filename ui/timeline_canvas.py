"""Interactive timeline widget (Semantic YT Studio 2.0 — Phase 2).

A single CTkCanvas draws every track/clip/ruler/playhead — NOT one Tk
widget per clip. This is what keeps 50/100/200/500-scene projects fast:
event count only affects how many `create_rectangle` calls happen on
(re)draw, never how many live Tk widget objects exist.

Editing (drag to move, drag edge to trim, double-click to split, Delete
key) is wired to editorial_timeline_edit.py's pure functions and pushed
through an UndoStack — this widget never mutates render state on its own;
it only calls those already-tested functions and repaints.
"""

from __future__ import annotations

import copy as _copy
import queue
import threading
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from . import icons as I
from . import theme as T
from . import timeline_layout as L
from . import tooltip as TT
from .undo_stack import Command, UndoStack

try:
    import editorial_timeline_edit as tl_edit
except Exception:  # pragma: no cover - exercised indirectly via app tests
    tl_edit = None

try:
    import waveform_cache as _waveform_cache
except Exception:  # pragma: no cover
    _waveform_cache = None

_TRACK_COLOR_KEYS = {
    "VIDEO_1": "clip_video", "VIDEO_2": "clip_video", "IMAGE": "clip_image",
    "VOICEOVER": "clip_voiceover", "MUSIC": "clip_music", "AMBIENCE": "clip_ambience",
    "SFX": "clip_sfx", "TEXT": "clip_text", "GRAPHICS": "clip_graphics",
}
AUDIO_TRACKS = frozenset({"AMBIENCE", "SFX", "MUSIC", "VOICEOVER"})


class TimelineCanvas(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        undo_stack: Optional[UndoStack] = None,
        on_select=None,
        on_dirty: Optional[Callable[[], None]] = None,
        on_notify: Optional[Callable[[str], None]] = None,
        on_playhead_change: Optional[Callable[[float], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color=T.TIMELINE_BG, **kwargs)
        self._timeline = None  # editorial.timeline.EditorialTimeline
        self._zoom = 1.0
        self._scroll_x = 0.0
        self._playhead = 0.0
        self._selected_id: Optional[str] = None
        self._hover_id: Optional[str] = None
        self._on_notify = on_notify
        self._on_playhead_change = on_playhead_change
        self._drag = None  # dict describing an in-progress drag
        self._snap_guide_x: Optional[float] = None
        self._snap_enabled = True
        self._undo = undo_stack
        self._on_select = on_select
        self._on_dirty = on_dirty
        self._save_cb: Optional[Callable[[], None]] = None
        self._locked_tracks: set = set()
        self._muted_tracks: set = set()
        self._solo_tracks: set = set()
        self._header_rows: dict = {}
        self._last_rows: list = []
        # Real audio waveforms (waveform_cache.py) — computed off the UI
        # thread, cached in memory by (event_id, source identity), redrawn
        # once ready. Never fabricated: an event with no resolvable source
        # or a decode failure simply draws no waveform.
        self._waveform_state_dir: Optional[Path] = None
        self._waveform_peaks: dict = {}
        self._waveform_pending: set = set()
        self._waveform_queue: "queue.Queue" = queue.Queue()
        self.after(150, self._poll_waveform_queue)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))

        def _tool_btn(parent, name, tooltip_text, command, *, danger=False, shortcut=None):
            b = ctk.CTkButton(
                parent, text=I.icon(name), width=T.ICON_BTN_W, height=T.CONTROL_H_SM,
                command=command, fg_color="transparent", border_width=1,
                border_color=(T.DANGER if danger else T.BORDER),
                text_color=(T.DANGER if danger else T.TEXT), font=ctk.CTkFont(size=13),
            )
            b.pack(side="left", padx=2)
            TT.attach(b, tooltip_text, shortcut=shortcut)
            return b

        _tool_btn(toolbar, "zoom_out", "Zoom out", self._on_zoom_out)
        self._zoom_label = ctk.CTkLabel(
            toolbar, text="100%", width=44, text_color=T.MUTED, font=ctk.CTkFont(size=T.FONT_METADATA[0]),
        )
        self._zoom_label.pack(side="left", padx=2)
        _tool_btn(toolbar, "zoom_in", "Zoom in", self._on_zoom_in)
        _tool_btn(toolbar, "split", "Split at playhead / clip midpoint", self._on_split_selected, shortcut="Ctrl/Cmd+B")
        _tool_btn(toolbar, "duplicate", "Duplicate selected clip", self._on_duplicate_selected, shortcut="Ctrl/Cmd+D")
        _tool_btn(toolbar, "delete", "Delete selected clip", self._on_delete_selected, danger=True, shortcut="Delete")
        self._snap_btn = ctk.CTkButton(
            toolbar, text="Snap", width=52, height=T.CONTROL_H_SM, command=self._on_toggle_snap,
            fg_color=T.ACCENT_SEL, border_width=1, border_color=T.ACCENT, text_color=T.ACCENT,
            font=ctk.CTkFont(size=11),
        )
        self._snap_btn.pack(side="left", padx=(6, 2))
        TT.attach(self._snap_btn, "Snap to scene boundaries, clip edges and the playhead while dragging")
        self._hint_label = ctk.CTkLabel(
            toolbar,
            text=(
                "Drag Text/Graphics/SFX/Ambience/Music freely. Drag the MIDDLE of a Video/Image "
                "clip to reorder it, or an EDGE to trim it. Voiceover is fixed to the narration."
            ),
            text_color=T.MUTED, font=ctk.CTkFont(size=T.FONT_METADATA[0]),
        )
        self._hint_label.pack(side="left", padx=(12, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Fixed-left track-header column (spec item 6): stays put while the
        # canvas itself scrolls horizontally — real widgets here, but at
        # most one small row per TRACK (≤ 9), never per clip.
        self._header_col = ctk.CTkFrame(body, fg_color=T.PANEL, width=96)
        self._header_col.grid(row=0, column=0, sticky="ns")
        self._header_col.grid_propagate(False)
        self._header_col.grid_columnconfigure(0, weight=1)
        # Spacer matching the ruler height so row 0 of the header column
        # lines up with the first actual track row on the canvas.
        self._header_spacer = ctk.CTkFrame(self._header_col, fg_color="transparent", height=int(L.RULER_HEIGHT))
        self._header_spacer.grid(row=0, column=0, sticky="ew"
        )

        canvas_wrap = ctk.CTkFrame(body, fg_color="transparent")
        canvas_wrap.grid(row=0, column=1, sticky="nsew")
        canvas_wrap.grid_columnconfigure(0, weight=1)
        canvas_wrap.grid_rowconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(
            canvas_wrap, bg=T.TIMELINE_BG, highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        hbar = ctk.CTkScrollbar(canvas_wrap, orientation="horizontal", command=self._on_hscroll)
        hbar.grid(row=1, column=0, sticky="ew")
        self._hbar = hbar

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel(e, delta=1))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel(e, delta=-1))
        # Delete/Backspace/shortcuts only fire while the canvas itself has
        # focus (set on click below) — deliberately scoped, since CTk
        # disallows bind_all on its widgets ("could result in undefined
        # behavior"), and this naturally avoids stealing keys from text
        # fields elsewhere in the app (spec item 22).
        try:
            self.canvas.configure(takefocus=1)
        except Exception:
            pass
        self.canvas.bind("<Delete>", self._on_delete_key)
        self.canvas.bind("<BackSpace>", self._on_delete_key)
        self.canvas.bind("<Home>", lambda _e: self.set_playhead(0.0))
        self.canvas.bind("<End>", lambda _e: self.set_playhead(self._duration()))
        self.canvas.bind("<Left>", lambda _e: self.set_playhead(max(0.0, self._playhead - 1.0)))
        self.canvas.bind("<Right>", lambda _e: self.set_playhead(min(self._duration(), self._playhead + 1.0)))
        self.canvas.bind("<Control-b>", lambda _e: self._on_split_selected())
        self.canvas.bind("<Command-b>", lambda _e: self._on_split_selected())
        self.canvas.bind("<Control-d>", lambda _e: self._on_duplicate_selected())
        self.canvas.bind("<Command-d>", lambda _e: self._on_duplicate_selected())

    # ---- data binding ----

    def set_timeline(self, timeline, *, save_cb: Optional[Callable[[], None]] = None) -> None:
        self._timeline = timeline
        self._save_cb = save_cb
        self._selected_id = None
        # Track-level mute/solo lives ON the timeline now (persisted —
        # see editorial/timeline.py's muted_tracks/solo_tracks) rather than
        # being purely session-local; load it here so a reopened project
        # shows the same mute/solo state it was saved with.
        self._muted_tracks = set(getattr(timeline, "muted_tracks", []) or [])
        self._solo_tracks = set(getattr(timeline, "solo_tracks", []) or [])
        self._waveform_peaks = {}
        self._waveform_pending = set()
        self.redraw()

    def set_waveform_state_dir(self, state_dir) -> None:
        """Where to cache decoded waveforms for this project — see
        waveform_cache.py. Call once when a project opens (EditorView.on_show)."""
        self._waveform_state_dir = Path(state_dir) if state_dir is not None else None

    def _request_waveform(self, ev) -> None:
        if _waveform_cache is None or self._waveform_state_dir is None:
            return
        if ev.event_id in self._waveform_peaks or ev.event_id in self._waveform_pending:
            return
        try:
            from preview_engine import resolve_audio_source

            source = resolve_audio_source(ev)
        except Exception:
            source = ev.source
        if not source:
            return
        self._waveform_pending.add(ev.event_id)
        state_dir = self._waveform_state_dir
        event_id = ev.event_id

        def work():
            peaks = _waveform_cache.get_or_build_waveform(state_dir, Path(source), buckets=300)
            self._waveform_queue.put((event_id, peaks))

        threading.Thread(target=work, daemon=True).start()

    def _poll_waveform_queue(self) -> None:
        changed = False
        try:
            while True:
                event_id, peaks = self._waveform_queue.get_nowait()
                self._waveform_pending.discard(event_id)
                self._waveform_peaks[event_id] = peaks or []
                changed = True
        except queue.Empty:
            pass
        if changed:
            self.redraw()
        self.after(200, self._poll_waveform_queue)

    def set_playhead(self, seconds: float, *, notify: bool = True) -> None:
        self._playhead = max(0.0, float(seconds))
        self.redraw()
        if notify and self._on_playhead_change is not None:
            try:
                self._on_playhead_change(self._playhead)
            except Exception:
                pass

    # ---- zoom / scroll ----

    def _on_zoom_in(self) -> None:
        self._zoom = L.zoom_in(self._zoom)
        self.redraw()

    def _on_zoom_out(self) -> None:
        self._zoom = L.zoom_out(self._zoom)
        self.redraw()

    def _on_toggle_snap(self) -> None:
        self._snap_enabled = not self._snap_enabled
        self._snap_btn.configure(
            fg_color=T.ACCENT_SEL if self._snap_enabled else "transparent",
            border_color=T.ACCENT if self._snap_enabled else T.BORDER,
            text_color=T.ACCENT if self._snap_enabled else T.MUTED,
        )
        self._notify("Snapping " + ("on" if self._snap_enabled else "off"))

    def _on_hscroll(self, *args) -> None:
        if not args:
            return
        if args[0] == "moveto":
            frac = float(args[1])
            total_w = L.content_width(self._duration(), self._zoom)
            self._scroll_x = frac * total_w
        elif args[0] == "scroll":
            amount, unit = float(args[1]), args[2]
            step = 40.0 if unit == "units" else self.canvas.winfo_width()
            self._scroll_x = max(0.0, self._scroll_x + amount * step)
        self.redraw()

    def _on_wheel(self, event, delta: Optional[int] = None) -> None:
        d = delta if delta is not None else (1 if event.delta > 0 else -1)
        self._scroll_x = max(0.0, self._scroll_x - d * 40.0)
        self.redraw()

    def _duration(self) -> float:
        # NOT timeline.audio_end directly — that's the narration's own
        # fixed length and stays untouched by editing (see
        # editorial_timeline_edit.timeline_duration's docstring). Reading
        # it here made the ruler/scroll extent stop at the ORIGINAL
        # length even after an edit (e.g. extending an IMAGE clip's
        # duration) made the timeline genuinely longer — the clip became
        # real in the data model but literally impossible to see or
        # scroll to, reported live as "the editor still behaves like
        # duration is fixed."
        if self._timeline is None or tl_edit is None:
            return float(self._timeline.audio_end) if self._timeline is not None else 0.0
        return tl_edit.timeline_duration(self._timeline)

    # ---- hit testing ----

    def _event_at(self, x: float, y: float):
        if self._timeline is None:
            return None
        # MUST match the row layout redraw() actually drew (self._last_rows,
        # cached there) — recomputing independently here previously used a
        # different track set and silently hit-tested against the WRONG y
        # positions (see redraw()'s comment for the concrete bug history).
        rows = self._last_rows or L.track_rows(
            {e.track for e in self._timeline.events} | set(L.ALWAYS_PRESENT_TRACKS)
        )
        t = L.x_to_time(x, self._zoom, self._scroll_x)
        for e in self._timeline.events:
            y0 = L.track_y(e.track, rows)
            if y0 <= y <= y0 + L.TRACK_HEIGHT and e.start <= t <= e.end:
                return e
        return None

    # ---- mouse interaction ----

    def _hit_zone_px(self, ev) -> float:
        """Edge hit-zone half-width in canvas pixels, from the clip's
        ACTUAL rendered rectangle — 8-12px, capped at a third of the clip's
        own width so two edge zones on a short clip can never overlap or
        swallow the whole clip."""
        x0 = L.time_to_x(ev.start, self._zoom, self._scroll_x)
        x1 = L.time_to_x(ev.end, self._zoom, self._scroll_x)
        return max(4.0, min(12.0, (x1 - x0) / 3.0))

    def _drag_mode_for(self, ev, x: float) -> Optional[str]:
        """"trim_start" / "trim_end" / "reorder" / "move", or None if this
        event isn't interactive right now (locked track, non-editable
        track, or no event under the cursor). Single source of truth for
        BOTH _on_press (what a click starts) and _on_hover (what cursor to
        show) — previously these were computed separately and could drift."""
        if ev is None or tl_edit is None or not tl_edit.is_editable(ev) or ev.track in self._locked_tracks:
            return None
        x0 = L.time_to_x(ev.start, self._zoom, self._scroll_x)
        x1 = L.time_to_x(ev.end, self._zoom, self._scroll_x)
        edge_zone = self._hit_zone_px(ev)
        if abs(x0 - x) <= edge_zone:
            return "trim_start"
        if abs(x1 - x) <= edge_zone:
            return "trim_end"
        # PRIMARY visual clips (VIDEO_1/IMAGE) reorder within the ripple-
        # locked playhead; everything else — including VIDEO_2 B-roll, an
        # independent overlay track (see OVERLAY_VISUAL_TRACKS) — is a
        # plain move, dragged to any time.
        return "reorder" if ev.track in tl_edit.PRIMARY_VISUAL_TRACKS else "move"

    _CURSOR_FOR_MODE = {
        "trim_start": "sb_h_double_arrow", "trim_end": "sb_h_double_arrow",
        "reorder": "fleur", "move": "fleur",
    }

    def _on_hover(self, event) -> None:
        ev = self._event_at(event.x, event.y)
        new_hover = ev.event_id if ev is not None else None
        if new_hover != self._hover_id:
            self._hover_id = new_hover
            self.redraw()
        mode = self._drag_mode_for(ev, event.x) if event.y >= L.RULER_HEIGHT else None
        cursor = self._CURSOR_FOR_MODE.get(mode, "")
        try:
            if self.canvas.cget("cursor") != cursor:
                self.canvas.configure(cursor=cursor)
        except Exception:
            pass

    def _on_press(self, event) -> None:
        try:
            self.canvas.focus_set()
        except Exception:
            pass
        if event.y < L.RULER_HEIGHT:
            # Click-drag on the time ruler seeks AND drags the playhead
            # (spec item 6/7) — snapping to clip/scene boundaries exactly
            # like a clip drag, reusing the same snap_time/scene_boundaries
            # (see _playhead_snap_bounds) rather than a second system.
            t = L.x_to_time(event.x, self._zoom, self._scroll_x)
            if self._snap_enabled and tl_edit is not None and self._timeline is not None:
                t = tl_edit.snap_time(t, self._playhead_snap_bounds())
            self.set_playhead(max(0.0, t))
            self._drag = {"mode": "playhead"}
            return
        ev = self._event_at(event.x, event.y)
        self._selected_id = ev.event_id if ev is not None else None
        if self._on_select is not None:
            try:
                self._on_select(self._selected_id)
            except Exception:
                pass
        mode = self._drag_mode_for(ev, event.x)
        if mode is not None:
            pps = L.pixels_per_second(self._zoom)
            visual = ev.track in tl_edit.VISUAL_TRACKS
            self._drag = {
                "event_id": ev.event_id, "mode": mode, "visual": visual,
                "orig_start": ev.start, "orig_end": ev.end,
                "press_x": event.x, "pps": pps,
                "snapshot": self._snapshot_events() if visual else None,
            }
        else:
            self._drag = None
        self.redraw()

    def _snapshot_events(self):
        return [_copy.copy(e) for e in (self._timeline.events if self._timeline else [])]

    def _restore_events(self, snapshot) -> None:
        if self._timeline is not None:
            self._timeline.events = [_copy.copy(e) for e in snapshot]

    def _playhead_snap_bounds(self) -> list:
        """Snap targets for a playhead drag: every clip's start/end (any
        track — "clip start"/"clip end"/"transition boundary" all coincide
        with a clip edge) plus scene_boundaries()'s own set (scene edges +
        0/audio_end). Reuses tl_edit.snap_time — no second snapping system."""
        bounds = list(tl_edit.scene_boundaries(self._timeline)) if self._timeline is not None else []
        if self._timeline is not None:
            for e in self._timeline.events:
                bounds.append(round(float(e.start), 3))
                bounds.append(round(float(e.end), 3))
        return bounds

    def _clip_snap_target(self, t: float) -> float:
        """Snap a clip-drag candidate time to scene boundaries AND the
        current playhead (spec item 11: "snap to playhead") — same
        snap_time()/tolerance the boundary-only snap already used, just
        with the playhead added to the candidate set."""
        if not self._snap_enabled or tl_edit is None or self._timeline is None:
            return t
        bounds = list(tl_edit.scene_boundaries(self._timeline))
        bounds.append(self._playhead)
        return tl_edit.snap_time(t, bounds)

    def _on_drag(self, event) -> None:
        if not self._drag or self._timeline is None or tl_edit is None:
            return
        d = self._drag
        if d["mode"] == "playhead":
            t = L.x_to_time(event.x, self._zoom, self._scroll_x)
            if self._snap_enabled:
                t = tl_edit.snap_time(t, self._playhead_snap_bounds())
            self.set_playhead(max(0.0, t))
            return
        dt = (event.x - d["press_x"]) / d["pps"] if d["pps"] else 0.0
        if d["mode"] == "move":
            target = self._clip_snap_target(d["orig_start"] + dt)
            tl_edit.move_event(self._timeline, d["event_id"], target, snap=False)
        elif d["mode"] == "trim_start":
            target = self._clip_snap_target(d["orig_start"] + dt)
            tl_edit.trim_event_start(self._timeline, d["event_id"], target, snap=False)
        elif d["mode"] == "trim_end":
            target = self._clip_snap_target(d["orig_end"] + dt)
            tl_edit.trim_event_end(self._timeline, d["event_id"], target, snap=False)
        elif d["mode"] == "reorder":
            mouse_t = L.x_to_time(event.x, self._zoom, self._scroll_x)
            target_index = self._visual_target_index(d["event_id"], mouse_t)
            tl_edit.move_visual_event_to_index(self._timeline, d["event_id"], target_index)
        # Snap indicator: a visible guide line whenever the dragged edge
        # landed exactly on a scene boundary OR the playhead this frame
        # (move/trim), or — for reorder — at the clip's new (post-move)
        # start, so the operator gets an unambiguous "this is where it
        # landed" cue even though the clip rectangle itself also visibly
        # moved.
        ev = tl_edit.find_event(self._timeline, d["event_id"])
        self._snap_guide_x = None
        if ev is not None:
            if d["mode"] == "reorder":
                self._snap_guide_x = L.time_to_x(ev.start, self._zoom, self._scroll_x)
            elif self._snap_enabled:
                bounds = list(tl_edit.scene_boundaries(self._timeline)) + [self._playhead]
                edge = ev.start if d["mode"] != "trim_end" else ev.end
                if any(abs(edge - b) < 1e-6 for b in bounds):
                    self._snap_guide_x = L.time_to_x(edge, self._zoom, self._scroll_x)
        self.redraw()

    def _visual_target_index(self, event_id: str, mouse_time: float) -> int:
        """Which slot in the visual sequence the mouse is currently over —
        each clip's midpoint is the tipping point, same convention as most
        drag-to-reorder timelines."""
        ordered = [e for e in tl_edit.visual_sequence_order(self._timeline) if e.event_id != event_id]
        idx = 0
        for e in ordered:
            if mouse_time > (e.start + e.end) / 2.0:
                idx += 1
            else:
                break
        return idx

    def _on_release(self, event) -> None:
        if not self._drag or self._timeline is None:
            self._drag = None
            return
        d = self._drag
        self._drag = None
        self._snap_guide_x = None
        if d.get("mode") == "playhead":
            # Seeking the playhead isn't a timeline edit — nothing to push
            # onto the undo stack, just stop dragging.
            self.redraw()
            return
        ev = tl_edit.find_event(self._timeline, d["event_id"]) if tl_edit else None
        if ev is None:
            return
        if d.get("visual"):
            # Ripple trim may have shifted many other events — snapshot the
            # whole event list for undo, rather than just this one event.
            after_snapshot = self._snapshot_events()
            before_snapshot = d["snapshot"]
            if [ (e.start, e.end) for e in after_snapshot ] == [ (e.start, e.end) for e in before_snapshot ]:
                return  # no actual change

            def do():
                self._restore_events(after_snapshot)
                self._after_edit()

            def undo():
                self._restore_events(before_snapshot)
                self._after_edit()

            label = {
                "trim_start": "Trim start (ripple)", "trim_end": "Trim end (ripple)",
                "reorder": "Reorder clip",
            }.get(d["mode"], "Edit clip")
            self._push(label, do, undo, run=False)
            return
        new_start, new_end = ev.start, ev.end
        if (new_start, new_end) == (d["orig_start"], d["orig_end"]):
            return  # no actual change -> nothing to record
        # Revert to the pre-drag state, then push a proper undo Command so
        # redo/undo replays through the same tested functions, not a raw
        # field write.
        ev.start, ev.end = d["orig_start"], d["orig_end"]

        def do():
            ev2 = tl_edit.find_event(self._timeline, d["event_id"])
            if ev2 is not None:
                ev2.start, ev2.end = new_start, new_end
            self._after_edit()

        def undo():
            ev2 = tl_edit.find_event(self._timeline, d["event_id"])
            if ev2 is not None:
                ev2.start, ev2.end = d["orig_start"], d["orig_end"]
            self._after_edit()

        label = {"move": "Move clip", "trim_start": "Trim start", "trim_end": "Trim end"}[d["mode"]]
        self._push(label, do, undo)

    def _on_double_click(self, event) -> None:
        if self._timeline is None or tl_edit is None:
            return
        t = L.x_to_time(event.x, self._zoom, self._scroll_x)
        ev = self._event_at(event.x, event.y)
        if ev is None or not tl_edit.is_editable(ev) or ev.track in self._locked_tracks:
            return
        self._on_double_click_at(ev.event_id, t)

    def _on_delete_key(self, event) -> None:
        self._on_delete_selected()

    def _on_delete_selected(self) -> None:
        if self._selected_id is None or self._timeline is None or tl_edit is None:
            return
        event_id = self._selected_id
        ev = tl_edit.find_event(self._timeline, event_id)
        if ev is None or not tl_edit.is_editable(ev) or ev.track in self._locked_tracks:
            return
        before = self._snapshot_events()

        def do():
            tl_edit.delete_event(self._timeline, event_id)
            self._selected_id = None
            self._after_edit()
            self._notify("Clip deleted")

        def undo():
            self._restore_events(before)
            self._after_edit()

        self._push("Delete clip", do, undo)

    def _on_duplicate_selected(self) -> None:
        """Ctrl/Cmd+D — spec item 22. Inserts a copy immediately after the
        original (ripple-inserted for visual tracks, appended for
        freely-movable tracks), clamped to stay inside the timeline."""
        if self._selected_id is None or self._timeline is None or tl_edit is None:
            return
        ev = tl_edit.find_event(self._timeline, self._selected_id)
        if ev is None or not tl_edit.is_editable(ev) or ev.track in self._locked_tracks:
            return
        event_id = self._selected_id
        before = self._snapshot_events()
        new_id_box: dict = {}

        def do():
            new_id_box["id"] = tl_edit.duplicate_event(self._timeline, event_id)
            self._selected_id = new_id_box.get("id")
            self._after_edit()
            self._notify("Clip duplicated")

        def undo():
            self._restore_events(before)
            self._after_edit()

        self._push("Duplicate clip", do, undo)

    def _on_split_selected(self) -> None:
        if self._selected_id is None or self._timeline is None or tl_edit is None:
            return
        ev = tl_edit.find_event(self._timeline, self._selected_id)
        if ev is None:
            return
        mid = (ev.start + ev.end) / 2.0
        self._on_double_click_at(ev.event_id, mid)

    def _on_double_click_at(self, event_id: str, t: float) -> None:
        before = self._snapshot_events()

        def do():
            tl_edit.split_event(self._timeline, event_id, t)
            self._after_edit()
            self._notify("Clip split")

        def undo():
            self._restore_events(before)
            self._after_edit()

        self._push("Split clip", do, undo)

    def _push(self, label: str, do, undo, *, run: bool = True) -> None:
        if self._undo is not None:
            self._undo.push(Command(label, do=do, undo=undo), run=run)
        elif run:
            do()

    def _notify(self, message: str) -> None:
        if self._on_notify is not None:
            try:
                self._on_notify(message)
            except Exception:
                pass

    def _after_edit(self) -> None:
        self.redraw()
        if self._on_dirty is not None:
            try:
                self._on_dirty()
            except Exception:
                pass
        if self._save_cb is not None:
            try:
                self._save_cb()
            except Exception:
                pass

    # ---- drawing ----

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        try:
            self._zoom_label.configure(text=f"{int(self._zoom * 100)}%")
        except Exception:
            pass
        if self._timeline is None:
            c.create_text(
                20, 20, anchor="nw", fill=T.MUTED,
                text="No timeline yet.", font=("", 12),
            )
            self._rebuild_track_headers([])
            self._last_rows = []
            return
        rows = L.track_rows({e.track for e in self._timeline.events} | set(L.ALWAYS_PRESENT_TRACKS))
        # _event_at() hit-tests against exactly these rows (see its own
        # docstring/comment) — the two MUST never diverge, or a click lands
        # on a different y than what's actually drawn (found via manual
        # testing: every track from IMAGE onward silently stopped
        # responding to clicks whenever a project had no VIDEO_1 events at
        # all — e.g. an all-generated-stills project — because _event_at()
        # used to recompute rows from a DIFFERENT, un-unioned track set).
        self._last_rows = rows
        self._rebuild_track_headers(rows)
        width = max(self.canvas.winfo_width(), 200)
        duration = self._duration()
        height = L.total_height(rows)
        any_solo = bool(self._solo_tracks)

        # Ruler
        c.create_rectangle(0, 0, width, L.RULER_HEIGHT, fill=T.PANEL, outline="")
        for t, label in L.ruler_ticks(duration, self._zoom):
            x = L.time_to_x(t, self._zoom, self._scroll_x)
            if x < -20 or x > width + 20:
                continue
            c.create_line(x, L.RULER_HEIGHT - 6, x, L.RULER_HEIGHT, fill=T.BORDER)
            c.create_text(x + 2, 2, anchor="nw", fill=T.MUTED, text=label, font=("", 9))

        # Track rows (labels now live in the fixed-left header column)
        for i, track in enumerate(rows):
            y0 = L.track_y(track, rows)
            dimmed = any_solo and track not in self._solo_tracks
            fill = T.TRACK if i % 2 == 0 else T.TRACK_ALT
            c.create_rectangle(0, y0, width, y0 + L.TRACK_HEIGHT, fill=fill, outline="")
            if dimmed:
                c.create_rectangle(0, y0, width, y0 + L.TRACK_HEIGHT, fill=T.BG, outline="", stipple="gray50")

        # Clips
        for ev in self._timeline.events:
            x0, y0, x1, y1 = L.clip_rect(ev.start, ev.end, ev.track, rows, self._zoom, self._scroll_x)
            if x1 < 0 or x0 > width:
                continue
            color = T.get_token(_TRACK_COLOR_KEYS.get(ev.track, "clip_video"))
            editable = tl_edit.is_editable(ev) if tl_edit else False
            locked = ev.track in self._locked_tracks
            muted = ev.track in self._muted_tracks or bool((ev.metadata or {}).get("muted"))
            dimmed = (any_solo and ev.track not in self._solo_tracks) or muted
            is_selected = ev.event_id == self._selected_id
            is_hovered = ev.event_id == self._hover_id and not is_selected
            outline = T.ACCENT if is_selected else (T.TEXT if is_hovered else "")
            width_o = 2 if is_selected else (1 if is_hovered else 0)
            c.create_rectangle(
                x0, y0 + 2, x1, y1 - 2, fill=color, outline=outline, width=width_o,
                stipple="gray50" if (not editable or dimmed) else "",
            )
            if locked:
                c.create_text(x1 - 10, y0 + 8, anchor="ne", fill=T.TEXT, text="🔒", font=("", 8))
            label = ev.source.rsplit("/", 1)[-1] if ev.source else ev.track
            if ev.track in AUDIO_TRACKS:
                self._draw_waveform(ev, x0, y0, x1, y1)
            c.create_text(x0 + 4, (y0 + y1) / 2, anchor="w", fill=T.TEXT, text=label[:28], font=("", 9))

        # Snap guide (spec item 7) — a bright vertical line the instant a
        # drag lands exactly on a scene boundary.
        if self._snap_guide_x is not None:
            c.create_line(self._snap_guide_x, 0, self._snap_guide_x, height, fill=T.ACCENT, width=1, dash=(3, 2))

        # Playhead
        px = L.time_to_x(self._playhead, self._zoom, self._scroll_x)
        if 0 <= px <= width:
            c.create_line(px, 0, px, height, fill=T.PLAYHEAD, width=2)
            c.create_polygon(px - 5, 0, px + 5, 0, px, 8, fill=T.PLAYHEAD, outline="")

        total_w = max(width, L.content_width(duration, self._zoom))
        try:
            self._hbar.set(self._scroll_x / total_w, (self._scroll_x + width) / total_w)
        except Exception:
            pass

    def _draw_waveform(self, ev, x0: float, y0: float, x1: float, y1: float) -> None:
        """Real decoded-audio peaks (waveform_cache.py), drawn as a
        min/max envelope filling the clip's own rectangle. Kicks off a
        background fetch on first sight of this event and simply draws
        nothing until it's ready — never a placeholder/fake waveform."""
        peaks = self._waveform_peaks.get(ev.event_id)
        if peaks is None:
            self._request_waveform(ev)
            return
        if not peaks:
            return
        clip_w = x1 - x0
        if clip_w < 6:
            return
        mid_y = (y0 + y1) / 2.0
        half_h = max(1.0, (y1 - y0) / 2.0 - 3.0)
        n = len(peaks)
        step = clip_w / n
        points_top = []
        points_bottom = []
        for i, (lo, hi) in enumerate(peaks):
            px = x0 + i * step
            points_top.append((px, mid_y - hi * half_h))
            points_bottom.append((px, mid_y - lo * half_h))
        # One filled polygon (top edge left->right, bottom edge right->left)
        # renders the whole envelope with a single canvas item instead of
        # 2*n separate line segments — keeps redraw cheap even for a long
        # voiceover track at high zoom.
        poly = []
        for px, py in points_top:
            poly += [px, py]
        for px, py in reversed(points_bottom):
            poly += [px, py]
        try:
            self.canvas.create_polygon(*poly, fill=T.TEXT, outline="", stipple="gray25")
        except Exception:
            pass

    def _rebuild_track_headers(self, rows) -> None:
        """Fixed-left track-header widgets: one small row per TRACK (≤ 9),
        not per clip. Only rebuilt when the track set actually changes, so
        a plain playhead move/redraw doesn't churn widgets."""
        if list(rows) == self._header_rows.get("_order"):
            return
        for w in self._header_col.winfo_children():
            if w is not getattr(self, "_header_spacer", None):
                w.destroy()
        self._header_rows = {"_order": list(rows)}
        for i, track in enumerate(rows):
            row = ctk.CTkFrame(self._header_col, fg_color="transparent", height=L.TRACK_HEIGHT)
            row.grid(row=i + 1, column=0, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row, text=L.TRACK_LABELS.get(track, track), font=ctk.CTkFont(size=T.FONT_TIMELINE_LABEL[0]),
                text_color=T.MUTED, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(6, 0))
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=1, column=0, sticky="w", padx=(4, 0))
            if track in AUDIO_TRACKS:
                self._track_toggle_btn(btns, track, "mute", self._muted_tracks, self._toggle_mute)
                self._track_toggle_btn(btns, track, "solo", self._solo_tracks, self._toggle_solo, label="S")
            self._track_toggle_btn(btns, track, "lock", self._locked_tracks, self._toggle_lock)

    def _track_toggle_btn(self, parent, track, kind, state_set, on_toggle, *, label=None):
        active = track in state_set
        icon_name = {"mute": "mute" if active else "unmute", "lock": "lock" if active else "unlock"}.get(kind, kind)
        text = label if label else I.icon(icon_name)
        btn = ctk.CTkButton(
            parent, text=text, width=20, height=18,
            fg_color=(T.ACCENT_SEL if active else "transparent"),
            border_width=1, border_color=(T.ACCENT if active else T.BORDER),
            text_color=(T.ACCENT if active else T.MUTED), font=ctk.CTkFont(size=9),
            command=lambda: on_toggle(track),
        )
        btn.pack(side="left", padx=1)
        tips = {
            "mute": "Mute this track in the timeline view",
            "solo": "Solo — dim every other track in the timeline view",
            "lock": "Lock — prevent edits to this track's clips",
        }
        TT.attach(btn, tips.get(kind, kind))
        return btn

    def _sync_mute_solo_to_timeline(self) -> None:
        """Persist the track-level mute/solo sets onto the timeline object
        itself (see editorial/timeline.py) and save — mirrors _toggle_lock's
        pattern except lock is intentionally session-only (locking is a
        working-safety toggle, not project data an export needs to know
        about) while mute/solo genuinely changes what gets exported."""
        if self._timeline is not None:
            self._timeline.muted_tracks = sorted(self._muted_tracks)
            self._timeline.solo_tracks = sorted(self._solo_tracks)
        self._header_rows = {}  # force header rebuild to repaint the button
        self._after_edit()

    def _toggle_mute(self, track: str) -> None:
        if track in self._muted_tracks:
            self._muted_tracks.discard(track)
        else:
            self._muted_tracks.add(track)
        self._sync_mute_solo_to_timeline()

    def _toggle_solo(self, track: str) -> None:
        if track in self._solo_tracks:
            self._solo_tracks.discard(track)
        else:
            self._solo_tracks.add(track)
        self._sync_mute_solo_to_timeline()

    def _toggle_lock(self, track: str) -> None:
        if track in self._locked_tracks:
            self._locked_tracks.discard(track)
        else:
            self._locked_tracks.add(track)
        self._header_rows = {}
        self.redraw()
