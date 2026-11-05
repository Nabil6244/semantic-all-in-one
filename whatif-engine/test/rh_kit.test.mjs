// Rules Horror drawing kit: every layer draws at every moment without a broken number, poses rest on the ground, cycles move,
// the rule card types on and wraps inside the frame. Run: node --test test/rh_kit.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { mockCanvas } from '../lib/mockcanvas.mjs';
import { createRegistry, runLayers } from '../lib/layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';
import { POSE_NAMES, SET_NAMES, poseAt, skeleton, setGround, wrapText, typedCount, glitchOn } from '../lib/rhkit.mjs';

const reg = registerBuiltins(createRegistry());
const make = (defs) => reg.instantiate(defs, { spec: {}, W: 1280, H: 720, loadImage: async () => null, warn() {} }, { lenient: false, warn() {} });
const TIMES = [0, 0.3, 1, 2.5, 4, 9];

test('every set and every pose draws at every moment without a broken number', async () => {
  const defs = [...SET_NAMES.map((s) => ({ type: 'rh_set', set: s, start: 0, end: 10, cam: { push: 0.06 } })),
    ...POSE_NAMES.map((p, i) => ({ type: 'rh_figure', pose: p, x: 0.2 + 0.1 * i, start: 0, end: 10, tag: 'you', eyes: 'red', walk_to: 0.8, moves: [{ at: 2, pose: 'flinch' }] })),
    { type: 'rh_mark', kind: 'tag', text: 'prey', x: 0.3, y: 0.2, start: 0, end: 10 }, { type: 'rh_mark', kind: 'sight', from: [0.6, 0.5], to: [0.3, 0.5], start: 0, end: 10 },
    { type: 'rh_mark', kind: 'ring', x: 0.8, y: 0.2, seconds: 3, start: 0, end: 10 }, { type: 'rh_mark', kind: 'cross', x: 0.5, y: 0.5, start: 0, end: 10 },
    { type: 'rh_rulecard', number: 3, text: 'Do not turn on the lights. Not even for a second.', start: 0, end: 10 },
    { type: 'rh_caption', text: 'and see a deer standing in your yard', start: 0, end: 10 }, { type: 'rh_glitch', start: 0, end: 10 }];
  const layers = await make(defs);
  for (const t of TIMES) {
    const { g, bad } = mockCanvas(1280, 720);
    runLayers(layers, { t, W: 1280, H: 720, g, spec: {}, claims: [] }, 'draw');
    assert.deepEqual(bad, [], `t=${t}`);
  }
});

test('an unknown mark kind is refused with a clear message; an unknown set or pose falls back instead of stopping', async () => {
  await assert.rejects(() => make([{ type: 'rh_mark', kind: 'blob' }]), /kind must be one of/);
  const layers = await make([{ type: 'rh_set', set: 'nowhere' }, { type: 'rh_figure', pose: 'moonwalk' }]);
  const { g, bad } = mockCanvas(1280, 720);
  runLayers(layers, { t: 1, W: 1280, H: 720, g, spec: {}, claims: [] }, 'draw');
  assert.deepEqual(bad, []);
});

test('every pose rests on the ground line, left or right, and stays inside the frame', () => {
  for (const name of POSE_NAMES) for (const facing of [1, -1]) for (const t of [0, 0.4, 0.9]) {
    const J = skeleton(poseAt({ pose: name }, t), 640, 540, 250, facing);
    const pts = [J.hip, J.sh, J.head, ...J.aL, ...J.aR, ...J.lL, ...J.lR];
    const low = Math.max(...pts.map((p) => p[1]), J.head[1] + J.r);
    assert.ok(Math.abs(low - 540) < 0.01, `${name} ${facing} t=${t} rests at ${low}`);
    for (const p of pts) assert.ok(p[0] > 100 && p[0] < 1180 && p[1] > 0, `${name} point outside the frame`);
  }
});

test('walk and run move the legs over time; a held pose still breathes', () => {
  for (const n of ['walk', 'run']) {
    const a = poseAt({ pose: n }, 0), b = poseAt({ pose: n }, 0.2);
    assert.notEqual(a.lL[0], b.lL[0], `${n} legs move`);
  }
  assert.notEqual(poseAt({ pose: 'stand' }, 0).neck, poseAt({ pose: 'stand' }, 1).neck);
});

test('a scripted pose change blends instead of jumping', () => {
  const def = { pose: 'stand', moves: [{ at: 2, pose: 'flinch' }] };
  const before = poseAt(def, 1.99).lean, mid = poseAt(def, 2.15).lean, after = poseAt(def, 2.6).lean;
  assert.ok(Math.abs(before) < 3 && mid < before && mid > after && after < -12, `${before} ${mid} ${after}`);
});

test('the sleeping figure lies down on the ground', () => {
  const J = skeleton(poseAt({ pose: 'sleep' }, 0), 640, 540, 250, 1);
  assert.ok(Math.abs(J.head[1] - J.lL[2][1]) < 120, 'head and feet at nearly the same height');
  assert.ok(Math.abs(J.head[0] - J.lL[2][0]) > 150, 'stretched out sideways');
});

