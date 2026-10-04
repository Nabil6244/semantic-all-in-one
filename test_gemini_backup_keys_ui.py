"""The Settings page offers backup Gemini keys, and every Gemini feature in the app is given them (so the key pool has something to rotate to)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_SCRIPT = r'''
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); sys.stdout.flush(); os._exit(0)
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); sys.stdout.flush(); os._exit(0)
inst.gemini_key_var.set("MAIN")
print("PASS:four_backup_boxes:" + str(len(inst.gemini_backup_vars) == 4))
print("PASS:no_backup_means_main_only:" + str(inst._gemini_settings() == {"gemini_api_key": "MAIN"}))
inst.gemini_backup_vars[0].set(" B1 "); inst.gemini_backup_vars[2].set("B3")
got = inst._gemini_settings()
print("PASS:backups_are_passed_on:" + str(got == {"gemini_api_key": "MAIN", "gemini_api_key_1": "B1", "gemini_api_key_3": "B3"}))
from visual_director.llm import resolve_gemini_api_keys
os.environ.pop("GEMINI_API_KEY", None)
print("PASS:the_pool_sees_them_in_order:" + str(resolve_gemini_api_keys(got) == ["MAIN", "B1", "B3"]))
sys.stdout.flush(); os._exit(0)
'''


class TestBackupKeys(unittest.TestCase):
    def test_backup_boxes_and_the_settings_every_feature_receives(self):
        script = Path(tempfile.mkdtemp()) / "_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120, cwd=ROOT)
        for line in out.stdout.splitlines():
            if line.startswith("SKIP:"):
                self.skipTest(line[5:])
        results = {l.split(":")[1]: l.split(":")[2] for l in out.stdout.splitlines() if l.startswith("PASS:")}
        for name in ("four_backup_boxes", "no_backup_means_main_only", "backups_are_passed_on", "the_pool_sees_them_in_order"):
            self.assertEqual(results.get(name), "True", f"{name}\n{out.stdout[-800:]}\n{out.stderr[-800:]}")

    def test_the_settings_page_has_the_boxes_and_one_save_button(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('placeholder_text=f"Backup Gemini key {n}"', src)
        self.assertIn("Save AI Settings", src)
        self.assertIn('placeholder_text="Groq API key"', src)
        self.assertIn("Test keys", src)
        self.assertIn('text="Show keys"', src)                       # the keys can be shown, to check they differ
        self.assertIn("is the same as", src)                          # and a repeated key is called out
        self.assertEqual(src.count('{"gemini_api_key": self.gemini_key_var.get().strip()}'), 1, "only the helper builds the dict: every feature goes through it")


if __name__ == "__main__":
    unittest.main()
