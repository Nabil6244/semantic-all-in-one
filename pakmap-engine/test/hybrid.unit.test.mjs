// Hybrid Map engine options: pure logic (lib/hybrid.mjs) and the validator rules around footage.
import test from 'node:test';
import assert from 'node:assert/strict';
import { footageWindows, pausedSpan, shiftedEvent, footageAlpha, kenBurnsScale, resolveKenBurns, fitRate, fitFrame } from '../lib/hybrid.mjs';
import { validateEvents } from '../lib/events.mjs';

const full = (id, a, b, extra = {}) => ({ id, type: 'media_full', t_in: a, t_out: b, media: 'x.png', ...extra });
const marker = (id, a, b) => ({ id, type: 'marker', t_in: a, t_out: b, lon: 0, lat: 0, label: 'X' });

test('footage windows are merged and sorted', () => {
  assert.deepEqual(footageWindows([full('b', 8, 10), full('a', 3, 5), full('c', 4.5, 6.5), marker('m', 0, 20)]), [[3, 6.5], [8, 10]]);
  assert.deepEqual(footageWindows([marker('m', 0, 1)]), []);
});

test('pausedSpan counts only the overlap with the windows', () => {
  const w = [[3, 5], [8, 10]];
  assert.equal(pausedSpan(w, 0, 2), 0);
  assert.equal(pausedSpan(w, 2.5, 4), 1);
  assert.equal(pausedSpan(w, 0, 20), 4);
  assert.equal(pausedSpan(w, 6, 7), 0);
});

test('without windows the very same event object comes back (PakMap is untouched)', () => {
  const e = marker('m', 1, 9);
  assert.equal(shiftedEvent(e, 6, []), e);
  assert.equal(shiftedEvent(e, 6, undefined), e);
});

test('a layer\'s start moves later by the time spent under footage; its end does not move', () => {
  const w = [[3, 5]];
  const e = marker('m', 2, 9);
  assert.equal(shiftedEvent(e, 2.5, w).t_in, 2);              // before the footage: untouched
  assert.equal(shiftedEvent(e, 4, w).t_in, 3);                // under it: 1 s of the 2 s window has passed
  assert.equal(shiftedEvent(e, 6, w).t_in, 4);                // after it: the whole 2 s
  assert.equal(shiftedEvent(e, 6, w).t_out, 9);               // the planned end is narration time
  assert.equal(shiftedEvent(marker('late', 6, 9), 7, w).t_in, 6); // started after the footage: nothing to pause
});

test('the animation clock stops exactly at footage entry and resumes from the same point', () => {
  const w = [[3, 5]];
  const e = marker('m', 2.7, 9);
  const elapsed = (t) => t - shiftedEvent(e, t, w).t_in; // what every entrance animation measures
  assert.ok(Math.abs(elapsed(3) - 0.3) < 1e-9);
  assert.ok(Math.abs(elapsed(4.2) - 0.3) < 1e-9);          // frozen under footage
  assert.ok(Math.abs(elapsed(5) - 0.3) < 1e-9);            // same state at the moment the footage ends
  assert.ok(Math.abs(elapsed(5.4) - 0.7) < 1e-9);          // then it carries on
});

test('footage is never time-shifted (it plays in real time)', () => {
  const f = full('f', 3, 5);
  assert.equal(shiftedEvent(f, 4, [[3, 5]]), f);
});

test('footage opacity: dissolve in and out; a clip that the next one dissolves over stays opaque', () => {
  const a = full('a', 3, 5), b = full('b', 4.5, 7, { xfade_prev: true });
  const evs = [a, b];
  assert.equal(footageAlpha(a, 3, evs, 0.5), 0);
  assert.ok(Math.abs(footageAlpha(a, 3.25, evs, 0.5) - 0.5) < 1e-9);
  assert.equal(footageAlpha(a, 4.7, evs, 0.5), 1);          // handing over: opaque
  assert.equal(footageAlpha(a, 4.99, evs, 0.5), 1);
  assert.ok(Math.abs(footageAlpha(b, 4.75, evs, 0.5) - 0.5) < 1e-9); // the second dissolves in over it
  assert.ok(Math.abs(footageAlpha(b, 6.75, evs, 0.5) - 0.5) < 1e-9); // and out to the map at the end
  assert.equal(footageAlpha(full('solo', 3, 5), 4.9, [full('solo', 3, 5)], 0.5) < 0.25, true); // ordinary fade out
});

