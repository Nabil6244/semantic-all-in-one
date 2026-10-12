"""AI / Cloud Production → Import CSV: local_video rows at any scene number.

Covers manual attachments (any filename, any scene), folder matching by the
CSV's own scene number, manual-over-folder priority, attach-later, persistence
across a fresh AssetManager (app restart), and local rows never taking a
Flow file made before the CSV changed.
"""

from __future__ import annotations

import ast
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from asset_manager import AssetManager
from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from providers.local_assets import find_numbered_asset
from scene_recovery import scene_key, summarize_assets

import video_generator as vg


def _mp4(path: Path, tag: str) -> Path:
    """Tiny file the media sniffer reads as MP4; ``tag`` identifies it by content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16 + tag.encode())
    return path


def _tag(path: Path) -> str:
    return path.read_bytes()[28:].decode()


class FakeFlowImage(AssetProvider):
    name = "flow_image"
    source = AssetSource.FLOW_IMAGE

    def __init__(self):
        self.calls: list[str] = []

    def resolve(self, scene, images_dir, log=print):
        self.calls.append(scene.scene_number)
        target = Path(images_dir) / f"{int(scene.scene_number):03d}.jpg"
        target.write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
        return AssetResult(scene.scene_number, target, MediaType.IMAGE, self.source, SceneStatus.READY,
                           metadata={"prompt": scene.prompt})

    def resolve_batch(self, scenes, images_dir, log=print, should_stop=None, **_):
        return {s.scene_number: self.resolve(s, images_dir, log) for s in scenes}


LOCAL_SCENES = {1, 5, 17, 105, 218}


def _plan(n=218, local=LOCAL_SCENES):
    rows = []
    for i in range(1, n + 1):
        if i in local:
            rows.append(SceneRow(scene_number=str(i), script_segment=f"s{i}", asset_type="local_video", prompt=f"p{i}"))
        else:
            rows.append(SceneRow(scene_number=str(i), script_segment=f"s{i}", asset_type="image", prompt=f"p{i}"))
    return rows


class LocalVideoCsvWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "Images"
        self.picks = self.tmp / "picks"
        self.folder = self.tmp / "LocalFolder"
        self.images.mkdir()
        self.folder.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mgr(self, folder=None, flow=None):
        return AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None,
                            local_assets_dir=folder)

    def _scene(self, rows, n):
        return next(s for s in rows if s.scene_number == str(n))

    # 1 — manual attach to the first 10 scenes of a 218-scene project
    def test_manual_attach_first_ten_of_218(self):
        rows = _plan(local=set(range(1, 11)))
        mgr = self._mgr()
        for n in range(1, 11):
            r = mgr.attach_manual_clip(self._scene(rows, n), _mp4(self.picks / f"clip{n}.mp4", f"m{n}"))
            self.assertTrue(r.ok, r.error)
        for n in range(1, 11):
            got = mgr.resolve_scene(self._scene(rows, n))
            self.assertTrue(got.ok)
            self.assertEqual(_tag(got.path), f"m{n}")

    # 2, 4, 5, 6 — non-consecutive scenes, any filename, scene chosen by the user wins
    def test_manual_attach_any_filename_any_scene(self):
        rows = _plan(local={5, 17, 50, 105, 218})
        mgr = self._mgr()
        picks = {
            105: _mp4(self.picks / "001.mp4", "picked-001"),
            50: _mp4(self.picks / "my_video.mp4", "my_video"),
            218: _mp4(self.picks / "intro_clip.mp4", "intro"),
            5: _mp4(self.picks / "a.mp4", "five"),
            17: _mp4(self.picks / "b.mov", "seventeen"),
        }
        for n, src in picks.items():
            r = mgr.attach_manual_clip(self._scene(rows, n), src)
            self.assertTrue(r.ok, r.error)
        self.assertEqual(_tag(self.images / "105.mp4"), "picked-001")
        self.assertFalse((self.images / "001.mp4").exists(), "001.mp4 attached to scene 105 must not land on scene 1")
        self.assertEqual(_tag(self.images / "050.mp4"), "my_video")
        self.assertEqual(_tag(self.images / "218.mp4"), "intro")
        self.assertEqual(_tag(self.images / "017.mov"), "seventeen")

    # 3, 11 — folder matching by actual scene number + filename boundaries
    def test_folder_matches_real_scene_numbers(self):
        for n in (1, 99, 100, 105, 218, 999, 1000, 1102):
            _mp4(self.folder / (f"{n:03d}.mp4"), f"f{n}")
        for n in (1, 99, 100, 105, 218, 999, 1000, 1102):
            match, issue = find_numbered_asset(self.folder, str(n), "video")
            self.assertIsNone(issue, issue and issue.reason)
            self.assertEqual(_tag(match.path), f"f{n}")
        self.assertEqual(find_numbered_asset(self.folder, "10", "video")[1].code, "missing")  # 100.mp4 ≠ scene 10

        rows = _plan(local={1, 105})
        mgr = self._mgr(folder=self.folder)
        self.assertEqual(_tag(mgr.resolve_scene(self._scene(rows, 1)).path), "f1")
        self.assertEqual(_tag(mgr.resolve_scene(self._scene(rows, 105)).path), "f105")

    def test_folder_file_does_not_change_source_of_non_local_scene(self):
        _mp4(self.folder / "002.mp4", "f2")
        rows = _plan(local={1})
        flow = FakeFlowImage()
        mgr = self._mgr(folder=self.folder, flow=flow)
        mgr.resolve_all([self._scene(rows, 2)])
        self.assertEqual(flow.calls, ["2"])
        self.assertTrue((self.images / "002.jpg").exists())

    # 7 — folder scan never replaces a valid manual attachment
    def test_folder_does_not_overwrite_manual_attachment(self):
        _mp4(self.folder / "105.mp4", "folder-105")
        rows = _plan(local={105, 218})
        mgr = self._mgr()
        mgr.attach_manual_clip(self._scene(rows, 105), _mp4(self.picks / "mine.mp4", "manual-105"))
        mgr.attach_manual_clip(self._scene(rows, 218), _mp4(self.picks / "x.mp4", "manual-218"))  # not in folder

        mgr = self._mgr(folder=self.folder)  # user picks a folder afterwards
        r105 = mgr.resolve_scene(self._scene(rows, 105))
        r218 = mgr.resolve_scene(self._scene(rows, 218))
        self.assertTrue(r105.ok and r218.ok, (r105.error, r218.error))
        self.assertEqual(_tag(self.images / "105.mp4"), "manual-105")
        self.assertEqual(_tag(self.images / "218.mp4"), "manual-218")
        summary = mgr.resolve_all(rows[104:105] + rows[217:218])
        self.assertTrue(all(r.ok for r in summary.results.values()))
        self.assertEqual(_tag(self.images / "105.mp4"), "manual-105")

    # 8, 9 — import without local files: Flow images still generate, locals NEEDS ACTION, attach later → READY
    def test_attach_later_does_not_block_flow_images(self):
        rows = _plan()
        flow = FakeFlowImage()
        mgr = self._mgr(flow=flow)
        summary = mgr.resolve_all(rows)
        self.assertEqual(len(flow.calls), 218 - len(LOCAL_SCENES))
        for n in LOCAL_SCENES:
            r = summary.results[str(n)]
            self.assertEqual(r.status, SceneStatus.NEEDS_ACTION)
            self.assertEqual(r.source, AssetSource.LOCAL, "must not fall back to another source")
        # 13 — render gate still refuses with local scenes missing
        results = {scene_key(k): v for k, v in summary.results.items()}
        stats = summarize_assets([s.scene_number for s in rows], results, set())
        self.assertFalse(stats["allow_render"])
        self.assertEqual(sorted(stats["attention_scenes"]), sorted(scene_key(n) for n in LOCAL_SCENES))

        for n in LOCAL_SCENES:
            r = mgr.attach_manual_clip(self._scene(rows, n), _mp4(self.picks / f"later{n}.mp4", f"later{n}"))
            self.assertTrue(r.ok)
            results[scene_key(n)] = r
        stats = summarize_assets([s.scene_number for s in rows], results, set())
        self.assertTrue(stats["allow_render"])

        # Generate again: nothing regenerated, attachments kept.
        flow.calls.clear()
        summary = mgr.resolve_all(rows)
        self.assertEqual(flow.calls, [])
        self.assertTrue(all(r.ok for r in summary.results.values()))

    # 10 — save / reopen (fresh manager reads the manifest) and missing-file detection
    def test_attachment_survives_reopen_and_missing_file_is_reported(self):
        rows = _plan(local={105})
        self._mgr().attach_manual_clip(self._scene(rows, 105), _mp4(self.picks / "001.mp4", "keep"))
        record = json.loads((self.images / ".asset_manifest.json").read_text())["105"]
        self.assertEqual(record["source"], "manual")

        reopened = self._mgr(folder=self.folder)
        got = reopened.resolve_scene(self._scene(rows, 105))
        self.assertTrue(got.ok)
        self.assertEqual(_tag(got.path), "keep")

        for p in self.images.glob("105*"):
            p.unlink()
        gone = self._mgr().resolve_scene(self._scene(rows, 105))
        self.assertFalse(gone.ok)
        self.assertEqual(gone.status, SceneStatus.NEEDS_ACTION)

    def test_flow_file_from_before_csv_change_is_not_used(self):
        """Scene 1 was flow_video, then the CSV was changed to local_video."""
        before = SceneRow(scene_number="1", script_segment="s", asset_type="video", prompt="p1")
        _mp4(self.images / "001.mp4", "flow-made")
        mgr = self._mgr()
        mgr.manifest.set("1", {"source": "flow_video", "status": "complete", "prompt": "p1",
                               "local_path": str(self.images / "001.mp4")})
        after = SceneRow(scene_number="1", script_segment="s", asset_type="local_video", prompt="p1")
        r = mgr.resolve_scene(after)
        self.assertFalse(r.ok, "a Flow clip must not count as the scene's local video")
        self.assertEqual(r.status, SceneStatus.NEEDS_ACTION)
        self.assertIsNone(vg.find_image_for_scene(self.images, "1"))
        kept = list(self.images.glob("001_replaced*.mp4"))
        self.assertEqual(len(kept), 1, "the Flow file is set aside, not deleted")
        self.assertEqual(_tag(kept[0]), "flow-made")
        del before

        r = mgr.attach_manual_clip(after, _mp4(self.picks / "mine.mp4", "mine"))
        self.assertTrue(r.ok)
        self.assertEqual(_tag(mgr.resolve_scene(after).path), "mine")

    def test_stock_file_is_isolated_like_flow(self):
        _mp4(self.images / "017.mp4", "stock-made")
        mgr = self._mgr()
        mgr.manifest.set("17", {"source": "stock_video", "status": "complete", "stock_query": "q",
                                "local_path": str(self.images / "017.mp4")})
        r = mgr.resolve_scene(SceneRow(scene_number="17", script_segment="s", asset_type="local_video"))
        self.assertEqual(r.status, SceneStatus.NEEDS_ACTION)

    def test_legacy_local_rows_keep_baseline_lookup(self):
        """Enoch cards / legacy `local` rows: no MANUAL shortcut, no set-aside, plain Images/ lookup."""
        legacy = SceneRow(scene_number="3", script_segment="s", asset_type="local")
        _mp4(self.images / "003.mp4", "placed")
        mgr = self._mgr()
        mgr.manifest.set("3", {"source": "manual", "status": "complete", "local_path": str(self.images / "003.mp4")})
        self.assertIsNone(mgr._cache_hit(legacy, AssetSource.LOCAL))
        mgr.manifest.set("3", {"source": "flow_image", "status": "complete"})
        r = mgr.resolve_scene(legacy)
        self.assertTrue(r.ok)
        self.assertEqual(_tag(r.path), "placed")
        self.assertFalse(list(self.images.glob("003_replaced*")))

    def test_local_assets_folder_prefixed_names_still_match(self):
        _mp4(self.folder / "7_Realistic_cinematic.mp4", "prefixed-7")
        mgr = self._mgr(folder=self.folder)
        r = mgr.resolve_scene(SceneRow(scene_number="7", script_segment="s", asset_type="local_video"))
        self.assertTrue(r.ok, r.error)
        self.assertEqual(_tag(r.path), "prefixed-7")

    # 12 — scene numbering is untouched
    def test_scene_numbers_unchanged(self):
        rows = _plan()
        mgr = self._mgr(flow=FakeFlowImage())
        summary = mgr.resolve_all(rows)
        self.assertEqual([s.scene_number for s in rows], [str(i) for i in range(1, 219)])
        self.assertEqual(sorted(summary.results, key=int), [str(i) for i in range(1, 219)])


class AppGateAndHydrationTests(unittest.TestCase):
    def test_folder_gate_only_in_local_assets_mode(self):
        src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_validate")
        body = ast.get_source_segment(src, fn)
        gate = body[: body.index("Choose a Local Assets folder")]
        last_if = gate[gate.rindex("if self._production_mode_is_local()"):]
        self.assertNotIn("wants_local_numbered", last_if)

    def test_hydration_rule_for_local_rows(self):
        from app import _manifest_record_matches_row

        local = SceneRow(scene_number="1", script_segment="s", asset_type="local_video", prompt="p")
        self.assertTrue(_manifest_record_matches_row({"source": "manual", "prompt": "other"}, local))
        self.assertTrue(_manifest_record_matches_row({"source": "local"}, local))
        self.assertFalse(_manifest_record_matches_row({"source": "flow_video", "prompt": "p"}, local))
        flow = SceneRow(scene_number="2", script_segment="s", asset_type="image", prompt="p")
        self.assertTrue(_manifest_record_matches_row({"source": "flow_image", "prompt": "p"}, flow))
        self.assertFalse(_manifest_record_matches_row({"source": "flow_image", "prompt": "old"}, flow))


if __name__ == "__main__":
    unittest.main()
