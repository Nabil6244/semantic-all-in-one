import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Grid, parseAsciiGrid, gridFromPointsCsv, resolveRamp, colorAt, RAMPS, imageSize, renderGridRGBA, mercY, mercLat } from '../lib/raster.mjs';
import { multiCentroid, multiAreaKm2, moveShapeTrueScale, bboxOfPolys, pointInPolys, polyBoxes, ringAreaKm2, mainPolys } from '../lib/shapes.mjs';
import { placesToDots } from '../lib/points.mjs';
import { loadBundledGrid, loadBundledPlaces, loadCountries, regionPolys, resolveEvent, resolveSpecData, loadGridFile, DataError } from '../lib/datasets.mjs';
import { validateEvents } from '../lib/events.mjs';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-data-'));

test('grid: bilinear sampling, nodata is ignored (no holes at a coastline), outside is NaN', () => {
  const g = new Grid({ west: 0, east: 2, south: 0, north: 2, cols: 2, rows: 2, values: Float32Array.from([10, 20, 30, -9999]), nodata: -9999 });
  assert.equal(g.sample(0.5, 1.5), 10);           // centre of the north-west cell
  assert.equal(g.sample(1.0, 1.5), 15);           // half way between the two northern cells
  assert.ok(Number.isNaN(g.sample(1.5, 0.5)), 'the centre of an empty cell stays empty');
  const near = g.sample(1.3, 0.7);
  assert.ok(near >= 20 && near <= 30, `next to the empty cell the value comes only from cells that have data (${near})`);
  assert.equal(g.sample(1.0, 1.0), 20);           // the empty cell contributes nothing: mean of 10, 20, 30
  assert.ok(Number.isNaN(g.sample(-1, 1)));
  assert.throws(() => new Grid({ west: 0, east: 1, south: 0, north: 1, cols: 2, rows: 2, values: new Float32Array(3) }), /3 values but 2 x 2/);
});

test('grid: crop keeps the cells around a region and the same values', () => {
  const vals = Float32Array.from({ length: 100 }, (_, i) => i);
  const g = new Grid({ west: 0, east: 10, south: 0, north: 10, cols: 10, rows: 10, values: vals });
  const c = g.crop([3, 3, 5, 5], 1);
  assert.ok(c.cols < g.cols && c.rows < g.rows);
  for (const [lon, lat] of [[3.5, 4.5], [4.5, 3.5], [4.2, 4.8]]) assert.equal(c.sample(lon, lat), g.sample(lon, lat));
});

test('ESRI ASCII grid and lon,lat,value CSV load into grids', () => {
  const asc = 'ncols 3\nnrows 2\nxllcorner 30\nyllcorner -2\ncellsize 1\nNODATA_value -9999\n1 2 3\n4 -9999 6\n';
  const g = parseAsciiGrid(asc);
  assert.deepEqual([g.west, g.east, g.south, g.north], [30, 33, -2, 0]);
  assert.equal(g.sample(30.5, -0.5), 1);
  assert.ok(Number.isNaN(g.cell(1, 1)));
  assert.throws(() => parseAsciiGrid('ncols 3\nnrows 2\n1 2'), /cellsize/);
  const c = gridFromPointsCsv('lon,lat,value\n30.2,0.2,100\n30.3,0.3,200\n32.5,2.5,50\n', 1);
  assert.equal(c.sample(c.west + 0.5, c.north - 2.5), 150, 'two points in one cell are averaged');
  assert.throws(() => gridFromPointsCsv('a,b\n'), /no "lon,lat,value" rows/);
});

test('a GeoTIFF in lon/lat loads; one in another projection is refused with advice', async () => {
  const { writeArrayBuffer } = await import('geotiff');
  const dir = tmp(), values = Float32Array.from([1, 2, 3, 4, 5, 6]);
  const mk = (epsg) => Buffer.from(writeArrayBuffer(values, { width: 3, height: 2, ModelPixelScale: [1, 1, 0], ModelTiepoint: [0, 0, 0, 30, 0, 0], GeographicTypeGeoKey: epsg, GTModelTypeGeoKey: 2, GTRasterTypeGeoKey: 1, GeogAngularUnitsGeoKey: 9102 }));
  fs.writeFileSync(path.join(dir, 'ok.tif'), mk(4326));
  const g = await loadGridFile(path.join(dir, 'ok.tif'));
  assert.deepEqual([g.cols, g.rows, g.west, g.north], [3, 2, 30, 0]);
  assert.equal(g.values[5], 6);
  fs.writeFileSync(path.join(dir, 'odd.tif'), mk(3857));
  await assert.rejects(() => loadGridFile(path.join(dir, 'odd.tif')), /EPSG:3857.*EPSG:4326/);
  await assert.rejects(() => loadGridFile(path.join(dir, 'x.png')), /unsupported grid file type/);
});

