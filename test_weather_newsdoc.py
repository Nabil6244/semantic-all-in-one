"""News Doc (weather/newsdoc): a footage-first editing option built from its reference video (docs/weather/news_footage_plan.md).

Offline: the story reader, the news harvester (a fake YouTube that serves a generated test video), the timeline (map shots only at
data moments, at most 10 %, 40 s apart; news runs first; graphics never on the map), the graphics clips (transparent), the overlay
pass, the app's picker, and the whole plan under NoPaidCalls (no AI provider, no network)."""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from hybrid.plan import validate_plan

SCRIPT = ("TORNADO WARNING — PECOS COUNTY, TEXAS Severe storms are unfolding right now across Texas on October 14, 2026. "
          "The National Weather Service issued a Tornado Warning for Pecos County at 2:30 PM. "
          "The storm was moving northeast at 20 miles per hour. "
          "Roofs were ripped off homes and trees were snapped along the path. "
          "Debris was scattered across the roads for miles. "
          "Crews worked through the night to restore power. "
          "MAJOR FLOODING — CANADIAN RIVER, OKLAHOMA Turning to Oklahoma, the Canadian River is in major flood. "
          "The river stage measured 18.0 feet, well above the 14.0-foot flood stage. "
          "Communities in the path include Lancaster, Logan, Bremen and Amanda. "
          "Water covered the fields and the roads near the river. "
          "Families waited on rooftops for rescue boats. "
          "Most flood deaths happen in vehicles, so turn around when you see water on the road.")


def words_of(text, wps=2.2):
    out, t = [], 0.0
    for w in text.split():
        out.append((w, round(t, 3), round(t + 0.3, 3)))
        t += 1.0 / wps + (0.4 if w.endswith(".") else 0.0)
    return out, t + 0.5


def test_video(path: Path, seconds: float = 30.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
                   check=True)


class FakeYouTube:
    def __init__(self, src: Path):
        self.src, self.searched, self.downloaded = src, [], []

    def search(self, query, max_results=5):
        from providers.youtube.base import VideoCandidate

        self.searched.append(query)
        place = query.split()[0]
        return [VideoCandidate("live1", "u", f"LIVE {place} storm coverage 24/7", "KWES NewsWest 9", 3600.0),
                VideoCandidate("cmp1", "u", "Craziest storms compilation", "Fails", 300.0),
                VideoCandidate("off1", "u", "Cooking pasta at home", "Chef", 200.0),
                VideoCandidate(f"good_{place}", "u", f"{place} tornado and flooding damage", "KWES NewsWest 9", 140.0)]

    def download_segment(self, cand, start, duration, dest, log=print):
        self.downloaded.append(cand.video_id)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(duration), "-i", str(self.src), "-c", "copy", str(dest)],
                       check=True)
        return dest


def story():
    from weather.newsdoc.story import read

    words, dur = words_of(SCRIPT)
    return read(words, dur, SCRIPT), words, dur


class TheStory(unittest.TestCase):
    def test_parts_places_numbers_lists(self):
        st, _w, _d = story()
        self.assertEqual([t for _i, t in st.parts][1:], ["MAJOR FLOODING"])
        pecos = next(x for x in st.lines if any(p[0] == "Pecos County" for p in x.places))
        self.assertEqual(pecos.place_state["Pecos County"], "Texas")
        self.assertIn("Tornado Warning", pecos.yellow)
        self.assertTrue(any(n.shown == "18" and n.label == "FEET" for x in st.lines for n in x.numbers))
        self.assertEqual(next(x.items for x in st.lines if x.items), ["Lancaster", "Logan", "Bremen", "Amanda"])


