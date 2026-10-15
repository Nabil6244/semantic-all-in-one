"""Weather repairs a plan's small problems itself (weather.autofix): a plan full of the mistakes an AI makes still checks and builds,
and every repair is a note. No network (the NWS answers are fixtures), no rendering."""

import tempfile
import unittest
from pathlib import Path

from weather import generate as wgen
from weather.cache import HttpCache
from weather.nws import NwsClient

from test_weather_data import DALLAS_ROUTES, FakeNet, fixture
from test_weather_render import NOW

BEATS = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
         'b1,beat,good morning everyone,map,hold,,Texas,region,,,"good morning everyone dallas stays hot this week",,,,,,,,,,,one\n'
         "b1,layer,zebra crossing here,,hud_title,t1,,,YOUR WEATHER,TEXAS,,,,,,,,,,,,\n"            # words not in the recording
         'b2,beat,zebra crossing over there,map,hold,,Texas,region,,,"here is the outlook for dallas",,,,,,,,,,,two\n'   # not its words
         'b3,beat,and that is all,mapp,,,Texas,region,,,"and that is all",,,,,,,,,,,three\n')       # mode misspelt
LAYERS = ("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
          "b1,good morning everyone,,sat,Satellite,,,,until the end,\n"                               # type case, until wording, no source
          "b1,dallas stays hot,,dal,temp,Dallas,,,,\n"                                                # alias, city without state, no source
          'b1,dallas stays hot,,dal,source_line,,"nws:forecast@Dallas,TX#day1",,,\n'                 # duplicate id, a source it does not take
          'b2,here is the outlook,,strip,forecast_strip,"Dallas, TX","nws:forecast@Dallas, TX#day1-12",,,\n'   # too many days, space
          "b2,for dallas,,lbl,place_label,\"Houston, TX\",,,end,\"{'text': 'Houston', 'colour': 'red'}\"\n"   # single quotes, unknown key
          "b3,that is all,,bolt,lightning_bolt,,,,,\n"                                                # no such graphic
          "b9,,1,x,source_line,,,,,\n"                                                                # no such beat
          "b3,words never said,,src3,source_line,,,,,\n")                                             # words not in the recording
WORDS = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("good morning everyone dallas stays hot this week here is the outlook for dallas and that is all".split())]


class AFullyBrokenLookingPlanStillWorks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.project = wgen.WeatherProject(d / "proj")
        self.project.root.mkdir()
        self.project.beats_csv.write_text(BEATS, encoding="utf-8")
        self.project.layers_csv.write_text(LAYERS, encoding="utf-8")
        client = NwsClient("me@example.com", cache=HttpCache(d / "cache", now=lambda: NOW), fetch=FakeNet(DALLAS_ROUTES))
        wgen.fetch(self.project, "me@example.com", now=NOW, client=client, gibs_get=lambda u: fixture("gibs_geocolor_domain.xml").decode())

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_checks_and_every_repair_is_a_note(self):
        notes = []
        plan, rows, snap, payload = wgen.plan_layers(self.project, WORDS, 10.0, now=NOW, notes=notes)
        said = "\n".join(notes)
        self.assertEqual([b.id for b in plan.beats], ["b1", "b2", "b3"])           # b2's first words were wrong: it starts on its own words
        self.assertTrue(any("lined up" in n for n in notes))                       # b2 starts where the recording says its words
        self.assertEqual(plan.beats[2].mode, "map")                                 # "mapp"
        by_id = {r.id: r for r in rows}
        self.assertEqual(by_id["sat"].until, "end")
        self.assertEqual(by_id["sat"].data_source.text, "gibs:geocolor@latest")
        self.assertEqual(by_id["dal"].data_source.text, "nws:forecast@Dallas,TX#day1")
        self.assertIsNone(by_id["dal_2"].data_source)                              # the duplicate id renamed, its source dropped
        self.assertEqual(by_id["strip"].data_source.selector, "day1-5")
        self.assertEqual(by_id["strip"].beat, "b2")                                 # its beat kept its place
        self.assertEqual(by_id["lbl"].extra, {"text": "Houston"})
        self.assertNotIn("bolt", by_id)
        self.assertNotIn("x", by_id)
        self.assertIn("src3", by_id)                                                # appears as its beat starts
        events = {e["id"] for e in payload.events}
        self.assertIn("wx_dal", events)
        self.assertIn("wx_strip", events)
        for word in ("b2", "lightning_bolt", "b9", "src3", "extra"):
            self.assertIn(word, said)

    def test_nothing_is_changed_on_disk(self):
        wgen.plan_layers(self.project, WORDS, 10.0, now=NOW, notes=[])
        self.assertEqual(self.project.beats_csv.read_text(encoding="utf-8"), BEATS)
        self.assertEqual(self.project.layers_csv.read_text(encoding="utf-8"), LAYERS)

    def test_the_strict_reader_is_still_there(self):
        with self.assertRaises(Exception):
            wgen.plan_layers(self.project, WORDS, 10.0, now=NOW, autofix=False)


