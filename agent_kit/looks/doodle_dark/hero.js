// doodle_dark mascot: a flat 2D cartoon survivor drawn as SVG. Every frame is a pure function of t.
//
//   import { hero, DESIGNS, FACES } from '/agent_kit/looks/doodle_dark/hero.js';
//   svg.innerHTML = hero(t, { design: 'scout', face: 'scared', x: 960, y: 900, scale: 1.2, talking: true });
//   svg.innerHTML = hero(t, { face: 'panic', closeup: true, x: 960, y: 560, scale: 3 });   // head only
//
// Local frame: feet at (0,0), y up is negative, about 420 units tall at scale 1. Poses come in Step 2;
// this file has the stand pose, the three candidate designs and every face.
import { P } from './palette.js';

const INK = P.ink, W = 6;
let _sw = 0, _bobA = 0;   // scarf-tail and hat-bobble swing (degrees), set by hero() each frame

export const DESIGNS = {
  // A: olive beanie, orange scarf, navy jacket, backpack straps
  // muted to sit in the dim night palette (reference study 2)
  scout: { skin: '#e3bf9c', skinShade: '#c9a47f', jacket: '#3a4760', pants: '#262a34', shoes: '#191c24',
           hat: 'beanie', hatColor: '#5f6a3c', hatBand: '#4d5731', scarf: '#c8743c', straps: '#6a4a30' },
  // B: messy dark hair, goggles on the forehead, bandage on the cheek, teal hoodie
  patch: { skin: '#c98d5e', skinShade: '#b07a4e', jacket: '#2f8f83', pants: '#33363f', shoes: '#1d2029',
           hat: 'hair', hatColor: '#2a1d17', goggles: '#5fd3d6', bandage: true, hood: true },
  // C: yellow bike helmet, purple bandana, brown jacket, torch on the chest
  rook: { skin: '#f5d7b5', skinShade: '#e0bd98', jacket: '#6a4a3a', pants: '#2b2f3a', shoes: '#1d2029',
          hat: 'helmet', hatColor: '#f2c230', hatBand: '#d4a61c', scarf: '#8c5bd6', torch: true },
};

export const FACES = ['calm', 'scared', 'panic', 'worried', 'relieved', 'angry', 'sad', 'thinking', 'sleeping', 'holdbreath'];

// seeded blink: about every 3-4 s, 0.12 s long
function blink(t, seed = 7) {
  const period = 3.3 + (seed % 5) * 0.17;
  const k = ((t + seed * 0.37) % period) / period;
  return k > 0.965 ? 1 : 0;
}

// ---------- face pieces (head centre at 0,0, head radius 78) ----------
function eyes(face, t, talking) {
  const closed = face === 'sleeping' || (face !== 'panic' && blink(t) === 1);
  const big = face === 'scared' || face === 'panic' || face === 'holdbreath';
  const rx = big ? 21 : 17, ry = big ? 26 : 21, ex = 29, ey = 6;
  if (closed) {
    return [-ex, ex].map((x) => `<path d="M${x - 15} ${ey + 2} Q${x} ${ey + 12} ${x + 15} ${ey + 2}" fill="none" stroke="${INK}" stroke-width="${W}" stroke-linecap="round"/>`).join('');
  }
  const pr = face === 'panic' ? 5 : face === 'scared' ? 7 : 9;
  let px = 0, py = 2;
  if (face === 'thinking') { px = 6; py = -8; }
  if (face === 'sad') py = 6;
  if (face === 'worried') px = -4;
  if (face === 'panic') { px = Math.sin(t * 40) * 3; } // trembling pupils
  return [-ex, ex].map((x) =>
    `<ellipse cx="${x}" cy="${ey}" rx="${rx}" ry="${ry}" fill="#fff" stroke="${INK}" stroke-width="${W - 1}"/>` +
    `<circle cx="${x + px}" cy="${ey + py}" r="${pr}" fill="${INK}"/>` +
    `<circle cx="${x + px - 3}" cy="${ey + py - 3}" r="${Math.max(1.5, pr / 3)}" fill="#fff"/>`).join('');
}

