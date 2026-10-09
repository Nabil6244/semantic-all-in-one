"""A commons_image / commons_video CSV row (the Commons API is gone; the router sends it to the stock search) carries its
search as stock keywords, searches the right media type and records the source the router uses — before this, every
such row failed "No stock keywords given for this scene." (project #085, 31 scenes)."""

import unittest

from providers.base import AssetSource, SceneRow
from providers.router import SceneAssetRouter


def row(asset_type, prompt):
    return SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "asset_type": asset_type, "prompt": prompt})


class CommonsCsvRows(unittest.TestCase):
    def test_image_row_searches_its_first_query_as_an_image(self):
        r = row("commons_image", "Ethiopic manuscript Book of Enoch||Ge'ez manuscript Enoch")
        self.assertEqual(r.stock, "Ethiopic manuscript Book of Enoch")
        self.assertEqual(r.search_queries, ["Ethiopic manuscript Book of Enoch", "Ge'ez manuscript Enoch"])
        self.assertEqual((r.stock_media_type, r.stock_source), ("image", AssetSource.STOCK_IMAGE))
        self.assertEqual(SceneAssetRouter.classify(r), r.stock_source, "the provider records the source the router chose")

    def test_single_query_and_video_rows(self):
        self.assertEqual(row("commons_image", "John Martin The Plains of Heaven").stock, "John Martin The Plains of Heaven")
        v = row("commons_video", "moon landing")
        self.assertEqual((v.stock, v.stock_media_type, v.stock_source), ("moon landing", "video", AssetSource.STOCK_VIDEO))
        self.assertEqual(SceneAssetRouter.classify(v), AssetSource.STOCK_VIDEO)

    def test_other_rows_are_unchanged(self):
        s = row("stock_image", "old parchment")
        self.assertEqual((s.stock, s.prompt, s.stock_media_type), ("old parchment", "", "image"))
        a = row("archive_video", "apollo 11||saturn v")
        self.assertEqual((a.stock, a.prompt), ("", "apollo 11"))
        self.assertEqual(row("stock", "city").stock_media_type, "all")


if __name__ == "__main__":
    unittest.main()
