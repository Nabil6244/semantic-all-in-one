// The film's clock: when each era's time skip runs and how long its view holds, the year and population at any t, the
// text on screen, and the camera path. Pure: the same story and city give the same film, frame by frame.
//
// Every era after the first opens with a time skip (the year counts up, the city grows or shrinks, the camera rises a
// little to show it), then holds on the new city while the camera keeps moving and the captions read.

import { yearLabel, styleForYear } from './story.mjs';
import { eventFocus } from './fx.mjs';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const ease = (k) => { k = clamp(k, 0, 1); return k * k * k * (k * (6 * k - 15) + 10); };
const smooth = (k) => { k = clamp(k, 0, 1); return k * k * (3 - 2 * k); };
const lerp = (a, b, k) => a + (b - a) * k;
const angLerp = (a, b, k) => a + ((((b - a) % 360) + 540) % 360 - 180) * k;

export const INTRO = 4.5, OUTRO = 7, TITLE_HOLD = 3.4, CAPTION_WPS = 2.7, EVENT_HOLD = 5.5, BEAT_HOLD = 4.2;
// the clock keeps running through a stop (as in the reference films the year never freezes, it slows down): a stop with
// text or a new building drifts at most HOLD_RATE years a second and a third of the way to what comes next; a filler
// stop half of the way. Only the film's climax freezes the year.
export const HOLD_RATE = 1.6, CLIMAX_BEAT = 8.5;
/** Easing of a key segment: linear while a stop drifts, a soft ease (never at rest) through a skip. */
const keyEase = (a, u) => (a.lin ? clamp(u, 0, 1) : 0.45 * clamp(u, 0, 1) + 0.55 * ease(u));
// mostly high, slanted views over the whole town; down among the roofs only now and then
// close shots always circle a landmark with the city round it ('revisit'), never plain houses
const SHOT_CYCLE = ['orbit', 'push', 'revisit', 'flyover', 'pullback', 'revisit', 'orbit', 'push', 'revisit', 'flyover'];
const MIN_DIST = 90, MAX_DIST = 7000, WIDE_MIN = 420, OPENING_MIN = 1150;

/**
 * Steady growth between far-apart eras: the reference films never jump 80 years in one cut, the year stops every couple
 * of decades on a new view of the bigger town. Adds `beat` eras (same name, flag and style as the era before, no text,
 * population on the geometric path) every ~`every` years, at most `max` per gap.
 */
