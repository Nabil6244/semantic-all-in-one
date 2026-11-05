import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSet, sidesFromText, isAncient } from '../lib/props.mjs';
import { figure, ANCIENT_FACTIONS } from '../lib/figures.mjs';
import { buildTimeline, GLOBE_HOLD } from '../lib/timeline.mjs';
import { parseStory } from '../lib/beats_csv.mjs';

const ground = () => ({ y: 0, water: 0, forest: false, color: [80, 130, 60] });
const isRifle = (p) => p.c[0] === 40 && p.c[1] === 36 && p.c[2] === 32;

test('ancient soldiers carry a spear and shield, never a rifle', () => {
  for (const f of ANCIENT_FACTIONS) for (const pose of ['standing', 'aiming', 'kneeling']) {
    const parts = figure('soldier', { faction: f, pose });
    assert.ok(!parts.some(isRifle), `${f}/${pose} has a rifle`);
    assert.ok(parts.some((p) => p.sy >= 2.5 || p.sx >= 2.5), `${f}/${pose} has no spear`);
  }
});

test('a battle before firearms has armies, no tanks or guns; a modern battle is unchanged', () => {
  const ctx = { ground, era: 'ancient', factions: ['civilian'], sides: ['roman', 'carthaginian'] };
  assert.ok(isAncient(ctx));
  const a = buildSet('battle', 11, 240, ctx), m = buildSet('battle', 11, 240, { ground });
  const tankGrey = (b) => b.c && b.c[0] === 30 && b.c[1] === 30 && b.c[2] === 32;   // tyre and track rubber (C.rubber)
  assert.ok(a.boxes.length > 4000, `ancient battle has ${a.boxes.length} boxes`);
  assert.equal(a.boxes.filter(tankGrey).length, 0, 'no rubber tracks or tyres before firearms');
  assert.ok(m.boxes.some(tankGrey), 'the modern battle keeps its vehicles');
});

test('every recipe builds in the ancient era', () => {
  for (const r of ['village', 'city', 'airfield', 'lz', 'battle', 'fortress', 'beach_landing', 'jungle', 'trail', 'delta']) {
    const s = buildSet(r, 3, 240, { ground, era: 'ancient' });
    assert.ok(s.boxes.length > 100, r);
  }
});

test('the two sides follow the narration', () => {
  assert.deepEqual(sidesFromText('Then came 216 BC, the Battle of Cannae.'), ['roman', 'carthaginian']);
  assert.deepEqual(sidesFromText('Mehmed takes Constantinople in 1453.'), ['byzantine', 'ottoman']);
  assert.equal(sidesFromText('The Senate meets.'), null);
});

test('a long opening globe read leaves the globe after GLOBE_HOLD seconds', () => {
  const csv = 'row,id,date,place,lon,lat,rung,alt,heading,site,gap,text,extra\nplan,T,,,,,,,,,,,"{""world"":""x""}"\nchapter,c,,,,,,,,,,One,\n'
    + 'beat,b1,-0753-04,Rome,12.5,41.9,globe,,,,,"One two three four five six. Seven eight nine ten eleven. Twelve thirteen fourteen fifteen.",\n'
    + 'beat,b2,-0753-04,Tiber,12.5,41.9,map,,,,,"The river.",\n';
  const spec = parseStory(csv);
  const vo = [{ start: 0, end: 4, text: 'One two three four five six.' }, { start: 4.3, end: 8, text: 'Seven eight nine ten eleven.' },
    { start: 8.3, end: 11, text: 'Twelve thirteen fourteen fifteen.' }, { start: 11.6, end: 13, text: 'The river.' }];
  const tl = buildTimeline(spec, vo);
  assert.ok(tl.beats[1].travelT0 <= GLOBE_HOLD + 0.01, `descent starts at ${tl.beats[1].travelT0}`);
  for (let k = 1; k < tl.camera.length; k++) assert.ok(tl.camera[k].t0 >= tl.camera[k - 1].t0 - 1e-6, 'camera segments in order');
});

import { direct, MAX_SHOT } from '../lib/director.mjs';
test('a long hold keeps moving: no framing lasts past MAX_SHOT and every part starts where the last ended', () => {
  const spec = { beats: [{ id: 'm', rung: 'map', lon: 12.5, lat: 41.9, sentences: ['x'], chapter: 'c', seed: 3 }] };
  const { camera } = direct(spec, [{ i: 0, travelT0: 0, travelT1: 0, speakT0: 0, speakT1: 60, holdT1: 60 }], 62);
  const moves = camera.filter((c) => c.type === 'move');
  assert.ok(moves.length >= 6);
  for (const m of moves) assert.ok(m.t1 - m.t0 <= MAX_SHOT + 1e-6);
  for (let k = 1; k < moves.length; k++) assert.deepEqual(moves[k].from, moves[k - 1].to);
});

test('a minute on one map place is a one-way dive: lower every part, new heading, no framing shown twice', () => {
  const spec = { beats: [{ id: 'm', rung: 'map', lon: 12.5, lat: 41.9, sentences: ['x'], chapter: 'c', seed: 3 }] };
  const { camera } = direct(spec, [{ i: 0, travelT0: 0, travelT1: 0, speakT0: 0, speakT1: 60, holdT1: 60 }], 62);
  const moves = camera.filter((c) => c.type === 'move');
  for (let k = 1; k < moves.length; k++) {
    assert.ok(moves[k].to.alt < moves[k - 1].to.alt, `part ${k} is lower than the one before`);
    assert.notEqual(moves[k].to.heading, moves[k - 1].to.heading);
    assert.equal(moves[k].ease, 'linear', 'steady speed through the junction');
  }
  const keys = moves.map((m) => [m.to.alt.toFixed(1), m.to.heading.toFixed(0)].join('/'));
  assert.equal(new Set(keys).size, keys.length);
  assert.ok(moves.at(-1).to.alt <= 430 && moves.at(-1).to.alt >= 400, 'ends close over the place');
});
