"""StarMap inside the real app: the sixth style card, the panel, loading a beat CSV into the project, its pictures and clips as
rows of the EXISTING Visual Plan table, Check plan, the copied prompt with every dataset (none selected), the main button, persistence and
reopening, and generation (arguments, success, a picture that needs attention, Stop).

Live VideoGeneratorApp in a subprocess (same convention as test_hybrid_app_integration.py). The narration, the providers and the
renderer are fakes: nothing is downloaded, generated or drawn and no Flow credit is spent."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, time, wave, struct
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
OUT = sys.stdout

def emit(name, ok, detail=""):
    OUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); OUT.flush()

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
from pakmap.words import estimate_words
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)

tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws
SAMPLE = Path("starmap/samples/apollo11_beats.csv")
WORDS = estimate_words(Path("starmap/samples/apollo11_script.txt").read_text(), words_per_second=2.5)
wav = tmp / "vo.wav"
with wave.open(str(wav), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000 * 55)
shown = {}
_app.messagebox.showinfo = lambda title, msg, **k: shown.setdefault("info", (title, msg))
_app.messagebox.showerror = lambda title, msg, **k: shown.setdefault("error", (title, msg))
_asked = []
_app.messagebox.askyesno = lambda title, msg, **k: (_asked.append(msg), True)[1]
inst._show_preview = lambda p: shown.setdefault("preview", p)
inst._show_error_dialog = lambda title, summary, details: shown.setdefault("dialog", (title, summary, details))
went = []
inst._goto_workflow_view = lambda name, *a, **k: went.append(name)
inst._pakmap_get_words = lambda *a, **k: WORDS
shown_widget = lambda w: bool(w.grid_info())

def scenario():
    # ---- the sixth style ----------------------------------------------------------------------------------------
    emit("starmap_is_a_style_card", "StarMap" in inst._style_cards and "StarMap" in inst.STYLE_CHOICES)
    inst._current_voiceover_path = lambda: None
    inst._on_style_pick("StarMap"); inst.update_idletasks()
    emit("picking_it_shows_only_its_panel", inst.generation_mode == "starmap" and inst._style_picker.get() == "StarMap" and shown_widget(inst._starmap_block)
         and not shown_widget(inst._hybrid_block) and not shown_widget(inst._pakmap_block) and shown_widget(inst._starmap_controls), inst.generation_mode)
    emit("the_button_asks_for_the_voiceover_first", inst._cta_action == "import_audio", inst._cta_action)
    inst._current_voiceover_path = lambda: wav
    inst._sync_primary_cta()
    emit("then_for_the_beat_csv", inst._cta_action == "starmap_load_csv" and "beat CSV" in inst.hint_var.get(), inst._cta_action)
    inst._on_style_pick("Hybrid Map"); inst.update_idletasks()
    emit("hybrid_takes_over_from_starmap", inst.generation_mode == "hybrid" and not inst._starmap_enabled_var.get() and not shown_widget(inst._starmap_block))
    inst._on_style_pick("StarMap"); inst._overscaled_enabled_var.set(True); inst._on_overscaled_toggle()
    emit("overscaled_takes_over_from_starmap", inst.generation_mode == "overscaled" and not inst._starmap_enabled_var.get(), inst.generation_mode)
    inst._on_style_pick("StarMap")

    # ---- the prompt ---------------------------------------------------------------------------------------------
    inst._copy_csv_prompt("starmap", inst._starmap_status_var)
    clip = inst.clipboard_get()
    emit("the_copied_prompt_lists_the_datasets", "apollo11.translunar_coast" in clip and "artemis1.orion" in clip and "<<<DATASETS>>>" not in clip
         and "StarMap" in inst._starmap_status_var.get() and not hasattr(inst, "_starmap_pack_var"), inst._starmap_status_var.get())

    # ---- loading the CSV ------------------------------------------------------------------------------------------
    ok = inst._starmap_load_csv(str(SAMPLE))
    emit("the_csv_is_kept_in_the_project", ok and ws.starmap_csv_path.is_file() and inst._starmap_file_var.get() == str(ws.starmap_csv_path), inst._starmap_file_var.get())
    emit("its_cards_and_clips_are_visual_plan_rows", inst._scene_rows_owner == "starmap" and [(r.scene_number, r.asset_type) for r in inst._scene_rows] == [("1", "stock_image"), ("2", "stock_image"), ("3", "stock_image")]
         and "NASA image library first" in inst._scene_rows[0].script_segment, str([(r.scene_number, r.asset_type, r.script_segment[:30]) for r in inst._scene_rows]))
    emit("scene_actions_use_the_starmap_folder", inst._scene_action_images_dir() == ws.starmap_images_dir)
    emit("loading_checks_the_plan_in_the_background", inst._starmap_busy)
    yield (lambda: not inst._starmap_busy)
    text = inst._starmap_plan_box.get("1.0", "end")
    emit("check_plan_shows_the_report_and_every_beat", "8 beats" in text and "#8" in text and "OK" in text and inst._starmap_ok is True, text[:200])
    emit("the_button_says_generate", inst._cta_action == "generate", inst._cta_action)

    bad = tmp / "bad.csv"
    bad.write_text(SAMPLE.read_text().replace("tranquility base,surface,apollo11.pdi", "tranquility bas,surface,apollo11.pdi"), encoding="utf-8")
    inst._starmap_load_csv(str(bad))
    yield (lambda: not inst._starmap_busy)
    text = inst._starmap_plan_box.get("1.0", "end")
    emit("a_csv_with_a_fault_names_its_row", "ERROR row" in text and "tranquility bas" in text and inst._starmap_ok is False, text[:200])
    inst._starmap_load_csv(str(SAMPLE))
    yield (lambda: not inst._starmap_busy)

    # ---- generation -------------------------------------------------------------------------------------------------------------
    import starmap.app_integration as sai
    from pakmap.app_integration import PakmapResult
    got = {}
    def fake_ok(csv_path, vo, out, **kw):
        got.update(kw, csv=str(csv_path), out=str(out))
        kw["progress_cb"]("Drawing space…", 0.4); kw["log"]("[StarMap] fake")
        Path(out).write_bytes(b"x" * 10)
        return PakmapResult(True, [], Path(out), None, ["NASA"], ["a note"])
    sai.generate_starmap_video = fake_ok
    inst._scene_rows[2].asset_type = "stock_video"; inst._scene_rows[2].stock = "moonwalk footage"      # the user changed clip 3 in the table
    shown.clear()
    inst._on_generate()
    emit("running_state_shows_stop", inst._starmap_running and inst._cta_action == "starmap_cancel")
    yield (lambda: not inst._starmap_running)
    emit("a_run_finishes_and_the_video_is_reported", "StarMap video ready" in str(shown.get("info")) and shown.get("preview") == got.get("out"), str(shown.get("info"))[:80])
    emit("generation_gets_the_table_as_left_the_folders_and_callbacks",
         [(r.scene_number, r.asset_type) for r in got["scene_rows"]] == [("1", "stock_image"), ("2", "stock_image"), ("3", "stock_video")]
         and got["images_dir"] == ws.starmap_images_dir and got["work_dir"] == ws.starmap_work_dir and got["csv"] == str(ws.starmap_csv_path)
         and sorted(got["media_callbacks"]) == ["on_manager_ready", "on_scene_complete", "on_scene_generating", "on_scene_start"]
         and got["whisper_words"] == WORDS and got["sound_design"] is True and got["reference_now"] == ws.starmap_settings().get("reference_now")
         and "pack" not in got, str(got.get("images_dir")))
    emit("no_flow_question_when_no_flow_rows", not _asked, str(_asked))

    sai.generate_starmap_video = lambda *a, **kw: PakmapResult(False, ["Visual Plan scene 2 (card in beat b5, CSV row 21): no result"], unresolved=["2"])
    went.clear(); shown.clear()
    inst._on_generate()
    yield (lambda: not inst._starmap_running)
    emit("a_picture_that_needs_attention_opens_the_visual_plan", went == ["visual_plan"] and "need attention" in inst._starmap_status_var.get(), inst._starmap_status_var.get())

    import threading
    gate = threading.Event()
    def slow(*a, **kw):
        while not kw["cancel_check"]():
            time.sleep(0.02)
        return PakmapResult(False, ["Cancelled"], cancelled=True)
    sai.generate_starmap_video = slow
    inst._on_generate()
    yield (lambda: inst._starmap_running)
    inst._on_starmap_cancel()
    yield (lambda: not inst._starmap_running)
    emit("stop_cancels_the_run", inst._starmap_status_var.get() == "Cancelled", inst._starmap_status_var.get())

    # ---- persistence -------------------------------------------------------------------------------------------------------------------
    inst._starmap_sound_var.set(False); inst._save_starmap_settings(active=True)
    saved = ws.starmap_settings()
    emit("settings_are_saved", saved.get("sound_design") is False and saved.get("active") is True and "pack" not in saved
         and len(saved.get("reference_now", "")) == 10, str(saved))
    inst._starmap_sound_var.set(True)
    inst._starmap_enabled_var.set(False); inst._starmap_controls.grid_remove(); inst.generation_mode = "normal"; inst._scene_rows = []
    inst._bind_workspace_paths()
    emit("reopening_restores_style_rows_and_switches", inst.generation_mode == "starmap" and inst._starmap_enabled_var.get() and len(inst._scene_rows) == 3
         and inst._starmap_sound_var.get() is False and inst._starmap_reference_now() == saved["reference_now"], f"{inst.generation_mode} {len(inst._scene_rows)}")
    ws2 = ProjectWorkspace(project_id="p2", title="Other", seq=2, root=tmp / "proj2")
    for d in ("csv", "assets", "audio", "logs", "final", "flow"):
        (ws2.root / d).mkdir(parents=True, exist_ok=True)
    inst._workspace = ws2
    inst._bind_workspace_paths()
    emit("another_project_starts_clean", inst.generation_mode == "normal" and not inst._starmap_enabled_var.get() and inst._scene_rows == [] and ws.starmap_settings().get("active") is True,
         f"{inst.generation_mode} {ws.starmap_settings()}")
    inst._workspace = ws
    inst._bind_workspace_paths()
    emit("and_coming_back_restores_it", inst.generation_mode == "starmap")

def finish():
    os._exit(0)

gen = scenario()
state = {"cond": None, "since": 0.0}

def tick():
    try:
        if state["cond"] is not None:
            if state["cond"]():
                state["cond"] = None
            elif time.time() - state["since"] > 25:
                emit("timed_out_waiting", False, "a wait in the scenario never became true")
                finish()
            else:
                inst.after(20, tick)
                return
        while True:
            cond = next(gen)
            if cond is not None and not cond():
                state["cond"], state["since"] = cond, time.time()
                inst.after(20, tick)
                return
    except StopIteration:
        finish()
    except Exception:
        import traceback
        emit("scenario_crashed", False, traceback.format_exc().replace("\n", " | ")[-800:])
        finish()

inst.after(100, tick)
inst.mainloop()
'''


class TestStarmapInTheApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_starmap_app_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                              cwd=Path(__file__).resolve().parent)
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _all(self, *names):
        for n in names:
            with self.subTest(n):
                if n not in self._results:
                    self.fail(f"subprocess never reported {n!r}\nstdout:\n{self._stdout[-2000:]}\nstderr:\n{self._stderr[-2500:]}")
                ok, detail = self._results[n]
                self.assertTrue(ok, f"{n} failed: {detail}\nstderr:\n{self._stderr[-1500:]}")

    def test_the_style_card_and_switching(self):
        self._all("starmap_is_a_style_card", "picking_it_shows_only_its_panel", "the_button_asks_for_the_voiceover_first", "then_for_the_beat_csv",
                  "hybrid_takes_over_from_starmap", "overscaled_takes_over_from_starmap")

    def test_the_prompt_and_loading_a_csv(self):
        self._all("the_copied_prompt_lists_the_datasets", "the_csv_is_kept_in_the_project", "its_cards_and_clips_are_visual_plan_rows",
                  "scene_actions_use_the_starmap_folder", "loading_checks_the_plan_in_the_background", "check_plan_shows_the_report_and_every_beat",
                  "the_button_says_generate", "a_csv_with_a_fault_names_its_row")

    def test_generation(self):
        self._all("running_state_shows_stop", "a_run_finishes_and_the_video_is_reported", "generation_gets_the_table_as_left_the_folders_and_callbacks",
                  "no_flow_question_when_no_flow_rows", "a_picture_that_needs_attention_opens_the_visual_plan", "stop_cancels_the_run")

    def test_persistence(self):
        self._all("settings_are_saved", "reopening_restores_style_rows_and_switches", "another_project_starts_clean", "and_coming_back_restores_it")

    def test_no_crash(self):
        self.assertNotIn("scenario_crashed", self._results, self._results.get("scenario_crashed"))
        self.assertNotIn("timed_out_waiting", self._results)


if __name__ == "__main__":
    unittest.main()
