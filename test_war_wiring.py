"""War Documentary wiring: every graphic name the CSV can ask for produces its graphic from the narration, the automatic direction reaches
the new graphics from narration cues alone, and front-line data can be added from the app panel."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from cinematic_explainer.war import app_section as A
from cinematic_explainer.war import frontline as FL
from cinematic_explainer.war import planner
from cinematic_explainer.war import registry
from cinematic_explainer.war.direction import CSV_GRAPHIC

CSV_ROWS = [
    ("title", "This is the war that changed Europe.", "kit_title"),
    ("chapter", "Chapter 2, the battle for the east.", "kit_chapter"),
    ("date", "In February 2022 Russian columns crossed the border.", "kit_datecard"),
    ("quote", 'Zelensky said, "We are all here, defending our independence."', "kit_quote"),
    ("speaker", "Valerii Zaluzhnyi, Ukraine's commander in chief, warned of a stalemate.", "lay_figure_hero"),
    ("number", "Ukraine lost 2,000 troops in a single week.", "kit_bignum"),
    ("compare", "Russia fired 18 shells for every 6 Ukrainian shells.", "kit_versus"),
    ("ratio", "Eight in ten vessel strikes hit merchant ships, according to Ambrey.", "kit_bignum"),
    ("equipment", "HIMARS changed the artillery war in the summer.", "lay_equipment_hero"),
    ("timeline", "In 2014 Russia annexed Crimea, and in 2022 it launched the full invasion.", "lay_timeline"),
    ("map", "Fighting moved from Bakhmut toward Chasiv Yar.", "tac_map"),
    ("route", "Russian columns advanced from Belarus toward Kyiv.", "tac_map"),
    ("institution", "NATO met in Brussels to discuss new aid.", "institution_card"),
    ("supply", "Fuel, rail cars and ammunition trucks all had to reach the front.", "lay_logistics"),
    ("list", "They used tunnels, scooters, civilian clothes and human cover.", "kit_recap"),
    ("steps", "First they cut the bridge, second they shelled the depot, third they advanced.", "kit_chips"),
    ("sticker", "Drones now dominate the battlefield near Bakhmut.", "kit_sticker"),   # no place: the drones type panel instead (rich first)
    ("icons", "Drones, tanks and artillery were used together.", "kit_icons"),
    ("speaker card", "Oleksandr Syrskyi, Ukraine's commander, ordered a pullback.", "kit_speaker"),
    ("claim", "Moscow claimed it had destroyed five HIMARS launchers.", "kit_stamp"),
    ("source", "A report by the Institute for the Study of War found heavy losses.", "lay_document"),
    ("stamp", "The video cannot be verified independently.", "kit_stamp"),
    ("flag", "Poland became the main hub for Western aid.", "kit_flag"),
    ("scale", "Twelve soldiers in single file crossed the field.", "kit_scale"),
    ("radar", "Air defence intercepted drones and missiles over Kyiv.", "kit_radar"),
    ("dossier", "The secret plan ordered troops to take the capital in three days.", "kit_dossier"),
    ("kinetic", "Nobody expected the war to last this long.", "kit_kinetic"),
    ("keywords", "Courage, attrition and patience defined the year.", "kit_keywords"),
    ("chart", "Russia launched 1,200 drones in January, 1,500 in February and 2,100 in March.", "kit_chart"),
    ("article", "According to Reuters, officials said that the depot was destroyed.", "lay_document"),
    ("flyover", "Russia launched dozens of Shahed drones at Kyiv overnight.", "kit_flyover"),
    ("front line", "In February 2024, Russian forces captured Avdiivka after months of fighting.", "tac_map"),
    ("locator", "The strike hit Odesa's port at dawn.", "map_inset"),
    ("label", "Russia fired 44 Iskander-M missiles overnight.", "bc_label"),
    ("caption", "Officials said the depot had burned for two full days.", "bc_caption"),
    ("big word", "America approved 2.1 billion dollars of interceptors.", "bc_bigword"),
]


def plan_rows(rows, footage=None, extra=None):
    t, sc = 0.0, []
    for i, (g, txt) in enumerate(rows):
        s = {"text": txt, "start": t, "end": t + 6.0, "scene_no": i + 1, "graphic": g, "footage": footage, "footage_meta": {}}
        s.update((extra or {}).get(i, {}))
        sc.append(s)
        t += 6.0
    return planner.plan(sc, config={}), sc


def kinds_in(plan, s, csv_only=False):
    return [ly.kind for ly in plan.layers if s["start"] - 0.1 <= ly.start < s["end"] and (not csv_only or (ly.params or {}).get("csv_graphic"))]


class CsvWiringTests(unittest.TestCase):
    def test_every_csv_graphic_name_produces_its_graphic(self):
        plan, sc = plan_rows([(g, t) for g, t, _ in CSV_ROWS])
        cards = registry.all_cards()
        for (g, _t, want), s in zip(CSV_ROWS, sc):
            with self.subTest(graphic=g):
                self.assertIn(want, cards)
                self.assertIn(want, kinds_in(plan, s, csv_only=True))

    def test_every_csv_target_is_handled(self):
        names = {g for g, _t, _k in CSV_ROWS} | {"satellite"}
        targets = {CSV_GRAPHIC[n] for n in names if n in CSV_GRAPHIC}
        self.assertEqual({v for v in CSV_GRAPHIC.values() if v} - targets, set())

    def test_satellite_from_images_column_and_single_still(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, "a.jpg"), Path(d, "b.jpg")
            Image.new("RGB", (640, 360), (80, 80, 80)).save(a)
            Image.new("RGB", (640, 360), (40, 40, 40)).save(b)
            rows = [("satellite", "Satellite images showed the airfield before and after the strike."),
                    ("satellite", "A satellite image of the base taken in March 2024.")]
            plan, sc = plan_rows(rows, extra={0: {"images": f"{a}|{b}"}, 1: {"images": str(a)}})
            self.assertIn("lay_satellite", kinds_in(plan, sc[0], True))
            self.assertIn("lay_satellite", kinds_in(plan, sc[1], True))
            single = [ly for ly in plan.layers if ly.kind == "lay_satellite" and ly.start >= 6.0][0]
            self.assertTrue(single.params.get("single"))

    def test_csv_map_keeps_its_route_and_flag(self):
        plan, sc = plan_rows([("route", "Russian columns advanced from Belarus toward Kyiv.")])
        ly = [l for l in plan.layers if l.kind == "tac_map"][0]
        self.assertTrue(ly.params.get("csv_graphic"))
        self.assertEqual(ly.params["routes"][0]["from"], "Belarus")
        from cinematic_explainer.war import maps_tactical as MT
        self.assertEqual(MT.render_info(ly.params, 3.0, 6.0)["skipped"], [])


class AutomaticWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = str(Path(cls.tmp.name, "clip.mp4"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=8", "-r", "25", cls.clip], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_narration_cues_reach_the_new_graphics(self):
        rows = [("", "Fighting moved from Bakhmut toward Chasiv Yar."),
                ("", "Russia launched 1,200 drones in January, 1,500 in February and 2,100 in March."),
                ("", "According to Reuters, officials said that the depot was destroyed."),
                ("", "Russia fired missiles at the power grid all winter."),
                ("", "In February 2024, Russian forces captured Avdiivka after months of fighting."),
                ("", "Drones struck the Crimean Bridge and Saky air base overnight."),
                ("", "Ukrainian troops liberated Kherson in November 2022.")]
        plan, sc = plan_rows(rows, footage=self.clip)
        self.assertIn("kit_chart", kinds_in(plan, sc[1]))
        self.assertIn("lay_document", kinds_in(plan, sc[2]))
        self.assertIn("kit_flyover", kinds_in(plan, sc[3]))
        for i in (4, 6):
            maps = [ly for ly in plan.layers if ly.kind == "tac_map" and sc[i]["start"] - 0.01 <= ly.start < sc[i]["end"]]
            self.assertTrue(maps and maps[0].params.get("control"), sc[i]["text"])
        site_map = [ly for ly in plan.layers if ly.kind == "tac_map" and sc[5]["start"] - 0.01 <= ly.start < sc[5]["end"]][0]
        self.assertIn("Saky Air Base", [p.get("name") for p in site_map.params["places"] if isinstance(p, dict)])

    def test_chart_never_replaces_a_csv_number(self):
        plan, sc = plan_rows([("number", "Russia launched 1,200 drones in January, 1,500 in February and 2,100 in March.")])
        self.assertNotIn("kit_chart", kinds_in(plan, sc[0]))


class AppFrontlineTests(unittest.TestCase):
    def test_import_from_the_panel(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(FL, "default_dirs", lambda: [FL.DATA_DIR, Path(d) / "frontlines"]):
                self.assertIn("No front-line data yet", A.frontline_summary())
                g = Path(d, "x.geojson")
                g.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
                    "type": "Polygon", "coordinates": [[[36, 47], [37, 47], [37, 48], [36, 48], [36, 47]]]}}]}))
                with self.assertRaises(ValueError):
                    A.import_frontline_file(str(g))                     # no date / source / licence: refused
                A.import_frontline_file(str(g), as_of="2024-01-05", source="Test", licence="test")
                self.assertIn("1 snapshot", A.frontline_summary())
                good, _ = FL.load_library()
                self.assertEqual(good[0]["as_of"], "2024-01-05")

    def test_csv_columns_survive_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "s.csv")
            p.write_text('scene_number,script_segment,asset_type,prompt,graphic,images\n1,"Satellite images showed the base.",none,,satellite,a.jpg|b.jpg\n')
            sc = A.read_scenes_csv(str(p))
            self.assertEqual((sc[0]["graphic"], sc[0]["images"]), ("satellite", "a.jpg|b.jpg"))

    def test_prompt_lists_the_new_graphics(self):
        txt = A.csv_prompt_text("x")
        for name in ("chart", "article", "flyover", "satellite", "locator"):
            self.assertIn(f"    {name} ", txt)


if __name__ == "__main__":
    unittest.main()
