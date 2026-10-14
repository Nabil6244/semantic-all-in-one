// storm_stats (lib/layers/storm_stats.mjs): its event checks and its card's place in the frame.
import test from 'node:test';
import assert from 'node:assert/strict';
import stormStats, { statsLayout } from '../lib/layers/storm_stats.mjs';

const rows = [{ label: 'PEAK STRENGTH', value: 'CAT 5 · 160 MPH', sub: 'SEP 28, 8:00 AM EDT' },
  { label: 'LOWEST PRESSURE', value: '937 MB' }, { label: 'LANDFALL', value: 'CAT 4 · 150 MPH', sub: 'SEP 28, 3:05 PM EDT' }];

test('a storm_stats event needs a title and one to four labelled rows', () => {
  assert.deepEqual(stormStats.validate({ title: 'HURRICANE IAN', rows, anchor: 'l' }), []);
  assert.ok(stormStats.validate({ rows }).length);
  assert.ok(stormStats.validate({ title: 'X', rows: [] }).length);
  assert.ok(stormStats.validate({ title: 'X', rows: [{ label: 'A' }] }).length);
  assert.ok(stormStats.validate({ title: 'X', rows, anchor: 'tr' }).length);
});

test('the card stays inside the frame, clear of the HUD title and the source line, on either side', () => {
  for (const anchor of ['l', 'r']) for (let n = 1; n <= 4; n++) {
    const L = statsLayout(n, anchor);
    assert.ok(L.x >= 0 && L.x + L.w <= 1920, `x ${anchor} ${n}`);
    assert.ok(L.y >= 150 && L.y + L.h <= 1080 - 100, `y ${anchor} ${n}: ${L.y}..${L.y + L.h}`);
  }
});
