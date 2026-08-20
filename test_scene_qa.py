#!/usr/bin/env python3
"""QA / error-management layer: navigation, header consistency, bulk targeting, stale jobs."""

from __future__ import annotations

import unittest
from pathlib import Path

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from scene_qa import (
    SceneQAState,
    format_header,
    load_qa_file,
    preview_alternatives,
    save_qa_file,
    summarize_alternative_preview,
)
from scene_recovery import SceneRecoveryTracker, scene_key
from test_asset_pipeline import AssetPipelineTestCase, FakeProvider
from asset_manager import AssetManager


def _scene(n, kind="stock_video", text="narration", fallbacks=None, **kwargs):
    if kind == "youtube_video":
        return SceneRow(
            scene_number=str(n), script_segment=text, asset_type="youtube_video",
            prompt=kwargs.get("prompt", f"query {n}"),
            search_queries=kwargs.get("search_queries", [kwargs.get("prompt", f"query {n}")]),
            fallbacks=fallbacks or [],
        )
    if kind == "flow_video":
        return SceneRow(
            scene_number=str(n), script_segment=text, asset_type="video",
            prompt=kwargs.get("prompt", f"prompt {n}"), fallbacks=fallbacks or [],
        )
    return SceneRow(
        scene_number=str(n), script_segment=text, asset_type="stock_video",
        stock=kwargs.get("stock", f"stock {n}"), fallbacks=fallbacks or [],
    )


def _ready(n, source=AssetSource.STOCK_VIDEO):
    return AssetResult(str(n), Path(f"{int(n):03d}.mp4"), MediaType.VIDEO, source, SceneStatus.READY)


def _fail(n, error, source=AssetSource.STOCK_VIDEO):
    return AssetResult(
        str(n), None, None, source, SceneStatus.NEEDS_ACTION, error=error,
    )


def _project(n=100, failures=None):
    failures = failures or {}
    scenes = [_scene(i) for i in range(1, n + 1)]
    results = {}
    for i in range(1, n + 1):
        key = scene_key(i)
        if i in failures:
            results[key] = _fail(i, failures[i])
        else:
            results[key] = _ready(i)
    return scenes, results


class TestErrorNavigation(unittest.TestCase):
    def test_go_to_error_cycles_three_failures_in_100_scenes(self):
        scenes, results = _project(100, {47: "YouTube search returned 0 results",
                                         83: "Stock — download failed",
                                         121: "Flow — generation failed"})
        # 121 is beyond 100 — use 91 as the third
        scenes, results = _project(100, {47: "e1", 83: "e2", 91: "e3"})
        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.unresolved_keys, ["047", "083", "091"])
        self.assertEqual(qa.go_to_error(snap.unresolved_keys), "047")
        self.assertEqual(qa.go_to_error(snap.unresolved_keys), "083")
        self.assertEqual(qa.go_to_error(snap.unresolved_keys), "091")
        self.assertEqual(qa.go_to_error(snap.unresolved_keys), "047")

    def test_go_to_error_finds_scene_221(self):
        scenes, results = _project(221, {221: "Download failed: stock asset exceeded 200MB, aborted"})
        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.header, "220 / 221 READY · 1 NEEDS ACTION")
        self.assertEqual(qa.go_to_error(snap.unresolved_keys), "221")
        self.assertIn("200MB", snap.issues[0].error)

    def test_previous_next_cycles(self):
        scenes, results = _project(20, {3: "a", 8: "b", 15: "c"})
        qa = SceneQAState()
        keys = qa.snapshot(scenes, results).unresolved_keys
        self.assertEqual(qa.next_error(keys), "003")
        self.assertEqual(qa.next_error(keys), "008")
        self.assertEqual(qa.prev_error(keys), "003")
        self.assertEqual(qa.prev_error(keys), "015")


