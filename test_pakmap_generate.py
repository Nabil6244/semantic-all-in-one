"""pakMap generation (the part the app calls, without Tk): compile -> engine -> add the narration -> validate."""

import json
import pathlib
import shutil
import subprocess
import tempfile
import threading
import unittest

from pakmap.app_integration import PakmapResult, check_pakmap_plan, credits_text, generate_pakmap_video
from pakmap.engine_runner import PakmapRenderCancelled, PakmapRenderError, RenderOutcome, cache_dir, engine_dir, render_spec
from pakmap.words import estimate_words

ROOT = pathlib.Path(__file__).resolve().parent
HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_NODE = shutil.which("node") is not None
NARRATION = "Kenya has forty seven million people. Most of them live around Nairobi. The north is almost empty."
WORDS = estimate_words(NARRATION)
CSV = ("item_no,vo_anchor,layer_type,layer_id,label_text,sub_text,geo_ref,value_to,value_format,camera_action,frame\n"
       "1,Kenya has,hud_title,,PART 1,THE EMPTY HALF,,,,,\n"
       "1,Kenya has,camera,c0,,,Kenya,,,start,country\n"
       "1,forty seven million,stat,pop,,KENYA,,47,0 MILLION PEOPLE,,\n"
       "1,Nairobi,marker,nbo,NAIROBI,,Nairobi,,,,\n")


def _ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not available")
class TestGenerate(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.csv = self.d / "script.csv"
        self.csv.write_text(CSV, encoding="utf-8")
        self.vo = self.d / "vo.wav"
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=6", str(self.vo))
        self.out = self.d / "final" / "video.mp4"
        self.out.parent.mkdir()
        self.work = self.d / "work"
        self.logs, self.progress, self.specs = [], [], []

    def fake_render(self, spec, output, *, progress=None, cancel_check=None, log=print, **kw):
        self.specs.append(spec)
        if progress:
            for i in (1, 5, 10):
                progress(i, 10)
        _ffmpeg("-f", "lavfi", "-i", f"color=c=0x285ac8:size=640x360:rate=30:duration={spec['duration']}", "-pix_fmt", "yuv420p", str(output))
        return RenderOutcome(pathlib.Path(output), 10, {
            "credits": {"attribution": ["We acknowledge the use of imagery provided by NASA GIBS.", "Rainfall: CHIRPS"], "notes": ["Historical Landsat imagery, not current."]},
            "warnings": [{"message": "Frame is narrower than the soft limit"}],
        })

    def run_gen(self, **kw):
        kw.setdefault("render", self.fake_render)
        return generate_pakmap_video(self.csv, self.vo, self.out, work_dir=self.work, whisper_words=WORDS, base_dir=self.d, resolution="640x360", fps=30,
                                     progress_cb=lambda m, f: self.progress.append((m, f)), log=self.logs.append, **kw)

    def test_a_full_run_produces_a_valid_video_with_the_narration(self):
        r = self.run_gen(watermark={"text": "My Channel"})
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.output_path, self.out)
        probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(self.out)], capture_output=True, text=True).stdout)
        self.assertEqual({s["codec_type"] for s in probe["streams"]}, {"video", "audio"})
        self.assertAlmostEqual(float(probe["format"]["duration"]), 6.0, delta=0.6)

    def test_the_spec_the_engine_receives_follows_the_voiceover_and_the_settings(self):
        self.run_gen(watermark={"text": "My Channel"})
        spec = self.specs[0]
        self.assertAlmostEqual(spec["duration"], 6.0, delta=0.2)
        self.assertEqual((spec["width"], spec["height"], spec["fps"]), (640, 360, 30))
        self.assertEqual(spec["watermark"], {"text": "My Channel"})
        self.assertEqual(spec["base_dir"], str(self.d))
        self.assertEqual({e["type"] for e in spec["events"]}, {"hud_title", "stat", "marker"})

    def test_plan_and_spec_are_kept_with_the_project_and_credits_sit_next_to_the_video(self):
        self.run_gen()
        self.assertTrue((self.work / "pakmap_spec.json").is_file())
        self.assertIn("hud_title", (self.work / "pakmap_plan.txt").read_text())
        credits = (self.out.parent / "video - credits.txt").read_text()
        self.assertIn("NASA GIBS", credits)
        self.assertIn("Historical Landsat", credits)
        self.assertIn("soft limit", credits)

    def test_credits_and_renderer_warnings_come_back_to_the_app(self):
        r = self.run_gen()
        self.assertEqual(r.credits[:2], ["We acknowledge the use of imagery provided by NASA GIBS.", "Rainfall: CHIRPS"])
        self.assertTrue(any("soft limit" in w for w in r.warnings))
        self.assertIsNotNone(r.report)

    def test_progress_runs_forward_and_ends_at_100_percent(self):
        self.run_gen()
        fr = [f for _, f in self.progress]
        self.assertEqual(fr, sorted(fr))
        self.assertEqual(self.progress[-1], ("Done.", 1.0))
        self.assertTrue(any("Drawing the map" in m for m, _ in self.progress))

    def test_a_script_problem_stops_before_anything_is_drawn(self):
        self.csv.write_text(CSV.replace("Nairobi,marker", "Atlantis rises,marker"), encoding="utf-8")
        r = self.run_gen()
        self.assertFalse(r.ok)
        self.assertIn("can't find 'Atlantis rises'", r.errors[0])
        self.assertEqual(self.specs, [], "the renderer must not be started")
        self.assertIsNotNone(r.report)
        self.csv.write_text("item_no,layer_type\n1,nonsense\n", encoding="utf-8")
        self.assertIn("unknown layer_type", self.run_gen().errors[0])

    def test_a_renderer_failure_is_reported_in_plain_words(self):
        def boom(spec, output, **kw):
            raise PakmapRenderError("pakMap render failed: map setup failed: no browser")
        r = self.run_gen(render=boom)
        self.assertFalse(r.ok)
        self.assertEqual(r.errors, ["pakMap render failed: map setup failed: no browser"])
        r2 = self.run_gen(render=lambda *a, **k: (_ for _ in ()).throw(ValueError("weird")))
        self.assertIn("unexpected error while drawing the map", r2.errors[0])

    def test_stop_is_honoured_during_the_drawing_and_before_it(self):
        def cancelled(spec, output, **kw):
            raise PakmapRenderCancelled("stopped")
        r = self.run_gen(render=cancelled)
        self.assertTrue(r.cancelled and not r.ok)
        ev = threading.Event(); ev.set()
        r2 = self.run_gen(cancel_check=ev.is_set)
        self.assertTrue(r2.cancelled)
        self.assertEqual(self.specs, [])

    def test_missing_inputs_are_explained(self):
        self.assertIn("CSV not found", generate_pakmap_video(self.d / "no.csv", self.vo, self.out, work_dir=self.work, whisper_words=WORDS).errors[0])
        self.assertIn("voiceover file not found", generate_pakmap_video(self.csv, self.d / "no.wav", self.out, work_dir=self.work, whisper_words=WORDS).errors[0])
        self.assertIn("no word times", generate_pakmap_video(self.csv, self.vo, self.out, work_dir=self.work, whisper_words=[]).errors[0])
        self.assertIn("bad resolution", generate_pakmap_video(self.csv, self.vo, self.out, work_dir=self.work, whisper_words=WORDS, resolution="big").errors[0])

    def test_a_render_that_produces_a_wrong_length_video_is_not_called_a_success(self):
        def short(spec, output, **kw):
            _ffmpeg("-f", "lavfi", "-i", "color=c=red:size=640x360:rate=30:duration=1", "-pix_fmt", "yuv420p", str(output))
            return RenderOutcome(pathlib.Path(output), 1, {})
        r = self.run_gen(render=short)
        # the narration is longer than the picture: the shared exporter holds the last frame, so either it fits or it is refused, never a silent mismatch
        if r.ok:
            probe = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.out)], capture_output=True, text=True).stdout)
            self.assertAlmostEqual(probe, 6.0, delta=1.5)
        else:
            self.assertTrue(r.errors)


