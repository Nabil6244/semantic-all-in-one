"""Horror picture cards through the Visuals tab (cards.py). Synthetic plans; a fake asset manager, so nothing is fetched and no AI is called."""
import json
import sys
import tempfile
import unittest
from importlib import util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
spec = util.spec_from_file_location('rce_cards_test', REPO / 'roblox-cinema-engine' / 'cards.py')
C = util.module_from_spec(spec); spec.loader.exec_module(C)


class FakeManager:
    def __init__(self, fail=False): self.settings, self.asked, self.fail = {'gemini_enabled': True}, [], fail
    def request_cancel(self): pass
    def resolve_all(self, rows):
        self.asked = [r.scene_number for r in rows]
        if self.fail: raise RuntimeError('Flow is not signed in')


class Cards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name); self.images = self.d / 'assets'

    def plan(self, cards):
        f = self.d / 'film.mp4.plan.json'; f.write_text(json.dumps({'scenes': [], **({'cards': cards} if cards is not None else {})})); return str(f)

    def test_history_plan_has_no_requests(self):
        self.assertEqual(C.requests(self.plan(None), self.images), [])
        self.assertFalse(self.images.exists(), 'nothing is written for a film without cards')

    def test_only_picture_cards_are_requested(self):
        r = C.requests(self.plan([{'id': 'c1', 'kind': 'clock', 'picture': False}, {'id': 'c2', 'kind': 'drawing', 'picture': True, 'prompt': 'p', 'what': 'w'}]), self.images)
        self.assertEqual([(x['id'], x['n']) for x in r], [('c2', 1)])
        row = C.table_rows(r)[0]
        self.assertEqual(row.scene_number, '1')
        self.assertTrue(row.wants_flow_image)

    def test_a_card_keeps_its_number_so_an_old_picture_never_lands_on_another_card(self):
        first = C.requests(self.plan([{'id': 'c1', 'picture': True, 'prompt': 'drawing'}, {'id': 'c2', 'picture': True, 'prompt': 'letter'}]), self.images)
        again = C.requests(self.plan([{'id': 'c1', 'picture': True, 'prompt': 'new thing'}, {'id': 'c2', 'picture': True, 'prompt': 'letter'}]), self.images)
        self.assertEqual(first[1]['n'], again[1]['n'])
        self.assertNotIn(again[0]['n'], [c['n'] for c in first])

    def test_fetch_makes_no_ai_calls_and_keeps_own_files(self):
        pic = self.d / 'own.png'; pic.write_bytes(b'x')
        reqs = C.requests(self.plan([{'id': 'c1', 'picture': True, 'prompt': 'a', 'asset': 'own.png'}, {'id': 'c2', 'picture': True, 'prompt': 'b'}]), self.images)
        m = FakeManager()
        rows = C.fetch(reqs, m, self.images, base_dir=str(self.d))
        self.assertEqual(m.settings['gemini_enabled'], False)
        self.assertEqual(m.asked, [str(reqs[1]['n'])], "the CSV's own file is not fetched")
        import visual_bridge
        self.assertEqual(C.pictures(reqs, visual_bridge.records(self.images, rows)), {'c1': str(pic)})

    def test_a_failed_fetch_leaves_the_card_code_made_and_does_not_raise(self):
        reqs = C.requests(self.plan([{'id': 'c1', 'picture': True, 'prompt': 'a'}]), self.images)
        rows = C.fetch(reqs, FakeManager(fail=True), self.images)
        import visual_bridge
        out = self.d / 'cards.json'
        C.write_pictures(str(out), reqs, visual_bridge.records(self.images, rows))
        self.assertEqual(json.loads(out.read_text()), {})

    def test_pictures_ignores_videos_and_gone_files(self):
        vid = self.d / 'a.mp4'; vid.write_bytes(b'x'); img = self.d / 'a.JPG'; img.write_bytes(b'x')
        reqs = [{'n': 1, 'id': 'c1'}, {'n': 2, 'id': 'c2'}, {'n': 3, 'id': 'c3'}, {'n': 4, 'id': 'c4'}]
        recs = {1: {'path': str(vid)}, 2: {'path': str(self.d / 'gone.png')}, 3: {'path': str(img)}}
        self.assertEqual(C.pictures(reqs, recs), {'c3': str(img)})

    def test_the_visuals_tab_knows_the_style(self):
        import visual_bridge
        self.assertEqual(visual_bridge.OWNERS['roblox_cinema'][0], '_rc_active')
        import ui.roblox_cinema_section as S
        self.assertEqual(S.OWNER, 'roblox_cinema')
        self.assertTrue((S._engine_dir() / 'cards.py').is_file())


if __name__ == '__main__':
    unittest.main()
