"""Enoch Template visual balance: the six primary visual types and their precedence, the evidence relationship, the
configurable text-card targets, the fallback order (evidence -> explanatory graphic -> text card, never unrelated stock),
consecutive text cards, repeated imagery, missing assets, AI mislabelling, and planned vs actual mix kept apart."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ancient_texts import visual_mix as V
from ancient_texts.claims import ledger_from_dict
from ancient_texts.plan import SceneMeta, refine_plan
from ancient_texts.qc import load_profile
from ancient_texts.subjects import load_pack
from enoch_template_testutil import NoPaidCalls
from style_engine.loader import load_style
from test_enoch_template_plan import AI_ONLY, NO_ART, plan_from

STYLE, PACK = load_style("enoch_template"), load_pack("enoch")


def meta(n, kind="", card=None, **kw):
    return SceneMeta(scene=n, reason=kw.pop("reason", "names"), source_kind=kind, anchors=kw.pop("anchors", []), card=card, **kw)


def card(kind, **fields):
    return {"kind": kind, "fields": fields, "installed": True}


class Precedence(unittest.TestCase):
    def test_every_rule_in_order(self):
        cases = [
            (meta(1, "artwork"), {"ai_provenance": True}, "ai_reconstruction"),      # AI is never hidden by search words
            (meta(2, "ai"), {}, "ai_reconstruction"),
            (meta(3, "local", card("statement", phrase="x")), {}, "text_card"),
            (meta(4, "local", card("section_break", title="x")), {}, "text_card"),
            (meta(5, "map"), {}, "map_diagram"),
            (meta(6, "local", card("comparison")), {}, "map_diagram"),
            (meta(7, "local", card("source_excerpt", mode="summary")), {}, "map_diagram"),
            (meta(8, "artwork"), {}, "historical_artwork"),
            (meta(9, "document"), {}, "manuscript_document"),
            (meta(10, "local", card("framed_object", caption="x")), {}, "manuscript_document"),
            (meta(11, "real_world"), {}, "real_world_location"),
            (meta(12, "local"), {}, "real_world_location"),
            (meta(13, "ai", planned_card={"kind": "statement"}), {}, "unresolved"),       # a card that was never installed
            (meta(14, "document"), {"installed": False}, "unresolved"),
        ]
        for m, kw, want in cases:
            self.assertEqual(V.classify(m, **kw), want, m.scene)

    def test_reproducible_shares(self):
        metas = [meta(i, k) for i, k in enumerate(["document", "artwork", "map", "ai", "real_world"] * 4, 1)]
        a, b = V.planned_mix(metas), V.planned_mix(copy.deepcopy(metas))
        self.assertEqual(a["shares"], b["shares"])
        self.assertAlmostEqual(sum(a["shares"].values()), 1.0, places=3)


class EvidenceRelation(unittest.TestCase):
    def test_relations(self):
        status = {"C-001": "documented", "C-002": "disputed"}
        R = V.evidence_relation
        self.assertEqual(R(meta(1, "document"), "manuscript_document"), "direct_evidence")
        self.assertEqual(R(meta(10, "document", reason="context"), "manuscript_document"), "illustration",
                         "a document picture the narration does not name is illustration, not evidence")
        self.assertEqual(R(meta(2, "artwork"), "historical_artwork"), "illustration")
        self.assertEqual(R(meta(3, "ai"), "ai_reconstruction"), "reconstruction")
        self.assertEqual(R(meta(4, "local", card("statement"), claim_ids=["C-002"]), "text_card", status), "interpretation")
        self.assertEqual(R(meta(5, "local", card("statement"), claim_ids=["C-001"]), "text_card", status), "narration_text")
        self.assertEqual(R(meta(6, "local", card("source_excerpt", mode="quotation")), "map_diagram"), "direct_evidence")
        self.assertEqual(R(meta(7, "local", card("source_excerpt", mode="summary")), "map_diagram"), "illustration")
        self.assertEqual(R(meta(8, "real_world", reason="context"), "real_world_location"), "illustration")
        self.assertEqual(R(meta(9, "real_world", reason="locates"), "real_world_location"), "direct_evidence")


class Targets(unittest.TestCase):
    def codes(self, text_cards, total=20, targets=None):
        cats = ["text_card"] * text_cards + ["manuscript_document"] * (total - text_cards)
        return {i.code for i in V.evaluate_mix(cats, list(range(1, total + 1)), targets or V.DEFAULT_TARGETS, label="t")}

    def test_bands(self):
        band_codes = {"text_cards_above_target", "text_cards_above_warning", "text_cards_far_above_target"}
        self.assertFalse(band_codes & self.codes(3))                              # 15%: inside 15-20%
        self.assertFalse(band_codes & self.codes(4))                              # 20%: inside
        self.assertEqual(band_codes & self.codes(4, total=18), {"text_cards_above_target"})      # 22%
        self.assertEqual(band_codes & self.codes(5), {"text_cards_above_target"})                # 25%: the warning starts above
        self.assertEqual(band_codes & self.codes(11, total=40), {"text_cards_above_warning"})    # 27.5%
        self.assertEqual(band_codes & self.codes(7), {"text_cards_far_above_target"})            # 35%

    def test_findings_are_soft_never_hard(self):
        issues = V.evaluate_mix(["text_card"] * 10, list(range(10)), V.DEFAULT_TARGETS, label="t")
        self.assertTrue(issues)
        self.assertEqual({i.severity for i in issues}, {"soft"})

    def test_targets_are_configurable_from_the_profile(self):
        prof = load_profile("enoch_ref_01")
        self.assertEqual(V.load_targets(prof)["text_card"], {"target": [0.15, 0.2], "warn": [0.25, 0.3]})
        custom = V.load_targets({"visual_mix": {"text_card": {"target": [0.4, 0.5], "warn": [0.6, 0.7]}}})
        self.assertNotIn("text_cards_far_above_target", self.codes(7, targets=custom))

    def test_consecutive_text_cards(self):
        cats = ["manuscript_document", "text_card", "text_card", "map_diagram", "text_card", "text_card", "text_card"]
        found = [i for i in V.evaluate_mix(cats, list(range(1, 8)), V.DEFAULT_TARGETS, label="t") if i.code == "consecutive_text_cards"]
        self.assertEqual(len(found), 2)
        self.assertIn("stops changing in kind", found[1].message)


LEDGER = ledger_from_dict({
    "sources": [{"id": "jude", "kind": "primary", "citation": "The Letter of Jude", "exists": "unchecked"}],
    "claims": [{"id": "C-001", "text": "The Letter of Jude quotes a prophecy it attributes to Enoch.", "status": "documented",
                "support": [{"source_id": "jude", "locator": "1:14-15", "relation": "direct"}]},
               {"id": "C-002", "text": "Its exclusion is debated.", "status": "disputed", "support": []}],
})


class FallbackOrder(unittest.TestCase):
    def run_one(self, narration, *, ledger=None, smap=None, style=STYLE):
        p = plan_from([(narration, "image"), ("Light filled the hall.", "image")])
        with tempfile.TemporaryDirectory() as d, NoPaidCalls() as guard:
            r = refine_plan(p, style=style, pack=PACK, ledger=ledger, script_map=smap, images_dir=Path(d), ai_ceiling=0.0)
        guard.assert_clean()
        return p, r

    def test_existing_evidence_before_historical_art(self):
        p, r = self.run_one("The Watchers came down on Mount Hermon.")      # names a place AND matches a Blake artwork
        self.assertEqual(p.scenes[0].search_queries[0], "Mount Hermon", r.scenes[0].change)
        self.assertEqual(r.scenes[0].evidence, "direct_evidence")
        p, r = self.run_one("The Watchers came down in a storm.")          # no place: the artwork is next
        self.assertIn("Blake", p.scenes[0].search_queries[0])
        self.assertEqual(r.scenes[0].category, "historical_artwork")

    def test_explanatory_cited_card_before_a_text_card(self):
        from ancient_texts.framework import build_script_map

        text = "The Letter of Jude quotes a prophecy."
        smap, _ = build_script_map(text + " Light filled the hall.", {"sentences": [
            {"id": "S-001", "text": text, "role": "evidence", "claim_ids": ["C-001"]},
            {"id": "S-002", "text": "Light filled the hall.", "role": "conclusion", "non_factual": "rhetorical"}]})
        p, r = self.run_one(text, ledger=LEDGER, smap=smap, style=NO_ART)
        self.assertEqual(r.scenes[0].card["kind"], "source_excerpt")
        self.assertEqual(r.scenes[0].card["fields"]["mode"], "summary")
        self.assertEqual(r.scenes[0].card["fields"]["locator"], "1:14-15")
        self.assertEqual((r.scenes[0].category, r.scenes[0].evidence), ("map_diagram", "illustration"))
        p, r = self.run_one(text, style=NO_ART)                              # no ledger: the narration's own words
        self.assertEqual(r.scenes[0].card["kind"], "statement")
        self.assertEqual(r.scenes[0].category, "text_card")

    def test_never_unrelated_stock_to_fix_the_mix(self):
        p = plan_from([(t, "image") for t in AI_ONLY])
        with tempfile.TemporaryDirectory() as d:
            r = refine_plan(p, style=NO_ART, pack=PACK, images_dir=Path(d))
        self.assertFalse([s for s in p.scenes if s.asset_type.startswith("stock")])
        self.assertGreater(r.report["planned_mix"]["shares"]["text_card"], 0.30, "the shortage is reported, not hidden")
        self.assertIn("text_cards_far_above_target", {i.code for i in r.issues})


class IntegrationActualMix(unittest.TestCase):
    def test_actual_mix_reads_the_projects_ledger_and_provenance(self):
        from ancient_texts import integration
        from test_enoch_template_render import _project

        ws = _project(Path(tempfile.mkdtemp()), "enoch_template")
        st = integration.state_dir(ws)
        st.mkdir(parents=True)
        (st / "claims.json").write_text(json.dumps({"sources": [], "claims": [
            {"id": "C-002", "text": "debated", "status": "disputed", "support": []}]}))
        (st / "plan_report.json").write_text(json.dumps({"scenes": [
            {"scene": 1, "source_kind": "local", "reason": "emphasizes", "claim_ids": ["C-002"],
             "card": {"kind": "statement", "fields": {"phrase": "x"}, "installed": True}},
            {"scene": 2, "source_kind": "artwork", "reason": "illustrates", "claim_ids": []}]}))
        (st / "asset_provenance.json").write_text(json.dumps({"2": "flow_image"}))
        Image.new("RGB", (8, 8)).save(ws.assets_dir / "001.png")
        Image.new("RGB", (8, 8), (9, 9, 9)).save(ws.assets_dir / "002.png")
        a = integration.actual_visual_mix(ws)
        self.assertEqual([s["evidence"] for s in a["scenes_detail"]], ["interpretation", "reconstruction"])
        self.assertIn("ai_label_mismatch", {i["code"] for i in a["issues"]})
        self.assertIsNone(integration.actual_visual_mix(_project(Path(tempfile.mkdtemp()), "enoch_template")), "no plan: no mix")


class PlannedVersusActual(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        Image.new("RGB", (64, 36), (10, 20, 30)).save(self.d / "001.jpg")
        Image.new("RGB", (64, 36), (10, 20, 30)).save(self.d / "002.jpg")         # identical to scene 1
        Image.new("RGB", (64, 36), (90, 20, 30)).save(self.d / "003.jpg")         # an AI file planned as artwork
        Image.new("RGB", (64, 36), (90, 90, 30)).save(self.d / "005.png")         # not the card the plan installed
        self.metas = [meta(1, "document"), meta(2, "document"), meta(3, "artwork"), meta(4, "artwork"),
                      meta(5, "local", {**card("statement", phrase="x"), "sha256": "0" * 16})]

    def test_actual_mix_counts_only_what_exists(self):
        planned = V.planned_mix(self.metas)
        actual = V.actual_mix(self.d, self.metas, provenance={3: "flow_image"})
        self.assertEqual(planned["counts"]["unresolved"], 0)
        self.assertEqual(actual["counts"]["unresolved"], 1, "scene 4 has no file: never counted as a used visual")
        self.assertEqual(planned["counts"]["historical_artwork"], 2)
        self.assertEqual(actual["counts"]["historical_artwork"], 0)
        self.assertEqual(actual["counts"]["ai_reconstruction"], 1)
        codes = {(i["code"], i["severity"], i["ref"]) for i in actual["issues"]}
        self.assertIn(("missing_asset", "hard", "4"), codes)
        self.assertIn(("ai_label_mismatch", "hard", "3"), codes)
        self.assertIn(("repeated_imagery", "soft", "1"), codes)
        self.assertIn(("card_file_replaced", "review", "5"), codes)

    def test_provenance_declaration_and_manifest(self):
        (self.d / ".asset_manifest.json").write_text(json.dumps({"001": {"status": "complete", "source": "stock_image"}}))
        st = self.d / "state"
        st.mkdir()
        (st / "asset_provenance.json").write_text(json.dumps({"3": "ai_generated"}))
        prov = V.load_provenance(self.d, st)
        self.assertEqual(prov, {1: "stock_image", 3: "ai_generated"})

    def test_planned_repeats_and_untied_documents(self):
        p = plan_from([("The reasons are still debated.", "stock_image"), ("Ethiopic manuscripts kept it.", "stock_image"),
                       ("Again, the reasons are debated.", "stock_image")], default_query="old printed Bible page")
        p.scenes[1].search_queries = ["Ethiopic manuscript"]
        r = refine_plan(p, style=STYLE, pack=PACK)
        self.assertEqual(r.scenes[0].evidence, "illustration")
        self.assertEqual(r.scenes[1].evidence, "direct_evidence")
        self.assertIn("repeated_imagery", {i.code for i in r.issues})

    def test_refine_report_carries_the_planned_mix(self):
        p = plan_from([("Ethiopic manuscripts kept the book alive.", "stock_image"), ("Light filled the hall.", "image")])
        r = refine_plan(p, style=STYLE, pack=PACK)
        mix = r.report["planned_mix"]
        self.assertEqual(set(mix), {"counts", "shares", "evidence_counts"})
        self.assertEqual(sum(mix["counts"].values()), 2)
        self.assertTrue(all(m.category and m.evidence for m in r.scenes))


if __name__ == "__main__":
    unittest.main()
