// Value grids and colour ramps for the data layers (pure; runs in node and in the page).
//
// A Grid is a north-up lon/lat raster: values[row * cols + col], row 0 = north edge. Its
// cell centres sit half a cell inside the bbox. Sampling is bilinear and ignores nodata
// neighbours, so a coastline does not bleed a "no data" hole into the land.

export const MERC_MAX_LAT = 85.0511;

export class Grid {
  constructor({ west, south, east, north, cols, rows, values, nodata = null }) {
    Object.assign(this, { west, south, east, north, cols, rows, values, nodata });
    if (values.length !== cols * rows) throw new Error(`grid has ${values.length} values but ${cols} x ${rows} cells`);
    this.dx = (east - west) / cols;
    this.dy = (north - south) / rows;
  }
  valid(v) { return Number.isFinite(v) && v !== this.nodata; }
  cell(c, r) {
    if (c < 0 || r < 0 || c >= this.cols || r >= this.rows) return NaN;
    const v = this.values[r * this.cols + c];
    return this.valid(v) ? v : NaN;
  }
  contains(lon, lat) { return lon >= this.west && lon <= this.east && lat >= this.south && lat <= this.north; }
  /** Bilinear value at lon/lat; NaN outside the grid or where there is no data nearby. */
  sample(lon, lat) {
    if (!this.contains(lon, lat)) return NaN;
    const fx = (lon - this.west) / this.dx - 0.5, fy = (this.north - lat) / this.dy - 0.5;
    const c0 = Math.floor(fx), r0 = Math.floor(fy), tx = fx - c0, ty = fy - r0;
    let sum = 0, wsum = 0;
    for (const [dc, dr, w] of [[0, 0, (1 - tx) * (1 - ty)], [1, 0, tx * (1 - ty)], [0, 1, (1 - tx) * ty], [1, 1, tx * ty]]) {
      const v = this.cell(c0 + dc, r0 + dr);
      if (!Number.isNaN(v) && w > 0) { sum += v * w; wsum += w; }
    }
    return wsum > 1e-9 ? sum / wsum : NaN;
  }
  /** The part of the grid around bbox (plus `pad` cells), so only the needed cells travel to the page. */
  crop(bbox, pad = 2) {
    const [w, so, e, n] = bbox;
    const c0 = Math.max(0, Math.floor((w - this.west) / this.dx) - pad), c1 = Math.min(this.cols, Math.ceil((e - this.west) / this.dx) + pad);
    const r0 = Math.max(0, Math.floor((this.north - n) / this.dy) - pad), r1 = Math.min(this.rows, Math.ceil((this.north - so) / this.dy) + pad);
    const cols = Math.max(1, c1 - c0), rows = Math.max(1, r1 - r0), Ctor = this.values.constructor, values = new Ctor(cols * rows);
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) values[r * cols + c] = this.values[(r0 + r) * this.cols + c0 + c];
    return new Grid({ west: this.west + c0 * this.dx, east: this.west + (c0 + cols) * this.dx, north: this.north - r0 * this.dy, south: this.north - (r0 + rows) * this.dy, cols, rows, values, nodata: this.nodata });
  }
  /** Share (0..1) of sample points inside bbox that have data: used to refuse a dataset that does not cover the region. */
  coverage(bbox, step = 40, inside = null) {
    const [w, s, e, n] = bbox;
    let have = 0, total = 0;
    for (let i = 0; i < step; i++) for (let j = 0; j < step; j++) {
      const lon = w + ((i + 0.5) / step) * (e - w), lat = s + ((j + 0.5) / step) * (n - s);
      if (inside && !inside(lon, lat)) continue; // only count points that are really inside the region
      total++;
      if (!Number.isNaN(this.sample(lon, lat))) have++;
    }
    return total ? have / total : 0;
  }
  range(bbox) {
    let lo = Infinity, hi = -Infinity;
    const [w, s, e, n] = bbox, step = 40;
    for (let i = 0; i < step; i++) for (let j = 0; j < step; j++) {
      const v = this.sample(w + ((i + 0.5) / step) * (e - w), s + ((j + 0.5) / step) * (n - s));
      if (!Number.isNaN(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    }
    return [lo, hi];
  }
}

/** ESRI ASCII grid (.asc): ncols, nrows, xllcorner/xllcenter, yllcorner/yllcenter, cellsize, NODATA_value. */
export function parseAsciiGrid(text) {
  const lines = String(text).split(/\r?\n/);
  const head = {};
  let i = 0;
  for (; i < lines.length; i++) {
    const m = lines[i].trim().match(/^([A-Za-z_]+)\s+(-?[\d.eE+-]+)$/);
    if (!m) break;
    head[m[1].toLowerCase()] = Number(m[2]);
  }
  const need = ['ncols', 'nrows', 'cellsize'];
  for (const k of need) if (!(k in head)) throw new Error(`ASCII grid header is missing ${k}`);
  const cs = head.cellsize;
  const west = 'xllcenter' in head ? head.xllcenter - cs / 2 : head.xllcorner;
  const south = 'yllcenter' in head ? head.yllcenter - cs / 2 : head.yllcorner;
  if (west === undefined || south === undefined || Number.isNaN(west) || Number.isNaN(south)) throw new Error('ASCII grid header needs xllcorner and yllcorner');
  const nums = lines.slice(i).join(' ').split(/\s+/).filter(Boolean).map(Number);
  const cols = head.ncols, rows = head.nrows;
  if (nums.length < cols * rows) throw new Error(`ASCII grid has ${nums.length} values, expected ${cols * rows}`);
  return new Grid({ west, south, east: west + cols * cs, north: south + rows * cs, cols, rows, values: Float32Array.from(nums.slice(0, cols * rows)), nodata: head.nodata_value ?? -9999 });
}

/** Scattered "lon,lat,value" rows -> a grid by averaging into cells of `cellsize` degrees. */
export function gridFromPointsCsv(text, cellsize = 0.1) {
  const pts = [];
  for (const line of String(text).split(/\r?\n/)) {
    const [a, b, c] = line.split(/[;,\t]/).map(Number);
    if ([a, b, c].every(Number.isFinite)) pts.push([a, b, c]);
  }
  if (!pts.length) throw new Error('no "lon,lat,value" rows found in the file');
  const w = Math.min(...pts.map((p) => p[0])), e = Math.max(...pts.map((p) => p[0])), s = Math.min(...pts.map((p) => p[1])), n = Math.max(...pts.map((p) => p[1]));
  const cols = Math.max(1, Math.ceil((e - w) / cellsize) + 1), rows = Math.max(1, Math.ceil((n - s) / cellsize) + 1);
  const sum = new Float64Array(cols * rows), cnt = new Uint32Array(cols * rows);
  for (const [lon, lat, v] of pts) {
    const c = Math.min(cols - 1, Math.floor((lon - w) / cellsize)), r = Math.min(rows - 1, Math.floor((n - lat) / cellsize));
    sum[r * cols + c] += v; cnt[r * cols + c]++;
  }
  const values = new Float32Array(cols * rows).fill(-9999);
  for (let k = 0; k < values.length; k++) if (cnt[k]) values[k] = sum[k] / cnt[k];
  return new Grid({ west: w, south: n - rows * cellsize, east: w + cols * cellsize, north: n, cols, rows, values, nodata: -9999 });
}

// ---- colour ramps -----------------------------------------------------------------
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

/** Stops are [value, '#rrggbb']. Rainfall follows Reference 2: dry = orange, then yellow, green, teal, blue = wet. */
export const RAMPS = {
  rainfall: [[0, '#D9822B'], [250, '#E6B84A'], [600, '#C8D65A'], [1000, '#5DBB63'], [1500, '#2E9E8F'], [2200, '#2F6FB5']],
  heat: [[0, '#FFF3B0'], [0.35, '#FDBB5A'], [0.7, '#E8602C'], [1, '#8E1B1B']],
  density: [[0, '#2B1E5A'], [0.35, '#7A2E8E'], [0.7, '#E8602C'], [1, '#FBE040']],
  diverging: [[0, '#2F6FB5'], [0.5, '#F2F2F2'], [1, '#C8381F']],
};

/** Resolve a ramp name or custom stops; stops given on a 0..1 scale are stretched over [min, max]. */
export function resolveRamp(ramp, min, max) {
  const stops = typeof ramp === 'string' ? RAMPS[ramp] : ramp;
  if (!stops || stops.length < 2) throw new Error(`unknown colour ramp ${JSON.stringify(ramp)} (use ${Object.keys(RAMPS).join(', ')} or a list of [value, "#rrggbb"] stops)`);
  const unit = stops[stops.length - 1][0] <= 1;
  return stops.map(([v, c]) => [unit ? min + v * (max - min) : v, hex(c)]);
}

export function colorAt(stops, v) {
  if (v <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [v0, c0] = stops[i - 1], [v1, c1] = stops[i], t = (v - v0) / (v1 - v0 || 1);
      return [0, 1, 2].map((k) => Math.round(c0[k] + (c1[k] - c0[k]) * t));
    }
  }
  return stops[stops.length - 1][1];
}

