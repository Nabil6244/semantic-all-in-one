"""Enoch Template, Phase 1: the style and subject-pack data files (no production behaviour yet).

  * styles/enoch_template.json loads, appears in the style list the project-creation dropdown uses, and is never chosen by
    auto-detection;
  * it is Book of Enoch's data with exactly the intended differences (the copied figures, artwork searches and search terms
    behave as Book of Enoch's do), and styles/book_of_enoch.json stays byte-identical;
  * its AI ceiling is 0.12 and configurable in the file; the limit never turns a scene into AI;
  * ancient_texts/packs/enoch.json is data only: no stored credentials, nothing marked verified, research items "to_verify".
Everything runs under NoPaidCalls: loading and allocating a style makes no network, Flow or AI call.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from enoch_template_testutil import NoPaidCalls, normalized_sha256
from style_engine import resolve_style
from style_engine.loader import clear_loader_caches, load_style, style_choices

ROOT = Path(__file__).resolve().parent
STYLE_PATH = ROOT / "styles" / "enoch_template.json"
PACK_PATH = ROOT / "ancient_texts" / "packs" / "enoch.json"
BOOK_OF_ENOCH_SHA256 = "93e318447adbb417a4234012064f1ef844d7475cdd86d031481600f77385443a"

# Every value in which Enoch Template deliberately differs from Book of Enoch (specification v2, Phase 1). Anything else
# that differs is drift; anything here that stops differing is a lost decision.
INTENDED_DIFFERENCES = frozenset({
    "/id", "/name",
    "/identity/description", "/identity/tone", "/identity/best_for",
    "/visual/camera/intensity", "/visual/motion_rules/dramatic_push_on_evidence",
    "/visual/variety/avoid_repeated_archival_photo", "/visual/variety/min_unique_keys",
    "/pacing/hook", "/pacing/climax", "/pacing/transition_density",
    "/transitions/preferred", "/transitions/avoid",
    "/audio/ambience_intensity", "/audio/sfx_intensity", "/audio/music_intensity", "/audio/music_duck_db",
    "/hook/window_seconds",
    "/captions/style", "/captions/density",
    "/intelligence/preview_visual", "/intelligence/preview_pacing", "/intelligence/preview_audio",
    "/visual_roles/weights/atmosphere",
    "/search_guidance/prefer_terms", "/search_guidance/avoid_terms",
    "/selection_rules/max_ai_share",
    "/storytelling/narrative", "/storytelling/hook_strategy",
    "/graphics/numbers_first", "/graphics/big_numbers",
})


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _differences(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _differences(a.get(k), b.get(k), f"{path}/{k}")
        return out
    return [] if a == b else [path]


class StyleLoads(unittest.TestCase):
    def setUp(self):
        clear_loader_caches()

    def test_loads_with_its_own_identity(self):
        with NoPaidCalls() as guard:
            style = load_style("enoch_template")
        guard.assert_clean()
        self.assertIsNotNone(style)
        self.assertEqual((style.id, style.name), ("enoch_template", "Enoch Template"))
        self.assertGreaterEqual(style.version, 2)
        self.assertEqual(_json(STYLE_PATH)["id"], "enoch_template")

    def test_resolves_as_a_manual_style(self):
        resolved = resolve_style(mode="manual", style_id="enoch_template", script="")
        self.assertEqual(resolved.style.id, "enoch_template")

    def test_listed_for_project_creation(self):
        """project_picker.py builds its dropdown from style_choices(): label -> ("manual", style id)."""
        choices = dict((name, sid) for sid, name in style_choices())
        self.assertEqual(choices.get("Enoch Template"), "enoch_template")
        self.assertEqual(choices.get("Book of Enoch"), "book_of_enoch", "Book of Enoch is still offered next to it")
        self.assertEqual(len([sid for sid, _ in style_choices() if sid == "enoch_template"]), 1)


class NeverAutoDetected(unittest.TestCase):
    SCRIPTS = [
        "Enoch template. The Book of Enoch describes a figure seated beside the throne before creation. Scholars such as "
        "Collins and Nickelsburg compared it with Isaiah and the Gospels.",
        "El Libro de Enoc describe a una figura junto al trono. Los rollos del Mar Muerto y los manuscritos etíopes lo conservaron.",
        "A hidden ancient text, Ethiopic manuscripts, Qumran fragments and a Greek papyrus of Isaiah.",
    ]

    def test_no_detection_weights(self):
        from style_engine.detect import _style_weights_from_builtins

        self.assertEqual(load_style("enoch_template").intelligence.weights, {})
        self.assertNotIn("enoch_template", _style_weights_from_builtins())

    def test_detection_and_auto_mode_never_pick_it(self):
        from style_engine.detect import detect_style

        for text in self.SCRIPTS:
            self.assertNotEqual(detect_style(script=text)[0].id, "enoch_template", text[:40])
            resolved = resolve_style(mode="auto", script=text)
            self.assertNotEqual(resolved.style.id, "enoch_template", text[:40])


class BookOfEnochPreserved(unittest.TestCase):
    def test_book_of_enoch_is_byte_identical(self):
        self.assertEqual(normalized_sha256(ROOT / "styles" / "book_of_enoch.json"), BOOK_OF_ENOCH_SHA256)

    def test_the_differences_are_exactly_the_intended_ones(self):
        diff = set(_differences(_json(ROOT / "styles" / "book_of_enoch.json"), _json(STYLE_PATH)))
        self.assertEqual(sorted(diff - INTENDED_DIFFERENCES), [], "unintended difference from Book of Enoch")
        self.assertEqual(sorted(INTENDED_DIFFERENCES - diff), [], "an intended difference was lost")

    def test_search_terms_extend_book_of_enoch_and_keep_its_order(self):
        book, mine = load_style("book_of_enoch").search_guidance, load_style("enoch_template").search_guidance
        self.assertEqual(mine.prefer_terms[:len(book.prefer_terms)], book.prefer_terms)
        self.assertEqual(mine.avoid_terms[:len(book.avoid_terms)], book.avoid_terms)
        for t in ("kindle", "e-reader", "ebook", "paperback"):
            self.assertIn(t, mine.avoid_terms)


class CopiedDataBehavesLikeBookOfEnoch(unittest.TestCase):
    def test_figures_are_the_same_and_enrich_the_same_prompts(self):
        from style_engine.entities import enrich_plan
        from test_style_entities import plan

        book, mine = load_style("book_of_enoch").entities, load_style("enoch_template").entities
        self.assertEqual(mine, book)
        a, b = plan(), plan()
        self.assertEqual(enrich_plan(a, book), enrich_plan(b, mine))
        self.assertEqual([s.visual_description for s in a.scenes], [s.visual_description for s in b.scenes])

    def test_graphics_rules_are_names_and_plain_numbers_only(self):
        from graphics.engine import style_graphics_rules

        rules = style_graphics_rules(NS(style={"style_id": "enoch_template"}))
        self.assertTrue(rules.get("short_names") and rules.get("plain_numbers"))
        self.assertFalse(rules.get("big_numbers") or rules.get("numbers_first"), "no big centred number cards in this style")
        self.assertIn("Semjaza", rules["entity_names"])

    def test_candidate_gate_drops_avoided_subjects_and_modern_products(self):
        from style_engine.visual_selection import style_candidate_gate
        from test_style_search_terms import EnochCandidateGate

        cand = EnochCandidateGate().cand
        mine = resolve_style(mode="manual", style_id="enoch_template", script="")
        c = [cand("pexels", "Holy Quran page"), cand("openverse", "Book of Enoch on a Kindle e-reader"),
             cand("pixabay", "old book"), cand("openverse", "Ethiopic manuscript cover")]
        self.assertEqual([x.extra["alt"] for x in style_candidate_gate(c, mine)], ["Ethiopic manuscript cover"])

    def test_style_search_terms_match_book_of_enoch_on_its_fixture(self):
        from test_style_search_terms import plan
        from visual_allocation.allocator import _style_search_terms

        a, b = plan(), plan()
        na = _style_search_terms(a, resolve_style(mode="manual", style_id="book_of_enoch", script=""))
        nb = _style_search_terms(b, resolve_style(mode="manual", style_id="enoch_template", script=""))
        self.assertEqual(na, nb)
        self.assertEqual([(s.asset_type, s.search_queries) for s in a.scenes], [(s.asset_type, s.search_queries) for s in b.scenes])


class AIShareIsAConfigurableCeiling(unittest.TestCase):
    def setUp(self):
        from test_style_ai_limits import AI, allocate

        self.AI = AI
        with NoPaidCalls() as guard:
            self.plan, self.after = allocate("enoch_template")
            _, self.before = allocate("enoch_template", limits=False)
            _, self.book = allocate("book_of_enoch")
        guard.assert_clean()

    def test_ceiling_and_run_are_set_in_the_style_file(self):
        rules = load_style("enoch_template").selection_rules
        self.assertEqual((rules.max_ai_share, rules.max_ai_run), (0.12, 2))
        self.assertEqual(_json(STYLE_PATH)["selection_rules"]["max_ai_share"], 0.12, "the value lives in the file, not in code")

    def test_real_subjects_go_to_real_sources(self):
        from test_style_ai_limits import REAL

        for sid in REAL:
            self.assertNotIn(self.after[sid].asset_type, self.AI, self.after[sid].reason)

    def test_the_limit_never_creates_ai_work(self):
        for sid, d in self.after.items():
            if self.before[sid].asset_type not in self.AI:
                self.assertNotIn(d.asset_type, self.AI, f"scene {sid} became AI because of the style limits")

    def test_never_more_ai_than_book_of_enoch_on_the_same_script(self):
        count = lambda decisions: sum(1 for d in decisions.values() if d.asset_type in self.AI)  # noqa: E731
        self.assertLessEqual(count(self.after), count(self.book))

    def test_ai_leaves_only_for_a_real_source_or_a_named_artwork(self):
        import visual_allocation.allocator as A
        from test_style_ai_limits import REAL

        for sid, d in self.after.items():
            if self.before[sid].asset_type in self.AI and d.asset_type not in self.AI:
                self.assertTrue(sid in REAL or A.ARTWORK_REASON in d.reason, f"scene {sid}: {d.reason}")


class SubjectPack(unittest.TestCase):
    def setUp(self):
        self.pack = _json(PACK_PATH)

    def test_identity(self):
        self.assertEqual((self.pack["pack_id"], self.pack["style_id"], self.pack["schema_version"]), ("enoch", "enoch_template", 1))
        self.assertIsNotNone(load_style(self.pack["style_id"]))

    def test_data_only_no_figures_duplicated_here(self):
        self.assertNotIn("entities", self.pack, "figures live in the style file the style engine reads")
        self.assertFalse((ROOT / "ancient_texts" / "packs" / "__init__.py").exists())

    def test_no_credentials_or_sources_are_stored_or_invented(self):
        for s in self.pack["scholars"]:
            self.assertIsNone(s["credential"], s["name"])
            self.assertIsNone(s["credential_source_id"], s["name"])
            self.assertTrue(s["name"].strip())

    def test_research_items_are_questions_not_findings(self):
        items = self.pack["research_watch_list"]
        self.assertTrue(items)
        self.assertEqual({i["status"] for i in items}, {"to_verify"})
        self.assertEqual(len({i["id"] for i in items}), len(items))
        text = json.dumps(self.pack).lower()
        for word in ('"verified"', '"documented"', '"human_verified"'):
            self.assertNotIn(word, text, "nothing in the pack is marked as checked")

    def test_terms_are_lowercase_and_multilingual(self):
        for key in ("subject_terms", "document_terms", "place_terms"):
            self.assertTrue(all(t == t.lower() for t in self.pack[key]), key)
        self.assertIn("libro de enoc", self.pack["subject_terms"])
        self.assertIn("manuscrito", self.pack["document_terms"])

    def test_anchor_motifs_are_unique_search_seeds(self):
        ids = [m["id"] for m in self.pack["anchor_motifs"]]
        self.assertEqual(len(ids), len(set(ids)))
        for m in self.pack["anchor_motifs"]:
            self.assertTrue(m["query"].strip() and m["concept_terms"])
            self.assertIn(m["kind"], {"document", "artwork", "place"})


if __name__ == "__main__":
    unittest.main()
