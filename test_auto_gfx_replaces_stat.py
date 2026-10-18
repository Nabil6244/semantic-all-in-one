"""Hybrid/pakMap "Add graphics from the narration": a graphic made from the narration replaces the plain stat box that shows the same number,
and nothing else. Run with: python -m unittest test_auto_gfx_replaces_stat"""
import unittest

import gfx_templates as G
from pakmap.compile import compile_csv
from pakmap.words import estimate_words

LEAD = "Canada is a vast country with many surprises waiting for anyone who looks at it closely. "
SIZE = LEAD + "It covers 9,984,670 square kilometres of land and water, nearly ten million. Then the story moves on to other things."
SHARE = LEAD + "About sixty percent of its lakes are unnamed, which surprises many people. Then the story moves on to other things."


def stat(id_, t_in, t_out, value, fmt, sub="X"):
    return {"id": id_, "type": "stat", "anchor": "br", "value_from": value, "value_to": value, "format": fmt, "sub": sub, "t_in": t_in, "t_out": t_out}


def _words(text):
    return estimate_words(text)


def _when(words, needle):
    for i, (w, a, _b) in enumerate(words):
        if needle in w:
            return a
    raise AssertionError(needle)


SECOND = LEAD + "It covers 9,984,670 square kilometres of land and water. Much later the story reaches another place entirely, and it is long and slow and quiet. " \
         "Nobody there is in any hurry at all today. People walk slowly along the shore and talk about the weather. The longest border on Earth runs for 8,891 square kilometres across the continent, which is hard to believe."
SAME = LEAD + "It covers 9,984,670 square kilometres of land and water. Much later the story reaches another place entirely, and it is long and slow and quiet. " \
       "Nobody there is in any hurry at all today. People walk slowly along the shore and talk about the weather. Once more it covers 9,984,670 square kilometres of land and water, said again for emphasis."


class TestRepeats(unittest.TestCase):
    def auto(self, text, **kw):
        # these tests are about the repeat rules of ONE layout (the planner may also pick another layout for the same kind of fact: test_hybrid_graphics_planning)
        kw.setdefault("enabled", ("big_number",))
        return G.auto_events(_words(text), niche="map", **kw)

    def test_the_same_template_comes_back_for_a_different_fact_that_stands_out(self):
        evs = self.auto(SECOND)
        self.assertEqual([e["template"]["id"] for e in evs], ["big_number", "big_number"])
        self.assertNotEqual(evs[0]["slots"]["value"], evs[1]["slots"]["value"])
        self.assertGreaterEqual(evs[1]["t_in"] - evs[0]["t_out"], G.SAME_TEMPLATE_GAP_S)

    def test_a_different_fact_that_does_not_stand_out_waits_for_the_window(self):
        plain = SECOND.replace("The longest border on Earth runs", "A border runs")
        self.assertEqual(len(self.auto(plain)), 1)

    def test_the_same_fact_again_is_a_near_duplicate_and_blocked(self):
        self.assertEqual(len(self.auto(SAME)), 1)

    def test_far_apart_the_same_template_is_free_again(self):
        filler = " ".join(["The road goes on and on through quiet country and nothing happens at all."] * 32)
        text = SIZE.replace("Then the story moves on to other things.", filler) + " The island reaches 8,891 square kilometres across, which is a lot of ground to cover."
        self.assertEqual([e["template"]["id"] for e in self.auto(text)], ["big_number", "big_number"])

    def test_running_twice_does_not_add_more(self):
        first = self.auto(SECOND)
        again = self.auto(SECOND, taken=[(e["t_in"], e["t_out"]) for e in first])
        self.assertEqual(again, [])


