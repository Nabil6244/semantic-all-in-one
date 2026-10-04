import test from 'node:test';
import assert from 'node:assert/strict';
import { formatValue, parseFormat, counterAt } from '../lib/format.mjs';
import { lifeAlpha, wordsVisible, lineProgress, dotsShown, clusterShown, revealOrder, popAt } from '../lib/anim.mjs';
import { trimPolyline, cumulative, overlaps } from '../lib/geom.mjs';
import { generatePoints, parsePointsCsv } from '../lib/points.mjs';
import { validateEvents, validateWatermark, textLayers, activeAt } from '../lib/events.mjs';
import { hudLayout, statLayout, captionLayout, markerLayout, pickSide, watermarkLayout } from '../lib/layout.mjs';
import { GEOM, TIMING } from '../lib/style.mjs';

const measure = (text, px) => text.length * px * 0.66; // fixed-width stand-in for canvas measureText

test('number formats from the reference: 12.6M, 17,700, -67.7 C, 1/5, 2c, 9,300 KM, M8.8', () => {
  assert.equal(formatValue(12.6, '0.0M'), '12.6M');
  assert.equal(formatValue(17700, '#,##0'), '17,700');
  assert.equal(formatValue(9300, '#,##0 KM'), '9,300 KM');
  assert.equal(formatValue(-67.7, '0.0 °C'), '−67.7 °C');
  assert.equal(formatValue(1, '0/5'), '1/5');
  assert.equal(formatValue(2, '0¢'), '2¢');
  assert.equal(formatValue(8.8, 'M0.0'), 'M8.8');
  assert.equal(formatValue(312700, '#,##0 KM²'), '312,700 KM²');
  assert.equal(formatValue(-0.04, '0.0'), '0.0'); // no "minus zero"
  assert.equal(formatValue(445, '0× SMALLER'), '445× SMALLER');
});

test('a format without a number placeholder is rejected with a clear message', () => {
  assert.throws(() => parseFormat('KM'), /no number placeholder/);
});

test('counter eases out into the value with no overshoot (3,927 -> 4,000 style)', () => {
  const c = (t) => counterAt(t, { from: 3900, to: 4000, t0: 1, dur: 0.6 });
  assert.equal(c(0.5), 3900);
  assert.equal(c(1.6), 4000);
  let prev = c(1);
  for (let t = 1.02; t <= 1.6; t += 0.02) { const v = c(t); assert.ok(v >= prev && v <= 4000); prev = v; }
  assert.ok(c(1.3) > 3950, 'decelerating: past half way by half time');
  assert.equal(counterAt(2, { from: 5, to: 5, t0: 1, dur: 1 }), 5);
});

test('layer fades in and out, and is gone outside its window', () => {
  assert.equal(lifeAlpha(0.9, 1, 5), 0);
  assert.equal(lifeAlpha(5, 1, 5), 0);
  assert.equal(lifeAlpha(3, 1, 5), 1);
  assert.ok(lifeAlpha(1.1, 1, 5) > 0 && lifeAlpha(1.1, 1, 5) < 1);
  assert.ok(lifeAlpha(4.9, 1, 5) < 1);
});

test('word-by-word reveal: one word every 0.067 s, never more than the text has', () => {
  assert.equal(wordsVisible(0.9, 1, 3), 0);
  assert.equal(wordsVisible(1.0, 1, 3), 1);
  assert.equal(wordsVisible(1.07, 1, 3), 2);
  assert.equal(wordsVisible(1.2, 1, 3), 3);
  assert.equal(wordsVisible(9, 1, 3), 3);
});

test('line draw: ease-out only (already moving on the first frame, finished at 0.9 s)', () => {
  assert.equal(lineProgress(0, 0), 0);
  assert.ok(lineProgress(1 / 30, 0) > 0.08);
  assert.equal(lineProgress(0.9, 0), 1);
  let prevStep = Infinity, prev = 0;
  for (let t = 0.05; t <= 0.9; t += 0.05) { const p = lineProgress(t, 0), step = p - prev; assert.ok(step <= prevStep + 1e-9, 'steps must shrink'); prevStep = step; prev = p; }
});

test('dot density is linear over 3.1 s; clusters pop one after another', () => {
  assert.equal(dotsShown(3, 3, 1000), 0);
  assert.equal(dotsShown(3 + TIMING.dotsReveal / 2, 3, 1000), 500);
  assert.equal(dotsShown(99, 3, 1000), 1000);
  assert.equal(clusterShown(1, 1, 5), 1);
  assert.equal(clusterShown(1 + 2 * TIMING.pointStagger, 1, 5), 3);
  assert.equal(clusterShown(50, 1, 5), 5);
});