test('ramps: rainfall runs dry orange to wet blue; custom and 0..1 stops work; unknown ramps are rejected', () => {
  const st = resolveRamp('rainfall', 0, 2200);
  assert.deepEqual(colorAt(st, -50), [0xD9, 0x82, 0x2B]);
  assert.deepEqual(colorAt(st, 5000), [0x2F, 0x6F, 0xB5]);
  const mid = colorAt(st, 800);
  assert.ok(mid[1] > mid[0] - 40 && mid[1] > 150, `800 mm should be yellow-green, got ${mid}`);
  const unit = resolveRamp('heat', 10, 20);
  assert.equal(unit[0][0], 10); assert.equal(unit[unit.length - 1][0], 20);
  assert.equal(resolveRamp([[0, '#000000'], [10, '#ffffff']], 0, 1).length, 2);
  assert.throws(() => resolveRamp('nope', 0, 1), /unknown colour ramp/);
  assert.ok(Object.keys(RAMPS).includes('density'));
});

test('mercator image: rows are evenly spaced in mercator y, round trip is exact, output is transparent where there is no data', () => {
  for (const lat of [-60, -10, 0, 33, 70]) assert.ok(Math.abs(mercLat(mercY(lat)) - lat) < 1e-9);
  const { width, height } = imageSize([30, -5, 42, 5], 800);
  assert.ok(width > 100 && height > 50);
  const g = new Grid({ west: 30, east: 36, south: -5, north: 5, cols: 6, rows: 10, values: new Float32Array(60).fill(100) });
  const px = renderGridRGBA(g, [30, -5, 42, 5], resolveRamp('rainfall', 0, 2200), { width: 12, height: 10 });
  assert.equal(px[3], 255);                    // west edge: data
  assert.equal(px[(11) * 4 + 3], 0);           // east edge: outside the grid -> transparent
});

test('shapes: a country moved to another latitude keeps its true area (a plain degree shift does not)', () => {
  const pol = loadCountries().get('POL').polys, area = multiAreaKm2(pol);
  assert.ok(Math.abs(area - 312696) / 312696 < 0.02, `Poland ${area.toFixed(0)} km2`);
  const equator = moveShapeTrueScale(pol, { lon: 37.6, lat: 2.6 });
  assert.ok(Math.abs(multiAreaKm2(equator) - area) / area < 0.03, `moved area ${multiAreaKm2(equator).toFixed(0)}`);
  const [lon0, lat0] = multiCentroid(pol), naive = pol.map((p) => p.map((r) => r.map(([x, y]) => [x - lon0 + 37.6, y - lat0 + 2.6])));
  assert.ok(Math.abs(multiAreaKm2(naive) - area) / area > 0.2, 'a plain shift from 52 N to the equator changes the area a lot');
  const [cx, cy] = multiCentroid(equator);
  assert.ok(Math.abs(cx - 37.6) < 0.5 && Math.abs(cy - 2.6) < 0.5, `centre lands on target (${cx.toFixed(2)}, ${cy.toFixed(2)})`);
});

test('shapes: overseas islets are dropped from a country\'s main landmass (Norway keeps Norway, not Bouvet Island)', () => {
  const nor = loadCountries().get('NOR').polys, main = mainPolys(nor), bb = bboxOfPolys(main);
  assert.ok(bboxOfPolys(nor)[1] < -50, 'the raw bbox reaches Bouvet Island in the south Atlantic');
  assert.ok(bb[1] > 55, `main landmass starts around 57 N (got ${bb[1]})`);
});

test('shapes: point in polygon honours holes and multi-part countries', () => {
  const sq = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]], hole = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], inner = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]];
  const polys = [[hole, inner], [[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]]];
  const boxes = polyBoxes(polys);
  assert.equal(pointInPolys(2, 2, polys, boxes), true);
  assert.equal(pointInPolys(5, 5, polys, boxes), false);
  assert.equal(pointInPolys(25, 5, polys, boxes), true);
  assert.equal(pointInPolys(15, 5, polys, boxes), false);
  assert.deepEqual(bboxOfPolys(polys), [0, 0, 30, 10]);
  assert.ok(ringAreaKm2([[0, 0], [1, 0], [1, 1], [0, 1]]) > 12000);
  void sq;
});

test('bundled rainfall: dry north-west Kenya is dry, the western highlands are wet, the Amazon is very wet', () => {
  const { grid, meta } = loadBundledGrid('rainfall_chirps');
  assert.equal(meta.unit, 'mm/year');
  const lodwar = grid.sample(35.6, 3.12), kakamega = grid.sample(34.75, 0.28), amazon = grid.sample(-60, -3);
  assert.ok(lodwar < 450, `Lodwar ${lodwar}`);
  assert.ok(kakamega > 1300, `Kakamega ${kakamega}`);
  assert.ok(amazon > 1800, `Amazon ${amazon}`);
  assert.ok(Number.isNaN(grid.sample(0, 0 + 60)), 'north of 50 N the dataset has no data');
  assert.ok(grid.coverage([34, -4, 42, 4]) > 0.5);
});

