// Pure-module tests: story parsing, growth order, timeline, camera, flags. No browser, no network.
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseStory, parseYear, yearLabel, styleForYear } from '../lib/story.mjs';
import { makeLots, rankLots, needed, riseOf, eventFactor, cityExtent, makeTrees, roadRanks, fallbackLanes, densityOf } from '../lib/growth.mjs';
import { buildTimeline, stateAt, timeOfYear, hudAt, cameraAt, popLabel, skipSeconds } from '../lib/timeline.mjs';
import { makeTerrain } from '../lib/terrain.mjs';
import { parseFlag } from '../lib/hud.mjs';
import { footprint } from '../lib/landmarks.mjs';

const flatWorld = (n = 200, cell = 10, h = 20) => {
  const a = new Float32Array(n * n).fill(h);
  return makeTerrain(a, n, n, cell, { step: 2 });
};

const CSV = `row,year,until,era_name,flag,population,caption,title,kicker,style,shot,focus,hold,kind,radius,weight,extra
plan,,,Testville,,,,,,,,"0,0",,,,,"{""world"":""t""}"
district,-500,,Old town,,,,,,,,"0,0",,,,1,
era,500 BC,,Founding,h:#fff,#00f,1000,A village by the river.,,,,,,,,,
era,AD 100,,Rome,,20000,,THE GOLDEN AGE,Empire,,,,,,,,
era,1200,,Middle Ages,,,The town shrinks.,,,,,,,,,,
era,1900,,Modern,,60000,Factories everywhere.,,,,,,,,,,
event,1100,,,,,A great fire.,,,,,"0.001,0.001",,fire,300,,
landmark,50,,Temple,,,,,,,,"0.0005,0.0005",,temple,,,"{""size"":40}"
landmark,1500,1800,Old wall,,,,,,,,,,wall,,,"{""path"":[[0,0],[0.001,0]]}"`;

test('years parse in every common form', () => {
  assert.equal(parseYear('-658'), -658);
  assert.equal(parseYear('658 BC'), -658);
  assert.equal(parseYear('60 BCE'), -60);
  assert.equal(parseYear('AD 540'), 540);
  assert.equal(parseYear('c. 1200'), 1200);
  assert.equal(parseYear('nonsense'), null);
  assert.equal(yearLabel(-658), '658 BC');
  assert.equal(yearLabel(540, { adPrefix: true }), 'AD 540');
  assert.equal(yearLabel(1453, { adPrefix: true }), '1453');
  assert.equal(styleForYear(1950), 'modern');
});

test('story rows parse, gaps in population are filled, bad rows warn', () => {
  const s = parseStory(CSV);
  assert.equal(s.plan.city, 'Testville');
  assert.equal(s.plan.world, 't');
  assert.equal(s.eras.length, 4);
  assert.equal(s.eras[0].year, -500);
  assert.ok(s.eras[2].population > 20000 && s.eras[2].population < 60000, 'interpolated');
  assert.ok(s.warnings.some((w) => /no population/.test(w)));
  assert.equal(s.landmarks.length, 2);
  assert.equal(s.landmarks[1].until, 1800);
  assert.equal(s.events[0].radius, 300);
  assert.throws(() => parseStory('row,year\nplan,'), /no era rows/);
  const shifted = parseStory('row,year,era_name,caption,style\nera,1700,Town,One, two,south_asian\n');
  assert.ok(shifted.warnings.some((w) => /comma inside a cell/.test(w)), 'an unquoted comma is reported');
});

test('lots line the streets, stay off water and out of each other', () => {
  const T = flatWorld();
  const roads = [{ c: 3, p: [[-500, 0], [500, 0]] }, { c: 2, p: [[0, -500], [0, 500]] }];
  const lots = makeLots(roads, T, { seed: 3 });
  assert.ok(lots.length > 100);
  for (let i = 0; i < lots.length; i += 7) for (let j = i + 1; j < lots.length; j += 13) {
    const a = lots[i], b = lots[j];
    assert.ok(Math.hypot(a.x - b.x, a.z - b.z) >= (a.rad + b.rad) * 0.999, 'no overlap');
  }
  assert.ok(lots.every((l) => Math.abs(l.z) > 2 || Math.abs(l.x) > 2), 'not on the street');
});

