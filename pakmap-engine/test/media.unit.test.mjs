import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { cardState, clipFrame, crossfadeAt } from '../lib/anim.mjs';
import { cardSize, cardRect, cardLabelRect, stripLayout, stickerRect, coverCrop, zoneLayout, applyPos, statLayout } from '../lib/layout.mjs';
import { validateEvents, freezeWindows, mediaRefs, mediaKey } from '../lib/events.mjs';
import { createCamera } from '../lib/camera.mjs';
import { prepareMedia, kindOf } from '../lib/media.mjs';
import { DataError } from '../lib/datasets.mjs';
import { GEOM, TIMING } from '../lib/style.mjs';

const measure = (text, px) => text.length * px * 0.66;
const hasFfmpeg = spawnSync('ffmpeg', ['-version']).status === 0;

test('photo card entry: starts at 115 % and 40 % opacity, settles in 0.17 s, no border on the first frame', () => {
  const a = cardState(1.0, 1.0, 5);
  assert.ok(Math.abs(a.scale - 1.15) < 1e-9 && Math.abs(a.alpha - 0.4) < 1e-9 && a.border === 0);
  assert.ok(a.dx > 0 && a.dy < 0, 'arrives from slightly up and to the right');
  const done = cardState(1.0 + TIMING.cardIn, 1.0, 5);
  assert.ok(Math.abs(done.scale - 1) < 1e-9 && Math.abs(done.alpha - 1) < 1e-9 && done.border === 1 && done.dx === 0);
  let prev = 1.15;
  for (let t = 1.0; t <= 1.17; t += 0.01) { const s = cardState(t, 1.0, 5).scale; assert.ok(s <= prev + 1e-9, 'scale only shrinks into place'); prev = s; }
});

test('photo card exit: a plain fade over 0.45 s, no shrink and no slide', () => {
  const mid = cardState(5 - 0.225, 1.0, 5), end = cardState(4.999, 1.0, 5);
  assert.ok(mid.alpha > 0.4 && mid.alpha < 0.6, `half faded (${mid.alpha})`);
  assert.ok(Math.abs(mid.scale - 1) < 1e-9); assert.equal(mid.dx, 0); assert.equal(mid.dy, 0);
  assert.ok(end.alpha < 0.01);
  assert.equal(cardState(5, 1.0, 5).alpha, 0);
  assert.equal(cardState(0.9, 1.0, 5).alpha, 0);
});

test('clip frames loop or hold the last frame; crossfade swaps images on a schedule', () => {
  assert.equal(clipFrame(1, 1, 30, 60, false), 0);
  assert.equal(clipFrame(2, 1, 30, 60, false), 30);
  assert.equal(clipFrame(9, 1, 30, 60, false), 59, 'holds the last frame');
  assert.equal(clipFrame(9, 1, 30, 60, true), (8 * 30) % 60, 'loops');
  assert.deepEqual(crossfadeAt(1.5, 1, 2, 3), { from: 0, to: 0, mix: 0 });
  const x = crossfadeAt(4.25, 1, 2, 3);
  assert.equal(x.from, 0); assert.equal(x.to, 1); assert.ok(x.mix > 0.4 && x.mix < 0.6);
  assert.deepEqual(crossfadeAt(5, 1, 2, 3), { from: 1, to: 1, mix: 0 });
  assert.deepEqual(crossfadeAt(5, 1, 1, 3), { from: 0, to: 0, mix: 0 });
});

test('card sizes and anchors follow the references (420 x 303 landscape, 63 px from the right edge)', () => {
  assert.deepEqual(cardSize({}), { w: 420, h: 303 });
  assert.deepEqual(cardSize({ shape: 'portrait' }), { w: 260, h: 360 });
  assert.equal(cardSize({ w: 210 }).h, Math.round((210 * 303) / 420));
  const tr = cardRect({ anchor: 'tr' });
  assert.equal(tr.x + tr.w, 1920 - GEOM.card.margin.right);
  assert.equal(tr.y, GEOM.card.margin.top);
  const bl = cardRect({ anchor: 'bl' });
  assert.equal(bl.x, GEOM.card.margin.left);
  assert.equal(bl.y + bl.h, 1080 - GEOM.card.margin.bottom);
  const c = cardRect({ anchor: 'center', offset: [10, 0] });
  assert.equal(c.x, Math.round((1920 - 420) / 2) + 10);
  assert.equal(c.y, Math.round((1080 - 303) / 2));
  const ml = cardRect({ anchor: 'ml' }), mr = cardRect({ anchor: 'mr' });
  assert.equal(ml.x, GEOM.card.margin.left); assert.equal(mr.x + mr.w, 1920 - GEOM.card.margin.right); assert.equal(ml.y, Math.round((1080 - 303) / 2));
});

test('card label: a 42 px high yellow chip centred 6 px under the card', () => {
  const card = { x: 100, y: 200, w: 420, h: 303 }, L = cardLabelRect(card, 'NAIROBI', measure);
  assert.equal(L.h, 42); assert.equal(L.y, 200 + 303 + 6);
  assert.ok(Math.abs(L.x + L.w / 2 - 310) <= 1);
});

