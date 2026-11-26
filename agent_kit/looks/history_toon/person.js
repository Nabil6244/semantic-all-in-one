// history_toon cast: flat 2D cartoon people with big round white faces, drawn as SVG. Every frame is a pure function of t.
//
//   import { person, personAt, OUTFITS } from '/agent_kit/looks/history_toon/person.js';
//   svg.innerHTML += person(t, { outfit: 'pilot', face: 'worried', pose: 'salute', x: 960, y: 900, scale: 1.1 });
//   svg.innerHTML += person(t, { outfit: { ...OUTFITS.officer, coat: '#3b2f52' }, face: 'angry', closeup: true, x: 960, y: 520, scale: 3 });
//
// Local frame: feet at (0,0), y up is negative, about 400 units tall at scale 1 (head centre at 0,-318, radius 64).
// Seated poses put the hips at y = -128, so draw the chair seat there.
// OUTFITS are only starting points: every video designs its OWN cast (colours, hats, extras) from its script.
import { P, shade } from './palette.js';

const INK = P.ink, W = P.ink_w;

export const OUTFITS = {
  pilot:   { coat: '#7b7a45', pants: '#6b6a3c', boots: '#4a3a2a', hat: 'flightcap', hatColor: '#6e5a3e', goggles: true, scarf: '#f3ead4', belt: '#5a4630' },
  soldier: { coat: '#7a7f45', pants: '#6a6e3c', boots: '#3f3324', hat: 'helmet', hatColor: '#6f7440', star: P.gold, belt: '#5a4630' },
  officer: { coat: '#2c3a55', pants: '#26324a', boots: '#1f1a16', hat: 'peaked', hatColor: '#2c3a55', band: P.gold, buttons: P.gold },
  sailor:  { coat: '#f0ece2', pants: '#2c3a55', boots: '#1f1a16', hat: 'sailor', hatColor: '#f0ece2', scarf: '#2c3a55' },
  worker:  { coat: '#5f7a8a', pants: '#3f4a55', boots: '#3a2c20', hat: 'flatcap', hatColor: '#5a4a3a' },
  farmer:  { coat: '#a8774a', pants: '#6a5a3e', boots: '#4a3a2a', hat: 'straw', hatColor: '#e0c27a' },
  suit:    { coat: '#4a4a52', pants: '#3a3a42', boots: '#1f1a16', hat: 'none', hair: 'short', hairColor: '#2b2620', tie: P.red },
  noble:   { coat: '#7a2f3a', pants: '#3a2a2a', boots: '#2b2018', hat: 'crown', hatColor: P.gold, cape: '#a83a3a', buttons: P.gold },
  monk:    { coat: '#c8873a', pants: '#c8873a', boots: '#6a4a2a', hat: 'none', hair: 'bald', robe: true },
  woman:   { coat: '#8a5a6a', pants: '#8a5a6a', boots: '#3a2a24', hat: 'none', hair: 'bun', hairColor: '#2b2620', robe: true },
  elder:   { coat: '#6a5a4a', pants: '#4a4038', boots: '#2b2018', hat: 'none', hair: 'grey', hairColor: '#d8d4cc', glasses: true },
  civilian:{ coat: '#9a9a8a', pants: '#4a4a52', boots: '#3a2c20', hat: 'none', hair: 'short', hairColor: '#2b2620' },
};

export const FACES = ['calm', 'happy', 'smile', 'scared', 'shock', 'worried', 'sweat', 'sad', 'cry', 'angry', 'thinking', 'determined', 'smug', 'sleep'];
export const POSES = ['stand', 'walk', 'wave', 'salute', 'point', 'hold', 'armsup', 'shrug', 'think', 'fist', 'sit', 'bow', 'hug', 'write'];
export const SPEED = { walk: 120 };   // px per second at scale 1, so feet don't slide

