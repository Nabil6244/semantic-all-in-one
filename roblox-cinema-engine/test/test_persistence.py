"""A Roblox Cinema project keeps its page choices and its planned film, and reuses the voice-over timing while the voice file is unchanged."""
import importlib.util, json, sys, tempfile, types, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ui import roblox_cinema_section as S  # noqa: E402


def load_runner():
    spec = importlib.util.spec_from_file_location('rce_runner_t', ROOT / 'roblox-cinema-engine' / 'runner.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Var:
    def __init__(self, v=''): self.v = v; self.cbs = []
    def get(self): return self.v
    def set(self, v):
        self.v = v
        for c in self.cbs: c()
    def trace_add(self, _m, cb): self.cbs.append(cb)


class Box:
    def __init__(self): self.t = ''
    def get(self, *_a): return self.t
    def delete(self, *_a): self.t = ''
    def insert(self, _i, t): self.t = t
    def bind(self, *_a): pass


def make_app(state_dir):
    a = types.SimpleNamespace(_workspace=types.SimpleNamespace(state_dir=str(state_dir)) if state_dir else None, _rc_text_box=Box(), _rc_csv_var=Var(), _rc_voice_var=Var(),
                              _rc_res_var=Var(next(iter(S.RESOLUTIONS))), _rc_music_var=Var(True), _rc_status_var=Var(), _rc_planned=None, _rc_running=False)
    S._wire_persistence(a)
    return a


class Persistence(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.tmp = Path(self.d.name)
        (self.tmp / 'state').mkdir(); self.csv = self.tmp / 's.csv'; self.csv.write_text('row,text\nbeat,Hello there.\n'); self.voice = self.tmp / 'v.wav'; self.voice.write_bytes(b'RIFF0000')
        self.base = str(self.tmp / 'state' / 'roblox_cinema' / 'film'); Path(self.base).parent.mkdir(parents=True)
        Path(self.base + '.mp4.plan.json').write_text('{}')

    def tearDown(self): self.d.cleanup()

    def _planned(self, a):
        a._rc_planned = {'src': {'csv': str(self.csv)}, 'voice': str(self.voice), 'res': 720, 'music': True, 'base': self.base}; S._save(a)

    def test_choices_and_plan_come_back_when_the_project_reopens(self):
        a = make_app(self.tmp / 'state'); S._restore(a)
        a._rc_csv_var.set(str(self.csv)); a._rc_voice_var.set(str(self.voice)); a._rc_music_var.set(False); a._rc_text_box.t = 'pasted words'
        self._planned(a)
        b = make_app(self.tmp / 'state'); S._restore(b)          # a fresh page, same project
        self.assertEqual((b._rc_csv_var.get(), b._rc_voice_var.get(), b._rc_music_var.get(), b._rc_text_box.t), (str(self.csv), str(self.voice), False, 'pasted words'))
        self.assertIsNotNone(b._rc_planned); self.assertEqual(b._rc_planned['base'], self.base)

    def test_a_changed_story_or_voice_means_generate_again(self):
        a = make_app(self.tmp / 'state'); S._restore(a); a._rc_csv_var.set(str(self.csv)); self._planned(a)
        self.csv.write_text('row,text\nbeat,Hello there, changed.\n')
        b = make_app(self.tmp / 'state'); S._restore(b)
        self.assertIsNone(b._rc_planned); self.assertEqual(b._rc_csv_var.get(), str(self.csv))   # the choice is still remembered
        self._planned(a); self.voice.write_bytes(b'RIFF000000000')
        c = make_app(self.tmp / 'state'); S._restore(c); self.assertIsNone(c._rc_planned)

    def test_another_project_does_not_inherit_the_plan(self):
        a = make_app(self.tmp / 'state'); S._restore(a); self._planned(a)
        other = self.tmp / 'other'; other.mkdir()
        a._workspace = types.SimpleNamespace(state_dir=str(other)); S._restore(a)
        self.assertIsNone(a._rc_planned)

    def test_voice_timing_is_reused_only_while_the_voice_file_is_unchanged(self):
        r = load_runner(); calls = []
        r._tools = lambda: types.SimpleNamespace(transcribe=lambda src, dst: (calls.append(src), Path(dst).write_text(json.dumps({'duration': 3, 'words': [{'word': 'a', 'start': 0, 'end': 1}]})), 1)[2])
        words = str(self.tmp / 'w.json'); log = []
        self.assertEqual(r._voice_words(str(self.voice), words, None, log.append), 1); self.assertEqual(len(calls), 1)
        self.assertEqual(r._voice_words(str(self.voice), words, None, log.append), 1); self.assertEqual(len(calls), 1)   # reused
        self.assertIn('reused', log[-1])
        self.voice.write_bytes(b'RIFF-another-voice'); r._voice_words(str(self.voice), words, None, log.append); self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
