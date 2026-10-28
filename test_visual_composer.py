"""Visual composer: a relevant graphic for any narration (finance, history, cooking, ...), the relevance gate on 3D shots, and the What If hook."""
import json
import unittest

from visual_composer import apply as vc, compose, concepts
from whatif import planner
from whatif.planner import Shot


def timed(script, per=0.34):
    t, out = 0.0, []
    for w in script.split():
        out.append((w, round(t, 3), round(t + per * 0.9, 3)))
        t += per
    return out


class Concepts(unittest.TestCase):
    CASES = [
        ("Bitcoin fell 40% in a single week.", "change"),
        ("The Roman Empire lasted from 27 BC until 476 AD, and in 1453 Constantinople fell.", "timeline"),
        ("First you mix the flour, then let it rest, and finally bake it.", "process"),
        ("Shipping, banking, retail and farming all depend on it.", "list"),
        ("The company earned $4.2 billion last year.", "stat"),
        ("An enzyme is a protein that speeds up a reaction.", "term"),
        ("Tokyo is 3 times more crowded than Paris.", "compare"),
        ('She said "we will never give up this fight" to the crowd.', "quote"),
        ("Only 12 percent of voters turned out.", "percent"),
        ("It was a quiet evening in the village.", "keyword"),
    ]

    def test_kinds_follow_the_sentence_not_a_topic(self):
        for text, kind in self.CASES:
            self.assertEqual(concepts.analyze(text).kind, kind, text)

    def test_figures_and_names_come_from_the_sentence(self):
        c = concepts.analyze("Tokyo is 3 times more crowded than Paris.")
        self.assertEqual(c.names, ["PARIS", "TOKYO"])
        self.assertEqual(c.values, [1.0, 3.0])
        c = concepts.analyze("The company earned $4.2 billion last year.")
        self.assertEqual((c.values, c.unit, c.prefix), ([4.2], "BILLION", "$"))
        c = concepts.analyze("The Roman Empire lasted from 27 BC until 476 AD, and in 1453 Constantinople fell.")
        self.assertEqual(c.years, [-27, 476, 1453])

    def test_every_kind_composes_a_valid_graphic_both_sizes(self):
        for text, kind in self.CASES:
            c = concepts.analyze(text)
            for plate in (True, False):
                t = compose.compose(c, plate=plate)
                self.assertIsNotNone(t, (kind, plate))
                self.assertEqual(compose.problems(t), [], (kind, plate))
                json.dumps(t)

    def test_author_output_is_kept_only_if_it_validates(self):
        c = concepts.analyze("Sales doubled.")
        good = json.dumps({"id": "x", "family": "composed", "use": "u", "items": [{"p": "text", "text": "SALES DOUBLED", "at": [0.5, 0.5]}]})
        bad = json.dumps({"id": "x", "family": "composed", "use": "u", "items": [{"p": "fireworks"}]})
        self.assertIsNotNone(compose.author("Sales doubled.", c, lambda s, u: good))
        self.assertIsNone(compose.author("Sales doubled.", c, lambda s, u: bad))
        self.assertIsNone(compose.author("Sales doubled.", c, lambda s, u: "no json"))


class Gate(unittest.TestCase):
    def test_a_model_not_about_its_narration_becomes_a_picture_of_it(self):
        shots = [Shot(id="a", start=0, end=6, kind="craft", model="voyager.glb", name="VOYAGER 1", text="Prices climbed across the country."),
                 Shot(id="b", start=6, end=12, kind="image", text="Wages rose more slowly."),
                 Shot(id="c", start=12, end=18, kind="craft", model="voyager.glb", name="VOYAGER 1", text="Voyager 1 left the solar system."),
                 Shot(id="d", start=18, end=24, kind="craft", model="voyager.glb", name="VOYAGER 1", text="The probe kept going.")]
        notes = []
        self.assertEqual(vc.gate_3d(shots, notes), 1)
        self.assertEqual([s.kind for s in shots], ["image", "image", "craft", "craft"])
        self.assertTrue(shots[0].asset.startswith("flow_image:"))
        self.assertIn("Prices climbed", shots[0].asset)


