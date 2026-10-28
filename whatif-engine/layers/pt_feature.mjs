// PT_FEATURE: one product feature in the concept-trailer look -- white, bold, no box: a small kicker, a huge value ("200MP"),
// a small line under it ("main sensor"). It sits in the empty half of the frame (side), never over the phone.
//   { "type": "pt_feature", "kicker": "Up to", "value": "200MP", "sub": "main sensor", "side": "left", "start": 4, "end": 8 }
// Also exports the shared product-trailer helpers (enter/exit motion, fitted fonts, side anchors) used by the other pt_* layers.
import { C, tm, clamp01, quartOut, SANS, DISPLAY } from './tm_theme.mjs';

/** Enter: fade + rise + blur-in over 0.7 s; exit: fade over 0.45 s. k 0..1, rise in px (S-scaled), blur in px. */
export function ptMotion(d, t, S, { inDur = 0.7, outDur = 0.45, rise = 26 } = {}) {
  const a = d.start ?? 0, b = d.end ?? a + 5, age = t - a;
  const kin = quartOut(age / inDur), kout = clamp01((b - t) / outDur);
  return { k: Math.min(kin, kout), kin, age, rise: (1 - kin) * rise * S, blur: (1 - kin) * 14 * S };
}

/** Bold display font (Montserrat variable) with weight; Inter for small lines. px at 1920. */
export const ptFont = (S, px, w = 800, fam = 'display') => `${w} ${Math.round(px * S)}px ${fam === 'display' ? DISPLAY : SANS}, ${DISPLAY}, sans-serif`;

/** The largest px <= px at which text (with tracking) fits maxW. */
export function ptFit(T, text, px, maxW, w = 800, fam = 'display', track = 0) {
  let p = px;
  while (p > 12 && T.measure(text, ptFont(T.S, p, w, fam), track * p / 100) > maxW) p -= 4;
  return p;
}

/** x anchor + align for a side: left half starts at 8 %, right half starts at 58 %, centre is centred. Max text width 34 %. */
export function ptSide(side, W) {
  if (side === 'right') return { x: W * 0.58, align: 'left', maxW: W * 0.34 };
  if (side === 'center') return { x: W * 0.5, align: 'center', maxW: W * 0.8 };
  return { x: W * 0.08, align: 'left', maxW: W * 0.34 };
}

/** Draw inside the motion (alpha, rise, blur). */
export function ptWith(g, f, m, fn) {
  if (m.k <= 0.002) return;
  g.save(); g.globalAlpha = f.alpha * m.k; g.translate(0, m.rise);
  if (m.blur > 0.3) g.filter = `blur(${m.blur.toFixed(1)}px)`;
  fn(); g.restore();
}

export default {
  type: 'pt_feature',
  space: 'screen',
  create: (def) => { if (def.value == null || def.value === '') throw new Error('pt_feature: "value" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = ptMotion(d, f.t, S);
    const { x, align, maxW } = ptSide(d.side === 'right' ? 'right' : 'left', W);
    const value = String(d.value), vpx = ptFit(T, value, 210, maxW, 800, 'display', -3);
    const cy = H * 0.5, vy = cy + vpx * S * 0.34;
    ptWith(g, f, m, () => {
      if (d.kicker) T.text(String(d.kicker), x, vy - vpx * S * 0.78 - 18 * S, { font: ptFont(S, 44, 600, 'sans'), color: C.white, align, shadow: 0.35, alpha: 0.92 });
      T.text(value, x, vy, { font: ptFont(S, vpx, 800), track: -vpx * 0.03, color: C.white, align, shadow: 0.35 });
      if (d.sub) {
        const k2 = clamp01((m.age - 0.25) / 0.5);
        T.text(String(d.sub), x, vy + 70 * S + (1 - k2) * 10 * S, { font: ptFont(S, 46, 600, 'sans'), color: '#E9ECF1', align, shadow: 0.35, alpha: k2 });
      }
    });
  },
};
