"""Tests for chunked script planning."""

from __future__ import annotations

import unittest

from visual_director.chunking import (
    merge_chunk_plans,
    should_chunk_plan,
    split_script_into_chunks,
)
from visual_director.schema import VisualPlan, VisualScene


def _mini_scene(sid: int, narration: str) -> VisualScene:
    return VisualScene(
        scene_id=sid,
        narration=narration,
        visual_goal="goal",
        visual_description="desc",
        asset_type="stock_video",
        provider_preference="stock_video",
        search_queries=["query one", "query two"],
        timestamp_needed=False,
        timestamp_hint="",
        duration=3.0,
        importance="medium",
        fallbacks=["stock_image"],
        visual_treatment="static",
        transition="cut",
    )


class TestChunking(unittest.TestCase):
    def test_should_chunk_long_scripts(self):
        words = " ".join(["word"] * 2600)
        self.assertTrue(should_chunk_plan(words))
        self.assertFalse(should_chunk_plan("short script here"))

    def test_split_respects_paragraphs(self):
        script = "\n\n".join([" ".join([f"w{i}" for i in range(600)]) for _ in range(5)])
        chunks = split_script_into_chunks(script, target_words=800)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertIn("w0", chunks[0])

    def test_merge_renumbers_scenes(self):
        p1 = VisualPlan(topic="A", scenes=[_mini_scene(5, "one"), _mini_scene(9, "two")])
        p2 = VisualPlan(topic="B", scenes=[_mini_scene(1, "three")])
        merged = merge_chunk_plans([p1, p2])
        self.assertEqual([s.scene_id for s in merged.scenes], [1, 2, 3])
        self.assertEqual(len(merged.scenes), 3)
