"""Voxel Map is wired in as a style: the picker lists it under Maps, app.py routes its buttons, and the runner checks and plans a
story without a GPU or a download."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "voxelmap-engine" / "samples" / "border_war_1979.csv"


def _runner():
    spec = importlib.util.spec_from_file_location("vme_runner_test", ROOT / "voxelmap-engine" / "runner.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VoxelMapWiring(unittest.TestCase):
    def test_picker_lists_it_under_maps(self):
        from ui import style_registry as R
        self.assertIn("Voxel Map", dict(R.grouped(R.with_extras(("Normal video",)))).get("Maps", []))
        self.assertIn("Voxel Map", R.EXTRA_BLURBS)
        self.assertIn("Voxel Map", R.EXTRA_CARDS)

    def test_app_routes_the_style(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for needle in ('_vm_section.activate(self)', '_vm_section.deactivate(self)', '_vm_section.cta(self, action)',
                       '_vm_section.sync_cta(self)', '"_vm_running"', 'return "Voxel Map"', '"vm_generate", "vm_render", "vm_cancel"'):
            self.assertIn(needle, src)
        self.assertIn('"Voxel Map"', (ROOT / "ui" / "style_kit.py").read_text(encoding="utf-8"))

    def test_nothing_starts_on_pick(self):
        src = (ROOT / "ui" / "voxelmap_section.py").read_text(encoding="utf-8")
        browse = src.split("def _browse")[1].split("def activate")[0]
        self.assertNotIn("_runner()", browse)
        self.assertNotIn("vm.", browse)

    def test_downloads_only_after_asking(self):
        src = (ROOT / "ui" / "voxelmap_section.py").read_text(encoding="utf-8")
        self.assertRegex(src, r"askyesno\(\"Download close-up terrain\?\"")
        self.assertEqual(len(re.findall(r"vm\.prepare\(", src)), 1)
        self.assertIn("if prepare:", src)


class VoxelMapRunner(unittest.TestCase):
    def test_check_and_plan_sample_without_a_gpu(self):
        r = _runner()
        c = r.check(str(SAMPLE))
        unbuilt = [e for e in c["errors"] if "is not built" in e]
        if unbuilt and len(unbuilt) == len(c["errors"]):
            # Built worlds are generated data (voxelmap-engine/worlds/ is git-ignored, ~80 MB), so a fresh checkout such as CI
            # has none: the check must say so clearly, and planning needs one.
            self.assertTrue(all("tools/build_world.py" in e for e in unbuilt), unbuilt)
            self.skipTest(f"no built voxel world on this machine: {unbuilt[0]}")
        self.assertEqual(c["errors"], [])
        self.assertGreater(c["duration_s"], 10)
        with tempfile.TemporaryDirectory() as d:
            p = r.plan(str(SAMPLE), d)
            self.assertFalse(p["voiceTimed"])
            tl = json.loads((Path(d) / "timeline.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(tl["duration"], p["duration"], places=1)

    def test_render_needs_a_plan_first(self):
        r = _runner()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                r.render(str(SAMPLE), d, output=str(Path(d) / "o.mp4"))


if __name__ == "__main__":
    unittest.main()
