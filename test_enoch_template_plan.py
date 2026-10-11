"""Enoch Template, Phase 5: the refine pass on a VisualPlan -- relevance reasons, the AI ceiling (with its denominator and an
honest report), the run limit, motifs, cards, and never filling a gap with unrelated stock. Deterministic, offline."""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from ancient_texts.plan import AI_TYPES, flow_counts, refine_plan
from ancient_texts.qc import check_acquired_assets
from ancient_texts.subjects import load_pack
from enoch_template_testutil import NoPaidCalls
from style_engine.loader import load_style
from visual_director.schema import parse_visual_plan

STYLE = load_style("enoch_template")
PACK = load_pack("enoch")
NO_ART = dataclasses.replace(STYLE, selection_rules=dataclasses.replace(STYLE.selection_rules, artworks=[]))

AI_ONLY = [  # reconstructions with nothing real to show
    "A voice spoke from the cloud of light.", "The heavens opened above the mountain.", "Winds carried him beyond the edge of the world.",
    "He stood before a house of crystal and fire.", "Rivers of flame ran beneath the throne.", "The stars were bound in a dark prison.",
    "A great silence filled the hall.", "Light poured from the seated figure.", "The walls shook with the voice.",
    "The path ended at the edge of the abyss.", "Shadows moved across the sky.", "Everything was still again.",
]
MIXED = [
    ("The Watchers descended in a storm of fire.", "video"),                  # artwork exists (Blake)
    ("Ethiopic manuscripts kept the book alive for centuries.", "image"),     # real document
    ("The flood swept over the world.", "video"),                             # artwork (Doré)
    ("A house of crystal stood among flames.", "image"),
    ("In 1947 shepherds found jars in a cave near the Dead Sea.", "image"),   # real place / document
    ("The stars of heaven were imprisoned in the dark.", "video"),
    ("Snow lay on the summit of Mount Hermon.", "image"),                     # real place
    ("The giants fought among themselves in the night.", "video"),
    ("Scholars studied the Dead Sea Scrolls in Jerusalem.", "stock_video"),
    ("A great abyss opened with pillars of fire.", "video"),                 # artwork (John Martin)
    ("The archangels cried out to heaven.", "image"),                         # artwork (Reni)
    ("Light filled the hall.", "image"),
]


def plan_from(rows, *, default_query="ancient mysterious scene"):
    scenes = []
    for i, row in enumerate(rows):
        text, at = (row, "image") if isinstance(row, str) else row
        sc = {"scene_id": i + 1, "narration": text, "visual_goal": text, "visual_description": text + " painterly",
              "asset_type": at, "provider_preference": {"image": "flow_image", "video": "flow_video"}.get(at, at), "duration": 4.0}
        if at.startswith("stock"):
            sc["search_queries"] = [default_query]
        scenes.append(sc)
    return parse_visual_plan({"title": "t", "scenes": scenes})


def ai_count(plan):
    return sum(1 for s in plan.scenes if s.asset_type in AI_TYPES)


class Denominator(unittest.TestCase):
    def test_report_fields_and_denominator(self):
        p = plan_from(MIXED)
        with tempfile.TemporaryDirectory() as d, NoPaidCalls() as guard:
            r = refine_plan(p, style=STYLE, pack=PACK, images_dir=Path(d))
        guard.assert_clean()
        rep = r.report
        self.assertEqual(rep["eligible_visual_scenes"], 12)
        parts = (rep["ai_scenes"] + rep["documentary_source_imagery"] + rep["designed_cards"] + rep["historical_art"]
                 + rep["real_world_footage"] + rep["maps"] + rep["local_files"])
        self.assertEqual(parts, 12, "every scene is counted exactly once")
        self.assertEqual(rep["ai_allowed"], 1)                       # floor(12 * 0.12)
        self.assertEqual(rep["ai_scenes"], ai_count(p))
        self.assertEqual(rep["ai_ceiling_met"], rep["ai_scenes"] <= 1)
        self.assertLessEqual(rep["flow_after"]["ai_scenes"], rep["flow_before"]["ai_scenes"])


