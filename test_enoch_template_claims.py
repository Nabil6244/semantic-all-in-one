"""Enoch Template, Phase 3: the claim ledger. Synthetic fixtures only -- these are NOT findings about real history.

Ten required conditions, each with the status and diagnostic it must get; plus: a passing ledger is never called proof,
nothing is filled in, the pack's watch-list stays open, and quotes/credentials reach a card only when backed.
"""

from __future__ import annotations

import copy
import unittest

from ancient_texts.claims import (check_ledger, check_wording, credential_for_card, ledger_from_dict, quote_for_card, report,
                                  sources_markdown, watch_list_as_claims)
from ancient_texts.issues import ValidationError
from ancient_texts.subjects import load_pack
from enoch_template_testutil import NoPaidCalls

SOURCES = [
    {"id": "ed1", "kind": "edition", "citation": "Synthetic Edition One (fixture)", "exists": "confirmed", "exists_checked_by": "fixture"},
    {"id": "ed2", "kind": "scholarship", "citation": "Synthetic Study Two (fixture)", "exists": "confirmed", "exists_checked_by": "fixture",
     "credential": "Professor of Synthetic Studies", "credential_locator": "p. ii"},
    {"id": "ghost", "kind": "scholarship", "citation": "A Study Nobody Can Find (fixture)", "exists": "not_found", "exists_checked_by": "catalogue"},
    {"id": "ed3", "kind": "scholarship", "citation": "Synthetic Study Three (fixture)", "exists": "confirmed", "exists_checked_by": "fixture",
     "credential": "Chair of Something"},
]
REVIEWED = {"state": "reviewed", "by": "fixture reviewer", "date": "2026-10-11", "basis": "read the cited pages"}


def claim(cid, status, support, **kw):
    return {"id": cid, "text": f"synthetic claim {cid}", "status": status, "support": support, **kw}


FIXTURES = {
    "supported": claim("C-001", "documented", [{"source_id": "ed1", "locator": "ch. 46", "relation": "direct"},
                                               {"source_id": "ed2", "locator": "p. 12", "relation": "partial"}], review=REVIEWED),
    "no_locator": claim("C-002", "documented", [{"source_id": "ed1", "locator": "", "relation": "direct"}]),
    "nonexistent_source": claim("C-003", "documented", [{"source_id": "ghost", "locator": "p. 4", "relation": "direct"}]),
    "exists_but_does_not_support": claim("C-004", "documented", [{"source_id": "ed1", "locator": "ch. 2", "relation": "context"}]),
    "conflicting_sources": claim("C-005", "documented", [{"source_id": "ed1", "locator": "ch. 3", "relation": "direct"},
                                                         {"source_id": "ed2", "locator": "p. 40", "relation": "contradicts"}]),
    "interpretation_as_fact": claim("C-006", "interpretation", [{"source_id": "ed2", "locator": "p. 7", "relation": "direct"}]),
    "unsupported_quote": claim("C-007", "documented", [{"source_id": "ed1", "locator": "ch. 9", "relation": "direct",
                                                        "quote": {"text": "words nobody checked", "edition": "", "verified": False}}]),
    "unsupported_credential": claim("C-008", "interpretation", [{"source_id": "ed3", "locator": "p. 1", "relation": "direct"}]),
    "reviewed_without_evidence": claim("C-009", "documented", [{"source_id": "ed1", "locator": "", "relation": "unchecked"}],
                                       review=REVIEWED),
    "disputed_qualified": claim("C-010", "disputed", [{"source_id": "ed2", "locator": "p. 88", "relation": "partial"}],
                                limitations="others read it differently"),
}


def ledger(*names):
    return ledger_from_dict({"sources": copy.deepcopy(SOURCES), "claims": [copy.deepcopy(FIXTURES[n]) for n in names]})


def issues_for(name):
    return [(i.code, i.severity) for i in check_ledger(ledger(name))]


class TenConditions(unittest.TestCase):
    def test_1_properly_supported_claim_has_no_failure(self):
        got = issues_for("supported")
        self.assertFalse([c for c, s in got if s == "hard"], got)
        self.assertNotIn(("unreviewed_claim", "review"), got)

    def test_2_source_without_locator(self):
        self.assertIn(("missing_locator", "hard"), issues_for("no_locator"))
        self.assertIn(("documented_without_support", "hard"), issues_for("no_locator"))

    def test_3_nonexistent_source(self):
        self.assertIn(("source_not_found", "hard"), issues_for("nonexistent_source"))

    def test_4_source_exists_but_does_not_support(self):
        got = issues_for("exists_but_does_not_support")
        self.assertIn(("source_does_not_support", "hard"), got)
        self.assertIn(("documented_without_support", "hard"), got)

    def test_5_conflicting_sources_are_kept_and_flagged(self):
        got = issues_for("conflicting_sources")
        self.assertIn(("conflicting_sources", "hard"), got)
        self.assertIn(("source_contradicts_claim", "hard"), got)

    def test_6_interpretation_stated_as_fact(self):
        lg = ledger("interpretation_as_fact")
        bad = check_wording(lg, "C-006", "This proves that no other text ever said it.", "en", "S-001")
        self.assertEqual([(i.code, i.severity) for i in bad], [("interpretation_stated_as_fact", "hard")])
        ok = check_wording(lg, "C-006", "According to one study, this may echo an older text.", "en", "S-001")
        self.assertEqual(ok, [])
        es = check_wording(lg, "C-006", "Esto demuestra que ningún otro texto lo dijo.", "es", "S-001")
        self.assertEqual([i.code for i in es], ["interpretation_stated_as_fact"])

    def test_7_unsupported_quote_never_reaches_a_card(self):
        lg = ledger("unsupported_quote")
        self.assertIn(("unverified_quote", "review"), [(i.code, i.severity) for i in check_ledger(lg)])
        self.assertIsNone(quote_for_card(lg, "C-007"))

    def test_8_unsupported_credential_is_not_shown(self):
        lg = ledger("unsupported_credential", "supported")
        self.assertIsNone(credential_for_card(lg, "ed3"), "a credential without a locator in its source is not shown")
        self.assertIsNone(credential_for_card(lg, "ghost"))
        self.assertEqual(credential_for_card(lg, "ed2"), "Professor of Synthetic Studies")

    def test_9_reviewed_without_evidence(self):
        self.assertIn(("reviewed_without_evidence", "hard"), issues_for("reviewed_without_evidence"))

    def test_10_disputed_claim_with_qualified_wording(self):
        lg = ledger("disputed_qualified")
        self.assertEqual(check_wording(lg, "C-010", "Some scholars argue that the passage may be later; others disagree.", "en"), [])
        self.assertEqual(check_wording(lg, "C-010", "Algunos estudiosos sostienen que podría ser un añadido.", "es"), [])
        unqualified = check_wording(lg, "C-010", "The passage is a later addition.", "en")
        self.assertEqual([(i.code, i.severity) for i in unqualified], [("needs_qualification", "hard")])
        self.assertIn(("disputed_claim", "review"), [(i.code, i.severity) for i in check_ledger(lg)])


