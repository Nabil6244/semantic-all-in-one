// The overlay timeline: a flat list of events, each with an explicit time
// window. (Anchoring events to narration words is a later phase; by then this
// list is what the CSV compiler produces.) Validation follows the spec rules:
// at most 2 stat chips and 5 text layers on screen at once, one HUD title at a
// time, no silence longer than 5 s.
import { parseFormat } from './format.mjs';
import { LINE_KINDS, ROLES, FILL_ROLES } from './style.mjs';

export const EVENT_TYPES = ['hud_title', 'stat', 'caption', 'marker', 'line', 'dots', 'cluster', 'value_overlay', 'ghost_shape', 'streak', 'pip', 'filmstrip', 'sticker', 'media_full', 'fill'];
export const CARD_ANCHORS = ['tl', 'tr', 'ml', 'mr', 'bl', 'br', 'center'];
export const CARD_SHAPES = ['landscape', 'square', 'portrait'];
export const MAX_STAT = 2;
export const MAX_TEXT_LAYERS = 5;
export const MAX_GAP_S = 5;

/** How many text objects an event puts on screen. */
export function textLayers(e) {
  switch (e.type) {
    case 'hud_title': return e.sub ? 2 : 1;
    case 'stat': return 1;
    case 'caption': return 1;
    case 'marker': return e.sub ? 2 : 1;
    default: return 0;
  }
}

export function validateEvents(events, duration) {
  const errors = [], warnings = [];
  const ids = new Set();
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  (events || []).forEach((e, i) => {
    const at = `events[${i}]${e.id ? ` (${e.id})` : ''}`;
    if (!e.id) errors.push(`${at}: needs an id`);
    else if (ids.has(e.id)) errors.push(`${at}: duplicate id ${e.id}`);
    ids.add(e.id);
    if (!EVENT_TYPES.includes(e.type)) { errors.push(`${at}: unknown type ${JSON.stringify(e.type)} (use ${EVENT_TYPES.join(', ')})`); return; }
    if (!num(e.t_in) || !num(e.t_out) || e.t_out <= e.t_in) errors.push(`${at}: needs numeric t_in < t_out`);
    else if (num(duration) && e.t_out > duration + 1e-9) errors.push(`${at}: ends after the video (${e.t_out}s > ${duration}s)`);
    if (e.type === 'hud_title' && !e.label) errors.push(`${at}: hud_title needs a label`);
    if (e.type === 'stat') {
      if (!num(e.value_to)) errors.push(`${at}: stat needs a numeric value_to`);
      try { parseFormat(e.format ?? '0'); } catch (err) { errors.push(`${at}: ${err.message}`); }
    }
    if (e.type === 'caption' && !e.text) errors.push(`${at}: caption needs text`);
    if (e.type === 'marker') {
      if (!num(e.lon) || !num(e.lat)) errors.push(`${at}: marker needs numeric lon and lat`);
      if (!e.label) errors.push(`${at}: marker needs a label`);
      if (e.role && !ROLES[e.role]) errors.push(`${at}: unknown role ${e.role}`);
    }
    if (e.type === 'line') {
      if (!LINE_KINDS[e.kind]) errors.push(`${at}: line kind must be one of ${Object.keys(LINE_KINDS).join(', ')}`);
      if (!Array.isArray(e.coords) || e.coords.length < 2) errors.push(`${at}: line needs at least 2 coords`);
    }
    if (e.type === 'dots' || e.type === 'cluster') {
      const n = Array.isArray(e.points) ? e.points.length : (e.random ? e.random.n : 0);
      if (!(n > 0) && !e.data) errors.push(`${at}: ${e.type} needs points, random: {bbox, n} or data: "bundled:..." / "file:..."`);
    }
    if (e.type === 'value_overlay' && !e.data) errors.push(`${at}: value_overlay needs data: "bundled:rainfall_chirps" or "file:..."`);
    if (e.type === 'ghost_shape') {
      if (!e.iso || typeof e.iso !== 'string') errors.push(`${at}: ghost_shape needs iso (the country to copy, e.g. "POL")`);
      if (!e.to || !num(e.to.lon) || !num(e.to.lat)) errors.push(`${at}: ghost_shape needs to: {lon, lat} (where its centre goes)`);
      if (e.role && !ROLES[e.role]) errors.push(`${at}: unknown role ${e.role}`);
    }
    if (e.type === 'streak' && !e.region_iso && !e.bbox) errors.push(`${at}: streak needs region_iso or bbox`);
    if (e.type === 'pip') {
      if (!e.media && !(Array.isArray(e.images) && e.images.length)) errors.push(`${at}: pip needs media (a picture or video file) or images: [a, b] for a crossfade`);
      if (e.anchor && !CARD_ANCHORS.includes(e.anchor)) errors.push(`${at}: pip anchor must be one of ${CARD_ANCHORS.join(', ')}`);
      if (e.shape && !CARD_SHAPES.includes(e.shape)) errors.push(`${at}: pip shape must be one of ${CARD_SHAPES.join(', ')}`);
      if (e.leader && !(num(e.leader.lon) && num(e.leader.lat))) errors.push(`${at}: pip leader needs lon and lat`);
    }
    if (e.type === 'filmstrip') {
      if (!Array.isArray(e.cards) || e.cards.length < 3 || e.cards.length > 7) errors.push(`${at}: a filmstrip needs 3-7 cards (got ${Array.isArray(e.cards) ? e.cards.length : 0})`);
      else e.cards.forEach((c, k) => { if (!c || !c.media) errors.push(`${at}: card ${k + 1} needs media`); });
    }
    if (e.type === 'sticker') {
      if (!e.media) errors.push(`${at}: sticker needs media (a PNG with transparency)`);
      if (!(num(e.lon) && num(e.lat)) && !(e.at && num(e.at.x) && num(e.at.y))) errors.push(`${at}: sticker needs lon and lat (map position) or at: {x, y}`);
    }
    if (e.type === 'fill') {
      if (!(Array.isArray(e.iso) && e.iso.length) && !(Array.isArray(e.polys) && e.polys.length)) errors.push(`${at}: fill needs iso: ["KEN"] or polys (a MultiPolygon)`);
      if (e.role && !FILL_ROLES[e.role]) errors.push(`${at}: unknown fill role ${e.role} (use ${Object.keys(FILL_ROLES).join(', ')})`);
      if (e.opacity != null && !(e.opacity >= 0 && e.opacity <= 1)) errors.push(`${at}: fill opacity must be between 0 and 1`);
    }
    if (e.type === 'media_full' && !e.media) errors.push(`${at}: media_full needs media (a picture or video file)`);
  });
  if (errors.length) return { errors, warnings };

  // concurrency rules, checked at every start/end boundary
  const marks = [...new Set(events.flatMap((e) => [e.t_in, e.t_out]))].sort((a, b) => a - b);
  for (const t of marks) {
    const live = events.filter((e) => e.t_in <= t + 1e-9 && t < e.t_out - 1e-9);
    const stats = live.filter((e) => e.type === 'stat').length;
    if (stats > MAX_STAT) errors.push(`${stats} stat chips are on screen at ${t.toFixed(2)}s (max ${MAX_STAT}): ${live.filter((e) => e.type === 'stat').map((e) => e.id).join(', ')}. Shorten one with hold or t_end.`);
    const text = live.reduce((n, e) => n + textLayers(e), 0);
    if (text > MAX_TEXT_LAYERS) errors.push(`${text} text layers are on screen at ${t.toFixed(2)}s (max ${MAX_TEXT_LAYERS}): ${live.filter((e) => textLayers(e) > 0).map((e) => `${e.id}${textLayers(e) > 1 ? ` (${textLayers(e)})` : ''}`).join(', ')}. Shorten one with hold or t_end.`);
    if (live.filter((e) => e.type === 'hud_title').length > 1) errors.push(`two hud_title events overlap at ${t.toFixed(2)}s`);
    if (live.some((e) => e.type === 'sticker') && live.some((e) => e.type === 'pip' || e.type === 'filmstrip')) errors.push(`a sticker and a photo card are on screen together at ${t.toFixed(2)}s (the references show one rich picture at a time)`);
    if (live.filter((e) => e.type === 'media_full').length > 1) errors.push(`two media_full events overlap at ${t.toFixed(2)}s`);
  }
  // silence: no event of any kind for more than MAX_GAP_S
  if (num(duration) && events.length) {
    const spans = events.map((e) => [e.t_in, e.t_out]).sort((a, b) => a[0] - b[0]);
    let covered = 0;
    if (spans[0][0] > MAX_GAP_S) warnings.push(`nothing changes for the first ${spans[0][0].toFixed(1)}s`);
    for (const [a, b] of spans) {
      if (a - covered > MAX_GAP_S) warnings.push(`nothing changes between ${covered.toFixed(1)}s and ${a.toFixed(1)}s`);
      covered = Math.max(covered, b);
    }
    if (duration - covered > MAX_GAP_S) warnings.push(`nothing changes after ${covered.toFixed(1)}s`);
  }
  return { errors, warnings };
}

