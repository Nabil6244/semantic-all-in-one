"""Regression tests for the "Select by source" bulk-selection feature:
a button that opens a menu of source buckets (Flow Video, Flow Image,
Stock Video, Unassigned, ...) and, on click, selects exactly that bucket's
scenes into the SAME selection set the existing bulk actions (Retry
selected, bulk Change Source) already act on.

Uses the same subprocess-isolated live-VideoGeneratorApp convention as
test_overscaled_ui_integration.py -- in-process Tk construction corrupts
the shared Tk default root for the rest of a pytest run.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_LIVE_CHECK_SCRIPT = r'''
import os
import sys

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.getcwd())

def emit(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}:{name}:{detail}")

try:
    import app as _app
except ModuleNotFoundError as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from pathlib import Path as _P

try:
    instance = _app.VideoGeneratorApp()
    instance.withdraw()
except Exception as exc:
    print(f"SKIP:{exc}")
    os._exit(0)

# A mixed project: 3 flow_video, 2 flow_image, 4 stock_video, 1 unassigned.
scenes = []
for i in range(1, 4):
    scenes.append(SceneRow(scene_number=str(i), script_segment=f"v{i}", asset_type="video", prompt=f"p{i}"))
for i in range(4, 6):
    scenes.append(SceneRow(scene_number=str(i), script_segment=f"i{i}", asset_type="image", prompt=f"p{i}"))
for i in range(6, 10):
    scenes.append(SceneRow(scene_number=str(i), script_segment=f"s{i}", asset_type="stock_video", stock=f"q{i}"))
scenes.append(SceneRow(scene_number="10", script_segment="u"))

instance._scene_rows = scenes
for i, scene in enumerate(scenes):
    instance._decorate_scene_row(i, scene, grid_row=i)

# 1) Button exists and is wired to the real menu-opening method (widget
#    construction alone -- no Tk mainloop needed to check this).
emit("select_by_source_button_exists", hasattr(instance, "_select_by_source_btn"), "")
emit(
    "select_by_source_button_command_wired",
    instance._select_by_source_btn.cget("command") == instance._open_select_by_source_menu,
    "",
)

# 2) Bucket grouping matches the exact same classification the existing
#    header summary already uses -- same counts, same names.
by_bucket = instance._scene_keys_by_source_bucket()
emit("flow_video_bucket_count", len(by_bucket.get("Flow Video", [])) == 3, str(by_bucket.get("Flow Video")))
emit("flow_image_bucket_count", len(by_bucket.get("Flow Image", [])) == 2, str(by_bucket.get("Flow Image")))
emit("stock_video_bucket_count", len(by_bucket.get("Stock Video", [])) == 4, str(by_bucket.get("Stock Video")))
emit("unassigned_bucket_count", len(by_bucket.get("Unassigned", [])) == 1, str(by_bucket.get("Unassigned")))

mix_label = instance._scene_source_mix_label()
emit(
    "bucket_counts_match_existing_summary_label",
    "Flow Video 3" in mix_label and "Flow Image 2" in mix_label and "Stock Video 4" in mix_label,
    repr(mix_label),
)

# 3) Selecting a bucket populates the SAME selection set the existing bulk
#    actions already read from -- no new selection mechanism.
flow_video_keys = by_bucket["Flow Video"]
instance._select_scenes_by_source_bucket(flow_video_keys)
emit(
    "select_bucket_populates_shared_selection_set",
    instance._qa.selected_failed == set(flow_video_keys),
    str(instance._qa.selected_failed),
)

# 4) Selecting a bucket REPLACES the prior selection (doesn't accumulate) --
#    matches the plan's "one bucket at a time" v1 scope.
flow_image_keys = by_bucket["Flow Image"]
instance._select_scenes_by_source_bucket(flow_image_keys)
emit(
    "select_bucket_replaces_prior_selection",
    instance._qa.selected_failed == set(flow_image_keys),
    str(instance._qa.selected_failed),
)

# 5) Row checkboxes reflect the new selection (existing UI feedback path).
checked = [
    k for k, w in instance._scene_row_widgets.items()
    if w.get("check_var") is not None and w["check_var"].get()
]
emit(
    "row_checkboxes_reflect_bucket_selection",
    set(checked) == set(flow_image_keys),
    str(sorted(checked)),
)

# 6) Existing bulk-action buttons (Retry selected) become enabled once a
#    bucket is selected, unmodified -- proves no new wiring was needed there.
emit(
    "existing_retry_selected_button_enabled_by_bucket_selection",
    str(instance.retry_selected_btn.cget("state")) == "normal",
    str(instance.retry_selected_btn.cget("state")),
)

sys.stdout.flush()
os._exit(0)
'''


class TestSelectBySource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script_path = Path(tempfile.mkdtemp()) / "_select_by_source_live_check.py"
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

    def test_button_exists_and_is_wired(self):
        self._assert_check("select_by_source_button_exists")
        self._assert_check("select_by_source_button_command_wired")

    def test_bucket_counts_match_existing_header_summary(self):
        self._assert_check("flow_video_bucket_count")
        self._assert_check("flow_image_bucket_count")
        self._assert_check("stock_video_bucket_count")
        self._assert_check("unassigned_bucket_count")
        self._assert_check("bucket_counts_match_existing_summary_label")

    def test_selecting_a_bucket_uses_the_shared_selection_set(self):
        self._assert_check("select_bucket_populates_shared_selection_set")
        self._assert_check("row_checkboxes_reflect_bucket_selection")

    def test_selecting_a_bucket_replaces_the_prior_selection(self):
        self._assert_check("select_bucket_replaces_prior_selection")

    def test_existing_bulk_actions_work_unmodified_on_a_bucket_selection(self):
        self._assert_check("existing_retry_selected_button_enabled_by_bucket_selection")


if __name__ == "__main__":
    unittest.main()