// ---- mercator image space (what a MapLibre image source expects) -----------------------
export const mercY = (lat) => { const s = Math.sin((Math.max(-MERC_MAX_LAT, Math.min(MERC_MAX_LAT, lat)) * Math.PI) / 180); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };
export const mercLat = (y) => (180 / Math.PI) * Math.atan(0.5 * (Math.exp(Math.PI - 2 * Math.PI * y) - Math.exp(-(Math.PI - 2 * Math.PI * y))));

/** Pixel size of a bbox image whose rows are evenly spaced in mercator y (so it overlays the map without squashing). */
export function imageSize(bbox, maxW = 1800) {
  const [w, s, e, n] = bbox;
  const aspect = ((mercY(s) - mercY(n)) * 2 * Math.PI) / (((e - w) * Math.PI) / 180);
  const width = Math.max(2, Math.min(maxW, Math.round(((e - w) / 360) * 4096)));
  return { width, height: Math.max(2, Math.round(width * aspect)) };
}

/** Colour a grid into RGBA pixels for bbox. Cells without data are transparent. */
export function renderGridRGBA(grid, bbox, stops, { width, height }, alpha = 255) {
  const [w, s, e, n] = bbox, out = new Uint8ClampedArray(width * height * 4);
  const y0 = mercY(n), y1 = mercY(s);
  for (let j = 0; j < height; j++) {
    const lat = mercLat(y0 + ((j + 0.5) / height) * (y1 - y0));
    for (let i = 0; i < width; i++) {
      const v = grid.sample(w + ((i + 0.5) / width) * (e - w), lat);
      if (Number.isNaN(v)) continue;
      const [r, g, b] = colorAt(stops, v), k = (j * width + i) * 4;
      out[k] = r; out[k + 1] = g; out[k + 2] = b; out[k + 3] = alpha;
    }
  }
  return out;
}
