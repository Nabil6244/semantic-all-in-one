"""Stress: open/close the Settings window 50 times in the real app (QA, 2026-10-17).

Asserts no growth (beyond a small measured constant per open) in Tcl commands, in app-wide ("bind all") mouse-wheel /
Shift handlers, in traces on the app's Tk variables (gemini_key_var, the backup key vars and every other variable the
window binds to), that the selected tab persists across reopen, that no callback raised, and that destroying the whole
app afterwards raises nothing.

settings.json is never written: app._settings_path / ui.theme._settings_path point at a temp copy, and the real file
is backed up, restored and compared byte-for-byte anyway.
"""

from __future__ import annotations

import filecmp
import json
import re
import shutil
import sys
import tempfile
import tkinter
import traceback
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPENS = 50
ALL_SEQS = ("<MouseWheel>", "<KeyPress-Shift_L>", "<KeyPress-Shift_R>", "<KeyRelease-Shift_L>",
            "<KeyRelease-Shift_R>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>")
TABS = ("General", "Keys & AI", "Flow", "This project")


def _block_flow_engine():
    """Belt and braces: no code path in these tests may start the Flow engine."""
    try:
        from providers.flow import engine_manager as _em

        def _refuse(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        _em.FlowEngineManager.start = _refuse
        _em.FlowEngineManager.ensure_running = _refuse
    except Exception:
        pass


def _walk(root):
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())