export function addBeats(eras, { every = 25, max = 4 } = {}) {
  const out = [];
  eras.forEach((e, i) => {
    const p = eras[i - 1];
    if (p && !e.beat && Number.isFinite(p.year) && Number.isFinite(e.year)) {
      const dy = e.year - p.year, k = Math.min(max, Math.floor(dy / every) - (dy % every < every * 0.4 ? 1 : 0));
      for (let j = 1; j <= k; j++) {
        const f = j / (k + 1), year = Math.round(p.year + dy * f);
        const population = p.population > 0 && e.population > 0 ? Math.round(Math.exp(Math.log(p.population) + (Math.log(e.population) - Math.log(p.population)) * f)) : Math.round(p.population + (e.population - p.population) * f);
        out.push({ line: p.line, year, name: p.name, flag: p.flag, population, caption: '', title: '', kicker: '', style: p.style, shot: null, focus: null, focusId: null, hold: BEAT_HOLD, extra: {}, beat: true });
      }
    }
    out.push(e);
  });
  return out;
}

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
export function buildTimeline(story, city, opts = {}) {
  const eras = story.eras;
  const adPrefix = eras[0].year < 0 && eras.some((e) => e.year > 0 && e.year < 1000);
  const keys = [], titles = [], captions = [], badges = [], holds = [], stops = [];
  let t = INTRO, prevEnd = { year: eras[0].year, pop: eras[0].population };
  // the opening: the city's name over its first view
  const first = eras[0], last = eras[eras.length - 1];
  titles.push({ t0: 0.6, t1: INTRO + 1.2, title: (story.plan.city || story.plan.title || '').toUpperCase(),
    kicker: `${yearLabel(first.year, { adPrefix: false })} – ${yearLabel(last.year, { adPrefix })}`, big: true });
  keys.push({ t: 0, year: first.year, pop: first.population });
  // an event between two eras stops the clock in its own year: the camera flies to it and the fire, siege or quake plays
  // out on screen with its caption. Any other event's caption joins the first era at or after it.
  const evCap = new Map(), mid = new Map();
  story.events.forEach((ev, j) => {
    const i = eras.findIndex((e) => e.year >= ev.year);
    if (i > 0 && ev.year > eras[i - 1].year && ev.year < eras[i].year) { mid.set(i, [...(mid.get(i) || []), j]); return; }
    if (!ev.caption) return;
    const host = eras[i] || last;
    evCap.set(host, [...(evCap.get(host) || []), ev.caption]);
  });
  eras.forEach((e, i) => {
    let tr0 = t, tr1 = t;
    if (i > 0) {
      const p = eras[i - 1];
      let from = { year: prevEnd.year, pop: prevEnd.pop };
      for (const j of (mid.get(i) || []).sort((a, b) => story.events[a].year - story.events[b].year)) {
        const ev = story.events[j], k = (ev.year - p.year) / (e.year - p.year);
        const pop = p.population > 0 && e.population > 0 ? Math.exp(lerp(Math.log(p.population), Math.log(e.population), k)) : lerp(p.population, e.population, k);
        const s0 = t;
        if (ev.year <= from.year) continue;   // the clock already drifted past it
        keys.push({ t, ...from }); t += skipSeconds(ev.year - from.year); keys.push({ t, year: ev.year, pop });
        const climax = !!ev.extra?.climax, caps = climax && Array.isArray(ev.extra?.captions) ? ev.extra.captions : ev.caption ? [ev.caption] : [];
        // the climax is a chain of shots (the city, the fleet, the camp and guns, the walls, the fall, the city after),
        // each about CLIMAX_BEAT s, with the year frozen; any other event lets the clock creep on by up to a year
        const hold = climax ? Math.max(6 * CLIMAX_BEAT, caps.reduce((s2, x) => s2 + readSeconds(x), 0) + 4) : Math.max(EVENT_HOLD, readSeconds(ev.caption) + 2);
        const drift = climax ? 0 : Math.min(1, Math.max(0, e.year - ev.year - 1));
        stops.push({ era: i, ev: j, s0, t0: t, t1: t + hold, year: ev.year, pop, climax });
        if (climax) {
          let c0 = t + 0.8; const each = (hold - 1.6) / Math.max(1, caps.length);
          for (const x of caps) { captions.push({ t0: c0, t1: c0 + Math.min(each - 0.4, readSeconds(x) + 2.5), text: x }); c0 += each; }
          // the city changes hands during the fall: the next era's flag goes up two thirds of the way in
          badges.push({ t: t + hold * 0.64, name: e.name || '', flag: e.flag || '' });
        } else {
          let c0 = t + 0.6;
          for (const x of caps) { captions.push({ t0: c0, t1: t + hold - 0.3, text: x }); c0 = t + hold; }
        }
        keys.push({ t, year: ev.year, pop, lin: true }); t += hold;
        from = { year: ev.year + drift, pop };
      }
      tr0 = t; tr1 = t + Math.max(skipSeconds(e.year - from.year), opts.minSkip?.[i] ?? 0);   // long enough for the camera's flight
      keys.push({ t: tr0, ...from });
      keys.push({ t: tr1, year: e.year, pop: e.population });
    }
    const texts = [...(evCap.get(e) || []), ...(e.caption ? [e.caption] : [])];
    const titleT = e.title ? TITLE_HOLD : 0;
    // a stop where a landmark arrives holds a little longer, so its name can show after the title card
    const prevY = i ? eras[i - 1].year : -Infinity;
    const lmHere = (story.landmarks || []).some((l) => l.lon != null && l.year != null && l.year > prevY && l.year <= e.year);
    const trHere = (story.landmarks || []).some((l) => trackable(l) && l.year != null && l.year > prevY && l.year <= e.year);   // a wall built along its length needs time
    // a stop where several landmarks are begun tours them all, one shot each, so every one is seen being built
    const arrivals = tourList(story, city, prevY, e.year);
    const tt = tourTimes(arrivals, city), tourT = [...tt.base, ...tt.fl].reduce((x, y) => x + y, 0);   // unhurried: a glide per landmark, calm flights
    const need = Math.max(1.0 + titleT + texts.reduce((s, x) => s + readSeconds(x), 0) + 0.8 + (lmHere ? 2.5 : 0), trHere ? 8 : 0, i > 0 ? tourT : 0);
    const hold = e.beat ? Math.max(BEAT_HOLD, need) : Math.max(e.hold ?? 0, need, 5.5);
    const h0 = tr1, h1 = tr1 + hold;
    badges.push({ t: i === 0 ? 0 : (tr0 + tr1) / 2, name: e.name || '', flag: e.flag || '' });
    if (e.title) titles.push({ t0: h0 + 0.2, t1: h0 + 0.2 + TITLE_HOLD, title: e.title.toUpperCase(), kicker: e.kicker || '' });
    let c0 = h0 + 0.6 + titleT;
    const each = texts.length ? (h1 - 0.4 - c0) / texts.reduce((s, x) => s + readSeconds(x), 0) : 0;
    for (const x of texts) { const d = readSeconds(x) * each; captions.push({ t0: c0, t1: c0 + d, text: x }); c0 += d; }
    holds.push({ era: i, tr0, tr1, h0, h1, year: e.year, pop: e.population, style: e.style || styleForYear(e.year) });
    // the clock runs on through the stop towards what comes next (the next era or an event in between)
    const nx = eras[i + 1];
    if (nx) {
      const evNext = story.events.filter((ev) => ev.year > e.year && ev.year < nx.year).map((ev) => ev.year);
      const toY = Math.min(nx.year, ...evNext), gap = toY - e.year;
      const drift = gap <= 1 ? 0 : e.beat ? gap * 0.5 : Math.min(gap / 3, hold * HOLD_RATE);
      const k = drift / Math.max(1e-9, nx.year - e.year);
      const pop = e.population > 0 && nx.population > 0 ? Math.exp(lerp(Math.log(e.population), Math.log(nx.population), k)) : lerp(e.population, nx.population, k);
      keys.push({ t: h0, year: e.year, pop: e.population, lin: true });
      prevEnd = { year: e.year + drift, pop };
      keys.push({ t: h1, ...prevEnd });
    }
    t = h1;
  });
  const duration = t + OUTRO;
  keys.push({ t: duration, year: last.year, pop: last.population });
  const tl = { duration, keys, titles, captions, badges, holds, stops, adPrefix, styles: holds.map((h) => h.style) };
  tl.camera = cameraPath(story, city, tl);
  // second pass: a flight between eras that needs more time than its skip (far, or a big turn or height change) gets it
  if (!opts.minSkip) {
    const minSkip = {}; let more = false;
    for (const sg of tl.camera) {
      if (sg.type !== 'fly' || sg.hold == null) continue;
      const a = sg.from, b = sg.to, gd = Math.sqrt(a.dist * b.dist), travel = Math.hypot(b.x - a.x, b.z - a.z);
      const dh = Math.abs(((((b.heading - a.heading) % 360) + 540) % 360) - 180), dz = Math.abs(Math.log(b.dist / a.dist));
      const need = Math.min(7, Math.max(travel / (0.2 * gd), dz / 0.35, dh / 6));
      if (need > sg.t1 - sg.t0 + 0.3) { minSkip[sg.hold] = need; more = true; }
    }
    if (more) return buildTimeline(story, city, { ...opts, minSkip });
  }
  tl.landmarkTimes = Object.fromEntries(story.landmarks.map((l) => {
    const tIn = l.year == null || l.year <= first.year ? -1e9 : timeOfYear(tl, l.year);
    // the era's hero building is still a construction site when the camera arrives, and is finished while it circles
    // only the first stop after its year builds it on screen; a later hero shot shows it finished
    // built on screen in its own shot of its era's landmark tour
    const tOut = l.until == null ? 1e9 : timeOfYear(tl, l.until);
    const part = holds.flatMap((h) => h.tour || []).find((p) => p.id === l.id);
    // the front keeps pace with the camera: it reaches the shot's last ~2.2 km at the shot's end, the rest follows
    if (part && part.track) { const L = pathLength(l, city), sc = L / Math.min(L, TRACK_MAX); return [l.id, { tIn: part.t0 + 0.2, tDone: part.t0 + 0.2 + (part.t1 - 0.6 - part.t0) * sc, tOut }]; }
    if (part) { const td = part.t0 + 0.55 * (part.t1 - part.t0); return [l.id, { tIn: Math.max(Math.min(tIn, td - 2.2), td - 8, part.t0 - 2.5), tDone: td, tOut }]; }
    const host = null;
    const tDone = host ? Math.max(tIn + 2.2, host.h0 + 0.5 * (host.h1 - host.h0)) : tIn + 2.2;
    // never a building site for longer than ~8 s: one finished in a later era breaks ground just before that era's view
    return [l.id, { tIn: Math.max(tIn, tDone - 8), tDone, tOut: l.until == null ? 1e9 : timeOfYear(tl, l.until) }];
  }));
  // the hero building's name on screen while the camera circles it (after the era's title card, if there is one)
  tl.labels = [];
  for (const h of holds) for (const pt of h.tour || []) {
    const l = story.landmarks.find((x) => x.id === pt.id);
    if (!l || l.extra?.label === false) continue;
    const tt = tl.titles.find((x) => x.t1 > pt.t0 && x.t0 < pt.t1), t0 = Math.max(pt.t0 + 0.6, tt ? tt.t1 + 0.3 : 0), t1 = pt.t1 - 0.3;
    if (t1 - t0 > 1.2) tl.labels.push({ t0, t1, text: String(l.extra?.label || l.id).toUpperCase() });
  }
  // the climax's camp gets its name on screen ("OTTOMAN CAMP"), from the event's extra "camp_label"
  for (const st of stops) if (st.climax && st.campBeat >= 0 && story.events[st.ev].extra?.camp_label) {
    const bd = (st.t1 - st.t0) / st.beats, t0 = st.t0 + st.campBeat * bd + 0.8;
    tl.labels.push({ t0, t1: t0 + bd * 0.6, text: String(story.events[st.ev].extra.camp_label).toUpperCase() });
  }
  tl.eventTimes = story.events.map((ev) => timeOfYear(tl, ev.year));
  // when each event plays on screen: its own stop, or a few seconds from the moment the clock reaches it
  tl.eventWindows = story.events.map((ev, j) => {
    const st = stops.find((x) => x.ev === j);
    return st ? { t0: st.t0, t1: st.t1 } : { t0: tl.eventTimes[j], t1: tl.eventTimes[j] + 4 };
  });
  return tl;
}

