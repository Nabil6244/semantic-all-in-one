"""Tk objects cleaned up on a worker thread never call Tk from there.

A tkinter Variable, Image or Font (and Pillow's ImageTk.PhotoImage) deletes its Tcl side in __del__. When Python's garbage collector runs on
a worker thread, that call is handed to the main thread and the worker waits for it. On 2026-10-19 the app froze for good this way: a worker
was importing a module (holding its import lock) when the collector ran such a __del__ and waited for the main thread, while the main thread
was importing the same module and waited for the worker's lock.

install() wraps those __del__ methods: on the main thread they run as before; on any other thread the object is queued and drain() (called
by the app's main-thread pump, app.VideoGeneratorApp._pump_thread_after) runs the original cleanup a moment later.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable, List, Tuple

_pending: "queue.SimpleQueue[Tuple[Callable, object]]" = queue.SimpleQueue()
_installed: List[str] = []


def _deferred(orig: Callable) -> Callable:
    def __del__(self) -> None:
        if threading.current_thread() is threading.main_thread():
            orig(self)
        else:
            _pending.put((orig, self))     # keeps the object alive until the main thread runs its cleanup (once: PEP 442)
    __del__._tk_thread_guard = True        # type: ignore[attr-defined]
    __del__.__wrapped__ = orig             # type: ignore[attr-defined]
    return __del__


def _targets() -> list:
    out = []
    import tkinter
    import tkinter.font

    out += [tkinter.Variable, tkinter.Image, tkinter.font.Font]
    try:
        from PIL import ImageTk

        out += [ImageTk.PhotoImage, ImageTk.BitmapImage]
    except Exception:                      # noqa: BLE001 -- Pillow's Tk support missing: nothing of it to guard
        pass
    return out


def install() -> List[str]:
    """Wrap the __del__ methods (once). Returns the names of the classes guarded."""
    for cls in _targets():
        d = cls.__dict__.get("__del__")
        if d is None or getattr(d, "_tk_thread_guard", False):
            continue
        cls.__del__ = _deferred(d)
        _installed.append(f"{cls.__module__}.{cls.__qualname__}")
    return list(_installed)


def drain(limit: int = 500) -> int:
    """Run queued cleanups (main thread only). Returns how many ran."""
    if threading.current_thread() is not threading.main_thread():
        return 0
    n = 0
    while n < limit:
        try:
            orig, obj = _pending.get_nowait()
        except queue.Empty:
            break
        try:
            orig(obj)
        except Exception:                  # noqa: BLE001 -- the window may already be gone; a cleanup never stops the app
            pass
        del obj
        n += 1
    return n


def pending() -> int:
    return _pending.qsize()