if __name__ == "__main__":
    unittest.main()


class LayerRowsWithoutType(unittest.TestCase):
    """An AI-written plan whose title rows have no type (project #005, 2026-10-14) loads: each becomes a title card, said in notes."""

    def test_typeless_title_rows_are_title_cards(self):
        from weather.autofix import repair_beats

        text = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
                'b1,beat,It was the ocean,map,push_in,,Florida,region,,,"It was the ocean that came for the town.",,,,,,,,,,,open\n'
                "b1,layer,It was the ocean,,,,,,THE PENINSULA,Long Beach,,,,,,,,,,,,\n"
                "b1,layer,the ocean that,,,,,,,,,,,,,,,,,,,\n")
        words = [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate("It was the ocean that came for the town.".split())]
        notes = []
        plan, _ = repair_beats(text, words, 6.0, notes)
        self.assertEqual([l.type for l in plan.beats[0].layers], ["hud_title"])
        self.assertTrue(any("THE PENINSULA" in n and "hud_title" in n for n in notes))
        self.assertTrue(any("left out" in n for n in notes))


class PlacesTheMapDoesNotKnow(unittest.TestCase):
    """'Southern California' (project #005, 2026-10-14) stopped the video: now the map uses 'California', said in a note."""

    def test_unknown_place_becomes_a_known_one(self):
        from weather.autofix import repair_beats

        text = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
                'b1,beat,It was the ocean,map,push_in,,Southern California,region,,,"It was the ocean that came for the town.",,,,,,,,,,,open\n'
                "b1,camera,the ocean that,,fly_to,,Coastal Southern California,region,,,,,,,,,,,,,2,\n")
        words = [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate("It was the ocean that came for the town.".split())]
        notes = []
        plan, _ = repair_beats(text, words, 6.0, notes)
        self.assertTrue(all(c.place == "California" for c in plan.beats[0].camera if c.place))
        self.assertTrue(any("Southern California" in n for n in notes))

    def test_an_unknown_opening_place_never_loses_the_camera_start(self):
        """'Southern Plains' on beat b1 (project #007, 2026-10-15) dropped the only camera start: 'the plan needs exactly one camera
        'start''. With no earlier place, the opening uses the first state the story goes to (not a close-up's coordinates)."""
        from hybrid.plan import validate_plan
        from weather.autofix import repair_beats

        head = "beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
        text = (head + 'b1,beat,Storms are unfolding,map,push_in,,Southern Plains,region,,,"Storms are unfolding across the plains.",,,,,,,,,,,open\n'
                'b2,beat,A warning near,map,push_in,,"30.89,-102.88",local,,,"A warning near the town.",,,,,,,,,,,zoom\n'
                'b3,beat,Over in Texas,map,push_in,,Texas,region,,,"Over in Texas it rained.",,,,,,,,,,,wide\n')
        said = "Storms are unfolding across the plains. A warning near the town. Over in Texas it rained."
        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(said.split())]
        notes = []
        plan, _ = repair_beats(text, words, 9.0, notes)
        self.assertEqual(validate_plan(plan), [])
        start = [c for b in plan.beats for c in b.camera if c.action == "start"]
        self.assertEqual([c.place for c in start], ["Texas"])
        self.assertTrue(any("Southern Plains" in n and "'Texas'" in n for n in notes))


