// Weather page: a COPY of pakmap-engine/page.js (see UPSTREAM.json). Changes from the original, and nothing else: pakMap's
// modules load from /pakmap-engine/lib/; timed satellite layers (spec.weather.satellite) sit above the base imagery; the
// weather graphics (lib/wx_draw.mjs, plus every plugin in lib/layers/) are drawn after pakMap's overlay; timed tile loops
// (spec.weather.rasters: radar, satellite loops) step through their frames; a satellite/radar tile that cannot be downloaded
// shows the base imagery instead of stopping the render, and a dark or empty one (night, no rain) is not mistaken for a broken one.
//
// --- the original header follows ---
// Runs inside the hidden browser. Builds ONE map from /spec.json and exposes
// window.renderFrame(t): evaluates the shared camera + imagery selection for
// time t (seconds), draws that exact frame, and resolves with a JPEG (base64)
// once every tile for it is on screen.
import * as maplibregl from '/maplibre/maplibre-gl.mjs';
import { createCamera, metersPerPixel, frameWidthKm, easings } from '/pakmap-engine/lib/camera.mjs';
import { selectLayers } from '/pakmap-engine/lib/imagery.mjs';
import { createOverlay } from '/pakmap-engine/lib/draw.mjs';
import { freezeWindows } from '/pakmap-engine/lib/events.mjs';
import { Grid, resolveRamp, imageSize, renderGridRGBA, mercY } from '/pakmap-engine/lib/raster.mjs';
import { FILL_ROLES } from '/pakmap-engine/lib/style.mjs';
import { lifeAlpha } from '/pakmap-engine/lib/anim.mjs';
import { footageWindows, shiftedEvent } from '/pakmap-engine/lib/hybrid.mjs';
import { createWxOverlay } from '/weather-engine/lib/wx_draw.mjs';
import { frameAt } from '/weather-engine/lib/wx_raster.mjs';
import wxPlugins from '/weather-engine/plugins.mjs';

const clamp01 = (v) => Math.max(0, Math.min(1, v));

