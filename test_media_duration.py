"""Actual-vs-requested asset duration.

Every fixture here is synthesised locally with ffmpeg or is plain metadata.
No provider is contacted and no Flow generation is ever invoked — see
TestCreditSafety, which asserts that explicitly.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from media_duration import (
    ACTUAL_DURATION_KEY,
    LEGACY_DURATION_KEY,
    REQUESTED_DURATION_KEY,
    annotate_actual_duration,
    cached_duration,
    coerce_duration,
    probe_media_duration,
)


def _clip(path: Path, seconds: float) -> Path:
    subprocess.run(
        ["bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c=navy:s=320x180:d={seconds}", "-r", "25", "-y", str(path)],
        check=True,
    )
    return path


def _still(path: Path) -> Path:
    subprocess.run(
        ["bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=navy:s=320x180", "-frames:v", "1", "-y", str(path)],
        check=True,
    )
    return path


class TestDurationDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.video = _clip(cls.dir / "clip.mp4", 8.2)
        cls.image = _still(cls.dir / "still.png")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_real_duration_is_measured_from_the_file(self) -> None:
        self.assertAlmostEqual(probe_media_duration(self.video), 8.2, delta=0.15)

    def test_a_still_has_no_duration(self) -> None:
        self.assertIsNone(probe_media_duration(self.image))

    def test_a_missing_or_unreadable_file_is_safe(self) -> None:
        self.assertIsNone(probe_media_duration(self.dir / "nope.mp4"))
        junk = self.dir / "junk.mp4"
        junk.write_bytes(b"not a video")
        self.assertIsNone(probe_media_duration(junk))
        self.assertIsNone(probe_media_duration(self.dir))

    def test_malformed_durations_are_rejected(self) -> None:
        for bad in (None, "", "abc", [], {}, True, False, 0, -3, float("nan"), float("inf")):
            self.assertIsNone(coerce_duration(bad), repr(bad))

    def test_valid_numbers_are_accepted(self) -> None:
        self.assertEqual(coerce_duration("8.2"), 8.2)
        self.assertEqual(coerce_duration(8), 8.0)


class TestCachedMetadataIsRespected(unittest.TestCase):
    def test_existing_actual_duration_is_reused(self) -> None:
        meta = {ACTUAL_DURATION_KEY: 6.5}
        self.assertEqual(cached_duration(meta), 6.5)

    def test_the_legacy_duration_key_counts_as_cached(self) -> None:
        """Providers already wrote `duration`; it must not force a re-probe."""
        self.assertEqual(cached_duration({LEGACY_DURATION_KEY: 4.25}), 4.25)

    def test_a_corrupt_cached_value_is_ignored(self) -> None:
        for bad in ("soon", -1, 0, None, {}):
            self.assertIsNone(cached_duration({ACTUAL_DURATION_KEY: bad}), repr(bad))

    def test_cached_metadata_avoids_probing_entirely(self) -> None:
        meta = {ACTUAL_DURATION_KEY: 3.0}
        annotate_actual_duration(meta, Path("/definitely/not/here.mp4"), is_video=True)
        self.assertEqual(meta[ACTUAL_DURATION_KEY], 3.0)

    def test_no_metadata_is_not_a_crash(self) -> None:
        self.assertIsNone(cached_duration(None))
        self.assertIsNone(annotate_actual_duration(None, "x", is_video=True))


class TestMetadataPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.video = _clip(cls.dir / "c.mp4", 5.0)
        cls.image = _still(cls.dir / "s.png")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_actual_and_requested_are_stored_separately(self) -> None:
        meta = {}
        annotate_actual_duration(meta, self.video, is_video=True, requested=10)
        self.assertAlmostEqual(meta[ACTUAL_DURATION_KEY], 5.0, delta=0.15)
        self.assertEqual(meta[REQUESTED_DURATION_KEY], 10.0)
        self.assertNotEqual(meta[ACTUAL_DURATION_KEY], meta[REQUESTED_DURATION_KEY])

    def test_the_legacy_key_is_kept_in_step(self) -> None:
        meta = {}
        annotate_actual_duration(meta, self.video, is_video=True)
        self.assertEqual(meta[LEGACY_DURATION_KEY], meta[ACTUAL_DURATION_KEY])

    def test_an_existing_legacy_value_is_not_overwritten(self) -> None:
        meta = {LEGACY_DURATION_KEY: 2.0}
        annotate_actual_duration(meta, self.video, is_video=True)
        self.assertEqual(meta[LEGACY_DURATION_KEY], 2.0)

    def test_images_get_no_actual_duration(self) -> None:
        meta = {}
        annotate_actual_duration(meta, self.image, is_video=False, requested=10)
        self.assertNotIn(ACTUAL_DURATION_KEY, meta)
        self.assertNotIn(LEGACY_DURATION_KEY, meta)

    def test_a_requested_duration_alone_never_implies_an_actual_one(self) -> None:
        """The whole point: the setting must not masquerade as reality."""
        meta = {}
        annotate_actual_duration(meta, None, is_video=True, requested=10)
        self.assertEqual(meta[REQUESTED_DURATION_KEY], 10.0)
        self.assertNotIn(ACTUAL_DURATION_KEY, meta)


class _FakeResult:
    """Stand-in for AssetResult — no provider, no network, no generation."""

    def __init__(self, scene_number, metadata=None):
        self.scene_number = scene_number
        self.metadata = metadata


class TestEditorialIntegration(unittest.TestCase):
    """The plan must carry the real source length, without confusing it with
    the scene's own required duration."""

    def _plan(self, asset_results=None, scene_seconds=7.4):
        from editorial.builder import build_editorial_plan
        rows = [{"scene_number": "1", "script_segment": "narration text",
                 "asset_type": "video", "prompt": "p"}]
        aligned = [{"scene_number": "1", "script_segment": "narration text",
                    "start_time": 0.0, "end_time": scene_seconds}]
        return build_editorial_plan(rows, aligned, scene_seconds,
                                    asset_results=asset_results)

    def test_actual_duration_reaches_the_plan(self) -> None:
        results = {"001": _FakeResult("1", {ACTUAL_DURATION_KEY: 8.2,
                                            REQUESTED_DURATION_KEY: 10.0})}
        scene = self._plan(results).scenes[0]
        self.assertEqual(scene.actual_asset_duration, 8.2)
        self.assertEqual(scene.requested_asset_duration, 10.0)

    def test_requested_is_never_mistaken_for_actual(self) -> None:
        """A requested 10s with a real 8.2s file must stay two numbers."""
        results = {"001": _FakeResult("1", {ACTUAL_DURATION_KEY: 8.2,
                                            REQUESTED_DURATION_KEY: 10.0})}
        scene = self._plan(results).scenes[0]
        self.assertNotEqual(scene.actual_asset_duration, scene.requested_asset_duration)

    def test_narration_stays_authoritative_for_scene_length(self) -> None:
        """Neither asset figure may move the scene's own duration."""
        plain = self._plan(None, scene_seconds=7.4).scenes[0]
        for meta in ({ACTUAL_DURATION_KEY: 2.0}, {ACTUAL_DURATION_KEY: 30.0},
                     {REQUESTED_DURATION_KEY: 10.0}):
            scene = self._plan({"001": _FakeResult("1", dict(meta))},
                               scene_seconds=7.4).scenes[0]
            self.assertEqual(scene.duration, plain.duration)
            self.assertEqual(scene.start, plain.start)
            self.assertEqual(scene.end, plain.end)

    def test_a_shortfall_is_exposed_not_acted_on(self) -> None:
        results = {"001": _FakeResult("1", {ACTUAL_DURATION_KEY: 5.1})}
        scene = self._plan(results, scene_seconds=7.4).scenes[0]
        self.assertFalse(scene.source_covers_scene)
        self.assertAlmostEqual(scene.asset_duration_shortfall, 2.3, places=2)

    def test_ample_source_is_reported_as_covering(self) -> None:
        results = {"001": _FakeResult("1", {ACTUAL_DURATION_KEY: 8.2})}
        scene = self._plan(results, scene_seconds=5.4).scenes[0]
        self.assertTrue(scene.source_covers_scene)
        self.assertEqual(scene.asset_duration_shortfall, 0.0)

    def test_unknown_source_duration_is_None_not_zero(self) -> None:
        scene = self._plan(None).scenes[0]
        self.assertIsNone(scene.actual_asset_duration)
        self.assertIsNone(scene.source_covers_scene)
        self.assertIsNone(scene.asset_duration_shortfall)

    def test_scene_number_padding_is_tolerated(self) -> None:
        for key, num in (("001", "001"), ("1", "1")):
            results = {key: _FakeResult(num, {ACTUAL_DURATION_KEY: 6.0})}
            self.assertEqual(self._plan(results).scenes[0].actual_asset_duration, 6.0)

    def test_junk_asset_results_never_break_plan_building(self) -> None:
        for junk in (None, {}, [], "nonsense", 42,
                     {"001": None}, {"001": _FakeResult("1", "not-a-dict")},
                     {"001": _FakeResult("", {ACTUAL_DURATION_KEY: 5.0})}):
            plan = self._plan(junk)
            self.assertEqual(len(plan.scenes), 1)

    def test_the_plan_survives_a_save_load_roundtrip(self) -> None:
        from editorial.schema import EditorialPlan
        results = {"001": _FakeResult("1", {ACTUAL_DURATION_KEY: 8.2,
                                            REQUESTED_DURATION_KEY: 10.0})}
        plan = self._plan(results)
        again = EditorialPlan.from_dict(plan.to_dict())
        self.assertEqual(again.scenes[0].actual_asset_duration, 8.2)
        self.assertEqual(again.scenes[0].requested_asset_duration, 10.0)


