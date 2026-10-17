"""Runs scripts/ui_audit.py on the real app (both themes, three styles, every
view, Settings tabs, project picker, error dialog) and requires zero findings:
no unreadable text (WCAG 4.5:1 / 3:1 large), no clipped labels, no controls past
the window edge, no font sizes off the design scale, no placeholder text."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class UiAudit(unittest.TestCase):
    def test_no_findings_on_any_screen(self):
        out = Path(tempfile.mkdtemp()) / "audit.json"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ui_audit.py"), "--sizes", "1100x700", "--themes", "dark,light",
             "--styles", "Normal video,Hybrid Map,StarMap", "--dialogs", "--json", str(out)],
            cwd=ROOT, capture_output=True, text=True, timeout=900,
        )
        if not out.is_file():
            if "TclError" in proc.stderr and "display" in proc.stderr.lower():
                self.skipTest("no display")
            self.fail(f"audit did not run:\n{proc.stderr[-3000:]}")
        summary = json.loads(out.read_text(encoding="utf-8"))["summary"]
        self.assertGreater(summary["screens"], 80)
        self.assertEqual(summary["errors"], {})
        self.assertEqual(summary["totals"], {}, json.dumps(summary["examples"], indent=1)[:4000])


if __name__ == "__main__":
    unittest.main()
