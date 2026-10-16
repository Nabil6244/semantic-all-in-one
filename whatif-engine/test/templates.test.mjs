import test from 'node:test';
import assert from 'node:assert/strict';
import { loadLibrary, validate } from '../lib/library.mjs';
import { build, seconds, calc, fill, param, keyedAt } from '../lib/tpl.mjs';
import { PRIMS, PRIM_NAMES } from '../lib/prims.mjs';
import { ICONS, ICON_NAMES, drawIcon } from '../lib/icons.mjs';
import tmTemplate from '../layers/tm_template.mjs';
import tmMission, { valueAt } from '../layers/tm_mission.mjs';

// A 2D context that accepts every call and fails on a NaN/Infinity argument (a broken formula in a template shows up here).
function mockCanvas(W = 1280, H = 720) {
  const bad = [];
  const grad = { addColorStop() {} };
  const target = { canvas: { width: W, height: H }, globalAlpha: 1, lineWidth: 1, measureText: (s) => ({ width: String(s).length * 12 }), createRadialGradient: () => grad, createLinearGradient: () => grad,
    createPattern: () => ({}), getLineDash: () => [] };
  const g = new Proxy(target, {
    get(o, k) {
      if (k in o) return o[k];
      return (...args) => { for (const a of args) if (typeof a === 'number' && !Number.isFinite(a)) bad.push(`${String(k)}(${args.join(', ')})`); };
    },
    set(o, k, v) { if (typeof v === 'number' && !Number.isFinite(v)) bad.push(`${String(k)} = ${v}`); o[k] = v; return true; },
  });
  return { g, bad };
}

const LIB = loadLibrary();

test('the library has the V4 visuals and the suggested ones (70+), each valid', () => {
  assert.ok(LIB.size >= 70, `only ${LIB.size} templates`);
  for (const id of ['target_section', 'photon_orbit', 'light_bends', 'star_lensing', 'orbit_trail', 'squeeze_object', 'eht_pair', 'warp_well', 'two_clocks_ratio', 'pov_split',
    'river_walkway', 'rules_change', 'spacetime_axes', 'tidal_stretch', 'singularity_equation', 'hawking_glow', 'info_letter', 'deep_time_axis', 'stage_header', 'end_question'])
    assert.ok(LIB.has(id), `missing ${id}`);
  const problems = [...LIB.values()].flatMap(validate);
  assert.deepEqual(problems, []);
});

test('every template draws every frame without a broken number (defaults, 6 moments)', async () => {
  for (const t of LIB.values()) {
    const len = t.hold ?? 6;
    const inst = await tmTemplate.create({ template: t, slots: {}, start: 10, end: 10 + len }, {});
    const { g, bad } = mockCanvas();
    for (const k of [0, 0.1, 0.3, 0.5, 0.8, 1]) tmTemplate.draw(inst, { g, W: 1280, H: 720, t: 10 + len * k, alpha: 1 });
    assert.deepEqual(bad.slice(0, 3), [], `${t.id} drew a broken number`);
  }
});

test('slots, arithmetic, times and cues', () => {
  assert.equal(fill('{a} AND {b}', { a: 'X', b: 2 }), 'X AND 2');
  assert.deepEqual(fill('{list}', { list: [1, 2] }), [1, 2]);
  assert.equal(fill('{missing}', {}), '{missing}');
  assert.equal(calc('=0.5+0.0422*4'), 0.5 + 0.0422 * 4);
  assert.equal(calc('=max(1,2)*cos(0)'), 2);
  assert.throws(() => calc('=alert(1)'), /unknown name/);
  assert.throws(() => calc('=1;process.exit()'), /unknown name|not a formula/);
  assert.equal(seconds('50%', 8), 4);
  assert.equal(seconds('end-1.5', 8), 6.5);
  assert.equal(seconds('@photon+0.5', 8, { photon: 2 }), 2.5);
  assert.equal(seconds('@nobody', 8, {}, 3), 3);
});

test('a CSV value reaches the drawing: the ratio banner counts to the given number', () => {
  const t = LIB.get('two_clocks_ratio');
  const items = build(t, { ratio_to: 100, ratio_from: 2 }, { len: 8, cues: { ratio: 1 } });
  const banner = items.find((x) => x.p === 'text' && String(x.text).includes('#'));
  assert.equal(param(banner, 'value', 0, null), 2);
  assert.equal(param(banner, 'value', 7, null), 100);
  assert.match(banner.text, /1 HOUR FOR YOU = # HOURS ON EARTH/);
});

test('each repeats an item per list element with stagger', () => {
  const t = { id: 'x', items: [{ p: 'text', each: 'rows', text: '{it}', at: [0.1, '=0.2+0.1*{i}'], in: 1, stagger: 0.5 }], slots: { rows: { default: ['A', 'B', 'C'] } } };
  const items = build(t, {}, { len: 6 });
  assert.deepEqual(items.map((x) => x.text), ['A', 'B', 'C']);
  assert.deepEqual(items.map((x) => x._in), [1, 1.5, 2]);
  assert.ok(Math.abs(items[2].at[1] - 0.4) < 1e-9);
});

test('colours and positions animate', () => {
  assert.equal(keyedAt({ keys: [[0, '#000000'], [1, '#ffffff']], ease: 'linear' }, 0.5), '#808080');
  assert.deepEqual(keyedAt({ keys: [[0, [0, 0]], [2, [1, 1]]], ease: 'linear' }, 1), [0.5, 0.5]);
});

test('every primitive and icon is drawable', () => {
  const { g, bad } = mockCanvas();
  for (const n of ICON_NAMES) drawIcon(g, n, 100, 100, 50, { level: 0.5, burn: 0.3 });
  assert.equal(Object.keys(ICONS).length, ICON_NAMES.length);
  assert.ok(PRIM_NAMES.length >= 24);
  assert.ok(PRIMS.arrow && PRIMS.blackhole && PRIMS.grid && PRIMS.equation);
  assert.deepEqual(bad, []);
});

test('mission card: the number counts between beats of the same unit and switches on a new unit', () => {
  const keys = [{ t: 0, value: 208, unit: 'MILLION KM' }, { t: 10, value: 6.3, unit: 'MILLION KM' }, { t: 20, value: 2215, unit: 'KM' }];
  assert.equal(valueAt(keys, 5).v, 208);
  const mid = valueAt(keys, 10.5).v;
  assert.ok(mid < 208 && mid > 6.3, `counting: ${mid}`);
  assert.ok(Math.abs(valueAt(keys, 15).v - 6.3) < 1e-6);
  assert.equal(valueAt(keys, 20.1).v, 2215);
  assert.throws(() => tmMission.create({}), /keys/);
  const inst = tmMission.create({ keys, stages: ['A', 'B', 'C'], start: 0, end: 30 });
  const { g, bad } = mockCanvas();
  for (const t of [0, 5, 10.4, 21]) tmMission.draw(inst, { g, W: 1280, H: 720, t, alpha: 1 });
  assert.deepEqual(bad, []);
});
