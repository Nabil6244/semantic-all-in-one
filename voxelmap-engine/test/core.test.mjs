import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseStory, parseCsv, splitSentences } from '../lib/beats_csv.mjs';
import { buildTimeline, captionsAt, at, CAPTION_CLEAR_GAP } from '../lib/timeline.mjs';
import { cameraAt, autoTilt, travelSeconds, placeCamera } from '../lib/camera3d.mjs';
import { makeGeo, blockHeight, distanceKm } from '../lib/geo.mjs';
import { tintTable, blendTables } from '../lib/territory.mjs';
import { buildSet, particlesAt, RECIPES } from '../lib/props.mjs';
import { buildCells, buildChunk } from '../lib/terrain_mesh.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE = fs.readFileSync(path.join(HERE, '..', 'samples', 'indochina_1954_1965.csv'), 'utf8');
const story = parseStory(SAMPLE);
const tl = buildTimeline(story);
const META = { bbox: [92, 5, 112, 25], res: 0.025, w: 800, h: 800 };

test('the sample story parses into chapters, beats, territories and labels', () => {
  assert.equal(story.chapters.length, 3);
  assert.equal(story.beats.length, 10);
  assert.equal(story.territories.length, 2);
  assert.ok(story.labels.length >= 10);
  assert.deepEqual(splitSentences('One. Two words! Three?'), ['One.', 'Two words!', 'Three?']);
  assert.equal(parseCsv('a,b\n"x,""y""",2\n')[0].a, 'x,"y"');
});

test('bad rows fail with the row number', () => {
  assert.throws(() => parseStory('row,id,date,lon,lat,text\nbeat,b1,1954-05,1,2,Hi.\n'), /chapter row before it/);
  assert.throws(() => parseStory('row,id,date,lon,lat,text\nchapter,c,,,,T\nbeat,b1,May 1954,1,2,Hi.\n'), /row 3.*YYYY-MM/);
});

test('every camera move happens in the silence before its beat (no move overlaps narration)', () => {
  assert.deepEqual(tl.warnings, []);
  for (const b of tl.beats.slice(1)) {
    assert.ok(b.travelT1 <= b.speakT0, `${b.id} lands before its first sentence`);
    const prev = tl.beats[tl.beats.indexOf(b) - 1];
    assert.ok(b.travelT0 >= prev.speakT1, `${b.id} leaves after the previous sentence ends`);
  }
});

test('the camera never jumps: frame-to-frame movement stays small relative to altitude', () => {
  const geo = makeGeo(META), ground = () => 1;
  let prev = null, worst = 0;
  for (let t = 0; t < tl.duration; t += 1 / 30) {
    const p = placeCamera(cameraAt(tl.camera, t), geo, ground).pos;
    if (prev) { const d = Math.hypot(p.x - prev.x, p.y - prev.y, p.z - prev.z) / Math.max(1, p.y); worst = Math.max(worst, d); }
    prev = p;
  }
  assert.ok(worst < 0.25, `largest per-frame step is ${worst.toFixed(3)} of the camera height`);
});

test('the camera is never frozen: every second it moves', () => {
  const geo = makeGeo(META), ground = () => 1;
  for (let t = 0; t + 1 < tl.duration; t += 1) {
    const a = placeCamera(cameraAt(tl.camera, t), geo, ground), b = placeCamera(cameraAt(tl.camera, t + 1), geo, ground);
    assert.ok(Math.hypot(a.pos.x - b.pos.x, a.pos.z - b.pos.z) > 1e-4 || Math.abs(a.pos.y - b.pos.y) > 1e-4, `still at ${t}s`);
  }
});

test('tilt follows altitude: straight down for maps, oblique near the ground', () => {
  assert.equal(autoTilt(2000), 0);
  assert.equal(autoTilt(3), 58);
  let last = -1;
  for (const a of [1500, 800, 300, 100, 30, 10, 6]) { const v = autoTilt(a); assert.ok(v >= last); last = v; }
  assert.ok(travelSeconds({ lon: 104, lat: 15, alt: 1900 }, { lon: 103, lat: 21, alt: 5.5 }) > travelSeconds({ lon: 104, lat: 15, alt: 300 }, { lon: 104.2, lat: 15.1, alt: 300 }));
});

test('every chapter card sits in a narration silence and the date box jumps to the card month', () => {
  for (const c of tl.chapters.slice(1)) {
    const b = tl.beats.find((x) => x.chapter === c.id);
    const spoken = tl.captions.some((s) => s.t0 < c.cardT0 + 2 && s.t1 > c.cardT0);
    assert.ok(!spoken, `${c.title} card starts in silence`);
    assert.ok(c.cardT1 <= b.speakT0 + 0.81);
  }
});

test('a skip of years steps the date box through months', () => {
  const b5 = tl.beats.find((b) => b.id === 'b5');
  const skip = tl.dates.filter((d) => d.t > b5.travelT0 && d.t <= b5.speakT0).map((d) => d.label);
  assert.ok(skip.length >= 4, skip.join(', '));
  assert.equal(skip[skip.length - 1], 'MAY 1959');
});

