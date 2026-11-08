"""War Documentary stage 2: script-driven control events, strategic sites, front-line sequences, and the new graphics cards.
All front-line data here is synthetic (test_data)."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from cinematic_explainer.render import Layer
from cinematic_explainer.war import catalog as C
from cinematic_explainer.war import frontline as FL
from cinematic_explainer.war import graphics_lib as GL
from cinematic_explainer.war import map_events as ME
from cinematic_explainer.war import maps_tactical as MT
from cinematic_explainer.war import semantics as S
from test_war_frontline import Dec, Plan, Row, synth


class EventTests(unittest.TestCase):
    def test_events_follow_the_script(self):
        t = "In February 2024, Russian forces captured Avdiivka after months of fighting."
        ev = ME.events_for(t, S.analyze_scene(t, C, None, 0, 6), 0.0)
        self.assertEqual((ev[0]["place"], ev[0]["side"], ev[0]["action"], ev[0]["date"]), ("Avdiivka", "russia", "gain", "February 2024"))
        t = "Ukrainian troops liberated Kherson in November 2022."
        ev = ME.events_for(t, S.analyze_scene(t, C, None, 0, 6), 0.0)
        self.assertEqual((ev[0]["side"], ev[0]["action"]), ("ukraine", "gain"))
        t = "Russian troops withdrew from Kherson."
        ev = ME.events_for(t, S.analyze_scene(t, C, None, 0, 6), 0.0)
        self.assertEqual(ev[0]["action"], "loss")

    def test_no_actor_no_event(self):
        t = "The town was captured in 2024."
        self.assertEqual(ME.events_for(t, S.analyze_scene(t, C, None, 0, 6), 0.0), [])

    def test_attach_adds_event_place_and_push_in(self):
        rows = [Row(_no=1, _start=0.0, _end=7.0, text="In February 2024, Russian forces captured Avdiivka.")]
        ly = Layer("tac_map", 0.0, 7.0, {"theme": "tactical", "places": [{"name": "Donetsk"}, {"name": "Bakhmut"}]}, dim=False)
        res = ME.attach(Plan([ly], [Dec(1)]), rows, {}, C)
        self.assertEqual(res["attached"], 1)
        self.assertEqual(ly.params["control"][0]["place"], "Avdiivka")
        self.assertIn("Avdiivka", [p["name"] for p in ly.params["places"] if isinstance(p, dict)])
        self.assertEqual(ly.params["close_steps"][-1], True)

    def test_render_capture(self):
        p = {"theme": "tactical", "places": [{"name": "Avdiivka"}],
             "control": [{"place": "Avdiivka", "side": "russia", "action": "gain", "verb": "captured", "date": "February 2024", "start": 0.5, "length": 1.0}]}
        info = MT.render_info(p, 3.0, 5.0)
        self.assertEqual(info["control"]["events"], 1)
        self.assertIn("RUSSIAN FORCES CAPTURED", info.get("control_chips", []))
        self.assertIsNotNone(MT.tac_map(1.0, 5.0, p))

    def test_unknown_place_skipped(self):
        p = {"theme": "tactical", "places": [{"name": "Kyiv"}], "control": [{"place": "Nowhereville", "side": "russia"}]}
        self.assertEqual(MT.render_info(p, 3.0, 5.0)["control"]["skipped"], ["Nowhereville"])


class SiteTests(unittest.TestCase):
    def test_site_resolves_before_town(self):
        p, _ = MT.resolve_place("Zaporizhzhia nuclear plant")
        self.assertEqual((p["name"], p["site"]), ("Zaporizhzhia Nuclear Power Plant", "nuclear"))
        self.assertNotIn("site", MT.resolve_place("Zaporizhzhia")[0])

    def test_sites_in_text(self):
        names = [s["name"] for _, s in ME.sites_in("Drones hit the Crimean Bridge and Saky air base overnight.")]
        self.assertEqual(names, ["Crimean Bridge", "Saky Air Base"])

    def test_icons_draw(self):
        for k in ME.TYPE_LABEL:
            self.assertGreater(ME.site_icon(k, 32).getchannel("A").getextrema()[1], 0, k)


class SequenceTests(unittest.TestCase):
    S3 = [synth("2022-03-01", west=34.6), synth("2022-09-30", west=35.5), synth("2023-11-30", west=35.7)]

    def test_steps_and_ticker(self):
        spec = {"mode": "sequence", "snaps": self.S3, "times": [0.6, 3.0, 6.0], "length": 2.0}
        sub, i, _ = FL._seq_step(spec, 4.0)
        self.assertEqual((i, sub["a"]["as_of"], sub["b"]["as_of"]), (1, "2022-03-01", "2022-09-30"))
        self.assertEqual(FL._seq_step(spec, 0.2)[1], 0)
        info = MT.render_info({"theme": "tactical", "places": [{"name": "Kharkiv"}], "frontline": spec}, 7.5, 9.0)
        self.assertEqual(info["frontline"]["ticker"][1], "NOV 2023")

    def test_map_across_dated_sentences_becomes_a_sequence(self):
        rows = [Row(_no=1, _start=0.0, _end=4.0, text="By March 2022 Russian troops occupied the south."),
                Row(_no=2, _start=4.0, _end=8.0, text="In late September 2022 the front line shifted."),
                Row(_no=3, _start=8.0, _end=14.0, text="By November 2023 the line had barely moved.")]
        ly = Layer("tac_map", 0.0, 14.0, {"theme": "tactical", "places": [{"name": "Kharkiv"}]}, dim=False)
        res = FL.attach(Plan([ly], [Dec(1), Dec(2), Dec(3)]), rows, {"frontline_snapshots": self.S3})
        self.assertEqual(res["attached"], 1)
        self.assertEqual(ly.params["frontline"]["mode"], "sequence")
        self.assertEqual([s["as_of"] for s in ly.params["frontline"]["snaps"]], ["2022-03-01", "2022-09-30", "2023-11-30"])


class GraphicsTests(unittest.TestCase):
    def test_missing_inputs_draw_nothing(self):
        self.assertIsNone(GL.lay_satellite(1.0, 5.0, {"before": "/nope.jpg", "after": "/nope2.jpg"}))
        self.assertIsNone(GL.lay_document(1.0, 5.0, {}))
        self.assertIsNone(GL.kit_chart(1.0, 5.0, {"items": [{"label": "a", "value": 1}]}))
        self.assertIsNone(GL.kit_flyover(1.0, 5.0, {"name": "unicorn"}))

    def test_cards_render(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, "a.png"), Path(d, "b.png")
            Image.new("RGB", (800, 500), (90, 90, 90)).save(a)
            im = Image.new("RGB", (800, 500), (90, 90, 90))
            ImageDraw.Draw(im).rectangle([300, 200, 400, 300], fill=(20, 20, 20))
            im.save(b)
            for t in (0.5, 2.0, 4.5):
                self.assertEqual(GL.lay_satellite(t, 6.0, {"before": str(a), "after": str(b), "focus": {"x": .3, "y": .3, "w": .2, "h": .2}}).size, (1280, 720))
        self.assertEqual(GL.lay_document(2.0, 5.0, {"text": "The ministry said that losses had doubled.", "highlight": "losses had doubled"}).size, (1280, 720))
        for kind in ("bars", "percent", "line", "donut"):
            self.assertEqual(GL.kit_chart(2.0, 5.0, {"kind": kind, "items": [{"label": "A", "value": 10}, {"label": "B", "value": 30}, {"label": "C", "value": 20}]}).size, (1280, 720))
        self.assertEqual(GL.kit_flyover(1.0, 4.0, {"name": "missile", "label": "MISSILES", "count": 2}).size, (1280, 720))

    def test_chart_uses_the_scripts_figures(self):
        t = "Russia launched 1,200 drones in January, 1,500 in February and 2,100 in March."
        sent = S.analyze_scene(t, C, None, 0, 6).sentences[0]
        c = GL.chart_of(t, sent.numbers)
        self.assertEqual([(i["label"], i["display"]) for i in c["items"]], [("January", "1,200"), ("February", "1,500"), ("March", "2,100")])
        self.assertEqual(c["kind"], "line")
        t2 = "Losses rose to 1,200 and then 3,000."
        self.assertIsNone(GL.chart_of(t2, S.analyze_scene(t2, C, None, 0, 6).sentences[0].numbers))     # unlabelled figures: no chart

    def test_article_and_flyover_cues(self):
        t = "According to Reuters, officials said that the depot was destroyed."
        a = GL.article_of(S.analyze_scene(t, C, None, 0, 6).sentences[0])
        self.assertIsNotNone(a)
        self.assertIn("depot was destroyed", a["highlight"])
        f = GL.flyover_of("Russia launched dozens of Shahed drones at Kyiv.")
        self.assertEqual((f["name"], f["count"]), ("drone", 3))
        self.assertIsNone(GL.flyover_of("The drone factory opened."))

    def test_registered(self):
        from cinematic_explainer.war import registry
        cards = registry.all_cards()
        for k in GL.GFX_CARDS:
            self.assertIn(k, cards)


if __name__ == "__main__":
    unittest.main()