test('populated places become dots around real places: deterministic, inside the country, more dots for bigger places', () => {
  const { places } = loadBundledPlaces();
  assert.ok(places.length > 7000);
  const ken = regionPolys(['KEN']), boxes = polyBoxes(ken), bb = bboxOfPolys(ken);
  const here = places.filter(([lon, lat]) => lon >= bb[0] && lon <= bb[2] && lat >= bb[1] && lat <= bb[3]);
  const accept = (x, y) => pointInPolys(x, y, ken, boxes);
  const a = placesToDots(here, { perMillion: 200, seed: 5, accept }), b = placesToDots(here, { perMillion: 200, seed: 5, accept });
  assert.deepEqual(a, b);
  assert.ok(a.length > 300);
  assert.ok(a.every(([x, y]) => accept(x, y)));
  const nbo = a.filter(([x, y]) => Math.hypot(x - 36.82, y + 1.29) < 0.6).length, small = a.filter(([x, y]) => Math.hypot(x - 35.6, y - 3.1) < 0.6).length;
  assert.ok(nbo > small * 3, `Nairobi ${nbo} vs Lodwar ${small}`);
});

test('data layers: missing or wrong data is a clear error that says what to supply', async () => {
  const run = (e, o) => resolveEvent({ id: 'x', t_in: 0, t_out: 5, ...e }, o);
  await assert.rejects(() => run({ type: 'value_overlay' }), /needs data.*bundled:rainfall_chirps.*file:/);
  await assert.rejects(() => run({ type: 'value_overlay', data: 'bundled:nope' }), /unknown bundled dataset/);
  await assert.rejects(() => run({ type: 'value_overlay', data: 'bundled:rainfall_chirps', clip_iso: ['NOR'] }), /covers only 0%.*land between 50 N and 50 S.*file:/);
  await assert.rejects(() => run({ type: 'value_overlay', data: 'file:missing.tif' }, { baseDir: tmp() }), /data file not found: missing.tif/);
  await assert.rejects(() => run({ type: 'value_overlay', data: 'rain.tif' }), /must start with "bundled:" or "file:"/);
  await assert.rejects(() => run({ type: 'value_overlay', data: 'bundled:rainfall_chirps', clip_iso: ['XXX'] }), /unknown country code "XXX"/);
  await assert.rejects(() => run({ type: 'dots', data: 'bundled:populated_places' }), /say which area/);
  await assert.rejects(() => run({ type: 'ghost_shape', iso: 'ZZZ', to: { lon: 0, lat: 0 } }), /unknown country code "ZZZ"/);
  await assert.rejects(() => run({ type: 'streak' }), /say where the streaks go/);
  await assert.rejects(() => run({ type: 'dots', data: 'file:pts.csv' }, { baseDir: tmp() }), DataError);
});

test('data layers resolve with credits and facts the author can quote', async () => {
  const dir = tmp();
  fs.writeFileSync(path.join(dir, 'pts.csv'), 'lat,lon\n-1.2,36.8\n0.5,35.2\n');
  const spec = { events: [
    { id: 'rain', type: 'value_overlay', t_in: 0, t_out: 5, data: 'bundled:rainfall_chirps', clip_iso: ['KEN'] },
    { id: 'pol', type: 'ghost_shape', t_in: 0, t_out: 5, iso: 'POL', to: { lon: 37.6, lat: 2.6 } },
    { id: 'own', type: 'dots', t_in: 0, t_out: 5, data: 'file:pts.csv' },
    { id: 'st', type: 'streak', t_in: 0, t_out: 5, region_iso: ['KEN'], n: 20, seed: 2 },
    { id: 'cap', type: 'caption', t_in: 0, t_out: 5, text: 'X' },
  ] };
  const { events, credits } = await resolveSpecData(spec, { baseDir: dir });
  const by = Object.fromEntries(events.map((e) => [e.id, e]));
  assert.ok(by.rain.data_range[0] > 100 && by.rain.data_range[1] > 1800);
  assert.equal(by.rain.ramp, 'rainfall');
  assert.ok(by.rain.grid.cols < 3600, 'only the cells around Kenya are sent');
  assert.ok(Math.abs(by.pol.area_km2 - 312696) / 312696 < 0.02);
  assert.deepEqual(by.own.points, [[36.8, -1.2], [35.2, 0.5]]);
  assert.equal(by.st.seeds.length, 20);
  assert.equal(by.cap.text, 'X');
  assert.ok(credits.some((c) => /CHIRPS/.test(c)) && credits.some((c) => /supplied by the author/.test(c)));
});

test('timeline validation knows the data layer types', () => {
  const t = (e) => validateEvents([{ id: 'e', t_in: 0, t_out: 5, ...e }], 10).errors.join();
  assert.match(t({ type: 'value_overlay' }), /needs data/);
  assert.match(t({ type: 'ghost_shape', to: { lon: 1, lat: 1 } }), /needs iso/);
  assert.match(t({ type: 'ghost_shape', iso: 'POL' }), /needs to:/);
  assert.match(t({ type: 'streak' }), /region_iso or bbox/);
  assert.equal(t({ type: 'dots', data: 'bundled:populated_places', region_iso: ['KEN'] }), '');
  assert.equal(t({ type: 'value_overlay', data: 'bundled:rainfall_chirps' }), '');
});
