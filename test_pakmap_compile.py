"""pakMap compiler: CSV + narration words -> a pakmap-engine spec and a plan report."""

import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from pakmap import CompileError, CsvError, compile_csv
from pakmap.compile import CLEAR_S, LEAD_S, check_with_engine
from pakmap.words import estimate_words

ROOT = pathlib.Path(__file__).resolve().parent
HAS_NODE = shutil.which("node") is not None

NARRATION = ("Kenya has forty seven million people. Most of them live around Nairobi and Lake Victoria. "
             "The north is another story. Turkana is almost empty. "
             "The equator runs straight through Kenya. Yet the north gets very little rain.")
WORDS = estimate_words(NARRATION)

HEAD = "item_no,vo_anchor,t_start,t_end,hold,layer_type,layer_id,layer_action,geo_ref,label_text,sub_text,color_role,value_from,value_to,value_format,anchor,asset_path,data_source,camera_action,frame,line_kind,offset_s,params\n"
TITLE = '1,Kenya has,,,,hud_title,,,,PART 1,,,,,,,,,,,,,\n'
COLS = HEAD.strip().split(",")


def R(**kw):
    """One CSV line from named columns (so tests never miscount commas)."""
    import csv, io
    unknown = set(kw) - set(COLS)
    assert not unknown, unknown
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow([kw.get(c, "") for c in COLS])
    return buf.getvalue() + "\n"


def build(body, **kw):
    kw.setdefault("validate", False)
    return compile_csv(text=HEAD + body, words=kw.pop("words", WORDS), **kw)


def word_start(text, index=0):
    hits = [s for w, s, _ in WORDS if w.strip(".,").lower() == text.lower()]
    return hits[index]