function brows(face) {
  const y = -24, s = `fill="none" stroke="${INK}" stroke-width="${W}" stroke-linecap="round"`;
  const pair = (l, r) => `<path d="${l}" ${s}/><path d="${r}" ${s}/>`;
  switch (face) {
    case 'angry': return pair(`M-46 ${y - 6} L-16 ${y + 6}`, `M46 ${y - 6} L16 ${y + 6}`);
    case 'scared': case 'panic': case 'holdbreath': return pair(`M-44 ${y - 4} Q-30 ${y - 16} -16 ${y - 8}`, `M44 ${y - 4} Q30 ${y - 16} 16 ${y - 8}`);
    case 'worried': case 'sad': return pair(`M-44 ${y + 2} L-16 ${y - 8}`, `M44 ${y + 2} L16 ${y - 8}`);
    case 'thinking': return pair(`M-44 ${y} L-16 ${y}`, `M44 ${y - 10} Q30 ${y - 16} 16 ${y - 8}`);
    case 'sleeping': return '';
    default: return pair(`M-42 ${y - 2} Q-30 ${y - 8} -18 ${y - 2}`, `M42 ${y - 2} Q30 ${y - 8} 18 ${y - 2}`);
  }
}

function mouth(face, t, talking) {
  const y = 42, s = `fill="none" stroke="${INK}" stroke-width="${W}" stroke-linecap="round" stroke-linejoin="round"`;
  const open = talking ? 0.5 + 0.5 * Math.abs(Math.sin(t * 13.0) * Math.sin(t * 7.3 + 1)) : 0;
  if (talking && face !== 'sleeping') {
    const h = 4 + open * 18;
    return `<ellipse cx="0" cy="${y}" rx="${14 + open * 4}" ry="${h / 2}" fill="#5b1f24" stroke="${INK}" stroke-width="${W - 1}"/>`;
  }
  switch (face) {
    case 'scared': return `<ellipse cx="0" cy="${y + 2}" rx="11" ry="14" fill="#5b1f24" stroke="${INK}" stroke-width="${W - 1}"/>`;
    case 'panic': return `<path d="M-24 ${y + 12} L-12 ${y} L0 ${y + 12} L12 ${y} L24 ${y + 12}" ${s}/>`;
    case 'worried': return `<path d="M-20 ${y + 6} Q-10 ${y - 4} 0 ${y + 4} Q10 ${y + 12} 20 ${y + 2}" ${s}/>`;
    case 'relieved': return `<path d="M-24 ${y - 4} Q0 ${y + 22} 24 ${y - 4}" ${s}/>`;
    case 'angry': return `<path d="M-20 ${y + 8} L20 ${y + 8}" ${s}/><path d="M-20 ${y + 8} Q0 ${y - 6} 20 ${y + 8}" ${s}/>`;
    case 'sad': return `<path d="M-20 ${y + 10} Q0 ${y - 8} 20 ${y + 10}" ${s}/>`;
    case 'thinking': return `<path d="M-14 ${y + 4} L16 ${y}" ${s}/>`;
    case 'holdbreath': return `<path d="M-16 ${y + 2} Q0 ${y - 4} 16 ${y + 2}" ${s}/>`;
    case 'sleeping': return `<ellipse cx="0" cy="${y + 2}" rx="7" ry="6" fill="#5b1f24" stroke="${INK}" stroke-width="${W - 2}"/>`;
    default: return `<path d="M-18 ${y} Q0 ${y + 12} 18 ${y}" ${s}/>`;
  }
}

