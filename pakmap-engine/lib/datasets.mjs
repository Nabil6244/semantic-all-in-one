// Data sources for the data layers (node side). A layer names its data as
//   "bundled:<id>"   a small open dataset shipped in data/  (rainfall_chirps, populated_places)
//   "file:<path>"    the author's own file: GeoTIFF / ESRI ASCII grid / lon,lat,value CSV for grids,
//                    lat,lon CSV for points (path is relative to the spec file's folder)
// User files win over bundled data simply by being named. A layer whose data is missing or
// does not cover its region is a clear error, never a silent drop.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { Grid, parseAsciiGrid, gridFromPointsCsv, RAMPS } from './raster.mjs';
import { parsePointsCsv, placesToDots } from './points.mjs';
import { bboxOfPolys, mainPolys, multiAreaKm2, multiCentroid, moveShapeTrueScale, pointInPolys, polyBoxes } from './shapes.mjs';
import { rng } from './anim.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DATA_DIR = path.join(HERE, '..', 'data');

export class DataError extends Error {}

export const BUNDLED = {
  rainfall_chirps: { kind: 'grid' },
  populated_places: { kind: 'places' },
};

export function bundledMeta(id) {
  if (!BUNDLED[id]) throw new DataError(`unknown bundled dataset "${id}" (available: ${Object.keys(BUNDLED).join(', ')})`);
  return JSON.parse(fs.readFileSync(path.join(DATA_DIR, `${id}.json`), 'utf8'));
}

const cache = new Map();
const once = (key, fn) => { if (!cache.has(key)) cache.set(key, fn()); return cache.get(key); };

export function loadBundledGrid(id) {
  const meta = bundledMeta(id);
  if (meta.kind !== 'grid') throw new DataError(`"${id}" is not a grid dataset`);
  return once(`grid:${id}`, () => {
    const buf = zlib.gunzipSync(fs.readFileSync(path.join(DATA_DIR, meta.file)));
    const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
    return { meta, grid: new Grid({ ...meta, values: new Int16Array(ab) }) };
  });
}

export function loadBundledPlaces(id = 'populated_places') {
  return once(`places:${id}`, () => {
    const meta = bundledMeta(id);
    return { meta, places: JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(DATA_DIR, meta.file))).toString('utf8')) };
  });
}

let countries = null;
/** ISO3 -> MultiPolygon coordinates, from the countries file the map engines already ship. */
export function loadCountries(file) {
  if (countries && !file) return countries;
  const f = file || path.join(HERE, '..', '..', 'map_scene', 'data', 'countries.json.gz');
  const raw = JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString('utf8'));
  const map = new Map();
  for (const ft of raw.features) {
    const g = ft.g;
    map.set(ft.iso, { name: ft.n, polys: g.type === 'Polygon' ? [g.coordinates] : g.coordinates });
  }
  if (!file) countries = map;
  return map;
}

export function regionPolys(isoList, file) {
  const map = loadCountries(file), polys = [];
  for (const iso of isoList) {
    const c = map.get(iso);
    if (!c) throw new DataError(`unknown country code "${iso}" (use ISO 3166 alpha-3, e.g. KEN)`);
    polys.push(...c.polys);
  }
  return polys;
}

