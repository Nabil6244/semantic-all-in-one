"""visual_bridge's plan helpers for the page styles (Prepper Host / Food Files / Stickman: spec_rows + apply_spec; Toon Tales /
Kids Stories: file_rows + apply_files): the made pictures are listed, and a file the user picks in the Visuals tab is what Render uses."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import visual_bridge as vb
from asset_manager import AssetManifest


def _png(path, color):
    Image.new("RGB", (8, 8), color).save(path)
    return str(path)


def _pick(images_dir, no, path):   # what the Visuals tab's Local clip / Change source writes
    AssetManifest(Path(images_dir)).set(no, {"scene_number": no, "status": "complete", "source": "manual", "type": "image",
                                             "local_path": str(path), "user_override": True})


class SpecHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dir = self.tmp / "assets"

    def test_spec_rows_list_every_picture_and_seed_the_made_ones(self):
        a = _png(self.tmp / "a.png", "red")
        spec = {"pictures": {"k1": {"prompt": "a barn"}, "k2": {"prompt": "a shelf"}}, "assets": {"pictures": {"k1": a}}}
        rows = vb.spec_rows(self.dir, spec)
        self.assertEqual([r.scene_number for r in rows], ["001", "002"])
        recs = vb.records(self.dir, rows)
        self.assertEqual(recs[1]["path"], a)
        self.assertNotIn(2, recs)            # not made yet: listed, nothing seeded

    def test_apply_spec_uses_the_users_pick(self):
        a, mine = _png(self.tmp / "a.png", "red"), _png(self.tmp / "mine.png", "blue")
        spec = {"pictures": {"k1": {"prompt": "a barn"}}, "assets": {"pictures": {"k1": a}}}
        rows = vb.spec_rows(self.dir, spec)
        self.assertEqual(vb.apply_spec(self.dir, rows, spec), 0)   # nothing changed in the tab
        _pick(self.dir, "001", mine)
        self.assertEqual(vb.apply_spec(self.dir, rows, spec), 1)
        self.assertEqual(spec["assets"]["pictures"]["k1"], mine)
        self.assertEqual(vb.spec_rows(self.dir, spec)[0].scene_number, "001")   # Generate again never overwrites the pick
        self.assertEqual(vb.records(self.dir, rows)[1]["path"], mine)

    def test_apply_files_writes_the_pick_over_the_engines_file(self):
        place = self.tmp / "places" / "town.png"
        place.parent.mkdir()
        _png(place, "red")
        Path(str(place) + ".depth.npy").write_bytes(b"x")
        mine = _png(self.tmp / "mine.jpg", "blue")
        files = {"town": (str(place), "a town square")}
        rows = vb.file_rows(self.dir, files)
        _pick(self.dir, "001", mine)
        self.assertEqual(vb.apply_files(self.dir, rows, files, keep_original=True), 1)
        self.assertGreater(Image.open(place).convert("RGB").getpixel((0, 0))[2], 240)   # blue now (a jpg pick: ~255)
        self.assertTrue((place.parent / "town.orig.png").is_file())        # the painted one is kept
        self.assertFalse(Path(str(place) + ".depth.npy").exists())         # its old depth map would warp the new picture

    def test_new_owners_are_registered(self):
        for owner, flag in (("prepper_host", "_ph_active"), ("foodfiles", "_ff_active"), ("stickman", "_sm_active"),
                            ("toon_tales", "_tt_active"), ("kids_stories", "_ks_active")):
            self.assertEqual(vb.OWNERS[owner][0], flag)


if __name__ == "__main__":
    unittest.main()