class SettingsWindowStress(unittest.TestCase):
    results: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.real_settings = ROOT / "settings.json"
        cls.tmp = Path(tempfile.mkdtemp(prefix="stress_settings_"))
        cls.backup = cls.tmp / "settings.backup.json"
        cls.had = cls.real_settings.is_file()
        data = {}
        if cls.had:
            shutil.copy2(cls.real_settings, cls.backup)
            try:
                data = json.loads(cls.real_settings.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data.pop("active_project_id", None)
        data["projects_root"] = str(cls.tmp / "projects")
        cls.sp = cls.tmp / "settings.json"
        cls.sp.write_text(json.dumps(data), encoding="utf-8")
        cls.errors = []
        try:
            sys.path.insert(0, str(ROOT))
            sys.path.insert(0, str(ROOT / "scripts"))
            _block_flow_engine()
            import app as app_mod
            import ui.theme as T

            app_mod._settings_path = lambda: cls.sp
            T._settings_path = lambda: cls.sp
            import ui_audit

            cls.app_mod, cls.inst = ui_audit.build_app()
        except Exception as exc:  # no display
            cls.inst = None
            cls.skip_reason = str(exc)
            return

        def no_engine(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        cls.inst._get_flow_engine_manager = no_engine
        cls.inst.report_callback_exception = lambda et, ev, tb: cls.errors.append(
            "".join(traceback.format_exception(et, ev, tb)))
        # A real (temp) project so the "This project" tab has content too.
        import project_workspace

        ws = project_workspace.create_project("stress settings", projects_root=cls.tmp / "projects")
        cls.inst._activate_workspace(ws, persist=False)
        cls.inst.update()

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "inst", None) is not None:
                cls.inst.destroy()
        except Exception:
            pass
        finally:
            if cls.had:
                shutil.copy2(cls.backup, cls.real_settings)
                assert filecmp.cmp(cls.backup, cls.real_settings, shallow=False), "settings.json not restored"
            if cls.results:
                print("\n[stress settings] " + json.dumps(cls.results, indent=1), file=sys.stderr)
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        if self.inst is None:
            self.skipTest("needs Tk: " + getattr(self, "skip_reason", ""))

    # --------------------------------------------------------------- helpers
    def _settle(self, n=3):
        for _ in range(n):
            self.inst.update()

    def _n_commands(self) -> int:
        return len(self.inst.tk.splitlist(self.inst.tk.call("info", "commands")))

    def _all_handlers(self) -> dict:
        out = {}
        for seq in ALL_SEQS:
            script = str(self.inst.tk.call("bind", "all", seq))
            out[seq] = sum(1 for line in script.split("\n") if line.strip())
        return out

    def _app_vars(self) -> dict:
        found = {}
        for name, val in vars(self.inst).items():
            if isinstance(val, tkinter.Variable):
                found[name] = val
            elif isinstance(val, (list, tuple)):
                for i, v in enumerate(val):
                    if isinstance(v, tkinter.Variable):
                        found[f"{name}[{i}]"] = v
            elif isinstance(val, dict):
                for k, v in val.items():
                    if isinstance(v, tkinter.Variable):
                        found[f"{name}[{k!r}]"] = v
        return found

    def _trace_counts(self) -> dict:
        out = {}
        for name, var in self._app_vars().items():
            try:
                out[name] = len(var.trace_info())
            except tkinter.TclError:
                out[name] = -1
        return out

    def _n_after(self) -> int:
        return len(self.inst.tk.splitlist(self.inst.tk.call("after", "info")))

    def _open(self):
        before = {str(w) for w in self.inst.winfo_children()}
        self.inst._open_settings()
        self._settle()
        new = [w for w in self.inst.winfo_children() if str(w) not in before and w.winfo_class() == "Toplevel"]
        self.assertEqual(len(new), 1, "Settings did not open exactly one window")
        return new[0]

    def _close(self, win, via_wm: bool):
        handler = ""
        try:
            handler = str(win.protocol("WM_DELETE_WINDOW") or "")
        except Exception:
            pass
        if via_wm and handler:
            win.tk.call(handler)  # what the window's close box does
        else:
            win.destroy()
        self._settle()

    @staticmethod
    def _tabview(win):
        return next(w for w in _walk(win) if type(w).__name__ == "CTkTabview")

    # ------------------------------------------------------------------ test
    def _in_mainloop(self, fn, settle_ms: int = 600):
        """Run fn inside the real mainloop, as the app does: worker threads the window starts (Flow status, cache
        size) call self.after(), which only works while the main thread is in the mainloop."""
        box = {}

        def run():
            try:
                box["value"] = fn()
            except BaseException as exc:  # re-raised below, outside Tk
                box["exc"] = exc
            self.inst.after(settle_ms, self.inst.quit)

        self.inst.after(0, run)
        self.inst.mainloop()
        if "exc" in box:
            raise box["exc"]
        return box.get("value")

    def test_1_open_close_50_times(self):
        self._in_mainloop(self._body_open_close_50)

    def _body_open_close_50(self):
        inst = self.inst
        # Warm-up: the first open builds caches (fonts, images, lazy imports) that stay for the session.
        for _ in range(2):
            self._close(self._open(), via_wm=False)
        self.errors.clear()
        cmds0, handlers0, traces0, after0 = self._n_commands(), self._all_handlers(), self._trace_counts(), self._n_after()
        names_start = set(inst.tk.splitlist(inst.tk.call("info", "commands")))
        tops0 = len([w for w in inst.winfo_children() if w.winfo_class() == "Toplevel"])
        per_open_cmds = []
        tab_mismatch = []
        handlers_open = None
        traces_open = None
        for i in range(OPENS):
            c = self._n_commands()
            win = self._open()
            if i == 0:
                handlers_open = self._all_handlers()
                traces_open = self._trace_counts()
            tabview = self._tabview(win)
            expected = inst._settings.get("settings_tab") or "General"
            if tabview.get() != expected:
                tab_mismatch.append((i, expected, tabview.get()))
            tabview.set(TABS[(i + 1) % len(TABS)])
            self._settle(1)
            self._close(win, via_wm=bool(i % 2))
            self.assertEqual(inst._settings.get("settings_tab"), TABS[(i + 1) % len(TABS)],
                             f"open {i}: tab choice not remembered on close")
            per_open_cmds.append(self._n_commands() - c)
        cmds1, handlers1, traces1, after1 = self._n_commands(), self._all_handlers(), self._trace_counts(), self._n_after()
        # Name the commands the 50 opens left behind (numeric id stripped), grouped.
        from collections import Counter

        leaked = dict(Counter(re.sub(r"^\d+", "", n) for n in
                              set(inst.tk.splitlist(inst.tk.call("info", "commands"))) - names_start).most_common(8))
        tops1 = len([w for w in inst.winfo_children() if w.winfo_class() == "Toplevel"])
        grown_traces = {k: (traces0.get(k), v) for k, v in traces1.items() if v != traces0.get(k)}
        added_while_open = {k: handlers_open[k] - handlers0[k] for k in handlers0 if handlers_open[k] != handlers0[k]}
        traced_while_open = {k: (traces0.get(k), v) for k, v in traces_open.items() if v != traces0.get(k)}
        self.results["open_close"] = {
            "opens": OPENS,
            "tcl_commands_before": cmds0,
            "tcl_commands_after": cmds1,
            "tcl_commands_delta_total": cmds1 - cmds0,
            "tcl_commands_delta_per_open": round((cmds1 - cmds0) / OPENS, 2),
            "leaked_command_names": leaked,
            "per_open_delta_first5": per_open_cmds[:5],
            "per_open_delta_last5": per_open_cmds[-5:],
            "bind_all_handlers_before": handlers0,
            "bind_all_added_while_open": added_while_open,
            "bind_all_handlers_after": handlers1,
            "vars_checked": len(traces0),
            "vars_with_traces_added_while_open": traced_while_open,
            "trace_growth": grown_traces,
            "gemini_key_var_traces": [traces0.get("gemini_key_var"), traces1.get("gemini_key_var")],
            "after_ids_before_after": [after0, after1],
            "toplevels_before_after": [tops0, tops1],
            "tab_mismatches": tab_mismatch,
            "callback_errors": len(self.errors),
            "callback_error_text": [e[-1500:] for e in self.errors[:2]],
        }
        # A stale CustomTkinter after() can call a recycled "<id><lambda>" command (see test_7); that known bug is
        # asserted there. Anything else raised in a callback fails here.
        stale_hits = [e for e in self.errors if "<lambda>() missing 1 required positional argument" in e]
        other = [e for e in self.errors if e not in stale_hits]
        self.results["open_close"]["stale_after_hits"] = len(stale_hits)
        self.assertEqual(other, [], "exceptions in Tk callbacks:\n" + "\n".join(other[:3]))
        self.assertEqual(tab_mismatch, [], "selected tab not restored on reopen")
        self.assertEqual(handlers1, handlers0, "bind-all mouse-wheel/Shift handlers grew")
        self.assertEqual(grown_traces, {}, "traces piled up on app variables")
        self.assertEqual(tops1, tops0, "a Settings window survived its close")
        # CustomTkinter internals leave a few commands per open (measured ~6); allow up to 10/open, flag anything more.
        self.assertLessEqual(cmds1 - cmds0, 10 * OPENS, f"Tcl commands grew {cmds1 - cmds0} over {OPENS} opens")
        self.assertLessEqual(after1 - after0, 5, "after() callbacks piled up")

    def _cycle(self, n):
        for _ in range(n):
            self._close(self._open(), via_wm=False)

    def _py_vars(self) -> int:
        return len(self.inst.tk.splitlist(self.inst.tk.call("info", "globals", "PY_VAR*")))

    def _cmds_named(self, suffix: str) -> int:
        return sum(1 for n in self.inst.tk.splitlist(self.inst.tk.call("info", "commands")) if re.sub(r"^\d+", "", n) == suffix)

    def test_3_measure_leaks_over_10_opens(self):
        self._in_mainloop(self._body_measure_leaks)

    def _body_measure_leaks(self):
        """Measure what 10 more opens leave behind; the two known leaks are asserted (as expected failures) below."""
        import gc
        from collections import Counter

        tk = self.inst.tk
        globs = lambda: {str(n) for n in tk.splitlist(tk.call("info", "globals", "PY_VAR*"))}  # noqa: E731
        b1_before = str(tk.call("bind", "all", "<Button-1>")).count("set_focus")
        focus_cmds, save_cmds, vars0 = self._cmds_named("set_focus"), self._cmds_named("save"), globs()
        self._cycle(10)
        gc.collect()
        self._settle()
        new_vars = globs() - vars0
        kinds = Counter()
        for name in new_vars:
            try:
                kinds[repr(str(tk.globalgetvar(name)))[:40]] += 1
            except Exception:
                kinds["<array/unset>"] += 1
        type(self).leaks = {
            "button1_set_focus_handlers_before_after": [b1_before, str(tk.call("bind", "all", "<Button-1>")).count("set_focus")],
            "set_focus_cmds_delta": self._cmds_named("set_focus") - focus_cmds,
            "save_cmds_delta": self._cmds_named("save") - save_cmds,
            "py_vars_delta": len(new_vars),
            "leaked_py_var_values": dict(kinds.most_common(12)),
        }
        self.results["leaks_10_opens"] = self.leaks

    # BUG (CustomTkinter, reached by every Settings open): CTkToplevel.__init__ does
    # self.bind_all("<Button-1>", set_focus, add=True) (customtkinter/windows/ctk_toplevel.py:79-82) and never
    # unbinds it, so every Settings window leaves one app-wide <Button-1> handler (and its Tcl command
    # "<id>set_focus") behind; after N opens every click in the app runs N dead handlers. ui/ctk_perf.py only
    # untracks CTkScrollableFrame's bind_all handlers, not CTkToplevel's.
    def test_5_button1_bind_all_does_not_grow(self):
        before, after = self.leaks["button1_set_focus_handlers_before_after"]
        self.assertEqual(after, before, "every Settings open leaves an app-wide <Button-1> handler behind")

    # BUG (weather/app_section.py build_settings, `contact.trace_add("write", save)`): the Tcl trace holds `save`,
    # `save` closes over the local StringVar `contact`, so neither the Tcl command "<id>save" nor the variable is
    # ever freed: one of each per Settings open.
    def test_6_weather_contact_trace_released(self):
        self.assertEqual(self.leaks["save_cmds_delta"], 0, f"'save' trace commands left behind: {self.leaks}")

    def test_2_wheel_after_close_is_clean(self):
        """After all those closes a wheel event must not hit a dead handler (it would raise in report_callback)."""
        self.errors.clear()
        target = self.inst.log_box._textbox
        for _ in range(5):
            target.event_generate("<MouseWheel>", delta=-120, x=5, y=5)
            target.event_generate("<KeyPress-Shift_L>")
            target.event_generate("<KeyRelease-Shift_L>")
        self._settle()
        self.assertEqual(self.errors, [], "\n".join(self.errors[:3]))

    def _stale_afters(self) -> list:
        """Pending after() events whose Tcl command no longer exists (the widget that scheduled them was destroyed).
        When the id is reused by a new command of the same name, the stale event calls that unrelated function."""
        tk = self.inst.tk
        cmds = {str(c) for c in tk.splitlist(tk.call("info", "commands"))}
        stale = []
        for aid in tk.splitlist(tk.call("after", "info")):
            try:
                script = str(tk.splitlist(tk.call("after", "info", aid))[0])
            except Exception:
                continue
            name = script.split()[0] if script.split() else ""
            if name and name not in cmds:
                stale.append(re.sub(r"^\d+", "", script))
        return stale

    # BUG (CustomTkinter, reached from Settings): CTkTabview.set() schedules self.after(100, lambda: ...)
    # (customtkinter/windows/widgets/ctk_tabview.py:452) and CTkTextbox runs a self.after(…) scrollbar loop
    # (ctk_textbox.py:177). _open_settings calls tabview.set(last tab) and holds a CTkTextbox, so closing Settings
    # leaves pending Tcl after events whose "<id><lambda>" command tkinter already deleted. CPython reuses the id, so
    # the stale event can run a different, live "<id><lambda>" command: seen intermittently (~1 in 14 runs of test_1)
    # as "TypeError: CTkScrollableFrame.__init__.<locals>.<lambda>() missing 1 required positional argument: 'e'"
    # through report_callback_exception. Fix idea: in ui/ctk_perf.py, track after ids per CTk widget and
    # after_cancel them in destroy.
    def test_7_close_leaves_no_stale_after_events(self):
        before = set(self._stale_afters())
        win = self._open()
        tabview = self._tabview(win)
        tabview.set("Flow" if tabview.get() != "Flow" else "General")
        win.destroy()  # closed right away, as a quick user can
        self.inst.update()
        stale = [s for s in self._stale_afters() if s not in before]
        self.results["stale_afters_after_quick_close"] = stale
        self._settle()
        self.inst.after(400, self.inst.quit)  # let them fire before the next test
        self.inst.mainloop()
        self.assertEqual(stale, [], "closing Settings left after() events pointing at deleted commands")

    def test_9_destroy_app_raises_nothing(self):
        inst = self.inst
        self.errors.clear()
        try:
            inst.destroy()
        except Exception:  # e.g. TclError: can't delete Tcl command
            self.fail("destroying the app raised:\n" + traceback.format_exc())
        finally:
            type(self).inst = None
        self.assertEqual(self.errors, [], "\n".join(self.errors[:3]))


if __name__ == "__main__":
    unittest.main()
