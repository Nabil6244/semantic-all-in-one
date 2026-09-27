"""Regression test for a real reported bug: Overscaled/Exp Solar's bulk
"Change Source" action only mutated in-memory self._scene_rows / a separate
legacy AssetManager — it never reached the CSV file that
_run_overscaled_generation actually re-reads and recompiles at Generate
time. Rows the Local Visual Planner left with a blank asset_type default to
Flow (its legacy-format convention: "a prompt always meant an AI image"),
so choosing "stock" in the UI and then clicking Generate still launched
Flow's Playwright-driven Chrome automation.

Fix: _apply_overscaled_source_override() writes the chosen provider's
asset_type/prompt directly into the CSV file for the selected scene(s) —
the one thing both compile_overscaled_csv and generate_scene_graph_local_
planner already always respect verbatim — then reloads the Visual Plan.

Follows the same real-subprocess "live check" convention as
test_overscaled_ui_integration.py / test_overscaled_visual_plan_preview_
workflow.py (a real CTk() root corrupts global Tk image-name state built
in-process).
"""

from __future__ import annotations

import inspect
import unittest


class TestChangeSourceOverrideWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls._app = _app

    def test_scene_action_with_source_routes_overscaled_mode_to_the_csv_override(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._scene_action_with_source)
        self.assertIn('generation_mode == "overscaled"', src)
        self.assertIn("_apply_overscaled_source_override", src)

    def test_bulk_dialog_routes_overscaled_mode_to_the_csv_override(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._change_source_dialog_bulk)
        self.assertIn('generation_mode == "overscaled"', src)
        self.assertIn("_apply_overscaled_source_override", src)

    def test_fix_all_issues_does_not_use_the_wrong_images_dir_in_overscaled_mode(self):
        # Was silently building an AssetManager rooted at self.images_var
        # (never populated for Overscaled/Exp Solar) and running the
        # normal-workflow-only VQA report system — now guarded instead.
        src = inspect.getsource(self._app.VideoGeneratorApp._on_fix_all_visual_issues)
        self.assertIn('generation_mode == "overscaled"', src)


