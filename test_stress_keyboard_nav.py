"""Stress: keyboard access in the real app (ui/a11y.py), QA 2026-10-17.

For each of the 13 views in ui/theme.NAV_ITEMS: Tab traversal (Tk's own `tk_focusNext`, which is what the <Tab>
binding on "all" runs, plus real <Tab> key events) must cycle through the visible, enabled controls without getting
stuck and without landing on a widget of a hidden view; disabled buttons are skipped; Space / Return on a focused nav
button runs its command.

settings.json is never written: app._settings_path / ui.theme._settings_path point at a temp copy, and the real file
is backed up, restored and compared byte-for-byte anyway.
"""

from __future__ import annotations

import filecmp
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_STEPS = 1500


def _block_flow_engine():
    try:
        from providers.flow import engine_manager as _em

        def _refuse(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        _em.FlowEngineManager.start = _refuse
        _em.FlowEngineManager.ensure_running = _refuse
    except Exception:
        pass


class KeyboardNav(unittest.TestCase):
    results: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.real_settings = ROOT / "settings.json"
        cls.tmp = Path(tempfile.mkdtemp(prefix="stress_kbd_"))
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
        sp = cls.tmp / "settings.json"
        sp.write_text(json.dumps(data), encoding="utf-8")
        cls.errors = []
        try:
            sys.path.insert(0, str(ROOT))
            sys.path.insert(0, str(ROOT / "scripts"))
            _block_flow_engine()
            import app as app_mod
            import ui.theme as T

            app_mod._settings_path = lambda: sp
            T._settings_path = lambda: sp
            import ui_audit

            cls.app_mod, cls.inst = ui_audit.build_app()
            cls.T = T
        except Exception as exc:  # no display
            cls.inst = None
            cls.skip_reason = str(exc)
            return

        def no_engine(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        cls.inst._get_flow_engine_manager = no_engine
        cls.inst.report_callback_exception = lambda *a: cls.errors.append(a)
        cls.inst.geometry("1440x900+20+20")
        import project_workspace

        ws = project_workspace.create_project("stress keyboard", projects_root=cls.tmp / "projects")
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
                print("\n[stress keyboard] " + json.dumps(cls.results, indent=1), file=sys.stderr)
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        if self.inst is None:
            self.skipTest("needs Tk: " + getattr(self, "skip_reason", ""))
        self.errors.clear()

    # --------------------------------------------------------------- helpers
    def _views(self):
        return [k for k, _l, _g in self.T.NAV_ITEMS if self.inst._shell.view(k) is not None]

    def _go(self, key):
        self.inst._shell.navigate(key)
        for _ in range(3):
            self.inst.update()

    def _w(self, path):
        try:
            return self.inst.nametowidget(str(path))
        except Exception:
            return None

    def _viewable(self, path) -> bool:
        return bool(int(self.inst.tk.call("winfo", "viewable", str(path))))

    def _owner_button(self, path):
        """The CTkButton whose canvas `path` is (or None)."""
        w = self._w(path)
        m = getattr(w, "master", None)
        if m is not None and type(m).__name__ == "CTkButton" and getattr(m, "_canvas", None) is w:
            return m
        return None

    def _hidden_view_of(self, path):
        """Name of a hidden view that contains `path`, if any."""
        p = str(path)
        for key, frame in self.inst._shell.views.items():
            if key == self.inst._shell.active_view:
                continue
            fp = str(frame)
            if p == fp or p.startswith(fp + "."):
                return key
        return None

    def _focus_next(self, path) -> str:
        return str(self.inst.tk.call("tk_focusNext", str(path)))

    def _visible_enabled_buttons(self):
        """CTkButton canvases in the main window that are viewable and enabled right now."""
        import customtkinter as ctk

        out = set()
        stack = [self.inst]
        while stack:
            w = stack.pop()
            if w.winfo_class() == "Toplevel" or type(w).__name__.endswith("Toplevel"):
                continue
            stack.extend(w.winfo_children())
            if isinstance(w, ctk.CTkButton) and getattr(w, "_canvas", None) is not None:
                if self._viewable(w._canvas) and str(w.cget("state")) != "disabled":
                    out.add(str(w._canvas))
        return out

    def _walk_tab_ring(self, start: str):
        seen = []
        cur = start
        stuck = None
        for _ in range(MAX_STEPS):
            nxt = self._focus_next(cur)
            if nxt == cur:
                stuck = cur
                break
            seen.append(nxt)
            cur = nxt
            if nxt == start:
                break
        return seen, stuck

    # ------------------------------------------------------------------ tests
    def test_1_tab_ring_every_view(self):
        """tk_focusNext from the view's nav button: closes the ring, visits only viewable/enabled widgets."""
        report = {}
        problems = []
        hidden_problems = []
        for key in self._views():
            self._go(key)
            start = str(self.inst._shell._nav_btns[key]._canvas)
            ring, stuck = self._walk_tab_ring(start)
            hidden = [p for p in ring if not self._viewable(p)]
            in_hidden_view = sorted({self._hidden_view_of(p) for p in ring if self._hidden_view_of(p)})
            disabled = [p for p in ring if (b := self._owner_button(p)) is not None and str(b.cget("state")) == "disabled"]
            visible_btns = self._visible_enabled_buttons()
            reached = set(ring)
            missed = visible_btns - reached
            closed = bool(ring) and ring[-1] == start
            report[key] = {
                "ring_len": len(ring), "closed": closed, "stuck_on": stuck,
                "not_viewable": len(hidden), "hidden_views_entered": in_hidden_view,
                "disabled_buttons_focused": len(disabled),
                "visible_enabled_buttons": len(visible_btns), "visible_buttons_missed": len(missed),
            }
            if not closed or stuck:
                problems.append(f"{key}: Tab ring did not close (len {len(ring)}, stuck on {stuck})")
            if hidden:
                hidden_problems.append(f"{key}: Tab lands on {len(hidden)} non-viewable widget(s) "
                                       f"(hidden views {in_hidden_view}); first: {hidden[0]}")
            if disabled:
                problems.append(f"{key}: Tab lands on {len(disabled)} disabled button(s); first {disabled[0]}")
            if missed:
                problems.append(f"{key}: {len(missed)} visible enabled button(s) not reachable by Tab; "
                                f"first {sorted(missed)[0]}")
        self.results["tab_rings"] = report
        type(self).hidden_problems = hidden_problems
        self.assertEqual(problems, [], "\n".join(problems[:15]))

    # BUG ui/a11y.py:36 — canvas.configure(takefocus=lambda *_a: _is_enabled(btn)). When -takefocus is a script, Tk's
    # ::tk::FocusOK returns the script's result as-is and skips its own `winfo viewable` check, so every enabled
    # button anywhere (hidden pages, hidden panels, collapsed sections: ~120-135 per ring) is in the Tab order.
    # Fix: return 1 only when the button is enabled AND canvas.winfo_viewable(), else 0.
    def test_1b_tab_never_lands_on_hidden_widgets(self):
        if not hasattr(type(self), "hidden_problems"):
            self.test_1_tab_ring_every_view()
        self.assertEqual(self.hidden_problems, [], "\n".join(self.hidden_problems[:15]))

    # BUG (same root cause as test_1b, ui/a11y.py:36): on the Script page, Tab from the second style segmented button
    # (...scriptview...!ctksegmentedbutton.!ctkbutton3) goes to a hidden "Browse" button; `focus` on a non-viewable
    # window does nothing, so focus stays put and every further Tab computes the same target: keyboard focus is
    # trapped on that segment for good (observed: 9 Tabs in a row stay on it).
    def test_2_real_tab_keys_move_focus(self):
        """Real <Tab>/<Shift-Tab> key events go through Tk's bindings and move focus forward and back."""
        self._go("script")
        start = self.inst._shell._nav_btns["script"]._canvas
        self._focus_or_skip(start)
        tk = self.inst.tk
        toplevel = str(self.inst)

        def focused():
            return str(tk.call("focus", "-lastfor", toplevel))

        self.assertEqual(focused(), str(start), "could not focus the nav button")
        def press(seq, at):
            """Send one real key to `at`; the newly focused path. If focus did not move because the window lost
            keyboard focus to another test window (parallel runner), skip as _focus_or_skip does."""
            w = self.inst.nametowidget(at)
            target = w.tk_focusNext() if seq == "<Tab>" else w.tk_focusPrev()
            w.event_generate(seq)
            self.inst.update()
            now = focused()
            if now == at and self.inst.focus_get() is None:
                self.skipTest("the window lost keyboard focus to another window mid-walk")
            if now == at:
                self.fail(f"{seq} did not move focus from {at} (Tk's next/prev target: {target})")
            return now

        path = [focused()]
        for _ in range(25):
            path.append(press("<Tab>", path[-1]))
        self.assertEqual(len(set(path)), len(path), f"focus repeated / got stuck: {path}")
        for p in path:
            self.assertTrue(self._viewable(p), f"Tab focused a non-viewable widget {p}")
        # back again
        back = [path[-1]]
        for _ in range(25):
            back.append(press("<Shift-Tab>", back[-1]))
        self.assertEqual(back[-1], path[0], "Shift+Tab did not walk back to where Tab started")
        self.results["real_tab_path_len"] = len(path)

    def _focus_or_skip(self, widget):
        """Tk sends key events to the widget that HAS focus. With other test windows open (parallel runner) the
        OS may refuse focus_force for a moment and the key would go elsewhere: retry, then skip (not fail)."""
        for _ in range(20):
            widget.focus_force()
            self.inst.update()
            if self.inst.focus_get() is not None and str(self.inst.focus_get()) == str(widget):
                return
            self.inst.after(50)
        self.skipTest("the window could not take keyboard focus (another window is active)")

    def test_3_space_and_return_press_nav_button(self):
        for key, seq in (("audio", "<space>"), ("render", "<Return>"), ("script", "<space>")):
            self._go("project")
            canvas = self.inst._shell._nav_btns[key]._canvas
            self._focus_or_skip(canvas)
            canvas.event_generate(seq)
            for _ in range(3):
                self.inst.update()
            self.assertEqual(self.inst._shell.active_view, key, f"{seq} on the focused {key} nav button did nothing")
        self.assertEqual(self.errors, [])

    def test_4_disabled_button_skipped_and_not_pressed(self):
        import customtkinter as ctk

        self._go("project")
        host = self.inst._shell.views["project"]
        frame = ctk.CTkFrame(host)
        frame.grid(row=999, column=0)
        hits = []
        a = ctk.CTkButton(frame, text="A", command=lambda: hits.append("A"))
        b = ctk.CTkButton(frame, text="B", command=lambda: hits.append("B"), state="disabled")
        c = ctk.CTkButton(frame, text="C", command=lambda: hits.append("C"))
        for btn in (a, b, c):
            btn.pack(side="left")
        try:
            for _ in range(3):
                self.inst.update()
            self.assertEqual(self._focus_next(a._canvas), str(c._canvas), "Tab did not skip the disabled button")
            self.assertEqual(str(self.inst.tk.call("tk_focusPrev", str(c._canvas))), str(a._canvas))
            # Tk delivers generated key events to the focus window, so focus the disabled button's canvas first.
            self._focus_or_skip(b._canvas)
            b._canvas.event_generate("<space>")
            b._canvas.event_generate("<Return>")
            self.inst.update()
            self.assertEqual(hits, [], "a disabled button ran its command from the keyboard")
            b.configure(state="normal")
            self.inst.update()
            self.assertEqual(self._focus_next(a._canvas), str(b._canvas), "re-enabled button not reachable again")
            self._focus_or_skip(b._canvas)
            b._canvas.event_generate("<space>")
            self.inst.update()
            self.assertEqual(hits, ["B"])
        finally:
            frame.destroy()
            self.inst.update()

    def test_5_hidden_view_button_not_focusable(self):
        """A button on a hidden view must not take focus (Tk's FocusOK skips the viewable check when -takefocus is a
        script that returns 1)."""
        self._go("project")
        hidden_btn = next(
            (w for key, frame in self.inst._shell.views.items() if key != "project" for w in _walk(frame)
             if type(w).__name__ == "CTkButton" and str(w.cget("state")) != "disabled"), None)
        if hidden_btn is None:
            self.skipTest("no enabled button on any hidden view")
        self.assertFalse(self._viewable(hidden_btn._canvas))
        ok = str(self.inst.tk.call("tk::FocusOK", str(hidden_btn._canvas)))
        self.results["focusok_hidden_about_button"] = ok
        self.assertIn(ok, ("0", "False", "false"), "a button on a hidden view is Tab-focusable")


def _walk(root):
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())


if __name__ == "__main__":
    unittest.main()
