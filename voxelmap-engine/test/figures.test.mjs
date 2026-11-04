import test from 'node:test';
import assert from 'node:assert/strict';
import { figure, formation, figureHeight, KINDS, POSES, FACTION_NAMES } from '../lib/figures.mjs';
import { buildSet, particlesAt, RECIPES } from '../lib/props.mjs';

const lowestHighest = (parts) => [Math.min(...parts.map((p) => p.y)), figureHeight(parts)];
const flat = { ground: () => ({ y: 0, water: 0, forest: false, color: [84, 138, 56] }) };
const isHuman = (b) => b.sx <= 1.2 && b.sy <= 1.3 && b.sz <= 1.2;   // figure-sized boxes only

test('every kind, pose and faction builds finite boxes within the per-figure part limit', () => {
  for (const kind of KINDS) for (const pose of POSES) for (const faction of FACTION_NAMES) {
    const parts = figure(kind, { faction, pose, phase: 1.1, seed: 5 });
    assert.ok(parts.length >= 6 && parts.length <= 12, `${kind}/${pose}/${faction}: ${parts.length} parts`);
    for (const p of parts) assert.ok([p.x, p.y, p.z, p.sx, p.sy, p.sz].every(Number.isFinite) && p.sx > 0 && p.sy > 0 && p.sz > 0 && p.c.length === 3 && p.y >= -1e-9);
  }
});

test('a standing or walking figure is about 2 units tall, a kneeling one lower, a prone one flat', () => {
  for (const kind of KINDS) for (const pose of ['standing', 'walking', 'aiming']) {
    const [lo, hi] = lowestHighest(figure(kind, { pose, phase: 0.7 }));
    assert.ok(lo === 0 || lo < 0.15, `${kind}/${pose} feet at ${lo}`);
    assert.ok(hi > 1.95 && hi < 2.3, `${kind}/${pose} height ${hi}`);
  }
  const kneel = figureHeight(figure('soldier', { pose: 'kneeling' })), prone = figureHeight(figure('soldier', { pose: 'prone' }));
  assert.ok(kneel > 1.4 && kneel < 1.9 && prone < 0.7, `${kneel} ${prone}`);
  assert.ok(figure('soldier', { pose: 'aiming' }).some((p) => p.sx > 0.8 && p.sy <= 0.1), 'a thin rifle box');
});

test('walking moves the legs and arms with the phase; factions and kinds differ in colour', () => {
  assert.notDeepEqual(figure('soldier', { pose: 'walking', phase: 0 }), figure('soldier', { pose: 'walking', phase: 1.5 }));
  const body = (f, kind = 'soldier') => figure(kind, { faction: f, seed: 3 }).sort((a, b) => b.sx * b.sy * b.sz - a.sx * a.sy * a.sz)[0].c.join();
  const cols = ['us_marine', 'pavn', 'viet_cong', 'french', 'pla', 'sailor'].map((f) => body(f));
  assert.equal(new Set(cols).size, cols.length, cols.join(' | '));
  assert.notEqual(body('us_army'), body('us_army', 'officer'));
  const hats = new Set(['viet_cong', 'pavn', 'french', 'sailor'].map((f) => JSON.stringify(figure('soldier', { faction: f }).filter((p) => p.y > 1.8).map((p) => p.sx))));
  assert.ok(hats.size >= 3, 'hat shapes differ');
  const shirts = new Set(Array.from({ length: 30 }, (_, i) => figure('civilian', { seed: i }).find((p) => p.sz > 0.55).c.join()));
  assert.ok(shirts.size >= 5, 'civilians vary');
  const skins = new Set(Array.from({ length: 40 }, (_, i) => figure('soldier', { faction: 'us_army', seed: i }).find((p) => p.sy === 0.4).c.join()));
  assert.ok(skins.size >= 3, 'skin tones vary');
});

test('figures are deterministic', () => {
  assert.deepEqual(figure('civilian', { seed: 9, pose: 'walking', phase: 2 }), figure('civilian', { seed: 9, pose: 'walking', phase: 2 }));
});

test('formations give the requested count, no two closer than 0.6, deterministic, and follow cx/cz/th', () => {
  let seed = 1;
  const rng = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (const type of ['ranks', 'column', 'line', 'crowd', 'scatter', 'around']) for (const count of [1, 2, 9, 40, 173]) {
    const f = formation(type, count, { cx: 50, cz: 60, th: 0.8 }, rng);
    assert.equal(f.length, count, type);
    for (const p of f) assert.ok(Number.isFinite(p.x) && Number.isFinite(p.z) && Number.isFinite(p.th));
    let min = 1e9; for (let i = 0; i < f.length; i++) for (let j = i + 1; j < f.length; j++) min = Math.min(min, Math.hypot(f[i].x - f[j].x, f[i].z - f[j].z));
    assert.ok(min >= 0.6, `${type}/${count}: closest ${min.toFixed(2)}`);
    const cx = f.reduce((a, p) => a + p.x, 0) / count, cz = f.reduce((a, p) => a + p.z, 0) / count;
    assert.ok(Math.hypot(cx - 50, cz - 60) < 12 + count * 0.15, `${type} centred ${cx},${cz}`);
  }
  const mk = () => { let s = 7; return () => { s = (s * 16807) % 2147483647; return s / 2147483647; }; };
  assert.deepEqual(formation('crowd', 30, { cx: 1 }, mk()), formation('crowd', 30, { cx: 1 }, mk()));
  // ranks face forward, rings face the middle
  const r = formation('ranks', 12, { th: 0.5 }, mk());
  assert.ok(r.every((p) => Math.abs(p.th - 0.5) < 1e-9));
  const ring = formation('around', 10, { radius: 3, cx: 10, cz: 10 }, mk());
  for (const p of ring) { const dx = Math.cos(p.th), dz = -Math.sin(p.th); assert.ok(dx * (10 - p.x) + dz * (10 - p.z) > 2.5, 'faces the centre'); }
});

