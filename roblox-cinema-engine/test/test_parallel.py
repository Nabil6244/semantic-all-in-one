"""Parallel render: the frames are split into contiguous ranges that cover the film exactly once, joined without re-encoding."""
import importlib.util, json, subprocess, tempfile, types, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location('rce_runner_p', ROOT / 'roblox-cinema-engine' / 'runner.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Parallel(unittest.TestCase):
    def setUp(self):
        self.r = load(); self.d = tempfile.TemporaryDirectory(); self.silent = str(Path(self.d.name) / 'film.silent.mp4'); self.calls = []; self.concat = []
        self.r._binaries = lambda: ('node', 'ffmpeg')
        Path(self.silent + '.plan.json').write_text(json.dumps({'fps': 24}))

    def tearDown(self): self.d.cleanup()

    def fake_node(self, duration, fail_part=None):
        def run(args, **kw):
            self.calls.append(args)
            if '--plan-only' in args: return {'plan': {'duration': duration}, 'warnings': [], 'perf': None}
            out = args[args.index('--out') + 1]; Path(out).write_bytes(b'x')
            if fail_part and fail_part in out: raise RuntimeError('boom')
            return {'plan': None, 'warnings': ['w'], 'perf': {'wall_s': 1}}
        self.r._run_node = run
        self.r.subprocess = types.SimpleNamespace(run=lambda cmd, **k: (self.concat.append(cmd), types.SimpleNamespace(returncode=0, stderr=''))[1], PIPE=subprocess.PIPE)

    def test_a_short_film_is_left_to_one_renderer(self):
        self.fake_node(20.0)
        self.assertIsNone(self.r._render_parallel(['--csv', 'a', '--out', self.silent], self.silent, 3))

    def test_ranges_cover_every_frame_exactly_once_and_are_joined_by_copy(self):
        self.fake_node(125.0)                               # 3000 frames
        res = self.r._render_parallel(['--csv', 'a', '--out', self.silent], self.silent, 3)
        ranges = sorted(tuple(int(x) for x in c[c.index('--range') + 1].split(',')) for c in self.calls if '--range' in c)
        self.assertEqual(ranges[0][0], 0); self.assertEqual(ranges[-1][1], 3000)
        for (a, b), (c, d) in zip(ranges, ranges[1:]): self.assertEqual(b, c)
        self.assertEqual(len(ranges), 3); self.assertEqual(res['perf']['parallel_parts'], 3)
        self.assertIn('copy', self.concat[0]); self.assertEqual(self.concat[0][self.concat[0].index('-c') + 1], 'copy')   # nothing is re-encoded
        self.assertFalse(list(Path(self.d.name).glob('*.part*')))                                            # the part files are cleaned up

    def test_one_failing_part_fails_the_render_and_leaves_no_parts(self):
        self.fake_node(125.0, fail_part='part1')
        with self.assertRaises(RuntimeError): self.r._render_parallel(['--csv', 'a', '--out', self.silent], self.silent, 3)
        self.assertFalse(list(Path(self.d.name).glob('*.part*'))); self.assertEqual(self.concat, [])

    def test_workers_are_chosen_from_the_cores(self):
        self.assertIn(self.r.auto_workers(), (1, 2, 3))


if __name__ == '__main__':
    unittest.main()
