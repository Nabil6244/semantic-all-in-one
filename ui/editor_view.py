"""CapCut-style editor workspace — Semantic YT Studio 2.0.

The Editor opens automatically once assets + voiceover are ready (the
automatic first-cut — see firstcut.py) and BEFORE final export. It composes
the pieces built for this pass around the existing, already-tested
editorial timeline (editorial_timeline_edit.py) and TimelineCanvas:

  LEFT    MediaBrowser   — real generated assets, insert/drag onto timeline
  CENTER  PreviewPlayer  — real decoded proxy playback (preview_engine.py)
  RIGHT   InspectorPanel — context-sensitive properties for the selection
  BOTTOM  TimelineCanvas — the existing multi-track editable timeline

All four operate on the SAME EditorialTimeline object and the SAME
UndoStack — an edit made anywhere here is real, persists (save_timeline),
and affects export (reconcile_timeline_into_decisions in app.py's render
pipeline).
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from . import theme as T
from .inspector_panel import InspectorPanel
from .media_browser import MediaBrowser
from .preview_player import PreviewPlayer
from .timeline_canvas import TimelineCanvas
from .undo_stack import UndoStack
from .widgets import EmptyState, SectionHeader

try:
    import editorial_timeline_edit as tl_edit
except Exception:  # pragma: no cover
    tl_edit = None

try:
    import preview_engine as pv_engine
except Exception:  # pragma: no cover
    pv_engine = None

PROXY_WIDTH, PROXY_HEIGHT = 480, 270

# Real drag-to-resize bounds (spec item 10) — wide enough to stay usable,
# narrow/wide enough to cap either panel from swallowing the whole window.
MIN_MEDIA_W, MAX_MEDIA_W = 180, 480
MIN_INSPECTOR_W, MAX_INSPECTOR_W = 200, 480


def clamp_panel_width(width: float, min_w: int, max_w: int) -> int:
    """Pure clamp math for a sash drag — kept standalone (no Tk) so it's
    directly unit-testable without a live widget."""
    return int(max(min_w, min(max_w, round(width))))


class EditorView(ctk.CTkFrame):
    key = "editor"

    def __init__(self, master, app: Any, **kwargs):
        super().__init__(master, fg_color=T.PANEL_ALT, **kwargs)
        self.app = app
        self._timeline = None
        self._undo = getattr(app, "_timeline_undo", None) or UndoStack()
        if not hasattr(app, "_timeline_undo"):
            try:
                app._timeline_undo = self._undo
            except Exception:
                pass
        self._proxy_build_token = 0
        self._proxy_result_queue: "queue.Queue" = queue.Queue()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = SectionHeader(
            self, "Editor",
            "Real preview, real timeline — edits here affect the final export.",
        )
        header.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD, 4))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=T.PAD, pady=(0, 6))
        ctk.CTkButton(toolbar, text="↺ Rebuild first cut from assets", height=28, command=self._rebuild_first_cut).pack(side="left")
        self._save_indicator = ctk.CTkLabel(toolbar, text="", font=ctk.CTkFont(size=11), text_color=T.MUTED)
        self._save_indicator.pack(side="left", padx=12)
        ctk.CTkButton(
            toolbar, text="Undo", width=64, height=28, command=self._undo_click,
            fg_color="transparent", border_width=1, border_color=T.BORDER, text_color=T.TEXT,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            toolbar, text="Redo", width=64, height=28, command=self._redo_click,
            fg_color="transparent", border_width=1, border_color=T.BORDER, text_color=T.TEXT,
        ).pack(side="right")

        self._empty = EmptyState(
            self, "No first cut yet",
            "Generate assets and voiceover, then build the first cut to open the "
            "full editor with real preview and an editable timeline.",
            "Build first cut now",
            command=self._rebuild_first_cut,
        )
        self._empty.grid(row=2, column=0, sticky="nsew", padx=T.PAD, pady=(0, T.PAD))

        # Three-panel-over-timeline layout using plain grid (NOT
        # tk.PanedWindow): this customtkinter version's CTkFrame widgets
        # synchronously redraw on <Configure> before their own internal
        # canvas exists when embedded directly as PanedWindow panes,
        # corrupting the widget mid-construction — reproducible even for
        # the pre-existing TimelineCanvas. Real drag-to-resize is instead
        # built directly on the grid geometry manager already in use here:
        # two thin "sash" columns between Media|Preview and Preview|
        # Inspector whose press/drag adjusts the adjacent column's
        # grid_columnconfigure(minsize=...) live (see _start_sash_drag/
        # _drag_sash below) — a genuine resize, not a cosmetic control,
        # using a layout mechanism already proven compatible with these
        # widgets rather than the crash-prone PanedWindow embedding.
        self._panel_widths = dict(getattr(app, "_editor_panel_widths", None) or {"media": 240, "inspector": 260})
        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.grid(row=2, column=0, sticky="nsew", padx=T.PAD, pady=(0, T.PAD))
        self._body.grid_remove()
        self._body.grid_columnconfigure(0, weight=0, minsize=self._panel_widths["media"])
        self._body.grid_columnconfigure(1, weight=0, minsize=6)
        self._body.grid_columnconfigure(2, weight=1)
        self._body.grid_columnconfigure(3, weight=0, minsize=6)
        self._body.grid_columnconfigure(4, weight=0, minsize=self._panel_widths["inspector"])
        self._body.grid_rowconfigure(0, weight=3)
        self._body.grid_rowconfigure(1, weight=0, minsize=240)

        self._media = MediaBrowser(self._body, on_insert=self._on_insert_asset, on_drag_drop=self._on_drag_drop)
        self._media.grid(row=0, column=0, sticky="nsew")

        self._sash_left = self._make_sash("media")
        self._sash_left.grid(row=0, column=1, sticky="ns")

        center = ctk.CTkFrame(self._body, fg_color="transparent")
        center.grid(row=0, column=2, sticky="nsew")
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)
        self._preview = PreviewPlayer(center, on_time_change=self._on_preview_time, canvas_width=PROXY_WIDTH, canvas_height=PROXY_HEIGHT)
        self._preview.grid(row=0, column=0, sticky="nsew")

        self._sash_right = self._make_sash("inspector")
        self._sash_right.grid(row=0, column=3, sticky="ns")

        self._inspector = InspectorPanel(self._body, undo_stack=self._undo, on_change=self._on_edit)
        self._inspector.grid(row=0, column=4, sticky="nsew")

        timeline_wrap = ctk.CTkFrame(self._body, fg_color="transparent")
        timeline_wrap.grid(row=1, column=0, columnspan=5, sticky="nsew", pady=(8, 0))
        timeline_wrap.grid_columnconfigure(0, weight=1)
        timeline_wrap.grid_rowconfigure(0, weight=1)
        self._timeline_canvas = TimelineCanvas(
            timeline_wrap, undo_stack=self._undo,
            on_select=self._on_select, on_dirty=self._on_edit,
            on_notify=lambda msg: app._shell.notify(msg) if getattr(app, "_shell", None) else None,
            on_playhead_change=self._on_canvas_playhead,
        )
        self._timeline_canvas.grid(row=0, column=0, sticky="nsew")

        self.bind("<space>", lambda _e: self._preview.toggle_play())
        self._undo.bind_on_change(self._refresh_undo_indicator)
        self.after(150, self._poll_proxy_queue)

    # ---- panel resizing (spec item 10) ----

    def _make_sash(self, which: str) -> ctk.CTkFrame:
        """A thin draggable divider. ``which`` is "media" (dragging it
        resizes the Media Browser column) or "inspector" (dragging it
        resizes the Inspector column, in the mirrored direction — moving
        it right grows the center Preview and shrinks the Inspector).
        Writes a real grid_columnconfigure(minsize=...) on every motion
        event — an actual resize, not a cosmetic hover effect."""
        sash = ctk.CTkFrame(self._body, fg_color=T.BORDER, width=6, cursor="sb_h_double_arrow")
        sash.grid_propagate(False)
        sash.bind("<ButtonPress-1>", lambda e: self._start_sash_drag(which, e))
        sash.bind("<B1-Motion>", lambda e: self._drag_sash(which, e))
        return sash

    def _start_sash_drag(self, which: str, event) -> None:
        self._sash_drag = {"which": which, "start_x_root": event.x_root, "start_w": self._panel_widths[which]}

    def _drag_sash(self, which: str, event) -> None:
        d = getattr(self, "_sash_drag", None)
        if not d or d["which"] != which:
            return
        dx = event.x_root - d["start_x_root"]
        if which == "media":
            new_w = clamp_panel_width(d["start_w"] + dx, MIN_MEDIA_W, MAX_MEDIA_W)
            col = 0
        else:
            # Dragging the right sash RIGHT should grow the center preview
            # and shrink the Inspector — the mirror image of the left sash.
            new_w = clamp_panel_width(d["start_w"] - dx, MIN_INSPECTOR_W, MAX_INSPECTOR_W)
            col = 4
        self._panel_widths[which] = new_w
        self._body.grid_columnconfigure(col, minsize=new_w)
        # Session-scoped persistence (see module docstring / final report:
        # this doesn't yet survive an app restart, only navigating away
        # from and back to the Editor within one run).
        try:
            self.app._editor_panel_widths = dict(self._panel_widths)
        except Exception:
            pass

    # ---- lifecycle ----

    def on_show(self) -> None:
        ws = getattr(self.app, "_workspace", None)
        if ws is None:
            self._show_empty()
            return
        if tl_edit is None:
            self._show_empty()
            return
        timeline = tl_edit.load_timeline(ws.state_dir)
        if not timeline.events:
            self._show_empty()
            return
        self._timeline = timeline
        self._show_body()
        self._timeline_canvas.set_waveform_state_dir(ws.state_dir)
        self._timeline_canvas.set_timeline(timeline, save_cb=self._save)
        self._inspector.set_timeline(timeline)
        voiceover = None
        try:
            voiceover = ws.get_active_voiceover()
        except Exception:
            pass
        self._media.set_project(ws.assets_dir, voiceover, None)
        self._rebuild_proxy(debounce=False)

    def _show_empty(self) -> None:
        self._empty.grid()
        self._body.grid_remove()

    def _show_body(self) -> None:
        self._empty.grid_remove()
        self._body.grid()

    # ---- first cut ----

    def _rebuild_first_cut(self) -> None:
        ws = getattr(self.app, "_workspace", None)
        if ws is None:
            return
        try:
            from firstcut import build_first_cut_async

            build_first_cut_async(self.app, on_done=lambda ok, msg: self.after(0, self._after_first_cut, ok, msg))
        except Exception as exc:
            if getattr(self.app, "_shell", None):
                self.app._shell.notify(f"Could not build first cut: {exc}")

    def _after_first_cut(self, ok: bool, message: str) -> None:
        if getattr(self.app, "_shell", None):
            self.app._shell.notify(message)
        if ok:
            self.on_show()

    # ---- selection / edit plumbing ----

    def _on_select(self, event_id: Optional[str]) -> None:
        self._inspector.show_event(event_id)

    def _on_edit(self) -> None:
        self._save()
        self._rebuild_proxy(debounce=True)
        self._timeline_canvas.redraw()

    def _save(self) -> None:
        ws = getattr(self.app, "_workspace", None)
        if ws is None or self._timeline is None or tl_edit is None:
            return
        tl_edit.save_timeline(ws.state_dir, self._timeline)
        if hasattr(self.app, "_mark_saved"):
            try:
                self.app._mark_saved()
            except Exception:
                pass

    def _undo_click(self) -> None:
        label = self._undo.undo()
        if label and getattr(self.app, "_shell", None):
            self.app._shell.notify(f"Undid: {label}")
        self._save()
        self._rebuild_proxy(debounce=True)

    def _redo_click(self) -> None:
        label = self._undo.redo()
        if label and getattr(self.app, "_shell", None):
            self.app._shell.notify(f"Redid: {label}")
        self._save()
        self._rebuild_proxy(debounce=True)

    def _refresh_undo_indicator(self) -> None:
        self._timeline_canvas.redraw()

    # ---- media browser wiring ----
    #
    # Visual assets (kind="visual") insert into whichever track the media
    # browser's "Insert visuals to" selector currently says — VIDEO_1
    # (primary) or VIDEO_2 (B-roll), via insert_visual_clip (ripple —
    # never overlaps). Audio assets (voiceover/music) insert as a new,
    # freely-movable clip on their own track via add_event — the same
    # mechanism the Inspector's existing "Add SFX"/"Add Ambience" actions
    # already use (app.py's _details_action), not a separate code path.

    _AUDIO_TRACK_FOR_KIND = {"voiceover": "VOICEOVER", "music": "MUSIC", "sfx": "SFX", "ambience": "AMBIENCE"}
    _DEFAULT_AUDIO_DURATION = {"voiceover": 5.0, "music": 8.0, "sfx": 1.0, "ambience": 6.0}
    # Fallback ONLY for a still image (no intrinsic duration to probe) or a
    # video file ffprobe couldn't read — matches the existing editorial
    # default single-shot duration used elsewhere in the pipeline. A real
    # video asset always gets its ACTUAL probed duration (see
    # _visual_insert_duration) — never this hardcoded value.
    _FALLBACK_VISUAL_DURATION = 4.0

    def _visual_insert_duration(self, path) -> float:
        """The real duration to give a newly-inserted visual clip: an
        actual video file's own ffprobe'd length (memoized — see
        media_duration.probe_media_duration), or the fallback default for
        a still image / an unprobeable file. Never a blind hardcode for a
        real video asset."""
        try:
            ext = Path(path).suffix.lower()
        except Exception:
            return self._FALLBACK_VISUAL_DURATION
        if ext not in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
            return self._FALLBACK_VISUAL_DURATION
        try:
            import media_duration

            dur = media_duration.probe_media_duration(path, log_failures=False)
        except Exception:
            dur = None
        return float(dur) if dur and dur > 0 else self._FALLBACK_VISUAL_DURATION

    def _insert_item_at(self, item, at_time: float) -> Optional[str]:
        if self._timeline is None or tl_edit is None:
            return None
        if item.kind == "visual":
            track = self._media.target_track() if hasattr(self._media, "target_track") else "VIDEO_1"
            duration = self._visual_insert_duration(item.path)
            return tl_edit.insert_visual_clip(
                self._timeline, track=track, at_time=at_time, duration=duration,
                scene_number=item.scene_number, source=str(item.path),
            )
        track = self._AUDIO_TRACK_FOR_KIND.get(item.kind)
        if track is None:
            return None
        dur = self._DEFAULT_AUDIO_DURATION.get(item.kind, 4.0)
        total = tl_edit.timeline_duration(self._timeline)
        end = min(at_time + dur, total) if total else at_time + dur
        if end <= at_time:
            end = at_time + 0.5
        return tl_edit.add_event(
            self._timeline, track=track, start=at_time, end=end,
            scene_number=item.scene_number, source=str(item.path),
        )

    def _on_insert_asset(self, item) -> None:
        playhead = getattr(self._timeline_canvas, "_playhead", 0.0)
        event_id = self._insert_item_at(item, playhead)
        if event_id:
            self._on_edit()
            self._timeline_canvas.redraw()
            if getattr(self.app, "_shell", None):
                self.app._shell.notify(f"Inserted {item.label}")

    def _on_drag_drop(self, item, root_x: int, root_y: int) -> None:
        canvas_widget = self._timeline_canvas.canvas
        cx0, cy0 = canvas_widget.winfo_rootx(), canvas_widget.winfo_rooty()
        cx1, cy1 = cx0 + canvas_widget.winfo_width(), cy0 + canvas_widget.winfo_height()
        if not (cx0 <= root_x <= cx1 and cy0 <= root_y <= cy1):
            return  # dropped outside the timeline — no-op
        from . import timeline_layout as L

        local_x = root_x - cx0
        t = L.x_to_time(local_x, self._timeline_canvas._zoom, self._timeline_canvas._scroll_x)
        self._on_insert_asset_at(item, t)

    def _on_insert_asset_at(self, item, at_time: float) -> None:
        event_id = self._insert_item_at(item, at_time)
        if event_id:
            self._on_edit()
            self._timeline_canvas.redraw()

    # ---- preview <-> timeline sync ----

    def _on_canvas_playhead(self, t: float) -> None:
        self._preview.seek(t)

    def _on_preview_time(self, t: float) -> None:
        self._timeline_canvas.set_playhead(t, notify=False)

    # ---- proxy building (background thread, debounced) ----

    def _rebuild_proxy(self, *, debounce: bool) -> None:
        if self._timeline is None or pv_engine is None:
            return
        ws = getattr(self.app, "_workspace", None)
        if ws is None:
            return
        self._proxy_build_token += 1
        token = self._proxy_build_token
        self._preview.set_building(True)
        delay = 600 if debounce else 0
        self.after(delay, lambda: self._start_proxy_thread(token, ws.state_dir))

    def _start_proxy_thread(self, token: int, state_dir: Path) -> None:
        if token != self._proxy_build_token or self._timeline is None:
            return
        timeline_copy = self._timeline

        ws = getattr(self.app, "_workspace", None)

        def work():
            import copy as _copy

            muted = set(getattr(self._timeline_canvas, "_muted_tracks", set()))
            solo = set(getattr(self._timeline_canvas, "_solo_tracks", set()))
            # Real projects' VOICEOVER TimelineEvents carry no playable
            # source of their own (they're per-beat timing markers over
            # ONE continuous, immutable narration recording — see
            # preview_engine.build_audio_mix's docstring) — the actual
            # file has to come from the workspace, same accessor
            # find_voiceover_audio()/get_active_voiceover() the rest of
            # the app already uses (see on_show()'s media-browser wiring
            # just above). Without this, preview audio silently had no
            # narration at all.
            voiceover_path = None
            if ws is not None:
                try:
                    voiceover_path = ws.get_active_voiceover() or ws.find_voiceover_audio()
                except Exception:
                    voiceover_path = None
            video = pv_engine.build_video_proxy(state_dir, _copy.deepcopy(timeline_copy), width=PROXY_WIDTH, height=PROXY_HEIGHT)
            audio = pv_engine.build_audio_mix(
                state_dir, _copy.deepcopy(timeline_copy), muted_tracks=frozenset(muted), solo_tracks=frozenset(solo),
                voiceover_path=voiceover_path,
            )
            # NOT timeline_copy.audio_end directly — see
            # editorial_timeline_edit.timeline_duration's docstring: an
            # edit that extends a clip past the narration's own length
            # must extend the player's scrub-bar range too, or the extra
            # content becomes real in the data model but unreachable in
            # the UI (reported live as "duration still behaves as fixed").
            duration = tl_edit.timeline_duration(timeline_copy) if tl_edit is not None else float(timeline_copy.audio_end or 0.0)
            # Hand off through a thread-safe queue drained by the main
            # thread's own after()-scheduled poll (see _poll_proxy_queue) —
            # matches this codebase's established _ui_queue/_poll_queue
            # convention (app.py) rather than calling self.after() directly
            # from a worker thread.
            self._proxy_result_queue.put((token, video, audio, duration))

        threading.Thread(target=work, daemon=True).start()

    def _poll_proxy_queue(self) -> None:
        try:
            while True:
                token, video, audio, duration = self._proxy_result_queue.get_nowait()
                self._apply_proxy(token, video, audio, duration)
        except queue.Empty:
            pass
        self.after(150, self._poll_proxy_queue)

    _VISUAL_TRACKS = ("VIDEO_1", "VIDEO_2", "IMAGE")

    def _apply_proxy(self, token: int, video: Optional[Path], audio: Optional[Path], duration: float) -> None:
        if token != self._proxy_build_token:
            return  # a newer edit already superseded this build — discard, never overwrite fresher state
        self._preview.set_building(False)
        has_visual_content = bool(self._timeline) and any(e.track in self._VISUAL_TRACKS for e in self._timeline.events)
        failed = video is None and has_visual_content
        self._preview.set_proxies(video, audio, duration, failed=failed)
        if failed and getattr(self.app, "_shell", None):
            self.app._shell.notify("Preview build failed for this edit — the timeline is unaffected; edit again to retry.")
