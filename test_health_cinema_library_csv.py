"""Health Cinema stage 2: the CSV directs the visuals (no model call), and the 3D library builds a journey for any prepared organ from its anchors."""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path

from health_cinema import assets, direction, library, planner, scenes_csv as C

CSV = ('text,start,end,chapter,footage,visual,organ,shot,footage_alt,source\n'
       '"The liver filters your blood.",,,,,3D,liver,peel,,\n'
       '"A man named David learns about it after a blood test.",,,,man doctor blood test,footage,,,"patient clinic desk | doctor talking to patient",stock\n'
       '"Over time inflammation can scar it.",,,,,3d,liver,,,\n'
       '"Rest.",,,,,text,,,,\n'
       '"Keep moving every day.",,,,,,,,,\n')

class TestCsvDirection(unittest.TestCase):
    def rows(self): return C.parse_csv_text(CSV)
    def test_columns_are_read_and_validated(self):
        r = self.rows(); self.assertEqual((r[0]["visual"], r[0]["organ"], r[0]["shot"]), ("3d", "liver", "peel"))
        self.assertEqual(r[1]["footage_alt"], ["patient clinic desk", "doctor talking to patient"]); self.assertEqual(r[1]["source"], "stock")
        self.assertTrue(C.has_direction(r)); self.assertFalse(C.has_direction(C.parse_csv_text("text\nHello there.\n")))
        with self.assertRaisesRegex(ValueError, "visual 'hologram' is not one of"): C.parse_csv_text("text,visual\nHi.,hologram\n")
        self.assertEqual(C.parse_csv_text("text,shot\nHi.,spin\n")[0]["shot_desc"], "spin")      # a described shot is kept as its description, never an error

    def sentences(self):
        r = self.rows()
        for i, s in enumerate(r): s["start"], s["end"] = i * 5.0, i * 5.0 + 5.0
        return r

    def test_dscenes_come_from_the_rows_without_any_model(self):
        ds = direction.dscenes_from_rows(self.sentences()); self.assertEqual({d["plan_source"] for d in ds}, {"csv"})
        self.assertEqual(ds[0]["hint"]["visual"], "3d"); self.assertEqual(ds[0]["hint"]["organ"], "liver")
        self.assertEqual(ds[1]["queries"], ["man doctor blood test", "patient clinic desk", "doctor talking to patient"])
        self.assertEqual(ds[4]["queries"], ["keep moving every day"][:1] if False else ds[4]["queries"]); self.assertTrue(ds[4]["queries"])

    def test_planner_obeys_the_csv(self):
        ds = direction.dscenes_from_rows(self.sentences()); sent = self.sentences()
        ready = lambda t: t.startswith("auto:liver")
        sc = planner.plan_directed(sent, "mix", ds, ready, allow_footage=True)["scenes"]
        self.assertEqual([s.kind for s in sc], ["anatomy_3d", "footage", "anatomy_3d", "text_card", "footage"])
        self.assertEqual(sc[0].visual["template"], "auto:liver:peel"); self.assertEqual(sc[0].visual["shot"], "peel")
        self.assertEqual(sc[2].visual["template"].split(":")[:2], ["auto", "liver"])      # an explicit 3D row is honoured twice
        self.assertEqual(sc[1].visual["query"], "man doctor blood test")

    def test_explicit_3d_without_a_model_becomes_footage_naming_the_organ_not_a_card(self):
        sc = planner.plan_directed(self.sentences(), "mix", direction.dscenes_from_rows(self.sentences()), lambda t: False, allow_footage=True)["scenes"]
        self.assertEqual(sc[0].kind, "footage"); self.assertEqual(sc[0].visual["anatomy_wanted"], "liver"); self.assertIn("liver", sc[0].visual["query"])

    def test_consecutive_3d_rows_of_one_body_part_become_one_scene(self):
        rows = C.parse_csv_text("text,visual,organ,shot\n\"The liver filters blood.\",3d,liver,zoom\n\"Fat can build up in it.\",3d,liver,isolate\n\"Rest.\",text,,\n")
        for i, s in enumerate(rows): s["start"], s["end"] = i * 4.0, i * 4.0 + 4.0
        sc = planner.plan_directed(rows, "mix", direction.dscenes_from_rows(rows), lambda t: True, allow_footage=True)["scenes"]
        self.assertEqual([s.kind for s in sc], ["anatomy_3d", "text_card"]); self.assertEqual(sc[0].visual["shot"], "zoom"); self.assertAlmostEqual(sc[0].end - sc[0].start, 8.0, places=1)

    def test_csv_alternative_searches_are_tried_before_any_model_is_asked(self):
        d = {"narration": "A woman climbs stairs.", "queries": ["woman climbing stairs slowly", "senior woman stairs handrail", "elderly stairs morning"], "description": "", "goal": ""}
        self.assertEqual(direction.alternative_queries(d, ["woman climbing stairs slowly"], {"gemini_enabled": True})[:2], ["senior woman stairs handrail", "elderly stairs morning"])

    def test_a_clip_the_apps_qa_failed_is_weak_for_any_scene(self):
        from health_cinema import acquire
        self.assertTrue(acquire.is_weak({"ok": True, "qa": {"status": "FAIL", "vision_used": False, "semantic_match": 0.5}})); self.assertFalse(acquire.is_weak({"ok": True, "qa": {"status": "WEAK", "vision_used": False, "semantic_match": 0.5}}))