class LedgerIsNotProof(unittest.TestCase):
    def test_review_state_and_evidence_status_stay_separate(self):
        lg = ledger("supported", "interpretation_as_fact")
        self.assertEqual(lg.claims["C-001"].status, "documented")
        self.assertEqual(lg.claims["C-001"].review.state, "reviewed")
        self.assertEqual(lg.claims["C-006"].review.state, "unreviewed")
        self.assertIn(("unreviewed_claim", "review"), [(i.code, i.severity) for i in check_ledger(lg)])

    def test_unchecked_sources_stay_unchecked(self):
        data = {"sources": [{"id": "s1", "kind": "edition", "citation": "X"}],
                "claims": [claim("C-020", "documented", [{"source_id": "s1", "locator": "p. 3", "relation": "direct"}])]}
        lg = ledger_from_dict(data)
        self.assertEqual(lg.sources["s1"].exists, "unchecked")
        self.assertIn("source_existence_unchecked", [i.code for i in check_ledger(lg)])

    def test_the_sheet_never_calls_anything_verified(self):
        md = sources_markdown(ledger(*FIXTURES))
        self.assertIn("not proof", md)
        self.assertIn("NO LOCATOR", md)
        self.assertNotIn("verified", md.lower().replace("not verified", "").replace("unverified", ""))

    def test_nothing_is_invented(self):
        lg = ledger("no_locator")
        self.assertEqual(lg.claims["C-002"].support[0].locator, "")
        self.assertEqual(lg.sources["ed1"].url, "")

    def test_schema_errors_are_actionable(self):
        bad = {"sources": [{"id": "s 1", "kind": "blog", "citation": ""}],
               "claims": [{"id": "7", "status": "probably", "text": "", "support": [{"source_id": "s1", "relation": "maybe"}],
                           "review": {"state": "approved"}, "sentence_ids": ["one"]}]}
        with self.assertRaises(ValidationError) as ctx:
            ledger_from_dict(bad)
        msg = str(ctx.exception)
        for needle in ("malformed id", "kind 'blog'", "missing 'citation'", "unknown status", "relation 'maybe'", "review state",
                       "malformed sentence id"):
            self.assertIn(needle, msg)

    def test_invalid_references_are_hard(self):
        data = {"sources": copy.deepcopy(SOURCES),
                "claims": [claim("C-030", "documented", [{"source_id": "nope", "locator": "p. 1", "relation": "direct"}],
                                 conflicts_with=["C-999"])]}
        got = [(i.code, i.severity) for i in check_ledger(ledger_from_dict(data))]
        self.assertIn(("invalid_source_reference", "hard"), got)
        self.assertIn(("invalid_claim_reference", "hard"), got)

    def test_report_groups_every_category(self):
        with NoPaidCalls() as guard:
            lg = ledger(*FIXTURES)
            issues = check_ledger(lg) + check_wording(lg, "C-006", "This proves it.", "en")
            r = report(issues)
        guard.assert_clean()
        for key in ("unsupported_claims", "missing_locators", "invalid_sources", "source_does_not_support", "conflicting_sources",
                    "unreviewed_claims", "wording_vs_evidence", "quotes_without_verified_text", "needs_careful_qualification"):
            self.assertTrue(r[key], key)

    def test_verified_quote_reaches_a_card_only_with_edition_locator_and_reviewer(self):
        data = {"sources": copy.deepcopy(SOURCES), "claims": [claim("C-040", "documented", [
            {"source_id": "ed1", "locator": "1 En 46:1", "relation": "direct",
             "quote": {"text": "And there I saw One", "edition": "Synthetic Edition One", "verified": True, "verified_by": "fixture"}}])]}
        lg = ledger_from_dict(data)
        self.assertEqual(quote_for_card(lg, "C-040")[0], "And there I saw One")

    def test_the_pack_watch_list_stays_open(self):
        items = watch_list_as_claims(load_pack("enoch").research_watch_list)
        self.assertEqual({i.severity for i in items}, {"review"})
        self.assertEqual(len(items), 6)


if __name__ == "__main__":
    unittest.main()
