"""CustomTkinter startup fix: no global layout flush per scrollbar redraw.

CTkScrollbar._draw() and CTkOptionMenu._draw() end with ``canvas.update_idletasks()``. In Tk that call
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


def _patch_draw(cls) -> None:
    """Run cls._draw with its trailing ``canvas.update_idletasks()`` skipped (see the module note)."""
    original_draw = cls._draw
    if getattr(original_draw, "_sy_original", None) is not None:
        return

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
    cls._draw = draw_without_global_flush


def install() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from customtkinter import CTkScrollbar
    except Exception:
        return False
    _patch_draw(CTkScrollbar)
    try:   # CTkOptionMenu._draw has the same global flush: each dropdown built or re-filled ran a full-app layout pass
        from customtkinter import CTkOptionMenu   # (6 dropdowns cost ~5 s of the window opening, 2026-11-23)
        _patch_draw(CTkOptionMenu)
    except Exception:
        pass
    _install_scrollable_frame_unbind()
    _install_resize_deferral()
    _install_skip_same_configure()
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


# ---------------------------------------------------------------------------------------------------- live window resize
#
# Every CustomTkinter widget redraws its rounded shapes (canvas polygons) on each <Configure> it gets. Dragging the
# window edge sends one per pixel to every widget whose size changes, so a page of ~600 widgets redrew hundreds of
# shapes per mouse move: the stutter, worst on Windows, which sends many more resize events than macOS.
# While the main window is being resized, a widget's new size is still recorded at once (layout stays right), but its
# redraw waits; each waiting widget redraws ONCE, RESIZE_SETTLE_MS after the last size change of the window.

import os as _os
import weakref as _weakref

RESIZE_SETTLE_MS = 120

_RESIZE = {"active": False, "after": None, "root": None, "last": None}
_PENDING: "_weakref.WeakValueDictionary" = _weakref.WeakValueDictionary()
_PENDING_FIT: "_weakref.WeakValueDictionary" = _weakref.WeakValueDictionary()
_FIT_ORIGINAL = {"fn": None}
_AFTER_SETTLE: dict = {}


def resizing() -> bool:
    """True while the main window is being resized (redraws and page widths are waiting)."""
    return bool(_RESIZE["active"])


def after_settle(key, fn) -> None:
    """Run fn once when the current window resize settles (the latest fn per key wins)."""
    _AFTER_SETTLE[key] = fn


def _deferred_update_dimensions(self, event):
    width = self._reverse_widget_scaling(event.width)
    height = self._reverse_widget_scaling(event.height)
    if round(self._current_width) == round(width) and round(self._current_height) == round(height):
        return
    self._current_width = width
    self._current_height = height
    if _RESIZE["active"]:
        _PENDING[id(self)] = self   # drawn once the resize settles
        return
    self._draw(no_color_updates=True)


def flush_pending_draws() -> int:
    """Redraw every widget whose redraw waited for the resize to finish. Returns how many were drawn."""
    _RESIZE["active"] = False
    _RESIZE["after"] = None
    for fn in list(_AFTER_SETTLE.values()):   # layout first (page side padding), then widths, then redraws
        try:
            fn()
        except Exception:
            pass
    _AFTER_SETTLE.clear()
    fit = _FIT_ORIGINAL["fn"]
    frames = list(_PENDING_FIT.values())
    _PENDING_FIT.clear()
    for frame in frames:   # first the page widths (they re-lay out the content once), then the waiting redraws
        try:
            if fit is not None and frame.winfo_exists():
                fit(frame, None)
        except Exception:
            pass
    widgets = list(_PENDING.values())
    _PENDING.clear()
    drawn = 0
    for widget in widgets:
        try:
            if widget.winfo_exists():
                widget._draw(no_color_updates=True)
                drawn += 1
        except Exception:
            pass
    return drawn


def _on_root_configure(event) -> None:
    root = _RESIZE["root"]
    if root is None or event.widget is not root:
        return   # the root's binding also fires for every child (bindtags); only the window's own size counts
    size = (event.width, event.height)
    if _RESIZE["last"] is None:
        _RESIZE["last"] = size   # the first size is the window opening, not a resize
        return
    if size == _RESIZE["last"]:
        return
    _RESIZE["last"] = size
    _RESIZE["active"] = True
    pending = _RESIZE["after"]
    if pending is not None:
        try:
            root.after_cancel(pending)
        except Exception:
            pass
    try:
        _RESIZE["after"] = root.after(RESIZE_SETTLE_MS, flush_pending_draws)
    except Exception:
        flush_pending_draws()


def watch_window(root) -> bool:
    """Start deferring redraws while ``root`` (the main window) is resized. Call once after it exists."""
    if _os.environ.get("SYT_NO_RESIZE_DEFER"):
        return False
    old = _RESIZE["root"]
    if old is not None:
        try:
            if old.winfo_exists():
                return old is root
        except Exception:
            pass
        # the watched window was closed (tests build many): start clean, so a resize it left half-done cannot keep
        # every later window's redraws waiting
        _RESIZE.update(active=False, after=None, root=None, last=None)
        _PENDING.clear()
        _PENDING_FIT.clear()
        _AFTER_SETTLE.clear()
    try:
        root.bind("<Configure>", _on_root_configure, add="+")
    except Exception:
        return False
    _RESIZE["root"] = root
    only_window_configure(root)
    return True


def only_window_configure(root) -> bool:
    """Run the main window's <Configure> handlers only for the window itself, not for each child widget.

    Tk passes every widget's <Configure> to its window's bindings too (the window is in each widget's bindtags), and
    each one cost a full Python call (~20 us of event decoding). A window drag resizes thousands of widgets per mouse
    move: ~22,000 Python calls per step on the Visual Director, ~200 ms each step. Those handlers (CustomTkinter's
    window-size tracker and the resize watcher above) only care about the window, so the check now runs inside Tcl
    and a child's event never reaches Python. Handlers bound later with add="+" are left as they are."""
    try:
        script = str(root.tk.call("bind", str(root), "<Configure>"))
    except Exception:
        return False
    if not script.strip() or "%W eq" in script:
        return False
    me = str(root)
    lines = [ln for ln in script.split("\n") if ln.strip()]
    wrapped = "\n".join('if {"%W" eq "' + me + '"} {' + ln + "}" for ln in lines)
    try:
        root.tk.call("bind", me, "<Configure>", wrapped)
    except Exception:
        return False
    return True


def _install_resize_deferral() -> None:
    """Swap the per-widget resize handler. Must run before widgets are built: each widget binds the handler it finds
    on its class when it is created. Without watch_window() the new handler behaves exactly like the old one."""
    if _os.environ.get("SYT_NO_RESIZE_DEFER"):
        return
    try:
        from customtkinter.windows.widgets.core_widget_classes.ctk_base_class import CTkBaseClass
    except Exception:
        return
    if getattr(CTkBaseClass._update_dimensions_event, "_sy_deferred", False):
        return
    _defer_scroll_width()
    _deferred_update_dimensions._sy_deferred = True  # type: ignore[attr-defined]
    _deferred_update_dimensions._sy_original = CTkBaseClass._update_dimensions_event  # type: ignore[attr-defined]
    CTkBaseClass._update_dimensions_event = _deferred_update_dimensions



def _defer_scroll_width() -> None:
    """Every page lives in a CTkScrollableFrame, which stretches its content to the visible width on each resize.
    Tk then re-lays the page out level by level (~12 nested frames), resizing each label dozens of times per step:
    ~2,800 widget resizes per 4 px of window drag on the Visual Director. While the window is being resized the
    content keeps its width (for at most RESIZE_SETTLE_MS) and takes the new one once, when the drag settles."""
    try:
        from customtkinter import CTkScrollableFrame
    except Exception:
        return
    original = CTkScrollableFrame._fit_frame_dimensions_to_canvas
    if getattr(original, "_sy_deferred", False):
        return

    def fit(self, event):
        if _RESIZE["active"]:
            _PENDING_FIT[id(self)] = self
            return None
        return original(self, event)

    fit._sy_deferred = True  # type: ignore[attr-defined]
    fit._sy_original = original  # type: ignore[attr-defined]
    _FIT_ORIGINAL["fn"] = original
    CTkScrollableFrame._fit_frame_dimensions_to_canvas = fit



# ---------------------------------------------------------------------------------------------------- no-op configure
#
# A CustomTkinter widget redraws all its shapes on every configure(), even when nothing changed. The Visuals table
# re-applies each row's state on every refresh (checkbox state, button states, row colour, status text): hundreds of
# full redraws per refresh. A Windows PC's freeze report (2026-11-25) showed 4.5 s in one such refresh. A configure that
# only repeats the current values now returns at once; anything else is passed on unchanged.

_SAME_OK = frozenset({"state", "text", "fg_color", "text_color", "text_color_disabled", "border_width", "border_color",
                      "hover_color", "corner_radius", "cursor", "anchor"})


def _skip_same(original):
    def configure(self, require_redraw=False, **kwargs):
        if kwargs and not require_redraw and _SAME_OK.issuperset(kwargs):
            try:
                if all(self.cget(k) == v for k, v in kwargs.items()):
                    return None
            except Exception:
                pass
        return original(self, require_redraw=require_redraw, **kwargs)

    configure._sy_same = True  # type: ignore[attr-defined]
    configure._sy_original = original  # type: ignore[attr-defined]
    return configure


def _install_skip_same_configure() -> None:
    if _os.environ.get("SYT_NO_SKIP_SAME"):
        return
    try:
        from customtkinter import CTkButton, CTkCheckBox, CTkFrame, CTkLabel
    except Exception:
        return
    for cls in (CTkButton, CTkCheckBox, CTkFrame, CTkLabel):
        own = cls.__dict__.get("configure")
        if own is None or getattr(own, "_sy_same", False):
            continue
        cls.configure = _skip_same(own)
    original_set = CTkCheckBox.__dict__.get("set")
    if original_set is not None and not getattr(original_set, "_sy_same", False):
        def set_state(self, state, from_variable_callback=False):
            if getattr(self, "_check_state", None) is bool(state) and from_variable_callback:
                return None   # the variable was set to what the box already shows (every table refresh): no redraw
            return original_set(self, state, from_variable_callback)

        set_state._sy_same = True  # type: ignore[attr-defined]
        CTkCheckBox.set = set_state
