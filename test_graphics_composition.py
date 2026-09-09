"""Tests for graphics composition intelligence (deterministic presentation)."""

from __future__ import annotations

import unittest

from graphics.backgrounds import choose_background
from graphics.composition import (
    compose_presentation,
    compute_size_vh,
    score_placements,
    select_animation,
    select_placement,
    select_style_id,
)
from graphics.memory import GraphicsMemory
from graphics.semantics import infer_semantics


class TestSemanticRoleToStyle(unittest.TestCase):
    def test_location(self) -> None:
        self.assertEqual(select_style_id(role="LOCATION"), "minimal_caption")

    def test_person_lower_third(self) -> None:
        self.assertEqual(select_style_id(role="NAME"), "minimal_caption")
        self.assertEqual(select_style_id(role="LOWER_THIRD"), "minimal_caption")

    def test_statistic(self) -> None:
        self.assertEqual(select_style_id(role="STATISTIC"), "fact_number")

    def test_chapter(self) -> None:
        self.assertEqual(select_style_id(role="CHAPTER"), "statement")

    def test_technical(self) -> None:
        self.assertEqual(select_style_id(role="TECHNICAL_LABEL"), "minimal_caption")


class TestImportanceToSize(unittest.TestCase):
    def test_critical_larger_than_low(self) -> None:
        low = compute_size_vh(role="EMPHASIS", text="FACT", importance="low")
        high = compute_size_vh(role="EMPHASIS", text="FACT", importance="critical")
        self.assertGreater(high, low)

    def test_statistic_hierarchy_not_enormous(self) -> None:
        size = compute_size_vh(role="STATISTIC", text="25%", importance="medium")
        self.assertGreaterEqual(size, 0.052)
        self.assertLessEqual(size, 0.078)

    def test_never_unreadable(self) -> None:
        size = compute_size_vh(
            role="TECHNICAL_LABEL",
            text="x" * 80,
            importance="low",
            available_region_score=0.1,
        )
        self.assertGreaterEqual(size, 0.026)

    def test_never_overwhelms(self) -> None:
        size = compute_size_vh(role="STATISTIC", text="9", importance="critical")
        self.assertLessEqual(size, 0.078)

    def test_normal_text_stays_moderate(self) -> None:
        size = compute_size_vh(
            role="LABEL",
            text="Grid upgrade underway",
            importance="medium",
        )
        self.assertLessEqual(size, 0.046)
        self.assertGreaterEqual(size, 0.026)

    def test_important_text_remains_capped(self) -> None:
        size = compute_size_vh(
            role="EMPHASIS",
            text="FACT",
            importance="critical",
            emphasis="dramatic",
        )
        self.assertLessEqual(size, 0.048)
        label = compute_size_vh(role="LABEL", text="note", importance="low")
        self.assertGreater(size, label)

    def test_long_text_gets_smaller(self) -> None:
        short = compute_size_vh(role="CALLOUT", text="Grid", importance="high")
        long = compute_size_vh(
            role="CALLOUT",
            text="The electrical grid needs thousands of new transformers this decade",
            importance="high",
        )
        self.assertLess(long, short)

    def test_chapter_strongest_but_capped(self) -> None:
        chapter = compute_size_vh(role="CHAPTER", text="Part One", importance="critical")
        stat = compute_size_vh(role="STATISTIC", text="25%", importance="medium")
        normal = compute_size_vh(role="LABEL", text="Texas", importance="medium")
        self.assertGreater(chapter, normal)
        self.assertLessEqual(chapter, 0.068)
        self.assertLessEqual(stat, 0.078)

    def test_resolution_independent_vh(self) -> None:
        size = compute_size_vh(role="CALLOUT", text="Demand", importance="medium")
        # Same logical size at 720p and 4K — pixels scale with height.
        self.assertAlmostEqual(720 * size / 720, 1080 * size / 1080)
        self.assertLess(1080 * size, 1080 * 0.08)

    def test_deterministic_size(self) -> None:
        kwargs = dict(role="STATISTIC", text="+25%", importance="high", emphasis="strong")
        self.assertEqual(compute_size_vh(**kwargs), compute_size_vh(**kwargs))


