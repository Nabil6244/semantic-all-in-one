#!/usr/bin/env python3
"""A scene that only changed its number keeps its saved file: nothing is fetched (or paid for) twice.

PakMap, Hybrid Map, Weather and StarMap number their scenes by their order in the plan. One clip added near the start moved every
later number, and every later clip was fetched again although its file was on disk (project #006, 2026-10-15: 72 of 79).
No network, no Flow."""

from __future__ import annotations

import unittest
from pathlib import Path

from asset_manager import AssetManager, AssetManifest
from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from test_asset_pipeline import AssetPipelineTestCase


class CountingProvider(AssetProvider):
    """Writes <scene>.mp4 holding the search it was asked for, and counts its calls."""

    def __init__(self, source: AssetSource):
        self.source, self.calls = source, []

    def resolve(self, scene: SceneRow, images_dir: Path, log=print) -> AssetResult:
        self.calls.append(scene.stock or scene.prompt)
        target = Path(images_dir) / f"{int(scene.scene_number):03d}.mp4"
        target.write_bytes((scene.stock or scene.prompt).encode())
        return AssetResult(scene.scene_number, target, MediaType.VIDEO, self.source, SceneStatus.READY)

    def regenerate(self, scene, images_dir, exclude=None, log=print):
        return self.resolve(scene, images_dir, log=log)


def stock(n, query):
    return SceneRow(scene_number=str(n), script_segment=f"line {n}", asset_type="stock_video", prompt="", stock=query)


def flow(n, prompt):
    return SceneRow(scene_number=str(n), script_segment=f"line {n}", asset_type="video", prompt=prompt, stock="")


class ReuseByContent(AssetPipelineTestCase):
    def _mgr(self):
        self.stock = CountingProvider(AssetSource.STOCK_VIDEO)
        self.flow = CountingProvider(AssetSource.FLOW_VIDEO)
        return AssetManager(self.images, stock_provider=self.stock, flow_video_provider=self.flow, log=lambda *_: None)

    def _content(self, n):
        return (self.images / f"{n:03d}.mp4").read_bytes().decode()

    def test_a_clip_inserted_at_the_start_fetches_only_the_new_clip(self):
        queries = ["lake from above", "concrete dam", "river flowing", "town hall"]
        self._mgr().resolve_all([stock(i + 1, q) for i, q in enumerate(queries)])
        mgr = self._mgr()
        mgr.resolve_all([stock(i + 1, q) for i, q in enumerate(["houses in a neighborhood"] + queries)])
        self.assertEqual(self.stock.calls, ["houses in a neighborhood"])
        for i, q in enumerate(["houses in a neighborhood"] + queries, start=1):
            self.assertEqual(self._content(i), q)
        self.assertFalse((self.images / ".reuse_tmp").exists())

    def test_a_removed_clip_moves_the_rest_back_without_fetching(self):
        queries = ["a", "b c", "d e", "f g"]
        self._mgr().resolve_all([stock(i + 1, q) for i, q in enumerate(queries)])
        mgr = self._mgr()
        mgr.resolve_all([stock(i + 1, q) for i, q in enumerate(queries[1:])])
        self.assertEqual(self.stock.calls, [])
        for i, q in enumerate(queries[1:], start=1):
            self.assertEqual(self._content(i), q)

    def test_flow_is_never_paid_for_twice_when_the_order_changes(self):
        prompts = ["a red barn at dawn", "a river delta from space"]
        self._mgr().resolve_all([flow(i + 1, p) for i, p in enumerate(prompts)])
        mgr = self._mgr()
        mgr.resolve_all([flow(i + 1, p) for i, p in enumerate(reversed(prompts))])
        self.assertEqual(self.flow.calls, [])
        self.assertEqual(self._content(1), prompts[1])
        self.assertEqual(self._content(2), prompts[0])

    def test_the_same_clip_used_twice_is_copied(self):
        self._mgr().resolve_all([stock(1, "storm clouds")])
        mgr = self._mgr()
        mgr.resolve_all([stock(1, "dam"), stock(2, "storm clouds"), stock(3, "storm clouds")])
        self.assertEqual(self.stock.calls, ["dam"])
        self.assertEqual([self._content(i) for i in (1, 2, 3)], ["dam", "storm clouds", "storm clouds"])

    def test_a_different_source_or_search_is_still_fetched(self):
        self._mgr().resolve_all([stock(1, "storm clouds")])
        mgr = self._mgr()
        mgr.resolve_all([stock(1, "dam"), flow(2, "storm clouds")])   # the same words from another source are not the same thing
        self.assertEqual(self.stock.calls, ["dam"])
        self.assertEqual(self.flow.calls, ["storm clouds"])

    def test_a_scene_whose_number_did_not_change_is_left_alone(self):
        self._mgr().resolve_all([stock(1, "a b"), stock(2, "c d")])
        before = AssetManifest(self.images).get("2")
        mgr = self._mgr()
        mgr.resolve_all([stock(1, "a b"), stock(2, "c d")])
        self.assertEqual(self.stock.calls, [])
        self.assertEqual(AssetManifest(self.images).get("2"), before)
        self.assertNotIn("reused_from", before)

    def test_the_users_own_file_is_never_given_to_another_scene(self):
        self._mgr().resolve_all([stock(1, "storm clouds")])
        rec = AssetManifest(self.images).get("1")
        AssetManifest(self.images).set("1", {**rec, "source": AssetSource.MANUAL.value})
        mgr = self._mgr()
        mgr.resolve_all([stock(1, "storm clouds"), stock(2, "storm clouds")])
        self.assertEqual(self.stock.calls, ["storm clouds"])   # scene 2 fetched; scene 1 keeps the user's file


if __name__ == "__main__":
    unittest.main()
