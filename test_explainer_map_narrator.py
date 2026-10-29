"""The presenter over the map: only the stretches where no clip covers the map, and never a stretch too short to read."""
import unittest

from explainer.beats import map_narrator as M


class Windows(unittest.TestCase):
    def test_only_uncovered_map_stretches_of_enough_length(self):
        spec = {"duration": 30.0, "events": [{"type": "media_full", "t_in": 5.0, "t_out": 12.0}, {"type": "media_full", "t_in": 13.0, "t_out": 20.0}, {"type": "caption", "t_in": 1, "t_out": 2}]}
        w = M.map_windows(spec)
        self.assertEqual(w, [(0.0, 4.65), (20.35, 30.0)])      # the 1 s gap between the clips is too short for a presenter

    def test_no_marker_no_change(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(M.apply_if_marked("none.mp4", {"duration": 10.0, "events": []}, d + "/_work"))


if __name__ == "__main__":
    unittest.main()
