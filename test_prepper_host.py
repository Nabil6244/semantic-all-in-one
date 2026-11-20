"""Prepper Host: CSV, director, every shot drawn, the sound mix, the app page wiring and autorun. No network, no Flow."""
import json
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from prepper_host import csvplan, director, host as H, render as R

ROOT = Path(__file__).resolve().parent
PROMPT = (ROOT / "prepper_host" / "csv_prompt.txt").read_text()
EXAMPLE = PROMPT.split("EXAMPLE\n", 1)[1]
SAMPLE = ROOT / "prepper_host" / "samples" / "water_90_days.csv"


def fake_words(text, step=0.32):
    out, t = [], 0.1
    for w in text.split():
        out.append({"word": w, "start": round(t, 3), "end": round(t + step * 0.8, 3)})
        t += step
    return out, t + 0.5


def _plan(rows, size=(320, 180)):
    rows = [r for r in rows if r["shot"] != "thumbnail"]
    words, dur = fake_words(csvplan.script_of(rows))
    return director.direct(rows, words, dur, size=size, host_meta=H.DALE)


class CsvTests(unittest.TestCase):
    def test_prompt_example_reads_clean(self):
        rows, problems = csvplan.read(EXAMPLE)
        self.assertEqual(problems, [])
        self.assertEqual([r["shot"] for r in rows][:4], ["host", "broll", "split", "chapter"])
        self.assertEqual(rows[-1]["shot"], "thumbnail")

    def test_prompt_names_every_shot(self):
        for s in csvplan.SHOTS:
            self.assertIn(s, PROMPT)

    def test_rows_syntax(self):
        r = csvplan.parse_rows("4 PEOPLE x 90 DAYS = 1 GAL/DAY; WATER YOU NEED = 360 GAL !red; ~THE ATTIC; -BACKYARD")
        self.assertEqual(r[1], {"label": "WATER YOU NEED", "value": "360 GAL", "colour": "red", "strike": False, "tick": True})
        self.assertTrue(r[2]["strike"])
        self.assertFalse(r[3]["tick"])
        self.assertEqual(csvplan.number_of("~4,000 CAL"), 4000.0)
        self.assertEqual(csvplan.products_of("Rice | Beans |"), ["Rice", "Beans"])

    def test_needs_line_and_flags_bad_shots(self):
        with self.assertRaises(ValueError):
            csvplan.read("shot,visual\nhost,x\n")
        rows, problems = csvplan.read("line,shot\nHello there.,zoom\n")
        self.assertEqual(rows[0]["shot"], "")
        self.assertTrue(problems)


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.rows, _ = csvplan.read(str(SAMPLE))
        self.spec = _plan(self.rows)

    def test_shots_cover_the_voice_in_order(self):
        sh = self.spec["shots"]
        self.assertEqual(sh[0]["t0"], 0.0)
        for a, b in zip(sh, sh[1:]):
            self.assertLessEqual(a["t0"], b["t0"])
        self.assertAlmostEqual(sh[-1]["t1"], self.spec["duration"], places=2)

    def test_every_card_kind_and_host_rhythm(self):
        kinds = [s["kind"] for s in self.spec["shots"]]
        for k in ("host", "split", "pip", "broll", "product", "compare", "data", "checklist", "bars", "big"):
            self.assertIn(k, kinds)
        self.assertEqual(self.spec["chapters"][0]["text"], "ITEM 1 · WATER")

    def test_reveals_inside_their_shot_and_in_order(self):
        for s in self.spec["shots"]:
            items = s.get("card", {}).get("items", [])
            for a, b in zip(items, items[1:]):
                self.assertLess(a["at"], b["at"])
            for it in items:
                self.assertGreaterEqual(it["at"], s["t0"] - 0.2)

    def test_host_pictures_get_his_look(self):
        pics = self.spec["pictures"]
        hosty = [p for p in pics.values() if p["host"]]
        self.assertTrue(hosty)
        self.assertTrue(all("{host}" in p["prompt"] or H.shows_host(p["prompt"]) for p in hosty))
        self.assertIn("olive-green", H.expand("{host} carries water", H.DALE))
        self.assertTrue(any(p.get("product") for p in pics.values()))

    def test_script_only_rows_get_shots(self):
        rows = [{"line": s, "shot": "", "visual": "", "product": "", "title": "", "rows": "", "chapter": "", "n": i}
                for i, s in enumerate(director.sentences("I bought rice. It lasts years. Water first. Then beans. Then oats. Done."))]
        spec = _plan(rows)
        kinds = [s["kind"] for s in spec["shots"]]
        self.assertEqual(kinds[0], "host")
        self.assertTrue(set(kinds) <= {"host", "split", "pip", "broll"})

    def test_long_rows_are_cut(self):
        long = " ".join(["word"] * 60) + "."
        rows = [{"line": long, "shot": "broll", "visual": "a barn", "product": "", "title": "", "rows": "", "chapter": "", "n": 1}]
        spec = _plan(rows)
        self.assertGreaterEqual(len(spec["shots"]), 3)
        self.assertTrue(all(s["t1"] - s["t0"] <= 7.5 for s in spec["shots"]))

    def test_round_trip_csv(self):
        text = csvplan.from_plan(self.spec)
        rows, problems = csvplan.read(text)
        self.assertEqual(problems, [])
        self.assertEqual(csvplan.script_of(rows), csvplan.script_of([r for r in self.rows if r["shot"] != "thumbnail"]))


