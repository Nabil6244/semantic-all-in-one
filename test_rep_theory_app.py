"""Rep Theory inside the real app: picking the style, the four option checkboxes and their defaults, the shared primary button, and what Render hands to the engine for every combination (smart planner, 3D clips,
Flow pictures with the app's own Flow settings, mixed looks), Stop, a failed run and a missing voiceover.

Live VideoGeneratorApp in a subprocess (same convention as test_pakmap_app_integration.py: in-process Tk construction corrupts the shared root). The engine, the transcription and Flow are replaced by fakes:
nothing is rendered, generated, transcribed or sent."""
from __future__ import annotations
import subprocess, sys, tempfile, unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, threading, time, wave, struct
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True); sys.path.insert(0, os.getcwd()); REAL_STDOUT = sys.stdout
def emit(name, ok, detail=""): REAL_STDOUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); REAL_STDOUT.flush()
try: import app as _app
except ModuleNotFoundError as exc: print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
_iso = Path(tempfile.mkdtemp()) / "settings.json"; _app._settings_path = lambda: _iso
try: inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc: print(f"SKIP:{exc}"); os._exit(0)
tmp = Path(tempfile.mkdtemp()); ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"): (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
wav = tmp / "vo.wav"
with wave.open(str(wav), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 16000)
WORDS = [(x, 0.2 * i, 0.2 * i + 0.18) for i, x in enumerate("Your triceps straighten the elbow. Your lats pull the body up.".split())]      # (word, start, end) like the app's own word timings
shown = {}
_app.messagebox.showinfo = lambda t, m, **k: shown.setdefault("info", (t, m)); _app.messagebox.showerror = lambda t, m, **k: shown.setdefault("error", (t, m))
inst._pakmap_get_words = lambda *a, **k: WORDS; inst._current_voiceover_path = lambda: wav
from reptheory import engine
calls = {}; mode = {"v": "ok"}
def fake_run(project_dir, sentences, vo, out, **kw):
    calls.clear(); calls.update(kw, sentences=sentences, out=out)
    if mode["v"] == "block":
        while not kw["cancel_check"](): time.sleep(0.02)
        raise engine.Cancelled()
    if mode["v"] == "fail": raise RuntimeError("boom: renderer exploded")
    kw["progress_cb"](0.5, "fake"); kw["log"]("fake log line"); Path(out).write_bytes(b"x" * 4096)
    return {"scenes": [1, 2, 3], "size": (1920, 1080), "video_seconds": 9.0, "not_implemented": []}
engine.run_rep_theory = fake_run
inst._image_flow_run_settings = lambda: ({"generationMode": "ui", "model": "GEM_PIX_2"}, ["7"])