function extras(face, t) {
  // sweat drop for scared/worried/panic, Zzz for sleeping, tear for sad
  if (face === 'scared' || face === 'worried' || face === 'panic') {
    const k = (t * 0.8) % 1, y = -30 + k * 30;
    return `<path d="M62 ${y} q-8 14 0 20 q8 -6 0 -20z" fill="${P.teal}" stroke="${INK}" stroke-width="3" opacity="${1 - k * 0.6}"/>`;
  }
  if (face === 'sad') return `<path d="M-30 ${16} q-6 12 0 16 q6 -4 0 -16z" fill="${P.teal}" stroke="${INK}" stroke-width="3"/>`;
  if (face === 'sleeping') {
    const k = (t * 0.5) % 1;
    return `<text x="${70 + k * 30}" y="${-70 - k * 50}" font-family="Impact, sans-serif" font-size="${30 + k * 14}" fill="${P.paper}" stroke="${INK}" stroke-width="3" paint-order="stroke" opacity="${1 - k}">Z</text>`;
  }
  return '';
}

// ---------- head with hat/hair ----------
function headwear(d, back) {
  const c = d.hatColor;
  if (d.hat === 'beanie') {
    if (back) return '';
    return `<g transform="translate(0 -14)"><path d="M-80 -22 Q-82 -98 0 -100 Q82 -98 80 -22 Z" fill="${c}" stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"/>` +
      `<rect x="-86" y="-38" width="172" height="28" rx="12" fill="${d.hatBand}" stroke="${INK}" stroke-width="${W}"/>` +
      `<g transform="rotate(${_bobA.toFixed(2)} 0 -86)"><circle cx="0" cy="-104" r="16" fill="${d.hatBand}" stroke="${INK}" stroke-width="${W}"/></g></g>`;
  }
  if (d.hat === 'helmet') {
    if (back) return '';
    return `<g transform="translate(0 -16)"><path d="M-88 -18 Q-90 -102 0 -104 Q90 -102 88 -18 Z" fill="${c}" stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"/>` +
      `<path d="M-30 -96 L-26 -60 M0 -102 L0 -62 M30 -96 L26 -60" stroke="${d.hatBand}" stroke-width="10" stroke-linecap="round"/>` +
      `<path d="M-94 -20 L94 -20" stroke="${INK}" stroke-width="${W + 2}" stroke-linecap="round"/>` +
      `<path d="M-62 -16 Q-70 10 -66 30 M62 -16 Q70 10 66 30" fill="none" stroke="${INK}" stroke-width="4"/></g>`;
  }
  // messy hair + goggles
  if (back) return `<path d="M-84 -10 Q-96 -70 -60 -96 Q-20 -124 30 -110 Q90 -96 86 -10 Z" fill="${c}" stroke="${INK}" stroke-width="${W}"/>`;
  let s = `<path d="M-80 -30 L-70 -70 L-48 -58 L-36 -100 L-12 -70 L6 -108 L22 -72 L48 -100 L52 -62 L78 -74 L80 -30 Q40 -54 0 -50 Q-40 -54 -80 -30Z" fill="${c}" stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"/>`;
  if (d.goggles) {
    s += `<g transform="translate(0 -10)"><path d="M-80 -58 L80 -58" stroke="${INK}" stroke-width="10"/>` +
      `<circle cx="-26" cy="-60" r="20" fill="${d.goggles}" stroke="${INK}" stroke-width="${W}"/>` +
      `<circle cx="26" cy="-60" r="20" fill="${d.goggles}" stroke="${INK}" stroke-width="${W}"/>` +
      `<circle cx="-32" cy="-66" r="5" fill="#fff" opacity=".8"/><circle cx="20" cy="-66" r="5" fill="#fff" opacity=".8"/></g>`;
  }
  return s;
}

