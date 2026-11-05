import test from 'node:test';
import assert from 'node:assert/strict';
import { worldFor, storyPoints, MAX_CELLS } from '../lib/world_extent.mjs';

const beat = (lon, lat, rung = 'map', x = {}) => ({ lon, lat, rung, ...x });

test('a missing world is sized around every place the story names, never around globe beats', () => {
  const story = { beats: [beat(0, 0, 'globe'), beat(-77.0, 38.9), beat(-90.1, 29.9, 'ground', { effects: [{ kind: 'smoke', at: [-95.4, 29.8] }] })],
    labels: [{ lon: -74.0, lat: 40.7 }] };
  assert.equal(storyPoints(story).length, 4);
  const w = worldFor(story);
  const [lo0, la0, lo1, la1] = w.bbox;
  for (const [lon, lat] of storyPoints(story)) assert.ok(lon > lo0 && lon < lo1 && lat > la0 && lat < la1, `${lon},${lat} inside ${w.bbox}`);
  assert.ok(w.w * w.h <= MAX_CELLS && w.tiles.length > 0);
  assert.ok(lo1 - lo0 >= 12 && la1 - la0 >= 12);
});

test('a continent-wide story gets coarser blocks and a lower tile zoom instead of a huge grid', () => {
  const w = worldFor({ beats: [beat(-165, 65), beat(-55, 12)], labels: [] });
  assert.ok(w.w * w.h <= MAX_CELLS, `${w.w}x${w.h}`);
  assert.ok(w.res > 0.025 && w.zoom < 7);
  assert.ok(w.tiles.length < 600, `${w.tiles.length} tiles`);
  assert.ok(w.bbox[3] <= 80 && w.bbox[0] >= -180);
});

test('a single-place story still gets a world', () => {
  const w = worldFor({ beats: [beat(10, 50, 'ground')], labels: [] });
  assert.ok(w && w.bbox[0] < 10 && w.bbox[2] > 10);
  assert.equal(worldFor({ beats: [beat(0, 0, 'globe')], labels: [] }), null);
});
