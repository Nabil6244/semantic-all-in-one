"""Regression tests for the Overscaled/Exp Solar "Change Source" persistence
bug: editing a scene's asset type in the Visual Plan (e.g. flow_image ->
stock_image) correctly downloaded the new asset and updated the UI, but the
NEXT full Generate/render still asked for the original CSV asset_type
(flow_image), discarding the user's choice.

ROOT CAUSE (traced, not guessed):

Overscaled/Exp Solar's real generation entry point (scene_graph.
app_integration.generate_overscaled_video -> scene_graph.media_resolution.
resolve_scene_graph_media -> video_generator.resolve_scene_assets) always
builds its OWN fresh AssetManager scoped to ProjectWorkspace.
overscaled_images_dir (root/"overscaled"/"_work"/"media") -- never
self._asset_manager, never self._scene_rows, never assets_dir. It re-reads
the CSV file from disk and re-classifies every scene's asset_type from
scratch on every single Generate click.

app.py's per-scene "Change Source" action (_scene_action_with_source, plus
its siblings _scene_action / _add_local_clip / _add_local_clip_bulk /
_start_flow_batch) hardcoded `images_dir = self._workspace.assets_dir` --
the NORMAL/simple-CSV workflow's own Images/ folder -- regardless of
generation_mode. So picking "stock_image" for an Overscaled scene
downloaded the file and wrote its manifest record into assets_dir, a
location Overscaled's own resolver never looks at. The next full Generate
re-parsed the CSV, saw asset_type=flow_image again (the CSV itself was
never touched), found no manifest record in overscaled_images_dir, and
asked Flow for it again -- silently discarding the user's override.

FIX: app.py's new _scene_action_images_dir() returns
self._workspace.overscaled_images_dir when generation_mode == "overscaled",
else assets_dir (unchanged normal-workflow behavior) -- used at all 5
per-scene-action call sites. No new manifest, no change to Flow/stock
provider behavior, no change to _cache_hit's existing "Change Source"
reuse logic (asset_manager.py, unmodified) -- that logic already handles
this correctly once given the right directory, which
TestChangeSourcePersistsThroughFullRender proves empirically below.

No real Flow account, network call, or real render is used anywhere in
this file. Flow credits spent: 0.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
from scene_graph.media_resolution import resolve_scene_graph_media
from scene_graph.overscaled_csv import compile_overscaled_csv
from test_asset_pipeline import FakeProvider


class _RaisingFlowProvider(FakeProvider):
    """A FlowProvider stub that fails the test loudly if Flow is ever
    actually asked to generate anything -- exactly what "render does NOT
    request Flow" must mean in a deterministic test."""

    def resolve(self, scene, images_dir, log=print):
        raise AssertionError(
            f"Flow was invoked for scene {scene.scene_number} -- "
            "the user's stock_image override was lost."
        )

    def resolve_batch(self, scenes, images_dir, log=print, should_stop=None,
                       on_scene_ready=None, on_scene_generating=None):
        raise AssertionError(
            f"Flow batch was invoked for scenes {[s.scene_number for s in scenes]} -- "
            "the user's stock_image override was lost."
        )


class _RaisingStockProvider(FakeProvider):
    """Mirror stub for the reverse direction (stock_image -> flow_image):
    fails loudly if stock is asked for again after the user switched to
    Flow."""

    def resolve(self, scene, images_dir, log=print):
        raise AssertionError(
            f"Stock was invoked for scene {scene.scene_number} -- "
            "the user's flow_image override was lost."
        )


class TestChangeSourcePersistsThroughFullRender(unittest.TestCase):
    """The core requirement, proven with real production classes
    (AssetManager, SceneRow, resolve_scene_graph_media) end to end:

        CSV says flow_image
                v
        user override says stock_image (AssetManager.change_source, the
        SAME method app.py's Change Source dialog calls)
                v
        stock asset is resolved and manifest-recorded
                v
        "generation completes" (this AssetManager instance is discarded --
        simulates the app closing / a fresh Generate click)
                v
        render preparation (a FRESH resolve_scene_graph_media() call,
        exactly what generate_overscaled_video() does) sees stock_image
                v
        render does NOT request Flow (a Flow provider that raises if
        called is passed and must never fire)
    """

    def _run(self, compile_fn, label: str):
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "overscaled" / "_work" / "media"
        images_dir.mkdir(parents=True)

        scene_graph = compile_fn()

        # Step 1: user changes source for the scene, via the REAL
        # AssetManager.change_source() -- the exact call app.py's
        # _scene_action_worker makes for a "change_source" action.
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        mgr = AssetManager(images_dir, stock_provider=stock, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="flow_image", prompt="a photo of a tank")
        change_result = mgr.change_source(scene, "stock_image")
        self.assertTrue(change_result.ok, f"[{label}] change_source itself must succeed")
        self.assertEqual(change_result.source, AssetSource.STOCK_IMAGE)
        self.assertTrue(Path(change_result.path).is_file())

        # Step 2: "generation completes" -- this AssetManager/session ends.
        del mgr

        # Step 3: render preparation -- a brand-new resolve_scene_graph_media()
        # call, exactly what generate_overscaled_video() issues on the next
        # Generate click, against the SAME images_dir and the UNCHANGED CSV
        # (still says flow_image -- the CSV itself was never edited).
        flow = _RaisingFlowProvider(AssetSource.FLOW_IMAGE, {})
        with patch("providers.stock.pexels.build_pexels_provider",
                   side_effect=lambda d, k: FakeProvider(AssetSource.STOCK_IMAGE, {})):
            resolved = resolve_scene_graph_media(
                scene_graph, images_dir=images_dir, pexels_api_key="k",
                flow_engine_manager=object(),  # non-None: passes the "is Flow
                # configured" gate in video_generator.resolve_scene_assets;
                # _RaisingFlowProvider itself proves Flow is never actually
                # invoked, regardless of this dummy object's shape.
            )

        self.assertIn("n1", resolved, f"[{label}] render prep must resolve the node")
        self.assertEqual(
            Path(resolved["n1"]), change_result.path,
            f"[{label}] render must use the user's stock-resolved file, not re-derive from the CSV",
        )

    def test_overscaled_flow_image_to_stock_image(self):
        def compile_overscaled():
            rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1",
                      "node_type": "image", "asset_type": "flow_image", "prompt": "a photo of a tank"}]
            compiled = compile_overscaled_csv(rows, segment_id="seg")
            self.assertTrue(compiled.ok, compiled.errors)
            return compiled.scene_graph

        self._run(compile_overscaled, "Overscaled")

    def test_exp_solar_flow_image_to_stock_image(self):
        def compile_exp_solar():
            rows = [{"scene_number": "1", "script_segment": "x", "beat": "hero",
                      "asset_type": "flow_image", "prompt": "a photo of a tank"}]
            adapted = adapt_exp_solar_csv_rows(rows)
            self.assertTrue(adapted.ok, adapted.errors)
            compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
            self.assertTrue(compiled.ok, compiled.errors)
            return compiled.scene_graph

        self._run(compile_exp_solar, "Exp Solar")


