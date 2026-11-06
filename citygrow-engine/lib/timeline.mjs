// The film's clock: when each era's time skip runs and how long its view holds, the year and population at any t, the
// text on screen, and the camera path. Pure: the same story and city give the same film, frame by frame.
//
// Every era after the first opens with a time skip (the year counts up, the city grows or shrinks, the camera rises a
// little to show it), then holds on the new city while the camera keeps moving and the captions read.

import { yearLabel, styleForYear } from './story.mjs';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const ease = (k) => { k = clamp(k, 0, 1); return k * k * k * (k * (6 * k - 15) + 10); };
const smooth = (k) => { k = clamp(k, 0, 1); return k * k * (3 - 2 * k); };
const lerp = (a, b, k) => a + (b - a) * k;
const angLerp = (a, b, k) => a + ((((b - a) % 360) + 540) % 360 - 180) * k;

export const INTRO = 4.5, OUTRO = 3.5, TITLE_HOLD = 3.4, CAPTION_WPS = 2.7;
const SHOT_CYCLE = ['orbit', 'push', 'flyover', 'pullback', 'low_track', 'orbit', 'push', 'pullback'];
const MIN_DIST = 110, MAX_DIST = 7000;

export const readSeconds = (text) => (text ? text.trim().split(/\s+/).length / CAPTION_WPS + 1.3 : 0);
export function skipSeconds(dy) { return clamp(2.4 + 0.85 * Math.log2(1 + Math.abs(dy) / 25), 2.6, 7.5); }

/** Population on the counter: rounded the way an estimate is written. */
export function popLabel(p) {
  const r = p < 1000 ? 50 : p < 10000 ? 100 : p < 100000 ? 1000 : p < 1e6 ? 5000 : 50000;
  return `c. ${(Math.round(p / r) * r).toLocaleString('en-US')}`;
}

/**
 * story: parseStory() result. city: { toXZ(lon, lat) -> {x, z}, extent(year, pop) -> {x, z, r}, landmarkXZ: {id: {x, z}} }.
 */
export function buildTimeline(story, city) {
  const eras = story.eras;
  const adPrefix = eras[0].year < 0 && eras.some((e) => e.year > 0 && e.year < 1000);
  const keys = [], titles = [], captions = [], badges = [], holds = [];
  let t = INTRO;
  // the opening: the city's name over its first view
  const first = eras[0], last = eras[eras.length - 1];
  titles.push({ t0: 0.6, t1: INTRO + 1.2, title: (story.plan.city || story.plan.title || '').toUpperCase(),
    kicker: `${yearLabel(first.year, { adPrefix: false })} – ${yearLabel(last.year, { adPrefix })}`, big: true });
  keys.push({ t: 0, year: first.year, pop: first.population });
  // event captions join the first era at or after them
  const evCap = new Map();
  for (const ev of story.events) if (ev.caption) {
    const host = eras.find((e) => e.year >= ev.year) || last;
    evCap.set(host, [...(evCap.get(host) || []), ev.caption]);
  }
  eras.forEach((e, i) => {
    let tr0 = t, tr1 = t;
    if (i > 0) {
      tr1 = t + skipSeconds(e.year - eras[i - 1].year);
      keys.push({ t: tr0, year: eras[i - 1].year, pop: eras[i - 1].population });
      keys.push({ t: tr1, year: e.year, pop: e.population });
    }
    const texts = [...(evCap.get(e) || []), ...(e.caption ? [e.caption] : [])];
    const titleT = e.title ? TITLE_HOLD : 0;
    const need = 1.0 + titleT + texts.reduce((s, x) => s + readSeconds(x), 0) + 0.8;
    const hold = Math.max(e.hold ?? 0, need, 5.5);
    const h0 = tr1, h1 = tr1 + hold;
    badges.push({ t: i === 0 ? 0 : (tr0 + tr1) / 2, name: e.name || '', flag: e.flag || '' });
    if (e.title) titles.push({ t0: h0 + 0.2, t1: h0 + 0.2 + TITLE_HOLD, title: e.title.toUpperCase(), kicker: e.kicker || '' });
    let c0 = h0 + 0.6 + titleT;
    const each = texts.length ? (h1 - 0.4 - c0) / texts.reduce((s, x) => s + readSeconds(x), 0) : 0;
    for (const x of texts) { const d = readSeconds(x) * each; captions.push({ t0: c0, t1: c0 + d, text: x }); c0 += d; }
    holds.push({ era: i, tr0, tr1, h0, h1, year: e.year, pop: e.population, style: e.style || styleForYear(e.year) });
    t = h1;
  });
  const duration = t + OUTRO;
  keys.push({ t: duration, year: last.year, pop: last.population });
  const tl = { duration, keys, titles, captions, badges, holds, adPrefix, styles: holds.map((h) => h.style) };
  tl.camera = cameraPath(story, city, tl);
  tl.landmarkTimes = Object.fromEntries(story.landmarks.map((l) => [l.id, {
    tIn: l.year == null || l.year <= first.year ? -1e9 : timeOfYear(tl, l.year),
    tOut: l.until == null ? 1e9 : timeOfYear(tl, l.until),
  }]));
  tl.eventTimes = story.events.map((ev) => timeOfYear(tl, ev.year));
  return tl;
}

