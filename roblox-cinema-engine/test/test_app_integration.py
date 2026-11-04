"""App integration: the style is registered by appended lines only, app.py hooks exist at every Product Trailer site, no existing app.py line
was removed (the protected-manifest rule), and the section module imports. Run from the repo root: python3 -m unittest discover -s roblox-cinema-engine/test"""
import re, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))


class Integration(unittest.TestCase):
    def test_registry(self):
        from ui import style_registry as R
        self.assertIn('Roblox Cinema', R.with_extras(('Normal video',)))
        self.assertIn('Roblox Cinema', dict(R.GROUPS)['Documentary'])
        self.assertIn('Roblox Cinema', R.EXTRA_BLURBS); self.assertEqual(len(R.EXTRA_CARDS['Roblox Cinema']), 4)

    def test_section_module(self):
        import ui.roblox_cinema_section as S
        for fn in ('build', 'activate', 'deactivate', 'sync_cta', 'cta', 'cancel', 'on_generate', 'on_render', 'options'): self.assertTrue(callable(getattr(S, fn)), fn)
        self.assertTrue((S._engine_dir() / 'runner.py').is_file() and (S._engine_dir() / 'render.mjs').is_file())

    def test_app_hooks_one_per_product_trailer_site(self):
        s = (REPO / 'app.py').read_text()
        for needle in ('from ui import roblox_cinema_section as _rc_section', 'return "Roblox Cinema"', '_rc_section.activate(self)', '_rc_section.deactivate(self)',
                       'rc_block.grid() if active == "Roblox Cinema"', '("rc_generate", "rc_render", "rc_cancel")', '_rc_section.sync_cta(self)', '_RUN_FLAGS + ("_rc_running",)'):
            self.assertIn(needle, s, needle)

    def test_app_py_has_no_removed_lines(self):
        r = subprocess.run(['git', 'diff', '--numstat', '--', 'app.py'], cwd=REPO, capture_output=True, text=True).stdout.split()
        if r: self.assertEqual(r[1], '0', f'app.py lost {r[1]} lines vs HEAD (additions only)')


if __name__ == '__main__':
    unittest.main()
