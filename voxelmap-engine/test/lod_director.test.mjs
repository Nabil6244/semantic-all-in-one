import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { LEVELS, wantedTiles, parentKey, sampleHeight, tileKey, blockHeights, TILE_BLOCKS, FADE_BAND } from '../lib/lod.mjs';
import { makeWorldData, addTile } from '../lib/world_data.mjs';
import { chooseShot, shotFrames, moveKind, SHOTS, offset } from '../lib/director.mjs';
import { softLinear, moveAt, cameraAt } from '../lib/camera3d.mjs';
import { parseStory } from '../lib/beats_csv.mjs';
import { buildTimeline } from '../lib/timeline.mjs';
import { buildCells, buildChunk, sunShadow } from '../lib/terrain_mesh.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const story = parseStory(fs.readFileSync(path.join(HERE, '..', 'samples', 'indochina_1954_1965.csv'), 'utf8'));

test('levels: no detail high up, level 1 at mid altitude, level 2 only close to the ground', () => {
  assert.equal(wantedTiles({ x: 400, y: 600, z: 400 }, 800, 800).length, 0);
  const mid = wantedTiles({ x: 400, y: 30, z: 400 }, 800, 800);
  assert.ok(mid.some((t) => t.level === 1) && !mid.some((t) => t.level === 2));
  const low = wantedTiles({ x: 405, y: 2, z: 405 }, 800, 800);
  assert.ok(low.some((t) => t.level === 2));
  for (const t of low) assert.ok(t.fade >= 0 && t.fade <= 1);
  // the tile under a low camera is fully faded in; fade only falls with distance
  const under = low.find((t) => t.level === 2 && t.d <= 2);
  assert.equal(under.fade, 1);
  const L2 = LEVELS[1];
  const far = wantedTiles({ x: 405, y: L2.near * (FADE_BAND - 0.05), z: 405 }, 800, 800).filter((t) => t.level === 2);
  assert.ok(far.every((t) => t.fade < 1));
});

test('a level-2 tile belongs to exactly one level-1 parent', () => {
  assert.equal(parentKey(2, 13, 9), tileKey(1, 3, 2));
  assert.equal(parentKey(1, 3, 2), null);
});

test('heights: the finest data wins, and fine heights match the world scale (no step between levels on flat land)', () => {
  const meta = { w: 80, h: 80, bbox: [0, 0, 2, 2], res: 0.025 };
  const n = 80 * 80, elev = new Int16Array(n).fill(900), land = new Uint8Array(n).fill(1), region = new Uint16Array(n);
  const data = makeWorldData(meta, { elev, land, region });
  const coarse = sampleHeight(data, 5, 5);
  const N = TILE_BLOCKS * TILE_BLOCKS;
  addTile(data, { level: 1, tx: 0, tz: 0, elev: new Int16Array(N).fill(900), land: new Uint8Array(N).fill(1), region: new Uint16Array(N) });
  const fine = sampleHeight(data, 5, 5);
  assert.ok(Math.abs(coarse - fine) <= 1, `${coarse} vs ${fine}`);
  assert.notEqual(fine, coarse); // the level-1 tile answered
  assert.equal(sampleHeight(data, 60, 60), coarse); // outside the tile: the world grid
  assert.deepEqual([...blockHeights(Int16Array.from([-50, -500, -2000, -4000]), new Uint8Array(4), 4, 4)], [0, -4, -8, -12]);
});

test('detail tile meshes are closed at their edges (skirts reach below the sea floor)', () => {
  const w = 4, h = 4, elev = new Int16Array(16).fill(400), land = new Uint8Array(16).fill(1);
  const cells = buildCells(elev, land, w, h, { k: 4 });
  const c = buildChunk(cells, new Uint16Array(16), w, h, 0, 0, w, h, -16);
  let minY = 0; for (let i = 1; i < c.pos.length; i += 3) minY = Math.min(minY, c.pos[i]);
  assert.equal(minY, -16);
  assert.equal(c.sh.length, c.quads * 4);
});

test('baked sun shadow falls on the side away from the sun', () => {
  const w = 12, h = 12, hgt = new Int16Array(w * h).fill(1);
  hgt[6 * w + 6] = 12; // a tower in the middle
  const s = sunShadow(hgt, w, h);
  // the sun is toward +x and +z, so the shadow lies toward -x / -z
  assert.equal(s[5 * w + 5], 0);
  assert.equal(s[7 * w + 7], 1);
});

test('the director varies shots, never repeats one back to back when another fits, and reads outcomes', () => {
  const tl = buildTimeline(story);
  const shots = tl.shots.map((s) => s.shot);
  assert.ok(new Set(shots).size >= 4, shots.join(','));
  for (let i = 1; i < shots.length; i++) if (story.beats[i].rung !== 'oblique') assert.notEqual(shots[i], shots[i - 1], `beats ${i - 1}/${i}`);
  assert.equal(shots[0], 'establishing');
  assert.equal(shots.at(-1), 'pullback'); // "the war is only beginning" ends the film
  for (const s of shots) assert.ok(SHOTS.includes(s));
  assert.ok(tl.shots.some((s) => s.move === 'descent') && tl.shots.some((s) => s.move === 'ascent'));
});

test('a shot can be forced from the story, and an aerial track follows a given path', () => {
  const spec = JSON.parse(JSON.stringify(story));
  spec.beats[4].shot = 'pullback';
  assert.equal(chooseShot(spec, 4, null), 'pullback');
  const b = { ...story.beats[4], heading: null, path: [[106, 18], [106.3, 15]] };
  const fr = shotFrames(b, 'aerial_track', 1);
  assert.equal(fr.start.lat, 18); assert.equal(fr.end.lat, 15);
  assert.ok(fr.start.heading > 170 && fr.start.heading < 190); // heading south along the path
});

test('moves: kinds, offsets and soft-linear easing are continuous', () => {
  assert.equal(moveKind({ lon: 100, lat: 15, alt: 1900 }, { lon: 103, lat: 21, alt: 5 }), 'descent');
  assert.equal(moveKind({ lon: 100, lat: 15, alt: 5 }, { lon: 100.3, lat: 15.2, alt: 5 }), 'hop');
  const p = offset({ lon: 105, lat: 15 }, 90, 111.32 * Math.cos(15 * Math.PI / 180));
  assert.ok(Math.abs(p.lon - 106) < 1e-9 && Math.abs(p.lat - 15) < 1e-9);
  let prev = 0;
  for (let k = 0.001; k <= 1; k += 0.001) { const v = softLinear(k); assert.ok(v >= prev - 1e-12 && v - prev < 0.003); prev = v; }
  assert.ok(Math.abs(softLinear(1) - 1) < 1e-9 && softLinear(0) === 0);
  const a = { lon: 100, lat: 10, alt: 5, heading: 0 }, z = { lon: 100.05, lat: 10, alt: 5, heading: 0 };
  assert.ok(Math.abs(moveAt(a, z, 0.5, 'linear').lon - 100.025) < 1e-9);
});

test('the camera is continuous across every shot and move boundary', () => {
  const tl = buildTimeline(story);
  for (const s of tl.camera.slice(1)) {
    const before = cameraAt(tl.camera, s.t0 - 1e-4), after = cameraAt(tl.camera, s.t0 + 1e-4);
    assert.ok(Math.abs(before.lon - after.lon) < 1e-3 && Math.abs(before.lat - after.lat) < 1e-3, `jump at ${s.t0.toFixed(2)} (${s.type})`);
    assert.ok(Math.abs(Math.log(before.alt / after.alt)) < 0.01, `altitude jump at ${s.t0.toFixed(2)}`);
  }
});