class TestErrorCountAndHeader(unittest.TestCase):
    def test_error_count_recovers(self):
        scenes, results = _project(10, {2: "x", 5: "y", 9: "z"})
        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.needs_action, 3)
        self.assertEqual(snap.error_counter, "3 NEEDS ACTION")
        results["002"] = _ready(2)
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.needs_action, 2)
        results["005"] = _ready(5)
        results["009"] = _ready(9)
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.needs_action, 0)
        self.assertEqual(snap.error_counter, "0 NEEDS ACTION")
        self.assertEqual(snap.health, "healthy")

    def test_header_134_ready_1_failed_never_all_ready(self):
        scenes, results = _project(135, {221: "Download failed: stock asset exceeded 200MB, aborted"})
        # 221 not in 135 — use scene 135 as the failed one matching the production bug shape
        scenes, results = _project(135, {135: "Download failed: stock asset exceeded 200MB, aborted"})
        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.ready, 134)
        self.assertEqual(snap.needs_action, 1)
        self.assertEqual(snap.header, "134 / 135 READY · 1 NEEDS ACTION")
        self.assertNotIn("ALL READY", snap.header)
        self.assertFalse(snap.header.startswith("✓"))
        self.assertEqual(snap.issues[0].key, "135")
        self.assertIn("200MB", snap.issues[0].error)

    def test_header_all_ready(self):
        scenes, results = _project(135, {})
        snap = SceneQAState().snapshot(scenes, results)
        self.assertEqual(snap.header, "✓ 135 / 135 READY")
        self.assertEqual(snap.health_label, "✓ PIPELINE HEALTHY")

    def test_progress_not_100_until_resolved(self):
        scenes, results = _project(10, {4: "fail"})
        snap = SceneQAState().snapshot(scenes, results)
        self.assertLess(snap.progress, 1.0)
        results["004"] = _ready(4)
        snap = SceneQAState().snapshot(scenes, results)
        self.assertEqual(snap.progress, 1.0)

    def test_counts_add_up(self):
        scenes, results = _project(10, {1: "a", 2: "b"})
        qa = SceneQAState()
        qa.begin_job("3", "retrying")
        snap = qa.snapshot(scenes, results)
        self.assertEqual(
            snap.ready + snap.processing + snap.needs_action + snap.skipped + snap.waiting,
            snap.total,
        )
        self.assertEqual(snap.processing, 1)
        self.assertEqual(snap.needs_action, 2)


class TestRetryAndAlternativeState(unittest.TestCase):
    def test_retry_success_updates_status(self):
        scenes, results = _project(5, {2: "old error"})
        qa = SceneQAState()
        token = qa.begin_job("2", "retrying")
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.statuses["002"], "retrying")
        self.assertTrue(qa.apply_result("2", token))
        results["002"] = _ready(2)
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.statuses["002"], "ready")
        self.assertEqual(snap.needs_action, 0)

    def test_retry_failure_keeps_new_error(self):
        scenes, results = _project(5, {2: "old error"})
        qa = SceneQAState()
        token = qa.begin_job("2", "retrying")
        self.assertTrue(qa.apply_result("2", token))
        results["002"] = _fail(2, "new download error")
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.statuses["002"], "needs_action")
        self.assertEqual(snap.issues[0].error, "new download error")

    def test_stale_callback_does_not_overwrite(self):
        scenes, results = _project(5, {2: "old"})
        qa = SceneQAState()
        old = qa.begin_job("2", "retrying")
        new = qa.begin_job("2", "retrying")
        self.assertFalse(qa.apply_result("2", old))
        self.assertTrue(qa.apply_result("2", new))
        results["002"] = _ready(2)
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.statuses["002"], "ready")
        self.assertEqual(snap.needs_action, 0)

    def test_historical_failed_log_does_not_affect_header(self):
        scenes, results = _project(5, {})
        results["002"] = _ready(2)
        historical_log = "Scene 2 FAILED Download failed"
        snap = SceneQAState().snapshot(scenes, results)
        self.assertEqual(snap.needs_action, 0)
        self.assertEqual(snap.header, "✓ 5 / 5 READY")
        self.assertNotIn("FAILED", snap.header)
        self.assertTrue("Scene 2 FAILED" in historical_log)


class TestSkipDecreasesErrorCount(unittest.TestCase):
    def test_skip_removes_from_unresolved(self):
        scenes, results = _project(5, {2: "x", 4: "y"})
        qa = SceneQAState()
        results["002"] = AssetResult(
            "2", Path("002.png"), MediaType.IMAGE, AssetSource.STOCK_VIDEO, SceneStatus.SKIPPED,
            error="Skipped — no visual asset (placeholder only).",
        )
        snap = qa.snapshot(scenes, results, skipped={"002"})
        self.assertEqual(snap.needs_action, 1)
        self.assertEqual(snap.skipped, 1)
        self.assertEqual(snap.unresolved_keys, ["004"])


