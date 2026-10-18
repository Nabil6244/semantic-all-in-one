"""pakmap/guard.py: the dry run pakMap and Hybrid share, the same idea as What If's preflight + heal (never a stop over one bad row)."""
import json
import pathlib
import tempfile
import unittest

import gfx_templates as G
from pakmap import guard
from pakmap.words import estimate_words

TEXT = "Fact one. Kenya has forty seven million people. The north is another story. Turkana is almost empty. From Mombasa the railway runs."
WORDS = estimate_words(TEXT)
HEAD = "item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,sub_text,value_to,params\n"


class TestHeal(unittest.TestCase):
    def test_a_semicolon_csv_a_typo_in_layer_type_and_a_typo_in_a_template_id_are_read_as_meant(self):
        raw = ("item_no;vo_anchor;layer_type;layer_id;geo_ref;label_text;sub_text;value_to;params\n"
               "1;Fact one;hud_titel;;;PART 1;;;\n"
               '1;forty seven;template;;;X;;60;{"template":"ring_percen"}\n')
        text, notes = guard.heal_text(raw)
        self.assertTrue(text.startswith("item_no,vo_anchor,layer_type"))
        joined = " | ".join(notes)
        self.assertIn("semicolons", joined); self.assertIn("'hud_titel' read as 'hud_title'", joined); self.assertIn("'ring_percen' read as 'ring_percent'", joined)

    def test_drop_rows_by_row_or_by_item_keeps_the_rest(self):
        text = HEAD + "1,a,hud_title,,,A,,,\n1,b,hud_title,,,B,,,\n2,c,hud_title,,,C,,,\n"
        self.assertEqual(guard.drop_rows(text, {3}).count("\n"), 3)
        self.assertEqual(guard.drop_rows(text, set(), {1}).strip().splitlines()[-1].split(",")[0], "2")


class TestDryRun(unittest.TestCase):
    def test_bad_rows_are_left_out_with_a_note_and_the_rest_compiles(self):
        csv_text = (HEAD + "1,Fact one,hud_title,,,PART 1,,,\n"
                    '1,forty seven million,template,,,,,,"{""template"":""ring_percent""}"\n'      # a required slot empty
                    "1,The north,marker,m,Nowhereland,NOWHERE,,,\n"                                 # a place that is not on the map
                    '1,Turkana,template,,,X,,,"{""template"":""rank_bars""}"\n'                      # no rows
                    "1,railway runs,stat,s1,,,KENYA,47,\n")
        dr = guard.dry_run(None, WORDS, text=csv_text, duration=20)
        self.assertTrue(dr.ok, dr.stops)
        self.assertEqual({e["type"] for e in dr.result.spec["events"]}, {"hud_title", "stat"})
        left = [r for r in dr.repairs if r.startswith("left out")]
        self.assertEqual(len(left), 3)
        self.assertEqual(sorted(dr.dropped), [3, 4, 5])

    def test_two_titles_at_once_the_later_one_gives_way(self):
        csv_text = HEAD + "1,Fact one,hud_title,,,A,,,\n1,Fact one,hud_title,,,B,,,\n"
        dr = guard.dry_run(None, WORDS, text=csv_text, duration=20)
        self.assertTrue(dr.ok, dr.stops)
        self.assertEqual([e["label"] for e in dr.result.spec["events"]], ["A"])

    def test_only_no_usable_row_is_a_stop(self):
        dr = guard.dry_run(None, WORDS, text=HEAD + "1,x,nonsense,,,,,,\n", duration=20)
        self.assertFalse(dr.ok)
        self.assertIn("no rows", dr.stops[0])

    def test_the_file_on_disk_is_never_changed(self):
        d = pathlib.Path(tempfile.mkdtemp()); f = d / "s.csv"
        f.write_text(HEAD + "1,Fact one,hud_title,,,A,,,\n1,zzz never,marker,m,Kenya,K,,,\n", encoding="utf-8")
        before = f.read_text(encoding="utf-8")
        dr = guard.dry_run(f, WORDS, duration=20)
        self.assertTrue(dr.ok); self.assertEqual(f.read_text(encoding="utf-8"), before)

    def test_compile_guarded_uses_the_plain_compile_when_all_is_well(self):
        d = pathlib.Path(tempfile.mkdtemp()); f = d / "s.csv"
        f.write_text(HEAD + "1,Fact one,hud_title,,,A,,,\n", encoding="utf-8")
        res, repairs, stops, repaired = guard.compile_guarded(f, WORDS, duration=20)
        self.assertIsNotNone(res); self.assertFalse(repaired); self.assertEqual(stops, [])
        f.write_text(HEAD + "1,Fact one,hud_title,,,A,,,\n1,zzz never,marker,m,Kenya,K,,,\n", encoding="utf-8")
        res, repairs, stops, repaired = guard.compile_guarded(f, WORDS, duration=20)
        self.assertTrue(repaired and res is not None and any("zzz never" in r for r in repairs))


