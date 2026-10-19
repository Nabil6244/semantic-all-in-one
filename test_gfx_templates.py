"""gfx_templates.py: the universal template library on the planner's side, and its pakMap hook (layer_type template, auto templates)."""
import json
import pathlib
import unittest

import gfx_templates as G
from pakmap.compile import CompileError, compile_csv, compile_rows
from pakmap.schema import parse_csv
from pakmap.words import estimate_words

ROOT = pathlib.Path(__file__).resolve().parent
SAMPLE = ROOT / "pakmap-engine" / "samples" / "canada-10-facts"


def _csv(*rows):
    head = "item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,sub_text,value_to,params\n"
    return head + "\n".join(rows) + "\n"


class TestLibrary(unittest.TestCase):
    def test_every_template_is_valid_and_has_niches(self):
        lib = G.load_library()
        self.assertGreaterEqual(len(lib), 30)
        self.assertEqual([p for t in lib.values() for p in G.validate(t)], [])
        for t in lib.values():
            self.assertTrue(t["niches"], t["id"])

    def test_unknown_template_names_a_close_one(self):
        with self.assertRaisesRegex(ValueError, "rank_bars"):
            G.get("rank_bar")

    def test_catalog_lists_columns(self):
        self.assertIn("rank_bars [stats] reads label*, rows*", G.catalog_text("map"))


class TestSlots(unittest.TestCase):
    def test_rows_values_labels_parse(self):
        self.assertEqual(G.parse_rows("CANADA@orange=202,080; NORWAY=83281"), [{"label": "CANADA", "value": 202080.0, "text": "202,080", "color": "orange"}, {"label": "NORWAY", "value": 83281.0, "text": "83281"}])
        self.assertEqual(G.parse_rows("A|B|C")[1]["label"], "B")
        self.assertEqual(G.parse_list("1;2;3", numbers=True), [1.0, 2.0, 3.0])
        self.assertEqual(G.parse_list("J;F;M"), ["J", "F", "M"])

    def test_a_required_slot_the_row_left_empty_is_an_error_not_the_example(self):
        t = G.get("rank_bars")
        with self.assertRaisesRegex(ValueError, "needs title.*rows|needs rows"):
            G.slots_from_fields(t, {"label": "", "sub": "KM"})
        ok = G.slots_from_fields(t, {"label": "COASTLINE", "text": "A=1; B=2", "sub": "KM"})
        self.assertEqual(ok["rows"][1], {"label": "B", "value": 2.0, "text": "2"})
        self.assertEqual(ok["title"], "COASTLINE")

    def test_a_heading_may_come_from_label_or_text(self):
        t = G.get("versus_numbers")
        s = G.slots_from_fields(t, {"label": "HEAD TO HEAD"}, {"a_label": "A", "a_value": 1, "b_label": "B", "b_value": 2})
        self.assertEqual(s["title"], "HEAD TO HEAD")

    def test_cues_are_found_in_the_narration(self):
        t = {"items": [{"in": "@photon"}]}
        words = [("The", 1.0, 1.2), ("photon", 2.5, 3.0)]
        self.assertEqual(G.find_cues(t, words, 2.0, 6.0), {"photon": 0.5})


class TestAuto(unittest.TestCase):
    WORDS = estimate_words("Canada is a vast country with many surprises waiting for anyone who looks at it closely. About sixty percent of its lakes are unnamed, "
                           "which surprises many people who have never been there. Travellers often say the distances are hard to picture until they drive them. "
                           "Canada covers 9,984,670 square kilometres of land and water, nearly ten million. "
                           "Forty percent of it is forest and the rest is tundra and farmland across the country.")

    def test_a_stated_share_and_size_get_the_right_graphic_with_the_numbers_said(self):
        evs = G.auto_events(self.WORDS, niche="map")
        by = {e["template"]["id"]: e for e in evs}
        self.assertEqual(by["ring_percent"]["slots"]["value"], 60)
        self.assertEqual(by["big_number"]["slots"]["value"], 9984670)
        self.assertIn("KM²", by["big_number"]["slots"]["unit"])

    def test_pacing_spacing_taken_windows_and_opening(self):
        evs = G.auto_events(self.WORDS, niche="map")
        for a, b in zip(evs, evs[1:]):
            self.assertGreaterEqual(b["t_in"] - a["t_out"], G.MIN_SPACING_S - 1e-6)
        self.assertTrue(all(e["t_in"] >= G.FIRST_AT_S for e in evs))
        blocked = G.auto_events(self.WORDS, niche="map", taken=[(0, 500)])
        self.assertEqual(blocked, [])

    def test_a_year_or_a_small_bare_number_is_not_a_headline(self):
        self.assertIsNone(G._big("It happened in 1998."))
        self.assertIsNone(G._big("There are 12 of them."))
        self.assertIsNone(G._percent("It grew 400 percent."))

    def test_other_niches_do_not_get_map_only_templates(self):
        lib = G.load_library()
        got = G.auto_events(self.WORDS, niche="weather")
        self.assertTrue(all("any" in lib[e["template"]["id"]]["niches"] for e in got), [e["template"]["id"] for e in got])      # only graphics made for every niche