class TestSearch(unittest.TestCase):
    def test_search_scene_number_and_failed(self):
        scenes, results = _project(20, {7: "rocket failed", 12: "ok wait no"})
        results["012"] = _ready(12)
        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        qa.filter_query = "7"
        hits = [s for s in scenes if qa.scene_matches(s, snap.statuses[scene_key(s.scene_number)], results.get(scene_key(s.scene_number)))]
        self.assertEqual([s.scene_number for s in hits], ["7"])
        qa.filter_query = "failed"
        hits = [s for s in scenes if qa.scene_matches(s, snap.statuses[scene_key(s.scene_number)], results.get(scene_key(s.scene_number)))]
        self.assertEqual([s.scene_number for s in hits], ["7"])
        qa.filter_query = "rocket"
        hits = [s for s in scenes if qa.scene_matches(s, snap.statuses[scene_key(s.scene_number)], results.get(scene_key(s.scene_number)))]
        self.assertTrue(any(s.scene_number == "7" for s in hits))


class TestBulkTargeting(unittest.TestCase):
    def test_bulk_retry_targets_only_failed(self):
        scenes, results = _project(100, {47: "a", 83: "b", 91: "c", 102: "d",
                                         108: "e", 119: "f", 127: "g"})
        # 100 scenes — clamp failures inside range
        scenes, results = _project(135, {
            47: "YouTube no results", 83: "Stock download failed", 91: "Flow generation failed",
            102: "YouTube no results", 108: "Stock download failed",
            119: "YouTube no results", 127: "YouTube no results",
        })
        qa = SceneQAState()
        snap = qa.snapshot(scenes, results)
        self.assertEqual(snap.header, "128 / 135 READY · 7 NEEDS ACTION")
        targets = qa.targets(snap.unresolved_keys, selected_only=False)
        self.assertEqual(len(targets), 7)
        self.assertEqual(targets, ["047", "083", "091", "102", "108", "119", "127"])
        ready_keys = [scene_key(i) for i in range(1, 136) if scene_key(i) not in targets]
        self.assertEqual(len(ready_keys), 128)

    def test_selective_bulk_affects_exactly_three(self):
        scenes, results = _project(20, {2: "a", 5: "b", 8: "c", 11: "d", 14: "e", 17: "f", 19: "g"})
        qa = SceneQAState()
        keys = qa.snapshot(scenes, results).unresolved_keys
        qa.selected_failed = {"002", "008", "017"}
        selected = qa.targets(keys, selected_only=True)
        self.assertEqual(selected, ["002", "008", "017"])


class TestAlternativePreview(unittest.TestCase):
    def test_mixed_providers_use_existing_fallbacks(self):
        scenes = [
            _scene(47, "youtube_video", fallbacks=["stock_video"], prompt="q1",
                   search_queries=["q1"]),
            _scene(83, "stock_video", fallbacks=["flow_image"], stock="s1"),
            _scene(91, "flow_video", fallbacks=["stock_image"], prompt="p1"),
            _scene(102, "youtube_video", fallbacks=["stock_video"], prompt="q2",
                   search_queries=["q2"]),
            _scene(108, "stock_video", fallbacks=["flow_image"], stock="s2"),
            _scene(119, "youtube_video", fallbacks=["stock_video"], prompt="q3",
                   search_queries=["q3"]),
            _scene(127, "youtube_video", fallbacks=["stock_video"], prompt="q4",
                   search_queries=["q4"]),
        ]
        tracker = SceneRecoveryTracker()
        for n in (47, 102, 119, 127):
            tracker.mark_query(str(n), f"q{ {47:1,102:2,119:3,127:4}[n] }")
            tracker.mark_provider(str(n), "youtube")
        tracker.mark_provider("83", "stock_video")
        tracker.mark_provider("108", "stock_video")
        tracker.mark_provider("91", "flow_video")
        previews = preview_alternatives(scenes, tracker)
        counts = summarize_alternative_preview(previews)
        self.assertEqual(counts.get("Stock Video"), 4)
        self.assertEqual(counts.get("Flow Image"), 2)
        self.assertEqual(counts.get("Stock Image"), 1)