test('reveal order is a fixed permutation (same every render)', () => {
  const a = revealOrder(500, 7), b = revealOrder(500, 7), c = revealOrder(500, 8);
  assert.deepEqual(a, b);
  assert.notDeepEqual(a, c);
  assert.deepEqual([...a].sort((x, y) => x - y), Array.from({ length: 500 }, (_, i) => i));
  assert.ok(popAt(0, 0).alpha === 0 && popAt(1, 0).alpha === 1);
});

test('trimPolyline returns the first part of the line, head-first, with the head direction', () => {
  const line = [[0, 0], [10, 0], [10, 10]];
  assert.equal(cumulative(line)[2], 20);
  assert.deepEqual(trimPolyline(line, 0.25).points, [[0, 0], [5, 0]]);
  const half = trimPolyline(line, 0.5);
  assert.deepEqual(half.points, [[0, 0], [10, 0]]);
  const three = trimPolyline(line, 0.75);
  assert.deepEqual(three.points, [[0, 0], [10, 0], [10, 5]]);
  assert.ok(Math.abs(three.angle - Math.PI / 2) < 1e-9);
  assert.deepEqual(trimPolyline(line, 1).points, line);
  assert.deepEqual(trimPolyline(line, 0).points, [[0, 0]]);
  assert.equal(overlaps({ x: 0, y: 0, w: 10, h: 10 }, { x: 9, y: 9, w: 5, h: 5 }), true);
  assert.equal(overlaps({ x: 0, y: 0, w: 10, h: 10 }, { x: 20, y: 0, w: 5, h: 5 }), false);
});

test('generated points are deterministic, stay in the box, and cluster around hotspots', () => {
  const spec = { bbox: [30, -5, 42, 5], n: 2000, seed: 5, uniform: 0.1, hotspots: [{ lon: 36.8, lat: -1.3, spread: 0.5, weight: 1 }] };
  const a = generatePoints(spec), b = generatePoints(spec);
  assert.deepEqual(a, b);
  assert.ok(a.every(([x, y]) => x >= 30 && x <= 42 && y >= -5 && y <= 5));
  const near = a.filter(([x, y]) => Math.hypot(x - 36.8, y + 1.3) < 1.5).length;
  assert.ok(near > 1400, `most points should sit near the hotspot (${near})`);
  assert.deepEqual(parsePointsCsv('lat,lon\n-1.29,36.82\n0.5,35\nbad,row\n'), [[36.82, -1.29], [35, 0.5]]);
});

const ev = (o) => ({ id: o.id, type: 'caption', text: 'X', t_in: 0, t_out: 5, ...o });

test('timeline rules: unknown type, bad window, duplicate id, end after video', () => {
  assert.match(validateEvents([ev({ id: 'a', type: 'teleport' })], 10).errors.join(), /unknown type/);
  assert.match(validateEvents([ev({ id: 'a', t_in: 4, t_out: 2 })], 10).errors.join(), /t_in < t_out/);
  assert.match(validateEvents([ev({ id: 'a' }), ev({ id: 'a' })], 10).errors.join(), /duplicate id/);
  assert.match(validateEvents([ev({ id: 'a', t_out: 12 })], 10).errors.join(), /ends after the video/);
  assert.match(validateEvents([{ type: 'caption', text: 'x', t_in: 0, t_out: 1 }], 10).errors.join(), /needs an id/);
});

test('timeline rules: layer-specific fields are checked', () => {
  const t = (e) => validateEvents([{ id: 'e', t_in: 0, t_out: 5, ...e }], 10).errors.join();
  assert.match(t({ type: 'stat', value_to: 'x' }), /numeric value_to/);
  assert.match(t({ type: 'stat', value_to: 1, format: 'KM' }), /no number placeholder/);
  assert.match(t({ type: 'marker', label: 'A' }), /lon and lat/);
  assert.match(t({ type: 'marker', lon: 1, lat: 1, label: 'A', role: 'pink' }), /unknown role/);
  assert.match(t({ type: 'line', kind: 'zigzag', coords: [[0, 0], [1, 1]] }), /line kind/);
  assert.match(t({ type: 'line', kind: 'flow', coords: [[0, 0]] }), /at least 2 coords/);
  assert.match(t({ type: 'dots' }), /needs points/);
  assert.equal(t({ type: 'dots', random: { bbox: [0, 0, 1, 1], n: 10 } }), '');
});