def logtext(): return inst.log_box.get("1.0", "end") + "".join(inst._log_backlog) + "".join(inst._log_ui_buf)
def scenario():
    inst._on_style_pick("Rep Theory")
    emit("picking_the_style_shows_its_block", inst._rt_block.winfo_manager() != "" and inst._rt_active)
    emit("option_defaults", (inst._rt_smart_var.get(), inst._rt_3d_var.get(), inst._rt_flow_var.get(), inst._rt_variety_var.get(), inst._rt_preview_var.get()) == (True, True, False, True, False),
         str((inst._rt_smart_var.get(), inst._rt_3d_var.get(), inst._rt_flow_var.get(), inst._rt_variety_var.get())))
    labels = []
    def walk(w):
        for c in w.winfo_children():
            try: labels.append(c.cget("text"))
            except Exception: pass
            walk(c)
    walk(inst._rt_block)
    emit("the_four_checkboxes_are_on_screen", all(t in labels for t in ("Scene per idea (smart planner)", "3D muscle clips", "Flow pictures", "Mix looks for long videos", "Preview (1280x720)", "Render Rep Theory")), str([l for l in labels if isinstance(l, str)][:14]))
    inst._sync_primary_cta()
    emit("button_says_render_when_a_voiceover_exists", inst._cta_action == "rt_render", inst._cta_action)
    inst._current_voiceover_path = lambda: None; inst._sync_primary_cta()
    emit("button_asks_for_a_voiceover_first", inst._cta_action == "import_audio", inst._cta_action)
    inst._current_voiceover_path = lambda: wav; inst._sync_primary_cta()

    # ---- defaults: smart planner + 3D + mixed looks, no Flow
    inst._on_primary_cta()
    emit("running_state_shows_stop_or_finishes", True)
    yield (lambda: not inst._rt_running and bool(calls))
    emit("defaults_reach_the_engine", (calls.get("planner"), calls.get("per_beat"), calls.get("illustrate"), calls.get("clips3d"), calls.get("variety"), calls.get("flow_settings")) == ("beats", True, False, True, True, None), str({k: calls.get(k) for k in ("planner", "per_beat", "illustrate", "clips3d", "variety", "flow_settings")}))
    emit("words_became_sentences_and_output_is_in_the_project", len(calls["sentences"]) >= 1 and Path(calls["out"]).parent == ws.final_dir, str((len(calls["sentences"]), calls["out"])))
    emit("status_says_done", inst._rt_status_var.get().startswith("Done") and inst._cta_action == "rt_render", inst._rt_status_var.get() + "|" + inst._cta_action)

    # ---- Flow pictures on: the app's own Flow settings and accounts are used
    inst._rt_flow_var.set(True); inst._on_primary_cta(); yield (lambda: not inst._rt_running and bool(calls))
    emit("flow_uses_the_apps_flow_settings_and_accounts", calls.get("illustrate") is True and calls.get("flow_settings") == {"generationMode": "ui", "model": "GEM_PIX_2"} and calls.get("flow_accounts") == ["7"] and calls.get("flow_mode") == "ui", str({k: calls.get(k) for k in ("illustrate", "flow_settings", "flow_accounts", "flow_mode")}))

    # ---- 3D off, flow off: mixed looks still on
    inst._rt_flow_var.set(False); inst._rt_3d_var.set(False); inst._on_primary_cta(); yield (lambda: not inst._rt_running and bool(calls))
    emit("3d_off_reaches_the_engine", calls.get("clips3d") is False and calls.get("illustrate") is False and calls.get("variety") is True)

    # ---- smart planner off: legacy planner, per-beat and mixed looks off whatever the other boxes say
    inst._rt_3d_var.set(True); inst._rt_smart_var.set(False); inst._on_primary_cta(); yield (lambda: not inst._rt_running and bool(calls))
    emit("smart_off_means_legacy_planner_and_no_variety", (calls.get("planner"), calls.get("per_beat"), calls.get("variety")) == ("legacy", False, False), str({k: calls.get(k) for k in ("planner", "per_beat", "variety")}))
    inst._rt_smart_var.set(True)

    # ---- preview checkbox
    inst._rt_preview_var.set(True); inst._on_primary_cta(); yield (lambda: not inst._rt_running and bool(calls))
    emit("preview_reaches_the_engine", calls.get("quality") == "preview"); inst._rt_preview_var.set(False)

    # ---- Stop
    mode["v"] = "block"; calls.clear(); inst._on_primary_cta()
    yield (lambda: inst._rt_running and bool(calls))
    emit("while_running_the_button_is_stop", inst._cta_action == "rt_cancel", inst._cta_action)
    inst._on_primary_cta()                 # an immediate second press is the app's accidental double-click guard: it must NOT cancel
    emit("a_double_click_does_not_cancel", not inst._rt_cancel.is_set())
    inst._cta_last_start_press = 0.0; inst._on_primary_cta()
    yield (lambda: not inst._rt_running)
    emit("stop_cancels_the_run", inst._rt_status_var.get() == "Stopped." and inst._cta_action == "rt_render", inst._rt_status_var.get() + "|" + inst._cta_action)

    # ---- a failed run says why
    mode["v"] = "fail"; inst._on_primary_cta(); yield (lambda: not inst._rt_running)
    emit("failure_is_explained", "boom: renderer exploded" in inst._rt_status_var.get() and "boom" in logtext(), inst._rt_status_var.get())
    mode["v"] = "ok"

    # ---- the 3D model warning when the model is missing
    from reptheory import clip3d
    clip3d.available = lambda: False; inst.log_box.delete("1.0", "end"); inst._log_backlog.clear(); inst._log_ui_buf.clear(); calls.clear(); inst._on_primary_cta(); yield (lambda: not inst._rt_running and bool(calls))
    emit("missing_model_is_logged_not_fatal", "3D body model or renderer not found" in logtext() and calls.get("clips3d") is True)

    # ---- no voiceover: refused politely, nothing starts
    inst._current_voiceover_path = lambda: None; calls.clear(); shown.clear(); _app_cta = inst._cta_action
    from reptheory import app_section; app_section.on_render_click(inst)
    emit("no_voiceover_is_refused_politely", "error" in shown and not calls and not inst._rt_running, str(shown))

    # ---- leaving the style hides the block
    inst._on_style_pick("Health Cinema")
    emit("another_style_hides_the_block", inst._rt_block.winfo_manager() == "" and not inst._rt_active)
    inst._on_style_pick("Rep Theory")
    emit("coming_back_shows_it_with_the_options_kept", inst._rt_block.winfo_manager() != "" and inst._rt_smart_var.get() and inst._rt_3d_var.get())

