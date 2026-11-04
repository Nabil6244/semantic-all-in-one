import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sfx_plan as SP  # noqa: E402
from sfx_plan import SR  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "out"


def beat(i, rung, site, t0, t1):
    return {"id": f"b{i}", "rung": rung, "site": site, "travelT0": t0, "travelT1": t1, "speakT0": t1 + 0.4, "speakT1": t1 + 5}


TL = {"duration": 100.0, "beats": [
    beat(0, "globe", None, 3.0, 3.0), beat(1, "ground", "battle", 6.0, 12.0), beat(2, "oblique", None, 25.0, 30.0),
    beat(3, "ground", "city", 40.0, 46.0), beat(4, "ground", "village", 58.0, 63.0), beat(5, "ground", "beach_landing", 70.0, 75.0),
    beat(6, "ground", "airfield", 80.0, 85.0), beat(7, "ground", "jungle", 88.0, 92.0), beat(8, "map", None, 95.0, 97.0)]}


def noise_voice(n_s=30, seed=1):
    rng = np.random.default_rng(seed)
    v = np.zeros(n_s * SR, np.float32)
    for a in range(2, n_s - 3, 6):                 # 3 s of "speech" every 6 s
        v[a * SR:(a + 3) * SR] = (rng.standard_normal(3 * SR) * 0.1).astype(np.float32)
    return v


class Tests(unittest.TestCase):
    def test_deterministic(self):
        a = json.dumps(SP.build_plan(TL), sort_keys=True); b = json.dumps(SP.build_plan(json.loads(json.dumps(TL))), sort_keys=True)
        self.assertEqual(a, b)
        tl2 = json.loads(json.dumps(TL)); tl2["beats"][1]["id"] = "zz"
        self.assertNotEqual(SP.build_plan(tl2)["beats"][1]["events"], SP.build_plan(TL)["beats"][1]["events"])

    def test_bed_choice(self):
        by = {b["site"] or b["rung"]: b for b in SP.build_plan(TL)["beats"]}
        ids = lambda k: [l["id"] for l in by[k]["layers"]]  # noqa: E731
        self.assertTrue(by["battle"]["events"]); self.assertIn("amb_fire_01", ids("battle"))
        self.assertTrue(all(i.startswith("amb_nature") for i in ids("jungle")[:1])); self.assertEqual(by["jungle"]["events"], [])
        self.assertTrue(ids("city")[0].startswith("amb_city")); self.assertIn("amb_water_02", ids("beach_landing"))
        self.assertTrue(ids("airfield")[0].startswith("amb_technology"))
        self.assertEqual(by["globe"]["kind"], "pad"); self.assertEqual(by["oblique"]["layers"][0]["id"].split("_")[1], "atmospheric")
        self.assertLess(by["map"]["level_db"], by["globe"]["level_db"])

    def test_crossfade_timing(self):
        p = SP.build_plan(TL)
        for i, b in enumerate(p["beats"]):
            self.assertEqual(b["fade_in"], [b["start"], round(b["start"] + 1.5, 3)])
            self.assertEqual(b["start"], TL["beats"][i]["travelT1"])
            if i + 1 < len(p["beats"]):
                n = p["beats"][i + 1]
                self.assertEqual(b["fade_out"], [n["start"], round(n["start"] + 1.5, 3)])      # outgoing fades exactly while incoming fades in
                self.assertEqual(b["end"], TL["beats"][i + 1]["travelT0"])
                self.assertTrue(all(b["start"] <= e["t"] < b["end"] for e in b["events"]))     # gunfire stops with the beat
        e = SP.bed_envelope(p["beats"][1], 100 * SR); n = SP.bed_envelope(p["beats"][2], 100 * SR)
        k = int(30.75 * SR)
        self.assertAlmostEqual(float(e[k] ** 2 + n[k] ** 2), 1.0, places=2)                    # equal power mid-fade
        self.assertEqual(float(e[int(5 * SR)]), 0.0); self.assertEqual(float(e[int(20 * SR)]), 1.0)

    def test_only_catalog_files(self):
        p = SP.build_plan(TL, [{"t": 10, "kind": "blast"}, {"t": 50, "kind": "plane"}, {"t": 60, "kind": "crowd"}, {"t": 70, "kind": "nope"}, {"t": 999, "kind": "blast"}])
        self.assertEqual(len(p["spots"]), 3)
        cat = SP.catalog()
        for cid in SP.plan_files(p):
            self.assertIn(cid, cat); self.assertTrue(SP.catalog_file(cid).exists())
        files = [l["file"] for b in p["beats"] for l in b["layers"]] + [s["file"] for s in p["spots"]]
        self.assertTrue(all(f in {x["file"] for x in cat.values()} for f in files))
        self.assertFalse(any("whoosh" in f for f in files))
        for k in (list(SP.FIRE_FILES) + SP.RUMBLE_FILES + [i for v in SP.SPOTS.values() for i in v[0]]):
            self.assertIn(k, cat)

    def test_levels_on_synthetic(self):
        v = noise_voice(60)
        plan = SP.build_plan({"duration": 60.0, "beats": [beat(0, "ground", "village", 0.5, 1.0)]}, [{"t": 3.0, "kind": "blast"}, {"t": 27.0, "kind": "blast"}])
        s = SP.render(plan, v)
        self.assertEqual(s.shape, (len(v), 2))
        vpeak = float(np.max(np.abs(v)))
        self.assertLessEqual(float(np.max(np.abs(s))), vpeak + 1e-6)                          # never above the voice's peak
        db = lambda x: 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)  # noqa: E731
        sp = np.zeros(len(v), bool); si = np.zeros(len(v), bool)
        for a in range(2, 57, 6):                       # speech 3 s, silence 3 s; trim the duck attack / release edges
            sp[int((a + 0.4) * SR):int((a + 2.7) * SR)] = True
            si[int((a + 4.2) * SR):int((a + 4.9) * SR)] = True
        for t in (3.0, 27.0):                           # keep the spot events out of the bed measurement
            sp[int(t * SR):int((t + 3.6) * SR)] = False; si[int(t * SR):int((t + 3.6) * SR)] = False
        mono = s.mean(axis=1)
        under = db(v[sp]) - db(mono[sp])
        up = db(mono[si]) - db(mono[sp])
        self.assertTrue(18 < under < 27, under)                # ~22 dB under the voice during speech (stereo->mono is ~ -1.5 dB)
        self.assertTrue(3.5 < up < 9.5, up)                    # ~6 dB up in the silences
        self.assertGreater(float(np.abs(s[int(3.0 * SR):int(6.5 * SR)]).max()), float(np.abs(mono[sp]).max()))  # the blast spot is in the stem

    def test_loop_and_determinism_render(self):
        v = noise_voice(10)
        p = SP.build_plan({"duration": 10.0, "beats": [beat(0, "ground", "village", 0.5, 1.0)]})
        a = SP.render(p, v); b = SP.render(p, v)
        self.assertTrue(np.array_equal(a, b))
        x = np.ones((SR, 2), np.float32); y = SP.loop_to(x, 3 * SR, 0.3)
        self.assertEqual(len(y), 3 * SR); self.assertTrue(np.allclose(y[:, 0], 1.0, atol=1e-5) or float(y.min()) > 0.9)


if __name__ == "__main__":
    unittest.main()