class TheNewsHarvest(unittest.TestCase):
    def test_few_searches_continuous_muted_runs_and_a_cache(self):
        from weather.newsdoc.harvest import harvest

        tmp = Path(tempfile.mkdtemp())
        test_video(tmp / "src.mp4", 60.0)
        st, _w, _d = story()
        yt = FakeYouTube(tmp / "src.mp4")
        got = harvest(tmp / "wx", st, {"main_day": "2026-10-14"}, backend=yt, pause=0.0, log=lambda m: None)
        self.assertLessEqual(len(yt.searched), 3 * len(st.parts))   # a few searches per part: news, a fallback, drone of the place
        self.assertTrue(all(v.startswith("good_") for v in yt.downloaded), yt.downloaded)   # live / compilation / off-topic skipped
        self.assertTrue(got.runs)
        for r in got.runs:
            self.assertTrue(5.0 - 1e-6 <= r.dur <= 15.0 + 1e-6, r.dur)
            info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(tmp / "wx" / r.path)],
                                             capture_output=True, text=True).stdout)["streams"]
            self.assertEqual([s["codec_type"] for s in info], ["video"])   # muted
            self.assertEqual((info[0]["width"], info[0]["height"]), (1920, 1080))
        self.assertTrue(any("KWES" in c for c in got.credits()))
        again = harvest(tmp / "wx", st, {"main_day": "2026-10-14"}, backend=FakeYouTube(tmp / "src.mp4"), pause=0.0, log=lambda m: None)
        self.assertTrue(again.cached)
        self.assertEqual(len(again.runs), len(got.runs))

    def test_a_short_download_gives_only_real_runs_and_a_second_piece(self):
        from weather.newsdoc.harvest import harvest, media_seconds

        class Short(FakeYouTube):
            def download_segment(self, cand, start, duration, dest, log=print):
                return super().download_segment(cand, start, 8.4, dest, log)   # YouTube capture came back short

        tmp = Path(tempfile.mkdtemp())
        test_video(tmp / "src.mp4", 60.0)
        st, _w, _d = story()
        yt = Short(tmp / "src.mp4")
        got = harvest(tmp / "wx", st, {"main_day": "2026-10-14"}, backend=yt, pause=0.0, log=lambda m: None)
        self.assertTrue(got.runs)
        for r in got.runs:
            self.assertGreaterEqual(media_seconds(tmp / "wx" / r.path), 4.0)
        self.assertGreaterEqual(len(yt.downloaded), 2 * len({r.video_id for r in got.runs}))   # more pieces from later in each video
        broken = [f for f in (tmp / "wx" / "_work" / "news_cache").glob("*_p*r*.mp4") if f.stat().st_size <= 1000]
        self.assertEqual(broken, [])

    def test_only_reports_of_this_event_are_taken(self):
        from providers.youtube.base import VideoCandidate as V
        from weather.newsdoc.harvest import rank

        q = {"words": ["pecos", "fort", "stockton"], "state": "texas", "hazard": ["tornado"], "month": "october", "year": "2026"}
        got = [c.video_id for c in rank([
            V("ok", "u", "Eyewitness footage of tornado passing through Fort Stockton, Texas", "News", 60.0),
            V("ok2", "u", "Texas tornado damage October 2026", "KWES", 120.0),
            V("school", "u", "New elementary school in Pecos", "NewsWest 9", 120.0),          # no hazard
            V("size", "u", "Tornado Size Comparison", "Comparisons", 300.0),                   # no place, a comparison
            V("old", "u", "Pecos tornado May 2019", "KWES", 90.0),                             # another year / month
            V("sep", "u", "Oklahoma tornado update (Thursday, Sept. 30)", "KOCO", 90.0),        # another month
            V("hurr", "u", "Hurricane Isaias to bring tornadoes to Gulf Coast", "FOX Weather", 200.0)], q)]
        self.assertEqual(got, ["ok", "ok2"])

    def test_no_youtube_is_a_note_never_a_stop(self):
        from weather.newsdoc.harvest import harvest

        class Broken:
            def search(self, *a, **k):
                raise RuntimeError("HTTP Error 429")

        st, _w, _d = story()
        got = harvest(Path(tempfile.mkdtemp()), st, {}, backend=Broken(), pause=0.0, log=lambda m: None)
        self.assertEqual(got.runs, [])
        self.assertTrue(any("429" in n for n in got.notes))