function head(d, face, t, talking) {
  let s = headwear(d, true);
  s += `<circle cx="0" cy="0" r="78" fill="${d.skin}" stroke="${INK}" stroke-width="${W}"/>`;
  if (face === 'holdbreath') {
    const pf = 1 + 0.04 * Math.sin(t * 5);
    s += [-1, 1].map((sd) => `<ellipse cx="${sd * 56}" cy="36" rx="${30 * pf}" ry="${26 * pf}" fill="${d.skin}" stroke="${INK}" stroke-width="${W - 1}"/>`).join('') +
      `<circle cx="0" cy="0" r="72" fill="${d.skin}"/>`;
  }
  s += `<path d="M-60 40 Q0 82 60 40 Q40 74 0 76 Q-40 74 -60 40Z" fill="${d.skinShade}" opacity=".55"/>`;
  // cheeks
  s += `<circle cx="-46" cy="22" r="10" fill="#e8806a" opacity="${face === 'relieved' || face === 'calm' ? 0.45 : 0.2}"/>` +
       `<circle cx="46" cy="22" r="10" fill="#e8806a" opacity="${face === 'relieved' || face === 'calm' ? 0.45 : 0.2}"/>`;
  if (d.bandage) s += `<g transform="translate(-46 30) rotate(-20)"><rect x="-18" y="-7" width="36" height="14" rx="5" fill="#f1e2c4" stroke="${INK}" stroke-width="3"/><path d="M-4 -3 v6 M4 -3 v6" stroke="#c9b48c" stroke-width="2"/></g>`;
  s += eyes(face, t, talking) + brows(face) + mouth(face, t, talking) + extras(face, t);
  s += headwear(d, false);
  return s;
}

// ---------- jointed rig ----------
// All angles in degrees, screen plane. A limb hangs straight down at 0; positive swings its end toward +x
// (the way the hero faces). Knees/elbows are relative to the upper segment.
// Hip is at (0, -110 + drop) above the feet; the torso leans around the hip; the head sits 220 above the hip.
const THIGH = 56, SHIN = 56, UPPER = 50, LOWER = 48;

const STAND = { lean: 0, drop: 0, tilt: 0, lT: -3, lS: 0, rT: 3, rS: 0, lU: -12, lL: 0, rU: 12, rL: 0, rot: 0 };
const sin = Math.sin, TAU = Math.PI * 2;

// pose name -> function(t) returning joint angles (+ optional bob). Cycles are pure functions of t.
export const POSES = {
  stand: () => ({ ...STAND }),
  walk: (t) => {
    const p = t * TAU * 1.7, s1 = sin(p);
    return { ...STAND, lT: 22 * s1, rT: -22 * s1, lS: -28 * Math.max(0, -s1), rS: -28 * Math.max(0, s1),
             lU: -18 * s1 - 6, rU: 18 * s1 + 6, lL: 10, rL: 10, lean: 4, bob: -5 * Math.abs(sin(p)) };
  },
  run: (t) => {
    const p = t * TAU * 2.7, s1 = sin(p);
    return { ...STAND, lT: 42 * s1 + 8, rT: -42 * s1 + 8, lS: -70 * Math.max(0, -s1) - 10, rS: -70 * Math.max(0, s1) - 10,
             lU: -45 * s1, rU: 45 * s1, lL: 80, rL: 80, lean: 14, bob: -12 * Math.abs(sin(p)), drop: 6 };
  },
  sneak: (t) => {
    const p = t * TAU * 0.8, s1 = sin(p);
    return { ...STAND, drop: 30, lean: 18, lT: 30 + 14 * s1, rT: 30 - 14 * s1, lS: -55, rS: -55,
             lU: 35, lL: 70, rU: 45, rL: 75, tilt: -6, bob: -3 * Math.abs(s1) };
  },
  crouch: (t) => ({ ...STAND, drop: 46, lean: 4, lT: -52, lS: 98, rT: 52, rS: -98, lU: 22, lL: 30, rU: -22, rL: -30, bob: Math.sin(t * 2) * 1.5 }),
  sit: () => ({ ...STAND, drop: 55, lT: 90, lS: -90, rT: 84, rS: -86, lU: 10, lL: 50, rU: 18, rL: 55 }),
  hold: () => ({ ...STAND, rU: 25, rL: 95 }),
  point: () => ({ ...STAND, rU: 85, rL: 5, tilt: 4 }),
  handsup: (t) => ({ ...STAND, lU: -150, lL: -15, rU: 150, rL: 15, bob: sin(t * 30) * 1.5 }),
  push: (t) => ({ ...STAND, lean: 24, lT: 14, lS: -10, rT: -26, rS: -8, lU: 80, lL: 8, rU: 88, rL: 6,
                  bob: sin(t * 9) * 2 }),
  peek: (t) => ({ ...STAND, lean: 12, tilt: 10 + sin(t * 1.3) * 3, rU: 30, rL: 60, lU: -8 }),
  eat: (t) => ({ ...STAND, rU: 20, rL: 120 + sin(t * 6) * 8, lU: -10, lL: 20 }),
  cower: (t) => ({ ...STAND, drop: 44, lean: 0, lT: -50, lS: 96, rT: 50, rS: -96, lU: 150, lL: -50, rU: -150, rL: 50, frontL: 1,
                   tilt: 0, bob: Math.sin(t * 28) * 1.2 }),
  lie: () => ({ ...STAND, rot: -90, lU: -6, rU: 6, lT: -2, rT: 2 }),     // on his back (sleep / hurt)
};