class TestFootage(unittest.TestCase):
    def media_row(self, t0, t1, cover=True):
        flag = "true" if cover else "false"
        return f"1,,,0,{t0},{t1},,media_full,f1,in,,,,,,,,,,,,,,,,,stock_video:a lake,,none,,\"{{\"\"cover_ui\"\":{flag}}}\","

    def compile(self, text, needle, cover=True):
        words = _words(text)
        t = _when(words, needle)
        return compile_csv(text=HEAD + self.media_row(t - 1, t + 9, cover) + "\n", words=words, validate=False, auto_templates=True)

    def test_a_number_said_over_covering_footage_is_drawn_over_it_and_flagged(self):
        res = self.compile(SIZE, "9,984,670")
        tpls = [e for e in res.spec["events"] if e["type"] == "map_template"]
        self.assertEqual([e["template"]["id"] for e in tpls], ["big_number"])
        self.assertTrue(tpls[0]["over_footage"])
        self.assertTrue(next(e for e in res.spec["events"] if e["id"] == "f1")["cover_ui"])      # the footage itself is untouched

    def test_a_plate_template_gets_a_local_backing_over_footage_so_the_clip_stays_visible(self):
        res = self.compile(SHARE, "sixty")
        ev = next(e for e in res.spec["events"] if e["type"] == "map_template")
        self.assertEqual(ev["template"]["id"], "ring_percent")
        self.assertTrue(ev["over_footage"])
        self.assertFalse(ev["template"]["plate"])
        self.assertNotIn("dim", ev["template"])                                  # no full-frame dim over the clip
        self.assertEqual(ev["template"]["shade"]["at"], [0.5, 0.5])             # a soft backing under the ring only

    def test_footage_that_does_not_cover_still_blocks_and_nothing_is_flagged(self):
        res = self.compile(SIZE, "9,984,670", cover=False)
        self.assertEqual([e["id"] for e in res.spec["events"] if e["type"] == "map_template"], [])

    def test_a_graphic_on_the_map_is_not_flagged(self):
        words = _words(SIZE)
        res = compile_csv(text=HEAD + "1,,,0,0.3,2.5,,stat,s2,in,,,,,,,,,,,OTHER,,7,7,0,br,,,,,,\n", words=words, validate=False, auto_templates=True)
        ev = next(e for e in res.spec["events"] if e["type"] == "map_template")
        self.assertNotIn("over_footage", ev)

    def test_an_explicit_template_row_can_ask_for_it_in_params(self):
        words = _words(SIZE)
        csv_text = ("item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,sub_text,value_to,params\n"
                    '1,Canada is a vast,template,,,FACT 1,THE COUNTRY,,"{""template"": ""yellow_tag"", ""over_footage"": true}"\n')
        res = compile_csv(text=csv_text, words=words, validate=False)
        self.assertTrue(next(e for e in res.spec["events"] if e["type"] == "map_template")["over_footage"])


class TestMeasurements(unittest.TestCase):
    def big(self, sentence):
        return G._big(G._spoken_number(sentence))

    def test_metres_keep_the_narrators_spelling_and_are_never_a_bare_M(self):
        self.assertEqual(self.big("The water can rise up to 16 meters, as tall as a building.")["unit"], "METERS")
        self.assertEqual(self.big("The wall stands 12 metres high above the sea.")["unit"], "METRES")

    def test_speeds_and_temperatures_are_facts_by_themselves(self):
        self.assertEqual((self.big("Winds reached 120 knots over the island.")["value"], self.big("Winds reached 120 knots over the island.")["unit"]), (120, "KT"))
        self.assertEqual(self.big("The storm gusted at 150 km/h near the coast.")["unit"], "KM/H")
        cold = self.big("Temperatures fell to -40 degrees Celsius in the night.")
        self.assertEqual((cold["value"], cold["unit"], cold["prefix"]), (40, "°C", "−"))       # the minus sign is kept, the number is not converted
        self.assertEqual(self.big("It hit 104 degrees Fahrenheit by noon.")["unit"], "°F")

    def test_a_small_measurement_needs_something_being_measured(self):
        self.assertIsNone(self.big("It was a 5 mile walk to town on a sunny day."))
        self.assertIsNone(self.big("Here are 5 facts about it."))
        self.assertEqual(self.big("The cliff is 80 feet tall at its edge.")["unit"], "FT")

    def test_no_unit_is_converted(self):
        self.assertEqual(self.big("The runway is 3 miles long and very wide.")["unit"], "MILES")
        self.assertEqual(self.big("The runway is 3 kilometres long and very wide.")["unit"], "KM")

    def test_the_planner_picks_the_graphic_from_the_trigger_words(self):
        words = _words(LEAD + "Winds reached 120 knots over the island, the strongest in years. Then the story moves on to other things entirely.")
        evs = G.auto_events(words, niche="map")
        self.assertEqual([(e["template"]["id"], e["slots"]["unit"]) for e in evs], [("big_number", "KT")])


