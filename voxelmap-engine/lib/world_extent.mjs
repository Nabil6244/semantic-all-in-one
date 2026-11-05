// The world a story needs when its `world` is not built yet: a box around every place the story names, the grid size and the
// elevation download it would take. tools/build_world.py builds it (runner.build_world); nothing here touches the network.

export const MAX_CELLS = 2.6e6;      // the largest built world (Mediterranean) is 1.9 M cells; bigger boxes get coarser blocks instead
export const MB_PER_TILE = 0.067;    // average Terrarium PNG in cache/terrarium

/** Every lon/lat the story puts on the map (globe beats sit on the globe asset, not the world). */
export function storyPoints(story) {
  const pts = [];
  const add = (p) => { if (Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])) pts.push([p[0], p[1]]); };
  for (const b of story.beats || []) {
    if (b.rung === 'globe') continue;
    add([b.lon, b.lat]);
    for (const p of b.path || []) add(p);
    for (const e of b.effects || []) { add(e.at); add(e.to); }
    for (const c of b.cards || []) add([c.lon, c.lat]);
  }
  for (const l of story.labels || []) add([l.lon, l.lat]);
  return pts;
}

const txy = (lon, lat, z) => { const n = 2 ** z, r = (lat * Math.PI) / 180; return [((lon + 180) / 360) * n, ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n]; };

/** {bbox, res, zoom, w, h, tiles: ["z/x/y"]} for a world around the story's places, or null when the story names no place. */
export function worldFor(story) {
  const pts = storyPoints(story);
  if (!pts.length) return null;
  const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
  let lon0 = Math.min(...lons), lon1 = Math.max(...lons), lat0 = Math.min(...lats), lat1 = Math.max(...lats);
  // margin for the map views around the places: at least 4 degrees, more for a wide story; at least 12 degrees across
  const padX = Math.max(4, 0.15 * (lon1 - lon0)), padY = Math.max(4, 0.15 * (lat1 - lat0));
  lon0 -= padX; lon1 += padX; lat0 -= padY; lat1 += padY;
  const grow = (a, b, min) => { const d = Math.max(0, min - (b - a)) / 2; return [a - d, b + d]; };
  [lon0, lon1] = grow(lon0, lon1, 12); [lat0, lat1] = grow(lat0, lat1, 12);
  lon0 = Math.max(-180, Math.floor(lon0)); lon1 = Math.min(180, Math.ceil(lon1));
  lat0 = Math.max(-80, Math.floor(lat0)); lat1 = Math.min(80, Math.ceil(lat1));   // Terrarium tiles are Web Mercator
  const area = (lon1 - lon0) * (lat1 - lat0);
  let res = 0.025;
  while (area / (res * res) > MAX_CELLS) res = +(res + 0.005).toFixed(3);
  // the coarsest tile zoom whose pixels are still at most half a block
  let zoom = 3;
  while (zoom < 7 && 360 / (2 ** zoom * 256) > res / 2) zoom++;
  const [x0, y0] = txy(lon0, lat1, zoom), [x1, y1] = txy(lon1, lat0, zoom), tiles = [];
  for (let y = Math.floor(y0); y <= Math.floor(y1); y++) for (let x = Math.floor(x0); x <= Math.floor(x1); x++) tiles.push(`${zoom}/${x}/${y}`);
  return { bbox: [lon0, lat0, lon1, lat1], res, zoom, w: Math.round((lon1 - lon0) / res), h: Math.round((lat1 - lat0) / res), tiles };
}
