#!/usr/bin/env python3
"""Phase 2 verification: 135-scene progress, state consistency, rapid completion, restart, concurrency."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from asset_manager import AssetManager, AssetManifest
from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from scene_qa import SceneQAState, format_header, scene_key
from test_asset_pipeline import AssetPipelineTestCase, FakeProvider


def _ready(n, source=AssetSource.STOCK_VIDEO):
    return AssetResult(str(n), Path(f"{int(n):03d}.mp4"), MediaType.VIDEO, source, SceneStatus.READY)


def _fail(n, error="Needs action"):
    return AssetResult(str(n), None, None, AssetSource.STOCK_VIDEO, SceneStatus.NEEDS_ACTION, error=error)


def _scene(n, stock=None):
    if stock is None:
        stock = f"query {n}"
    return SceneRow(scene_number=str(n), script_segment=f"seg {n}", asset_type="stock_video", stock=stock)


class Test135SceneProgress(unittest.TestCase):
    def test_100_ready_of_135_never_shows_15(self):
        """Reproduce stale-progress bug: manifest truth is 100 ready, UI snapshot must match."""
        scenes = [_scene(i) for i in range(1, 136)]
        results = {scene_key(i): _ready(i) for i in range(1, 101)}
        for i in range(101, 136):
            results[scene_key(i)] = _fail(i, "pending")

        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.ready, 100)
        self.assertEqual(snap.total, 135)
        self.assertEqual(snap.needs_action, 35)
        self.assertIn("100 / 135 READY", format_header(snap))
        self.assertNotIn("15 / 135", format_header(snap))

    def test_mixed_live_states_count_consistently(self):
        scenes = [_scene(i) for i in range(1, 136)]
        results = {scene_key(i): _ready(i) for i in range(1, 101)}
        qa = SceneQAState()
        for i in range(101, 121):
            qa.busy[scene_key(i)] = "generating"
        # Scenes without results and not busy → waiting (shown as QUEUED in header)
        for i in range(131, 136):
            results[scene_key(i)] = _fail(i, "No search results")

        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.ready, 100)
        self.assertEqual(snap.processing, 20)
        self.assertEqual(snap.waiting, 10)
        self.assertEqual(snap.needs_action, 5)
        self.assertEqual(
            snap.ready + snap.processing + snap.waiting + snap.needs_action,
            snap.total,
        )
        header = format_header(snap)
        self.assertIn("100 / 135 READY", header)
        self.assertIn("20 PROCESSING", header)
        self.assertIn("10 QUEUED", header)
        self.assertIn("5 NEEDS ACTION", header)

    def test_progress_ratio_matches_ready_over_total(self):
        scenes = [_scene(i) for i in range(1, 136)]
        results = {scene_key(i): _ready(i) for i in range(1, 101)}
        for i in range(101, 136):
            results[scene_key(i)] = _fail(i)
        snap = SceneQAState().snapshot(scenes, results)
        self.assertAlmostEqual(snap.progress, 100 / 135, places=3)
        self.assertLess(snap.progress, 1.0)


class TestStateTransitions(unittest.TestCase):
    def setUp(self):
        self.scenes = [_scene(i) for i in range(1, 6)]
        self.results: dict[str, AssetResult] = {}
        self.qa = SceneQAState()

    def _snap(self):
        return self.qa.snapshot(self.scenes, self.results)

    def test_queued_to_processing_to_ready(self):
        key = scene_key(1)
        # waiting (no result, not busy) → shown as QUEUED
        snap = self._snap()
        self.assertEqual(snap.statuses[key], "waiting")
        self.assertEqual(snap.waiting, 5)

        self.qa.busy[key] = "searching"
        snap = self._snap()
        self.assertEqual(snap.processing, 1)

        self.qa.busy.pop(key)
        self.results[key] = _ready(1)
        snap = self._snap()
        self.assertEqual(snap.statuses[key], "ready")
        self.assertEqual(snap.ready, 1)
        self.assertEqual(snap.processing, 0)

    def test_processing_to_needs_action(self):
        key = scene_key(2)
        self.qa.busy[key] = "generating"
        snap = self._snap()
        self.assertEqual(snap.processing, 1)
        self.qa.busy.pop(key)
        self.results[key] = _fail(2, "Download failed")
        snap = self._snap()
        self.assertEqual(snap.needs_action, 1)
        self.assertEqual(snap.processing, 0)

    def test_needs_action_to_ready(self):
        key = scene_key(3)
        self.results[key] = _fail(3)
        snap = self._snap()
        self.assertEqual(snap.needs_action, 1)
        self.results[key] = _ready(3)
        snap = self._snap()
        self.assertEqual(snap.ready, 1)
        self.assertEqual(snap.needs_action, 0)

    def test_processing_to_skipped(self):
        key = scene_key(4)
        self.qa.busy[key] = "generating"
        self.qa.busy.pop(key)
        self.results[key] = AssetResult(
            "4", None, None, AssetSource.STOCK_VIDEO, SceneStatus.SKIPPED, error="skipped"
        )
        skipped = {key}
        snap = self.qa.snapshot(self.scenes, self.results, skipped)
        self.assertEqual(snap.skipped, 1)
        self.assertEqual(snap.statuses[key], "skipped")


class TestRapidCompletion(AssetPipelineTestCase):
    def test_ten_instant_completions_all_counted(self):
        stock = FakeProvider(AssetSource.STOCK, {})
        rows = [_scene(i) for i in range(1, 11)]
        completed: list[str] = []

        def on_complete(scene, result):
            completed.append(scene.scene_number)

        summary = self._manager(stock=stock).resolve_all(
            rows, on_scene_complete=on_complete, max_parallel=4
        )
        self.assertTrue(summary.ok)
        self.assertEqual(len(completed), 10)
        self.assertEqual(set(completed), {str(i) for i in range(1, 11)})

        results = {scene_key(i): summary.results[str(i)] for i in range(1, 11)}
        snap = SceneQAState().snapshot(rows, results)
        self.assertEqual(snap.ready, 10)
        self.assertEqual(snap.header, "✓ 10 / 10 READY")


class TestManifestRestart(AssetPipelineTestCase):
    def test_100_of_135_restored_from_manifest_immediately(self):
        rows = [_scene(i) for i in range(1, 136)]
        manifest = AssetManifest(self.images)
        for i in range(1, 101):
            path = self.images / f"{i:03d}.mp4"
            path.write_bytes(b"clip")
            manifest.set(
                str(i),
                {
                    "source": "stock_video",
                    "local_path": str(path),
                    "status": "complete",
                    "stock_query": f"query {i}",
                },
            )
        for i in range(101, 136):
            manifest.set(
                str(i),
                {"source": "stock_video", "status": "failed", "error": "Previous attempt failed"},
            )

        restored: dict[str, AssetResult] = {}
        for scene in rows:
            key = scene_key(scene.scene_number)
            rec = manifest.get(scene.scene_number) or {}
            path = Path(rec["local_path"]) if rec.get("local_path") else None
            if rec.get("status") == "complete" and path is not None and path.is_file():
                restored[key] = _ready(int(scene.scene_number))
            elif rec.get("status") == "failed":
                restored[key] = _fail(int(scene.scene_number))

        snap = SceneQAState().snapshot(rows, restored)
        self.assertEqual(snap.ready, 100)
        self.assertEqual(snap.needs_action, 35)
        self.assertNotEqual(snap.ready, 0)
        self.assertIn("100 / 135 READY", format_header(snap))


class TestConcurrencyMeasurement(AssetPipelineTestCase):
    def test_four_workers_demonstrate_parallelism(self):
        class SlowStock(FakeProvider):
            def __init__(self):
                super().__init__(AssetSource.STOCK, {})
                self.delay = 0.12
                self.in_flight = 0
                self.max_in_flight = 0
                self._lock = threading.Lock()

            def resolve(self, scene, images_dir, log=print):
                with self._lock:
                    self.in_flight += 1
                    self.max_in_flight = max(self.max_in_flight, self.in_flight)
                try:
                    time.sleep(self.delay)
                    return super().resolve(scene, images_dir, log=log)
                finally:
                    with self._lock:
                        self.in_flight -= 1

        stock = SlowStock()
        rows = [_scene(i) for i in range(1, 9)]
        t0 = time.time()
        summary = self._manager(stock=stock).resolve_all(rows, max_parallel=4)
        elapsed = time.time() - t0
        self.assertTrue(summary.ok)
        self.assertGreaterEqual(stock.max_in_flight, 2, "expected concurrent in-flight work")
        sequential_estimate = stock.delay * len(rows)
        self.assertLess(elapsed, sequential_estimate * 0.75, f"elapsed={elapsed:.2f}s sequential~{sequential_estimate:.2f}s")
        # 4 workers remains appropriate: parallelism observed without oversubscription in test


if __name__ == "__main__":
    unittest.main()
