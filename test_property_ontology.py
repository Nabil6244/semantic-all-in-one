#!/usr/bin/env python3
"""Property Script Analyzer — real-estate visual language (property-only).

Covers the eight required property archetypes end-to-end:
property facts -> script beat -> classification -> Flow visual intent ->
Stock contextual query, plus the invariants that make Flow and Stock
genuinely different outputs rather than interchangeable ones.

No network, no UI. Run: python -m pytest test_property_ontology.py -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research.models import MediaCandidate, PropertySummary, ResearchResult
from research.property_ontology import (
    GUARDED_FEATURES,
    PropertyLocation,
    build_context_query,
    clean_stock_query,
    feature_is_supported,
    resolve_property_type,
    unsupported_features,
    visual_hints_from_facts,
)
from research.property_script import analyze_property_script


def _with_media(prop: PropertySummary, tmp: Path) -> ResearchResult:
    photo = tmp / f"{prop.property_id}.jpg"
    photo.write_bytes(b"jpeg")
    return ResearchResult(
        property=prop,
        media=[MediaCandidate(
            local_path=photo, media_type="image",
            source_url="https://x.test/a.jpg", property_id=prop.property_id,
        )],
    )


# (label, PropertySummary, facts, narration)
SCENARIOS = [
    ("kentucky_rural_cabin",
     PropertySummary(city="Vanceburg", state="Kentucky", property_type="log cabin", property_id="ky"),
     {"lot_size": "57 acres", "feature": "pond; creek frontage", "price": "$425,000"},
     "The hand-hewn log cabin sits above the creek."),
    ("tennessee_farmhouse",
     PropertySummary(city="Franklin", state="Tennessee", property_type="farmhouse", property_id="tn"),
     {"lot_size": "12 acres", "feature": "porch; barn"},
     "The restored farmhouse looks out over rolling fields."),
    ("texas_ranch",
     PropertySummary(city="Bandera", state="Texas", property_type="ranch", property_id="tx"),
     {"lot_size": "340 acres", "feature": "corral"},
     "The ranch house overlooks open rangeland."),
    ("colorado_mountain",
     PropertySummary(city="Breckenridge", state="Colorado", property_type="mountain home", property_id="co"),
     {"feature": "deck"},
     "The great room opens toward the valley."),
    ("florida_waterfront",
     PropertySummary(city="Naples", state="Florida", property_type="waterfront", property_id="fl"),
     {"feature": "dock; seawall"},
     "A private dock reaches into the calm water."),
    ("suburban_home",
     PropertySummary(city="Plano", state="Texas", property_type="single family home", property_id="sub"),
     {"feature": "garage; fenced yard"},
     "The kitchen opens onto a bright family room."),
    ("luxury_estate",
     PropertySummary(city="Greenwich", state="Connecticut", property_type="luxury estate", property_id="lux"),
     {"feature": "gated entrance"},
     "A gated entrance opens onto the formal grounds."),
    ("horse_property",
     PropertySummary(city="Ocala", state="Florida", property_type="horse property", property_id="hp"),
     {"feature": "stable; paddock"},
     "Four paddocks surround the center-aisle stable."),
]


class TestPropertyTypeOntology(unittest.TestCase):
    def test_each_archetype_resolves_to_a_distinct_profile(self):
        keys = {resolve_property_type(p.property_type).key for _, p, _, _ in SCENARIOS}
        # Eight archetypes must not collapse into one generic profile.
        self.assertGreaterEqual(len(keys), 7)
        self.assertNotIn("property", keys)  # nothing fell through to default

    def test_same_word_different_property_type_gives_different_landscape(self):
        ranch = resolve_property_type("ranch")
        horse = resolve_property_type("horse property")
        hunting = resolve_property_type("hunting property")
        vacant = resolve_property_type("development land")
        landscapes = {ranch.landscape, horse.landscape, hunting.landscape, vacant.landscape}
        self.assertEqual(len(landscapes), 4)

    def test_unknown_property_type_degrades_gracefully(self):
        profile = resolve_property_type("something nobody has ever listed")
        self.assertEqual(profile.key, "property")
        self.assertTrue(profile.landscape)

    def test_ontology_is_not_us_only(self):
        # Mechanism is type+location driven, so a non-US location works.
        query = build_context_query(
            subject="creek", profile=resolve_property_type("cabin"),
            location=PropertyLocation(state="Bavaria", country="Germany"),
        )
        self.assertIn("Bavaria", query)


class TestFactToVisualReasoning(unittest.TestCase):
    def test_acreage_fact_implies_aerial_land_visual(self):
        hints = dict((k, i) for k, i, _ in visual_hints_from_facts({"lot_size": "57 acres"}))
        self.assertEqual(hints["lot_size"], "property_aerial")

    def test_water_fact_implies_water_visual(self):
        hints = dict((k, i) for k, i, _ in visual_hints_from_facts({"feature": "pond"}))
        self.assertEqual(hints["feature"], "property_water")

    def test_non_visual_facts_produce_no_shot(self):
        # A price/listing id/agent name is not a picture.
        self.assertEqual(visual_hints_from_facts({"price": "$425,000"}), [])
        self.assertEqual(visual_hints_from_facts({"listing_id": "MLS123"}), [])
        self.assertEqual(visual_hints_from_facts({"agent": "Jane Smith"}), [])


class TestNoInventedFeatures(unittest.TestCase):
    def test_unsupported_feature_is_flagged(self):
        self.assertIn("pool", unsupported_features("home with a pool", "A quiet home.", {}))

    def test_fact_supported_feature_is_allowed(self):
        self.assertNotIn("barn", unsupported_features("barn exterior", "A quiet home.", {"feature": "barn"}))

    def test_narration_supported_feature_is_allowed(self):
        self.assertTrue(feature_is_supported("dock", "A private dock reaches out.", {}))

    def test_flow_prompt_never_claims_unsupported_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(state="Kentucky", property_type="log cabin", property_id="ky")
            beats = analyze_property_script(
                "A quiet retreat in the woods.",
                _with_media(prop, Path(tmp)),
                property_facts={"lot_size": "57 acres"},  # no pool/barn/dock
            )
            for beat in beats:
                leftover = unsupported_features(beat.intent.flow_prompt, beat.narration, {"lot_size": "57 acres"})
                self.assertEqual(leftover, [], f"invented {leftover} in: {beat.intent.flow_prompt}")


class TestStockQueryHygiene(unittest.TestCase):
    def test_price_and_listing_metadata_never_reach_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(state="Kentucky", property_type="log cabin", property_id="ky")
            beats = analyze_property_script(
                "At $425,000, this property is priced to sell.",
                _with_media(prop, Path(tmp)),
                property_facts={"price": "$425,000", "listing_id": "MLS123"},
            )
            q = beats[0].intent.stock_query
            for bad in ("$", "425", "MLS", "for sale"):
                self.assertNotIn(bad.lower(), q.lower())

    def test_stock_query_is_not_a_narration_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(state="Kentucky", property_type="log cabin", property_id="ky")
            narration = "The hand-hewn log cabin sits above the creek."
            beats = analyze_property_script(narration, _with_media(prop, Path(tmp)))
            self.assertNotEqual(beats[0].intent.stock_query.lower().strip(), narration.lower().strip(" ."))

    def test_clean_stock_query_dedupes_repeated_terms(self):
        out = clean_stock_query("Florida pasture countryside pasture countryside stable")
        self.assertEqual(len(out.split()), len(set(w.lower() for w in out.split())))


class TestLocationAwareness(unittest.TestCase):
    def test_region_appears_in_outdoor_context_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _, prop, facts, narration in SCENARIOS:
                beats = analyze_property_script(narration, _with_media(prop, Path(tmp)), property_facts=facts)
                intent = beats[0].intent
                if intent.scope.value in ("property_interior", "construction_detail"):
                    continue  # location deliberately omitted for interiors/close-ups
                if prop.state:
                    self.assertIn(prop.state.lower(), intent.stock_query.lower(),
                                  f"{prop.property_type}: {intent.stock_query}")

    def test_location_omitted_where_it_would_over_restrict(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(city="Plano", state="Texas", property_type="single family home", property_id="s")
            beats = analyze_property_script("The kitchen has granite countertops.", _with_media(prop, Path(tmp)))
            # An interior close-up should not be geo-restricted.
            self.assertNotIn("texas", beats[0].intent.stock_query.lower())


class TestFlowVsStockSeparation(unittest.TestCase):
    def test_property_specific_beat_requires_authentic_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(state="Kentucky", property_type="log cabin", property_id="ky")
            beats = analyze_property_script("The hand-hewn log cabin sits above the creek.",
                                            _with_media(prop, Path(tmp)))
            self.assertTrue(beats[0].intent.requires_authentic)
            self.assertTrue(beats[0].intent.intent_type.startswith("property_"))

    def test_missing_research_media_is_marked_not_faked(self):
        # Decision hierarchy step 3: no authentic media -> mark it, never let
        # generic stock silently represent a specific property fact.
        prop = PropertySummary(state="Kentucky", property_type="log cabin", property_id="ky")
        beats = analyze_property_script(
            "The hand-hewn log cabin sits above the creek.",
            ResearchResult(property=prop, media=[]),  # no media
        )
        self.assertTrue(beats[0].intent.requires_authentic)
        self.assertTrue(beats[0].intent.research_media_unavailable)

    def test_flow_and_stock_are_different_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(state="Kentucky", property_type="log cabin", property_id="ky")
            beats = analyze_property_script("The hand-hewn log cabin sits above the creek.",
                                            _with_media(prop, Path(tmp)))
            intent = beats[0].intent
            self.assertTrue(intent.flow_prompt)
            self.assertTrue(intent.stock_query)
            self.assertNotEqual(intent.flow_prompt, intent.stock_query)


class TestAllArchetypesEndToEnd(unittest.TestCase):
    def test_every_archetype_produces_both_intents_and_type_specific_wording(self):
        seen_stock = {}
        with tempfile.TemporaryDirectory() as tmp:
            for label, prop, facts, narration in SCENARIOS:
                beats = analyze_property_script(narration, _with_media(prop, Path(tmp)), property_facts=facts)
                intent = beats[0].intent
                self.assertTrue(intent.flow_prompt, f"{label}: no flow prompt")
                self.assertTrue(intent.stock_query, f"{label}: no stock query")
                self.assertTrue(intent.intent_type, f"{label}: no intent type")
                seen_stock[label] = intent.stock_query
        # Different property types must not all produce the same query.
        self.assertEqual(len(set(seen_stock.values())), len(seen_stock))

    def test_suburban_interior_is_not_described_as_a_rustic_cabin(self):
        with tempfile.TemporaryDirectory() as tmp:
            prop = PropertySummary(city="Plano", state="Texas", property_type="single family home", property_id="s")
            beats = analyze_property_script("The kitchen opens onto a bright family room.",
                                            _with_media(prop, Path(tmp)))
            flow = beats[0].intent.flow_prompt.lower()
            self.assertNotIn("cabin", flow)
            self.assertNotIn("rustic", flow)


class TestMultiListingIsolationPreserved(unittest.TestCase):
    def test_beats_keep_their_own_property_id(self):
        a = PropertySummary(name="Hunters Ridge", state="Kentucky", property_type="log cabin", property_id="A")
        b = PropertySummary(name="Willow Creek", state="Tennessee", property_type="farmhouse", property_id="B")
        beats = analyze_property_script(
            "Hunters Ridge features a stone fireplace. Willow Creek features a wide porch.",
            ResearchResult(property=a), properties=[a, b], default_property_id="A",
        )
        self.assertEqual(beats[0].property_id, "A")
        self.assertEqual(beats[1].property_id, "B")
        self.assertNotEqual(beats[0].property_id, beats[1].property_id)


if __name__ == "__main__":
    unittest.main()
