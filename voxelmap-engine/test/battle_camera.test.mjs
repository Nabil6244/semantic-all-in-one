import test from 'node:test';
import assert from 'node:assert/strict';
import { shotFrames, offset } from '../lib/director.mjs';

const km = (a, b) => Math.hypot((a.lon - b.lon) * 111.32 * Math.cos((a.lat * Math.PI) / 180), (a.lat - b.lat) * 111.32);
const beat = (site) => ({ id: 'b', rung: 'ground', site, lon: 74.5, lat: 31.2 });

test('a battle pass stays on the action: tight span, low camera', () => {
  for (const shot of ['flyover', 'low_track', 'orbit']) {
    const f = shotFrames(beat('battle'), shot, 3);
    assert.ok(km(f.start, f.end) <= 0.3, `${shot} span ${km(f.start, f.end)} km`);
    assert.ok(f.start.alt <= 0.09, `${shot} alt ${f.start.alt}`);
  }
});

test('other ground sets keep their wide passes', () => {
  const f = shotFrames(beat('village'), 'low_track', 3);
  assert.ok(km(f.start, f.end) > 0.4);
  const g = shotFrames(beat('jungle'), 'flyover', 3);
  assert.ok(km(g.start, g.end) > 0.7);
  assert.ok(offset({ lon: 0, lat: 0 }, 90, 1).lon > 0);
});