test('the rule card types on and its lines fit inside the frame', () => {
  assert.equal(typedCount(0), 0);
  assert.ok(typedCount(2) > typedCount(1) && typedCount(1) > typedCount(0.5));
  const g = { measureText: (s) => ({ width: String(s).length * 20 }) };
  const lines = wrapText(g, 'Do not turn on the lights. Not even for a second. Whatever you hear, stay in bed.', 600);
  assert.ok(lines.length >= 3);
  for (const l of lines) assert.ok(l.length * 20 <= 600 || !l.includes(' '), `line too wide: ${l}`);
});

test('glitch bursts switch on and off at their moments; the ground of a set is a fraction of the frame', () => {
  const d = { bursts: [{ at: 5, dur: 0.2 }] };
  assert.equal(glitchOn(d, 4.9), 0); assert.equal(glitchOn(d, 5.1), 1); assert.equal(glitchOn(d, 5.3), 0);
  for (const s of SET_NAMES) assert.ok(setGround(s) > 0.5 && setGround(s) < 0.95);
});

test('animals, props, the crowd, bubbles and the zoomed camera draw at every moment without a broken number', async () => {
  const { PROP_KINDS, ANIMAL_NAMES, ANIMAL_POSES } = await import('../lib/rhart.mjs');
  const defs = [...ANIMAL_NAMES.flatMap((a) => ANIMAL_POSES.map((p) => ({ type: 'rh_animal', animal: a, pose: p, x: 0.6, start: 0, end: 10, cam: { focus: [0.6, 0.5], zoom: 1.6 } }))),
    ...PROP_KINDS.map((k) => ({ type: 'rh_prop', kind: k, start: 0, end: 10 })),
    ...['classroom', 'cinema'].map((k) => ({ type: 'rh_crowd', kind: k, mark: [1, 3], label: 'NORMAL', eyes_red: true, turn: 2, start: 0, end: 10 })),
    { type: 'rh_mark', kind: 'bubble', text: 'COME HERE.', x: 0.3, y: 0.3, to: [0.32, 0.45], start: 0, end: 10 }, { type: 'rh_mark', kind: 'banner', text: 'do not pet it', x: 0.5, y: 0.2, start: 0, end: 10 },
    { type: 'rh_figure', pose: 'stand', hollow: true, eyes: 'red', stare: true, start: 0, end: 10 },
    { type: 'rh_figure', pose: 'stand', look: 'grin', start: 0, end: 10 }, { type: 'rh_figure', pose: 'walk', look: 'mannequin', start: 0, end: 10 }];
  const layers = await make(defs);
  for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: {}, claims: [] }, 'draw'); assert.deepEqual(bad, [], `t=${t}`); }
  await assert.rejects(() => make([{ type: 'rh_prop', kind: 'blob' }]), /kind must be one of/);
});

test('the colour schemes draw people, sets, the crowd and the hazard card without a broken number', async () => {
  const { SET_NAMES } = await import('../lib/rhkit.mjs');
  for (const scheme of ['dark', 'colour']) {
    const layers = await make([{ type: 'rh_bg', start: 0, end: 10 }, ...SET_NAMES.map((s) => ({ type: 'rh_set', set: s, start: 0, end: 10 })),
      ...['', 'hazmat', 'grin'].map((look, i) => ({ type: 'rh_figure', pose: 'walk', look: look || undefined, outfit: i === 2 ? 'attendant' : undefined, x: 0.2 + 0.2 * i, start: 0, end: 10 })),
      { type: 'rh_figure', pose: 'sit', outfit: 'usher', face: 'scared', start: 0, end: 10 }, { type: 'rh_crowd', kind: 'cinema', mark: [1, 3], start: 0, end: 10 },
      { type: 'rh_rulecard', number: 4, text: 'Never let it separate you from the others.', style: 'hazard', start: 0, end: 10 }]);
    for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: { rh: { scheme } }, claims: [] }, 'draw'); assert.deepEqual(bad, [], `${scheme} t=${t}`); }
  }
});

test('the mirror draws at every moment (lead, smile, press, water) in all three schemes', async () => {
  for (const scheme of ['mono', 'dark', 'colour']) {
    const layers = await make([{ type: 'rh_bg', start: 0, end: 10 }, { type: 'rh_set', set: 'bathroom', start: 0, end: 10 }, { type: 'rh_figure', pose: 'stand', x: 0.3, set: 'bathroom', start: 0, end: 10 },
      { type: 'rh_mirror', set: 'bathroom', pose: 'walk', lead: 0.5, smile_at: 2, press_at: 4, water: true, start: 0, end: 10 }, { type: 'rh_set', set: 'hall_mirror', start: 0, end: 10 }, { type: 'rh_mirror', set: 'hall_mirror', start: 0, end: 10 }, { type: 'rh_set', set: 'kitchen', start: 0, end: 10 }]);
    for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: { rh: { scheme } }, claims: [] }, 'draw'); assert.deepEqual(bad, [], `${scheme} t=${t}`); }
  }
});