class TestTiming(unittest.TestCase):
    def test_events_land_on_their_words(self):
        r = build(TITLE + '1,Nairobi,,,,marker,nbo,,Nairobi,NAIROBI,,,,,,,,,,,,,\n')
        ev = {e["id"]: e for e in r.spec["events"]}
        self.assertAlmostEqual(ev["nbo"]["t_in"], word_start("nairobi"), places=2)
        rep = {e.id: e for e in r.report.events}
        self.assertEqual(rep["nbo"].timing, "anchored")
        self.assertEqual(rep["nbo"].matched.strip(".,"), "Nairobi")

    def test_the_title_leads_its_words_by_0_14_s(self):
        r = build('1,Nairobi,,,,hud_title,,,,PART 1,,,,,,,,,,,,,\n')
        self.assertAlmostEqual(r.spec["events"][0]["t_in"], word_start("nairobi") - LEAD_S, places=2)

    def test_explicit_times_offsets_and_the_end_modifier(self):
        r = build(TITLE + '1,,2.5,6.0,,caption,a,,,HELLO,,,,,,bc,,,,,,,\n'
                  '1,Nairobi,,,3,caption,b,,,B,,,,,,bc,,,,,,0.25,\n'
                  '1,Nairobi|end,,,3,caption,c,,,C,,,,,,bc,,,,,,,\n')
        ev = {e["id"]: e for e in r.spec["events"]}
        self.assertEqual((ev["a"]["t_in"], ev["a"]["t_out"]), (2.5, 6.0))
        self.assertAlmostEqual(ev["b"]["t_in"], word_start("nairobi") + 0.25, places=2)
        self.assertGreater(ev["c"]["t_in"] + 0.25, ev["b"]["t_in"])  # the end of "Nairobi" is later than its start
        self.assertEqual(ev["b"]["t_out"], round(ev["b"]["t_in"] + 3, 3))

    def test_a_fixed_half_second_clear_beat_between_items(self):
        r = build(TITLE + '1,Nairobi,,,,fill,f,,Kenya,,,subject,,,,,,,,,,\n2,The equator,,,,hud_title,,,,PART 2,,,,,,,,,,,,,\n')
        ev = {e["id"]: e for e in r.spec["events"]}
        second = ev["i2_hud_title1"]["t_in"]
        self.assertAlmostEqual(ev["i1_hud_title1"]["t_out"], second - CLEAR_S, places=2)
        self.assertAlmostEqual(ev["f"]["t_out"], second - CLEAR_S, places=2)
        self.assertEqual(ev["i2_hud_title1"]["t_out"], r.spec["duration"])  # the last item runs to the end

    def test_unanchored_rows_are_spread_between_their_neighbours_and_flagged(self):
        r = build(TITLE + '1,,,,2,caption,x1,,,A,,,,,,bc,,,,,,\n1,,,,2,caption,x2,,,B,,,,,,bc,,,,,,\n1,Turkana,,,2,caption,x3,,,C,,,,,,bc,,,,,,\n')
        ev = {e["id"]: e for e in r.spec["events"]}
        self.assertLess(ev["i1_hud_title1"]["t_in"], ev["x1"]["t_in"])
        self.assertLess(ev["x1"]["t_in"], ev["x2"]["t_in"])
        self.assertLess(ev["x2"]["t_in"], ev["x3"]["t_in"])
        rep = {e.id: e for e in r.report.events}
        self.assertEqual((rep["x1"].timing, rep["x2"].timing, rep["x3"].timing), ("proportional", "proportional", "anchored"))
        self.assertIn("PROPORTIONAL", r.report.to_text())

    def test_two_rows_can_anchor_on_the_same_words(self):
        r = build(R(item_no=1, vo_anchor="Kenya has forty seven", layer_type="hud_title", label_text="PART 1") + R(item_no=1, vo_anchor="Kenya has", layer_type="fill", layer_id="f", geo_ref="Kenya", color_role="subject"))
        self.assertFalse([w for w in r.report.warnings if "earlier in the narration" in w])

    def test_a_layer_is_cut_at_the_next_item_and_the_warning_explains_why(self):
        r = build(TITLE + '1,Nairobi,,,30,stat,s,,,,,,1,2,0,br,,,,,,,\n2,The equator,,,,hud_title,,,,PART 2,,,,,,,,,,,,,\n')
        ev = {e["id"]: e for e in r.spec["events"]}
        self.assertAlmostEqual(ev["s"]["t_out"], ev["i2_hud_title1"]["t_in"] - CLEAR_S, places=2)
        self.assertTrue(any("would run to" in w and "0.5 s clear beat" in w for w in r.report.warnings))

    def test_out_rows_end_an_earlier_layer(self):
        r = build(TITLE + '1,Nairobi,,,,line,rail,,,,,,,,,,,,,,reference,,"{""coords"": [[0,0],[1,1]]}"\n1,Turkana,,,,line,rail,out,,,,,,,,,,,,,,,\n')
        ev = {e["id"]: e for e in r.spec["events"]}
        self.assertAlmostEqual(ev["rail"]["t_out"], word_start("turkana"), places=2)