class TestOverFootageTreatment(unittest.TestCase):
    TEXT = LEAD + "The water can rise up to 16 meters, as tall as a five story building. Then the story moves on to other things entirely."

    def run_it(self, **kw):
        words = _words(self.TEXT)
        t = _when(words, "16")
        return t, G.auto_events(words, niche="map", footage=[(t - 2, t + 12)], **kw)

    def test_a_measurement_over_footage_is_flagged_and_backed_locally_not_dimmed(self):
        _t, evs = self.run_it()
        self.assertEqual([e["template"]["id"] for e in evs], ["big_number"])
        ev = evs[0]
        self.assertTrue(ev["over_footage"])
        self.assertNotIn("dim", ev["template"])
        self.assertEqual(ev["template"]["shade"]["at"], [0.5, 0.52])          # centred on the number
        self.assertEqual(G.load_library()["big_number"]["dim"], 0.55)         # the library template keeps its own dim for the map

    def test_off_footage_the_template_is_exactly_as_before(self):
        words = _words(self.TEXT)
        ev = G.auto_events(words, niche="map")[0]
        self.assertNotIn("over_footage", ev)
        self.assertEqual(ev["template"]["dim"], 0.55)
        self.assertNotIn("shade", ev["template"])

    def test_a_graphic_waits_for_a_caption_that_is_only_just_ending(self):
        words = _words(self.TEXT)
        t = _when(words, "16")
        a = next(s[1] for s in G.sentences(words) if "16" in s[0])
        evs = G.auto_events(words, niche="map", footage=[(t - 2, t + 12)], taken=[(a - 3, a + 0.2)])
        self.assertEqual(len(evs), 1)
        self.assertAlmostEqual(evs[0]["t_in"], a + 0.2 + G.MIN_GAP_AFTER_S, places=2)

    def test_a_layer_that_starts_inside_its_window_still_blocks_it(self):
        words = _words(self.TEXT)
        a = next(s[1] for s in G.sentences(words) if "16" in s[0])
        self.assertEqual(G.auto_events(words, niche="map", footage=[(a - 2, a + 12)], taken=[(a + 1.0, a + 4)]), [])

    def test_a_late_start_is_not_taken_when_it_would_miss_the_words(self):
        words = _words(self.TEXT)
        a = next(s[1] for s in G.sentences(words) if "16" in s[0])
        self.assertEqual(G.auto_events(words, niche="map", footage=[(a - 2, a + 12)], taken=[(a - 3, a + 3.0)]), [])


class TestDocStyleOverFootage(unittest.TestCase):
    def test_an_eligible_title_and_caption_keep_their_flag_and_timing_and_an_ordinary_one_does_not(self):
        evs = [{"id": "t", "type": "hud_title", "label": "PART 1", "sub": "THE BAY", "t_in": 5.0, "t_out": 9.0, "over_footage": True},
               {"id": "c", "type": "caption", "text": "FOLLOW FOR MORE", "anchor": "bc", "t_in": 6.0, "t_out": 9.5, "over_footage": True},
               {"id": "u", "type": "hud_title", "label": "OTHER", "t_in": 5.0, "t_out": 9.0}]
        out = {e["id"]: e for e in G.apply_doc_style(evs)}
        for i in ("t", "c"):
            self.assertTrue(out[i]["over_footage"])
        self.assertEqual((out["t"]["t_in"], out["t"]["t_out"], out["c"]["t_in"], out["c"]["t_out"]), (5.0, 9.0, 6.0, 9.5))
        self.assertNotIn("over_footage", out["u"])
        self.assertEqual(out["t"]["slots"]["text"], "PART 1 · THE BAY")


