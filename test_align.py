#!/usr/bin/env python3
"""Unit tests for script↔whisper alignment helpers (no Whisper download required)."""

import unittest

from video_generator import (
    align_rows,
    is_distinctive,
    split_words,
    words_match,
    render_caption_overlay,
    _scene_display_timeline,
)


class TestNormalize(unittest.TestCase):
    def test_hyphen_compounds_split(self):
        self.assertEqual(
            split_words("slip-and-fall lawsuit"),
            ["slip", "and", "fall", "lawsuit"],
        )
        self.assertEqual(
            split_words("door-to-door residential"),
            ["door", "to", "door", "residential"],
        )

    def test_possessive_stripped(self):
        self.assertEqual(split_words("York City's snow"), ["york", "city", "snow"])
        self.assertEqual(split_words("you're buying"), ["youre", "buying"])

    def test_number_phrases_collapse_like_whisper(self):
        self.assertEqual(split_words("twenty-five million"), ["25", "million"])
        self.assertEqual(split_words("one point eight million"), ["1", "8", "million"])
        self.assertEqual(split_words("hundred thirty million"), ["130", "million"])
        self.assertEqual(split_words("three hundred fifty dollars"), ["350", "dollars"])

    def test_lone_ones_not_collapsed(self):
        # Prose "one" must stay a word — Whisper usually keeps it
        self.assertEqual(split_words("one landscaping company"), ["one", "landscaping", "company"])
        self.assertEqual(split_words("buy a truck"), ["buy", "a", "truck"])

    def test_words_match_digit_equivalents(self):
        self.assertTrue(words_match("25", "25"))
        self.assertTrue(words_match("twenty", "20"))
        self.assertTrue(words_match("8", "eight"))
        self.assertFalse(words_match("snow", "plow"))

    def test_digits_are_distinctive(self):
        self.assertTrue(is_distinctive("25"))
        self.assertTrue(is_distinctive("130"))
        self.assertFalse(is_distinctive("1"))  # too short / ambiguous
        self.assertFalse(is_distinctive("and"))


class TestAlign(unittest.TestCase):
    def _whisper_from_text(self, text, t0=0.0, dt=0.4):
        words = split_words(text)
        out = []
        t = t0
        for w in words:
            out.append((w, t, t + dt * 0.8))
            t += dt
        return out, t

    def test_anchors_hyphen_and_number_scenes(self):
        rows = [
            {"scene_number": "1", "script_segment": "a slip-and-fall lawsuit or two"},
            {"scene_number": "2", "script_segment": "twenty-five million dollars in a light year"},
            {"scene_number": "3", "script_segment": "one point eight million for every inch"},
            {"scene_number": "4", "script_segment": "subscribe this channel every single week"},
        ]
        # Simulate Whisper: hyphens split, numbers as digits
        transcript = (
            "a slip and fall lawsuit or two "
            "25 million dollars in a light year "
            "1 8 million for every inch "
            "subscribe this channel every single week"
        )
        whisper_words, audio_end = self._whisper_from_text(transcript)
        results, _ = align_rows(rows, whisper_words)
        conf = [r["confidence"] for r in results]
        self.assertEqual(conf, [1.0, 1.0, 1.0, 1.0], results)
        # Monotonic
        for a, b in zip(results, results[1:]):
            self.assertLessEqual(a["start_time"], b["start_time"])
            self.assertLessEqual(a["end_time"], b["start_time"] + 1e-9)

    def test_miss_does_not_cascade_past_later_matches(self):
        """A scene with no overlap must not prevent later scenes from anchoring."""
        rows = [
            {"scene_number": "1", "script_segment": "alpha bravo charlie distinctive"},
            {"scene_number": "2", "script_segment": "zzzz not in transcript anywhere"},
            {"scene_number": "3", "script_segment": "delta echo foxtrot ending"},
        ]
        transcript = "alpha bravo charlie distinctive delta echo foxtrot ending"
        whisper_words, _ = self._whisper_from_text(transcript)
        results, _ = align_rows(rows, whisper_words)
        self.assertEqual(results[0]["confidence"], 1.0)
        self.assertEqual(results[1]["confidence"], 0.0)  # interpolated
        self.assertEqual(results[2]["confidence"], 1.0)  # still anchored (no cascade)

    def test_full_script_against_digit_style_whisper(self):
        """
        Regression for the end-of-video cascade: script numbers as words,
        whisper as digits — nearly all late scenes should still anchor.
        """
        templates = [
            "twenty-five million dollars in revenue year {n}",
            "one point eight million viewers watched episode {n}",
            "hundred thirty million stars in galaxy cluster {n}",
            "three hundred fifty dollars per month for plan {n}",
            "slip-and-fall lawsuit number {n} in the docket",
        ]
        rows = [
            {
                "scene_number": str(i),
                "script_segment": templates[(i - 1) % len(templates)].format(n=i),
            }
            for i in range(1, 201)
        ]

        # Build a whisper-like stream by tokenizing each scene the same way
        # (script path already collapses numbers). Perfect-match baseline.
        whisper_words = []
        t = 0.0
        dt = 0.35
        for row in rows:
            for w in split_words(row["script_segment"]):
                whisper_words.append((w, t, t + dt * 0.8))
                t += dt

        results, _ = align_rows(rows, whisper_words)
        low = [r["scene_number"] for r in results if r["confidence"] < 1.0]
        anchored = sum(1 for r in results if r["confidence"] == 1.0)
        # Expect near-perfect anchoring on a same-tokenizer transcript
        self.assertGreaterEqual(anchored, 190, f"only {anchored}/200; low={low}")
        # Critical: no long contiguous miss run at the end
        late_low = [s for s in low if int(s) >= 169]
        self.assertLessEqual(len(late_low), 5, f"late cascade still present: {late_low}")


class TestCaptions(unittest.TestCase):
    def test_display_timeline_matches_durations(self):
        rows = [
            {"start_time": 0.0, "end_time": 1.0},
            {"start_time": 1.2, "end_time": 2.5},
            {"start_time": 2.5, "end_time": 4.0},
        ]
        windows = _scene_display_timeline(rows, audio_end=4.0)
        self.assertEqual(windows[0], (0.0, 1.2))
        self.assertEqual(windows[1], (1.2, 2.5))
        self.assertEqual(windows[2], (2.5, 4.0))

    def test_caption_overlay_png(self):
        import tempfile
        from pathlib import Path
        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cap.png"
            path = render_caption_overlay(
                "York City's snow is piling up fast",
                out,
                width=640,
                height=360,
            )
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file())
            img = Image.open(path)
            self.assertEqual(img.size, (640, 360))
            self.assertEqual(img.mode, "RGBA")
            # Must have some non-transparent pixels (text drawn)
            alpha = img.getchannel("A")
            alphas = list(alpha.get_flattened_data())
            self.assertTrue(any(p > 0 for p in alphas))
            img.close()

    def test_empty_caption_returns_none(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(
                render_caption_overlay("   ", Path(d) / "x.png", 320, 180)
            )


if __name__ == "__main__":
    unittest.main()