class TestErrors(unittest.TestCase):
    def test_a_phrase_that_is_not_in_the_narration_names_the_row(self):
        with self.assertRaises(CompileError) as cm:
            build(TITLE + '1,Atlantis rises,,,,caption,c,,,X,,,,,,bc,,,,,,\n')
        self.assertIn("row 3: can't find 'Atlantis rises' in the narration", cm.exception.report.errors[0])

    def test_an_item_with_no_anchor_at_all_cannot_be_placed(self):
        with self.assertRaises(CompileError) as cm:
            build('1,,,,,hud_title,,,,PART 1,,,,,,,,,,,,,\n')
        self.assertIn("item 1: none of its rows has a vo_anchor or t_start", cm.exception.report.errors[0])

    def test_items_must_follow_the_narration_in_order(self):
        with self.assertRaises(CompileError) as cm:
            build('1,The equator,,,,hud_title,,,,A,,,,,,,,,,,,,\n2,Kenya has,,,,hud_title,,,,B,,,,,,,,,,,,,\n')
        self.assertTrue(any("must follow the narration in order" in e for e in cm.exception.report.errors))

    def test_row_problems_name_their_rows(self):
        with self.assertRaises(CompileError) as cm:
            build(TITLE + '1,Nairobi,,,,marker,m,,Atlantis,ATL,,,,,,,,,,,,,\n'
                  '1,Nairobi,,,,fill,f,,"-1.2,36.8",,,,,,,,,,,,,,\n'
                  '1,Nairobi,,,,line,l,,Mombasa,,,,,,,,,,,,,,\n'
                  '1,Nairobi,,,,stat,s,,,,,,,,,,,,,,,,\n'
                  '1,Nairobi,,,,ghost_shape,g,,Kenya,,,,,,,,,,,,,,\n')
        e = "\n".join(cm.exception.report.errors)
        self.assertIn("row 3: can't find 'Atlantis'", e)
        self.assertIn("row 4: fill needs an area", e)
        self.assertIn("row 5: line needs line_kind", e)
        self.assertIn("row 6: stat needs value_to", e)
        self.assertIn("row 7: ghost_shape needs params.to", e)

    def test_camera_rows_need_a_target_and_unknown_out_layers_are_caught(self):
        with self.assertRaises(CompileError) as cm:
            build(TITLE + R(item_no=1, vo_anchor="Kenya has", layer_type="camera", camera_action="start", frame="country") + R(item_no=1, vo_anchor="Nairobi", layer_type="caption", layer_id="c", layer_action="out"))
        e = "\n".join(cm.exception.report.errors)
        self.assertIn("camera start needs a target", e)
        self.assertIn("refers to layer 'c'", e)

    def test_the_error_says_what_was_actually_heard(self):
        words = [("then", 0.0, 0.3), ("marcebid", 0.5, 1.0), ("is", 1.0, 1.2), ("dry", 1.2, 1.5)]
        with self.assertRaises(CompileError) as cm:
            compile_csv(text=HEAD + R(item_no=1, vo_anchor="Marsabit", layer_type="caption", label_text="X"), words=words, validate=False)
        self.assertIn("closest words heard are 'marcebid' at 0.5s", cm.exception.report.errors[0])

    def test_csv_problems_are_raised_before_compiling(self):
        with self.assertRaises(CsvError):
            compile_csv(text="item_no,layer_type\n1,nonsense\n", words=WORDS)