class TestReplacement(unittest.TestCase):
    def run_auto(self, text, stats, **kw):
        words = _words(text)
        replaced = []
        evs = G.auto_events(words, niche="map", stats=stats, replaced=replaced, **kw)
        return words, evs, replaced

    def test_big_number_replaces_the_stat_that_shows_the_same_number(self):
        words = _words(SIZE)
        t = _when(words, "9,984,670")
        s = stat("b2_stat3", t, t + 4, 9984670, "#,##0 KM²", "AREA")
        _w, evs, replaced = self.run_auto(SIZE, [s])
        self.assertEqual([e["template"]["id"] for e in evs], ["big_number"])
        self.assertEqual(replaced, ["b2_stat3"])

    def test_scale_words_in_the_stat_format_count(self):
        words = _words(LEAD + "It covers almost 10 million square kilometres. Then the story moves on to other things.")
        t = _when(words, "10")
        s = stat("s", t, t + 4, 10.0, "0 MILLION KM²")
        replaced = []
        evs = G.auto_events(words, niche="map", stats=[s], replaced=replaced)
        self.assertEqual(([e["template"]["id"] for e in evs], replaced), (["big_number"], ["s"]))

    def test_ring_percent_replaces_a_percentage_stat(self):
        words = _words(SHARE)
        t = _when(words, "sixty")
        s = stat("b4_stat2", t + 1, t + 5, 60, "0%", "OF LAKES")
        _w, evs, replaced = self.run_auto(SHARE, [s])
        self.assertEqual([e["template"]["id"] for e in evs], ["ring_percent"])
        self.assertEqual(replaced, ["b4_stat2"])

    def test_an_unrelated_stat_stays_and_still_blocks_the_graphic(self):
        words = _words(SIZE)
        t = _when(words, "9,984,670")
        s = stat("other", t, t + 4, 12, "0 YEARS")
        _w, evs, replaced = self.run_auto(SIZE, [s])
        self.assertEqual((evs, replaced), ([], []))

    def test_a_stat_that_does_not_overlap_the_moment_is_left_alone(self):
        words = _words(SIZE)
        s = stat("far", 0.0, 1.5, 9984670, "#,##0 KM²")
        _w, evs, replaced = self.run_auto(SIZE, [s])
        self.assertEqual(replaced, [])
        self.assertEqual([e["template"]["id"] for e in evs], ["big_number"])   # nothing was in its way, so it is simply added

    def test_a_graphic_that_cannot_be_drawn_leaves_the_stat_alone(self):
        words = _words(SIZE)
        t = _when(words, "9,984,670")
        s = stat("b2_stat3", t, t + 4, 9984670, "#,##0 KM²")
        lib = G.load_library()
        was = lib["big_number"]["slots"]["label"].get("required")
        lib["big_number"]["slots"]["label"]["required"] = True
        orig, old = G._big, G.AUTO[:]
        try:
            blank = lambda sentence: {**orig(sentence), "label": ""}        # the narration gave no caption and the template needs one
            G.AUTO[:] = [(a, b, blank if c is orig else c) for a, b, c in old]
            replaced = []
            evs = G.auto_events(words, niche="map", stats=[s], replaced=replaced)
        finally:
            G.AUTO[:] = old
            lib["big_number"]["slots"]["label"]["required"] = was
        self.assertEqual((evs, replaced), ([], []))

    def test_running_the_step_twice_does_not_duplicate(self):
        words = _words(SIZE)
        t = _when(words, "9,984,670")
        s = stat("b2_stat3", t, t + 4, 9984670, "#,##0 KM²")
        _w, evs, replaced = self.run_auto(SIZE, [s])
        taken = [(e["t_in"], e["t_out"]) for e in evs]
        remaining = [x for x in [s] if x["id"] not in replaced]
        again = G.auto_events(words, niche="map", taken=taken, stats=remaining, replaced=[])
        self.assertEqual(again, [])

    def test_without_the_stats_argument_nothing_changed(self):
        words = _words(SIZE)
        self.assertEqual(G.auto_events(words, niche="map"), G.auto_events(words, niche="map", stats=(), replaced=[]))