// [rShoulder, rElbow, lShoulder, lElbow, rHip, rKnee, lHip, lKnee, lean]; degrees from straight down, + = outward/forward
const POSE = {
  stand:  [10, 0, 10, 0, 2, 0, 2, 0, 0],
  wave:   [150, 40, 12, 0, 2, 0, 2, 0, 0],
  salute: [125, 120, 10, 0, 2, 0, 2, 0, 0],
  point:  [92, 0, 12, 0, 2, 0, 2, 0, 0],
  hold:   [35, 70, 35, 70, 2, 0, 2, 0, 0],
  armsup: [160, 10, 160, 10, 4, 0, 4, 0, 0],
  shrug:  [55, 80, 55, 80, 2, 0, 2, 0, 0],
  think:  [30, 135, 20, 70, 2, 0, 2, 0, 0],
  fist:   [140, -20, 15, 0, 6, 0, 6, 0, 0],
  sit:    [25, 50, 25, 50, 85, -85, 85, -85, 0],
  bow:    [10, 0, 10, 0, 2, 0, 2, 0, 22],
  hug:    [70, 90, 70, 90, 2, 0, 2, 0, 0],
  write:  [40, 80, 15, 30, 85, -85, 85, -85, 8],
};

function blink(t, seed) { const p = 3.1 + (seed % 5) * 0.21; return ((t + seed * 0.43) % p) / p > 0.962; }

// ---------- face (head centre 0,0, r 64) ----------
function face(f, t, talking, seed, look = 0) {
  const s = `fill="none" stroke="${INK}" stroke-width="${W}" stroke-linecap="round" stroke-linejoin="round"`;
  let g = '';
  const ex = 22, ey = 4, lx = look * 6;
  const closed = f === 'sleep' || (f !== 'shock' && f !== 'scared' && blink(t, seed));
  if (closed) g += [-ex, ex].map((x) => `<path d="M${x - 9} ${ey} Q${x} ${ey + 7} ${x + 9} ${ey}" ${s}/>`).join('');
  else if (f === 'shock' || f === 'scared') {
    const tr = f === 'scared' ? Math.sin(t * 38) * 1.5 : 0;
    g += [-ex, ex].map((x) => `<ellipse cx="${x}" cy="${ey}" rx="13" ry="16" fill="#fff" stroke="${INK}" stroke-width="${W - 0.5}"/><circle cx="${x + lx + tr}" cy="${ey + 1}" r="4.5" fill="${INK}"/>`).join('');
  } else if (f === 'happy' || f === 'smug') {
    g += [-ex, ex].map((x) => `<path d="M${x - 9} ${ey + 3} Q${x} ${ey - 8} ${x + 9} ${ey + 3}" ${s}/>`).join('');
  } else {
    const ry = f === 'determined' || f === 'angry' ? 8 : 10;
    g += [-ex, ex].map((x) => `<ellipse cx="${x + lx}" cy="${ey}" rx="6.5" ry="${ry}" fill="${INK}"/><circle cx="${x + lx - 2}" cy="${ey - 3}" r="2" fill="#fff"/>`).join('');
  }
  // brows
  const by = -18;
  const pair = (a, b) => `<path d="${a}" ${s}/><path d="${b}" ${s}/>`;
  if (f === 'angry' || f === 'determined') g += pair(`M-34 ${by - 6} L-12 ${by + 4}`, `M34 ${by - 6} L12 ${by + 4}`);
  else if (['worried', 'sweat', 'sad', 'cry', 'scared'].includes(f)) g += pair(`M-34 ${by + 3} L-12 ${by - 6}`, `M34 ${by + 3} L12 ${by - 6}`);
  else if (f === 'shock') g += pair(`M-34 ${by - 6} Q-23 ${by - 14} -12 ${by - 8}`, `M34 ${by - 6} Q23 ${by - 14} 12 ${by - 8}`);
  else if (f === 'thinking' || f === 'smug') g += pair(`M-34 ${by} L-12 ${by}`, `M34 ${by - 8} Q23 ${by - 12} 12 ${by - 5}`);
  // mouth
  const my = 32;
  if (talking && f !== 'sleep') {
    const o = 0.45 + 0.55 * Math.abs(Math.sin(t * 12.5) * Math.sin(t * 7.1 + seed));
    g += `<ellipse cx="0" cy="${my}" rx="${9 + o * 3}" ry="${2 + o * 8}" fill="#6a2a2a" stroke="${INK}" stroke-width="${W - 1}"/>`;
  } else switch (f) {
    case 'happy': g += `<path d="M-16 ${my - 4} Q0 ${my + 16} 16 ${my - 4} Z" fill="#6a2a2a" stroke="${INK}" stroke-width="${W - 1}" stroke-linejoin="round"/>`; break;
    case 'smile': case 'smug': g += `<path d="M-14 ${my - 2} Q0 ${my + 9} 14 ${my - 4}" ${s}/>`; break;
    case 'shock': g += `<ellipse cx="0" cy="${my + 2}" rx="8" ry="11" fill="#6a2a2a" stroke="${INK}" stroke-width="${W - 1}"/>`; break;
    case 'scared': g += `<path d="M-18 ${my + 4} l6 -6 l6 6 l6 -6 l6 6 l6 -6" ${s}/>`; break;
    case 'sad': case 'cry': g += `<path d="M-13 ${my + 6} Q0 ${my - 5} 13 ${my + 6}" ${s}/>`; break;
    case 'angry': g += `<path d="M-14 ${my + 4} L14 ${my + 4}" ${s}/>`; break;
    case 'worried': case 'sweat': g += `<path d="M-15 ${my + 4} Q-7 ${my - 2} 0 ${my + 3} Q7 ${my + 8} 15 ${my + 1}" ${s}/>`; break;
    case 'sleep': g += `<path d="M-6 ${my} h12" ${s}/>`; break;
    default: g += `<path d="M-10 ${my} Q0 ${my + 5} 10 ${my}" ${s}/>`;
  }
  if (f === 'sweat') { const d = (t * 0.7) % 1; g += `<path d="M46 ${-22 + d * 30} q-8 12 0 16 q8 -4 0 -16z" fill="#9fd0e6" stroke="${INK}" stroke-width="3" opacity="${1 - d * 0.6}"/>`; }
  if (f === 'cry') { const d = (t * 1.2) % 1; g += [-ex, ex].map((x) => `<path d="M${x} ${ey + 14 + d * 34} q-5 8 0 11 q5 -3 0 -11z" fill="#9fd0e6" stroke="${INK}" stroke-width="2.5"/>`).join(''); }
  if (f === 'angry') g += `<path d="M40 -46 l8 8 m-2 -12 l-4 14" stroke="${P.red}" stroke-width="4" stroke-linecap="round"/>`;
  return g;
}