class WhatIfHook(unittest.TestCase):
    SCRIPT = ("Every great city begins with a simple promise to the people who live there and it keeps that promise for many long years. "
              "In 2008 the housing market collapsed and house prices fell 30 percent across the whole country within a single year. "
              "To bake the bread you first mix the flour and water, then let the dough rest, and finally bake it in a hot oven. "
              "The average family spent 4 times more on rent than on food, and nobody had planned for that at all in advance.")

    def test_a_money_and_cooking_video_gets_its_own_graphics(self):
        raw = timed(self.SCRIPT)
        p = planner.plan(raw, self.SCRIPT, raw[-1][2] + 0.5, "Housing", flow_video="images")
        composed = [L for L in p.layers if L.get("composed")]
        self.assertGreaterEqual(len(composed), 1, p.notes)       # the figures already have callouts; the baking steps get their own graphic
        kinds = {L["composed"] for L in composed}
        self.assertIn("process", kinds)
        for L in composed:
            self.assertEqual(compose.problems(L["template"]), [])
            self.assertFalse(L["plate"])
        self.assertTrue(any("composed" in n for n in p.notes))


class SceneComposer(unittest.TestCase):
    def test_scene_comes_from_the_sentence_not_a_model_list(self):
        from visual_composer.scene import scene_for

        spec, conf = scene_for("Then the probe fell under its parachute through thick clouds.")
        self.assertEqual((spec["layout"], spec["craft"]["kind"], spec["craft"]["parachute"]), ("craft", "capsule", True))
        self.assertTrue(spec["env"]["clouds"] and spec["motion"]["fall"] > 0)
        spec, conf = scene_for("A frozen world of ice with a thin blue atmosphere.")
        self.assertEqual(spec["world"]["type"], "ice")
        spec, _ = scene_for("Lava flows across a red molten planet.")
        self.assertEqual(spec["world"]["type"], "lava")
        self.assertNotEqual(scene_for("A red molten planet.")[0]["world"]["palette"], scene_for("A blue molten planet.")[0]["world"]["palette"])
        self.assertNotEqual(scene_for("A red molten planet.")[0]["seed"], scene_for("A red molten world.")[0]["seed"])
        self.assertIsNone(scene_for("Prices rose 20 percent last year."))

    def test_pictures_about_drawable_things_become_scenes_but_photos_and_neighbours_do_not(self):
        shots = [Shot(id="a", start=0, end=5, kind="image", text="A frozen world of ice."), Shot(id="b", start=5, end=10, kind="image", text="A frozen world of ice again."),
                 Shot(id="c", start=10, end=15, kind="image", text="The photo showed a frozen world of ice."), Shot(id="d", start=15, end=20, kind="video", text="Prices rose 20 percent.")]
        n = vc.upgrade_scenes(shots, [])
        self.assertEqual([s.kind for s in shots], ["scene", "image", "image", "video"])
        self.assertEqual(n, 1)
        self.assertEqual(shots[0].extra["scene_spec"]["world"]["type"], "ice")


class SceneSliceTwo(unittest.TestCase):
    def test_interior_and_field_sentences(self):
        from visual_composer.scene import scene_for

        spec, _ = scene_for("Inside the planet, the core is surrounded by layers of molten rock.")
        self.assertGreaterEqual(len(spec["world"]["cutaway"]["layers"]), 3)
        self.assertEqual(spec["camera"]["path"], "orbit")
        spec, _ = scene_for("Jupiter's magnetic field is the strongest of any planet.")
        self.assertTrue(spec["world"]["field"]["lines"] >= 8)
        self.assertNotIn("cutaway", spec["world"])

    def test_cutaway_layers_carry_labels_per_world_type(self):
        from visual_composer.scene import LAYERS, scene_for

        gas, _ = scene_for("Inside the giant gas planet the core is wrapped in layers of hydrogen.")
        self.assertEqual([l["label"] for l in gas["world"]["cutaway"]["layers"]], ["CLOUD DECK", "LIQUID HYDROGEN", "METALLIC HYDROGEN", "CORE"])
        rock, _ = scene_for("Inside the planet, the core is surrounded by layers of molten rock.")
        self.assertTrue(all(l["label"] for l in rock["world"]["cutaway"]["layers"]))
        for t, rows in LAYERS.items():
            self.assertTrue(all(len(r) == 3 and r[2] and len(r[2]) <= 22 for r in rows), t)

    def test_a_falling_craft_inside_the_air_is_not_a_cutaway(self):
        from visual_composer.scene import scene_for

        spec, _ = scene_for("The probe fell deeper into the clouds, inside the storm.")
        self.assertEqual(spec["layout"], "craft")
        self.assertNotIn("cutaway", spec.get("world", {}))

    def test_ai_author_is_kept_only_when_valid(self):
        import json as _json

        from visual_composer import scene

        good = _json.dumps({"layout": "planet", "world": {"type": "ocean", "palette": ["#112233", "#445566"], "city": 0.8}, "camera": {"path": "orbit"}})
        spec, conf = scene.author("A water world glowing with cities at night.", lambda s, u: "Sure!\n" + good)
        self.assertEqual((spec["world"]["type"], conf), ("ocean", 0.7))
        for bad in ('{"layout":"planet","world":{"type":"cheese"}}', "{}", "not json", '{"layout":"planet","world":{"type":"gas","palette":["red"]}}'):
            self.assertIsNone(scene.author("x", lambda s, u, b=bad: b))

    def test_a_sentence_the_rules_cannot_read_goes_to_the_author_and_is_capped(self):
        import json as _json

        calls = []
        spec = _json.dumps({"layout": "planet", "world": {"type": "ice", "palette": ["#a0c0e0", "#ffffff"]}})
        shots = [Shot(id=f"s{i}", start=i * 5, end=i * 5 + 5, kind="image" if i % 2 == 0 else "plate", text="Silence settled over the pale shimmering distant landscape tonight.") for i in range(40)]
        n = vc.upgrade_scenes(shots, [], author=lambda s, u: (calls.append(1), spec)[1])
        self.assertEqual(n, len(calls))
        self.assertLessEqual(len(calls), vc.MAX_AI_CALLS)
        self.assertGreaterEqual(n, 1)


