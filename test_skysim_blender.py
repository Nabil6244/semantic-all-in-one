"""Sky Sim Blender runner: scene grouping, per-frame sky states, and the 2D fallback (none of these start Blender)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from skysim import blender_runner as br
from test_skysim_steps import run

ENGINE = Path(__file__).resolve().parent / 'whatif-engine'


class Scenes(unittest.TestCase):
    def test_ton618_is_one_blender_scene(self):
        _, _, spec, _ = run('ton618_distance.csv')
        groups = br.scenes(spec)
        self.assertEqual(len(groups), 1)
        self.assertEqual((groups[0]['start'], groups[0]['end']), (0.0, spec['duration']))
        self.assertEqual(len(groups[0]['shots']), 6)

    def test_space_steps_are_not_blender_scenes(self):
        _, _, spec, _ = run('sun_every_planet.csv')
        self.assertEqual(br.scenes(spec), [])

    def test_frame_states_follow_the_light_and_cover_the_scene(self):
        _, _, spec, _ = run('ton618_distance.csv')
        g = br.scenes(spec)[0]
        states = br.frame_states(g, 15)
        keys = br.frame_states(g)                                # adaptive: fewer, same span
        self.assertLess(len(keys), len(states))
        self.assertGreaterEqual(keys[-1]['t'], g['end'] - 1e-6)                # the last output frame is covered
        self.assertGreaterEqual(states[-1]['t'], g['end'] - 1 / 15)
        flux = [s['flux_x'] for s in states]
        self.assertLess(flux[0], 1e-15)
        self.assertGreater(flux[-1], 1e6)
        self.assertTrue(all(b >= a * 0.999 for a, b in zip(flux, flux[1:])), 'the object only comes closer')
        self.assertEqual(len({s['name'] for s in states}), len(states))


class Parity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_easing_matches_the_engine(self):
        shot = {'start': 10, 'end': 20, 'camera': 'push', 'sky': {'angular_deg': 10, 'flux_x': 100}, 'sky_from': {'angular_deg': 0.1, 'flux_x': 1}}
        js = ("import('./lib/skysim_sky.mjs').then(m => { const s = %s; const out = [11, 13.5, 18].map(t => "
              "[m.skyAt(s, t).angular_deg, m.skyAt(s, t).flux_x, m.cameraAt(s, t).scale]); console.log(JSON.stringify(out)); })") % json.dumps(shot)
        got = json.loads(subprocess.run(['node', '-e', js], cwd=ENGINE, capture_output=True, text=True, check=True).stdout)
        for t, (a, f, sc) in zip((11, 13.5, 18), got):
            py = br.sky_at(shot, t)
            self.assertAlmostEqual(py['angular_deg'], a, places=9)
            self.assertAlmostEqual(py['flux_x'], f, places=6)
            self.assertAlmostEqual(br.camera_at(shot, t)['scale'], sc, places=9)


class Fallback(unittest.TestCase):
    def test_no_blender_keeps_the_2d_look(self):
        _, _, spec, _ = run('ton618_distance.csv')
        with mock.patch.object(br, 'find_blender', return_value=None):
            notes = br.apply(spec, Path('/nonexistent'))
        self.assertIn('Blender not found', notes[0])
        self.assertTrue(all(s['kind'] == 'sky' for s in spec['shots']))

    def test_a_failed_scene_stays_2d(self):
        _, _, spec, _ = run('ton618_distance.csv')
        with mock.patch.object(br, 'render_scene', side_effect=RuntimeError('boom')):
            notes = br.apply(spec, Path('/tmp/skysim_test_media'), blender='/bin/true')
        self.assertIn('boom', notes[0])
        self.assertTrue(all(s['kind'] == 'sky' for s in spec['shots']))

    def test_rendered_scene_becomes_video_shots_with_anchors(self):
        _, _, spec, _ = run('ton618_distance.csv')
        states = [{'name': f'k{i:07d}', 't': i / 10} for i in range(600)]
        fake = {'file': Path('scene1.mp4'), 'anchors': {s['name']: {'x': 0.5, 'y': 0.3, 'r': 0.01} for s in states}, 'states': states}
        with mock.patch.object(br, 'render_scene', return_value=fake):
            br.apply(spec, Path('/tmp/skysim_test_media'), blender='/bin/true')
        shots = spec['shots']
        self.assertTrue(all(s['kind'] == 'video' and s['file'] == 'scene1.mp4' for s in shots))
        self.assertEqual([s['in_s'] for s in shots], [s['start'] for s in shots])
        self.assertEqual(shots[0]['_anchor'], {'x': 960.0, 'y': 324.0, 'r': 19.2})


if __name__ == '__main__':
    unittest.main()