def rows_and_wins(dur):
    from weather.sidecar import WxRow
    from weather.timing import Window

    rows = [WxRow(0, "d2", "auto_radar", "radar"), WxRow(0, "d2", "auto_warn", "warnings_archive"),
            WxRow(0, "d8", "auto_crest", "river_crest"), WxRow(0, "d9", "auto_crest2", "river_crest"),
            WxRow(0, "d2", "auto_src", "source_line")]
    wins = {"auto_radar": Window(12.0, 30.0), "auto_warn": Window(12.5, 30.0), "auto_crest": Window(70.0, 80.0),
            "auto_crest2": Window(75.0, 80.0), "auto_src": Window(13.0, 30.0)}
    return rows, wins


class TheTimeline(unittest.TestCase):
    def setUp(self):
        from weather.newsdoc.harvest import Run
        from weather.newsdoc.plan import build

        self.st, self.words, self.dur = story()
        rows, wins = rows_and_wins(self.dur)
        runs = [Run(f"_work/news_cache/v_r{k}.mp4", "v", "Pecos tornado", "KWES", "u", 0, "Pecos County", 0.0, 8.0) for k in range(3)] + \
               [Run(f"_work/news_cache/w_r{k}.mp4", "w", "Canadian River flood", "KFOR", "u", 1, "Oklahoma", 0.0, 9.0) for k in range(3)]
        self.nd = build(self.st, self.words, rows, wins, runs, notes=[])

    def test_the_plan_is_valid_and_covers_the_narration(self):
        self.assertEqual(validate_plan(self.nd.hybrid), [])
        shots = self.nd.shots
        self.assertEqual(shots[0].t0, 0.0)
        self.assertAlmostEqual(shots[-1].t1, self.dur, places=3)
        self.assertTrue(all(abs(a.t1 - b.t0) < 1e-6 for a, b in zip(shots, shots[1:])))

    def test_map_only_at_data_moments_within_the_budget_and_apart(self):
        maps = [s for s in self.nd.shots if s.kind == "map"]
        self.assertTrue(maps)
        from weather.newsdoc import MAP_SHARE

        self.assertLessEqual(sum(s.t1 - s.t0 for s in maps), MAP_SHARE * self.dur + 1e-6)
        self.assertTrue(all(s.rows for s in maps))
        from weather.newsdoc.plan import MAP_GAP_S

        self.assertTrue(all(b.t0 - a.t1 >= MAP_GAP_S - 1e-6 for a, b in zip(maps, maps[1:])))
        self.assertIn("auto_warn", maps[0].rows)    # rides along with the radar shot
        self.assertIn("auto_src", [r.id for r in self.nd.rows])   # its source line goes with it

    def test_news_first_then_b_roll_and_no_run_twice(self):
        news = [s for s in self.nd.shots if s.kind == "news"]
        self.assertTrue(news)
        self.assertEqual(len({s.asset for s in news}), len(news))
        self.assertTrue(all(s.asset.startswith("stock_video:") for s in self.nd.shots if s.kind == "stock"))
        stock = [s.asset for s in self.nd.shots if s.kind == "stock"]
        self.assertEqual(len(stock), len(set(stock)))   # a repeated search is reframed

    def test_graphics_follow_the_story_and_never_sit_on_the_map(self):
        kinds = {o.kind for o in self.nd.overlays}
        self.assertIn("dossier", kinds)          # the warning's case file opens the story
        self.assertTrue({"chapter", "caption"} & kinds)
        for k in ("checklist",):
            self.assertIn(k, kinds)
        for o in self.nd.overlays:   # a place tag only over news footage of the event, never over b-roll (it would name the b-roll's place)
            if o.kind == "place":
                under = [s for s in self.nd.shots if s.t0 < o.t1 and o.t0 < s.t1]
                self.assertTrue(all(s.kind in ("news", "map") for s in under), o)
        maps = [s for s in self.nd.shots if s.kind == "map"]
        for o in self.nd.overlays:   # nothing on the map but a place name (the map shows that place)
            if o.kind not in ("place", "orange_place"):
                self.assertFalse(any(m.t0 < o.t1 and o.t0 < m.t1 for m in maps), o)
        chart = next((o for o in self.nd.overlays if o.kind == "chart"), None)
        if chart is not None:
            self.assertEqual(chart.params["labels"], ["RIVER STAGE", "FLOOD STAGE"])
        place = next((o for o in self.nd.overlays if o.kind == "place"), None)
        if place is not None:
            self.assertEqual(place.params["sub"], "TEXAS" if "PECOS" in place.params["name"] else place.params["sub"])

    def test_without_any_data_the_map_is_a_short_opening_only(self):
        from weather.newsdoc.plan import build

        nd = build(self.st, self.words, [], {}, [], notes=[])
        maps = [s for s in nd.shots if s.kind == "map"]
        self.assertEqual(len(maps), 1)
        self.assertLessEqual(maps[0].t1 - maps[0].t0, 3.5 + 1e-6)
        self.assertEqual(validate_plan(nd.hybrid), [])