class TestEvents(unittest.TestCase):
    def ev(self, body):
        return {e["id"]: e for e in build(TITLE + body).spec["events"]}

    def test_marker_prefers_the_city_fill_prefers_the_area(self):
        e = self.ev('1,Nairobi,,,,marker,m,,Nairobi,NAIROBI,,,,,,,,,,,,,"{""value"": ""4.4 MILLION""}"\n1,Nairobi,,,,fill,f,,Kenya,,,compare,,,,,,,,,,,\n'
                    '1,Nairobi,,,,fill,f2,,Nairobi,,,featured,,,,,,,,,,,\n')
        self.assertAlmostEqual(e["m"]["lon"], 36.81, delta=0.05)
        self.assertEqual(e["m"]["value"], "4.4 MILLION")
        self.assertEqual(e["m"]["role"], "dark")
        self.assertEqual((e["f"]["iso"], e["f"]["role"]), (["KEN"], "compare"))
        self.assertIn("polys", e["f2"])  # a county is drawn from its own outline

    def test_stat_caption_zone_label_and_defaults(self):
        e = self.ev('1,forty seven,,,,stat,s,,,,KENYA,,40,47,0 MILLION PEOPLE,tr,,,,,,,\n1,forty seven,,,,stat,s2,,,,,,,9,,,,,,,,,\n'
                    '1,north,,,,caption,c,,,"LINE ONE\\nLINE TWO",SOURCE,,,,,bc,,,,,,,\n1,Turkana,,,,zone_label,z,,"3.1,35.6",TURKANA,,,,,,,,,,,,,\n')
        self.assertEqual((e["s"]["value_from"], e["s"]["value_to"], e["s"]["format"], e["s"]["anchor"], e["s"]["sub"]), (40, 47, "0 MILLION PEOPLE", "tr", "KENYA"))
        self.assertEqual((e["s2"]["value_from"], e["s2"]["format"], e["s2"]["anchor"]), (9, "#,##0", "br"))
        self.assertEqual(e["c"]["text"], "LINE ONE\nLINE TWO")
        self.assertEqual((e["z"]["type"], e["z"]["dot"], e["z"]["role"]), ("marker", False, "neutral"))

    def test_lines_dots_overlays_and_comparisons(self):
        e = self.ev('1,Nairobi,,,,line,l,,Mombasa;Nairobi,,,,,,,,,,,,rail,,\n1,Nairobi,,,,dots,d,,Kenya,,,,,,,,,bundled:populated_places,,,,,"{""per_million"": 99}"\n'
                    '1,Nairobi,,,,value_overlay,v,,Kenya,,,,,,,,,bundled:rainfall_chirps,,,,,\n'
                    '1,Nairobi,,,,ghost_shape,g,,Poland,,,,,,,,,,,,,,"{""to"": {""lon"": 37.6, ""lat"": 2.6}}"\n1,Nairobi,,,,streak,k,,Kenya,,,,,,,,,,,,,,\n'
                    '1,Nairobi,,,,cluster,cl,,Mombasa;Lodwar,,,#FF8800,,,,,,,,,,,\n')
        self.assertEqual(e["l"]["kind"], "rail"); self.assertEqual(len(e["l"]["coords"]), 2)
        self.assertEqual((e["d"]["data"], e["d"]["region_iso"], e["d"]["per_million"]), ("bundled:populated_places", ["KEN"], 99))
        self.assertEqual((e["v"]["data"], e["v"]["clip_iso"]), ("bundled:rainfall_chirps", ["KEN"]))
        self.assertEqual((e["g"]["iso"], e["g"]["to"]["lat"], e["g"]["role"]), ("POL", 2.6, "compare"))
        self.assertEqual(e["k"]["region_iso"], ["KEN"])
        self.assertEqual((e["cl"]["color"], len(e["cl"]["points"])), ("#FF8800", 2))

    def test_media_layers(self):
        e = self.ev('1,Nairobi,,,,pip,p,,Nairobi,NAIROBI,,,,,,tr,a.jpg|b.jpg,,,,,,\n1,Nairobi,,,,filmstrip,fs,,,TURKANA,,,,,,center,t.jpg,,,,,,\n'
                    '1,Nairobi,,,,filmstrip,fs,,,MARSABIT,,,,,,,m.jpg,,,,,,\n1,Nairobi,,,,filmstrip,fs,,,GARISSA,,,,,,,g.jpg,,,,,,\n'
                    '1,Turkana,,,,media_full,mf,,,,,,,,,,clip.mp4,,,,,,\n')
        self.assertEqual((e["p"]["images"], e["p"]["anchor"], e["p"]["label"]), (["a.jpg", "b.jpg"], "tr", "NAIROBI"))
        self.assertIn("leader", e["p"])
        self.assertEqual([c["label"] for c in e["fs"]["cards"]], ["TURKANA", "MARSABIT", "GARISSA"])
        self.assertEqual(e["fs"]["align"], "center")
        self.assertEqual(e["mf"]["media"], "clip.mp4")

    def test_unknown_params_pass_through_to_the_renderer(self):
        e = self.ev('1,Nairobi,,,,marker,m,,Nairobi,N,,,,,,,,,,,,,"{""side"": ""l"", ""future_option"": 5}"\n')
        self.assertEqual((e["m"]["side"], e["m"]["future_option"]), ("l", 5))


