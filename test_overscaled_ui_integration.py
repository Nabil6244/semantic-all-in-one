"""Checks that Overscaled integrates into the EXISTING Visual Plan / Generate
workflow as a generation MODE — not a parallel UI.

Two layers:

  - TestOverscaledUIWiring: source-level checks (inspect.getsource()),
    following test_flow_reliability_audit.py's / test_structured_progress.py's
    established convention for app.py, for environments with no live
    display.

  - TestOverscaledLiveWidgetConstruction: instantiates the REAL
    VideoGeneratorApp (no .mainloop()) in an ISOLATED SUBPROCESS and drives
    the actual, real methods — proves:
      * importing an Overscaled CSV sets self.generation_mode = "overscaled",
        populates the SAME self._scene_rows / self._render_scene_rows() the
        normal CSV path uses (no second plan panel), and navigates to the
        EXISTING Visual Plan tab
      * there is no second "Generate Overscaled Video" button anywhere
      * the SHARED self._on_generate() (the same function the existing
        Generate button calls) routes to Overscaled generation when the
        mode is "overscaled", and leaves the normal path completely alone
        when it isn't
      * the resolved Pexels key / Flow engine manager reach the real call

    A real CTk() root was found to corrupt global Tk image-name state when
    constructed in-process (broke an unrelated, already-passing test in
    test_preview_player_audio.py via a stale PhotoImage collision) — exactly
    what test_structured_progress.py's own convention avoids. Isolating this
    check in its own throwaway process removes that risk entirely.
"""

from __future__ import annotations

import inspect
import unittest


class TestOverscaledUIWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls._app = _app

    def test_overscaled_section_has_no_generate_button(self):
        # The whole point of this integration: no second Generate button.
        src = inspect.getsource(self._app.VideoGeneratorApp._build_overscaled_section)
        self.assertNotIn("Generate Overscaled Video", src)
        self.assertIn("_browse_overscaled_csv", src)

    def test_shared_on_generate_routes_by_mode(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._on_generate)
        self.assertIn('self.generation_mode == "overscaled"', src)
        self.assertIn("self._run_overscaled_generation()", src)

    def test_shared_sync_primary_cta_routes_by_mode(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._sync_primary_cta)
        self.assertIn('self.generation_mode == "overscaled"', src)
        self.assertIn("self._sync_primary_cta_overscaled()", src)

    def test_generation_handler_calls_the_pure_pipeline_entry_point(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertIn("from scene_graph.app_integration import generate_overscaled_video", src)
        self.assertIn("generate_overscaled_video(", src)
        self.assertIn("threading.Thread", src)

    def test_generation_handler_persists_the_csv_into_the_project(self):
        # Regression: the normal workflow saves both the script and the CSV
        # into the project (_apply_ai_plan: ws.save_script + plan.write_csv),
        # so reopening a project restores its state. Overscaled previously
        # did neither — only the generated video was ever saved, so the CSV
        # that drove it vanished on reopen. Must copy into the project's own
        # overscaled_csv_path BEFORE generating, and update the CSV var to
        # the persisted copy (not the original, possibly-external, path).
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertIn("self._workspace.copy_overscaled_csv_in(", src)
        self.assertIn("self._overscaled_csv_var.set(csv_path)", src)

    def test_reopening_a_project_restores_its_saved_overscaled_csv(self):
        # The other half of the same fix: _bind_workspace_paths (which runs
        # on every project open/switch, mirroring how it restores
        # ws.csv_path / ws.script_path for the normal workflow) must also
        # restore ws.overscaled_csv_path if the project has one saved.
        src = inspect.getsource(self._app.VideoGeneratorApp._bind_workspace_paths)
        self.assertIn("ws.overscaled_csv_path.is_file()", src)
        self.assertIn("self._load_overscaled_csv(str(ws.overscaled_csv_path))", src)

    def test_generation_handler_resolves_the_same_pexels_key_and_flow_manager_as_normal_workflow(self):
        # Regression guard: Overscaled must reuse the SAME already-configured
        # Pexels key / Flow engine the normal workflow uses (app.py's own
        # pexels_key_var / _get_flow_engine_manager), not require a second,
        # separately-set API key — a real "media resolution failed: no
        # Pexels API key" error was hit before this was wired through.
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertIn("self.pexels_key_var.get()", src)
        self.assertIn('os.environ.get("PEXELS_API_KEY"', src)
        self.assertIn("self._get_flow_engine_manager()", src)
        self.assertIn("pexels_api_key=pexels_api_key", src)
        self.assertIn("flow_engine_manager=flow_engine_manager", src)

    def test_generation_handler_reuses_the_existing_voiceover_control(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertIn("self._current_voiceover_path()", src)
        self.assertNotIn("filedialog.askopenfilename", src)

    def test_csv_browser_reuses_existing_file_dialog_pattern(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._browse_overscaled_csv)
        self.assertIn("filedialog.askopenfilename", src)
        self.assertIn("CSV files", src)

    def test_csv_browser_feeds_the_existing_visual_plan_table(self):
        # Must populate self._scene_rows / call self._render_scene_rows()
        # using the EXISTING SceneRow model — never a bespoke plan widget.
        # The actual compile+populate body lives in _load_overscaled_csv,
        # shared with project-reopen restoration (_bind_workspace_paths);
        # _browse_overscaled_csv itself just picks a file and calls it.
        browse_src = inspect.getsource(self._app.VideoGeneratorApp._browse_overscaled_csv)
        self.assertIn("self._load_overscaled_csv(path)", browse_src)
        self.assertIn('self._goto_workflow_view("visual_plan")', browse_src)

        load_src = inspect.getsource(self._app.VideoGeneratorApp._load_overscaled_csv)
        self.assertIn("SceneRow.from_csv_row", load_src)
        self.assertIn("self._scene_rows = ", load_src)
        self.assertIn("self._render_scene_rows()", load_src)

    def test_generation_handler_never_touches_gemini_or_visual_director(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertNotIn("visual_director", src.lower())
        self.assertNotIn("gemini", src.lower())

    def test_ui_callbacks_are_dispatched_back_onto_the_main_thread(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertIn("self.after(0,", src)

    def test_normal_pipeline_body_is_unmodified_by_this_feature(self):
        # _run_pipeline (the actual normal-mode work) must not mention
        # anything Overscaled-specific — only _on_generate's top and
        # _sync_primary_cta's top gained a mode guard.
        src = inspect.getsource(self._app.VideoGeneratorApp._run_pipeline)
        self.assertNotIn("overscaled", src.lower())

    def test_refresh_scene_preview_guards_overscaled_mode(self):
        # Regression guard for the actual root cause of "Visual Plan shows
        # 0 scenes after importing an Overscaled CSV": VisualPlanView.on_show()
        # unconditionally calls _refresh_scene_preview() on every navigation
        # to Visual Plan (including the one _browse_overscaled_csv itself
        # triggers), which re-derives self._scene_rows from the EMPTY normal
        # self.csv_var and wipes out the just-loaded Overscaled plan.
        src = inspect.getsource(self._app.VideoGeneratorApp._refresh_scene_preview)
        self.assertIn('self.generation_mode == "overscaled"', src)

    def test_generation_handler_drives_the_visual_plan_status_column(self):
        # Regression guard: the Status column had no data source for
        # Overscaled rows at all (they never go through the normal per-scene
        # asset-resolution loop that drives it), so it sat on "QUEUED"
        # forever even while the log showed real, scene-by-scene activity.
        src = inspect.getsource(self._app.VideoGeneratorApp._run_overscaled_generation)
        self.assertIn("_classify_scene_status", src)
        self.assertIn("_set_scene_status", src)


class TestClassifySceneStatus(unittest.TestCase):
    """Pure-function checks for the log-line -> status-word classifier that
    now actually gets used (see TestOverscaledUIWiring above) — it existed
    unused in app.py before this feature wired it up."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls._classify = staticmethod(_app._classify_scene_status)

    def test_recognizes_ready_states(self):
        self.assertEqual(self._classify("LOCAL (cached, reusing)"), "ready")
        self.assertEqual(self._classify("Success"), "ready")

    def test_recognizes_in_progress_states(self):
        self.assertEqual(self._classify("searching video 'a bridge'"), "searching")
        self.assertEqual(self._classify("selected pexels asset 123"), "downloading")
        self.assertEqual(self._classify("generating image..."), "generating")
        self.assertEqual(self._classify("FAIL (score 0.57) — retry_same"), "retrying")

    def test_recognizes_failure(self):
        self.assertEqual(self._classify("FAILED: Download failed: timeout"), "failed")

    def test_unrecognized_routing_line_returns_none(self):
        # e.g. "STOCK_VIDEO" / "FLOW_VIDEO" routing decisions are not a status.
        self.assertIsNone(self._classify("STOCK_VIDEO"))


_LIVE_CHECK_SCRIPT = r'''
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)  # piped stdout is block-buffered by
# default; os._exit() below skips normal interpreter shutdown (and therefore
# the flush that would otherwise happen), so every print() must be flushed
# as it happens or it is silently discarded.
sys.path.insert(0, os.getcwd())  # this script lives in a tempdir, not the repo

def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}")

from tkinter import filedialog, messagebox
messagebox.showerror = lambda *a, **k: None
messagebox.showinfo = lambda *a, **k: None

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

try:
    instance = _app.VideoGeneratorApp()
    instance.withdraw()  # constructed for inspection only, never shown
except Exception as exc:  # no display / Tk can't open a window here
    print(f"SKIP:{exc}")
    os._exit(0)

# 1) Only ONE Generate button exists anywhere: no second widget was created.
emit("no_second_generate_button", not hasattr(instance, "_overscaled_generate_btn"), "")
emit("no_second_plan_panel", not hasattr(instance, "_overscaled_plan_panel"), "")
emit("generation_mode_starts_normal", instance.generation_mode == "normal", instance.generation_mode)

# 2) Card is mounted in the real scrollable frame and visible by default;
#    its controls (just a CSV picker now) start hidden.
emit("mounted_in_scroll", instance._overscaled_block.master is instance._scroll,
     instance._scroll.__class__.__name__)
emit("card_visible_by_default", bool(instance._overscaled_block.grid_info()), "")
emit("controls_start_hidden", not bool(instance._overscaled_controls.grid_info()), "")

# 3) Switch toggling flips generation_mode both ways.
instance._overscaled_enabled_var.set(True)
instance._on_overscaled_toggle()
instance.update_idletasks()
emit("switch_on_sets_overscaled_mode", instance.generation_mode == "overscaled", instance.generation_mode)
instance._overscaled_enabled_var.set(False)
instance._on_overscaled_toggle()
instance.update_idletasks()
emit("switch_off_restores_normal_mode", instance.generation_mode == "normal", instance.generation_mode)

# 4) Importing a real Overscaled CSV: compiles, sets mode, feeds the
#    EXISTING Visual Plan table, and navigates there — Test 1/2 from spec.
view_before = instance._shell.active_view
filedialog.askopenfilename = lambda **kw: os.path.abspath("overscaled_sample.csv")
instance._browse_overscaled_csv()
instance.update_idletasks()

emit("started_on_script_view", view_before == "script", view_before)
emit("import_sets_overscaled_mode", instance.generation_mode == "overscaled", instance.generation_mode)
emit("import_navigates_to_visual_plan", instance._shell.active_view == "visual_plan", instance._shell.active_view)
emit("existing_scene_table_is_populated", len(instance._scene_rows) == 7, str(len(instance._scene_rows)))
if instance._scene_rows:
    row3 = next((r for r in instance._scene_rows if r.scene_number == "3"), None)
    emit("asset_type_preserved_on_existing_row_model", row3 is not None and row3.asset_type == "stock_image",
         repr(row3.asset_type if row3 else None))
    emit("role_enrichment_present_in_script_segment", row3 is not None and row3.script_segment.startswith("[entity]"),
         repr(row3.script_segment if row3 else None))
else:
    emit("asset_type_preserved_on_existing_row_model", False, "no scene rows")
    emit("role_enrichment_present_in_script_segment", False, "no scene rows")
emit("existing_scene_table_widget_is_visible", bool(instance._scenes_wrap.grid_info()), "")

# 5) The SHARED _on_generate() (same entry point the existing Generate
#    button calls via _on_primary_cta) routes to Overscaled when mode is
#    "overscaled" — Test 3 from spec.
calls = []

def fake_generate(*args, **kwargs):
    calls.append((args, kwargs))
    from scene_graph.app_integration import OverscaledGenerationResult
    return OverscaledGenerationResult(ok=True, errors=[], output_path=None)

tmp_root = Path(tempfile.mkdtemp())
instance._current_voiceover_path = lambda: Path(__file__)  # Test 5: existing voiceover state reused
instance._workspace = type("W", (), {
    "root": tmp_root,
    # _run_overscaled_generation now persists the chosen CSV into the
    # project (see project_workspace.copy_overscaled_csv_in) before
    # generating — this fake workspace only cares about dispatch, so it
    # just hands the same path back unchanged.
    "copy_overscaled_csv_in": lambda self, src: src,
})()
instance.pexels_key_var.set("fake-pexels-key-for-test")

import scene_graph.app_integration as real_module
real_module.generate_overscaled_video = fake_generate

instance.generation_mode = "overscaled"
instance._on_generate()
for _ in range(50):
    if calls:
        break
    time.sleep(0.05)
emit("shared_generate_routes_to_overscaled", bool(calls), str(calls[:1]))
if calls:
    args, kwargs = calls[0]
    emit("existing_voiceover_path_passed_through", args[1] == __file__, repr(args[1]))
    emit("pexels_key_passed_through", kwargs.get("pexels_api_key") == "fake-pexels-key-for-test",
         repr(kwargs.get("pexels_api_key")))
    emit("flow_engine_manager_passed_through", kwargs.get("flow_engine_manager") is not None,
         repr(kwargs.get("flow_engine_manager")))
else:
    emit("existing_voiceover_path_passed_through", False, "no call captured")
    emit("pexels_key_passed_through", False, "no call captured")
    emit("flow_engine_manager_passed_through", False, "no call captured")

# 6) The SAME SHARED _on_generate() does NOT route to Overscaled when mode
#    is "normal" — Test 4 from spec. _revalidate_license is neutralized
#    (no real auth/network dependency belongs in this check) and
#    self._workspace=None forces the normal path's own existing early
#    return, so nothing beyond the mode check itself is exercised here.
overscaled_spy_calls = []
instance._run_overscaled_generation = lambda: overscaled_spy_calls.append(True)
instance._revalidate_license = lambda: (True, "")
instance.generation_mode = "normal"
instance._workspace = None
instance._on_generate()
emit("normal_mode_does_not_route_to_overscaled", overscaled_spy_calls == [], str(overscaled_spy_calls))

sys.stdout.flush()
os._exit(0)  # hard exit: a throwaway process, skip thread-join/Tk teardown entirely
'''


class TestOverscaledLiveWidgetConstruction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        script_path = Path(tempfile.mkdtemp()) / "_overscaled_live_check.py"
        script_path.write_text(_LIVE_CHECK_SCRIPT, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=60,
            cwd=Path(__file__).resolve().parent,
        )
        cls._stdout = proc.stdout
        cls._stderr = proc.stderr
        cls._results = {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[len("SKIP:"):])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._results[name] = (status == "PASS", detail)

    def _assert_check(self, name: str) -> None:
        if name not in self._results:
            self.fail(f"subprocess never reported {name!r}\nstdout:\n{self._stdout}\nstderr:\n{self._stderr[-2000:]}")
        ok, detail = self._results[name]
        self.assertTrue(ok, f"{name} failed: {detail}\nstderr:\n{self._stderr[-2000:]}")

    def test_no_second_generate_button_exists(self):
        self._assert_check("no_second_generate_button")

    def test_no_second_plan_panel_exists(self):
        self._assert_check("no_second_plan_panel")

    def test_generation_mode_starts_normal(self):
        self._assert_check("generation_mode_starts_normal")

    def test_overscaled_card_is_mounted_in_the_real_scrollable_frame(self):
        self._assert_check("mounted_in_scroll")

    def test_overscaled_card_is_visible_by_default(self):
        self._assert_check("card_visible_by_default")

    def test_controls_start_hidden_but_card_itself_does_not(self):
        self._assert_check("controls_start_hidden")

    def test_switch_toggles_generation_mode_both_ways(self):
        self._assert_check("switch_on_sets_overscaled_mode")
        self._assert_check("switch_off_restores_normal_mode")

    def test_importing_csv_sets_mode_and_navigates_to_visual_plan(self):
        self._assert_check("started_on_script_view")
        self._assert_check("import_sets_overscaled_mode")
        self._assert_check("import_navigates_to_visual_plan")

    def test_importing_csv_populates_the_existing_visual_plan_table(self):
        self._assert_check("existing_scene_table_is_populated")
        self._assert_check("existing_scene_table_widget_is_visible")

    def test_asset_type_is_preserved_on_the_existing_row_model(self):
        self._assert_check("asset_type_preserved_on_existing_row_model")

    def test_semantic_role_is_visible_without_a_new_widget(self):
        self._assert_check("role_enrichment_present_in_script_segment")

    def test_shared_generate_button_routes_to_overscaled_when_mode_is_overscaled(self):
        self._assert_check("shared_generate_routes_to_overscaled")

    def test_existing_voiceover_state_is_reused_for_generation(self):
        self._assert_check("existing_voiceover_path_passed_through")

    def test_pexels_key_is_resolved_and_passed_through(self):
        self._assert_check("pexels_key_passed_through")

    def test_flow_engine_manager_is_resolved_and_passed_through(self):
        self._assert_check("flow_engine_manager_passed_through")

    def test_shared_generate_button_does_not_route_to_overscaled_when_mode_is_normal(self):
        self._assert_check("normal_mode_does_not_route_to_overscaled")


if __name__ == "__main__":
    unittest.main()