_LIVE_CHECK_SCRIPT = r'''
import os
import sys
import csv
import tempfile
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())

def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}")

from tkinter import messagebox
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

from providers.base import SceneRow
from providers.router import SceneAssetRouter

tmp = Path(tempfile.mkdtemp())
csv_path = tmp / "plan.csv"
with open(csv_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["scene_number", "script_segment"])
    w.writerow(["1", "A quiet observatory sits atop a remote mountain."])
    w.writerow(["2", "The turbine spins rapidly to generate power."])

instance._overscaled_use_local_planner_var.set(True)
instance._overscaled_csv_var.set(str(csv_path))
loaded = instance._load_overscaled_csv(str(csv_path))
emit("csv_loads_via_local_planner", loaded, "")

row2_before = next((r for r in instance._scene_rows if r.scene_number == "2"), None)
emit(
    "planner_infers_video_for_motion_verb_before_override",
    row2_before is not None and row2_before.asset_type == "video",
    repr(row2_before.asset_type if row2_before else None),
)

# Reproduce the SECOND reported bug: a scene that previously FAILED (e.g.
# a Flow RPC rejection) keeps showing that stale error/NEEDS_ACTION status
# after being switched to a different source, because the on-disk manifest
# record and self._asset_results were never invalidated.
from asset_manager import AssetManifest
from providers.base import AssetResult, AssetSource as _AssetSource, SceneStatus
from project_workspace import ProjectWorkspace

instance._workspace = ProjectWorkspace(project_id="p1", title="t", seq=1, root=tmp / "ws")
images_dir = instance._workspace.overscaled_images_dir
images_dir.mkdir(parents=True, exist_ok=True)
manifest = AssetManifest(images_dir)
manifest.set("1", {"status": "failed", "error": "Flow RPC rejected: PUBLIC_ERROR_UNUSUAL_ACTIVITY"})
instance._asset_results["001"] = AssetResult(
    scene_number="1", path=None, media_type=None, source=_AssetSource.LOCAL,
    status=SceneStatus.NEEDS_ACTION, error="Flow RPC rejected: PUBLIC_ERROR_UNUSUAL_ACTIVITY",
)

# The reported bug: switch to stock, confirm it lands in the CSV FILE
# ITSELF (what Generate actually re-reads), not just the in-memory table.
instance.generation_mode = "overscaled"
instance._apply_overscaled_source_override(["1", "2"], "stock_image")

reloaded_manifest_record = AssetManifest(images_dir).get("1")
emit(
    "stale_failed_manifest_record_is_cleared",
    reloaded_manifest_record in (None, {}),
    repr(reloaded_manifest_record),
)
row1_status = instance._asset_results.get("001")
emit(
    "stale_needs_action_status_is_cleared_after_override",
    row1_status is None or row1_status.status != SceneStatus.NEEDS_ACTION,
    repr(row1_status.status if row1_status else None),
)

# The CSV Generate compiles is whatever _overscaled_csv_var points at — with
# a project open, that is the PROJECT's own copy (the same file
# _run_overscaled_generation persists), never the user's original file.
generate_csv_path = Path(instance._overscaled_csv_var.get())
with open(generate_csv_path, newline="") as f:
    rows_on_disk = list(csv.DictReader(f))
emit(
    "override_persists_to_the_csv_file_on_disk",
    all(r.get("asset_type") == "stock_image" for r in rows_on_disk),
    str(rows_on_disk),
)
with open(csv_path, newline="") as f:
    original_rows = list(csv.DictReader(f))
emit(
    "users_original_csv_file_is_not_modified",
    generate_csv_path != csv_path and all("asset_type" not in r for r in original_rows),
    f"{generate_csv_path} {original_rows}",
)

# Visual Plan reloaded automatically — badge must now show stock, not Flow.
row1_after = next((r for r in instance._scene_rows if r.scene_number == "1"), None)
row2_after = next((r for r in instance._scene_rows if r.scene_number == "2"), None)
emit(
    "row1_classifies_as_stock_not_flow",
    row1_after is not None and SceneAssetRouter.classify(row1_after) == _app.AssetSource.STOCK_IMAGE,
    repr(SceneAssetRouter.classify(row1_after) if row1_after else None),
)
emit(
    "row2_motion_verb_row_also_overridden_to_stock",
    row2_after is not None and SceneAssetRouter.classify(row2_after) == _app.AssetSource.STOCK_IMAGE,
    repr(SceneAssetRouter.classify(row2_after) if row2_after else None),
)

# The bug found live: the underlying self._scene_rows data updated
# correctly (proven above), but _render_scene_rows()'s scene_number-only
# signature cache skipped rebuilding row WIDGETS for the SAME set of
# scene_numbers — so the visible Src badge kept showing the OLD source
# (e.g. "AI Image") even though the header/sidebar counts and the
# underlying data were already correct. Check the actual rendered widget.
badge1 = instance._scene_row_widgets.get("001", {}).get("badge")
badge_text = badge1.cget("text") if badge1 is not None else None
emit(
    "row1_badge_widget_actually_shows_the_new_source",
    badge_text is not None and "stock" in badge_text.lower(),
    repr(badge_text),
)

# The override must have found a real, non-empty search query even though
# the bare 2-column CSV never had a prompt/stock column to reuse — this is
# the exact edge case that made the very first fix attempt silently no-op.
emit(
    "override_has_a_real_non_empty_query_not_a_blank_one",
    row1_after is not None and bool((row1_after.stock or row1_after.prompt or "").strip()),
    repr((row1_after.stock, row1_after.prompt) if row1_after else None),
)

sys.stdout.flush()
os._exit(0)
'''


class TestChangeSourceOverrideLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        script_path = Path(tempfile.mkdtemp()) / "_change_source_override_live_check.py"
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

    def test_csv_loads_via_local_planner(self):
        self._assert_check("csv_loads_via_local_planner")

    def test_planner_infers_video_for_motion_verb_before_override(self):
        self._assert_check("planner_infers_video_for_motion_verb_before_override")

    def test_override_persists_to_the_csv_file_on_disk(self):
        self._assert_check("override_persists_to_the_csv_file_on_disk")

    def test_row_classifies_as_stock_not_flow_after_override(self):
        self._assert_check("row1_classifies_as_stock_not_flow")

    def test_motion_verb_row_is_also_overridden_to_stock(self):
        self._assert_check("row2_motion_verb_row_also_overridden_to_stock")

    def test_override_has_a_real_query_even_from_a_bare_two_column_csv(self):
        self._assert_check("override_has_a_real_non_empty_query_not_a_blank_one")

    def test_stale_failed_manifest_record_is_cleared_on_override(self):
        self._assert_check("stale_failed_manifest_record_is_cleared")

    def test_stale_needs_action_status_is_cleared_on_override(self):
        self._assert_check("stale_needs_action_status_is_cleared_after_override")

    def test_row_badge_widget_actually_repaints_after_override(self):
        self._assert_check("row1_badge_widget_actually_shows_the_new_source")

    def test_users_original_csv_file_is_not_modified(self):
        self._assert_check("users_original_csv_file_is_not_modified")


if __name__ == "__main__":
    unittest.main()
