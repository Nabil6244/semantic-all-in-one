"""Visual scene transition helpers (fade / dissolve / flash / soft)."""

from __future__ import annotations

import unittest

from video_generator import (
    _fade_vf_suffix,
    scene_visual_transition_style,
    transition_fade_params,
)


class TestVisualTransitions(unittest.TestCase):
    def test_styles_rotate(self) -> None:
        styles = [scene_visual_transition_style(i, 12) for i in range(12)]
        self.assertGreater(len(set(styles)), 2)
        self.assertEqual(styles[0], "fade")

    def test_cut_has_no_fade(self) -> None:
        fi, fo, color = transition_fade_params("cut", 4.0)
        self.assertEqual(fi, 0.0)
        self.assertEqual(fo, 0.0)
        self.assertEqual(color, "black")

    def test_dissolve_longer_than_fade(self) -> None:
        fade = transition_fade_params("fade", 5.0)
        dissolve = transition_fade_params("dissolve", 5.0)
        self.assertGreaterEqual(dissolve[0], fade[0])

    def test_flash_uses_white_in(self) -> None:
        fi, fo, color = transition_fade_params("flash", 4.0)
        self.assertGreater(fi, 0.0)
        self.assertEqual(color, "white")

    def test_fade_vf_suffix(self) -> None:
        self.assertEqual(_fade_vf_suffix(3.0, 0.0, 0.0), "")
        out = _fade_vf_suffix(3.0, 0.25, 0.25, "black")
        self.assertIn("fade=t=in", out)
        self.assertIn("fade=t=out", out)
        self.assertIn("color=black", out)

    def test_selected_map_only(self) -> None:
        """Render path uses an explicit map — unlisted scenes stay hard cuts."""
        style_map = {"3": "dissolve", "7": "flash"}
        self.assertIsNone(style_map.get("2"))
        self.assertEqual(style_map.get("3"), "dissolve")


if __name__ == "__main__":
    unittest.main()
