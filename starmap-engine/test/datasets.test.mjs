// Every dataset -- the six mission packs and the architectural fixtures (Voyager, Juno, Parker, JWST, an asteroid, a
// hypothetical Moon base ...) -- builds in the generic engine: its extra bodies join the world and every trajectory produces
// finite positions from start to end. No dataset needs renderer code of its own.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildWorld } from '../lib/world.mjs';
import { createTrajectory } from '../lib/paths.mjs';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const base = JSON.parse(fs.readFileSync(path.join(ROOT, 'starmap', 'catalog', 'bodies.json'), 'utf8')).world;
const dirs = [path.join(ROOT, 'starmap', 'packs'), path.join(ROOT, 'test_fixtures', 'starmap_datasets')];
const datasets = dirs.flatMap((d) => (fs.existsSync(d) ? fs.readdirSync(d).filter((f) => f.endsWith('.json')).sort().map((f) => JSON.parse(fs.readFileSync(path.join(d, f), 'utf8'))) : []));

test('the library has the six missions and the broad fixture set', () => {
  const ids = new Set(datasets.map((d) => d.id));
  for (const id of ['apollo8', 'apollo11', 'apollo13', 'artemis1', 'chandrayaan3', 'change4', 'voyager1', 'voyager2', 'artemis3', 'moon_base_2050',
    'juno', 'parker_solar_probe', 'jwst', 'perseverance', 'osiris_rex', 'iss', 'rosetta', 'new_horizons']) assert.ok(ids.has(id), id);
});

test('every dataset trajectory builds in the generic engine, with finite positions across its whole span', () => {
  for (const d of datasets) {
    const world = buildWorld([...base, ...(d.world || [])], { date: new Date('2000-01-01T00:00:00Z') });
    for (const t of d.trajectories || []) {
      const anyDate = (t.samples && t.samples[0].utc) || t.generate.find((g) => g.from_utc).from_utc;
      world.setTime(new Date(anyDate));
      const traj = createTrajectory(world, t);
      for (const k of [0, 0.25, 0.5, 0.75, 1]) {
        const when = traj.t0 + (traj.t1 - traj.t0) * k;
        world.setTime(new Date(when));
        const p = traj.at(when).position;
        assert.ok(p.every(Number.isFinite), `${d.id}/${t.id} at ${new Date(when).toISOString()}`);
      }
    }
  }
});
