"""Regression tests for ui/timeline_layout.py (Phase 2 interactive timeline).
Pure math — no Tk, no canvas."""

from __future__ import annotations

import unittest

from ui.timeline_layout import (
    ZOOM_LEVELS,
    clip_rect,
    content_width,
    pixels_per_second,
    ruler_ticks,
    time_to_x,
    total_height,
    track_rows,
    track_y,
    visible_time_range,
    x_to_time,
    zoom_in,
    zoom_out,
)


class TestTimeToPixel(unittest.TestCase):
    def test_time_to_x_at_100_percent(self):
        self.assertAlmostEqual(time_to_x(1.0, 1.0, 0.0), pixels_per_second(1.0))

    def test_time_to_x_accounts_for_scroll(self):
        x_no_scroll = time_to_x(5.0, 1.0, 0.0)
        x_scrolled = time_to_x(5.0, 1.0, 50.0)
        self.assertAlmostEqual(x_no_scroll - x_scrolled, 50.0)

    def test_x_to_time_is_the_inverse_of_time_to_x(self):
        for t in (0.0, 3.3, 12.0, 59.9):
            for zoom in (0.25, 1.0, 4.0):
                x = time_to_x(t, zoom, 10.0)
                back = x_to_time(x, zoom, 10.0)
                self.assertAlmostEqual(t, back, places=4)


class TestZoomNeverChangesTiming(unittest.TestCase):
    def test_zoom_changes_pixel_scale_only(self):
        # Same instant in time, different zoom -> different pixel position,
        # but x_to_time always recovers the SAME time — zoom never touches
        # the underlying timing data (spec requirement M).
        t = 12.5
        x_25 = time_to_x(t, 0.25, 0.0)
        x_400 = time_to_x(t, 4.0, 0.0)
        self.assertNotEqual(x_25, x_400)
        self.assertAlmostEqual(x_to_time(x_25, 0.25, 0.0), t)
        self.assertAlmostEqual(x_to_time(x_400, 4.0, 0.0), t)

    def test_zoom_in_out_step_through_known_levels(self):
        self.assertEqual(zoom_in(1.0), 2.0)
        self.assertEqual(zoom_out(1.0), 0.5)

    def test_zoom_in_caps_at_max_level(self):
        self.assertEqual(zoom_in(ZOOM_LEVELS[-1]), ZOOM_LEVELS[-1])

    def test_zoom_out_caps_at_min_level(self):
        self.assertEqual(zoom_out(ZOOM_LEVELS[0]), ZOOM_LEVELS[0])


class TestContentWidth(unittest.TestCase):
    def test_longer_duration_is_wider(self):
        self.assertGreater(content_width(100, 1.0), content_width(10, 1.0))

    def test_zero_duration_still_has_positive_width(self):
        self.assertGreaterEqual(content_width(0, 1.0), 1.0)


class TestTrackLayout(unittest.TestCase):
    def test_track_rows_follows_canonical_order(self):
        rows = track_rows(["SFX", "VIDEO_1", "TEXT"])
        self.assertEqual(rows, ["VIDEO_1", "SFX", "TEXT"])

    def test_absent_tracks_are_skipped_not_blanked(self):
        rows = track_rows(["VIDEO_1"])
        self.assertEqual(rows, ["VIDEO_1"])

    def test_unknown_track_appended_sorted(self):
        rows = track_rows(["VIDEO_1", "ZZZ_CUSTOM"])
        self.assertEqual(rows[-1], "ZZZ_CUSTOM")

    def test_track_y_increases_with_row_index(self):
        rows = ["VIDEO_1", "TEXT", "SFX"]
        y0 = track_y("VIDEO_1", rows)
        y1 = track_y("TEXT", rows)
        y2 = track_y("SFX", rows)
        self.assertLess(y0, y1)
        self.assertLess(y1, y2)

    def test_total_height_grows_with_track_count(self):
        self.assertGreater(total_height(["a", "b", "c"]), total_height(["a"]))


class TestRulerTicks(unittest.TestCase):
    def test_ticks_cover_the_full_duration(self):
        ticks = ruler_ticks(65.0, 1.0)
        self.assertGreaterEqual(ticks[-1][0], 60.0)

    def test_tick_labels_are_mm_ss(self):
        ticks = ruler_ticks(70.0, 1.0)
        self.assertTrue(any(label == "1:00" for _, label in ticks))

    def test_zoomed_out_produces_fewer_ticks_than_zoomed_in(self):
        far = ruler_ticks(600.0, 0.25)
        near = ruler_ticks(600.0, 4.0)
        self.assertLess(len(far), len(near))

    def test_no_duration_produces_at_least_one_tick(self):
        ticks = ruler_ticks(0.0, 1.0)
        self.assertGreaterEqual(len(ticks), 1)


class TestClipRect(unittest.TestCase):
    def test_clip_rect_width_matches_duration_in_pixels(self):
        rows = ["VIDEO_1", "TEXT"]
        x0, y0, x1, y1 = clip_rect(2.0, 5.0, "TEXT", rows, zoom=1.0, scroll_x=0.0)
        self.assertAlmostEqual(x1 - x0, 3.0 * pixels_per_second(1.0))

    def test_clip_rect_y_matches_its_track_row(self):
        rows = ["VIDEO_1", "TEXT"]
        _, y0, _, y1 = clip_rect(0.0, 1.0, "TEXT", rows, zoom=1.0, scroll_x=0.0)
        self.assertEqual(y0, track_y("TEXT", rows))


class TestVisibleRange(unittest.TestCase):
    def test_visible_time_range_scales_with_zoom(self):
        wide = visible_time_range(800, 0.25, 0.0)
        narrow = visible_time_range(800, 4.0, 0.0)
        self.assertGreater(wide[1] - wide[0], narrow[1] - narrow[0])


if __name__ == "__main__":
    unittest.main()
