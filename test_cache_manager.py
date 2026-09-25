"""Project-scoped Cache & Storage operations (cache_manager.py) — a thin
layer over the EXISTING, already-project-scoped downloaded_assets.py /
preview_engine.py helpers. See cache_manager.py's own module docstring.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_workspace import create_project

import cache_manager as cm


def _seed_cache(ws) -> None:
    """Put some cache content (temp/generated/preview) plus protected user
    data in a project, so tests can verify selective clearing."""
    ws.ensure_dirs()
    (ws.tmp_dir / "scratch.tmp").write_bytes(b"t" * 1000)
    (ws.flow_dir / "001.png").write_bytes(b"g" * 2000)
    proxy_dir = ws.state_dir / "preview_proxy"
    proxy_dir.mkdir(parents=True, exist_ok=True)
    (proxy_dir / "proxy_video_abc.mp4").write_bytes(b"p" * 3000)
    ws.script_dir.mkdir(parents=True, exist_ok=True)
    (ws.script_dir / "narration.txt").write_bytes(b"protected script")
    ws.csv_dir.mkdir(parents=True, exist_ok=True)
    (ws.csv_dir / "plan.csv").write_bytes(b"protected csv")
    ws.audio_dir.mkdir(parents=True, exist_ok=True)
    (ws.audio_dir / "narration.wav").write_bytes(b"protected narration")
    ws.final_dir.mkdir(parents=True, exist_ok=True)
    (ws.final_dir / "final_video.mp4").write_bytes(b"protected final")


def _protected_still_intact(ws) -> bool:
    return (
        (ws.script_dir / "narration.txt").is_file()
        and (ws.csv_dir / "plan.csv").is_file()
        and (ws.audio_dir / "narration.wav").is_file()
        and (ws.final_dir / "final_video.mp4").is_file()
    )


class TestProjectCacheIsolation(unittest.TestCase):
    """1. Project A cache is isolated from Project B."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_cache_bytes_are_scoped_to_each_project(self):
        a = create_project("Project A", projects_root=self.tmp)
        b = create_project("Project B", projects_root=self.tmp)
        _seed_cache(a)
        a.ensure_dirs()
        b.ensure_dirs()

        self.assertGreater(cm.project_cache_bytes(a), 0)
        self.assertEqual(cm.project_cache_bytes(b), 0, "B must not see A's cache")

    def test_generated_assets_never_cross_into_the_other_projects_scan(self):
        a = create_project("Project A", projects_root=self.tmp)
        b = create_project("Project B", projects_root=self.tmp)
        _seed_cache(a)
        b.ensure_dirs()

        report_a = cm.generated_asset_cache_bytes(a)
        report_b = cm.generated_asset_cache_bytes(b)
        self.assertGreater(report_a, 0)
        self.assertEqual(report_b, 0)


class TestSwitchBackReusesCache(unittest.TestCase):
    """3. Switching back to Project A can reuse its existing cache (i.e.
    nothing in this module ever clears a project's cache as a side effect
    of merely inspecting/switching to another project)."""

    def test_inspecting_project_b_does_not_touch_project_a_cache(self):
        tmp = Path(tempfile.mkdtemp())
        a = create_project("Project A", projects_root=tmp)
        b = create_project("Project B", projects_root=tmp)
        _seed_cache(a)
        b.ensure_dirs()

        before = cm.project_cache_bytes(a)
        # Simulate "switching to B and working there" — nothing about
        # inspecting/scanning B's cache may touch A's on-disk files.
        cm.project_cache_bytes(b)
        cm.generated_asset_cache_bytes(b)
        cm.proxy_cache_bytes(b)

        after = cm.project_cache_bytes(a)
        self.assertEqual(before, after)
        self.assertTrue((a.flow_dir / "001.png").is_file())


class TestSelectiveClearing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = create_project("Clear Test", projects_root=self.tmp)
        _seed_cache(self.ws)

    def test_clear_temp_cache_only_removes_tmp_dir_contents(self):
        cm.clear_temp_cache(self.ws)
        self.assertEqual(list(self.ws.tmp_dir.rglob("*")), [])
        # Generated/preview cache and all protected data survive.
        self.assertTrue((self.ws.flow_dir / "001.png").is_file())
        self.assertTrue((self.ws.state_dir / "preview_proxy" / "proxy_video_abc.mp4").is_file())
        self.assertTrue(_protected_still_intact(self.ws))

    def test_clear_preview_cache_only_removes_preview_proxy_dir(self):
        cm.clear_preview_cache(self.ws)
        self.assertFalse((self.ws.state_dir / "preview_proxy").is_dir())
        # Temp/generated cache and all protected data survive.
        self.assertTrue((self.ws.tmp_dir / "scratch.tmp").is_file())
        self.assertTrue((self.ws.flow_dir / "001.png").is_file())
        self.assertTrue(_protected_still_intact(self.ws))

    def test_clear_generated_asset_cache_only_affects_the_target_project(self):
        other = create_project("Untouched Project", projects_root=self.tmp)
        _seed_cache(other)

        cm.clear_generated_asset_cache(self.ws)

        self.assertFalse((self.ws.flow_dir / "001.png").is_file())
        self.assertTrue(_protected_still_intact(self.ws))
        # The other project's generated assets are completely untouched.
        self.assertTrue((other.flow_dir / "001.png").is_file())
        self.assertTrue(_protected_still_intact(other))

    def test_clear_all_cache_never_deletes_project_or_source_or_final_files(self):
        second = create_project("Second Project", projects_root=self.tmp)
        _seed_cache(second)

        result = cm.clear_all_cache(self.tmp)

        self.assertEqual(result.projects_scanned, 2)
        self.assertGreater(result.bytes_freed, 0)
        self.assertEqual(result.failures, [])
        for ws in (self.ws, second):
            self.assertTrue(_protected_still_intact(ws))
            self.assertEqual(list(ws.tmp_dir.rglob("*")), [])
            self.assertFalse((ws.flow_dir / "001.png").is_file())
            self.assertFalse((ws.state_dir / "preview_proxy").is_dir())


class TestSingleProjectBehaviorUnchanged(unittest.TestCase):
    """8. Existing cache behavior remains unchanged within a single
    project — cache_manager is purely additive over the existing
    downloaded_assets/preview_engine helpers, never replacing them."""

    def test_project_cache_bytes_matches_the_sum_of_existing_helpers(self):
        import downloaded_assets
        from preview_engine import PROXY_DIRNAME

        tmp = Path(tempfile.mkdtemp())
        ws = create_project("Consistency Check", projects_root=tmp)
        _seed_cache(ws)

        expected = downloaded_assets.scan_downloaded_assets(ws).total_bytes
        expected += sum(
            p.stat().st_size for p in (ws.state_dir / PROXY_DIRNAME).rglob("*") if p.is_file()
        )
        self.assertEqual(cm.project_cache_bytes(ws), expected)


if __name__ == "__main__":
    unittest.main()
