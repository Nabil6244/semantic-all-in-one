"""Phase 2: the daily 5:30 AM Central prep as OS task TEXT (nothing is installed here), and the due / catch-up rule."""

import ast
import plistlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from weather.automation import schedule as sch

UTC = timezone.utc
CMD = ["/usr/bin/python3", "-m", "weather.automation", "due", "--root", "/Users/me/Weather Forecasts", "--contact", "me@example.com", "--notify"]


class TaskText(unittest.TestCase):
    def test_the_launchd_plist_is_valid_and_wakes_every_15_minutes(self):
        p = plistlib.loads(sch.launchd_plist(CMD, "/app", "/Users/me/Weather Forecasts/prep.log").encode("utf-8"))
        self.assertEqual(p["Label"], sch.LABEL)
        self.assertEqual(p["ProgramArguments"], CMD)
        self.assertEqual(p["StartInterval"], 900)
        self.assertTrue(p["RunAtLoad"])
        self.assertEqual(p["WorkingDirectory"], "/app")

    def test_the_windows_task_xml_is_valid_and_repeats_every_15_minutes_all_day(self):
        root = ET.fromstring(sch.windows_task_xml(CMD, r"C:\App").replace('encoding="UTF-16"', ""))
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(root.find(".//t:Repetition/t:Interval", ns).text, "PT15M")
        self.assertEqual(root.find(".//t:Exec/t:Command", ns).text, CMD[0])
        self.assertIn('"/Users/me/Weather Forecasts"', root.find(".//t:Exec/t:Arguments", ns).text)
        self.assertEqual(root.find(".//t:StartWhenAvailable", ns).text, "true")
        create, delete = sch.windows_commands(r"C:\x.xml")
        self.assertEqual(create[:2], ["schtasks", "/Create"])
        self.assertEqual(delete[:2], ["schtasks", "/Delete"])

    def test_the_default_command_runs_the_due_check_with_this_python(self):
        cmd = sch.command("/tmp/wx", "me@example.com")
        self.assertEqual(cmd[1:5], ["-m", "weather.automation", "due", "--root"])

    def test_nothing_here_installs_a_task(self):
        """install()/uninstall() exist for the app's switch; the only callers are the app and the user (no module calls them)."""
        for f in Path(sch.__file__).parent.glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree) if isinstance(n, ast.Call)}
            self.assertFalse({"install", "uninstall"} & calls, f.name)


class Due(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_due_from_530_central_until_today_is_prepared(self):
        before = datetime(2026, 10, 13, 10, 29, tzinfo=UTC)    # 5:29 AM CDT
        after = datetime(2026, 10, 13, 10, 30, tzinfo=UTC)     # 5:30 AM CDT
        self.assertFalse(sch.is_due(self.root, before))
        self.assertTrue(sch.is_due(self.root, after))
        (self.root / "2026-10-13").mkdir()
        (self.root / "2026-10-13" / "prep.json").write_text("{}")
        self.assertFalse(sch.is_due(self.root, after))
        self.assertTrue(sch.is_due(self.root, datetime(2026, 10, 14, 11, 0, tzinfo=UTC)))   # the next day

    def test_central_time_moves_with_daylight_saving(self):
        self.assertTrue(sch.is_due(self.root, datetime(2026, 12, 1, 11, 30, tzinfo=UTC)))    # 5:30 AM CST
        self.assertFalse(sch.is_due(self.root, datetime(2026, 12, 1, 10, 30, tzinfo=UTC)))   # 4:30 AM CST

    def test_the_catch_up_offer_when_the_app_opens_late(self):
        msg = sch.catch_up_offer(self.root, datetime(2026, 10, 13, 14, 0, tzinfo=UTC))
        self.assertIn("Tuesday, October 13", msg)
        self.assertIn("5:30 AM Central", msg)
        self.assertIsNone(sch.catch_up_offer(self.root, datetime(2026, 10, 13, 9, 0, tzinfo=UTC)))


if __name__ == "__main__":
    unittest.main()
