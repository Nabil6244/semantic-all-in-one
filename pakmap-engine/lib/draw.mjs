// Canvas drawing for the overlay layers. Runs in the renderer page only. All the
// numbers it uses (timing, geometry, colours) live in the pure modules next to it
// so they can be tested without a browser.
import { COLORS, FONT, GEOM, LINE_KINDS, ROLES, TIMING } from './style.mjs';
import { activeAt, mediaRefs, mediaKey } from './events.mjs';
import { formatValue, parseFormat, counterAt } from './format.mjs';
import { clamp01, easeOut, lifeAlpha, wordsVisible, lineProgress, dotsShown, clusterShown, revealOrder, cardState, clipFrame, crossfadeAt } from './anim.mjs';
import { hudLayout, statLayout, captionLayout, markerLayout, pickSide, watermarkLayout, cardRect, cardLabelRect, stripLayout, stickerRect, coverCrop, zoneLayout, applyPos, FRAME } from './layout.mjs';
import { trimPolyline } from './geom.mjs';
import { generatePoints } from './points.mjs';
import { mercY } from './raster.mjs';
import { footageWindows, shiftedEvent, footageAlpha, kenBurnsScale, resolveKenBurns, fitFrame } from './hybrid.mjs';

const font = (px) => `${FONT.weight} ${px}px ${FONT.family}, Montserrat, sans-serif`;
const easeOutBack = (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y); ctx.arcTo(x + w, y, x + w, y + h, rr); ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr); ctx.arcTo(x, y, x + w, y, rr); ctx.closePath();
}

