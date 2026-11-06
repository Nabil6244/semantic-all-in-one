"""The installed app carries the engines it loads by path (Roblox Cinema, Voxel Map, Kids Learn), their music and three.js add-ons, and runs
their Python tool scripts without a Python on the machine. Before this, the Windows app showed "Roblox Cinema is not installed"."""
import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import engine_packaging as E
import script_runner

ROOT = Path(__file__).resolve().parent


class Shipped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = E.data_files(ROOT)
        cls.dest = {f"{d}/{Path(s).name}" for s, d in cls.files}

    def test_every_engine_ships_its_runner_and_renderer(self):
        for eng, need in (("roblox-cinema-engine", ("runner.py", "render.mjs", "tools/mix_audio.py", "tools/narration_timing.py")),
                          ("voxelmap-engine", ("runner.py", "render.mjs", "page.html", "page.js", "tools/mix_audio.py")),
                          ("cartoon3d-engine", ("runner.py", "lesson.mjs", "assets/host/host.glb")),
                          ("citygrow-engine", ("runner.py", "render.mjs", "page.html", "page.js", "lib/timeline.mjs", "tools/music_bed.py", "tools/build_city.py",
                                               "samples/rome_timelapse.csv"))):
            for rel in need:
                self.assertIn(f"{eng}/{rel}", self.dest, f"{eng}/{rel} is not shipped")

    def test_the_csv_prompt_the_copy_button_reads_is_shipped(self):
        self.assertIn("citygrow-engine/tools/story_prompt.md", self.dest)

    def test_no_tests_outputs_or_build_folders(self):
        for s, d in self.files:
            self.assertFalse(set(d.split("/")) & (E.SKIP_DIRS - {"node_modules"}), d)
            self.assertTrue(Path(s).is_file(), s)

    def test_every_module_a_shipped_page_or_script_imports_is_shipped(self):
        for s, d in self.files:
            if not s.endswith((".mjs", ".js")) or "node_modules" in d:
                continue
            for rel in re.findall(r"""from\s+['"](\.{1,2}/[^'"]+)['"]""", Path(s).read_text(encoding="utf-8", errors="replace")):
                target = (ROOT / d / rel).resolve().relative_to(ROOT).as_posix()
                self.assertIn(target, self.dest, f"{d}/{Path(s).name} imports {rel}, which is not shipped")

    def test_music_rules_horror_and_three_addons(self):
        self.assertIn("assets/music/lost_frontier.opus", self.dest)
        self.assertIn("rules_horror/prompt.txt", self.dest)
        self.assertIn("starmap-engine/node_modules/three/examples/jsm/objects/Reflector.js", self.dest)

    def test_the_build_list_uses_it(self):
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn("datas += engine_data_files_new(ROOT)", spec)
        self.assertIn("hiddenimports += engine_hidden_new", spec)


class ScriptsWithoutPython(unittest.TestCase):
    def test_installed_app_runs_the_script_in_process(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "helper_mod.py").write_text("VALUE = 7\n", encoding="utf-8")
            script = Path(d) / "tool.py"
            script.write_text(textwrap.dedent("""
                import sys, helper_mod
                print("args", sys.argv[1:], helper_mod.VALUE)
                sys.exit(3 if sys.argv[1] == "fail" else 0)
            """), encoding="utf-8")
            argv, path = sys.argv[:], sys.path[:]
            with mock.patch.object(sys, "frozen", True, create=True):
                rc, out = script_runner.run_script(script, ["ok", 5])
                self.assertEqual(rc, 0, out)
                self.assertIn("args ['ok', '5'] 7", out)
                rc, out = script_runner.run_script(script, ["fail"])
                self.assertEqual(rc, 3)
            self.assertEqual((sys.argv, sys.path), (argv, path))     # nothing leaks into the app

    def test_from_source_a_child_python_runs_it(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "tool.py"
            script.write_text("import sys; print('child', sys.argv[1]); sys.exit(2)\n", encoding="utf-8")
            rc, out = script_runner.run_script(script, ["x"])
            self.assertEqual((rc, "child x" in out), (2, True))


if __name__ == "__main__":
    unittest.main()
