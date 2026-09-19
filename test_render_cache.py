"""Regression tests for render_cache.py (Semantic YT Studio 2.0 — Batch 1).

Pure filesystem/JSON logic — no ffmpeg, no GPU, no network. Covers key
determinism, every invalidation trigger, project isolation, schema
versioning, and the "uncertainty -> miss" correctness rule.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from render_cache import (
    RENDER_CACHE_SCHEMA_VERSION,
    RenderCache,
    build_scene_cache_key,
    cache_index_path,
)


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        scene_number="1",
        img_path=None,
        duration=5.0,
        width=1920,
        height=1080,
        fps=30,
        zoom=True,
        zoom_in=True,
        zoom_amount=0.10,
    )
    kwargs.update(overrides)
    return kwargs


class TestCacheKeyDeterminism(unittest.TestCase):
    def test_same_inputs_same_key(self):
        k1 = build_scene_cache_key(**_base_kwargs())
        k2 = build_scene_cache_key(**_base_kwargs())
        self.assertEqual(k1, k2)

    def test_key_is_stable_across_dict_ordering(self):
        # timed_overlays / edit_decision are dict-shaped inputs — key must
        # not depend on Python dict insertion order.
        ed1 = {"shots": [{"a": 1, "b": 2}]}
        ed2 = {"shots": [{"b": 2, "a": 1}]}
        k1 = build_scene_cache_key(**_base_kwargs(edit_decision=ed1))
        k2 = build_scene_cache_key(**_base_kwargs(edit_decision=ed2))
        self.assertEqual(k1, k2)


class TestCacheKeyInvalidationTriggers(unittest.TestCase):
    def test_duration_change_invalidates(self):
        k1 = build_scene_cache_key(**_base_kwargs(duration=5.0))
        k2 = build_scene_cache_key(**_base_kwargs(duration=6.0))
        self.assertNotEqual(k1, k2)

    def test_resolution_change_invalidates(self):
        k1 = build_scene_cache_key(**_base_kwargs(width=1920, height=1080))
        k2 = build_scene_cache_key(**_base_kwargs(width=1280, height=720))
        self.assertNotEqual(k1, k2)

    def test_zoom_settings_invalidate(self):
        k1 = build_scene_cache_key(**_base_kwargs(zoom=True))
        k2 = build_scene_cache_key(**_base_kwargs(zoom=False))
        self.assertNotEqual(k1, k2)

    def test_caption_and_text_effects_invalidate(self):
        k1 = build_scene_cache_key(**_base_kwargs(text_effect_filters=""))
        k2 = build_scene_cache_key(**_base_kwargs(text_effect_filters="fade=in"))
        self.assertNotEqual(k1, k2)

    def test_camera_style_invalidates(self):
        k1 = build_scene_cache_key(**_base_kwargs(camera_style="pan"))
        k2 = build_scene_cache_key(**_base_kwargs(camera_style="zoom"))
        self.assertNotEqual(k1, k2)

    def test_encode_args_invalidate(self):
        k1 = build_scene_cache_key(**_base_kwargs(encode_args=["-c:v", "libx264"]))
        k2 = build_scene_cache_key(**_base_kwargs(encode_args=["-c:v", "h264_videotoolbox"]))
        self.assertNotEqual(k1, k2)

    def test_edit_decision_change_invalidates(self):
        k1 = build_scene_cache_key(**_base_kwargs(edit_decision={"shots": [{"x": 1}]}))
        k2 = build_scene_cache_key(**_base_kwargs(edit_decision={"shots": [{"x": 2}]}))
        self.assertNotEqual(k1, k2)

    def test_source_file_content_change_invalidates(self):
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "007.png"
            img.write_bytes(b"original-bytes")
            k1 = build_scene_cache_key(**_base_kwargs(img_path=img))
            # Same filename, overwritten in place — the confirmed real-world
            # regeneration pattern (scene assets are named by scene number).
            img.write_bytes(b"different-bytes-longer")
            k2 = build_scene_cache_key(**_base_kwargs(img_path=img))
            self.assertNotEqual(k1, k2)

    def test_edit_decision_shot_source_file_change_invalidates(self):
        with tempfile.TemporaryDirectory() as td:
            shot_src = Path(td) / "shot_001.png"
            shot_src.write_bytes(b"a")
            ed = {"shots": [{"source_path": str(shot_src)}]}
            k1 = build_scene_cache_key(**_base_kwargs(edit_decision=ed))
            shot_src.write_bytes(b"bb")
            k2 = build_scene_cache_key(**_base_kwargs(edit_decision=ed))
            self.assertNotEqual(k1, k2)

    def test_timed_overlay_png_change_invalidates(self):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "overlay.png"
            png.write_bytes(b"a")
            overlays = [(png, 0.0, 1.0, "fade", (0, 0))]
            k1 = build_scene_cache_key(**_base_kwargs(timed_overlays=overlays))
            png.write_bytes(b"bb")
            k2 = build_scene_cache_key(**_base_kwargs(timed_overlays=overlays))
            self.assertNotEqual(k1, k2)


class TestRenderCacheHitMiss(unittest.TestCase):
    def test_miss_on_empty_cache(self):
        with tempfile.TemporaryDirectory() as td:
            cache = RenderCache(Path(td))
            self.assertIsNone(cache.get("1", "somekey"))

    def test_put_then_get_hits(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            rendered = Path(td) / "clip_001.mp4"
            rendered.write_bytes(b"fake-clip-bytes")

            cache = RenderCache(state_dir)
            cache.put("1", "keyABC", rendered)

            # Fresh instance — simulates a new process/run re-loading the index.
            cache2 = RenderCache(state_dir)
            hit = cache2.get("1", "keyABC")
            self.assertIsNotNone(hit)
            self.assertTrue(hit.is_file())
            self.assertEqual(hit.read_bytes(), b"fake-clip-bytes")

    def test_wrong_key_is_a_miss(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            rendered = Path(td) / "clip.mp4"
            rendered.write_bytes(b"x")
            cache = RenderCache(state_dir)
            cache.put("1", "keyABC", rendered)
            self.assertIsNone(cache.get("1", "different-key"))

    def test_missing_clip_file_on_disk_is_a_miss(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            rendered = Path(td) / "clip.mp4"
            rendered.write_bytes(b"x")
            cache = RenderCache(state_dir)
            cache.put("1", "keyABC", rendered)
            # Simulate the cached clip file being deleted out from under the index.
            for f in cache._clips_dir.iterdir():
                f.unlink()
            cache2 = RenderCache(state_dir)
            self.assertIsNone(cache2.get("1", "keyABC"))

    def test_empty_cached_clip_file_is_a_miss(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            rendered = Path(td) / "clip.mp4"
            rendered.write_bytes(b"x")
            cache = RenderCache(state_dir)
            cache.put("1", "keyABC", rendered)
            for f in cache._clips_dir.iterdir():
                f.write_bytes(b"")  # truncate to zero bytes
            cache2 = RenderCache(state_dir)
            self.assertIsNone(cache2.get("1", "keyABC"))

    def test_put_missing_source_clip_is_a_noop(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            cache = RenderCache(state_dir)
            cache.put("1", "keyABC", Path(td) / "does_not_exist.mp4")
            self.assertIsNone(cache.get("1", "keyABC"))

    def test_reuse_copies_to_out_path(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            rendered = Path(td) / "clip.mp4"
            rendered.write_bytes(b"the-bytes")
            cache = RenderCache(state_dir)
            cache.put("1", "keyABC", rendered)
            hit = cache.get("1", "keyABC")
            out_path = Path(td) / "run" / "scene_001.mp4"
            ok = cache.reuse(hit, out_path)
            self.assertTrue(ok)
            self.assertEqual(out_path.read_bytes(), b"the-bytes")

    def test_reuse_failure_returns_false_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            cache = RenderCache(Path(td) / "state")
            # Source doesn't exist -> copy fails -> must return False, not raise.
            ok = cache.reuse(Path(td) / "missing.mp4", Path(td) / "out.mp4")
            self.assertFalse(ok)


class TestProjectIsolation(unittest.TestCase):
    def test_two_projects_never_share_entries(self):
        with tempfile.TemporaryDirectory() as td:
            state_a = Path(td) / "project_a" / "state"
            state_b = Path(td) / "project_b" / "state"
            rendered = Path(td) / "clip.mp4"
            rendered.write_bytes(b"shared-scene-number-different-project")

            cache_a = RenderCache(state_a)
            cache_a.put("1", "sameKey", rendered)

            cache_b = RenderCache(state_b)
            # Same scene_key AND same cache_key, but a different project's
            # cache instance that has never seen this entry -> must miss.
            self.assertIsNone(cache_b.get("1", "sameKey"))
            self.assertTrue(cache_a.get("1", "sameKey") is not None)


class TestSchemaVersionAndCorruption(unittest.TestCase):
    def test_missing_index_file_is_empty_cache(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            self.assertFalse(cache_index_path(state_dir).exists())
            cache = RenderCache(state_dir)
            self.assertIsNone(cache.get("1", "anykey"))

    def test_corrupt_json_is_empty_cache_not_a_crash(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True)
            cache_index_path(state_dir).write_text("{not valid json", encoding="utf-8")
            cache = RenderCache(state_dir)  # must not raise
            self.assertIsNone(cache.get("1", "anykey"))

    def test_wrong_schema_version_is_empty_cache(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True)
            cache_index_path(state_dir).write_text(
                json.dumps(
                    {
                        "schema_version": RENDER_CACHE_SCHEMA_VERSION + 999,
                        "entries": {"1": {"cache_key": "k", "clip_file": "x.mp4"}},
                    }
                ),
                encoding="utf-8",
            )
            cache = RenderCache(state_dir)
            self.assertIsNone(cache.get("1", "k"))

    def test_non_dict_json_is_empty_cache(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True)
            cache_index_path(state_dir).write_text("[1, 2, 3]", encoding="utf-8")
            cache = RenderCache(state_dir)
            self.assertIsNone(cache.get("1", "anykey"))


if __name__ == "__main__":
    unittest.main()
