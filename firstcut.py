"""Automatic first-cut construction (Semantic YT Studio 2.0 — CapCut-style
editor).

Runs the SAME editorial planning pipeline app.py's render flow already
runs (asset validation, voiceover transcription/alignment, editorial plan
build + compile) but stops BEFORE any FFmpeg scene rendering — zero render
cost, zero Flow credit spend, just the plan + timeline the operator will
then edit in the Editor. See app.py's _run_pipeline(mode="firstcut") for
where this reuses the existing pipeline, and ui/editor_view.py for the
Editor that opens once this timeline exists.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Optional

from editorial.timeline import EditorialTimeline, TimelineEvent


def save_first_cut_timeline(
    state_dir: Path,
    editorial_plan: Any,
    *,
    bg_path: Optional[Path] = None,
    sfx_events: Optional[list] = None,
    ambience_beds: Optional[list] = None,
) -> bool:
    """Extract the EditorialTimeline the engine already compiled onto
    ``editorial_plan.timeline`` and persist it via editorial_timeline_edit's
    existing save path — the SAME on-disk representation the Editor loads
    and the render pipeline reconciles edits from. Returns False (never
    raises) if there's nothing to save.

    ``sfx_events``/``ambience_beds`` (from smart_editing.build_plan(), same
    shape mix_sfx_with_narration() consumes) replace the editorial engine's
    own semantic-only SFX/AMBIENCE placeholders with the REAL, resolved,
    audible plan — see editorial_timeline_edit.materialize_sfx_ambience_events
    for why that distinction matters."""
    import editorial_timeline_edit as tl_edit

    raw = getattr(editorial_plan, "timeline", None)
    if not isinstance(raw, dict):
        return False
    timeline = EditorialTimeline.from_dict(raw)
    if not timeline.events:
        return False

    if sfx_events is not None or ambience_beds is not None:
        tl_edit.materialize_sfx_ambience_events(
            timeline, sfx_events=sfx_events, ambience_beds=ambience_beds,
        )

    # MUSIC has no first-class representation in build_timeline_from_decisions
    # (music timing/ducking is computed separately — see app.py's render
    # pipeline) but the Editor needs a real, editable MUSIC clip to show and
    # let the operator mute/volume/replace. One full-length event is a
    # faithful starting point; ducking detail still applies at export time.
    if bg_path and Path(bg_path).is_file():
        timeline.add(
            TimelineEvent(
                event_id="music_bed",
                track="MUSIC",
                start=0.0,
                end=float(timeline.audio_end),
                source=str(bg_path),
                z_index=0,
                metadata={"volume": 0.15},
            )
        )

    return tl_edit.save_timeline(state_dir, timeline)


def build_first_cut_async(app: Any, *, on_done: Optional[Callable[[bool, str], None]] = None) -> bool:
    """Kick off first-cut construction on app's existing worker-thread
    pipeline (mode="firstcut"). Returns False immediately (and calls
    on_done(False, reason) synchronously) if a run is already in progress
    or validation fails — otherwise True, with on_done called later from
    the UI thread once app._on_firstcut_complete fires."""
    if getattr(app, "_running", False):
        if on_done is not None:
            on_done(False, "A run is already in progress.")
        return False

    config, err = app._validate(require_audio=True)
    if err:
        if on_done is not None:
            on_done(False, err)
        return False

    app._firstcut_on_done = on_done
    app._running = True
    try:
        app.generate_btn.configure(state="disabled", text="Building first cut…")
    except Exception:
        pass
    try:
        app.status_var.set("Building first cut…")
        app.stage_var.set("EDITORIAL")
    except Exception:
        pass

    app._worker = threading.Thread(
        target=app._run_pipeline,
        args=(config, "firstcut"),
        daemon=True,
    )
    app._worker.start()
    return True
