"""CustomTkinter startup fix: no global layout flush per scrollbar redraw.

CTkScrollbar._draw() ends with ``canvas.update_idletasks()``. In Tk that call
is global: it runs every pending geometry/redraw task in the whole app. The
window builds 36+ scrollbars (every text box has two), so startup ran dozens
of full-app layout passes while widgets were still being created. Tk redraws
the canvas on its next idle pass anyway, which is what the user sees.

install() runs the original _draw with that one call skipped. Everything else
in _draw (shape, colours, hover state) is unchanged.

It also fixes a CustomTkinter leak: every CTkScrollableFrame adds app-wide
("bind all") mouse-wheel and Shift handlers and never removes them, so each
closed dialog left ~8 dead handlers that ran on EVERY later wheel event. The
frame now remembers its handlers and removes exactly those when destroyed.
"""

from __future__ import annotations

_INSTALLED = False


def _skip(*_args, **_kwargs):
    return None


def install() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from customtkinter import CTkScrollbar
    except Exception:
        return False
    original_draw = CTkScrollbar._draw

    def draw_without_global_flush(self, no_color_updates=False):
        canvas = getattr(self, "_canvas", None)
        if canvas is None:
            return original_draw(self, no_color_updates)
        canvas.update_idletasks = _skip  # instance attribute shadows the method for this call only
        try:
            return original_draw(self, no_color_updates)
        finally:
            try:
                del canvas.update_idletasks
            except AttributeError:
                pass

    draw_without_global_flush._sy_original = original_draw  # type: ignore[attr-defined]
    CTkScrollbar._draw = draw_without_global_flush
    _install_scrollable_frame_unbind()
    _INSTALLED = True
    return True


def _remove_all_binding(widget, sequence: str, funcid: str) -> None:
    """Drop one handler from a "bind all" sequence, keeping every other handler on it."""
    script = widget.tk.call("bind", "all", sequence)
    kept = "\n".join(line for line in str(script).split("\n") if funcid not in line)
    widget.tk.call("bind", "all", sequence, kept)
    # bind_all registers the callback on the ROOT window, so only quitting the app would free it. The root's
    # deletecommand frees it now and also takes it off the root's cleanup list (no double delete at exit).
    try:
        widget._root().deletecommand(funcid)
    except Exception:
        pass


def _bind_all_tracked(self, sequence=None, func=None, add=None):
    import tkinter

    funcid = tkinter.Misc.bind_all(self, sequence, func, add)
    if funcid:
        self.__dict__.setdefault("_sy_all_binds", []).append((sequence, funcid))
    return funcid


def _after_tracked(self, ms, func=None, *args):
    """after() that remembers its pending timer so destroy() can cancel it. Tk keeps an after timer alive
    after the widget dies, and its callback name (built from a Python object id) can be reused by a new,
    live callback: a closed dialog's late timer then called the wrong function."""
    import tkinter

    if func is None:
        return tkinter.Misc.after(self, ms)
    pending = self.__dict__.setdefault("_sy_afters", set())
    holder = []

    def run(*a):
        if holder:
            pending.discard(holder[0])
        return func(*a)

    after_id = tkinter.Misc.after(self, ms, run, *args)
    holder.append(after_id)
    pending.add(after_id)
    return after_id


def _wrap_destroy(cls) -> None:
    original_destroy = cls.destroy

    def destroy_and_clean(self):
        for after_id in list(self.__dict__.pop("_sy_afters", ())):
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        for sequence, funcid in self.__dict__.pop("_sy_all_binds", []):
            try:
                _remove_all_binding(self, sequence, funcid)
            except Exception:
                pass
        return original_destroy(self)

    destroy_and_clean._sy_original = original_destroy  # type: ignore[attr-defined]
    cls.destroy = destroy_and_clean


def _install_scrollable_frame_unbind() -> None:
    """Widgets whose app-wide bindings / timers CustomTkinter never removes on destroy:
    CTkScrollableFrame (wheel + Shift), CTkToplevel (<Button-1> focus handler, one per dialog ever opened),
    CTkTabview (tab-switch timer) and CTkTextbox (scrollbar check loop)."""
    from customtkinter import CTkScrollableFrame, CTkTabview, CTkTextbox, CTkToplevel

    for cls in (CTkScrollableFrame, CTkToplevel):
        cls.bind_all = _bind_all_tracked
    for cls in (CTkTabview, CTkTextbox):
        cls.after = _after_tracked
    for cls in (CTkScrollableFrame, CTkToplevel, CTkTabview, CTkTextbox):
        _wrap_destroy(cls)