/** Year and population at t: flat on holds, eased through each skip (population geometric, so growth reads evenly). */
export function stateAt(tl, t) {
  const k = tl.keys;
  let i = 0; while (i + 1 < k.length && k[i + 1].t <= t) i++;
  const a = k[i], b = k[Math.min(k.length - 1, i + 1)];
  if (b.t <= a.t || a.year === b.year && a.pop === b.pop) return { year: a.year, pop: a.pop, skip: 0 };
  const e = ease((t - a.t) / (b.t - a.t));
  const pop = a.pop > 0 && b.pop > 0 ? Math.exp(lerp(Math.log(a.pop), Math.log(b.pop), e)) : lerp(a.pop, b.pop, e);
  return { year: lerp(a.year, b.year, e), pop, skip: Math.sin(Math.PI * clamp((t - a.t) / (b.t - a.t), 0, 1)) };
}

/** The screen time at which the story reaches a year (first crossing; before the story -> 0, after it -> the end). */
export function timeOfYear(tl, y) {
  const k = tl.keys;
  if (y <= k[0].year) return 0;
  for (let i = 0; i + 1 < k.length; i++) {
    const a = k[i], b = k[i + 1];
    if (y >= a.year && y <= b.year && b.year > a.year) {
      // invert the eased year: bisection
      let lo = 0, hi = 1;
      for (let n = 0; n < 30; n++) { const m = (lo + hi) / 2; if (lerp(a.year, b.year, ease(m)) < y) lo = m; else hi = m; }
      return a.t + (b.t - a.t) * hi;
    }
  }
  return tl.duration;
}

/** Index of the era on screen at t (the skip into an era belongs to it). */
export function eraIndexAt(tl, t) {
  let i = 0; for (let k = 0; k < tl.holds.length; k++) if (tl.holds[k].tr0 <= t) i = k;
  return i;
}

/** Everything the text layer shows at t. */
export function hudAt(tl, t) {
  const s = stateAt(tl, t);
  const fadeIn = (t0, t1, d = 0.6) => smooth((t - t0) / d) * smooth((t1 - t) / d);
  const title = tl.titles.find((x) => t >= x.t0 && t <= x.t1);
  const cap = tl.captions.find((x) => t >= x.t0 && t <= x.t1);
  let bi = 0; for (let k = 0; k < tl.badges.length; k++) if (tl.badges[k].t <= t) bi = k;
  const prev = tl.badges[Math.max(0, bi - 1)], cur = tl.badges[bi];
  const swap = bi > 0 ? smooth((t - cur.t) / 0.7) : 1;
  return {
    year: yearLabel(s.year, { adPrefix: tl.adPrefix }), yearNum: s.year, pop: popLabel(s.pop), skip: s.skip,
    badge: cur, badgePrev: prev, badgeSwap: swap,
    title: title ? { ...title, alpha: fadeIn(title.t0, title.t1, 0.8) } : null,
    caption: cap ? { text: cap.text, alpha: fadeIn(cap.t0, cap.t1, 0.5) } : null,
    black: Math.max(1 - smooth(t / 1.2), smooth((t - (tl.duration - 1.4)) / 1.4)),
    hudAlpha: smooth((t - INTRO + 1.0) / 1.0),
  };
}

