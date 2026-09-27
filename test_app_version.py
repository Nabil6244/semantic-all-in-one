"""The app version has one source (app_version.py) and every consumer agrees."""

import re
import unittest
from pathlib import Path

from app_version import APP_VERSION
from licensing import generation_tracking

ROOT = Path(__file__).resolve().parent


class TestAppVersion(unittest.TestCase):
    def test_version_is_semver(self):
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")

    def test_windows_installer_matches(self):
        iss = (ROOT / "scripts" / "windows_setup.iss").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'#define MyAppVersion "([^"]+)"', iss).group(1), APP_VERSION)

    def test_macos_bundle_reads_it(self):
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn('"CFBundleShortVersionString": APP_VERSION', spec)
        self.assertIn('"app_version.py"', spec)

    def test_generation_events_record_it(self):
        self.assertEqual(generation_tracking.app_version(), APP_VERSION)


if __name__ == "__main__":
    unittest.main()
