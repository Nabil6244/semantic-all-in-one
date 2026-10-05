"""Hybrid Map inside the real app: the third style switch, planning with AI (scripted Director), loading a plan, footage as rows of the
EXISTING Visual Plan table, replacement/failed-clip state, persistence and reopening, and generation arguments and errors.

Live VideoGeneratorApp in a subprocess (same convention as test_pakmap_app_integration.py). The Director, the providers and the renderer
are fakes: nothing is downloaded, generated or drawn and no Flow credit is spent."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLAN_JSON = Path(__file__).with_name("test_hybrid_app_plan.json")

_SCRIPT = r'''
import os, sys, tempfile, threading, time, wave, struct, json
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
PLAN_PATH = tmp / "plan.json"
PLAN_PATH.write_text(open(os.environ["HYBRID_PLAN_JSON"]).read())
wav = tmp / "vo.wav"
with wave.open(str(wav), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000 * 24)
WORDS = [("pakistan", 0.5, 0.9), ("is", 0.9, 1.1)] + [("w%d" % i, 2 + i * 0.5, 2.3 + i * 0.5) for i in range(40)]
shown = {}
_app.messagebox.showinfo = lambda title, msg, **k: shown.setdefault("info", (title, msg))
_app.messagebox.showerror = lambda title, msg, **k: shown.setdefault("error", (title, msg))
_asked = []; _answer = {"v": True}
_app.messagebox.askyesno = lambda title, msg, **k: (_asked.append(msg), _answer["v"])[1]
inst._show_preview = lambda p: shown.setdefault("preview", p)
inst._show_error_dialog = lambda title, summary, details: shown.setdefault("dialog", (title, summary, details))
went = []
inst._goto_workflow_view = lambda name, *a, **k: went.append(name)
inst._pakmap_get_words = lambda *a, **k: WORDS

def scenario():
    # ---- the third switch ---------------------------------------------------------------------------
    emit("starts_off_and_hidden", inst.generation_mode == "normal" and not inst._hybrid_controls.winfo_ismapped())
    inst._current_voiceover_path = lambda: None
    inst._hybrid_enabled_var.set(True); inst._on_hybrid_toggle()
    emit("switch_turns_hybrid_on", inst.generation_mode == "hybrid" and inst._hybrid_controls.winfo_manager() != "")
    emit("button_asks_for_the_voiceover_first", inst._cta_action == "import_audio", inst._cta_action)
    inst._current_voiceover_path = lambda: wav
    inst._sync_primary_cta()
    emit("then_for_the_plan", inst._cta_action == "hybrid_load_csv" and "beat CSV" in inst.hint_var.get(), inst._cta_action)
    inst._pakmap_enabled_var.set(True); inst._on_pakmap_toggle()
    emit("pakmap_takes_over_from_hybrid", inst.generation_mode == "pakmap" and not inst._hybrid_enabled_var.get() and not inst._hybrid_controls.winfo_ismapped())
    inst._hybrid_enabled_var.set(True); inst._on_hybrid_toggle()
    emit("hybrid_takes_over_from_pakmap", inst.generation_mode == "hybrid" and not inst._pakmap_enabled_var.get())
    inst._overscaled_enabled_var.set(True); inst._on_overscaled_toggle()
    emit("overscaled_takes_over_from_hybrid", inst.generation_mode == "overscaled" and not inst._hybrid_enabled_var.get(), inst.generation_mode)
    inst._overscaled_enabled_var.set(False); inst._on_overscaled_toggle()
    inst._hybrid_enabled_var.set(True); inst._on_hybrid_toggle()

    # ---- the panel: four steps, progress, two big choices, file row, channel name, quiet actions, timeline, chips, details, status ---------
    kids = inst._hybrid_controls.winfo_children()
    rows_used = sorted({int(w.grid_info().get("row", -1)) for w in kids})
    emit("the_panel_follows_pakmaps_layout_row_for_row", rows_used == [-1, 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], str(rows_used))  # row 1 is the progress card, hidden while nothing runs
    emit("it_has_check_plan_and_the_ai_actions_as_buttons", all(hasattr(inst, n) for n in ("_hybrid_check_btn", "_hybrid_plan_btn", "_hybrid_repair_btn", "_hybrid_open_btn")))
    emit("the_old_load_plan_and_load_csv_buttons_are_one_browse", hasattr(inst, "_hybrid_load_btn") and not hasattr(inst, "_hybrid_csv_btn"))

    # ---- loading a plan: footage becomes rows of the existing Visual Plan table -----------------------
    ok = inst._hybrid_load_plan_file(str(PLAN_PATH))
    rows = inst._scene_rows
    emit("a_plan_file_loads_and_is_kept_in_the_project", ok and ws.hybrid_plan_path.is_file() and inst._hybrid_plan is not None)
    # ---- friendly panel: steps, timeline, chips, copy-the-prompt -----------------------------------------------------------------------
    labels = [l.cget("text") for l in inst._hybrid_step_labels]
    emit("the_four_steps_show_the_plan_as_done", len(labels) == 4 and labels[1].startswith("\u2713"), str(labels))
    inst._hybrid_draw_timeline()
    n_beats = len(inst._hybrid_plan.beats)
    emit("the_timeline_draws_one_block_per_beat", len(getattr(inst, "_hybrid_beat_boxes", [])) == n_beats and n_beats > 0, str(n_beats))
    inst._hybrid_select_beat(0)
    emit("clicking_a_beat_describes_it", inst._hybrid_beat_label.cget("text").startswith("Beat 1"), inst._hybrid_beat_label.cget("text"))
    emit("the_attention_list_is_filled_or_says_all_good", len(inst._hybrid_chips.winfo_children()) >= 1)
    _copied = []
    inst.clipboard_append = lambda text, **k: _copied.append(text)
    inst._hybrid_copy_prompt()
    emit("the_csv_prompt_is_copied_for_the_user", bool(_copied) and "BEAT PLAN" in _copied[0] and "copied" in inst._hybrid_status_var.get().lower(), repr(_copied)[:80] + inst._hybrid_status_var.get()[:30])
    wid = inst._hybrid_progress_start("Testing", "detail")
    emit("the_progress_card_shows_while_work_runs_and_the_main_button_waits", bool(inst._hybrid_progress_card.grid_info()))
    inst._hybrid_progress_update("part 2 of 5", wid, 0.4)
    emit("the_progress_text_and_bar_follow_the_work", inst._hybrid_progress_detail.cget("text") == "part 2 of 5" and abs(inst._hybrid_progress_bar.get() - 0.4) < 0.01)
    inst._hybrid_progress_done(wid, "done")
    emit("the_progress_card_goes_away_when_it_is_done", not inst._hybrid_progress_card.grid_info() and inst._hybrid_status_var.get() == "done")
    emit("friendly_words_for_the_directors_progress_lines", inst._hybrid_friendly("Hybrid Director: chapter 2/5 (6-12 min), attempt 1/2\u2026")[1] == 0.2 and "part 2 of 5" in inst._hybrid_friendly("Hybrid Director: chapter 2/5 (6-12 min), attempt 1/2\u2026")[0])
    emit("footage_clips_and_the_card_are_rows_map_beats_and_local_files_are_not",
         [(r.scene_number, r.asset_type) for r in rows] == [("1", "stock_video"), ("2", "image"), ("3", "stock_image")], str([(r.scene_number, r.asset_type) for r in rows]))
    emit("rows_say_which_beat_and_why", "Hybrid beat 02" in rows[0].script_segment and "clip 1/3" in rows[0].script_segment and "farmers at work" in rows[0].script_segment and "supporting card" in rows[2].script_segment, rows[0].script_segment)
    inst._refresh_scene_preview()
    emit("visiting_the_tab_does_not_wipe_them", len(inst._scene_rows) == 3 and inst._scene_rows_owner == "hybrid")
    emit("scene_actions_use_the_hybrid_images_folder", inst._scene_action_images_dir() == ws.hybrid_images_dir, str(inst._scene_action_images_dir()))
    emit("the_plan_view_lists_every_beat", all(s in inst._hybrid_plan_box.get("1.0", "end") for s in ("#1", "#2", "#3", "MAP+FOOTAGE", "FOOTAGE", "Visual Plan scene 1")), inst._hybrid_plan_box.get("1.0", "end")[:200])
    emit("button_says_generate_when_there_is_a_plan", inst._cta_action == "generate", inst._cta_action)

    # ---- the Visual Plan's own state: replaced, failed, ready --------------------------------------------
    from asset_manager import AssetManifest
    ws.hybrid_images_dir.mkdir(parents=True, exist_ok=True)
    (ws.hybrid_images_dir / "001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
    man = AssetManifest(ws.hybrid_images_dir)
    man.set("1", {"status": "complete", "source": "manual", "user_override": True, "local_path": str(ws.hybrid_images_dir / "001.png")})
    man.set("3", {"status": "failed", "source": "stock_image", "prompt": "glacier in the karakoram", "error": "No stock result"})
    inst._populate_hybrid_visual_plan()
    st = lambda i: inst._row_status_from_result(inst._scene_rows[i])
    emit("a_replaced_clip_shows_ready_a_failed_one_needs_action_with_its_reason",
         st(0) == "ready" and st(2) == "needs_action" and "No stock result" in str(getattr(inst._asset_results.get(_app._scene_key("3")), "error", "")), f"{st(0)} {st(1)} {st(2)}")
    emit("the_plan_view_shows_the_clip_states", "scene 1: ready" in inst._hybrid_plan_box.get("1.0", "end") or inst._hybrid_show_plan() is None)
    man.set("3", {})

    # ---- Plan with AI (a scripted Director) ---------------------------------------------------------------
    import hybrid.app_integration as hai
    from hybrid.plan import HybridPlan
    from hybrid.pipeline import PlanResult
    from hybrid.validate import validate
    canned = HybridPlan.load(PLAN_PATH)
    calls = {}
    def fake_plan(words, script, settings, **kw):
        calls.update(words=words, script=script, key=settings.get("gemini_api_key"), duration=kw.get("duration"))
        kw["on_progress"]("Hybrid Director: planning the beats (attempt 1/2)…")
        res = PlanResult(plan=canned, findings=validate(canned))
        res.repair_passes, res.repaired = 1, [["b2"]]
        return res
    hai.plan_with_ai = fake_plan
    inst._hybrid_plan = None; inst._hybrid_set_plan(None, None, save=False)
    inst.gemini_key_var.set("")
    inst._hybrid_plan_with_ai()
    emit("planning_without_a_gemini_key_says_so", "Gemini" in str(shown.get("error")) and not inst._hybrid_busy, str(shown.get("error"))[:80])
    shown.clear()
    inst.gemini_key_var.set("k-test")
    inst._vo_script_box.insert("1.0", "Pakistan is a long country.")
    went.clear()
    inst._hybrid_plan_with_ai()
    emit("planning_runs_in_the_background_and_locks_the_button", inst._hybrid_busy)
    yield (lambda: not inst._hybrid_busy)
    emit("the_file_row_says_a_plan_made_with_ai_is_that", inst._hybrid_file_var.get() == "Made with Plan with AI", inst._hybrid_file_var.get())
    emit("the_plan_arrives_in_the_project_and_the_table", inst._hybrid_plan is not None and len(inst._scene_rows) == 3 and ws.hybrid_plan_path.is_file() and (ws.hybrid_dir / "plan_report.json").is_file())
    emit("the_director_got_the_script_the_real_words_the_key_and_the_length", calls.get("script") == "Pakistan is a long country." and calls.get("words") == WORDS and calls.get("key") == "k-test" and abs(calls.get("duration") - 24.0) < 0.1, str((calls.get("script"), calls.get("key"), calls.get("duration"))))
    emit("repair_is_reported_and_the_user_is_sent_to_the_visual_plan", "Repaired 1 weak beat" in inst._hybrid_plan_box.get("1.0", "end") and went == ["visual_plan"], str(went))

    # ---- generation ------------------------------------------------------------------------------------------
    import hybrid.generate as hg
    from pakmap.app_integration import PakmapResult
    got = {}
    def fake_ok(plan, vo, out, **kw):
        got.update(kw, plan=plan, out=str(out))
        kw["progress_cb"]("Drawing the map…", 0.4); kw["log"]("[pakMap] fake")
        Path(out).write_bytes(b"x" * 10)
        return PakmapResult(True, [], Path(out), None, ["NASA credit"], ["a note"])
    hg.generate_hybrid_video = fake_ok
    inst._scene_rows[1].asset_type = "stock_video"; inst._scene_rows[1].prompt = ""; inst._scene_rows[1].stock = "canals at sunrise"   # the user changed clip 2's source in the table
    _asked.clear()
    inst._on_generate()
    emit("running_state_shows_stop", inst._hybrid_running and inst._cta_action == "hybrid_cancel")
    yield (lambda: not inst._hybrid_running)
    emit("a_run_finishes_and_the_video_is_reported", "Hybrid Map video ready" in str(shown.get("info")) and shown.get("preview") == got.get("out") and inst._cta_action == "generate", str(shown.get("info"))[:60])
    emit("generation_receives_the_table_as_the_user_left_it_the_folder_and_live_callbacks",
         [(r.scene_number, r.asset_type) for r in got["scene_rows"]] == [("1", "stock_video"), ("2", "stock_video"), ("3", "stock_image")]
         and got["media_dir"] == ws.hybrid_images_dir and sorted(got["media_callbacks"]) == ["on_manager_ready", "on_scene_complete", "on_scene_generating", "on_scene_start"], str(got.get("media_dir")))
    emit("it_renders_into_the_projects_work_folder_with_the_plan_and_settings",
         got["work_dir"] == ws.hybrid_work_dir and got["plan"] is inst._hybrid_plan and got["sound_design"] is True and Path(got["out"]).parent == ws.final_dir and got["whisper_words"] == WORDS, str(got.get("work_dir")))
    emit("no_flow_question_when_nothing_new_needs_flow", not _asked, str(_asked))
    shown.clear()

    inst._hybrid_sound_var.set(False); inst._save_hybrid_settings()
    emit("the_sound_switch_is_saved_in_the_project", ws.hybrid_settings().get("sound_design") is False, str(ws.hybrid_settings()))
    inst._hybrid_sound_var.set(True); inst._save_hybrid_settings()

    # Flow credits are asked for, and declining runs nothing
    from copy import deepcopy
    p2 = deepcopy(canned.to_dict()); p2["beats"][1]["footage"]["clips"][0]["asset"] = "flow_video:aerial of the Indus"
    inst._hybrid_load_plan_file(str(_write(p2)))
    _asked.clear(); _answer["v"] = False; got.clear()
    inst._on_generate()
    # scene 1 already has the user's own replacement (saved above): it must NOT be counted as new Flow work; only the canal picture is
    emit("declining_flow_credits_runs_nothing", len(_asked) == 1 and "1 clip(s)" in _asked[0] and "a canal at sunrise" in _asked[0] and "aerial of the Indus" not in _asked[0] and "credits" in _asked[0]
         and not inst._hybrid_running and not got, str(_asked)[:140])
    _answer["v"] = True
    fm = object(); inst._get_flow_engine_manager = lambda: fm; inst._video_account_ids = lambda: ["7"]
    inst._on_generate(); yield (lambda: not inst._hybrid_running)
    emit("accepting_passes_the_flow_manager_and_accounts", got.get("flow_engine_manager") is fm and got.get("flow_video_account_ids") == ["7"], str(got.get("flow_video_account_ids")))
    shown.clear()

    # an unresolved clip opens the Visual Plan; a plan with errors will not render
    hg.generate_hybrid_video = lambda *a, **kw: PakmapResult(False, ["Picture 1 (beat b2 · footage clip 1): no result"], unresolved=["1"])
    went.clear()
    inst._on_generate(); yield (lambda: not inst._hybrid_running)
    emit("an_unresolved_clip_opens_the_visual_plan", went == ["visual_plan"] and "need attention" in inst._hybrid_status_var.get(), str((went, inst._hybrid_status_var.get())))
    shown.clear(); got.clear()
    bad = deepcopy(canned.to_dict()); bad["beats"][2]["layers"][0]["place"] = "Nowhere At All"
    inst._hybrid_load_plan_file(str(_write(bad)))
    hg.generate_hybrid_video = fake_ok
    inst._on_generate()
    emit("a_plan_with_errors_will_not_render_and_says_why", "Fix the plan first" in str(shown.get("error")) and "Nowhere At All" in str(shown.get("error")) and not got and not inst._hybrid_running, str(shown.get("error"))[:120])
    shown.clear()

    # ...and "Repair errors" sends only the broken beat back to the Director and replaces the plan with the repaired one
    import hybrid.pipeline as hp
    seen = {}
    def fake_repair(plan, words, llm, **kw):
        seen.update(words=words, key=llm.providers["gemini"].settings.get("gemini_api_key"), script=kw.get("script"))
        r = PlanResult(plan=canned, findings=validate(canned)); r.repair_passes, r.repaired = 1, [["b3"]]
        return r
    hp.repair_errors = fake_repair
    inst.gemini_key_var.set("k-test")
    inst._hybrid_repair_errors()
    yield (lambda: not inst._hybrid_busy)
    emit("repair_errors_replaces_the_plan_with_the_repaired_one_and_says_so",
         seen.get("words") == WORDS and seen.get("key") == "k-test" and not [f for f in validate(inst._hybrid_plan) if f.severity == "error"] and "no errors" in inst._hybrid_status_var.get(), inst._hybrid_status_var.get())
    shown.clear(); seen.clear()
    inst._hybrid_repair_errors()
    emit("repair_errors_with_nothing_to_repair_does_not_call_the_director", not seen and "no errors to repair" in inst._hybrid_status_var.get(), inst._hybrid_status_var.get())

    # Stop
    started = threading.Event()
    def slow(plan, vo, out, **kw):
        started.set()
        while not kw["cancel_check"]():
            time.sleep(0.01)
        return PakmapResult(False, ["Cancelled"], cancelled=True)
    hg.generate_hybrid_video = slow
    inst._hybrid_load_plan_file(str(PLAN_PATH))
    inst._on_generate()
    yield (lambda: started.is_set())
    inst._on_primary_cta()
    yield (lambda: not inst._hybrid_running)
    emit("stop_cancels_the_run", inst._hybrid_status_var.get() == "Cancelled" and inst._cta_action == "generate", inst._hybrid_status_var.get())
    shown.clear()

    # ---- a Hybrid CSV, read against the project's narration ----------------------------------------------------------
    csv_path = tmp / "hybrid.csv"
    FOOTP = '"{""cover_ui"": true, ""dissolve_s"": 0.5, ""kenburns"": ""auto"", ""fit"": ""slow""}"'
    csv_path.write_text("\n".join([
        "item_no,vo_anchor,offset_s,layer_type,layer_id,geo_ref,label_text,sub_text,color_role,value_from,value_to,value_format,anchor,asset_path,camera_action,frame,line_kind,hold,params",
        "1,pakistan,,camera,c0,Pakistan,,,,,,,,,start,globe,,,",
        "1,pakistan,1.4,camera,c1,Pakistan,,,,,,,,,fly_to,country,,,",
        "1,pakistan,,hud_title,,,PART 1,,,,,,,,,,,,",
        "1,w4,,pip,card1,Lahore,LAHORE,,,,,,tr,stock_image:old city gate in Lahore,,,,5,",
        f"1,w12,,media_full,f1,,,,,,,,,stock_video:wheat fields in Punjab,,,,4,{FOOTP}",
        "1,w22,,marker,m1,Lahore,LAHORE,,,,,,,,,,,,",
        f"1,w26,,media_full,f2,,,,,,,,,stock_video:river in the mountains,,,,4,{FOOTP}",
    ]), encoding="utf-8")
    _asked.clear(); shown.clear()
    inst._hybrid_import_csv_file(str(csv_path))
    emit("loading_a_csv_runs_in_the_background_and_locks_the_buttons", inst._hybrid_busy)
    yield (lambda: not inst._hybrid_busy)
    modes = [b.mode for b in inst._hybrid_plan.beats]
    emit("the_csv_becomes_the_plan", "footage" in modes and "map_footage" in modes and len(inst._hybrid_plan.beats) >= 4, str(modes))
    emit("its_footage_and_card_are_rows_of_the_visual_plan", [r.asset_type for r in inst._scene_rows] == ["stock_image", "stock_video", "stock_video"], str([(r.scene_number, r.asset_type) for r in inst._scene_rows]))
    emit("the_plan_is_kept_in_the_project_and_the_status_says_so", ws.hybrid_plan_path.is_file() and "Imported hybrid.csv" in inst._hybrid_status_var.get(), inst._hybrid_status_var.get())
    emit("the_file_row_shows_which_csv_the_plan_came_from", inst._hybrid_file_var.get().endswith("hybrid.csv"), inst._hybrid_file_var.get())
    emit("it_has_no_errors_so_the_user_is_sent_to_the_visual_plan", went and went[-1] == "visual_plan", str(went))
    bad_csv = tmp / "bad.csv"
    bad_csv.write_text("item_no,vo_anchor,layer_type\n1,this is never said,marker\n", encoding="utf-8")
    before = inst._hybrid_plan
    inst._hybrid_import_csv_file(str(bad_csv))
    yield (lambda: not inst._hybrid_busy)
    emit("a_csv_with_a_fault_says_which_row_and_keeps_the_current_plan", inst._hybrid_plan is before and "problems" in inst._hybrid_plan_box.get("1.0", "end") and "row" in inst._hybrid_plan_box.get("1.0", "end"), inst._hybrid_plan_box.get("1.0", "end")[:160])
    inst._hybrid_load_plan_file(str(PLAN_PATH))     # back to the plan the persistence checks below expect

    # ---- persistence: reopening the project --------------------------------------------------------------------
    inst._hybrid_load_plan_file(str(PLAN_PATH))
    inst._hybrid_sound_var.set(False); inst._save_hybrid_settings(active=True)
    emit("active_style_and_plan_are_saved", ws.hybrid_settings() == {"sound_design": False, "active": True} and ws.hybrid_plan_path.is_file(), str(ws.hybrid_settings()))
    inst._hybrid_plan = None; inst._hybrid_sound_var.set(True)
    inst._hybrid_enabled_var.set(False); inst._hybrid_controls.grid_remove(); inst.generation_mode = "normal"; inst._scene_rows = []
    inst._bind_workspace_paths()
    emit("reopening_restores_plan_style_footage_rows_and_sound_switch",
         inst.generation_mode == "hybrid" and inst._hybrid_enabled_var.get() and inst._hybrid_plan is not None and len(inst._scene_rows) == 3 and inst._hybrid_sound_var.get() is False and [b.id for b in inst._hybrid_plan.beats] == ["b1", "b2", "b3"],
         f"{inst.generation_mode} {len(inst._scene_rows)}")
    emit("a_replacement_made_before_survives_the_reopen", inst._row_status_from_result(inst._scene_rows[0]) == "ready")
    # a different, empty project: nothing of Hybrid shows
    ws2 = ProjectWorkspace(project_id="p2", title="Other", seq=2, root=tmp / "proj2")
    for d in ("csv", "assets", "audio", "logs", "final", "flow"):
        (ws2.root / d).mkdir(parents=True, exist_ok=True)
    inst._workspace = ws2
    inst._bind_workspace_paths()
    emit("another_project_starts_clean_and_the_first_keeps_its_flag", inst.generation_mode == "normal" and inst._hybrid_plan is None and inst._scene_rows == [] and not inst._hybrid_enabled_var.get() and ws.hybrid_settings().get("active") is True,
         f"{inst.generation_mode} {inst._hybrid_plan} {ws.hybrid_settings()}")
    inst._workspace = ws
    inst._bind_workspace_paths()
    emit("and_coming_back_restores_it_again", inst.generation_mode == "hybrid" and inst._hybrid_plan is not None)

    # ---- fixing one CSV cell inside the app ------------------------------------------------------------------------------------------
    csvp = tmp / "cells.csv"
    csvp.write_text("beat,row,start,end,mode,place,frame,asset,t,label,why\n"
                    "b1,beat,0,10,map_footage,Pennsylvania,region,,,,a full state\n"
                    "b1,card,,,,,,stock_image:a steel mill at night,2,STEEL,\n"
                    "b2,beat,10,24,map,Great Lakez,region,,,,the lakes\n", encoding="utf-8")
    inst._hybrid_load_plan_file(str(csvp))
    def chip_texts():
        out = []
        for line in inst._hybrid_chips.winfo_children():
            for w in line.winfo_children():
                try:
                    out.append(w.cget("text"))
                except Exception:
                    pass
        return out
    texts = chip_texts()
    emit("an_error_names_its_row_and_column_and_offers_fix", any("Row 4" in t and "place" in t for t in texts) and "Fix" in texts, str(texts)[:300])
    from hybrid import cell_fix
    from hybrid.validate import validate as _v
    f = next(x for x in _v(inst._hybrid_plan) if x.code == "unresolved_place")
    cell = cell_fix.cell_for_finding(csvp.read_text(), inst._hybrid_plan, f)
    inst._hybrid_open_cell_editor(str(csvp), cell)
    win = inst._hybrid_cell_win
    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)
    widgets = list(walk(win))
    tips = [w for w in widgets if w.__class__.__name__ == "CTkButton" and w.cget("text") == "Great Lakes"]
    emit("the_editor_suggests_a_place_the_atlas_knows", bool(tips), str([w.cget("text") for w in widgets if w.__class__.__name__ == "CTkButton"]))
    if tips:
        tips[0].invoke()
    apply_btn = next(w for w in widgets if w.__class__.__name__ == "CTkButton" and w.cget("text") == "Apply")
    apply_btn.invoke()
    emit("apply_fixes_the_plan_and_writes_the_file_keeping_the_original",
         "Great Lakes," in csvp.read_text() and (tmp / "cells.original.csv").is_file() and not [x for x in _v(inst._hybrid_plan) if x.severity == "error"]
         and not getattr(inst, "_hybrid_cell_editor_open", True), inst._hybrid_status_var.get())

def _write(d):
    p = tmp / f"p_{abs(hash(json.dumps(d, sort_keys=True)))}.json"
    p.write_text(json.dumps(d)); return p

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
        emit("scenario_crashed", False, traceback.format_exc().replace("\n", " | ")[-600:])
        finish()

inst.after(100, tick)
inst.mainloop()
'''


class TestHybridInTheApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        script = Path(tempfile.mkdtemp()) / "_hybrid_app_check.py"
        script.write_text(_SCRIPT, encoding="utf-8")
        env = dict(os.environ, HYBRID_PLAN_JSON=str(PLAN_JSON))
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300, cwd=Path(__file__).resolve().parent, env=env)
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
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout[-2000:]}\nstderr:\n{self._stderr[-2500:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def _all(self, *names):
        for n in names:
            with self.subTest(n):
                self._check(n)

    def test_the_third_style_switch(self):
        self._all("starts_off_and_hidden", "switch_turns_hybrid_on", "button_asks_for_the_voiceover_first", "then_for_the_plan",
                  "pakmap_takes_over_from_hybrid", "hybrid_takes_over_from_pakmap", "overscaled_takes_over_from_hybrid")

    def test_the_panel_has_pakmaps_layout(self):
        self._all("the_panel_follows_pakmaps_layout_row_for_row", "it_has_check_plan_and_the_ai_actions_as_buttons", "the_old_load_plan_and_load_csv_buttons_are_one_browse")

    def test_footage_is_rows_of_the_existing_visual_plan(self):
        self._all("the_four_steps_show_the_plan_as_done", "the_timeline_draws_one_block_per_beat", "clicking_a_beat_describes_it", "the_attention_list_is_filled_or_says_all_good",
                  "the_csv_prompt_is_copied_for_the_user", "the_progress_card_shows_while_work_runs_and_the_main_button_waits", "the_progress_text_and_bar_follow_the_work",
                  "the_progress_card_goes_away_when_it_is_done", "friendly_words_for_the_directors_progress_lines")
        self._all("a_plan_file_loads_and_is_kept_in_the_project", "footage_clips_and_the_card_are_rows_map_beats_and_local_files_are_not", "rows_say_which_beat_and_why",
                  "visiting_the_tab_does_not_wipe_them", "scene_actions_use_the_hybrid_images_folder", "the_plan_view_lists_every_beat",
                  "button_says_generate_when_there_is_a_plan")

    def test_replaced_and_failed_clips_show_their_state(self):
        self._all("a_replaced_clip_shows_ready_a_failed_one_needs_action_with_its_reason", "the_plan_view_shows_the_clip_states")

    def test_planning_with_ai(self):
        self._all("planning_without_a_gemini_key_says_so", "planning_runs_in_the_background_and_locks_the_button", "the_plan_arrives_in_the_project_and_the_table",
                  "the_director_got_the_script_the_real_words_the_key_and_the_length", "repair_is_reported_and_the_user_is_sent_to_the_visual_plan")

    def test_generation(self):
        self._all("running_state_shows_stop", "a_run_finishes_and_the_video_is_reported", "generation_receives_the_table_as_the_user_left_it_the_folder_and_live_callbacks",
                  "it_renders_into_the_projects_work_folder_with_the_plan_and_settings", "no_flow_question_when_nothing_new_needs_flow", "the_sound_switch_is_saved_in_the_project",
                  "declining_flow_credits_runs_nothing", "accepting_passes_the_flow_manager_and_accounts", "an_unresolved_clip_opens_the_visual_plan",
                  "a_plan_with_errors_will_not_render_and_says_why", "repair_errors_replaces_the_plan_with_the_repaired_one_and_says_so",
                  "repair_errors_with_nothing_to_repair_does_not_call_the_director", "stop_cancels_the_run")

    def test_loading_a_hybrid_csv(self):
        self._all("loading_a_csv_runs_in_the_background_and_locks_the_buttons", "the_csv_becomes_the_plan", "its_footage_and_card_are_rows_of_the_visual_plan",
                  "the_plan_is_kept_in_the_project_and_the_status_says_so", "the_file_row_shows_which_csv_the_plan_came_from", "it_has_no_errors_so_the_user_is_sent_to_the_visual_plan",
                  "a_csv_with_a_fault_says_which_row_and_keeps_the_current_plan")

    def test_persistence_and_reopening(self):
        self._all("active_style_and_plan_are_saved", "reopening_restores_plan_style_footage_rows_and_sound_switch", "a_replacement_made_before_survives_the_reopen",
                  "another_project_starts_clean_and_the_first_keeps_its_flag", "and_coming_back_restores_it_again")

    def test_fixing_one_csv_cell_in_the_app(self):
        self._all("an_error_names_its_row_and_column_and_offers_fix", "the_editor_suggests_a_place_the_atlas_knows",
                  "apply_fixes_the_plan_and_writes_the_file_keeping_the_original")


if __name__ == "__main__":
    unittest.main()
