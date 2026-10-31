"""Visuals tab: a QUEUED row (never tried) can be made from the scene inspector, not only a failed one.

The inspector's retry button reads "Generate" for queued rows and makes them through the same recovery queue the failed-scene retry
uses (at most four at a time; Flow rows go as one batch). Ready rows are never touched. Kept out of app.py, which only calls these."""
from __future__ import annotations


def label_generate_button(app, generate: bool) -> None:
    """The retry button reads Generate for rows never tried, Regenerate otherwise."""
    btn = getattr(app, "details_retry_btn", None)
    if btn is not None:
        try:
            btn.configure(text="Generate" if generate else "Regenerate")
        except Exception:
            pass


def generate_waiting_scenes(app, scenes: list) -> bool:
    """Generate on a selection that holds QUEUED rows: those rows (and any failed ones in it) are made. False = no queued rows here
    (the failed-scene retry then runs as before)."""
    from app import _scene_key
    snap = app._qa_snapshot()
    status = {s.scene_number: snap.statuses.get(_scene_key(s.scene_number), app._row_status_from_result(s)) for s in scenes}
    waiting = [s for s in scenes if status[s.scene_number] == "waiting"]
    if not waiting:
        return False
    if app._generation_blocks_scene_actions():
        return True
    if len(scenes) == 1:
        app._scene_action("retry", scenes[0])
        return True
    todo = [s for s in scenes if status[s.scene_number] in ("waiting", "needs_action", "failed", "timeout")
            and _scene_key(s.scene_number) not in app._busy_scenes]
    app._recovery_queue = [("retry", s) for s in todo]
    app._recovery_total = len(todo)
    app._recovery_done = 0
    app._append_log(f"\n[QA] generate {len(todo)} queued / unresolved scene(s) — ready scenes untouched\n")
    app._set_qa_bulk_progress(f"GENERATING SCENES  0 / {len(todo)}")
    if not app._retry_pumping:
        app._retry_pumping = True
        app._pump_retry_queue()
    return True
