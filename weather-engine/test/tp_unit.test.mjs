// Weather Teamplate's layout and timing maths (lib/wxu_tp_style.mjs): every card stays inside the frame and readable, words
// appear in order, the stat's phases, place tags flip below when the space above is taken, and tags step aside under cards.
import test from 'node:test';
import assert from 'node:assert/strict';
import { TP, keywordLayout, keywordPositions, wordIn, chapterProgress, tagRect, statPhase, compactRect, placeRect, pulse, shown } from '../lib/wxu_tp_style.mjs';
import plugins from '../lib/layers/tp_title.mjs';
import stat from '../lib/layers/tp_stat.mjs';
import tag from '../lib/layers/tp_tag.mjs';
import place from '../lib/layers/tp_place.mjs';

const measure = (s, px) => s.length * px * 0.72;   // a heavy sans, roughly

test('a short keyword title is one centred line, inside the frame', () => {
  const L = keywordLayout(['THE', 'PATH'], 1, measure);
  assert.equal(L.lines.length, 1);
  assert.equal(L.align, 'center');
  assert.equal(L.px, TP.keyword.px);
  const pos = keywordPositions(L);
  assert.ok(pos.every((w) => w.x >= 0 && w.x + w.w <= 1920 && w.y > 0 && w.y < 1080));
  assert.ok(Math.abs((pos[0].x + pos[1].x + pos[1].w) / 2 - 960) < 1);
});

test('a long title puts the key word on its own last line, left aligned, and never runs off the frame', () => {
  const words = 'LAKE HAS RISEN AND FALLEN FOR MILLENNIA'.split(' ');
  const L = keywordLayout(words, words.length - 1, measure);
  assert.ok(L.lines.length >= 2);
  assert.deepEqual(L.lines.at(-1).words.map((w) => w.text), ['MILLENNIA']);
  assert.ok(L.px >= TP.keyword.minPx);
  for (const w of keywordPositions(L)) assert.ok(w.x >= 0 && w.x + w.w <= 1920, `${w.text} at ${w.x}`);
});

test('words appear one after another; the chapter kicker leads its title', () => {
  assert.equal(wordIn(0, 0, 0), 0);
  assert.ok(wordIn(0.3, 0, 0) > 0.99);
  assert.equal(wordIn(0.2, 0, 1), 0);
  const p = chapterProgress(0.4, 0);
  assert.ok(p.kicker > 0.9 && p.title === 0);
  assert.equal(chapterProgress(2, 0).title, 1);
});

test('tags: black at the top centre, orange in the middle', () => {
  const b = tagRect('black', 200), o = tagRect('orange', 200);
  assert.ok(Math.abs(b.x + b.w / 2 - 960) < 1e-9 && b.y < 100);
  assert.ok(o.y > 400 && o.y < 540);
});

test('the stat counts big, types its label after the count, then settles top right', () => {
  const e = { big_in: 10, big_out: 16, count_s: 2 };
  assert.equal(statPhase(e, 9).phase, 'none');
  assert.equal(statPhase(e, 11).phase, 'big');
  assert.equal(statPhase(e, 11).typed, 0);
  assert.equal(statPhase(e, 14).typed, 1);
  assert.equal(statPhase(e, 17).phase, 'compact');
  const r = compactRect(300);
  assert.ok(r.x + r.w <= 1920 - TP.stat.right + 1e-9 && r.y < 100);
});

test('a place tag goes below its point when the space above is taken', () => {
  const up = placeRect(900, 500, 200);
  assert.equal(up.side, 'above');
  const down = placeRect(900, 500, 200, [{ x: 0, y: 380, w: 1920, h: 80 }]);
  assert.equal(down.side, 'below');
  assert.ok(placeRect(900, 60, 200).side === 'below');
  const p = pulse(0.8, 0);
  assert.ok(p.r > TP.place.dot && p.r <= TP.place.ring && p.a > 0 && p.a < 1);
});

test('tags step aside while a card is up', () => {
  assert.equal(shown([[10, 13]], 5), 1);
  assert.equal(shown([[10, 13]], 11), 0);
  assert.ok(shown([[10, 13]], 9.85) > 0 && shown([[10, 13]], 9.85) < 1);
  assert.equal(shown(undefined, 11), 1);
});

test('the plugins name what is missing', () => {
  assert.deepEqual(plugins.validate({ kind: 'keyword', words: ['A', 'B'], accent: 1 }), []);
  assert.match(plugins.validate({ kind: 'keyword', words: ['A'], accent: 3 })[0], /accent/);
  assert.match(plugins.validate({ kind: 'chapter' })[0], /title/);
  assert.match(stat.validate({ value: 2.5, label: 'X', big_in: 1, big_out: 2 })[0], /whole/);
  assert.match(tag.validate({ text: 'X', tone: 'green' })[0], /tone/);
  assert.match(place.validate({ text: 'X' })[0], /lon and lat/);
});
