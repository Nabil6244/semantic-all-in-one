"""Runs a job inside the real app, on the Tk thread (app.main calls attach() when SYT_AUTORUN is set). Works for every style the same way a
person does:

  1. a new project with the voiceover (and script) in it;
  2. the style's card is picked (app._on_style_pick), and the style page's own file fields are filled as its Browse buttons would;
  3. the big button (app._on_primary_cta) is pressed for whatever it says next (load the CSV, load the voiceover, Generate, Make pictures,
     Render), and while it says Stop the job waits;
  4. done when the finished video is in the project's final/ folder (every style exports there: ws.next_final_path).

Nothing here re-implements a style. File dialogs are answered with the job's files (CSV, voiceover, music; anything else is cancelled).
Other dialogs cannot be clicked by anyone, so they are recorded: a question is answered Yes (the app's own way to go on), an error stops the
job with its text. Scenes that do not come back (failed Flow pictures...) get the button pressed again: the app fetches only what is
missing, SCENE_ROUNDS times; after that the job stops and lists them. The sign-in is the app's own: the job waits for the person."""

from __future__ import annotations

import shutil
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import job as J

POLL_MS = 1000
SIGN_IN_WAIT_S = 30 * 60
STEP_WAIT_S = 10 * 3600        # one press (a long render or a big Flow batch) may take hours; the app's stall watchdog stops a stuck tool
SCENE_ROUNDS = 3               # presses of the same Generate step: the app fetches only the scenes still missing each time
SETTLE_S = 4.0                 # after a press, the button needs a moment to turn into Stop
FINAL_STABLE_S = 3.0
SKIP_SHARE = 0.3               # after the rounds, up to this share of scenes still missing are skipped and the video is rendered anyway
SKIP_WAIT_S = 600              # the app's skip queue gets this long to mark them
IMPORT_ACTIONS = {"import_csv", "overscaled_import_csv", "pakmap_import_csv", "hybrid_load_csv", "starmap_load_csv", "import_audio", "weather_load"}
CLAUDE_HANDOFF = {"analyze", "vo_plan", "upload_claude_csv"}


def _running(action: str) -> bool:
    return action == "none" or action.endswith("cancel")