class TestCamera(unittest.TestCase):
    def cam(self, body):
        return build(TITLE + body).spec["camera"]

    def test_start_fly_to_and_framing(self):
        c = self.cam('1,Kenya has,,,,camera,,,Kenya,,,,,,,,,,start,country,,,\n1,Nairobi,,,,camera,,,Nairobi,,,,,,,,,,fly_to,local,,,\n')
        self.assertAlmostEqual(c["start"]["lon"], 37.9, delta=0.2)
        self.assertGreater(c["start"]["zoom"], 5)
        mv = c["moves"][0]
        self.assertEqual((mv["type"], mv["to"]["zoom"]), ("fly_to", 8.4))
        self.assertAlmostEqual(mv["t"], word_start("nairobi"), places=2)
        self.assertAlmostEqual(mv["to"]["lon"], 36.81, delta=0.05)

    def test_any_row_can_carry_a_camera_move_and_push_in_is_relative(self):
        c = self.cam(R(item_no=1, vo_anchor="Kenya has", layer_type="camera", geo_ref="Kenya", camera_action="start", frame="country")
                     + R(item_no=1, vo_anchor="Nairobi", layer_type="caption", layer_id="c", label_text="X", anchor="bc", geo_ref="Kenya", camera_action="fly_to", frame="region")
                     + R(item_no=1, vo_anchor="Turkana", layer_type="camera", camera_action="push_in"))
        self.assertEqual([m["type"] for m in c["moves"]], ["fly_to", "push_in"])
        self.assertAlmostEqual(c["moves"][1]["to"]["zoom"], c["moves"][0]["to"]["zoom"] + 1.0, places=2)

    def test_overlapping_moves_are_shortened_with_a_warning_and_too_close_ones_refused(self):
        r = build(TITLE + '1,Kenya has,,,,camera,,,Kenya,,,,,,,,,,start,country,,,\n1,Nairobi,,,,camera,,,Nairobi,,,,,,,,,,fly_to,local,,,\n'
                  '1,Lake Victoria,,,,camera,,,Lodwar,,,,,,,,,,fly_to,local,,,\n')
        a, b = r.spec["camera"]["moves"]
        self.assertLessEqual(a["t"] + a["dur"], b["t"])
        with self.assertRaises(CompileError) as cm:
            build(TITLE + '1,Nairobi,,,,camera,,,Nairobi,,,,,,,,,,fly_to,local,,,\n1,Nairobi,,,,camera,,,Lodwar,,,,,,,,,,fly_to,local,,0.1,\n')
        self.assertIn("too close together", " ".join(cm.exception.report.errors))

    def test_defaults_are_explained_and_a_pull_back_into_the_globe_no_longer_warns(self):
        r = build(TITLE)
        self.assertIn("default world view", " ".join(r.report.warnings))
        r2 = build(TITLE + '1,Kenya has,,,,camera,,,Kenya,,,,,,,,,,start,country,,,\n1,Nairobi,,,,camera,,,Kenya,,,,,,,,,,pull_back,globe,,,\n')
        self.assertNotIn("globe", " ".join(r2.report.warnings))  # the zoom-out artifact is fixed (Phase 8): nothing to warn about


@unittest.skipUnless(HAS_NODE and (ROOT / "pakmap-engine" / "tools" / "validate_spec.mjs").exists(), "node or the engine is not available")
class TestRendererRules(unittest.TestCase):
    def test_the_renderers_own_rules_are_applied_and_name_the_layers(self):
        body = ('1,Kenya has,,,,hud_title,,,,PART 1,SUB,,,,,,,,,,,,\n' + "".join(f'1,Nairobi,,,10,caption,c{i},,,TEXT {i},,,,,,bc,,,,,,,\n' for i in range(5)))
        with self.assertRaises(CompileError) as cm:
            compile_csv(text=HEAD + body, words=WORDS)
        e = " ".join(cm.exception.report.errors)
        self.assertIn("renderer rule:", e)
        self.assertIn("text layers are on screen", e)
        self.assertIn("c0", e)

    def test_a_valid_script_passes_and_media_under_a_camera_move_is_refused(self):
        ok = compile_csv(text=HEAD + '1,Kenya has,,,,hud_title,,,,PART 1,SUB,,,,,,,,,,,,\n', words=WORDS)
        self.assertEqual(ok.report.errors, [])
        with self.assertRaises(CompileError) as cm:
            compile_csv(text=HEAD + '1,Kenya has,,,,hud_title,,,,PART 1,,,,,,,,,,,,,\n1,Nairobi,6,12,,media_full,mf,,,,,,,,,,clip.mp4,,,,,,\n'
                        '1,Kenya has,,,,camera,,,Kenya,,,,,,,,,,start,country,,,\n1,Nairobi,8,,,camera,,,Nairobi,,,,,,,,,,fly_to,local,3,,\n', words=WORDS)
        self.assertIn("runs under full-screen media", " ".join(cm.exception.report.errors))

    def test_check_with_engine_runs(self):
        e, w, ran = check_with_engine({"width": 1920, "height": 1080, "fps": 30, "duration": 5, "camera": {"start": {"lon": 0, "lat": 0, "zoom": 3}}, "events": []})
        self.assertTrue(ran)
        self.assertEqual(e, [])