test('timeline rules: at most 2 stat chips, 5 text layers, 1 HUD title at a time', () => {
  const stat = (id, a, b) => ({ id, type: 'stat', value_to: 1, t_in: a, t_out: b });
  assert.match(validateEvents([stat('a', 0, 5), stat('b', 0, 5), stat('c', 1, 4)], 10).errors.join(), /3 stat chips/);
  assert.deepEqual(validateEvents([stat('a', 0, 5), stat('b', 0, 5), stat('c', 5, 9)], 10).errors, []);
  const many = [
    { id: 'h', type: 'hud_title', label: 'A', sub: 'B', t_in: 0, t_out: 9 },
    { id: 'm1', type: 'marker', lon: 1, lat: 1, label: 'M', sub: 'S', t_in: 1, t_out: 8 },
    { id: 's', type: 'stat', value_to: 1, t_in: 1, t_out: 8 },
    { id: 'c', type: 'caption', text: 'T', t_in: 1, t_out: 8 },
  ];
  assert.match(validateEvents(many, 10).errors.join(), /6 text layers/);
  assert.match(validateEvents([{ id: 'h1', type: 'hud_title', label: 'A', t_in: 0, t_out: 5 }, { id: 'h2', type: 'hud_title', label: 'B', t_in: 3, t_out: 8 }], 10).errors.join(), /two hud_title/);
  assert.equal(textLayers({ type: 'line' }), 0);
});

test('timeline rules: silence longer than 5 s is a warning, not an error', () => {
  const r = validateEvents([ev({ id: 'a', t_in: 1, t_out: 2 }), ev({ id: 'b', t_in: 9, t_out: 10 })], 12);
  assert.deepEqual(r.errors, []);
  assert.ok(r.warnings.some((w) => /between 2\.0s and 9\.0s/.test(w)));
  assert.deepEqual(validateEvents([ev({ id: 'a', t_in: 0, t_out: 4 }), ev({ id: 'b', t_in: 3, t_out: 8 })], 8).warnings, []);
  assert.equal(activeAt([ev({ id: 'a', t_in: 1, t_out: 2 })], 1.5).length, 1);
  assert.equal(activeAt([ev({ id: 'a', t_in: 1, t_out: 2 })], 2).length, 0);
});

test('layout: title chip at (45,37) 67 high, subtitle 39 high under it with the 8 px gap', () => {
  const L = hudLayout({ label: 'PART 1', sub: 'THE EMPTY HALF' }, measure);
  assert.deepEqual([L.title.x, L.title.y, L.title.h], [45, 37, 67]);
  assert.equal(L.subtitle.y - (L.title.y + L.title.h), GEOM.subtitle.gap + 1);
  assert.equal(L.subtitle.h, 39);
  assert.equal(L.title.w, Math.round(measure('PART 1', 46) + 38));
  assert.deepEqual(L.subtitle.words, ['THE', 'EMPTY', 'HALF']);
  assert.equal(hudLayout({ label: 'X' }, measure).subtitle, null);
});

test('layout: stat chip sits in the chosen corner, inside the margins, and grows with its text', () => {
  const br = statLayout({ anchor: 'br', number: '312,700 KM', sub: 'POLAND' }, measure);
  assert.equal(br.x + br.w, 1920 - GEOM.margin.right);
  assert.equal(br.y + br.h, 1080 - GEOM.margin.bottom);
  const bl = statLayout({ anchor: 'bl', number: '54%', sub: 'OF THE LAND' }, measure);
  assert.equal(bl.x, 40);
  const tr = statLayout({ anchor: 'tr', number: '445x' }, measure);
  assert.equal(tr.y, 60);
  const bc = statLayout({ anchor: 'bc', number: '1/5' }, measure);
  assert.ok(Math.abs(bc.x + bc.w / 2 - 960) <= 1);
  const wide = statLayout({ anchor: 'br', number: '9,999,999 KM', sub: 'X' }, measure), narrow = statLayout({ anchor: 'br', number: '9 KM', sub: 'X' }, measure);
  assert.ok(wide.w > narrow.w);
  assert.ok(statLayout({ anchor: 'br', number: '1', sub: 'X' }, measure).h > statLayout({ anchor: 'br', number: '1' }, measure).h);
});