class TestPakmapHook(unittest.TestCase):
    def test_a_template_row_becomes_a_map_template_event_with_cues_and_hold(self):
        text = "Fact one. Canada holds about sixty percent of the lakes. Most have no name at all."
        res = compile_csv(text=_csv('1,Fact one,hud_title,,,PART 1,,,',
                                    '1,sixty percent,template,,,FACT 1 · LAKES,OF ALL LAKES,60,"{""template"": ""ring_percent""}"'),
                          words=estimate_words(text), validate=False)
        ev = next(e for e in res.spec["events"] if e["type"] == "map_template")
        self.assertEqual(ev["template"]["id"], "ring_percent")
        self.assertEqual(ev["slots"]["value"], 60)
        self.assertNotIn("_hold", ev)
        self.assertGreater(ev["t_out"], ev["t_in"])

    def test_a_missing_required_value_stops_the_compile_naming_the_row(self):
        with self.assertRaises(CompileError) as cm:
            compile_csv(text=_csv('1,Fact one,template,,,FACT 1,,,"{""template"": ""ring_percent""}"'), words=estimate_words("Fact one is here."), validate=False)
        self.assertIn("row 2", str(cm.exception)); self.assertIn("value", str(cm.exception))

    def test_an_unknown_template_id_is_explained(self):
        with self.assertRaises(CompileError) as cm:
            compile_csv(text=_csv('1,Fact one,template,,,X,,,"{""template"": ""rank_bar""}"'), words=estimate_words("Fact one."), validate=False)
        self.assertIn("rank_bars", str(cm.exception))

    def test_region_label_follows_the_centre_of_the_region(self):
        res = compile_csv(text=_csv('1,Fact one,template,,Nunavut,NUNAVUT,,,"{""template"": ""region_label""}"'), words=estimate_words("Fact one is Nunavut."), validate=False)
        f = next(e for e in res.spec["events"] if e["type"] == "map_template")["follow"]
        self.assertTrue(-120 < f["lon"] < -60 and 60 < f["lat"] < 80, f)

    def test_auto_templates_are_added_only_when_asked(self):
        rows, _ = parse_csv(None, text=_csv('1,Canada,hud_title,,,PART 1,,,'))
        words = TestAuto.WORDS
        off = compile_rows(rows, words, validate=False)
        on = compile_rows(rows, words, validate=False, auto_templates=True)
        self.assertFalse([e for e in off.spec["events"] if e["type"] == "map_template"])
        self.assertTrue([e for e in on.spec["events"] if e["type"] == "map_template"])


class TestPrompt(unittest.TestCase):
    def test_the_pakmap_prompt_lists_the_templates_and_no_placeholder_is_left(self):
        from app_csv_prompts import TEMPLATE_PLACEHOLDER, build_prompt

        text = build_prompt("pakmap", "Canada has many lakes.", graphics=True)
        self.assertNotIn(TEMPLATE_PLACEHOLDER, text)
        self.assertIn("rank_bars [stats] reads label*, rows*", text)
        self.assertIn("fact_card [facts]", text)
        self.assertIn("Canada has many lakes.", text)
        # the switch off: the prompt is exactly the one the style always had (no template section, no catalog)
        plain = build_prompt("pakmap", "Canada has many lakes.")
        self.assertNotIn("template:", plain); self.assertNotIn("TEMPLATES", plain); self.assertNotIn("rank_bars", plain)

    def test_the_toggle_reaches_the_planner(self):
        from pakmap.app_integration import check_pakmap_plan

        words = TestAuto.WORDS
        import tempfile

        csv = pathlib.Path(tempfile.mkdtemp()) / "s.csv"
        csv.write_text(_csv('1,Canada is a vast,hud_title,,,PART 1,,,'), encoding="utf-8")
        _r_off, _rep, _p = check_pakmap_plan(csv, words, duration=60.0)
        _r_on, _rep2, _p2 = check_pakmap_plan(csv, words, duration=60.0, auto_templates=True)
        n = lambda r: len([e for e in r.spec["events"] if e["type"] == "map_template"]) if r else -1
        self.assertEqual(n(_r_off), 0)
        self.assertGreater(n(_r_on), 0)


