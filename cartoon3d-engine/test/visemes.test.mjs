// node --test cartoon3d-engine/test/visemes.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { wordVisemes, visemeTrack } from '../lib/visemes.mjs';

test('words map to the expected mouth shapes', () => {
  assert.deepEqual(wordVisemes('Ball!'), ['PP', 'O', 'DD']);
  assert.deepEqual(wordVisemes('you'), ['U']);
  assert.deepEqual(wordVisemes('Can'), ['kk', 'aa', 'nn']);
  assert.ok(wordVisemes('Zebra').length > 0, 'unknown words still get shapes from spelling');
});

test('the track opens on speech, shuts in silence and closes the lips for b', () => {
  const words = [{ text: 'ball', t0: 0.5, t1: 1.0 }];
  const env = Array.from({ length: 60 }, (_, i) => (i >= 15 && i <= 30 ? 0.8 : 0));       // loud only while the word plays (30 fps)
  const V = visemeTrack(words, env, 30, 2, 30);
  assert.equal(V.frames.length, 60);
  const at = (t, n) => V.frames[Math.round(t * 30)][V.names.indexOf(n)];
  assert.ok(at(0.53, 'PP') > 50, 'lips closed just before "b" sounds (40 ms lead)');
  assert.ok(at(0.73, 'O') > 40, 'open on the vowel');
  for (const t of [0.1, 1.6, 1.9]) assert.ok(V.frames[Math.round(t * 30)].every((x) => x < 5), `shut at ${t}s`);
});