class AICeiling(unittest.TestCase):
    def run_plan(self, rows, style=STYLE, images=True, **kw):
        p = plan_from(rows)
        before = flow_counts(p)
        if images:
            with tempfile.TemporaryDirectory() as d:
                r = refine_plan(p, style=style, pack=PACK, images_dir=Path(d), **kw)
                files = sorted(x.name for x in Path(d).iterdir())
        else:
            r, files = refine_plan(p, style=style, pack=PACK, **kw), []
        self.assertLessEqual(flow_counts(p)["ai_scenes"], before["ai_scenes"], "never more Flow work")
        return p, r, files

    def test_12_scenes_meet_the_ceiling_with_relevant_material(self):
        p, r, files = self.run_plan(MIXED)
        self.assertTrue(r.report["ai_ceiling_met"], r.report)
        self.assertLessEqual(ai_count(p), 1)
        for m in r.scenes:
            self.assertIn(m.reason, ("names", "proves", "locates", "shows_person", "compares", "illustrates", "quotes",
                                     "reconstructs", "emphasizes", "sections", "user_file", "context"))
        changed = [m for m in r.scenes if m.change]
        self.assertTrue(all("->" in m.change for m in changed))

    def test_no_artwork_available(self):
        p, r, _ = self.run_plan(MIXED, style=NO_ART)
        self.assertTrue(all("artwork" not in (m.change or "") for m in r.scenes))
        self.assertTrue(r.report["ai_ceiling_met"], "documents, places and statement cards still cover it")

    def test_25_and_100_scenes(self):
        for n in (25, 100):
            rows = [(MIXED[i % len(MIXED)][0], MIXED[i % len(MIXED)][1]) for i in range(n)]
            p, r, _ = self.run_plan(rows)
            self.assertEqual(r.report["eligible_visual_scenes"], n)
            self.assertEqual(r.report["ai_allowed"], int(n * 0.12))
            self.assertTrue(r.report["ai_ceiling_met"], (n, r.report))
            self.assertLessEqual(r.report["max_ai_run_observed"], 2)

    def test_three_consecutive_ai_shots_are_broken(self):
        rows = [("Ethiopic manuscripts kept the book.", "stock_image")] + [(t, "image") for t in AI_ONLY[:3]] + \
               [("Snow lay on Mount Hermon.", "stock_image")]
        p, r, _ = self.run_plan(rows, ai_ceiling=1.0)          # the ceiling alone would allow all three
        self.assertLessEqual(r.report["max_ai_run_observed"], 2)

    def test_impossible_ceiling_is_reported_not_hidden(self):
        p, r, files = self.run_plan(AI_ONLY, style=NO_ART, images=False)   # no Images folder: no card can be installed
        rep = r.report
        self.assertFalse(rep["ai_ceiling_met"])
        self.assertGreater(rep["ai_scenes"], rep["ai_allowed"])
        self.assertTrue(rep["scenes_with_no_non_ai_alternative"])
        self.assertIn("ai_ceiling_not_met", [i.code for i in r.issues if i.severity == "hard"])

    def test_with_cards_the_narrations_own_words_replace_ai_not_unrelated_stock(self):
        p, r, files = self.run_plan(AI_ONLY, style=NO_ART)
        self.assertTrue(r.report["ai_ceiling_met"], r.report)
        statements = [m for m in r.scenes if m.card and m.card["kind"] == "statement"]
        self.assertTrue(statements)
        for m in statements:
            narration = p.scenes[m.scene - 1].narration
            self.assertIn(m.card["fields"]["phrase"].rstrip("."), narration)
        self.assertFalse([s for s in p.scenes if s.asset_type in ("stock_video", "stock_image")],
                         "no stock search was invented for scenes that name nothing real")
        self.assertEqual(len(files), len(statements))
        codes = {i.code for i in r.issues}
        self.assertIn("text_cards_far_above_target", codes, "a script naming nothing real is reported")
        self.assertIn("consecutive_text_cards", codes)

    def test_many_documents_are_used_as_documents(self):
        rows = [(f"The {w} was copied again in the monastery.", "image") for w in
                ("manuscript", "scroll", "fragment", "manuscript", "codex", "manuscript", "scroll", "fragment")]
        p, r, _ = self.run_plan(rows)
        self.assertGreaterEqual(r.report["documentary_source_imagery"], 6)


