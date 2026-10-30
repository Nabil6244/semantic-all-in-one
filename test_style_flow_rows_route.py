"""Styles that hand their own Flow picture rows to the AssetManager (Rep Theory, Product Trailer, Health Cinema)
must build rows the router accepts. A row built directly with asset_type="flow_image" skips the CSV reader's
normalisation and was rejected as "no prompt, no stock keywords, and no local file found"."""
import shutil
import tempfile
import unittest
from pathlib import Path

from providers.base import AssetSource
from providers.router import SceneAssetRouter


class _Manager:
    def __init__(self, images_dir: Path):
        self.images_dir, self.seen = images_dir, []

    def resolve_all(self, rows):
        errors = SceneAssetRouter.validate(rows, self.images_dir)      # what the real AssetManager checks first
        if errors: raise RuntimeError("; ".join(errors))
        self.seen = [SceneAssetRouter.classify(r) for r in rows]


class RepTheoryFlowRows(unittest.TestCase):
    def test_every_requested_picture_routes_to_flow(self):
        from reptheory.app_section import fetch_pictures
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        requests = [{"no": n, "text": f"line {n}", "prompt": f"a trainee doing move {n}"} for n in (1, 4, 6, 8)]
        m = _Manager(d)
        rows = fetch_pictures(m, d, requests, lambda: False, lambda msg: None)
        self.assertEqual(len(rows), 4)
        self.assertEqual(m.seen, [AssetSource.FLOW_IMAGE] * 4)


class DirectRowsSource(unittest.TestCase):
    def test_style_sections_do_not_build_unnormalised_flow_rows(self):
        root = Path(__file__).resolve().parent
        for rel in ("reptheory/app_section.py", "ui/product_trailer_section.py", "health_cinema/app_section.py"):
            self.assertNotIn('asset_type="flow_image"', (root / rel).read_text(), rel)


if __name__ == "__main__":
    unittest.main()
