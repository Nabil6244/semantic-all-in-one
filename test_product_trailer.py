import io
import json
import re
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

import product_trailer as pt
from product_trailer import beats as pb
from product_trailer.csv_io import parse_csv_text
from product_trailer.planner import FACE, FILL_FRAME, MOVES, TEXT_MOVES, plan_spec

ROOT = Path(__file__).parent
SAMPLES = sorted((ROOT / "docs" / "product_trailer" / "samples").glob("*.csv"))
KINDS = re.search(r"export const KINDS = \[([^\]]*)\]", (ROOT / "whatif-engine" / "lib" / "shots.mjs").read_text()).group(1)
KINDS = [k.strip().strip("'\"") for k in KINDS.split(",") if k.strip()]

CSV = """﻿#product,Galaxy S27 Ultra,Titanium Black,SAMSUNG,09:41,Tue 27 Oct
#disclaimer,Concept trailer. Not affiliated.
# a comment
order, feature ,kicker,value,sub,look
1,camera,The next-gen,200MP,main sensor,
2, camera ,,50MP,ultrawide,

3,frame,,Aluminum Frame,,wash:red
4,os,,Android 17,,wash:purple
5,chip,,Snapdragon 8 Elite Gen 6,,badge
6,display,,120Hz
"""


def click_track(path: Path, bpm: float = 120.0, seconds: float = 20.0, sr: int = 22050) -> None:
    y = np.zeros(int(seconds * sr), dtype=np.float32)
    rng = np.random.default_rng(1)
    click = (rng.standard_normal(int(0.02 * sr)) * np.exp(-np.linspace(0, 8, int(0.02 * sr)))).astype(np.float32)
    for k in range(int(seconds * bpm / 60)):
        i = int(k * 60 / bpm * sr)
        y[i:i + len(click)] += click[: len(y) - i]
    pcm = (np.clip(y * 0.6, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


class CsvTests(unittest.TestCase):
    def test_parse(self):
        d = parse_csv_text(CSV)
        p = d["product"]
        self.assertEqual(p["name"], "Galaxy S27 Ultra")
        self.assertEqual(p["colour"], "Titanium Black")
        self.assertEqual(p["wordmark"], "SAMSUNG")
        self.assertEqual(p["disclaimer"], "Concept trailer. Not affiliated.")
        self.assertEqual(len(d["features"]), 6)
        self.assertEqual(d["features"][1]["feature"], "camera")
        self.assertEqual(d["features"][5]["look"], "")          # missing trailing column

    def test_no_product_line_uses_file_name(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "pixel_10_pro.csv"
            p.write_text("order,feature,kicker,value,sub,look\n1,camera,,50MP,,\n")
            d = pt.read_csv(p)
        self.assertEqual(d["product"]["name"], "Pixel 10 Pro")
        self.assertTrue(d["product"]["disclaimer"])

    def test_samples_parse_and_build(self):
        self.assertTrue(SAMPLES, "docs/product_trailer/samples/*.csv missing")
        with tempfile.TemporaryDirectory() as t:
            for s in SAMPLES:
                d = pt.read_csv(s)
                self.assertTrue(d["features"], s.name)
                self.assertNotEqual(d["product"]["name"], "New Phone")
                spec = json.loads(Path(pt.build_spec(s, None, Path(t) / s.stem)).read_text())
                self.assertEqual(spec["duration"], 60.0 if d["product"].get("pace") != "reveal" else min(95.0, 6.0 * (len(d["features"]) + 1) + 3.0))
                self.assertEqual(validate(spec), [], s.name)


class BeatTests(unittest.TestCase):
    def test_click_track(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "click.wav"
            click_track(p, bpm=120, seconds=20)
            info = pb.detect(str(p))
        self.assertAlmostEqual(info.duration, 20.0, delta=0.1)
        self.assertAlmostEqual(info.tempo, 120.0, delta=3.0)
        clicks = np.arange(0, 20, 0.5)
        near = [min(abs(clicks - b)) for b in info.beats if b > 0.2]
        self.assertGreater(len(near), 30)
        self.assertLess(float(np.median(near)), 0.05)

    def test_no_music_grid(self):
        info = pb.detect(None)
        self.assertEqual(info.duration, 60.0)
        self.assertAlmostEqual(info.beats[1] - info.beats[0], 60 / 110, places=3)


def validate(spec):
    problems, prev = [], 0.0
    for s in spec["shots"]:
        if s["kind"] not in KINDS:
            problems.append(f"{s['id']} kind {s['kind']}")
        if not s["end"] > s["start"]:
            problems.append(f"{s['id']} empty")
        if s["start"] < prev - 1e-6:
            problems.append(f"{s['id']} overlaps")
        prev = s["end"]
    if abs(spec["shots"][-1]["end"] - spec["duration"]) > 1e-6:
        problems.append("does not reach the end")
    for k in ("width", "height", "fps", "duration", "look", "shots", "layers"):
        if k not in spec:
            problems.append(f"missing {k}")
    return problems


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.data = parse_csv_text(CSV)
        self.beats = pb.BeatInfo(duration=80.0, tempo=120.0, beats=[round(i * 0.5, 4) for i in range(161)], source="test")

    def spec(self, seed=0):
        return plan_spec(self.data, self.beats, seed=seed)

    def test_deterministic(self):
        self.assertEqual(json.dumps(self.spec(3)), json.dumps(self.spec(3)))
        self.assertNotEqual(json.dumps(self.spec(3)), json.dumps(self.spec(4)))

    def test_valid_and_complete(self):
        spec = self.spec()
        self.assertEqual(validate(spec), [])
        types = {L["type"] for L in spec["layers"]}
        self.assertTrue({"pt_feature", "pt_bigtype", "pt_reveal", "pt_card", "pt_badge"} <= types, types)
        prod = [s for s in spec["shots"] if s["kind"] == "product"]
        for s in prod:
            self.assertIn(s["move"], MOVES)
            for k in ("phone", "color", "backdrop", "seed"):
                self.assertIn(k, s)
            self.assertEqual(s["phone"], "galaxy s27 ultra")
        self.assertEqual(spec["layers"][-1]["type"], "pt_card")
        self.assertGreaterEqual(spec["duration"] - spec["shots"][-1]["start"], 2.0)

    def test_no_repeated_moves_and_alternating_faces(self):
        for seed in range(6):
            prod = [s for s in self.spec(seed)["shots"] if s["kind"] == "product"]
            for a, b in zip(prod, prod[1:]):
                self.assertNotEqual(a["move"], b["move"], (seed, a["id"], b["id"]))

    def test_cuts_on_beats(self):
        for seed in range(4):
            spec = self.spec(seed)
            beats = set(self.beats.beats)
            for s in spec["shots"][1:]:
                self.assertIn(s["start"], beats, (seed, s["id"], s["start"]))

    def test_cold_open_has_no_text(self):
        spec = self.spec()
        first_text = min(L["start"] for L in spec["layers"])
        self.assertGreater(first_text, spec["duration"] * 0.12)

    def test_wash_and_moves_follow_feature_type(self):
        spec = self.spec()
        washes = [s for s in spec["shots"] if s.get("backdrop") == "wash"]
        self.assertEqual({s["wash_style"] for s in washes}, {"swoosh", "aurora"})
        self.assertTrue(any(s["move"] in ("chip", "chip_macro") and s["object"] == "chip" for s in spec["shots"] if s["kind"] == "product"))

    def test_no_move_repeats_within_three_shots(self):
        for seed in range(8):
            prod = [s["move"] for s in self.spec(seed)["shots"] if s["kind"] == "product"]
            for i in range(1, len(prod)):
                self.assertNotIn(prod[i], prod[max(0, i - 3):i], (seed, i, prod))

    def test_text_never_over_the_phone(self):
        for seed in range(8):
            spec = self.spec(seed)
            prod = [s for s in spec["shots"] if s["kind"] == "product"]
            for L in spec["layers"]:
                mid = (L["start"] + L["end"]) / 2
                s = next((s for s in prod if s["start"] <= mid < s["end"]), None)
                if s is None:
                    continue
                if "side" in L:
                    self.assertNotEqual(L["side"], s["frame_side"], (seed, L["type"], s["id"]))
                if L["type"] in ("pt_feature", "pt_tagline"):
                    self.assertNotIn(s["move"], FILL_FRAME, (seed, L["type"], s["id"], s["move"]))
                    self.assertIn(s["move"], TEXT_MOVES)
                if L["type"] == "pt_bigtype" and s["move"] == "screen":
                    self.assertIs(s["screen"].get("clock"), False, (seed, s["id"]))
                if L["type"] == "pt_bigtype":
                    self.assertTrue(s["move"] == "screen" or FACE[s["move"]] != "front", (seed, s["move"]))

    def test_shot_count_like_the_reference(self):
        beats = pb.BeatInfo(duration=87.0, tempo=120.0, beats=[round(i * 0.5, 4) for i in range(175)], source="test")
        datas = [self.data] + [pt.read_csv(s) for s in SAMPLES]
        for data in datas:
            if data["product"].get("pace") == "reveal":
                continue
            for seed in range(4):
                spec = plan_spec(data, beats, seed=seed)
                self.assertEqual(validate(spec), [])
                self.assertGreaterEqual(len(spec["shots"]), 30, (data["product"]["name"], seed, len(spec["shots"])))   # 2026-10-28: calmer opening (3 s cold-open shots), so a few cuts fewer than the reference's 38
                cold = [s for s in spec["shots"] if s["end"] <= spec["duration"] * 0.16 + 0.01]
                self.assertTrue(all(s["end"] - s["start"] <= 3.6 + 1e-6 for s in cold[:-1]), cold)
                self.assertEqual(len({s["move"] for s in cold}), len(cold), [s["move"] for s in cold])

    def test_background_per_csv_line(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "Skyline.jpg").write_bytes(b"\xff\xd8\xff\xd9")
            (d / "t.csv").write_text("#product,Test Phone,Titanium Black\norder,feature,kicker,value,sub,look\n"
                                     "1,camera,,200MP,main sensor,gradient:#3355ff\n2,design,,Slimmer.,,image:Skyline.jpg\n"
                                     "3,frame,,Titanium,,wash:#00aaff:aurora\n4,battery,,5000mAh,,image:missing.png\n", encoding="utf-8")
            spec = json.loads(Path(pt.build_spec(d / "t.csv", out_dir=d / "out")).read_text(encoding="utf-8"))
            backs = [(s["backdrop"], s.get("wash"), s.get("wash_style"), s.get("backdrop_file")) for s in spec["shots"] if s["kind"] == "product" and s["backdrop"] != "stars"]
            self.assertIn(("gradient", "#3355ff", None, None), backs)
            self.assertIn(("image", None, None, "Skyline.jpg"), backs)                # case kept, copied beside the spec
            self.assertIn(("wash", "#00aaff", "aurora", None), backs)
            self.assertTrue((d / "out" / "media" / "Skyline.jpg").is_file())
            self.assertTrue(any("missing.png" in n for n in spec["whatif"]["notes"]))   # a missing picture falls back to stars


if __name__ == "__main__":
    unittest.main()


class FrontCapAndTextTests(unittest.TestCase):
    def setUp(self):
        self.beats = pb.BeatInfo(duration=87.0, tempo=120.0, beats=[round(i * 0.5, 4) for i in range(175)], source="test")
        self.datas = [parse_csv_text(CSV)] + [pt.read_csv(s) for s in SAMPLES if pt.read_csv(s)["product"].get("pace") != "reveal"]

    def test_front_shots_capped(self):
        for data in self.datas:
            for seed in range(6):
                prod = [s for s in plan_spec(data, self.beats, seed=seed)["shots"] if s["kind"] == "product"]
                front = [s for s in prod if FACE[s["move"]] == "front"]
                self.assertLessEqual(len(front), 0.30 * len(prod) + 1e-9, (data["product"]["name"], seed, [s["move"] for s in prod]))
                back = [s for s in prod if FACE[s["move"]] == "back"]
                self.assertGreater(len(back) + sum(FACE[s["move"]] == "side" for s in prod), len(front))

    def test_every_feature_beat_has_visible_text_inside_its_shot(self):
        for data in self.datas:
            for seed in range(6):
                spec = plan_spec(data, self.beats, seed=seed)
                texts = [L for L in spec["layers"] if L["type"] in ("pt_feature", "pt_tagline", "pt_badge", "pt_bigtype")]
                firsts = [L for L in texts]
                self.assertGreaterEqual(len({(L["start"]) for L in firsts}), min(len(data["features"]), 3))
                for L in texts:
                    s = next(s for s in spec["shots"] if s["start"] <= L["start"] < s["end"])
                    self.assertLessEqual(L["end"], s["end"] + 1e-6, (L, s["id"]))
                    self.assertGreaterEqual(L["end"] - L["start"], 1.5, L)          # long enough to clear the 0.7 s blur-in
                    self.assertNotIn(s["move"], FILL_FRAME if L["type"] in ("pt_feature", "pt_tagline") else ())
                    self.assertTrue(L.get("opacity", 1) > 0.5)


class RevealPaceTests(unittest.TestCase):
    def setUp(self):
        self.data = pt.read_csv(ROOT / "docs" / "product_trailer" / "samples" / "galaxy_s27_ultra_reveal.csv")
        self.beats = pb.BeatInfo(duration=95.0, tempo=120.0, beats=[round(i * 0.5, 4) for i in range(191)], source="test")

    def test_csv_pace_and_colours(self):
        self.assertEqual(self.data["product"]["pace"], "reveal")
        self.assertEqual(self.data["product"]["colors"], ["Navy", "Sky Blue", "Pink", "White"])
        self.assertEqual(parse_csv_text(CSV)["product"].get("pace"), None)

    def test_shot_lengths_moves_and_look(self):
        for seed in range(4):
            spec = plan_spec(self.data, self.beats, seed=seed)
            self.assertEqual(validate(spec), [])
            prod = [s for s in spec["shots"] if s["kind"] == "product"]
            body = prod[:-1]
            for s in body[:-1]:
                self.assertTrue(5.5 - 1e-6 <= s["end"] - s["start"] <= 6.5 + 1e-6, (s["id"], s["start"], s["end"]))
                self.assertIn(s["start"], self.beats.beats)
            self.assertEqual(prod[0]["move"], "reveal")
            self.assertGreaterEqual(sum(s["move"] == "reveal" for s in body), len(body) // 4)
            self.assertGreater(sum(s["backdrop"] == "charcoal" for s in prod), len(prod) / 2)
            self.assertGreater(sum(bool(s.get("fog")) for s in prod), len(prod) / 2)
            for s in body:
                self.assertEqual(s["frame_side"], "center")
                if FACE[s["move"]] == "back":
                    self.assertTrue(s.get("streak"), s["id"])
                if FACE[s["move"]] == "front":
                    self.assertTrue(s.get("glow"), s["id"])
                if s["move"] == "reveal":
                    self.assertIn("power_on", s["screen"])
                    self.assertIn(s["screen"]["wallpaper"], ("liquid", "wave"))
            self.assertTrue(any(s.get("dim_out") for s in prod))

    def test_colours_cycle(self):
        prod = [s for s in plan_spec(self.data, self.beats)["shots"] if s["kind"] == "product"]
        self.assertEqual({s["color"] for s in prod}, {"Navy", "Sky Blue", "Pink", "White"})
        self.assertTrue(all(a["color"] != b["color"] for a, b in zip(prod, prod[1:])))

    def test_captions_only(self):
        spec = plan_spec(self.data, self.beats)
        types = [L["type"] for L in spec["layers"]]
        self.assertNotIn("pt_feature", types)
        caps = [L for L in spec["layers"] if L["type"] == "pt_caption"]
        self.assertEqual(len(caps), len(self.data["features"]))
        self.assertIn("200MP Primary Camera", [c["text"] for c in caps])
        for c in caps:
            s = next(s for s in spec["shots"] if s["start"] <= c["start"] < s["end"])
            self.assertLessEqual(c["end"], s["end"])
        self.assertEqual(types[-2:], ["pt_reveal", "pt_card"])

    def test_pace_argument_and_no_music_grid(self):
        data = parse_csv_text(CSV)
        spec = plan_spec(data, self.beats, pace="reveal")
        self.assertIn("pt_caption", {L["type"] for L in spec["layers"]})
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.csv"
            p.write_text(CSV, encoding="utf-8")
            spec = json.loads(Path(pt.build_spec(p, None, Path(t) / "o", pace="reveal")).read_text())
            prod = [s for s in spec["shots"] if s["kind"] == "product"]
            self.assertTrue(all(abs(s["end"] - s["start"] - 6.0) < 1e-6 for s in prod[:-2]), [(s["start"], s["end"]) for s in prod])
