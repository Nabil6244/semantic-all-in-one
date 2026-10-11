"""Enoch Template, long form: synthetic 12-, 15- and 40-minute scripts go through the script map, the structure checks and
the refine pass (cards installed) within a time budget, with no fixed scene count, deterministic order, no duplicate or
missing scene, and the AI ceiling reported honestly. Planning and validation only (no render, no network)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from ancient_texts.claims import ledger_from_dict
from ancient_texts.framework import build_script_map, check_structure, evidence_sections
from ancient_texts.plan import refine_plan
from ancient_texts.subjects import load_pack
from enoch_template_testutil import NoPaidCalls
from style_engine.loader import load_style
from test_enoch_template_plan import MIXED, plan_from

WPM = 130
LEDGER = ledger_from_dict({
    "sources": [{"id": "ed1", "kind": "edition", "citation": "Synthetic edition", "exists": "confirmed", "exists_checked_by": "fixture"}],
    "claims": [{"id": "C-001", "text": "x", "status": "documented", "support": [{"source_id": "ed1", "locator": "p. 1", "relation": "direct"}],
                "review": {"state": "reviewed", "by": "fixture", "basis": "p. 1"}}],
})


def long_script(minutes: float):
    target = int(minutes * WPM)
    sents, words, n, sec = [], 0, 1, 0
    sents.append({"id": "S-001", "text": "Why did this book survive when so many others were lost?", "role": "hook", "opens": "Q1",
                  "non_factual": "question", "cue": True})
    n = 2
    while words < target:
        sec += 1
        for k in range(6):
            base = MIXED[(sec * 6 + k) % len(MIXED)][0]
            text = base if k else f"{base[:-1]} in section {sec}."
            sents.append({"id": f"S-{n:03d}", "text": text, "role": "evidence", "section": f"E{sec}", "claim_ids": ["C-001"],
                          "cue": k == 0})
            words += len(text.split())
            n += 1
    sents.append({"id": f"S-{n:03d}", "text": "Some scholars read the evidence differently.", "role": "counterargument",
                  "claim_ids": ["C-001"]})
    sents.append({"id": f"S-{n + 1:03d}", "text": "So the question has an answer, within limits.", "role": "conclusion",
                  "resolves": "Q1", "non_factual": "rhetorical"})
    return " ".join(s["text"] for s in sents), {"language": "en", "sentences": sents}, sec


class LongForm(unittest.TestCase):
    def run_minutes(self, minutes: float, budget_s: float):
        script, ann, sections = long_script(minutes)
        rows = []
        for s in ann["sentences"]:
            at = "image" if len(rows) % 3 == 0 else "stock_image"
            rows.append((s["text"], at))
        plan = plan_from(rows, default_query="old manuscript")
        t0 = time.perf_counter()
        with NoPaidCalls() as guard, tempfile.TemporaryDirectory() as d:
            smap, issues = build_script_map(script, ann)
            issues += check_structure(smap, LEDGER)
            result = refine_plan(plan, style=load_style("enoch_template"), pack=load_pack("enoch"), script_map=smap, images_dir=Path(d))
        guard.assert_clean()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, budget_s, f"{minutes} min plan took {elapsed:.1f}s")
        self.assertEqual(len(evidence_sections(smap)), sections, "no fixed section count")
        ids = [m.scene for m in result.scenes]
        self.assertEqual(ids, list(range(1, len(rows) + 1)), "deterministic order, nothing duplicated or missing")
        rep = result.report
        self.assertEqual(rep["eligible_visual_scenes"], len(rows))
        self.assertEqual(rep["ai_ceiling_met"], rep["ai_scenes"] <= rep["ai_allowed"])
        self.assertLessEqual(rep["max_ai_run_observed"], 2)
        self.assertFalse([i for i in issues if i.severity == "hard"], [i.message for i in issues if i.severity == "hard"][:3])
        return rep, elapsed

    def test_12_minutes(self):
        rep, _ = self.run_minutes(12, 120)
        self.assertGreater(rep["eligible_visual_scenes"], 150)

    def test_15_minutes(self):
        rep, _ = self.run_minutes(15, 150)
        self.assertTrue(rep["ai_ceiling_met"], rep)

    def test_40_minutes(self):
        rep, _ = self.run_minutes(40, 400)
        self.assertGreater(rep["eligible_visual_scenes"], 500)


if __name__ == "__main__":
    unittest.main()
