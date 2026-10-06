#!/usr/bin/env python3
"""The production orchestration layer: event log, job ledger, failure recovery, dependency graph, surgical
regeneration plan, analytics, and the AssetManager hooks (transient retries for non-Flow sources only).

No network, no Flow, no rendering.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import asset_manager as am
from asset_manager import AssetManager, asset_record_matches
from production import analytics, events, jobs, recovery, regeneration
from production.graph import ProductionGraph, load_snapshot, save_snapshot
from production.recovery import RetryPolicy, classify_failure, should_auto_retry
from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneRow, SceneStatus


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.images = self.tmp / "assets"
        self.images.mkdir()
        events.bind_project(None)

    def tearDown(self):
        events.bind_project(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


# ----------------------------------------------------------------------------- events
class TestEvents(_Tmp):
    def test_emit_and_read_back_with_run_id(self):
        events.bind_project(self.state)
        with events.run("render") as run:
            events.emit("asset", scene="001", outcome="generated")
        got = events.read(self.state)
        self.assertEqual([e["kind"] for e in got], ["run_start", "asset", "run_end"])
        self.assertTrue(all(e["run"] == run["id"] for e in got))
        self.assertEqual(got[-1]["outcome"], "ok")

    def test_start_end_run_and_worker_threads_inherit_the_run(self):
        import threading

        events.bind_project(self.state)
        token = events.start_run("assets")
        t = threading.Thread(target=lambda: events.emit("asset", scene="002", outcome="reused"))
        t.start(); t.join()
        events.end_run(token, "partial")
        got = events.read(self.state)
        self.assertEqual(got[1]["run"], token["id"])  # emitted from a thread without the context variable
        self.assertEqual(got[-1]["outcome"], "partial")
        self.assertEqual(events.current_run(), "")

    def test_corrupt_lines_are_skipped_and_rotation_keeps_history(self):
        events.bind_project(self.state)
        events.emit("a")
        with open(events.events_path(self.state), "a") as f:
            f.write("{not json\n")
        with mock.patch.object(events, "MAX_BYTES", 10):
            events.emit("b")  # rotates the old file to .1 first
        kinds = [e["kind"] for e in events.read(self.state)]
        self.assertEqual(kinds, ["a", "b"])

    def test_no_project_bound_keeps_events_in_memory(self):
        events.emit("cache", cache="whisper", hit=True)
        self.assertEqual(events.read(None, kinds=["cache"])[-1]["cache"], "whisper")


# ----------------------------------------------------------------------------- jobs
class TestJobLedger(_Tmp):
    def test_lifecycle_timings_and_persistence(self):
        ledger = jobs.JobLedger(self.state, project="p")
        job = ledger.create("asset", scene="7", source="stock_video")
        self.assertEqual(job.scene, "007")
        ledger.start(job.id)
        ledger.complete(job.id, outputs=["/x/007.mp4"])
        ledger.flush()
        again = jobs.JobLedger(self.state)
        j = again.get(job.id)
        self.assertEqual((j.state, j.attempts, j.outputs), ("completed", 1, ["/x/007.mp4"]))
        self.assertGreaterEqual(j.exec_s, 0.0)

    def test_running_job_of_a_closed_session_is_interrupted_and_retryable(self):
        ledger = jobs.JobLedger(self.state)
        job = ledger.create("render")
        ledger.start(job.id)
        ledger.flush()
        reopened = jobs.JobLedger(self.state)
        j = reopened.get(job.id)
        self.assertEqual((j.state, j.error_class, j.retryable), ("failed", "interrupted", True))
        self.assertEqual([x.id for x in reopened.interrupted()], [job.id])

    def test_duplicate_active_job_is_reused(self):
        ledger = jobs.JobLedger(None)
        a = ledger.create("asset", scene="3")
        b = ledger.create("asset", scene="003")
        self.assertIs(a, b)

    def test_failure_classification_retrying_and_blocked_dependents(self):
        ledger = jobs.JobLedger(None)
        asset = ledger.create("asset", scene="4")
        render = ledger.create("render", depends_on=[asset.id])
        ledger.start(asset.id)
        ledger.fail(asset.id, "Download failed: Read timed out.", will_retry=True)
        self.assertEqual(ledger.get(asset.id).state, "retrying")
        ledger.start(asset.id)
        ledger.fail(asset.id, "No suitable stock video result found for \"x\".")
        self.assertEqual((ledger.get(asset.id).state, ledger.get(asset.id).error_class), ("failed", "not_found"))
        self.assertEqual(ledger.get(render.id).state, "blocked")
        st = ledger.status()
        self.assertEqual((st["failed"], st["blocked"]), (1, 1))

    def test_cancel_is_cancelled_not_failed(self):
        ledger = jobs.JobLedger(None)
        job = ledger.create("asset", scene="1")
        ledger.start(job.id)
        ledger.fail(job.id, "Cancelled.")
        self.assertEqual(ledger.get(job.id).state, "cancelled")

    def test_track_context_manager(self):
        ledger = jobs.JobLedger(None)
        with ledger.track("align") as job:
            pass
        self.assertEqual(ledger.get(job.id).state, "completed")
        with self.assertRaises(ValueError):
            with ledger.track("render") as job2:
                raise ValueError("ffmpeg broke")
        self.assertEqual(ledger.get(job2.id).state, "failed")

    def test_history_is_capped(self):
        ledger = jobs.JobLedger(self.state)
        with mock.patch.object(jobs, "MAX_FINISHED", 5):
            for i in range(12):
                j = ledger.create("asset", scene=i)
                ledger.start(j.id)
                ledger.complete(j.id)
            ledger.flush()
        self.assertLessEqual(len(jobs.JobLedger(self.state).jobs()), 6)


# ----------------------------------------------------------------------------- recovery
class TestFailureClassification(unittest.TestCase):
    def test_kinds(self):
        cases = {
            "Download failed: HTTPSConnectionPool(host='videos.pexels.com'): Read timed out.": ("timeout", True),
            "Download failed: ('Connection aborted.', ConnectionResetError(54))": ("network", True),
            "Pexels rate limit reached (429) — try again later.": ("rate_limit", True),
            "503 Service Unavailable": ("busy", True),
            "No suitable stock video result found for \"x\".": ("not_found", False),
            "Pexels rejected the API key (401 Unauthorized).": ("auth", False),
            "Download failed: less than 3 GB free on the disk": ("disk", False),
            "Download failed: stock asset exceeded 200MB, aborted": ("too_large", False),
            "Download failed: download took longer than 1800s, aborted": ("slow", False),
            "Download failed: download cancelled": ("cancelled", False),
            "No search query given for this youtube_video scene.": ("invalid_input", False),
            "PUBLIC_ERROR_UNUSUAL_ACTIVITY": ("flow_hold", False),
            "": ("unknown", False),
        }
        for text, (kind, retryable) in cases.items():
            fc = classify_failure(text)
            self.assertEqual((fc.kind, fc.retryable), (kind, retryable), text)
        self.assertEqual(classify_failure(TimeoutError("read timeout")).kind, "timeout")

    def test_flow_is_never_auto_retried_here(self):
        transient = classify_failure("Read timed out")
        self.assertTrue(should_auto_retry(transient, source="stock_video", attempt=1))
        for src in ("flow_video", "flow_image", "video", "image"):
            self.assertFalse(should_auto_retry(transient, source=src, attempt=1))
        self.assertFalse(should_auto_retry(transient, source="stock_video", attempt=3))

    def test_backoff_grows_and_is_capped(self):
        p = RetryPolicy(max_attempts=5, base_delay_s=2, max_delay_s=10)
        self.assertEqual([p.delay(a) for a in (1, 2, 3, 4)], [2, 4, 8, 10])


class TestRecoveryScan(_Tmp):
    def test_partials_and_broken_cache_entries_are_cleaned_finished_files_are_not(self):
        (self.images / "004.mp4.part").write_bytes(b"half")
        (self.images / "005_part.mp4").write_bytes(b"half")
        (self.images / "006.mp4").write_bytes(b"done")
        clips = self.state / "render_cache"
        clips.mkdir()
        (clips / "scene_1_aaaa.mp4").write_bytes(b"clip")
        (self.state / "render_cache.json").write_text(json.dumps({"schema_version": 3, "entries": {
            "1": {"cache_key": "k1", "clip_file": "scene_1_aaaa.mp4"},
            "2": {"cache_key": "k2", "clip_file": "scene_2_gone.mp4"}}}))
        (self.images / am.MANIFEST_NAME).write_text(json.dumps({
            "006": {"status": "complete", "local_path": str(self.images / "006.mp4")},
            "007": {"status": "complete", "local_path": str(self.images / "007.mp4")}}))

        class WS:
            state_dir = self.state
            assets_dir = self.images

        report = recovery.scan_project(WS(), images_dir=self.images)
        actions = sorted((a.action, Path(a.target).name if a.action == "delete_partial" else a.target) for a in report.actions)
        self.assertEqual(actions, [("delete_partial", "004.mp4.part"), ("delete_partial", "005_part.mp4"),
                                   ("drop_render_cache_entry", "2"), ("reresolve_asset", "007")])
        recovery.apply(report, WS())
        self.assertFalse((self.images / "004.mp4.part").exists())
        self.assertFalse((self.images / "005_part.mp4").exists())
        self.assertTrue((self.images / "006.mp4").exists())
        index = json.loads((self.state / "render_cache.json").read_text())
        self.assertEqual(sorted(index["entries"]), ["1"])
        self.assertIn("half-finished", report.summary())


# ----------------------------------------------------------------------------- AssetManager hooks
class _ScriptedProvider(AssetProvider):
    """Fails with the scripted errors, then succeeds."""

    def __init__(self, source: AssetSource, errors):
        self.source, self.errors, self.calls = source, list(errors), 0

    def resolve(self, scene, images_dir, log=print):
        self.calls += 1
        if self.errors:
            err = self.errors.pop(0)
            return AssetResult(scene.scene_number, None, None, self.source, SceneStatus.FAILED, error=err)
        p = Path(images_dir) / f"{int(scene.scene_number):03d}.jpg"
        p.write_bytes(b"img")
        return AssetResult(scene.scene_number, p, MediaType.IMAGE, self.source, SceneStatus.READY,
                           metadata={"provider_asset_id": f"id{self.calls}"})

    def regenerate(self, scene, images_dir, exclude=None, log=print):
        return self.resolve(scene, images_dir, log)


class TestAssetManagerRecovery(_Tmp):
    def setUp(self):
        super().setUp()
        self.ledger = jobs.bind_project(self.state, "t")
        events.bind_project(self.state)
        self.fast = mock.patch.object(am, "TRANSIENT_RETRY_POLICY", RetryPolicy(max_attempts=3, base_delay_s=0, max_delay_s=0))
        self.fast.start()

    def tearDown(self):
        self.fast.stop()
        jobs.bind_project(None)
        super().tearDown()

    def _scene(self, n="1", asset_type="stock_image"):
        return SceneRow(scene_number=n, script_segment="x", asset_type=asset_type, prompt="p", stock="harbor at dawn")

    def test_transient_stock_failure_is_retried_and_recovers(self):
        prov = _ScriptedProvider(AssetSource.STOCK_IMAGE, ["Download failed: Read timed out.", "503 Service Unavailable"])
        mgr = AssetManager(self.images, stock_provider=prov, log=lambda *_: None)
        summary = mgr.resolve_all([self._scene()])
        self.assertTrue(summary.results["1"].ok)
        self.assertEqual(prov.calls, 3)
        job = self.ledger.latest_for_scene("1")
        self.assertEqual((job.state, job.attempts), ("completed", 3))
        outcomes = [e.get("outcome") for e in events.read(self.state, kinds=["asset"])]
        self.assertEqual(outcomes, ["generated"])

    def test_permanent_failure_is_not_retried(self):
        prov = _ScriptedProvider(AssetSource.STOCK_IMAGE, ["No suitable stock image result found for \"x\"."] * 3)
        mgr = AssetManager(self.images, stock_provider=prov, log=lambda *_: None)
        summary = mgr.resolve_all([self._scene()])
        self.assertFalse(summary.results["1"].ok)
        self.assertEqual(prov.calls, 1)
        job = self.ledger.latest_for_scene("1")
        self.assertEqual((job.state, job.error_class), ("failed", "not_found"))

    def test_retries_stop_at_the_policy_limit(self):
        prov = _ScriptedProvider(AssetSource.STOCK_IMAGE, ["Read timed out"] * 5)
        mgr = AssetManager(self.images, stock_provider=prov, log=lambda *_: None)
        self.assertFalse(mgr.resolve_all([self._scene()]).results["1"].ok)
        self.assertEqual(prov.calls, 3)

    def test_flow_keeps_its_own_single_retry(self):
        flow = _ScriptedProvider(AssetSource.FLOW_IMAGE, ["Read timed out"] * 5)
        mgr = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        result = mgr._resolve_one(self._scene(asset_type="image"), AssetSource.FLOW_IMAGE)
        self.assertFalse(result.ok)
        self.assertEqual(flow.calls, 2)  # exactly the frozen Flow rule: one same-source retry, nothing added

    def test_cancellation_during_backoff_stops_retrying(self):
        prov = _ScriptedProvider(AssetSource.STOCK_IMAGE, ["Read timed out"] * 5)
        mgr = AssetManager(self.images, stock_provider=prov, log=lambda *_: None)
        with mock.patch.object(am, "TRANSIENT_RETRY_POLICY", RetryPolicy(max_attempts=3, base_delay_s=5, max_delay_s=5)):
            import threading

            threading.Timer(0.3, lambda: mgr.request_cancel_scene("1")).start()
            t = time.monotonic()
            mgr._resolve_one(self._scene(), AssetSource.STOCK_IMAGE)
            self.assertLess(time.monotonic() - t, 3.0)
        self.assertEqual(prov.calls, 1)

    def test_cache_hit_is_recorded_as_reuse(self):
        prov = _ScriptedProvider(AssetSource.STOCK_IMAGE, [])
        mgr = AssetManager(self.images, stock_provider=prov, log=lambda *_: None)
        mgr.resolve_all([self._scene()])
        mgr.resolve_all([self._scene()])
        self.assertEqual(prov.calls, 1)
        outcomes = [e.get("outcome") for e in events.read(self.state, kinds=["asset"])]
        self.assertEqual(outcomes, ["generated", "reused"])


class TestCanonicalReuseRule(unittest.TestCase):
    def test_rule_matches_prompt_and_query(self):
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="stock_video", prompt="", stock="harbor")
        rec = {"status": "complete", "source": "stock_video", "stock_query": "harbor"}
        self.assertTrue(asset_record_matches(rec, scene, AssetSource.STOCK_VIDEO))
        self.assertFalse(asset_record_matches(dict(rec, stock_query="mountain"), scene, AssetSource.STOCK_VIDEO))
        self.assertTrue(asset_record_matches(dict(rec, source="manual", stock_query="other"), scene, AssetSource.STOCK_VIDEO))
        self.assertFalse(asset_record_matches(dict(rec, status="failed"), scene, AssetSource.STOCK_VIDEO))


# ----------------------------------------------------------------------------- graph & regeneration
def _rows():
    return [
        {"scene_number": "1", "script_segment": "It began at night.", "asset_type": "stock_video", "prompt": "plant at night"},
        {"scene_number": "2", "script_segment": "The reactor was tested.", "asset_type": "stock_image", "prompt": "control room"},
        {"scene_number": "3", "script_segment": "Then it failed.", "asset_type": "stock_video", "prompt": "explosion fire"},
    ]


class TestDependencyGraph(_Tmp):
    def _assets(self, rows):
        man = {}
        for r in rows:
            n = int(r["scene_number"])
            p = self.images / f"{n:03d}.mp4"
            p.write_bytes(b"m" * n)
            man[f"{n:03d}"] = {"status": "complete", "source": r["asset_type"], "stock_query": r["prompt"], "local_path": str(p)}
        return man

    def _graph(self, rows, man, **kw):
        kw.setdefault("timings", {"1": (0, 4), "2": (4, 7), "3": (7, 10)})
        return ProductionGraph.build(rows, manifest=man, images_dir=self.images, audio_key="a", **kw)

    def test_no_change_reuses_everything(self):
        rows = _rows(); man = self._assets(rows)
        g = self._graph(rows, man)
        cs = g.diff(g.snapshot())
        self.assertEqual((cs.assets_to_regenerate, cs.clips_to_render, cs.needs_realign), ([], [], False))

    def test_first_run_keeps_reusable_assets(self):
        rows = _rows(); man = self._assets(rows)
        cs = self._graph(rows, man).diff(None)
        self.assertTrue(cs.first_run)
        self.assertEqual(cs.assets_to_regenerate, [])
        self.assertEqual(cs.clips_to_render, ["001", "002", "003"])

    def test_prompt_change_regenerates_one_asset_and_one_clip(self):
        rows = _rows(); man = self._assets(rows)
        snap = self._graph(rows, man).snapshot()
        rows[1]["prompt"] = "a different control room"
        cs = self._graph(rows, man).diff(snap)
        self.assertEqual((cs.assets_to_regenerate, cs.clips_to_render), (["002"], ["002"]))
        self.assertEqual(cs.changed, {"002": ["visual"]})

    def test_caption_change_never_regenerates_the_asset(self):
        rows = _rows(); man = self._assets(rows)
        snap = self._graph(rows, man).snapshot()
        rows[2]["caption"] = "MELTDOWN"
        cs = self._graph(rows, man).diff(snap)
        self.assertEqual((cs.assets_to_regenerate, cs.clips_to_render), ([], ["003"]))

    def test_narration_change_rerenders_only_scenes_whose_length_changed(self):
        rows = _rows(); man = self._assets(rows)
        snap = self._graph(rows, man).snapshot()
        rows[0]["script_segment"] = "It began at night, quietly."
        before = self._graph(rows, man, timings={}).diff(snap)  # not aligned yet: any scene may move
        self.assertEqual(before.clips_to_render, ["001", "002", "003"])
        self.assertTrue(before.needs_realign)
        # aligned: scene 1 grew by a second, 2 and 3 only moved later
        after = self._graph(rows, man, timings={"1": (0, 5), "2": (5, 8), "3": (8, 11)}).diff(snap)
        self.assertEqual(after.clips_to_render, ["001"])
        self.assertEqual(after.assets_to_regenerate, [])

    def test_swapped_media_file_rerenders_its_clip_without_regenerating(self):
        rows = _rows(); man = self._assets(rows)
        snap = self._graph(rows, man).snapshot()
        time.sleep(0.01)
        (self.images / "002.mp4").write_bytes(b"replaced by Change Source")
        cs = self._graph(rows, man).diff(snap)
        self.assertEqual((cs.assets_to_regenerate, cs.clips_to_render), ([], ["002"]))

    def test_missing_file_is_regenerated(self):
        rows = _rows(); man = self._assets(rows)
        snap = self._graph(rows, man).snapshot()
        (self.images / "003.mp4").unlink()
        cs = self._graph(rows, man).diff(snap)
        self.assertEqual(cs.assets_to_regenerate, ["003"])

    def test_settings_change_rerenders_all_clips_but_keeps_assets(self):
        rows = _rows(); man = self._assets(rows)
        snap = self._graph(rows, man, settings={"resolution": "1920x1080"}).snapshot()
        cs = self._graph(rows, man, settings={"resolution": "3840x2160"}).diff(snap)
        self.assertEqual((cs.assets_to_regenerate, cs.clips_to_render), ([], ["001", "002", "003"]))
        self.assertIn("settings", cs.global_changes)

    def test_overscaled_arrow_links_connected_scenes(self):
        rows = [dict(r) for r in _rows()]
        rows[0]["node_id"], rows[1]["node_id"], rows[2]["node_id"] = "a", "b", "c"
        rows[1]["edge_from"] = "a"
        man = self._assets(rows)
        g = self._graph(rows, man)
        hit = g.impact("1", "structure")
        self.assertEqual(hit["rerender_clips"], ["001", "002"])

    def test_impact_queries(self):
        rows = _rows(); man = self._assets(rows)
        g = self._graph(rows, man)
        self.assertEqual(g.impact(2, "visual")["regenerate_assets"], ["002"])
        self.assertEqual(g.impact(2, "text")["regenerate_assets"], [])
        self.assertTrue(g.impact(2, "narration")["realign"])
        self.assertIn("asset:002", g.explain_scene(2)["built_from"])

    def test_snapshot_round_trip(self):
        rows = _rows(); man = self._assets(rows)
        g = self._graph(rows, man)
        save_snapshot(self.state, g)
        self.assertEqual(g.diff(load_snapshot(self.state)).clips_to_render, [])


class TestRegenerationPlan(_Tmp):
    def test_plan_lines_and_measured_estimate(self):
        rows = _rows()
        man = {}
        for r in rows:
            n = int(r["scene_number"]); p = self.images / f"{n:03d}.mp4"; p.write_bytes(b"x" * n)
            man[f"{n:03d}"] = {"status": "complete", "source": r["asset_type"], "stock_query": r["prompt"], "local_path": str(p)}
        g = ProductionGraph.build(rows, manifest=man, images_dir=self.images, audio_key="a", timings={"1": (0, 1), "2": (1, 2), "3": (2, 3)})
        snap = g.snapshot()
        rows[0]["prompt"] = "something else"
        g2 = ProductionGraph.build(rows, manifest=man, images_dir=self.images, audio_key="a", timings={"1": (0, 1), "2": (1, 2), "3": (2, 3)})
        history = [{"kind": "render", "clips_rendered": 10, "scene_render_s": 50.0},
                   {"kind": "job", "type": "asset", "state": "completed", "source": "stock_video", "exec_s": 8.0}]
        plan = regeneration.plan_for(g2, snap, history=history, sources={"001": "stock_video"})
        self.assertEqual((plan.assets_regenerate, plan.clips_render), (["001"], ["001"]))
        self.assertAlmostEqual(plan.est_saved_s, 2 * 5.0)  # two clips kept x 5 s measured per clip
        self.assertAlmostEqual(plan.est_asset_s, 8.0)
        text = "\n".join(plan.lines())
        self.assertIn("Scene 001: visual instruction changed", text)
        self.assertIn("re-render 1 clip(s)", text)

    def test_clips_not_in_the_render_cache_are_planned_for_rendering(self):
        rows = _rows()
        man = {}
        for r in rows:
            n = int(r["scene_number"]); p = self.images / f"{n:03d}.mp4"; p.write_bytes(b"x" * n)
            man[f"{n:03d}"] = {"status": "complete", "source": r["asset_type"], "stock_query": r["prompt"], "local_path": str(p)}
        (self.images / am.MANIFEST_NAME).write_text(json.dumps(man))
        tim = {"1": (0, 1), "2": (1, 2), "3": (2, 3)}
        g, _ = regeneration.prepare(rows, images_dir=self.images, state_dir=self.state, audio_key="a", timings=tim)
        regeneration.commit(g, self.state)
        (self.state / "render_cache.json").write_text(json.dumps({"schema_version": 3, "entries": {"1": {}, "3": {}}}))
        _, plan = regeneration.prepare(rows, images_dir=self.images, state_dir=self.state, audio_key="a", timings=tim)
        self.assertEqual((plan.clips_render, plan.clips_reuse), (["002"], ["001", "003"]))

    def test_render_stats_from_perf_recorder(self):
        from perf_instrumentation import PerfRecorder

        perf = PerfRecorder()
        perf.record("scene_render", 9.0)
        perf.record("mux", 1.0)
        perf.note_cache(True); perf.note_cache(False)
        st = regeneration.render_stats(perf, video_s=20.0, fps=30)
        self.assertEqual((st["frames"], st["fps"], st["speed_x"], st["clips_reused"], st["clips_rendered"]),
                         (600, 60.0, 2.0, 1, 1))


class TestAnalytics(unittest.TestCase):
    def test_summary_from_events(self):
        evts = [
            {"kind": "run_start", "run": "r1"},
            {"kind": "asset", "outcome": "generated", "source": "stock_video", "run": "r1"},
            {"kind": "asset", "outcome": "reused", "source": "flow_image", "run": "r1"},
            {"kind": "asset", "outcome": "failed", "source": "youtube_video", "run": "r1"},
            {"kind": "job", "type": "asset", "state": "completed", "source": "stock_video", "attempt": 2, "exec_s": 4.0, "wait_s": 1.0},
            {"kind": "job", "type": "asset", "state": "failed", "source": "youtube_video", "attempt": 1, "exec_s": 9.0,
             "wait_s": 0.0, "error_class": "not_found"},
            {"kind": "cache", "cache": "render_clip", "hit": True},
            {"kind": "cache", "cache": "editorial_ai", "hit": True},
            {"kind": "ai_call", "task": "script_analysis", "ok": True, "duration_s": 12.0, "tokens_in": 100, "tokens_out": 50},
            {"kind": "render", "duration_s": 30.0, "frames": 900, "fps": 30.0, "clips_reused": 5, "clips_rendered": 5},
            {"kind": "run_end", "run": "r1", "outcome": "ok", "duration_s": 60.0},
        ]
        r = analytics.summarize(evts, scenes=10, duration_s=30.0)
        self.assertEqual((r.assets["generated"], r.assets["reused"], r.assets["failed"]), (1, 1, 1))
        self.assertEqual(r.providers["stock_video"]["retries"], 1)
        self.assertEqual(r.queue["failures_by_class"], {"not_found": 1})
        self.assertEqual(r.rendering["rerender_rate"], 0.5)
        self.assertEqual((r.ai["calls"], r.ai["avoided_calls"], r.ai["tokens_in"]), (1, 1, 100))
        text = analytics.format_report(r)
        for heading in ("PROJECT", "ASSETS", "PROVIDERS", "JOBS", "RENDERING", "AI"):
            self.assertIn(heading, text)


class TestGeminiCallsAreRecorded(unittest.TestCase):
    def test_complete_emits_ai_call_with_tokens(self):
        import visual_director.llm as llm

        class R:
            status_code = 200
            text = ""

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}],
                        "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2}}

        with mock.patch("requests.post", return_value=R()):
            llm.GeminiLLM(api_key="k").complete("s", "u")
        e = events.read(None, kinds=["ai_call"])[-1]
        self.assertEqual((e["ok"], e["tokens_in"], e["tokens_out"], e["cached"]), (True, 7, 2, False))

    def test_failed_call_is_recorded_and_still_raises(self):
        import visual_director.llm as llm

        with mock.patch("requests.post", side_effect=__import__("requests").ConnectionError("down")):
            with self.assertRaises(llm.LLMError):
                llm.GeminiLLM(api_key="k").complete("s", "u")
        e = events.read(None, kinds=["ai_call"])[-1]
        self.assertEqual((e["ok"], e["error_class"]), (False, "network"))

    def test_vision_check_sends_the_key_in_a_header_not_the_url(self):
        from visual_qa import semantic

        img = Path(tempfile.mkdtemp()) / "f.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"0" * 100)
        seen = {}

        class R:
            status_code = 200

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"semantic_match": 0.8, "usable": true}'}]}}]}

        def post(url, **kw):
            seen["url"], seen["headers"] = url, kw.get("headers") or {}
            return R()

        scene = SceneRow(scene_number="1", script_segment="harbor", prompt="harbor at dawn")
        with mock.patch("requests.post", side_effect=post):
            score, _ = semantic.vision_semantic_score(scene, [img], settings={"gemini_api_key": "SECRET"})
        self.assertEqual(score, 0.8)
        self.assertNotIn("SECRET", seen["url"])
        self.assertEqual(seen["headers"].get("x-goog-api-key"), "SECRET")
        shutil.rmtree(img.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
