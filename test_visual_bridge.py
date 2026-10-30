"""Every style that fetches assets goes through the Visuals tab (visual_bridge): Health Cinema footage (test_health_cinema_visuals.py), Rep Theory Flow pictures, Product Trailer
AI pictures and stock clips. Generate scenes lists them in the table; Render (or Product Trailer's Generate) uses exactly what the table holds."""
from __future__ import annotations
import os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix="vb_rt_lib_"); os.environ.setdefault("REP_THEORY_ASSET_DIR", _TMP)

from PIL import Image

import visual_bridge as VB
from providers.base import SceneRow


def _file(d: Path, name: str, data: bytes = b"x") -> Path:
    p = Path(d) / name; p.write_bytes(data); return p


class Bridge(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_seed_records_snapshot_and_the_users_choice_wins(self):
        a, b = _file(self.d, "a.mp4"), _file(self.d, "b.mp4")
        rows = [SceneRow(scene_number="1", script_segment="Your heart beats.", asset_type="stock_video", stock="heart")]
        VB.seed(self.d, "1", str(a), "stock_video", stock="heart")
        rec = VB.records(self.d, rows)[1]
        self.assertTrue(rec["ok"]); self.assertEqual(rec["path"], str(a)); self.assertEqual(rec["narration"], "Your heart beats.")
        from asset_manager import AssetManifest
        AssetManifest(self.d).set("1", dict(AssetManifest(self.d).get("1"), local_path=str(b), user_override=True))
        VB.seed(self.d, "1", str(a), "stock_video", stock="heart")      # a later Generate never replaces what the user picked
        self.assertEqual(VB.snapshot(self.d, rows), {1: str(b)})

    def test_missing_or_failed_files_are_left_out(self):
        rows = [SceneRow(scene_number="2", script_segment="x", asset_type="stock_video", stock="q")]
        VB.seed(self.d, "2", str(self.d / "gone.mp4"), "stock_video")
        self.assertEqual(VB.records(self.d, rows), {})

    def test_rows_are_saved_and_restored(self):
        rows = [SceneRow(scene_number="3", script_segment="s", asset_type="flow_image", prompt="p")]
        VB.save(self.d, rows)
        self.assertEqual([(r.scene_number, r.prompt) for r in VB.load(self.d)], [("3", "p")])

    def test_owns_only_while_the_style_is_active(self):
        app = SimpleNamespace(_scene_rows_owner="health_cinema", _health_active=True, _workspace=SimpleNamespace(root=str(self.d)))
        self.assertTrue(VB.owns(app)); self.assertEqual(VB.images_dir(app), self.d / "state" / "health_cinema" / "assets")
        app._health_active = False
        self.assertFalse(VB.owns(app)); self.assertIsNone(VB.images_dir(app))
        app._scene_rows_owner = "hybrid"; app._health_active = True
        self.assertFalse(VB.owns(app))      # Hybrid has its own wiring in app.py


class ProductTrailerFootage(unittest.TestCase):
    def test_a_clip_chosen_in_visuals_is_used_and_every_sentence_is_listed(self):
        from product_trailer import footage
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        mine = _file(d, "mine.mp4")
        parsed = {"chapters": [{"items": [{"kind": "footage", "query": "hand holding phone"}, {"kind": "footage", "query": "city night"}]}]}
        cand = SimpleNamespace(provider="pexels", asset_id="7", duration=9.0, width=1920, height=1080)
        class B:
            def search(self, q, kind, n): return [cand]
        downloads = []
        def dl(c, folder, n, log=print):
            downloads.append(n); return _file(Path(folder), f"{n}.mp4")
        items = []
        got = footage.resolve_footage(parsed, d, {}, lambda m: None, backends=[B()], download=dl, chosen={1: {"query": "hand holding phone", "path": str(mine)}}, items=items)
        self.assertEqual(got, {"found": 2, "missing": 0}); self.assertEqual(downloads, ["2"])
        self.assertEqual(parsed["chapters"][0]["items"][0]["path"], str(mine))
        self.assertEqual([i["n"] for i in items], [1, 2])

    def test_a_chosen_clip_for_a_different_search_is_not_used(self):
        from product_trailer import footage
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        parsed = {"chapters": [{"items": [{"kind": "footage", "query": "new search"}]}]}
        items = []
        footage.resolve_footage(parsed, d, {}, lambda m: None, backends=[], chosen={1: {"query": "old search", "path": str(_file(d, "old.mp4"))}}, items=items)
        self.assertNotIn("path", parsed["chapters"][0]["items"][0]); self.assertEqual(items[0]["path"], "")


class RepTheoryPictures(unittest.TestCase):
    def scenes(self):
        return [{"no": 1, "kind": "text", "text": "Squeeze the bar as hard as you can.", "decisions": [], "art": None, "prop": ""}]

    def test_generate_scenes_lists_the_pictures_without_calling_flow(self):
        from reptheory import beat_art as BA
        wanted = []
        stat = BA.prepare(self.scenes(), collect=wanted)
        self.assertEqual(stat["generated"], 0); self.assertEqual(len(wanted), 1)
        self.assertEqual(wanted[0]["prompt"], BA.prompt_for("Squeeze the bar as hard as you can."))

    def test_render_uses_the_visuals_picture(self):
        from reptheory import beat_art as BA, library as L
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        pic = d / "pick.png"; Image.new("RGB", (64, 64), (200, 10, 10)).save(pic)
        sc = self.scenes()
        rec = {"ok": True, "path": str(pic), "source": "manual", "query": "", "narration": sc[0]["text"]}
        stat = BA.prepare(sc, chosen={1: rec}, generate_missing=False)
        self.assertEqual(stat["chosen"], 1); self.assertEqual(sc[0]["kind"], "illus"); self.assertTrue(L.find(sc[0]["art"]))

    def test_a_picture_for_other_words_is_not_used(self):
        from reptheory import beat_art as BA
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        pic = d / "pick.png"; Image.new("RGB", (64, 64)).save(pic)
        sc = self.scenes()
        stat = BA.prepare(sc, chosen={1: {"ok": True, "path": str(pic), "source": "manual", "narration": "something else"}}, generate_missing=False)
        self.assertEqual(stat["chosen"], 0); self.assertNotEqual(sc[0]["kind"], "illus")


class ExportPage(unittest.TestCase):
    def test_outcome_rule(self):
        from export_state import STYLE_LABELS, run_outcome
        self.assertEqual(run_outcome("", "/x.mp4"), "completed")
        self.assertEqual(run_outcome("Stopped.", None), "cancelled")
        self.assertEqual(run_outcome("", "/x.mp4", stopped=True), "cancelled")
        self.assertEqual(run_outcome("boom", None), "failed"); self.assertEqual(run_outcome("", None), "failed")
        for key in ("health_cinema", "reptheory", "product_trailer", "war"): self.assertIn(key, STYLE_LABELS)

    def test_every_own_render_style_reports_to_export(self):
        root = Path(__file__).resolve().parent
        for f in (Path("health_cinema/app_section.py"), Path("reptheory/app_section.py"), Path("ui/product_trailer_section.py")):      # War Documentary: test_war_app_section.py
            text = (root / f).read_text(encoding="utf-8")
            self.assertIn("_track_generation_start(", text, f); self.assertIn("_track_generation_end(", text, f); self.assertIn("_export_progress(", text, f)


if __name__ == "__main__":
    unittest.main()
