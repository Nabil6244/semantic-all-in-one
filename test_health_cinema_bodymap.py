import json, os, tempfile, unittest
from pathlib import Path
from PIL import Image
from health_cinema import bodymap, illustrations as ILL, scenes_csv as S

ANCH = Path.home() / "HealthCinemaTools" / "bench" / "anchors_body.json"
B = lambda t0, t1, **k: dict(dict(t0=t0, t1=t1, text="", region="body", scale="whole", focus="body", effect="none", label="", card_type="none", card_ref="", card_prompt="", card_at=None), **k)

class TestIllustrationLibrary(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = self.d; Image.new("RGB", (64, 36), (9, 9, 9)).save(Path(self.d) / "src.png")
    def tearDown(self): os.environ.pop("HEALTH_CINEMA_ILLUSTRATION_DIR", None)
    def test_register_find_and_reuse(self):
        self.assertIsNone(ILL.find("a"))
        ILL.register(Path(self.d) / "src.png", id="a", topic="Skin infection", view="lesion", kind="lesion", prompt="p", source="flow")
        self.assertEqual(ILL.find("a")["topic"], "Skin infection"); self.assertEqual(ILL.find(topic="skin infection", view="Lesion")["id"], "a")
        self.assertEqual(ILL.missing([{"ref": "a"}, {"ref": "b", "topic": "x", "view": "y"}]), [{"ref": "b", "topic": "x", "view": "y"}])
    def test_placeholder_never_chosen(self):
        ILL.register(Path(self.d) / "src.png", id="p", topic="t", view="v", kind="v", prompt="p", source="placeholder"); self.assertIsNone(ILL.find("p"))

@unittest.skipUnless(ANCH.is_file(), "body model not prepared")
class TestBodyMap(unittest.TestCase):
    A = bodymap.load_anchors(ANCH) if ANCH.is_file() else {}
    def test_anchors_are_real_positions(self):
        for r in ("head", "neck", "chest", "abdomen", "pelvis", "forearm_l", "forearm_r", "hand_l", "thigh_l", "shin_r", "foot_l", "heart"): self.assertIn(r, self.A)
        self.assertGreater(self.A["forearm_l"]["center"][0], 0.15); self.assertLess(self.A["forearm_r"]["center"][0], -0.15)       # left = +x
        self.assertLess(self.A["foot_l"]["center"][2], 0.1); self.assertGreater(self.A["head"]["center"][2], 1.5)
    def test_validate_catches_bad_beats(self):
        r = bodymap.validate([B(0, 3, region="elbowz"), B(3, 6, scale="huge"), B(6, 9, effect="spread")], self.A)
        self.assertEqual(len(r["errors"]), 3, r)
    def test_card_without_library_entry_is_reported_not_invented(self):
        os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = tempfile.mkdtemp()
        try: r = bodymap.validate([B(0, 3), B(3, 7, region="forearm_l", scale="close", effect="skin_layers", card_type="lesion", card_ref="nope", card_prompt="x")], self.A)
        finally: os.environ.pop("HEALTH_CINEMA_ILLUSTRATION_DIR")
        self.assertEqual(r["errors"], []); self.assertEqual(r["missing_illustrations"][0]["ref"], "nope")
    def test_spec_is_deterministic_and_complete(self):
        beats = [B(0, 3), B(3, 7, region="forearm_l", scale="region", focus="skin", label="Forearm"), B(7, 12, region="forearm_l", scale="close", focus="skin", effect="skin_layers"),
                 B(12, 16, region="forearm_l", scale="region", focus="vessels", effect="spread"), B(16, 20, region="heart", scale="region", focus="organ")]
        s1, s2 = bodymap.build_spec(beats, self.A, 20.0), bodymap.build_spec(beats, self.A, 20.0)
        self.assertEqual(json.dumps(s1, sort_keys=True), json.dumps(s2, sort_keys=True)); ts = [k["t"] for k in s1["camera"]]
        self.assertEqual(ts, sorted(ts)); self.assertEqual(s1["duration"], 20.0); self.assertIn("path", s1["procedural"]); self.assertIn("blk.dermis", s1["anchor_overrides"])
        self.assertTrue(any("not literal" in l["text"] for l in s1["labels"]))

class TestCsvColumns(unittest.TestCase):
    def test_body_row_parses(self):
        rows = S.parse_csv_text("text,visual,body_region,body_scale,body_effect,card_type,card_ref,card_at\nHello there.,body,Forearm_L,close,skin_layers,lesion,x,1.2\n")
        self.assertEqual((rows[0]["visual"], rows[0]["body_region"], rows[0]["card_at"]), ("body", "forearm_l", 1.2))
    def test_body_needs_region(self):
        with self.assertRaises(ValueError): S.parse_csv_text("text,visual\nHello there.,body\n")

if __name__ == "__main__": unittest.main()

@unittest.skipUnless(ANCH.is_file(), "body model not prepared")
class TestBodyMapOrgans(unittest.TestCase):
    A = bodymap.load_anchors(ANCH) if ANCH.is_file() else {}
    def test_organ_focus_needs_an_organ_region(self):
        r = bodymap.validate([B(0, 3, region="forearm_l", scale="region", focus="organ")], self.A); self.assertEqual(len(r["errors"]), 1)
    def test_condition_effect_only_on_organs_that_have_it(self):
        ok = bodymap.validate([B(0, 4, region="liver_only", scale="region", focus="organ", effect="fatty")], self.A); self.assertEqual(ok["errors"], [])
        bad = bodymap.validate([B(0, 4, region="kidneys", scale="region", focus="organ", effect="fatty")], self.A); self.assertEqual(len(bad["errors"]), 1)
    def test_liver_beat_builds_layers_tint_and_single_label(self):
        sp = bodymap.build_spec([B(0, 3), B(3, 8, region="liver_only", scale="region", focus="organ", effect="fatty")], self.A, 8.0)
        self.assertIn("Layer_Liver", sp["layers"]); self.assertIn("Layer_Liver:Liver", sp["tints"]); self.assertEqual(len([l for l in sp["labels"] if l["id"].startswith(("b1", "cond"))]), 1)
        self.assertEqual([n for n in sp["layer_order"]], sorted(sp["layer_order"], key=bodymap.LAYER_ORDER.index))
    def test_leg_route_goes_through_hip_and_abdomen(self):
        beats = [B(0, 3), B(3, 7, region="shin_l", scale="close", focus="skin", effect="skin_layers"), B(7, 12, region="shin_l", scale="region", focus="vessels", effect="spread")]
        self.assertEqual(bodymap.validate(beats, self.A)["errors"], []); chain = [a for a, _ in bodymap.route_chain("shin_l", self.A)]
        self.assertEqual(chain[1:], ["thigh_l", "hip_l", "abdomen", "heart"]); self.assertIn("path", bodymap.build_spec(beats, self.A, 12.0)["procedural"])
    def test_merged_body_has_every_organ_layer(self):
        d = json.loads(ANCH.read_text())["layers"]
        for n in ("Layer_Skin", "Layer_Skeleton", "Layer_Heart", "Layer_Liver", "Layer_Urinary", "Layer_Cortex", "Layer_Intestines"): self.assertIn(n, d)

class TestCsvNeeds(unittest.TestCase):
    def test_needs_lists_each_missing_id_once_and_rejects_idless_cards(self):
        from health_cinema import bodymap_flow as F
        d = tempfile.mkdtemp(); os.environ["HEALTH_CINEMA_ILLUSTRATION_DIR"] = d
        try:
            f = Path(d) / "s.csv"; f.write_text("text,visual,body_region,card_type,card_ref,card_prompt\nOne here.,body,forearm_l,lesion,x1,A lesion\nTwo here.,body,forearm_l,lesion,x1,A lesion\nThree here.,body,heart,none,,\n")
            self.assertEqual([n["id"] for n in F.needs_from_csv(f)], ["x1"])
            f.write_text("text,visual,body_region,card_type,card_ref,card_prompt\nOne here.,body,forearm_l,lesion,,A lesion\n")
            with self.assertRaises(ValueError): F.needs_from_csv(f)
        finally: os.environ.pop("HEALTH_CINEMA_ILLUSTRATION_DIR")
