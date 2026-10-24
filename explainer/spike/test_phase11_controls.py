"""Phase 11 tests: patch v2 (docs/explainer/m4_app_patch_v2.diff), the on-screen controls for the Explainer options (footage share and source, background, narrator).
Checked on scratch copies of the CURRENT app.py (which already holds patch v1); the real app.py and spec are never modified. Offline, no window.
usage: python3 -B explainer/spike/test_phase11_controls.py   (from the repository root)"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
PATCH = Path(os.environ.get("EXPLAINER_PATCH_V2") or ROOT / "docs" / "explainer" / "m4_app_patch_v2.diff")


class FakeTk:
    def __init__(self, value=None):
        self.value, self.calls = value, []

    def get(self):
        return self.value

    def set(self, v):
        self.value = v

    def configure(self, **kw):
        self.calls.append(kw)
        self.last = dict(getattr(self, "last", {}), **kw)


APPLIED = "explainer.ui_options" in (ROOT / "app.py").read_text()          # patch v2 is already in the working tree's app.py (the tests hold in both states)


def scratch_app(d):
    """A scratch copy of the app.py WITHOUT patch v2 (taken out of the working tree's file when it is already applied), and the patch applied to it there."""
    shutil.copy(ROOT / "app.py", Path(d) / "app.py")
    if APPLIED:
        subprocess.run(["patch", "-R", "-p1", "-s", "-i", str(PATCH)], cwd=str(d), capture_output=True, text=True, check=True)
    return subprocess.run(["patch", "-p1", "-s", "-i", str(PATCH)], cwd=str(d), capture_output=True, text=True)


class PatchShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text()

    def test_it_only_adds_lines_to_app_py(self):
        self.assertEqual(sorted(re.findall(r"^\+\+\+ b/(.+)$", self.text, re.M)), ["app.py"])
        self.assertEqual([l for l in self.text.splitlines() if l.startswith("-") and not l.startswith("---")], [])

    def test_it_applies_to_the_working_tree_without_touching_it(self):
        r = subprocess.run(["git", "apply"] + (["--reverse"] if APPLIED else []) + ["--check", str(PATCH)], cwd=str(ROOT), capture_output=True, text=True)       # applied: it reverses cleanly
        self.assertEqual(r.returncode, 0, r.stderr)
        n = subprocess.run(["git", "apply", "--numstat", str(PATCH)], cwd=str(ROOT), capture_output=True, text=True).stdout.split()
        self.assertEqual(n[1], "0")
        self.assertEqual(int(n[0]), 4)          # two calls into explainer/ui_options.py, nothing more

    def test_the_scratch_result_compiles_and_the_app_still_imports_the_explainer_only_inside_methods(self):
        with tempfile.TemporaryDirectory() as d:
            r = scratch_app(d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            tree = ast.parse((Path(d) / "app.py").read_text())
            self.assertEqual([n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) and "explainer" in ast.dump(n)], [])
            subprocess.run([sys.executable, "-B", "-m", "py_compile", str(Path(d) / "app.py")], check=True)

    def test_the_weather_guard_rule_still_holds_on_the_scratch_result(self):
        """The guard's own rule and command (git diff -U0 against the base commit): no line removed except the approved ones."""
        manifest = json.loads((ROOT / "test_fixtures" / "weather_protected.json").read_text())
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(scratch_app(d).returncode, 0)
            (Path(d) / "base_app.py").write_text(subprocess.run(["git", "show", f"{manifest['base_commit']}:app.py"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout)
            out = subprocess.run(["git", "diff", "--no-index", "--no-color", "-U0", "base_app.py", "app.py"], cwd=d, capture_output=True, text=True).stdout
        gone = [l[1:] for l in out.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertEqual([g for g in gone if g not in set(manifest["approved_removed_lines"].get("app.py", []))], [])

    def test_the_real_app_holds_either_no_patch_v2_or_exactly_its_four_lines(self):
        text = (ROOT / "app.py").read_text()
        self.assertEqual(text.count("explainer.ui_options"), 2 if APPLIED else 0)


class FakeCtk:
    """A stand-in for customtkinter that records what install() builds."""

    def __init__(self):
        self.menus, self.labels, self.frames = [], [], []
        outer = self

        class StringVar(FakeTk):
            def __init__(self, value=""):
                super().__init__(value)

        class Frame:
            def __init__(self, master, **kw):
                self.kw, self.grid_kw = kw, None
                outer.frames.append(self)

            def grid(self, **kw):
                self.grid_kw = kw

        class Label:
            def __init__(self, master, **kw):
                self.kw = kw
                outer.labels.append(self)

            def grid(self, **kw):
                self.grid_kw = kw

        class Menu(FakeTk):
            def __init__(self, master, **kw):
                super().__init__()
                self.kw, self.grid_kw = kw, None
                outer.menus.append(self)

            def grid(self, **kw):
                self.grid_kw = kw

        self.StringVar, self.CTkFrame, self.CTkLabel, self.CTkOptionMenu = StringVar, Frame, Label, Menu
        self.CTkFont = lambda **kw: kw


class TraceVar(FakeTk):
    def __init__(self, value=False):
        super().__init__(value)
        self.traces = []

    def trace_add(self, mode, cb):
        self.traces.append(cb)

    def set(self, v):
        self.value = v
        for cb in self.traces:
            cb("name", "", "w")


class UiOptions(unittest.TestCase):
    """The REAL explainer/ui_options.py (the application only calls it) against a fake app object, and the exact lines patch v2 adds to app.py."""

    def app(self, settings=None, switch=False):
        a = types.SimpleNamespace()
        a._settings = {} if settings is None else settings
        a._hybrid_explainer_var = TraceVar(switch)
        a.saved = []
        a._persist_global_settings = lambda: a.saved.append(json.dumps(a._settings, sort_keys=True))
        a._hybrid_status_var = FakeTk("")
        return a

    def installed(self, settings=None, switch=False):
        from unittest import mock
        from explainer import ui_options as U
        a, ctk = self.app(settings, switch), FakeCtk()
        with mock.patch.dict(sys.modules, {"customtkinter": ctk}):
            U.install(a, object())
        return a, ctk

    def test_defaults_when_nothing_was_ever_saved(self):
        from explainer import ui_options as U
        a = self.app()
        self.assertEqual(U.from_settings(a._settings), {"share": "Off", "source": "stock_video", "background": "paper", "narrator": "serious"})
        self.assertEqual(a._settings, {}, "reading the settings must not write anything")

    def test_saved_values_are_shown_and_invalid_ones_fall_back(self):
        from explainer import ui_options as U
        self.assertEqual(U.from_settings({"explainer_footage_share": 0.3, "explainer_footage_source": "youtube_video", "explainer_background": "grid", "explainer_narrator": "cartoon"}),
                         {"share": "30%", "source": "youtube_video", "background": "grid", "narrator": "cartoon"})
        default = {"share": "Off", "source": "stock_video", "background": "paper", "narrator": "serious"}
        for bad in ({"explainer_footage_share": "x", "explainer_footage_source": "tiktok", "explainer_background": "neon", "explainer_narrator": 7},
                    {"explainer_footage_share": None, "explainer_footage_source": [1], "explainer_background": None, "explainer_narrator": {}}, {"explainer_footage_share": float("nan")}, None, "text"):
            self.assertEqual(U.from_settings(bad), default, bad)

    def test_a_hand_edited_share_shows_the_nearest_choice(self):
        from explainer import ui_options as U
        for v, label in ((0.27, "30%"), (0.9, "40%"), (-1, "Off"), (0.04, "Off"), (0.06, "10%")):
            self.assertEqual(U.from_settings({"explainer_footage_share": v})["share"], label, v)

    def test_install_builds_four_menus_in_row_three_with_the_saved_choices(self):
        a, ctk = self.installed({"explainer_footage_share": 0.2, "explainer_background": "warm"}, switch=True)
        self.assertEqual(len(ctk.menus), 4)
        self.assertEqual([l.kw["text"] for l in ctk.labels], ["Footage", "from", "Background", "Narrator"])
        self.assertEqual(ctk.frames[0].grid_kw["row"], 3)
        self.assertEqual([m.kw["values"][0] for m in ctk.menus], ["Off", "stock_video", "paper", "serious"])
        self.assertEqual({k: v.get() for k, v in a._hybrid_explainer_opt_vars.items()}, {"share": "20%", "source": "stock_video", "background": "warm", "narrator": "serious"})
        self.assertEqual(sorted(ctk.menus[1].kw["values"]), sorted(["stock_video", "youtube_video", "flow_video", "stock_image", "flow_image"]))
        self.assertEqual(a.saved, [], "building the menus must not write the settings")

    def test_changing_a_menu_saves_the_right_keys_and_values(self):
        a, ctk = self.installed(switch=True)
        for k, v in (("share", "20%"), ("source", "flow_video"), ("background", "warm"), ("narrator", "cartoon")):
            a._hybrid_explainer_opt_vars[k].set(v)
        ctk.menus[0].kw["command"]("20%")                       # what the menu calls when the user picks a value
        self.assertEqual(a._settings, {"explainer_footage_share": 0.2, "explainer_footage_source": "flow_video", "explainer_background": "warm", "explainer_narrator": "cartoon"})
        self.assertEqual(len(a.saved), 1)

    def test_persistence_failure_never_raises(self):
        from explainer import ui_options as U
        a, _ctk = self.installed(switch=True)
        a._persist_global_settings = lambda: (_ for _ in ()).throw(OSError("disk full"))
        a._hybrid_explainer_opt_vars["share"].set("10%")
        U.save(a)
        self.assertEqual(a._settings["explainer_footage_share"], 0.1)

    def test_the_menus_follow_the_switch_through_its_variable(self):
        a, ctk = self.installed(switch=False)
        self.assertTrue(all(m.last["state"] == "disabled" for m in ctk.menus))
        a._hybrid_explainer_var.set(True)                       # the switch toggles this variable: the installed trace re-enables the menus
        self.assertTrue(all(m.last["state"] == "normal" for m in ctk.menus))
        a._hybrid_explainer_var.set(False)
        self.assertTrue(all(m.last["state"] == "disabled" for m in ctk.menus))

    def test_the_explainer_reads_back_exactly_what_the_menus_saved(self):
        from explainer.integration import footage_settings, look_settings
        a, ctk = self.installed(switch=True)
        for k, v in (("share", "30%"), ("source", "youtube_video"), ("background", "grid"), ("narrator", "cartoon")):
            a._hybrid_explainer_opt_vars[k].set(v)
        ctk.menus[0].kw["command"]("30%")
        self.assertEqual(footage_settings(a._settings), (0.3, "youtube_video"))
        self.assertEqual(look_settings(a._settings), ("grid", "cartoon"))
        self.assertEqual(footage_settings({}), (0.0, "stock_video"))
        self.assertEqual(look_settings({}), ("paper", "serious"))

    def test_the_status_line_asks_for_scenes_only_when_there_is_something_to_fetch(self):
        from explainer import ui_options as U
        clip = lambda x: types.SimpleNamespace(asset=x)
        beat = lambda *c: types.SimpleNamespace(clips=[clip(x) for x in c])
        boards = types.SimpleNamespace(beats=[beat("/p/board_1.mp4"), types.SimpleNamespace(clips=[]), beat("C:\\clips\\x.mp4")])
        footage = types.SimpleNamespace(beats=[beat("/p/board_1.mp4"), beat("stock_video:workers")])
        self.assertFalse(U.needs_scenes(boards))
        self.assertTrue(U.needs_scenes(footage))
        self.assertTrue(U.needs_scenes(types.SimpleNamespace(beats=[beat("flow_image:a map")])))
        self.assertFalse(U.needs_scenes(types.SimpleNamespace()))
        a = self.app()
        a._hybrid_status_var.set("Explainer plan ready: 2 beats. Check the plan, then get the scenes and render as usual.")     # what v1 sets just before
        U.status_after_plan(a, boards)
        self.assertNotIn("get the scenes", a._hybrid_status_var.get())
        self.assertIn("render as usual", a._hybrid_status_var.get())
        a._hybrid_status_var.set("keep me")
        U.status_after_plan(a, footage)
        self.assertEqual(a._hybrid_status_var.get(), "keep me", "with footage rows the original 'get the scenes' line stays")

    def test_the_patch_adds_exactly_the_two_calls_and_nothing_else(self):
        added = [l[1:].strip() for l in PATCH.read_text().splitlines() if l.startswith("+") and not l.startswith("+++")]
        self.assertEqual(len(added), 4, added)
        self.assertTrue(added[0].startswith("from explainer.ui_options import install") and added[1] == "_install_explainer_options(self, actions)")
        self.assertTrue(added[2].startswith("from explainer.ui_options import status_after_plan") and added[3] == "status_after_plan(self, plan)")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(scratch_app(d).returncode, 0)
            src = (Path(d) / "app.py").read_text()
        self.assertLess(src.index("_install_explainer_options(self, actions)"), src.index("Load beat CSV: your own plan"))
        self.assertLess(src.index("get the scenes and render as usual"), src.index("status_after_plan(self, plan)"))

    def test_the_new_module_is_in_the_packaged_app(self):
        from explainer import packaging
        self.assertIn("explainer.ui_options", packaging.python_modules(ROOT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