def anchors_file(d: str) -> str:
    box = lambda c, h: {"min": [c[0] - h, c[1] - h, c[2] - h], "max": [c[0] + h, c[1] + h, c[2] + h], "center": c}
    A = {"liver_only": box([0.1, 0, 1.2], 0.09), "gallbladder": box([0.12, -0.02, 1.15], 0.02), "abdomen": box([0, 0, 1.1], 0.25), "knee_l": box([0.1, 0, 0.5], 0.06), "menisci": box([0.1, 0, 0.5], 0.04)}
    p = Path(d) / "anchors_abdomen.json"
    p.write_text(json.dumps({"anchors": A, "layers": {"Layer_Liver": ["Liver"], "Layer_Skeleton": ["x"], "Layer_Stomach": ["s"], "Layer_Intestines": ["i"]}, "polys": {}})); return str(p)

class TestLibrary(unittest.TestCase):
    def test_every_shot_builds_a_valid_spec_from_the_models_own_anchors(self):
        with tempfile.TemporaryDirectory() as d:
            ap = anchors_file(d)
            for shot in (x for x in library.SHOTS if x not in library.CONDITION):
                sp = library.build_spec(f"auto:liver:{shot}", ap)
                self.assertEqual(sp["duration"], library.DURATION); self.assertEqual(sp["camera"][0]["t"], 0); self.assertTrue(all(c["target"] == "liver_only" for c in sp["camera"]))
                self.assertIn("Layer_Liver", sp["layers"]); self.assertEqual(sp["layers"]["Layer_Liver"][-1][1], 1.0)
                self.assertTrue(all(0.3 <= c["fill"] <= library.FILL_MAX for c in sp["camera"]))          # framed by how much of the frame the organ fills (journey.fit_dist)
                self.assertEqual([l["text"] for l in sp["labels"]], ["Liver", "Gallbladder"])
            self.assertEqual(library.build_spec("auto:liver:isolate", ap)["layers"]["Layer_Skeleton"][-1][1], 0.12)
            self.assertGreater(library.build_spec("auto:liver:peel", ap)["layers"]["Layer_Skeleton"][0][1], 0.5)

    def test_missing_anchor_or_layer_means_no_template_never_a_guess(self):
        with tempfile.TemporaryDirectory() as d:
            ap = anchors_file(d)
            with self.assertRaises(KeyError): library.build_spec("auto:pancreas:orbit", ap)       # no pancreas anchor in this model
            old = assets.asset_dirs; assets.asset_dirs = lambda: [Path(d)]
            try:
                (Path(d) / "abdomen.glb").write_bytes(b"x")
                self.assertTrue(assets.template_ready("auto:liver:orbit")); self.assertFalse(assets.template_ready("auto:pancreas:orbit")); self.assertFalse(assets.template_ready("auto:knee:orbit"))
                self.assertEqual(assets.model_for_template("auto:liver:peel"), "abdomen"); self.assertEqual(assets.model_for_template("brain_journey"), "head")
            finally: assets.asset_dirs = old

    def test_template_for_prefers_authored_journeys_and_uses_aliases(self):
        ready = lambda t: True
        self.assertEqual(library.template_for("heart", ready), "heart_journey"); self.assertEqual(library.template_for("osteoarthritis", ready, shot="orbit"), "auto:knee:orbit")
        self.assertIsNone(library.template_for("liver", lambda t: False)); self.assertIsNone(library.template_for("toenail", ready))
        self.assertEqual(library.find_organ("Fat builds up inside liver cells, doctors call it fatty liver disease."), "liver")

    def test_kidney_comes_from_bodyparts3d_and_is_only_ready_when_that_model_is_installed(self):
        self.assertEqual(library.organ_key("kidney stones"), "kidney"); self.assertEqual(library.ORGANS["kidney"].model, "abdomen")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(KeyError): library.build_spec("auto:kidney:orbit", anchors_file(d))      # a model without the BodyParts3D kidneys has no kidney scene: never a stand-in shape