function limbPath(c, w, len1, a1, len2, a2, pass, end = '') {
  // two segments in a nested frame; pass 'ink' draws the outline, 'fill' the colour, 'end' adds the hand/foot
  const stroke = pass === 'ink' ? INK : c, sw = pass === 'ink' ? w + W * 2 : w;
  return `<g transform="rotate(${-a1})"><path d="M0 0 L0 ${len1}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round"/>` +
         `<g transform="translate(0 ${len1}) rotate(${-a2})"><path d="M0 0 L0 ${len2}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round"/>` +
         `${pass === 'fill' ? end : ''}</g></g>`;
}

function arm(d, up, low, side, item, t) {
  const hand = `<circle cx="0" cy="${LOWER + 4}" r="16" fill="${d.skin}" stroke="${INK}" stroke-width="${W}"/>` +
               (item && side > 0 ? `<g transform="translate(0 ${LOWER + 4})">${ITEMS[item] ? ITEMS[item](t) : ''}</g>` : '');
  return `<g transform="translate(${56 * side} -116)">` + limbPath(d.jacket, 28, UPPER, up, LOWER, low, 'ink') +
         limbPath(d.jacket, 28, UPPER, up, LOWER, low, 'fill', hand) + '</g>';
}

function leg(d, th, sh, side) {
  const foot = `<g transform="translate(0 ${SHIN}) rotate(${th + sh})"><ellipse cx="10" cy="4" rx="30" ry="15" fill="${d.shoes}" stroke="${INK}" stroke-width="${W}"/></g>`;
  return `<g transform="translate(${24 * side} 0)">` + limbPath(d.pants, 32, THIGH, th, SHIN, sh, 'ink') +
         limbPath(d.pants, 32, THIGH, th, SHIN, sh, 'fill', foot) + '</g>';
}

