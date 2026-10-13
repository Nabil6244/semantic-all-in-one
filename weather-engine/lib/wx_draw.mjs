// The weather graphics on top of the map: temperature markers, the forecast strip, the "now" card, the alert legend and
// the source line. Drawn after pakMap's own overlay, in 1920x1080 reference units (scaled to the frame). The strings are
// formatted by weather/events.py; nothing here invents a number.
//
// Like pakMap's map layers they pause under Hybrid footage (shiftedEvent) and are hidden while full-screen footage is up.
import { COLORS, FONT, TIMING } from '../../pakmap-engine/lib/style.mjs';
import { clamp01, easeOut, lifeAlpha } from '../../pakmap-engine/lib/anim.mjs';
import { activeAt } from '../../pakmap-engine/lib/events.mjs';
import { FRAME } from '../../pakmap-engine/lib/layout.mjs';
import { footageWindows, shiftedEvent, footageAlpha } from '../../pakmap-engine/lib/hybrid.mjs';
import { drawIcon } from './wx_icons.mjs';
import { WX, stripLayout, nowLayout, tempChipLayout, chooseSide, chipCovers, legendLayout, sourceLayout } from './wx_layout.mjs';
import { frameAt } from './wx_raster.mjs';

export const WX_TYPES = ['temp_marker', 'forecast_strip', 'now_card', 'alert_legend', 'source_line'];
const PANEL = 'rgba(8,19,32,0.90)';
const MUTED = '#9FB3C8';
const POP = '#5AB0FF';
const font = (px, weight = FONT.weight) => `${weight} ${px}px ${FONT.family}, Montserrat, sans-serif`;
const easeOutBack = (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };

/** A temperature like "92°" counts up to its value as it appears (from 12 degrees under it, easing out over `dur` s);
 *  anything that is not a plain temperature is shown as it is. The final frames always show the exact value. */
export function countUp(str, t, t0, dur = 0.6) {
  const m = /^(-?\d+)\u00b0$/.exec(String(str));
  if (!m) return str;
  const v = Number(m[1]), k = easeOut(clamp01((t - t0) / dur));
  return `${Math.round(v - 12 * (1 - k))}\u00b0`;
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y); ctx.arcTo(x + w, y, x + w, y + h, rr); ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr); ctx.arcTo(x, y, x + w, y, rr); ctx.closePath();
}

/** How much full-screen footage covers the frame at t (0..1): weather graphics fade out under it. */
export function footageCover(events, t) {
  let cover = 0;
  for (const e of events) {
    if (e.type !== 'media_full' || t < e.t_in || t >= e.t_out) continue;
    const a = e.xfade_prev || events.some((o) => o.xfade_prev) ? footageAlpha(e, t, events, TIMING.dissolve)
      : Math.min(clamp01((t - e.t_in) / (e.dissolve_s ?? TIMING.dissolve)), clamp01((e.t_out - t) / (e.dissolve_s ?? TIMING.dissolve)));
    cover = Math.max(cover, a);
  }
  return cover;
}

