"""Redesign safety net: the real app, off screen, must still have everything test_fixtures/ui_workflow_baseline.json recorded -
every nav page, every style (same main-button action, nothing started on pick, every button callback on its page), every page's
button callbacks, and every app attribute holding a Tk variable or widget (what saved settings, handlers and tests bind to).

Adding is fine; losing anything fails. After an intended change, rewrite the baseline:
    python scripts/ui_workflow_snapshot.py --update
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))


class UiWorkflowSmoke(unittest.TestCase):
    def test_lost_detector(self):
        import ui_workflow_snapshot as S

        base = {"views": ["a"], "vars": ["_v"], "widgets": ["_w"], "pages": {"a": {"X.go": "Go"}},
                "styles": {"S": {"cta": "generate", "running": [], "buttons": {"X.gen": "Generate"}}}}
        self.assertEqual(S.lost(base, json.loads(json.dumps(base))), {})
        cur = json.loads(json.dumps(base))
        cur["views"] = []
        cur["styles"]["S"]["cta"] = "picker"
        cur["styles"]["S"]["running"] = ["_s_running"]
        cur["styles"]["S"]["buttons"] = {"X.gen": "Make", "X.new": "New"}   # text change and an added button are fine
        got = S.lost(base, cur)
        self.assertEqual(got["views"], ["a"])
        self.assertEqual(len(got["style:S"]), 2)

    def test_nothing_lost_against_baseline(self):
        baseline = ROOT / "test_fixtures" / "ui_workflow_baseline.json"
        self.assertTrue(baseline.is_file(), "run: python scripts/ui_workflow_snapshot.py --update")
        out = Path(tempfile.mkdtemp()) / "snap.json"
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "ui_workflow_snapshot.py"), "--json", str(out)],
                              cwd=ROOT, capture_output=True, text=True, timeout=1500)
        if not out.is_file():
            if "TclError" in proc.stderr and "display" in proc.stderr.lower():
                self.skipTest("no display")
            self.fail(f"snapshot did not run:\n{proc.stderr[-3000:]}")
        import ui_workflow_snapshot as S

        gone = S.lost(json.loads(baseline.read_text(encoding="utf-8")), json.loads(out.read_text(encoding="utf-8")))
        self.assertEqual(gone, {}, json.dumps(gone, indent=1)[:6000])


if __name__ == "__main__":
    unittest.main()