class TestCanadaSample(unittest.TestCase):
    def test_the_ten_facts_sample_compiles_and_passes_the_engine_rules(self):
        res = compile_csv(f"{SAMPLE}.csv", estimate_words(pathlib.Path(f"{SAMPLE}.txt").read_text()))
        self.assertEqual(res.report.errors, [])
        used = [e["template"]["id"] for e in res.spec["events"] if e["type"] == "map_template"]
        for t in ("fact_title", "ring_percent", "big_number", "rank_bars", "versus_numbers", "month_columns", "trend_line", "top_list", "region_label", "fact_card"):
            self.assertIn(t, used)
        self.assertEqual(used.count("fact_card"), 2)
        json.dumps(res.spec)   # serialisable for the renderer


if __name__ == "__main__":
    unittest.main()


class TestDocStyle(unittest.TestCase):
    EV = [
        {"id": "t", "type": "hud_title", "label": "PART 1", "sub": "THE EMPTY HALF", "t_in": 0.3, "t_out": 5.0},
        {"id": "c", "type": "caption", "text": "THE NORTH IS ANOTHER STORY", "anchor": "bc", "t_in": 6.0, "t_out": 9.0},
        {"id": "s", "type": "stat", "value_from": 0, "value_to": 47, "format": "#,##0", "sub": "KENYA", "anchor": "br", "t_in": 10.0, "t_out": 14.0},
        {"id": "s2", "type": "stat", "value_from": 40, "value_to": 47, "format": "0 MILLION PEOPLE", "sub": "KENYA", "anchor": "br", "t_in": 15.0, "t_out": 18.0},
        {"id": "m", "type": "marker", "lon": 1.0, "lat": 2.0, "label": "NAIROBI", "t_in": 1.0, "t_out": 4.0},
    ]

    def test_titles_captions_and_whole_number_counters_get_the_news_look_with_the_same_ids_and_times(self):
        out = {e["id"]: e for e in G.apply_doc_style(self.EV)}
        self.assertEqual(out["t"]["template"]["id"], "yellow_tag")
        self.assertEqual(out["t"]["slots"]["text"], "PART 1 · THE EMPTY HALF")
        self.assertEqual((out["t"]["t_in"], out["t"]["t_out"]), (0.3, 5.0))
        self.assertEqual(out["c"]["template"]["id"], "typed_caption")
        self.assertEqual(out["s"]["template"]["id"], "counter_corner")
        self.assertEqual(out["s"]["slots"], {"value": 47, "label": "KENYA", "anchor": "br"})

    def test_what_has_no_faithful_twin_is_left_alone(self):
        out = {e["id"]: e for e in G.apply_doc_style(self.EV)}
        self.assertEqual(out["s2"]["type"], "stat")        # counts from 40 and has a unit: the native chip stays
        self.assertEqual(out["m"]["type"], "marker")

    def test_the_switch_reaches_the_compiler_and_the_engine_accepts_the_result(self):
        text = "Fact one. Kenya has forty seven million people. The north is another story."
        csv_text = _csv('1,Fact one,hud_title,,,PART 1,THE EMPTY HALF,,', '1,north is another,caption,,,THE NORTH IS ANOTHER STORY,,,')
        off = compile_csv(text=csv_text, words=estimate_words(text))
        on = compile_csv(text=csv_text, words=estimate_words(text), doc_style=True)
        self.assertEqual({e["type"] for e in off.spec["events"]}, {"hud_title", "caption"})
        self.assertEqual({e["type"] for e in on.spec["events"]}, {"map_template"})
        self.assertEqual(on.report.errors, [])


class TestMoreAuto(unittest.TestCase):
    @staticmethod
    def _where(name):
        from pakmap.geo import resolve

        try:
            loc = resolve(name, "point")
            return (loc.lon, loc.lat)
        except Exception:
            return None

    def test_a_comparison_a_year_and_a_journey_get_their_graphics(self):
        words = estimate_words("This story is about a very large country that most travellers underestimate before they come. In 1947 the border was drawn across the map by a "
                               "commission that never visited the land. Many travellers still cross it every single day without noticing anything unusual at all along the way. "
                               "Russia is nearly twice as large as Canada, which surprises most visitors and often starts long arguments over dinner. A fact worth remembering "
                               "when planning any long journey through either place, because the distances are hard to picture until you drive them yourself. "
                               "The railway runs from Vancouver to Halifax across five time zones.")
        evs = G.auto_events(words, niche="map", resolve=self._where)
        by = {e["template"]["id"]: e for e in evs}
        self.assertEqual(by["year_wipe"]["slots"]["text"], "1947")
        self.assertEqual((by["big_number"]["slots"]["value"], by["big_number"]["slots"]["unit"]), (2, "×"))
        self.assertIn("CANADA", by["big_number"]["slots"]["label"])
        self.assertEqual(by["route_travel"]["slots"]["to_label"], "HALIFAX")
        self.assertEqual(len(by["route_travel"]["slots"]["points"]), 2)

    def test_a_journey_needs_both_places_to_be_found(self):
        self.assertIsNone(G._route("It runs from Nowhereville to Atlantis.", lambda n: None))
        self.assertIsNone(G._route("It runs from Vancouver to Halifax.", None))


