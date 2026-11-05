import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseCsv, normalizeRows, buildLesson } from '../lib/lesson.mjs';

const CSV = `type,text,object,color,count,word,gesture,emotion,pause
say,"Hi, friend!",,,,,,,
word,"Look! A ball! Ball!",ball,red,,Ball,,,
repeat,Can you say ball?,,,,,,,
count,"One, two, three!",star,,3,,,,
color,Blue! It is blue.,balloon,blue,,,,,
bogus,odd type,,,,,,,
count,No numbers here,duck,,12,,,,
,,,,,,,,
`;
const v = (text, d = 2) => ({ dur: d, words: text.split(/\s+/).map((w, k) => ({ text: w.replace(/[^\w']/g, ''), t0: 0.1 + k * 0.3, t1: 0.35 + k * 0.3 })) });

test('csv parses quotes and skips blank rows', () => {
  const rows = parseCsv(CSV);
  assert.equal(rows.length, 7);
  assert.equal(rows[0].text, 'Hi, friend!');
});

test('bad cells fall back with a problem note, never stop', () => {
  const { beats, problems } = normalizeRows(parseCsv(CSV));
  assert.equal(beats.length, 7);
  assert.equal(beats[5].type, 'say');
  assert.equal(beats[6].count, 3);
  assert.equal(beats[0].gesture, 'wave');
  assert.ok(problems.some((p) => p.includes('unknown type')) && problems.some((p) => p.includes('not 1-10')));
});

test('props appear on spoken numbers, cards on the word, repeat leaves a quiet turn', () => {
  const { beats } = normalizeRows(parseCsv(CSV));
  const L = buildLesson(beats, beats.map((b) => v(b.text)));
  const stars = L.props.filter((p) => p.kind === 'star');
  assert.deepEqual(stars.map((p) => p.n), [1, 2, 3]);
  const countLine = L.lines[3];
  assert.ok(stars.every((p, k) => Math.abs(p.t0 - (countLine.t0 + 0.1 + k * 0.3)) < 1e-6), 'each star pops on its number word');
  const ball = L.props.find((p) => p.kind === 'ball');
  assert.ok(ball.t1 > L.lines[2].t1, 'ball stays through the repeat line');
  assert.ok(ball.t1 <= stars[0].t0, 'ball leaves before the stars come');
  const card = L.cards.find((c) => c.text === 'Ball');
  assert.ok(card.t0 > L.lines[1].t0 && card.t1 > card.t0);
  assert.equal(L.badges.length, 1);
  assert.ok(L.badges[0].t1 - L.badges[0].t0 > 1.5, 'child gets a real pause');
  assert.equal(L.cards.find((c) => c.text === 'Blue').color, 'blue');
  for (let i = 1; i < L.lines.length; i++) assert.ok(L.lines[i].t0 > L.lines[i - 1].t1, 'lines never overlap');
  for (const p of L.props) assert.ok(p.t1 > p.t0 && p.t1 <= L.duration);
  // A count with no number words still spreads its props across the line.
  const ducks = L.props.filter((p) => p.kind === 'duck');
  assert.equal(ducks.length, 3); assert.ok(ducks[0].t0 < ducks[1].t0 && ducks[1].t0 < ducks[2].t0);
});

const CSV2 = `type,text,object,color,count,word,gesture,emotion,pause,sound
opposite,"Up, up, up! Now down, down.",,,,up/down,,,,
opposite,"Small. Now big!",ball,,,big/small,,,,
opposite,odd,,,,left/right,,,,
animal,"The cow says moo! Moo!",cow,,,,,,,moo
shape,This is a triangle.,triangle,,,,,,,
letter,"A is for apple.",apple,,,A,,,,
feeling,"I feel sad.",,,,sad,,,,
feeling,"Sleepy...",,,,sleepy,,,,
`;

test('new types: opposite moves on its words, animal hops on its sound, letter and feeling cards', () => {
  const { beats, problems } = normalizeRows(parseCsv(CSV2));
  assert.deepEqual(beats[0].pair, ['up', 'down']); assert.equal(beats[0].object, 'balloon');
  assert.deepEqual(beats[1].pair, ['big', 'small'], 'pair order comes from the word column');
  assert.ok(problems.some((p) => p.includes('left/right')));
  const L = buildLesson(beats, beats.map((b) => v(b.text)));
  const bal = L.props.find((p) => p.kind === 'balloon');
  assert.deepEqual(bal.anims.map((a) => a.kind), ['up', 'down']);
  const line0 = L.lines[0], downWord = line0.words.find((w) => w.text.toLowerCase().startsWith('down'));
  assert.equal(bal.anims[1].t, downWord.t0, 'moves down exactly on "down"');
  assert.ok(L.gestures.some((g) => g.gesture === 'pointDown') && L.gestures.some((g) => g.gesture === 'point'));
  for (let i = 1; i < L.gestures.length; i++) assert.ok(L.gestures[i].t >= L.gestures[i - 1].t, 'gestures sorted');
  const cow = L.props.find((p) => p.kind === 'cow');
  assert.equal(cow.anims.filter((a) => a.kind === 'hop').length, 2);
  assert.ok(L.cards.some((c) => c.text === 'Moo!' && c.sound));
  assert.ok(L.cards.some((c) => c.text === 'Triangle'));
  const letterCard = L.cards.find((c) => c.text === 'A a'), apple = L.props.find((p) => p.kind === 'apple');
  assert.ok(letterCard.t0 < apple.t0 + 0.1, 'letter first, apple on its word');
  const face = L.props.find((p) => p.kind === 'face' && p.color === 'sad');
  assert.ok(face); assert.equal(beats[6].emotion, 'sad');
  assert.equal(beats[7].emotion, 'neutral');
});

test('two cards on one line: the first stays until the second appears', () => {
  const { beats } = normalizeRows(parseCsv(CSV2));
  const L = buildLesson(beats, beats.map((b) => v(b.text)));
  const up = L.cards.find((c) => c.text === 'Up'), down = L.cards.find((c) => c.text === 'Down');
  assert.ok(Math.abs(up.t1 - (down.t0 - 0.02)) < 1e-6);
  for (let k = 1; k < L.cards.length; k++) assert.ok(L.cards[k].t0 >= L.cards[k - 1].t1, 'cards never overlap');
});

test('chant lines start on a half-bar of the music and clap on its beat', () => {
  const { beats } = normalizeRows(parseCsv('type,text\nsay,Hello!\nchant,"One, two, three, four!"\n'));
  const L = buildLesson(beats, [{ dur: 1.3, words: [] }, { dur: 2.4, words: [] }], { beat: 0.5 });
  const c = L.lines.find((l) => l.type === 'chant');
  assert.equal(c.t0 % 1, 0);                          // half-bar = 2 beats = 1 s at 120 bpm
  assert.ok(c.t0 >= L.lines[0].t1);
  const g = L.gestures.find((x) => x.gesture === 'clap'); assert.equal(g.t, c.t0); assert.equal(g.beat, 0.5);
  const plain = buildLesson(beats, [{ dur: 1.3, words: [] }, { dur: 2.4, words: [] }]);      // no beat given: timing as before
  assert.equal(plain.lines[1].t0, +(0.6 + 1.3 + 0.35).toFixed(3));
});
