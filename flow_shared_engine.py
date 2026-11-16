"""One Flow engine per app.

A FlowEngineManager only reuses an engine it started itself. A style that made its own manager inside the app therefore saw the app's
engine as foreign, killed it and started another (2026-11-16: War Flow pictures never reached the video in the app, while the same code
worked from the command line, where it is the only manager). shared_or_new() returns the app's own manager (registered, or found on the
running app window), or a fresh manager when a style runs on its own.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_SHARED: Optional[Callable[[], Any]] = None


def register_shared(getter: Optional[Callable[[], Any]]) -> None:
    global _SHARED
    _SHARED = getter


def _app_getter() -> Optional[Callable[[], Any]]:
    """The running app window's own engine getter (app.py VideoGeneratorApp._get_flow_engine_manager), found through Tk's default root, so
    app.py needs no change (its line guard reads any added line as a moved one)."""
    try:
        import tkinter

        return getattr(getattr(tkinter, "_default_root", None), "_get_flow_engine_manager", None)
    except Exception:  # noqa: BLE001
        return None


def shared_or_new(log: Callable[[str], None] = print) -> Any:
    for getter in (_SHARED, _app_getter()):
        if getter is None:
            continue
        try:
            mgr = getter()
            if mgr is not None:
                return mgr
        except Exception:  # noqa: BLE001 - no app manager: a manager of our own
            pass
    from providers.flow.engine_manager import FlowEngineManager

    return FlowEngineManager(log=log)
