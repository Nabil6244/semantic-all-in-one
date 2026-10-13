"""Weather through Hybrid's generator: the weather layers reach the renderer, pass pakMap's own rule check, the numbers
report is written, stale data stops the render, and the packaging list is complete. The renderer is faked here (the real
renders are weather-engine's golden tests)."""

import json
import struct
import subprocess
import tempfile
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from weather import generate as wgen
from weather.cache import HttpCache
from weather.nws import NwsClient
from weather.packaging import data_files
from weather.render import make_render, with_weather

from test_weather_data import DALLAS_ROUTES, FakeNet, fixture

ROOT = Path(__file__).resolve().parent
UTC = timezone.utc
NOW = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)

BEATS = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
         'b1,beat,good morning everyone,map,hold,,Texas,region,,,"good morning everyone dallas stays hot this week",,,,,,,,,,,one\n'
         "b1,layer,good morning everyone,,hud_title,t1,,,YOUR WEATHER,TEXAS,,,,,,,,,,,,\n"
         'b2,beat,here is the outlook,map,hold,,Texas,region,,,"here is the outlook for dallas and that is all",,,,,,,,,,,two\n')
LAYERS = ("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
          "b1,,0,sat,satellite,,gibs:geocolor@latest,,end,\n"
          'b1,dallas stays hot,,dal,temp_marker,"Dallas, TX","nws:forecast@Dallas,TX#day1",,,\n'
          "b1,dallas stays hot,,al,alert_area,TX,nws:alerts@TX,,,\n"
          'b2,for dallas,,strip,forecast_strip,"Dallas, TX","nws:forecast@Dallas,TX#day1-5",,,\n'
          "b2,for dallas,,src,source_line,,,,,\n")
WORDS = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("good morning everyone dallas stays hot this week here is the outlook for dallas and that is all".split())]


class Generate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.project = wgen.WeatherProject(self.d / "proj")
        self.project.root.mkdir()
        self.project.beats_csv.write_text(BEATS, encoding="utf-8")
        self.project.layers_csv.write_text(LAYERS, encoding="utf-8")
        with wave.open(str(self.d / "vo.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<h", 0) * 8000 * 10)
        client = NwsClient("me@example.com", cache=HttpCache(self.d / "cache", now=lambda: NOW), fetch=FakeNet(DALLAS_ROUTES))
        wgen.fetch(self.project, "me@example.com", now=NOW, client=client, gibs_get=lambda u: fixture("gibs_geocolor_domain.xml").decode())
        self.specs = []
        self.logged = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_gen(self, now=NOW):
        from pakmap import app_integration as ai
        from pakmap.engine_runner import RenderOutcome

        def fake_render_spec(spec, output, **kw):
            self.specs.append(spec)
            Path(output).write_bytes(b"x")
            return RenderOutcome(output=Path(output), frames=1, sidecar={}, warnings=[])

        with mock.patch("weather.render.render_spec", fake_render_spec), \
             mock.patch("scene_graph.app_integration._export_via_existing_renderer", lambda g, s, *, voiceover_path, output_path, **k: Path(output_path).write_bytes(b"x")), \
             mock.patch("scene_graph.app_integration.validate_rendered_output", lambda *a, **k: None), \
             mock.patch.object(ai, "voiceover_duration", lambda path: 10.0), \
             mock.patch("pakmap.compile.check_with_engine", lambda s: ([], [], True)):
            return wgen.generate_forecast_video(self.project, self.d / "vo.wav", self.d / "out.mp4", whisper_words=WORDS, now=now,
                                                sound_design=False, log=self.logged.append)

    def test_the_weather_layers_reach_the_renderer_with_hybrids_spec(self):
        r = self.run_gen()
        self.assertTrue(r.ok, r.errors)
        spec = self.specs[0]
        self.assertEqual(spec["hybrid"], {"pause_overlays": True})              # Hybrid's own options are kept
        ids = [e["id"] for e in spec["events"]]
        self.assertIn("t1", ids)                                                 # the beat CSV's hud_title
        self.assertEqual([i for i in ids if i.startswith("wx_al_")], ["wx_al_0", "wx_al_1", "wx_al_2"])
        wx = {e["id"]: e for e in spec["weather"]["events"]}
        self.assertEqual(wx["wx_dal"]["t_in"], 1.5)                             # on "dallas stays hot"
        self.assertEqual(wx["wx_strip"]["t_in"], 6.0)                           # on "for dallas" in b2
        self.assertEqual(spec["weather"]["satellite"][0]["t_out"], spec["duration"])
        self.assertTrue((self.d / "out.numbers.txt").is_file())
        self.assertIn("[dal] Dallas, TX mon high", (self.d / "out.numbers.txt").read_text())
        self.assertTrue((self.project.work_dir / "weather_numbers.txt").is_file())

    def test_the_merged_spec_passes_pakmaps_own_rule_check_and_weathers(self):
        self.assertTrue(self.run_gen().ok)
        from pakmap.compile import check_with_engine

        errors, _warnings, ran = check_with_engine(self.specs[0])
        if not ran:
            self.skipTest("node is not available")
        self.assertEqual(errors, [])
        f = self.d / "spec.json"
        f.write_text(json.dumps(self.specs[0]), encoding="utf-8")
        r = subprocess.run(["node", "--input-type=module", "-e",
                            "import fs from 'node:fs'; import { validateWxEvents } from './weather-engine/lib/wx_draw.mjs';"
                            "const s = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));"
                            "process.stdout.write(JSON.stringify(validateWxEvents(s.weather.events, s.duration)));", str(f)],
                           cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])

    def test_stale_data_stops_before_anything_is_rendered(self):
        r = self.run_gen(now=NOW + timedelta(hours=7))
        self.assertFalse(r.ok)
        self.assertIn("not fresh enough to render", r.errors[0])
        self.assertEqual(self.specs, [])

    def test_a_weather_row_for_a_beat_that_is_not_there_is_left_out_and_the_video_renders(self):
        self.project.layers_csv.write_text(LAYERS + "b9,,1,x,source_line,,,,,\n", encoding="utf-8")
        r = self.run_gen()
        self.assertTrue(r.ok, r.errors)
        self.assertNotIn("wx_x", [e["id"] for e in self.specs[0]["weather"]["events"]])
        self.assertTrue(any("x" in line and "left out" in line for line in self.logged), self.logged)

    def test_a_flow_clip_becomes_a_stock_request(self):
        beats = BEATS.replace('b2,beat,here is the outlook,map,hold,,Texas,region,', 'b2,beat,here is the outlook,footage,,,,,') + \
            "b2,clip,,,,,,,,,,,,,,,,,,flow_video:a tornado,,why\n"
        self.project.beats_csv.write_text(beats, encoding="utf-8")
        self.project.layers_csv.write_text(LAYERS.replace("b2,for dallas,,strip,", "b1,dallas stays hot,,strip,").replace("b2,for dallas,,src,", "b1,dallas stays hot,,src,"),
                                           encoding="utf-8")
        r = self.run_gen()
        self.assertFalse(any("Flow" in str(e) for e in r.errors), r.errors)   # never refused for it, never a Flow clip: it asks the stock providers (no key in tests)
        self.assertTrue(any("flow_video:a tornado" in line and "stock footage" in line for line in self.logged), self.logged)

    def test_no_data_fetched_yet_is_said_plainly(self):
        self.project.resolved_json.unlink()
        r = self.run_gen()
        self.assertFalse(r.ok)
        self.assertIn("fetch it first", r.errors[0])


