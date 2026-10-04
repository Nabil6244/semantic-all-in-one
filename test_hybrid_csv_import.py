"""The Hybrid CSV importer: the CSV of composition_styles/hybrid_csv_prompt.txt becomes a HybridPlan that the rest of Hybrid (validator, Visual Tab,
compiler, renderer options) treats like any other plan."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from hybrid.compile import compile_plan, plan_to_rows
from hybrid.csv_import import CsvImportError, plan_from_csv
from hybrid.plan import HybridPlan
from hybrid.validate import validate

PROMPT = Path(__file__).with_name("composition_styles") / "hybrid_csv_prompt.txt"
HEADER = "item_no,vo_anchor,offset_s,layer_type,layer_id,geo_ref,label_text,sub_text,color_role,value_from,value_to,value_format,anchor,asset_path,camera_action,frame,line_kind,hold,params"
FOOT = '"{""cover_ui"": true, ""dissolve_s"": 0.5, ""kenburns"": ""auto"", ""fit"": ""slow""}"'


def example():
    t = PROMPT.read_text(encoding="utf-8")
    script = t.split("Script:\n", 1)[1].split("\n\nCSV:", 1)[0].strip()
    return script, t.split("CSV:\n", 1)[1].split("\n\nNOW WRITE", 1)[0].strip()


def words_of(script, pace=2.6):
    toks = re.findall(r"[A-Za-z']+", script)
    w = [(x, round(i / pace, 3), round(i / pace + 0.3, 3)) for i, x in enumerate(toks)]
    return w, w[-1][2] + 0.5


def errs(plan):
    return [f for f in validate(plan) if f.severity == "error"]


class TestTheExample(unittest.TestCase):
    def setUp(self):
        script, csv_text = example()
        self.words, self.dur = words_of(script)
        self.res = plan_from_csv(csv_text, self.words, self.dur)
        self.plan = self.res.plan

    def test_map_cards_and_footage_become_the_right_beats_in_order(self):
        self.assertEqual([b.mode for b in self.plan.beats], ["map_footage", "footage", "map", "footage", "map_footage"])
        for a, b in zip(self.plan.beats, self.plan.beats[1:]):
            self.assertAlmostEqual(a.end, b.start, places=3)                 # one contiguous timeline
        self.assertEqual(self.plan.beats[0].start, 0.0)
        self.assertAlmostEqual(self.plan.beats[-1].end, self.plan.duration, places=2)

    def test_footage_clips_and_cards_carry_their_pictures_and_places(self):
        b = self.plan.beats
        self.assertEqual([c.asset for c in b[1].clips], ["stock_video:green grass sprouting through pale sand in a time lapse"])
        self.assertEqual(b[3].clips[0].asset, "stock_video:farmer planting seedlings in dark wet soil after rain")
        self.assertEqual((b[0].support.asset, b[0].support.place, b[0].support.label), ("stock_image:endless sand dunes of the Sahara under a hard noon sun", "Algeria", "SAHARA"))
        self.assertEqual(b[4].support.place, "28.5,8.0")

    def test_the_camera_opens_on_the_globe_flies_in_and_never_moves_under_footage(self):
        steps = [(s.action, s.place, s.frame, s.t) for bt in self.plan.beats for s in bt.camera]
        self.assertEqual(steps[0], ("start", "Algeria", "globe", 0.0))
        self.assertEqual(steps[1][:3], ("fly_to", "Algeria", "country"))
        self.assertAlmostEqual(steps[1][3], 1.4, places=2)
        self.assertEqual(sum(1 for s in steps if s[0] == "start"), 1)
        for a, b in self.plan.footage_windows():
            self.assertFalse(any(a + 0.01 < s[3] < b - 0.01 for s in steps))

    def test_a_layer_that_would_have_appeared_under_footage_appears_just_after_it_and_says_so(self):
        marker = next(l for bt in self.plan.beats for l in bt.layers if l.id == "niger")
        footage_end = self.plan.beats[1].end
        self.assertGreaterEqual(marker.t, footage_end)
        self.assertTrue(any("niger" in n and "under footage" in n for n in self.res.notes))

    def test_titles_fills_and_stats_keep_what_the_csv_said(self):
        l0 = {l.id: l for l in self.plan.beats[0].layers}
        self.assertEqual((l0["i1_hud_title1"].label, l0["i1_hud_title1"].sub), ("THE GREEN SAHARA", "A SHIFTING LANDSCAPE"))
        self.assertEqual((l0["sahara"].type, l0["sahara"].place, l0["sahara"].role), ("fill", "Algeria", "subject"))
        s = l0["area"]
        self.assertEqual((s.value_from, s.value_to, s.format, s.anchor), (0.0, 9.0, "0 MILLION KM²", "br"))

    def test_it_is_a_normal_plan_valid_compilable_and_round_trippable(self):
        self.assertEqual(errs(self.plan), [])
        res = compile_plan(self.plan, validate=True)
        self.assertEqual(res.report.errors, [])
        foot = [e for e in res.spec["events"] if e["type"] == "media_full"]
        self.assertEqual(len(foot), 2)
        self.assertTrue(all(e.get("cover_ui") and e.get("fit") == "slow" for e in foot))
        self.assertEqual(res.spec["hybrid"]["pause_overlays"], True)          # the Hybrid behaviours a plain pakMap import would not get
        self.assertTrue(res.spec["media_lazy"])
        again = HybridPlan.from_dict(self.plan.to_dict())
        self.assertEqual([(b.id, b.mode, b.start, b.end) for b in again.beats], [(b.id, b.mode, b.start, b.end) for b in self.plan.beats])

    def test_the_footage_and_cards_are_rows_of_the_visual_plan(self):
        from hybrid.app_integration import visual_dicts

        rows = visual_dicts(self.plan)
        self.assertEqual([r["asset_type"] for r in rows], ["stock_image", "stock_video", "stock_video", "stock_image"])


class TestShapes(unittest.TestCase):
    words = [(f"w{i}", round(i / 2.6, 3), round(i / 2.6 + 0.3, 3)) for i in range(160)]
    dur = 160 / 2.6 + 0.5

    def csv(self, *rows):
        return "\n".join([HEADER, *rows])

    def test_two_clips_that_follow_each_other_are_one_footage_beat_with_two_clips(self):
        out = plan_from_csv(self.csv(
            "1,w0,,camera,c0,Kenya,,,,,,,,,start,globe,,,",
            "1,w0,1.4,camera,c1,Kenya,,,,,,,,,fly_to,country,,,",
            "1,w0,,hud_title,,,PART 1,,,,,,,,,,,,",
            f"1,w20,,media_full,f1,,,,,,,,,stock_video:one,,,,4,{FOOT}",
            f"1,w30,,media_full,f2,,,,,,,,,stock_video:two,,,,4,{FOOT}",
            "1,w60,,marker,m,Nairobi,NAIROBI,,,,,,,,,,,,"), self.words, self.dur)
        foot = [b for b in out.plan.beats if b.mode == "footage"]
        self.assertEqual(len(foot), 1)
        self.assertEqual([c.asset for c in foot[0].clips], ["stock_video:one", "stock_video:two"])
        self.assertIsNotNone(foot[0].clips[0].dur)
        self.assertEqual(errs(out.plan), [])

    def test_a_card_far_from_another_gets_its_own_map_beat_and_one_too_close_is_dropped_with_a_note(self):
        out = plan_from_csv(self.csv(
            "1,w0,,camera,c0,Kenya,,,,,,,,,start,country,,,",
            "1,w0,,hud_title,,,PART 1,,,,,,,,,,,,",
            "1,w4,,pip,p1,Nairobi,NAIROBI,,,,,,tr,stock_image:one,,,,5,",
            "1,w6,,pip,p2,Mombasa,MOMBASA,,,,,,tl,stock_image:two,,,,5,",
            "1,w40,,pip,p3,Kisumu,KISUMU,,,,,,tr,stock_image:three,,,,5,"), self.words, self.dur)
        cards = [b.support.asset for b in out.plan.beats if b.support]
        self.assertEqual(cards, ["stock_image:one", "stock_image:three"])
        self.assertTrue(any("p2" in n or "row 5" in n for n in out.notes))

    def test_a_camera_move_under_footage_waits_until_the_map_returns(self):
        out = plan_from_csv(self.csv(
            "1,w0,,camera,c0,Kenya,,,,,,,,,start,country,,,",
            "1,w0,,hud_title,,,PART 1,,,,,,,,,,,,",
            f"1,w20,,media_full,f1,,,,,,,,,stock_video:one,,,,6,{FOOT}",
            "1,w25,,camera,c1,Uganda,,,,,,,,,fly_to,country,,,",
            "1,w60,,marker,m,Nairobi,NAIROBI,,,,,,,,,,,,"), self.words, self.dur)
        foot = next(b for b in out.plan.beats if b.mode == "footage")
        move = next(s for b in out.plan.beats for s in b.camera if s.place == "Uganda")
        self.assertGreaterEqual(move.t, foot.end)

    def test_a_csv_without_a_camera_start_gets_one_and_says_so(self):
        out = plan_from_csv(self.csv("1,w0,,hud_title,,,PART 1,,,,,,,,,,,,", "1,w5,,marker,m,Kenya,KENYA,,,,,,,,,,,,"), self.words, self.dur)
        starts = [s for b in out.plan.beats for s in b.camera if s.action == "start"]
        self.assertEqual([s.place for s in starts], ["Kenya"])
        self.assertTrue(any("no camera start" in n for n in out.notes))

    def test_layers_hybrid_cannot_draw_yet_are_left_out_with_a_note_and_the_rest_imports(self):
        header = HEADER.replace("asset_path,", "asset_path,data_source,")
        text = "\n".join([header,
                          "1,w0,,camera,c0,Kenya,,,,,,,,,,start,country,,,",
                          "1,w0,,hud_title,,,PART 1,,,,,,,,,,,,,,",
                          '1,w5,,dots,d,Kenya,,,,,,,,,bundled:populated_places,,,,,"{""per_million"": 160}"',
                          "1,w8,,marker,m,Nairobi,NAIROBI,,,,,,,,,,,,,"])
        out = plan_from_csv(text, self.words, self.dur)
        self.assertTrue(any("dots" in n and "left out" in n for n in out.notes))
        self.assertEqual(sorted(l.type for b in out.plan.beats for l in b.layers), ["hud_title", "marker"])

    def test_a_fault_in_the_csv_is_reported_with_its_row_number(self):
        with self.assertRaises(CsvImportError) as cm:
            plan_from_csv(self.csv("1,w0,,camera,c0,Kenya,,,,,,,,,start,country,,,", "1,zzzz not spoken,,marker,m,Nairobi,NAIROBI,,,,,,,,,,,,"), self.words, self.dur)
        self.assertTrue(any("row 3" in p and "zzzz" in p for p in cm.exception.problems))
        with self.assertRaises(CsvImportError):
            plan_from_csv("not,a,hybrid,csv\n1,2,3,4", self.words, self.dur)

    def test_footage_at_the_very_start_still_gives_a_valid_plan(self):
        out = plan_from_csv(self.csv(
            "1,w0,,hud_title,,,PART 1,,,,,,,,,,,,",
            f"1,w0,,media_full,f1,,,,,,,,,stock_video:opening,,,,5,{FOOT}",
            "1,w20,,camera,c0,Kenya,,,,,,,,,start,country,,,",
            "1,w20,,marker,m,Nairobi,NAIROBI,,,,,,,,,,,,"), self.words, self.dur)
        self.assertEqual(out.plan.beats[0].mode, "footage")
        self.assertEqual(errs(out.plan), [])


if __name__ == "__main__":
    unittest.main()