/** Year and population at t: flat on holds, eased through each skip (population geometric, so growth reads evenly). */
export function stateAt(tl, t) {
  const k = tl.keys;
  let i = 0; while (i + 1 < k.length && k[i + 1].t <= t) i++;
  const a = k[i], b = k[Math.min(k.length - 1, i + 1)];
  if (b.t <= a.t || a.year === b.year && a.pop === b.pop) return { year: a.year, pop: a.pop, skip: 0 };
  const e = keyEase(a, (t - a.t) / (b.t - a.t));
  const pop = a.pop > 0 && b.pop > 0 ? Math.exp(lerp(Math.log(a.pop), Math.log(b.pop), e)) : lerp(a.pop, b.pop, e);
  return { year: lerp(a.year, b.year, e), pop, skip: a.lin ? 0 : Math.sin(Math.PI * clamp((t - a.t) / (b.t - a.t), 0, 1)) };
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
      for (let n = 0; n < 30; n++) { const m = (lo + hi) / 2; if (lerp(a.year, b.year, keyEase(a, m)) < y) lo = m; else hi = m; }
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
    label: (() => { const lb = (tl.labels || []).find((x) => t >= x.t0 && t <= x.t1); return lb ? { text: lb.text, alpha: fadeIn(lb.t0, lb.t1, 0.7) } : null; })(),
    black: Math.max(1 - smooth(t / 1.2), smooth((t - (tl.duration - 1.4)) / 1.4)),
    hudAlpha: smooth((t - INTRO + 1.0) / 1.0),
  };
}

