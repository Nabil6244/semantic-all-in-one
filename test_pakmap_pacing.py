"""PakMap pacing: several pictures per PART, side-by-side cards, card handoff, footage inserts per PART, picture-density warnings.
Local fixtures only (no AI, no Flow, no network)."""

import unittest

from pakmap.compile import CompileError, compile_csv, compile_rows
from pakmap.pacing import apply_card_handoff, apply_pacing
from pakmap.schema import parse_csv

HEAD = "item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,anchor,asset_path,hold,params\n"
# narration: w0 w1 ... w299, one word every 0.5 s (150 s)
WORDS = [(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(300)]


def build(body, **kw):
    """Compile + the PakMap pacing step, as Check plan and Generate do (pakmap.app_integration)."""
    import os
    import tempfile

    kw.setdefault("validate", False)
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(HEAD + body)
    try:
        res = compile_csv(path, WORDS, duration=150.0, **kw)
        apply_pacing(res, path)
    finally:
        os.unlink(path)
    return res


def ev(res):
    return {e["id"]: e for e in res.spec["events"]}


def pacing_warnings(res):
    return [w for w in res.report.warnings if "picture" in w or "insert" in w]


TITLE = "1,w0,hud_title,t1,,PART 1,,,,\n"


class TestPictures(unittest.TestCase):
    def test_several_cards_in_one_part(self):
        res = build(TITLE + "".join(f"1,w{n},pip,c{n},,CARD {n},tr,a{n}.jpg,,\n" for n in (10, 40, 70, 100)))
        e = ev(res)
        self.assertEqual([k for k in e if e[k]["type"] == "pip"], ["c10", "c40", "c70", "c100"])
        self.assertEqual(res.report.errors, [])

    def test_two_cards_side_by_side_and_a_three_card_filmstrip(self):
        res = build(TITLE + "1,w10,pip,a,,KING,tl,king.jpg,,\n1,w10,pip,b,,FLAG,tr,flag.jpg,,\n"
                    "1,w30,filmstrip,fs,,KING,center,k.jpg,,\n1,w30,filmstrip,fs,,FLAG,,f.jpg,,\n1,w30,filmstrip,fs,,ARMY,,a.jpg,,\n")
        e = ev(res)
        self.assertEqual((e["a"]["t_out"], e["b"]["t_out"]), (11.0, 11.0))  # side by side: neither is cut (5.0 + 6 s default)
        self.assertEqual(len(e["fs"]["cards"]), 3)

    def test_a_single_card_is_unchanged(self):
        res = build(TITLE + "1,w10,pip,c,Nairobi,NAIROBI,tr,city.jpg,,\n")
        c = ev(res)["c"]
        self.assertEqual((c["t_in"], c["t_out"]), (5.0, 11.0))
        self.assertIn("leader", c)
        self.assertFalse(any("hands over" in n for n in res.report.info))


class TestHandoff(unittest.TestCase):
    BODY = TITLE + "1,w10,pip,a,,A,tr,a.jpg,8,\n1,w20,pip,b,,B,tr,b.jpg,,\n1,w22,pip,c,,C,tl,c.jpg,,\n"

    def test_a_card_in_the_same_corner_hands_over(self):
        res = build(self.BODY)
        e = ev(res)
        self.assertAlmostEqual(e["a"]["t_out"], 10.0 + 0.45)  # b snaps in at 10 s; a fades out under it
        self.assertEqual(e["c"]["t_out"], 17.0)  # a card in another corner keeps its time
        self.assertTrue(any("hands over" in n for n in res.report.info))
        self.assertAlmostEqual({x.id: x for x in res.report.events}["a"].t_out, 10.45)

    def test_a_card_is_never_cut_to_a_flash(self):
        spec = {"events": [{"id": "a", "type": "pip", "t_in": 5.0, "t_out": 11.0}, {"id": "b", "type": "pip", "t_in": 5.2, "t_out": 11.0}]}
        apply_card_handoff(spec, None)
        self.assertEqual(spec["events"][0]["t_out"], 6.0)

    def test_compile_csv_alone_is_unchanged(self):
        res = compile_csv(text=HEAD + self.BODY, words=WORDS, duration=150.0, validate=False)
        self.assertEqual(ev(res)["a"]["t_out"], 13.0)
        self.assertFalse(any("picture" in w for w in res.report.warnings))

    def test_hybrid_render_skips_pacing(self):
        import inspect
        from pakmap import app_integration as ai

        src = inspect.getsource(ai.generate_pakmap_video)
        self.assertIn("if not spec_extra:", src)
        self.assertLess(src.index("if not spec_extra:"), src.index("apply_pacing(res, csv_path)"))

    def test_hybrid_compile_rows_is_not_touched(self):
        rows, _ = parse_csv("", text=HEAD + self.BODY)
        res = compile_rows(rows, WORDS, duration=150.0, validate=False)
        self.assertEqual(ev(res)["a"]["t_out"], 13.0)  # 5 s + hold 8: not handed over
        self.assertFalse(any("picture" in w for w in res.report.warnings))


class TestGeneratePath(unittest.TestCase):
    def test_pakmap_generate_renders_with_the_handoff(self):
        import test_pakmap_sourcing as ts

        run = ts.TestGenerateRun("test_the_pictures_are_fetched_into_the_images_folder_and_rendered_from_their_files")
        run.setUp()
        self.addCleanup(run.tearDown)
        (run.d / "s.csv").write_text("item_no,vo_anchor,layer_type,layer_id,label_text,geo_ref,asset_path,anchor,hold\n"
                                     "1,Kenya has,hud_title,t,PART 1,,,,\n1,Kenya has,pip,a,A,,a.jpg,tr,8\n1,Nairobi,pip,b,B,,b.jpg,tr,\n", encoding="utf-8")
        r = run.run_gen(ts.FakeProviders())
        self.assertTrue(r.ok, r.errors)
        e = {x["id"]: x for x in run.specs[-1]["events"]}
        self.assertAlmostEqual(e["a"]["t_out"], e["b"]["t_in"] + 0.45)


class TestFootageInserts(unittest.TestCase):
    def test_one_short_insert_per_part_is_fine(self):
        res = build(TITLE + "1,w10,pip,c1,,C,tr,c.jpg,,\n1,w30,media_full,f1,,,,storm.mp4,8,\n1,w50,pip,c2,,C,tr,c2.jpg,,\n"
                    "2,w80,hud_title,t2,,PART 2,,,,\n2,w90,media_full,f2,,,,charge.mp4,6,\n2,w100,pip,c3,,C,tr,c3.jpg,,\n")
        self.assertEqual([w for w in pacing_warnings(res) if "insert" in w], [])

    def test_two_inserts_in_one_part_and_a_long_insert_are_flagged(self):
        res = build(TITLE + "1,w10,media_full,f1,,,,a.mp4,6,\n1,w40,media_full,f2,,,,b.mp4,15,\n")
        w = " ".join(pacing_warnings(res))
        self.assertIn("PART 1 (PART 1)", w)
        self.assertIn("2 full-screen footage inserts (rows 3, 4)", w)
        self.assertIn("row 4 is 15.0s long", w)


class TestDensity(unittest.TestCase):
    def test_a_long_part_with_one_picture_is_sparse_and_says_why(self):
        res = build(TITLE + "1,w20,pip,c,,C,tr,c.jpg,,\n1,w180,marker,m,Nairobi,NAIROBI,,,,\n")
        w = pacing_warnings(res)
        self.assertTrue(any("no picture from 16.0s to 150.0s" in x for x in w), w)
        self.assertTrue(any("1 picture moment in 150s (0.4 per minute" in x for x in w), w)

    def test_a_picture_every_15_s_is_not_sparse(self):
        res = build(TITLE + "".join(f"1,w{n},pip,c{n},,C,tr,c{n}.jpg,,\n" for n in range(10, 300, 30)))
        self.assertEqual(pacing_warnings(res), [])

    def test_side_by_side_cards_count_as_one_moment(self):
        res = build(TITLE + "1,w20,pip,a,,A,tl,a.jpg,,\n1,w20,pip,b,,B,tr,b.jpg,,\n1,w180,marker,m,Nairobi,NAIROBI,,,,\n")
        self.assertTrue(any("1 picture moment in" in x for x in pacing_warnings(res)))

    def test_an_abstract_part_is_not_measured(self):
        res = build('1,w0,hud_title,t1,,PART 1,,,,"{""pacing"": ""abstract""}"\n1,w180,marker,m,Nairobi,NAIROBI,,,,\n')
        self.assertEqual(pacing_warnings(res), [])

    def test_density_never_blocks_the_plan(self):
        res = build(TITLE + "1,w180,marker,m,Nairobi,NAIROBI,,,,\n")
        self.assertEqual(res.report.errors, [])
        self.assertTrue(pacing_warnings(res))


class TestStickerWithCard(unittest.TestCase):
    def test_the_renderer_rule_is_unchanged(self):
        # the current engine still shows one rich picture at a time: a sticker and a photo card together is a renderer error
        with self.assertRaises(CompileError) as cm:
            build(TITLE + "1,w10,pip,c,,C,tr,c.jpg,,\n1,w12,sticker,s,Nairobi,,,s.png,,\n", validate=True)
        self.assertIn("sticker and a photo card", " ".join(cm.exception.report.errors))


if __name__ == "__main__":
    unittest.main()