// ---------- hats and hair (drawn over the head) ----------
function hat(o, t) {
  const c = o.hatColor || '#555', d = shade(c, -0.25), st = `stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"`;
  let g = '';
  switch (o.hat) {
    case 'flightcap':
      g += `<path d="M-68 8 Q-72 -70 0 -72 Q72 -70 68 8 L56 10 Q54 -40 0 -44 Q-54 -40 -56 10 Z" fill="${c}" ${st}/>`;
      g += `<path d="M-68 4 q-10 30 4 52 l14 -6 q-6 -22 -4 -42z M68 4 q10 30 -4 52 l-14 -6 q6 -22 4 -42z" fill="${d}" ${st}/>`;
      if (o.goggles) g += `<path d="M-60 -38 H60" stroke="${INK}" stroke-width="10"/>` + [-24, 24].map((x) => `<circle cx="${x}" cy="-40" r="17" fill="#9cc7c0" ${st}/><circle cx="${x - 5}" cy="-45" r="5" fill="#fff" opacity=".8"/>`).join('');
      break;
    case 'helmet':
      g += `<path d="M-72 -6 Q-74 -84 0 -86 Q74 -84 72 -6 Z" fill="${c}" ${st}/><path d="M-80 -6 H80" stroke="${INK}" stroke-width="${W + 6}" stroke-linecap="round"/><path d="M-78 -6 H78" stroke="${d}" stroke-width="8" stroke-linecap="round"/>`;
      if (o.star) g += `<path d="M0 -62 l5 11 12 1 -9 8 3 12 -11 -6 -11 6 3 -12 -9 -8 12 -1z" fill="${o.star}" stroke="${INK}" stroke-width="2.5"/>`;
      break;
    case 'peaked':
      g += `<path d="M-60 -40 Q-70 -78 0 -84 Q70 -78 60 -40 Z" fill="${c}" ${st}/><rect x="-58" y="-48" width="116" height="16" fill="${o.band || P.red}" ${st}/>`;
      g += `<path d="M-50 -32 Q0 -14 54 -32 L50 -26 Q0 -8 -46 -26 Z" fill="${INK}"/><circle cx="0" cy="-62" r="8" fill="${o.band || P.gold}" stroke="${INK}" stroke-width="3"/>`;
      break;
    case 'flatcap':
      g += `<path d="M-62 -30 Q-60 -80 6 -78 Q66 -74 66 -36 L82 -30 Q40 -18 -62 -30Z" fill="${c}" ${st}/>`; break;
    case 'sailor':
      g += `<path d="M-50 -48 Q0 -76 50 -48 L46 -34 Q0 -48 -46 -34Z" fill="${c}" ${st}/><path d="M-46 -40 Q0 -54 46 -40" stroke="${P.navy}" stroke-width="6" fill="none"/>`; break;
    case 'straw':
      g += `<ellipse cx="0" cy="-40" rx="104" ry="20" fill="${c}" ${st}/><path d="M-50 -42 Q-46 -92 0 -94 Q46 -92 50 -42Z" fill="${c}" ${st}/><path d="M-50 -48 Q0 -38 50 -48" stroke="${P.red}" stroke-width="8" fill="none"/>`; break;
    case 'crown':
      g += `<path d="M-52 -46 L-56 -98 L-28 -70 L0 -106 L28 -70 L56 -98 L52 -46 Z" fill="${c}" ${st}/>` + [-28, 0, 28].map((x) => `<circle cx="${x}" cy="-58" r="6" fill="${P.red}" stroke="${INK}" stroke-width="2.5"/>`).join(''); break;
    case 'tophat':
      g += `<rect x="-44" y="-138" width="88" height="96" rx="6" fill="${c}" ${st}/><ellipse cx="0" cy="-44" rx="76" ry="14" fill="${c}" ${st}/><rect x="-44" y="-66" width="88" height="14" fill="${o.band || P.red}"/>`; break;
    case 'fez':
      g += `<path d="M-38 -48 L-30 -104 H30 L38 -48 Z" fill="${c}" ${st}/><path d="M0 -104 q24 6 22 40" stroke="${INK}" stroke-width="4" fill="none"/>`; break;
    case 'turban':
      g += `<path d="M-68 -18 Q-80 -104 0 -100 Q80 -104 68 -18 Q0 -46 -68 -18Z" fill="${c}" ${st}/><path d="M-60 -44 Q0 -80 60 -44 M-62 -70 Q0 -40 56 -82" stroke="${d}" stroke-width="5" fill="none"/>`; break;
  }
  if (o.headband) g += `<path d="M-64 -26 Q0 -40 64 -26 L64 -12 Q0 -26 -64 -12 Z" fill="#f6f1e6" ${st}/><circle cx="0" cy="-24" r="8" fill="${P.red}"/>`;
  return g;
}

