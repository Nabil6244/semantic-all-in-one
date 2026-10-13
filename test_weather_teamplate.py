"""Weather Teamplate (weather/teamplate): the edit it applies to the plan and the compiled spec, its footage rules, and that the
Weather style's output is unchanged when the style is not picked. The renderer is faked (the real graphics are checked by
weather-engine/test/tp_*.test.mjs)."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from weather import teamplate as tp
from weather.teamplate.footage import conflicts, prefer_library_strict, relevance_problems, split_long_shots

import test_weather_render as twr
from test_weather_render import WORDS

ROOT = Path(__file__).resolve().parent
HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"


def spec():
    return {
        "width": 1920, "height": 1080, "fps": 30, "duration": 60.0,
        "camera": {"start": {"lon": -71, "lat": 19, "zoom": 1.7}, "moves": [
            {"type": "fly_to", "t": 1.4, "dur": 2.2, "to": {"zoom": 5.3, "lon": -76.6, "lat": 20.4}},
            {"type": "fly_to", "t": 20.0, "dur": 2.4, "to": {"zoom": 5.8, "lon": -83.8, "lat": 28.1}}]},
        "events": [
            {"id": "t1", "type": "hud_title", "label": "HURRICANE IAN", "sub": "SEPTEMBER 2022", "t_in": 0.0, "t_out": 20.0},
            {"id": "t2", "type": "hud_title", "label": "WARNINGS AND RAIN", "sub": "WEDNESDAY", "t_in": 20.0, "t_out": 45.0},
            {"id": "c1", "type": "media_full", "media": "clip.mp4", "dissolve_s": 0.5, "cover_ui": True, "kenburns": "auto", "t_in": 45.0, "t_out": 60.0},
        ],
    }


def part():
    return {"events": [
        {"id": "wx_ew", "type": "counter", "t_in": 20.0, "t_out": 45.0, "value": 5, "label": "EXTREME WIND WARNINGS ISSUED", "sub": "NWS", "count_s": 2.0},
        {"id": "wx_fm", "type": "place_label", "lon": -81.87, "lat": 26.64, "text": "FORT MYERS", "t_in": 18.0, "t_out": 45.0},
        {"id": "wx_src", "type": "source_line", "text": "Data: NOAA", "t_in": 0.0, "t_out": 45.0},
    ], "satellite": [], "rasters": [], "credits": []}


class Names(unittest.TestCase):
    def test_only_the_teamplate_names_pick_it(self):
        self.assertEqual(tp.normalize("teamplate"), "teamplate")
        self.assertEqual(tp.normalize("Weather Teamplate"), "teamplate")
        for other in (None, "", "classic", "Weather", "something else"):
            self.assertEqual(tp.normalize(other), "classic")


class Spec(unittest.TestCase):
    def setUp(self):
        self.spec, self.part = spec(), part()
        self.before = json.dumps([self.spec, self.part])
        self.s, self.p = tp.apply_spec(self.spec, self.part)
        self.wx = {e["id"]: e for e in self.p["events"]}

    def test_the_callers_dicts_are_not_changed(self):
        self.assertEqual(json.dumps([self.spec, self.part]), self.before)

    def test_titles_become_a_chapter_card_then_keyword_cards_with_a_context_tag(self):
        self.assertFalse([e for e in self.s["events"] if e["type"] == "hud_title"])
        ch, kw, tag = self.wx["tp_t1"], self.wx["tp_t2"], self.wx["tp_t2_tag"]
        self.assertEqual((ch["kind"], ch["title"], ch["kicker"]), ("chapter", "HURRICANE IAN", "SEPTEMBER 2022"))
        self.assertEqual((kw["kind"], kw["words"], kw["accent"]), ("keyword", ["WARNINGS", "AND", "RAIN"], 2))
        self.assertLessEqual(kw["t_out"] - kw["t_in"], tp.KEYWORD_HOLD_S + 1e-9)
        self.assertEqual(tag["text"], "WEDNESDAY")
        self.assertGreaterEqual(tag["t_in"], kw["t_out"])
        self.assertLessEqual(tag["t_out"], 45.0)

    def test_the_key_word_can_be_marked(self):
        self.assertEqual(tp.split_keyword("*BOTTOM* OF BLUFF"), {"words": ["BOTTOM", "OF", "BLUFF"], "accent": 0})

    def test_footage_cuts_and_the_map_is_graded(self):
        clip = next(e for e in self.s["events"] if e["type"] == "media_full")
        self.assertAlmostEqual(clip["dissolve_s"], tp.CUT_S)
        self.assertEqual(self.s["imagery"]["grade"], tp.MAP_GRADE)

    def test_the_map_cuts_between_beats_and_keeps_its_opening_move(self):
        moves = self.s["camera"]["moves"]
        self.assertEqual(moves[0]["type"], "fly_to")   # the establishing move from the globe
        cut = moves[1]
        self.assertEqual(cut["type"], "push_in")
        self.assertLess(cut["dur"], 1.0 / 30 + 1e-9)
        self.assertEqual((cut["to"]["lon"], cut["to"]["lat"]), (-83.8, 28.1))
        self.assertAlmostEqual(cut["t"] * 30, round(cut["t"] * 30))   # on a frame
        prev_end = 0.0
        for m in moves:   # no overlaps, nothing under the footage (45-60 s)
            self.assertGreaterEqual(m["t"], prev_end - 1e-9)
            prev_end = m["t"] + m["dur"]
            self.assertLessEqual(prev_end, 45.0)

    def test_a_keyword_card_waits_for_the_map_cut_it_belongs_to(self):
        sp = spec()
        sp["camera"]["moves"][1]["t"] = 20.4   # Hybrid starts the move a little after the beat
        s, p = tp.apply_spec(sp, part())
        cut = next(m for m in s["camera"]["moves"] if m["type"] == "push_in")
        card = next(e for e in p["events"] if e["id"] == "tp_t2")
        self.assertGreater(card["t_in"], cut["t"] + cut["dur"])

    def test_a_counter_waits_for_the_title_card_and_keeps_its_value_and_words(self):
        st = self.wx["wx_ew"]
        self.assertEqual(st["type"], "tp_stat")
        self.assertEqual((st["value"], st["label"], st["sub"]), (5, "EXTREME WIND WARNINGS ISSUED", "NWS"))
        self.assertGreaterEqual(st["big_in"], self.wx["tp_t2"]["t_out"])
        self.assertLessEqual(st["big_out"], st["t_out"])

    def test_place_tags_step_aside_while_a_card_is_up(self):
        pl = self.wx["wx_fm"]
        self.assertEqual(pl["type"], "tp_place")
        self.assertTrue(any(a <= self.wx["tp_t2"]["t_in"] and b >= self.wx["tp_t2"]["t_out"] for a, b in pl["hide"]))

    def test_every_word_on_screen_was_already_in_the_plan_or_the_data(self):
        def strings(objs):
            out = set()
            for e in objs:
                for k in ("label", "sub", "text", "title", "kicker"):
                    if e.get(k):
                        out.add(str(e[k]))
                out.update(e.get("words") or [])
            return out
        before = strings(self.spec["events"] + self.part["events"])
        before |= {w for s in before for w in s.split()}
        self.assertLessEqual(strings(self.s["events"] + self.p["events"]), before)

    def test_a_data_graphic_arriving_under_a_card_comes_in_after_it(self):
        pa = part()
        pa["events"].append({"id": "wx_rec", "type": "post_record", "value": "16.07 IN", "t_in": 20.2, "t_out": 40.0})
        s, p = tp.apply_spec(spec(), pa)
        rec = next(e for e in p["events"] if e["id"] == "wx_rec")
        card = next(e for e in p["events"] if e["id"] == "tp_t2")
        self.assertGreaterEqual(rec["t_in"], card["t_out"])
        self.assertEqual((rec["value"], rec["t_out"]), ("16.07 IN", 40.0))

    def test_unknown_weather_graphics_pass_through_unchanged(self):
        self.assertEqual(self.wx["wx_src"], self.part["events"][2])


class FootageRules(unittest.TestCase):
    def plan(self, rows, dur=20.0):
        from hybrid.beat_csv import plan_from_csv

        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("damaging winds swept across wyoming on tuesday and here is more".split())]
        return plan_from_csv(HEAD + rows, words, dur)

    def test_tropical_footage_on_a_wyoming_wind_story_is_refused(self):
        self.assertTrue(conflicts("palm trees bending in a tropical storm", "damaging winds swept across Wyoming on Tuesday"))
        self.assertFalse(conflicts("prairie grass whipping in strong wind gusts", "damaging winds swept across Wyoming on Tuesday"))
        self.assertTrue(conflicts("heatwave over a sunny city street", "heavy snow and blowing snow closed the interstate"))
        self.assertFalse(conflicts("dark storm clouds over farmland", "heavy rain flooded farm roads in Iowa"))
        self.assertFalse(conflicts("waves crashing on the beach", "the hurricane's surge reached the coast"))

    def test_relevance_problems_name_the_beat_and_ignore_your_own_files(self):
        p = self.plan('b1,beat,damaging winds,footage,,,,,,,"damaging winds swept across wyoming on tuesday",,,,,,,,,,,one\n'
                      "b1,clip,,,,,,,,,,,,,,,,,,stock_video:palm trees bending in a tropical storm,,why\n"
                      'b2,beat,and here is,footage,,,,,,,"and here is more",,,,,,,,,,,two\n'
                      "b2,clip,,,,,,,,,,,,,,,,,,media/palms_tropical.mp4,,why\n")
        probs = relevance_problems(p)
        self.assertEqual(len(probs), 1)
        self.assertIn("beat b1", probs[0])
        self.assertIn("tropical", probs[0])

    def test_a_long_stock_shot_is_cut_into_five_second_shots_of_the_same_subject(self):
        p = self.plan('b1,beat,damaging winds,footage,,,,,,,"damaging winds swept across wyoming on tuesday",,,,,,,,,,,one\n'
                      "b1,clip,,,,,,,,,,,,,,,,,,stock_video:prairie grass in strong wind,,why\n", dur=15.0)
        notes = []
        split_long_shots(p, notes)
        assets = [c.asset for c in p.beats[0].clips]
        self.assertEqual(len(assets), 3)
        self.assertEqual(len(set(assets)), 3)   # each its own request, so the providers fetch three different clips
        self.assertTrue(all(a.startswith("stock_video:prairie grass in strong wind") for a in assets))
        self.assertTrue(notes)

    def test_event_footage_and_short_shots_are_never_split(self):
        p = self.plan('b1,beat,damaging winds,footage,,,,,,,"damaging winds swept across wyoming on tuesday",,,,,,,,,,,one\n'
                      "b1,clip,,,,,,,,,,,,,,,,,,media/real_event.mp4,,why\n", dur=15.0)
        split_long_shots(p)
        self.assertEqual(len(p.beats[0].clips), 1)
        p = self.plan('b1,beat,damaging winds,footage,,,,,,,"damaging winds swept across wyoming on tuesday",,,,,,,,,,,one\n'
                      "b1,clip,,,,,,,,,,,,,,,,,,stock_video:prairie grass in strong wind,,why\n", dur=6.0)
        split_long_shots(p)
        self.assertEqual(len(p.beats[0].clips), 1)

    def test_your_library_clip_must_fit_the_narration_too(self):
        from weather.footage_library import prefer_library

        with tempfile.TemporaryDirectory() as d:
            for name in ("wind/palm_trees_tropical_storm_wind.mp4", "wind/prairie_wind_gusts.mp4"):
                (Path(d) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / name).write_bytes(b"")
            csv_text = (HEAD + 'b1,beat,damaging winds,footage,,,,,,,"damaging winds swept across wyoming on tuesday",,,,,,,,,,,one\n'
                        "b1,clip,,,,,,,,,,,,,,,,,,stock_video:trees bending in tropical storm wind,,why\n")
            classic, _ = prefer_library(csv_text, d)
            strict, notes = prefer_library_strict(csv_text, d)
            self.assertIn("palm_trees_tropical", classic)          # the Weather style matches by weather condition only
            self.assertIn("prairie_wind_gusts", strict)            # Teamplate also checks the place the narration describes
            self.assertNotIn("palm_trees_tropical", strict)
            self.assertTrue(notes)


class EndToEnd(unittest.TestCase):
    """Through generate_forecast_video with the renderer faked: what reaches weather-engine in each style (the Forecast project of
    test_weather_render)."""

    setUp = twr.Generate.setUp
    tearDown = twr.Generate.tearDown

    def run_style(self, style):
        from pakmap import app_integration as ai
        from pakmap.engine_runner import RenderOutcome

        got = []

        def fake_render_spec(spec, output, **kw):
            got.append(spec)
            Path(output).write_bytes(b"x")
            return RenderOutcome(output=Path(output), frames=1, sidecar={}, warnings=[])

        kw = {} if style is None else {"edit_style": style}
        with mock.patch("weather.render.render_spec", fake_render_spec), \
             mock.patch("scene_graph.app_integration._export_via_existing_renderer", lambda g, s, *, voiceover_path, output_path, **k: Path(output_path).write_bytes(b"x")), \
             mock.patch("scene_graph.app_integration.validate_rendered_output", lambda *a, **k: None), \
             mock.patch.object(ai, "voiceover_duration", lambda path: 10.0), \
             mock.patch("pakmap.compile.check_with_engine", lambda s: ([], [], True)):
            from datetime import datetime, timezone

            from weather import generate as wgen

            res = wgen.generate_forecast_video(self.project, self.d / "vo.wav", self.d / "out.mp4", whisper_words=WORDS,
                                               now=datetime(2026, 10, 12, 21, 0, tzinfo=timezone.utc), sound_design=False, log=lambda m: None, **kw)
        self.assertTrue(res.ok, res.errors)
        return got[0]

    def test_the_weather_style_is_unchanged_when_teamplate_is_not_picked(self):
        default, classic = self.run_style(None), self.run_style("classic")
        strip = lambda s: {k: v for k, v in s.items() if k not in ("output",)}   # noqa: E731
        self.assertEqual(json.dumps(strip(default), sort_keys=True, default=str), json.dumps(strip(classic), sort_keys=True, default=str))
        self.assertTrue(any(e["type"] == "hud_title" for e in default["events"]))
        self.assertFalse(any(str(e.get("type", "")).startswith("tp_") for e in default["weather"]["events"]))
        self.assertNotIn("grade", default.get("imagery") or {})

    def test_teamplate_reaches_the_renderer_restyled_with_the_same_data(self):
        classic, team = self.run_style("classic"), self.run_style("teamplate")
        self.assertFalse(any(e["type"] == "hud_title" for e in team["events"]))
        types = {e["type"] for e in team["weather"]["events"]}
        self.assertTrue({"tp_title", "tp_vignette"} <= types, types)
        # the data graphics are the same ones, with the same numbers
        same = lambda s: sorted(json.dumps(e, sort_keys=True) for e in s["weather"]["events"] if e["type"] in ("temp_marker", "forecast_strip", "source_line"))  # noqa: E731
        self.assertEqual(same(classic), same(team))
        self.assertEqual(team["imagery"]["grade"], tp.MAP_GRADE)


class Packaging(unittest.TestCase):
    def test_the_style_ships_in_the_build(self):
        from weather.packaging import data_files, python_modules

        files = [Path(src).relative_to(ROOT).as_posix() for src, _dst in data_files(ROOT)]
        for need in ("weather-engine/lib/wxu_tp_style.mjs", "weather-engine/lib/layers/tp_title.mjs", "weather-engine/lib/layers/tp_dip.mjs",
                     "weather-engine/lib/layers/tp_stat.mjs", "weather-engine/lib/layers/tp_tag.mjs", "weather-engine/lib/layers/tp_place.mjs",
                     "weather-engine/lib/layers/tp_lower.mjs", "weather-engine/lib/layers/tp_vignette.mjs"):
            self.assertIn(need, files)
        mods = python_modules(ROOT)
        self.assertIn("weather.teamplate", mods)
        self.assertIn("weather.teamplate.footage", mods)


class Cutaways(unittest.TestCase):
    """Automatic B-roll: only where the map is holding and the words describe weather a camera can film."""

    def plan_and_payload(self, text, words):
        from hybrid.beat_csv import plan_from_csv

        from weather.events import WeatherPayload

        csv_text = (HEAD + f'b1,beat,{words[0][0]},map,hold,,Texas,region,,,"{text}",,,,,,,,,,,one\n'
                    f"b1,layer,{words[0][0]},,hud_title,t1,,,HEADLINE,SUB,,,,,,,,,,,,\n")
        plan = plan_from_csv(csv_text, words, words[-1][2] + 0.5)
        return plan, WeatherPayload()

    def words(self, text, start=0.0, step=0.45):
        return [(w, start + i * step, start + i * step + 0.4) for i, w in enumerate(text.split())]

    def test_request_comes_from_the_words_and_never_from_agency_names_or_data_talk(self):
        from weather.teamplate.cutaways import request_for

        self.assertEqual(request_for("streets turned into rivers as floodwaters rose across the city"), "aerial view of floodwater in city streets")
        self.assertEqual(request_for("the surge pushed water far inland along the coast"), "storm surge flooding the coast")
        self.assertIsNone(request_for("every number comes from the National Hurricane Center"))
        self.assertIsNone(request_for("this map adds up radar rainfall estimates"))
        self.assertIsNone(request_for("issued five extreme wind warnings"))
        self.assertIsNone(request_for("the sun came up over the plains and people went to work"))   # nothing weather-like to film

    def test_a_cutaway_lands_in_a_quiet_descriptive_stretch_and_keeps_the_map_around_it(self):
        from weather.teamplate.cutaways import add_cutaways

        text = ("here is the week ahead for texas and then the rain kept falling for hours and streets flooded in the city "
                "while creeks rose over their banks and water spread across low ground everywhere you looked that night")
        w = self.words(text)
        plan, payload = self.plan_and_payload(text, w)
        notes = []
        self.assertEqual(add_cutaways(plan, w, payload, notes), 1)
        ids = [b.id for b in plan.beats]
        self.assertEqual(ids[0], "b1")                      # the sidecar's beat id is kept
        cut = next(b for b in plan.beats if b.mode == "footage")
        self.assertTrue(cut.clips[0].asset.startswith("stock_video:"))
        self.assertGreaterEqual(cut.start, 3.5)             # never over the title arriving
        self.assertLessEqual(cut.end - cut.start, 10.0 + 1e-9)
        self.assertEqual(relevance_problems(plan), [])
        from hybrid.plan import validate_plan

        self.assertEqual(validate_plan(plan), [])
        self.assertEqual(plan.beats[0].layers[0].until, plan.beats[-1].end)   # the title is held to the original beat end
        self.assertTrue(notes)

    def test_measurements_read_out_keep_the_map(self):
        from weather.teamplate.cutaways import add_cutaways

        text = ("here is the week ahead for texas and heavy rain fell at four inches an hour then six inches then eight inches "
                "and the gauge read ten inches by midnight with twelve inches by morning and fourteen inches by noon")
        w = self.words(text)
        plan, payload = self.plan_and_payload(text, w)
        self.assertEqual(add_cutaways(plan, w, payload), 0)

    def test_the_share_of_footage_is_capped(self):
        from weather.teamplate.cutaways import add_cutaways

        text = " ".join(["the rain kept falling and streets flooded across the city"] * 12)
        w = self.words("here is the week " + text)
        plan, payload = self.plan_and_payload("here is the week " + text, w)
        add_cutaways(plan, w, payload)
        share = sum(b.end - b.start for b in plan.beats if b.mode == "footage") / plan.duration
        self.assertLessEqual(share, 0.40 + 1e-6)
        self.assertGreater(share, 0.2)


class Prompt(unittest.TestCase):
    def test_the_teamplate_prompt_section_asks_for_generic_footage_on_descriptive_sentences(self):
        text = (ROOT / "weather" / "prompts" / "teamplate_csv_addendum.txt").read_text(encoding="utf-8")
        for need in ("40%", "stock_video:", "Never name a place, a storm or a date"):
            self.assertIn(need, text)
        from weather.packaging import data_files

        self.assertIn("weather/prompts/teamplate_csv_addendum.txt", [Path(src).relative_to(ROOT).as_posix() for src, _ in data_files(ROOT)])


class TagsUnderFootage(unittest.TestCase):
    def test_context_tags_and_lower_thirds_step_aside_under_footage(self):
        sp, pa = spec(), part()
        sp["events"][1]["t_out"] = 50.0     # the beat's tag would run on into the footage (45-60 s)
        pa["events"].append({"id": "wx_hl", "type": "headline", "title": "Landfall", "t_in": 40.0, "t_out": 50.0})
        s, p = tp.apply_spec(sp, pa)
        over = [e for e in p["events"] if e["type"] in ("tp_tag", "tp_lower") and e["t_out"] > 45.0]
        self.assertTrue(over)
        for e in over:
            self.assertIn([45.0, 60.0], e["hide"], e)

if __name__ == "__main__":
    unittest.main()
