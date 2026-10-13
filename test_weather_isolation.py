"""Weather must not change any existing style. The guard:

  1. every protected file (test_fixtures/weather_protected.json: pakMap, Hybrid, StarMap, the map engines, map_scene, the CSV
     prompts, the providers, Flow, the asset manager, the generator) still hashes as recorded at the base commit;
  2. no new file appeared inside a protected folder (Weather's code lives in weather/ and weather-engine/ only);
  3. app.py and VideoGenerator.spec: no line of theirs was removed or changed, except lines approved in the manifest (phase 1B
     may only ADD lines);
  4. no existing module imports Weather: until the app wiring (phase 1B), the app cannot reach Weather at all.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from enoch_template_testutil import normalized_sha256

ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT / "test_fixtures" / "weather_protected.json").read_text(encoding="utf-8"))
WEATHER_OWN = ("weather/", "weather-engine/", "test_weather_", "docs/weather/", "test_fixtures/weather_protected.json")


def git(*args: str) -> "str | None":
    if not shutil.which("git") or not (ROOT / ".git").exists():
        return None
    r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else None


class ProtectedFiles(unittest.TestCase):
    def test_nothing_protected_changed_or_disappeared(self):
        changed, missing = [], []
        for rel, sha in MANIFEST["files"].items():
            p = ROOT / rel
            if not p.is_file():
                missing.append(rel)
            elif normalized_sha256(p) != sha:
                changed.append(rel)
        self.assertEqual((changed, missing), ([], []),
                         "protected files differ from test_fixtures/weather_protected.json: Weather must not change existing styles")

    def test_no_new_file_inside_a_protected_folder(self):
        tracked = git("ls-files", "--", *MANIFEST["protected_paths"])
        untracked = git("ls-files", "--others", "--exclude-standard", "--", *MANIFEST["protected_paths"])
        if tracked is None or untracked is None:
            self.skipTest("git is not available")
        now = {f for f in (tracked + untracked).split("\n") if f and "/node_modules/" not in f}
        self.assertEqual(sorted(now - set(MANIFEST["files"])), [], "new files belong in weather/ or weather-engine/, not in a protected folder")


class SharedFilesOnlyGrow(unittest.TestCase):
    def test_app_and_spec_lose_no_line_except_the_approved_ones(self):
        base = MANIFEST["base_commit"]
        for name, approved in MANIFEST["approved_removed_lines"].items():
            diff = git("diff", "--no-color", "-U0", base, "--", name)
            if diff is None:
                self.skipTest("git is not available")
            removed = [ln[1:] for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---")]
            unexpected = [ln for ln in removed if ln not in approved]
            self.assertEqual(unexpected, [], f"{name}: these lines were removed or changed, and only additions are allowed")


class NothingReachesWeather(unittest.TestCase):
    def test_no_existing_module_imports_weather(self):
        files = git("ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py")
        if files is None:
            self.skipTest("git is not available")
        pattern = re.compile(r"^\s*(from\s+weather(\.|\s)|import\s+weather\b)", re.M)
        hits = []
        for rel in files.split("\n"):
            if not rel or rel.startswith(WEATHER_OWN) or "/node_modules/" in rel:
                continue
            try:
                text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if pattern.search(text):
                hits.append(rel)
        approved = set(MANIFEST.get("approved_importers", []))
        self.assertEqual(sorted(set(hits) - approved), [], "only the approved app wiring (phase 1B) may import Weather")


if __name__ == "__main__":
    unittest.main()
