// Runs inside the hidden browser. Builds the map from /spec.json and exposes
// window.renderFrame(t) — sets everything for time t (seconds) and resolves
// once the map has fully drawn that frame.
import * as maplibregl from '/maplibre/maplibre-gl.mjs';

const COLORS = { parent: '#2f8fe3', focus: '#ff1a1a', inner: '#ffcf1f' };
const FILL_OPACITY = { parent: 0.78, focus: 0.96, inner: 0.97 };
const APPEAR = { parent: [0.0, 0.35], focus: [0.3, 0.42], inner: [0.9, 1.05] };
const LABEL_AT = 0.5;
const LABEL_POP = 0.35;

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const easeOutBack = (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
const lerp = (a, b, t) => a + (b - a) * t;

function expandBounds([minx, miny, maxx, maxy], k) {
  const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2;
  const hw = Math.max((maxx - minx) / 2, 0.05) * k, hh = Math.max((maxy - miny) / 2, 0.05) * k;
  return [Math.max(-179, cx - hw), Math.max(-80, cy - hh), Math.min(179, cx + hw), Math.min(80, cy + hh)];
}

async function setup() {
  const scene = await (await fetch('/spec.json')).json();
  const W = scene.width, H = scene.height;
  const dark = scene.style !== 'natural';
  await document.fonts.load("800 64px 'MapLabel'");

  const map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      // imagery === false: no satellite tiles (offline tests only).
      sources: scene.imagery === false ? {} : { sat: { type: 'raster', tiles: [`${location.origin}/tiles/{z}/{y}/{x}.jpg`], tileSize: 256, maxzoom: 8 } },
      layers: [
        { id: 'bg', type: 'background', paint: { 'background-color': scene.imagery === false ? '#3b5d3a' : '#08131f' } },
        ...(scene.imagery === false ? [] : [{ id: 'sat', type: 'raster', source: 'sat', paint: {
          'raster-fade-duration': 0,
          'raster-saturation': dark ? 0.22 : 0,
          'raster-brightness-min': dark ? 0.1 : 0,
          'raster-brightness-max': 1,
          'raster-contrast': dark ? -0.12 : 0,
        } }]),
      ],
    },
    interactive: false, attributionControl: false, fadeDuration: 0, maxZoom: 11, maxPitch: 60,
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    preserveDrawingBuffer: true,
  });
  await new Promise((resolve, reject) => { map.once('load', resolve); map.once('error', (e) => reject(e.error || e)); });

  if (scene.sea) {
    map.addSource('sea', { type: 'geojson', data: { type: 'Feature', geometry: scene.sea } });
    map.addLayer({ id: 'sea', type: 'fill', source: 'sea', paint: { 'fill-color': '#0d2536', 'fill-antialias': true } });
  }
  const areas = scene.areas || [];
  for (const area of areas) {
    const role = area.role;
    if (area.point) {
      map.addSource(`${role}-pt`, { type: 'geojson', data: { type: 'Feature', geometry: { type: 'Point', coordinates: area.point } } });
      map.addLayer({ id: `${role}-ring-glow`, type: 'circle', source: `${role}-pt`, paint: {
        'circle-color': 'rgba(0,0,0,0)', 'circle-radius': 10, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 10,
        'circle-stroke-opacity': 0, 'circle-blur': 0.6 } });
      map.addLayer({ id: `${role}-disc`, type: 'circle', source: `${role}-pt`, paint: {
        'circle-color': COLORS[role], 'circle-opacity': 0, 'circle-radius': 10,
        'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3, 'circle-stroke-opacity': 0 } });
      continue;
    }
    map.addSource(`${role}-fill`, { type: 'geojson', data: { type: 'Feature', geometry: area.fill } });
    map.addSource(`${role}-line`, { type: 'geojson', data: { type: 'Feature', geometry: { type: 'MultiLineString', coordinates: area.outline } } });
    map.addLayer({ id: `${role}-fill`, type: 'fill', source: `${role}-fill`, paint: { 'fill-color': COLORS[role], 'fill-opacity': 0, 'fill-antialias': true } });
    map.addLayer({ id: `${role}-glow`, type: 'line', source: `${role}-line`, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 22, 'line-blur': 16, 'line-opacity': 0 } });
    map.addLayer({ id: `${role}-edge`, type: 'line', source: `${role}-line`, layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 3.2, 'line-opacity': 0 } });
  }

  const byRole = Object.fromEntries(areas.map((a) => [a.role, a]));
  const focus = byRole.focus;
  const wide = byRole.parent ? byRole.parent.bbox : expandBounds(focus.bbox, 4);
  const pad = (fx, fy) => ({ top: H * fy, bottom: H * fy * 0.8, left: W * fx, right: W * fx });
  const camFor = (bbox, padding) => {
    const c = map.cameraForBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding });
    return { center: [c.center.lng, c.center.lat], zoom: Math.min(c.zoom, 10.5) };
  };
  const wideCam = { ...camFor(wide, pad(0.08, 0.1)), pitch: 0, bearing: 0 };
  const closeCam = { ...camFor(focus.bbox, pad(0.2, 0.2)), pitch: 38, bearing: -14 };
  const D = scene.duration;
  const push = Math.min(D * 0.55, 4.5);

  const mix = (a, b, t) => ({
    center: [lerp(a.center[0], b.center[0], t), lerp(a.center[1], b.center[1], t)],
    zoom: lerp(a.zoom, b.zoom, t), pitch: lerp(a.pitch, b.pitch, t), bearing: lerp(a.bearing, b.bearing, t),
  });
  const drift = (cam, u) => ({ ...cam, zoom: cam.zoom + 0.22 * u, bearing: cam.bearing - 4 * u });
  function cameraAt(t) {
    if (scene.camera === 'drift') return drift(closeCam, t / D);
    if (scene.camera === 'zoom_out') {
      if (t < push) return mix(drift(closeCam, 0), wideCam, ease(t / push));
      return { ...wideCam, zoom: wideCam.zoom - 0.12 * easeOut((t - push) / Math.max(0.01, D - push)) };
    }
    if (t < push) return mix(wideCam, closeCam, ease(t / push));
    return drift(closeCam, easeOut((t - push) / Math.max(0.01, D - push)));
  }

  // Every frame is composited on this 2D canvas (map + tint + pointer +
  // label + credit) and read out as a JPEG — far faster than a page
  // screenshot, and independent of how the browser composites the page.
  const out = document.createElement('canvas');
  out.width = W; out.height = H;
  const ctx = out.getContext('2d');
  const mapCanvas = map.getCanvas();
  const target = byRole[(scene.label && scene.label.target) || 'focus'] || focus;
  const labelText = (scene.label && scene.label.text) || '';
  const labelFont = `800 ${Math.round(H * 0.058)}px 'MapLabel'`;
  const creditFont = `800 ${Math.round(H * 0.012)}px 'MapLabel'`;
  const lineWidth = Math.max(2, Math.round(H * 0.0028));
  ctx.font = labelFont;
  const labelW = labelText ? ctx.measureText(labelText).width : 0;
  const labelH = Math.round(H * 0.058) * 1.1;

  // Where the label sits relative to its area, picked once (when it first
  // appears) so it never jumps: the nearest spot where the label box doesn't
  // cover the area itself, preferring the sea/open side like the reference.
  let chosenOffset = null;
  const areaLayers = areas.filter((x) => !x.point).map((x) => `${x.role}-fill`).filter((id) => map.getLayer(id));
  function chooseOffset(a, w, h) {
    const cands = [];
    for (const dist of [0.2, 0.28, 0.36]) {
      for (const [dx, dy] of [[0, 1], [-0.7, 0.7], [0.7, 0.7], [0, -1], [-0.7, -0.7], [0.7, -0.7], [-1, 0], [1, 0]]) {
        cands.push([dx * H * dist * 1.6, dy * H * dist]);
      }
    }
    const targetLayer = `${target.role}-fill`;
    let best = null, bestScore = Infinity;
    for (const [ox, oy] of cands) {
      const cx = a.x + ox, cy = a.y + oy;
      const box = [[cx - w / 2 - 12, cy - h / 2 - 8], [cx + w / 2 + 12, cy + h / 2 + 8]];
      if (box[0][0] < W * 0.03 || box[1][0] > W * 0.97 || box[0][1] < H * 0.06 || box[1][1] > H * 0.8) continue;  // bottom 20%: fact tags + subtitles
      const hitsTarget = map.getLayer(targetLayer) ? map.queryRenderedFeatures(box, { layers: [targetLayer] }).length : 0;
      const hitsAny = areaLayers.length ? map.queryRenderedFeatures(box, { layers: areaLayers }).length : 0;
      const score = hitsTarget * 100 + hitsAny * 10 + Math.hypot(ox, oy) / H;
      if (score < bestScore) { best = [ox, oy]; bestScore = score; }
    }
    return best || [0, -H * 0.2];
  }

  function labelLayout(t) {
    if (!labelText || t < LABEL_AT) return null;
    const a = map.project(target.anchor);
    const east = map.project([target.anchor[0] + 0.05, target.anchor[1]]);
    const angle = Math.atan2(east.y - a.y, east.x - a.x);
    const w = labelW, h = labelH;
    if (!chosenOffset) chosenOffset = chooseOffset(a, w, h);
    let lx = a.x + chosenOffset[0], ly = a.y + chosenOffset[1];
    lx = Math.max(w / 2 + W * 0.04, Math.min(W - w / 2 - W * 0.04, lx));
    ly = Math.max(H * 0.1, Math.min(H * 0.9, ly));
    const pop = clamp01((t - LABEL_AT) / LABEL_POP);
    const grow = clamp01((t - LABEL_AT - LABEL_POP) / Math.max(0.01, D - LABEL_AT - LABEL_POP));
    const scale = (pop < 1 ? 0.5 + 0.5 * easeOutBack(pop) : 1) * (1 + 0.08 * grow);
    const ey = ly < a.y ? ly + h * 0.5 * scale : ly - h * 0.5 * scale;
    const reach = easeOut(clamp01((t - LABEL_AT - 0.1) / 0.3));
    return { a, lx, ly, ey, angle, scale, alpha: clamp01(pop * 2), reach };
  }

  function glowStroke(draw, color, blurs) {
    for (const [blur, alpha] of blurs) {
      ctx.save(); ctx.shadowColor = color; ctx.shadowBlur = blur; ctx.globalAlpha *= alpha; draw(); ctx.restore();
    }
  }

  function composite(t) {
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
    ctx.drawImage(mapCanvas, 0, 0, W, H);
    // Lift the satellite's near-black sea to dark navy; brighter pixels untouched.
    ctx.globalCompositeOperation = 'lighten';
    ctx.fillStyle = '#0b2233';
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'source-over';
    const L = labelLayout(t);
    if (L) {
      if (L.reach > 0) {
        const x2 = lerp(L.lx, L.a.x, L.reach), y2 = lerp(L.ey, L.a.y, L.reach);
        ctx.strokeStyle = '#fff'; ctx.lineWidth = lineWidth; ctx.lineCap = 'round';
        glowStroke(() => { ctx.beginPath(); ctx.moveTo(L.lx, L.ey); ctx.lineTo(x2, y2); ctx.stroke(); },
          'rgba(255,255,255,0.9)', [[10, 0.6], [4, 1]]);
      }
      ctx.save();
      ctx.globalAlpha = L.alpha;
      ctx.translate(L.lx, L.ly); ctx.rotate(L.angle); ctx.scale(L.scale, L.scale);
      ctx.font = labelFont; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#fff';
      ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 3; ctx.fillText(labelText, 0, 0); ctx.restore();
      glowStroke(() => ctx.fillText(labelText, 0, 0), 'rgba(255,255,255,0.9)', [[18, 0.55], [6, 0.9]]);
      ctx.fillText(labelText, 0, 0);
      ctx.restore();
    }
    if (scene.credit) {
      ctx.font = creditFont; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.fillText(scene.credit, W * 0.016, H * 0.984);
    }
  }

  function metersPerPixel(lat, zoom) { return 156543.03 * Math.cos(lat * Math.PI / 180) / Math.pow(2, zoom); }

  function styleAt(t, zoom) {
    for (const area of areas) {
      const [a0, a1] = APPEAR[area.role] || [0, 0.4];
      const k = easeOut(clamp01((t - a0) / (a1 - a0)));
      const role = area.role;
      if (area.point) {
        const r = Math.max(10, (area.radius_km * 1000) / metersPerPixel(area.point[1], zoom));
        map.setPaintProperty(`${role}-disc`, 'circle-radius', r * (0.6 + 0.4 * k));
        map.setPaintProperty(`${role}-disc`, 'circle-opacity', 0.9 * k);
        map.setPaintProperty(`${role}-disc`, 'circle-stroke-opacity', k);
        map.setPaintProperty(`${role}-ring-glow`, 'circle-radius', r * (0.6 + 0.4 * k));
        map.setPaintProperty(`${role}-ring-glow`, 'circle-stroke-opacity', 0.55 * k);
        continue;
      }
      map.setPaintProperty(`${role}-fill`, 'fill-opacity', FILL_OPACITY[role] * k);
      map.setPaintProperty(`${role}-glow`, 'line-opacity', 0.75 * k);
      map.setPaintProperty(`${role}-edge`, 'line-opacity', k);
    }
  }

  const waitDrawn = () => new Promise((resolve) => {
    const timer = setTimeout(resolve, 30000);
    map.once('idle', () => { clearTimeout(timer); resolve(); });
    map.triggerRepaint();
  });

  window.renderFrame = async (t) => {
    const cam = cameraAt(t);
    map.jumpTo(cam);
    styleAt(t, cam.zoom);
    await waitDrawn();
    composite(t);
    return out.toDataURL('image/jpeg', 0.92).slice('data:image/jpeg;base64,'.length);
  };
  window.__mapReady = true;
}

setup().catch((err) => { window.__mapError = String((err && err.message) || err); });
