"""Every picture a Smart editing switch shows (ui/views.py preview=(thumb, full)) exists in assets/ and is a thumbnail of the size the
card draws; the "Use Hybrid Map Graphics & Sound" switch once had none."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
VIEWS = (ROOT / "ui" / "views.py").read_text(encoding="utf-8")
PREVIEWS = re.findall(r'preview=\("([^"]+)",\s*"([^"]+)"\)', VIEWS)


class SmartPreviews(unittest.TestCase):
    def test_every_named_picture_exists(self):
        self.assertGreaterEqual(len(PREVIEWS), 5)
        for thumb, full in PREVIEWS:
            for rel in (thumb, full):
                self.assertTrue((ROOT / "assets" / rel).is_file(), rel)

    def test_thumbs_are_2x_of_the_128x72_card_picture(self):
        for thumb, _full in PREVIEWS:
            with Image.open(ROOT / "assets" / thumb) as im:
                self.assertEqual(im.size, (256, 144), thumb)

    def test_the_hybrid_switch_has_its_picture(self):
        start = VIEWS.index('_feature("Use Hybrid Map Graphics & Sound"')
        end = VIEWS.index("_group(", start)
        self.assertIn('preview=("smart_previews/hybrid_style_thumb.png", "smart_previews/hybrid_style_preview.jpg")', VIEWS[start:end])

    def test_the_build_ships_every_smart_preview(self):
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        self.assertIn('(ROOT / "assets" / "smart_previews").glob("*.*")', spec)
        for thumb, full in PREVIEWS:
            for rel in (thumb, full):
                if not rel.startswith("smart_previews/"):
                    self.assertIn(f'"{Path(rel).name}"', spec, rel)   # e.g. doc_style_preview.jpg is listed by name


if __name__ == "__main__":
    unittest.main()
