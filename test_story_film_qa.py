"""story_fast/film_qa.py on a synthetic film with KNOWN defects: it must find them, write sheets, and never call the film good. Needs ffmpeg."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from story_fast import film_qa, sound   # noqa: E402

HAVE_FF = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def build_film(path):
    """14 s, 30 fps, 320x180. 0-3 s moving test pattern | 3-8 s FROZEN grey card | 8-8.4 s BLACK dip then pattern | 9-9.1 s WHITE flash | 10-14 s pattern with a colour cast."""
    seg = [
        "testsrc2=s=320x180:r=30:d=3",
        "color=c=0x808080:s=320x180:r=30:d=5",
        "color=c=black:s=320x180:r=30:d=0.4",
        "testsrc2=s=320x180:r=30:d=0.6,hue=h=40",
        "color=c=white:s=320x180:r=30:d=0.1",
        "testsrc2=s=320x180:r=30:d=0.9,hue=h=80",
        "testsrc2=s=320x180:r=30:d=4,colorchannelmixer=rr=0.6:gg=0.9:bb=1.0",
    ]
    ins, chain = [], ""
    for i, s in enumerate(seg):
        ins += ["-f", "lavfi", "-i", s]
        chain += f"[{i}:v]format=yuv420p,setsar=1[v{i}];"
    chain += "".join(f"[v{i}]" for i in range(len(seg))) + f"concat=n={len(seg)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + ins + ["-f", "lavfi", "-i", "aevalsrc='sin(2*PI*180*t)*0.25*lt(mod(t\\,1.2)\\,0.8)':s=44100:d=14", "-filter_complex", chain,
                    "-map", "[v]", "-map", f"{len(seg)}:a", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-g", "15", "-c:a", "aac", "-shortest", path], check=True)


SHOTS = [
    {"shot_id": "a", "start": 0.0, "end": 3.0, "treatment": "push_in", "transition_in": "cut"},
    {"shot_id": "b", "start": 3.0, "end": 8.0, "treatment": "hold_alive", "transition_in": "cut"},
    {"shot_id": "c", "start": 8.0, "end": 9.0, "treatment": "push_in", "transition_in": "cut"},     # black dip at its start, NOT planned
    {"shot_id": "d", "start": 9.0, "end": 10.0, "treatment": "pan_left", "transition_in": "cut"},    # white flash at its start, NOT planned
    {"shot_id": "e", "start": 10.0, "end": 14.0, "treatment": "arc", "transition_in": "cut"},
]


@unittest.skipUnless(HAVE_FF, "ffmpeg missing")
class FilmQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.mp4 = os.path.join(cls.d, "film.mp4")
        build_film(cls.mp4)
        cls.rep = film_qa.analyze(cls.mp4, SHOTS, os.path.join(cls.d, "qa"), voice=None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def test_never_claims_success(self):
        r = self.rep
        self.assertTrue(r["verdict"].startswith("NOT ASSESSED"))
        md = Path(self.d, "qa", "report.md").read_text()
        self.assertIn("not a verdict", md.lower())
        for bad in ("passed", "all good", "success"):
            self.assertNotIn(bad, md.lower().replace("never reports success", ""))

    def test_finds_the_planted_defects(self):
        v = self.rep["video"]
        fl = v["joins"]["luma_flashes_or_dips"]
        ids = {(f["shot_id"], f["kind"]) for f in fl}
        self.assertIn(("d", "flash"), ids)                                  # white flash at 9.0 s
        self.assertTrue(all(f["shot_id"] != "x" for f in fl))
        self.assertTrue(all(not f["planned"] for f in fl))
        static = v["shots"]["visually_static_>=4s"] if "visually_static_>=4s" in v["shots"] else v["shots"]["visually_static_>=%gs" % film_qa.TH["hold_static_s"]]
        self.assertTrue(any(s["shot_id"] == "b" for s in static), v["shots"])   # frozen card held 5 s
        self.assertTrue(any(d["at_join"] == "c" and d["min_luma"] < 0.05 for d in v["dark_dips"]), v["dark_dips"])   # black dip at 8.0 s, found and tied to the join
        self.assertTrue(any("dark dips" in f for f in self.rep["flags"]))
        self.assertEqual(self.rep["audio"]["voice_vs_mix"]["bed_present"] if "voice_vs_mix" in self.rep["audio"] else False, False)

    def test_sheets_and_numbers_exist(self):
        files = self.rep["sheets"]["files"]
        self.assertTrue(files["mid"] and files["joins"])
        for p in files["mid"] + files["joins"]:
            self.assertTrue(os.path.getsize(p) > 2000)
        self.assertIsNotNone(self.rep["audio"]["loudness"]["integrated_lufs"])
        self.assertTrue(json.loads(Path(self.d, "qa", "report.json").read_text())["flags"])

    def test_clean_film_raises_no_flash_flags(self):
        mp4 = os.path.join(self.d, "clean.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=6", "-c:v", "libx264", "-preset", "ultrafast", mp4], check=True)
        shots = [{"shot_id": "x", "start": 0.0, "end": 3.0, "treatment": "p", "transition_in": "cut"}, {"shot_id": "y", "start": 3.0, "end": 6.0, "treatment": "p", "transition_in": "cut"}]
        r = film_qa.analyze(mp4, shots, os.path.join(self.d, "qa2"), sheets=False)
        self.assertEqual(r["video"]["joins"]["luma_flashes_or_dips"], [])
        self.assertTrue(r["verdict"].startswith("NOT ASSESSED"))
        self.assertIn("error", r["audio"])        # no audio stream is reported, not invented

    def test_audio_bed_measurement_on_a_known_mix(self):
        v, out = os.path.join(self.d, "v.wav"), os.path.join(self.d, "mix.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "aevalsrc='sin(2*PI*180*t)*0.28*lt(mod(t\\,1.2)\\,0.8)':s=44100:d=30", "-ac", "1", v], check=True)
        plan = sound.build_plan([{"shot_id": str(i), "start": i * 3.0, "end": i * 3.0 + 3.0, "text": "x", "genre": "neutral", "energy": 3, "transition_in": "cut",
                                  "continuity": {"location": "room"}, "env": []} for i in range(10)], 30.0, sfx=False, ambience=False)
        r = sound.render_mix(plan, v, out, work_dir=self.d)
        self.assertFalse(r["fallback"], r)
        a = film_qa.audio_report(out, 0, 30, v)["voice_vs_mix"]
        self.assertTrue(a["bed_present"])
        self.assertAlmostEqual(a["voice_gain_in_mix"], 1.0, delta=0.01)
        self.assertGreater(a["ducking_depth_db"], 3.0)
        # and the same voice alone reads as "no bed"
        a0 = film_qa.audio_report(v, 0, 30, v)["voice_vs_mix"]
        self.assertFalse(a0["bed_present"])
        self.assertIn("narration alone", a0["note"])


if __name__ == "__main__":
    unittest.main()