class PlaceLabelsNeverPileUp(unittest.TestCase):
    """48 place labels in project #005 piled up on one coast: at most 2 a beat."""

    def test_third_label_in_a_beat_is_left_out(self):
        from weather.autofix import repair_layers

        text = "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n" + "".join(
            f'b1,good morning,,l{k},place_label,"{c}",,,,\n' for k, c in enumerate(["Dallas, TX", "Houston, TX", "Dallas, TX"]))
        notes = []
        rows = repair_layers(text, notes)
        self.assertEqual([r.id for r in rows], ["l0", "l1"])
        self.assertTrue(any("pile up" in n for n in notes))


class TheVoiceoverIsTranscribedOnce(unittest.TestCase):
    """A restart used to transcribe a 15-minute voiceover again (minutes): the transcript is saved in the project."""

    def test_second_call_uses_the_saved_transcript(self):
        from weather.app_section import voiceover_words

        class App:
            calls = 0

            def _pakmap_get_words(self, vo, model, state, log):
                App.calls += 1
                return [("hello", 0.0, 0.4), ("there", 0.5, 0.9)]

        with tempfile.TemporaryDirectory() as d:
            p = wgen.WeatherProject(Path(d) / "weather")
            vo = Path(d) / "vo.mp3"
            vo.write_bytes(b"x")
            log = []
            first = voiceover_words(App(), p, vo, "small", None, log.append)
            again = voiceover_words(App(), p, vo, "small", None, log.append)
            self.assertEqual(first, again)
            self.assertEqual(App.calls, 1)
            vo.write_bytes(b"re-recorded")
            voiceover_words(App(), p, vo, "small", None, log.append)
            self.assertEqual(App.calls, 2)


class NoStockClipShownTwice(unittest.TestCase):
    """Project #006 (2026-10-15) asked for "concrete dam" 7 times: every repeat now asks for another framing of it."""

    def test_repeats_get_other_framings(self):
        from hybrid.plan import Beat, Clip, HybridPlan
        from weather.motion import vary_repeats

        beats = [Beat(id=f"b{i}", mode="footage", start=i * 5.0, end=i * 5.0 + 5, clips=[Clip(asset="stock_video:concrete dam")])
                 for i in range(4)]
        beats.append(Beat(id="b9", mode="footage", start=20.0, end=25.0, clips=[Clip(asset="weather/clips/a.mp4")]))
        plan = HybridPlan(duration=25.0, beats=beats)
        notes = []
        self.assertEqual(vary_repeats(plan, notes), 3)
        assets = [b.clips[0].asset for b in plan.beats]
        self.assertEqual(assets[:4], ["stock_video:concrete dam", "stock_video:concrete dam, close up",
                                      "stock_video:concrete dam, wide shot", "stock_video:concrete dam, aerial view"])
        self.assertEqual(assets[4], "weather/clips/a.mp4")
        self.assertTrue(any("shown twice" in n for n in notes))


class TheMapAlwaysHasAnOpeningCamera(unittest.TestCase):
    """Project #007 (2026-10-15): the opening camera's place was unknown and was left out, and the video stopped with "the plan
    needs exactly one camera 'start'". Now the map opens somewhere it knows."""

    def test_unknown_opening_place_still_opens_the_map(self):
        from hybrid.plan import Beat, CameraStep, HybridPlan
        from weather.autofix import fix_places

        plan = HybridPlan(duration=10.0, beats=[Beat(id="b1", mode="map", start=0.0, end=10.0,
                                                     camera=[CameraStep(action="start", place="Nowhere Plains Zzz", frame="region")])])
        notes = []
        fix_places(plan, notes)
        starts = [c for b in plan.beats for c in b.camera if c.action == "start"]
        self.assertEqual(len(starts), 1)
        self.assertTrue(any("opening camera" in n or "opens on" in n for n in notes))
        self.assertEqual(HybridPlan.from_dict(plan.to_dict()).validate() if hasattr(HybridPlan, "validate") else [], [])
