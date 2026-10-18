import test from 'node:test';
import assert from 'node:assert/strict';
import { activeAt } from '../lib/events.mjs';
import { firstFrameAt, safeCuts, planSegments, remembersFirstFrame, frameCosts } from '../lib/segments.mjs';

test('firstFrameAt matches the frame test activeAt uses', () => {
  for (const fps of [24, 25, 30, 60]) {
    for (const t of [0, 0.1, 1 / 3, 13.82, 16.7, 22.78, 29.21, 100.0333]) {
      const i = firstFrameAt(t, fps);
      assert.ok(i / fps >= t, `${t}@${fps}`);
      assert.ok(i === 0 || (i - 1) / fps < t, `${t}@${fps}`);
    }
  }
});

test('only map-anchored cards, filmstrips and auto-side markers remember their first frame', () => {
  assert.equal(remembersFirstFrame({ type: 'pip' }), true);
  assert.equal(remembersFirstFrame({ type: 'pip', at: { lon: 1, lat: 2 } }), false);
  assert.equal(remembersFirstFrame({ type: 'filmstrip' }), true);
  assert.equal(remembersFirstFrame({ type: 'marker' }), true);
  assert.equal(remembersFirstFrame({ type: 'marker', side: 'left' }), false);
  assert.equal(remembersFirstFrame({ type: 'marker', dot: false }), false);
  for (const type of ['caption', 'stat', 'line', 'fill', 'media_full', 'hud_title']) assert.equal(remembersFirstFrame({ type }), false);
});

test('no cut ever splits a layer that remembers its first frame', () => {
  const fps = 30, total = 30 * 120;
  const events = [
    { id: 'p', type: 'pip', t_in: 13.82, t_out: 16.7 },
    { id: 'm', type: 'marker', t_in: 40, t_out: 75.5 },
    { id: 'f', type: 'filmstrip', t_in: 74, t_out: 80 },
    { id: 'c', type: 'caption', t_in: 0, t_out: 120 },
  ];
  const cuts = new Set(safeCuts(events, total, fps));
  for (let s = 1; s < total; s++) {
    const before = activeAt(events, (s - 1) / fps).filter(remembersFirstFrame).map((e) => e.id);
    const after = activeAt(events, s / fps).filter(remembersFirstFrame).map((e) => e.id);
    const split = before.some((id) => after.includes(id));
    assert.equal(cuts.has(s), !split, `frame ${s}`);
  }
  const segs = planSegments(events, total, fps, { targetS: 30, minS: 10 });
  assert.equal(segs[0].from, 0);
  assert.equal(segs[segs.length - 1].to, total);
  segs.forEach((g, k) => { if (k) assert.equal(g.from, segs[k - 1].to); if (k) assert.ok(cuts.has(g.from)); });
  // the marker (40-75.5 s) and filmstrip (74-80 s) hold the cut until 80 s
  assert.deepEqual(segs.map((g) => g.from / fps), [0, 30, 80, 110]);
});

test('segments depend only on the timings, so a changed picture keeps them', () => {
  const ev = (media) => [{ id: 'p', type: 'pip', media, t_in: 31, t_out: 33 }, { id: 'v', type: 'media_full', media: 'a.mp4', cover_ui: true, t_in: 50, t_out: 60 }];
  assert.deepEqual(planSegments(ev('a.jpg'), 3000, 30), planSegments(ev('b.jpg'), 3000, 30));
});

test('a short video is one segment, and the last short piece joins the one before', () => {
  assert.equal(planSegments([], 30 * 35, 30).length, 1);
  assert.deepEqual(planSegments([], 30 * 65, 30).map((g) => g.to - g.from), [900, 1050]);
});

test('frames that are only a full-screen video clip cost little (Hybrid only)', () => {
  const events = [{ type: 'media_full', media: 'x.mp4', cover_ui: true, t_in: 1, t_out: 3, dissolve_s: 0.5 }];
  const c = frameCosts({ fps: 10, hybrid: {}, events }, 40);
  assert.equal(c[5], 1);
  assert.ok(c[20] < 1);
  assert.equal(frameCosts({ fps: 10, events }, 40)[20], 1);
});