class TestPlacementIntelligence(unittest.TestCase):
    def test_negative_space_prefers_quiet_cell(self) -> None:
        composition = {
            "cells": {
                "bottom_left": {"detail": 0.02, "mean": 0.3, "variance": 0.01, "textlike": 0.0},
                "bottom_right": {"detail": 0.25, "mean": 0.7, "variance": 0.1, "textlike": 0.05},
                "center": {"detail": 0.3, "mean": 0.6, "variance": 0.1, "textlike": 0.0},
                "bottom_center": {"detail": 0.15, "mean": 0.5, "variance": 0.05, "textlike": 0.0},
            },
            "avoid": ["bottom_right", "center"],
            "fallback": "bottom_left",
        }
        place, *_rest = select_placement(
            role="LOCATION", text="Texas", composition=composition
        )
        self.assertEqual(place, "bottom_left")

    def test_face_avoidance(self) -> None:
        composition = {
            "avoid": ["bottom_center", "center"],
            "cells": {
                "bottom_center": {"detail": 0.4, "mean": 0.5, "variance": 0.1, "textlike": 0.0},
                "bottom_left": {"detail": 0.05, "mean": 0.35, "variance": 0.02, "textlike": 0.0},
                "bottom_right": {"detail": 0.06, "mean": 0.35, "variance": 0.02, "textlike": 0.0},
            },
            "fallback": "bottom_left",
        }
        place, *_ = select_placement(
            role="CALLOUT", text="Important point", composition=composition
        )
        self.assertNotIn(place, ("bottom_center", "center"))

    def test_lower_third_prefers_bottom_left(self) -> None:
        place, px, py, align, scores, _ = select_placement(
            role="LOWER_THIRD", text="Jane Doe"
        )
        self.assertEqual(place, "bottom_left")
        self.assertEqual(align, "left")
        self.assertGreater(scores["bottom_left"], scores["top_right"])

    def test_deterministic(self) -> None:
        a = score_placements(role="STATISTIC", text="+25%")
        b = score_placements(role="STATISTIC", text="+25%")
        self.assertEqual(a, b)


class TestBackgroundIntelligence(unittest.TestCase):
    def test_busy_bright_gets_separation(self) -> None:
        comp = {
            "cells": {
                "center": {"mean": 0.8, "detail": 0.2, "variance": 0.1, "textlike": 0.0},
            },
            "avoid": ["center"],
        }
        bg = choose_background(
            role="EMPHASIS",
            text="A longer emphasis line here",
            composition=comp,
            importance="high",
        )
        self.assertIn(bg, ("SCRIM", "GRADIENT", "PANEL", "FULL_WIDTH_OVERLAY", "PILL"))

    def test_clean_dark_minimal(self) -> None:
        comp = {
            "cells": {
                "bottom_left": {"mean": 0.25, "detail": 0.02, "variance": 0.01, "textlike": 0.0},
            }
        }
        bg = choose_background(role="LOCATION", text="Oslo", composition=comp, importance="low")
        self.assertIn(bg, ("NONE", "SHADOW", "PILL"))


class TestAnimationIntelligence(unittest.TestCase):
    def test_statistic_reveal(self) -> None:
        self.assertEqual(select_animation(role="STATISTIC"), "MASK_REVEAL")

    def test_location_slide(self) -> None:
        self.assertEqual(select_animation(role="LOCATION"), "SLIDE")

    def test_person_slide(self) -> None:
        self.assertEqual(select_animation(role="LOWER_THIRD"), "SLIDE")

    def test_chapter_reveal(self) -> None:
        self.assertEqual(select_animation(role="CHAPTER"), "MASK_REVEAL")

    def test_normal_text_fades(self) -> None:
        self.assertEqual(select_animation(role="CAPTION"), "FADE")
        self.assertEqual(select_animation(role="EMPHASIS", emphasis="normal"), "FADE")

    def test_fast_footage_softens(self) -> None:
        anim = select_animation(
            role="EMPHASIS",
            emphasis="dramatic",
            purpose="reveal",
            footage={"motion_level": 0.9},
        )
        self.assertEqual(anim, "FADE")

    def test_busy_footage_simplifies(self) -> None:
        anim = select_animation(
            role="EMPHASIS",
            emphasis="dramatic",
            purpose="reveal",
            footage={"visual_complexity": 0.8, "motion_level": 0.3},
        )
        self.assertEqual(anim, "FADE")

    def test_fast_footage_does_not_get_slow_reveal(self) -> None:
        anim = select_animation(
            role="CALLOUT",
            purpose="reveal",
            duration=0.8,
            footage={"motion_level": 0.8},
        )
        self.assertEqual(anim, "FADE")

    def test_stable_important_fact_may_reveal(self) -> None:
        anim = select_animation(
            role="EMPHASIS",
            emphasis="strong",
            purpose="emphasize",
            footage={"motion_level": 0.15, "stable": True},
        )
        self.assertEqual(anim, "MASK_REVEAL")

    def test_deterministic_animation(self) -> None:
        a = select_animation(role="LOCATION", footage={"motion_level": 0.3})
        b = select_animation(role="LOCATION", footage={"motion_level": 0.3})
        self.assertEqual(a, b)


