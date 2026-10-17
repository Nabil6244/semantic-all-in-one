"""The Visuals table's Time column for styles that never write an editorial plan (What If, Hybrid): the row's own timecode."""

import types
import unittest

from app import VideoGeneratorApp as App
from providers.base import SceneRow


def fake(rows, editorial=None):
    f = types.SimpleNamespace(_scene_rows=[SceneRow(scene_number=n, script_segment=s, asset_type="image", prompt="") for n, s in rows])
    f._editorial_scene_lookup = lambda n: (editorial or {}).get(str(n), {})
    f._format_scene_timecode = App._format_scene_timecode
    f._scene_segment_time_label = lambda n: App._scene_segment_time_label(f, n)
    return f


class SceneTime(unittest.TestCase):
    def label(self, f, n):
        return App._scene_time_label(f, n)

    def test_what_if_rows_show_start_and_end(self):
        f = fake([("1", "0:00  What If shot s1 · 2.5 s — Four billion years"), ("150", "15:53  What If shot s197 · 4.3 s — It is")])
        self.assertEqual(self.label(f, "1"), "0:00.0–0:02.5")
        self.assertEqual(self.label(f, "150"), "15:53.0–15:57.3")

    def test_a_timecode_without_a_length_shows_its_start(self):
        self.assertEqual(self.label(fake([("4", "1:05  Hybrid beat 02 · map — why")]), "4"), "1:05.0")

    def test_no_time_anywhere_is_a_dash(self):
        self.assertEqual(self.label(fake([("5", "no time here")]), "5"), "—")
        self.assertEqual(self.label(fake([]), "9"), "—")

    def test_the_editorial_plan_still_wins(self):
        f = fake([("1", "0:00  What If shot s1 · 2.5 s — x")], {"1": {"start": 3.0, "end": 7.5}})
        self.assertEqual(self.label(f, "1"), "0:03.0–0:07.5")


if __name__ == "__main__":
    unittest.main()
