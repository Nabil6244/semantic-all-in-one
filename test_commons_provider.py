"""A pass of only commons_ rows (What If's second real source after NASA) gets the key-free stock search (Openverse carries
Wikimedia Commons): it used to have no provider at all, and every row failed "stock_image provider is not configured"."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import video_generator as vg


class CommonsRows(unittest.TestCase):
    def test_a_commons_only_pass_searches_wikimedia_commons_only(self):
        """Never Pexels or Pixabay: through the general stock search a Titan row got a TGV speed plaque (project #016)."""
        made = []

        class FakeOpenverse:
            name = "openverse"

            def __init__(self, source=""):
                made.append(source)

            def search(self, *a, **k):
                return []                   # nothing found: the row fails on its own, after the provider was made

        with tempfile.TemporaryDirectory() as d, mock.patch("providers.stock.openverse.OpenverseBackend", FakeOpenverse), \
                mock.patch("providers.stock.pexels.PexelsBackend", side_effect=AssertionError("Pexels must not be asked")):
            with self.assertRaises(SystemExit):
                vg.resolve_scene_assets([{"scene_number": "45", "asset_type": "commons_image", "prompt": "Saturn F ring Voyager 1"}],
                                        Path(d), log=lambda m: None, pexels_api_key="a-key")
        self.assertEqual(made, ["wikimedia"])

    def test_plain_stock_rows_without_commons_are_unchanged(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("providers.stock.openverse.OpenverseBackend") as fake:
            with self.assertRaises(SystemExit):
                vg.resolve_scene_assets([{"scene_number": "1", "asset_type": "flow_image", "prompt": "x"}], Path(d), log=lambda m: None,
                                        flow_engine_manager=object())
        fake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
