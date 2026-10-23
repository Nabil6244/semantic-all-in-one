"""Phase 8 hardening tests (no application code is touched): what ships in the packaged app, a run from a copy that holds only the shipped Explainer files, the one setting the
application passes in, and the properties of the proposed app.py / spec patch (docs/explainer/m4_app_patch.diff), checked on scratch copies, never on the real files.
Offline and deterministic. usage: python3 -B explainer/spike/test_phase8_hardening.py   (from the repository root)"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
PATCH = Path(os.environ.get("EXPLAINER_PATCH") or ROOT / "docs" / "explainer" / "m4_app_patch.diff")      # EXPLAINER_PATCH: check another copy of the diff
SCRIPT = ("The farmers worked the fields from the early morning until the evening. Every family in the village depended on the harvest. "
          "When the rains failed the people of the village went hungry. The king sent grain from the cities to the farmers. "
          "Trade across the harbour brought new ships every season. By the end of the year the village was richer than before.")


def words_for(script):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_director_real_material import synth
    return synth(script)


class Packaging(unittest.TestCase):
    def test_every_asset_folder_and_file_ships(self):
        from explainer import packaging as PK
        asset_dirs = sorted(p.name for p in (ROOT / "explainer" / "assets").iterdir() if p.is_dir())
        self.assertEqual(sorted(d.split("/")[1] for d in PK.DATA_DIRS), asset_dirs)
        shipped = {Path(src).name for src, _dst in PK.data_files(ROOT)}
        for d in asset_dirs:
            for f in (ROOT / "explainer" / "assets" / d).glob("*"):
                if f.is_file():
                    self.assertIn(f.name, shipped, f"{d}/{f.name} would be missing from the packaged app")
        self.assertIn("manifest.json", shipped)

    def test_every_module_is_named_and_the_verification_scripts_are_not(self):
        from explainer import packaging as PK
        mods = set(PK.python_modules(ROOT))
        for need in ("explainer.cartoon.kit", "explainer.beats.framing", "explainer.director.compose_cartoon", "explainer.director.compose_ref", "explainer.integration", "explainer.narrator.rig"):
            self.assertIn(need, mods)
        self.assertFalse([m for m in mods if ".spike" in m])
        on_disk = {".".join(p.relative_to(ROOT).with_suffix("").parts[:-1] if p.name == "__init__.py" else p.relative_to(ROOT).with_suffix("").parts) for p in (ROOT / "explainer").rglob("*.py") if "spike" not in p.parts}
        self.assertEqual(sorted(on_disk - mods), [])


class Settings(unittest.TestCase):
    def test_the_cartoon_share_setting_is_clamped_and_never_raises(self):
        from explainer.integration import cartoon_share as cs
        self.assertEqual([cs(None), cs({}), cs({"explainer_cartoon_share": None}), cs({"explainer_cartoon_share": "0.3"}), cs({"explainer_cartoon_share": -2}), cs({"explainer_cartoon_share": 9}),
                          cs({"explainer_cartoon_share": "x"}), cs({"explainer_cartoon_share": [1]}), cs({"explainer_cartoon_share": float("nan")}), cs("not a dict")], [0.0, 0.0, 0.0, 0.3, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0])

    def test_direct_plan_never_raises_and_reports_why(self):
        from explainer.integration import direct_plan
        with tempfile.TemporaryDirectory() as d:
            for words, script in (([], None), ([("a", 0.0, 0.1)], ""), ([("x", "bad", 0.2)], None), ([("go", 1.0, 0.5)], "Go.")):
                out = direct_plan(words, script, {}, work_dir=d)
                self.assertIn("plan", out)
                self.assertIsInstance(out["problems"], list)
                if out["plan"] is None:
                    self.assertTrue(out["problems"])

    def test_without_the_setting_the_plan_is_the_directors_default(self):
        from explainer.director import DirectorOptions, direct
        from explainer.integration import direct_plan
        words, dur = words_for(SCRIPT)
        with tempfile.TemporaryDirectory() as d:
            a = direct_plan(words, SCRIPT, {"explainer_style": False, "unrelated": 1}, work_dir=d, duration=dur)
            b = direct(words, SCRIPT, DirectorOptions(work_dir=d), duration=dur)
            self.assertEqual(json.dumps(a["plan"], sort_keys=True), json.dumps(b.plan, sort_keys=True))
            c = direct_plan(words, SCRIPT, {"explainer_cartoon_share": 0.4}, work_dir=d, duration=dur)
            self.assertIn("cartoon", [x["kind"] for x in c["report"]["selection"]["beats"]])

    def test_paths_with_spaces_and_non_ascii_letters_work(self):
        from explainer.integration import direct_plan
        words, dur = words_for(SCRIPT)
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d) / "My Project é ü" / "hybrid work"
            wd.mkdir(parents=True)
            out = direct_plan(words, SCRIPT, {"explainer_cartoon_share": 0.3}, work_dir=str(wd), duration=dur)
            self.assertIsNotNone(out["plan"], out["problems"])
            for b in out["plan"]["beats"]:
                if b["mode"] == "footage":
                    p = Path(b["footage"]["clips"][0]["asset"])
                    self.assertTrue(p.is_absolute() and p.is_file() and p.stat().st_size > 0, p)


class ShippedFilesOnly(unittest.TestCase):
    def test_a_copy_with_only_the_shipped_explainer_files_directs_and_encodes(self):
        """Packaged-app stand-in: the Explainer package without its verification scripts, tests, fixtures or docs, beside the rest of the repository."""
        from explainer import packaging as PK
        with tempfile.TemporaryDirectory() as d:
            app = Path(d) / "app root"
            for mod in PK.python_modules(ROOT):
                rel = Path(*mod.split("."))
                src = ROOT / (str(rel) + ".py") if (ROOT / (str(rel) + ".py")).is_file() else ROOT / rel / "__init__.py"
                dst = app / (src.relative_to(ROOT))
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            for src, dest in PK.data_files(ROOT):
                (app / dest).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, app / dest / Path(src).name)
            self.assertFalse((app / "explainer" / "spike").exists())
            words, dur = words_for(SCRIPT)
            code = ("import sys, json, pathlib; sys.dont_write_bytecode=True\n"
                    "sys.path.insert(0, %r)\n" % str(app) +
                    "from explainer.integration import direct_plan\n"
                    "import explainer; assert explainer.__file__.startswith(%r), explainer.__file__\n" % str(app) +
                    "words, dur = json.loads(%r)\n" % json.dumps([[list(w) for w in words], dur]) +
                    "out = direct_plan([tuple(w) for w in words], %r, {'explainer_cartoon_share': 0.3}, work_dir=%r, duration=dur)\n" % (SCRIPT, str(Path(d) / "work")) +
                    "clips = [b['footage']['clips'][0]['asset'] for b in (out['plan'] or {'beats': []})['beats'] if b['mode'] == 'footage']\n"
                    "print(json.dumps({'plan': out['plan'] is not None, 'problems': out['problems'], 'clips': len(clips), 'sizes': [pathlib.Path(c).stat().st_size for c in clips]}))\n")
            env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")      # the repository comes after the app copy: the Explainer itself must come from the copy
            r = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(app), env=env, capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            res = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertTrue(res["plan"], res["problems"])
            self.assertGreater(res["clips"], 0)
            self.assertTrue(all(s > 1000 for s in res["sizes"]))


class AppPatch(unittest.TestCase):
    """The proposed app.py / spec change (not applied): checked on scratch copies of HEAD's files."""

    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text()

    def test_it_only_adds_lines_to_app_and_spec(self):
        files = re.findall(r"^\+\+\+ b/(.+)$", self.text, re.M)
        self.assertEqual(sorted(files), ["VideoGenerator.spec", "app.py"])
        removed = [l for l in self.text.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, [])

    def test_it_applies_cleanly_to_head_and_the_result_parses(self):
        with tempfile.TemporaryDirectory() as d:
            for f in ("app.py", "VideoGenerator.spec"):
                (Path(d) / f).write_text(subprocess.run(["git", "show", f"HEAD:{f}"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout)
            r = subprocess.run(["git", "apply", "--unsafe-paths", "--directory", d, str(PATCH)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                r = subprocess.run(["patch", "-p1", "-i", str(PATCH)], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            src = (Path(d) / "app.py").read_text()
            tree = ast.parse(src)
            top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) and "explainer" in ast.dump(n)]
            self.assertEqual(top, [], "app.py must import the Explainer only inside methods")
            ast.parse((Path(d) / "VideoGenerator.spec").read_text())

    def test_every_application_method_it_calls_exists_in_the_real_app(self):
        real = (ROOT / "app.py").read_text()
        added = "\n".join(l[1:] for l in self.text.splitlines() if l.startswith("+") and not l.startswith("+++"))
        called = set(re.findall(r"self\.(_[a-z_]+)\(", added)) - set(re.findall(r"def (_[a-z_]+)\(", added))
        missing = sorted(m for m in called if not re.search(rf"def {m}\(", real) and f"self.{m}" not in real)
        self.assertEqual(missing, [])
        for var in set(re.findall(r"self\.(_hybrid_[a-z_]+)", added)) - {"_hybrid_explainer_var", "_hybrid_explainer_btn", "_hybrid_explainer_direct", "_on_hybrid_explainer_changed"}:
            self.assertIn(var, real)

    def test_the_weather_guard_sees_only_added_lines(self):
        """The guard's own rule on a scratch result: no line of the base commit's app.py or spec removed except the approved ones."""
        manifest = json.loads((ROOT / "test_fixtures" / "weather_protected.json").read_text())
        base = manifest["base_commit"]
        with tempfile.TemporaryDirectory() as d:
            for f in ("app.py", "VideoGenerator.spec"):
                head = subprocess.run(["git", "show", f"HEAD:{f}"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout
                (Path(d) / f).write_text(head)
            subprocess.run(["patch", "-p1", "-i", str(PATCH)], cwd=d, capture_output=True, text=True, check=True)
            for f in ("app.py", "VideoGenerator.spec"):
                old = subprocess.run(["git", "show", f"{base}:{f}"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.splitlines()
                new = (Path(d) / f).read_text().splitlines()
                import difflib
                gone = [l[1:] for l in difflib.unified_diff(old, new, lineterm="", n=0) if l.startswith("-") and not l.startswith("---")]
                approved = set(manifest["approved_removed_lines"].get(f, []))
                self.assertEqual([g for g in gone if g not in approved], [], f)


class FakeTk:
    """Just enough of a Tk variable / widget for the patched handlers."""

    def __init__(self, value=None):
        self.value, self.calls = value, []

    def get(self):
        return self.value

    def set(self, v):
        self.value = v

    def configure(self, **kw):
        self.calls.append(kw)
        self.last = dict(getattr(self, "last", {}), **kw)


class PatchedHandlers(unittest.TestCase):
    """Runs the REAL patched handler source (extracted from a scratch copy of HEAD's app.py with the patch applied) against a fake app object: the Stop path, a failed director, a plan
    the Hybrid model cannot read, and a late worker answer. No window is opened and the real app.py is never imported."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        d = Path(cls.tmp)
        (d / "app.py").write_text(subprocess.run(["git", "show", "HEAD:app.py"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout)
        (d / "VideoGenerator.spec").write_text(subprocess.run(["git", "show", "HEAD:VideoGenerator.spec"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout)
        r = subprocess.run(["patch", "-p1", "-i", str(PATCH)], cwd=str(d), capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        tree = ast.parse((d / "app.py").read_text())
        want = {"_hybrid_explainer_direct", "_hybrid_stop_work", "_on_hybrid_explainer_changed"}
        defs = [n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body if isinstance(n, ast.FunctionDef) and n.name in want]
        assert {n.name for n in defs} == want
        cls.mod_src = ast.Module(body=defs, type_ignores=[])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def make(self, director=None, from_dict=None, switch=True, workers=None):
        import types
        events = types.SimpleNamespace(set_plan=[], errors=[], progress_done=[], log=[], threads=[], after=[])

        class Thread:
            def __init__(self, target=None, daemon=None):
                self.target = target
                events.threads.append(self)

            def start(self):
                pass

        class MB:
            @staticmethod
            def showerror(*a):
                events.errors.append(a)

            @staticmethod
            def showinfo(*a):
                events.errors.append(a)

        g = {"threading": types.SimpleNamespace(Thread=Thread), "messagebox": MB}
        exec(compile(self.mod_src, "patched_app.py", "exec"), g)

        class App:
            pass
        app = App()
        for name in ("_hybrid_explainer_direct", "_hybrid_stop_work", "_on_hybrid_explainer_changed"):
            setattr(App, name, g[name])
        app._hybrid_running = False
        app._hybrid_busy = False
        app._hybrid_work_id = 7
        app._hybrid_explainer_var = FakeTk(switch)
        app._hybrid_explainer_btn = FakeTk()
        app._hybrid_plan_btn = FakeTk()
        app._hybrid_status_var = FakeTk("")
        app._settings = {}
        app.model_var = FakeTk("base")
        app._workspace = types.SimpleNamespace(state_dir="s", hybrid_dir="h")
        app._require_workspace = lambda what: True
        app._current_voiceover_path = lambda: "vo.wav"
        app._vo_script_text = lambda: "a script"
        app._pakmap_get_words = lambda *a: [("a", 0.0, 0.1)]
        app._append_log = lambda m: events.log.append(m)
        app._persist_global_settings = lambda: None
        app.after = lambda ms, fn: events.after.append(fn)
        app._hybrid_progress_start = lambda title, detail="": (setattr(app, "_hybrid_work_id", app._hybrid_work_id + 1) or app._hybrid_work_id)
        app.current_plan = "THE CURRENT PLAN"
        app._hybrid_set_plan = lambda plan, report=None, **kw: (events.set_plan.append(plan), setattr(app, "current_plan", plan))

        def progress_done(work_id, text=""):                 # the real one: only the newest work id counts, and it retires the id
            if work_id != app._hybrid_work_id:
                return
            app._hybrid_work_id += 1
            events.progress_done.append(text)
        app._hybrid_progress_done = progress_done
        fake_hybrid = types.ModuleType("hybrid.plan")
        fake_hybrid.HybridPlan = types.SimpleNamespace(from_dict=from_dict or (lambda d: types.SimpleNamespace(beats=[1, 2, 3])))
        fake_pm = types.ModuleType("pakmap.app_integration")
        fake_pm.voiceover_duration = lambda p: 10.0
        fake_ex = types.ModuleType("explainer.integration")
        fake_ex.direct_plan = director or (lambda *a, **k: {"plan": {"beats": []}, "problems": [], "warnings": ["w1"], "report": {}})
        mods = {"hybrid.plan": fake_hybrid, "pakmap.app_integration": fake_pm, "explainer.integration": fake_ex}
        return app, events, mods

    def run_worker(self, app, events, mods):
        from unittest import mock
        with mock.patch.dict(sys.modules, mods):
            app._hybrid_explainer_direct()
            for t in events.threads:
                t.target()
            while events.after:
                events.after.pop(0)()

    def test_a_good_plan_is_installed_and_the_button_comes_back(self):
        app, ev, mods = self.make()
        self.run_worker(app, ev, mods)
        self.assertEqual(len(ev.set_plan), 1)
        self.assertEqual(ev.errors, [])
        self.assertFalse(app._hybrid_busy)
        self.assertEqual(app._hybrid_explainer_btn.last, {"state": "normal", "text": "Direct with Explainer"})
        self.assertEqual(len(ev.progress_done), 1)

    def test_a_director_failure_leaves_the_current_plan_and_resets_everything(self):
        app, ev, mods = self.make(director=lambda *a, **k: {"plan": None, "problems": ["no place"], "warnings": [], "report": {}})
        self.run_worker(app, ev, mods)
        self.assertEqual(ev.set_plan, [])
        self.assertEqual(app.current_plan, "THE CURRENT PLAN")
        self.assertEqual(len(ev.errors), 1)
        self.assertIn("unchanged", ev.errors[0][1])
        self.assertEqual(len(ev.progress_done), 1)
        self.assertEqual(app._hybrid_explainer_btn.last, {"state": "normal", "text": "Direct with Explainer"})

    def test_a_director_that_raises_is_handled_like_a_failure(self):
        def boom(*a, **k):
            raise SystemExit(3)
        app, ev, mods = self.make(director=boom)
        self.run_worker(app, ev, mods)
        self.assertEqual(ev.set_plan, [])
        self.assertFalse(app._hybrid_busy)
        self.assertEqual(len(ev.errors), 1)

    def test_a_plan_the_model_cannot_read_closes_the_progress_card_and_keeps_the_plan(self):
        def bad(d):
            raise ValueError("beat b3 has no mode")
        app, ev, mods = self.make(from_dict=bad)
        self.run_worker(app, ev, mods)
        self.assertEqual(ev.set_plan, [])
        self.assertEqual(app.current_plan, "THE CURRENT PLAN")
        self.assertEqual(len(ev.progress_done), 1, "the progress card must be closed")
        self.assertIn("unchanged", ev.progress_done[0])
        self.assertEqual(len(ev.errors), 1)
        self.assertIn("beat b3 has no mode", ev.errors[0][1])
        self.assertFalse(app._hybrid_busy)
        self.assertEqual(app._hybrid_explainer_btn.last, {"state": "normal", "text": "Direct with Explainer"})
        self.assertTrue(any("could not be read" in m for m in ev.log))

    def test_stop_resets_the_button_and_a_late_answer_changes_nothing(self):
        from unittest import mock
        app, ev, mods = self.make()
        with mock.patch.dict(sys.modules, mods):
            app._hybrid_explainer_direct()
            self.assertEqual(app._hybrid_explainer_btn.last["text"], "Directing…")
            self.assertTrue(app._hybrid_busy)
            app._hybrid_stop_work()                                   # the user presses Stop while the director works
            self.assertFalse(app._hybrid_busy)
            self.assertEqual(app._hybrid_explainer_btn.last, {"state": "normal", "text": "Direct with Explainer"})
            before = (list(app._hybrid_explainer_btn.calls), list(ev.errors), list(ev.set_plan), len(ev.progress_done))
            for t in ev.threads:                                      # the worker finishes later and posts its answer
                t.target()
            while ev.after:
                ev.after.pop(0)()
            after = (list(app._hybrid_explainer_btn.calls), list(ev.errors), list(ev.set_plan), len(ev.progress_done))
        self.assertEqual(before, after, "a late worker answer must not re-disable the button, install a plan or show an error")
        self.assertEqual(app.current_plan, "THE CURRENT PLAN")

    def test_stop_respects_the_switch(self):
        app, ev, mods = self.make(switch=False)
        app._hybrid_stop_work()
        self.assertEqual(app._hybrid_explainer_btn.last, {"state": "disabled", "text": "Direct with Explainer"})

    def test_a_second_run_after_stop_is_not_disturbed_by_the_first_ones_late_answer(self):
        from unittest import mock
        app, ev, mods = self.make()
        with mock.patch.dict(sys.modules, mods):
            app._hybrid_explainer_direct()
            first = ev.threads[0]
            app._hybrid_stop_work()
            app._hybrid_explainer_direct()                            # started again
            second = ev.threads[1]
            first.target()
            while ev.after:
                ev.after.pop(0)()
            self.assertEqual(ev.set_plan, [])                         # the stale answer is ignored while the new run is still going
            self.assertEqual(app._hybrid_explainer_btn.last["text"], "Directing…")
            self.assertTrue(app._hybrid_busy)
            second.target()
            while ev.after:
                ev.after.pop(0)()
        self.assertEqual(len(ev.set_plan), 1)
        self.assertEqual(app._hybrid_explainer_btn.last, {"state": "normal", "text": "Direct with Explainer"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
