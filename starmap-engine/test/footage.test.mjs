// Phase 3: footage beats. Map time freezes under footage and resumes; layer starts/ends move off the footage the Hybrid
// way; dissolves are centred on the boundaries; clips are cut lazily and deleted after their beat.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { planFootage, clipFrameIndex, extractPlan, kenBurnsAt } from '../lib/footage.mjs';
import { progressAt } from '../lib/timing.mjs';
import { createClock } from '../lib/clock.mjs';
import { createCutter, cardClips } from '../cutter.mjs';
import { defaultLayers } from '../lib/layers.mjs';

const SPEC = { fps: 30, width: 320, height: 180, footage: [
  { id: 'a', image: 'x.jpg', start: 10, end: 16 },
  { id: 'b', file: 'clip.mp4', start: 16, end: 20, in_s: 2 },          // straight after a: dissolves over a, not the map
  { id: 'c', image: 'y.jpg', start: 30, end: 34, transition_out: 'cut' }] };

test('map time stops under footage and carries on after it', () => {
  const fp = planFootage(SPEC);
  assert.deepEqual(fp.problems, []);
  assert.equal(fp.mu(5), 5);
  assert.equal(fp.mu(10), 10); assert.equal(fp.mu(13), 10); assert.equal(fp.mu(20), 10.001);   // a + b: one frozen span; exit state after its midpoint
  assert.ok(Math.abs(fp.mu(25) - 15.001) < 1e-9); assert.ok(Math.abs(fp.mu(40) - 26.002) < 1e-9);
  // a universe fast-forward that spans the footage pauses and resumes: same date at entry and at return
  const keys = { keys: [{ t: 8, utc: '1969-07-16T16:00:00Z' }, { t: 24, utc: '1969-07-19T17:00:00Z' }] };
  const clock = createClock(fp.mapClock(keys)), at = (t) => +clock.utc(fp.mu(t));
  assert.ok(Math.abs(at(10) - at(20)) < 180e3, 'a few minutes of universe time at most (the 1 ms midpoint cut of a 3-day fast-forward)');
  assert.ok(at(20.5) > at(20));
  assert.equal(clock.utc(fp.mu(24)).toISOString(), '1969-07-19T17:00:00.000Z', 'keys still land at their narration time');
  // a jump keyed at the footage's start and end happens at its midpoint, while the map is hidden
  const jump = createClock(fp.mapClock({ keys: [{ t: 10, utc: '1969-07-16T00:00:00Z' }, { t: 20, utc: '1969-07-20T00:00:00Z' }] }));
  assert.equal(jump.utc(fp.mu(14.9)).toISOString(), '1969-07-16T00:00:00.000Z');
  assert.equal(jump.utc(fp.mu(15.1)).toISOString(), '1969-07-20T00:00:00.000Z');
  // a camera move spanning the footage is paused, not run under it
  const cam = fp.mapCamera({ moves: [{ t: 9, dur: 4, to: {} }, { t: 25, dur: 2, to: {} }] });
  assert.deepEqual(cam.moves.map((m) => [m.t, m.dur]), [[9, 4], [15.001, 2]], '1 s before the footage, 3 s after it');
  const tight = planFootage({ ...SPEC, camera: { moves: [{ t: 9, dur: 4, to: {} }, { t: 22, dur: 2, to: {} }] } });
  assert.deepEqual(tight.mapCamera({ moves: [{ t: 9, dur: 4 }, { t: 22, dur: 2 }] }).moves.map((m) => [m.t, +m.dur.toFixed(3)]), [[9, 3.001], [12.001, 2]]);
  assert.match(tight.warnings.join(), /move at 9 s is cut short/);
  // a reveal that the footage interrupts is as far along on return as it was at entry
  assert.ok(Math.abs(progressAt({ t0: 8, t1: 24 }, 10, fp.mu) - progressAt({ t0: 8, t1: 24 }, 20, fp.mu)) < 1e-3);
});

test('dissolves are centred on the boundaries; footage after footage never shows the map', () => {
  const fp = planFootage(SPEC);
  assert.equal(fp.mapAlpha(9.7), 1);
  assert.equal(fp.mapAlpha(10), 0.5);                          // halfway through the dissolve at the boundary
  assert.equal(fp.mapAlpha(10.3), 0);
  for (let t = 10.3; t <= 19.7; t += 0.1) assert.ok(fp.mapAlpha(t) < 1e-9, `map showed at ${t.toFixed(1)}`);
  const at16 = fp.coverage(16);
  assert.deepEqual(at16.map((x) => [x.beat.id, x.alpha]), [['a', 1], ['b', 0.5]]);   // b dissolves in over a
  assert.equal(fp.mapAlpha(20), 0.5); assert.equal(fp.mapAlpha(20.3), 1);
  assert.equal(fp.mapAlpha(33.99), 0); assert.equal(fp.mapAlpha(34.01), 1);         // a cut
});

test('layers: starts and ends move off the footage (Hybrid rules); over-footage layers are untouched', () => {
  const fp = planFootage(SPEC);
  assert.deepEqual(fp.adjustLayer({ start: 2, end: 10.1 }), { start: 2, end: 10.1 }, 'leaves under the dissolve: unchanged');
  assert.equal(fp.adjustLayer({ start: 2, end: 14 }).end, 20 + 0.25 + 0.8, 'held until the map is back, plus grace');
  const late = fp.adjustLayer({ start: 12, end: 28 });
  assert.equal(late.start, 20); assert.ok(late.fade_in >= 0.5, 'appears with the map');
  assert.deepEqual(fp.adjustLayer({ start: 12, end: 14, over_footage: true }), { start: 12, end: 14, over_footage: true });
  // the app's channel name becomes a layer
  assert.equal(defaultLayers({ watermark: { text: 'My Channel' } }).at(-1).type, 'channel_name');
  assert.equal(defaultLayers({ layers: [], watermark: { text: 'x', enabled: false } }).length, 0);
});