function hair(o) {
  const c = o.hairColor || INK, st = `stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"`;
  switch (o.hair) {
    case 'short': return `<path d="M-64 -8 Q-70 -72 0 -70 Q66 -72 64 -10 Q50 -44 10 -40 Q-30 -52 -64 -8Z" fill="${c}" ${st}/>`;
    case 'bun': return `<circle cx="0" cy="-74" r="24" fill="${c}" ${st}/><path d="M-64 -4 Q-72 -72 0 -68 Q72 -72 64 -4 Q56 -40 0 -44 Q-56 -40 -64 -4Z" fill="${c}" ${st}/>`;
    case 'long': return `<path d="M-66 60 Q-80 -74 0 -70 Q80 -74 66 60 L50 60 Q56 -36 0 -42 Q-56 -36 -50 60Z" fill="${c}" ${st}/>`;
    case 'grey': return `<path d="M-64 0 q-12 -26 4 -40 q-4 -18 18 -18 M64 0 q12 -26 -4 -40 q4 -18 -18 -18" fill="${c}" ${st}/>`;
    default: return '';
  }
}

// ---------- body pieces ----------
const R = Math.PI / 180;
function limb(x, y, a1, a2, l1, l2, color, side, width = 22) {
  const ex = x + side * Math.sin(a1 * R) * l1, ey = y + Math.cos(a1 * R) * l1;
  const a = a1 + a2, hx = ex + side * Math.sin(a * R) * l2, hy = ey + Math.cos(a * R) * l2;
  const d = `M${x} ${y} L${ex.toFixed(1)} ${ey.toFixed(1)} L${hx.toFixed(1)} ${hy.toFixed(1)}`;
  return { svg: `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${width + 2 * W}" stroke-linecap="round" stroke-linejoin="round"/>` +
                `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"/>`, hx, hy };
}