test('growth starts at the core and a shrinking city loses its edge first', () => {
  const T = flatWorld();
  const lots = makeLots(fallbackLanes(T, 2), T, { seed: 4 });
  rankLots(lots, [{ x: 0, z: 0, year: 0, weight: 1 }], { firstYear: 0, lastYear: 1000 });
  const n = lots.length;
  const first = lots.filter((l) => l.rank < n * 0.1), last = lots.filter((l) => l.rank > n * 0.9);
  const md = (ls) => ls.reduce((s, l) => s + Math.hypot(l.x, l.z), 0) / ls.length;
  assert.ok(md(first) < md(last) * 0.6, 'first houses are near the core');
  assert.equal(riseOf(0, n * 0.5, n), 1);
  assert.equal(riseOf(n * 0.6, n * 0.5, n), 0);
  assert.ok(riseOf(n * 0.5 - 5, n * 0.5, n) > 0 && riseOf(n * 0.5 - 5, n * 0.5, n) < 1, 'a soft edge');
  const e1 = cityExtent(lots, n * 0.1), e2 = cityExtent(lots, n * 0.8);
  assert.ok(e2.r > e1.r);
});

test('a later core grows after an earlier one', () => {
  const T = flatWorld(300);
  const lots = makeLots(fallbackLanes(T, 5), T, { seed: 5 });
  rankLots(lots, [{ x: -800, z: 0, year: 0 }, { x: 800, z: 0, year: 900 }], { firstYear: 0, lastYear: 1000 });
  const early = lots.filter((l) => l.rank < lots.length * 0.15);
  assert.ok(early.filter((l) => l.x < 0).length > early.length * 0.8);
});

test('people per lot: big pre-modern cities pack denser; modern lots are blocks', () => {
  assert.equal(densityOf(10000, 500), 1);
  assert.ok(densityOf(1000000, 125) > 2);
  assert.equal(densityOf(3000000, 2000), 1);
  assert.ok(needed(1e6, 125, 1e9) < needed(1e6, 125, 1e9) * 2 && needed(1e6, 125, 1e9) < 1e6 / 7);
  assert.equal(needed(1e9, 2000, 500), 500, 'capped by the lots there are');
});

test('fire clears an area, then it regrows from the edge inward', () => {
  const ev = [{ x: 0, z: 0, r: 100, year: 1000, regrow: 20, down: 2 }];
  assert.equal(eventFactor(ev, 0, 0, 999), 1);
  assert.equal(eventFactor(ev, 0, 0, 1001), 0);
  assert.equal(eventFactor(ev, 500, 0, 1001), 1);
  assert.ok(eventFactor(ev, 95, 0, 1008) > eventFactor(ev, 5, 0, 1008));
  assert.equal(eventFactor(ev, 5, 0, 1030), 1);
});

test('trees are cleared when the city reaches them; streets appear with their first house', () => {
  const T = flatWorld();
  const roads = [{ c: 3, p: [[-400, 0], [400, 0]] }, { c: 3, p: [[-400, 300], [400, 300]] }];
  const lots = rankLots(makeLots(roads, T, { seed: 2 }), [{ x: 0, z: 0, year: 0 }]);
  const trees = makeTrees(T, lots, { seed: 2 });
  assert.ok(trees.some((t) => Number.isFinite(t.rank)) && trees.some((t) => !Number.isFinite(t.rank)));
  const rr = roadRanks(roads, lots);
  assert.ok(rr[0] < rr[1], 'the street through the core comes first');
});

function testCity() {
  return { toXZ: (lon, lat) => ({ x: lon * 80000, z: -lat * 110000 }), extent: () => ({ x: 0, z: 0, r: 600 }), landmarkXZ: { Temple: { x: 40, z: -55 } } };
}

test('timeline: skips, holds, captions, titles and the camera never stop', () => {
  const s = parseStory(CSV);
  const tl = buildTimeline(s, testCity());
  assert.equal(tl.holds.length, 4);
  for (let i = 1; i < tl.holds.length; i++) {
    const h = tl.holds[i];
    assert.ok(h.tr1 - h.tr0 >= 2.5 && h.h1 > h.h0);
    assert.ok(Math.abs(stateAt(tl, h.h0 + 0.1).year - h.year) < 1e-6, 'the year holds during the hold');
  }
  const mid = (tl.holds[1].tr0 + tl.holds[1].tr1) / 2;
  const y = stateAt(tl, mid).year;
  assert.ok(y > -500 && y < 100);
  assert.ok(tl.captions.some((c) => c.text === 'A great fire.'), 'event captions join the next era');
  assert.ok(tl.titles.some((t) => t.title === 'THE GOLDEN AGE'));
  assert.ok(tl.adPrefix);
  assert.equal(hudAt(tl, tl.holds[1].h0 + 1).year, 'AD 100');
  assert.ok(timeOfYear(tl, 50) > tl.holds[0].h1 && timeOfYear(tl, 50) < tl.holds[1].tr1);
  assert.ok(tl.landmarkTimes.Temple.tIn > 0);
  // the camera keeps moving everywhere (no still screens)
  let prev = cameraAt(tl.camera, 0);
  for (let t = 0.5; t < tl.duration; t += 0.5) {
    const c = cameraAt(tl.camera, t);
    const moved = Math.hypot(c.x - prev.x, c.z - prev.z) + Math.abs(c.dist - prev.dist) + Math.abs(c.heading - prev.heading) * 5;
    assert.ok(moved > 0.05, `camera still at ${t}`);
    assert.ok(Number.isFinite(c.dist) && c.dist > 50);
    prev = c;
  }
});

