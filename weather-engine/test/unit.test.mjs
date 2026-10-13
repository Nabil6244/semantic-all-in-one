// Pure parts of weather-engine: layout, event checks, icons list, footage cover.
import test from 'node:test';
import assert from 'node:assert/strict';
import { stripLayout, nowLayout, legendLayout, sourceLayout, tempChipLayout, chooseSide, chipCovers, WX } from '../lib/wx_layout.mjs';
import { validateWxEvents, footageCover, WX_TYPES, countUp } from '../lib/wx_draw.mjs';
import { frameAt, validateRasters } from '../lib/wx_raster.mjs';
import { ICONS } from '../lib/wx_icons.mjs';
import { FRAME } from '../../pakmap-engine/lib/layout.mjs';
import { GEOM } from '../../pakmap-engine/lib/style.mjs';

const inside = (r) => r.x >= 0 && r.y >= 0 && r.x + r.w <= FRAME.w && r.y + r.h <= FRAME.h;

test('the forecast strip fits the frame for 3 to 7 days, centred, with equal columns', () => {
  for (let n = 3; n <= 7; n++) {
    const L = stripLayout(n);
    assert.ok(inside(L), `strip of ${n} days leaves the frame`);
    assert.ok(Math.abs(L.x + L.w / 2 - FRAME.w / 2) <= 1, 'strip is centred');
    assert.equal(L.cells.length, n);
    const widths = new Set(L.cells.map((c) => c.w.toFixed(3)));
    assert.equal(widths.size, 1, 'columns are the same width');
    assert.ok(L.x >= GEOM.margin.left - 1 && L.x + L.w <= FRAME.w - GEOM.margin.right + 1, 'strip keeps the frame margins');
  }
});

test('the strip stays clear of the source line at the bottom', () => {
  const L = stripLayout(5), S = sourceLayout(600);
  assert.ok(L.y + L.h <= S.y, `strip bottom ${L.y + L.h} overlaps the source line top ${S.y}`);
});

test('the now card sits top right (or top left) inside the margins, below no title', () => {
  const r = nowLayout('tr'), l = nowLayout('tl');
  assert.ok(inside(r) && inside(l));
  assert.equal(r.x + r.w, FRAME.w - GEOM.margin.right);
  assert.equal(l.x, GEOM.margin.left);
  assert.ok(r.title.y >= 0);
});

test('a temperature chip goes to the side pickSide chooses and keeps a forced side', () => {
  assert.equal(chooseSide(1800, 540, 260, 'l'), 'l');
  const s = chooseSide(1850, 540, 260, 'auto');
  assert.notEqual(s, 'r', 'a city at the right edge does not put its chip off screen');
  const L = tempChipLayout({ x: 500, y: 500, side: 'r', width: 260 });
  assert.equal(L.x, 500 + WX.marker.offset);
  assert.equal(L.h, WX.marker.h);
});

test('a new temperature chip takes a side that does not cover a chip already on screen', () => {
  const width = 260;
  const first = chooseSide(1000, 500, width, 'auto');
  const taken = [tempChipLayout({ x: 1000, y: 500, side: first, width })];
  const near = chooseSide(1010, 505, width, 'auto', taken);           // a city right next to the first one
  const r = tempChipLayout({ x: 1010, y: 505, side: near, width }), o = taken[0];
  assert.ok(!(r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h), `chips overlap on side ${near}`);
  assert.equal(chooseSide(1010, 505, width, 'l', taken), 'l', 'a forced side is kept');
});

test('a chip that the camera brings onto another chip is detected (so it can move to a free side)', () => {
  const width = 260, a = tempChipLayout({ x: 900, y: 500, side: 'b', width });
  assert.equal(chipCovers(1000, 500, width, 'b', [a]), true);      // two cities 100 px apart, both chips below: they overlap
  const s = chooseSide(1000, 500, width, 'auto', [a]);
  assert.equal(chipCovers(1000, 500, width, s, [a]), false);
});

test('legend and source line are inside the frame', () => {
  assert.ok(inside(legendLayout(4, 300)));
  assert.ok(inside(sourceLayout(900)));
});

