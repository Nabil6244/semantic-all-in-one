#!/usr/bin/env python3
"""UI helpers that don't require a display: scene-list rebuild fingerprint."""

from __future__ import annotations

import unittest


def scene_row_signature(numbers) -> tuple:
    def key(n):
        try:
            return f"{int(str(n).strip()):03d}"
        except ValueError:
            return str(n).strip()
    return tuple(key(n) for n in numbers)


class TestSceneListFingerprint(unittest.TestCase):
    def test_150_scenes_stable_signature(self):
        nums = [str(i) for i in range(1, 151)]
        a = scene_row_signature(nums)
        b = scene_row_signature(nums)
        self.assertEqual(len(a), 150)
        self.assertEqual(a, b)

    def test_changed_plan_invalidates_signature(self):
        a = scene_row_signature(["1", "2"])
        b = scene_row_signature(["1", "2", "3"])
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
