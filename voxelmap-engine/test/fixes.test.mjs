import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildSet, particlesAt, RECIPES } from '../lib/props.mjs';
import { parseStory } from '../lib/beats_csv.mjs';
import { buildTimeline, MAX_SQUEEZE } from '../lib/timeline.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const story = parseStory(fs.readFileSync(path.join(HERE, '..', 'samples', 'indochina_1954_1965.csv'), 'utf8'));
// the drawn size of a particle, as the renderer scales it
const volume = (ps) => ps.reduce((v, p) => { const k = (p.sx ? 1 : Math.sqrt(Math.max(0, p.a ?? 1))) * (p.g ?? 1); return v + (p.sx ?? p.s) * k * (p.sy ?? p.s) * k * (p.sz ?? p.s) * k; }, 0);

test('particles never vanish in one frame: drawn volume changes by under 20% of its peak between frames', () => {
  const ctx = { ground: (x, z) => ({ y: 0, water: x < 40 ? 1 : x < 44 ? 2 : 0, forest: z > 100, color: [80, 130, 60] }) };
  for (const r of RECIPES) for (const seed of [7, 4242]) {
    const set = buildSet(r, seed, 144, ctx);
    let prev = null, worst = 0, peak = 1e-9;
    for (let t = 0; t < 40; t += 1 / 30) { const v = volume(particlesAt(set, t)); peak = Math.max(peak, v); if (prev != null) worst = Math.max(worst, Math.abs(v - prev)); prev = v; }
    assert.ok(worst / peak < 0.2, `${r}/${seed}: ${(100 * worst / peak).toFixed(1)}%`);
  }
});

test('an emitter stays in or out of the budget for the whole film, whatever the others are doing', () => {
  const set = buildSet('battle', 99, 144);
  const count = (t) => particlesAt(set, t).length;
  for (let t = 0; t < 20; t += 0.37) assert.ok(count(t) <= 600);
});

test('a tight real pause: margins shrink, then the move speeds up a little, and only then is it reported', () => {
  const plan = buildTimeline(story);
  const b2 = plan.beats.find((b) => b.id === 'b2');
  const need = b2.travelT1 - b2.travelT0; // the natural move into Dien Bien Phu
  const shift = (gap) => {
    // the same narration, with the silence before b2 set to `gap` seconds
    const said = plan.narration.map((s) => ({ start: s.start, end: s.end, text: s.text }));
    const k = said.findIndex((s) => s.text === story.beats[1].sentences[0]), d = said[k].start - said[k - 1].end - gap;
    for (let j = k; j < said.length; j++) { said[j].start -= d; said[j].end -= d; }
    return buildTimeline(story, said);
  };
  const roomy = shift(need + 0.4);
  assert.deepEqual(roomy.warnings, []); assert.deepEqual(roomy.notes, []);
  const squeezed = shift(need * (1 - MAX_SQUEEZE / 2) + 0.3);
  assert.deepEqual(squeezed.warnings, []); assert.equal(squeezed.notes.length, 1);
  const short = shift(need * 0.5);
  assert.ok(short.warnings.some((w) => /runs into the narration/.test(w)));
});

import { parseStory as _parseStory } from '../lib/beats_csv.mjs';
test('a territory row without a date starts with the first beat; a malformed date still fails', () => {
  const head = 'row,id,date,place,lon,lat,rung,alt,heading,site,gap,text,extra\n';
  const body = 'chapter,c1,,,,,,,,,,One,\nbeat,b1,1965-09,X,74.5,31.2,map,,,,,"Hello there.",\n';
  const ok = _parseStory(head + 'territory,t,,,,,,,,,,,"{""rules"":[]}"\n' + body);
  assert.equal(ok.territories[0].date, '1965-09');
  assert.throws(() => _parseStory(head + 'territory,t,1965,,,,,,,,,,"{}"\n' + body), /YYYY-MM/);
});

import { monthLabel as _ml, monthIndex as _mi } from '../lib/timeline.mjs';
test('BC dates parse, order and label correctly', () => {
  assert.equal(_ml('-0753-04'), 'APR 753 BC');
  assert.equal(_ml('1965-09'), 'SEP 1965');
  assert.equal(_ml('0080-01'), 'JAN 80 AD');
  assert.ok(_mi('-0753-04') < _mi('-0616-01') && _mi('-0616-01') < _mi('0117-01'));
  const head = 'row,id,date,place,lon,lat,rung,alt,heading,site,gap,text,extra\n';
  const s = _parseStory(head + 'chapter,c,,,,,,,,,,T,\nbeat,b,-0753-04,X,12.5,41.9,map,,,,,"Hi there.",\n');
  assert.equal(s.beats[0].date, '-0753-04');
});
