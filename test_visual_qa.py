"""Visual QA + Auto-Fix tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from style_engine.visual_selection import scene_has_manual_authority
from visual_qa.coverage import score_duration_coverage
from visual_qa.fix_engine import (
    FlowBudgetState,
    _flow_budget_from_allocation,
    _scene_uses_flow_video_credit,
)
from visual_qa.flow_qa import check_flow_temporal_quality
from visual_qa.models import VisualQAStatus, scene_preserves_source_authority, status_from_score
from visual_qa.repetition import score_repetition
from visual_qa.retry import recommended_action_for
from visual_qa.semantic import metadata_semantic_score
from visual_qa.scorer import evaluate_scene_asset
from visual_qa.technical import check_technical
from visual_qa.models import VisualQAResult


class TestTechnicalQA(unittest.TestCase):
    def test_missing_file_fails(self):
        rep = check_technical(Path("/nonexistent/file.mp4"), MediaType.VIDEO)
        self.assertFalse(rep.ok)
        self.assertEqual(rep.score, 0.0)

    def test_image_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "001.png"
            img.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
                b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            rep = check_technical(img, MediaType.IMAGE)
            self.assertTrue(rep.ok or rep.score > 0)


class TestCoverageQA(unittest.TestCase):
    def test_long_clip_passes(self):
        score, warnings, _ = score_duration_coverage(6.2, 8.1)
        self.assertGreaterEqual(score, 0.8)
        self.assertFalse(warnings)

    def test_short_clip_warns(self):
        score, warnings, _ = score_duration_coverage(6.0, 3.0)
        self.assertLess(score, 0.6)
        self.assertTrue(any("short" in w for w in warnings))


class TestSemanticMetadata(unittest.TestCase):
    def test_matching_title_scores_high(self):
        scene = SceneRow(
            scene_number="1",
            script_segment="Apollo 11 landed on the Moon in 1969.",
            asset_type="stock_video",
            prompt="apollo 11 moon landing",
        )
        result = AssetResult(
            "1",
            Path("001.mp4"),
            MediaType.VIDEO,
            AssetSource.STOCK_VIDEO,
            SceneStatus.READY,
            metadata={"title": "Apollo 11 Moon Landing", "description": "saturn v lunar surface"},
        )
        score, warnings = metadata_semantic_score(scene, result)
        self.assertGreater(score, 0.45)

    def test_generic_mismatch_scores_low(self):
        scene = SceneRow(
            scene_number="2",
            script_segment="Hydrothermal vents support unique deep-sea ecosystems.",
            asset_type="stock_video",
            prompt="hydrothermal vent ROV",
        )
        result = AssetResult(
            "2",
            Path("002.mp4"),
            MediaType.VIDEO,
            AssetSource.STOCK_VIDEO,
            SceneStatus.READY,
            metadata={"title": "ocean waves sunset", "description": "generic beach water"},
        )
        score, warnings = metadata_semantic_score(scene, result)
        self.assertLess(score, 0.55)


class TestRepetition(unittest.TestCase):
    def test_duplicate_asset_penalized(self):
        from style_engine.visual_selection import SelectionHistory

        hist = SelectionHistory()
        hist.record(provider="pexels", asset_id="abc123", title="ocean waves")
        score, warnings = score_repetition("abc123", "ocean waves", "", hist)
        self.assertLess(score, 0.7)
        self.assertTrue(any("duplicate" in w for w in warnings))


class TestManualAuthority(unittest.TestCase):
    def test_explicit_flow_video_preserved(self):
        row = SceneRow(
            scene_number="1",
            script_segment="Moon walk footage",
            asset_type="flow_video",
            prompt="astronauts walking on lunar surface",
        )
        self.assertTrue(scene_preserves_source_authority(row))
        self.assertTrue(scene_has_manual_authority(row))

    def test_empty_asset_type_not_manual(self):
        row = SceneRow(
            scene_number="2",
            script_segment="Automatic beat",
            asset_type="",
            prompt="",
        )
        self.assertFalse(scene_preserves_source_authority(row))


class TestRetryMapping(unittest.TestCase):
    def test_semantic_mismatch_suggests_alternative(self):
        qa = VisualQAResult(
            scene_number="3",
            status=VisualQAStatus.FAIL,
            overall_score=0.4,
            failure_reasons=["semantic mismatch"],
        )
        scene = SceneRow(scene_number="3", script_segment="x", asset_type="", prompt="apollo landing")
        action = recommended_action_for(qa, scene)
        self.assertEqual(action.value, "alternative")


class TestFlowBudget(unittest.TestCase):
    def test_reserve_blocks_unlimited_flow(self):
        state = FlowBudgetState(limit=10, used=10, reserve=1)
        self.assertFalse(state.can_regenerate_flow())

    def test_allocation_budget(self):
        state = _flow_budget_from_allocation({"ai_budget_limit": 20, "ai_assigned": 5}, 100)
        self.assertEqual(state.limit, 20)
        self.assertGreaterEqual(state.reserve, 1)

    def test_flow_image_regen_does_not_use_video_budget(self):
        state = FlowBudgetState(limit=2, used=2, reserve=0)
        image_scene = SceneRow(
            scene_number="1",
            script_segment="Concept diagram",
            asset_type="image",
            prompt="abstract diagram",
        )
        self.assertFalse(_scene_uses_flow_video_credit(image_scene))
        self.assertFalse(state.can_regenerate_flow())
        video_scene = SceneRow(
            scene_number="2",
            script_segment="Rocket launch",
            asset_type="video",
            prompt="rocket launch cinematic",
        )
        self.assertTrue(_scene_uses_flow_video_credit(video_scene))


class TestFlowTemporal(unittest.TestCase):
    def test_identical_frames_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.jpg"
            p2 = Path(tmp) / "b.jpg"
            data = b"sameframe"
            p1.write_bytes(data)
            p2.write_bytes(data)
            score, warnings = check_flow_temporal_quality([p1, p2])
            self.assertLess(score, 0.5)
            self.assertTrue(warnings)


class TestStatusThresholds(unittest.TestCase):
    def test_pass_weak_fail(self):
        self.assertEqual(status_from_score(0.85), VisualQAStatus.PASS)
        self.assertEqual(status_from_score(0.7), VisualQAStatus.WEAK)
        self.assertEqual(status_from_score(0.4), VisualQAStatus.FAIL)


class TestStillImageDurationQA(unittest.TestCase):
    """A still is held for the whole narration beat by the renderer, so it has
    no playback duration to fall short of. ffprobe reports one video frame
    (measured: exactly 0.040000s) for a JPEG/PNG, which used to read as a clip
    ~75x too short and produced a false 'duration insufficient' on EVERY image
    (stock, research and Flow alike)."""

    def test_still_image_with_multisecond_narration_scores_full(self):
        score, warnings, _ = score_duration_coverage(8.0, 0.04, is_still_image=True)
        self.assertEqual(score, 1.0)
        self.assertEqual(warnings, [])

    def test_still_image_produces_no_duration_warnings(self):
        for narr in (1.5, 3.0, 6.0, 12.0):
            score, warnings, _ = score_duration_coverage(narr, 0.04, is_still_image=True)
            self.assertEqual(score, 1.0, f"narration {narr}s")
            joined = " ".join(warnings).lower()
            self.assertNotIn("too short", joined)
            self.assertNotIn("unknown asset duration", joined)
            # dur_score >= 0.5 is what keeps "duration insufficient" out of
            # failure_reasons in scorer.evaluate_scene_asset().
            self.assertGreaterEqual(score, 0.5)

    def test_still_image_flag_defaults_off(self):
        """Existing positional callers keep the old behaviour exactly."""
        score, warnings, _ = score_duration_coverage(6.0, 0.04)
        self.assertLess(score, 0.5)
        self.assertTrue(any("short" in w for w in warnings))

    def test_video_duration_scoring_unchanged(self):
        # Long enough clip.
        score, warnings, _ = score_duration_coverage(6.2, 8.1)
        self.assertGreaterEqual(score, 0.8)
        self.assertFalse(warnings)
        # Half-length clip still warns and still scores low.
        score, warnings, _ = score_duration_coverage(6.0, 3.0)
        self.assertLess(score, 0.6)
        self.assertTrue(any("short" in w for w in warnings))
        # Genuinely too-short clip.
        score, warnings, _ = score_duration_coverage(10.0, 1.0)
        self.assertLess(score, 0.5)
        self.assertTrue(any("too short" in w for w in warnings))
        # Unknown duration on a video still warns.
        score, warnings, _ = score_duration_coverage(6.0, None)
        self.assertEqual(score, 0.4)
        self.assertTrue(any("unknown" in w for w in warnings))


class TestFlowImageSemanticQA(unittest.TestCase):
    """A Flow image is generated FROM our prompt, so the prompt is its visual
    description — not third-party metadata to be verified against narration
    vocabulary. Real measured case: a correct smartphone photo scored 0.457 and
    was flagged 'wrong subject'."""

    SCRIPT = "We really can carry more computing power in our pockets than entire governments once possessed."
    PROMPT = "Real close-up photograph of a smartphone held in a hand"

    def _flow_image(self, prompt=None, script=None):
        scene = SceneRow(
            scene_number="13",
            script_segment=script or self.SCRIPT,
            asset_type="image",
            prompt=prompt or self.PROMPT,
        )
        result = AssetResult(
            "13", Path("013.png"), MediaType.IMAGE,
            AssetSource.FLOW_IMAGE, SceneStatus.READY,
            metadata={"provider": "flow", "asset_type": "image"},
        )
        return scene, result

    def test_good_prompt_with_low_narration_overlap_not_penalized(self):
        scene, result = self._flow_image()
        from visual_qa.semantic import UNVERIFIED_FLOW_SEMANTIC

        score, warnings = metadata_semantic_score(scene, result)
        self.assertNotIn(
            "semantic mismatch — generic or wrong subject", warnings,
            "a faithful Flow image must not be penalized for prompt/narration word choice",
        )
        self.assertEqual(
            score, UNVERIFIED_FLOW_SEMANTIC,
            "metadata tier must report UNVERIFIED and defer to vision, not invent a score",
        )

    def test_conceptual_prompt_not_penalized(self):
        scene, result = self._flow_image(
            prompt="Conceptual still contrasting a retro-futuristic illustration beside a modern photograph",
            script="And perhaps the strangest part is this. The future was not completely wrong.",
        )
        from visual_qa.semantic import UNVERIFIED_FLOW_SEMANTIC

        score, warnings = metadata_semantic_score(scene, result)
        self.assertEqual(score, UNVERIFIED_FLOW_SEMANTIC)
        self.assertNotIn("semantic mismatch — generic or wrong subject", warnings)

    def test_scene_visual_description_still_wins_when_present(self):
        scene = SceneRow(
            scene_number="13", script_segment=self.SCRIPT,
            asset_type="image", prompt=self.PROMPT,
            visual_description="a smartphone held in a hand",
        )
        _, result = self._flow_image()
        score, _ = metadata_semantic_score(scene, result)
        self.assertGreater(score, 0.0)

    def test_stock_semantic_scoring_unchanged(self):
        """Stock assets are FOUND, not generated — their metadata is still the
        thing under test, so both existing stock cases must behave as before."""
        good_scene = SceneRow(
            scene_number="1", script_segment="Apollo 11 landed on the Moon in 1969.",
            asset_type="stock_video", prompt="apollo 11 moon landing",
        )
        good = AssetResult(
            "1", Path("001.mp4"), MediaType.VIDEO, AssetSource.STOCK_VIDEO, SceneStatus.READY,
            metadata={"title": "Apollo 11 Moon Landing", "description": "saturn v lunar surface"},
        )
        self.assertGreater(metadata_semantic_score(good_scene, good)[0], 0.45)

        bad_scene = SceneRow(
            scene_number="2", script_segment="Hydrothermal vents support unique deep-sea ecosystems.",
            asset_type="stock_video", prompt="hydrothermal vent ROV",
        )
        bad = AssetResult(
            "2", Path("002.mp4"), MediaType.VIDEO, AssetSource.STOCK_VIDEO, SceneStatus.READY,
            metadata={"title": "ocean waves sunset", "description": "generic beach water"},
        )
        self.assertLess(metadata_semantic_score(bad_scene, bad)[0], 0.55)

    def test_stock_image_with_wrong_metadata_still_penalized(self):
        scene = SceneRow(
            scene_number="3", script_segment="Hydrothermal vents support unique deep-sea ecosystems.",
            asset_type="stock_image", prompt="hydrothermal vent ROV",
        )
        result = AssetResult(
            "3", Path("003.jpg"), MediaType.IMAGE, AssetSource.STOCK_IMAGE, SceneStatus.READY,
            metadata={"title": "ocean waves sunset", "description": "generic beach water"},
        )
        self.assertLess(metadata_semantic_score(scene, result)[0], 0.55)

    def test_research_semantic_scoring_unchanged(self):
        """Same shape as the Flow case (prompt shares no vocabulary with the
        narration, metadata is wrong) — research media is FOUND, not generated,
        so it must still be judged on its own metadata and stay penalized."""
        scene = SceneRow(
            scene_number="4",
            script_segment=self.SCRIPT,
            asset_type="research",
            prompt=self.PROMPT,
        )
        result = AssetResult(
            "4", Path("004.jpg"), MediaType.IMAGE, AssetSource.RESEARCH, SceneStatus.READY,
            metadata={"title": "ocean waves sunset", "description": "generic beach water"},
        )
        self.assertLess(
            metadata_semantic_score(scene, result)[0], 0.55,
            "research media must still be judged on its own metadata",
        )

    def test_identical_scene_differs_only_by_flow_source(self):
        """The ONLY thing the fix keys on is 'was this generated by Flow'."""
        scene = SceneRow(
            scene_number="7", script_segment=self.SCRIPT,
            asset_type="image", prompt=self.PROMPT,
        )
        meta = {"provider": "flow", "asset_type": "image"}
        flow = AssetResult("7", Path("007.png"), MediaType.IMAGE,
                           AssetSource.FLOW_IMAGE, SceneStatus.READY, metadata=dict(meta))
        stock = AssetResult("7", Path("007.jpg"), MediaType.IMAGE,
                            AssetSource.STOCK_IMAGE, SceneStatus.READY, metadata={})
        from visual_qa.semantic import UNVERIFIED_FLOW_SEMANTIC

        flow_score = metadata_semantic_score(scene, flow)[0]
        stock_score = metadata_semantic_score(scene, stock)[0]
        self.assertEqual(flow_score, UNVERIFIED_FLOW_SEMANTIC)
        self.assertNotEqual(stock_score, UNVERIFIED_FLOW_SEMANTIC)
        self.assertLess(stock_score, 0.55)

    def test_flow_video_semantic_unchanged(self):
        """Only Flow IMAGE is in scope — no evidence was gathered for video."""
        from visual_qa.semantic import is_flow_generated_image

        result = AssetResult(
            "5", Path("005.mp4"), MediaType.VIDEO, AssetSource.FLOW_VIDEO, SceneStatus.READY,
            metadata={"provider": "flow"},
        )
        self.assertFalse(is_flow_generated_image(result))

    def test_only_flow_image_matches_helper(self):
        from visual_qa.semantic import is_flow_generated_image

        for source, media, expect in (
            (AssetSource.FLOW_IMAGE, MediaType.IMAGE, True),
            (AssetSource.FLOW_VIDEO, MediaType.VIDEO, False),
            (AssetSource.STOCK_IMAGE, MediaType.IMAGE, False),
            (AssetSource.RESEARCH, MediaType.IMAGE, False),
            (AssetSource.YOUTUBE_VIDEO, MediaType.VIDEO, False),
        ):
            r = AssetResult("1", Path("x"), media, source, SceneStatus.READY)
            self.assertEqual(is_flow_generated_image(r), expect, f"{source}")


class TestThresholdsAndRetryUnchanged(unittest.TestCase):
    def test_vqa_thresholds_unchanged(self):
        from visual_qa.models import PASS_THRESHOLD, WEAK_THRESHOLD

        self.assertEqual(PASS_THRESHOLD, 0.80)
        self.assertEqual(WEAK_THRESHOLD, 0.60)
        self.assertEqual(status_from_score(0.85), VisualQAStatus.PASS)
        self.assertEqual(status_from_score(0.7), VisualQAStatus.WEAK)
        self.assertEqual(status_from_score(0.4), VisualQAStatus.FAIL)

    def test_vqa_weights_unchanged(self):
        import inspect
        import visual_qa.scorer as scorer

        src = inspect.getsource(scorer.evaluate_scene_asset)
        for weight in ("0.30", "0.22", "0.15", "0.12", "0.13", "0.08"):
            self.assertIn(weight, src, f"overall-score weight {weight} changed")

    def test_genuine_failure_still_triggers_retry(self):
        """VQA is not disabled and real problems still recommend a retry."""
        scene = SceneRow(
            scene_number="9", script_segment="x", asset_type="image", prompt="p",
        )
        frozen = VisualQAResult(
            scene_number="9", overall_score=0.45, status=VisualQAStatus.FAIL,
            warnings=["Flow: frozen or static frames detected"],
        )
        self.assertEqual(recommended_action_for(frozen, scene).value, "retry_same")

        low = VisualQAResult(
            scene_number="9", overall_score=0.30, status=VisualQAStatus.FAIL,
        )
        self.assertEqual(recommended_action_for(low, scene).value, "retry_same")

        mismatch = VisualQAResult(
            scene_number="9", overall_score=0.50, status=VisualQAStatus.FAIL,
            failure_reasons=["semantic mismatch"],
        )
        self.assertEqual(recommended_action_for(mismatch, scene).value, "retry_same")

    def test_clean_result_recommends_no_retry(self):
        scene = SceneRow(
            scene_number="9", script_segment="x", asset_type="image", prompt="p",
        )
        clean = VisualQAResult(
            scene_number="9", overall_score=0.86, status=VisualQAStatus.PASS,
        )
        self.assertEqual(recommended_action_for(clean, scene).value, "none")


class TestFlowImageVisionVerification(unittest.TestCase):
    """Flow-image subject can only be confirmed by the vision tier."""

    def _scene_result(self, tmp):
        img = Path(tmp) / "013.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        scene = SceneRow(scene_number="13", script_segment="Computing power in our pockets.",
                         asset_type="image", prompt="Real close-up photograph of a smartphone in a hand")
        result = AssetResult("13", img, MediaType.IMAGE, AssetSource.FLOW_IMAGE,
                             SceneStatus.READY, metadata={"provider": "flow"})
        return scene, result

    def test_flow_image_always_offered_to_vision(self):
        from visual_qa.semantic import UNVERIFIED_FLOW_SEMANTIC, needs_vision_inspection

        with tempfile.TemporaryDirectory() as tmp:
            scene, result = self._scene_result(tmp)
            self.assertTrue(
                needs_vision_inspection(scene, result,
                                        semantic=UNVERIFIED_FLOW_SEMANTIC, technical=1.0),
                "a Flow still must always be offered to vision — metadata cannot confirm it",
            )
            # Even a high semantic must not close the gate for Flow stills.
            self.assertTrue(needs_vision_inspection(scene, result, semantic=0.99, technical=1.0))

    def test_vision_result_overrides_unverified_semantic(self):
        import visual_qa.scorer as scorer

        with tempfile.TemporaryDirectory() as tmp:
            scene, result = self._scene_result(tmp)
            orig = scorer.vision_semantic_score
            try:
                scorer.vision_semantic_score = lambda sc, fr, settings=None: (0.95, [])
                good = scorer.evaluate_scene_asset(scene, result, images_dir=None,
                                                   settings={"gemini_api_key": "k"}, enable_vision=True)
                scorer.vision_semantic_score = lambda sc, fr, settings=None: (0.05, ["vision: wrong subject"])
                bad = scorer.evaluate_scene_asset(scene, result, images_dir=None,
                                                  settings={"gemini_api_key": "k"}, enable_vision=True)
            finally:
                scorer.vision_semantic_score = orig

        self.assertTrue(good.vision_used)
        self.assertTrue(bad.vision_used)
        self.assertGreater(good.semantic_match, bad.semantic_match)
        self.assertGreater(good.overall_score, bad.overall_score,
                           "a wrong-subject Flow image must score below a correct one")

    def test_no_vision_means_unverified_not_verified_good(self):
        from visual_qa.semantic import UNVERIFIED_FLOW_SEMANTIC

        with tempfile.TemporaryDirectory() as tmp:
            scene, result = self._scene_result(tmp)
            qa = evaluate_scene_asset(scene, result, images_dir=None, enable_vision=False)
        self.assertFalse(qa.vision_used)
        self.assertNotEqual(qa.status, VisualQAStatus.PASS,
                            "without vision, VQA must not claim the image was verified")
        self.assertEqual(metadata_semantic_score(scene, result)[0], UNVERIFIED_FLOW_SEMANTIC)


class TestVisionImageEncoding(unittest.TestCase):
    def test_mime_matches_extension_including_windows_paths(self):
        from visual_qa.semantic import _vision_mime_type

        cases = {
            "a.png": "image/png", "b.PNG": "image/png",
            "c.jpg": "image/jpeg", "d.JPEG": "image/jpeg",
            r"C:\\Users\\me\\VideoGenerator\\proj\\assets\\001.png": "image/png",
            r"C:\\Users\\me\\assets\\002.JPG": "image/jpeg",
        }
        for path, expected in cases.items():
            self.assertEqual(_vision_mime_type(path), expected, path)

    def test_real_flow_image_sizes_are_within_the_vision_limit(self):
        from visual_qa.semantic import _MAX_VISION_IMAGE_BYTES

        # Real measured Flow PNGs span 643KB-1.17MB; the old 900_000 cap
        # silently dropped 43% of them.
        self.assertGreater(_MAX_VISION_IMAGE_BYTES, 1_170_925)


class TestQACacheFollowsFileContents(unittest.TestCase):
    def test_replaced_image_at_same_path_gets_fresh_evaluation(self):
        """retry_same rewrites a DIFFERENT image to the SAME path."""
        import time

        from visual_qa.cache import get_cached, store_cached

        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            asset = images / "001.png"
            asset.write_bytes(b"first-image-bytes")
            qa = VisualQAResult(scene_number="1", overall_score=0.42,
                                status=VisualQAStatus.FAIL)
            store_cached(images, asset, "1", qa)
            self.assertIsNotNone(get_cached(images, asset, "1"), "same file must hit cache")

            time.sleep(0.01)
            asset.write_bytes(b"second-image-bytes-regenerated-differently")
            self.assertIsNone(
                get_cached(images, asset, "1"),
                "a regenerated image at the same path must NOT reuse the old verdict",
            )

    def test_same_size_rewrite_still_invalidates(self):
        import time

        from visual_qa.cache import get_cached, store_cached

        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            asset = images / "002.png"
            asset.write_bytes(b"A" * 32)
            store_cached(images, asset, "2",
                         VisualQAResult(scene_number="2", status=VisualQAStatus.PASS))
            time.sleep(0.01)
            asset.write_bytes(b"B" * 32)          # identical size, new content
            self.assertIsNone(get_cached(images, asset, "2"))

    def test_engine_version_bumped(self):
        from visual_qa.models import QA_ENGINE_VERSION

        self.assertGreaterEqual(QA_ENGINE_VERSION, 2)


class TestFlowImageQADoesNotBlockWorkflow(unittest.TestCase):
    """Flow-image QA is advisory: still counted and still reported, but it must
    never halt an unattended production run."""

    def _snapshot(self, source):
        from scene_qa import SceneQAState

        scene = SceneRow(scene_number="1", script_segment="s",
                         asset_type="image" if source == AssetSource.FLOW_IMAGE else "stock_image",
                         prompt="p")
        result = AssetResult("1", Path("001.png"), MediaType.IMAGE, source, SceneStatus.READY,
                             metadata={"visual_qa": {"status": "FAIL",
                                                     "failure_reasons": ["semantic mismatch"]}})
        return SceneQAState().snapshot([scene], {"001": result})

    def test_flow_image_failure_does_not_block_render(self):
        snap = self._snapshot(AssetSource.FLOW_IMAGE)
        self.assertEqual(snap.visual_fail, 1, "failure must still be COUNTED")
        self.assertEqual(len(snap.visual_issues), 1, "failure must still be REPORTED")
        self.assertEqual(snap.visual_fail_blocking, 0, "but must not stop the workflow")

    def test_non_flow_failure_still_blocks(self):
        snap = self._snapshot(AssetSource.STOCK_IMAGE)
        self.assertEqual(snap.visual_fail, 1)
        self.assertEqual(snap.visual_fail_blocking, 1)

    def test_render_permission_never_depends_on_vqa(self):
        from scene_recovery import allow_final_render

        ok = AssetResult("1", Path("001.png"), MediaType.IMAGE, AssetSource.FLOW_IMAGE,
                         SceneStatus.READY,
                         metadata={"visual_qa": {"status": "FAIL", "failure_reasons": ["x"]}})
        self.assertTrue(allow_final_render(["1"], {"001": ok}),
                        "a QA-failed but resolved asset must not block rendering")

    def test_vqa_exception_does_not_fail_the_asset(self):
        """If VQA itself errors, the asset stays usable."""
        import asset_manager as am

        scene = SceneRow(scene_number="1", script_segment="s", asset_type="image", prompt="p")
        with tempfile.TemporaryDirectory() as tmp:
            mgr = am.AssetManager(Path(tmp), log=lambda *_: None)
            result = AssetResult("1", Path(tmp) / "001.png", MediaType.IMAGE,
                                 AssetSource.FLOW_IMAGE, SceneStatus.READY, metadata={})
            record = {}
            mgr._run_visual_qa(scene, result, record)   # file absent -> QA path errors internally
            self.assertTrue(result.ok, "VQA problems must never invalidate a resolved asset")


class TestFailedRepairKeepsWorkingAsset(unittest.TestCase):
    """A failed QA repair must not turn a working asset into NEEDS_ACTION —
    that is what let an advisory Flow-image verdict block the render."""

    def _mgr_scene(self, tmp, retry_ok):
        from visual_qa.fix_engine import FlowBudgetState, fix_scene_if_needed

        scene = SceneRow(scene_number="1", script_segment="s",
                         asset_type="image", prompt="p")
        good = AssetResult("1", Path(tmp) / "001.png", MediaType.IMAGE,
                           AssetSource.FLOW_IMAGE, SceneStatus.READY, metadata={})
        failed = AssetResult("1", None, None, AssetSource.FLOW_IMAGE,
                             SceneStatus.FAILED, error="flow engine unavailable")

        class FakeMgr:
            images_dir = Path(tmp)
            selection_history = None
            resolved_style = None
            def classify(self, scene): return AssetSource.FLOW_IMAGE
            def retry_scene(self, scene): return good if retry_ok else failed
            regenerate_scene = retry_scene
            def alternative_scene(self, scene): return failed

        qa = VisualQAResult(scene_number="1", overall_score=0.55,
                            status=VisualQAStatus.FAIL,
                            failure_reasons=["semantic mismatch"])
        results = {"1": good}
        fix_scene_if_needed(FakeMgr(), scene, qa, results=results,
                            flow_budget=FlowBudgetState(), max_attempts=2,
                            log=lambda *_: None)
        return results["1"], good

    def test_failed_retry_preserves_the_working_asset(self):
        from scene_recovery import allow_final_render

        with tempfile.TemporaryDirectory() as tmp:
            kept, good = self._mgr_scene(tmp, retry_ok=False)
        self.assertTrue(kept.ok, "a failed repair must not discard a usable asset")
        self.assertIs(kept, good)
        self.assertTrue(allow_final_render(["1"], {"001": kept}),
                        "render must remain allowed after a failed QA repair")

    def test_successful_retry_still_replaces_the_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            kept, good = self._mgr_scene(tmp, retry_ok=True)
        self.assertTrue(kept.ok)
        self.assertIs(kept, good)

    def test_scene_with_no_working_asset_still_records_failure(self):
        from visual_qa.fix_engine import FlowBudgetState, fix_scene_if_needed

        scene = SceneRow(scene_number="1", script_segment="s",
                         asset_type="image", prompt="p")
        failed = AssetResult("1", None, None, AssetSource.FLOW_IMAGE,
                             SceneStatus.FAILED, error="flow engine unavailable")
        already_failed = AssetResult("1", None, None, AssetSource.FLOW_IMAGE,
                                     SceneStatus.FAILED, error="original failure")

        class FakeMgr:
            images_dir = Path(".")
            selection_history = None
            resolved_style = None
            def classify(self, scene): return AssetSource.FLOW_IMAGE
            def retry_scene(self, scene): return failed
            regenerate_scene = retry_scene
            def alternative_scene(self, scene): return failed

        results = {"1": already_failed}
        qa = VisualQAResult(scene_number="1", overall_score=0.4,
                            status=VisualQAStatus.FAIL,
                            failure_reasons=["semantic mismatch"])
        fix_scene_if_needed(FakeMgr(), scene, qa, results=results,
                            flow_budget=FlowBudgetState(), max_attempts=2,
                            log=lambda *_: None)
        self.assertFalse(results["1"].ok, "a genuinely failed scene must stay failed")


if __name__ == "__main__":
    unittest.main()
