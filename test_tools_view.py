"""The Tools page: one sidebar entry for the tools that were only in the overflow menu. Every card calls a real app method."""
import os
import unittest
from unittest import mock


class ToolCardsContract(unittest.TestCase):
    def test_every_card_calls_an_existing_app_method(self):
        import app
        from ui.views import TOOL_CARDS

        cls = next(v for v in vars(app).values() if isinstance(v, type) and hasattr(v, "_open_workspace_overflow"))
        for title, _blurb, _label, method in TOOL_CARDS:
            self.assertTrue(callable(getattr(cls, method, None)), f"{title}: {method} is not an app method")

    def test_overflow_menu_still_offers_the_same_tools(self):
        with open(os.path.join(os.path.dirname(__file__), "app.py"), encoding="utf-8") as fh:
            src = fh.read()
        for method in ("_open_rating_history", "_open_csv_generator", "_open_learning", "_toggle_activity_log"):
            self.assertIn(f"command=self.{method}", src)

    def test_nav_has_tools_and_keeps_about_last(self):
        from ui import theme as T
        import app

        keys = [k for k, _l, _g in T.NAV_ITEMS]
        self.assertIn("tools", keys)
        self.assertEqual(keys[-2:], ["qa", "about"])
        self.assertIn("tools", T.NAV_ICONS)
        self.assertEqual(app._LAZY_VIEWS["tools"], "ToolsView")


@unittest.skipUnless(os.environ.get("DISPLAY") or os.name == "nt" or os.uname().sysname == "Darwin", "needs a display")
class ToolsViewBuild(unittest.TestCase):
    def test_builds_and_runs_the_app_method(self):
        import customtkinter as ctk
        from ui.views import TOOL_CARDS, ToolsView

        try:
            root = ctk.CTk()
        except Exception as exc:   # no display available
            self.skipTest(str(exc))
        try:
            fake = mock.Mock(spec=[m for *_x, m in TOOL_CARDS])
            view = ToolsView(root, fake)
            view.on_show()
            self.assertEqual(set(view._buttons), {m for *_x, m in TOOL_CARDS})
            view._buttons["_open_csv_generator"].invoke()
            fake._open_csv_generator.assert_called_once_with()
            # a build without one of the tools: its button is disabled, not dead
            partial = mock.Mock(spec=["_open_settings"])
            view2 = ToolsView(root, partial)
            view2.on_show()
            self.assertEqual(view2._buttons["_open_learning"].cget("state"), "disabled")
            self.assertEqual(view2._buttons["_open_settings"].cget("state"), "normal")
        finally:
            root.destroy()


class SidebarFitsSmallestWindow(unittest.TestCase):
    """Adding the Tools entry first pushed "About" 3 px past the sidebar at 1100x700 and hid the version label."""

    def test_last_item_and_version_fit_at_1100x700(self):
        import shutil
        import sys
        import tempfile
        from pathlib import Path

        root = Path(__file__).resolve().parent
        sys.path.insert(0, str(root / "scripts"))
        import ui_audit

        settings = root / "settings.json"
        backup = Path(tempfile.mkdtemp()) / "settings.json"
        had = settings.is_file()
        if had:
            shutil.copy2(settings, backup)
        try:
            try:
                _mod, inst = ui_audit.build_app()
            except Exception as exc:
                self.skipTest(f"app cannot be built here: {exc}")
            try:
                inst.geometry("1100x700+20+20")
                for _ in range(5):
                    inst.update()
                side = inst._shell.sidebar
                bottom = side.winfo_rooty() + side.winfo_height()
                last = inst._shell._nav_btns["about"]
                self.assertLessEqual(last.winfo_rooty() + last.winfo_height(), bottom)
                v = inst._shell.version_label
                self.assertLessEqual(v.winfo_rooty() + v.winfo_height(), bottom)
            finally:
                inst.destroy()
        finally:
            if had:
                shutil.copy2(backup, settings)


if __name__ == "__main__":
    unittest.main()