class DrawTests(unittest.TestCase):
    def test_every_shot_draws(self):
        rows, _ = csvplan.read(str(SAMPLE))
        spec = _plan(rows)
        spec["host"] = {"name": "Dale", "tagline": "30 years on a ranch", "set_image": str(ROOT / "prepper_host" / "hosts" / "dale" / "set.png")}
        spec["shots"][0]["namebar"] = True
        assets = {"pictures": {}, "fallback": spec["host"]["set_image"]}
        dr = R.Drawer(spec, assets)
        seen = set()
        for i, s in enumerate(spec["shots"]):
            for f in (0.1, 0.6, 0.95):
                im = dr.frame(dict(s, i=i), s["t0"] + (s["t1"] - s["t0"]) * f)
                self.assertEqual(im.size, (320, 180))
            seen.add(s["kind"])
        im = dr.frame(dict(spec["shots"][3], i=3), spec["chapters"][0]["t"] + 0.8)
        self.assertGreater(np.asarray(im).std(), 5)
        self.assertGreaterEqual(len(seen), 10)

    def test_count_up(self):
        self.assertEqual(R.fmt_count("360 GAL", 360, 1.0), "360 GAL")
        self.assertEqual(R.fmt_count("$1,600", 1600, 0.0), "$0")

    def test_mix_levels_and_length(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "v.wav"
            sr = 24000
            t = np.arange(int(sr * 3)) / sr
            y = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
            with wave.open(str(v), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(y.tobytes())
            spec = {"voice_path": str(v), "duration": 3.0, "sfx": [{"t": 0.5, "name": "whoosh"}, {"t": 1.0, "name": "tick"}]}
            rep = R.mix(spec, Path(d) / "m.wav", sound="fx")
            self.assertLessEqual(rep["peak_db"], -0.9)
            with wave.open(str(Path(d) / "m.wav")) as w:
                self.assertAlmostEqual(w.getnframes() / w.getframerate(), 3.0, places=2)


class AppWiringTests(unittest.TestCase):
    def test_app_hooks(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        for hook in ("from ui import prepper_host_section as _ph_section", "_ph_section.activate(self)", "_ph_section.cta(self, action)",
                     "_ph_section.sync_cta(self)", "_ph_section.resume_on_open(self)", "_ph_section.deactivate(self, remember=False)",
                     'return "Prepper Host"'):
            self.assertIn(hook, src)

    def test_style_card_and_labels(self):
        from ui import style_registry as RG
        import export_state
        self.assertIn("Prepper Host", RG.STANDALONE)
        self.assertEqual(RG.group_of("Prepper Host"), "Explainers")
        self.assertIn("Prepper Host", RG.EXTRA_CARDS)
        self.assertEqual(export_state.STYLE_LABELS["prepper_host"], "Prepper Host")

    def test_page_module_loads(self):
        from ui import prepper_host_section as S
        self.assertEqual(S.STYLE, "Prepper Host")
        self.assertIn("dale", S.HOSTS.values())

    def test_autorun_job(self):
        from autorun import job as J
        import make_video as MV
        self.assertEqual(J.STYLES["prepper-host"]["fields"]["csv"], "_ph_csv_var")
        self.assertEqual(MV.STYLES["prepper-host"][2], "prepper_host/csv_prompt.txt")
        j = J.make_job("prepper-host", csv=str(SAMPLE))
        self.assertEqual(j["voice"], "")
        with self.assertRaises(J.JobError):
            J.make_job("prepper-host")

    def test_shipped_host_pack(self):
        meta = H.load("dale")
        self.assertTrue(meta["portrait"] and Path(meta["portrait"]).is_file())
        self.assertTrue(meta["set_image"] and Path(meta["set_image"]).is_file())
        self.assertIn("dale", H.names())


class FlowVoiceTests(unittest.TestCase):
    def test_chunks_fit_a_clip(self):
        from prepper_host import flowvoice as fv
        line = "Here's the thing nobody tells you about the first week without power, and it's the reason most families run out early, every single time."
        parts = fv.chunks(line)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p.split()) <= fv.MAX_WORDS for p in parts))
        self.assertEqual(" ".join(parts).split(), line.split())

    def test_split_rows_keeps_shots_and_marks_host_lines(self):
        from prepper_host import flowvoice as fv
        rows, _ = csvplan.read(str(SAMPLE))
        rows = [r for r in rows if r["shot"] != "thumbnail"]
        spec = _plan(rows)
        rows2 = fv.split_rows(rows, spec)
        self.assertEqual(csvplan.script_of(rows2).split(), csvplan.script_of(rows).split())
        self.assertTrue(any(r.get("say") for r in rows2))
        self.assertTrue(all(r["shot"] in fv.SAY_KINDS for r in rows2 if r.get("say")))
        self.assertTrue(all(r["shot"] for r in rows2))

    def test_build_uses_clip_speech_and_attach_times_it(self):
        from prepper_host import flowvoice as fv
        with tempfile.TemporaryDirectory() as d:
            sr = fv.SR
            clip = Path(d) / "c.wav"   # 1 s quiet, 2 s speech-like tone, 1 s quiet
            t = np.arange(sr * 2) / sr
            y = np.concatenate([np.zeros(sr), 0.3 * np.sin(2 * np.pi * 180 * t), np.zeros(sr)])
            with wave.open(str(clip), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes((y * 32767).astype("<i2").tobytes())
            a, b = fv.speech_span(y.astype(np.float32))
            self.assertAlmostEqual(a, 0.94, delta=0.1)
            self.assertAlmostEqual(b, 3.12, delta=0.1)
            rows = [{"line": "Water first, then everything else.", "shot": "host", "say": True},
                    {"line": "Beans keep for years.", "shot": "host", "say": True}]
            old = fv.CACHE
            fv.CACHE = Path(d)
            try:
                vo = fv.build(rows, {0: str(clip), 1: str(clip)}, "en-US-AndrewNeural", log=lambda m: None)
            finally:
                fv.CACHE = old
            self.assertAlmostEqual(vo["duration"], 2 * (b - a + fv.pv.GAP), delta=0.1)
            self.assertEqual(len(vo["words"]), 9)
            spec = {"shots": [{"t0": 0.0, "t1": 2.0, "kind": "host", "row": 0}, {"t0": vo["said"][1][2], "t1": 4.0, "kind": "split", "row": 1},
                              {"t0": 4.0, "t1": 5.0, "kind": "broll", "row": 1}]}
            fv.attach(spec, rows, vo["said"])
            self.assertEqual(spec["shots"][0]["talk_at"], round(a, 3))
            self.assertAlmostEqual(spec["shots"][1]["talk_at"], a, places=2)
            self.assertFalse(spec["shots"][1]["talk_loop"])
            self.assertNotIn("talk", spec["shots"][2])

    def test_page_offers_flow_voice(self):
        from ui import prepper_host_section as S
        self.assertIn("flow", S.TALKING.values())


if __name__ == "__main__":
    unittest.main()