// ------------------------------------------------------------------------------------------------ camera
// State: { x, z (metres, focus on the ground), dist (m from focus), heading (deg, 0 = looking north), tilt (deg from
// straight down) }.

function shotStates(kind, f, R, heading) {
  const H = heading, rad = (H * Math.PI) / 180, fx = Math.sin(rad), fz = -Math.cos(rad);
  const d = (v) => clamp(v, MIN_DIST, MAX_DIST);
  switch (kind) {
    case 'establishing': return [{ ...f, dist: d(R * 2.4), tilt: 40, heading: H }, { ...f, dist: d(R * 1.9), tilt: 46, heading: H + 14 }];
    case 'push': return [{ ...f, dist: d(R * 1.5), tilt: 48, heading: H }, { ...f, dist: d(R * 0.7), tilt: 57, heading: H + 10 }];
    case 'pullback': return [{ ...f, dist: d(R * 0.55), tilt: 60, heading: H }, { ...f, dist: d(R * 1.5), tilt: 46, heading: H - 10 }];
    case 'landmark': {   // close orbit around a new building: R is its size here
      const D = clamp(R * 4.5, 200, 750);
      return [{ ...f, dist: D * 1.25, tilt: 52, heading: H }, { ...f, dist: D, tilt: 58, heading: H + 38 }];
    }
    case 'flyover': return [
      { x: f.x - fx * R * 0.45, z: f.z - fz * R * 0.45, dist: d(R * 0.75), tilt: 60, heading: H },
      { x: f.x + fx * R * 0.45, z: f.z + fz * R * 0.45, dist: d(R * 0.7), tilt: 60, heading: H + 6 }];
    case 'low_track': {
      const sx = -fz, sz = fx, D = clamp(R * 0.35, 160, 420);
      return [{ x: f.x - sx * D * 0.6, z: f.z - sz * D * 0.6, dist: D, tilt: 66, heading: H }, { x: f.x + sx * D * 0.6, z: f.z + sz * D * 0.6, dist: D, tilt: 64, heading: H + 4 }];
    }
    default: return [{ ...f, dist: d(R * 1.15), tilt: 50, heading: H }, { ...f, dist: d(R * 1.0), tilt: 53, heading: H + 30 }];   // orbit
  }
}

export function cameraPath(story, city, tl) {
  const segs = [];
  let heading = story.plan.heading ?? 20, prevKind = null, prevEnd = null, cyc = 0;
  tl.holds.forEach((h, i) => {
    const e = story.eras[h.era];
    const ext = city.extent(h.year, h.pop, h.style);
    let f = { x: ext.x, z: ext.z };
    if (e.focus) f = city.toXZ(e.focus.lon, e.focus.lat);
    else if (e.focusId && city.landmarkXZ?.[e.focusId]) f = city.landmarkXZ[e.focusId];
    let kind = e.shot || (i === 0 ? 'establishing' : null);
    let R = ext.r;
    // a building that appears with this era is what the era is about: fly in close to it (largest one first)
    const prevYear = i ? story.eras[h.era - 1].year : -Infinity;
    const fresh = !e.shot && !e.focus && !e.focusId && i > 0 && story.landmarks
      .filter((l) => l.year != null && l.year > prevYear && l.year <= h.year && city.landmarkXZ?.[l.id] && l.lon != null)
      .sort((a, b) => (b.extra?.size ?? 60) - (a.extra?.size ?? 60))[0];
    if (fresh) { kind = 'landmark'; f = city.landmarkXZ[fresh.id]; R = fresh.extra?.size ?? 60; }
    if (!kind) { do { kind = SHOT_CYCLE[cyc++ % SHOT_CYCLE.length]; } while (kind === prevKind); }
    let [a, b] = shotStates(kind, f, R, heading);
    if (i === 0) {   // the opening drifts in over the title
      const pre = { ...a, dist: clamp(a.dist * 1.35, MIN_DIST, MAX_DIST), tilt: a.tilt - 6, heading: a.heading - 10 };
      segs.push({ type: 'move', t0: 0, t1: h.h0, from: pre, to: a, ease: 'linear' });
    } else {
      // the skip: rise to see the whole city change, then settle into the new view
      const travel = Math.hypot(a.x - prevEnd.x, a.z - prevEnd.z);
      const peak = clamp(Math.max(prevEnd.dist, a.dist, travel * 1.1, ext.r * 1.6), MIN_DIST, MAX_DIST);
      segs.push({ type: 'fly', t0: h.tr0, t1: h.tr1, from: prevEnd, to: a, peak });
    }
    segs.push({ type: 'move', t0: h.h0, t1: h.h1, from: a, to: b, ease: 'linear' });
    prevEnd = b; prevKind = kind; heading = b.heading;
  });
  const end = prevEnd, last = tl.holds[tl.holds.length - 1];
  segs.push({ type: 'move', t0: last.h1, t1: tl.duration, from: end, to: { ...end, dist: clamp(end.dist * 1.6, MIN_DIST, MAX_DIST), tilt: end.tilt - 8, heading: end.heading + 8 }, ease: 'linear' });
  return segs;
}

