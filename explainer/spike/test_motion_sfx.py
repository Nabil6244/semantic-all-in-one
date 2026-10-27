"""Sound layer tests (explainer/motion/sfx.py + build_sfx.py). Objective measurements only: nobody has listened to these assets.
usage: python3 -B explainer/spike/test_motion_sfx.py   (from the repository root)"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from explainer.motion import build_sfx as B     # noqa: E402
from explainer.motion import sfx as S           # noqa: E402

EVIDENCE = ROOT / "docs" / "explainer" / "phase_sound_evidence"


def track_of(events, dur=20.0, notes=None):
    p = S.build_sfx_track(events, dur, 30, tempfile.mktemp(suffix=".wav"), notes=notes)
    x, sr = S.read_wav(Path(p))
    return x, sr


class Assets(unittest.TestCase):
    def test_check_passes(self):
        r = subprocess.run([sys.executable, "-B", str(ROOT / "explainer/motion/build_sfx.py"), "--check"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_verify_and_size(self):
        self.assertEqual(S.verify_assets(), [])
        total = sum(p.stat().st_size for p in S.ASSETS.iterdir())
        self.assertLess(total, 6 * 1024 * 1024)
        print("assets total bytes:", total)

    def test_deterministic(self):
        a, _ = B.build_all()
        b, _ = B.build_all()
        self.assertEqual(a, b)

    def test_no_clipping_and_levels(self):
        for fn in S._manifest()["files"]:
            x, sr = S.read_wav(S.ASSETS / fn)
            pk = float(np.max(np.abs(x)))
            self.assertLess(pk, 0.9, fn)
            if fn.startswith("bed_"):
                rms = 20 * np.log10(np.sqrt(np.mean(x ** 2)))
                self.assertTrue(-19.5 < rms < -16.5, (fn, rms))
            else:
                self.assertTrue(0.45 < pk < 0.55, (fn, pk))                    # -6 dBFS
                self.assertLess(len(x) / sr, 1.2)
                self.assertLess(abs(x.mean()), 0.01)
                # never harsh: little energy above 8 kHz
                sp = np.abs(np.fft.rfft(x)) ** 2
                f = np.fft.rfftfreq(len(x), 1 / sr)
                self.assertLess(sp[f > 8000].sum() / sp.sum(), 0.02, fn)

    def test_beds_loop_seamlessly(self):
        for mood in B.MOODS:
            x, sr = S.read_wav(S.ASSETS / ("bed_%s.wav" % mood))
            self.assertEqual(len(x), sr * 30)
            step = float(np.max(np.abs(np.diff(x))))                          # largest sample-to-sample move inside the bed
            join = abs(float(x[0] - x[-1]))
            self.assertLessEqual(join, step * 1.5, (mood, join, step))
            self.assertLess(join, 0.02)


class Track(unittest.TestCase):
    def test_length_exact(self):
        for d in (3.0, 12.345, 60.0):
            x, sr = track_of([{"t": 1.0, "kind": "stamp"}], d)
            self.assertEqual(len(x), int(round(d * sr)))

    def test_stamp_impact_placement(self):
        x, sr = track_of([{"t": 5.0, "kind": "stamp"}], 8.0)
        i = int(np.argmax(np.abs(x)))
        self.assertAlmostEqual(i / sr, 5.0 + 4 / 30.0, delta=0.001)
        self.assertLess(float(np.max(np.abs(x))), 0.9)

    def test_whoosh_at_onset_and_quiet_before(self):
        x, sr = track_of([{"t": 3.0, "kind": "slide"}], 6.0)
        self.assertEqual(float(np.max(np.abs(x[:int(3.0 * sr) - 1]))), 0.0)
        self.assertGreater(float(np.max(np.abs(x[int(3.0 * sr):int(3.5 * sr)]))), 0.01)

    def test_count_ticks_slow_down(self):
        ev, _ = S.select_events([{"t": 2.0, "kind": "count", "frames": 30}])
        seq = ev[0]["seq"]
        gaps = np.diff(seq)
        self.assertEqual(len(seq), S.COUNT_TICKS)
        self.assertTrue(all(gaps[i] < gaps[i + 1] for i in range(len(gaps) - 1)))
        self.assertAlmostEqual(seq[-1] - 2.0, 1.0 * (1 - (1 / 8) ** (1 / 3)), delta=0.01)

    def test_density(self):
        ev = [{"t": 1.0 + 0.1 * i, "kind": k} for i, k in enumerate(("stamp", "slide", "pop", "rustle", "cross", "reveal", "pop", "slide"))]
        kept, dropped = S.select_events(ev)
        ats = sorted(e["at"] for e in kept)
        for i in range(len(ats) - S.MAX_PER_WINDOW):
            self.assertGreaterEqual(ats[i + S.MAX_PER_WINDOW] - ats[i], S.WINDOW_S - 1e-9)
        self.assertTrue(dropped)
        self.assertIn("stamp", [e["kind"] for e in kept])                       # highest priority survives
        kept2, _ = S.select_events([{"t": 1.0, "kind": "pop"}, {"t": 1.2, "kind": "pop"}, {"t": 1.3, "kind": "pop"}, {"t": 1.6, "kind": "pop"}])
        pops = sorted(e["at"] for e in kept2)
        self.assertTrue(all(b - a >= S.SAME_KIND_GAP_S - 1e-9 for a, b in zip(pops, pops[1:])))

    def test_missing_asset_silent_with_note(self):
        notes = []
        saved = S._cache.copy()
        S._cache["a:stamp_thump.wav"] = "stamp_thump.wav: gone"
        try:
            x, sr = track_of([{"t": 1.0, "kind": "stamp"}], 3.0, notes)
        finally:
            S._cache.clear()
            S._cache.update(saved)
        self.assertEqual(float(np.max(np.abs(x))), 0.0)
        self.assertTrue(any("unavailable" in n for n in notes))

    def test_report_walk(self):
        rep = {"selection": {"beats": [{"id": "b1", "start": 10.0, "end": 20.0}]},
               "beat_details": {"b1": {"cue_specs": [{"id": "s", "kind": "visual", "params": {"style": "stamp"}}, {"id": "n", "kind": "visual", "params": {"style": "plate", "count": {"frames": 30}}}, {"id": "z", "kind": "visual", "params": {"style": "stamp"}}],
                                       "layout": [{"cue": "s", "first_frame": 30}, {"cue": "n", "first_frame": 60}]}}}
        ev = S.events_from_report(rep)
        self.assertEqual([(e["kind"], round(e["t"], 3)) for e in ev], [("stamp", 11.0), ("slide", 12.0), ("count", 12.0)])
        x, sr = track_of(rep, 25.0)
        self.assertAlmostEqual(int(np.argmax(np.abs(x[:int(11.9 * sr)]))) / sr, 11.0 + 4 / 30.0, delta=0.001)


class Bed(unittest.TestCase):
    def test_ducking(self):
        bed = S.load_bed("neutral")
        y, sr = S.duck_bed_under_voice(bed, [(10.0, 20.0)], 40.0)
        self.assertEqual(len(y), 40 * sr)

        def db(a, b):
            seg = y[int(a * sr):int(b * sr)]
            ref = S._resample(np.tile(bed[0], 3), bed[1], sr)[int(a * sr):int(b * sr)]
            return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) / np.sqrt(np.mean(ref ** 2)))
        self.assertAlmostEqual(db(5, 9), -16.0, delta=0.7)                       # gap
        self.assertAlmostEqual(db(14, 19), -22.0, delta=0.7)                     # speech
        self.assertAlmostEqual(db(30, 38), -16.0, delta=0.7)
        c = S.duck_curve_db([(10.0, 20.0)], 40.0)
        r = 200
        self.assertGreater(c[int(10.05 * r)], -19.0)                              # still on its way down 50 ms in
        self.assertLess(c[int(10.25 * r)], -21.0)                                 # attack: ~95% of the way in 250 ms
        self.assertLess(c[int(20.3 * r)], -16.8)                                  # release is slower than attack: 300 ms in, not yet back
        self.assertGreater(c[int(20.6 * r)], -17.0)                               # 600 ms: ~95% back
        self.assertLessEqual(float(c.max()), -16.0 + 1e-6)

    def test_windows_from_words(self):
        w = S.voice_windows_from_words([("a", 0.0, 0.4), ("b", 0.5, 0.9), ("c", 2.0, 2.3)])
        self.assertEqual(w, [(0.0, 0.9), (2.0, 2.3)])

    def test_mix_and_demo(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        ev = [{"t": 0.5, "kind": "slide"}, {"t": 1.0, "kind": "stamp"}, {"t": 2.0, "kind": "pop"}, {"t": 2.6, "kind": "rustle"}, {"t": 3.5, "kind": "count", "frames": 30}, {"t": 5.0, "kind": "cross"},
              {"t": 6.2, "kind": "reveal"}, {"t": 7.5, "kind": "stamp"}]
        notes = []
        sfx = S.build_sfx_track(ev, 10.0, 30, str(EVIDENCE / "demo_sfx_only.wav"), notes=notes)
        x, sr = S.duck_bed_under_voice(S.load_bed("neutral"), [(2.0, 4.0), (6.0, 9.0)], 10.0)
        bedp = str(EVIDENCE / "demo_bed_ducked.wav")
        S._write_wav(bedp, x, sr)
        out = S.mix_explainer_audio(None, sfx, bedp, str(EVIDENCE / "demo_10s_sfx_and_bed.wav"), 10.0, notes=notes)
        self.assertIsNotNone(out, notes)
        y, sr2 = S.read_wav(Path(out))
        self.assertEqual(sr2, 48000)
        self.assertAlmostEqual(len(y) / sr2, 10.0, delta=0.01)
        self.assertLess(float(np.max(np.abs(y))), 0.96)
        w = int(0.4 * sr2)
        rms = [20 * np.log10(np.sqrt(np.mean(y[i:i + w] ** 2)) + 1e-9) for i in range(0, len(y) - w, w)]
        print("demo RMS per 0.4 s window (dBFS): min %.1f max %.1f peak %.3f" % (min(rms), max(rms), float(np.max(np.abs(y)))))
        self.assertLess(max(rms), -12.0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