test('ken burns: no flag, no zoom; with the flag a steady push-in over the time on screen', () => {
  assert.equal(kenBurnsScale(full('f', 0, 10), 5), 1);
  const f = full('f', 0, 10, { kenburns: true });
  assert.equal(kenBurnsScale(f, 0), 1);
  assert.ok(Math.abs(kenBurnsScale(f, 5) - 1.03) < 1e-9);
  assert.ok(Math.abs(kenBurnsScale(f, 10) - 1.06) < 1e-9);
  assert.ok(Math.abs(kenBurnsScale({ ...f, kenburns_zoom: 0.1 }, 10) - 1.1) < 1e-9);
});

test('validator: two overlapping clips are an error unless the second hands over from the first', () => {
  const ok = (events) => validateEvents(events, 20).errors;
  assert.match(ok([full('a', 3, 6), full('b', 5, 8)]).join(' '), /two media_full events overlap/);
  assert.deepEqual(ok([full('a', 3, 5.5), full('b', 5, 8, { xfade_prev: true })]), []);
  assert.match(ok([full('a', 3, 6), full('b', 5, 8, { xfade_prev: true }), full('c', 5.5, 9, { xfade_prev: true })]).join(' '), /two media_full events overlap/);
  assert.deepEqual(ok([full('a', 3, 5), full('b', 5.5, 8)]), []);
});

test('validator: the footage flags must be booleans', () => {
  const errs = validateEvents([full('a', 3, 5, { cover_ui: 'yes', kenburns: 1 })], 20).errors.join(' ');
  assert.match(errs, /cover_ui must be true or false/);
  assert.match(errs, /kenburns must be true or false/);
  assert.deepEqual(validateEvents([full('a', 3, 5, { cover_ui: true, kenburns: true, xfade_prev: false })], 20).errors, []);
});

test('ken burns "auto" pushes in on a still and never on a video', () => {
  const f = full('f', 0, 10, { kenburns: 'auto', kenburns_zoom: 0.1 });
  assert.ok(Math.abs(kenBurnsScale(resolveKenBurns(f, { kind: 'image' }), 10) - 1.1) < 1e-9);
  assert.equal(kenBurnsScale(resolveKenBurns(f, { kind: 'video' }), 10), 1);
  assert.equal(kenBurnsScale(resolveKenBurns(f, null), 10), 1);
  assert.equal(kenBurnsScale(resolveKenBurns(full('g', 0, 10, {}), { kind: 'image' }), 10), 1); // a PakMap event (no flag) never moves
  assert.deepEqual(validateEvents([full('a', 3, 5, { kenburns: 'auto' })], 20).errors, []);
  assert.match(validateEvents([full('a', 3, 5, { kenburns: 'sometimes' })], 20).errors.join(' '), /kenburns must be true or false/);
});

test('a clip shorter than its slot is slowed to fit (not below half speed), then ping-pongs: it never jumps back to its first frame', () => {
  assert.equal(fitRate(10, 8), 1);                      // long enough: untouched
  assert.ok(Math.abs(fitRate(8, 12.4) - 8 / 12.4) < 1e-9); // the 8 s clip in a 12.4 s slot plays at about 0.65x
  assert.equal(fitRate(2, 12), 0.5);                    // never slower than half speed
  assert.equal(fitRate(5, 0), 1);
  // 2 s of material at 30 fps = 61 frames, 12 s slot at the 0.5 floor: covers 4 s, then back and forth
  const seq = Array.from({ length: 12 * 30 }, (_, i) => fitFrame(i / 30, 0, 30, 61, 0.5));
  assert.equal(seq[0], 0);
  assert.ok(seq.every((f, i) => i === 0 || Math.abs(f - seq[i - 1]) <= 1), 'neighbouring output frames are neighbouring clip frames: no jump anywhere');
  assert.ok(seq.some((f, i) => i > 0 && f < seq[i - 1]), 'it does turn round when the material runs out');
  assert.ok(seq.every((f) => f >= 0 && f < 61));
  const slow = Array.from({ length: 12 * 30 }, (_, i) => fitFrame(i / 30, 0, 30, 61, 1)); // the old behaviour for contrast: modulo restarts jump from 60 to 0
  assert.ok(new Set(slow).size === 61);
  assert.deepEqual(validateEvents([full('a', 3, 5, { fit: 'slow' })], 20).errors, []);
  assert.match(validateEvents([full('a', 3, 5, { fit: 'fast' })], 20).errors.join(' '), /fit must be "slow"/);
});