class Runner:
    def __init__(self, app: Any, job_path: "str | Path"):
        self.app = app
        self.job_path = Path(job_path)
        self.status = J.Status(self.job_path)
        self.log_file = J.log_path(self.job_path)
        self._lock = threading.Lock()
        self.job: dict = {}
        self.style: dict = {}
        self.errors_seen = 0
        self.ws = None
        self.explainer_before: Optional[bool] = None
        self.presses: Dict[str, int] = {}
        self.pressed_at = 0.0
        self.step_started = 0.0
        self.handoff_done = False
        self.finished = False
        self.skipped: List[str] = []

    # ---- plumbing -------------------------------------------------------------------------------------------------------------------
    def log(self, msg: str) -> None:
        with self._lock:
            try:
                with self.log_file.open("a", encoding="utf-8") as f:
                    f.write(msg if msg.endswith("\n") else msg + "\n")
            except OSError:
                pass

    def say(self, step: str, message: str = "") -> None:
        self.status.set(state="running", step=step, message=message)
        self.log(f"[AUTORUN] {step}{': ' + message if message else ''}")

    def end(self) -> None:
        self.finished = True
        self._restore()
        self.app.after(3000, self.app.destroy)

    def fail(self, why: str) -> None:
        if self.finished:
            return
        self.log(f"[AUTORUN] FAILED: {why}")
        bad = self.scene_problems()
        self.status.set(state="failed", message=why, failed_scenes=bad)
        self.end()

    def done(self, video: Path) -> None:
        out = self.job.get("out")
        shown = str(video)
        if out:
            try:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(video, out)
                shown = out
            except OSError as exc:
                self.log(f"[AUTORUN] could not copy the video to {out}: {exc}; it stays at {video}")
        self.log(f"[AUTORUN] DONE: {shown}")
        self.status.set(state="done", step="done", message="the video is ready", video=shown)
        self.end()

    def _restore(self) -> None:
        """The Explainer look is an app-wide setting: put it back as the person had it."""
        if self.explainer_before is None:
            return
        try:
            self.app._hybrid_explainer_var.set(self.explainer_before)
            self.app._on_hybrid_explainer_changed()
        except Exception:
            pass
        self.explainer_before = None

    def guarded(self, fn: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            if self.finished:
                return
            try:
                fn()
            except Exception as exc:
                self.log(traceback.format_exc())
                self.fail(f"{type(exc).__name__}: {exc}")
        return run

    def later(self, fn: Callable[[], None], ms: int = POLL_MS) -> None:
        self.app.after(ms, self.guarded(fn))

    def new_error(self) -> Optional[str]:
        errs = self.status.data.get("errors") or []
        if len(errs) > self.errors_seen:
            self.errors_seen = len(errs)
            return errs[-1]
        return None

    def scene_problems(self) -> List[str]:
        """Scenes of the Visuals table that are not ready: 'scene 12: failed (Flow: ...)'."""
        out: List[str] = []
        try:
            import sys
            ok = getattr(sys.modules.get(type(self.app).__module__), "_QA_RENDER_OK", ("ready", "done", "complete", "skipped"))   # the running app's module (__main__ when run as app.py)
            for r in list(getattr(self.app, "_scene_rows", []) or []):
                st = str(self.app._row_status_from_result(r))
                if st in ok:
                    continue
                no = getattr(r, "scene_number", None) or (r.get("scene_number") if isinstance(r, dict) else "?")
                why = getattr(r, "error", "") or getattr(r, "message", "") or (r.get("error", "") if isinstance(r, dict) else "")
                out.append(f"scene {no}: {st}" + (f" ({str(why)[:160]})" if why else ""))
        except Exception:
            pass
        return out[:200]

    # ---- dialogs: answered or recorded, never shown ---------------------------------------------------------------------------------
    def answer_file(self, title: Any = "", filetypes: Any = None) -> str:
        words = f"{title} {filetypes}".lower()
        if "music" in words:
            pick = self.job.get("music", "")
        elif any(w in words for w in ("voice", "audio", "narration", "mp3", "wav")):
            pick = self.job.get("voice", "")
        elif any(w in words for w in ("csv", "scene", "plan", "story", "lesson", "feature", "script", "shot", "beat")):
            pick = self.job.get("csv", "")
        else:
            pick = ""
        self.log(f"[AUTORUN] file dialog '{title}': {'answered with ' + pick if pick else 'cancelled'}")
        return pick

    def patch_dialogs(self) -> None:
        from tkinter import filedialog as fd, messagebox as mb

        def info(kind: str) -> Callable[..., str]:
            def f(title: Any = "", message: Any = "", *a: Any, **k: Any) -> str:
                text = f"{title}: {message}".strip()
                self.log(f"[AUTORUN] {kind} dialog: {text}")
                if kind == "error":
                    self.status.add("errors", text[:2000])
                return "ok"
            return f

        def ask(title: Any = "", message: Any = "", *a: Any, **k: Any) -> bool:
            text = f"{title}: {message}".strip()
            self.log(f"[AUTORUN] question answered Yes: {text}")
            self.status.add("questions", text[:600])
            return True

        mb.showinfo, mb.showwarning, mb.showerror = info("info"), info("warning"), info("error")
        mb.askyesno = mb.askokcancel = mb.askyesnocancel = mb.askretrycancel = ask
        mb.askquestion = lambda *a, **k: (ask(*a, **k) and "yes")
        fd.askopenfilename = lambda *a, **k: self.answer_file(k.get("title", a[0] if a else ""), k.get("filetypes"))
        fd.askopenfilenames = lambda *a, **k: tuple(x for x in (self.answer_file(k.get("title", ""), k.get("filetypes")),) if x)
        fd.askdirectory = lambda *a, **k: (self.log(f"[AUTORUN] folder dialog '{k.get('title', '')}': cancelled") or "")
        fd.asksaveasfilename = lambda *a, **k: (self.log(f"[AUTORUN] save dialog '{k.get('title', '')}': cancelled") or "")

        orig = self.app._append_log

        def tee(text: str, *a: Any, **k: Any) -> Any:
            self.log(str(text).rstrip("\n"))
            return orig(text, *a, **k)
        self.app._append_log = tee

    # ---- the steps ------------------------------------------------------------------------------------------------------------------
    def take_over(self) -> bool:
        """Before the window's first idle moment (the app opens its project picker then): the picker and the sign-in are routed to the
        job, and dialogs are answered. Returns False for a bad job file."""
        try:
            self.job = J.read_job(self.job_path)
        except Exception as exc:
            self.status.set(state="failed", message=f"bad job file: {exc}")
            self.app.after(2000, self.app.destroy)
            return False
        self.style = J.STYLES[self.job["style"]]
        self.patch_dialogs()
        self.ready = False
        self.app._open_project_picker = lambda *a, **k: setattr(self, "ready", True)   # signed in: no picker, the job makes its own project
        real_login = self.app._show_login_dialog

        def login(*a: Any, **k: Any) -> Any:
            self.status.set(state="waiting_for_sign_in", step="sign in", message="sign in in the app window; the job goes on by itself")
            self.log("[AUTORUN] waiting for you to sign in in the app window")
            return real_login(*a, **k)
        self.app._show_login_dialog = login
        self.status.set(state="starting", step="opening the app", message=f"style {self.job['style']}")
        return True

    def close_picker(self) -> None:
        """A picker that opened anyway (an app that shows it another way): closed, the job makes its own project."""
        pk = getattr(self.app, "_project_picker", None)
        try:
            if pk is not None and pk.winfo_exists():
                pk.destroy()
                self.ready = True
        except Exception:
            pass

    def start(self) -> None:
        t0 = time.time()

        def wait_ready() -> None:
            self.close_picker()
            if self.ready:
                self.later(self.make_project, 10)
            elif time.time() - t0 > SIGN_IN_WAIT_S:
                self.fail("the app was not signed in within 30 minutes")
            else:
                self.later(wait_ready)
        self.later(wait_ready)

    def make_project(self) -> None:
        from project_workspace import create_project, load_project

        app, job = self.app, self.job
        existing = (job.get("project") or "").strip()
        if existing:
            ws = load_project(Path(existing))
            if ws is None:
                self.fail(f"project folder is not a video project: {existing}")
                return
            self.say("open project", ws.root.name)
            app._activate_workspace(ws, persist=True, clear_session=True)
            self.ws = ws
            self.status.set(project=str(ws.root))
            self.later(self.pick_style, 300)
            return
        self.say("create project", job["title"])
        ws = create_project(job["title"], projects_root=app._projects_root_path())
        ws.ensure_dirs()
        dest = None
        if job["voice"]:
            voice = Path(job["voice"])
            dest = Path(ws.audio_path).parent / f"voiceover{voice.suffix.lower()}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(voice, dest)
            ws.set_active_voiceover(dest, source="imported")
            self.job["voice"] = str(dest)
        script = Path(job["script"]).read_text(encoding="utf-8-sig") if job["script"] else ""
        if script:
            Path(ws.script_path).parent.mkdir(parents=True, exist_ok=True)
            Path(ws.script_path).write_text(script, encoding="utf-8")
        app._activate_workspace(ws, persist=True, clear_session=True)
        if dest is not None:
            app.audio_var.set(str(dest))
        for box in (getattr(app, "script_box", None), getattr(app, "_vo_script_box", None)):
            if box is not None and script:
                try:
                    box.delete("1.0", "end")
                    box.insert("1.0", script)
                except Exception:
                    pass
        self.ws = ws
        self.status.set(project=str(ws.root))
        self.later(self.pick_style, 300)

    def pick_style(self) -> None:
        app, pick = self.app, self.style["pick"]
        self.say("pick the style", pick)
        if pick == "Explainer":
            self.explainer_before = bool(getattr(app, "_hybrid_explainer_var", None) and app._hybrid_explainer_var.get())
        try:
            app._shell.navigate("visual_director")
        except Exception:
            pass
        app._on_style_pick(pick)
        if app._active_style() != pick:
            self.fail(f"the style {pick!r} could not be chosen (is it switched on in this app?)")
            return
        if self.job["style"] in ("hybrid", "explainer") and not app._hybrid_enabled_var.get():
            app._hybrid_switch.toggle()                     # "Use Hybrid Map for this project", as a click
        for kind, attr in self.style["fields"].items():     # the style page's own Browse buttons only remember the file
            val = self.job.get(kind, "")
            var = getattr(app, attr, None)
            if val and var is not None:
                var.set(val)
                self.log(f"[AUTORUN] {pick}: {kind} = {val}")
        if self.job["style"] == "what-if" and self.job["csv"]:
            from whatif import app_section as _wi
            _wi.load_csv(app, self.job["csv"])
        self.later(self.prepare, 500)

    def prepare(self) -> None:
        """Explainer only: its scene CSV is kept by Load (not imported), then Direct with Explainer makes the plan."""
        app = self.app
        if self.job["style"] != "explainer":
            self.later(self.step, 10)
            return
        if self.job["csv"]:
            app._hybrid_browse_file()
        self.say("direct with Explainer", "listening to the narration and planning the scenes")
        before = app._hybrid_plan
        app._hybrid_explainer_direct()
        t0 = time.time()

        def wait_plan() -> None:
            err = self.new_error()
            if err:
                self.fail(f"directing with Explainer: {err}")
            elif not app._hybrid_busy and app._hybrid_plan is not None and app._hybrid_plan is not before:
                self.later(self.step, 10)
            elif not app._hybrid_busy and time.time() - t0 > 10:
                self.fail("Direct with Explainer ended without a plan; see the log")
            elif time.time() - t0 > STEP_WAIT_S:
                self.fail("Direct with Explainer: no plan after 10 hours")
            else:
                self.later(wait_plan)
        self.later(wait_plan)

    def final_video(self) -> "tuple[Optional[Path], bool]":
        """(the newest finished video in final/, whether it has stopped changing). A video still being written is never a reason to press
        the button again (that would render it a second time)."""
        if self.ws is None:
            return None, False
        vids = [p for p in Path(self.ws.final_dir).glob("*.mp4") if p.stat().st_size > 0 and ".part" not in p.name and not p.name.startswith(".")]
        if not vids:
            return None, False
        v = max(vids, key=lambda p: p.stat().st_mtime)
        return v, time.time() - v.stat().st_mtime > FINAL_STABLE_S

    def step(self) -> None:
        """One look at the big button: wait while it says Stop, else press it for whatever it says next."""
        app = self.app
        err = self.new_error()
        if err:
            self.fail(err)
            return
        try:
            app._sync_primary_cta()
        except Exception:
            pass
        action = str(getattr(app, "_cta_action", "generate") or "generate")
        if _running(action) or time.time() - self.pressed_at < SETTLE_S:
            if self.step_started and time.time() - self.step_started > STEP_WAIT_S:
                self.fail(f"one step ran for more than {STEP_WAIT_S / 3600:.0f} hours")
                return
            self.later(self.step)
            return
        video, settled = self.final_video()
        if video is not None:
            if settled:
                self.done(video)
            else:
                self.later(self.step)                       # just written: look again in a moment, never press again
            return
        if action == "picker":
            self.fail("the app has no project open")
            return
        if action in CLAUDE_HANDOFF:
            if not self.job["csv"] or self.handoff_done:
                self.fail(f"the {self.job['style']} style needs its scene CSV (--csv); write it with: make_video.py prompt --style {self.job['style']}")
                return
            self.handoff_done = True
            self.say("load the CSV", Path(self.job["csv"]).name)
            app._import_claude_csv_path(Path(self.job["csv"]), source_label="uploaded")
            self.press_done()
            return
        n = self.presses.get(action, 0) + 1
        self.presses[action] = n
        limit = 2 if action in IMPORT_ACTIONS else SCENE_ROUNDS + 1
        if n > limit:
            bad = self.scene_problems()
            rows = len(getattr(app, "_scene_rows", []) or [])
            if bad and not self.skipped and action not in IMPORT_ACTIONS and len(bad) <= SKIP_SHARE * rows and hasattr(app, "_bulk_recovery"):
                self.skip_then_render(action, bad)
                return
            what = f"{len(bad)} scene(s) are still not ready after {SCENE_ROUNDS} rounds" if bad else f"the app keeps asking for '{action}'"
            self.fail(f"{what}; open the project's Visuals tab to fix or skip them, then Render")
            return
        label = {"import_csv": "load the CSV", "overscaled_import_csv": "load the CSV", "pakmap_import_csv": "load the CSV", "hybrid_load_csv": "load the CSV",
                 "starmap_load_csv": "load the CSV", "import_audio": "load the voiceover", "weather_load": "load the CSV"}.get(action, action.replace("_", " "))
        self.say(label, f"press {n}" if n > 1 else "")
        app._on_primary_cta()
        self.press_done()

    def skip_then_render(self, action: str, bad: List[str]) -> None:
        """Unattended, a few scenes that never came back must not stop the night: they are skipped (the Visuals tab's own Skip failed,
        so the render treats them as the author's skip) and the next press renders. The status and the report list them."""
        app = self.app
        self.skipped = list(bad)
        self.status.set(skipped_scenes=self.skipped)
        self.say("skip missing scenes", f"{len(bad)} scene(s) still missing after {SCENE_ROUNDS} rounds: skipped, rendering without them")
        for b in bad:
            self.log(f"[AUTORUN]   skipped {b}")
        app._bulk_recovery("skip", selected_only=False)
        t0 = time.time()

        def wait_skip() -> None:
            if getattr(app, "_retry_pumping", False) and time.time() - t0 < SKIP_WAIT_S:
                self.later(wait_skip)
                return
            self.fill_skipped()
            self.presses[action] = SCENE_ROUNDS            # one more press: the render (all scenes now ready or skipped)
            self.press_done()
        self.later(wait_skip)

    def fill_skipped(self) -> None:
        """A skipped scene's file is a 1x1 placeholder (a flat screen in the video): it gets a still of the nearest ready scene instead
        (a picture is copied, a clip gives its middle frame)."""
        import subprocess

        app = self.app
        results = getattr(app, "_asset_results", None) or {}
        if not results:
            return

        def ok_file(r: Any) -> Optional[Path]:
            path = getattr(r, "path", None)
            st = str(getattr(getattr(r, "status", None), "value", getattr(r, "status", "")))
            return Path(path) if path and st != "skipped" and getattr(r, "ok", False) and Path(path).is_file() else None

        keys = list(results.keys())
        for i, k in enumerate(keys):
            r = results[k]
            if str(getattr(getattr(r, "status", None), "value", "")) != "skipped" or not getattr(r, "path", None):
                continue
            dest = Path(r.path)
            for j in sorted(range(len(keys)), key=lambda j: (abs(j - i), j > i)):
                src = ok_file(results[keys[j]]) if j != i else None
                if src is None:
                    continue
                try:
                    if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                        from PIL import Image
                        Image.open(src).convert("RGB").save(dest, "PNG")
                    else:
                        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(src), "-frames:v", "1", str(dest)],
                                       check=True, timeout=60)
                    self.log(f"[AUTORUN]   scene {getattr(r, 'scene_number', k)}: shows a still of scene {getattr(results[keys[j]], 'scene_number', keys[j])}")
                    break
                except Exception as exc:  # noqa: BLE001 - the next neighbour is tried
                    self.log(f"[AUTORUN]   scene {getattr(r, 'scene_number', k)}: still from {src.name} failed: {exc}")

    def press_done(self) -> None:
        self.pressed_at = time.time()
        self.step_started = time.time()
        self.later(self.step)


def attach(app: Any, job_path: str) -> Runner:
    """Called by app.main before mainloop (SYT_AUTORUN). The job starts once the window is up."""
    r = Runner(app, job_path)
    if r.take_over():                                   # now, before mainloop: the app's first idle step opens the picker
        app.after(1500, r.guarded(r.start))
    return r
