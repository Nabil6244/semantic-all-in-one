"""Sky Sim step CSV, planner and preflight (docs/skysim/PLAN.md step 2)."""
import math
import unittest
from unittest import mock
from pathlib import Path

from skysim import planner, preflight
from skysim.steps import read_steps
from whatif.narration import Word

SAMPLES = Path(__file__).resolve().parent / 'skysim' / 'samples'


def timed_words(steps, step=0.35, gap=0.6):
    """The steps' narration as a fake voiceover: one word every 0.35 s, a short pause between steps."""
    out, t = [], 0.0
    for s in steps:
        for w in s.narration.split():
            out.append(Word(w, w.lower().strip('.,?!'), t, t + 0.3))
            t += step
        t += gap
    return out, t + 1.0


def run(name):
    text = (SAMPLES / name).read_text()
    steps, _ = read_steps(text)
    words, dur = timed_words(steps)
    spec, rep = preflight.dry_run(text, words, dur)
    return steps, words, spec, rep


class Samples(unittest.TestCase):
    def test_samples_plan_clean(self):
        for name in ('sun_every_planet.csv', 'ton618_distance.csv'):
            _, _, spec, rep = run(name)
            self.assertEqual(rep['problems'], [], name)
            self.assertEqual(rep['repaired'], [], name)
            self.assertEqual(spec['shots'][-1]['end'], spec['duration'])

    def test_steps_start_on_their_words(self):
        steps, words, spec, _ = run('sun_every_planet.csv')
        firsts = [w for w in words if w.text == 'Now']
        self.assertEqual(spec['shots'][1]['start'], round(firsts[0].start, 3))
        self.assertEqual(spec['shots'][0]['start'], 0.0)

    def test_sun_from_mercury_readouts(self):
        _, _, spec, _ = run('sun_every_planet.csv')
        L = spec['layers']
        start = spec['shots'][1]['start']
        stats = [x for x in L if x['type'] == 'sk_stats' and x['start'] == start][0]
        values = {r['label']: r['value'] for r in stats['rows']}
        self.assertEqual(values['SIZE IN THE SKY'], '2.6× wider than from Earth')
        self.assertEqual(values['LIGHT'], "6.7× Earth's sunlight")
        self.assertEqual(values['LIGHT TRAVEL TIME'], '3 min 13 s')
        self.assertTrue(values['DISTANCE FROM THE SUN'].startswith('0.39 AU'))
        self.assertIn('THE SUN FROM MERCURY', [x['text'] for x in L if x['type'] == 'sk_title'])
        ring = [x for x in L if x['type'] == 'sk_scalering' and x['start'] == start][0]
        self.assertAlmostEqual(ring['ratio'], 0.387, delta=0.01)

    def test_phobos_view(self):
        _, _, spec, _ = run('sun_every_planet.csv')
        shot = spec['shots'][3]
        self.assertEqual((shot['look'], shot['sky']['object']), ('moon_surface', 'mars'))
        stats = [x for x in spec['layers'] if x['type'] == 'sk_stats' and x['start'] == shot['start']][0]
        self.assertIn('42° · 82× our Moon',   # reference shows 81× (Moon taken as 0.52°)
[r['value'] for r in stats['rows']])

    def test_ton618_is_one_held_scene(self):
        _, _, spec, _ = run('ton618_distance.csv')
        shots = spec['shots']
        self.assertEqual({s['scene'] for s in shots}, {'scene1'})
        self.assertTrue(all(s['enter'] == 'continue' and 'sky_from' in s for s in shots[1:]))
        self.assertEqual([s['sky']['stage'] for s in shots], ['night', 'night', 'day', 'day', 'burn', 'melt'])
        cards = [x for x in spec['layers'] if x['type'] == 'sk_rungcard']
        self.assertEqual([c['value'] for c in cards], ['10.8 BILLION LY', '1,000,000 LY', '1,000 LY', '187 LY', '50 LY', '0.1 LY'])
        self.assertEqual(cards[0]['lines'], ['Magnitude 12.1: too faint for the eye'])
        self.assertEqual(cards[4]['lines'], ["14 times the Sun's light", 'Earth: about 250 °C'])
        # the card holds the distance and the facts for the whole rung; nothing repeats it top right
        self.assertEqual([r['label'] for x in spec['layers'] if x['type'] in ('sk_stats', 'sk_readout') for r in x['rows']], ['EVENT HORIZON'])
        self.assertTrue(all(abs(c['end'] - s['end']) < 1e-3 for c, s in zip(cards, shots)))
        # every rung gets a new camera angle (the CSV repeats 'shore' on steps 1-2 and 5-6)
        from skysim import blender_runner as br
        vs = br.views_for(shots)
        self.assertTrue(all(x != y for x, y in zip(vs, vs[1:])), vs)