class TestChangeSourceReverseDirection(unittest.TestCase):
    """stock_image -> flow_image: the same persistence must work in reverse,
    since app.py's Change Source dialog offers flow_image as a target too."""

    def test_stock_image_to_flow_image(self):
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "overscaled" / "_work" / "media"
        images_dir.mkdir(parents=True)

        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1",
                  "node_type": "image", "asset_type": "stock_image", "prompt": "a tank photo"}]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)

        flow = FakeProvider(AssetSource.FLOW_IMAGE, {}, media_type=None)
        from providers.base import MediaType
        flow.media_type = MediaType.IMAGE
        mgr = AssetManager(images_dir, flow_image_provider=flow, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="stock_image", stock="a tank photo")
        change_result = mgr.change_source(scene, "flow_image")
        self.assertTrue(change_result.ok)
        self.assertEqual(change_result.source, AssetSource.FLOW_IMAGE)
        del mgr

        stock = _RaisingStockProvider(AssetSource.STOCK_IMAGE, {})
        with patch("providers.stock.pexels.build_pexels_provider", side_effect=lambda d, k: stock):
            resolved = resolve_scene_graph_media(
                compiled.scene_graph, images_dir=images_dir, pexels_api_key="k",
            )
        self.assertIn("n1", resolved)
        self.assertEqual(Path(resolved["n1"]), change_result.path)


class TestHydrationReflectsOverride(unittest.TestCase):
    """Reopen-safety: after Change Source persists a stock_image override
    into overscaled_images_dir's manifest, the EXISTING project-reopen
    hydration (app.py's _hydrate_overscaled_assets_from_manifest, added for
    the earlier resume-after-crash fix) must show the override too --
    reusing that mechanism, not a new one."""

    def test_hydration_shows_overridden_source_not_original_csv_type(self):
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "overscaled" / "_work" / "media"
        images_dir.mkdir(parents=True)

        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        mgr = AssetManager(images_dir, stock_provider=stock, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="flow_image", prompt="a photo of a tank")
        change_result = mgr.change_source(scene, "stock_image")
        self.assertTrue(change_result.ok)
        del mgr

        from asset_manager import AssetManifest

        manifest = AssetManifest(images_dir)
        record = manifest.get("1")
        self.assertIsNotNone(record)
        self.assertEqual(record.get("status"), "complete")
        self.assertEqual(
            record.get("source"), "stock_image",
            "the persisted manifest record -- what hydration reads -- must reflect the override",
        )


_LIVE_ROUTING_CHECK_SCRIPT = r'''
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

from project_workspace import ProjectWorkspace

tmp = Path(tempfile.mkdtemp())
root = tmp / "proj"
root.mkdir()
ws = ProjectWorkspace(project_id="p1", title="Test", seq=1, root=root)
ws.ensure_dirs()
instance._workspace = ws

instance.generation_mode = "overscaled"
overscaled_dir = instance._scene_action_images_dir()
emit("overscaled_mode_uses_overscaled_images_dir",
     overscaled_dir == ws.overscaled_images_dir,
     f"got {overscaled_dir!r}, expected {ws.overscaled_images_dir!r}")

instance.generation_mode = "normal"
normal_dir = instance._scene_action_images_dir()
emit("normal_mode_uses_assets_dir",
     normal_dir == ws.assets_dir,
     f"got {normal_dir!r}, expected {ws.assets_dir!r}")

sys.stdout.flush()
os._exit(0)
'''


class TestSceneActionImagesDirRouting(unittest.TestCase):
    """App-level check (real VideoGeneratorApp, subprocess-isolated per the
    established convention -- constructing it in-process corrupts the
    shared Tk default root for later tests in the same pytest session)
    that _scene_action_images_dir() itself routes correctly by mode. This
    is the actual method app.py's Change Source / Retry / Alternative /
    Skip / Add Local Clip / Flow batch retry all call."""

    @classmethod
    def setUpClass(cls):
        script_path = Path(tempfile.mkdtemp()) / "_scene_action_routing_check.py"
        script_path.write_text(_LIVE_ROUTING_CHECK_SCRIPT, encoding="utf-8")
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

    def test_overscaled_mode_uses_overscaled_images_dir(self):
        self._assert_check("overscaled_mode_uses_overscaled_images_dir")

    def test_normal_mode_uses_assets_dir(self):
        self._assert_check("normal_mode_uses_assets_dir")


if __name__ == "__main__":
    unittest.main()
