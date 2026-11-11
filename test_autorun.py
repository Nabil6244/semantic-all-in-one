"""make_video.py + autorun: a job runs any style through the app's own big button, dialogs are answered or recorded, failures are reported."""

import ast
import json
import re
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import make_video as MV
from autorun import driver as D, job as J

ROOT = Path(__file__).resolve().parent


def _files(d: Path):
    (d / "vo.mp3").write_bytes(b"ID3")
    (d / "song.mp3").write_bytes(b"ID3")
    (d / "script.txt").write_text("Venice rose on a lagoon.", encoding="utf-8")
    (d / "scenes.csv").write_text("row,scene\n", encoding="utf-8")


class TableTest(unittest.TestCase):
    def test_every_card_of_the_app_has_a_style_and_a_prompt(self):
        from ui import style_registry as R
        choices = ast.literal_eval(re.search(r"STYLE_CHOICES = (\(.*?\))", (ROOT / "app.py").read_text(encoding="utf-8")).group(1))
        cards = set(R.with_extras(choices)) | {"Weather"}
        self.assertEqual({s["pick"] for s in J.STYLES.values()}, cards)
        for k, s in J.STYLES.items():
            self.assertTrue((ROOT / s["csv_prompt"]).is_file(), k)

    def test_the_command_has_the_same_table(self):
        self.assertEqual(set(MV.STYLES), set(J.STYLES))
        for k, (csv, voice, prompt, card) in MV.STYLES.items():
            self.assertEqual((csv, voice, prompt, card), (J.STYLES[k]["csv"], J.STYLES[k]["voice"], J.STYLES[k]["csv_prompt"], J.STYLES[k]["pick"]), k)

    def test_job_checks(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            _files(d)
            self.assertEqual(J.make_job("War Documentary".replace(" Documentary", ""), str(d / "vo.mp3"))["style"], "war")
            self.assertEqual(J.make_job("Product_Trailer", csv=str(d / "scenes.csv"), music=str(d / "song.mp3"))["voice"], "")   # voice optional there
            for bad in (lambda: J.make_job("nope", str(d / "vo.mp3")), lambda: J.make_job("explainer"), lambda: J.make_job("hybrid", str(d / "vo.mp3")),
                        lambda: J.make_job("explainer", str(d / "script.txt")), lambda: J.make_job("explainer", str(d / "vo.mp3"), out=str(d / "x.mov"))):
                self.assertRaises(J.JobError, bad)

    def test_command_arguments_and_prompts(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            _files(d)
            ok = types.SimpleNamespace(style="Explainer", voice=str(d / "vo.mp3"), script=str(d / "script.txt"), csv="", music="", out="")
            self.assertEqual(MV.check_args(ok), "")
            self.assertEqual(ok.style, "explainer")
            self.assertIn("needs --csv", MV.check_args(types.SimpleNamespace(**{**vars(ok), "style": "hybrid"})))
            self.assertIn("needs --voice", MV.check_args(types.SimpleNamespace(**{**vars(ok), "voice": ""})))
            self.assertEqual(MV.check_args(types.SimpleNamespace(**{**vars(ok), "style": "kids-learn", "voice": "", "csv": str(d / "scenes.csv")})), "")
        self.assertEqual(MV.find_app()[-1], str(MV.HERE / "app.py"))
        for k in MV.STYLES:
            self.assertIsNotNone(MV.find_prompt(k, []), k)


FAKE_APP = '''
import json, os, sys, time
from pathlib import Path
job = Path(os.environ["SYT_AUTORUN"])
spec = json.loads(job.read_text())
st = job.with_name(job.stem + ".status.json")
title = spec["title"]
if title == "hang":
    time.sleep(600)
elif title == "bad":
    st.write_text(json.dumps({"state": "failed", "message": "2 scene(s) are still not ready", "failed_scenes": ["scene 3: failed (Flow: unusual activity)"],
                              "project": "/p/bad"}))
else:
    v = job.with_name(title + ".mp4"); v.write_bytes(b"mp4")
    st.write_text(json.dumps({"state": "done", "video": str(v), "project": "/p/" + title}))
'''


class BatchTest(unittest.TestCase):
    def test_a_failure_or_a_hang_never_stops_the_night_and_the_report_says_why(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            _files(d)
            (d / "fake").mkdir()
            (d / "fake" / "app.py").write_text(FAKE_APP, encoding="utf-8")
            (d / "videos.csv").write_text("style,voice,script,csv,title\n"
                                          "explainer,vo.mp3,script.txt,scenes.csv,one\n"
                                          "war,vo.mp3,script.txt,,bad\n"
                                          "explainer,vo.mp3,script.txt,,hang\n"
                                          "hybrid,vo.mp3,script.txt,,nocsv\n"
                                          "explainer,vo.mp3,script.txt,,two\n", encoding="utf-8")
            report = d / "report.txt"
            args = ["batch", str(d / "videos.csv"), "--app", str(d / "fake" / "app.py"), "--jobs-dir", str(d / "jobs"), "--report", str(report),
                    "--allow-sleep", "--force"]
            with mock.patch("sys.stderr"), mock.patch("sys.stdout"):
                self.assertEqual(MV.main(args), 2)                              # a wrong line: nothing starts
            self.assertFalse((d / "jobs").exists())
            with mock.patch.object(MV.time, "sleep", lambda s: None), mock.patch("sys.stderr"), mock.patch("sys.stdout"):
                real_follow = MV.follow
                with mock.patch.object(MV, "follow", lambda job, proc, max_s=0, say=print: real_follow(job, proc, max_s=0.000001 if "hang" in job.read_text() else 0,
                                                                                                         say=say)):
                    code = MV.main(args + ["--skip-bad"])
            self.assertEqual(code, 1)
            res = json.loads(report.with_suffix(".json").read_text())["results"]
            self.assertEqual([(r["title"], r["state"]) for r in res], [("one", "done"), ("bad", "failed"), ("hang", "failed"), ("nocsv", "failed"), ("two", "done")])
            text = report.read_text()
            self.assertIn("2 of 5 video(s) made, 3 failed", text)
            self.assertIn("scene 3: failed (Flow: unusual activity)", text)
            self.assertIn("stopped after", text)
            self.assertIn("not started: the hybrid style needs --csv", text)
            self.assertTrue(Path(res[4]["video"]).is_file())

    def test_json_batch_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            (d / "b.json").write_text(json.dumps({"videos": [{"style": "war", "voice": "a/vo.mp3"}, {}]}), encoding="utf-8")
            self.assertEqual(MV.read_batch(d / "b.json"), [{"style": "war", "voice": str(d / "a" / "vo.mp3"), "script": "", "csv": "", "music": "",
                                                            "title": "", "out": ""}])


class _Var:
    def __init__(self, v=None):
        self.v = v

    def get(self):
        return self.v

    def set(self, v):
        self.v = v


class FakeApp:
    """The app as the driver sees it: style cards, the big button's next action, Stop while running, the video in final/."""

    def __init__(self, root: Path, style_page=False, scenes_ready_after=2):
        self.root, self.queue, self.destroyed, self.calls = root, [], False, []
        self.audio_var, self.output_var, self.csv_var = _Var(""), _Var(""), _Var("")
        self._hybrid_enabled_var, self._hybrid_explainer_var = _Var(False), _Var(False)
        self._hybrid_switch = types.SimpleNamespace(toggle=lambda: self._hybrid_enabled_var.set(True))
        self._hybrid_plan, self._hybrid_busy = None, False
        self._rh_csv_var, self._rh_voice_var = _Var(""), _Var("")
        self.style, self.style_page, self.ws = "Normal video", style_page, None
        self.rounds, self.ready_after, self.running, self.loaded = 0, scenes_ready_after, 0, False
        self._cta_action = "picker"
        self.script_box = None
        self._scene_rows = [{"scene_number": 1}, {"scene_number": 2}]

    # Tk
    def after(self, ms, fn):
        self.queue.append(fn)

    def destroy(self):
        self.destroyed = True

    def run(self, limit=2000):
        n = 0
        while self.queue and not self.destroyed and n < limit:
            self.queue.pop(0)()
            n += 1

    # app methods the driver calls
    def _append_log(self, text):
        self.calls.append(("log", text))

    def _open_project_picker(self):
        raise AssertionError("the picker must be replaced")

    def _show_login_dialog(self, **k):
        self.calls.append(("login",))

    def _projects_root_path(self):
        return self.root / "projects"

    def _activate_workspace(self, ws, **k):
        self.ws = ws
        self.calls.append(("project",))

    def _active_style(self):
        return self.style

    def _on_style_pick(self, choice):
        self.style = choice
        self.calls.append(("pick", choice))
        if choice == "Explainer":
            self._hybrid_explainer_var.set(True)

    def _on_hybrid_explainer_changed(self):
        self.calls.append(("explainer", self._hybrid_explainer_var.get()))

    def _hybrid_browse_file(self):
        from tkinter import filedialog
        self.calls.append(("csv", filedialog.askopenfilename(title="Select a Hybrid CSV or plan", filetypes=[("Hybrid CSV", "*.csv")])))

    def _hybrid_explainer_direct(self):
        self.calls.append(("direct",))
        self._hybrid_plan = object()

    def _row_status_from_result(self, r):
        return "ready" if self.rounds >= self.ready_after else "failed"

    def _import_claude_csv_path(self, path, **k):
        self.loaded = True

    def _sync_primary_cta(self):
        if self.running:
            self.running -= 1
            self._cta_action = "rh_cancel" if self.style_page else "cancel"
        elif self.style_page:
            self._cta_action = "rh_render" if self.rounds else "rh_generate"
        elif not self.loaded and not self._hybrid_plan:
            self._cta_action = "import_csv"
        else:
            self._cta_action = "generate"

    def _on_primary_cta(self):
        a = self._cta_action
        if a == "import_csv":
            from tkinter import filedialog
            p = filedialog.askopenfilename(title="Select script CSV", filetypes=[("CSV files", "*.csv")])
            self.calls.append(("csv", p))
            self.loaded = bool(p)
            return
        if a == "rh_generate" and (getattr(self, "refuse", False) or not (self._rh_csv_var.get() and self._rh_voice_var.get())):
            from tkinter import messagebox
            messagebox.showerror("Cannot start", "Choose the story CSV first.")
            return
        self.running = 2
        if a in ("rh_render",) or (a == "generate" and self.rounds >= self.ready_after):
            self.calls.append(("render",))
            out = self.ws.next_final_path()
            out.write_bytes(b"mp4")
        else:
            self.rounds += 1
            self.calls.append(("scenes", self.rounds))


class DriverTest(unittest.TestCase):
    def setUp(self):
        for name, val in (("POLL_MS", 0), ("SETTLE_S", 0), ("FINAL_STABLE_S", -1)):
            p = mock.patch.object(D, name, val)
            p.start()
            self.addCleanup(p.stop)
        mb = mock.patch.multiple("tkinter.messagebox", showinfo=mock.DEFAULT, showwarning=mock.DEFAULT, showerror=mock.DEFAULT, askyesno=mock.DEFAULT,
                                 askokcancel=mock.DEFAULT, askyesnocancel=mock.DEFAULT, askretrycancel=mock.DEFAULT, askquestion=mock.DEFAULT)
        fd = mock.patch.multiple("tkinter.filedialog", askopenfilename=mock.DEFAULT, askopenfilenames=mock.DEFAULT, askdirectory=mock.DEFAULT,
                                 asksaveasfilename=mock.DEFAULT)
        for p in (mb, fd):
            p.start()
            self.addCleanup(p.stop)

    def _run(self, d: Path, app: FakeApp, **job):
        _files(d)
        spec = {"voice": str(d / "vo.mp3"), "script": str(d / "script.txt"), "csv": str(d / "scenes.csv"), "out": str(d / "out" / "film.mp4"), **job}
        path = d / "job.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        D.attach(app, str(path))
        app.run(3)
        app._open_project_picker()           # signed in: the app opens its picker, which the job replaced
        app.run()
        return path, J.read_status(path), [c for c in app.calls if c[0] != "log"]

    def test_a_normal_style_follows_the_big_button_to_the_video(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            app = FakeApp(d)
            job, st, steps = self._run(d, app, style="enoch-template")
            self.assertEqual(steps, [("project",), ("pick", "Enoch Template"), ("csv", str(d / "scenes.csv")), ("scenes", 1), ("scenes", 2), ("render",)])
            self.assertEqual(st["state"], "done", st)
            self.assertEqual(Path(st["video"]).resolve(), (d / "out" / "film.mp4").resolve())
            self.assertTrue(app.destroyed)
            from project_workspace import load_project
            ws = load_project(Path(st["project"]))
            self.assertEqual(ws.script_path.read_text(encoding="utf-8"), "Venice rose on a lagoon.")
            self.assertEqual(ws.get_active_voiceover(), Path(app.audio_var.get()).resolve())

    def test_explainer_directs_first_and_puts_the_switch_back(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            app = FakeApp(d)
            job, st, steps = self._run(d, app, style="explainer")
            self.assertEqual([s[0] for s in steps], ["project", "pick", "csv", "direct", "scenes", "scenes", "render", "explainer"])
            self.assertEqual(steps[-1], ("explainer", False))            # the app-wide Explainer look is back as it was
            self.assertTrue(app._hybrid_enabled_var.get())
            self.assertEqual(st["state"], "done", st)

    def test_a_style_page_gets_its_own_fields_filled(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            app = FakeApp(d, style_page=True)
            job, st, steps = self._run(d, app, style="rules-horror")
            self.assertEqual(app._rh_csv_var.get(), str(d / "scenes.csv"))
            self.assertTrue(app._rh_voice_var.get().endswith("voiceover.mp3"))   # the project's copy
            self.assertEqual([s[0] for s in steps], ["project", "pick", "scenes", "render"])
            self.assertEqual(st["state"], "done", st)

    def test_scenes_that_never_come_back_stop_the_job_and_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            app = FakeApp(d, scenes_ready_after=99)
            job, st, steps = self._run(d, app, style="normal")
            self.assertEqual(st["state"], "failed")
            self.assertEqual([s for s in steps if s[0] == "scenes"], [("scenes", 1), ("scenes", 2), ("scenes", 3), ("scenes", 4)])
            self.assertIn("still not ready", st["message"])
            self.assertEqual(st["failed_scenes"], ["scene 1: failed", "scene 2: failed"])
            self.assertNotIn(("render",), steps)

    def test_a_video_still_being_written_is_waited_for_not_rendered_again(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            app = FakeApp(d)
            with mock.patch.object(D, "FINAL_STABLE_S", 0.3):   # the render's file is fresh when the button goes back to Generate
                job, st, steps = self._run(d, app, style="enoch-template")
                for _ in range(200):
                    if app.destroyed:
                        break
                    import time as _t
                    _t.sleep(0.01)
                    app.run()
            st = J.read_status(job)
            self.assertEqual(st["state"], "done", st)
            self.assertEqual([c for c in app.calls if c[0] == "render"], [("render",)])   # rendered once

    def test_an_error_dialog_stops_the_job_with_its_text(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            app = FakeApp(d, style_page=True)
            app.refuse = True                            # the page refuses to start: Generate says why
            job, st, steps = self._run(d, app, style="rules-horror")
            self.assertEqual(st["state"], "failed")
            self.assertIn("Choose the story CSV first", st["message"])
            self.assertTrue(app.destroyed)

    def test_questions_are_answered_yes_and_files_by_kind(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            _files(d)
            path = d / "job.json"
            path.write_text(json.dumps({"style": "product-trailer", "csv": str(d / "scenes.csv"), "music": str(d / "song.mp3")}), encoding="utf-8")
            r = D.Runner(FakeApp(d), path)
            r.job = J.read_job(path)
            r.patch_dialogs()
            from tkinter import filedialog, messagebox
            self.assertTrue(messagebox.askyesno("Visual QA", "Render anyway?"))
            self.assertIn("Visual QA: Render anyway?", J.read_status(path)["questions"])
            self.assertEqual(filedialog.askopenfilename(title="Choose the music track"), str(d / "song.mp3"))
            self.assertEqual(filedialog.askopenfilename(title="Choose the feature CSV", filetypes=[("CSV", "*.csv")]), str(d / "scenes.csv"))
            self.assertEqual(filedialog.askopenfilename(title="Choose the end-card picture"), "")
            self.assertEqual(filedialog.askdirectory(title="Folder"), "")

    def test_sign_in_is_waited_for(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            _files(d)
            path = d / "job.json"
            path.write_text(json.dumps({"style": "explainer", "voice": str(d / "vo.mp3")}), encoding="utf-8")
            app = FakeApp(d)
            D.attach(app, str(path))
            app.run(3)
            app._show_login_dialog(message="")
            self.assertEqual(J.read_status(path)["state"], "waiting_for_sign_in")
            self.assertIn(("login",), app.calls)


if __name__ == "__main__":
    unittest.main()
