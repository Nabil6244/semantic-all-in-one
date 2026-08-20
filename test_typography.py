"""Focused tests for the typography theme / render layer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_editing import SmartEditingSettings, drawtext_filters, plan_text_effects
from typography import (
    DEFAULT_THEME,
    EFFECT_TO_STYLE,
    TYPOGRAPHY_STYLES,
    FontRegistry,
    TypographyTheme,
    build_drawtext_filters,
    classify_semantic,
    format_display_text,
    map_effect_to_style,
    plan_typography_decision,
    render_style_overlay,
    reset_variation_history,
    resolve_font_path,
    typography_params_for_effect,
)
from typography.fonts import bundled_fonts_dir, list_bundled_fonts, reset_font_cache
from typography.placement import PLACEMENTS, resolve_placement
from typography.styles import TYPOGRAPHY_STYLE_IDS, casing_mode_for_style
from typography.variation import VariationHistory, score_style_only


class TestFontResolution(unittest.TestCase):
    def setUp(self) -> None:
        reset_font_cache()

    def test_bundled_fonts_present(self) -> None:
        fonts = list_bundled_fonts()
        families = {f for f, _, _ in fonts}
        for required in (
            "Manrope",
            "Inter",
            "Plus Jakarta Sans",
            "Space Grotesk",
            "DM Sans",
            "Outfit",
        ):
            self.assertIn(required, families, f"missing bundled family {required}")
        self.assertTrue(bundled_fonts_dir().is_dir())

    def test_resolve_preferred_families(self) -> None:
        manrope = resolve_font_path("Manrope", "ExtraBold")
        inter = resolve_font_path("Inter", "Bold")
        self.assertIsNotNone(manrope)
        self.assertIsNotNone(inter)
        self.assertTrue(Path(manrope).is_file())
        self.assertTrue(Path(inter).is_file())

    def test_registry_falls_back_for_unknown_weight(self) -> None:
        path = FontRegistry().resolve("Space Grotesk", "ExtraBold")
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())


class TestStyleMapping(unittest.TestCase):
    def test_all_style_ids_defined(self) -> None:
        for style_id in TYPOGRAPHY_STYLE_IDS:
            self.assertIn(style_id, TYPOGRAPHY_STYLES)

    def test_effect_map_covers_presets(self) -> None:
        for effect in (
            "fade",
            "highlight",
            "rise",
            "pop",
            "punch",
            "scale",
            "word_reveal",
            "impact",
        ):
            self.assertIn(effect, EFFECT_TO_STYLE)
            self.assertIn(EFFECT_TO_STYLE[effect], TYPOGRAPHY_STYLES)

    def test_question_style(self) -> None:
        self.assertEqual(
            map_effect_to_style("highlight", "What will technology turn us into?"),
            "question",
        )

    def test_number_style(self) -> None:
        self.assertEqual(map_effect_to_style("impact", "42%"), "fact_number")
        self.assertEqual(map_effect_to_style("highlight", "$100"), "fact_number")

    def test_normal_sentence_minimal_caption(self) -> None:
        self.assertEqual(
            map_effect_to_style(
                "highlight",
                "Technology is changing the way we live.",
            ),
            "minimal_caption",
        )
        self.assertEqual(
            map_effect_to_style(
                "fade",
                "Every single day, technology is changing the way we live.",
            ),
            "minimal_caption",
        )

    def test_emphasis_keyword_and_punch(self) -> None:
        self.assertEqual(map_effect_to_style("highlight", "Neural"), "keyword_highlight")
        self.assertEqual(map_effect_to_style("punch", "NOW"), "kinetic_punch")
        self.assertEqual(
            map_effect_to_style("punch", "WE DON'T EVEN NOTICE IT HAPPENING."),
            "statement",
        )

    def test_word_reveal_and_statement(self) -> None:
        self.assertEqual(map_effect_to_style("word_reveal", "one by one"), "word_reveal")
        self.assertEqual(map_effect_to_style("rise", "The shift begins"), "statement")

    def test_short_dramatic_statement(self) -> None:
        self.assertEqual(map_effect_to_style("rise", "we don't notice"), "statement")
        self.assertEqual(
            map_effect_to_style("highlight", "attention economy"),
            "keyword_highlight",
        )


class TestDisabledTextEffects(unittest.TestCase):
    def test_plan_empty_when_text_effects_off(self) -> None:
        rows = [{"scene_number": "1", "script_segment": 'We "HATE" MONDAYS and $100.'}]
        aligned = [{"scene_number": "1", "start_time": 0.0, "end_time": 5.0}]
        whisper = [("we", 0.0, 0.2), ("hate", 0.2, 0.5), ("mondays", 0.5, 0.9)]
        settings = SmartEditingSettings(text_effects=False, sound_effects=False)
        self.assertEqual(plan_text_effects(rows, aligned, whisper, settings), [])

    def test_drawtext_empty_for_no_effects(self) -> None:
        self.assertEqual(build_drawtext_filters([], 1280, 720), "")
        self.assertEqual(drawtext_filters([], 1280, 720), "")

    def test_params_empty_text_when_effects_off_payload_empty(self) -> None:
        self.assertEqual(build_drawtext_filters([], 1920, 1080), "")


class TestDisplayCasing(unittest.TestCase):
    def setUp(self) -> None:
        reset_variation_history()
    def test_natural_sentence_casing(self) -> None:
        self.assertEqual(
            format_display_text(
                "technology is changing the way we live.",
                casing="sentence",
            ),
            "Technology is changing the way we live.",
        )

    def test_question_casing(self) -> None:
        self.assertEqual(
            format_display_text(
                "what will technology turn us into?",
                casing="sentence",
            ),
            "What will technology turn us into?",
        )

    def test_emphasis_casing_modes(self) -> None:
        self.assertEqual(format_display_text("breakthrough", casing="upper"), "BREAKTHROUGH")
        self.assertEqual(
            format_display_text("attention economy", casing="title"),
            "Attention Economy",
        )
        self.assertEqual(
            casing_mode_for_style(
                "minimal_caption", "technology is changing", uppercase_flag=False
            ),
            "sentence",
        )
        self.assertEqual(
            casing_mode_for_style("kinetic_punch", "breakthrough", uppercase_flag=True),
            "upper",
        )

    def test_style_specific_uppercase_behavior(self) -> None:
        punch = typography_params_for_effect(
            {
                "text": "breakthrough",
                "effect": "punch",
                "intensity": 0.65,
                "local_start": 1.0,
                "local_end": 1.4,
            },
            1920,
            1080,
        )
        self.assertEqual(punch["style_id"], "kinetic_punch")
        self.assertEqual(punch["text"], "BREAKTHROUGH")
        self.assertEqual(punch["raw_text"], "breakthrough")

        caption = typography_params_for_effect(
            {
                "text": "technology is changing the way we live.",
                "effect": "fade",
                "intensity": 0.5,
                "local_start": 0.0,
                "local_end": 0.8,
            },
            1920,
            1080,
        )
        self.assertEqual(caption["style_id"], "minimal_caption")
        self.assertEqual(caption["text"], "Technology is changing the way we live.")
        self.assertFalse(caption["text"].isupper())

        question = typography_params_for_effect(
            {
                "text": "what will technology turn us into?",
                "effect": "highlight",
                "intensity": 0.6,
                "local_start": 0.0,
                "local_end": 0.7,
            },
            1280,
            720,
        )
        self.assertEqual(question["style_id"], "question")
        self.assertEqual(question["text"], "What will technology turn us into?")

    def test_weak_filler_words_skipped(self) -> None:
        fx = {
            "text": "through",
            "effect": "highlight",
            "intensity": 0.65,
            "local_start": 0.2,
            "local_end": 0.5,
        }
        params = typography_params_for_effect(fx, 1280, 720)
        self.assertEqual(params["text"], "")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(render_style_overlay(fx, Path(tmp) / "weak.png", 1280, 720))

    def test_drawtext_includes_modern_params(self) -> None:
        fx = [
            {
                "text": "AI",
                "effect": "punch",
                "intensity": 0.7,
                "local_start": 0.2,
                "local_end": 0.6,
            }
        ]
        filt = build_drawtext_filters(fx, 1280, 720)
        self.assertIn("drawtext=", filt)
        self.assertIn("fontfile=", filt)
        self.assertIn("letter_spacing=", filt)
        self.assertIn(r"between(t\,0.200\,0.600)", filt)
        self.assertNotRegex(filt, r"fontcolor=white@\(if\(lt\(t,[0-9]")

    def test_theme_override_changes_size(self) -> None:
        fx = {
            "text": "Quiet moment here today",
            "effect": "fade",
            "intensity": 0.5,
            "local_start": 0.0,
            "local_end": 0.4,
        }
        base = typography_params_for_effect(fx, 1280, 720, theme=DEFAULT_THEME)
        theme = TypographyTheme(
            style_overrides={"minimal_caption": {"size_vh": 0.08}},
        )
        tuned = typography_params_for_effect(fx, 1280, 720, theme=theme)
        self.assertGreater(tuned["fontsize"], base["fontsize"])

    def test_pillow_overlay_writes_png(self) -> None:
        fx = {
            "text": "42%",
            "effect": "impact",
            "intensity": 0.8,
            "local_start": 0.1,
            "local_end": 0.5,
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fact.png"
            path = render_style_overlay(fx, out, 1280, 720)
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 500)


class TestPlacement(unittest.TestCase):
    def setUp(self) -> None:
        reset_variation_history()
    def test_deterministic_position_selection(self) -> None:
        a = resolve_placement("keyword_highlight", "Neural", 1920, 1080, fontsize=48)
        b = resolve_placement("keyword_highlight", "Neural", 1920, 1080, fontsize=48)
        self.assertEqual(a["placement"], b["placement"])
        self.assertIn(a["placement"], PLACEMENTS)

    def test_aspect_ratio_aware_positioning(self) -> None:
        landscape = resolve_placement("fact_number", "42%", 1920, 1080, fontsize=80)
        vertical = resolve_placement("fact_number", "42%", 1080, 1920, fontsize=80)
        self.assertIn(landscape["placement"], ("top_right", "top_left", "top_center"))
        self.assertEqual(vertical["placement"], "top_center")
        self.assertEqual(vertical["aspect"], "vertical")
        self.assertEqual(landscape["aspect"], "landscape")

    def test_long_text_positioning(self) -> None:
        long = (
            "Technology is changing the way we live every single day around us now."
        )
        info = resolve_placement("minimal_caption", long, 1920, 1080, fontsize=36)
        self.assertEqual(info["placement"], "bottom_center")
        self.assertFalse(info["placement"].endswith(("_left", "_right")))

    def test_params_expose_placement(self) -> None:
        params = typography_params_for_effect(
            {
                "text": "42%",
                "effect": "impact",
                "intensity": 0.8,
                "local_start": 0.1,
                "local_end": 0.4,
            },
            1920,
            1080,
        )
        self.assertIn(params["placement"], PLACEMENTS)
        self.assertIn("placement_info", params)


class TestProofStyle(unittest.TestCase):
    def setUp(self) -> None:
        reset_variation_history()

    def test_proof_env_forces_unmistakable_style(self) -> None:
        import os

        os.environ["VIDEOGEN_TYPOGRAPHY_PROOF"] = "1"
        try:
            self.assertEqual(map_effect_to_style("fade", "quietly now"), "proof_modern")
            params = typography_params_for_effect(
                {
                    "text": "changing",
                    "effect": "highlight",
                    "intensity": 0.8,
                    "local_start": 0.1,
                    "local_end": 0.5,
                },
                1280,
                720,
            )
            self.assertEqual(params["style_id"], "proof_modern")
            self.assertEqual(params["text"], "Changing")
            self.assertEqual(params["placement"], "top_left")
            self.assertTrue(params["accent_bar"])
            self.assertIn("Manrope", str(params.get("font_path") or ""))
        finally:
            os.environ.pop("VIDEOGEN_TYPOGRAPHY_PROOF", None)


class TestVariationAntiRepetition(unittest.TestCase):
    def setUp(self) -> None:
        reset_variation_history()

    def test_semantic_type_influences_style(self) -> None:
        self.assertEqual(classify_semantic("What happens next?", "highlight"), "question")
        self.assertEqual(classify_semantic("42%", "impact"), "fact")
        self.assertEqual(classify_semantic("WE ARE DONE", "punch"), "dramatic")
        self.assertIn(
            classify_semantic(
                "Technology is changing the way we live every day.",
                "fade",
            ),
            ("long_narration", "narration"),
        )
        q = plan_typography_decision("What will technology turn us into?", "highlight")
        self.assertEqual(q.style_id, "question")
        f = plan_typography_decision("42%", "impact")
        self.assertEqual(f.style_id, "fact_number")
        d = plan_typography_decision("NOW", "punch")
        self.assertEqual(d.style_id, "kinetic_punch")

    def test_long_text_gets_lower_third(self) -> None:
        reset_variation_history()
        d = plan_typography_decision(
            "Technology is changing the way we live every single day around us.",
            "fade",
            duration=1.5,
        )
        self.assertEqual(d.style_id, "minimal_caption")
        self.assertIn(d.placement, ("bottom_center", "bottom_left", "bottom_right"))

    def test_numbers_and_questions(self) -> None:
        reset_variation_history()
        self.assertEqual(
            typography_params_for_effect(
                {"text": "42%", "effect": "impact", "local_start": 0, "local_end": 0.4},
                1280,
                720,
            )["style_id"],
            "fact_number",
        )
        self.assertEqual(
            typography_params_for_effect(
                {
                    "text": "What will technology turn us into?",
                    "effect": "highlight",
                    "local_start": 0,
                    "local_end": 0.8,
                },
                1280,
                720,
            )["style_id"],
            "question",
        )

    def test_short_dramatic_can_be_kinetic(self) -> None:
        reset_variation_history()
        d = plan_typography_decision("BREAKTHROUGH", "punch", duration=0.4)
        self.assertEqual(d.style_id, "kinetic_punch")

    def test_consecutive_effects_vary_style(self) -> None:
        reset_variation_history()
        # Many similar keywords — must not all lock to one style.
        texts = [
            "Neural",
            "Attention",
            "Signal",
            "Pattern",
            "Network",
            "System",
            "Model",
            "Engine",
        ]
        styles = []
        for t in texts:
            d = plan_typography_decision(t, "highlight", duration=0.5)
            styles.append(d.style_id)
        unique = set(styles)
        self.assertGreaterEqual(len(unique), 2, f"styles not varied: {styles}")
        # No run of 3 identical styles in a row.
        for i in range(len(styles) - 2):
            self.assertFalse(
                styles[i] == styles[i + 1] == styles[i + 2],
                f"same style thrice at {i}: {styles}",
            )

    def test_consecutive_effects_vary_position(self) -> None:
        reset_variation_history()
        placements = []
        for t in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"):
            d = plan_typography_decision(t, "highlight", duration=0.5)
            placements.append(d.placement)
        self.assertGreaterEqual(len(set(placements)), 2, f"placements: {placements}")
        for i in range(len(placements) - 2):
            self.assertFalse(
                placements[i] == placements[i + 1] == placements[i + 2],
                f"same placement thrice: {placements}",
            )

    def test_repeated_styles_are_penalized(self) -> None:
        hist = VariationHistory()
        d1 = plan_typography_decision("Neural", "highlight", history=hist, record=True)
        before = score_style_only(d1.style_id, "Attention", "highlight", history=hist)
        # Empty-history baseline for same candidate.
        fresh = VariationHistory()
        baseline = score_style_only(d1.style_id, "Attention", "highlight", history=fresh)
        self.assertLess(before, baseline)

    def test_text_effects_off_bypasses_typography(self) -> None:
        rows = [{"scene_number": "1", "script_segment": 'We "HATE" MONDAYS and $100.'}]
        aligned = [{"scene_number": "1", "start_time": 0.0, "end_time": 5.0}]
        whisper = [("we", 0.0, 0.2), ("hate", 0.2, 0.5), ("mondays", 0.5, 0.9)]
        settings = SmartEditingSettings(text_effects=False, sound_effects=False)
        self.assertEqual(plan_text_effects(rows, aligned, whisper, settings), [])
        self.assertEqual(build_drawtext_filters([], 1280, 720), "")


if __name__ == "__main__":
    unittest.main()