class CinemaAdapter(unittest.TestCase):
    def test_irrelevant_3d_layer_goes_and_a_graphic_is_composed(self):
        from types import SimpleNamespace as NS

        from visual_composer import cinema as vcc

        beats = [NS(text="Wheat prices rose 25 percent last winter and farmers worried.", start=0.0, end=9.0, mode="footage", place=None)]
        plan = NS(beats=beats, words=timed(beats[0].text), title="x")
        spec = {"duration": 12.0, "footage": [{"start": 0.0, "end": 9.0}], "layers": [
            {"type": "cinema_craft", "model": "wi:voyager.glb", "start": 1.0, "end": 8.0, "_cite": "NASA 3D MODEL OF VOYAGER 1", "over_footage": True},
            {"type": "tm_caption", "text": "VOYAGER 1", "start": 1.4, "end": 7.8, "over_footage": True}]}
        notes = []
        vcc.gate_layers(spec, plan, notes)
        self.assertEqual([L["type"] for L in spec["layers"]], [])
        self.assertTrue(notes)


class CinemaScenes(unittest.TestCase):
    def plan_spec(self):
        from types import SimpleNamespace as NS

        beats = [NS(text="A frozen world of cracked ice drifted in silence under a thin blue atmosphere.", start=0.0, end=8.0, mode="footage", place=None),
                 NS(text="Then prices rose 20 percent across the whole country last year.", start=8.0, end=16.0, mode="footage", place=None),
                 NS(text="Inside the planet the core is wrapped in thick layers of molten rock.", start=16.0, end=24.0, mode="footage", place=None)] + [
            NS(text="Wages rose slowly across the whole country that year.", start=24.0 + 8 * i, end=32.0 + 8 * i, mode="footage", place=None) for i in range(3)]
        plan = NS(beats=beats, words=timed(" ".join(b.text for b in beats)), title="x")
        spec = {"duration": 48.0, "footage": [{"start": b.start, "end": b.end} for b in beats], "layers": []}
        return plan, spec

    def test_footage_about_drawable_things_gets_a_scene_layer_once_the_engine_can_draw_it(self):
        from unittest import mock

        from visual_composer import cinema as vcc

        plan, spec = self.plan_spec()
        with mock.patch.object(vcc, "engine_supports_scene", return_value=False):
            self.assertEqual(vcc.scenes(spec, plan, []), 0)
            self.assertEqual(spec["layers"], [])
        with mock.patch.object(vcc, "engine_supports_scene", return_value=True):
            notes = []
            self.assertEqual(vcc.scenes(spec, plan, notes), 2)
        got = [L for L in spec["layers"] if L["type"] == "cinema_scene"]
        self.assertEqual([round(L["start"]) for L in got], [0, 16])
        self.assertTrue(all(L["over_footage"] and L["scene_spec"] for L in got))
        self.assertEqual(got[0]["scene_spec"]["world"]["type"], "ice")
        self.assertTrue(got[1]["scene_spec"]["world"].get("cutaway"))


if __name__ == "__main__":
    unittest.main()
