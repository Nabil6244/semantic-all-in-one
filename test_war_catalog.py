"""War catalog, provenance and registry: offline, deterministic."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.war import catalog as C
from cinematic_explainer.war import provenance as P
from cinematic_explainer.war import registry as R


def _ids(matches):
    return [m.entry["id"] for m in matches if m.entry]


class EquipmentTests(unittest.TestCase):
    def test_specific_alias_exact(self):
        m = C.find_equipment("The T-72 was filmed near the river.")
        self.assertEqual(_ids(m), ["t-72"])
        self.assertEqual(m[0].confidence, "exact")

    def test_variants_and_spellings(self):
        for s in ("a Bayraktar TB2 flew", "the TB-2 drone", "Bayrakhtar footage", "BAYRAKTAR"):
            self.assertIn("bayraktar-tb2", _ids(C.find_equipment(s)), s)

    def test_model_suffix_matches_base(self):
        self.assertIn("t-72", _ids(C.find_equipment("a T-72B3 and a T72")))
        self.assertIn("m1-abrams", _ids(C.find_equipment("an M1A2 tank")))

    def test_word_boundaries(self):
        self.assertEqual(_ids(C.find_equipment("The grading of the Gradient was poor")), [])
        self.assertEqual(_ids(C.find_equipment("Tor-M2 and Tory leaders")), ["tor-m2"])

    def test_generic_tank_is_class_level_only(self):
        m = C.find_equipment("A tank crossed the bridge.")
        self.assertEqual(len(m), 1)
        self.assertEqual((m[0].entry, m[0].confidence, m[0].class_id), (None, "generic", "tank"))
        m = C.find_equipment("a missile hit the depot")
        self.assertTrue(all(x.entry is None for x in m))

    def test_specific_suppresses_same_class_generic(self):
        m = C.find_equipment("The Leopard 2 tank advanced.")
        self.assertEqual(_ids(m), ["leopard-2"])
        self.assertTrue(all(x.confidence != "generic" for x in m))

    def test_ambiguity_is_flagged_not_resolved(self):
        entries, generic = C._equipment()
        # build a temporary duplicate alias scenario through the matcher helper
        owners = [e["id"] for e in entries if "Bear" in e["aliases"]]
        self.assertEqual(owners, ["tu-95ms"])
        sample = [{"id": "a", "name": "Alpha", "aliases": ["Dupe"]}, {"id": "b", "name": "Beta", "aliases": ["Dupe"]}]
        C._compiled.cache_clear()
        orig = C._entries
        try:
            C._entries = lambda name: sample  # type: ignore[assignment]
            m = C._find("figures", "the Dupe case")
            self.assertEqual({x.confidence for x in m}, {"ambiguous"})
            self.assertEqual(len(m), 2)
        finally:
            C._entries = orig  # type: ignore[assignment]
            C._compiled.cache_clear()

    def test_cyrillic_and_diacritics(self):
        self.assertIn("t-72", _ids(C.find_equipment("танк Т-72 на дороге")))
        self.assertEqual(C.normalise("Erdoğan"), "erdogan")

    def test_data_integrity(self):
        entries, generic = C._equipment()
        ids = [e["id"] for e in entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(entries), 40)
        for e in entries:
            self.assertIn(e["class"], C.EQUIPMENT_CLASSES, e["id"])
            self.assertLessEqual(len(e["specs"]), 3, e["id"])
            for s in e["specs"]:
                self.assertTrue(s.get("source"), f"{e['id']} spec without source")
                self.assertEqual(s.get("status"), "attributed")
            for la in e["look_alikes"]:
                self.assertIn(la, ids, f"{e['id']} look-alike {la}")
        self.assertTrue(set(generic) <= set(C.EQUIPMENT_CLASSES))
        classes_used = {e["class"] for e in entries}
        for c in ("tank", "ifv", "artillery", "rocket_artillery", "missile_ballistic", "missile_cruise", "air_defense", "drone",
                  "fighter", "helicopter", "bomber", "ship", "radar", "ew", "logistics"):
            self.assertIn(c, classes_used)

    def test_card_params_only_state_sourced_specs(self):
        p = C.equipment_card_params(C.get_equipment("t-72"))
        self.assertEqual(p["status"], "attributed")
        self.assertTrue(all("value" in s for s in p["specs"]))


class PlaceFigureTests(unittest.TestCase):
    def test_places_sane_coordinates(self):
        places = C._entries("places.json")
        self.assertGreaterEqual(len(places), 40)
        for p in places:
            self.assertTrue(20 <= p["lat"] <= 80 and -20 <= p["lon"] <= 80, p["id"])

    def test_place_aliases(self):
        for s in ("fighting in Kiev", "Київ", "Kyiv"):
            self.assertEqual(_ids(C.find_place(s)), ["kyiv"], s)
        self.assertIn("donbas", _ids(C.find_place("the Donbass front")))

    def test_acronym_is_case_sensitive(self):
        self.assertEqual(_ids(C.find_institution("the UN said")), ["un"])
        self.assertEqual(_ids(C.find_institution("an un related thing")), [])

    def test_figures_no_portraits_no_quotes(self):
        figs = C._entries("figures.json")
        for f in figs:
            self.assertIsNone(f["portrait"])
            self.assertNotIn("quote", f)
        self.assertEqual(_ids(C.find_figure("Gerasimov said it")), ["gerasimov"])

    def test_every_figure_role_either_dated_or_flagged(self):
        for f in C._entries("figures.json"):
            self.assertTrue(f["verify_role"] or any(ch.isdigit() for ch in f["role"]), f["id"])


class ProvenanceTests(unittest.TestCase):
    RECORDS = {
        "pexels": {"source": "stock", "provider": "pexels", "provider_asset_id": "123", "author": "A Person", "source_url": "https://www.pexels.com/video/123/", "type": "video"},
        "pixabay": {"source": "stock", "provider": "pixabay", "provider_asset_id": "9", "author": "Pix", "source_url": "https://pixabay.com/videos/9/", "type": "video"},
        "youtube": {"source": "youtube_video", "provider": "youtube", "provider_asset_id": "abc", "channel": "Some Channel", "source_url": "https://youtu.be/abc",
                    "video_title": "Clip", "license": "Standard YouTube License", "type": "video"},
        "openverse": {"source": "stock", "provider": "openverse", "provider_asset_id": "o1", "author": "Someone", "source_url": "https://openverse.org/image/o1", "type": "image"},
    }

    def test_never_confirmed(self):
        for name, rec in self.RECORDS.items():
            p = P.from_manifest_record(rec)
            self.assertNotEqual(p.status, "confirmed", name)
            self.assertFalse(P.usable_as_evidence(P.from_manifest_record({})), name)

    def test_licence_unknown_unless_present(self):
        self.assertEqual(P.from_manifest_record(self.RECORDS["pexels"]).licence, "unknown")
        self.assertEqual(P.from_manifest_record(self.RECORDS["openverse"]).licence, "unknown")
        self.assertEqual(P.from_manifest_record(self.RECORDS["youtube"]).licence, "Standard YouTube License")

    def test_attributed_only_with_author_and_url(self):
        self.assertEqual(P.from_manifest_record(self.RECORDS["pexels"]).status, "attributed")
        self.assertEqual(P.from_manifest_record({"provider": "pexels"}).status, "unverified")
        self.assertEqual(P.from_manifest_record({}).status, "unverified")

    def test_dates_are_not_invented(self):
        p = P.from_manifest_record(self.RECORDS["youtube"])
        self.assertEqual((p.event_date, p.captured_date, p.published_date, p.location), ("", "", "", ""))

    def test_flags_and_labels(self):
        p = P.Provenance(status="confirmed")
        self.assertTrue(P.usable_as_evidence(p))
        p.recycled = True
        self.assertFalse(P.usable_as_evidence(p))
        self.assertEqual(P.requires_label(p), "FILE FOOTAGE")
        self.assertEqual(P.requires_label(P.Provenance(status="illustrative")), "ILLUSTRATIVE")
        self.assertFalse(P.usable_as_evidence(P.Provenance(status="unverified")))

    def test_credits_skip_unknowns_and_dupes(self):
        a = P.from_manifest_record(self.RECORDS["pexels"])
        lines = P.credits_lines([a, a, P.Provenance(), P.from_manifest_record(self.RECORDS["youtube"])])
        self.assertEqual(len(lines), 2)
        self.assertIn("A Person", lines[0])

    def test_roundtrip_dict(self):
        a = P.from_manifest_record(self.RECORDS["youtube"])
        self.assertEqual(P.Provenance.from_dict(a.to_dict()), a)


class RegistryTests(unittest.TestCase):
    def test_roundtrip_and_rename_stable_key(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "clip.mp4"
            f.write_bytes(b"x" * 5000)
            reg = R.Registry(Path(td) / "reg.json")
            key = reg.put(f, {"status": "attributed"})
            g = Path(td) / "renamed" / "other.mp4"
            g.parent.mkdir()
            g.write_bytes(f.read_bytes())
            self.assertEqual(R.content_key(g), key)
            self.assertEqual(reg.get(g)["status"], "attributed")
            reg.update(g, caveats=["x"])
            self.assertEqual(reg.get(f)["caveats"], ["x"])
            h = Path(td) / "different.mp4"
            h.write_bytes(b"y" * 5000)
            self.assertIsNone(reg.get(h))

    def test_corrupt_file_is_empty_and_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "reg.json"
            path.write_text("{ not json", encoding="utf-8")
            f = Path(td) / "a.bin"
            f.write_bytes(b"1")
            reg = R.Registry(path)
            self.assertIsNone(reg.get(f))
            reg.put(f, {"k": 1})
            self.assertEqual(reg.get(f), {"k": 1})
            self.assertEqual(json.loads(path.read_text())["schema"], R.SCHEMA_VERSION)

    def test_wrong_schema_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "reg.json"
            path.write_text(json.dumps({"schema": 99, "assets": {"a" * 24: {"x": 1}}}), encoding="utf-8")
            self.assertIsNone(R.Registry(path).get("a" * 24))

    def test_missing_file_returns_none(self):
        self.assertIsNone(R.content_key("/no/such/file.mp4"))
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(R.Registry(Path(td) / "r.json").put("/no/such/file.mp4", {}))

    def test_all_cards_has_phase1_cards_without_other_modules(self):
        cards = R.all_cards()
        for k in ("kicker", "source", "number", "list", "portrait", "shot_head"):
            self.assertIn(k, cards)


if __name__ == "__main__":
    unittest.main()