export function createWxOverlay({ spec, ctx, project, plugins = [] }) {
  const W = spec.width, H = spec.height, S = H / FRAME.h;
  const wx = (spec.weather && spec.weather.events) || [];
  const all = spec.events || [];
  const hold = spec.hybrid && spec.hybrid.pause_overlays ? footageWindows(all) : [];
  const measure = (text, px, weight) => { ctx.save(); ctx.font = font(px, weight); const w = ctx.measureText(text).width; ctx.restore(); return w; };
  function text(str, x, y, px, color, align = 'left', weight = FONT.weight, spacing = 0.3) {
    ctx.font = font(px, weight); ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'alphabetic';
    ctx.letterSpacing = `${spacing}px`; ctx.fillText(str, x, y); ctx.letterSpacing = '0px';
  }
  function panel(x, y, w, h, r, fill = PANEL) {
    // where the panel lands on screen (through any slide / pop transform), in 1080p units: place labels keep clear of it
    const m = ctx.getTransform(), pts = [[x, y], [x + w, y + h]].map(([px, py]) => [(m.a * px + m.c * py + m.e) / S, (m.b * px + m.d * py + m.f) / S]);
    panelRects.push({ x: Math.min(pts[0][0], pts[1][0]), y: Math.min(pts[0][1], pts[1][1]), w: Math.abs(pts[1][0] - pts[0][0]), h: Math.abs(pts[1][1] - pts[0][1]) });
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 16; ctx.shadowOffsetY = 4; ctx.fillStyle = fill;
    roundRect(ctx, x, y, w, h, r); ctx.fill(); ctx.restore();
  }
  function titleChip(x, y, h, px, label) {
    const w = measure(label, px) + 32;
    panel(x, y, w, h, 10, COLORS.yellow);
    text(label, x + 16, y + h / 2 + px * 0.36, px, COLORS.text_dark, 'left', 800, 0.6);
    return w;
  }

  let vis = 1; // 1 - how much full-screen footage covers the frame
  const sides = new Map();
  let placed = []; // chips drawn so far in this frame (a new marker's chip avoids them)
  let panelRects = []; // every panel drawn so far in this frame (place labels avoid them)
  const markerSeen = {}; // id -> {city, on, off}: frames the marker's city was inside / outside the frame
  function drawTempMarker(e, t) {
    const q = project(e.lon, e.lat);
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.markerPop, TIMING.chipOut); if (a <= 0) return;
    const st = (markerSeen[e.id] ||= { city: e.city, on: 0, off: 0 });
    if (!q || q.x < 0 || q.y < 0 || q.x > W || q.y > H) { st.off++; return; }
    st.on++;
    const x = q.x / S, y = q.y / S, m = WX.marker;
    const tempW = measure(e.temp, m.tempPx), labelW = Math.max(measure(e.city, m.cityPx), measure(e.tag, m.tagPx, 700));
    const width = m.padX + m.icon + m.gap + tempW + m.gap + labelW + m.padX;
    let side = sides.get(e.id);
    // a chip keeps its side for the shot; it moves only when the camera brings another chip onto it (cities converge as the
    // camera pulls back), and then to a side that is free
    if (!side || (e.side === 'auto' || !e.side) && chipCovers(x, y, width, side, placed)) { side = chooseSide(x, y, width, e.side, placed); sides.set(e.id, side); }
    const L = tempChipLayout({ x, y, side, width });
    placed.push(L);
    const pop = easeOutBack(clamp01((t - e.t_in) / TIMING.markerPop)), slide = (1 - easeOut(clamp01((t - e.t_in) / TIMING.chipIn))) * 8;
    ctx.save(); ctx.globalAlpha = a * vis;
    ctx.save(); ctx.translate(x, y); ctx.scale(pop, pop);
    ctx.fillStyle = COLORS.panel; ctx.strokeStyle = COLORS.white; ctx.lineWidth = 3.5;
    ctx.beginPath(); ctx.arc(0, 0, m.dot, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.restore();
    const y0 = L.y + slide;
    panel(L.x, y0, L.w, L.h, L.r);
    drawIcon(ctx, e.icon, L.x + m.padX + m.icon / 2, y0 + L.h / 2, m.icon);
    const tx = L.x + m.padX + m.icon + m.gap;
    text(countUp(e.temp, t, e.t_in + 0.1), tx, y0 + L.h / 2 + m.tempPx * 0.36, m.tempPx, COLORS.white, 'left', 800, -0.5);
    const lx = tx + tempW + m.gap;
    text(e.city, lx, y0 + L.h / 2 - 3, m.cityPx, COLORS.white, 'left', 800, 0.6);
    text(e.tag, lx, y0 + L.h / 2 + m.tagPx + 2, m.tagPx, COLORS.yellow, 'left', 700, 0.8);
    ctx.restore();
  }

  function drawStrip(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.chipIn, TIMING.chipOut); if (a <= 0) return;
    const L = stripLayout(e.days.length), s = WX.strip;
    const slide = (1 - easeOut(clamp01((t - e.t_in) / 0.35))) * 24;
    ctx.save(); ctx.globalAlpha = a * vis; ctx.translate(0, slide);
    panel(L.x, L.y, L.w, L.h, L.r);
    titleChip(L.title.x, L.title.y, L.title.h, L.title.px, e.title);
    e.days.forEach((d, i) => {
      const c = L.cells[i], k = clamp01((t - e.t_in - 0.15 - i * 0.07) / 0.25);
      if (k <= 0) return;
      ctx.save(); ctx.globalAlpha = a * vis * easeOut(k);
      if (i > 0) { ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(c.x, L.y + 22); ctx.lineTo(c.x, L.y + L.h - 22); ctx.stroke(); }
      text(d.dow, c.cx, L.y + 46, s.dowPx, COLORS.white, 'center', 800, 1.2);
      drawIcon(ctx, d.icon, c.cx, L.y + 100, s.icon);
      text(d.hi, c.cx - (d.lo ? 6 : 0), L.y + 182, s.hiPx, COLORS.white, 'right', 800, -0.5);
      if (d.lo) text(d.lo, c.cx + 6, L.y + 182, s.loPx, MUTED, 'left', 700, -0.3);
      if (d.pop) text(d.pop, c.cx, L.y + 216, s.popPx, POP, 'center', 800, 0.4);
      ctx.restore();
    });
    ctx.restore();
  }

  function drawNow(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.chipIn, TIMING.chipOut); if (a <= 0) return;
    const L = nowLayout(e.anchor), n = WX.now;
    const slide = (1 - easeOut(clamp01((t - e.t_in) / 0.3))) * 18;
    ctx.save(); ctx.globalAlpha = a * vis; ctx.translate(0, -slide);
    panel(L.x, L.y, L.w, L.h, L.r);
    titleChip(L.title.x, L.title.y, L.title.h, L.title.px, e.title);
    drawIcon(ctx, e.icon, L.x + 30 + n.icon / 2, L.y + 92, n.icon);
    text(countUp(e.temp, t, e.t_in + 0.15), L.x + L.w - 28, L.y + 128, n.tempPx, COLORS.white, 'right', 800, -1);
    text(e.text, L.x + 28, L.y + 180, n.textPx, COLORS.white, 'left', 700, 0.3);
    text(e.foot, L.x + 28, L.y + 210, n.footPx, MUTED, 'left', 600, 0.4);
    ctx.restore();
  }

  function drawLegend(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.chipIn, TIMING.chipOut); if (a <= 0) return;
    const g = WX.legend, widest = Math.max(...e.items.map((it) => measure(it.label, g.px, 800)));
    const L = legendLayout(e.items.length, widest);
    ctx.save(); ctx.globalAlpha = a * vis;
    panel(L.x, L.y, L.w, L.h, L.r);
    e.items.forEach((it, i) => {
      const y = L.y + g.padY + i * (g.rowH + g.gap);
      ctx.fillStyle = it.color; roundRect(ctx, L.x + g.padX, y + (g.rowH - g.swatch) / 2, g.swatch, g.swatch, 5); ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.lineWidth = 1.5; ctx.stroke();
      text(it.label, L.x + 2 * g.padX + g.swatch, y + g.rowH / 2 + g.px * 0.36, g.px, COLORS.white, 'left', 800, 0.6);
    });
    ctx.restore();
  }

  function drawSource(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, 0.3, TIMING.chipOut); if (a <= 0) return;
    const s = WX.source, L = sourceLayout(measure(e.text, s.px, 600));
    ctx.save(); ctx.globalAlpha = a * vis;
    ctx.fillStyle = 'rgba(8,19,32,0.72)'; roundRect(ctx, L.x, L.y, L.w, L.h, L.r); ctx.fill();
    text(e.text, L.x + s.padX, L.baseline, s.px, 'rgba(255,255,255,0.92)', 'left', 600, 0.3);
    ctx.restore();
  }

  // the clock chip of a timed tile loop ("RADAR · 4:35 PM CDT"), bottom left above the source line
  const rasters = (spec.weather && spec.weather.rasters) || [];
  function drawRasterClocks(t) {
    let row = 0;
    for (const r0 of rasters) {
      if (!r0.clock || t < r0.t_in || t >= r0.t_out) continue;
      const r = shiftedEvent(r0, t, hold);
      const f = r.frames[Math.max(0, frameAt(r, t).index)];
      if (!f || !f.label) continue;
      const a = lifeAlpha(t, r.t_in, r.t_out, 0.3, TIMING.chipOut); if (a <= 0) continue;
      const px = 22, w = measure(f.label, px) + 28, h = 40, x = WX.source.left;
      let y = FRAME.h - WX.source.baselineFromBottom - WX.source.h - 14 - h - row * (h + 8);
      // a panel already there (the lower-third headline): the clock sits just above it
      for (const r of [...placed].sort((p, q) => q.y - p.y)) if (x < r.x + r.w && x + w > r.x && y < r.y + r.h && y + h > r.y) y = r.y - h - 8;
      ctx.save(); ctx.globalAlpha = a * vis;
      panel(x, y, w, h, 9);
      text(f.label, x + 14, y + h / 2 + px * 0.36, px, COLORS.white, 'left', 800, 0.5);
      ctx.restore();
      row++;
    }
  }

  const DRAW = { alert_legend: drawLegend, temp_marker: drawTempMarker, now_card: drawNow, forecast_strip: drawStrip, source_line: drawSource };
  // plugins (lib/layers/*.mjs): each draws its own event type with the same helpers, in 1080p reference units
  const helpers = { ctx, project, measure, text, panel, titleChip, roundRect, font, drawIcon, S, W, H, FRAME, WX, COLORS, TIMING,
    clamp01, easeOut, lifeAlpha, vis: () => vis, placed: () => placed, panels: () => panelRects };
  const pluginList = [...plugins].sort((a, b) => (a.order ?? 50) - (b.order ?? 50));
  for (const p of pluginList) DRAW[p.type] = (e, t) => p.draw(e, t, helpers);
  // plugins with overFootage (the footage credit chip) are drawn last, on the footage itself, at full strength
  const onMap = pluginList.filter((p) => !p.overFootage), onFootage = pluginList.filter((p) => p.overFootage);
  const footageHelpers = { ...helpers, footage: true, vis: () => 1 };
  return {
    /** Temperature markers: frames their city was on / off screen (render.mjs reports the ones mostly off screen). */
    stats: () => markerSeen,
    /** Draw the weather graphics active at t (the map and pakMap's overlay are already on ctx). */
    draw(t) {
      if (!wx.length && !rasters.some((r) => r.clock)) return;
      const hide = footageCover(all, t);
      if (hide < 1) drawMap(t, hide);
      if (onFootage.length) {
        ctx.save(); ctx.scale(S, S);
        for (const p of onFootage) for (const e of activeAt(wx, t)) if (e.type === p.type) p.draw(e, t, footageHelpers);
        ctx.restore();
      }
    },
  };

  function drawMap(t, hide) {
      const live = activeAt(wx, t).map((e) => shiftedEvent(e, t, hold));
      vis = 1 - hide;
      // the panels on screen now are taken: a temperature chip picks a side that does not hide under them
      placed = []; panelRects = [];
      for (const e of live) {
        if (e.type === 'forecast_strip') { const L = stripLayout(e.days.length); placed.push(L, { x: L.title.x, y: L.title.y, w: 260, h: L.title.h }); }
        if (e.type === 'now_card') { const L = nowLayout(e.anchor); placed.push(L, { x: L.title.x, y: L.title.y, w: 260, h: L.title.h }); }
      }
      ctx.save(); ctx.scale(S, S);
      for (const type of ['alert_legend', ...onMap.filter((p) => (p.order ?? 50) < 50).map((p) => p.type), 'temp_marker', 'now_card', 'forecast_strip',
        ...onMap.filter((p) => (p.order ?? 50) >= 50).map((p) => p.type), 'source_line']) for (const e of live) if (e.type === type) DRAW[type](e, t);
      drawRasterClocks(t);
      ctx.restore();
  }
}