function torso(d, br) {
  let s = `<path d="M-62 ${-136 + br} Q0 ${-152 + br} 62 ${-136 + br} L60 -2 Q0 10 -60 -2 Z" fill="${d.jacket}" stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"/>`;
  s += `<path d="M0 ${-140 + br} L0 4" stroke="${INK}" stroke-width="3" opacity=".5"/>`;
  if (d.hood) s += `<path d="M-50 ${-140 + br} Q0 ${-116 + br} 50 ${-140 + br}" fill="none" stroke="${INK}" stroke-width="${W}"/><path d="M-12 ${-126 + br} l-4 40 M12 ${-126 + br} l4 40" stroke="#e9e2d0" stroke-width="5" stroke-linecap="round"/>`;
  if (d.straps) s += `<path d="M-40 ${-138 + br} L-34 -10 M40 ${-138 + br} L34 -10" stroke="${d.straps}" stroke-width="14"/><path d="M-40 ${-138 + br} L-34 -10 M40 ${-138 + br} L34 -10" stroke="${INK}" stroke-width="3" opacity=".6"/>`;
  if (d.scarf) s += `<path d="M-56 ${-140 + br} Q0 ${-116 + br} 56 ${-140 + br} L50 ${-122 + br} Q0 ${-100 + br} -50 ${-122 + br}Z" fill="${d.scarf}" stroke="${INK}" stroke-width="${W}"/><g transform="rotate(${_sw.toFixed(2)} 24 ${-114 + br})"><path d="M24 ${-114 + br} q8 28 10 56 l-24 -4z" fill="${d.scarf}" stroke="${INK}" stroke-width="${W - 1}" stroke-linejoin="round"/></g>`;
  if (d.torch) s += `<g transform="translate(-30 ${-86 + br})"><rect x="-12" y="-10" width="24" height="34" rx="5" fill="#3b3f4a" stroke="${INK}" stroke-width="4"/><circle cx="0" cy="-12" r="10" fill="${P.window}" stroke="${INK}" stroke-width="4"/></g>`;
  return s;
}

// ---------- things he can hold (drawn at the right hand, pointing along the forearm) ----------
const ink = `stroke="${INK}" stroke-width="5" stroke-linejoin="round"`;
export const ITEMS = {
  can: () => `<rect x="-16" y="4" width="32" height="44" rx="6" fill="#c9ced8" ${ink}/><rect x="-16" y="16" width="32" height="18" fill="${P.danger}" ${ink}/>`,
  bat: () => `<path d="M-6 -10 L-10 150 Q0 166 10 150 L6 -10 Z" fill="#b5834f" ${ink}/><rect x="-7" y="-16" width="14" height="22" rx="4" fill="#3b3f4a" ${ink}/>`,
  torch: (t) => `<rect x="-11" y="0" width="22" height="58" rx="6" fill="#3b3f4a" ${ink}/><rect x="-15" y="50" width="30" height="16" rx="4" fill="#565c6a" ${ink}/>` +
                `<path d="M-15 66 L-120 420 L120 420 L15 66 Z" fill="${P.window}" opacity="${0.32 + 0.04 * Math.sin(t * 7)}" style="mix-blend-mode:screen"/>`,
  radio: () => `<rect x="-26" y="2" width="52" height="64" rx="8" fill="#4a5163" ${ink}/><path d="M14 2 L22 -40" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>` +
               `<rect x="-16" y="12" width="32" height="18" rx="3" fill="${P.toxic}" ${ink}/><circle cx="0" cy="48" r="9" fill="#2b2f3a" ${ink}/>`,
  phone: (t) => `<rect x="-17" y="-2" width="34" height="58" rx="7" fill="#20242e" ${ink}/><rect x="-11" y="5" width="22" height="40" rx="3" fill="${P.teal}" opacity="${0.7 + 0.3 * Math.sin(t * 4)}"/>`,
  knife: () => `<rect x="-6" y="-4" width="12" height="26" rx="3" fill="#3b3f4a" ${ink}/><path d="M-7 22 L0 90 L7 22 Z" fill="#dfe4ec" ${ink}/>`,
  axe: () => `<path d="M-5 -10 L-5 150 L5 150 L5 -10 Z" fill="#b5834f" ${ink}/><path d="M5 110 Q50 100 52 140 Q40 160 5 150 Z" fill="#c9ced8" ${ink}/>`,
};