class TheGraphics(unittest.TestCase):
    def test_each_look_is_a_transparent_clip_and_lays_over_footage(self):
        from weather.newsdoc import finish, graphics
        from weather.newsdoc.plan import Overlay

        tmp = Path(tempfile.mkdtemp())
        test_video(tmp / "base.mp4", 6.0)
        still = tmp / "still.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(tmp / "base.mp4"), "-frames:v", "1", str(still)], check=True)
        ovs = [Overlay("place", 0.2, 2.0, {"name": "PECOS COUNTY", "sub": "TEXAS"}), Overlay("glitch", 2.0, 2.42, {}),
               Overlay("number", 2.5, 4.5, {"value": 18.0, "shown": "18", "label": "FEET"}),
               Overlay("checklist", 1.0, 3.0, {"title": "IN THE PATH", "items": ["A", "B", "C"]}),
               Overlay("chart", 3.0, 5.5, {"title": "RIVER", "unit": "FEET", "values": [18, 14], "shown": ["18", "14"], "labels": ["A", "B"]}),
               Overlay("quote_card", 4.5, 6.0, {"text": "Most flood deaths happen in vehicles.", "red": "in vehicles"}),
               Overlay("quote", 0.5, 2.0, {"text": "Turn around.", "red": "around"}), Overlay("ytag", 0.1, 1.5, {"text": "FLOOD WARNING"}),
               Overlay("chapter", 0.1, 1.5, {"text": "MAJOR FLOODING"}), Overlay("panel", 0.1, 2.5, {"title": "WHY", "bullets": ["one two three", "four five six"]}),
               Overlay("ring", 0.2, 2.0, {"value": 70, "label": "CHANCE OF RAIN"}), Overlay("year", 2.0, 3.0, {"text": "2019"}),
               Overlay("line", 3.0, 5.5, {"title": "RIVER", "unit": "FEET", "values": [6.7, 14, 15.3], "shown": ["6.7", "14", "15.3"], "labels": ["A", "B", "C"]}),
               Overlay("pullquote", 1.0, 3.0, {"text": "We have never seen water this high here", "who": "Jane Smith"}),
               Overlay("nametag", 1.0, 3.0, {"name": "JANE SMITH", "role": "COUNTY JUDGE"}), Overlay("rings", 3.0, 5.0, {"items": ["WIND", "HAIL", "FLOODING"]}),
               Overlay("caption", 0.2, 2.0, {"text": "MAJOR FLOODING"}), Overlay("headline", 1.0, 3.0, {"title": "TORNADO WARNING ISSUED", "sub": "Pecos County · 2:30 PM"}),
               Overlay("dossier", 0.5, 2.5, {"title": "TORNADO WARNING", "fields": [("DATE", "2026-10-14")]}),
               Overlay("hbars", 2.0, 4.0, {"title": "RIVERS", "unit": "FEET", "values": [18, 15, 6.7], "shown": ["18", "15", "6.7"], "labels": ["A", "B", "C"]}),
               Overlay("framed", 1.0, 3.0, {"caption": "PECOS COUNTY", "stills": [str(still)]}),
               Overlay("polaroids", 1.0, 3.0, {"title": "TWO TYPES", "labels": ["WIND", "WATER"], "stills": [str(still), str(still)]})]
        clips = []
        for o in ovs:
            p = graphics.render(o, tmp)
            self.assertIsNotNone(p, o.kind)
            fmt = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", str(p)],
                                 capture_output=True, text=True).stdout.strip()
            self.assertIn(fmt, ("argb", "rgba", "bgra"), o.kind)
            clips.append((p, o.t0))
        ok, notes = finish.composite(tmp / "base.mp4", clips, tmp / "out.mp4")
        self.assertTrue(ok, notes)
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json",
                                          str(tmp / "out.mp4")], capture_output=True, text=True).stdout)
        self.assertEqual(sorted(s["codec_type"] for s in info["streams"]), ["audio", "video"])   # the narration is kept
        self.assertAlmostEqual(float(info["format"]["duration"]), 6.0, delta=0.2)