test('captions: two lines at most, the older greyed, cleared inside a long silence', () => {
  const s = tl.captions[1];
  const lines = captionsAt(tl.captions, s.t0 + 0.1);
  assert.equal(lines.length, 2); assert.ok(lines[0].old); assert.ok(!lines[1].old);
  assert.match(lines[1].tag, /^\[[A-Z]{3} \d{4}\]$/);
  const fake = [{ t0: 0, t1: 3, text: 'a', tag: '[x]' }, { t0: 3 + CAPTION_CLEAR_GAP + 5, t1: 20, text: 'b', tag: '[x]' }];
  assert.equal(captionsAt(fake, 7).length, 0);
  assert.equal(captionsAt(fake, 4).length, 1);
});

test('territory rules tint North and South Vietnam by province latitude, and blend softly', () => {
  const regions = [{ i: 1, iso: 'VNM', name: 'Hanoi', lat: 21 }, { i: 2, iso: 'VNM', name: 'Saigon', lat: 10.8 }, { i: 3, iso: 'THA', name: 'Bangkok', lat: 13.7 }];
  const split = story.territories.find((x) => x.key === 'split');
  const tab = tintTable(regions, split);
  assert.deepEqual([...tab.slice(4, 7)], [0xb8, 0x32, 0x2a]);
  assert.deepEqual([...tab.slice(8, 11)], [0x2f, 0x5f, 0xa8]);
  assert.equal(tab[15], 0);
  const half = blendTables(new Uint8Array(1024), tab, 0.5);
  assert.ok(half[7] > 0 && half[7] < tab[7]);
});

test('sets are generated from recipes, deterministic, and animate from t alone', () => {
  for (const r of RECIPES) {
    const a = buildSet(r, 7), b = buildSet(r, 7);
    assert.deepEqual(a.boxes.slice(0, 50), b.boxes.slice(0, 50));
    assert.ok(a.boxes.length > 100, `${r} has content`);
  }
  const battle = buildSet('battle', 3);
  assert.deepEqual(particlesAt(battle, 12.3), particlesAt(battle, 12.3));
  assert.notDeepEqual(particlesAt(battle, 12.3), particlesAt(battle, 12.8));
  assert.equal(buildSet('nonsense', 1).recipe, 'village');
});

test('terrain: block heights step with elevation and a chunk closes every wall', () => {
  assert.equal(blockHeight(10), 1); assert.equal(blockHeight(500), 2); assert.equal(blockHeight(900), 3); assert.equal(blockHeight(-100), 0); assert.equal(blockHeight(-4000), -3);
  const w = 3, h = 3, elev = Int16Array.from([0, 0, 0, 0, 900, 0, 0, 0, 0].map((e, i) => (i === 4 ? 900 : -50)));
  const land = Uint8Array.from([0, 0, 0, 0, 1, 0, 0, 0, 0]);
  const cells = buildCells(elev, land, w, h);
  assert.equal(cells.hgt[4], 3);
  const c = buildChunk(cells, new Uint16Array(9), w, h, 0, 0, w, h);
  // 1 island top + 4 island walls + 3 merged sea rows + sea walls at the world edge
  assert.ok(c.quads >= 8 && c.quads <= 30, String(c.quads)); // shore and open-sea runs merge separately
  assert.equal(c.index.length, c.quads * 6);
});

test('geo: distance and lon/lat round trip', () => {
  const geo = makeGeo(META), p = geo.toWorld(105.85, 21.03), back = geo.toLonLat(p.x, p.z);
  assert.ok(Math.abs(back.lon - 105.85) < 1e-9 && Math.abs(back.lat - 21.03) < 1e-9);
  assert.ok(Math.abs(distanceKm({ lon: 105.85, lat: 21.03 }, { lon: 106.7, lat: 10.78 }) - 1140) < 30);
});

test('a real voiceover drives the travel; a silence too short for a move is reported, never hidden', () => {
  // narration with no pause at all between beats: every move must spill into speech and say so
  const said = [];
  let t = 1;
  for (const b of story.beats) for (const s of b.sentences) { said.push({ start: t, end: t + 3, text: s }); t += 3.1; }
  const real = buildTimeline(story, said);
  assert.ok(real.warnings.some((w) => /runs into the narration/.test(w)));
  assert.equal(real.captions[0].t0, 1);
  // with generous pauses, no warnings and every move inside its silence
  const roomy = []; t = 1;
  story.beats.forEach((b) => { t += 14; for (const s of b.sentences) { roomy.push({ start: t, end: t + 3, text: s }); t += 3.2; } });
  const ok = buildTimeline(story, roomy);
  assert.ok(!ok.warnings.some((w) => /runs into/.test(w)), ok.warnings.join('; '));
  for (const b of ok.beats.slice(1)) assert.ok(b.travelT1 <= b.speakT0);
});

test('the timeline is deterministic', () => {
  assert.deepEqual(buildTimeline(parseStory(SAMPLE)), tl);
  assert.ok(at(tl.territory, 0) === null);
});
