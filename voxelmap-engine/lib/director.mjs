// The camera director: picks a shot for every beat from its narration, geography and place in the story, and joins the
// shots with moves that fly inside the narration's silences. Pure and deterministic.
//
// Shots held while a beat is spoken:
//   globe_spin     globe: the planet turns the place to the front while the camera closes in (the reference's opening)
//   establishing   map: a slow push down onto the region
//   pullback       map: rises away at the end of a chapter or on an outcome ("falls", "only beginning")
//   aerial_track   oblique: travels along the beat's path (extra.path) or slides across the front
//   orbit          ground: circles the set
//   low_track      ground: a low lateral dolly across a village, city, beach or airfield
//   flyover        ground: a low pass over a battlefield, trail or jungle
// Moves between beats (made by camera3d's fly): long-distance travel rises in an arc, a high-to-low descent lands on
// the next set, a hop between nearby sets stays low. A shot never repeats the previous shot type when another fits.

import { distanceKm } from './geo.mjs';
import { travelSeconds } from './camera3d.mjs';

export const SHOTS = ['globe_spin', 'establishing', 'pullback', 'aerial_track', 'orbit', 'low_track', 'flyover'];
export const RUNG = { globe: { alt: 16000 }, map: { alt: 1900 }, oblique: { alt: 420 }, ground: { alt: 0.15 } }; // ground: low over a human-scale diorama (lib/diorama.mjs)
const GROUND_ALT = { orbit: 0.16, low_track: 0.09, flyover: 0.12 }; // km above the diorama
// A battle's action sits within ~100 m of the set's centre (trench lines, firing ranks, tanks) while the diorama is ~1 km wide, and the
// camera's lon/lat is its LOOK TARGET: a 0.8 km pass spent most of its length looking at empty field. Battles get a tight pass, a lower
// camera and a shorter orbit so the fighting fills the frame the whole time.
const BATTLE_ALT = { orbit: 0.085, low_track: 0.06, flyover: 0.06 };
const BATTLE_SPAN = { flyover: 0.26, low_track: 0.2 };
// Indoor rooms are ~40 units across: the camera comes in close and slow over the cut-away walls. A landmark is framed whole: a
// slow orbit around it at a height that fits its size.
const INDOOR_ALT = { orbit: 0.075, low_track: 0.065, flyover: 0.07 };
const INDOOR_SPAN = { flyover: 0.1, low_track: 0.08 };
const LANDMARK_ALT = { orbit: 0.22, low_track: 0.19, flyover: 0.2 };
const LANDMARK_SIZE = { palace: 2.3, wall: 1.5, cathedral: 1.15, pyramid: 1.1, castle: 1.0, colosseum: 1.0, domed: 1.0, mosque: 1.0, pantheon: 0.9, temple: 0.85, arch: 0.6, column: 0.6 };   // camera height per landmark size
const OUTCOME = /\b(falls?|fell|ends?|ended|lost|defeat|beginning|over|surrender|withdraw)/i;
const hash = (s) => { let h = 2166136261; for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0; return h; };

/** Offset a lon/lat by `km` toward compass bearing `deg` (0 = north). */
export function offset(p, deg, km) {
  const r = (deg * Math.PI) / 180;
  return { lon: p.lon + (Math.sin(r) * km) / (111.32 * Math.cos((p.lat * Math.PI) / 180)), lat: p.lat + (Math.cos(r) * km) / 111.32 };
}
const bearing = (a, b) => (Math.atan2((b.lon - a.lon) * Math.cos((a.lat * Math.PI) / 180), b.lat - a.lat) * 180) / Math.PI;

/** The shot for beat i (story spec beats; `prevShot` the shot before). */
export function chooseShot(spec, i, prevShot) {
  const b = spec.beats[i];
  if (b.shot && SHOTS.includes(b.shot)) return b.shot;
  const last = i === spec.beats.length - 1, chapterLast = last || spec.beats[i + 1].chapter !== b.chapter;
  const chapterFirst = i === 0 || spec.beats[i - 1].chapter !== b.chapter;
  const text = b.sentences.join(' ');
  let pick, alts = [];
  if (b.rung === 'globe') return 'globe_spin';
  if (b.rung === 'map') { pick = (chapterLast && !chapterFirst) || last || OUTCOME.test(text) ? 'pullback' : 'establishing'; alts = ['establishing', 'pullback']; }
  else if (b.rung === 'oblique') { pick = 'aerial_track'; alts = ['aerial_track', 'establishing']; }
  else {
    const r = b.site || '';
    if (/^(hall|office)$/.test(r)) { pick = 'orbit'; alts = ['orbit', 'low_track']; }
    else if (b.landmark) { pick = 'orbit'; alts = ['orbit', 'low_track', 'flyover']; }
    else if (/battle|fortress|trail|jungle/.test(r)) { pick = hash(b.id + b.place) % 2 ? 'flyover' : 'orbit'; alts = ['flyover', 'orbit', 'low_track']; }
    else { pick = 'low_track'; alts = ['low_track', 'orbit']; }
  }
  if (pick === prevShot) pick = alts.find((x) => x !== prevShot) || pick;
  return pick;
}

