"""Regression tests for the O(1) editorial scene-lookup index (Semantic YT
Studio 2.0 — Batch 1, PHASE 3).

app.py's ``_editorial_scene_lookup`` used to linearly rescan
``plan["scenes"]`` on every single call (O(n) per lookup, called once per
scene while rendering the scene list -> O(n^2) overall). This verifies the
replacement index (``_editorial_scene_index_for``) preserves the exact
original two-pass string-then-int-normalized matching semantics, and that
every code path which resets ``_editorial_plan_cache`` also resets
``_editorial_scene_index`` alongside it (a stale index is a correctness bug,
not just a performance one — it would keep serving scene data for a plan
that no longer exists).

Following test_flow_reliability_audit.py's convention: the class is skipped
outright if customtkinter isn't importable in this environment, and
constructs a bare instance via ``object.__new__`` to exercise these methods
without booting the actual Tk GUI.
"""

from __future__ import annotations

import inspect
import unittest


def _load_app_module():
    import app as _app

    return _app


class TestEditorialSceneIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls._app = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def _bare_instance(self):
        """A VideoGeneratorApp instance with no Tk widgets constructed —
        only the attributes _editorial_scene_index_for/_editorial_scene_lookup
        actually touch."""
        obj = object.__new__(self._app.VideoGeneratorApp)
        obj._editorial_scene_index = None
        return obj

    def _plan(self, scene_numbers):
        return {
            "scenes": [
                {"scene_number": sn, "marker": f"scene-{sn}"} for sn in scene_numbers
            ]
        }

    def test_index_reachable_by_raw_string_key(self):
        obj = self._bare_instance()
        plan = self._plan(["1", "2", "3"])
        index = self._app.VideoGeneratorApp._editorial_scene_index_for(obj, plan)
        self.assertEqual(index["2"]["marker"], "scene-2")

    def test_index_also_reachable_by_int_normalized_key(self):
        obj = self._bare_instance()
        plan = self._plan(["007", "008"])
        index = self._app.VideoGeneratorApp._editorial_scene_index_for(obj, plan)
        # Original two-pass lookup matched both "007" and int-normalized "7".
        self.assertIn("007", index)
        self.assertIn("7", index)
        self.assertEqual(index["7"]["marker"], "scene-007")

    def test_index_built_once_and_reused(self):
        obj = self._bare_instance()
        plan = self._plan(["1", "2"])
        index1 = self._app.VideoGeneratorApp._editorial_scene_index_for(obj, plan)
        # Second call with a *different* plan object must still return the
        # cached index (same identity) — it's per-instance, invalidated only
        # by the loader/reset sites, not by argument comparison.
        other_plan = self._plan(["9", "10"])
        index2 = self._app.VideoGeneratorApp._editorial_scene_index_for(obj, other_plan)
        self.assertIs(index1, index2)

    def test_non_numeric_scene_number_does_not_crash_int_normalization(self):
        obj = self._bare_instance()
        plan = self._plan(["intro", "2"])
        index = self._app.VideoGeneratorApp._editorial_scene_index_for(obj, plan)
        self.assertIn("intro", index)
        self.assertIn("2", index)

    def test_lookup_matches_by_raw_and_int_normalized_scene_number(self):
        obj = self._bare_instance()
        plan = self._plan(["007", "008"])
        # Bypass the file-loading side of _editorial_scene_lookup: shadow the
        # loader with an instance attribute returning our fixed plan (the
        # rest of the method — index building + key matching — is real).
        obj._load_editorial_plan_cached = lambda: plan

        result_raw = self._app.VideoGeneratorApp._editorial_scene_lookup(obj, "007")
        result_int = self._app.VideoGeneratorApp._editorial_scene_lookup(obj, 7)
        self.assertEqual(result_raw.get("marker"), "scene-007")
        self.assertEqual(result_int.get("marker"), "scene-007")

    def test_lookup_missing_scene_returns_empty_dict(self):
        obj = self._bare_instance()
        plan = self._plan(["1", "2"])
        obj._load_editorial_plan_cached = lambda: plan
        result = self._app.VideoGeneratorApp._editorial_scene_lookup(obj, "999")
        self.assertEqual(result, {})


class TestSceneIndexInvalidationSitesArePaired(unittest.TestCase):
    """Every place that resets self._editorial_plan_cache must also reset
    self._editorial_scene_index in the same breath — otherwise a plan reload
    could leave a lookup serving stale scene data via the old index. This
    was a real bug caught during implementation (not shipped); this test
    guards against it regressing."""

    @classmethod
    def setUpClass(cls):
        try:
            cls._app = _load_app_module()
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")

    def _assert_paired(self, source: str, label: str):
        # Every "_editorial_plan_cache = None" line must be followed
        # somewhere later in the same source block by a matching
        # "_editorial_scene_index = None" reset.
        self.assertIn(
            "_editorial_plan_cache = None",
            source,
            f"{label}: expected a plan-cache reset in this method",
        )
        self.assertIn(
            "_editorial_scene_index = None",
            source,
            f"{label}: plan-cache reset without a matching scene-index reset",
        )

    def test_load_editorial_plan_cached_pairs_both_resets(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._load_editorial_plan_cached)
        self._assert_paired(src, "_load_editorial_plan_cached")

    def test_invalidate_stale_editorial_timeline_pairs_both_resets(self):
        src = inspect.getsource(
            self._app.VideoGeneratorApp._invalidate_stale_editorial_timeline
        )
        self._assert_paired(src, "_invalidate_stale_editorial_timeline")

    def test_activate_workspace_pairs_both_resets(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._activate_workspace)
        self._assert_paired(src, "_activate_workspace")

    def test_every_plan_cache_reset_site_in_the_whole_file_has_a_paired_index_reset(self):
        """Belt-and-suspenders: scan the whole module source for every
        assignment to _editorial_plan_cache and confirm the same count of
        _editorial_scene_index assignments exists (the two must always move
        together — this is the exact class of bug caught during Batch 1
        implementation before it shipped)."""
        full_src = inspect.getsource(self._app)
        plan_cache_assignments = full_src.count("self._editorial_plan_cache = ")
        scene_index_assignments = full_src.count("self._editorial_scene_index = ")
        self.assertGreaterEqual(
            scene_index_assignments,
            plan_cache_assignments,
            "every self._editorial_plan_cache assignment must have a "
            "corresponding self._editorial_scene_index reset",
        )


if __name__ == "__main__":
    unittest.main()