// ------------------------------------------------------------------------------------------------ camera
// State: { x, z (metres, focus on the ground), dist (m from focus), heading (deg, 0 = looking north), tilt (deg from
// straight down) }.

function shotStates(kind, f, R, heading) {
  const H = heading, rad = (H * Math.PI) / 180, fx = Math.sin(rad), fz = -Math.cos(rad);
  const d = (v) => clamp(v, WIDE_MIN, MAX_DIST);   // a wide view always shows the town as a town
  switch (kind) {
    // the opening: the young town small in its landscape, the coast or river beyond it
    case 'establishing': return [{ ...f, dist: d(Math.max(R * 2.6, OPENING_MIN)), tilt: 60, heading: H }, { ...f, dist: d(Math.max(R * 2.1, OPENING_MIN * 0.8)), tilt: 64, heading: H + 14 }];
    case 'push': return [{ ...f, dist: d(R * 1.6), tilt: 61, heading: H }, { ...f, dist: d(R * 0.9), tilt: 65, heading: H + 10 }];
    case 'pullback': return [{ ...f, dist: d(R * 0.75), tilt: 65, heading: H }, { ...f, dist: d(R * 1.6), tilt: 60, heading: H - 10 }];
    case 'landmark': {   // a low, close orbit round a new building (R is its size here): the hero shot
      // a big or tall one (a 270 m tower, a hippodrome) is seen from further back and more level, top in frame
      const big = R > 150, D = clamp(R * (big ? 3.2 : 2.8), 330, big ? 1300 : 680), T0 = big ? 58 : 63;
      return [{ ...f, dist: D * 1.25, tilt: T0, heading: H }, { ...f, dist: D, tilt: T0 + 4, heading: H + 22 }];   // a slow arc, the building held in frame
    }
    case 'event': {   // the fire, the siege: close enough to see the smoke and the camp, wide enough to see the city
      const D = clamp(R * 1.9, 240, 1500);
      return [{ ...f, dist: D * 1.15, tilt: 60, heading: H }, { ...f, dist: D * 0.85, tilt: 64, heading: H + 26 }];
    }
    case 'street': {   // down among the roofs, drifting along
      const D = clamp(R * 0.24, 260, 420);   // close, but the town still reads as a town around it
      return [{ x: f.x - fx * D * 0.5, z: f.z - fz * D * 0.5, dist: D, tilt: 63, heading: H }, { x: f.x + fx * D * 0.5, z: f.z + fz * D * 0.5, dist: D * 0.92, tilt: 64, heading: H + 12 }];
    }
    case 'flyover': return [
      { x: f.x - fx * R * 0.45, z: f.z - fz * R * 0.45, dist: d(R * 0.75), tilt: 65, heading: H },
      { x: f.x + fx * R * 0.45, z: f.z + fz * R * 0.45, dist: d(R * 0.7), tilt: 65, heading: H + 6 }];
    case 'low_track': {
      const sx = -fz, sz = fx, D = clamp(R * 0.4, 280, 520);
      return [{ x: f.x - sx * D * 0.6, z: f.z - sz * D * 0.6, dist: D, tilt: 66, heading: H }, { x: f.x + sx * D * 0.6, z: f.z + sz * D * 0.6, dist: D, tilt: 64, heading: H + 4 }];
    }
    default: return [{ ...f, dist: d(R * 1.15), tilt: 61, heading: H }, { ...f, dist: d(R * 1.0), tilt: 63, heading: H + 30 }];   // orbit
  }
}

/** The nearest point (x, z) on a wall standing in `year` to `at`, or null (no wall in the story). */
export function nearestWall(story, city, at, year) {
  let best = null, bd = Infinity;
  for (const l of story.landmarks || []) {
    if (l.kind !== 'wall' || !Array.isArray(l.extra?.path)) continue;
    if ((l.year != null && l.year > year) || (l.until != null && l.until <= year)) continue;
    const pts = l.extra.path.map(([lon, lat]) => city.toXZ(lon, lat));
    for (let i = 0; i + 1 < pts.length; i++) {
      const a = pts[i], b = pts[i + 1], vx = b.x - a.x, vz = b.z - a.z, L2 = vx * vx + vz * vz || 1;
      const k = clamp(((at.x - a.x) * vx + (at.z - a.z) * vz) / L2, 0, 1), x = a.x + vx * k, z = a.z + vz * k, d = Math.hypot(x - at.x, z - at.z);
      if (d < bd) { bd = d; best = { x, z }; }
    }
  }
  return best && bd < 3000 ? best : null;
}