async function setup() {
  const spec = await (await fetch('/spec.json')).json();
  const W = spec.width, H = spec.height;
  // 4K export: the layout stays W x H (camera, zoom, card positions are unchanged); every frame has R times the pixels.
  const R = spec.pixel_scale || 1;
  const providers = spec.providers; // coarse -> fine, resolved by the renderer
  const wxSat = (spec.weather && spec.weather.satellite) || [];   // timed satellite layers (weather)
  const wxRasters = (spec.weather && spec.weather.rasters) || [];  // timed tile loops: radar, satellite loops (weather)
  const rasterProv = wxRasters.flatMap((r) => r.frames.map((f) => f.provider));
  const isWx = new Set([...wxSat.map((s) => s.provider.id), ...rasterProv.map((p) => p.id)]);
  const byId = Object.fromEntries([...providers, ...wxSat.map((s) => s.provider), ...rasterProv].map((p) => [p.id, p]));
  const imagery = spec.imagery;
  const camera = createCamera({ camera: spec.camera, width: W, height: H, duration: spec.duration, freeze: freezeWindows(spec.events) });
  await document.fonts.load("800 40px PakMapSans");
  const overlays = spec.overlays || {};
  const tokens = spec.tokens || {};
  const offline = spec.imagery_enabled === false; // tests: no tiles, flat colour instead

  // ---- tile protocol: fetch from the local cache server; optionally key out black "no data" ----
  const clearPng = await (async () => {
    const c = new OffscreenCanvas(1, 1);
    c.getContext('2d').clearRect(0, 0, 1, 1);
    return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer();
  })();
  async function keyBlack(blob) {
    const bmp = await createImageBitmap(blob);
    const c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext('2d', { willReadFrequently: true });
    g.drawImage(bmp, 0, 0);
    const img = g.getImageData(0, 0, c.width, c.height), d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      const lum = d[i] + d[i + 1] + d[i + 2];
      if (lum < 18) d[i + 3] = 0;
      else if (lum < 54) d[i + 3] = Math.round(((lum - 18) / 36) * 255);
    }
    g.putImageData(img, 0, 0);
    return (await c.convertToBlob({ type: 'image/png' })).arrayBuffer();
  }
  // A tile is one of three things: imagery, legitimately none (404: outside the layer's coverage, drawn transparent as
  // before), or a download that failed (503). A failed tile is never drawn transparent -- that left black land in the
  // video. It is drawn from the best lower-resolution imagery there is: the same layer one zoom level coarser (and
  // so on), else a coarser layer. Only when nothing at all can be shown does the render stop (renderFrame).
  const tileStats = { failed: 0, invalid: 0, fromParent: 0, fromCoarserLayer: 0, missing: [], wxMissing: 0 };
  window.__tileStats = tileStats;
  // A downloaded tile that cannot be decoded is not imagery. Nor is an all-black tile from a layer with no "no data"
  // black (Blue Marble covers the whole globe; its darkest real tiles, deep ocean, never go below r+g+b of about 24, so
  // "every pixel under 12" leaves a wide margin). A layer whose black means "no data" (Landsat) keeps its black tiles:
  // they are legitimate and keyed out as before.
  async function validTile(blob, provider) {
    let bmp;
    try { bmp = await createImageBitmap(blob); } catch { return false; }
    if (provider?.blackIsNodata || isWx.has(provider?.id)) return true;   // satellite tiles are used as delivered (dark at night is real)
    const c = new OffscreenCanvas(32, 32), g = c.getContext('2d', { willReadFrequently: true });
    g.drawImage(bmp, 0, 0, 32, 32);
    const d = g.getImageData(0, 0, 32, 32).data;
    for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] >= 12) return true;
    return false;
  }
  const invalidTiles = new Set();   // tiles that stayed invalid after a fresh download: failed for the rest of the render
  async function getTile(id, z, x, y) {
    const key = `${id} ${z}/${x}/${y}`;
    if (invalidTiles.has(key)) return { failed: true };
    for (const refetch of [false, true]) {   // an invalid tile is downloaded once more, bypassing the cached copy
      const res = await fetch(`/tile/${id}/${z}/${x}/${y}${refetch ? '?refetch=1' : ''}`).catch(() => null);
      if (res && res.status === 204) return { none: true };   // outside the satellite picture
      if (!res || !res.ok) return res && res.status === 404 ? { none: true } : { failed: true };
      const blob = await res.blob();
      if (await validTile(blob, byId[id])) return { blob };
    }
    invalidTiles.add(key);
    tileStats.invalid++;
    return { failed: true };
  }
  // The part of an ancestor tile (k levels up) that covers tile x/y, enlarged to a full tile.
  async function cropAncestor(blob, k, x, y) {
    const bmp = await createImageBitmap(blob), n = 1 << k, s = bmp.width / n;
    const c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext('2d');
    g.imageSmoothingQuality = 'high';
    g.drawImage(bmp, (x % n) * s, (y % n) * s, s, s, 0, 0, bmp.width, bmp.height);
    return c.convertToBlob({ type: 'image/png' });
  }
  async function fallbackTile(p, z, x, y) {
    for (let k = 1; k <= z; k++) {   // same layer, coarser zoom
      const r = await getTile(p.id, z - k, x >> k, y >> k);
      if (r.blob) { tileStats.fromParent++; return { blob: await cropAncestor(r.blob, k, x, y), from: p }; }
      if (r.none) break;   // the layer has nothing here at all: try a coarser layer
    }
    for (let i = providers.findIndex((q) => q.id === p.id) - 1; i >= 0; i--) {   // providers run coarse -> fine
      const q = providers[i];
      for (let k = Math.max(0, z - q.maxNativeZoom); k <= z; k++) {
        const r = await getTile(q.id, z - k, x >> k, y >> k);
        if (r.blob) { tileStats.fromCoarserLayer++; return { blob: k ? await cropAncestor(r.blob, k, x, y) : r.blob, from: q }; }
        if (r.none) break;
      }
    }
    return null;
  }
  maplibregl.addProtocol('pkt', async (params) => {
    const m = params.url.match(/^pkt:\/\/([\w-]+)\/(\d+)\/(\d+)\/(\d+)/);
    if (!m) return { data: clearPng };
    const [id, z, x, y] = [m[1], Number(m[2]), Number(m[3]), Number(m[4])];
    let tile = await getTile(id, z, x, y), from = byId[id];
    if (tile.none) return { data: clearPng };
    if (tile.failed) {
      tileStats.failed++;
      tile = byId[id] ? await fallbackTile(byId[id], z, x, y) : null;
      if (!tile && isWx.has(id)) { tileStats.wxMissing++; return { data: clearPng }; }   // a satellite gap: the base map shows through
      if (!tile) { tileStats.missing.push(`${id} ${z}/${x}/${y}`); return { data: clearPng }; }
      from = tile.from;
    }
    return { data: from?.blackIsNodata ? await keyBlack(tile.blob) : await tile.blob.arrayBuffer() };
  });

  // ---- style: one raster layer per provider, graded the same way ----
  const g = imagery.grade || {};
  const sources = {}, layers = [{ id: 'space', type: 'background', paint: { 'background-color': offline ? '#3b5d3a' : '#03070d' } }];
  if (!offline) {
    for (const p of providers) {
      // tileSize / R: at pixel_scale 2 MapLibre fetches tiles one zoom level finer, so the imagery is sharper, not just enlarged
      sources[p.id] = { type: 'raster', tiles: [`pkt://${p.id}/{z}/{x}/{y}`], tileSize: p.tileSize / R, minzoom: 0, maxzoom: p.maxNativeZoom };
      layers.push({ id: `img-${p.id}`, type: 'raster', source: p.id, layout: { visibility: 'none' }, paint: {
        'raster-fade-duration': 0, 'raster-opacity': 1,
        'raster-saturation': g.saturation ?? 0, 'raster-contrast': g.contrast ?? 0,
        'raster-brightness-min': g.brightness_min ?? 0, 'raster-brightness-max': g.brightness_max ?? 1,
        'raster-hue-rotate': g.hue_rotate ?? 0 } });
    }
    // weather: timed satellite layers above the base imagery (and so under every fill, line and graphic)
    for (const s of wxSat) {
      const p = s.provider;
      sources[p.id] = { type: 'raster', tiles: [`pkt://${p.id}/{z}/{x}/{y}`], tileSize: p.tileSize / R, minzoom: 0, maxzoom: p.maxNativeZoom };
      layers.push({ id: `wxsat-${s.id}`, type: 'raster', source: p.id, layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-opacity': 0, 'raster-resampling': 'linear' } });
    }
    // weather: timed tile loops that sit under the region fills (satellite loops); radar (above_fills) is added after the fills
    for (const r of wxRasters.filter((x) => !x.above_fills)) {
      r.frames.forEach((f, k) => {
        const p = f.provider;
        if (!sources[p.id]) sources[p.id] = { type: 'raster', tiles: [`pkt://${p.id}/{z}/{x}/{y}`], tileSize: p.tileSize / R, minzoom: 0, maxzoom: p.maxNativeZoom };
        layers.push({ id: `wxr-${r.id}-${k}`, type: 'raster', source: p.id, layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-opacity': 0, 'raster-resampling': 'linear' } });
      });
    }
  }
  const map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8, sources, layers,
      // every value is set per frame from t; MapLibre's default 300 ms paint transition only delayed 'idle', never changed the frame
      transition: { duration: 0, delay: 0 },
      // globe when far out, ordinary flat map when close, blended in between
      projection: spec.flat_only ? { type: 'mercator' }
        : { type: ['interpolate', ['linear'], ['zoom'], 4, 'vertical-perspective', 6, 'mercator'] },
    },
    interactive: false, attributionControl: false, fadeDuration: 0, maxZoom: 14, maxPitch: 0,
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
  });
  await new Promise((resolve, reject) => { map.once('load', resolve); map.once('error', (e) => reject(e.error || e)); });

  // ---- vector overlays: country borders + translucent fills ----
  const fills = overlays.fills || [];
  if (overlays.borders || fills.length) {
    map.addSource('countries', { type: 'geojson', data: '/data/countries.geojson' });
    fills.forEach((f, i) => {
      map.addLayer({ id: `fill-${i}`, type: 'fill', source: 'countries', filter: ['in', ['get', 'iso'], ['literal', f.iso]],
        paint: { 'fill-color': tokens[f.color] || f.color || '#DF2721', 'fill-opacity': 0, 'fill-antialias': true } });
    });
    if (overlays.borders) {
      map.addLayer({ id: 'borders', type: 'line', source: 'countries', layout: { 'line-join': 'round' },
        paint: { 'line-color': '#ffffff', 'line-opacity': 0.92, 'line-width': ['interpolate', ['linear'], ['zoom'], 1, 0.7, 4, 1.6, 8, 2.6] } });
    }
  }

  // ---- fill events (translucent regions with an outline), timed like any other layer ----
  const hold = spec.hybrid && spec.hybrid.pause_overlays ? footageWindows(spec.events || []) : []; // Hybrid Map: map layers' clocks stop under footage
  const fillEvents = (spec.events || []).filter((e) => e.type === 'fill');
  fillEvents.forEach((e) => {
    const colour = e.color || FILL_ROLES[e.role || 'primary'];
    if (e.polys) {
      map.addSource(`fe-${e.id}`, { type: 'geojson', data: { type: 'Feature', geometry: { type: 'MultiPolygon', coordinates: e.polys } } });
    } else {
      if (!map.getSource('countries')) map.addSource('countries', { type: 'geojson', data: '/data/countries.geojson' });
      map.addSource(`fe-${e.id}`, { type: 'geojson', data: '/data/countries.geojson' });
    }
    const filter = e.polys ? undefined : ['in', ['get', 'iso'], ['literal', e.iso]];
    map.addLayer({ id: `fe-${e.id}`, type: 'fill', source: `fe-${e.id}`, ...(filter ? { filter } : {}), paint: { 'fill-color': colour, 'fill-opacity': 0, 'fill-antialias': true } }, map.getLayer('borders') ? 'borders' : undefined);
    if (e.outline !== false) map.addLayer({ id: `fe-line-${e.id}`, type: 'line', source: `fe-${e.id}`, ...(filter ? { filter } : {}), layout: { 'line-join': 'round' }, paint: { 'line-color': e.outline_color || '#ffffff', 'line-opacity': 0, 'line-width': ['interpolate', ['linear'], ['zoom'], 1, 1, 6, 2.5] } }, map.getLayer('borders') ? 'borders' : undefined);
  });

  // ---- value overlays (colour-ramp rasters from data, clipped to a region) ----
  const valueOverlays = (spec.events || []).filter((e) => e.type === 'value_overlay');
  for (const e of valueOverlays) {
    const g = e.grid, bin = atob(g.b64), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const values = g.type === 'i16' ? new Int16Array(bytes.buffer) : new Float32Array(bytes.buffer);
    const grid = new Grid({ west: g.west, south: g.south, east: g.east, north: g.north, cols: g.cols, rows: g.rows, values, nodata: g.nodata });
    const [w, s, ee, n] = e.bbox, size = imageSize(e.bbox, (e.max_px ?? 1800) * R), cv = document.createElement('canvas');
    cv.width = size.width; cv.height = size.height;
    const cx = cv.getContext('2d'), img = cx.createImageData(size.width, size.height);
    img.data.set(renderGridRGBA(grid, e.bbox, resolveRamp(e.ramp, e.min, e.max), size));
    cx.putImageData(img, 0, 0);
    if (e.clip_rings) {
      const y0 = mercY(n), y1 = mercY(s);
      cx.globalCompositeOperation = 'destination-in'; cx.fillStyle = '#000'; cx.beginPath();
      for (const poly of e.clip_rings) for (const ring of poly) ring.forEach(([lon, lat], i) => {
        const x = ((lon - w) / (ee - w)) * size.width, y = ((mercY(lat) - y0) / (y1 - y0)) * size.height;
        i ? cx.lineTo(x, y) : cx.moveTo(x, y);
      });
      cx.fill('evenodd');
    }
    map.addSource(`vo-${e.id}`, { type: 'image', url: cv.toDataURL('image/png'), coordinates: [[w, n], [ee, n], [ee, s], [w, s]] });
    map.addLayer({ id: `vo-${e.id}`, type: 'raster', source: `vo-${e.id}`, layout: { visibility: 'none' }, paint: { 'raster-opacity': 0, 'raster-fade-duration': 0, 'raster-resampling': 'linear' } }, map.getLayer('borders') ? 'borders' : undefined);
  }

  // ---- weather: timed tile loops that sit ABOVE the region fills (radar), under the borders ----
  if (!offline) {
    for (const r of wxRasters.filter((x) => x.above_fills)) {
      r.frames.forEach((f, k) => {
        const p = f.provider;
        if (!map.getSource(p.id)) map.addSource(p.id, { type: 'raster', tiles: [`pkt://${p.id}/{z}/{x}/{y}`], tileSize: p.tileSize / R, minzoom: 0, maxzoom: p.maxNativeZoom });
        map.addLayer({ id: `wxr-${r.id}-${k}`, type: 'raster', source: p.id, layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0, 'raster-opacity': 0, 'raster-resampling': 'linear' } }, map.getLayer('borders') ? 'borders' : undefined);
      });
    }
  }

  // ---- 2D compositing canvas: map -> ocean lift -> (debug HUD) -> JPEG ----
  const out = document.createElement('canvas');
  const OW = W * R, OH = H * R;   // the output frame in pixels
  out.width = OW; out.height = OH;
  const ctx = out.getContext('2d');
  const mapCanvas = map.getCanvas();
  const hudFont = `600 ${Math.round(OH * 0.022)}px monospace`;
  // The overlay works in output pixels (it scales its 1920x1080 design by height / 1080 itself); map points are in layout px.
  const wxOverlay = createWxOverlay({
    spec: R === 1 ? spec : { ...spec, width: OW, height: OH }, ctx, plugins: wxPlugins,
    project: (lon, lat) => { const p = map.project([lon, lat]); return p ? { x: p.x * R, y: p.y * R } : null; },
  });
  window.__wxStats = () => wxOverlay.stats();
  const overlay = createOverlay({
    spec: R === 1 ? spec : { ...spec, width: OW, height: OH }, ctx,
    project: (lon, lat) => { const p = map.project([lon, lat]); return p ? { x: p.x * R, y: p.y * R } : null; },
    unproject: (x, y) => map.unproject([x / R, y / R]),
    fetchMedia: async (id, frame) => createImageBitmap(await (await fetch(frame == null ? `/media/${id}` : `/media/${id}/${frame}`)).blob()),
  });

  function applyState(t, c) {
    let wipe = null;
    const mpp = metersPerPixel(c.lat, c.zoom);
    const sel = selectLayers(providers, mpp, c.lat, imagery);
    if (!offline) {
      for (const s of sel) {
        const id = `img-${s.id}`;
        map.setLayoutProperty(id, 'visibility', s.opacity > 0 ? 'visible' : 'none');
        if (s.opacity > 0) map.setPaintProperty(id, 'raster-opacity', s.opacity);
      }
    }
    for (const e of fillEvents) {
      const a = lifeAlpha(t, shiftedEvent(e, t, hold).t_in, e.t_out, e.fade_in ?? 0.4, 0.3);
      map.setPaintProperty(`fe-${e.id}`, 'fill-opacity', a * (e.opacity ?? 0.45));
      if (e.outline !== false) map.setPaintProperty(`fe-line-${e.id}`, 'line-opacity', a * 0.9);
    }
    for (const e of valueOverlays) {
      const a = lifeAlpha(t, shiftedEvent(e, t, hold).t_in, e.t_out, e.fade_in ?? 0.6, 0.4) * (e.opacity ?? 0.8);
      map.setLayoutProperty(`vo-${e.id}`, 'visibility', a > 0 ? 'visible' : 'none');
      if (a > 0) map.setPaintProperty(`vo-${e.id}`, 'raster-opacity', a);
    }
    fills.forEach((f, i) => {
      const k = easings.out(clamp01((t - (f.t ?? 0)) / Math.max(0.01, f.dur ?? 0.3)));
      map.setPaintProperty(`fill-${i}`, 'fill-opacity', (f.opacity ?? 0.5) * k);
    });
    if (!offline) {
      for (const s of wxSat) {
        const a = lifeAlpha(t, shiftedEvent(s, t, hold).t_in, s.t_out, s.fade_in ?? 0.8, 0.6) * (s.opacity ?? 1);
        map.setLayoutProperty(`wxsat-${s.id}`, 'visibility', a > 0 ? 'visible' : 'none');
        if (a > 0) map.setPaintProperty(`wxsat-${s.id}`, 'raster-opacity', a);
      }
      for (const r of wxRasters) {
        const sr = shiftedEvent(r, t, hold);
        const a = lifeAlpha(t, sr.t_in, r.t_out, r.fade_in ?? 0.5, 0.5) * (r.opacity ?? 0.85);
        const { index, mix } = frameAt(sr, t);
        // a wipe (before/after) draws this frame whole now; renderFrame then draws the next one behind the moving edge
        const wiping = r.wipe && a > 0 && mix > 0 && mix < 1;
        if (wiping) wipe = { r, index, a, mix };
        r.frames.forEach((_f, k) => {
          const op = a <= 0 ? 0 : wiping ? (k === index ? a : 0) : k === index ? a * (1 - mix) : k === index + 1 ? a * mix : 0;
          map.setLayoutProperty(`wxr-${r.id}-${k}`, 'visibility', op > 0 ? 'visible' : 'none');
          if (op > 0) map.setPaintProperty(`wxr-${r.id}-${k}`, 'raster-opacity', op);
        });
      }
    }
    return { sel, mpp, wipe };
  }

  // The frame is captured when the map is idle (every tile drawn). The 45 s check no longer captures whatever is on
  // screen: a slow tile (retries, then fallbacks) can take longer than that, and capturing then left an empty area.
  // Past 45 s the frame waits on while tiles are still loading, and the render stops with a clear error after
  // map_ready_timeout_s (default 10 min) rather than capture a half-drawn map.
  const READY_LIMIT_MS = (spec.map_ready_timeout_s ?? 600) * 1000;
  const waitDrawn = () => new Promise((resolve, reject) => {
    const started = performance.now();
    let timer;
    const onIdle = () => { clearTimeout(timer); resolve(); };
    const check = () => {
      if (map.areTilesLoaded()) { map.off('idle', onIdle); resolve(); return; }   // drawable: every tile is in
      if (performance.now() - started >= READY_LIMIT_MS) {
        map.off('idle', onIdle);
        reject(new Error(`the map imagery for this frame was still loading after ${Math.round(READY_LIMIT_MS / 1000)} s, so the render stopped rather than capture a half-drawn map. Check the internet connection and render again.`));
        return;
      }
      timer = setTimeout(check, Math.min(45000, Math.max(1000, READY_LIMIT_MS - (performance.now() - started))));
    };
    timer = setTimeout(check, Math.min(45000, READY_LIMIT_MS));
    map.once('idle', onIdle);
    map.triggerRepaint();
  });

  window.renderFrame = async (t) => {
    const c = camera.at(t);
    map.jumpTo({ center: [((c.lon + 540) % 360) - 180, c.lat], zoom: c.zoom, pitch: 0, bearing: 0 });
    const { sel, wipe } = applyState(t, c);
    await waitDrawn();
    if (tileStats.missing.length) {
      throw new Error(`map imagery could not be downloaded for ${tileStats.missing.length} tile(s) (e.g. ${tileStats.missing[0]}) and no lower-resolution imagery was available to stand in, so the render stopped rather than draw black land. Check the internet connection and render again.`);
    }
    ctx.globalCompositeOperation = 'source-over';
    // The globe leaves the sky around it transparent, and this canvas keeps the previous frame. Clear it first, or a zoom-out
    // (smaller globe each frame) shows the earlier, larger globes through the gap as rippled bands.
    ctx.fillStyle = '#03070d';
    ctx.fillRect(0, 0, OW, OH);
    ctx.drawImage(mapCanvas, 0, 0, OW, OH);
    if (imagery.ocean_lift && !offline) {
      ctx.globalCompositeOperation = 'lighten';
      ctx.fillStyle = imagery.ocean_lift;
      ctx.fillRect(0, 0, OW, OH);
      ctx.globalCompositeOperation = 'source-over';
    }
    if (wipe) {
      // before/after wipe: the next picture, drawn again behind an edge moving left to right, with a white divider on the edge
      const { r, index, a, mix } = wipe, x = OW * easings.inOut(mix);
      map.setLayoutProperty(`wxr-${r.id}-${index}`, 'visibility', 'none');
      map.setLayoutProperty(`wxr-${r.id}-${index + 1}`, 'visibility', 'visible');
      map.setPaintProperty(`wxr-${r.id}-${index + 1}`, 'raster-opacity', a);
      await waitDrawn();
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, x, OH); ctx.clip();
      ctx.drawImage(mapCanvas, 0, 0, OW, OH);
      if (imagery.ocean_lift && !offline) { ctx.globalCompositeOperation = 'lighten'; ctx.fillStyle = imagery.ocean_lift; ctx.fillRect(0, 0, OW, OH); }
      ctx.restore();
      ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 12 * OW / 1920; ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(x - 2 * OW / 1920, 0, 4 * OW / 1920, OH); ctx.restore();
    }
    await overlay.prepare(t);
    overlay.draw(t);
    wxOverlay.draw(t);
    if (spec.debug_hud) {
      ctx.font = hudFont; ctx.textBaseline = 'top';
      const lines = [`t ${t.toFixed(2)}s  zoom ${c.zoom.toFixed(2)}  frame ${frameWidthKm(c.lat, c.zoom, W).toFixed(0)} km`,
        sel.map((s) => `${s.id.replace('nasa_', '')} ${(s.opacity * 100).toFixed(0)}%`).join('  ')];
      lines.forEach((ln, i) => { ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(10, 10 + i * OH * 0.03, ctx.measureText(ln).width + 12, OH * 0.03); ctx.fillStyle = '#fff'; ctx.fillText(ln, 16, 12 + i * OH * 0.03); });
    }
    return out.toDataURL('image/jpeg', 0.92).slice('data:image/jpeg;base64,'.length);
  };
  window.__ready = true;
}

setup().catch((err) => { window.__error = String((err && err.message) || err); });