class Repair(unittest.TestCase):
    MESSY = ('Scene;Target;Viewer;Dist;Stats;Move;VO;extra\n'
             'landscap;betelgeuse;;4 lightyears;distance,size,sparkle;wobble;Betelgeuse moves in.\n'
             ';;;;;;;\n'
             'landscape;Plutonium Star;;far;;;It keeps coming.\n'
             ';;;;;;\n'
             'helmet;saturn;;1000 km;depth,PRESSURE=10 bar,clock:1 hour = 7 years;;Down we go.\n')

    def test_messy_csv_repaired(self):
        steps, notes = read_steps(self.MESSY)
        self.assertEqual(len(steps), 3)
        a, b, c = steps
        self.assertEqual((a.look, a.object, a.camera), ('landscape', 'betelgeuse', 'drift'))
        self.assertEqual(a.readouts, ['distance', 'size'])
        self.assertEqual(b.object_kind, 'star_generic')
        self.assertEqual(b.distance_m, a.distance_m)
        self.assertEqual(c.typed, {'PRESSURE': '10 bar'})
        self.assertAlmostEqual(c.clock[1] / c.clock[0], 61362, delta=1)
        joined = ' '.join(notes)
        for bit in ('extra', 'landscap', 'sparkle', 'wobble', 'Plutonium Star', "'far'"):
            self.assertIn(bit, joined)

    def test_garbage_never_raises(self):
        for text in ('', '﻿', 'a,b\n"unclosed', '\x00\x01', 'narration\n\n'):
            spec, rep = preflight.dry_run(text, [], 30.0)
            self.assertIsInstance(rep['problems'], list)

    def test_no_voiceover_words_spreads_steps(self):
        text = (SAMPLES / 'ton618_distance.csv').read_text()
        spec, rep = preflight.dry_run(text, [], 120.0)
        self.assertEqual(rep['problems'], [])
        starts = [s['start'] for s in spec['shots']]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(any(x['type'] == 'sk_subtitle' for x in spec['layers']))

    def test_long_sentence_splits_at_comma_no_lone_word(self):
        _, _, spec, _ = run('sun_every_planet.csv')
        subs = [x['text'] for x in spec['layers'] if x['type'] == 'sk_subtitle']
        self.assertIn('And from Neptune it is the brightest star in a black sky,', subs)
        self.assertTrue(all(len(s.split()) >= 3 for s in subs), subs)

    def test_static_same_sky_is_a_still_screen(self):
        text = ('look,object,distance,camera,narration\n'
                'landscape,sun,1 AU,static,The Sun at noon.\n'
                'landscape,sun,1 AU,static,Still the Sun at noon.\n')
        spec, rep = preflight.dry_run(text, [], 30.0)
        self.assertTrue(any('still screen' in p for p in rep['problems']))


if __name__ == '__main__':
    unittest.main()


class LakeLook(unittest.TestCase):
    def test_lake_csv_plans_one_held_lake_scene_with_cards(self):
        _, _, spec, _ = run('ton618_lake.csv')
        self.assertEqual({s['look'] for s in spec['shots']}, {'lake'})
        self.assertEqual({s['scene'] for s in spec['shots']}, {'scene1'})
        self.assertEqual(len([x for x in spec['layers'] if x['type'] == 'sk_rungcard']), 6)

    def test_silhouette_alias_reads_as_lake(self):
        from skysim import steps as stp
        self.assertEqual(stp.LOOK_ALIASES['silhouette'], 'lake')


class Ridges(unittest.TestCase):
    def test_profile_sees_a_wall_ahead_and_layers_nest(self):
        import numpy as np
        from skysim import ridges
        h = np.zeros((400, 400), dtype=np.float32)
        h[:60, :] = 600.0                                   # a 600 m wall from 2.8 km north of the camera (10 m a pixel)
        d = ridges.profile(h, 10.0, (200, 400 - 60), 0.0)
        far, mid, near = (L['deg'] for L in d['layers'])
        ahead = d['az_deg'].index(0.0)
        self.assertAlmostEqual(far[ahead], math.degrees(math.atan2(598, 2810)), delta=0.3)
        self.assertEqual(near[ahead], 0.0)                  # nothing within 1.1 km
        self.assertTrue(all(f >= m >= n for f, m, n in zip(far, mid, near)))

    def test_lake_level_finds_an_inland_lake(self):
        import numpy as np
        from skysim.tools.fetch_terrain import lake_level
        y, x = np.mgrid[0:200, 0:200]
        h = (300 + 2.0 * np.hypot(x - 100, y - 100)).astype(np.float32)
        h[80:120, 60:140] = 191.0
        self.assertEqual(lake_level(h, 10.0), 191.0)

    def test_no_real_place_means_engine_ridges(self):
        from skysim import ridges
        from skysim.tools import fetch_terrain
        with mock.patch.object(fetch_terrain, 'ensure', return_value=None):
            self.assertIsNone(ridges.load('lake', log=lambda *a: None))