def finish(): REAL_STDOUT.flush(); os._exit(0)
gen = scenario(); state = {"cond": None, "since": 0.0}
def tick():
    try:
        if state["cond"] is not None:
            if state["cond"](): state["cond"] = None
            elif time.time() - state["since"] > 20: emit("timed_out_waiting", False, "a wait never became true: " + inst._rt_status_var.get() + f" cancel={inst._rt_cancel.is_set()} running={inst._rt_running} mode={mode['v']} threads={[t.name for t in threading.enumerate()]}" + " | " + logtext()[-400:].replace("\n", " / ")); finish()
            else: inst.after(20, tick); return
        while True:
            cond = next(gen)
            if cond is not None and not cond(): state["cond"], state["since"] = cond, time.time(); inst.after(20, tick); return
    except StopIteration: finish()
    except Exception:
        import traceback; emit("scenario_crashed", False, traceback.format_exc().replace("\n", " | ")[-500:]); finish()
inst.after(100, tick); inst.mainloop()
'''
NAMES = ("picking_the_style_shows_its_block", "option_defaults", "the_four_checkboxes_are_on_screen", "button_says_render_when_a_voiceover_exists", "button_asks_for_a_voiceover_first", "defaults_reach_the_engine",
         "words_became_sentences_and_output_is_in_the_project", "status_says_done", "flow_uses_the_apps_flow_settings_and_accounts", "3d_off_reaches_the_engine", "smart_off_means_legacy_planner_and_no_variety",
         "preview_reaches_the_engine", "while_running_the_button_is_stop", "a_double_click_does_not_cancel", "stop_cancels_the_run", "failure_is_explained", "missing_model_is_logged_not_fatal", "no_voiceover_is_refused_politely",
         "another_style_hides_the_block", "coming_back_shows_it_with_the_options_kept")

class TestRepTheoryInTheApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_rt_app_check.py"; script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, cwd=Path(__file__).resolve().parent)
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"): raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")): status, rest = line.split(":", 1); name, _, detail = rest.partition(":"); cls._results[name] = (status == "PASS", detail)

    def test_every_step(self):
        for n in NAMES:
            with self.subTest(n):
                if n not in self._results: self.fail(f"subprocess never reported {n!r}\nstdout:\n{self._stdout[-1800:]}\nstderr:\n{self._stderr[-2500:]}")
                ok, detail = self._results[n]; self.assertTrue(ok, f"{n} failed: {detail}\nstderr:\n{self._stderr[-1500:]}")

if __name__ == "__main__": unittest.main()
