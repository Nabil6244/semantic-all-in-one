"""Tests for Professional Graphics + Motion Design Engine (Phases 1–3)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from editorial.intent import EditorialIntent
from editorial.schema import EditorialPlan, EditorialScene
from editorial.timeline import EditorialTimeline
from graphics.backgrounds import choose_background
from graphics.design_system import get_design_system
from graphics.director import decide_graphic
from graphics.engine import (
    graphic_spec_to_timeline_event,
    graphics_from_timeline,
    materialize_graphics_on_timeline,
    plan_graphics,
)
from graphics.extract import extract_locations, extract_statistics
from graphics.lifecycle import compute_lifecycle
from graphics.motion import ease, overlay_animation_name, sample_keyframes
from graphics.render import render_graphic_overlay
from graphics.schema import GraphicSpec, Keyframe, TextOverlaySpec
from graphics.statistic import build_statistic_overlay
from graphics.text_overlay import build_text_overlay
from graphics.director import GraphicDirective


def _scene(sn: str, text: str, *, purpose: str = "context", start: float = 0.0, end: float = 5.0):
    return EditorialScene(
        scene_number=sn,
        start=start,
        end=end,
        duration=end - start,
        narration_excerpt=text,
        purpose=purpose,  # type: ignore[arg-type]
    )


class TestExtract(unittest.TestCase):
    def test_meaningful_percent(self) -> None:
        stats = extract_statistics("Demand is expected to increase by 25 percent.")
        self.assertTrue(stats)
        self.assertIn("%", stats[0].display)
        self.assertTrue(stats[0].meaningful)

    def test_bare_year_skipped(self) -> None:
        stats = extract_statistics("In 1990 the grid was small.")
        self.assertEqual(stats, [])

    def test_location_known(self) -> None:
        locs = extract_locations("The projects stretch from Texas to California.")
        names = {l.name for l in locs}
        self.assertIn("Texas", names)
        self.assertIn("California", names)


class TestDirectorRestraint(unittest.TestCase):
    def test_no_graphic_for_plain_atmosphere(self) -> None:
        d = decide_graphic(
            narration="Soft light filled the quiet room as evening settled in.",
            purpose="emotion",
        )
        self.assertEqual(d, [])

    def test_statistic_when_meaningful(self) -> None:
        d = decide_graphic(
            narration="Demand is expected to increase by 25 percent this decade.",
            purpose="evidence",
        )
        self.assertTrue(d)
        self.assertEqual(d[0].decision, "STATISTIC")

    def test_location_label(self) -> None:
        d = decide_graphic(
            narration="In Texas, new plants are rising across the plains.",
            purpose="location",
        )
        self.assertTrue(d)
        self.assertEqual(d[0].decision, "LOCATION")

    def test_intent_none_suppresses(self) -> None:
        intent = EditorialIntent(
            scene_number="1",
            text_strategy="none",
            graphic_strategy="none",
            evidence_level="none",
            confidence=0.9,
        )
        d = decide_graphic(
            narration="Demand is expected to increase by 25 percent.",
            purpose="context",
            intent=intent,
        )
        # No statistic role / evidence purpose → suppressed
        self.assertEqual(d, [])


class TestBackgrounds(unittest.TestCase):
    def test_bright_complex_gets_scrim_or_gradient(self) -> None:
        comp = {
            "cells": {
                "center": {"mean": 0.8, "detail": 0.2, "variance": 0.1, "textlike": 0.0},
                "top_left": {"mean": 0.75, "detail": 0.18, "variance": 0.1, "textlike": 0.0},
            },
            "avoid": ["center"],
        }
        bg = choose_background(role="CAPTION", text="A longer caption line here", composition=comp)
        self.assertIn(bg, ("SCRIM", "GRADIENT", "FULL_WIDTH_OVERLAY", "PANEL"))

    def test_dark_clean_allows_none(self) -> None:
        comp = {
            "cells": {
                "center": {"mean": 0.25, "detail": 0.02, "variance": 0.01, "textlike": 0.0},
            }
        }
        bg = choose_background(role="LABEL", text="Austin", composition=comp)
        self.assertIn(bg, ("NONE", "SHADOW", "PILL"))

    def test_lower_third_role(self) -> None:
        bg = choose_background(role="LOWER_THIRD", text="Jane Doe")
        self.assertEqual(bg, "LOWER_THIRD")


class TestLifecycleAndMotion(unittest.TestCase):
    def test_lifecycle_fits_window(self) -> None:
        lc = compute_lifecycle(role="STATISTIC", available_s=2.0)
        self.assertLessEqual(lc.total, 2.05)

    def test_easing(self) -> None:
        self.assertEqual(ease(0.0, "ease_out"), 0.0)
        self.assertEqual(ease(1.0, "ease_out"), 1.0)
        self.assertGreater(ease(0.5, "ease_out"), 0.5)

    def test_keyframes(self) -> None:
        kfs = [Keyframe(0.0, 0.0), Keyframe(1.0, 1.0, "linear")]
        self.assertAlmostEqual(sample_keyframes(kfs, 0.5), 0.5)

    def test_overlay_map(self) -> None:
        self.assertEqual(overlay_animation_name("SCALE"), "fade")
        self.assertEqual(overlay_animation_name("SLIDE"), "slide_fade")


class TestPlanAndTimeline(unittest.TestCase):
    def test_plan_graphics_materializes_on_timeline(self) -> None:
        plan = EditorialPlan(
            scenes=[
                _scene(
                    "1",
                    "Demand is expected to increase by 25 percent across the grid.",
                    purpose="evidence",
                    start=0,
                    end=6,
                ),
                _scene(
                    "2",
                    "In California the buildout continues.",
                    purpose="location",
                    start=6,
                    end=10,
                ),
            ],
            audio_end=10,
        )
        gplan = plan_graphics(plan)
        self.assertGreaterEqual(len(gplan.specs), 1)
        roles = {s.role for s in gplan.specs}
        self.assertTrue("STATISTIC" in roles or "LOCATION" in roles)

        tl = EditorialTimeline(audio_end=10)
        materialize_graphics_on_timeline(tl, gplan)
        gfx_events = [e for e in tl.events if (e.metadata or {}).get("graphic")]
        self.assertEqual(len(gfx_events), len(gplan.specs))
        recovered = graphics_from_timeline(tl)
        self.assertEqual(len(recovered), len(gplan.specs))

    def test_timeline_event_has_payload(self) -> None:
        d = GraphicDirective(
            decision="STATISTIC",
            role="STATISTIC",
            reason="test",
            confidence=0.8,
            priority=3,
            text_hint="+25%",
            secondary_hint="DEMAND",
            payload={"value": 25.0, "unit": "%"},
        )
        spec = build_text_overlay(
            d,
            scene_number="1",
            scene_start=0,
            scene_end=5,
            scene_duration=5,
        )
        spec.text = build_statistic_overlay(
            display="+25%", label="DEMAND", value=25.0, unit="%",
            start=spec.start, end=spec.end, lifecycle=spec.lifecycle,
        )
        ev = graphic_spec_to_timeline_event(spec)
        self.assertEqual(ev.track, "TEXT")
        self.assertTrue(ev.metadata.get("graphic"))
        self.assertIn("+25%", ev.source)


class TestRender(unittest.TestCase):
    def test_statistic_png(self) -> None:
        spec = GraphicSpec(
            graphic_id="g1",
            decision="STATISTIC",
            role="STATISTIC",
            start=0,
            end=3,
            text=build_statistic_overlay(display="+25%", label="ELECTRICITY DEMAND"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "stat.png"
            path = render_graphic_overlay(spec, out, 1280, 720)
            self.assertIsNotNone(path)
            self.assertTrue(Path(path).is_file())
            self.assertGreater(Path(path).stat().st_size, 500)

    def test_lower_third_png(self) -> None:
        from graphics.lower_third import build_lower_third

        spec = GraphicSpec(
            graphic_id="g2",
            decision="LOWER_THIRD",
            role="LOWER_THIRD",
            start=0,
            end=3,
            text=build_lower_third(name="John Smith", title="Energy Analyst"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lt.png"
            path = render_graphic_overlay(spec, out, 1280, 720)
            self.assertIsNotNone(path)
            self.assertTrue(Path(path).is_file())

    def test_location_label_png(self) -> None:
        spec = GraphicSpec(
            graphic_id="g3",
            decision="LOCATION",
            role="LOCATION",
            start=0,
            end=2.5,
            text=TextOverlaySpec(
                role="LOCATION",
                text="Texas",
                background="PILL",
                animation="SLIDE",
                position_x=0.18,
                position_y=0.14,
                alignment="left",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "loc.png"
            path = render_graphic_overlay(spec, out, 1280, 720)
            self.assertIsNotNone(path)


class TestDesignSystem(unittest.TestCase):
    def test_consistent_package(self) -> None:
        ds = get_design_system()
        self.assertEqual(ds.name, "documentary_package_v1")
        self.assertEqual(ds.animation_for("STATISTIC"), "MASK_REVEAL")
        self.assertEqual(ds.background_for("LOWER_THIRD"), "LOWER_THIRD")


class TestNameExtraction(unittest.TestCase):
    def test_malcolm_mclean_not_then_malcolm(self) -> None:
        from graphics.extract import extract_name_title

        named = extract_name_title(
            "Then Malcolm McLean introduced the modern shipping container."
        )
        self.assertIsNotNone(named)
        assert named is not None
        self.assertEqual(named.name, "Malcolm McLean")
        self.assertNotIn("Then", named.name)
        self.assertTrue(len(named.title) <= 36)


class TestSmartTextConflicts(unittest.TestCase):
    def test_floating_name_suppressed_by_lower_third(self) -> None:
        from graphics.conflicts import filter_smart_text_for_graphics
        from graphics.schema import GraphicSpec, TextOverlaySpec

        gfx = [
            GraphicSpec(
                graphic_id="g1",
                decision="LOWER_THIRD",
                role="LOWER_THIRD",
                scene_number="1",
                start=1.0,
                end=4.0,
                text=TextOverlaySpec(
                    role="LOWER_THIRD",
                    text="Malcolm McLean",
                    secondary_text="Modern shipping",
                    start=1.0,
                    end=4.0,
                ),
            )
        ]
        fx = [
            {
                "text": "Mclean",
                "local_start": 1.2,
                "local_end": 2.5,
                "effect": "punch",
            }
        ]
        kept = filter_smart_text_for_graphics(
            fx, gfx, scene_start=0.0, scene_end=5.0
        )
        self.assertEqual(kept, [])

    def test_unrelated_smart_text_kept(self) -> None:
        from graphics.conflicts import filter_smart_text_for_graphics
        from graphics.schema import GraphicSpec, TextOverlaySpec

        gfx = [
            GraphicSpec(
                graphic_id="g1",
                decision="LOCATION",
                role="LOCATION",
                start=0.2,
                end=2.0,
                text=TextOverlaySpec(role="LOCATION", text="Texas", start=0.2, end=2.0),
            )
        ]
        fx = [
            {
                "text": "breakthrough",
                "local_start": 3.0,
                "local_end": 4.0,
                "effect": "highlight",
            }
        ]
        kept = filter_smart_text_for_graphics(
            fx, gfx, scene_start=0.0, scene_end=5.0
        )
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