test('weather events are checked, and every problem names the event', () => {
  const ok = [
    { id: 'm', type: 'temp_marker', t_in: 0, t_out: 2, lon: -96, lat: 32, temp: '90°', city: 'DALLAS', tag: 'MON HIGH', icon: 'sun' },
    { id: 's', type: 'forecast_strip', t_in: 0, t_out: 2, title: 'X', days: [{}, {}, {}] },
    { id: 'n', type: 'now_card', t_in: 0, t_out: 2, title: 'X NOW', temp: '80°' },
    { id: 'l', type: 'alert_legend', t_in: 0, t_out: 2, items: [{ label: 'A', color: '#fff' }] },
    { id: 'src', type: 'source_line', t_in: 0, t_out: 2, text: 'Data: NWS' },
  ];
  assert.deepEqual(validateWxEvents(ok, 2), []);
  const bad = validateWxEvents([
    { id: 'a', type: 'radar', t_in: 0, t_out: 1 },
    { id: 'b', type: 'temp_marker', t_in: 0, t_out: 1 },
    { id: 'c', type: 'forecast_strip', t_in: 0, t_out: 1, days: [{}, {}] },
    { id: 'd', type: 'source_line', t_in: 0, t_out: 9, text: 'x' },
    { id: 'd', type: 'source_line', t_in: 0, t_out: 1, text: 'x' },
  ], 5);
  assert.match(bad.join('\n'), /\(a\): unknown type "radar"/);
  assert.match(bad.join('\n'), /\(b\): temp_marker needs/);
  assert.match(bad.join('\n'), /\(c\): forecast_strip needs 3 to 7 days/);
  assert.match(bad.join('\n'), /\(d\): ends after the video/);
  assert.match(bad.join('\n'), /duplicate id/);
});

test('two forecast strips on screen at once are refused', () => {
  const day = [{}, {}, {}];
  const errs = validateWxEvents([{ id: 'a', type: 'forecast_strip', t_in: 0, t_out: 3, title: 'A', days: day }, { id: 'b', type: 'forecast_strip', t_in: 2, t_out: 4, title: 'B', days: day }], 5);
  assert.match(errs.join(), /two forecast strips overlap/);
});

test('full-screen footage covers the weather graphics, with the same dissolve as pakMap', () => {
  const ev = [{ id: 'f', type: 'media_full', t_in: 2, t_out: 6 }];
  assert.equal(footageCover(ev, 1), 0);
  assert.equal(footageCover(ev, 4), 1);
  assert.ok(footageCover(ev, 2.25) > 0 && footageCover(ev, 2.25) < 1);
  assert.equal(footageCover(ev, 6), 0);
});

test('every icon the data side can ask for is drawn', () => {
  for (const k of ['sun', 'moon', 'cloud', 'partly', 'partly_night', 'rain', 'storm', 'snow', 'sleet', 'fog', 'wind']) assert.ok(ICONS.includes(k), k);
  assert.deepEqual(WX_TYPES, ['temp_marker', 'forecast_strip', 'now_card', 'alert_legend', 'source_line']);
});

test('temperatures count up as they appear and always end on the exact value', () => {
  assert.equal(countUp('92\u00b0', 0, 0), '80\u00b0');
  assert.equal(countUp('92\u00b0', 0.6, 0), '92\u00b0');
  assert.equal(countUp('92\u00b0', 9, 0), '92\u00b0');
  assert.equal(countUp('-5\u00b0', 1, 0), '-5\u00b0');
  assert.equal(countUp('N/A', 0, 0), 'N/A');
});

test('a tile loop steps through its frames and cross-fades into the next', () => {
  const r = { t_in: 10, t_out: 20, crossfade_s: 0.5, frames: [{ at: 0 }, { at: 2 }, { at: 4 }] };
  assert.deepEqual(frameAt(r, 10), { index: 0, mix: 0 });
  assert.deepEqual(frameAt(r, 11.75), { index: 0, mix: 0.5 });
  assert.deepEqual(frameAt(r, 12), { index: 1, mix: 0 });
  assert.deepEqual(frameAt(r, 19), { index: 2, mix: 0 });
  assert.deepEqual(frameAt({ ...r, crossfade_s: 0 }, 11.9), { index: 0, mix: 0 });
});

test('tile loops are checked and every problem names the loop', () => {
  const p = { id: 'x', urlTemplate: 'https://e/{z}/{x}/{y}.png' };
  assert.deepEqual(validateRasters([{ id: 'r', t_in: 0, t_out: 5, frames: [{ at: 0, provider: p }, { at: 1, provider: { ...p, id: 'y' } }] }], 5), []);
  const e = validateRasters([{ id: 'r', t_in: 0, t_out: 9, frames: [{ at: 2, provider: p }, { at: 1, provider: {} }] }, { id: 'r', t_in: 0, t_out: 1, frames: [] }], 5).join('\n');
  assert.match(e, /\(r\): ends after the video/);
  assert.match(e, /frame 1 needs a provider/);
  assert.match(e, /frame 1 needs an "at" time, in order/);
  assert.match(e, /duplicate id/);
  assert.match(e, /needs at least one frame/);
});
