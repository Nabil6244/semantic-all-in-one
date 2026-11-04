import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSet, RECIPES } from '../lib/props.mjs';
import { landmarkFor, landmarkFromText, LANDMARKS } from '../lib/landmarks.mjs';
import { shotFrames, chooseShot } from '../lib/director.mjs';
import { POSES, figure } from '../lib/figures.mjs';

const ground = () => ({ y: 0, water: 0, forest: false, color: [80, 130, 60] });

test('indoor rooms exist as sites and fill with people, modern and ancient', () => {
  for (const r of ['hall', 'office']) {
    assert.ok(RECIPES.includes(r));
    for (const era of [undefined, 'ancient']) assert.ok(buildSet(r, 4, 240, { ground, era }).boxes.length > 250, `${r} ${era}`);
  }
  assert.ok(POSES.includes('sitting'));
  assert.ok(figure('civilian', { faction: 'senator', pose: 'sitting' }).length >= 6);
});

test('every landmark builds and becomes the set focus', () => {
  for (const l of LANDMARKS) {
    const s = buildSet('city', 2, 240, { ground, landmark: l });
    assert.equal(s.landmark, l);
    assert.ok(s.boxes.length > 1000, l);
  }
});

test('landmarks come from the CSV or the words, never onto a battlefield or into a room', () => {
  const b = (site, place, text = '') => ({ rung: 'ground', site, place, sentences: [text] });
  assert.equal(landmarkFromText('Mehmed rides into the Hagia Sophia.'), 'domed');
  assert.equal(landmarkFor(b('city', 'The Colosseum opens')), 'colosseum');
  assert.equal(landmarkFor(b('battle', 'Spartacus', 'gladiators revolt')), null);
  assert.equal(landmarkFor(b('hall', 'The Senate', 'the senate meets')), null);
  assert.equal(landmarkFor(b('battle', 'Siege'), { landmark: 'castle' }), 'castle');
  assert.equal(landmarkFor(b('city', 'The Colosseum'), { landmark: 'none' }), null);
  assert.equal(landmarkFor({ rung: 'map', place: 'Colosseum', sentences: [] }), null);
});

test('rooms and landmarks are filmed close and slow: an orbit, a low camera for rooms', () => {
  const room = { id: 'r', rung: 'ground', site: 'office', lon: 0, lat: 0, sentences: ['x'] };
  assert.equal(chooseShot({ beats: [room] }, 0, null), 'orbit');
  assert.ok(shotFrames(room, 'orbit', 1).start.alt <= 0.09);
  const lm = { id: 'l', rung: 'ground', site: 'city', landmark: 'colosseum', lon: 0, lat: 0, sentences: ['x'] };
  assert.equal(chooseShot({ beats: [lm] }, 0, null), 'orbit');
});

import { travelSeconds, flyAt, HOP_PEAK } from '../lib/camera3d.mjs';
test('a move between two scenes on one spot rises above the dioramas and comes back', () => {
  const a = { lon: 12.49, lat: 41.89, alt: 0.08, heading: 10, tilt: 50 }, b = { lon: 12.49, lat: 41.89, alt: 0.06, heading: 100, tilt: 50 };
  const mid = flyAt(a, b, 0.5);
  assert.ok(mid.alt >= 3, `peak ${mid.alt} km`);
  assert.ok(HOP_PEAK > 3);
  assert.ok(travelSeconds(a, b) >= 3, `${travelSeconds(a, b)} s`);
  assert.ok(flyAt(a, b, 0).alt < 0.1 && flyAt(a, b, 1).alt < 0.1);
});