class TheCard(unittest.TestCase):
    def test_news_doc_is_a_new_choice_and_the_other_styles_are_unchanged(self):
        from weather import app_section
        from weather.teamplate import STYLES

        def app(label, fmt_label="News"):
            return NS(_weather_style_var=NS(get=lambda: label), _weather_format_var=NS(get=lambda: fmt_label), _main_script_text=lambda: "")
        self.assertEqual(app_section.current_style(app("News Doc")), "newsdoc")
        self.assertEqual(app_section.current_style(app(STYLES["teamplate"])), "teamplate")
        self.assertEqual(app_section.current_style(app(STYLES["classic"])), "classic")
        self.assertEqual(app_section.current_style(app("Auto")), "teamplate")
        self.assertEqual(app_section.current_style(app("Auto", "Forecast")), "classic")

    def test_the_weather_render_never_loads_news_doc(self):
        for f in ("weather/generate.py", "weather/teamplate/__init__.py", "weather/render.py", "weather/autofix.py"):
            self.assertNotIn("newsdoc", Path(f).read_text(encoding="utf-8"), f)


class OneStyleForForecastsToo(unittest.TestCase):
    def test_a_forecast_script_gets_its_own_graphics(self):
        from weather.newsdoc.plan import build
        from weather.newsdoc.story import read

        text = ("FORECAST — DALLAS, TEXAS Storms return to Dallas this week. There is a 70 percent chance of rain on Thursday. "
                "Highs climb from 81 degrees on Monday to 88 degrees on Tuesday and 93 degrees on Wednesday. "
                "Expect wind, hail and lightning with the strongest storms. The last time it was this hot in October was 2019. "
                "Stay weather aware this week.")
        words, dur = words_of(text, 2.0)
        st = read(words, dur, text)
        nd = build(st, words, [], {}, [], notes=[])
        kinds = {o.kind for o in nd.overlays}
        self.assertIn("ring", kinds)
        self.assertIn("rings", kinds)
        self.assertEqual(validate_plan(nd.hybrid), [])
        self.assertTrue(nd.hybrid.settings.get("cover_ui"))   # the map is drawn only while a map shot is on screen


TWO_MINUTES = 'TORNADO WARNING — FORT STOCKTON, TEXAS On October 14, 2026, a Tornado Warning was issued for Pecos County at 2:30 PM.\nThe storm was moving northeast at 20 miles per hour near Fort Stockton.\nResidents filmed the funnel crossing open ranch land west of town.\n"We have never seen a tornado this close to the school," said Maria Lopez, the county emergency manager.\nForecasters say there is a 70 percent chance of more storms tomorrow.\nThe last tornado this strong here was back in 2019.\nThe biggest threats were wind, hail and lightning.\nHail damage to roofs and cars was reported across the county.\nSEVERE STORMS — NORTH TEXAS Farther north, storms pushed through Foard County and Knox County.\nCommunities in the path include Truscott, Crowell, Benjamin and Munday.\nThere are two threats with these storms: wind and water.\nThis matters because a storm that stalls can drop a month of rain in one evening.\nMAJOR FLOODING — CANADIAN RIVER, OKLAHOMA In Oklahoma, the Canadian River is in major flood.\nThe river measured 6.7 feet on Monday, 14.0 feet on Tuesday and 18.0 feet on Wednesday.\nThe river stage of 18.0 feet is well above the flood stage of 14.0 feet.\nRain totals reached 4 inches in Norman, 3 inches in Moore and 2 inches in Harrah.\nA Flood Warning remains in effect along the river through Thursday. Fields along the river are under water.\nMost flood deaths happen in vehicles, so turn around when you see water on the road.'


