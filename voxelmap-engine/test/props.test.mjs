import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSet, particlesAt, RECIPES, FINE } from '../lib/props.mjs';

const N = 144;
// box x,z are footprint centres
const waterLeft = { ground: (x) => ({ y: 0, water: x < 72 ? 1 : 0, forest: false, color: [80, 130, 60] }) };
const steepRight = { ground: (x) => ({ y: x > 72 ? (x - 72) * 5 : 0, water: 0, forest: false, color: [80, 130, 60] }) };
const tilted = { ground: (x) => ({ y: 10 + 0.02 * x, water: 0, forest: true, color: [80, 130, 60] }) };
const NO_BOATS = ['city', 'airfield', 'lz', 'battle', 'fortress', 'jungle', 'trail'];

test('FINE and recipes', () => {
  assert.equal(FINE, 48);
  for (const r of ['village', 'city', 'airfield', 'lz', 'battle', 'fortress', 'beach_landing', 'jungle', 'trail', 'delta']) assert.ok(RECIPES.includes(r));
});

test('every recipe builds within budget, flat and on odd terrain', () => {
  for (const r of RECIPES) for (const ctx of [undefined, waterLeft, steepRight, tilted]) {
    const s = buildSet(r, 5, N, ctx);
    assert.equal(s.recipe, r);
    assert.ok(s.boxes.length >= 100 && s.boxes.length <= 20000, `${r} boxes ${s.boxes.length}`);
    for (const t of [0, 3.7, 12.3, 40]) assert.ok(particlesAt(s, t).length <= 600);
    for (const b of s.boxes) assert.ok([b.x, b.y, b.z, b.sx, b.sy, b.sz].every(Number.isFinite) && b.c.length === 3, `${r} bad box`);
  }
  assert.equal(buildSet('nope', 1).recipe, 'village');
});

test('deterministic', () => {
  for (const r of RECIPES) {
    assert.deepEqual(buildSet(r, 9), buildSet(r, 9));
    assert.deepEqual(particlesAt(buildSet(r, 9), 5.5), particlesAt(buildSet(r, 9), 5.5));
  }
});

test('seeds differ substantially, recipes differ from each other', () => {
  const key = (b) => `${Math.round(b.x)},${Math.round(b.z)}`;
  for (const r of RECIPES) {
    const a = new Set(buildSet(r, 1).boxes.map(key)), b = buildSet(r, 2).boxes.map(key);
    const same = b.filter((k) => a.has(k)).length / b.length;
    assert.ok(same < 0.6, `${r} seeds too alike (${same.toFixed(2)})`);
  }
  const counts = RECIPES.map((r) => buildSet(r, 1).boxes.length);
  assert.ok(new Set(counts).size >= RECIPES.length - 1);
});

test('ctx: nothing on water in the water half', () => {
  for (const r of NO_BOATS) {
    const s = buildSet(r, 3, N, waterLeft);
    const bad = s.boxes.filter((b) => b.x < 71);
    assert.equal(bad.length, 0, `${r}: ${bad.length} boxes on water`);
  }
  // boats live on water
  const v = buildSet('village', 3, N, waterLeft);
  assert.ok(v.boxes.some((b) => b.x < 72), 'sampans on water');
  const dry = buildSet('village', 3, N, waterLeft).boxes.filter((b) => b.x >= 72);
  assert.ok(dry.length > 50);
});

test('ctx: nothing on the steep part', () => {
  for (const r of RECIPES) {
    const s = buildSet(r, 4, N, steepRight);
    const bad = s.boxes.filter((b) => b.x > 75);
    assert.equal(bad.length, 0, `${r}: ${bad.length} boxes on steep ground`);
  }
});

test('y follows ctx.ground', () => {
  for (const r of RECIPES) {
    const s = buildSet(r, 6, N, tilted);
    for (const b of s.boxes) assert.ok(b.y > 8.5 && b.y < 10 + 0.02 * N + 14, `${r} y=${b.y}`);
    const mid = s.boxes.map((b) => b.y - (10 + 0.02 * b.x)).sort((a, b) => a - b)[Math.floor(s.boxes.length / 2)];
    assert.ok(mid > -0.5 && mid < 3, `${r} median offset ${mid}`);
  }
});

test('particles: animate, finite, shaped fields', () => {
  const battle = buildSet('battle', 3);
  assert.notDeepEqual(particlesAt(battle, 12.3), particlesAt(battle, 12.8));
  for (const r of RECIPES) {
    const s = buildSet(r, 8, N, tilted);
    for (const t of [0, 1.3, 7.9, 12.3, 55]) for (const p of particlesAt(s, t)) {
      assert.ok([p.x, p.y, p.z, p.a].every(Number.isFinite), `${r} particle`);
      if (p.sx !== undefined) assert.ok([p.sx, p.sy, p.sz, p.rot].every(Number.isFinite) && p.c.length === 3);
      else assert.ok(Number.isFinite(p.s));
    }
  }
  // lz helicopters animate (descent + rotors)
  const lz = buildSet('lz', 2);
  assert.ok(particlesAt(lz, 1).some((p) => p.sx !== undefined));
  assert.notDeepEqual(particlesAt(lz, 1), particlesAt(lz, 4));
});