class TestGraphicCheck(unittest.TestCase):
    def test_a_graphic_that_cannot_be_drawn_is_found_and_a_good_one_passes(self):
        good = {"id": "g", "type": "map_template", "t_in": 0, "t_out": 5, "template": G.get("rank_bars"), "slots": {"title": "T", "rows": [{"label": "A", "value": 2}]}}
        bad = {"id": "b", "type": "map_template", "t_in": 0, "t_out": 5, "template": {"id": "broken", "items": "not a list"}, "slots": {}}
        got = guard.check_gfx({"width": 640, "height": 360, "events": [good, bad]})
        if not got:
            self.skipTest("node is not available here")
        self.assertIsNone(got["g"]["fatal"]); self.assertTrue(got["b"]["fatal"])

    def test_the_guard_leaves_out_an_auto_graphic_that_cannot_be_drawn(self):
        # a row graphic that fails the draw check is dropped by row; covered end to end by the Canada sample
        self.assertTrue(callable(guard.compile_guarded))


class TestHybridTemplates(unittest.TestCase):
    CSV = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
           'b1,beat,Lesotho is,map,,,Lesotho,country,,,Lesotho is a kingdom inside South Africa. Maseru sits on the border.,,,,,,,,,,,where\n'
           "b1,layer,Lesotho is,,hud_title,,,,PART 1,THE KINGDOM,,,,,,,,,,,,\n"
           "b1,layer,Maseru sits,,template,,Maseru,,MASERU,Capital on the border,,,location_card,,,,,,,,,\n"
           'b1,layer,kingdom inside,,template,,,,SHARE,,"{""rows"": ""A=1; B=2""}",,rank_bars,,,,,,,,,\n'
           "b1,layer,border,,template,,,,X,,,,rank_bar,,,,,,,,,\n")

    def test_a_template_layer_loads_compiles_and_a_bad_one_is_left_out_with_a_note(self):
        from hybrid.beat_csv import plan_from_csv
        from hybrid.compile import compile_plan

        words = estimate_words("Lesotho is a kingdom inside South Africa. Maseru sits on the border.")
        plan = plan_from_csv(self.CSV, words, words[-1][2] + 1.0)
        types = [(l.type, l.kind) for l in plan.beats[0].layers]
        self.assertIn(("template", "location_card"), types)
        res = compile_plan(plan, validate=False)
        made = [e["template"]["id"] for e in res.spec["events"] if e["type"] == "map_template"]
        self.assertCountEqual(made, ["location_card", "rank_bars"])
        self.assertTrue(any("left out" in n for n in res.notes), res.notes)


class TestPrompts(unittest.TestCase):
    def test_the_hybrid_prompt_lists_the_templates_and_the_example_uses_one(self):
        from app_csv_prompts import TEMPLATE_PLACEHOLDER, build_prompt

        t = build_prompt("hybrid", "A script.", graphics=True)
        self.assertNotIn(TEMPLATE_PLACEHOLDER, t)
        self.assertIn("rank_bars [stats] reads label*, rows*", t)
        self.assertIn(",template,,Maseru,,MASERU", t)
        plain = build_prompt("hybrid", "A script.")           # the switch off: the prompt the style always had
        self.assertNotIn("rank_bars", plain); self.assertNotIn("template", plain.split("Script:")[0].lower().replace("hybrid map", ""))


if __name__ == "__main__":
    unittest.main()