class EveryGraphicInEveryVideo(unittest.TestCase):
    def test_all_news_doc_graphics_and_the_adopted_ones_are_in_one_video(self):
        from weather.newsdoc.plan import REQUIRED, build

        from weather.newsdoc.story import read

        words, dur = words_of(TWO_MINUTES, 2.1)   # a two-minute story
        st = read(words, dur, TWO_MINUTES)
        nd = build(st, words, *rows_and_wins(dur), [], notes=[])
        have = {o.kind for o in nd.overlays}
        self.assertEqual(sorted(set(REQUIRED) - have), [])
        self.assertIn("orange_place", have)   # adopted from Weather Teamplate
        self.assertIn("forecast", have)       # adopted from Weather's day-by-day strip


class TheOptionalStoryCsv(unittest.TestCase):
    CSV = """Here is your plan:
```csv
sentence,vo_anchor,part,shot,search,graphic,g_text,g_value,g_items,place,when
s1,TORNADO WARNING — PECOS,,map,,,,,,"Pecos County, TX",2026-10-14
s2,The National Weather Service issued,,news,Fort Stockton Texas tornado,headline,TORNADO WARNING ISSUED,,,"Pecos County, TX",2:30 PM
s3,The storm was moving,,broll,storm clouds over a ranch,big_number,MPH,20,,,
s5,Debris was scattered,,card,,horizontal_bars,DEBRIS,MILES,A=3;B=2;C=1,,
s99,Nonexistent words here,,teleport,,sparkles,,,,,
```
Thanks!"""

    def setUp(self):
        from weather.newsdoc.story_csv import match, parse

        self.st, self.words, self.dur = story()
        self.notes = []
        self.rows = parse(self.CSV, self.notes)
        self.csv = match(self.rows, self.st, self.notes)

    def test_a_chat_answer_is_read_and_bad_rows_are_named_not_fatal(self):
        self.assertEqual(len(self.rows), 5)
        self.assertTrue(any("teleport" in n for n in self.notes))
        self.assertTrue(any("sparkles" in n for n in self.notes))
        self.assertTrue(any("Nonexistent" in n for n in self.notes))   # no sentence starts so: left out, never a stop
        self.assertEqual(sorted(self.csv), [0, 1, 2, 4])

    def test_its_cells_set_the_shot_the_search_and_the_graphic(self):
        from weather.newsdoc.plan import REQUIRED, build

        nd = build(self.st, self.words, [], {}, [], notes=[], csv=self.csv)
        line2 = self.st.lines[2]
        here = [s for s in nd.shots if s.t0 < line2.span_end and line2.span_start < s.t1 and s.kind == "stock"]
        self.assertTrue(any(s.asset == "stock_video:storm clouds over a ranch" for s in here))
        self.assertTrue(any(s.kind == "map" and s.t0 <= self.st.lines[0].span_start + 0.01 for s in nd.shots))
        num = next(o for o in nd.overlays if o.kind == "number" and o.params.get("shown") == "20")
        self.assertEqual(num.params["label"], "MPH")
        hb = next(o for o in nd.overlays if o.kind == "hbars" and o.params.get("labels") == ["A", "B", "C"])
        self.assertEqual(hb.params["values"], [3.0, 2.0, 1.0])
        self.assertEqual(validate_plan(nd.hybrid), [])

    def test_the_weather_card_saves_it_for_news_doc(self):
        from weather import app_section
        from weather.newsdoc.story_csv import FILE

        tmp = Path(tempfile.mkdtemp())
        (tmp / "weather").mkdir()
        box = NS(text="")

        class FakeApp:   # the app's module is where the card finds its dialogs (this test module)
            pass

        app = FakeApp()
        app.__dict__.update(_workspace=NS(root=str(tmp)), _weather_style_var=NS(get=lambda: "News Doc"),
                            _weather_format_var=NS(get=lambda: "News"), _main_script_text=lambda: "",
                            _weather_file_var=NS(set=lambda v: None), _weather_status_var=NS(set=lambda v: None),
                            _sync_primary_cta=lambda: None, _weather_plan_box=NS(configure=lambda **k: None, delete=lambda *a: None,
                                                                                  insert=lambda i, t: setattr(box, "text", t)))
        self.assertTrue(app_section.load_newsdoc_csv(app, self.CSV))
        self.assertTrue((tmp / "weather" / FILE).is_file())
        self.assertIn("5 row(s)", box.text)

    def test_the_prompts_name_every_column_and_every_graphic(self):
        from weather.newsdoc.story_csv import COLUMNS, GRAPHICS

        text = Path("weather/prompts/newsdoc_csv_prompt.txt").read_text(encoding="utf-8")
        self.assertIn(",".join(COLUMNS), text)
        kinds = {v for v in GRAPHICS.values()}
        named = {GRAPHICS[k] for k in GRAPHICS if re.search(r"\b" + k + r"\b", text)}
        self.assertEqual(sorted(kinds - named), [])
        self.assertTrue(Path("weather/prompts/newsdoc_script_prompt.txt").is_file())


