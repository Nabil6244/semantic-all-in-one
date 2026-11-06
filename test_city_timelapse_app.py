"""City Timelapse is wired in as a style: the picker lists it under Maps, app.py routes its buttons (additions only), nothing
starts on a file pick, and a world download only happens after the user agrees."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class CityTimelapseWiring(unittest.TestCase):
    def test_picker_lists_it_under_maps(self):
        from ui import style_registry as R
        self.assertIn("City Timelapse", dict(R.grouped(R.with_extras(("Normal video",)))).get("Maps", []))
        self.assertIn("City Timelapse", R.EXTRA_BLURBS)
        self.assertIn("City Timelapse", R.EXTRA_CARDS)

    def test_app_routes_the_style(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for needle in ("from ui import city_timelapse_section as _ct_section", "_ct_section.activate(self)", "_ct_section.deactivate(self)",
                       "_ct_section.cta(self, action)", "_ct_section.sync_cta(self)", '"_ct_running"', 'return "City Timelapse"',
                       '"ct_generate", "ct_render", "ct_cancel"', "_ct_section.resume_on_open(self)", 'ct_block.grid() if active == "City Timelapse"'):
            self.assertIn(needle, src)
        self.assertIn('"City Timelapse"', (ROOT / "ui" / "style_kit.py").read_text(encoding="utf-8"))

    def test_nothing_starts_on_pick(self):
        src = (ROOT / "ui" / "city_timelapse_section.py").read_text(encoding="utf-8")
        browse = src.split("def _browse")[1].split("def copy_csv_prompt")[0]
        self.assertNotIn("_runner()", browse)
        self.assertNotIn("ct.", browse)

    def test_world_download_only_after_asking(self):
        src = (ROOT / "ui" / "city_timelapse_section.py").read_text(encoding="utf-8")
        self.assertRegex(src, r'askyesno\("Build the city\'s world\?"')
        self.assertEqual(len(re.findall(r"ct\.build_world\(", src)), 1)
        ask = src.index("askyesno(\"Build the city's world?\""); build = src.index("ct.build_world(")
        self.assertLess(ask, build)

    def test_no_gemini(self):
        for f in [ROOT / "ui" / "city_timelapse_section.py", *sorted((ROOT / "citygrow-engine").rglob("*.py")), *sorted((ROOT / "citygrow-engine").rglob("*.mjs"))]:
            if "node_modules" in f.parts:
                continue
            self.assertNotRegex(f.read_text(encoding="utf-8"), r"(?i)(import\s+\S*(gemini|genai))|from\s+\S*(gemini|genai)|generativeai|gemini_client", f.name)

    def test_app_py_lines_only_added(self):
        try:
            diff = subprocess.run(["git", "diff", "HEAD", "--", "app.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except Exception:  # noqa: BLE001
            self.skipTest("no git")
        removed = [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, [], "City Timelapse only adds lines to app.py")


if __name__ == "__main__":
    unittest.main()