test('mistakes are caught before rendering', () => {
  const bad = planFootage({ fps: 30, footage: [
    { id: 'short', image: 'a.jpg', start: 1, end: 2.5 },
    { id: 'over', file: 'b.mp4', start: 2, end: 6 },
    { id: 'none', start: 8, end: 12 },
    { id: 'gif', file: 'c.gif', start: 13, end: 18 },
    { id: 'tr', image: 'd.jpg', start: 20, end: 25, transition_in: 'wipe' }] });
  const all = bad.problems.join(' | ');
  for (const want of [/short: 1.5 s is too short/, /short and over overlap/, /none: no clip/, /gif: unsupported file type/, /tr: transition_in must be/])
    assert.match(all, want);
  const warn = planFootage({ fps: 30, footage: [{ image: 'a.jpg', start: 1, end: 4 }], clock: { keys: [{ t: 2, utc: '2000-01-01T00:00:00Z' }] } }).warnings.join(' | ');
  assert.match(warn, /only 3.0 s on screen/); assert.match(warn, /clock key at 2 s is under footage/);
});

test('clip frames: in point, speed, dissolve lead-in; Ken Burns drifts steadily', () => {
  const fp = planFootage(SPEC), b = fp.beats.find((x) => x.id === 'b');
  const ex = extractPlan(b, 30);
  assert.equal(ex.fromS, 1.75);                               // the dissolve-in starts a quarter second before the in point
  assert.equal(clipFrameIndex(b, 16, 30), 8);                 // in_s 2 is 0.25 s after fromS
  assert.equal(clipFrameIndex(b, 17, 30), 38);
  const fast = planFootage({ fps: 30, footage: [{ file: 'v.mp4', start: 0, end: 5, speed: 2 }] }).beats[0];
  assert.equal(clipFrameIndex(fast, 1, 30) - clipFrameIndex(fast, 0, 30), 30, 'speed 2: two clip seconds per narration second at 15 frames each');
  const s = fp.beats.find((x) => x.id === 'a');
  assert.deepEqual(kenBurnsAt(s, s.t0), [0.5, 0.5, 1]);
  assert.ok(Math.abs(kenBurnsAt(s, (s.t0 + s.t1) / 2)[2] - 1.04) < 1e-9);
});

test('cutter: cuts a real clip only while its beat is near, holds the last frame, deletes it after', async (t) => {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return t.skip('ffmpeg not installed');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'starmap-test-'));
  const clip = path.join(dir, 'clip.mp4');
  spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=30:duration=2', '-pix_fmt', 'yuv420p', clip]);
  const spec = { fps: 30, width: 320, height: 180, footage: [{ id: 'c', file: 'clip.mp4', start: 5, end: 9 }] };   // 4 s beat, 2 s clip
  const cutter = createCutter({ spec, mediaDir: dir, tmpRoot: dir });
  try {
    assert.deepEqual(cutter.plan.problems, []);
    await cutter.ensure(1);
    assert.equal(cutter.frameFile(0, 0), null, 'not cut long before it is needed');
    await cutter.ensure(4.8);
    const f0 = cutter.frameFile(0, 0);
    assert.ok(fs.existsSync(f0));
    assert.equal(cutter.stats.frames, 60, 'the whole 2 s clip (it is shorter than the beat)');
    assert.equal(cutter.frameFile(0, 500), cutter.frameFile(0, 59), 'past the end: the last frame is held');
    const probe = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', f0]).stdout.toString().trim();
    assert.equal(probe, '320,180', 'scaled and cropped to the video size');
    await cutter.ensure(9.5);
    assert.ok(!fs.existsSync(f0), 'deleted once the beat is over');
    assert.equal(cutter.stats.deleted, 1);
    assert.match(createCutter({ spec: { ...spec, footage: [{ file: 'missing.mp4', start: 0, end: 4 }] }, mediaDir: dir, tmpRoot: dir }).plan.problems.join(), /file not found/);
  } finally {
    cutter.cleanup(); fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('video cards: cut up front at the card size, frame k for each moment, the last frame held', async (t) => {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return t.skip('ffmpeg not installed');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'starmap-test-'));
  spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=1920x1080:rate=30:duration=3', '-pix_fmt', 'yuv420p', path.join(dir, 'card.mp4')]);
  const spec = { fps: 30, width: 320, height: 180, footage: [],
    layers: [{ type: 'photo_card', image: 'still.jpg', start: 0, end: 2 }, { type: 'photo_card', video: 'card.mp4', start: 1, end: 2, in_s: 0.5 }] };
  assert.deepEqual(cardClips(spec), [{ i: 1, file: 'card.mp4', fromS: 0.5, durS: 2, rate: 30 }], 'only the clip card; card time plus a second');
  const cutter = createCutter({ spec, mediaDir: dir, tmpRoot: dir });
  try {
    await cutter.prepareCards();
    assert.equal(spec.layers[1].video_frames, 60, '2 s from 0.5 s at 30 fps');
    assert.equal(spec.layers[1].card_index, 1);
    const f0 = cutter.cardFrameFile(1, 0);
    assert.ok(fs.existsSync(f0));
    assert.equal(cutter.cardFrameFile(1, 999), cutter.cardFrameFile(1, 59), 'past the end: the last frame is held');
    const probe = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'stream=width', '-of', 'csv=p=0', f0]).stdout.toString().trim();
    assert.equal(probe, '960', 'small enough for a card');
  } finally {
    cutter.cleanup(); fs.rmSync(dir, { recursive: true, force: true });
  }
});