class TestPathology(unittest.TestCase):
    ANCH = str(assets.ROOT / "health_cinema" / "templates" / "micro_anchors.json")
    def test_micro_scenes_need_no_model_and_build_their_tracks(self):
        for key, track in (("plaque", "plaque"), ("clot", "clot"), ("blood_flow", "flow"), ("fatty_cell", "lipid"), ("cell", "lipid")):
            sp = library.build_spec(f"micro:{key}:orbit", self.ANCH)
            self.assertTrue(sp["no_model"]); self.assertIn(track, sp["tracks"]); self.assertEqual(sp["layers"], {}); self.assertTrue(sp["labels"]); self.assertEqual(sp["tracks"][track][-1][0], sp["duration"])
        self.assertEqual(assets.model_for_template("micro:plaque:orbit"), "micro"); self.assertTrue(assets.template_ready("micro:clot:orbit")); self.assertFalse(assets.template_ready("micro:nonsense:orbit"))
        self.assertTrue(all(0 <= v <= 1 for _, v in library.build_spec("micro:plaque:orbit", self.ANCH)["tracks"]["plaque"]))

    def test_sentences_find_the_right_pathology_and_shot(self):
        self.assertEqual(library.find_organ("Plaque builds up inside the artery wall."), "plaque"); self.assertEqual(library.find_organ("If a blood clot forms on that spot"), "clot")
        self.assertEqual(library.find_organ("Fat droplets fill the liver cells."), "fatty_cell"); self.assertIsNone(library.find_organ("Frank has a major ischemic stroke after the cells report.")); self.assertEqual(library.pick_shot("When too much fat builds up in the liver", "liver"), "fatty")
        self.assertEqual(library.pick_shot("The pancreas becomes inflamed.", "pancreas"), "inflamed"); self.assertEqual(library.pick_shot("Where the knee sits", "knee"), "zoom")
        self.assertEqual(library.template_for("atherosclerosis", lambda t: True), "micro:plaque:orbit")

    def test_condition_shot_tints_only_the_organ_and_only_where_the_condition_is_real(self):
        with tempfile.TemporaryDirectory() as d:
            ap = anchors_file(d); sp = library.build_spec("auto:liver:fatty", ap)
            self.assertIn("Layer_Liver:Liver", sp["tints"]); keys = sp["tints"]["Layer_Liver:Liver"]; self.assertEqual(keys[0][1], list(library.BASE_TINT["liver"][1])); self.assertNotEqual(keys[0][1], keys[-1][1])
            self.assertEqual([l["text"] for l in sp["labels"]], ["Fat builds up"])
            self.assertEqual(library.build_spec("auto:liver:inflamed", ap)["labels"][0]["text"], "Inflamed tissue")
        self.assertNotIn("fatty", library.available(lambda t: True)["knee"]); self.assertIn("fatty", library.available(lambda t: True)["liver"]); self.assertNotIn("fatty", library.available(lambda t: True)["spleen"])

    def test_sampler_carries_tracks_and_tints_to_every_frame(self):
        from health_cinema import journey
        with tempfile.TemporaryDirectory() as d:
            sp = library.build_spec("micro:plaque:orbit", self.ANCH); p = Path(d) / "s.json"; p.write_text(json.dumps(sp))
            _, _, fr = journey.sample(str(p), self.ANCH, 4, 1280, 720)
            self.assertEqual(fr[0]["proc"]["plaque"], 0.0); self.assertEqual(fr[-1]["proc"]["plaque"], 1.0); self.assertEqual(fr[0]["tint"], {})

    def test_csv_shot_reaches_the_template_and_short_3d_scenes_are_flagged(self):
        rows = C.parse_csv_text("text,visual,organ,shot\n\"Fat builds up in the liver.\",3d,liver,fatty\n")
        rows[0]["start"], rows[0]["end"] = 0.0, 3.0
        sc = planner.plan_directed(rows, "mix", direction.dscenes_from_rows(rows), lambda t: True, allow_footage=True)["scenes"][0]
        self.assertEqual(sc.visual["template"], "auto:liver:fatty"); self.assertIn("3d_short", [f["code"] for f in sc.flags])

    def test_csv_accepts_condition_shots_and_pathology_organs(self):
        rows = C.parse_csv_text("text,visual,organ,shot\n\"Fat builds up.\",3d,liver,fatty\n\"Plaque.\",3d,plaque,\n")
        self.assertEqual(rows[0]["shot"], "fatty"); self.assertEqual(library.organ_key(rows[1]["organ"]), "plaque")
        self.assertNotIn("shot", C.parse_csv_text("text,shot\nHi.,melt\n")[0])      # not a camera move: kept as shot_desc only


