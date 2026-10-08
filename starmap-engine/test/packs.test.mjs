// Every mission pack's trajectories (starmap/packs/*.json) generate in the engine, never pass inside the Earth or the Moon,
// never jump, and every landing ends on its site. An observed (sampled, Sun-centred) path is held to a heliocentric limit. A new pack is covered as soon as its file is added.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { buildWorld } from '../lib/world.mjs';
import { createTrajectory } from '../lib/paths.mjs';

const ROOT = new URL('../../starmap/', import.meta.url);
const bodies = JSON.parse(fs.readFileSync(new URL('catalog/bodies.json', ROOT), 'utf8')).world;
const packs = fs.readdirSync(new URL('packs/', ROOT)).filter((f) => f.endsWith('.json'))
  .map((f) => JSON.parse(fs.readFileSync(new URL(`packs/${f}`, ROOT), 'utf8')));
const RADIUS = { earth: 6371, moon: 1737.4 };
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

test('there are mission packs to check', () => assert.ok(packs.length >= 6));

for (const pack of packs) {
  test(`${pack.id}: trajectories generate, stay outside the Earth and the Moon, never jump, and land on their sites`, () => {
    const w = buildWorld(bodies, { date: pack.met_zero });
    for (const def of pack.trajectories) {
      const tr = createTrajectory(w, def);
      const frame = def.frame || tr.frame;
      // altitude above each body at 1500 moments across the flight (a launch starts and a landing ends at 0 km)
      for (let i = 0; i <= 1500; i++) {
        const when = tr.t0 + (tr.t1 - tr.t0) * (i / 1500);
        w.setTime(new Date(when));
        const p = tr.at(when).position;
        for (const body of ['earth', 'moon']) {
          const alt = dist(p, w.vec(frame, body)) - RADIUS[body];
          assert.ok(alt > -0.5, `${def.id} is ${(-alt).toFixed(1)} km inside the ${body} at ${new Date(when).toISOString()}`);
        }
      }
      // speed between consecutive samples: nothing faster than a spacecraft goes (a jump shows up as hundreds of km/s)
      for (let i = 1; i < tr.samples.length; i++) {
        w.setTime(new Date(tr.samples[i].ms));
        const P = tr.points();
        const v = dist(P[i], P[i - 1]) / ((tr.samples[i].ms - tr.samples[i - 1].ms) / 1000);
        assert.ok(v < (frame === 'sun' ? 60 : 12), `${def.id} moves ${v.toFixed(1)} km/s at sample ${i} (${new Date(tr.samples[i].ms).toISOString()})`);
      }
      // a landing ends on its site
      const landing = (def.generate || []).find((g) => g.kind === 'surface_track' && g.site_at === 'end');
      if (landing) {
        w.setTime(new Date(tr.t1));
        const [lon, lat] = landing.site;
        const site = w.vec(frame, landing.body).map((c, k) => c + w.surfaceOffset(landing.body, lon, lat, 0)[k]);
        assert.ok(dist(tr.at(tr.t1).position, site) < 0.5, `${def.id} ends on ${lon}, ${lat}`);
      }
    }
  });
}