class Relevance(unittest.TestCase):
    def test_unrelated_query_is_reaimed_at_what_the_narration_names(self):
        p = plan_from([("Ethiopic manuscripts kept the book alive.", "stock_image"), ("Light filled the hall.", "image")], default_query="happy family at the beach")
        r = refine_plan(p, style=STYLE, pack=PACK)
        self.assertNotEqual(p.scenes[0].search_queries[0], "happy family at the beach")
        self.assertIn("->", r.scenes[0].change)

    def test_nothing_to_aim_at_is_flagged_not_filled(self):
        p = plan_from([("It was quiet for a long time.", "stock_video"), ("Light filled the hall.", "image")], default_query="sunset over a city skyline")
        r = refine_plan(p, style=STYLE, pack=PACK)
        self.assertEqual(p.scenes[0].search_queries[0], "sunset over a city skyline", "no invented replacement")
        self.assertIn("query_not_tied_to_narration", [i.code for i in r.issues])
        self.assertEqual(r.scenes[0].reason, "context")

    def test_a_generation_prompt_used_as_a_search_is_not_searched(self):
        prompt = ("A 19th-century Romantic oil painting of a lone patriarch walking into a vast misty valley lit by divine light, "
                  "umber and slate tones, cinematic")
        p = plan_from([("Genesis says only that he walked with God.", "stock_image"), ("Light filled the hall.", "image")],
                      default_query=prompt)
        with tempfile.TemporaryDirectory() as d:
            r = refine_plan(p, style=STYLE, pack=PACK, images_dir=Path(d))
        self.assertNotEqual((p.scenes[0].search_queries or [""])[0], prompt)
        self.assertTrue(r.scenes[0].change)
        p2 = plan_from([("Genesis says only that he walked with God.", "stock_image"), ("Light filled the hall.", "image")],
                       default_query=prompt)
        r2 = refine_plan(p2, style=STYLE, pack=PACK)                       # no Images folder: shortened and flagged
        self.assertLessEqual(len(p2.scenes[0].search_queries[0].split()), 8)
        self.assertIn("generation_prompt_as_search", [i.code for i in r2.issues])

    def test_reaimed_artwork_is_a_still_and_never_repeats_its_neighbour(self):
        art = "Gustave Doré fall of the rebel angels engraving"
        p = plan_from([("Then the archangels cast down the rebels.", "stock_image"),
                       ("They were cast down into the dark.", "stock_video")], default_query="dark smoke over ruins")
        p.scenes[0].search_queries = [art]
        r = refine_plan(p, style=STYLE, pack=PACK, images_dir=Path(tempfile.mkdtemp()))
        self.assertNotEqual(p.scenes[1].search_queries[:1], [art], "not the same picture twice in a row")
        p2 = plan_from([("Light filled the hall.", "image"), ("They were cast down into the dark.", "stock_video")],
                       default_query="dark smoke over ruins")
        refine_plan(p2, style=STYLE, pack=PACK)
        self.assertEqual((p2.scenes[1].asset_type, p2.scenes[1].search_queries), ("stock_image", [art]),
                         "an engraving is searched as a still")
        del r

    def test_avoided_term_in_query(self):
        p = plan_from([("Ethiopic manuscripts kept the book alive.", "stock_image"), ("Light filled the hall.", "image")], default_query="Book of Enoch on a kindle")
        refine_plan(p, style=STYLE, pack=PACK)
        self.assertNotIn("kindle", p.scenes[0].search_queries[0].lower())

    def test_only_candidate_unrelated_is_flagged_after_download(self):
        p = plan_from([("Ethiopic manuscripts kept the book alive.", "stock_image"),
                       ("Snow lay on the summit of Mount Hermon.", "stock_image")])
        r = refine_plan(p, style=STYLE, pack=PACK)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".asset_manifest.json").write_text(json.dumps({
                "001": {"status": "complete", "title": "Smiling family having a picnic", "stock_query": "x"},
                "002": {"status": "complete", "title": "Holy Quran page close-up"}}), encoding="utf-8")
            found = {(i.code, i.ref) for i in check_acquired_assets(d, r.scenes, STYLE.search_guidance.avoid_terms)}
        self.assertIn(("asset_may_not_match", "1"), found)
        self.assertIn(("irrelevant_asset", "2"), found)


class DownloadAudit(unittest.TestCase):
    """The real mismatches found in the cached 'Book of Enoch test' project (URLs copied as text; no file needed)."""

    def test_mismatches_described_only_by_their_url_are_caught(self):
        from ancient_texts.integration import named_terms

        rows = [("It is called the Book of Enoch.", "stock_image", "Ge'ez", "https://commons.wikimedia.org/w/index.php?curid=89754113"),
                ("In the days of Jared, the Watchers descended on the summit of Mount Hermon.", "stock_video", "Mount Hermon",
                 "https://www.pexels.com/video/4k-aerial-view-of-golan-heights-landscape-30784839/"),
                ("Their leader, Semjaza, made them swear an oath together,", "stock_image", "William Blake Book of Enoch drawing",
                 "https://pixabay.com/photos/literature-a-book-school-training-3259341/"),
                ("Then the archangels cried out to heaven.", "stock_image", "Guido Reni Archangel Michael painting",
                 "https://pixabay.com/photos/holy-handkerchief-jesus-christ-icon-1576896/"),
                ("Then, in 1952, in Cave Four at Qumran,", "stock_video", "Qumran caves",
                 "https://www.pexels.com/video/view-of-mountain-caves-5372087/"),
                ("the same calendar followed by the community at Qumran.", "stock_video", "Qumran caves Judean desert",
                 "https://www.pexels.com/video/aerial-view-of-qumran-national-park-12345/")]
        p = parse_visual_plan({"title": "t", "scenes": [
            {"scene_id": i + 1, "narration": n, "visual_goal": n, "visual_description": q, "asset_type": a, "provider_preference": a,
             "search_queries": [q]} for i, (n, a, q, _u) in enumerate(rows)]})
        r = refine_plan(p, style=STYLE, pack=PACK)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".asset_manifest.json").write_text(json.dumps({f"{i + 1:03d}": {"status": "complete", "source_url": u}
                                                                     for i, (_n, _a, _q, u) in enumerate(rows)}), encoding="utf-8")
            found = {i.ref: i.code for i in check_acquired_assets(d, r.scenes, STYLE.search_guidance.avoid_terms, named_terms())}
        self.assertEqual(found.get("1"), "asset_unverifiable", "a bare Commons id says nothing about the picture")
        for scene in ("2", "3", "4", "5"):                    # Golan aerial, school books, Christ icon, generic caves
            self.assertEqual(found.get(scene), "asset_may_not_match", scene)
        self.assertNotIn("6", found, "a picture described as Qumran passes")


