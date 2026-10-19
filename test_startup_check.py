"""The packaged-build startup check (startup_check.py, run by CI on the built app through scripts/check_packaged_startup.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import startup_check

ROOT = Path(__file__).resolve().parent


class StartupCheck(unittest.TestCase):
    def test_source_tree_passes_and_writes_its_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.json"
            code = startup_check.run(str(out), ffmpeg=None)
            data = json.loads(out.read_text(encoding="utf-8"))
        # ffmpeg=None: no finder given, so that one check reports "not found"; everything else must pass from the source tree
        self.assertEqual([f for f in data["failures"] if not f.startswith("ffmpeg")], [])
        self.assertEqual(code, 1)
        self.assertGreater(data["checks"]["gfx_templates"], 0)

    def test_a_missing_module_or_engine_file_fails_the_check(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / startup_check.MODULES_FILE).write_text(json.dumps(["no_such_module_xyz"]), encoding="utf-8")
            orig = startup_check.bundle_root
            startup_check.bundle_root = lambda: root
            try:
                code = startup_check.run(str(root / "r.json"), ffmpeg=lambda: None)
            finally:
                startup_check.bundle_root = orig
            data = json.loads((root / "r.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertTrue(any("no_such_module_xyz" in f for f in data["failures"]))
        self.assertTrue(any(f.startswith("engine files missing") for f in data["failures"]))

    def test_a_listed_file_missing_from_the_bundle_fails_the_check(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / startup_check.FILES_FILE).write_text(json.dumps(["composition_styles/hybrid_beats_prompt_graphics.txt"]), encoding="utf-8")
            orig = startup_check.bundle_root
            startup_check.bundle_root = lambda: root
            try:
                startup_check.run(str(root / "r.json"), ffmpeg=lambda: None)
            finally:
                startup_check.bundle_root = orig
            data = json.loads((root / "r.json").read_text(encoding="utf-8"))
        self.assertTrue(any("hybrid_beats_prompt_graphics.txt" in f and f.startswith("files missing") for f in data["failures"]), data["failures"])

    def test_the_spec_ships_every_prompt_text_in_composition_styles(self):
        import fnmatch

        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        globs = [g for g in ("*_prompt.txt", "*_prompt_*.txt") if f'glob("{g}")' in spec]
        for f in (ROOT / "composition_styles").glob("*.txt"):
            self.assertTrue(any(fnmatch.fnmatch(f.name, g) for g in globs), f"{f.name} is not shipped by VideoGenerator.spec")
        self.assertIn('"startup_check_files.json"', spec)

    def test_every_engine_file_the_check_expects_exists_in_the_source_tree(self):
        for rel in startup_check.ENGINE_FILES:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_app_runs_the_check_before_any_window_and_the_spec_ships_the_module_list(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        main = src[src.index("def main() -> None:"):]
        self.assertLess(main.index("SYT_STARTUP_CHECK"), main.index("VideoGeneratorApp()"))
        self.assertLess(main.index("SYT_STARTUP_CHECK"), main.index("_acquire_single_instance_lock_windows()"))
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn('"startup_check_modules.json"', spec)
        self.assertIn('hiddenimports += ["startup_check"]', spec)

    def test_app_in_check_mode_exits_without_a_window(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.json"
            env = dict(os.environ, SYT_STARTUP_CHECK=str(out))
            r = subprocess.run([sys.executable, str(ROOT / "app.py")], env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=180)
            self.assertTrue(out.is_file(), r.stderr[-2000:])
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(data["checks"]["frozen"])
        self.assertEqual(r.returncode, 0 if data["ok"] else 1)

    def test_runner_reports_a_missing_build_instead_of_crashing(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_packaged_startup.py"), str(ROOT / "no_such_build" / "app.exe")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("built app not found", r.stdout)


if __name__ == "__main__":
    unittest.main()