const TRACK_KINDS = new Set(['wall', 'aqueduct', 'avenue']);
const trackable = (l) => TRACK_KINDS.has(l.kind) && Array.isArray(l.extra?.path) && l.extra.path.length > 1;
const pathXZ = (l, city) => l.extra.path.map(([lon, lat]) => city.toXZ(lon, lat));
function pathLength(l, city) { const P = pathXZ(l, city); let L = 0; for (let i = 1; i < P.length; i++) L += Math.hypot(P[i].x - P[i - 1].x, P[i].z - P[i - 1].z); return L; }

/** A wall, aqueduct or avenue going up: the camera travels alongside it, start to end, as it is built. */
export const TRACK_MAX = 520;
/** A point `d` metres along a path (x, z points). */
function along(P, d) {
  for (let i = 1; i < P.length; i++) {
    const L = Math.hypot(P[i].x - P[i - 1].x, P[i].z - P[i - 1].z);
    if (d <= L || i === P.length - 1) { const k = clamp(d / Math.max(1e-6, L), 0, 1); return { x: P[i - 1].x + (P[i].x - P[i - 1].x) * k, z: P[i - 1].z + (P[i].z - P[i - 1].z) * k }; }
    d -= L;
  }
  return P[P.length - 1];
}
function trackStates(l, city, cur = null) {
  // the camera rides with the building front over the first ~2.2 km (a long road or wall finishes beyond, off the shot)
  const P = pathXZ(l, city), L = pathLength(l, city), Lt = Math.min(L, TRACK_MAX);
  const a = along(P, Lt * 0.06), b = along(P, Lt * 0.94);
  const dir = (Math.atan2(b.x - a.x, -(b.z - a.z)) * 180) / Math.PI, D = clamp(Lt * 0.65, 480, 900);
  // looking across it at a slant, from whichever side keeps the camera facing nearly the way it already faces
  const opts = [dir + 62, dir - 118], near = (x) => Math.abs(((((x - (cur ?? x)) % 360) + 540) % 360) - 180);
  const H = near(opts[0]) <= near(opts[1]) ? opts[0] : opts[1];
  return [{ ...a, dist: D, tilt: 62, heading: H }, { ...b, dist: D * 0.95, tilt: 63, heading: H + 4 }];
}

/** The climax as a chain of shots: the city wide, the fleet, the camp and guns, along the walls, the walls up close as
 *  the city falls, then the city after. Beats without what they need (no fleet, no wall) are left out. */
function climaxBeats(story, city, tl, st, ev, at, wp, camp) {
  const ext = city.extent(st.year, st.pop, tl.holds[Math.max(0, st.era - 1)]?.style), H0 = camp[0].heading;
  const beats = [[{ x: ext.x, z: ext.z, dist: clamp(ext.r * 2.6, 900, MAX_DIST), tilt: 50, heading: H0 - 30 }, { x: ext.x, z: ext.z, dist: clamp(ext.r * 2.2, 800, MAX_DIST), tilt: 53, heading: H0 - 5 }]];
  const fl = city.eventFleet?.[st.ev];
  if (fl) beats.push([{ x: fl.x, z: fl.z, dist: 700, tilt: 58, heading: H0 + 40 }, { x: fl.x, z: fl.z, dist: 520, tilt: 62, heading: H0 + 70 }]);
  beats.push(camp);
  if (wp) {
    beats.push([{ x: wp.x, z: wp.z, dist: 520, tilt: 60, heading: H0 + 35 }, { x: wp.x + (at.z - wp.z) * 0.6, z: wp.z - (at.x - wp.x) * 0.6, dist: 480, tilt: 62, heading: H0 + 55 }]);
    beats.push([{ x: wp.x, z: wp.z, dist: 330, tilt: 63, heading: H0 - 20 }, { x: wp.x, z: wp.z, dist: 280, tilt: 66, heading: H0 + 15 }]);
  }
  const big = (story.landmarks || []).filter((l) => l.lon != null && city.landmarkXZ?.[l.id] && (l.year ?? -1e9) <= st.year && (l.until ?? Infinity) > st.year)
    .sort((a, b) => (b.extra?.size ?? 60) - (a.extra?.size ?? 60))[0];
  const c = big ? city.landmarkXZ[big.id] : { x: ext.x, z: ext.z };
  beats.push([{ ...c, dist: 420, tilt: 60, heading: H0 + 120 }, { ...c, dist: clamp(ext.r * 2.4, 900, MAX_DIST), tilt: 50, heading: H0 + 150 }]);
  return beats;
}

/** Keyframes for one smooth flight through every shot (no stopping and jumping between them). */
/** The reference films' calm: within a shot the camera turns at most ~1.4 deg/s, glides at most ~7% of its distance a
 *  second (a tracking shot ~16%) and changes height slowly. A shot asking for more is shortened towards its start. */
