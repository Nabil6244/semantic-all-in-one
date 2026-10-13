// Weather News graphics: the pure maths (count-up, reveal, dBZ scale, panel places) and each plugin's event checks.
import test from 'node:test';
import assert from 'node:assert/strict';
import { countAt, revealed, popIn, dbzX, legendRect, counterRect, reportsRect, pointChip, creditRect } from '../lib/wxu_news_anim.mjs';
import { validateWxEvents } from '../lib/wx_draw.mjs';
import counter from '../lib/layers/counter.mjs';
import radarLegend from '../lib/layers/radar_legend.mjs';
import stormPoints from '../lib/layers/storm_points.mjs';
import stormReports from '../lib/layers/storm_reports.mjs';
import stormCredit from '../lib/layers/storm_credit.mjs';

const plugins = [counter, radarLegend, stormPoints, stormReports, stormCredit];
const inFrame = (r) => r.x >= 0 && r.y >= 0 && r.x + r.w <= 1920 && r.y + r.h <= 1080;

test('a counter counts from 0 to its value and stays there', () => {
  const e = { t_in: 10, value: 46, count_s: 2 };
  assert.equal(countAt(e, 10), 0);
  assert.equal(countAt(e, 10.35), 0);
  assert.ok(countAt(e, 11.2) > 20 && countAt(e, 11.2) < 46);
  assert.equal(countAt(e, 12.35), 46);
  assert.equal(countAt(e, 30), 46);
  for (let t = 10; t < 13; t += 0.1) assert.ok(Number.isInteger(countAt(e, t)));
});

test('report dots appear in order and are counted per kind', () => {
  const pts = [{ kind: 'tornado', at: 1 }, { kind: 'wind', at: 2 }, { kind: 'tornado', at: 3 }];
  assert.deepEqual(revealed(pts, 2.5), { total: 2, byKind: { tornado: 1, wind: 1 } });
  assert.equal(revealed(pts, 0).total, 0);
  assert.ok(Math.abs(popIn({ at: 1 }, 1.15) - 0.5) < 1e-9);
});

test('the dBZ scale spans the legend bar', () => {
  const stops = [{ dbz: 5 }, { dbz: 75 }];
  assert.equal(dbzX(5, stops, 100, 700), 100);
  assert.equal(dbzX(75, stops, 100, 700), 800);
  assert.equal(dbzX(40, stops, 100, 700), 450);
  assert.equal(dbzX(90, stops, 100, 700), 800);
});

test('news panels stay inside the frame and clear of the HUD title', () => {
  for (const r of [legendRect(), counterRect('tr', 360), counterRect('tl', 360), counterRect('br', 360), counterRect('bl', 360), reportsRect(3, 140), creditRect(600)]) assert.ok(inFrame(r), JSON.stringify(r));
  assert.ok(counterRect('tl', 360).y >= 130, 'top-left counter sits under the HUD title');
  assert.ok(pointChip(1850, 500, 300).x + 300 <= 1920, 'a label near the right edge flips left');
  assert.ok(pointChip(400, 500, 300).x > 400);
});

test('plugin events are checked and named', () => {
  const ok = [
    { id: 'c', type: 'counter', t_in: 0, t_out: 5, value: 46, label: 'TORNADO REPORTS', sub: 'PRELIMINARY', anchor: 'tr' },
    { id: 'l', type: 'radar_legend', t_in: 0, t_out: 5, stops: [{ dbz: 5, color: '#04E9E7' }, { dbz: 75, color: '#FDFDFD' }], labels: [] },
    { id: 'p', type: 'storm_points', t_in: 0, t_out: 5, points: [{ lon: -82, lat: 26, at: 1, color: '#FF8F20', label: 'CAT 4' }] },
    { id: 'r', type: 'storm_reports', t_in: 0, t_out: 5, points: [{ lon: -97, lat: 36, kind: 'tornado', at: 1 }], legend: [{ kind: 'tornado', label: 'TORNADO', color: '#f00', total: 1 }], title: 'STORM REPORTS', sub: 'PRELIMINARY' },
    { id: 'f', type: 'footage_credit', t_in: 0, t_out: 5, text: 'VIDEO: NASA' },
  ];
  assert.deepEqual(validateWxEvents(ok, 10, plugins), []);
  const bad = validateWxEvents([
    { id: 'c', type: 'counter', t_in: 0, t_out: 5, value: 4.5, label: '' },
    { id: 'l', type: 'radar_legend', t_in: 0, t_out: 5, stops: [{ dbz: 50, color: '#f00' }, { dbz: 10, color: '#0f0' }] },
    { id: 'p', type: 'storm_points', t_in: 0, t_out: 5, points: [] },
    { id: 'r', type: 'storm_reports', t_in: 0, t_out: 5, points: [], legend: [{ kind: 'hail' }], title: 'REPORTS', sub: '' },
    { id: 'f', type: 'footage_credit', t_in: 0, t_out: 5 },
  ], 10, plugins);
  assert.deepEqual(bad, [
    'weather.events[0] (c): counter needs a whole, non-negative value', 'weather.events[0] (c): counter needs a label',
    'weather.events[1] (l): radar_legend stops need dbz (rising) and color', 'weather.events[2] (p): storm_points needs points',
    'weather.events[3] (r): storm_reports must be labelled PRELIMINARY', 'weather.events[4] (f): footage_credit needs text',
  ]);
  assert.equal(stormCredit.overFootage, true);
});