test('layout: a one-line caption is 108 px high (44 px caps with 32 px above and below)', () => {
  const c = captionLayout({ text: 'SOMETHING YOU CAN\'T SEE', anchor: 'bc' }, measure);
  assert.equal(c.h, 108);
  assert.equal(c.lines[0].baseline - c.y, 32 + 44);
  assert.equal(c.y + c.h, 1080 - GEOM.margin.bottom);
});

test('layout: marker label chip is 52 px high and starts 27 px right of the dot', () => {
  const m = markerLayout({ x: 589, y: 693, label: 'GARISSA', value: '163,000', side: 'r' }, measure);
  assert.equal(m.chip.h, 52);
  assert.equal(m.chip.x - 589, 27);
  assert.equal(m.chip.y + m.chip.h / 2, 693);
});

test('layout: caption chip handles two lines and a source line; marker label picks a side with room', () => {
  const one = captionLayout({ text: 'SOMETHING', anchor: 'bc' }, measure), two = captionLayout({ text: 'THE LOWEST\nDESERT', sub: 'MUNDAY ET AL. 2022' }, measure);
  assert.ok(two.h > one.h);
  assert.equal(two.lines.length, 2);
  assert.ok(two.sub && two.sub.baseline < two.y + two.h);
  const m = markerLayout({ x: 500, y: 400, label: 'NAIROBI', value: '4.4 MILLION', side: 'r' }, measure);
  assert.ok(m.chip.x > 500 && m.chip.text === 'NAIROBI · 4.4 MILLION');
  assert.equal(pickSide(1800, 400, 200, 34), 'l');
  assert.equal(pickSide(300, 400, 200, 34), 'r');
  assert.equal(pickSide(1000, 300, 2000, 34), 'r'); // nothing fits: falls back to the first choice
});

test('watermark: any channel name, bottom right (as in the references) or bottom left', () => {
  const br = watermarkLayout({ text: 'MY CHANNEL', position: 'br' }, measure), bl = watermarkLayout({ text: 'MY CHANNEL', position: 'bl' }, measure);
  assert.ok(br.textX + br.w <= 1920 - GEOM.watermark.right + 1 && br.textX > 960);
  assert.equal(bl.iconX, GEOM.watermark.left);
  assert.ok(bl.textX < 400);
  assert.equal(br.baseline, 1080 - GEOM.watermark.bottom);
  assert.ok(watermarkLayout({ text: 'A MUCH LONGER CHANNEL NAME' }, measure).textX < br.textX, 'a longer name grows to the left');
});

test('watermark settings are validated; none at all is fine', () => {
  assert.deepEqual(validateWatermark(undefined), []);
  assert.deepEqual(validateWatermark({ text: 'MY CHANNEL', position: 'bl', opacity: 0.5 }), []);
  assert.match(validateWatermark({ position: 'tl' }).join(), /"br".*"bl"/);
  assert.match(validateWatermark({ opacity: 3 }).join(), /between 0 and 1/);
  assert.match(validateWatermark({ text: 5 }).join(), /must be text/);
});

test('fill events are validated, and the text-layer rule names the layers that crowd the screen', () => {
  const t = (e) => validateEvents([{ id: 'f', t_in: 0, t_out: 5, ...e }], 10).errors.join();
  assert.match(t({ type: 'fill' }), /needs iso/);
  assert.match(t({ type: 'fill', iso: ['KEN'], role: 'pink' }), /unknown fill role pink/);
  assert.match(t({ type: 'fill', iso: ['KEN'], opacity: 2 }), /between 0 and 1/);
  assert.equal(t({ type: 'fill', iso: ['KEN'], role: 'compare', opacity: 0.5 }), '');
  assert.equal(t({ type: 'fill', polys: [[[[0, 0], [1, 0], [1, 1], [0, 0]]]] }), '');
  const crowd = [
    { id: 'hud', type: 'hud_title', label: 'A', sub: 'B', t_in: 0, t_out: 9 },
    ...['c1', 'c2', 'c3', 'c4'].map((id) => ({ id, type: 'caption', text: 'T', t_in: 1, t_out: 8 })),
  ];
  const msg = validateEvents(crowd, 10).errors.join();
  assert.match(msg, /6 text layers.*hud \(2\), c1, c2, c3, c4/);
  assert.match(msg, /Shorten one with hold or t_end/);
});
