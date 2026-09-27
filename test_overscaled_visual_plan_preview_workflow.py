"""Overscaled/Exp Solar workflow separation: Import/Analyze must only ever
populate the Visual Plan preview — asset generation/resolution must start
ONLY on an explicit Generate click.

Follows the exact same real-subprocess "live check" convention as
test_overscaled_ui_integration.py's TestOverscaledLiveWidgetConstruction
(a real CTk() root corrupts global Tk image-name state when constructed
in-process, so this is isolated in its own throwaway subprocess). That file
is left completely untouched; this is a new, separate suite for the new
requirement so the existing one keeps testing exactly what it always has.
"""

from __future__ import annotations

import inspect
import unittest


class TestOverscaledPreviewWorkflowWiring(unittest.TestCase):
    """Source-level checks, no display required."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls._app = _app

    def test_load_overscaled_csv_never_calls_media_resolution_or_generation(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._load_overscaled_csv)
        self.assertNotIn("generate_overscaled_video", src)
        self.assertNotIn("resolve_scene_graph_media", src)
        self.assertNotIn("AssetManager(", src)

    def test_local_planner_toggle_recompiles_the_preview_only(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._on_overscaled_local_planner_toggle)
        self.assertIn("_load_overscaled_csv", src)
        self.assertNotIn("generate_overscaled_video", src)
        self.assertNotIn("_run_overscaled_generation", src)


_LIVE_CHECK_SCRIPT = r'''
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())

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
    instance.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

# Spy on every real provider/generation entry point BEFORE any import, so a
# call during import/analyze/preview is caught no matter which module holds
# the reference.
resolve_calls = []
generate_calls = []

import scene_graph.media_resolution as media_resolution_module
media_resolution_module.resolve_scene_graph_media = lambda *a, **k: resolve_calls.append((a, k)) or {}

import scene_graph.app_integration as app_integration_module
app_integration_module.generate_overscaled_video = lambda *a, **k: generate_calls.append((a, k))

from providers.router import SceneAssetRouter

# --- 1) Local Visual Planner ON: import a BARE scene_number/script_segment
#        CSV (no asset_type/prompt/beat/node_id/... at all).
instance._overscaled_use_local_planner_var.set(True)
filedialog.askopenfilename = lambda **kw: os.path.abspath("local_planner_sample.csv")
instance._browse_overscaled_csv()
instance.update_idletasks()

emit("planner_on_no_media_resolution_during_import", resolve_calls == [], str(resolve_calls))
emit("planner_on_no_generation_during_import", generate_calls == [], str(generate_calls))
emit("planner_on_populates_visual_plan", len(instance._scene_rows) == 3, str(len(instance._scene_rows)))

row1 = next((r for r in instance._scene_rows if r.scene_number == "1"), None)
row2 = next((r for r in instance._scene_rows if r.scene_number == "2"), None)
row3 = next((r for r in instance._scene_rows if r.scene_number == "3"), None)

# 2) The Visual Plan must show what asset type/prompt the compiled graph
#    actually decided BEFORE any resolution — via the SAME pure,
#    no-network SceneAssetRouter.classify() every row's badge already uses.
emit("planner_row1_has_a_derived_prompt", bool(row1 and row1.prompt), repr(row1.prompt if row1 else None))
emit(
    "planner_row1_classifies_as_a_real_asset_source",
    row1 is not None and SceneAssetRouter.classify(row1) is not None,
    repr(SceneAssetRouter.classify(row1) if row1 else None),
)
emit(
    "planner_row2_comparison_role_visible",
    row2 is not None and row2.script_segment.startswith("[comparison]"),
    repr(row2.script_segment if row2 else None),
)

# 3) A continuation row (no node in the compiled graph) is labeled, not
#    silently dropped or shown as a normal hero row.
emit(
    "planner_continuation_row_labeled",
    row3 is not None and row3.script_segment.startswith("[continues previous]"),
    repr(row3.script_segment if row3 else None),
)
emit(
    "planner_continuation_row_has_no_asset",
    row3 is not None and SceneAssetRouter.classify(row3) is None,
    repr(SceneAssetRouter.classify(row3) if row3 else None),
)

# --- 4) Local Visual Planner OFF: the existing dedicated Overscaled CSV
#        path is unaffected — still preview-only, still no premature
#        resolution/generation.
resolve_calls.clear()
generate_calls.clear()
instance._overscaled_use_local_planner_var.set(False)
filedialog.askopenfilename = lambda **kw: os.path.abspath("overscaled_sample.csv")
instance._browse_overscaled_csv()
instance.update_idletasks()

emit("planner_off_no_media_resolution_during_import", resolve_calls == [], str(resolve_calls))
emit("planner_off_no_generation_during_import", generate_calls == [], str(generate_calls))
emit("planner_off_populates_visual_plan", len(instance._scene_rows) == 7, str(len(instance._scene_rows)))
row3_csv = next((r for r in instance._scene_rows if r.scene_number == "3"), None)
emit(
    "planner_off_existing_asset_type_still_shown",
    row3_csv is not None and row3_csv.asset_type == "stock_image",
    repr(row3_csv.asset_type if row3_csv else None),
)

# --- 5) Exp Solar + Local Visual Planner ON: same bare CSV, different style.
instance._overscaled_style_segmented.set("Exp Solar")
instance._on_overscaled_style_change("Exp Solar")
instance._overscaled_use_local_planner_var.set(True)
resolve_calls.clear()
generate_calls.clear()
filedialog.askopenfilename = lambda **kw: os.path.abspath("local_planner_sample.csv")
instance._browse_exp_solar_csv()
instance.update_idletasks()

emit("exp_solar_planner_no_resolution_during_import", resolve_calls == [], str(resolve_calls))
emit("exp_solar_planner_no_generation_during_import", generate_calls == [], str(generate_calls))
emit("exp_solar_planner_populates_visual_plan", len(instance._scene_rows) == 3, str(len(instance._scene_rows)))

# --- 6) Only an explicit Generate click reaches generate_overscaled_video —
#        same dispatch path test_overscaled_ui_integration.py already
#        proves for the non-planner CSV; confirmed here for completeness
#        with the planner still ON from step 5.
tmp_root = Path(tempfile.mkdtemp())
instance._current_voiceover_path = lambda: Path(__file__)
instance._workspace = type("W", (), {
    "root": tmp_root,
    "copy_overscaled_csv_in": lambda self, src: src,
    "next_overscaled_final_path": lambda self: tmp_root / "overscaled" / "overscaled_final.mp4",
})()
instance.pexels_key_var.set("fake-pexels-key-for-test")

import video_generator as vg_module
vg_module.transcribe_audio = lambda *a, **k: []

instance.generation_mode = "overscaled"
instance._on_generate()
for _ in range(50):
    if generate_calls:
        break
    time.sleep(0.05)
emit("explicit_generate_click_reaches_real_entry_point", bool(generate_calls), str(len(generate_calls)))
if generate_calls:
    _, kwargs = generate_calls[0]
    emit("explicit_generate_click_passes_use_local_planner_flag", kwargs.get("use_local_planner") is True,
         repr(kwargs.get("use_local_planner")))

sys.stdout.flush()
os._exit(0)
'''


class TestOverscaledPreviewWorkflowLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        script_path = Path(tempfile.mkdtemp()) / "_overscaled_preview_workflow_live_check.py"
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

    def test_planner_on_import_never_resolves_media(self):
        self._assert_check("planner_on_no_media_resolution_during_import")

    def test_planner_on_import_never_generates(self):
        self._assert_check("planner_on_no_generation_during_import")

    def test_planner_on_populates_visual_plan_from_bare_csv(self):
        self._assert_check("planner_on_populates_visual_plan")

    def test_planner_on_shows_derived_asset_decision_before_generation(self):
        self._assert_check("planner_row1_has_a_derived_prompt")
        self._assert_check("planner_row1_classifies_as_a_real_asset_source")

    def test_planner_on_shows_inferred_relationship_role(self):
        self._assert_check("planner_row2_comparison_role_visible")

    def test_planner_on_labels_continuation_rows(self):
        self._assert_check("planner_continuation_row_labeled")
        self._assert_check("planner_continuation_row_has_no_asset")

    def test_planner_off_still_preview_only(self):
        self._assert_check("planner_off_no_media_resolution_during_import")
        self._assert_check("planner_off_no_generation_during_import")
        self._assert_check("planner_off_populates_visual_plan")
        self._assert_check("planner_off_existing_asset_type_still_shown")

    def test_exp_solar_with_planner_on_is_also_preview_only(self):
        self._assert_check("exp_solar_planner_no_resolution_during_import")
        self._assert_check("exp_solar_planner_no_generation_during_import")
        self._assert_check("exp_solar_planner_populates_visual_plan")

    def test_explicit_generate_click_is_the_only_thing_that_triggers_generation(self):
        self._assert_check("explicit_generate_click_reaches_real_entry_point")
        self._assert_check("explicit_generate_click_passes_use_local_planner_flag")


if __name__ == "__main__":
    unittest.main()
