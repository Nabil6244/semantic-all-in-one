"""Regression tests for Overscaled/Exp Solar generation resume-after-crash.

Report recap: a partially-generated Overscaled/Exp Solar run (e.g. 30/58
scenes resolved), interrupted, then restarted after reopening the project,
appeared to regenerate everything from scratch — unlike the normal/simple
CSV workflow, which already resumes via AssetManager's on-disk manifest
(.asset_manifest.json, AssetManager._cache_hit — see
test_asset_pipeline.py::TestCachingAndResume, already proven generic across
FLOW_IMAGE/STOCK sources and unmodified here).

Root cause found by tracing both paths:

  1. scene_graph.media_resolution.resolve_scene_graph_media() (the Overscaled/
     Exp Solar adapter) already calls video_generator.resolve_scene_assets()
     -> AssetManager.resolve_all(), the SAME function/manifest the normal
     workflow uses -- so scene-level resolution ALREADY skips a scene whose
     manifest record is status=="complete" with a real file still on disk.
     TestOverscaledAdapterResumesLikeNormalWorkflow below proves this
     empirically for both Overscaled and Exp Solar: a provider stub that
     raises if called a second time for an already-resolved scene.

  2. What was actually missing: app.py's Overscaled Visual Plan
     (_load_overscaled_csv, reached both from a fresh CSV import and from
     _bind_workspace_paths on project reopen) built self._scene_rows fresh
     from the CSV every time but never populated self._asset_results from
     the on-disk manifest the way the normal workflow's own
     _hydrate_assets_from_manifest() does -- so on reopen, the Visual Plan
     showed every row QUEUED regardless of how much of the project was
     already done, and a generation restart looked like (and, from the
     operator's vantage point watching the UI, effectively was) starting
     from zero even though the underlying resolve happened to skip the
     real work. TestOverscaledVisualPlanHydratesFromManifest below proves
     the fix: a new _hydrate_overscaled_assets_from_manifest() (reusing the
     SAME AssetManifest class, pointed at ProjectWorkspace.
     overscaled_images_dir -- the exact path generate_overscaled_video()
     already resolves into) now restores READY/NEEDS_ACTION state into
     self._asset_results on load, exactly like the normal workflow already
     does for its own Images/ manifest.

No Flow account, network call, or real render is used anywhere in this
file. Flow credits spent: 0.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from providers.base import AssetSource
from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
from scene_graph.media_resolution import resolve_scene_graph_media
from scene_graph.overscaled_csv import compile_overscaled_csv
from test_asset_pipeline import FakeProvider


def _write_stock_rows(n: int) -> list[dict]:
    return [
        {"scene_number": str(i), "script_segment": f"seg {i}", "node_id": f"n{i}",
         "node_type": "image", "asset_type": "stock_image", "prompt": f"query {i}"}
        for i in range(1, n + 1)
    ]


class TestOverscaledAdapterResumesLikeNormalWorkflow(unittest.TestCase):
    """Proves resolve_scene_graph_media() (Overscaled's own media-resolution
    entry point) already reuses AssetManager's existing manifest-based
    resume -- a scene already marked complete on disk must never be handed
    to the provider again on a second call with the same images_dir, exactly
    like reopening the project and clicking Generate again after a crash."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images_dir = self.tmp / "images"
        self.images_dir.mkdir()
        self.fake = FakeProvider(AssetSource.STOCK_IMAGE, {})
        self._patcher = patch(
            "providers.stock.pexels.build_pexels_provider",
            side_effect=lambda images_dir, api_key: self.fake,
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_overscaled_second_run_only_resolves_missing_scenes(self):
        rows = _write_stock_rows(5)
        compiled1 = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled1.ok, compiled1.errors)
        resolve_scene_graph_media(compiled1.scene_graph, images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(sorted(self.fake.calls), ["1", "2", "3", "4", "5"])

        # Simulate "crash, reopen project, click Generate again": a FRESH
        # compile from the SAME CSV rows, same images_dir, same manifest.
        self.fake.calls = []
        compiled2 = compile_overscaled_csv(rows, segment_id="seg")
        resolve_scene_graph_media(compiled2.scene_graph, images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(self.fake.calls, [], "every scene was already complete -- nothing should be re-resolved")

    def test_overscaled_only_missing_scenes_are_scheduled_after_partial_run(self):
        rows = _write_stock_rows(6)
        # Simulate "crash after 3/6": only resolve the first half.
        compiled_partial = compile_overscaled_csv(rows[:3], segment_id="seg")
        resolve_scene_graph_media(compiled_partial.scene_graph, images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(sorted(self.fake.calls), ["1", "2", "3"])

        self.fake.calls = []
        compiled_full = compile_overscaled_csv(rows, segment_id="seg")
        resolved = resolve_scene_graph_media(compiled_full.scene_graph, images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(
            sorted(self.fake.calls), ["4", "5", "6"],
            "only the missing scenes (4-6) should be scheduled -- scenes 1-3 must be reused, not repeated",
        )
        self.assertEqual(len(resolved), 6, "final result must still include all 6 resolved assets")

    def test_exp_solar_second_run_only_resolves_missing_scenes(self):
        rows = [
            {"scene_number": str(i), "script_segment": f"seg {i}", "beat": "hero",
             "asset_type": "stock_image", "prompt": f"query {i}"}
            for i in range(1, 5)
        ]

        def compile_exp_solar():
            adapted = adapt_exp_solar_csv_rows(rows)
            self.assertTrue(adapted.ok, adapted.errors)
            compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
            self.assertTrue(compiled.ok, compiled.errors)
            return compiled.scene_graph

        resolve_scene_graph_media(compile_exp_solar(), images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(sorted(self.fake.calls), ["1", "2", "3", "4"])

        self.fake.calls = []
        resolve_scene_graph_media(compile_exp_solar(), images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(self.fake.calls, [], "Exp Solar must reuse the same manifest-based resume as Overscaled")

    def test_invalid_or_corrupt_asset_is_regenerated_not_treated_as_complete(self):
        rows = _write_stock_rows(2)
        compiled1 = compile_overscaled_csv(rows, segment_id="seg")
        resolve_scene_graph_media(compiled1.scene_graph, images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(sorted(self.fake.calls), ["1", "2"])

        # Corrupt/delete scene 1's file on disk without touching the manifest.
        (self.images_dir / "001.jpg").unlink()

        self.fake.calls = []
        compiled2 = compile_overscaled_csv(rows, segment_id="seg")
        resolve_scene_graph_media(compiled2.scene_graph, images_dir=self.images_dir, pexels_api_key="k")
        self.assertEqual(
            self.fake.calls, ["1"],
            "a manifest record whose file is missing/gone must be treated as needing regeneration, not reused",
        )


class TestOverscaledMediaResolutionReportsLiveSceneEvents(unittest.TestCase):
    """Reproduces the SEPARATE "8 ready" vs "157/165 scenes ready" report:
    even though AssetManager.resolve_all() already resolves a scene
    correctly, resolve_scene_assets() (video_generator.py, the function
    Overscaled/Exp Solar's resolve_scene_graph_media() calls) used to call
    it with NO on_scene_start/on_scene_complete/on_scene_generating
    callbacks at all -- unlike the normal CSV workflow's own inline
    AssetManager.resolve_all(...) call in app.py, which always passes
    them. With no callbacks, app.py's Visual Plan had to fall back to
    regex-classifying raw log text (_classify_scene_status), which has no
    case for a freshly-resolved (non-cached) scene's own
    "[ASSET] Scene N -> STOCK_IMAGE" routing line -- so a scene that
    genuinely just succeeded stayed at whatever stale status (often
    NEEDS_ACTION, restored from a PRIOR failed attempt by
    _hydrate_overscaled_assets_from_manifest) it already had.

    Proves the fix by driving resolve_scene_graph_media() -> resolve_scene_
    assets() with real on_scene_start/on_scene_complete/on_scene_generating
    callbacks (the exact plumbing added to video_generator.py, scene_graph/
    media_resolution.py and scene_graph/app_integration.py) and asserting
    on_scene_complete actually fires for every scene, carrying an ok result
    -- the same event app.py's real _overscaled_on_scene_complete pushes
    onto self._ui_queue as ("scene_asset", ...), which the ALREADY-PROVEN
    _poll_queue/_set_scene_status/_refresh_qa_ui pipeline (see
    test_flow_cancellation_retry.py) turns into a correct READY row and an
    accurate header count."""

    def test_on_scene_complete_fires_for_every_scene_not_just_cached_ones(self):
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "images"
        images_dir.mkdir()
        fake = FakeProvider(AssetSource.STOCK_IMAGE, {})

        with patch("providers.stock.pexels.build_pexels_provider", side_effect=lambda d, k: fake):
            rows = _write_stock_rows(5)
            compiled = compile_overscaled_csv(rows, segment_id="seg")
            self.assertTrue(compiled.ok, compiled.errors)

            started: list[str] = []
            completed: list[tuple[str, bool]] = []
            generating: list[str] = []

            resolve_scene_graph_media(
                compiled.scene_graph, images_dir=images_dir, pexels_api_key="k",
                on_scene_start=lambda scene, source: started.append(scene.scene_number),
                on_scene_complete=lambda scene, result: completed.append((scene.scene_number, result.ok)),
                on_scene_generating=lambda scene: generating.append(scene.scene_number),
            )

            self.assertEqual(sorted(started), ["1", "2", "3", "4", "5"],
                              "on_scene_start must fire for every freshly-resolved scene")
            self.assertEqual(sorted(completed), [("1", True), ("2", True), ("3", True), ("4", True), ("5", True)],
                              "on_scene_complete must fire for every scene with its real ok/fail result -- "
                              "this is what the UI needs instead of regex-classifying log text")

    def test_cached_scenes_also_report_on_scene_complete_on_second_run(self):
        """A cache-hit scene (already complete on disk) must still notify
        the UI via on_scene_complete -- see asset_manager.py resolve_all's
        cache-hit branch, which already calls it; this just proves
        Overscaled's adapter doesn't drop that callback along the way."""
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "images"
        images_dir.mkdir()
        fake = FakeProvider(AssetSource.STOCK_IMAGE, {})

        with patch("providers.stock.pexels.build_pexels_provider", side_effect=lambda d, k: fake):
            rows = _write_stock_rows(3)
            compiled1 = compile_overscaled_csv(rows, segment_id="seg")
            resolve_scene_graph_media(compiled1.scene_graph, images_dir=images_dir, pexels_api_key="k")

            compiled2 = compile_overscaled_csv(rows, segment_id="seg")
            completed: list[str] = []
            resolve_scene_graph_media(
                compiled2.scene_graph, images_dir=images_dir, pexels_api_key="k",
                on_scene_complete=lambda scene, result: completed.append(scene.scene_number),
            )
            self.assertEqual(
                sorted(completed), ["1", "2", "3"],
                "cache-hit scenes on a resumed run must still surface a READY event to the UI",
            )


_LIVE_HYDRATION_CHECK_SCRIPT = r'''
import csv
import os
import sys
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

from asset_manager import AssetManager
from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from project_workspace import ProjectWorkspace

tmp = Path(tempfile.mkdtemp())
root = tmp / "proj"
root.mkdir()
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=root)
ws.ensure_dirs()
instance._workspace = ws

rows = [
    {"scene_number": str(i), "script_segment": f"seg {i}", "node_id": f"n{i}",
     "node_type": "image", "asset_type": "stock_image", "prompt": f"query {i}"}
    for i in range(1, 5)
]
csv_path = tmp / "overscaled.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["scene_number", "script_segment", "node_id", "node_type", "asset_type", "prompt"])
    w.writeheader()
    for r in rows:
        w.writerow(r)

images_dir = ws.overscaled_images_dir
images_dir.mkdir(parents=True)
mgr = AssetManager(images_dir, log=lambda *_: None)
for i in (1, 2):
    path = images_dir / f"00{i}.jpg"
    path.write_bytes(b"fake-jpg-bytes")
    scene = SceneRow(scene_number=str(i), script_segment="x")
    result = AssetResult(str(i), path, MediaType.IMAGE, AssetSource.STOCK_IMAGE, SceneStatus.READY)
    mgr._manifest_write(scene, mgr._record_from_result(scene, result))
mgr._manifest_write(
    SceneRow(scene_number="3", script_segment="x"),
    {"status": "failed", "error": "simulated crash mid-scene", "local_path": None, "source": "stock_image"},
)

instance._overscaled_style_preset_id = "overscaled"
ok = instance._load_overscaled_csv(str(csv_path))
emit("load_overscaled_csv_ok", ok, "")

results = instance._asset_results
emit("scene1_restored_ready", "001" in results and results["001"].ok,
     "manifest-complete scene with a real file must restore READY")
emit("scene2_restored_ready", "002" in results and results["002"].ok, "")
emit("scene3_restored_needs_action", "003" in results and not results["003"].ok,
     "a failed manifest record must still surface as needs-action, not be silently dropped")
emit("scene4_stays_absent", "004" not in results,
     "scene 4 was never resolved -- must stay absent (QUEUED), not fabricated")

sys.stdout.flush()
os._exit(0)
'''


class TestOverscaledVisualPlanHydratesFromManifest(unittest.TestCase):
    """Proves the fix in app.py: on CSV load/project-reopen, Overscaled/Exp
    Solar's Visual Plan now restores self._asset_results from the SAME
    on-disk manifest generate_overscaled_video() already resolves against
    -- reusing project_workspace.overscaled_images_dir + asset_manager.
    AssetManifest, never a second store.

    Runs in a subprocess (same convention as
    test_overscaled_ui_integration.py's _LIVE_CHECK_SCRIPT): constructing a
    real VideoGeneratorApp() in-process corrupts the shared Tk default root
    for every test that runs afterward in the same pytest session."""

    @classmethod
    def setUpClass(cls):
        script_path = Path(tempfile.mkdtemp()) / "_overscaled_resume_live_check.py"
        script_path.write_text(_LIVE_HYDRATION_CHECK_SCRIPT, encoding="utf-8")
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

    def test_load_overscaled_csv_succeeds(self):
        self._assert_check("load_overscaled_csv_ok")

    def test_scene1_restored_ready(self):
        self._assert_check("scene1_restored_ready")

    def test_scene2_restored_ready(self):
        self._assert_check("scene2_restored_ready")

    def test_scene3_restored_needs_action(self):
        self._assert_check("scene3_restored_needs_action")

    def test_scene4_stays_absent(self):
        self._assert_check("scene4_stays_absent")


if __name__ == "__main__":
    unittest.main()