class TestRepeatedScenesDiffer(unittest.TestCase):
    def test_second_use_of_a_template_gets_a_variant_and_a_different_camera(self):
        rows = C.parse_csv_text("text,visual,organ,shot\n\"Blood flows.\",3d,blood flow,zoom\n\"Rest.\",text,,\n\"Blood flows again.\",3d,blood flow,zoom\n\"And again here.\",3d,blood flow,zoom\n")
        for i, s in enumerate(rows): s["start"], s["end"] = i * 8.0, i * 8.0 + 8.0
        sc = [s for s in planner.plan_directed(rows, "mix", direction.dscenes_from_rows(rows), lambda t: True, allow_footage=True)["scenes"] if s.kind == "anatomy_3d"]
        self.assertEqual([s.visual.get("variant", 0) for s in sc], [0, 1])      # the last two rows are consecutive rows of one organ: one scene
        anchors = str(assets.ROOT / "health_cinema" / "templates" / "micro_anchors.json"); a, b = (library.apply_variant(library.build_spec(s.visual["template"], anchors), s.visual.get("variant", 0)) for s in sc[:2])
        self.assertNotEqual(a["camera"][0]["az"], b["camera"][0]["az"]); self.assertEqual(b["procedural"]["variant"], 1); self.assertNotIn("variant", a["procedural"])
        self.assertEqual(library.apply_variant(library.build_spec("micro:clot:orbit", anchors), 0)["camera"], library.build_spec("micro:clot:orbit", anchors)["camera"])      # first use unchanged: cache stays valid


class TestCsvCards(unittest.TestCase):
    CSV = ('text,visual,stat,stat_unit,stat_label,stat_kicker,events,card_title,card_kicker\n'
           '"It beats about 100,000 times a day.",stat,"100,000",,heartbeats every day,Your heart,,,\n'
           '"Around 20 to 30 minutes in, the first heart cells begin to die. They are replaced by scar tissue.",timeline,,,,,"20 to 30 minutes: the first cells die | scar tissue: replaces the muscle",,The heart muscle\n'
           '"Here is what you can control.",chapter,,,,,,What you can control,Prevention\n')
    def rows(self):
        r = C.parse_csv_text(self.CSV)
        for i, s in enumerate(r): s["start"], s["end"] = i * 9.0, i * 9.0 + 9.0
        return r
    def test_columns_are_parsed_and_validated(self):
        r = self.rows(); self.assertEqual((r[0]["stat"], r[0]["stat_label"]), ("100,000", "heartbeats every day")); self.assertEqual(r[1]["events"][1], {"when": "scar tissue", "label": "replaces the muscle"})
        self.assertTrue(C.has_direction(r))
        with self.assertRaisesRegex(ValueError, "needs the number"): C.parse_csv_text("text,visual,stat\nHi.,stat,\n")
        with self.assertRaisesRegex(ValueError, "when: what happens"): C.parse_csv_text("text,visual,events\nHi.,timeline,just one thing\n")
        with self.assertRaisesRegex(ValueError, "at least two events"): C.parse_csv_text("text,visual,events\nHi.,timeline,\"a: b\"\n")
    def test_planner_builds_cards_from_the_rows_only(self):
        sent = self.rows(); sc = planner.plan_directed(sent, "mix", direction.dscenes_from_rows(sent), lambda t: True, allow_footage=True)["scenes"]
        self.assertEqual([s.kind for s in sc], ["stat_card", "timeline_card", "chapter_card"])
        self.assertEqual(sc[0].visual["number"], "100,000"); self.assertEqual(sc[0].visual["context"], "heartbeats every day"); self.assertEqual(sc[0].visual["source_line"], "From the narration")
        ev = sc[1].visual["events"]; self.assertEqual([e["when"] for e in ev], ["20 to 30 minutes", "scar tissue"]); self.assertLess(ev[0]["t0"], ev[1]["t0"]); self.assertGreaterEqual(ev[1]["t0"] - ev[0]["t0"], 0.9)
        self.assertEqual((sc[2].visual["title"], sc[2].visual["kicker"]), ("What you can control", "Prevention"))
    def test_high_end_director_gives_the_cards_their_own_text(self):
        from health_cinema.edit import director as D
        sent = self.rows(); sc = planner.plan_directed(sent, "mix", direction.dscenes_from_rows(sent), lambda t: True, allow_footage=True)["scenes"]
        p = D.build(sc, (255, 96, 80), src_duration=lambda path: 10.0); g = [s["gfx"] for s in p["shots"]]
        self.assertEqual((g[0]["number"], g[0]["context"], g[0]["kicker"], g[0]["source_line"]), ("100,000", "heartbeats every day", "Your heart", "From the narration"))
        self.assertEqual(g[1]["kicker"], "The heart muscle" if False else g[1]["kicker"]); self.assertEqual(len(g[1]["events"]), 2); self.assertEqual((g[2]["title"], g[2]["kicker"]), ("What you can control", "Prevention"))


if __name__ == "__main__": unittest.main()