export const MAX_TURN = 1.4, MAX_GLIDE = 0.07, MAX_TRACK = 0.09, MAX_ZOOM = 0.06;
function calmShots(segs) {
  for (const sg of segs) {
    if (sg.type !== 'move') continue;
    const dt = Math.max(0.3, sg.t1 - sg.t0), a = sg.from, b = sg.to, d = Math.sqrt(a.dist * b.dist);
    const dh = Math.abs(((((b.heading - a.heading) % 360) + 540) % 360) - 180), glide = Math.hypot(b.x - a.x, b.z - a.z) / d, zoom = Math.abs(Math.log(b.dist / a.dist));
    const k = Math.min(1, (MAX_TURN * dt) / Math.max(1e-6, dh), ((sg.track ? MAX_TRACK : MAX_GLIDE) * dt) / Math.max(1e-6, glide), (MAX_ZOOM * dt) / Math.max(1e-6, zoom));
    if (k < 1) Object.assign(sg.to, mix(a, b, k));   // in place: the flight that follows starts from here too
  }
  // flights: never a whip-pan or a plunge. If the next shot would need the camera to turn faster than ~5 deg/s or change
  // height faster than ~30%/s, that whole shot is turned / set back towards where the camera already is.
  const FLY_TURN = 5, FLY_ZOOM = 0.3;
  segs.forEach((sg, i) => {
    if (sg.type !== 'fly') return;
    const dt = Math.max(0.5, sg.t1 - sg.t0), a = sg.from, b = sg.to;
    const dh = ((((b.heading - a.heading) % 360) + 540) % 360) - 180, okH = FLY_TURN * dt;
    const nxt = segs.slice(i + 1).find((x) => x.type === 'move' && x.from === b);
    if (Math.abs(dh) > okH) {
      const shift = dh - Math.sign(dh) * okH;
      b.heading -= shift; if (nxt) nxt.to.heading -= shift;
    }
    const dz = Math.log(b.dist / a.dist), okZ = FLY_ZOOM * dt;
    if (Math.abs(dz) > okZ) {
      const f = Math.exp(Math.sign(dz) * okZ) * a.dist / b.dist;
      b.dist *= f; if (nxt) nxt.to.dist *= f;
    }
  });
}

function splineKeys(segs) {
  const K = [];
  // a shot is a straight, steady glide (its keys carry the shot's own velocity); only flights between shots curve
  const put = (t, st, v = null) => {
    let keep = null;
    while (K.length && K[K.length - 1].t >= t - 1e-6) keep = K.pop().v || keep;
    K.push({ t, x: st.x, z: st.z, ld: Math.log(st.dist), tilt: st.tilt, hd: st.heading, v: v || keep });
  };
  for (const sg of segs) {
    let v = null;
    if (sg.type === 'move' && sg.t1 - sg.t0 > 0.3) {
      const dt = sg.t1 - sg.t0, dh = ((((sg.to.heading - sg.from.heading) % 360) + 540) % 360) - 180;
      v = { x: (sg.to.x - sg.from.x) / dt, z: (sg.to.z - sg.from.z) / dt, ld: (Math.log(sg.to.dist) - Math.log(sg.from.dist)) / dt, tilt: (sg.to.tilt - sg.from.tilt) / dt, hd: dh / dt };
    }
    put(sg.t0, sg.from, v);
    if (sg.type === 'fly' && sg.t1 - sg.t0 > 0.6) {   // the middle of a flight: a little higher and leaning to the town
      const m = mix(sg.from, sg.to, 0.5), travel = Math.hypot(sg.to.x - sg.from.x, sg.to.z - sg.from.z), dt = sg.t1 - sg.t0;
      // high enough that the ground never races past: on screen a flight moves at most ~0.35 of the view a second
      // a long flight cranes up (it never races low over the roofs); a short one stays near the shots' own height
      const up = Math.log(Math.max(Math.min(sg.peak || m.dist, Math.max(sg.from.dist, sg.to.dist) * 1.35), Math.min(MAX_DIST, travel / Math.max(0.5, dt) / 0.22)));
      // (no detour towards the town: the shots themselves now aim where the city grows)
      put((sg.t0 + sg.t1) / 2, { ...m, dist: Math.exp(Math.max(Math.log(m.dist), up)), tilt: m.tilt - 6 });
    }
    put(sg.t1, sg.to, v);
  }
  for (let i = 1; i < K.length; i++) { let d = K[i].hd - K[i - 1].hd; d = ((d % 360) + 540) % 360 - 180; K[i].hd = K[i - 1].hd + d; }
  return K;
}

function hermite(K, t, f) {
  if (t <= K[0].t) return K[0][f];
  const n = K.length; if (t >= K[n - 1].t) return K[n - 1][f];
  let i = 0; while (K[i + 1].t < t) i++;
  const a = K[i], b = K[i + 1], h = b.t - a.t, u = (t - a.t) / h;
  const slope = (p, q) => (q[f] - p[f]) / Math.max(1e-6, q.t - p.t);
  const tan = (j) => {
    if (K[j].v) return K[j].v[f];
    if (j <= 0 || j >= n - 1) return 0;
    const s0 = slope(K[j - 1], K[j]), s1 = slope(K[j], K[j + 1]);
    return s0 * s1 <= 0 ? 0 : (s0 + s1) / 2;   // no overshoot where the motion turns back
  };
  const m0 = tan(i) * h, m1 = tan(i + 1) * h, u2 = u * u, u3 = u2 * u;
  return (2 * u3 - 3 * u2 + 1) * a[f] + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * b[f] + (u3 - u2) * m1;
}

/** Landmarks begun in (prevYear, year] that get a shot of their own: buildings with a place, and walls, aqueducts and
 *  avenues; biggest first. A row with "label": false (a minor road) is built without its own shot. */