class TestPlanCheck(unittest.TestCase):
    def setUp(self):
        self.csv = pathlib.Path(tempfile.mkdtemp()) / "s.csv"
        self.csv.write_text(CSV, encoding="utf-8")

    def test_a_good_plan_returns_the_report(self):
        res, report, problems = check_pakmap_plan(self.csv, WORDS, duration=6.0)
        self.assertIsNotNone(res)
        self.assertEqual(problems, [])
        self.assertIn("3 events", report.to_text())

    def test_problems_are_returned_not_raised(self):
        self.csv.write_text(CSV.replace("forty seven million", "never said"), encoding="utf-8")
        res, report, problems = check_pakmap_plan(self.csv, WORDS, duration=6.0)
        self.assertIsNone(res)
        self.assertIn("never said", problems[0])
        self.assertIsNotNone(report)
        res2, report2, problems2 = check_pakmap_plan(self.csv.parent / "gone.csv", WORDS)
        self.assertIsNone(res2); self.assertTrue(problems2)
        self.csv.write_text("item_no,layer_type\n1,nonsense\n", encoding="utf-8")
        self.assertIn("unknown layer_type", check_pakmap_plan(self.csv, WORDS)[2][0])

    def test_credits_text(self):
        t = credits_text(["A", "B"], ["note"])
        self.assertIn("- A", t); self.assertIn("- B", t); self.assertIn("- note", t)


def _has_browser():
    """Playwright's own Chromium is installed (a CI runner may only have a system Chrome)."""
    try:
        from providers.playwright_chromium import is_playwright_chromium_installed

        return bool(is_playwright_chromium_installed())
    except Exception:
        return False


def _can_render():
    return HAS_NODE and HAS_FFMPEG and _has_browser() and (ROOT / "flow-engine" / "node_modules" / "playwright").exists() and (ROOT / "pakmap-engine" / "node_modules" / "maplibre-gl").exists()


