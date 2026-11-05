"""Voxel Map: a long terrain download shows its progress, Stop ends it at once, a closed app leaves nothing running, and a project
reopens where it was left. No network, no GPU, no window."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "voxelmap-engine"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _runner_with_fake_engine(folder: Path, script: str):
    """runner.py with `render.mjs` replaced by a Python script and node by this Python."""
    (folder / "render.mjs").write_text(textwrap.dedent(script), encoding="utf-8")
    mod = _load("vme_runner_resume", ENGINE / "runner.py")
    mod.HERE = folder
    mod._binaries = lambda: (sys.executable, "")
    return mod


class RunnerProgressAndStop(unittest.TestCase):
    def test_prepare_shows_download_and_tile_counts(self):
        with tempfile.TemporaryDirectory() as t:
            vm = _runner_with_fake_engine(Path(t), """
                import json
                for ev in ({"event": "fetch", "done": 1, "total": 2}, {"event": "fetch", "done": 2, "total": 2},
                           {"event": "tile", "done": 472, "total": 967}, {"event": "done", "built": 1, "failed": 3, "total": 967}):
                    print(json.dumps(ev), flush=True)
            """)
            seen, logs = [], []
            vm.prepare("story.csv", progress=lambda f, m: seen.append((round(f, 3), m)), log=logs.append)
        msgs = [m for _f, m in seen]
        self.assertIn("Downloading elevation data 2/2", msgs)
        self.assertIn("Building terrain tile 472/967", msgs)
        self.assertEqual([f for f, _m in seen], sorted(f for f, _m in seen))
        self.assertTrue(any("3 terrain tiles" in m for m in logs))

    def test_stop_ends_a_step_that_prints_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            vm = _runner_with_fake_engine(Path(t), "import time; time.sleep(60)")
            began = time.monotonic()
            with self.assertRaises(vm.Cancelled):
                vm.prepare("story.csv", cancel=lambda: time.monotonic() - began > 0.5, log=lambda _m: None)
            self.assertLess(time.monotonic() - began, 10)


class BuildDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ENGINE / "tools"))
        cls.bd = _load("vme_build_detail", ENGINE / "tools" / "build_detail.py")

    WORLD = {"id": "t", "bbox": [-10.0, 0.0, 10.0, 20.0], "res": 0.08}

    def test_missing_elevation_skips_what_is_cached(self):
        with tempfile.TemporaryDirectory() as t:
            cache = Path(t)
            all_names = self.bd.missing_elevation(self.WORLD, [{"level": 1, "tx": 0, "tz": 0}], cache)
            self.assertTrue(all_names)
            z, x, y = all_names[0]
            (cache / str(z) / str(x)).mkdir(parents=True)
            (cache / str(z) / str(x) / f"{y}.png").write_bytes(b"x")
            self.assertEqual(self.bd.missing_elevation(self.WORLD, [{"level": 1, "tx": 0, "tz": 0}], cache), all_names[1:])

    def test_a_few_failed_downloads_do_not_stop_the_rest(self):
        got = []

        def get(z, x, y, _cache):
            if x == 3:
                raise OSError("one bad file")
            got.append(x)

        self.assertTrue(self.bd.download_all([(9, x, 0) for x in range(8)], Path("."), get=get, workers=2))
        self.assertEqual(sorted(got), [0, 1, 2, 4, 5, 6, 7])

    def test_gives_up_when_the_network_is_down(self):
        def get(*_a):
            raise OSError("no network")

        self.assertFalse(self.bd.download_all([(9, x, 0) for x in range(50)], Path("."), get=get, workers=1, give_up_after=5))

    def test_a_bad_tile_is_reported_not_raised(self):
        self.bd._JOB = (self.WORLD, None)
        self.bd.build_tile = lambda *_a: (_ for _ in ()).throw(OSError("bad"))
        args, err = self.bd._build_one((1, 0, 0))
        self.assertEqual(args, (1, 0, 0))
        self.assertIn("OSError", err)

    @unittest.skipIf(os.name == "nt", "a process's parent id does not change on Windows; a closed pipe ends it there")
    def test_ends_when_the_process_that_started_it_is_gone(self):
        with tempfile.TemporaryDirectory() as t:
            pid_file = Path(t) / "pid"
            child = (f"import os, sys, time; sys.path.insert(0, {str(ENGINE / 'tools')!r}); import build_detail as b; b.die_with_parent(); "
                     f"open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)")
            parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(6)"
            p = subprocess.Popen([sys.executable, "-c", parent])
            deadline = time.monotonic() + 30
            while not pid_file.is_file() or not pid_file.read_text():
                self.assertLess(time.monotonic(), deadline, "child never started")
                time.sleep(0.1)
            pid = int(pid_file.read_text())
            p.kill()
            p.wait()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
                if not r or r.startswith("Z"):
                    return
                time.sleep(0.2)
            subprocess.run(["kill", "-9", str(pid)])
            self.fail("the child kept running after its parent died")


class _Var:
    def __init__(self, v=""):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


def _app(state_dir: Path, **kw):
    picked = []
    app = SimpleNamespace(_workspace=SimpleNamespace(state_dir=str(state_dir)), _vm_csv_var=_Var(), _vm_voice_var=_Var(), _vm_res_var=_Var("720p preview (1280x720)"),
                          _vm_status_var=_Var(), _vm_planned=None, _vm_running=False, _vm_active=True, picked=picked,
                          after=lambda _ms, fn: fn(), _on_style_pick=picked.append, **kw)
    return app


class ProjectReopens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ui import voxelmap_section
        cls.s = voxelmap_section

    def _project(self, t):
        root = Path(t)
        csv, work = root / "story.csv", root / "work"
        csv.write_text("row\n", encoding="utf-8")
        work.mkdir()
        (work / "timeline.json").write_text("{}", encoding="utf-8")
        return root / "state", csv, work

    def test_page_files_and_plan_come_back(self):
        with tempfile.TemporaryDirectory() as t:
            state, csv, work = self._project(t)
            a = _app(state)
            a._vm_csv_var.set(str(csv))
            a._vm_res_var.set("1080p final (1920x1080)")
            a._vm_planned = {"csv": str(csv), "voice": "", "res": 1080, "work": str(work), "cards": []}
            self.s._save(a)

            b = _app(state)
            self.s.resume_on_open(b)
            self.assertEqual(b.picked, [self.s.STYLE])
            self.s._restore(b)
            self.assertEqual(b._vm_csv_var.get(), str(csv))
            self.assertEqual(b._vm_res_var.get(), "1080p final (1920x1080)")
            self.assertEqual(b._vm_planned["work"], str(work))
            self.assertIn("Restored", b._vm_status_var.get())

    def test_a_changed_story_needs_generate_again(self):
        with tempfile.TemporaryDirectory() as t:
            state, csv, work = self._project(t)
            a = _app(state)
            a._vm_csv_var.set(str(csv))
            a._vm_planned = {"csv": str(csv), "voice": "", "res": 720, "work": str(work), "cards": []}
            self.s._save(a)
            csv.write_text("row\nchanged\n", encoding="utf-8")
            b = _app(state)
            self.s._restore(b)
            self.assertEqual(b._vm_csv_var.get(), str(csv))
            self.assertIsNone(b._vm_planned)

    def test_closed_during_generate_says_it_carries_on(self):
        with tempfile.TemporaryDirectory() as t:
            state, csv, _work = self._project(t)
            a = _app(state, _vm_generating=True)
            a._vm_csv_var.set(str(csv))
            self.s._save(a)
            b = _app(state)
            self.s._restore(b)
            self.assertIn("carries on", b._vm_status_var.get())
            self.assertFalse(json.loads((state / "voxel_map" / "settings.json").read_text(encoding="utf-8")).get("planned"))

    def test_leaving_the_page_by_choice_is_remembered_but_opening_a_project_is_not(self):
        with tempfile.TemporaryDirectory() as t:
            state, _csv, _work = self._project(t)
            a = _app(state)
            self.s._save(a)
            self.s.deactivate(a, remember=False)      # another project opening
            b = _app(state)
            self.s.resume_on_open(b)
            self.assertEqual(b.picked, [self.s.STYLE])
            c = _app(state)
            self.s.deactivate(c)                      # another style picked
            d = _app(state)
            self.s.resume_on_open(d)
            self.assertEqual(d.picked, [])

    def test_nothing_starts_on_open(self):
        src = (ROOT / "ui" / "voxelmap_section.py").read_text(encoding="utf-8")
        for fn in ("def _save", "def _restore", "def resume_on_open"):
            body = src.split(fn)[1].split("\ndef ")[0]
            for start in ("on_generate", "on_render", "_start(", "auto_render.start", "_runner("):
                self.assertNotIn(start, body)


if __name__ == "__main__":
    unittest.main()