test('filmstrip: cards shrink as they multiply, like the references (3 cards 420 wide, 6 cards 240 wide on a 255 pitch)', () => {
  const three = stripLayout(3), six = stripLayout(6), seven = stripLayout(7);
  assert.equal(three[0].w, 420);
  assert.ok(Math.abs(three[0].x - 300) <= 6, `3 cards start near x=300 (${three[0].x})`);
  assert.ok(Math.abs(six[0].w - 240) <= 1, `6 cards ${six[0].w} wide`);
  assert.ok(Math.abs(six[1].x - six[0].x - 256) <= 2, 'pitch');
  assert.ok(seven[0].w < six[0].w);
  assert.ok(six.every((r) => r.x >= 0 && r.x + r.w <= 1920));
  assert.ok(Math.abs(six[0].h / six[0].w - 0.7) < 0.01, 'aspect about 1.43');
  assert.equal(new Set(six.map((r) => r.y)).size, 1, 'one row');
  assert.ok(stripLayout(6, { align: 'left' })[0].x < stripLayout(6, { align: 'right' })[0].x);
  assert.throws(() => stripLayout(2), /3-7 cards/);
  assert.throws(() => stripLayout(8), /3-7 cards/);
});

test('sticker: 42 % of the frame height by default, anchored by its bottom-centre; cover crop keeps the aspect', () => {
  const r = stickerRect({ x: 960, y: 700, aspect: 0.5 });
  assert.equal(r.h, Math.round(1080 * 0.42)); assert.equal(r.y + r.h, 700); assert.ok(Math.abs(r.x + r.w / 2 - 960) <= 1);
  assert.equal(stickerRect({ x: 0, y: 500, aspect: 1, heightFrac: 0.5 }).h, 540);
  const c = coverCrop(1600, 900, 420, 303);
  assert.ok(Math.abs(c.sw / c.sh - 420 / 303) < 1e-9);
  assert.ok(c.sx > 0 && c.sy === 0);
});

test('zone label is a 52 px chip centred on its point; a stat chip can be placed anywhere with pos', () => {
  const z = zoneLayout({ x: 500, y: 400, text: 'TURKANA' }, measure);
  assert.equal(z.h, 52); assert.equal(z.y + 26, 400); assert.ok(Math.abs(z.x + z.w / 2 - 500) <= 1);
  const s = applyPos(statLayout({ anchor: 'br', number: '6,000+ / KM', sub: 'NAIROBI' }, measure), { x: 1195, y: 171 });
  assert.equal(s.x, 1195); assert.equal(s.y, 171);
  assert.equal(s.number.baseline - s.y, statLayout({ anchor: 'br', number: '6,000+ / KM', sub: 'NAIROBI' }, measure).number.baseline - statLayout({ anchor: 'br', number: '6,000+ / KM', sub: 'NAIROBI' }, measure).y);
});

const E = (o) => ({ id: o.id, t_in: 0, t_out: 5, ...o });
test('timeline rules: media layers need their files, shapes and positions', () => {
  const t = (e) => validateEvents([E({ id: 'x', ...e })], 10).errors.join();
  assert.match(t({ type: 'pip' }), /needs media/);
  assert.equal(t({ type: 'pip', media: 'a.jpg', anchor: 'tr', shape: 'square' }), '');
  assert.match(t({ type: 'pip', media: 'a.jpg', anchor: 'top' }), /anchor must be one of/);
  assert.match(t({ type: 'pip', media: 'a.jpg', shape: 'tall' }), /shape must be one of/);
  assert.match(t({ type: 'pip', media: 'a.jpg', leader: { lon: 1 } }), /leader needs lon and lat/);
  assert.match(t({ type: 'filmstrip', cards: [{ media: 'a' }, { media: 'b' }] }), /3-7 cards \(got 2\)/);
  assert.match(t({ type: 'filmstrip', cards: [{ media: 'a' }, { media: 'b' }, {}] }), /card 3 needs media/);
  assert.match(t({ type: 'sticker', media: 'a.png' }), /lon and lat/);
  assert.equal(t({ type: 'sticker', media: 'a.png', at: { x: 100, y: 200 } }), '');
  assert.match(t({ type: 'media_full' }), /needs media/);
});

test('timeline rules: a sticker never shares the screen with a photo card or filmstrip; one interlude at a time', () => {
  const stk = E({ id: 's', type: 'sticker', media: 's.png', lon: 1, lat: 1, t_in: 2, t_out: 6 });
  assert.match(validateEvents([E({ id: 'p', type: 'pip', media: 'p.jpg', t_in: 0, t_out: 3 }), stk], 10).errors.join(), /sticker and a photo card/);
  assert.match(validateEvents([E({ id: 'f', type: 'filmstrip', cards: [{ media: 'a' }, { media: 'b' }, { media: 'c' }], t_in: 0, t_out: 3 }), stk], 10).errors.join(), /sticker and a photo card/);
  assert.deepEqual(validateEvents([E({ id: 'p', type: 'pip', media: 'p.jpg', t_in: 0, t_out: 2 }), stk], 10).errors, []);
  const m = (id, a, b) => E({ id, type: 'media_full', media: 'x.mp4', t_in: a, t_out: b });
  assert.match(validateEvents([m('a', 0, 4), m('b', 3, 6)], 10).errors.join(), /two media_full/);
  assert.deepEqual(freezeWindows([m('b', 6, 8), m('a', 1, 3)]), [[1, 3], [6, 8]]);
});

