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
    if (/battle|fortress|trail|jungle/.test(r)) { pick = hash(b.id + b.place) % 2 ? 'flyover' : 'orbit'; alts = ['flyover', 'orbit', 'low_track']; }
    else { pick = 'low_track'; alts = ['low_track', 'orbit']; }
  }
  if (pick === prevShot) pick = alts.find((x) => x !== prevShot) || pick;
  return pick;
}

/** Start and end framing of a held shot. */
export function shotFrames(b, shot, seed) {
  const base = { lon: b.lon, lat: b.lat, tilt: null };
  const battle = b.rung === 'ground' && b.site === 'battle';
  const alt0 = b.alt ?? (b.rung === 'ground' ? (battle ? BATTLE_ALT[shot] : null) ?? GROUND_ALT[shot] ?? RUNG.ground.alt : RUNG[b.rung].alt);
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
    const span = battle ? BATTLE_SPAN.flyover : 0.8; // km: a pass from one side of the set to the other (battle: only its action)
    return { start: { ...offset(base, h + 180, span / 2), alt: alt0, heading: h, tilt: 52 }, end: { ...offset(base, h, span / 2), alt: alt0 * 1.12, heading: h + 4, tilt: 50 }, ease: 'linear' };
  }
  const span = battle ? BATTLE_SPAN.low_track : 0.5; // low_track: a lateral dolly across the set
  return { start: { ...offset(base, h - 90, span / 2), alt: alt0, heading: h, tilt: 60 }, end: { ...offset(base, h + 90, span / 2), alt: alt0, heading: h, tilt: 60 }, ease: 'linear' };
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
    const holdEnd = Math.max(tb.speakT1, tb.travelT1 + 0.5);
    camera.push({ type: 'move', t0: tb.travelT1, t1: holdEnd, from: fr.start, to: fr.end, ease: fr.ease });
    shots.push({ beat: b.id, shot, move: prev ? moveKind(prev, fr.start) : 'open' });
    prev = fr.end; prevEnd = holdEnd; prevShot = shot;
  }
  camera.push({ type: 'hold', t0: prevEnd, t1: end, from: prev });
  return { camera, shots };
}

/** Seconds the move into beat i needs (used when planning silences). */
export function moveSeconds(spec, i, prevEndFrame) {
  const b = spec.beats[i], fr = shotFrames(b, chooseShot(spec, i, null), b.seed ?? i);
  return prevEndFrame ? travelSeconds(prevEndFrame, fr.start) : 0;
}
