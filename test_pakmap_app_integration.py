"""pakMap mode inside the real app: mode switching, the shared Generate button, loading a script, the channel
name, a full run with a fake renderer, failure, Stop, and reopening a project.

Live VideoGeneratorApp in a subprocess (same convention as test_bulk_retry_publishes_each_scene.py: in-process Tk
construction corrupts the shared root). The renderer and the transcription are replaced by fakes, so nothing is
drawn, downloaded or transcribed and no network is used."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = r'''
import os, sys, tempfile, threading, time, wave, struct
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())
REAL_STDOUT = sys.stdout

def emit(name, ok, detail=""):
    REAL_STDOUT.write(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}\n"); REAL_STDOUT.flush()

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}"); os._exit(0)
from project_workspace import ProjectWorkspace
# never touch the machine's real settings.json: the app saves the channel name there as the default for new projects
_iso = Path(tempfile.mkdtemp()) / "settings.json"
_app._settings_path = lambda: _iso
try:
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}"); os._exit(0)

def pump(until=None, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        inst.update()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True

tmp = Path(tempfile.mkdtemp())
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=tmp / "proj")
for d in ("csv", "assets", "audio", "logs", "final", "flow"):
    (ws.root / d).mkdir(parents=True, exist_ok=True)
inst._workspace = ws

# a script folder with a CSV and a tiny voiceover
src = tmp / "scripts"; src.mkdir()
csv_path = src / "kenya.csv"
csv_path.write_text("item_no,vo_anchor,layer_type,layer_id,label_text,sub_text,geo_ref\n1,Kenya has,hud_title,,PART 1,THE EMPTY HALF,\n1,Nairobi,marker,m,NAIROBI,,Nairobi\n", encoding="utf-8")
bad_csv = src / "bad.csv"
bad_csv.write_text("item_no,layer_type\n1,nonsense\n", encoding="utf-8")
wav = tmp / "vo.wav"
with wave.open(str(wav), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000)
WORDS = [("Kenya", 0.5, 0.9), ("has", 0.9, 1.1), ("Nairobi", 2.0, 2.5)]

def scenario():
    # ---- mode switching and the Generate button ------------------------------------------------
    emit("starts_in_normal_mode_with_pakmap_hidden", inst.generation_mode == "normal" and not inst._pakmap_controls.winfo_ismapped())
    inst._pakmap_enabled_var.set(True); inst._on_pakmap_toggle()
    emit("switch_turns_pakmap_mode_on", inst.generation_mode == "pakmap" and inst._pakmap_controls.winfo_manager() != "")
    inst._overscaled_enabled_var.set(True); inst._on_overscaled_toggle()
    emit("overscaled_takes_over_and_pakmap_steps_aside", inst.generation_mode == "overscaled" and not inst._pakmap_enabled_var.get())
    inst._pakmap_enabled_var.set(True); inst._on_pakmap_toggle()
    emit("pakmap_takes_over_from_overscaled", inst.generation_mode == "pakmap" and not inst._overscaled_enabled_var.get())

    inst._sync_primary_cta()
    emit("button_asks_for_a_csv_first", inst._cta_action == "pakmap_import_csv", inst._cta_action)

    # ---- loading a script -----------------------------------------------------------------------
    ok_bad = inst._load_pakmap_csv(str(bad_csv))
    box = inst._pakmap_plan_box.get("1.0", "end")
    emit("a_bad_csv_is_refused_with_its_row", (ok_bad is False) and "row 2" in box and "unknown layer_type" in box, box[:120])
    inst._pakmap_csv_var.set(str(csv_path)); inst._pakmap_base_dir = str(src)
    ok_good = inst._load_pakmap_csv(str(csv_path))
    box = inst._pakmap_plan_box.get("1.0", "end")
    emit("a_good_csv_is_summarised", ok_good and "2 rows in 1 item" in box and "1 hud_title" in box and "1 marker" in box, box[:120])
    inst._current_voiceover_path = lambda: None
    inst._sync_primary_cta()
    emit("button_asks_for_a_voiceover_next", inst._cta_action == "import_audio", inst._cta_action)
    inst._current_voiceover_path = lambda: wav
    inst._sync_primary_cta()
    emit("button_says_generate_when_ready", inst._cta_action == "generate", inst._cta_action)

    # ---- channel name: saved with the project and as the default for the next one ---------------------
    emit("no_channel_name_means_no_watermark", inst._pakmap_watermark() is None)
    inst._pakmap_channel_var.set("  My Channel ")
    saved = ws.pakmap_settings()
    emit("channel_name_is_saved_in_the_project", saved.get("channel_name") == "My Channel", str(saved))
    emit("channel_name_becomes_the_default", inst._settings.get("pakmap_channel_name") == "My Channel")
    emit("watermark_carries_the_name", inst._pakmap_watermark() == {"text": "My Channel"})
    inst._pakmap_channel_var.set("")
    emit("an_empty_name_is_a_real_choice", ws.pakmap_settings().get("channel_name") == "" and inst._pakmap_watermark() is None)
    inst._pakmap_channel_var.set("My Channel")

    # ---- a full run with a fake renderer --------------------------------------------------------------
    import pakmap.app_integration as pai
    calls = {}
    def fake_ok(csv, vo, out, **kw):
        calls.update(rows=kw.get("scene_rows"), media_dir=kw.get("media_dir"), callbacks=sorted((kw.get("media_callbacks") or {}).keys()), pexels=kw.get("pexels_api_key"), flow=kw.get("flow_engine_manager"), accounts=kw.get("flow_video_account_ids"), sound=kw.get("sound_design"), csv=str(csv), out=str(out), work=str(kw["work_dir"]), base=str(kw["base_dir"]), wm=kw["watermark"], words=kw["whisper_words"])
        kw["progress_cb"]("Drawing the map… frame 1/2", 0.4); kw["log"]("[pakMap] fake log line")
        Path(out).write_bytes(b"x" * 10)
        return pai.PakmapResult(True, [], Path(out), None, ["NASA credit", "CHIRPS credit"], [])
    pai.generate_pakmap_video = fake_ok
    inst._pakmap_get_words = lambda *a, **k: WORDS
    shown = {}
    _app.messagebox.showinfo = lambda title, msg, **k: shown.setdefault("info", (title, msg))
    _app.messagebox.showerror = lambda title, msg, **k: shown.setdefault("error", (title, msg))
    inst._show_preview = lambda p: shown.setdefault("preview", p)
    inst._show_error_dialog = lambda title, summary, details: shown.setdefault("dialog", (title, summary, details))

    g0 = (inst.smart_sfx_var.get(), inst.smart_scene_ambience_var.get())
    emit("sound_design_is_on_by_default", inst._pakmap_sound_var.get() is True)
    inst._on_generate()
    emit("running_state_shows_stop", inst._pakmap_running and inst._cta_action == "pakmap_cancel")
    yield (lambda: not inst._pakmap_running)
    emit("run_finishes_and_button_returns", (not inst._pakmap_running) and inst._cta_action == "generate", inst._cta_action)
    emit("the_script_was_copied_into_the_project", ws.pakmap_csv_path.is_file() and calls.get("csv") == str(ws.pakmap_csv_path), calls.get("csv", ""))
    emit("media_paths_stay_relative_to_the_original_folder", calls.get("base") == str(src) and ws.pakmap_settings().get("base_dir") == str(src), calls.get("base", ""))
    emit("watermark_and_words_reach_the_generator", calls.get("wm") == {"text": "My Channel"} and calls.get("words") == WORDS)
    emit("video_lands_in_the_projects_final_folder", Path(calls.get("out", "")).parent == ws.final_dir, calls.get("out", ""))
    emit("work_files_go_to_the_pakmap_work_folder", calls.get("work") == str(ws.pakmap_work_dir), calls.get("work", ""))
    emit("success_is_reported", "pakMap video ready" in str(shown.get("info")) and shown.get("preview") == calls.get("out") and inst._last_output == calls.get("out"), str(shown.get("info")))
    emit("status_says_done", inst._pakmap_status_var.get().startswith("Done"), inst._pakmap_status_var.get())

    # ---- sound design switch (Phase 7) ------------------------------------------------------------------
    emit("sound_design_reaches_the_generator", calls.get("sound") is True, str(calls.get("sound")))
    inst._pakmap_sound_var.set(False); inst._on_pakmap_sound_changed()
    emit("the_switch_is_saved_in_the_project", ws.pakmap_settings().get("sound_design") is False and inst._settings.get("pakmap_sound_design") is False, str(ws.pakmap_settings()))
    calls.clear()
    inst._on_generate(); yield (lambda: not inst._pakmap_running)
    emit("switch_off_reaches_the_generator", calls.get("sound") is False, str(calls.get("sound")))
    emit("pakmap_never_changes_the_global_sfx_and_ambience_settings", (inst.smart_sfx_var.get(), inst.smart_scene_ambience_var.get()) == g0, str(g0))
    inst._pakmap_sound_var.set(True); inst._on_pakmap_sound_changed()
    shown.clear()

    # ---- pictures from stock / Flow (Phase 8) -----------------------------------------------------------
    head = "item_no,vo_anchor,layer_type,layer_id,label_text,geo_ref,asset_path,anchor\n1,Kenya has,hud_title,t,PART 1,,,\n"
    (src / "stock.csv").write_text(head + "1,Nairobi,pip,p,,Nairobi,stock_image:Nairobi skyline,tr\n", encoding="utf-8")
    (src / "flow.csv").write_text(head + "1,Nairobi,pip,p,,Nairobi,flow_image:a map of Kenya,tr\n", encoding="utf-8")
    fm = object()
    inst._get_flow_engine_manager = lambda: fm
    inst._video_account_ids = lambda: ["7"]
    inst.pexels_key_var.set("PK")
    asked = []; answer = {"v": False}
    _app.messagebox.askyesno = lambda title, msg, **k: (asked.append(msg), answer["v"])[1]
    inst._pakmap_csv_var.set(str(src / "stock.csv")); inst._load_pakmap_csv(str(src / "stock.csv"))
    calls.clear(); inst._on_generate(); yield (lambda: not inst._pakmap_running and bool(calls))
    emit("stock_pictures_ask_nothing_start_no_flow_and_pass_the_key", not asked and calls.get("flow") is None and calls.get("accounts") is None and calls.get("pexels") == "PK", str((asked, calls.get("flow"), calls.get("pexels"))))
    inst._pakmap_csv_var.set(str(src / "flow.csv")); inst._load_pakmap_csv(str(src / "flow.csv"))
    calls.clear(); inst._on_generate()
    emit("declining_flow_credits_runs_nothing", len(asked) == 1 and "a map of Kenya" in asked[0] and "credits" in asked[0] and not inst._pakmap_running and not calls, str(asked))
    answer["v"] = True
    inst._on_generate(); yield (lambda: not inst._pakmap_running and bool(calls))
    emit("accepting_flow_credits_runs_with_the_flow_manager_and_accounts", calls.get("flow") is fm and calls.get("accounts") == ["7"] and len(asked) == 2, str((calls.get("flow"), calls.get("accounts"))))
    # ---- the Visual Plan tab (Phase 8) ----------------------------------------------------------------
    from asset_manager import AssetManifest
    both = head + "1,Nairobi,pip,p,NAIROBI,Nairobi,stock_image:Nairobi skyline,tr\n1,rain,media_full,v,,,flow_video:rain over Kenya,\n1,rain,pip,l,,,local/city.jpg,tl\n"
    (src / "both.csv").write_text(both, encoding="utf-8")
    inst._pakmap_csv_var.set(str(src / "both.csv")); inst._load_pakmap_csv(str(src / "both.csv"))
    rows = inst._scene_rows
    emit("script_pictures_become_visual_plan_rows", [(r.scene_number, r.asset_type) for r in rows] == [("1", "stock_image"), ("2", "video")], str([(r.scene_number, r.asset_type) for r in rows]))
    emit("a_local_file_is_not_a_row_and_rows_say_what_they_are", len(rows) == 2 and "photo card" in rows[0].script_segment and "NAIROBI" in rows[0].script_segment, rows[0].script_segment)
    inst._refresh_scene_preview()
    emit("the_table_is_not_wiped_by_visiting_the_tab", len(inst._scene_rows) == 2)
    emit("scene_actions_use_the_pakmap_images_folder", inst._scene_action_images_dir() == ws.pakmap_images_dir, str(inst._scene_action_images_dir()))
    # a saved picture (what Change source / Local clip / an earlier run leave) shows as ready after a reload
    ws.pakmap_images_dir.mkdir(parents=True, exist_ok=True)
    (ws.pakmap_images_dir / "001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
    AssetManifest(ws.pakmap_images_dir).set("1", {"status": "complete", "source": "manual", "user_override": True, "local_path": str(ws.pakmap_images_dir / "001.png")})
    inst._load_pakmap_csv(str(src / "both.csv"))
    emit("a_saved_replacement_shows_ready_after_reload", inst._row_status_from_result(inst._scene_rows[0]) == "ready" and inst._row_status_from_result(inst._scene_rows[1]) != "ready", inst._row_status_from_result(inst._scene_rows[0]))
    AssetManifest(ws.pakmap_images_dir).set("2", {"status": "failed", "source": "flow_video", "prompt": "rain over Kenya", "error": "Flow rejected the request"})
    inst._load_pakmap_csv(str(src / "both.csv"))
    emit("a_failed_picture_shows_needs_action_with_its_reason", inst._row_status_from_result(inst._scene_rows[1]) == "needs_action" and "Flow rejected" in str(getattr(inst._asset_results.get(_app._scene_key("2")), "error", "")), inst._row_status_from_result(inst._scene_rows[1]))
    inst._label_pakmap_rows({3: 12.0, 4: 75.0}, {"1": 3, "2": 4})
    emit("check_plan_puts_the_time_in_front_of_each_row", inst._scene_rows[0].script_segment.startswith("0:12  ") and inst._scene_rows[1].script_segment.startswith("1:15  "), inst._scene_rows[0].script_segment)
    # the table as the user left it (a changed source) is what generation receives
    inst._scene_rows[1].asset_type = "image"; inst._scene_rows[1].prompt = "Kenya rain, painted"
    answer["v"] = True; calls.clear()
    inst._on_generate(); yield (lambda: not inst._pakmap_running and bool(calls))
    got = calls.get("rows") or []
    emit("generation_receives_the_table_rows_the_images_folder_and_live_callbacks",
         [(r.scene_number, r.asset_type, r.prompt or r.stock) for r in got] == [("1", "stock_image", "Nairobi skyline"), ("2", "image", "Kenya rain, painted")]
         and calls.get("media_dir") == ws.pakmap_images_dir and calls.get("callbacks") == ["on_manager_ready", "on_scene_complete", "on_scene_generating", "on_scene_start"],
         str((calls.get("media_dir"), calls.get("callbacks"))))
    # a picture that cannot be found sends the author to the Visual Plan tab
    went = []
    inst._goto_workflow_view = lambda name, *a, **k: went.append(name)
    pai.generate_pakmap_video = lambda *a, **kw: pai.PakmapResult(False, ["Picture 2 (full-screen, script row 4): no picture was found for it"], unresolved=["2"])
    inst._show_error_dialog = lambda title, summary, details: shown.setdefault("dialog", (title, summary, details))
    inst._on_generate(); yield (lambda: not inst._pakmap_running)
    emit("an_unresolved_picture_opens_the_visual_plan", went == ["visual_plan"] and "need attention" in inst._pakmap_status_var.get(), str((went, inst._pakmap_status_var.get())))
    pai.generate_pakmap_video = fake_ok
    # stepping aside takes the pictures out of the shared table
    inst._pakmap_enabled_var.set(False); inst._on_pakmap_toggle()
    emit("switching_pakmap_off_clears_its_rows", inst._scene_rows == [] and inst.generation_mode == "normal", str(len(inst._scene_rows)))
    inst._pakmap_enabled_var.set(True); inst._on_pakmap_toggle()
    emit("switching_pakmap_on_brings_them_back", len(inst._scene_rows) == 2 and inst.generation_mode == "pakmap", str(len(inst._scene_rows)))
    inst._pakmap_csv_var.set(str(csv_path)); inst._load_pakmap_csv(str(csv_path))
    shown.clear()

    # ---- failure --------------------------------------------------------------------------------------
    shown.clear()
    pai.generate_pakmap_video = lambda *a, **kw: pai.PakmapResult(False, ["row 4: can't find 'Atlantis' in the narration"])
    inst._on_generate(); yield (lambda: not inst._pakmap_running)
    emit("failure_is_explained", "Atlantis" in str(shown.get("dialog")) and inst._pakmap_status_var.get().startswith("Failed") and not inst._pakmap_running, str(shown.get("dialog"))[:100])

    # ---- Stop -----------------------------------------------------------------------------------------
    started = threading.Event()
    def slow(csv, vo, out, **kw):
        started.set()
        while not kw["cancel_check"]():
            time.sleep(0.01)
        return pai.PakmapResult(False, ["Cancelled"], cancelled=True)
    pai.generate_pakmap_video = slow
    inst._on_generate()
    yield (lambda: started.is_set())
    inst._on_primary_cta()   # the button now says Stop
    yield (lambda: not inst._pakmap_running)
    emit("stop_cancels_the_run", (not inst._pakmap_running) and inst._pakmap_status_var.get() == "Cancelled" and inst._cta_action == "generate", inst._pakmap_status_var.get())

    # ---- missing prerequisites ------------------------------------------------------------------------
    shown.clear()
    inst._current_voiceover_path = lambda: None
    inst._run_pakmap_generation()
    emit("no_voiceover_is_refused_politely", "voiceover" in str(shown.get("error")).lower(), str(shown.get("error")))
    inst._current_voiceover_path = lambda: wav

    # ---- reopening the project ------------------------------------------------------------------------
    ws.set_pakmap_settings(channel_name="My Channel", base_dir=str(src), sound_design=False)   # what the project has saved
    inst._pakmap_sound_var.set(True)
    inst._pakmap_csv_var.set(""); inst._pakmap_channel_var.set("Other"); inst._pakmap_base_dir = ""   # what the open app shows
    ws.set_pakmap_settings(channel_name="My Channel", sound_design=False)    # (typing "Other" saved it; put the project's own back)
    inst._pakmap_enabled_var.set(False); inst._on_pakmap_toggle()
    inst._bind_workspace_paths()
    emit("the_real_settings_file_was_not_touched", not (Path(_app.__file__).parent / "settings.json").exists() or "pakmap_channel_name" not in __import__("json").loads((Path(_app.__file__).parent / "settings.json").read_text() or "{}"))
    emit("reopening_restores_the_sound_switch", inst._pakmap_sound_var.get() is False)
    emit("reopening_restores_script_name_and_mode",
         inst.generation_mode == "pakmap" and inst._pakmap_csv_var.get() == str(ws.pakmap_csv_path) and inst._pakmap_channel_var.get() == "My Channel" and inst._pakmap_base_dir == str(src),
         f"{inst.generation_mode} {inst._pakmap_csv_var.get()} {inst._pakmap_channel_var.get()!r} {inst._pakmap_base_dir}")

    # ---- a project without a pakMap script leaves the mode alone -------------------------------------
    ws.pakmap_csv_path.unlink()
    inst._bind_workspace_paths()
    emit("a_project_without_a_script_is_not_pakmap", inst.generation_mode == "normal" and inst._pakmap_csv_var.get() == "", inst.generation_mode)



def finish():
    REAL_STDOUT.flush()
    os._exit(0)

gen = scenario()
state = {"cond": None, "since": 0.0}

def tick():
    try:
        if state["cond"] is not None:
            if state["cond"]():
                state["cond"] = None
            elif time.time() - state["since"] > 20:
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
    except Exception as exc:
        import traceback
        emit("scenario_crashed", False, traceback.format_exc().replace("\n", " | ")[-400:])
        finish()

inst.after(100, tick)
inst.mainloop()
'''


class TestPakmapInTheApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(tempfile.mkdtemp()) / "_pakmap_app_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=240, cwd=Path(__file__).resolve().parent)
        cls._stdout, cls._stderr, cls._results = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._results:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout[-1500:]}\nstderr:\n{self._stderr[-2500:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_modes_and_button(self):
        for n in ("starts_in_normal_mode_with_pakmap_hidden", "switch_turns_pakmap_mode_on", "overscaled_takes_over_and_pakmap_steps_aside",
                  "pakmap_takes_over_from_overscaled", "button_asks_for_a_csv_first", "button_asks_for_a_voiceover_next", "button_says_generate_when_ready"):
            with self.subTest(n):
                self._check(n)

    def test_loading_a_script(self):
        self._check("a_bad_csv_is_refused_with_its_row")
        self._check("a_good_csv_is_summarised")

    def test_channel_name(self):
        for n in ("no_channel_name_means_no_watermark", "channel_name_is_saved_in_the_project", "channel_name_becomes_the_default",
                  "watermark_carries_the_name", "an_empty_name_is_a_real_choice"):
            with self.subTest(n):
                self._check(n)

    def test_a_full_run(self):
        for n in ("running_state_shows_stop", "run_finishes_and_button_returns", "the_script_was_copied_into_the_project",
                  "media_paths_stay_relative_to_the_original_folder", "watermark_and_words_reach_the_generator",
                  "video_lands_in_the_projects_final_folder", "work_files_go_to_the_pakmap_work_folder", "success_is_reported", "status_says_done"):
            with self.subTest(n):
                self._check(n)

    def test_sound_design_switch(self):
        for n in ("sound_design_is_on_by_default", "sound_design_reaches_the_generator", "the_switch_is_saved_in_the_project",
                  "switch_off_reaches_the_generator", "pakmap_never_changes_the_global_sfx_and_ambience_settings", "reopening_restores_the_sound_switch"):
            with self.subTest(n):
                self._check(n)

    def test_pictures_from_stock_and_flow(self):
        for n in ("stock_pictures_ask_nothing_start_no_flow_and_pass_the_key", "declining_flow_credits_runs_nothing",
                  "accepting_flow_credits_runs_with_the_flow_manager_and_accounts"):
            with self.subTest(n):
                self._check(n)

    def test_the_visual_plan_tab(self):
        for n in ("script_pictures_become_visual_plan_rows", "a_local_file_is_not_a_row_and_rows_say_what_they_are", "the_table_is_not_wiped_by_visiting_the_tab",
                  "scene_actions_use_the_pakmap_images_folder", "a_saved_replacement_shows_ready_after_reload", "a_failed_picture_shows_needs_action_with_its_reason", "check_plan_puts_the_time_in_front_of_each_row",
                  "generation_receives_the_table_rows_the_images_folder_and_live_callbacks", "an_unresolved_picture_opens_the_visual_plan",
                  "switching_pakmap_off_clears_its_rows", "switching_pakmap_on_brings_them_back"):
            with self.subTest(n):
                self._check(n)

    def test_failure_stop_and_missing_voiceover(self):
        for n in ("failure_is_explained", "stop_cancels_the_run", "no_voiceover_is_refused_politely"):
            with self.subTest(n):
                self._check(n)

    def test_reopening_a_project(self):
        self._check("reopening_restores_script_name_and_mode")
        self._check("a_project_without_a_script_is_not_pakmap")


if __name__ == "__main__":
    unittest.main()