test('camera holds still under full-screen media: same position before and after, drift included', () => {
  const cfg = { camera: { start: { lon: 37, lat: 1, zoom: 6 }, drift: { pct_per_s: 0.8, heading_deg: 70 }, moves: [] }, width: 1920, height: 1080, duration: 20 };
  const frozen = createCamera({ ...cfg, freeze: [[8, 12]] }), free = createCamera(cfg);
  const a = frozen.at(8), b = frozen.at(12);
  assert.ok(Math.abs(a.lon - b.lon) < 1e-9 && Math.abs(a.lat - b.lat) < 1e-9 && a.zoom === b.zoom, 'identical');
  assert.ok(Math.abs(free.at(8).lon - free.at(12).lon) > 1e-4, 'without the freeze it would have drifted');
  const c = frozen.at(14), d = frozen.at(15);
  assert.ok(Math.abs(c.lon - d.lon) > 1e-5, 'and it carries on drifting afterwards');
  assert.ok(Math.abs(frozen.at(3).lon - free.at(3).lon) < 1e-12, 'before the window nothing changes');
});

test('a camera move cannot run under full-screen media (the map is held still there)', () => {
  const cam = { start: { lon: 0, lat: 0, zoom: 3 }, moves: [{ type: 'push_in', t: 5, dur: 4, to: { zoom: 5 } }] };
  assert.throws(() => createCamera({ camera: cam, width: 1920, height: 1080, duration: 20, freeze: [[7, 10]] }), /runs under full-screen media/);
  assert.doesNotThrow(() => createCamera({ camera: cam, width: 1920, height: 1080, duration: 20, freeze: [[9, 12]] }));
});

test('media references: every file an event uses, with the size the frames need', () => {
  assert.deepEqual(mediaRefs({ type: 'pip', media: 'a.jpg' }).map((r) => [r.path, r.maxW]), [['a.jpg', 900]]);
  assert.deepEqual(mediaRefs({ type: 'pip', images: ['a.jpg', 'b.jpg'] }).map((r) => r.path), ['a.jpg', 'b.jpg']);
  assert.deepEqual(mediaRefs({ type: 'filmstrip', cards: [{ media: 'a' }, { media: 'b', start_s: 2 }] }).map((r) => [r.path, r.start_s]), [['a', 0], ['b', 2]]);
  assert.equal(mediaRefs({ type: 'media_full', media: 'c.mp4' })[0].maxW, 1920);
  assert.deepEqual(mediaRefs({ type: 'stat' }), []);
  assert.equal(mediaKey('a.mp4', 3), 'a.mp4@3');
  assert.equal(kindOf('x.PNG'), 'image'); assert.equal(kindOf('x.mov'), 'video'); assert.equal(kindOf('x.pdf'), null);
});

test('media preparation: pictures are indexed, clips become frames, bad files give clear advice', { skip: !hasFfmpeg }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-media-'));
  spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:size=320x180:rate=30:duration=2', '-pix_fmt', 'yuv420p', path.join(dir, 'c.mp4')]);
  spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:size=64x64', '-frames:v', '1', path.join(dir, 'p.png')]);
  const spec = { fps: 10, events: [
    { id: 'a', type: 'pip', t_in: 0, t_out: 1.5, media: 'p.png' },
    { id: 'b', type: 'media_full', t_in: 0, t_out: 1.5, media: 'c.mp4' },
  ] };
  const { index, files } = prepareMedia(spec, { baseDir: dir });
  assert.equal(index['p.png@0'].kind, 'image');
  assert.equal(index['c.mp4@0'].kind, 'video');
  assert.ok(index['c.mp4@0'].count >= 15 && index['c.mp4@0'].count <= 17, `frames: ${index['c.mp4@0'].count}`);
  assert.ok(fs.existsSync(path.join(files[index['c.mp4@0'].id].dir, '00001.jpg')));
  assert.throws(() => prepareMedia({ fps: 10, events: [{ id: 'z', type: 'pip', t_in: 0, t_out: 1, media: 'nope.jpg' }] }, { baseDir: dir }), /picture not found: nope.jpg/);
  assert.throws(() => prepareMedia({ fps: 10, events: [{ id: 'z', type: 'pip', t_in: 0, t_out: 1, media: 'doc.pdf' }] }, { baseDir: dir }), /not a picture or video file/);
  fs.writeFileSync(path.join(dir, 'broken.mp4'), 'not a video');
  assert.throws(() => prepareMedia({ fps: 10, events: [{ id: 'z', type: 'media_full', t_in: 0, t_out: 1, media: 'broken.mp4' }] }, { baseDir: dir }), DataError);
});
