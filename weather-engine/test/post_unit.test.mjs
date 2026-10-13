// Post-event graphics, the pure parts: layouts stay in the frame and clear of each other's furniture, counts run up to the
// given value only, hydrographs break at gaps, timeline labels do not overlap, and each plugin's checks name what is missing.
import test from 'node:test';
import assert from 'node:assert/strict';
import { POST, sidePanel, countText, barsLayout, barGrow, barLength, recordLayout, hydroLayout, hydroPoints, niceStep, rainLegendLayout,
  timelineLayout, placeMarks, baLabelAt, chipLayout } from '../lib/wxu_post_charts.mjs';
import { sourceLayout } from '../lib/wx_layout.mjs';
import { FRAME } from '../../pakmap-engine/lib/layout.mjs';
import chip from '../lib/layers/post_chip.mjs';
import bars from '../lib/layers/post_bars.mjs';
import record from '../lib/layers/post_record.mjs';
import hydro from '../lib/layers/post_hydrograph.mjs';
import legend from '../lib/layers/post_rainlegend.mjs';
import timeline from '../lib/layers/post_timeline.mjs';
import ba from '../lib/layers/post_beforeafter.mjs';

const inside = (r) => r.x >= 0 && r.y >= 0 && r.x + r.w <= FRAME.w && r.y + r.h <= FRAME.h;
const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

test('panels stay inside the frame, below the HUD title and above the source line', () => {
  const src = sourceLayout(900);
  for (const L of [barsLayout(1), barsLayout(8), barsLayout(8, 'l'), recordLayout(), recordLayout('l'), hydroLayout([1, 2, 3]), rainLegendLayout(11), timelineLayout()]) {
    assert.ok(inside(L), JSON.stringify(L));
    assert.ok(L.y >= POST.top - 1, `panel top ${L.y} under the HUD`);
    assert.ok(!overlaps(L, src), `panel ${JSON.stringify(L)} covers the source line`);
  }
  assert.equal(sidePanel(600, 200).x + 600, POST.right);
  assert.equal(sidePanel(600, 200, 'l').x, POST.left);
});

test('a count-up keeps the decimals and the unit, and never passes the value', () => {
  assert.equal(countText('31.26 IN', 0), '0.00 IN');
  assert.equal(countText('31.26 IN', 1), '31.26 IN');
  assert.equal(countText('41.9 FT', 2), '41.9 FT');
  assert.equal(countText('47.5', 1, 1), '47.5');
  assert.ok(Number(countText('31.26 IN', 0.5).split(' ')[0]) < 31.26);
  assert.equal(countText('N/A', 0.5), 'N/A');
});

test('bars grow one after another, the longest fills the track', () => {
  assert.equal(barGrow(0, 0, 0), 0);
  assert.ok(barGrow(0.8, 0, 0) > barGrow(0.8, 0, 1));
  assert.equal(barGrow(10, 0, 7), 1);
  const L = barsLayout(3);
  assert.equal(barLength(47.48, 47.48, L.barMax), L.barMax);
  assert.ok(Math.abs(barLength(23.74, 47.48, L.barMax) - L.barMax / 2) < 1e-9);
  assert.ok(L.rows[2].cy < L.y + L.h);
});

test('the hydrograph range holds the readings and flood lines, and a gap breaks the line', () => {
  assert.equal(niceStep(9.3), 10);
  assert.equal(niceStep(1.2), 2);
  const L = hydroLayout([2.5, null, 41.9, 30], [{ value: 32 }]);
  assert.ok(L.lo <= 2.5 && L.hi >= 41.9);
  const pts = hydroPoints([2.5, null, 41.9, 30], L);
  assert.equal(pts[1], null);
  assert.ok(pts[2][1] < pts[0][1], 'higher water is higher on screen');
  assert.equal(hydroPoints([1, 2, 3, 4], L, 1.5).length, 2);
});

test('timeline marks: positions along the axis, labels lifted a level when they would touch', () => {
  const L = timelineLayout();
  const marks = placeMarks([{ f: 0.2 }, { f: 0.25 }, { f: 0.28 }, { f: 0.9 }], L, () => 200);
  assert.deepEqual(marks.map((m) => m.level), [0, 1, 2, 0]);
  assert.ok(Math.abs(marks[0].x - (L.axisX + 0.2 * L.axisW)) < 1e-9);
  for (const m of marks) assert.ok(m.lx >= L.x && m.lx + m.w <= L.x + L.w);
  const top2 = L.y + 18 + 2 * POST.timeline.level + POST.timeline.box;
  assert.ok(top2 < L.axisY - 8, 'the third level of labels stays above the axis');
});

test('before/after label switches half way through the cross-fade', () => {
  const e = { t_in: 10, frames: [{ at: 0 }, { at: 5 }], crossfade: 2 };
  assert.deepEqual(baLabelAt(e, 11), { index: 0, mix: 0 });
  assert.equal(baLabelAt(e, 13.5).index, 0);
  assert.equal(baLabelAt(e, 14.2).index, 1);
  assert.deepEqual(baLabelAt(e, 16), { index: 1, mix: 0 });
});

test('a map chip turns away from the frame edge', () => {
  assert.equal(chipLayout(900, 500, 300).side, 'r');
  assert.equal(chipLayout(1800, 500, 300).side, 'l');
  assert.equal(chipLayout(900, 500, 300, 'b').side, 'b');
  assert.ok(inside(chipLayout(1850, 200, 300)));
});

test('each plugin names what an event is missing', () => {
  assert.deepEqual(chip.validate({ lon: -95, lat: 30, label: 'A', value: '1 IN' }), []);
  assert.match(chip.validate({ label: 'A' }).join(), /lon and lat/);
  assert.deepEqual(bars.validate({ title: 'T', bars: [{ label: 'A', value: 1, text: '1' }] }), []);
  assert.match(bars.validate({ title: 'T', bars: [] }).join(), /1 to 8 bars/);
  assert.match(bars.validate({ title: 'T', bars: [{ label: 'A' }] }).join(), /bar 1 needs/);
  assert.match(record.validate({ headline: 'X' }).join(), /needs place/);
  assert.match(hydro.validate({ title: 'X', values: [1] }).join(), /at least two/);
  assert.match(legend.validate({ stops: [] }).join(), /stops/);
  assert.match(timeline.validate({ ticks: [{}], marks: [{ f: 2 }] }).join(), /ticks.*mark 1/);
  assert.match(ba.validate({ frames: [{ at: 0, label: 'BEFORE', date: 'x' }] }).join(), /two frames/);
  for (const p of [chip, bars, record, hydro, legend, timeline, ba]) assert.match(p.type, /^post_/);
});