function torso(o) {
  const c = o.coat, d = shade(c, -0.18), st = `stroke="${INK}" stroke-width="${W}" stroke-linejoin="round"`;
  let g = '';
  if (o.cape) g += `<path d="M-58 -244 Q-96 -120 -82 -40 L82 -40 Q96 -120 58 -244Z" fill="${o.cape}" ${st}/>`;
  const hem = o.robe ? -14 : -112;
  g += `<path d="M-52 -248 Q-58 -250 -60 -240 L${o.robe ? -76 : -64} ${hem} Q0 ${hem + 10} ${o.robe ? 76 : 64} ${hem} L60 -240 Q58 -250 52 -248 Z" fill="${c}" ${st}/>`;
  g += `<path d="M0 -246 V${hem + 4}" stroke="${d}" stroke-width="4"/>`;
  if (!o.robe) g += `<path d="M-46 -176 h28 v22 h-28z M18 -176 h28 v22 h-28z" fill="${d}" stroke="${INK}" stroke-width="3"/>`;
  if (o.belt) g += `<rect x="-63" y="-140" width="126" height="14" fill="${o.belt}" ${st}/><rect x="-10" y="-142" width="20" height="18" fill="${P.gold}" stroke="${INK}" stroke-width="3"/>`;
  if (o.buttons) g += [-214, -190, -166].map((y) => `<circle cx="10" cy="${y}" r="5" fill="${o.buttons}" stroke="${INK}" stroke-width="2"/>`).join('');
  if (o.tie) g += `<path d="M0 -246 l-9 10 l9 56 l9 -56z" fill="${o.tie}" stroke="${INK}" stroke-width="3"/>`;
  if (o.scarf) g += `<path d="M-40 -252 Q0 -230 40 -252 L44 -238 Q0 -214 -44 -238 Z" fill="${o.scarf}" ${st}/><path d="M18 -236 l14 54 l-18 4 l-6 -54z" fill="${o.scarf}" ${st}/>`;
  if (o.badge) g += `<rect x="-48" y="-224" width="30" height="20" rx="3" fill="${o.badge}" stroke="${INK}" stroke-width="3"/>`;
  return g;
}

/** Draw one person. Options: outfit (name or object), face, pose, x, y, scale, facing (1 right / -1 left), talking,
 *  closeup (x,y = head centre), look (-1..1 eye direction), seed (blink timing), joints (override POSE numbers),
 *  hold (svg string drawn at the right hand, local coords with hand at 0,0), shadow (default true). */