@unittest.skipUnless(_can_render(), "needs node, ffmpeg, Playwright and the engine's packages")
class TestEngineRunner(unittest.TestCase):
    def spec(self, duration=2):
        return {"width": 320, "height": 180, "fps": 5, "duration": duration, "camera": {"start": {"lon": 20, "lat": 40, "zoom": 3}, "drift": {"pct_per_s": 0.5}, "moves": []},
                "events": [{"id": "h", "type": "hud_title", "t_in": 0.2, "t_out": duration, "label": "PART 1"}], "overlays": {"borders": False, "fills": []},
                "watermark": {"text": "Test"}}

    def test_the_real_engine_renders_a_spec_and_reports_progress(self):
        out = pathlib.Path(tempfile.mkdtemp()) / "m.mp4"
        seen = []
        r = render_spec(self.spec(), out, progress=lambda a, b: seen.append((a, b)), imagery=False)
        self.assertTrue(out.is_file())
        self.assertEqual(r.frames, 10)
        self.assertEqual(seen[-1], (10, 10))
        self.assertTrue(any("CHIRPS" not in a for a in r.sidecar["credits"]["attribution"]))
        self.assertFalse(list(out.parent.glob(".*rendering*")), "no half-written file is left behind")

    def test_an_engine_error_comes_back_with_its_message(self):
        bad = self.spec(); bad["events"] = [{"id": "x", "type": "stat", "t_in": 0, "t_out": 1, "value_to": "no"}]
        with self.assertRaisesRegex(PakmapRenderError, "value_to"):
            render_spec(bad, pathlib.Path(tempfile.mkdtemp()) / "m.mp4", imagery=False)

    def test_stop_kills_the_render_and_leaves_nothing(self):
        out = pathlib.Path(tempfile.mkdtemp()) / "m.mp4"
        ev = threading.Event()
        def stop_after_first(a, b):
            ev.set()
        with self.assertRaises(PakmapRenderCancelled):
            render_spec(self.spec(duration=20), out, progress=stop_after_first, cancel_check=ev.is_set, imagery=False)
        self.assertFalse(out.exists())
        self.assertFalse(list(out.parent.glob(".*rendering*")))

    def test_paths(self):
        self.assertTrue((engine_dir() / "render.mjs").is_file())
        self.assertTrue(cache_dir().is_dir())


if __name__ == "__main__":
    unittest.main()


class TestPackagingAndDiscovery(unittest.TestCase):
    def test_the_packaged_file_list_has_what_the_renderer_loads_and_nothing_else(self):
        from pakmap.packaging import engine_data_files

        files = engine_data_files(ROOT)
        names = {pathlib.Path(s).relative_to(ROOT).as_posix() for s, _ in files}
        for needed in ("pakmap-engine/render.mjs", "pakmap-engine/page.js", "pakmap-engine/page.html", "pakmap-engine/lib/draw.mjs",
                       "pakmap-engine/lib/camera.mjs", "pakmap-engine/lib/datasets.mjs", "pakmap-engine/assets/fonts/Montserrat-VF.ttf",
                       "pakmap-engine/data/rainfall_chirps_2016_2020_0p1.i16.gz", "pakmap-engine/data/places_index.json.gz",
                       "pakmap-engine/data/populated_places.json.gz", "pakmap-engine/package.json", "pakmap-engine/tools/validate_spec.mjs",
                       "pakmap-engine/node_modules/maplibre-gl/dist/maplibre-gl.mjs", "pakmap-engine/node_modules/geotiff/package.json"):
            self.assertIn(needed, names)
        for unwanted in ("pakmap-engine/test/", "pakmap-engine/samples/", "pakmap-engine/node_modules/@maplibre/", "pakmap-engine/tools/build_datasets.py", "pakmap-engine/tools/make_demo_media.py"):
            self.assertFalse([n for n in names if n.startswith(unwanted)], unwanted)
        self.assertTrue(all(pathlib.Path(s).is_file() for s, _ in files))
        self.assertTrue(all(not d.startswith("/") for _, d in files), "destinations are relative to the app root")

    def test_a_missing_node_package_is_explained_at_build_time(self):
        from pakmap.packaging import npm_closure

        with self.assertRaisesRegex(FileNotFoundError, "npm ci"):
            npm_closure(ROOT / "pakmap-engine" / "node_modules", "no-such-package")

    def test_the_apps_own_node_is_preferred_over_the_path(self):
        from unittest import mock

        import pakmap.compile as pc

        with mock.patch("providers.flow.engine_manager._find_node_binary", return_value="/app/bin/node"):
            self.assertEqual(pc._find_node(), "/app/bin/node")
        with mock.patch("providers.flow.engine_manager._find_node_binary", return_value=None), mock.patch("shutil.which", return_value="/usr/bin/node"):
            self.assertEqual(pc._find_node(), "/usr/bin/node")

    def test_the_city_index_is_found_through_the_engine_location(self):
        from pakmap import geo

        self.assertTrue(geo._engine_data("places_index.json.gz").is_file())