export function createOverlay({ spec, ctx, project, unproject = null, fetchMedia = null }) {
  const W = spec.width, H = spec.height, S = H / FRAME.h;
  const events = spec.events || [];
  // Hybrid Map only: while full-screen media is up the map layers' clocks stop (empty for PakMap, so nothing changes there)
  const hold = spec.hybrid && spec.hybrid.pause_overlays ? footageWindows(events) : [];
  const measure = (text, px) => { ctx.save(); ctx.font = font(px); const w = ctx.measureText(text).width; ctx.restore(); return w; };

  // point sets are resolved once, in a fixed order
  const pointSets = new Map();
  for (const e of events) {
    if (e.type !== 'dots' && e.type !== 'cluster') continue;
    const pts = Array.isArray(e.points) ? e.points : (spec.point_files && e.points_file ? spec.point_files[e.points_file] : generatePoints(e.random));
    if (!pts || !pts.length) continue;
    pointSets.set(e.id, { pts, order: e.type === 'dots' ? revealOrder(pts.length, e.seed ?? 1) : pts.map((_, i) => i) });
  }

  // ---- pictures and clip frames: loaded ahead of each frame (prepare), then drawn synchronously ----
  const mediaIndex = spec.media_index || {};
  const bitmaps = new Map(); // "id:frame" -> ImageBitmap
  const fps = spec.fps;
  const lookup = (path, start = 0) => mediaIndex[mediaKey(path, start)];
  const frameOf = (info, t, tIn, loop) => (info.kind === 'video' ? (info.fit ? fitFrame(t, tIn, fps, info.count, info.rate) : clipFrame(t, tIn, fps, info.count, loop)) : 0);
  async function ensure(info, frame) {
    const k = `${info.id}:${frame}`;
    if (bitmaps.has(k)) return;
    if (!fetchMedia) throw new Error('media needs a loader');
    bitmaps.set(k, await fetchMedia(info.id, info.kind === 'video' ? frame : null));
    if (bitmaps.size > 160) { const old = bitmaps.keys().next().value; bitmaps.get(old)?.close?.(); bitmaps.delete(old); }
  }
  const bmp = (path, start, t, tIn, loop) => { const info = lookup(path, start); return info ? bitmaps.get(`${info.id}:${frameOf(info, t, tIn, loop)}`) || null : null; };
  /** Every picture/clip frame the layers visible at t will need. */
  async function prepare(t) {
    for (const e0 of activeAt(events, t)) {
      const e = shiftedEvent(e0, t, hold);
      if (e.type === 'filmstrip') {
        for (let i = 0; i < e.cards.length; i++) {
          const c = e.cards[i], info = lookup(c.media, c.start_s ?? 0);
          if (info) await ensure(info, frameOf(info, t, e.t_in + i * (e.stagger_s ?? TIMING.cardStagger), c.loop));
        }
        continue;
      }
      for (const ref of mediaRefs(e)) {
        const info = lookup(ref.path, ref.start_s); if (!info) continue;
        await ensure(info, frameOf(info, t, e.t_in, ref.loop));
      }
    }
  }
  // map-anchored cards remember the geo point under their first position, then follow the map
  const anchors = new Map();
  function followMap(id, cx, cy) {
    if (!unproject) return [0, 0];
    let a = anchors.get(id);
    if (!a) { const g = unproject(cx * S, cy * S); if (!g) return [0, 0]; a = { g, x0: cx, y0: cy }; anchors.set(id, a); }
    const q = project(a.g.lng ?? a.g[0], a.g.lat ?? a.g[1]);
    return q ? [q.x / S - a.x0, q.y / S - a.y0] : [0, 0];
  }

  function text(str, x, y, px, color, align = 'left', spacing = 0.4) {
    ctx.font = font(px); ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'alphabetic';
    ctx.letterSpacing = `${spacing}px`;
    ctx.fillText(str, x, y);
    ctx.letterSpacing = '0px';
  }

  // ---- map-anchored layers: drawn in real pixels, before the chips -------------------
  function drawDots(e, t) {
    const set = pointSets.get(e.id); if (!set) return;
    const n = e.type === 'dots' ? dotsShown(t, e.t_in, set.pts.length, e.reveal_s ?? TIMING.dotsReveal) : clusterShown(t, e.t_in, set.pts.length, e.stagger_s ?? TIMING.pointStagger);
    const a = lifeAlpha(t, e.t_in, e.t_out, 0.01, TIMING.chipOut);
    const r = ((e.size ?? (e.type === 'dots' ? TIMING.dotPx : 10)) / 2) * S;
    ctx.save(); ctx.globalAlpha = a * (e.opacity ?? 0.96); ctx.fillStyle = e.color || (e.type === 'dots' ? COLORS.yellow : COLORS.orange);
    ctx.beginPath();
    for (let k = 0; k < n; k++) {
      const p = set.pts[set.order[k]], q = project(p[0], p[1]);
      if (!q || q.x < -10 || q.y < -10 || q.x > W + 10 || q.y > H + 10) continue;
      ctx.moveTo(q.x + r, q.y); ctx.arc(q.x, q.y, r, 0, Math.PI * 2);
    }
    ctx.fill(); ctx.restore();
  }

  function drawLine(e, t) {
    const kind = LINE_KINDS[e.kind], a = lifeAlpha(t, e.t_in, e.t_out, 0.01, TIMING.chipOut);
    const pts = e.coords.map(([lon, lat]) => { const q = project(lon, lat); return q ? [q.x, q.y] : null; }).filter(Boolean);
    if (pts.length < 2) return;
    const prog = lineProgress(t, e.t_draw ?? e.t_in, e.draw_s ?? TIMING.lineDraw);
    const { points, angle } = trimPolyline(pts, prog);
    ctx.save(); ctx.globalAlpha = a; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.strokeStyle = e.color || kind.color; ctx.lineWidth = (e.width ?? kind.width) * S;
    ctx.shadowColor = 'rgba(0,0,0,0.55)'; ctx.shadowBlur = 8 * S;
    if (kind.dash) ctx.setLineDash(kind.dash.map((d) => d * S));
    ctx.beginPath(); points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
    if (kind.arrow && prog > 0.02) {
      const [hx, hy] = points[points.length - 1], L = 26 * S;
      ctx.setLineDash([]); ctx.shadowBlur = 0; ctx.fillStyle = e.color || kind.color;
      ctx.beginPath();
      ctx.moveTo(hx + Math.cos(angle) * L * 0.55, hy + Math.sin(angle) * L * 0.55);
      ctx.lineTo(hx + Math.cos(angle + 2.5) * L, hy + Math.sin(angle + 2.5) * L);
      ctx.lineTo(hx + Math.cos(angle - 2.5) * L, hy + Math.sin(angle - 2.5) * L);
      ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }

  // A moved country outline (same size as the original), e.g. Poland laid over Kenya.
  function drawGhost(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, e.fade_in ?? 0.4, TIMING.chipOut); if (a <= 0) return;
    const col = (ROLES[e.role || 'compare'] || ROLES.compare).bg;
    ctx.save(); ctx.globalAlpha = a; ctx.beginPath();
    for (const poly of e.polys) for (const ring of poly) ring.forEach(([lon, lat], i) => { const q = project(lon, lat); if (q) (i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y)); });
    ctx.fillStyle = col; ctx.globalAlpha = a * (e.fill_opacity ?? 0.38); ctx.fill('evenodd');
    ctx.globalAlpha = a; ctx.lineWidth = 3 * S; ctx.strokeStyle = col; ctx.lineJoin = 'round'; ctx.stroke();
    ctx.restore();
  }

  // Decorative streaks over a region ("something you can't see"): short curved white lines that draw in one after another.
  function drawStreaks(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, 0.1, TIMING.chipOut); if (a <= 0) return;
    const heading = ((e.heading_deg ?? 60) * Math.PI) / 180, total = e.stagger_s ?? 1.2, draw = e.draw_s ?? 0.8, base = (e.length_px ?? 110) * S;
    ctx.save(); ctx.lineCap = 'round'; ctx.strokeStyle = e.color || COLORS.white; ctx.lineWidth = (e.width ?? 3) * S; ctx.shadowColor = 'rgba(0,0,0,0.4)'; ctx.shadowBlur = 4 * S;
    for (const [lon, lat, ph] of e.seeds) {
      const prog = lineProgress(t, e.t_in + ph * total, draw); if (prog <= 0) continue;
      const q = project(lon, lat); if (!q) continue;
      const len = base * (0.55 + 0.9 * ((ph * 7.31) % 1)), ang = heading + (((ph * 13.7) % 1) - 0.5) * 0.7, bend = (((ph * 5.17) % 1) - 0.5) * 0.9 * len;
      const nx = -Math.sin(ang), ny = Math.cos(ang), pts = [];
      for (let k = 0; k <= 14; k++) { const u = k / 14, off = Math.sin(u * Math.PI) * bend; pts.push([q.x + Math.cos(ang) * len * (u - 0.5) + nx * off, q.y + Math.sin(ang) * len * (u - 0.5) + ny * off]); }
      const { points } = trimPolyline(pts, prog);
      ctx.globalAlpha = a * (e.opacity ?? 0.85) * (0.6 + 0.4 * ph);
      ctx.beginPath(); points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
    }
    ctx.restore();
  }

  // ---- chips: drawn in 1080p reference units -----------------------------------------
  const markerState = new Map(); // remembered label side per marker so it never flips mid-shot
  function drawMarker(e, t) {
    const q = project(e.lon, e.lat); if (!q) return;
    const x = q.x / S, y = q.y / S, role = ROLES[e.role || 'dark'];
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.markerPop, TIMING.chipOut);
    if (a <= 0) return;
    if (e.dot === false) { // a county/zone name sitting on its region: chip only, centred on the point
      const Z = zoneLayout({ x, y, text: e.label }, measure), slide0 = (1 - easeOut(clamp01((t - e.t_in) / TIMING.chipIn))) * 8, zr = ROLES[e.role || 'neutral'] || ROLES.neutral;
      ctx.save(); ctx.globalAlpha = a; ctx.shadowColor = 'rgba(0,0,0,0.4)'; ctx.shadowBlur = 8; ctx.shadowOffsetY = 3; ctx.fillStyle = zr.bg;
      roundRect(ctx, Z.x, Z.y + slide0, Z.w, Z.h, Z.r); ctx.fill(); ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      text(Z.text, Z.x + Z.w / 2, Z.y + slide0 + Z.h / 2 + Z.px * 0.35, Z.px, zr.fg, 'center', 0.4);
      ctx.restore(); return;
    }
    const text0 = e.value ? `${e.label} · ${e.value}` : e.label;
    let side = markerState.get(e.id);
    if (!side) {
      side = e.side && e.side !== 'auto' ? e.side : pickSide(x, y, measure(text0, GEOM.marker.chipPx) + 2 * GEOM.marker.padX, GEOM.marker.chipH);
      markerState.set(e.id, side);
    }
    const L = markerLayout({ x, y, label: e.label, value: e.value, side }, measure);
    const pop = easeOutBack(clamp01((t - e.t_in) / TIMING.markerPop));
    ctx.save(); ctx.globalAlpha = a;
    // ring dot
    ctx.translate(x, y); ctx.scale(pop, pop);
    ctx.fillStyle = COLORS.panel; ctx.strokeStyle = COLORS.white; ctx.lineWidth = GEOM.marker.ring;
    ctx.beginPath(); ctx.arc(0, 0, L.dot.r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = COLORS.white; ctx.beginPath(); ctx.arc(0, 0, 3.5, 0, Math.PI * 2); ctx.fill();
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.scale(S, S);
    // chip
    const c = L.chip, slide = (1 - easeOut(clamp01((t - e.t_in) / TIMING.chipIn))) * 8;
    ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 8; ctx.fillStyle = role.bg; roundRect(ctx, c.x, c.y + slide, c.w, c.h, c.r); ctx.fill();
    ctx.shadowBlur = 0;
    text(c.text, c.x + c.w / 2, c.y + slide + c.h / 2 + c.px * 0.35, c.px, role.fg, 'center', 0.3);
    if (e.sub) {
      const sw = measure(e.sub, 22) + 2 * 12, sx = c.x, sy = c.y + c.h + 6 + slide;
      ctx.fillStyle = COLORS.subtitle; roundRect(ctx, sx, sy, sw, 36, 7); ctx.fill();
      text(e.sub, sx + sw / 2, sy + 25, 22, COLORS.white, 'center', 0.5);
    }
    ctx.restore();
  }

  function drawHud(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, 0.01, TIMING.chipOut); if (a <= 0) return;
    const L = hudLayout({ label: e.label, sub: e.sub }, measure);
    ctx.save(); ctx.globalAlpha = a;
    if (L.subtitle) {
      const s = L.subtitle, grow = easeOut(clamp01((t - e.t_in) / TIMING.subtitleGrow));
      ctx.fillStyle = COLORS.subtitle; roundRect(ctx, s.x, s.y, Math.max(2 * s.r, s.w * grow), s.h, s.r); ctx.fill();
      const n = wordsVisible(t, e.t_in + TIMING.subtitleGrow + 0.1, s.words.length);
      if (n > 0) text(s.words.slice(0, n).join(' '), s.x + GEOM.subtitle.padX, s.y + s.h / 2 + s.px * 0.35, s.px, COLORS.white, 'left', 0.9);
    }
    const tt = L.title, k = clamp01((t - (e.t_in + 0.17)) / TIMING.titlePop);
    if (k > 0) {
      ctx.save(); ctx.globalAlpha = a * k; ctx.translate(tt.x + tt.w / 2, tt.y + tt.h / 2); const sc = 0.94 + 0.06 * k; ctx.scale(sc, sc);
      ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 10; ctx.fillStyle = COLORS.white; roundRect(ctx, -tt.w / 2, -tt.h / 2, tt.w, tt.h, tt.r); ctx.fill(); ctx.shadowBlur = 0;
      text(tt.text, 0, tt.px * 0.35, tt.px, COLORS.text_dark, 'center', -0.4);
      ctx.restore();
    }
    ctx.restore();
  }

  function drawStat(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.chipIn, TIMING.chipOut); if (a <= 0) return;
    const fmt = parseFormat(e.format ?? '0'), from = e.value_from ?? e.value_to;
    const v = counterAt(t, { from, to: e.value_to, t0: e.t_in + 0.1, dur: e.ramp_dur ?? TIMING.statRamp });
    const widest = [formatValue(from, fmt), formatValue(e.value_to, fmt)].sort((p, q) => measure(q, GEOM.stat.numberPx) - measure(p, GEOM.stat.numberPx))[0];
    const L = applyPos(statLayout({ anchor: e.anchor || 'br', number: widest, sub: e.sub }, measure), e.pos);
    const slide = (1 - easeOut(clamp01((t - e.t_in) / TIMING.chipIn))) * 18;
    ctx.save(); ctx.globalAlpha = a; ctx.translate(0, slide);
    ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 16; ctx.fillStyle = 'rgba(8,19,32,0.94)'; roundRect(ctx, L.x, L.y, L.w, L.h, L.r); ctx.fill(); ctx.shadowBlur = 0;
    text(formatValue(v, fmt), L.number.cx, L.number.baseline, L.number.px, e.color || COLORS.yellow, 'center', -0.5);
    if (L.sub) text(L.sub.text, L.sub.cx, L.sub.baseline, L.sub.px, COLORS.white, 'center', 0.8);
    ctx.restore();
  }

  function drawCaption(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.chipIn, TIMING.chipOut); if (a <= 0) return;
    const L = captionLayout({ text: e.text, sub: e.sub, anchor: e.anchor || 'bc' }, measure);
    const slide = (1 - easeOut(clamp01((t - e.t_in) / TIMING.chipIn))) * 14;
    ctx.save(); ctx.globalAlpha = a; ctx.translate(0, slide);
    ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 14; ctx.fillStyle = 'rgba(8,19,32,0.94)'; roundRect(ctx, L.x, L.y, L.w, L.h, L.r); ctx.fill(); ctx.shadowBlur = 0;
    L.lines.forEach((ln) => text(ln.text, ln.cx, ln.baseline, ln.px, COLORS.yellow, 'center', 0.4));
    if (L.sub) text(L.sub.text, L.sub.cx, L.sub.baseline, L.sub.px, COLORS.white, 'center', 0.6);
    ctx.restore();
  }

  // ---- rich media (reference units) ----------------------------------------------------
  function paintImage(b, x, y, w, h, radius, alpha = 1) {
    if (!b || alpha <= 0) return;
    const c = coverCrop(b.width, b.height, w, h);
    ctx.save(); ctx.globalAlpha *= alpha; roundRect(ctx, x, y, w, h, radius); ctx.clip();
    ctx.drawImage(b, c.sx, c.sy, c.sw, c.sh, x, y, w, h); ctx.restore();
  }
  /** One framed photo card: white border and shadow, snapping in from 115 %, plain fade out. */
  function paintCard(rect, st, getBitmaps, label) {
    if (st.alpha <= 0) return;
    const g = GEOM.card, cx = rect.x + rect.w / 2 + st.dx, cy = rect.y + rect.h / 2 + st.dy;
    ctx.save(); ctx.globalAlpha = st.alpha; ctx.translate(cx, cy); ctx.scale(st.scale, st.scale);
    ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = g.shadowBlur; ctx.shadowOffsetY = 4;
    ctx.fillStyle = `rgba(255,255,255,${st.border})`; roundRect(ctx, -rect.w / 2, -rect.h / 2, rect.w, rect.h, g.radius); ctx.fill();
    if (st.border < 1) { ctx.fillStyle = '#1a1f26'; roundRect(ctx, -rect.w / 2 + 2, -rect.h / 2 + 2, rect.w - 4, rect.h - 4, g.radius - 2); ctx.fill(); }
    ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    const b = g.border, ix = -rect.w / 2 + b, iy = -rect.h / 2 + b, iw = rect.w - 2 * b, ih = rect.h - 2 * b;
    for (const [bm, a] of getBitmaps()) paintImage(bm, ix, iy, iw, ih, g.radius - b, a);
    ctx.restore();
    if (label) {
      const L = cardLabelRect(rect, label, measure);
      ctx.save(); ctx.globalAlpha = st.alpha; ctx.translate(st.dx, st.dy);
      ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 8; ctx.shadowOffsetY = 3; ctx.fillStyle = COLORS.yellow; roundRect(ctx, L.x, L.y, L.w, L.h, L.r); ctx.fill(); ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      text(L.text, L.x + L.w / 2, L.y + L.h / 2 + L.px * 0.35, L.px, COLORS.text_dark, 'center', 0.4);
      ctx.restore();
    }
  }

  function drawPip(e, t) {
    if (t < e.t_in || t >= e.t_out) return;
    const st = cardState(t, e.t_in, e.t_out); if (st.alpha <= 0) return;
    const rect0 = cardRect({ anchor: e.anchor || 'tr', shape: e.shape, w: e.w, offset: e.offset || [0, 0] });
    let rect = rect0;
    if (e.at) { const q = project(e.at.lon, e.at.lat); if (q) rect = { ...rect0, x: q.x / S - rect0.w / 2 + (e.offset?.[0] || 0), y: q.y / S - rect0.h / 2 + (e.offset?.[1] || 0) }; }
    else { const [dx, dy] = followMap(e.id, rect0.x + rect0.w / 2, rect0.y + rect0.h / 2); rect = { ...rect0, x: rect0.x + dx, y: rect0.y + dy }; }
    if (e.leader) {
      const q = project(e.leader.lon, e.leader.lat);
      if (q) {
        ctx.save(); ctx.globalAlpha = st.alpha; ctx.strokeStyle = COLORS.white; ctx.fillStyle = COLORS.white; ctx.lineWidth = 3; ctx.lineCap = 'round';
        const tx = q.x / S, ty = q.y / S, sx = Math.max(rect.x, Math.min(rect.x + rect.w, tx)), sy = Math.max(rect.y, Math.min(rect.y + rect.h, ty));
        ctx.shadowColor = 'rgba(0,0,0,0.5)'; ctx.shadowBlur = 6; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(tx, ty); ctx.stroke();
        ctx.beginPath(); ctx.arc(tx, ty, 7, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      }
    }
    const list = e.images && e.images.length ? e.images : [e.media];
    const xf = crossfadeAt(t, e.t_in, list.length, e.every_s ?? 3.0);
    paintCard(rect, st, () => {
      const get = (i) => bmp(list[i], e.start_s ?? 0, t, e.t_in, e.loop);
      return xf.mix > 0 ? [[get(xf.from), 1], [get(xf.to), xf.mix]] : [[get(xf.to), 1]];
    }, e.label);
  }

  function drawFilmstrip(e, t) {
    if (t < e.t_in || t >= e.t_out) return;
    const rects = stripLayout(e.cards.length, { align: e.align || 'center' });
    const [dx, dy] = followMap(e.id, 960, rects[0].y + rects[0].h / 2);
    e.cards.forEach((c, i) => {
      const t0 = e.t_in + i * (e.stagger_s ?? TIMING.cardStagger), st = cardState(t, t0, e.t_out);
      if (st.alpha <= 0) return;
      const r = { ...rects[i], x: rects[i].x + dx, y: rects[i].y + dy };
      paintCard(r, st, () => [[bmp(c.media, c.start_s ?? 0, t, t0, c.loop), 1]], c.label);
    });
  }

  function drawSticker(e, t) {
    const a = lifeAlpha(t, e.t_in, e.t_out, TIMING.stickerIn / 2, TIMING.stickerOut); if (a <= 0) return;
    const b = bmp(e.media, 0, t, e.t_in, false); if (!b) return;
    let x, y;
    if (e.at) { x = e.at.x; y = e.at.y; } else { const q = project(e.lon, e.lat); if (!q) return; x = q.x / S; y = q.y / S; }
    const r = stickerRect({ x, y, aspect: b.width / b.height, heightFrac: e.height_frac });
    const k = clamp01((t - e.t_in) / TIMING.stickerIn), sc = 0.6 + 0.4 * easeOutBack(k);
    ctx.save(); ctx.globalAlpha = a; ctx.translate(x, y); ctx.scale(sc, sc); ctx.drawImage(b, r.x - x, r.y - y, r.w, r.h); ctx.restore();
  }

  function drawMediaFull(e, t) {
    if (t < e.t_in || t >= e.t_out) return;
    // a straight cross-dissolve: linear both ways (a clip handed over to the next one stays opaque; see lib/hybrid.mjs)
    const a = e.xfade_prev || events.some((o) => o.xfade_prev) ? footageAlpha(e, t, events, TIMING.dissolve) : Math.min(clamp01((t - e.t_in) / (e.dissolve_s ?? TIMING.dissolve)), clamp01((e.t_out - t) / (e.dissolve_s ?? TIMING.dissolve)));
    if (a <= 0) return;
    const b = bmp(e.media, e.start_s ?? 0, t, e.t_in, e.loop); if (!b) return;
    ctx.save(); ctx.globalAlpha = a; const c = coverCrop(b.width, b.height, FRAME.w, FRAME.h);
    const k = kenBurnsScale(resolveKenBurns(e, e.kenburns === 'auto' ? lookup(e.media, e.start_s ?? 0) : null), t);
    if (k !== 1) { ctx.translate(FRAME.w / 2, FRAME.h / 2); ctx.scale(k, k); ctx.translate(-FRAME.w / 2, -FRAME.h / 2); }
    ctx.drawImage(b, c.sx, c.sy, c.sw, c.sh, 0, 0, FRAME.w, FRAME.h); ctx.restore();
  }

  function drawWatermark() {
    const w = spec.watermark; if (!w || !w.text || w.enabled === false) return;
    const L = watermarkLayout({ text: String(w.text).toUpperCase(), position: w.position || 'br' }, measure);
    ctx.save(); ctx.globalAlpha = w.opacity ?? 0.6;
    ctx.font = font(L.px); ctx.letterSpacing = '1px';
    ctx.fillStyle = COLORS.yellow; ctx.beginPath();
    ctx.moveTo(L.iconX + 6, L.baseline - 17); ctx.lineTo(L.iconX + 6, L.baseline + 1); ctx.lineTo(L.iconX + 21, L.baseline - 8); ctx.closePath(); ctx.fill();
    ctx.fillStyle = COLORS.white; ctx.textAlign = 'left'; ctx.fillText(String(w.text).toUpperCase(), L.textX, L.baseline);
    ctx.restore();
  }

  return {
    measure,
    prepare,
    /** Draw every active overlay for time t onto ctx (the map is already on it). Call prepare(t) first. */
    draw(t) {
      const live = activeAt(events, t).map((e) => shiftedEvent(e, t, hold)), each = (type, fn) => { for (const e of live) if (e.type === type) fn(e, t); };
      // map-anchored layers, in real pixels
      ctx.save();
      each('ghost_shape', drawGhost); each('streak', drawStreaks);
      for (const e of live) if (e.type === 'dots' || e.type === 'cluster') drawDots(e, t);
      each('line', drawLine);
      ctx.restore();
      // everything else in 1080p reference units. Full-screen media covers the map layers (and markers/stickers)
      // but stays UNDER the cards, stat chips, captions and the HUD. Hybrid footage (cover_ui) goes over those too.
      ctx.save(); ctx.scale(S, S);
      each('marker', drawMarker); each('sticker', drawSticker);
      for (const e of live) if (e.type === 'media_full' && !e.cover_ui) drawMediaFull(e, t);
      each('pip', drawPip); each('filmstrip', drawFilmstrip);
      each('stat', drawStat); each('caption', drawCaption); each('hud_title', drawHud);
      for (const e of live) if (e.type === 'media_full' && e.cover_ui) drawMediaFull(e, t);
      drawWatermark();
      ctx.restore();
    },
  };
}