class TestProviderNeutrality(unittest.TestCase):
    """One mechanism for every video provider; images untouched."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.video = _clip(cls.dir / "v.mp4", 6.0)
        cls.image = _still(cls.dir / "i.png")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _annotate(self, source_name, is_video=True):
        from providers.base import AssetResult, AssetSource, MediaType, SceneStatus
        from asset_manager import AssetManager
        result = AssetResult(
            "1", self.video if is_video else self.image,
            MediaType.VIDEO if is_video else MediaType.IMAGE,
            getattr(AssetSource, source_name), SceneStatus.READY, metadata={},
        )
        stub = AssetManager.__new__(AssetManager)   # no provider wiring, no network
        stub.settings = {"flow_video_duration": 10}
        AssetManager._annotate_actual_duration(stub, result)
        return result.metadata

    def test_flow_video(self) -> None:
        self.assertIn(ACTUAL_DURATION_KEY, self._annotate("FLOW_VIDEO"))

    def test_stock_video(self) -> None:
        self.assertIn(ACTUAL_DURATION_KEY, self._annotate("STOCK_VIDEO"))

    def test_youtube_video(self) -> None:
        self.assertIn(ACTUAL_DURATION_KEY, self._annotate("YOUTUBE_VIDEO"))

    def test_archive_and_nasa_video(self) -> None:
        for src in ("ARCHIVE_VIDEO", "NASA_VIDEO"):
            self.assertIn(ACTUAL_DURATION_KEY, self._annotate(src), src)

    def test_images_are_unaffected(self) -> None:
        for src in ("FLOW_IMAGE", "STOCK_IMAGE"):
            meta = self._annotate(src, is_video=False)
            self.assertNotIn(ACTUAL_DURATION_KEY, meta, src)


class TestCreditSafety(unittest.TestCase):
    """A duration mismatch must never cost a Flow credit.

    Flow video generation is paid. Reporting that a clip is shorter than its
    scene is an editorial observation, not a defect to repair: regenerating
    would spend a credit with no guarantee of a different length, since Flow
    no longer accepts a requested duration at all.
    """

    def test_building_a_plan_never_reaches_a_provider(self) -> None:
        """The generator is a tripwire: touching it fails the test."""
        from editorial.builder import build_editorial_plan

        class Exploding:
            scene_number = "1"
            metadata = {ACTUAL_DURATION_KEY: 2.0, REQUESTED_DURATION_KEY: 10.0}
            def __getattr__(self, name):
                raise AssertionError(f"plan building touched provider API {name!r}")

        rows = [{"scene_number": "1", "script_segment": "t", "asset_type": "video", "prompt": "p"}]
        aligned = [{"scene_number": "1", "script_segment": "t", "start_time": 0.0, "end_time": 9.0}]
        plan = build_editorial_plan(rows, aligned, 9.0, asset_results={"001": Exploding()})
        self.assertEqual(plan.scenes[0].actual_asset_duration, 2.0)
        self.assertFalse(plan.scenes[0].source_covers_scene)

    def test_a_short_asset_is_not_a_qa_failure(self) -> None:
        """A duration shortfall must not become a repair action."""
        from providers.base import SceneRow
        from visual_qa.models import VisualQAResult, VisualQAStatus
        from visual_qa.retry import recommended_action_for
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="video", prompt="p")
        qa = VisualQAResult(scene_number="1", overall_score=0.92,
                            status=VisualQAStatus.PASS,
                            warnings=["source is shorter than the scene"])
        self.assertIn(recommended_action_for(qa, scene).value, ("none", "keep"))

    def test_no_regeneration_path_keys_on_duration(self) -> None:
        """Guard against a future automatic 'too short -> regenerate' rule."""
        import inspect
        from visual_qa import fix_engine, retry
        for module in (fix_engine, retry):
            src = inspect.getsource(module)
            for token in ("actual_asset_duration", "asset_duration_shortfall",
                          "source_covers_scene", "requested_duration"):
                self.assertNotIn(token, src, f"{module.__name__} keys on {token}")

    def test_duration_work_did_not_touch_credit_accounting(self) -> None:
        """The credit ceiling and repair limits must be exactly as before."""
        from visual_qa.fix_engine import (
            LIFETIME_REPAIR_ATTEMPTS, QA_FLOW_SPEND_KEY, _flow_budget_from_allocation,
        )
        self.assertEqual(LIFETIME_REPAIR_ATTEMPTS, 3)
        self.assertEqual(QA_FLOW_SPEND_KEY, "qa_flow_video_regenerations")
        alloc = {"ai_budget_limit": 6, "ai_assigned": 3, "allocation_version": 2}
        self.assertEqual(_flow_budget_from_allocation(alloc, 3).remaining, 3)
        alloc[QA_FLOW_SPEND_KEY] = 2
        self.assertEqual(_flow_budget_from_allocation(alloc, 3).remaining, 1)

    def test_annotating_duration_cannot_generate_media(self) -> None:
        """The annotator only reads a local file — it holds no provider handle.

        Asserted against executable statements, with docstrings and comments
        stripped, so prose describing providers cannot mask a real call.
        """
        import ast
        import inspect
        import textwrap
        from asset_manager import AssetManager

        tree = ast.parse(textwrap.dedent(inspect.getsource(AssetManager._annotate_actual_duration)))
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(tree) if isinstance(node, ast.Call)
        }
        forbidden = {"retry_scene", "regenerate_scene", "alternative_scene",
                     "retry_flow_batch", "generate", "download"}
        self.assertEqual(called & forbidden, set(), f"annotator calls {called & forbidden}")