export function person(t, o = {}) {
  const fit = typeof o.outfit === 'string' ? OUTFITS[o.outfit] : { ...OUTFITS.civilian, ...(o.outfit || {}) };
  const pose = o.pose || 'stand';
  let J = [...(POSE[pose] || POSE.stand)];
  if (o.joints) J = J.map((v, i) => (o.joints[i] ?? v));
  const seed = o.seed ?? 3;
  if (pose === 'wave') J[1] = 40 + Math.sin(t * 9) * 25;
  if (pose === 'walk' || o.walking) {
    const ph = t * (o.stepRate || 4.2);
    J[4] = Math.sin(ph) * 24; J[6] = -Math.sin(ph) * 24; J[5] = Math.max(0, -Math.cos(ph)) * -30; J[7] = Math.max(0, Math.cos(ph)) * -30;
    J[0] = 10 - Math.sin(ph) * 18; J[2] = 10 + Math.sin(ph) * 18;
  }
  const bob = (pose === 'walk' || o.walking) ? -Math.abs(Math.sin(t * (o.stepRate || 4.2))) * 6 : Math.sin(t * 2 + seed) * 1.5;
  const s = o.scale ?? 1, f = o.facing ?? 1;
  let g = '';
  if (o.shadow !== false && !o.closeup) g += `<ellipse cx="0" cy="4" rx="70" ry="12" fill="#000" opacity=".18"/>`;
  g += `<g transform="translate(0 ${bob.toFixed(2)})">`;
  const sitting = pose === 'sit' || pose === 'write';
  const lean = J[8];
  // legs (hip at y -122). Forward = facing direction, so legs use side = +1 and the whole figure is mirrored by facing.
  const legs = [limb(-22, -122, J[6], J[7], 66, 62, fit.pants, (sitting || pose === 'walk' || o.walking) ? 1 : -1, 26), limb(22, -122, J[4], J[5], 66, 62, fit.pants, 1, 26)];
  for (const L of legs) g += L.svg + `<ellipse cx="${(L.hx + 10).toFixed(1)}" cy="${(L.hy + 2).toFixed(1)}" rx="24" ry="12" fill="${fit.boots}" stroke="${INK}" stroke-width="${W}"/>`;
  g += `<g transform="rotate(${lean} 0 -122)">`;
  const back = limb(-54, -232, J[2], J[3], 58, 54, fit.coat, -1);
  g += back.svg + `<circle cx="${back.hx.toFixed(1)}" cy="${back.hy.toFixed(1)}" r="15" fill="#fff" stroke="${INK}" stroke-width="${W}"/>`;
  g += torso(fit);
  // head
  g += `<g transform="translate(0 -318)">`;
  if (fit.hair === 'long') g += hair(fit);
  g += `<circle r="64" fill="${P.skin}" stroke="${INK}" stroke-width="${W}"/><path d="M-50 36 Q0 70 50 36" fill="none" stroke="${P.skinShade}" stroke-width="8" opacity=".7"/>`;
  g += face(o.face || 'calm', t, o.talking, seed, o.look || 0);
  if (fit.glasses) g += [-22, 22].map((x) => `<circle cx="${x}" cy="4" r="16" fill="none" stroke="${INK}" stroke-width="3.5"/>`).join('') + `<path d="M-6 4 h12" stroke="${INK}" stroke-width="3.5"/>`;
  if (fit.mustache) g += `<path d="M-22 22 q11 -10 22 0 q11 -10 22 0 q-11 10 -22 2 q-11 8 -22 -2z" fill="${fit.hairColor || INK}"/>`;
  if (fit.beard) g += `<path d="M-50 20 Q-46 84 0 88 Q46 84 50 20 Q30 44 0 46 Q-30 44 -50 20Z" fill="${fit.hairColor || INK}" stroke="${INK}" stroke-width="3"/>`;
  if (fit.hair !== 'long') g += hair(fit);
  g += hat(fit, t) + `</g>`;
  const front = limb(54, -232, J[0], J[1], 58, 54, fit.coat, 1);
  g += front.svg;
  if (o.hold) g += `<g transform="translate(${front.hx.toFixed(1)} ${front.hy.toFixed(1)})">${o.hold}</g>`;
  g += `<circle cx="${front.hx.toFixed(1)}" cy="${front.hy.toFixed(1)}" r="15" fill="#fff" stroke="${INK}" stroke-width="${W}"/>`;
  g += `</g></g>`;
  const x = o.x ?? 960, y = o.y ?? 900;
  const tr = o.closeup ? `translate(${x} ${y}) scale(${s * f} ${s}) translate(0 318)` : `translate(${x} ${y}) scale(${s * f} ${s})`;
  return `<g transform="${tr}">${g}</g>`;
}

/** Key-frame a person on spoken words: keys = [{at, pose, face, x, facing}], later keys win; x glides between keys,
 *  pose changes get a short settle. base = the other person() options. */
export function personAt(t, keys, base = {}) {
  const ks = [...keys].sort((a, b) => a.at - b.at);
  let cur = ks[0], next = null;
  for (const k of ks) { if (k.at <= t) cur = k; else { next = next || k; } }
  const o = { ...base, ...cur };
  const i = ks.indexOf(cur);
  const prev = ks[i - 1];
  if (next && cur.x !== undefined && next.x !== undefined && next.glide) {
    const k = Math.min(1, Math.max(0, (t - cur.at) / (next.at - cur.at)));
    o.x = cur.x + (next.x - cur.x) * k; o.walking = true;
  }
  if (prev && t - cur.at < 0.18) o.y = (o.y ?? 900) + 6 * Math.sin(((t - cur.at) / 0.18) * Math.PI);   // small dip on a pose change
  return person(t, o);
}
