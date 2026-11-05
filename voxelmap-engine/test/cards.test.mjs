import test from 'node:test';
import assert from 'node:assert/strict';
import { parseStory, MAX_CARDS } from '../lib/beats_csv.mjs';
import { buildTimeline } from '../lib/timeline.mjs';
import { cardRect, reservedBoxes, CARD_STYLES } from '../lib/hud.mjs';

const HEAD = 'row,id,date,place,lon,lat,rung,alt,heading,site,gap,text,extra\n';
const base = `${HEAD}plan,T,,,,,,,,,,,"{""world"":""x""}"\nchapter,c1,,,,,,,,,,One,\n` +
  'beat,b1,-0753-04,Rome,12.5,41.9,map,,,,,"The twins were raised by a wolf. They founded the city on the Palatine hill.",\n' +
  'beat,b2,-0753-05,Rome,12.5,41.9,map,,,,,"Romulus killed his brother Remus.",\n';
const card = (id, extra, label = 'A card') => `card,${id},,,12.5,41.9,,,,,,${label},"${extra.replace(/"/g, '""')}"\n`;

test('card rows join the beat they name, in any file order', () => {
  const spec = parseStory(base + card('b2', '{"asset":"a.jpg"}') + card('b1', '{"asset":"w.jpg","words":"founded the city"}'));
  assert.equal(spec.beats[0].cards.length, 1); assert.equal(spec.beats[1].cards.length, 1);
  assert.equal(spec.beats[0].cards[0].words, 'founded the city');
});
test('a card needs an existing beat, an asset, a valid anchor, and at most MAX_CARDS per beat', () => {
  assert.throws(() => parseStory(base + card('nope', '{"asset":"a.jpg"}')), /does not exist/);
  assert.throws(() => parseStory(base + card('b1', '{}')), /extra\.asset/);
  assert.throws(() => parseStory(base + card('b1', '{"asset":"a.jpg","anchor":"zz"}')), /anchor/);
  let rows = ''; for (let i = 0; i <= MAX_CARDS; i++) rows += card('b1', '{"asset":"a.jpg"}');
  assert.throws(() => parseStory(base + rows), /photo cards/);
});
test('a card appears on the sentence its words match, and stays inside its beat', () => {
  const spec = parseStory(base + card('b1', '{"asset":"w.jpg","words":"founded the city Palatine hill","hold":4}'));
  const sentences = [{ start: 1, end: 4, text: 'The twins were raised by a wolf.' }, { start: 5, end: 9, text: 'They founded the city on the Palatine hill.' }, { start: 10, end: 13, text: 'Romulus killed his brother Remus.' }];
  const tl = buildTimeline(spec, sentences);
  assert.equal(tl.cards.length, 1);
  assert.equal(tl.cards[0].t0, 5); assert.equal(tl.cards[0].t1, 9);
});
test('no words and no t: the card is spread inside the beat; a card with no room is dropped, never an error', () => {
  const spec = parseStory(base + card('b1', '{"asset":"w.jpg"}') + card('b2', '{"asset":"r.jpg","hold":5}'));
  const sentences = [{ start: 1, end: 9, text: 'The twins were raised by a wolf. They founded the city on the Palatine hill.' }, { start: 10, end: 10.8, text: 'Romulus killed his brother Remus.' }];
  const tl = buildTimeline(spec, sentences);
  assert.ok(tl.cards.length >= 1);
  for (const c of tl.cards) assert.ok(c.t1 > c.t0);
});
test('two cards on screen together take different sides', () => {
  const spec = parseStory(base + card('b1', '{"asset":"a.jpg","t":1,"hold":6}') + card('b1', '{"asset":"b.jpg","t":3,"hold":6}'));
  const tl = buildTimeline(spec, [{ start: 0, end: 9, text: 'The twins were raised by a wolf.' }, { start: 9.5, end: 12, text: 'Romulus killed his brother Remus.' }]);
  assert.equal(tl.cards.length, 2); assert.notEqual(tl.cards[0].anchor, tl.cards[1].anchor);
});
const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
test('the free sides never cover the date panel, caption log, hotbar, item bar or museum inset', () => {
  for (const [W, H] of [[1280, 720], [1920, 1080], [3840, 2160]]) {
    const R = reservedBoxes(W, H);
    for (const [iw, ih] of [[1600, 900], [900, 1200], [1000, 1000], [2400, 800]]) {
    for (const kind of Object.keys(CARD_STYLES)) {
      const ml = cardRect('ml', W, H, iw, ih, kind), mr = cardRect('mr', W, H, iw, ih, kind);
      for (const k of ['date', 'captions', 'bottom']) assert.ok(!hit(ml, R[k]), `ml ${W}x${H} ${iw}x${ih} hits ${k}`);
      for (const k of ['museum', 'bottom', 'items']) assert.ok(!hit(mr, R[k]), `mr ${W}x${H} ${iw}x${ih} hits ${k}`);
      assert.ok(ml.x >= 0 && mr.x + mr.w <= W);
    }
    }
  }
});
