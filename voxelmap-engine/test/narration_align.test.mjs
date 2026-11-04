import test from 'node:test';
import assert from 'node:assert/strict';
import { attachNarration } from '../lib/timeline.mjs';

const beat = (id, ...sentences) => ({ id, place: id, sentences });
const vo = (texts) => texts.map((text, k) => ({ start: k * 4, end: k * 4 + 3, text }));

test('a long voiceover is split by meaning, not by count, and every spoken sentence is kept', () => {
  const spec = { beats: [beat('Founding', 'Rome began as villages on the Tiber.'), beat('Carthage', 'Rome fought Carthage for Sicily.'), beat('Caesar', 'Caesar crossed the Rubicon.')] };
  const said = attachNarration(spec, vo([
    'Rome began as a few muddy villages.', 'The Tiber gave them a river crossing.', 'Nobody expected much.',
    'Then came Carthage, a sea power.', 'The war over Sicily lasted decades.', 'Carthage lost its fleet.',
    'Much later, Caesar marched south.', 'He crossed the Rubicon with one legion.']));
  assert.equal(said.length, 8);
  assert.deepEqual(said.map((s) => s.beat), [0, 0, 0, 1, 1, 1, 2, 2]);
  assert.equal(said[3].text, 'Then came Carthage, a sea power.');   // captions show what is said
});

test('beats never go backwards and none is left empty', () => {
  const spec = { beats: [beat('a', 'alpha one'), beat('b', 'bravo two'), beat('c', 'charlie three')] };
  const said = attachNarration(spec, vo(['charlie', 'bravo', 'alpha', 'nothing', 'more']));
  const beats = said.map((s) => s.beat);
  for (let k = 1; k < beats.length; k++) assert.ok(beats[k] >= beats[k - 1]);
  assert.deepEqual([...new Set(beats)], [0, 1, 2]);
});

test('fewer spoken sentences than beats keeps the one-to-one pairing', () => {
  const spec = { beats: [beat('a', 'x.'), beat('b', 'y.'), beat('c', 'z.')] };
  assert.deepEqual(attachNarration(spec, vo(['one', 'two'])).map((s) => s.beat), [0, 1]);
});
