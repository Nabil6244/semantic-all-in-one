"""Auto-render after Generate (Roblox Cinema, Voxel Map): when Generate has planned the film and Render is not clicked within
DELAY_S seconds, Render starts by itself. The status line counts down; Render, Stop, Generate or a new file cancels the countdown.

start(app, key, ...) after a successful Generate; stop(app, key) wherever the plan is replaced or the user acts; pending(app, key)
for the Stop button's state. `still_ok()` is asked at zero: when the plan is gone, a job runs, or the options changed since
Generate, nothing starts and the status says why."""
from __future__ import annotations

from typing import Any, Callable

DELAY_S = 30


def _attr(key: str) -> str:
    return f"_{key}_auto_render"


def pending(app: Any, key: str) -> bool:
    return getattr(app, _attr(key), None) is not None


def stop(app: Any, key: str, *, note: str = "") -> bool:
    """Cancels a running countdown (restoring the status line, plus `note`). True when one was running."""
    state = getattr(app, _attr(key), None)
    if state is None:
        return False
    setattr(app, _attr(key), None)
    if state.get("job") is not None:
        try:
            app.after_cancel(state["job"])
        except Exception:
            pass
    try:
        state["status"].set((state["base"] + ("  " + note if note else "")).strip())
    except Exception:
        pass
    return True


def start(app: Any, key: str, *, status_var: Any, still_ok: Callable[[], str], render: Callable[[], None], tag: str = "",
          delay_s: int = DELAY_S) -> None:
    """Counts down `delay_s` seconds on `status_var`, then calls render() if still_ok() returns "" (else its reason is shown)."""
    stop(app, key)
    state = {"left": int(delay_s), "base": status_var.get(), "status": status_var, "job": None}
    setattr(app, _attr(key), state)

    def tick() -> None:
        if getattr(app, _attr(key), None) is not state:
            return
        if state["left"] <= 0:
            setattr(app, _attr(key), None)
            why = still_ok()
            if why:
                status_var.set(f"{state['base']}  Auto-render did not start: {why}")
                return
            status_var.set(state["base"])
            if tag:
                app._append_log(f"{tag} Render was not clicked within {delay_s} s after Generate: starting it automatically\n")
            render()
            return
        status_var.set(f"{state['base']}  Render starts by itself in {state['left']} s (click Render now, or Stop to wait).")
        state["left"] -= 1
        state["job"] = app.after(1000, tick)

    tick()
    try:
        app._sync_primary_cta()
    except Exception:
        pass