class NeverStopsForAMissingClip(unittest.TestCase):
    def test_a_clip_no_provider_has_is_asked_again_then_the_video_is_made(self):
        import shutil
        from unittest import mock

        from pakmap.app_integration import PakmapResult
        from weather.events import WeatherPayload
        from weather.generate import WeatherProject
        from weather.newsdoc import generate as G
        from weather.newsdoc.harvest import Harvest
        from weather.newsdoc.plan import build

        tmp = Path(tempfile.mkdtemp())
        test_video(tmp / "vo.mp4", 6.0)
        st, words, _d = story()
        st.duration = 6.0
        st.lines = [x for x in st.lines if x.span_start < 6.0]
        st.lines[-1].span_end = 6.0
        nd = build(st, words, [], {}, [], notes=[])
        calls = []

        def fake_render(plan, vo, out, **kw):
            calls.append([c.asset for b in plan.beats for c in b.clips])
            if len(calls) == 1:
                return PakmapResult(False, ["1 clip has no picture"], unresolved=["1"])
            shutil.copyfile(tmp / "vo.mp4", out)
            return PakmapResult(True, output_path=Path(out))

        p = WeatherProject(tmp / "weather")
        p.root.mkdir()
        with mock.patch.object(G, "plan_newsdoc", return_value=(nd, WeatherPayload(), [], Harvest())), \
                mock.patch("hybrid.generate.generate_hybrid_video", side_effect=fake_render):
            res = G.generate_newsdoc_video(p, tmp / "vo.mp4", tmp / "out.mp4", whisper_words=words, log=lambda m: None)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0], calls[1])          # the missing clip was asked for again, differently
        self.assertTrue((tmp / "out.mp4").is_file())
        self.assertTrue((tmp / "out.newsdoc.json").is_file())


class NoAiAndNoNetwork(unittest.TestCase):
    def test_the_whole_plan_reaches_no_ai_provider_and_no_network(self):
        from enoch_template_testutil import NoPaidCalls
        from test_weather_intel import NOW, Replay
        from weather.generate import WeatherProject
        from weather.newsdoc.generate import plan_newsdoc

        tmp = Path(tempfile.mkdtemp())
        test_video(tmp / "src.mp4", 40.0)
        p = WeatherProject(tmp / "weather")
        p.root.mkdir()
        (p.root / "script.txt").write_text(SCRIPT, encoding="utf-8")
        words, dur = words_of(SCRIPT)
        with NoPaidCalls():
            nd, payload, notes, got = plan_newsdoc(p, words, dur, backend=FakeYouTube(tmp / "src.mp4"), pause=0.0, log=lambda m: None,
                                                   engine_kw=dict(now=NOW, get_text=Replay().text, get_bytes=Replay().bytes))
        self.assertEqual(validate_plan(nd.hybrid), [])
        self.assertTrue(any(s.kind == "news" for s in nd.shots))


if __name__ == "__main__":
    unittest.main()