export const MAX_SHOT = 11;   // seconds one framing may hold before the camera moves on to another view of the same place
/** The other framings of a beat's place, used to keep a long hold moving. */
export function altShots(b) {
  if (b.rung === 'map') return ['establishing', 'aerial_track', 'pullback'];
  if (b.rung === 'oblique') return ['aerial_track', 'establishing'];
  if (b.rung === 'ground') return /^(hall|office)$/.test(b.site || '') || b.landmark ? ['orbit', 'low_track'] : /battle|fortress|trail|jungle/.test(b.site || '') ? ['flyover', 'orbit', 'low_track'] : ['low_track', 'orbit'];
  return ['globe_spin'];
}

/** Start and end framing of a held shot. */
export function shotFrames(b, shot, seed) {
  const base = { lon: b.lon, lat: b.lat, tilt: null };
  const battle = b.rung === 'ground' && b.site === 'battle', indoor = b.rung === 'ground' && /^(hall|office)$/.test(b.site || ''), lm = b.rung === 'ground' && !indoor && !!b.landmark;
  const alt0 = b.alt ?? (b.rung === 'ground' ? (indoor ? INDOOR_ALT[shot] : lm ? LANDMARK_ALT[shot] * (LANDMARK_SIZE[b.landmark] ?? 1) : battle ? BATTLE_ALT[shot] : null) ?? GROUND_ALT[shot] ?? RUNG.ground.alt : RUNG[b.rung].alt);
  const h = b.heading ?? (b.rung === 'ground' ? (seed % 8) * 45 + 10 : 0);
  if (shot === 'globe_spin') return { start: { ...base, lon: b.lon - 75, lat: b.lat * 0.55, alt: alt0 * 1.2, heading: 0 }, end: { ...base, alt: alt0, heading: 0 }, ease: 'inout' };
  if (shot === 'establishing') return { start: { ...base, alt: alt0 * 1.18, heading: h - 3 }, end: { ...base, alt: alt0, heading: h + 3 }, ease: 'inout' };
  if (shot === 'pullback') return { start: { ...base, alt: alt0, heading: h }, end: { ...base, alt: alt0 * 1.7, heading: h + 5 }, ease: 'inout' };
  if (shot === 'orbit') return { start: { ...base, alt: alt0, heading: h }, end: { ...base, alt: alt0 * 1.05, heading: h + 28 }, ease: 'linear' };
  if (shot === 'aerial_track') {
    if (b.path && b.path.length >= 2) {
      const a = { lon: b.path[0][0], lat: b.path[0][1] }, z = { lon: b.path.at(-1)[0], lat: b.path.at(-1)[1] }, hd = b.heading ?? bearing(a, z);
      return { start: { ...a, alt: alt0, heading: hd, tilt: null }, end: { ...z, alt: alt0, heading: hd, tilt: null }, ease: 'linear' };
    }
    const span = alt0 * 0.35;
    return { start: { ...offset(base, h - 90, span / 2), alt: alt0, heading: h, tilt: null }, end: { ...offset(base, h + 90, span / 2), alt: alt0, heading: h, tilt: null }, ease: 'linear' };
  }
  if (shot === 'flyover') {
    const span = indoor ? INDOOR_SPAN.flyover : battle ? BATTLE_SPAN.flyover : lm ? 0.3 : 0.8; // km: a pass from one side of the set to the other (battle: only its action)
    return { start: { ...offset(base, h + 180, span / 2), alt: alt0, heading: h, tilt: 52 }, end: { ...offset(base, h, span / 2), alt: alt0 * 1.12, heading: h + 4, tilt: 50 }, ease: 'linear' };
  }
  const span = indoor ? INDOOR_SPAN.low_track : battle ? BATTLE_SPAN.low_track : lm ? 0.25 : 0.5; // low_track: a lateral dolly across the set
  return { start: { ...offset(base, h - 90, span / 2), alt: alt0, heading: h, tilt: 60 }, end: { ...offset(base, h + 90, span / 2), alt: alt0, heading: h, tilt: 60 }, ease: 'linear' };
}


/**
 * End framing of each of the k parts of a long hold. A wide (map / oblique) hold is a one-way DIVE toward the place: lower, turning,
 * drifting forward along the beat's path or heading, so every part shows something new and none returns to a view already shown (the
 * old cycle of the same three framings bobbed in place for a minute). A ground hold keeps to the set but changes shot and heading.
 */
