"""Life in Health Cinema 3D scenes: a heartbeat, breathing and a blood-flow wave, all a function of the scene time (renders stay deterministic and cached)."""
import json
import unittest
from pathlib import Path

from health_cinema import clips, journey

ROOT = Path(__file__).resolve().parent / "health_cinema"
PAGE = (ROOT / "threejs" / "page.js").read_text(encoding="utf-8")


class Pulse(unittest.TestCase):
    SPEC = {"pulse": [{"layers": ["Layer_Heart"], "anchor": "heart", "rate": 60, "amount": 0.05, "shape": "beat"},
                      {"layers": ["Layer_Lungs"], "anchor": "lungs", "rate": 15, "amount": 0.03, "shape": "breath"}]}

    def test_a_beat_contracts_briefly_then_rests(self):
        s = [journey.pulse_scales(self.SPEC, i / 100)["Layer_Heart"] for i in range(100)]      # one beat at 60 per minute
        self.assertAlmostEqual(min(s), 0.95, delta=0.003); self.assertLessEqual(max(s), 1.0)
        self.assertGreater(sum(v > 0.995 for v in s), 50)      # most of the beat is rest (filling)

    def test_rate_is_per_minute_and_repeats(self):
        for t in (0.03, 0.31, 0.7):
            self.assertAlmostEqual(journey.pulse_scales(self.SPEC, t)["Layer_Heart"], journey.pulse_scales(self.SPEC, t + 1.0)["Layer_Heart"], places=9)
            self.assertAlmostEqual(journey.pulse_scales(self.SPEC, t)["Layer_Lungs"], journey.pulse_scales(self.SPEC, t + 4.0)["Layer_Lungs"], places=9)

    def test_breathing_expands(self):
        s = [journey.pulse_scales(self.SPEC, i / 10)["Layer_Lungs"] for i in range(40)]
        self.assertAlmostEqual(min(s), 1.0, places=3); self.assertAlmostEqual(max(s), 1.03, places=3)

    def test_no_pulse_no_change(self):
        self.assertEqual(journey.pulse_scales({}, 3.0), {})


class Templates(unittest.TestCase):
    def test_heart_beats_breathes_and_its_vessels_carry_a_wave(self):
        spec = json.loads((ROOT / "templates" / "heart_journey.json").read_text(encoding="utf-8"))
        beats = [p for p in spec["pulse"] if p["shape"] == "beat"]; flow = spec["flow"][0]
        self.assertIn("Layer_Heart", beats[0]["layers"]); self.assertTrue(any(p["shape"] == "breath" and "Layer_Lungs" in p["layers"] for p in spec["pulse"]))
        self.assertEqual(flow["layer"], "Layer_Vessels"); self.assertEqual(flow["rate"], beats[0]["rate"])      # one wave per beat
        self.assertGreater(flow.get("inner", 0), 0)      # the wave starts outside the heart, so it never lights the whole organ at once

    def test_brain_arteries_carry_a_wave_from_the_neck(self):
        flow = json.loads((ROOT / "templates" / "brain_journey.json").read_text(encoding="utf-8"))["flow"][0]
        self.assertEqual(flow["layer"], "Layer_Arteries"); self.assertEqual(sorted(flow["origin"]), ["carotid_l", "carotid_r"])

    def test_stretching_a_scene_stretches_the_envelope_not_the_heart_rate(self):
        spec = clips.template_spec("heart_journey"); s = clips.scale_spec(spec, spec["duration"] * 2)
        self.assertEqual(s["pulse"], spec["pulse"]); self.assertEqual(s["flow"][0]["rate"], spec["flow"][0]["rate"])
        self.assertEqual([k[0] for k in s["flow"][0]["strength"]], [k[0] * 2 for k in spec["flow"][0]["strength"]])

    def test_chest_journey_keeps_breathing_without_the_heart_layers(self):
        spec = clips.template_spec("chest_journey")
        self.assertNotIn("Layer_Vessels", spec["layers"]); self.assertTrue(any("Layer_Lungs" in p["layers"] for p in spec["pulse"]))


class Page(unittest.TestCase):
    def test_page_applies_pulse_and_flow_every_frame(self):
        self.assertIn("f.pulse?.[ln]", PAGE); self.assertIn("flowU[fl.layer].strength.value = (f.flow?.[fl.id] ?? 0)", PAGE)
        self.assertIn("hcTime.value = f.t;", PAGE); self.assertIn("smoothstep(flowInner", PAGE); self.assertIn("if (c.pre)", PAGE)      # per-object pulses move the depth pre-pass twin too


