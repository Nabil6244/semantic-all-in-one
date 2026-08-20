#!/usr/bin/env python3
"""Per-video project workspace: isolation, reopen, destinations."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from asset_manager import AssetManager, AssetManifest
from project_workspace import (
    asset_belongs_to_project,
    create_project,
    find_project,
    list_projects,
    load_project,
    path_is_inside,
    sanitize_title,
)
from providers.base import AssetSource, SceneRow
from test_asset_pipeline import FakeProvider


class TestSanitize(unittest.TestCase):
    def test_unsafe_chars_stripped(self):
        raw = 'Why Your Brain Hates Your 9-to-5 Sleep Schedule: "tips"|<>?*'
        out = sanitize_title(raw)
        for ch in r'\/:*?"<>|':
            self.assertNotIn(ch, out)
        self.assertTrue(out.startswith("Why_Your_Brain"))

    def test_empty_is_untitled(self):
        self.assertEqual(sanitize_title(""), "Untitled")
        self.assertEqual(sanitize_title("   "), "Untitled")

    def test_length_limited(self):
        self.assertLessEqual(len(sanitize_title("x" * 400)), 60)


class TestProjectLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vg_proj_"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_new_project_creates_unique_workspace(self):
        a = create_project("Video A", projects_root=self.tmp, when=date(2026, 8, 20))
        self.assertTrue(a.root.is_dir())
        self.assertTrue((a.root / "project.json").is_file())
        self.assertEqual(a.seq, 1)
        self.assertEqual(a.project_id, "project_20260820_001")
        self.assertIn("Video_2026-08-20_001", a.root.name)
        for name in (
            "script", "csv", "audio", "assets", "flow", "youtube", "stock",
            "logs", "state", "final", "tmp",
        ):
            self.assertTrue((a.root / name).is_dir(), name)
        data = json.loads(a.meta_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project_id"], a.project_id)

    def test_second_project_is_different_folder(self):
        a = create_project("Video A", projects_root=self.tmp, when=date(2026, 8, 20))
        b = create_project("Video B", projects_root=self.tmp, when=date(2026, 8, 20))
        self.assertNotEqual(a.root, b.root)
        self.assertNotEqual(a.project_id, b.project_id)
        self.assertEqual(b.seq, 2)
        self.assertEqual(b.project_id, "project_20260820_002")
        self.assertTrue(a.root.is_dir())
        self.assertTrue(b.root.is_dir())

    def test_identity_is_project_id_not_folder_name(self):
        a = create_project("Rename Me", projects_root=self.tmp)
        pid = a.project_id
        new_root = a.root.parent / "totally_different_folder_name"
        a.root.rename(new_root)
        found = find_project(self.tmp, pid)
        self.assertIsNotNone(found)
        self.assertEqual(found.project_id, pid)
        self.assertEqual(found.root.resolve(), new_root.resolve())

    def test_reopen_does_not_create_new_workspace(self):
        a = create_project("Keep", projects_root=self.tmp)
        before = list(self.tmp.iterdir())
        again = load_project(a.root)
        self.assertIsNotNone(again)
        self.assertEqual(again.project_id, a.project_id)
        self.assertEqual(again.root.resolve(), a.root.resolve())
        self.assertEqual(len(list(self.tmp.iterdir())), len(before))
        listed = find_project(self.tmp, a.project_id)
        self.assertEqual(listed.root.resolve(), a.root.resolve())

    def test_untitled_folder(self):
        a = create_project("", projects_root=self.tmp, when=date(2026, 8, 20))
        self.assertTrue(a.root.name.endswith("_Untitled"))

    def test_csv_saved_inside_project(self):
        a = create_project("CSV", projects_root=self.tmp)
        src = self.tmp / "outside.csv"
        src.write_text("scene_number,script_segment\n1,hello\n", encoding="utf-8")
        dest = a.copy_csv_in(src)
        self.assertEqual(dest, a.csv_path)
        self.assertTrue(path_is_inside(dest, a.root))
        self.assertEqual(dest.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"))

    def test_tts_path_inside_project(self):
        a = create_project("TTS", projects_root=self.tmp)
        a.audio_path.write_bytes(b"RIFF")
        self.assertTrue(path_is_inside(a.audio_path, a.root))
        self.assertEqual(a.audio_path.parent, a.audio_dir)

    def test_find_voiceover_accepts_manual_upload(self):
        a = create_project("Manual VO", projects_root=self.tmp)
        self.assertIsNone(a.find_voiceover_audio())
        uploaded = a.audio_dir / "The Technology That .mp3"
        uploaded.write_bytes(b"ID3")
        found = a.find_voiceover_audio()
        self.assertEqual(found, uploaded)
        # Canonical narration.wav still wins when present.
        a.audio_path.write_bytes(b"RIFF")
        self.assertEqual(a.find_voiceover_audio(), a.audio_path)

    def test_flow_youtube_stock_dirs_are_project_scoped(self):
        a = create_project("A", projects_root=self.tmp)
        b = create_project("B", projects_root=self.tmp)
        (a.flow_dir / "scene_007.png").write_bytes(b"a")
        (a.youtube_dir / "scene_004.mp4").write_bytes(b"yt-a")
        (b.youtube_dir / "scene_004.mp4").write_bytes(b"yt-b")
        self.assertNotEqual(
            (a.youtube_dir / "scene_004.mp4").read_bytes(),
            (b.youtube_dir / "scene_004.mp4").read_bytes(),
        )
        self.assertFalse(path_is_inside(a.flow_dir / "scene_007.png", b.root))

    def test_final_versioning_final_1_final_2(self):
        a = create_project("Sleep Schedule", projects_root=self.tmp)
        first = a.next_final_path()
        self.assertEqual(first.name, "Sleep_Schedule.mp4")
        first.write_bytes(b"one")
        second = a.next_final_path()
        self.assertEqual(second.name, "final 1.mp4")
        second.write_bytes(b"two")
        third = a.next_final_path()
        self.assertEqual(third.name, "final 2.mp4")
        self.assertTrue(first.is_file())
        self.assertEqual(first.read_bytes(), b"one")

    def test_renderer_output_stays_in_project(self):
        a = create_project("Render", projects_root=self.tmp)
        out = a.next_final_path()
        out.write_bytes(b"mp4")
        self.assertTrue(path_is_inside(out, a.final_dir))

    def test_list_projects(self):
        create_project("One", projects_root=self.tmp)
        create_project("Two", projects_root=self.tmp)
        names = [p.title for p in list_projects(self.tmp)]
        self.assertEqual(names, ["One", "Two"])


class TestAssetIsolation(unittest.TestCase):
    def setUp(self):
        self.proj_root = Path(tempfile.mkdtemp(prefix="vg_iso_"))
        self.addCleanup(lambda: shutil.rmtree(self.proj_root, ignore_errors=True))

    def _mgr(self, ws, provider: FakeProvider) -> AssetManager:
        ws.ensure_dirs()
        return AssetManager(ws.assets_dir, stock_provider=provider, log=lambda *_: None)

    def test_scene_1_does_not_collide_across_projects(self):
        a = create_project("A", projects_root=self.proj_root)
        b = create_project("B", projects_root=self.proj_root)
        row = SceneRow(scene_number="1", script_segment="n", asset_type="stock_video", stock="q")
        ra = self._mgr(a, FakeProvider(AssetSource.STOCK, {})).resolve_scene(row)
        rb = self._mgr(b, FakeProvider(AssetSource.STOCK, {})).resolve_scene(row)
        ra.path.write_bytes(b"AAAA")
        rb.path.write_bytes(b"BBBB")
        self.assertTrue(ra.ok and rb.ok)
        self.assertTrue(path_is_inside(ra.path, a.root))
        self.assertTrue(path_is_inside(rb.path, b.root))
        self.assertNotEqual(ra.path.resolve(), rb.path.resolve())
        self.assertEqual(ra.path.read_bytes(), b"AAAA")
        self.assertEqual(rb.path.read_bytes(), b"BBBB")
        self.assertFalse(asset_belongs_to_project(ra.path, b))
        self.assertFalse(asset_belongs_to_project(rb.path, a))

    def test_retry_stays_in_same_project(self):
        a = create_project("Retry", projects_root=self.proj_root)
        fake = FakeProvider(AssetSource.STOCK, {})
        mgr = self._mgr(a, fake)
        row = SceneRow(scene_number="47", script_segment="n", asset_type="stock_video", stock="q")
        r1 = mgr.resolve_scene(row)
        self.assertTrue(r1.ok)
        r2 = mgr.retry_scene(row)
        self.assertTrue(r2.ok)
        self.assertTrue(path_is_inside(r2.path, a.root))
        self.assertEqual(load_project(a.root).project_id, a.project_id)
        self.assertEqual(len(list_projects(self.proj_root)), 1)

    def test_alternative_stays_in_same_project(self):
        a = create_project("Alt", projects_root=self.proj_root)
        fake = FakeProvider(AssetSource.STOCK, {})
        mgr = self._mgr(a, fake)
        row = SceneRow(scene_number="3", script_segment="n", asset_type="stock_video", stock="q")
        self.assertTrue(mgr.resolve_scene(row).ok)
        alt = mgr.alternative_scene(row)
        self.assertTrue(alt.ok)
        self.assertTrue(path_is_inside(alt.path, a.root))
        self.assertEqual(len(list_projects(self.proj_root)), 1)

    def test_b_cannot_resolve_a_assets(self):
        a = create_project("A", projects_root=self.proj_root)
        b = create_project("B", projects_root=self.proj_root)
        foreign = a.assets_dir / "001.jpg"
        foreign.write_bytes(b"from-a")
        rec = {
            "status": "complete",
            "local_path": str(foreign),
            "source": "stock",
        }
        man_b = AssetManifest(b.assets_dir)
        man_b.set("1", rec)
        loaded = man_b.get("1")
        path = Path(loaded["local_path"])
        self.assertTrue(path.is_file())
        self.assertFalse(asset_belongs_to_project(path, b))
        self.assertTrue(asset_belongs_to_project(path, a))

    def test_mirror_youtube_stays_in_project(self):
        a = create_project("YT", projects_root=self.proj_root)
        src = a.assets_dir / "004.mp4"
        src.write_bytes(b"clip")
        dest = a.mirror_provider_asset("youtube_video", "4", src)
        self.assertEqual(dest, a.youtube_dir / "scene_004.mp4")
        self.assertTrue(dest.is_file())

    def test_project_voice_id_persists(self):
        ws = create_project("Voice Project", projects_root=self.proj_root)
        self.assertEqual(ws.voice_id(), "")
        ws.set_voice_id("nabil")
        self.assertEqual(ws.voice_id(), "nabil")
        reloaded = load_project(ws.root)
        assert reloaded is not None
        self.assertEqual(reloaded.voice_id(), "nabil")


if __name__ == "__main__":
    unittest.main()