class Render(unittest.TestCase):
    def test_with_weather_adds_and_never_changes_the_callers_spec(self):
        spec = {"events": [{"id": "a"}], "duration": 5}
        before = json.dumps(spec)
        out = with_weather(spec, {"events": [], "satellite": [], "credits": []}, [{"id": "f", "type": "fill"}])
        self.assertEqual([e["id"] for e in out["events"]], ["a", "f"])
        self.assertIn("weather", out)
        self.assertEqual(json.dumps(spec), before)

    def test_make_render_has_the_signature_the_pakmap_generator_calls(self):
        import inspect

        from weather.events import WeatherPayload

        fn = make_render(WeatherPayload())
        params = inspect.signature(fn).parameters
        for name in ("progress", "cancel_check", "log"):
            self.assertIn(name, params)


class Packaging(unittest.TestCase):
    def test_every_file_the_weather_renderer_loads_ships_and_nothing_for_tests(self):
        files = [Path(src).relative_to(ROOT).as_posix() for src, _dst in data_files(ROOT)]
        for need in ("weather-engine/render.mjs", "weather-engine/page.js", "weather-engine/page.html", "weather-engine/UPSTREAM.json",
                     "weather-engine/lib/wx_draw.mjs", "weather-engine/lib/wx_icons.mjs", "weather-engine/lib/wx_layout.mjs",
                     "weather/data/cities.json", "weather/prompts/forecast_csv_prompt.txt"):
            self.assertIn(need, files)
        self.assertFalse([f for f in files if "/test" in f or "testdata" in f or "/tools/" in f], files)
        for src, dst in data_files(ROOT):
            self.assertEqual(Path(src).parent.relative_to(ROOT).as_posix(), Path(dst).as_posix())

    def test_every_weather_module_is_named_for_the_build(self):
        from weather.packaging import python_modules

        mods = python_modules(ROOT)
        for need in ("weather", "weather.app_section", "weather.generate", "weather.render", "weather.footage", "weather.resolve"):
            self.assertIn(need, mods)
        self.assertIn("weather.packaging import data_files as weather_data_files, python_modules", (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class Footage(unittest.TestCase):
    HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"

    def plan(self, assets):
        from hybrid.beat_csv import plan_from_csv

        rows = 'b1,beat,good morning everyone,map,hold,,Texas,region,,,"good morning everyone dallas stays hot this week",,,,,,,,,,,one\n'
        rows += 'b2,beat,here is the outlook,footage,,,,,,,"here is the outlook for dallas and that is all",,,,,,,,,,,two\n'
        rows += "".join(f"b2,clip,,,,,,,,,,,,,,,,,,{a},,why\n" for a in assets)
        return plan_from_csv(self.HEAD + rows, WORDS, 10.0)

    def test_stock_and_your_own_files_are_allowed(self):
        from weather.footage import footage_beats, footage_problems

        p = self.plan(["stock_video:heat haze over a city street", "stock_image:storm clouds", "media/my_clip.mp4"])
        self.assertEqual(footage_problems(p), [])
        self.assertEqual(footage_beats(p), 1)

    def test_generated_footage_and_youtube_are_refused_naming_the_beat(self):
        from weather.footage import footage_problems

        probs = footage_problems(self.plan(["flow_video:a tornado", "youtube:abc123"]))
        self.assertEqual(len(probs), 2)
        self.assertRegex(probs[0], r"beat b2: clip 'flow_video:a tornado': generated \(Flow\) video is never used")
        self.assertRegex(probs[1], r"beat b2: clip 'youtube:abc123': YouTube footage is used only as an approved")

    def test_a_windows_path_is_a_file_not_a_source(self):
        from weather.footage import _kind

        self.assertEqual(_kind(r"C:\clips\rain.mp4"), "file")
        self.assertEqual(_kind("stock_video:rain"), "stock_video")

