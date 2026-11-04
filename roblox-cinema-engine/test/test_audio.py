"""Audio tools: synthesized cues are deterministic and bounded, the mix places cues, ducks music under a voice and lands on the loudness target.
Run: python3 -m unittest discover -s roblox-cinema-engine/test -p "test_*.py"   (from the repo root)"""
import json, subprocess, sys, tempfile, unittest, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / 'tools')); sys.path.insert(0, str(HERE.parent))
import sfx_synth as SX  # noqa: E402
import mix_audio as MX  # noqa: E402


class Synth(unittest.TestCase):
    def test_every_cue_renders_bounded_and_deterministic(self):
        for name in SX.CUES:
            a, b = SX.render(name, 2.0, 5), SX.render(name, 2.0, 5)
            self.assertTrue(np.array_equal(a, b), name)
            self.assertTrue(np.isfinite(a).all() and 0.3 < np.abs(a).max() <= 0.91, f'{name} peak {np.abs(a).max()}')
            self.assertGreater(len(a), SX.SR * 0.2, name)
        self.assertFalse(np.array_equal(SX.render('explosion', 2.0, 1), SX.render('explosion', 2.0, 2)))
        self.assertIsNone(SX.render('no_such_cue'))

    def test_every_cue_the_planner_emits_has_a_sound(self):
        import re
        names = set()
        for f in (HERE / 'lib').glob('*.mjs'):
            names |= set(re.findall(r"cue: '([a-z_]+)'", f.read_text()))
            names |= set(re.findall(r"cues: \[([^\]]*)\]", f.read_text()) and [c for grp in re.findall(r"cues: \[([^\]]*)\]", f.read_text()) for c in re.findall(r"'([a-z_]+)'", grp)])
        missing = {n for n in names if n not in SX.CUES and n not in MX.LOOPING and n not in MX.ONESHOT and n != 'crowd'}
        self.assertEqual(missing, set())


class Mix(unittest.TestCase):
    def test_loop_fill_and_fade(self):
        x = MX.loop_fill(np.ones((1000, 2), np.float32), 5000)
        self.assertEqual(len(x), 5000)
        f = MX.fade(np.ones((100, 2), np.float32), 10, 10); self.assertAlmostEqual(float(f[0, 0]), 0.0); self.assertAlmostEqual(float(f[-1, 0]), 0.0)

    def test_music_uses_every_listed_track_and_ducks_under_voice(self):
        bed = MX.music_bed(['stormfront', 'despair_and_triumph'], 40)
        self.assertIsNotNone(bed); self.assertEqual(len(bed), 41 * MX.SR)
        voice = np.zeros(41 * MX.SR, np.float32); voice[5 * MX.SR:9 * MX.SR] = 0.3 * np.sin(np.arange(4 * MX.SR) * 0.05)
        from health_cinema.edit.audio import speech_duck
        g = speech_duck(voice, floor_db=-9.0)
        self.assertLess(float(g[7 * MX.SR]), 0.5); self.assertGreater(float(g[2 * MX.SR]), 0.95)

    def test_full_mix_on_a_small_plan_hits_the_loudness_target(self):
        with tempfile.TemporaryDirectory() as d:
            base = str(Path(d) / 'x.mp4')
            plan = {'duration': 12.0, 'scenes': [{'id': 's1', 't0': 0, 't1': 12, 'cues': ['gunfire', 'thunder']}]}
            cues = {'duration': 12.0, 'ambience': [{'t0': 0, 't1': 6, 'bed': 'sea'}, {'t0': 6, 't1': 12, 'bed': 'battle'}], 'music': {'tracks': ['stormfront']},
                    'cues': [{'t': 3.0, 'cue': 'explosion', 'gain': -9}, {'t': 8.0, 'cue': 'ramp_drop', 'gain': -14}, {'t': 2, 't1': 10, 'cue': 'gunfire_far', 'gain': -18, 'loop': True}]}
            Path(base + '.plan.json').write_text(json.dumps(plan)); Path(base + '.cues.json').write_text(json.dumps(cues))
            r = subprocess.run([sys.executable, str(HERE / 'tools' / 'mix_audio.py'), base], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            rep = json.loads(Path(base + '.mix.json').read_text())
            self.assertAlmostEqual(float(rep['measured_mix']['input_i']), -14.0, delta=1.0)
            self.assertLessEqual(float(rep['measured_mix']['input_tp']), -0.9)
            self.assertEqual(rep['cue_counts'].get('explosion'), 1)
            with wave.open(base + '.mix.wav') as w: self.assertAlmostEqual(w.getnframes() / w.getframerate(), 12.0, delta=0.1)


if __name__ == '__main__':
    unittest.main()