test('in the story scheme each layer takes its own mood palette; mono ignores moods', async () => {
  const { palOf, PALETTES } = await import('../lib/rhkit.mjs');
  for (const m of ['night', 'warm', 'cold', 'red', 'day', 'dawn']) assert.ok(palOf({ spec: { rh: { scheme: 'story' } } }, { mood: m }) === PALETTES[m], m);
  assert.equal(palOf({ spec: { rh: { scheme: 'mono' } } }, { mood: 'red' }), null);
  assert.equal(palOf({ spec: { rh: { scheme: 'story' } } }, {}), PALETTES.night);
  assert.equal(palOf({ spec: { rh: { scheme: 'dark' } } }, { mood: 'red' }), PALETTES.dark);
  for (const mood of ['night', 'warm', 'cold', 'red', 'day', 'dawn']) {
    const layers = await make([{ type: 'rh_bg', mood, start: 0, end: 10 }, { type: 'rh_set', set: 'bathroom', mood, start: 0, end: 10 }, { type: 'rh_figure', pose: 'walk', mood, start: 0, end: 10 },
      { type: 'rh_mirror', set: 'bathroom', mood, smile_at: 1, start: 0, end: 10 }, { type: 'rh_crowd', kind: 'cinema', mood, start: 0, end: 10 }, { type: 'rh_rulecard', number: 2, text: 'Never confirm it.', mood, start: 0, end: 10 }]);
    for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: { rh: { scheme: 'story' } }, claims: [] }, 'draw'); assert.deepEqual(bad, [], `${mood} t=${t}`); }
  }
});

test('the hand, handprint, black phone, floorboards and hair part props draw at every moment in every scheme', async () => {
  for (const scheme of ['mono', 'story', 'colour']) {
    const layers = await make([{ type: 'rh_prop', kind: 'ring_hand', side: 'left', flip_at: 2, start: 0, end: 10 }, { type: 'rh_prop', kind: 'ring_hand', side: 'right', start: 0, end: 10 },
      { type: 'rh_prop', kind: 'hair_part', side: 'left', flip_at: 3, start: 0, end: 10 }, { type: 'rh_prop', kind: 'handprint', start: 0, end: 10 },
      { type: 'rh_prop', kind: 'phone_black', smile_at: 1, text: 'I am up', start: 0, end: 10 }, { type: 'rh_prop', kind: 'floorboards', count: 11, extra: true, start: 0, end: 10 }, { type: 'rh_prop', kind: 'floorboards', start: 0, end: 10 }]);
    for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: { rh: { scheme } }, claims: [] }, 'draw'); assert.deepEqual(bad, [], `${scheme} t=${t}`); }
  }
});

test('every reference rule card (black, dim, hazard, tag, paper, sign) and the underwater scheme draw without a broken number', async () => {
  for (const scheme of ['mono', 'dark', 'colour', 'deep']) {
    const cards = ['black', 'dim', 'hazard', 'tag', 'paper', 'sign'].map((style, i) => ({ type: 'rh_rulecard', number: i + 1, style, text: 'Never answer it, even if it sounds like your mother.', start: 0, end: 10 }));
    const layers = await make([{ type: 'rh_bg', start: 0, end: 10 }, { type: 'rh_set', set: 'hallway', start: 0, end: 10 }, ...cards]);
    for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: { rh: { scheme } }, claims: [] }, 'draw'); assert.deepEqual(bad, [], `${scheme} t=${t}`); }
  }
});

test('the filled rooms draw every set in every colour palette, and the white-on-black look keeps the line art', async () => {
  const { SET_NAMES } = await import('../lib/rhkit.mjs');
  const { ROOM_NAMES } = await import('../lib/rhrooms.mjs');
  assert.deepEqual([...ROOM_NAMES].sort(), [...SET_NAMES].sort());
  for (const [scheme, mood] of [['dark'], ['colour'], ['deep'], ['story', 'warm'], ['story', 'red'], ['story', 'dawn'], ['story', 'cold']]) {
    const layers = await make([{ type: 'rh_bg', mood, start: 0, end: 10 }, ...SET_NAMES.map((s) => ({ type: 'rh_set', set: s, mood, start: 0, end: 10 })),
      ...[0, 1, 2, 3, 4].map((seed) => ({ type: 'rh_figure', pose: ['stand', 'walk', 'sit', 'run', 'sleep'][seed], seed, face: ['neutral', 'grin', 'scared'][seed % 3], mood, x: 0.15 + seed * 0.17, start: 0, end: 10 }))]);
    for (const t of TIMES) { const { g, bad } = mockCanvas(1280, 720); runLayers(layers, { t, W: 1280, H: 720, g, spec: { rh: { scheme } }, claims: [] }, 'draw'); assert.deepEqual(bad, [], `${scheme}/${mood} t=${t}`); }
  }
});