/** Problems with weather events (checked before a render starts), each naming the event. */
export function validateWxEvents(events, duration, plugins = []) {
  const errors = [], ids = new Set();
  const byType = Object.fromEntries(plugins.map((p) => [p.type, p]));
  const types = [...WX_TYPES, ...Object.keys(byType)];
  (events || []).forEach((e, i) => {
    const at = `weather.events[${i}]${e.id ? ` (${e.id})` : ''}`;
    if (!e.id) errors.push(`${at}: needs an id`); else if (ids.has(e.id)) errors.push(`${at}: duplicate id`); ids.add(e.id);
    if (!types.includes(e.type)) { errors.push(`${at}: unknown type ${JSON.stringify(e.type)} (use ${types.join(', ')})`); return; }
    if (byType[e.type]) {
      if (!(Number.isFinite(e.t_in) && Number.isFinite(e.t_out) && e.t_out > e.t_in)) errors.push(`${at}: needs numeric t_in < t_out`);
      else if (e.t_out > duration + 1e-9) errors.push(`${at}: ends after the video (${e.t_out}s > ${duration}s)`);
      for (const m of (byType[e.type].validate ? byType[e.type].validate(e) : [])) errors.push(`${at}: ${m}`);
      return;
    }
    if (!(Number.isFinite(e.t_in) && Number.isFinite(e.t_out) && e.t_out > e.t_in)) errors.push(`${at}: needs numeric t_in < t_out`);
    else if (e.t_out > duration + 1e-9) errors.push(`${at}: ends after the video (${e.t_out}s > ${duration}s)`);
    if (e.type === 'temp_marker' && !(Number.isFinite(e.lon) && Number.isFinite(e.lat) && e.temp && e.city)) errors.push(`${at}: temp_marker needs lon, lat, temp and city`);
    if (e.type === 'forecast_strip' && !(Array.isArray(e.days) && e.days.length >= 3 && e.days.length <= 7)) errors.push(`${at}: forecast_strip needs 3 to 7 days`);
    if (e.type === 'now_card' && !(e.temp && e.title)) errors.push(`${at}: now_card needs temp and title`);
    if (e.type === 'alert_legend' && !(Array.isArray(e.items) && e.items.length)) errors.push(`${at}: alert_legend needs items`);
    if (e.type === 'source_line' && !e.text) errors.push(`${at}: source_line needs text`);
  });
  const strips = events.filter((e) => e.type === 'forecast_strip');
  for (let i = 0; i < strips.length; i++) for (let j = i + 1; j < strips.length; j++) {
    if (strips[i].t_in < strips[j].t_out && strips[j].t_in < strips[i].t_out) errors.push(`two forecast strips overlap (${strips[i].id}, ${strips[j].id}): show one at a time`);
  }
  return errors;
}