export const activeAt = (events, t) => (events || []).filter((e) => t >= e.t_in && t < e.t_out);

/** Checks the optional channel-name watermark block of a spec. */
export function validateWatermark(w) {
  if (w == null) return [];
  const errs = [];
  if (typeof w !== 'object') return ['watermark must be an object like {"text": "MY CHANNEL", "position": "br"}'];
  if (w.text != null && typeof w.text !== 'string') errs.push('watermark.text must be text');
  if (w.position != null && !['br', 'bl'].includes(w.position)) errs.push('watermark.position must be "br" (bottom right, as in the references) or "bl" (bottom left)');
  if (w.opacity != null && !(w.opacity >= 0 && w.opacity <= 1)) errs.push('watermark.opacity must be between 0 and 1');
  return errs;
}

/** Time windows covered by full-screen media. The map camera holds still under them. */
export const freezeWindows = (events) => (events || []).filter((e) => e.type === 'media_full').map((e) => [e.t_in, e.t_out]).sort((a, b) => a[0] - b[0]);

/** Every media reference an event uses, as { path, start_s, loop, maxW } (cards need small frames, full-screen needs big ones). */
export function mediaRefs(e) {
  const mk = (path, extra = {}) => ({ path, start_s: e.start_s ?? 0, loop: !!e.loop, maxW: 1920, ...extra });
  switch (e.type) {
    case 'pip': return (e.images && e.images.length ? e.images : [e.media]).map((p) => mk(p, { maxW: 900 }));
    case 'filmstrip': return (e.cards || []).map((c) => mk(c.media, { start_s: c.start_s ?? 0, loop: !!c.loop, maxW: 700 }));
    case 'sticker': return [mk(e.media, { maxW: 1400 })];
    case 'media_full': return [mk(e.media, { maxW: 1920 })];
    default: return [];
  }
}
export const mediaKey = (path, start = 0) => `${path}@${start}`;