function softLinear(k, r = 0.15) {
  k = clamp(k, 0, 1); const v = 1 / (1 - r);
  if (k < r) return (v * k * k) / (2 * r);
  if (k > 1 - r) return 1 - (v * (1 - k) * (1 - k)) / (2 * r);
  return v * (k - r / 2);
}

function mix(a, b, e, distE = e) {
  return { x: lerp(a.x, b.x, e), z: lerp(a.z, b.z, e), dist: Math.exp(lerp(Math.log(a.dist), Math.log(b.dist), distE)),
    tilt: lerp(a.tilt, b.tilt, e), heading: angLerp(a.heading, b.heading, e) };
}

export function cameraAt(path, t) {
  let seg = path[0];
  for (const s of path) { if (s.t0 <= t) seg = s; else break; }
  const k = seg.t1 > seg.t0 ? clamp((t - seg.t0) / (seg.t1 - seg.t0), 0, 1) : 1;
  let c;
  if (seg.type === 'fly') {
    const e = ease(k);
    c = mix(seg.from, seg.to, e);
    const bump = Math.max(0, Math.log(seg.peak) - Math.max(Math.log(seg.from.dist), Math.log(seg.to.dist)));
    c.dist = Math.exp(lerp(Math.log(seg.from.dist), Math.log(seg.to.dist), e) + bump * Math.sin(Math.PI * e));
    c.tilt -= 8 * Math.sin(Math.PI * e);
  } else c = mix(seg.from, seg.to, seg.ease === 'linear' ? softLinear(k) : ease(k));
  // never a frozen frame: a slow sway, scaled to distance
  const s = Math.sin(t * 0.19) * 0.6 + Math.sin(t * 0.077 + 1.1) * 0.4;
  return { ...c, heading: c.heading + s * 2.2, x: c.x + Math.sin(t * 0.13) * c.dist * 0.012, z: c.z + Math.cos(t * 0.11) * c.dist * 0.01 };
}

/** Camera state -> eye and target (metres). groundY(x, z) is the drawn surface. */
export function placeCamera(c, groundY) {
  const gy = Math.max(0, groundY(c.x, c.z));
  const tilt = (c.tilt * Math.PI) / 180, hd = (c.heading * Math.PI) / 180;
  const pos = { x: c.x - Math.sin(hd) * Math.sin(tilt) * c.dist, y: gy + Math.cos(tilt) * c.dist, z: c.z + Math.cos(hd) * Math.sin(tilt) * c.dist };
  // never under the ground near the eye
  const floor = groundY(pos.x, pos.z) + 25;
  if (pos.y < floor) pos.y = floor;
  return { pos, target: { x: c.x, y: gy, z: c.z } };
}