/** Grid from a user file, chosen by extension. */
export async function loadGridFile(file) {
  const ext = path.extname(file).toLowerCase();
  if (ext === '.asc') return parseAsciiGrid(fs.readFileSync(file, 'utf8'));
  if (ext === '.csv' || ext === '.txt') return gridFromPointsCsv(fs.readFileSync(file, 'utf8'));
  if (ext === '.tif' || ext === '.tiff') {
    let fromArrayBuffer;
    try { ({ fromArrayBuffer } = await import('geotiff')); } catch {
      throw new DataError(`${path.basename(file)}: GeoTIFF support is not installed in this copy of the renderer. Save the grid as an ESRI ASCII grid (.asc) or a lon,lat,value .csv instead.`);
    }
    const buf = fs.readFileSync(file);
    const tiff = await fromArrayBuffer(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
    const img = await tiff.getImage();
    const keys = img.getGeoKeys?.() || {};
    const epsg = keys.GeographicTypeGeoKey || keys.ProjectedCSTypeGeoKey;
    if (epsg && epsg !== 4326) throw new DataError(`${path.basename(file)} uses EPSG:${epsg}; pakMap needs plain longitude/latitude (EPSG:4326). Re-save it in WGS 84.`);
    const [west, south, east, north] = img.getBoundingBox();
    const [raster] = await img.readRasters();
    const nodata = img.getGDALNoData();
    return new Grid({ west, south, east, north, cols: img.getWidth(), rows: img.getHeight(), values: Float32Array.from(raster), nodata: nodata ?? null });
  }
  throw new DataError(`${path.basename(file)}: unsupported grid file type "${ext}" (use .tif, .asc or a lon,lat,value .csv)`);
}

function fileOf(data, baseDir) {
  const rel = data.slice('file:'.length);
  const f = path.resolve(baseDir || '.', rel);
  if (!fs.existsSync(f)) throw new DataError(`data file not found: ${rel} (looked in ${path.dirname(f)})`);
  return f;
}

const regionBBox = (e, countriesFile) => (e.clip_iso ? bboxOfPolys(regionPolys(e.clip_iso, countriesFile)) : e.bbox || null);

/** Fill in everything a data layer needs, on a copy of the event; throws DataError with advice. */
export async function resolveEvent(e, { baseDir, countriesFile } = {}) {
  const out = { ...e };
  const credits = [];
  const where = `${e.type} "${e.id}"`;
  if (e.type === 'value_overlay') {
    if (!e.data) throw new DataError(`${where}: needs data. Use "bundled:rainfall_chirps" or your own file as "file:grid.tif" (.tif, .asc or lon,lat,value .csv).`);
    let grid, meta = null;
    if (e.data.startsWith('bundled:')) ({ grid, meta } = loadBundledGrid(e.data.slice(8)));
    else if (e.data.startsWith('file:')) grid = await loadGridFile(fileOf(e.data, baseDir));
    else throw new DataError(`${where}: data must start with "bundled:" or "file:" (got ${JSON.stringify(e.data)})`);
    const polys = e.clip_iso ? mainPolys(regionPolys(e.clip_iso, countriesFile)) : null; // main landmass: no overseas islets stretching the picture
    const bbox = polys ? bboxOfPolys(polys) : e.bbox || [grid.west, grid.south, grid.east, grid.north];
    const pb = polys ? polyBoxes(polys) : null;
    const cov = grid.coverage(bbox, 40, polys ? (x, y) => pointInPolys(x, y, polys, pb) : null);
    if (cov < 0.5) {
      const where2 = meta?.coverage ? ` It covers ${meta.coverage}.` : '';
      throw new DataError(`${where}: the data covers only ${(cov * 100).toFixed(0)}% of the region.${where2} Supply your own grid with data: "file:..." for this area.`);
    }
    const [lo, hi] = grid.range(bbox);
    const ramp = e.ramp ?? meta?.ramp ?? 'heat';
    if (typeof ramp === 'string' && !RAMPS[ramp]) throw new DataError(`${where}: unknown ramp "${ramp}" (use ${Object.keys(RAMPS).join(', ')} or custom stops)`);
    const part = grid.crop(bbox); // only the cells around the region travel to the page
    out.grid = { west: part.west, south: part.south, east: part.east, north: part.north, cols: part.cols, rows: part.rows, nodata: part.nodata, b64: Buffer.from(part.values.buffer, part.values.byteOffset, part.values.byteLength).toString('base64'), type: part.values instanceof Int16Array ? 'i16' : 'f32' };
    out.bbox = bbox; out.min = e.min ?? (typeof ramp === 'string' && ramp === 'rainfall' ? 0 : lo); out.max = e.max ?? (ramp === 'rainfall' ? 2200 : hi);
    out.ramp = ramp;
    if (polys) out.clip_rings = polys;
    out.unit = meta?.unit; out.data_range = [lo, hi];
    credits.push(meta?.attribution || `Grid data: ${path.basename(e.data.slice(5))} (supplied by the author)`);
  } else if (e.type === 'dots' && e.data) {
    const polys = e.region_iso ? mainPolys(regionPolys(e.region_iso, countriesFile)) : null;
    const boxes = polys ? polyBoxes(polys) : null;
    if (e.data.startsWith('bundled:')) {
      const { meta, places } = loadBundledPlaces(e.data.slice(8));
      if (!polys && !e.bbox) throw new DataError(`${where}: say which area to fill: region_iso: ["KEN"] or bbox: [west, south, east, north].`);
      const bb = polys ? bboxOfPolys(polys) : e.bbox;
      const inBox = places.filter(([lon, lat]) => lon >= bb[0] && lon <= bb[2] && lat >= bb[1] && lat <= bb[3]);
      if (!inBox.length) throw new DataError(`${where}: no populated places in that area. Supply your own points with data: "file:points.csv".`);
      out.points = placesToDots(inBox, { perMillion: e.per_million ?? 60, minPerPlace: e.min_per_place ?? 1, maxDots: e.max_dots ?? 6000, seed: e.seed ?? 1, accept: polys ? (x, y) => pointInPolys(x, y, polys, boxes) : null });
      credits.push(meta.attribution);
    } else if (e.data.startsWith('file:')) {
      out.points = parsePointsCsv(fs.readFileSync(fileOf(e.data, baseDir), 'utf8'), e.order || 'lat,lon');
      if (!out.points.length) throw new DataError(`${where}: no "lat,lon" rows found in ${e.data.slice(5)}`);
      credits.push(`Point data: ${path.basename(e.data.slice(5))} (supplied by the author)`);
    } else throw new DataError(`${where}: data must start with "bundled:" or "file:"`);
  } else if (e.type === 'ghost_shape') {
    const src = loadCountries(countriesFile).get(e.iso);
    if (!src) throw new DataError(`${where}: unknown country code "${e.iso}" (use ISO 3166 alpha-3, e.g. POL)`);
    out.source_name = src.name;
    out.area_km2 = Math.round(multiAreaKm2(src.polys));
    out.source_centre = multiCentroid(src.polys);
    out.polys = moveShapeTrueScale(src.polys, e.to, out.source_centre);
  } else if (e.type === 'streak') {
    const polys = e.region_iso ? mainPolys(regionPolys(e.region_iso, countriesFile)) : null;
    const bb = polys ? bboxOfPolys(polys) : e.bbox;
    if (!bb) throw new DataError(`${where}: say where the streaks go: region_iso: ["KEN"] or bbox: [west, south, east, north].`);
    const boxes = polys ? polyBoxes(polys) : null, r = rng(e.seed ?? 1), seeds = [];
    for (let tries = 0; seeds.length < (e.n ?? 36) && tries < 20000; tries++) {
      const lon = bb[0] + r() * (bb[2] - bb[0]), lat = bb[1] + r() * (bb[3] - bb[1]);
      if (!polys || pointInPolys(lon, lat, polys, boxes)) seeds.push([lon, lat, r()]);
    }
    if (!seeds.length) throw new DataError(`${where}: could not place any streaks inside that region`);
    out.seeds = seeds;
  }
  return { event: out, credits };
}

/** Resolve every data layer in a spec; returns the new events and the credits to add to the sidecar. */
export async function resolveSpecData(spec, opts = {}) {
  const credits = new Set(), events = [];
  for (const e of spec.events || []) {
    if (['value_overlay', 'ghost_shape', 'streak'].includes(e.type) || (e.type === 'dots' && e.data)) {
      const r = await resolveEvent(e, opts);
      events.push(r.event); r.credits.forEach((c) => credits.add(c));
    } else events.push(e);
  }
  return { events, credits: [...credits] };
}
