"""Settings window: closing it remembers the last tab (a later <Destroy> bind used
to replace that handler) and removes the key-variable traces it added."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class SettingsLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = ROOT / "settings.json"
        cls.backup = Path(tempfile.mkdtemp()) / "settings.json"
        cls.had = cls.settings.is_file()
        if cls.had:
            shutil.copy2(cls.settings, cls.backup)
        try:
            import sys

            sys.path.insert(0, str(ROOT / "scripts"))
            import ui_audit

            cls.app_mod, cls.inst = ui_audit.build_app()
        except Exception as exc:  # no display
            cls.inst = None
            cls.skip_reason = str(exc)
            return

        def no_engine(*_a, **_k):
            raise RuntimeError("tests never start the Flow engine")

        cls.inst._get_flow_engine_manager = no_engine
        cls.inst.report_callback_exception = lambda *a: None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "inst", None) is not None:
            cls.inst.destroy()
        if cls.had:
            shutil.copy2(cls.backup, cls.settings)

    def setUp(self):
        if self.inst is None:
            self.skipTest("needs Tk")

    def _open(self):
        before = {str(w) for w in self.inst.winfo_children()}
        self.inst._open_settings()
        self.inst.update()
        return [w for w in self.inst.winfo_children() if str(w) not in before and w.winfo_class() == "Toplevel"][0]

    def test_last_tab_is_remembered(self):
        self.inst._settings["settings_tab"] = "General"
        win = self._open()
        tabview = next(w for w in _walk(win) if type(w).__name__ == "CTkTabview")
        tabview.set("Flow")
        win.destroy()
        self.inst.update()
        self.assertEqual(self.inst._settings.get("settings_tab"), "Flow")
        win = self._open()
        tabview = next(w for w in _walk(win) if type(w).__name__ == "CTkTabview")
        self.assertEqual(tabview.get(), "Flow")
        win.destroy()
        self.inst.update()

    def test_key_traces_do_not_pile_up(self):
        var = self.inst.gemini_key_var
        start = len(var.trace_info())
        for _ in range(3):
            self._open().destroy()
            self.inst.update()
        self.assertEqual(len(var.trace_info()), start)


def _walk(root):
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        stack.extend(w.winfo_children())


if __name__ == "__main__":
    unittest.main()
