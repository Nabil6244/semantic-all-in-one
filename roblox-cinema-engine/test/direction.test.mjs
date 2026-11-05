import test from 'node:test';
import assert from 'node:assert/strict';
import { assembleScene } from '../lib/assemble.mjs';
import { cameraJumps } from '../lib/camera.mjs';
import { liveCount, particlesAt, PARTICLE } from '../lib/fx.mjs';
import { captionCards } from '../lib/director.mjs';
import { samplePlan } from './_helpers.mjs';

const plan = samplePlan();
const clone = (o) => JSON.parse(JSON.stringify(o));

test('the plan covers the film: scenes tile the timeline, every scene has shots and a reason', () => {
  assert.ok(plan.duration > 100 && plan.scenes.length === 17);
  plan.scenes.forEach((s, i) => { assert.ok(s.t1 > s.t0); if (i) assert.ok(Math.abs(s.t0 - plan.scenes[i - 1].t1) < 1e-6); assert.ok(s.shots.length >= 1); for (const sh of s.shots) assert.ok(sh.t1 > sh.t0 && sh.reason); });
  assert.ok(Math.abs(plan.scenes[plan.scenes.length - 1].t1 - plan.duration) < 1e-6);
});
test('the camera never goes through ground, water or roofs, and never jumps inside a shot', () => {
  const fps = 24;
  for (const s of plan.scenes) {
    const A = assembleScene(clone(s)), samples = [], cuts = s.shots.map((x) => x.t0);
    for (let t = s.t0; t < s.t1; t += 1 / fps) { const c = A.cameraAt(t); assert.ok(c.pos.every(Number.isFinite) && c.target.every(Number.isFinite), `${s.id} NaN at ${t}`); samples.push({ t, pos: c.pos, target: c.target });
      if (s.env !== 'map' && s.env !== 'interior') assert.ok(c.pos[1] > A.world.heightAt(c.pos[0], c.pos[2]) + 0.3, `${s.id} camera under ground at ${t.toFixed(2)}`); }
    const j = cameraJumps(samples, cuts, fps);
    assert.ok(j.length === 0 || j[0].rel < 4.5, `${s.id} jump ${j[0] && j[0].rel.toFixed(2)} at ${j[0] && j[0].t.toFixed(2)}`);
  }
});
test('the same scene gives the same camera and the same bodies, twice', () => {
  const s = plan.scenes[2], a = assembleScene(clone(s)), b = assembleScene(clone(s)), t = s.t0 + 5;
  assert.deepEqual(a.cameraAt(t), b.cameraAt(t));
  assert.deepEqual(a.actorAt(a.stage.actors[0], t), b.actorAt(b.stage.actors[0], t));
});
test('subtitles: cards are at most two lines of 42 characters, ordered, and cover every sentence', () => {
  const cards = plan.hud.subtitles;
  for (const c of cards) { assert.ok(c.lines.length <= 2 && c.lines.every((l) => l.length <= 44), c.text); assert.ok(c.t1 > c.t0); assert.equal(c.words.length, c.text.split(/\s+/).length); }
  for (let i = 1; i < cards.length; i++) assert.ok(cards[i].t0 >= cards[i - 1].t0 - 1e-6);
  for (const s of plan.sentences) assert.ok(cards.some((c) => c.t0 <= s.start + 0.05 && c.t1 >= s.start), `no card at the start of: ${s.text}`);
  const orphan = cards.filter((c, i) => c.text.split(/\s+/).length < 3 && plan.sentences.some((s) => s.text.split(/\s+/).length > 12 && s.text.endsWith(c.text)));
  assert.equal(orphan.length, 0, 'one-word orphan cards');
  assert.ok(captionCards({ text: 'a b c', start: 0, end: 1, words: [{ start: 0 }, { start: 0.3 }, { start: 0.6 }] }).length === 1);
});
test('effects: deterministic, inside their budgets, and every explosion has a sound cue', () => {
  let worst = 0;
  for (const s of plan.scenes) {
    const A = assembleScene(clone(s));
    for (let t = s.t0; t < s.t1; t += 0.5) { const n = liveCount(A.emitters, t); worst = Math.max(worst, n); assert.ok(n < 700, `${s.id} ${n} particles`); }
    for (const e of A.emitters.slice(0, 4)) assert.deepEqual(particlesAt(e, s.t0 + 3), particlesAt(e, s.t0 + 3));
    const bursts = A.emitters.filter((e) => e.type === 'explosion' || (e.type === 'splash' && e.burst)).length;
    assert.ok(A.cues.filter((c) => /explosion/.test(c.cue)).length >= bursts, `${s.id} explosions without sound`);
  }
  assert.ok(worst > 20 && Object.keys(PARTICLE).length > 10);
});
test('cast and effects follow the narration: a landing scene has boats, a night drop has chutes in the sky', () => {
  const landing = plan.scenes.find((s) => s.event === 'landing_operation'), drop = plan.scenes.find((s) => s.event === 'airborne_drop');
  assert.ok(landing.vehicles.some((v) => v.kind === 'landing_craft')); assert.ok(drop.cast.some((c) => c.formation === 'sky'));
});
test('the map scenes carry pins, a projection box and the honesty note', () => {
  for (const s of plan.scenes.filter((x) => x.env === 'map')) { assert.ok(s.map.pins.length >= 2 && s.map.bbox.length === 4); assert.match(s.map.note, /approximate/i); }
});

test('an unknown CSV place never falls back to a far place the narration names; long holds are split', async () => {
  const { parseStory } = await import('../lib/csv.mjs');
  const { direct, MAX_HOLD, MAX_MAP_HOLD } = await import('../lib/director.mjs');
  const csv = 'row,id,chapter,text,date,location,event,environment,time,weather,characters,actions,vehicles,camera,transition,extra\n'
    + 'plan,,,"T",2025,,,,,,,,,,,"{}"\n'
    + 'beat,b1,,"Deep in the desert of Iran near Natanz stands a granite peak that planners in Washington fear.",,Natanz,map,map,,,,,,,,"{""map"":{""pins"":[""Natanz"",""Isfahan""],""dive"":""Natanz""}}"\n'
    + 'beat,b2,,"Planners in Washington studied the mountain for months and the plan kept growing larger and larger every single week.",,Zzyzx Hollow,political_meeting,interior,,,,,,static_close,,"{}"\n';
  const words = []; let t = 0;
  for (const w of csv.split('\n').slice(2).map((l) => l.split('"')[1]).join(' ').split(/\s+/)) { words.push({ word: w.toLowerCase(), start: t, end: t + 0.9 }); t += 1.0; }
  const p = direct(parseStory(csv), { words, fps: 24 });
  assert.equal(p.scenes[0].place.name, 'Natanz');
  assert.equal(p.scenes[1].place.name, 'Natanz', 'unknown location keeps the last CSV-located place, not Washington');
  assert.ok(p.warnings.some((w) => /Zzyzx/.test(w)));
  for (const s of p.scenes) for (const sh of s.shots) assert.ok(sh.t1 - sh.t0 <= (s.env === 'map' ? MAX_MAP_HOLD : MAX_HOLD) + 0.01 || (sh.t1 - sh.t0) / 2 < 3.6, `${s.id} holds ${sh.t1 - sh.t0}`);
});
