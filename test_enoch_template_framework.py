"""Enoch Template, Phases 2 and 4: the topic-agnostic core (subject packs, language helpers) and the narrative framework
(roles, presets, the script map, structure checks). Everything is local and deterministic, under NoPaidCalls."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ancient_texts import language as L
from ancient_texts.claims import ledger_from_dict
from ancient_texts.framework import (PRESETS, build_script_map, check_structure, cue_intervals, evidence_sections)
from ancient_texts.issues import Issue, ValidationError
from ancient_texts.subjects import load_pack, pack_for_style, pack_from_dict
from enoch_template_testutil import NoPaidCalls

ROOT = Path(__file__).resolve().parent
ENOCH = json.loads((ROOT / "ancient_texts" / "packs" / "enoch.json").read_text(encoding="utf-8"))

JUBILEES = {  # a second, synthetic subject: proves nothing in the core assumes Enoch
    "pack_id": "jubilees_demo", "schema_version": 1, "subject": "The Book of Jubilees (demo)", "style_id": "enoch_template",
    "subject_terms": ["jubilees", "jubileos", "book of jubilees"], "document_terms": ["manuscript", "fragment", "scroll"],
    "place_terms": ["qumran", "ethiopia"], "scholars": [{"name": "Example Scholar", "aliases": [], "credential": None,
                                                          "credential_source_id": None}],
    "anchor_motifs": [{"id": "jubilees_fragment", "concept_terms": ["fragment", "scroll"], "query": "Jubilees Qumran fragment",
                       "kind": "document"}],
    "source_notes": [], "research_watch_list": [{"id": "J-01", "topic": "calendar", "prompt": "Check the calendar claim.",
                                                 "status": "to_verify"}],
}


def codes(issues):
    return [i.code for i in issues]


def sentence(i, text, role, **kw):
    return {"id": f"S-{i:03d}", "text": text, "role": role, **kw}


def script_and_map(sections: int, *, lang="en", contested=False, counter=True, resolve=True):
    """A synthetic script with a hook, provenance, `sections` evidence sections, an optional counterargument, a conclusion."""
    words = {
        "en": ("Why was this book kept for so long?", "The text survived in a few copies.", "The text describes a figure",
               "Some scholars read this as a later addition.", "So the question has an answer, within limits."),
        "es": ("¿Por qué se conservó este libro tanto tiempo?", "El texto sobrevivió en pocas copias.", "El texto describe una figura",
               "Algunos estudiosos lo leen como un añadido tardío.", "Así, la pregunta tiene respuesta, con límites."),
        "de": ("Warum wurde dieses Buch so lange bewahrt?", "Der Text ist in wenigen Abschriften erhalten.", "Der Text beschreibt eine Gestalt",
               "Einige Forscher halten das für einen späteren Zusatz.", "So hat die Frage eine Antwort, mit Grenzen."),
    }[lang]
    sents = [sentence(1, words[0], "hook", opens="Q1", non_factual="question", cue=True),
             sentence(2, words[1], "provenance", claim_ids=["C-001"])]
    n = 3
    for k in range(sections):
        sents.append(sentence(n, f"{words[2]} number {k + 1}.", "evidence", section=f"E{k + 1}",
                              claim_ids=["C-002" if contested else "C-001"], cue=k % 2 == 0))
        n += 1
    if counter:
        sents.append(sentence(n, words[3], "counterargument", claim_ids=["C-002"] if contested else ["C-001"]))
        n += 1
    sents.append(sentence(n, words[4], "conclusion", **({"resolves": "Q1"} if resolve else {}), non_factual="rhetorical"))
    script = " ".join(s["text"] for s in sents)
    return script, {"language": lang, "sentences": sents}


LEDGER = ledger_from_dict({
    "sources": [{"id": "ed1", "kind": "edition", "citation": "Edition 1 (synthetic)", "exists": "confirmed",
                 "exists_checked_by": "fixture"}],
    "claims": [{"id": "C-001", "text": "The text survived", "status": "documented",
                "support": [{"source_id": "ed1", "locator": "p. 1", "relation": "direct"}],
                "review": {"state": "reviewed", "by": "fixture", "basis": "p. 1"}},
               {"id": "C-002", "text": "A reading", "status": "disputed",
                "support": [{"source_id": "ed1", "locator": "p. 2", "relation": "partial"}]}],
})


class Phase2Core(unittest.TestCase):
    def test_enoch_pack_loads_through_the_framework(self):
        with NoPaidCalls() as guard:
            pack = load_pack("enoch")
        guard.assert_clean()
        self.assertEqual(pack.pack_id, "enoch")
        self.assertIs(pack_for_style("enoch_template").pack_id == "enoch", True)
        self.assertTrue(all(s.credential is None for s in pack.scholars))
        self.assertEqual({w.status for w in pack.research_watch_list}, {"to_verify"})

    def test_a_second_subject_pack_loads_without_enoch_assumptions(self):
        pack = pack_from_dict(copy.deepcopy(JUBILEES))
        self.assertEqual(pack.pack_id, "jubilees_demo")
        self.assertEqual(pack.scholar_for("as Example Scholar noted").name, "Example Scholar")
        import ast

        for f in ("subjects.py", "claims.py", "framework.py", "language.py", "plan.py", "cards.py", "qc.py", "audio.py", "issues.py"):
            tree = ast.parse((ROOT / "ancient_texts" / f).read_text(encoding="utf-8"))
            for node in ast.walk(tree):                     # code only: docstrings may name an example subject
                body = getattr(node, "body", None)
                if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                    body.pop(0)
            code = ast.unparse(tree).lower()
            self.assertNotIn("enoch", code, f"{f}: the core code names no subject")

    def test_invalid_packs_fail_with_every_actionable_problem(self):
        bad = copy.deepcopy(JUBILEES)
        bad["pack_id"] = "Bad Id"
        bad["subject_terms"] = ["Upper"]
        bad["scholars"] = [{"name": "X", "credential": "Professor", "credential_source_id": None}]
        bad["anchor_motifs"].append(dict(bad["anchor_motifs"][0]))
        bad["research_watch_list"][0]["status"] = "verified"
        with self.assertRaises(ValidationError) as ctx:
            pack_from_dict(bad)
        msg = str(ctx.exception)
        for needle in ("pack_id", "lowercase", "credential needs credential_source_id", "duplicate id", "open questions"):
            self.assertIn(needle, msg)
        with self.assertRaises(ValidationError):
            pack_from_dict({"pack_id": "x"})
        with self.assertRaises(ValidationError):
            load_pack(ROOT / "does_not_exist.json")

    def test_issue_rejects_unknown_severity(self):
        with self.assertRaises(ValueError):
            Issue("x", "fatal", "m")

    def test_deterministic_outputs(self):
        a = pack_from_dict(copy.deepcopy(ENOCH))
        b = pack_from_dict(copy.deepcopy(ENOCH))
        self.assertEqual(a, b)
        s1, m1 = script_and_map(3)
        self.assertEqual(build_script_map(s1, m1)[0], build_script_map(s1, m1)[0])

    def test_language_helpers_are_neutral(self):
        self.assertEqual(L.detect_language("El texto de la cueva es uno de los más antiguos y se conserva en Etiopía."), "es")
        self.assertEqual(L.detect_language("The text of the cave is one of the oldest and it was kept in Ethiopia."), "en")
        self.assertEqual(L.detect_language("xyz"), "und")
        self.assertEqual(L.split_sentences("¿Qué es? Es un libro. «Dijo esto.» Fin…"), ["¿Qué es?", "Es un libro.", "«Dijo esto.»", "Fin…"])
        self.assertEqual(L.sentence_hash("a  b"), L.sentence_hash(" a b "))


class Phase4Structure(unittest.TestCase):
    def check(self, sections, **kw):
        script, ann = script_and_map(sections, **{k: v for k, v in kw.items() if k in ("lang", "contested", "counter", "resolve")})
        smap, issues = build_script_map(script, ann, preset=kw.get("preset", "adaptive"))
        return smap, issues + check_structure(smap, LEDGER)

    def test_one_three_and_five_or_more_evidence_sections(self):
        for n in (1, 3, 5, 7):
            smap, issues = self.check(n)
            self.assertEqual(len(evidence_sections(smap)), n)
            self.assertNotIn("evidence_sections", codes(issues), f"{n} sections: no fixed count imposed by default")

    def test_the_reference_preset_is_optional_and_soft(self):
        _, issues = self.check(1, preset="reference_inspired")
        found = [i for i in issues if i.code == "evidence_sections"]
        self.assertEqual([i.severity for i in found], ["soft"])
        self.assertIn("reference_inspired", PRESETS)

    def test_a_major_dispute_requires_a_counterargument(self):
        _, issues = self.check(3, contested=True, counter=False)
        self.assertIn("missing_counterargument", codes(issues))
        self.assertEqual([i.severity for i in issues if i.code == "missing_counterargument"], ["hard"])
        _, issues = self.check(3, contested=True, counter=True)
        self.assertNotIn("missing_counterargument", codes(issues))

    def test_no_dispute_needs_no_counterargument(self):
        _, issues = self.check(3, contested=False, counter=False)
        self.assertNotIn("missing_counterargument", codes(issues))

    def test_disputed_wording_must_be_qualified_in_any_supported_language(self):
        for lang in ("en", "es", "de"):
            _, issues = self.check(2, lang=lang, contested=True)
            hard = [i for i in issues if i.code in ("needs_qualification", "interpretation_stated_as_fact")]
            self.assertTrue(hard, f"{lang}: evidence sentences link a disputed claim with no qualifier")

    def test_the_opening_question_must_be_resolved(self):
        _, issues = self.check(2, resolve=False)
        self.assertIn("unresolved_question", codes(issues))
        _, issues = self.check(2, resolve=True)
        self.assertNotIn("unresolved_question", codes(issues))

    def test_an_unsupported_factual_sentence_is_flagged(self):
        script, ann = script_and_map(2)
        script += " In 1947 three shepherds found seven jars."
        smap, issues = build_script_map(script, ann)
        issues += check_structure(smap, LEDGER)
        flagged = [i for i in issues if i.code in ("unlinked_factual_sentence", "unannotated_sentence")]
        self.assertTrue(flagged)

    def test_a_well_structured_script_is_not_rewritten(self):
        script, ann = script_and_map(3)
        smap, issues = build_script_map(script, ann)
        issues += check_structure(smap, LEDGER)
        self.assertEqual(smap.text(), L.normalize_text(script))
        self.assertEqual([i for i in issues if i.severity == "hard"], [])

    def test_language_is_never_hardcoded(self):
        for lang in ("en", "es", "de"):
            script, ann = script_and_map(2, lang=lang)
            ann.pop("language")
            smap, _ = build_script_map(script, ann)
            self.assertEqual(smap.language, lang)
        script, ann = script_and_map(2, contested=True)
        ann["language"] = "sw"
        smap, issues = build_script_map(script, ann)
        issues += check_structure(smap, LEDGER)
        self.assertIn("wording_unchecked_language", codes(issues), "an unlisted language becomes a review item, not a guess")

    def test_edited_script_and_bad_map_are_reported(self):
        script, ann = script_and_map(2)
        smap, issues = build_script_map(script.replace("survived", "lasted"), ann)
        self.assertIn("script_mismatch", codes(issues))
        bad = copy.deepcopy(ann)
        bad["sentences"][0]["role"] = "intro"
        with self.assertRaises(ValidationError):
            build_script_map(script, bad)
        smap, _ = build_script_map(script, None)
        self.assertEqual(codes(check_structure(smap, LEDGER)), ["no_script_map"])

    def test_curiosity_spacing_is_measured_not_enforced(self):
        script, ann = script_and_map(150)
        smap, _ = build_script_map(script, ann)
        self.assertTrue(cue_intervals(smap))
        for s in ann["sentences"]:
            s["cue"] = False
        smap, _ = build_script_map(script, ann)
        issues = check_structure(smap, LEDGER)
        self.assertEqual([i.severity for i in issues if i.code == "cue_spacing"], ["soft"])


if __name__ == "__main__":
    unittest.main()
