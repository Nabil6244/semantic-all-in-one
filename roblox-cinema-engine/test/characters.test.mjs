import test from 'node:test';
import assert from 'node:assert/strict';
import { makeCharacter, lookDistance, ROLES } from '../lib/characters.mjs';
import { poseAt, poseDelta, STATES, SPEED } from '../lib/animation.mjs';

test('a squad of soldiers is a crowd of different people, not copies', () => {
  const looks = Array.from({ length: 24 }, (_, i) => makeCharacter({ role: 'soldier', faction: 'allied', era: 'ww2', seed: `sq:${i}` }));
  let same = 0, pairs = 0; for (let i = 0; i < looks.length; i++) for (let j = i + 1; j < looks.length; j++) { pairs++; if (lookDistance(looks[i], looks[j]) < 1) same++; }
  assert.ok(same / pairs < 0.1, `${same}/${pairs} near-identical pairs`);
  assert.equal(new Set(looks.map((l) => JSON.stringify(l.face))).size > 12, true);
});
test('a named person keeps the same look in every scene', () => {
  const a = makeCharacter({ role: 'commander', faction: 'allied', era: 'ww2', name: 'Eisenhower', seed: 'x1' }), b = makeCharacter({ role: 'commander', faction: 'allied', era: 'ww2', name: 'Eisenhower', seed: 'zzz' });
  assert.equal(lookDistance(a, b), 0);
});
test('every role builds, in every era', () => { for (const r of ROLES) for (const era of ['ww1', 'ww2', 'cold_war', 'modern']) assert.ok(makeCharacter({ role: r, faction: 'civilian', era, seed: r })); });
test('no state freezes: every state moves over two seconds and has finite joints', () => {
  for (const st of STATES) {
    const sched = [{ t0: 0, t1: 99, state: st }]; let moved = 0, prev = poseAt(sched, 0.5, 0.2);
    for (let k = 1; k <= 40; k++) { const p = poseAt(sched, 0.5 + k * 0.05, 0.2); moved += poseDelta(prev, p); prev = p; for (const j of ['root', 'torso', 'head', 'armL', 'armR', 'legL', 'legR']) for (const v of Object.values(p[j])) assert.ok(Number.isFinite(v), `${st} ${j}`); }
    assert.ok(moved > 0.02, `${st} barely moves (${moved.toFixed(3)})`);
  }
});
test('a change of state blends (no pose pops larger than a stride)', () => {
  const sched = [{ t0: 0, t1: 2, state: 'run' }, { t0: 2, t1: 5, state: 'salute' }]; let worst = 0, prev = poseAt(sched, 1.9, 0.1);
  for (let t = 1.92; t < 2.6; t += 1 / 24) { const p = poseAt(sched, t, 0.1); worst = Math.max(worst, poseDelta(prev, p)); prev = p; }
  let base = 0, q = poseAt([{ t0: 0, t1: 99, state: 'run' }], 0.5, 0.1); for (let t = 0.54; t < 1.5; t += 1 / 24) { const p = poseAt([{ t0: 0, t1: 99, state: 'run' }], t, 0.1); base = Math.max(base, poseDelta(q, p)); q = p; }
  assert.ok(worst <= base * 1.1 + 0.2, `blend pop ${worst.toFixed(2)} vs a running stride's own ${base.toFixed(2)}`);
  assert.ok(SPEED.run > SPEED.walk);
});
