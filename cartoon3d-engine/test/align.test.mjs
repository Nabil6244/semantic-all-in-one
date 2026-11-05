// node --test cartoon3d-engine/test/align.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { alignLines, fillMissing } from '../lib/align.mjs';
import { parseCsv, normalizeRows, buildLesson } from '../lib/lesson.mjs';

const said = (s, t = 0.5, step = 0.4) => s.split(' ').map((w, i) => ({ text: w, t0: +(t + i * step).toFixed(2), t1: +(t + i * step + 0.3).toFixed(2) }));

test('lines are found in a recording with a misheard word, a skipped word and extra chatter', () => {
  const lines = ["Let's count the stars. One, two, three!", 'Three stars! Yay!', 'Can you say blue?'];
  const words = [...said('okay so', 0.0), ...said("let's count the stars 1 two three", 1.0), ...said('three stars yeah', 5.0), ...said('can you say', 8.0)];
  const [a, b, c] = alignLines(lines, words);
  assert.equal(a.t0, 1.0); assert.equal(a.words.at(-1).t0, 3.4);          // "1" heard for "One", and the count's own "three"
  assert.equal(b.t0, 5.0);                                                  // the next line's "Three" is not borrowed
  assert.equal(c.t0, 8.0); assert.equal(c.words.length, 4);                 // "blue" never said: it still gets a time inside the line
});

test('a line missing from the recording sits between its neighbours, and lesson timing follows the recording', () => {
  const lines = ['Hello friend!', 'This line was never recorded.', 'Bye bye!'];
  const found = alignLines(lines, [...said('hello friend', 1.0), ...said('bye bye', 9.0)]);
  assert.equal(found[1], null);
  const timed = fillMissing(found, 12, lines);
  assert.ok(timed[1].t0 > found[0].t1 && timed[1].t1 < found[2].t0);
  const { beats } = normalizeRows(parseCsv('type,text\nsay,Hello friend!\nrepeat,This line was never recorded.\nsay,Bye bye!\n'));
  const L = buildLesson(beats, [], { timed, voiceDuration: 12 });
  assert.deepEqual(L.lines.map((l) => l.t0), timed.map((x) => +x.t0.toFixed(3)));
  assert.ok(L.duration >= 12.4);
  assert.ok(L.badges[0].t1 <= timed[2].t0);                                // "Your turn" ends before her next line
});