class TestSoundAndGeoRows(unittest.TestCase):
    def test_a_graphic_makes_the_sound_of_what_it_draws_and_restraint_applies(self):
        from pakmap.audio_plan import plan_audio

        evs = [{"id": "a", "type": "map_template", "t_in": 3.0, "t_out": 9.0, "template": G.get("fact_card")},
               {"id": "b", "type": "map_template", "t_in": 12.0, "t_out": 18.0, "template": G.get("route_travel")},
               {"id": "c", "type": "map_template", "t_in": 20.0, "t_out": 24.0, "template": G.get("typed_caption")}]
        plan = plan_audio({"duration": 30, "events": evs, "camera": {"start": {"lon": 0, "lat": 0, "zoom": 3}, "moves": []}})
        self.assertEqual([(c.sound, c.source) for c in plan.cues], [("deep_thud", "a"), ("directional_whoosh", "b"), ("ui_click", "c")])   # every graphic has a sound now (the typed caption clicks)
        self.assertEqual(plan.silent, [])

    def test_a_template_can_set_or_silence_its_own_sound(self):
        t = {**G.get("fact_card"), "sfx": [{"at": 0.5, "sound": "cash_register"}]}
        self.assertEqual(G.sfx_cues({"template": t}), [(0.5, "cash_register", "graphic fact_card")])
        self.assertEqual(G.sfx_cues({"template": {**t, "sfx": []}}), [])

    def test_every_sound_the_graphics_use_exists_in_the_pakmap_vocabulary(self):
        from pakmap.sounds import SOUNDS

        for s in list(G.PRIM_SOUND.values()) + list(G.TEXT_STYLE_SOUND.values()):
            self.assertIn(s, SOUNDS, s)

    def test_a_route_row_gets_its_places_a_region_row_its_outline_and_a_location_card_its_coordinates(self):
        words = estimate_words("Fact one. The strait is narrow. From Vancouver to Ottawa is far.")
        csv_text = _csv('1,Fact one,hud_title,,,PART 1,,,',
                        '1,strait is narrow,template,,Vancouver,VANCOUVER,x,,"{""template"":""location_card""}"',
                        '1,From Vancouver,template,,Vancouver;Ottawa,,,,"{""template"":""route_travel""}"',
                        '1,far,template,,Canada,CANADA,,,"{""template"":""region_spotlight""}"')
        res = compile_csv(text=csv_text, words=words, validate=False)
        by = {e["template"]["id"]: e for e in res.spec["events"] if e["type"] == "map_template"}
        self.assertTrue(by["location_card"]["slots"]["coords"].startswith("49.28°N"))
        self.assertEqual(len(by["route_travel"]["slots"]["points"]), 2)
        polys = by["region_spotlight"]["slots"]["polys"]
        self.assertTrue(0 < len(polys) <= 150 and all(len(r) >= 4 for p in polys for r in p))


class TestGraphicsPromptsExamplesWork(unittest.TestCase):
    """With the switch on the prompts carry template rows in their examples: those examples must load through the real importers."""

    @staticmethod
    def _parts(text):
        script = text.split("Script:\n", 1)[1].split("\n\nCSV:\n", 1)[0].strip()
        csv_text = text.split("\n\nCSV:\n", 1)[1].split("\n\nNOW WRITE", 1)[0].strip() + "\n"
        return script, csv_text

    def test_the_pakmap_graphics_prompt_example_compiles_with_its_template_rows(self):
        from app_csv_prompts import build_prompt

        script, csv_text = self._parts(build_prompt("pakmap", graphics=True))
        words = estimate_words(script)
        res = compile_csv(text=csv_text, words=words, duration=words[-1][2] + 1.0)
        self.assertEqual(res.report.errors, [])
        self.assertTrue([e for e in res.spec["events"] if e["type"] == "map_template"])

    def test_the_hybrid_graphics_prompt_example_loads_and_compiles(self):
        from app_csv_prompts import build_prompt
        from hybrid.beat_csv import plan_from_csv
        from hybrid.compile import compile_plan

        script, csv_text = self._parts(build_prompt("hybrid", graphics=True))
        words = estimate_words(script)
        plan = plan_from_csv(csv_text, words, words[-1][2] + 0.5)
        self.assertTrue([l for b in plan.beats for l in b.layers if l.type == "template"])
        res = compile_plan(plan, validate=False)
        self.assertTrue([e for e in res.spec["events"] if e["type"] == "map_template"])
