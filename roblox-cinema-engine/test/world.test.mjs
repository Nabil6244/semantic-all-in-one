import test from 'node:test';
import assert from 'node:assert/strict';
import { ENVIRONMENTS, makeWorld } from '../lib/world.mjs';
import { RECIPES } from '../lib/recipes.mjs';
import { VOCAB } from '../lib/director.mjs';
import { VEHICLES, planVehicles, vehicleState } from '../lib/vehicles.mjs';

test('every environment builds, with finite ground and a centre anchor', () => {
  for (const env of ENVIRONMENTS) {
    const W = makeWorld(env, { seed: 5, culture: 'european', era: 'ww2', time: 'day', weather: 'clear' });
    for (const [x, z] of [[0, 0], [50, -40], [-120, 90], [200, 200]]) assert.ok(Number.isFinite(W.heightAt(x, z)), `${env} height`);
    assert.ok(W.anchorY('center').every(Number.isFinite), env);
  }
});
test('same seed, same set; different seed, different set', () => {
  const a = makeWorld('farmland', { seed: 3 }), b = makeWorld('farmland', { seed: 3 }), c = makeWorld('farmland', { seed: 4 });
  assert.equal(JSON.stringify(a.trees.slice(0, 20)), JSON.stringify(b.trees.slice(0, 20)));
  assert.notEqual(JSON.stringify(a.trees.slice(0, 20)), JSON.stringify(c.trees.slice(0, 20)));
});
test('every recipe names only things the engine has', () => {
  for (const [name, R] of Object.entries(RECIPES)) {
    assert.ok(VOCAB.environments.has(R.env), `${name} env ${R.env}`);
    for (const c of R.cast) assert.ok(VOCAB.roles.has(c.role), `${name} role ${c.role}`);
    for (const v of R.vehicles) assert.ok(VEHICLES[v.kind], `${name} vehicle ${v.kind}`);
    for (const f of R.fx) assert.ok(VOCAB.effects.has(f), `${name} fx ${f}`);
    for (const s of R.shots) assert.ok(VOCAB.cameras.has(s), `${name} shot ${s}`);
  }
  assert.ok(Object.keys(RECIPES).length >= 27);
});
test('ground vehicles sit on the ground, boats on the water, aircraft above both', () => {
  const beach = makeWorld('beach', { seed: 9 }), farm = makeWorld('farmland', { seed: 9 });
  for (const [kind, W] of [['tank', farm], ['jeep', farm], ['truck', farm], ['landing_craft', beach], ['ship', beach], ['transport_plane', farm]]) {
    const spec = VEHICLES[kind]; if (!spec) continue;
    const plans = planVehicles(kind, 3, spec.cls === 'air' ? 'flyover' : spec.cls === 'water' ? 'drift' : 'advance', W, { t0: 0, t1: 20, seed: kind, anchor: spec.cls === 'water' ? (W.anchors.offshore ? 'offshore' : 'center') : 'center' });
    for (const v of plans) for (const t of [0, 5, 10, 18]) {
      const s = vehicleState(v, t, W), g = Math.max(W.heightAt(s.x, s.z), W.water ? W.water.level : -1e9);
      if (spec.cls === 'ground') assert.ok(Math.abs(s.y - W.heightAt(s.x, s.z)) < 2.5, `${kind} floats/sinks ${s.y} vs ${W.heightAt(s.x, s.z)}`);
      if (spec.cls === 'air') assert.ok(s.y > g + 5, `${kind} too low`);
      if (spec.cls === 'water') assert.ok(Math.abs(s.y - (W.water ? W.water.level : 0)) < 3, `${kind} not on water`);
    }
  }
});
