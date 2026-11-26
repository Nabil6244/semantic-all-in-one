// shared bits for this film's scenes (doodle_dark)
import * as K from '/agent_kit/lib/kit.js';

export const AMBER = '#e7b45a', OFF = '#ece6d8', INK = '#0b0f18';

// explainer card background: near-black, faint dot grid
export function cardBg() {
  let d = '';
  for (let y = 30; y < 1080; y += 44) for (let x = 30; x < 1920; x += 44) d += `M${x} ${y}h0.1`;
  return `<rect width="1920" height="1080" fill="#0d0f14"/>` +
    `<radialGradient id="cbg"><stop offset="0" stop-color="#1a1e28"/><stop offset="1" stop-color="#0d0f14"/></radialGradient>` +
    `<rect width="1920" height="1080" fill="url(#cbg)"/>` +
    `<path d="${d}" stroke="#2a2f3b" stroke-width="3.5" stroke-linecap="round"/>`;
}

// a thin amber line drawn on with k in 0..1
export const line = (d, k, { w = 4, c = AMBER, fill = 'none' } = {}) =>
  `<path d="${d}" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${(1 - K.clamp(k)).toFixed(4)}" fill="${fill}" stroke="${c}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;

// pop scale for an element arriving at `at`
export const pop = (t, at, dur = 0.4) => K.easeOutBack(K.clamp((t - at) / dur));

// camera: slow drift + a punch on a word
export function cam(t, dur, hits = [], { zoom = 0.05, x = -20, y = -8 } = {}) {
  let s = 1;
  for (const h of hits) s *= K.punch(t, h, 0.05);
  return `${K.drift(t, dur, { zoom, x, y })} scale(${s.toFixed(4)})`;
}

// a CAPS label (HTML) with spaced letters
export const caps = (txt, x, y, { size = 30, color = OFF, align = 'center', op = 1 } = {}) =>
  `<div class="abs" style="left:${x}px;top:${y}px;transform:translateX(${align === 'center' ? '-50%' : '0'});opacity:${op};` +
  `font-weight:800;font-size:${size}px;letter-spacing:${size * 0.22}px;color:${color};white-space:nowrap">${txt}</div>`;

// slam as a plain number (K.slam returns a CSS 'scale(..)' string)
export const slamN = (t, at, from = 2.2, dur = 0.35) => {
  const k = K.clamp((t - at) / dur);
  return k >= 1 ? 1 : K.lerp(from, 1, K.easeOutExpo(k)) + Math.sin(k * Math.PI) * 0.04;
};