class EveryScene(unittest.TestCase):
    """Whatever the next video is about, its 3D scenes are alive: every generated organ that has a rhythm gets it, the body map breathes and beats, and
    Rep Theory's muscles flex. Built from synthetic anchors, so no model is needed."""

    def _anchors(self, names, layers):
        import tempfile
        bx = lambda: {"center": [0, 0, 1.0], "min": [-0.05, -0.05, 0.95], "max": [0.05, 0.05, 1.05]}
        d = tempfile.mkdtemp(); p = Path(d) / "a.json"; p.write_text(json.dumps({"anchors": {n: bx() for n in names}, "layers": {l: [] for l in layers}})); return str(p)

    def test_every_organ_with_a_rhythm_moves(self):
        from health_cinema import library as L
        for organ, kinds in L.LIFE.items():
            o = L.ORGANS[organ]; ap = self._anchors([o.anchor] + [x[1] for x in o.labels], list(o.hero) + list(o.context))
            spec = L.build_spec(f"auto:{organ}:orbit", ap)
            self.assertTrue(spec["pulse"] or spec["flow"], organ)
            for p in spec["pulse"]: self.assertTrue(set(p["layers"]) <= set(o.hero), organ)      # only the organ itself moves, never its context
            if any(k == "load" for k, _ in kinds): self.assertTrue(all(p.get("per_object") for p in spec["pulse"] if p["rate"] == L.STEPS), organ)      # a joint layer holds both sides
        self.assertEqual(L.life_for("skeleton", "skeleton", ["Layer_Skeleton"], 12.0), {"pulse": [], "flow": []})

    def test_perfusion_is_a_ripple_not_a_flush(self):
        from health_cinema import library as L
        fl = L.life_for("liver", "liver_only", ["Layer_Liver"], 12.0)["flow"][0]
        self.assertLess(fl["speed"] * 60 / fl["rate"], 0.08)      # the distance between two waves is a few cm, far smaller than the organ

    def test_body_map_heart_beats_lungs_breathe_blood_flows(self):
        from health_cinema import bodymap as B
        life = B.body_life({n: {} for n in ("heart", "lungs", "abdomen", "neck", "body")}, 8.0)
        layers = {l for p in life["pulse"] for l in p["layers"]}
        self.assertTrue({"Layer_Heart", "Layer_Lungs", "Layer_Discs"} <= layers)
        self.assertEqual({f["layer"] for f in life["flow"]}, {"Layer_Vessels", "Layer_AbdVessels", "Layer_HeadArteries", "Layer_Intestines"})
        self.assertEqual(B.body_life({}, 8.0), {"pulse": [], "flow": []})      # a model without those anchors simply does not move them

    def test_rep_theory_muscles_flex_once_named_with_the_new_look(self):
        try:
            from reptheory import clip3d as RT
        except Exception as exc:
            self.skipTest(f"reptheory not importable: {exc}")
        names = ["body", "heart", "lungs", "abdomen", "neck", "m_quads_l", "m_quads_r", "m_glutes_r"]
        A = {n: {"center": [0, 0, 1.0], "min": [-0.05, -0.05, 0.95], "max": [0.05, 0.05, 1.05]} for n in names}
        got = RT.spec_for("Squats work your quads and glutes", 8.0, A, "push")
        if not got: self.skipTest("Rep Theory found no muscles in the synthetic anchors")
        spec, _ = got
        self.assertEqual(spec["lighting"], "tissue")
        flex = {p["layers"][0]: p for p in spec["pulse"] if p.get("per_object")}
        self.assertIn("Layer_M_quads", flex); self.assertEqual(flex["Layer_M_quads"]["rate"], RT.REP_RATE)
        self.assertEqual(flex["Layer_M_quads"]["strength"][0][1], 0.0)      # still until it is named
        self.assertEqual(sorted(next(f for f in spec["flow"] if f["id"] == "pump_quads")["origin"]), ["m_quads_l", "m_quads_r"])

    def test_a_pulse_envelope_scales_the_movement(self):
        spec = {"pulse": [{"layers": ["L"], "anchor": "a", "rate": 60, "amount": 0.05, "shape": "breath", "strength": [[0, 0.0], [1, 0.0], [2, 1.0], [9, 1.0]]}]}
        self.assertEqual(journey.pulse_scales(spec, 0.5)["L"], 1.0); self.assertAlmostEqual(journey.pulse_scales(spec, 5.5)["L"], 1.05, places=6)


if __name__ == "__main__":
    unittest.main()