function tourList(story, city, prevYear, year) {
  const ok = (l) => l.year != null && l.year > prevYear && l.year <= year && l.extra?.label !== false && ((city.landmarkXZ?.[l.id] && l.lon != null) || trackable(l));
  const size = (l) => (trackable(l) ? Math.min(400, pathLength(l, city)) : l.extra?.size ?? 60);
  const list = (story.landmarks || []).filter(ok).sort((a, b) => size(b) - size(a));
  // biggest first, then always the nearest one next: the camera never zig-zags across the city
  const pos = (l, end = false) => (trackable(l) ? (end ? pathXZ(l, city).at(-1) : pathXZ(l, city)[0]) : city.landmarkXZ[l.id]);
  const out = list.length ? [list.shift()] : [];
  while (list.length) {
    const p = pos(out[out.length - 1], true); let bi = 0, bd = Infinity;
    list.forEach((l, k) => { const q = pos(l), d = Math.hypot(q.x - p.x, q.z - p.z); if (d < bd) { bd = d; bi = k; } });
    out.push(list.splice(bi, 1)[0]);
  }
  return out;
}
/** Seconds for each tour shot and for the flight into it: a glide per landmark, a flight long enough to stay calm. */
function tourTimes(list, city) {
  const pos = (l, end = false) => (trackable(l) ? (end ? pathXZ(l, city).at(-1) : pathXZ(l, city)[0]) : city.landmarkXZ[l.id]);
  const base = list.map((l) => (trackable(l) ? 9 : 6));
  const fl = list.map((l, k) => {
    if (!k) return 0;
    const p = pos(list[k - 1], true), q = pos(l), d = Math.hypot(q.x - p.x, q.z - p.z);
    return clamp(d / (0.15 * 650), 2.5, 9);
  });
  return { base, fl };
}