def _can_render() -> bool:
    if not (HAS_NODE and shutil.which("ffmpeg")):
        return False
    return (ROOT / "flow-engine" / "node_modules" / "playwright").exists() and (ROOT / "pakmap-engine" / "node_modules" / "maplibre-gl").exists()


@unittest.skipUnless(_can_render(), "needs node, ffmpeg, Playwright and the engine's packages")
class TestRendersForReal(unittest.TestCase):
    def test_a_compiled_script_renders_through_the_engine_with_every_layer_type(self):
        samples = ROOT / "pakmap-engine" / "samples"
        words = estimate_words((samples / "kenya-story.txt").read_text(encoding="utf-8"))
        res = compile_csv(samples / "kenya-story.csv", words, watermark={"text": "Test Channel"})
        d = pathlib.Path(tempfile.mkdtemp())
        spec = dict(res.spec, output=str(d / "out.mp4"), cache_dir=str(d / "cache"), width=480, height=270, fps=4, imagery_enabled=False, flat_only=True)
        (d / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        run = subprocess.run(["node", str(ROOT / "pakmap-engine" / "render.mjs"), str(d / "spec.json")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                             env={**__import__("os").environ, "PAKMAP_GL": "software"})
        events = [json.loads(l) for l in run.stdout.splitlines() if l.startswith("{")]
        self.assertEqual(events[-1]["event"], "done", run.stdout[-800:] + run.stderr[-800:])
        sidecar = json.loads((d / "out.mp4.pakmap.json").read_text())
        self.assertTrue(any("CHIRPS" in a for a in sidecar["credits"]["attribution"]))
        self.assertTrue(any("Natural Earth" in a for a in sidecar["credits"]["attribution"]))
        self.assertEqual(sidecar["frames"], round(res.spec["duration"] * 4))


class TestWholeScript(unittest.TestCase):
    SAMPLES = ROOT / "pakmap-engine" / "samples"

    def test_the_sample_script_compiles_and_every_event_is_inside_the_video(self):
        words = estimate_words((self.SAMPLES / "kenya-story.txt").read_text(encoding="utf-8"))
        r = compile_csv(self.SAMPLES / "kenya-story.csv", words, validate=HAS_NODE, watermark={"text": "Your Channel"})
        self.assertEqual(r.report.errors, [])
        self.assertEqual(len(r.spec["events"]), 21)
        d = r.spec["duration"]
        for e in r.spec["events"]:
            self.assertTrue(0 <= e["t_in"] < e["t_out"] <= d + 1e-6, e["id"])
        self.assertEqual(r.spec["watermark"]["text"], "Your Channel")
        self.assertEqual(r.spec["base_dir"], str(self.SAMPLES))
        json.dumps(r.spec)
        self.assertIn("21 events", r.report.to_text())

    def test_the_command_line_writes_a_spec(self):
        d = pathlib.Path(tempfile.mkdtemp())
        run = lambda *a: subprocess.run(["python3", "-m", "pakmap", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(run("words", str(self.SAMPLES / "kenya-story.txt"), "--out", str(d / "w.json")).returncode, 0)
        out = run("compile", str(self.SAMPLES / "kenya-story.csv"), "--words", str(d / "w.json"), "--out", str(d / "spec.json"))
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertEqual(len(json.loads((d / "spec.json").read_text())["events"]), 21)
        self.assertNotEqual(run("check", str(self.SAMPLES / "kenya-story.csv"), "--words", str(d / "w.json"), "--duration", "5").returncode, 0)


if __name__ == "__main__":
    unittest.main()
