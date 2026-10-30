"""A period picture that nothing passes is replaced by the illustrated scene drawn for that beat, instead of stopping the run."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from explainer import fallbacks as FB
from pakmap import sourcing as SRC


class StandIn(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "explainer").mkdir()
        self.clip = self.d / "explainer" / "board_x.mp4"
        self.clip.write_bytes(b"x")

    def test_record_and_lookup_by_sidecar_near_the_picture_folder(self):
        FB.record(self.d / "explainer", "Western Roman Empire historical painting", self.clip)
        FB._TABLE.clear()                                            # a later session: only the file is left
        self.assertEqual(FB.lookup("western  roman empire HISTORICAL painting", self.d / "media"), str(self.clip))
        self.assertIsNone(FB.lookup("something else", self.d / "media"))

    def test_missing_period_picture_gets_the_stand_in_and_others_stay_missing(self):
        FB.record(self.d / "explainer", "Byzantine Empire historical painting", self.clip)
        scenes = [SimpleNamespace(scene_number=1, script_segment="", asset_type="stock_image", prompt="Byzantine Empire historical painting"),
                  SimpleNamespace(scene_number=2, script_segment="", asset_type="stock_image", prompt="Harbour crane")]
        res = SimpleNamespace(paths={}, missing={"1": "nothing passed", "2": "not found"}, fetched=0)
        SRC._illustrate_missing(scenes, res, self.d / "media", lambda m: None)
        self.assertEqual(res.paths, {"1": str(self.clip)})
        self.assertEqual(list(res.missing), ["2"])


if __name__ == "__main__":
    unittest.main()