export function cameraPath(story, city, tl) {
  const segs = [];
  let heading = story.plan.heading ?? 20, prevKind = null, prevEnd = null, cyc = 0;
  const waiting = [], shown = new Set(), lastSeen = new Map();
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
    const heroOk = (l) => l.year != null && l.year > prevYear && l.year <= h.year && ((city.landmarkXZ?.[l.id] && l.lon != null) || trackable(l));
    const heroSize = (l) => (trackable(l) ? Math.min(400, pathLength(l, city)) : l.extra?.size ?? 60);
    // every landmark begun in this era gets its own shot, biggest first (a tour), so none is built off-screen
    const tour = !e.shot && !e.focus && !e.focusId && i > 0 ? tourList(story, city, prevYear, h.year) : [];
    const hero = tour[0] || null;
    let trackAB = null;
    if (hero && trackable(hero)) { kind = 'track'; trackAB = trackStates(hero, city, heading); h.fresh = hero.id; h.track = true; shown.add(hero.id); }
    else if (hero) { kind = 'landmark'; f = city.landmarkXZ[hero.id]; R = hero.extra?.size ?? 60; h.fresh = hero.id; shown.add(hero.id); lastSeen.set(hero.id, i); }
    if (!kind) { do { kind = SHOT_CYCLE[cyc++ % SHOT_CYCLE.length]; } while (kind === prevKind); }
    if (kind === 'revisit') {   // a standing landmark not seen for a while, the camera circling it
      const stand = (story.landmarks || []).filter((l) => l.lon != null && city.landmarkXZ?.[l.id] && (l.year ?? -1e9) <= h.year && (l.until ?? Infinity) > h.year)
        .sort((a, b) => (lastSeen.get(a.id) ?? -1) - (lastSeen.get(b.id) ?? -1) || (b.extra?.size ?? 60) - (a.extra?.size ?? 60));
      if (stand.length) { const l = stand[0]; lastSeen.set(l.id, i); f = city.landmarkXZ[l.id]; R = Math.max(80, l.extra?.size ?? 60) * 1.3; kind = 'landmark'; }
      else kind = 'orbit';
    }
    // a wide view is aimed where the city is growing now (the newest houses), not at a fixed centre
    if (!hero && !e.focus && !e.focusId && i > 0 && city.front) {
      const fr = city.front(h.year, h.pop, h.style, tl.holds[i + 1]?.pop);
      if (fr) f = { x: lerp(f.x, fr.x, 0.6), z: lerp(f.z, fr.z, 0.6) };
    }
    let [a, b] = trackAB || shotStates(kind, f, R, heading);
    if (i === 0) {   // the opening drifts in over the title
      const pre = { ...a, dist: clamp(a.dist * 1.35, MIN_DIST, MAX_DIST), tilt: a.tilt - 6, heading: a.heading - 10 };
      segs.push({ type: 'move', t0: 0, t1: h.h0, from: pre, to: a, ease: 'linear' });
    } else {
      // an event on the way: fly to it, watch it, then go on
      for (const st of (tl.stops || []).filter((x) => x.era === i)) {
        const ev = story.events[st.ev], at = city.toXZ(ev.lon, ev.lat);
        let ef = eventFocus({ ...at, kind: ev.kind, r: ev.radius || 600 }), er = (ev.radius || 600) * (ev.kind === 'siege' ? 0.75 : 1);
        // a siege is seen from behind the camp, looking over the tents and guns at the walls
        let sh = ev.kind === 'siege' ? (Math.atan2(-at.x, at.z) * 180) / Math.PI - 13 : heading;
        const wp = ev.kind === 'siege' ? nearestWall(story, city, at, ev.year) : null;
        if (wp) {   // the walls under attack in the same frame as the camp: aim between them, wide enough for both
          const dx = wp.x - at.x, dz = wp.z - at.z, d = Math.hypot(dx, dz);
          ef = { x: at.x + dx * 0.45, z: at.z + dz * 0.45 }; er = Math.max(er, d * 0.55);
          sh = (Math.atan2(dx, -dz) * 180) / Math.PI - 10;
        }
        const [ea, eb] = shotStates('event', ef, er, sh);
        const camp0 = [ea, eb], beats = st.climax ? climaxBeats(story, city, tl, st, ev, at, wp, camp0) : [camp0];
        const peak = clamp(Math.max(prevEnd.dist, beats[0][0].dist, Math.hypot(beats[0][0].x - prevEnd.x, beats[0][0].z - prevEnd.z) * 1.1), MIN_DIST, MAX_DIST);
        segs.push({ type: 'fly', t0: st.s0, t1: st.t0, from: prevEnd, to: beats[0][0], peak });
        // each beat: a move of three quarters of its time, then a short flight on to the next beat
        const bd = (st.t1 - st.t0) / beats.length;
        beats.forEach(([ba, bb], k) => {
          const t0 = st.t0 + k * bd, last = k === beats.length - 1, t1 = last ? st.t1 : t0 + bd * 0.74;
          segs.push({ type: 'move', t0, t1, from: ba, to: bb, ease: 'linear' });
          if (!last) segs.push({ type: 'fly', t0: t1, t1: t0 + bd, from: bb, to: beats[k + 1][0], peak: Math.max(bb.dist, beats[k + 1][0].dist) * 1.15 });
        });
        if (st.climax) { st.beats = beats.length; st.campBeat = beats.indexOf(camp0); }
        prevEnd = beats[beats.length - 1][1]; heading = prevEnd.heading; prevKind = 'event';
        if (!trackAB) [a, b] = shotStates(kind, f, R, heading);
      }
      // the skip: rise to see the whole city change, then settle into the new view
      const travel = Math.hypot(a.x - prevEnd.x, a.z - prevEnd.z);
      const peak = clamp(Math.max(prevEnd.dist, a.dist, travel * 1.1, ext.r * 1.6), MIN_DIST, MAX_DIST);
      // on the way the view leans towards the town itself, so a long flight never shows only the empty land between
      segs.push({ type: 'fly', t0: h.tr0, t1: h.tr1, from: prevEnd, to: a, peak, via: { x: ext.x, z: ext.z }, hold: i });
    }
    if (tour.length > 1) {   // the tour: each landmark in turn, a short flight between
      const { base, fl } = tourTimes(tour, city), sc = (h.h1 - h.h0) / [...base, ...fl].reduce((x, y) => x + y, 0);
      let cur = h.h0, hd = heading, prevB = null; h.tour = [];
      tour.forEach((l, k) => {
        const ab = k === 0 ? [a, b] : trackable(l) ? trackStates(l, city, hd) : shotStates('landmark', city.landmarkXZ[l.id], l.extra?.size ?? 60, hd);
        if (k > 0) { const f1 = cur + fl[k] * sc; segs.push({ type: 'fly', t0: cur, t1: f1, from: prevB, to: ab[0], peak: Math.max(ab[0].dist, prevB.dist) * 1.25 }); cur = f1; }
        const t1 = k === tour.length - 1 ? h.h1 : cur + base[k] * sc;
        segs.push({ type: 'move', t0: cur, t1, from: ab[0], to: ab[1], ease: 'linear', track: trackable(l) });
        h.tour.push({ id: l.id, t0: cur, t1, track: trackable(l) });
        shown.add(l.id); lastSeen.set(l.id, i); prevB = ab[1]; hd = ab[1].heading; cur = t1;
      });
      prevEnd = segs[segs.length - 1].to; prevKind = 'landmark'; heading = prevEnd.heading;
      return;
    }
    if (hero) h.tour = [{ id: hero.id, t0: h.h0, t1: h.h1, track: trackable(hero) }];
    segs.push({ type: 'move', t0: h.h0, t1: h.h1, from: a, to: b, ease: 'linear', track: !!trackAB });
    prevEnd = segs[segs.length - 1].to; prevKind = kind; heading = b.heading;
  });
  const end = prevEnd, last = tl.holds[tl.holds.length - 1];
  // the ending: a slow climb to a calm wide view of the whole city
  const le = city.extent(last.year, last.pop, last.style);
  segs.push({ type: 'move', t0: last.h1, t1: tl.duration, from: end, to: { x: le.x, z: le.z, dist: clamp(Math.max(le.r * 2.8, end.dist * 1.6), 1200, MAX_DIST), tilt: 58, heading: end.heading + 20 }, ease: 'linear' });
  calmShots(segs);
  segs.keys = splineKeys(segs);
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
  if (path.keys && path.keys.length > 1) {
    // no random sway: the camera holds its subject and glides with purpose (every shot already moves)
    const K = path.keys;
    return { x: hermite(K, t, 'x'), z: hermite(K, t, 'z'), dist: Math.exp(hermite(K, t, 'ld')), tilt: hermite(K, t, 'tilt'), heading: hermite(K, t, 'hd') };
  }
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
    if (seg.via) { const w = 0.65 * Math.sin(Math.PI * e); c.x += (seg.via.x - c.x) * w; c.z += (seg.via.z - c.z) * w; }
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