export function holdEnds(b, shot, fr, seed, k) {
  const ends = [fr.end];
  if (k <= 1) return ends;
  const wide = b.rung === 'map' || b.rung === 'oblique';
  if (wide) {
    const floor = b.rung === 'map' ? RUNG.oblique.alt : 140, a0 = fr.end.alt, a1 = Math.min(a0, floor);
    const dir = (seed % 2 ? 1 : -1), h0 = fr.end.heading ?? 0;
    const pts = b.path && b.path.length >= 2 ? b.path : null;
    for (let s = 1; s < k; s++) {
      const f = s / (k - 1), alt = a0 * Math.pow(a1 / a0, f);
      let at;
      if (pts) {   // travel along the path as the camera comes down
        const x = f * (pts.length - 1), j = Math.min(pts.length - 2, Math.floor(x)), u = x - j;
        at = { lon: pts[j][0] + (pts[j + 1][0] - pts[j][0]) * u, lat: pts[j][1] + (pts[j + 1][1] - pts[j][1]) * u };
      } else at = offset({ lon: b.lon, lat: b.lat }, h0 + dir * 70, alt * 0.35 * Math.sin(Math.PI * f) * 0.5);   // swing out and back onto the place
      ends.push({ lon: at.lon, lat: at.lat, alt, heading: h0 + dir * 38 * s, tilt: null });
    }
    return ends;
  }
  const alts = altShots(b).filter((x) => x !== shot);
  for (let s = 1; s < k; s++) { const sh = alts.length ? alts[(s - 1) % alts.length] : shot; ends.push(shotFrames(b, sh, seed + s * 3).end); }
  return ends;
}

/** Where the camera is when a hold of `dur` seconds on beat b ends (the move to the next beat starts from here). */
export function holdEndFrame(b, shot, seed, dur) {
  const fr = shotFrames(b, shot, seed), k = b.rung === 'globe' ? 1 : Math.max(1, Math.ceil(dur / MAX_SHOT));
  return holdEnds(b, shot, fr, seed, k).at(-1);
}

/** What kind of move joins two framings (for reports and tests). */
export function moveKind(a, b) {
  const d = distanceKm(a, b);
  if (d > 1500) return 'travel';
  if (a.alt > 150 && b.alt < 20) return 'descent';
  if (a.alt < 20 && b.alt > 150) return 'ascent';
  if (a.alt < 20 && b.alt < 20) return 'hop';
  return 'reframe';
}

/**
 * Camera path for the timed beats [{i, travelT0, travelT1, speakT0, speakT1}] -> { camera: segments, shots: [...] }.
 * The move into a beat runs [travelT0, travelT1] (inside the silence); its shot runs from travelT1 to the end of its speech.
 */
export function direct(spec, timed, end) {
  const camera = [], shots = [];
  let prev = null, prevEnd = 0, prevShot = null;
  for (const tb of timed) {
    const b = spec.beats[tb.i], shot = chooseShot(spec, tb.i, prevShot), fr = shotFrames(b, shot, b.seed ?? tb.i);
    if (prev) {
      camera.push({ type: 'hold', t0: prevEnd, t1: tb.travelT0, from: prev });
      camera.push({ type: 'fly', t0: tb.travelT0, t1: tb.travelT1, from: prev, to: fr.start });
    }
    const holdEnd = tb.holdT1 ?? Math.max(tb.speakT1, tb.travelT1 + 0.5);
    // a long read never sits on one framing: past MAX_SHOT the hold continues as connected moves through other framings of the
    // same place (each starts where the last ended, so there is never a jump)
    const dur = holdEnd - tb.travelT1, k = b.rung === 'globe' ? 1 : Math.max(1, Math.ceil(dur / MAX_SHOT));
    let from = fr.start, end = fr.end;
    const ends = holdEnds(b, shot, fr, b.seed ?? tb.i, k);
    if (k > 1 && shot === 'pullback' && b.rung !== 'ground') { const e0 = shotFrames(b, 'establishing', b.seed ?? tb.i); ends.splice(0, ends.length, ...holdEnds(b, 'establishing', e0, b.seed ?? tb.i, k)); }   // a long read dives in; it does not open by rising away
    for (let s = 0; s < k; s++) {
      const t0 = tb.travelT1 + (dur * s) / k, t1 = tb.travelT1 + (dur * (s + 1)) / k;
      end = ends[s];
      // several parts glide at a steady speed through each junction (an eased stop at every one read as a camera that keeps freezing)
      camera.push({ type: 'move', t0, t1, from, to: end, ease: k === 1 ? fr.ease : 'linear' });
      from = end;
    }
    shots.push({ beat: b.id, shot, move: prev ? moveKind(prev, fr.start) : 'open', parts: k });
    prev = end; prevEnd = holdEnd; prevShot = shot;
  }
  camera.push({ type: 'hold', t0: prevEnd, t1: end, from: prev });
  return { camera, shots };
}

/** Seconds the move into beat i needs (used when planning silences). */
export function moveSeconds(spec, i, prevEndFrame) {
  const b = spec.beats[i], fr = shotFrames(b, chooseShot(spec, i, null), b.seed ?? i);
  return prevEndFrame ? travelSeconds(prevEndFrame, fr.start) : 0;
}