HEAD = ("item_no,beat,vo_anchor,offset_s,t_start,t_end,hold,layer_type,layer_id,layer_action,camera_action,camera_dur,lat,lon,zoom,frame,easing,geo_ref,"
        "line_kind,label_text,sub_text,color_role,value_from,value_to,value_format,anchor,asset_path,data_source,sfx,ambience,params,notes\n")


class TestThroughTheCompiler(unittest.TestCase):
    def build(self, t):
        rows = [
            f"1,,,0,{t},{t + 4},,stat,s1,in,,,,,,,,,,,AREA,,9984670,9984670,\"#,##0 KM²\",br,,,,,,",
            f"1,,,0,{t},{t + 4},,pip,p1,in,,,,,,,,,,CANADA,,,,,,tr,stock_image:a lake,,,,,",
            f"1,,,0,{t},{t + 4},,zone_label,z1,in,,,,,,,,\"44.0,-55.0\",,ATLANTIC OCEAN,,neutral,,,,,,,,,,",
            f"1,,,0,0.3,2.5,,stat,s2,in,,,,,,,,,,,OTHER,,7,7,0,br,,,,,,",
        ]
        return HEAD + "\n".join(rows) + "\n"

    def compile(self, auto):
        words = _words(SIZE)
        t = _when(words, "9,984,670")
        return compile_csv(text=self.build(t), words=words, validate=False, auto_templates=auto)

    def test_the_stat_is_replaced_and_the_photo_card_label_and_other_stat_survive(self):
        ev = {e["id"]: e for e in self.compile(True).spec["events"]}
        self.assertNotIn("s1", ev)
        self.assertEqual([e["template"]["id"] for e in ev.values() if e["type"] == "map_template"], ["big_number"])
        for keep in ("p1", "z1", "s2"):
            self.assertIn(keep, ev)

    def test_with_doc_style_a_unit_stat_becomes_the_compact_card_and_sits_with_the_title_chip(self):
        words = _words(SIZE)
        t = _when(words, "9,984,670")
        csv_text = self.build(t) + f"1,,,0,{t - 1},{t + 6},,hud_title,h1,in,,,,,,,,,,FACT 1,THE SIZE,,,,,,,,,,,\n"
        res = compile_csv(text=csv_text, words=words, validate=False, auto_templates=True, doc_style=True)
        ids = [e["template"]["id"] for e in res.spec["events"] if e["type"] == "map_template"]
        self.assertIn("yellow_tag", ids)
        self.assertEqual(ids.count("counter_corner"), 2)                           # the unit stat and the plain one: small cards, not the big native chip
        self.assertNotIn("big_number", ids)                                        # the compact card already shows that number
        self.assertEqual([e["id"] for e in res.spec["events"] if e["type"] == "stat"], [])

    def test_with_the_switch_off_the_plan_is_exactly_as_before(self):
        ev = {e["id"] for e in self.compile(False).spec["events"]}
        self.assertEqual(ev, {"s1", "p1", "z1", "s2"})

    def test_a_legacy_plan_without_template_rows_compiles_and_the_report_has_no_dangling_event(self):
        res = self.compile(True)
        self.assertEqual({e.id for e in res.report.events}, {e["id"] for e in res.spec["events"]})

    def test_existing_template_rows_still_render(self):
        words = _words(SIZE)
        csv_text = ("item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,sub_text,value_to,params\n"
                    '1,Canada is a vast,template,,,FACT 1,THE COUNTRY,,"{""template"": ""yellow_tag""}"\n')
        res = compile_csv(text=csv_text, words=words, validate=False, auto_templates=True)
        self.assertIn("yellow_tag", [e["template"]["id"] for e in res.spec["events"] if e["type"] == "map_template"])


if __name__ == "__main__":
    unittest.main()