export function hero(t, { design = 'scout', face = 'calm', pose = 'stand', item = '', x = 960, y = 900, scale = 1,
                          facing = 1, talking = false, closeup = false, joints = null, light = '',
                          pose2 = '', mix = 0, dip = 0, shadow = true, speed = 0 } = {}) {
  const d = DESIGNS[design] || DESIGNS.scout;
  // secondary motion: scarf tail and bobble lag behind body movement
  const moving = speed || (pose === 'run' ? 2 : pose === 'walk' ? 1 : pose === 'sneak' ? 0.5 : 0);
  _sw = 7 * Math.sin(t * 3.1) + moving * (10 + 8 * Math.sin(t * 9)) + (dip ? 12 * dip : 0);
  _bobA = 6 * Math.sin(t * 2.6 + 1) + moving * 9 * Math.sin(t * 10.7) - (dip ? 10 * dip : 0);
  if (closeup) {
    return `<g transform="translate(${x} ${y}) scale(${scale * facing} ${scale})">${head(d, face, t, talking)}</g>`;
  }
  let j = { ...STAND, ...(POSES[pose] || POSES.stand)(t) };
  if (pose2 && mix > 0) {                              // blend toward a second pose (0..1)
    const b = { ...STAND, ...(POSES[pose2] || POSES.stand)(t) }, k = Math.min(1, mix);
    for (const key of Object.keys(b)) j[key] = (j[key] || 0) + ((b[key] || 0) - (j[key] || 0)) * k;
  }
  j = { ...j, ...(joints || {}) };
  if (dip) j.drop = (j.drop || 0) + 12 * dip;          // anticipation squash between poses
  const br = Math.sin(t * 2.2) * 2;                  // breathing
  const bob = (j.bob || 0) + br;
  // lie: rotate the whole body around the feet and lay him on the ground
  const lay = j.rot ? `translate(-150 -30) rotate(${j.rot} 0 0)` : '';
  const hip = `translate(0 ${-110 + j.drop + (j.bob || 0)})`;
  const f = light ? ` filter="url(#lit-${light})"` : '';
  const sh = shadow && !j.rot ? `<ellipse cx="${x}" cy="${y + 4 * scale}" rx="${(78 + (j.drop || 0) * 0.5) * scale}" ry="${13 * scale}" fill="#000" opacity=".38" filter="url(#blur4)"/>` : '';
  return sh + `<g${f}><g transform="translate(${x} ${y}) scale(${scale * facing} ${scale}) ${lay}">` +
    `<g transform="${hip}">` +
      leg(d, j.lT, j.lS, -1) + leg(d, j.rT, j.rS, 1) +
      `<g transform="rotate(${j.lean})">` +
        (j.frontL ? '' : arm(d, j.lU, j.lL, -1, item, t)) +
        torso(d, br) +
        `<g transform="translate(0 ${-220 + br}) rotate(${j.tilt})">${head(d, face, t, talking)}</g>` +
        arm(d, j.rU, j.rL, 1, item, t) +
        (j.frontL ? arm(d, j.lU, j.lL, -1, item, t) : '') +
      `</g>` +
    `</g></g></g>`;
}

// how far the hero travels per second in each moving pose (so feet do not slide too much)
export const SPEED = { walk: 190, run: 520, sneak: 70 };

// Key-framed hero: keys = [{ at, pose, face, item, x, facing }...] (scene seconds, sorted). Poses blend over `blend`
// seconds with a small anticipation dip; x glides between keys that set it. Everything else comes from `base`.
export function heroAt(t, keys, base = {}, blend = 0.28) {
  let i = 0;
  while (i + 1 < keys.length && t >= keys[i + 1].at) i++;
  const cur = keys[i], prev = keys[i - 1];
  const o = { ...base, ...cur };
  if (prev && t - cur.at < blend) {
    const k = (t - cur.at) / blend, e = k * k * (3 - 2 * k);
    o.pose = prev.pose || base.pose || 'stand'; o.pose2 = cur.pose || base.pose || 'stand'; o.mix = e;
    o.dip = Math.sin(Math.PI * k) * 0.8;
    if (prev.x !== undefined && cur.x !== undefined) o.x = prev.x + (cur.x - prev.x) * e;
  }
  delete o.at;
  return hero(t, o);
}