class TestMemoryAndDensity(unittest.TestCase):
    def test_repeated_concept_suppressed(self) -> None:
        mem = GraphicsMemory()
        mem.record(
            graphic_id="a",
            role="LOCATION",
            text="Texas",
            start=0.0,
            importance="low",
            scene_number="1",
        )
        reason = mem.should_suppress(
            role="LOCATION",
            text="Texas",
            start=5.0,
            importance="low",
            priority=3,
        )
        self.assertEqual(reason, "repeated_concept")

    def test_high_importance_survives_density(self) -> None:
        mem = GraphicsMemory()
        for i in range(4):
            mem.record(
                graphic_id=f"g{i}",
                role="LABEL",
                text=f"item{i}",
                start=float(i),
                importance="low",
                scene_number=str(i),
            )
        reason = mem.should_suppress(
            role="STATISTIC",
            text="+25%",
            start=10.0,
            importance="high",
            priority=3,
        )
        self.assertIsNone(reason)


class TestComposePresentation(unittest.TestCase):
    def test_statistic_bundle(self) -> None:
        d = compose_presentation(
            role="STATISTIC",
            text="+25%",
            secondary_text="DEMAND",
            scene_start=0.0,
            scene_end=5.0,
            scene_duration=5.0,
            importance="high",
            decision="STATISTIC",
            narration="Demand is expected to increase by 25 percent.",
        )
        self.assertEqual(d.style_id, "fact_number")
        self.assertEqual(d.animation, "MASK_REVEAL")
        self.assertGreaterEqual(d.size_vh, 0.052)
        self.assertLessEqual(d.size_vh, 0.078)
        self.assertLess(d.end - d.start, 5.0)
        self.assertEqual(d.scale, 1.0)

    def test_person_bundle(self) -> None:
        d = compose_presentation(
            role="NAME",
            text="Malcolm McLean",
            secondary_text="Shipping pioneer",
            scene_start=0.0,
            scene_end=4.0,
            scene_duration=4.0,
        )
        self.assertEqual(d.role, "NAME")
        self.assertEqual(d.background, "LOWER_THIRD")
        self.assertEqual(d.animation, "SLIDE")

    def test_deterministic_compose(self) -> None:
        kwargs = dict(
            role="LOCATION",
            text="California",
            scene_start=1.0,
            scene_end=5.0,
            scene_duration=4.0,
            confidence=0.7,
        )
        a = compose_presentation(**kwargs)
        b = compose_presentation(**kwargs)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_semantics_infer(self) -> None:
        role, imp, emp, purp = infer_semantics(
            role="STATISTIC", confidence=0.8, decision="STATISTIC"
        )
        self.assertEqual(role, "STATISTIC")
        self.assertEqual(purp, "quantify")
        self.assertIn(imp, ("medium", "high"))

    def test_occupied_area_stays_restrained(self) -> None:
        from graphics.composition import occupied_block_ratios

        d = compose_presentation(
            role="LABEL",
            text="A moderately long informational overlay about demand",
            scene_start=0.0,
            scene_end=5.0,
            scene_duration=5.0,
            importance="medium",
        )
        w, h = occupied_block_ratios(
            "A moderately long informational overlay about demand", d.size_vh
        )
        self.assertLessEqual(h, 0.16)
        self.assertLessEqual(w, 0.52)
        self.assertGreaterEqual(d.position_x, 0.12)
        self.assertLessEqual(d.position_x, 0.88)
        self.assertGreaterEqual(d.position_y, 0.12)
        self.assertLessEqual(d.position_y, 0.86)


if __name__ == "__main__":
    unittest.main()
