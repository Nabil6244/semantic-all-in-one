"""Enoch Template, Phase 6: the four whole-frame card kinds (plus the statement card) -- required data, no invented
quotations or credentials, no overflow, readable long names, Unicode limits stated honestly, deterministic pixels, and
the existing graphics untouched (names, keywords, numbers and maps stay with graphics/)."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ancient_texts.cards import KINDS, CardError, CardSpec, missing_glyphs, render, text_regions_fit, validate
from enoch_template_testutil import NoPaidCalls

TMP = Path(tempfile.mkdtemp())
Image.new("RGB", (1400, 900), (150, 120, 80)).save(TMP / "obj.jpg")
Image.new("RGB", (700, 1200), (90, 70, 50)).save(TMP / "obj2.jpg")

GOOD = {
    "source_excerpt": {"text": "A summary of what the passage says, in the narrator's language.", "citation": "Synthetic Edition (fixture)",
                       "locator": "ch. 46", "mode": "summary", "highlight": "what the passage says"},
    "framed_object": {"image": str(TMP / "obj.jpg"), "caption": "Fragment, Cave 4 (fixture)"},
    "comparison": {"left_image": str(TMP / "obj.jpg"), "left_label": "Text A", "right_image": str(TMP / "obj2.jpg"),
                   "right_label": "Text B", "title": "Two texts, one title"},
    "section_break": {"title": "Where the book survived", "subtitle": "A short subtitle"},
    "statement": {"phrase": "It was already there before the world.", "highlight": "already there"},
}


def codes(spec, **kw):
    return [i.code for i in validate(spec, **kw)]


class Validation(unittest.TestCase):
    def test_every_kind_validates_its_required_data(self):
        for kind in KINDS:
            self.assertEqual(codes(CardSpec(kind, dict(GOOD[kind]))), [], kind)
            missing = dict(GOOD[kind])
            missing.pop(next(iter(missing)))
            self.assertIn("card_missing_field", codes(CardSpec(kind, missing)), kind)
        self.assertEqual(codes(CardSpec("poster", {})), ["unknown_card_kind"])

    def test_quotation_needs_a_verified_quote_and_must_match_it(self):
        spec = CardSpec("source_excerpt", {"text": "And there I saw One", "citation": "Ed.", "locator": "46:1", "mode": "quotation"})
        self.assertIn("quote_not_verified", codes(spec))
        self.assertEqual(codes(spec, verified_quote=("And there I saw One", "Ed.", "Ed.", "46:1")), [])
        self.assertIn("quote_altered", codes(spec, verified_quote=("And there I saw Him", "Ed.", "Ed.", "46:1")))

    def test_credentials_are_never_printed_on_cards(self):
        spec = CardSpec("framed_object", dict(GOOD["framed_object"], credential="Professor at a university"))
        self.assertIn("unbacked_credential", codes(spec))
        with self.assertRaises(CardError):
            render(spec, TMP / "x.png")

    def test_statement_is_never_dressed_as_a_quote(self):
        self.assertIn("statement_looks_like_quote", codes(CardSpec("statement", {"phrase": '"He said this"'})))
        self.assertIn("card_text_too_long", codes(CardSpec("statement", {"phrase": " ".join(["word"] * 20)})))

    def test_missing_image_is_a_hard_failure_not_a_substitute(self):
        self.assertIn("card_image_missing", codes(CardSpec("framed_object", {"image": str(TMP / "none.jpg"), "caption": "x"})))


class Rendering(unittest.TestCase):
    def test_all_kinds_render_at_the_apps_output_sizes(self):
        with NoPaidCalls() as guard:
            for size in ((1920, 1080), (3840, 2160)):
                for kind in KINDS:
                    out = render(CardSpec(kind, dict(GOOD[kind])), TMP / f"{kind}_{size[0]}.png", size)
                    with Image.open(out) as im:
                        self.assertEqual(im.size, size)
        guard.assert_clean()

    def test_deterministic(self):
        a = render(CardSpec("comparison", dict(GOOD["comparison"])), TMP / "a.png")
        b = render(CardSpec("comparison", dict(GOOD["comparison"])), TMP / "b.png")
        self.assertEqual(hashlib.sha256(a.read_bytes()).hexdigest(), hashlib.sha256(b.read_bytes()).hexdigest())

    def test_long_names_and_titles_fit_or_are_refused(self):
        long_title = "The Ethiopic Book of Enoch in the Collections of the Monasteries of Lake Tana"
        self.assertTrue(text_regions_fit(CardSpec("section_break", {"title": long_title[:70]})))
        long_cite = "Example, A. B., and C. D. Example-Longname, A Very Long Scholarly Title, Volume Two, University Press, 2001"
        self.assertTrue(text_regions_fit(CardSpec("source_excerpt", dict(GOOD["source_excerpt"], citation=long_cite))))
        too_long = CardSpec("section_break", {"title": "W" * 60})
        self.assertFalse(text_regions_fit(too_long), "a single unbreakable word wider than the card is refused, not clipped")

    def test_accented_text_renders_and_unsupported_scripts_are_refused(self):
        self.assertEqual(missing_glyphs("Enoc etíope ñ ¿¡ Hénoch Jubiläen ç", "serif"), [])
        render(CardSpec("statement", {"phrase": "¿Por qué la escondieron? Él ya estaba allí."}), TMP / "es.png")
        with self.assertRaises(CardError) as ctx:
            render(CardSpec("statement", {"phrase": "ሰላም ለኩልክሙ ዓለም"}), TMP / "geez.png")
        self.assertIn("cannot draw", str(ctx.exception))

    def test_highlight_is_drawn_behind_the_phrase(self):
        plain = render(CardSpec("statement", {"phrase": GOOD["statement"]["phrase"]}), TMP / "plain.png")
        lit = render(CardSpec("statement", dict(GOOD["statement"])), TMP / "lit.png")
        self.assertNotEqual(plain.read_bytes(), lit.read_bytes())


class ExistingGraphicsUntouched(unittest.TestCase):
    def test_other_styles_get_no_cards_and_graphics_rules_unchanged(self):
        from types import SimpleNamespace as NS

        from graphics.engine import style_graphics_rules

        self.assertEqual(style_graphics_rules(NS(style={"style_id": "premium_documentary"})), {})
        self.assertNotIn("big_numbers", style_graphics_rules(NS(style={"style_id": "enoch_template"})))
        self.assertTrue(style_graphics_rules(NS(style={"style_id": "book_of_enoch"})).get("big_numbers"))


if __name__ == "__main__":
    unittest.main()