class CsvSourcesWin(unittest.TestCase):
    def test_the_csvs_real_source_is_restored_and_ai_is_never_restored(self):
        rows = [{"scene_number": "1", "script_segment": "It is called the Book of Enoch.", "asset_type": "stock_image", "prompt": "Ge'ez"},
                {"scene_number": "2", "script_segment": "A cave near the Dead Sea.", "asset_type": "map", "prompt": "Israel > Qumran"},
                {"scene_number": "3", "script_segment": "Light filled the hall.", "asset_type": "flow_image", "prompt": "light"},
                {"scene_number": "4", "script_segment": "Snow lay on Mount Hermon.", "asset_type": "archive_video", "prompt": "Hermon||snow"}]
        p = plan_from([(rows[0]["script_segment"], "video"), (rows[1]["script_segment"], "stock_video"),   # what an earlier step made
                       (rows[2]["script_segment"], "stock_video"), (rows[3]["script_segment"], "stock_video")])
        before = flow_counts(p)
        r = refine_plan(p, style=STYLE, pack=PACK, csv_rows=rows)
        self.assertEqual([s.asset_type for s in p.scenes][:2], ["stock_image", "map"])
        self.assertEqual(p.scenes[0].search_queries, ["Ge'ez"])
        self.assertEqual(p.scenes[2].asset_type, "stock_video", "an AI row the mix made real is never turned back into AI")
        self.assertEqual((p.scenes[3].asset_type, p.scenes[3].search_queries), ("archive_video", ["Hermon", "snow"]))
        self.assertIn("kept the CSV's own source", r.scenes[0].change)
        self.assertLessEqual(flow_counts(p)["ai_scenes"], before["ai_scenes"])


class Motifs(unittest.TestCase):
    def test_deliberate_motif_reuse_is_allowed_and_close_repeats_reported(self):
        rows = [("The Ethiopic manuscript survived.", "stock_image"), ("Something else happened.", "stock_video"),
                ("Back to the Ethiopic manuscript.", "stock_image")]
        p = plan_from(rows, default_query="old paper")
        r = refine_plan(p, style=STYLE, pack=PACK)
        motifs = [m.motif for m in r.scenes if m.motif]
        self.assertEqual(motifs, ["ethiopic_manuscript", "ethiopic_manuscript"])
        self.assertIn("motif_too_close", [i.code for i in r.issues])
        self.assertNotIn("repeated_search", [i.code for i in r.issues if i.ref == "3"])


class Cards(unittest.TestCase):
    def test_requested_card_is_installed_as_the_scenes_numbered_file(self):
        p = plan_from(MIXED[:3])
        with tempfile.TemporaryDirectory() as d:
            r = refine_plan(p, style=STYLE, pack=PACK, images_dir=Path(d),
                            card_requests={2: {"kind": "section_break", "fields": {"title": "Where the book survived"}}})
            self.assertTrue((Path(d) / "002.png").is_file())
        self.assertEqual(p.scenes[1].asset_type, "local")
        self.assertEqual(r.scenes[1].reason, "sections")

    def test_card_never_installed_next_to_another_file_for_the_scene(self):
        p = plan_from(AI_ONLY[:12])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "003.jpg").write_bytes(b"old")
            r = refine_plan(p, style=STYLE, pack=PACK, images_dir=Path(d))
            self.assertFalse((Path(d) / "003.png").exists())
        self.assertIn("card_conflicts_with_existing_file", [i.code for i in r.issues])
        self.assertNotEqual(p.scenes[2].asset_type, "local")

    def test_unverified_quotation_card_is_refused(self):
        p = plan_from(MIXED[:2])
        r = refine_plan(p, style=STYLE, pack=PACK, images_dir=Path(tempfile.mkdtemp()),
                        card_requests={1: {"kind": "source_excerpt", "fields": {"text": "made up", "citation": "x", "locator": "y",
                                                                                "mode": "quotation"}}})
        self.assertIn("quote_not_verified", [i.code for i in r.issues])
        self.assertNotEqual(p.scenes[0].asset_type, "local")


if __name__ == "__main__":
    unittest.main()
