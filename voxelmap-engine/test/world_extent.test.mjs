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

import { parseStory, normDate } from '../lib/beats_csv.mjs';

test('a CSV from another style says which section it belongs to', () => {
  const roblox = 'row,id,chapter,text,date,location,environment,camera,extra\nplan,,,"T",2026,,,,\nchapter,,"C",,"2:00 AM",,,,\nbeat,b1,,"Hi.",,Bedroom,interior,wide,\n';
  assert.throws(() => parseStory(roblox), /Roblox Cinema section/);
  assert.throws(() => parseStory('beat,row,vo_anchor,mode,id,text\n1,beat,,map,b1,Hi.\n'), /Hybrid Map \/ StarMap/);
});

test('common date forms become YYYY-MM; times and words are still refused', () => {
  assert.equal(normDate('1754'), '1754-01');
  assert.equal(normDate('1754-5'), '1754-05');
  assert.equal(normDate('1754-05-12'), '1754-05');
  assert.equal(normDate('-218'), '-0218-01');
  assert.equal(normDate('2:00 AM'), '2:00 AM');
  const csv = 'row,id,date,place,lon,lat,rung,text,extra\nplan,T,,,,,,,"{""world"":""indochina""}"\nchapter,c1,,,,,,One,\nbeat,b1,1954-3-7,Hanoi,105.8,21.0,map,Hello there.,\n';
  assert.equal(parseStory(csv).beats[0].date, '1954-03');
  assert.throws(() => parseStory(csv.replace('1954-3-7', 'March')), /date must be YYYY-MM/);
});

test('a story reaching the 180 degree line never asks for a tile past the map edge (HTTP 404)', () => {
  const w = worldFor({ beats: [{ lon: 139.7, lat: 35.7 }, { lon: -157.9, lat: 21.3 }, { lon: 179.5, lat: -10 }, { lon: -179.5, lat: 60 }] });
  const n = 2 ** w.zoom;
  assert.equal(w.bbox[2], 180);
  for (const t of w.tiles) { const [, x, y] = t.split('/').map(Number); assert.ok(x >= 0 && x < n && y >= 0 && y < n, t); }
});