test('a new landmark becomes the era\'s close shot', () => {
  const s = parseStory(CSV);
  const tl = buildTimeline(s, testCity());
  const h = tl.holds[1];
  const seg = tl.camera.find((c) => c.type === 'move' && c.t0 === h.h0);
  assert.ok(Math.hypot(seg.from.x - 40, seg.from.z + 55) < 1, 'focus on the temple');
  assert.ok(seg.from.dist < 400);
});

test('labels, skips and flags', () => {
  assert.equal(popLabel(3040), 'c. 3,000');
  assert.equal(popLabel(452300), 'c. 450,000');
  assert.ok(skipSeconds(5) < skipSeconds(500));
  assert.deepEqual(parseFlag('h:#a,#b|X'), { kind: 'h', colors: ['#a', '#b'], text: 'X' });
  assert.equal(parseFlag('#123').kind, 'plain');
});

test('landmark footprints follow their long axis and paths', () => {
  const f = footprint({ kind: 'hippodrome', x: 0, z: 0, extra: { size: 400, rot: 90 } });
  assert.ok(f.length >= 3);
  assert.ok(f.every((c) => Math.abs(c.x) < 1), 'rotated 90 degrees: the long axis runs north–south');
  const w = footprint({ kind: 'wall', points: [[0, 0], [100, 0]], extra: {} });
  assert.ok(w.length > 5 && w.every((c) => c.z === 0));
});

test('terrain: the drawn surface matches its own vertices', () => {
  const n = 51, a = new Float32Array(n * n);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) a[j * n + i] = i * 0.5 + j * 0.2;
  const T = makeTerrain(a, n, n, 4, { step: 2, exag: 1 });
  const j = 10, i = 7;
  assert.ok(Math.abs(T.heightAt(T.x0 + i * T.sp, T.x0 + j * T.sp) - T.hs[j * T.n + i]) < 1e-4);
});

test('desert cities get the dry look, others stay green, and the story can say it', async () => {
  const { climateOf, CLIMATES } = await import('../lib/climate.mjs');
  assert.equal(climateOf({ center: { lon: 55.2858, lat: 25.2303 } }), 'arid');  // Dubai, as parseStory gives it
  assert.equal(climateOf({ center: [55.2858, 25.2303] }), 'arid');
  assert.equal(climateOf({}, { center: [46.67, 24.71] }), 'arid');        // Riyadh, from the world's own centre
  assert.equal(climateOf({ center: [12.4823, 41.8955] }), 'temperate');   // Rome
  assert.equal(climateOf({ center: [70.3, 28.4] }), 'temperate');         // Rahim Yar Khan: irrigated farmland
  assert.equal(climateOf({ center: [12.48, 41.9], climate: 'desert' }), 'arid');
  assert.equal(climateOf({ center: [55.29, 25.23], climate: 'green' }), 'temperate');
  assert.ok(CLIMATES.arid.treeDensity < CLIMATES.temperate.treeDensity);
  assert.ok(((CLIMATES.arid.grassA >> 16) & 255) > ((CLIMATES.arid.grassA >> 8) & 255), 'arid ground is tan (red above green), not green');
});

test('the Dubai story file itself comes out arid', async () => {
  const { planCity } = await import('../render.mjs');
  const fs = await import('node:fs'), os = await import('node:os'), path = await import('node:path');
  const f = path.join(os.homedir(), 'Downloads', 'dubai_timelapse.csv');
  if (!fs.existsSync(f) || !fs.existsSync(path.join(new URL('..', import.meta.url).pathname, 'worlds', 'dubai'))) return;
  assert.equal(planCity(fs.readFileSync(f, 'utf8')).climate, 'arid');
});

test('land use decides the trees: woods fill, desert stays bare, unmapped follows the climate', async () => {
  const { LAND, landClassAt, treeFactor } = await import('../lib/climate.mjs');
  const cls = new Uint8Array(LAND.n * LAND.n); cls[0] = LAND.green;                      // north-west corner is a park
  assert.equal(landClassAt(cls, 1000, -999.9, -999.9), LAND.green);
  assert.equal(landClassAt(cls, 1000, 0, 0), 0);
  assert.equal(landClassAt(cls, 1000, 5000, 0), 0);                                        // outside the world
  assert.equal(landClassAt(null, 1000, 0, 0), 0);
  assert.ok(treeFactor(LAND.green, 0.12) >= 1);                                            // a park in the desert still gets trees
  assert.ok(treeFactor(LAND.dry, 1) < 0.1);
  assert.equal(treeFactor(0, 0.12), 0.12);
});