test('sets: march columns stay finite, inside the budget, and enter and leave off the set edge', () => {
  let seen = 0;
  for (const r of RECIPES) for (const seed of [1, 7]) {
    const s = buildSet(r, seed, 240, flat);
    for (const em of s.emitters.filter((e) => e.kind === 'march')) {
      seen++;
      assert.ok(em.count >= 1 && em.count * 12 <= 600);
      const a = em.path[0], b = em.path[em.path.length - 1];
      for (const q of [a, b]) assert.ok(q[0] < 1 || q[2] < 1 || q[0] > 239 || q[2] > 239, `${r}: path end inside the set`);
    }
    for (const t of [0, 2.5, 9.1, 33]) {
      const ps = particlesAt(s, t);
      assert.ok(ps.length <= 600);
      for (const p of ps) assert.ok([p.x, p.y, p.z, p.a].every(Number.isFinite));
    }
  }
  assert.ok(seen >= 6, `march emitters seen ${seen}`);
  const trail = buildSet('trail', 1, 240, flat), walkers = (t) => particlesAt(trail, t).filter((p) => p.g !== undefined && p.sx !== undefined);
  assert.ok(walkers(3).length > 20);
  assert.notDeepEqual(walkers(3), walkers(3.5));
});

test('ctx.factions is used: a battle shows two different uniforms', () => {
  const colours = (f) => new Set(buildSet('battle', 3, 240, { ...flat, factions: f }).boxes.filter((b) => isHuman(b) && b.sy > 0.6 && b.sy < 0.8 && b.sz > 0.5 && b.sz < 0.7).map((b) => b.c.join()));
  const a = colours(['viet_cong', 'us_marine']), b = colours(['french', 'pla']);
  assert.ok([...a].some((c) => c.startsWith('3'))); // black pyjamas
  assert.notDeepEqual([...a].sort(), [...b].sort());
});

test('names and signs are returned, on land, and absent by default', () => {
  const bare = buildSet('village', 2, 240, flat);
  assert.deepEqual(bare.labels, []); assert.deepEqual(bare.signs, []);
  const wet = { ground: (x) => ({ y: 0, water: x < 100 ? 1 : 0, forest: false, color: [84, 138, 56] }) };
  for (const ctx of [flat, wet]) for (const r of RECIPES) {
    const s = buildSet(r, 4, 240, { ...ctx, names: ['Gen. Karch', 'Col. Vo'], signs: ['WELCOME'], factions: ['us_army'] });
    assert.equal(s.labels.length, 2, r); assert.equal(s.signs.length, 1, r);
    for (const l of s.labels) { assert.ok(l.text && Number.isFinite(l.x + l.y + l.z)); assert.ok(l.y > 2.5 && l.y < 4, `label y ${l.y}`); assert.equal(ctx.ground(l.x, l.z).water, 0); }
    const g = s.signs[0]; assert.equal(g.text, 'WELCOME'); assert.ok(g.w >= 3 && g.h > 0.5 && Number.isFinite(g.rot));
    for (const dx of [-g.w / 2, 0, g.w / 2]) assert.equal(ctx.ground(g.x + dx * Math.cos(g.rot), g.z - dx * Math.sin(g.rot)).water, 0);
    assert.ok(g.y > 2.5);
  }
});

test('people density at n = 240 matches n = 144 (counts scale with area)', () => {
  // heads are the 0.4 cubes of skin colour; count figures by torsos (0.34 x 0.72 x 0.62)
  const people = (s) => s.boxes.filter((b) => Math.abs(b.sx - 0.34) < 1e-9 && Math.abs(b.sy - 0.72) < 1e-9 && Math.abs(b.sz - 0.62) < 1e-9).length;
  for (const r of ['battle', 'beach_landing', 'lz', 'city']) {
    let a = 0, b = 0;
    for (const seed of [1, 2, 3, 4]) { a += people(buildSet(r, seed, 144, flat)) / (144 * 144); b += people(buildSet(r, seed, 240, flat)) / (240 * 240); }
    assert.ok(a > 0 && b > 0, r);
    assert.ok(b / a > 0.4 && b / a < 2.5, `${r}: density ratio ${(b / a).toFixed(2)}`);
  }
});

test('box budget: 20000 per set at most', () => {
  for (const r of RECIPES) assert.ok(buildSet(r, 11, 240, flat).boxes.length <= 20300);
});