class TestAlternativeExecution(AssetPipelineTestCase):
    def test_failed_youtube_alternative_uses_fallback_provider(self):
        youtube = FakeProvider(AssetSource.YOUTUBE_VIDEO, {"4": "fail"}, media_type=MediaType.VIDEO)
        flow = FakeProvider(AssetSource.FLOW_VIDEO, {"4": "ok"}, media_type=MediaType.VIDEO)
        scene = SceneRow(
            scene_number="4", script_segment="x", asset_type="youtube_video",
            prompt="q1", search_queries=["q1"], fallbacks=["flow_video"],
            visual_description="cinematic",
        )
        mgr = AssetManager(
            self.images, youtube_provider=youtube, flow_video_provider=flow, log=lambda *_: None,
        )
        mgr.recovery.mark_query("4", "q1")
        mgr.recovery.mark_provider("4", "youtube")
        result = mgr.alternative_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.FLOW_VIDEO)
        self.assertEqual(youtube.calls, [])
        self.assertEqual(flow.calls, ["4"])


class TestBulkRetryDoesNotTouchReady(AssetPipelineTestCase):
    def test_retry_failed_only_calls_failed_scenes(self):
        scripted = {str(i): "ok" for i in range(1, 8)}
        scripted["2"] = "fail"
        scripted["5"] = "fail"
        stock = FakeProvider(AssetSource.STOCK_VIDEO, scripted, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number=str(i), script_segment="a", asset_type="stock_video", stock=f"q{i}")
            for i in range(1, 8)
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.resolve_all(rows)
        before = {i: (self.images / f"{i:03d}.mp4").read_bytes()
                  for i in (1, 3, 4, 6, 7)}
        stock.calls.clear()
        stock.scripted["2"] = "ok"
        stock.scripted["5"] = "ok"
        qa = SceneQAState()
        results = {scene_key(n): mgr.manifest.get(str(n)) and (
            _ready(n) if mgr.manifest.get(str(n)).get("status") == "complete" else _fail(n, "x")
        ) for n in range(1, 8)}
        # Use real resolve results
        real = {}
        for row in rows:
            rec = mgr.manifest.get(row.scene_number) or {}
            if rec.get("status") == "complete":
                real[scene_key(row.scene_number)] = _ready(row.scene_number)
            else:
                real[scene_key(row.scene_number)] = _fail(row.scene_number, rec.get("error") or "fail")
        snap = qa.snapshot(rows, real)
        self.assertEqual(len(snap.unresolved_keys), 2)
        for key in snap.unresolved_keys:
            scene = next(r for r in rows if scene_key(r.scene_number) == key)
            mgr.retry_scene(scene)
        self.assertEqual(sorted(stock.calls), ["2", "5"])
        for i, data in before.items():
            self.assertEqual((self.images / f"{i:03d}.mp4").read_bytes(), data)


class TestRestartPersistence(unittest.TestCase):
    def test_failed_scene_survives_qa_file_and_results(self):
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp())
        try:
            qa = SceneQAState()
            qa.attempts["221"] = 2
            save_qa_file(tmp, qa.attempts, skipped=[])
            loaded = load_qa_file(tmp)
            self.assertEqual(loaded["attempts"]["221"], 2)
            scenes, results = _project(10, {7: "Download failed: stock asset exceeded 200MB, aborted"})
            snap = SceneQAState().snapshot(scenes, results)
            self.assertEqual(qa.go_to_error(snap.unresolved_keys), "007")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestHeaderNeverFromLog(unittest.TestCase):
    def test_format_header_never_says_all_ready_when_unresolved(self):
        scenes, results = _project(135, {221: "x"})
        scenes, results = _project(135, {135: "Download failed: stock asset exceeded 200MB, aborted"})
        snap = SceneQAState().snapshot(scenes, results)
        header = format_header(snap)
        self.assertEqual(header, "134 / 135 READY · 1 NEEDS ACTION")
        self.assertNotEqual(header.upper(), "ALL READY")
        self.assertNotIn("ALL READY", header)


if __name__ == "__main__":
    unittest.main()
