"""Tests for dual/multi-asset editorial coverage."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from editorial.complements import (
    AssetCandidate,
    needs_complementary_coverage,
    score_complement_candidate,
    select_complements,
)
from editorial.edit_decision import EditDecision, ShotSpec
from editorial.engine import compile_editorial_plan
from editorial.persistence import load_cached_plan, save_editorial_plan
from editorial.schema import EDITORIAL_PLAN_VERSION, EditorialPlan, EditorialScene
from editorial.shot_planner import plan_edit_decision
from visual_allocation.coverage import COVERAGE_TO_EDIT_STRATEGY
import video_generator as vg


def _png(path: Path, color=(40, 80, 120)) -> Path:
    Image.new("RGB", (320, 180), color).save(path)
    return path


def _scene(
    sn: str,
    *,
    start: float,
    end: float,
    text: str,
    purpose: str = "process",
    actual: float | None = 3.0,
) -> EditorialScene:
    return EditorialScene(
        scene_number=sn,
        start=start,
        end=end,
        duration=end - start,
        narration_excerpt=text,
        purpose=purpose,  # type: ignore[arg-type]
        attention_score=0.7,
        asset_type_intent="stock_video",
        actual_asset_duration=actual,
        visual_description="transformer factory manufacturing",
        visual_goal="show transformer production",
    )


class TestCoverageStrategyMap(unittest.TestCase):
    def test_dual_maps_to_dual_asset(self) -> None:
        self.assertEqual(COVERAGE_TO_EDIT_STRATEGY["dual"], "DUAL_ASSET")


class TestComplementScoring(unittest.TestCase):
    def test_semantic_mismatch_rejected(self) -> None:
        scene = _scene(
            "1",
            start=0,
            end=8,
            text="America needs thousands of new transformers for electricity demand.",
        )
        primary = AssetCandidate(
            asset_id="001",
            path=Path("001.mp4"),
            is_primary=True,
            visual_role="context",
            query_hint="transformer factory",
        )
        with tempfile.TemporaryDirectory() as tmp:
            bad = _png(Path(tmp) / "beach.png", (200, 180, 80))
            good = _png(Path(tmp) / "grid.png", (20, 20, 20))
            bad_c = AssetCandidate(
                asset_id="001_b",
                path=bad,
                query_hint="tropical beach vacation palm trees",
                visual_role="atmosphere",
                asset_class="stock_image",
            )
            good_c = AssetCandidate(
                asset_id="001_c",
                path=good,
                query_hint="electrical power grid transformers demand",
                visual_role="consequence",
                asset_class="stock_image",
            )
            bad_score = score_complement_candidate(
                bad_c,
                scene=scene,
                primary=primary,
                beat_role="process",
                used_asset_ids=[],
                recent_asset_ids=[],
            )
            good_score = score_complement_candidate(
                good_c,
                scene=scene,
                primary=primary,
                beat_role="process",
                used_asset_ids=[],
                recent_asset_ids=[],
            )
            self.assertGreater(good_score, bad_score)
            picked = select_complements(
                [bad_c, good_c],
                scene=scene,
                primary=primary,
                beat_role="process",
                used_asset_ids=[],
                recent_asset_ids=[],
                min_score=0.28,
            )
            self.assertTrue(picked)
            self.assertEqual(picked[0].asset_id, "001_c")

    def test_duplicate_asset_penalized(self) -> None:
        scene = _scene("1", start=0, end=6, text="transformer manufacturing plant")
        primary = AssetCandidate(
            asset_id="001",
            path=Path("001.mp4"),
            is_primary=True,
            visual_role="context",
            query_hint="factory",
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = _png(Path(tmp) / "x.png")
            cand = AssetCandidate(
                asset_id="001_b",
                path=p,
                query_hint="transformer factory manufacturing plant",
                visual_role="detail",
                asset_class="stock_image",
            )
            fresh = score_complement_candidate(
                cand,
                scene=scene,
                primary=primary,
                beat_role="process",
                used_asset_ids=[],
                recent_asset_ids=[],
            )
            reused = score_complement_candidate(
                cand,
                scene=scene,
                primary=primary,
                beat_role="process",
                used_asset_ids=["001_b", "001_b"],
                recent_asset_ids=["001_b"],
            )
            self.assertLess(reused, fresh)

    def test_needs_complement_for_short_primary(self) -> None:
        self.assertTrue(
            needs_complementary_coverage(
                required=8.0, primary_usable=3.0, coverage_strategy="dual"
            )
        )
        self.assertFalse(
            needs_complementary_coverage(
                required=4.0, primary_usable=4.0, coverage_strategy="single"
            )
        )


class TestDualAssetPlanner(unittest.TestCase):
    def test_one_asset_covers_beat(self) -> None:
        scene = _scene("1", start=0, end=3, text="Brief beat.", actual=10.0, purpose="context")
        with tempfile.TemporaryDirectory() as tmp:
            primary = _png(Path(tmp) / "001.png")
            d = plan_edit_decision(scene, media_path=primary, coverage_strategy="single")
            # Still → IMAGE_MOTION; ample video would be SINGLE_SHOT
            self.assertIn(d.strategy, ("SINGLE_SHOT", "IMAGE_MOTION"))
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.total_output_duration(), 3.0, places=1)

    def test_short_primary_plus_complement_dual(self) -> None:
        scene = _scene(
            "2",
            start=0,
            end=8,
            text="America needs thousands of new transformers to meet rising electricity demand.",
            actual=3.2,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = _png(root / "002.png", (10, 10, 10))
            # Pretend video via asset type + actual duration; image file is fine for planner
            scene.asset_type_intent = "stock_video"
            comp = _png(root / "002_b.png", (80, 80, 80))
            candidates = [
                AssetCandidate(
                    asset_id="002",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformer factory",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="002_b",
                    path=comp,
                    visual_role="detail",
                    editorial_purpose="detail",
                    query_hint="transformer close-up manufacturing detail",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
            )
            self.assertEqual(d.strategy, "DUAL_ASSET")
            self.assertGreaterEqual(len(d.shots), 2)
            paths = {s.source_path for s in d.shots}
            self.assertIn(str(primary), paths)
            self.assertIn(str(comp), paths)
            self.assertAlmostEqual(d.total_output_duration(), 8.0, places=1)

    def test_best_of_multiple_complements(self) -> None:
        scene = _scene(
            "3",
            start=0,
            end=7,
            text="Transformer transportation to the electrical grid.",
            actual=2.5,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = _png(root / "003.png")
            weak = _png(root / "003_b.png", (1, 1, 1))
            strong = _png(root / "003_c.png", (2, 2, 2))
            candidates = [
                AssetCandidate(
                    asset_id="003",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="factory",
                ),
                AssetCandidate(
                    asset_id="003_b",
                    path=weak,
                    visual_role="atmosphere",
                    query_hint="office coffee break",
                    asset_class="stock_image",
                ),
                AssetCandidate(
                    asset_id="003_c",
                    path=strong,
                    visual_role="action",
                    editorial_purpose="action",
                    query_hint="transformer truck transportation electrical grid",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
            )
            self.assertEqual(d.strategy, "DUAL_ASSET")
            used = [s.asset_id for s in d.shots if not s.asset_id.endswith("003") or "_" in s.asset_id]
            # Strong complement should appear; weak office coffee should not be preferred
            comp_ids = [s.asset_id for s in d.shots if s.asset_id != "003"]
            self.assertIn("003_c", comp_ids)

    def test_no_useful_complement_falls_back(self) -> None:
        scene = _scene(
            "4",
            start=0,
            end=6,
            text="Transformers for the power grid.",
            actual=2.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            primary = _png(Path(tmp) / "004.png")
            junk = _png(Path(tmp) / "004_b.png")
            candidates = [
                AssetCandidate(
                    asset_id="004",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformers power",
                ),
                AssetCandidate(
                    asset_id="004_b",
                    path=junk,
                    visual_role="atmosphere",
                    query_hint="cats playing with yarn balls",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="extend",
            )
            # Unrelated complement rejected → single-asset fallback strategy
            self.assertNotEqual(d.strategy, "DUAL_ASSET")
            self.assertTrue(
                all(
                    (not s.source_path) or s.source_path == str(primary) or s.asset_id == "004"
                    for s in d.shots
                )
            )


class TestComplementDiscovery(unittest.TestCase):
    def test_find_complement_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "005.png")
            b = _png(root / "005_b.png", (9, 9, 9))
            c = _png(root / "005_c.jpg", (8, 8, 8))
            found = vg.find_complement_assets_for_scene(root, "5")
            names = {p.name for p in found}
            self.assertIn(b.name, names)
            self.assertIn(c.name, names)
            self.assertNotIn("005.png", names)


@unittest.skipUnless(
    __import__("shutil").which("ffmpeg") is not None,
    "ffmpeg not available",
)
class TestMultiAssetRender(unittest.TestCase):
    def test_different_assets_render(self) -> None:
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _png(root / "a.png", (255, 0, 0))
            b = _png(root / "b.png", (0, 255, 0))
            out = root / "scene.mp4"
            decision = {
                "scene_number": "1",
                "required_duration": 2.0,
                "strategy": "DUAL_ASSET",
                "shots": [
                    {
                        "shot_id": "1_s0",
                        "output_duration": 1.0,
                        "scale": 1.0,
                        "camera_style": "subtle_drift",
                        "source_path": str(a),
                        "asset_id": "001",
                    },
                    {
                        "shot_id": "1_s1",
                        "output_duration": 1.0,
                        "scale": 1.2,
                        "camera_style": "push_in",
                        "source_path": str(b),
                        "asset_id": "001_b",
                        "transition_in": "cut",
                    },
                ],
            }
            ok = vg._render_scene_from_edit_decision(
                img_path=a,
                out_path=out,
                duration=2.0,
                edit_decision=decision,
                width=320,
                height=180,
                fps=24,
            )
            self.assertTrue(ok)
            dur = probe_media_duration(out)
            self.assertIsNotNone(dur)
            self.assertAlmostEqual(float(dur), 2.0, delta=0.2)


class TestPlanVersioning(unittest.TestCase):
    def test_old_version_cache_invalidated(self) -> None:
        plan = EditorialPlan(
            version=EDITORIAL_PLAN_VERSION,
            audio_key="a",
            settings_key="s",
            audio_end=3.0,
            scenes=[_scene("1", start=0, end=3, text="hi", actual=5.0)],
        )
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            save_editorial_plan(state, plan)
            path = state / "editorial_plan.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["version"] = 2
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertIsNone(load_cached_plan(state, audio_key="a", settings_key="s"))
            # Current version loads
            save_editorial_plan(state, plan)
            loaded = load_cached_plan(state, audio_key="a", settings_key="s")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.version, EDITORIAL_PLAN_VERSION)

    def test_compile_discovers_disk_complements(self) -> None:
        rows_plan = EditorialPlan(
            audio_end=8.0,
            scenes=[
                _scene(
                    "1",
                    start=0,
                    end=8,
                    text="America needs transformers for electricity demand on the grid.",
                    actual=3.0,
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _png(root / "001.png", (1, 2, 3))
            _png(root / "001_b.png", (4, 5, 6))
            # Manifest dual coverage
            (root / ".asset_manifest.json").write_text(
                json.dumps(
                    {
                        "001": {
                            "status": "complete",
                            "local_path": str(root / "001.png"),
                            "coverage_plan": {
                                "strategy": "dual",
                                "narration_duration": 8.0,
                                "segments": [
                                    {"start": 0, "end": 3, "asset_class": "stock_video"},
                                    {
                                        "start": 3,
                                        "end": 8,
                                        "asset_class": "stock_image",
                                        "semantic_query_hint": "power grid electricity demand",
                                        "visual_role": "consequence",
                                    },
                                ],
                            },
                            "complement_assets": [
                                {
                                    "path": str(root / "001_b.png"),
                                    "asset_id": "001_b",
                                    "asset_class": "stock_image",
                                    "query_hint": "power grid electricity demand transformers",
                                    "visual_role": "consequence",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            compiled = compile_editorial_plan(rows_plan, images_dir=root)
            self.assertTrue(compiled.edit_decisions)
            d0 = EditDecision.from_dict(compiled.edit_decisions[0])
            self.assertEqual(d0.strategy, "DUAL_ASSET")
            self.assertGreaterEqual(d0.shot_count, 2)
            self.assertAlmostEqual(d0.total_output_duration(), 8.0, places=1)


class TestShotSpecSerialization(unittest.TestCase):
    def test_source_path_roundtrip(self) -> None:
        shot = ShotSpec(
            shot_id="1_s1",
            output_duration=2.0,
            source_path="/tmp/001_b.mp4",
            asset_id="001_b",
            visual_role="detail",
            editorial_purpose="detail",
        )
        restored = ShotSpec.from_dict(shot.to_dict())
        self.assertEqual(restored.source_path, "/tmp/001_b.mp4")
        self.assertEqual(restored.asset_id, "001_b")


if __name__ == "__main__":
    unittest.main()
