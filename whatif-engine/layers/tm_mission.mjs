// TM_MISSION: the mission card of a journey episode (V4 "What If You Explored a Black Hole", 0:48 -> 7:40), pinned top-right for the whole
// trip: a dim kicker ("MISSION · SGR A*") with a live dot, an amber label ("DISTANCE TO THE EDGE"), one big number that COUNTS between
// beats (208 MILLION KM -> 6.3 MILLION KM -> 2,215 KM -> 0 KM), a status line ("FALLING", "HOVERING · TIME ×100 SLOWER"), and a stage rail
// (APPROACH · PHOTON SPHERE · EDGE · INSIDE · SINGULARITY) with the current stage lit cyan. Frosted card x 77-97 %, y 3-15.6 % of the frame.
//   { "type": "tm_mission", "kicker": "MISSION · SGR A*", "stages": ["APPROACH", "PHOTON SPHERE", "EDGE", "INSIDE", "SINGULARITY"],
//     "keys": [{ "t": 50.2, "value": 27000, "unit": "LIGHT-YEARS", "label": "DISTANCE TO THE EDGE", "status": "FROM EARTH", "stage": 0 }, ...],
//     "start": 48, "end": 460 }
// A value counts from the previous key's value over 1.4 s when the unit is the same; a new unit switches with a short flash.
import { C, tm, colour, quartOut, fmt } from './tm_theme.mjs';

const keyAt = (keys, t) => { let i = -1; for (let k = 0; k < keys.length; k++) if (keys[k].t <= t + 1e-6) i = k; return i; };
export const short = (v) => (Math.abs(v) >= 100 || Number.isInteger(v) ? fmt(Math.round(v), 0) : fmt(v, Math.abs(v) < 10 ? 1 : 0));

export function valueAt(keys, t) {
  const i = keyAt(keys, t);
  if (i < 0) return keys.length ? { k: keys[0], v: keys[0].value, fresh: 0 } : null;
  const k = keys[i], p = keys[i - 1], age = t - k.t;
  const counting = p && p.unit === k.unit && typeof p.value === 'number' && typeof k.value === 'number';
  const v = counting ? p.value + (k.value - p.value) * quartOut(age / (k.count_s ?? 1.4)) : k.value;
  return { k, v, fresh: Math.max(0, 1 - age / 0.6) };
}

export default {
  type: 'tm_mission',
  space: 'screen',
  over_footage: true,
  create: (def) => {
    if (!Array.isArray(def.keys) || !def.keys.length) throw new Error('tm_mission: "keys" (one per beat: t, value, unit) is required');
    for (const k of def.keys) if (typeof k.t !== 'number') throw new Error('tm_mission: every key needs a time "t"');
    return { def, keys: [...def.keys].sort((a, b) => a.t - b.t) };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), now = valueAt(inst.keys, f.t);
    if (!now) return;
    const k0 = quartOut((f.t - (d.start ?? 0)) / 0.35), s = 0.96 + 0.04 * k0;
    // laid out in fractions of the card (V4 0:50: 19.8 % x 12.5 % of the frame): kicker, label, number, status, stage rail with its name
    const x = 0.771 * W, y = 0.031 * H, w = 0.198 * W, h = 0.125 * H, px = x + 0.06 * w, F = h / 90;
    g.save(); g.globalAlpha = f.alpha * k0;
    g.translate(x + w, y); g.scale(s, s); g.translate(-(x + w), -y);
    T.card(x, y, w, h, { r: 8, fill: 'rgba(12,16,22,0.72)', border: 'rgba(255,255,255,0.10)' });
    const px_ = (n) => n * F / T.S;                 // card units -> the theme's 1920-wide px
    T.text(String(d.kicker || 'MISSION').toUpperCase(), px, y + 0.14 * h, { font: T.mono(px_(6.5), 600), track: 2, color: 'rgba(142,153,168,0.75)', shadow: 0 });
    g.fillStyle = colour(d.dot || 'green'); g.globalAlpha *= 0.6 + 0.4 * Math.sin(f.t * 3) ** 2; g.beginPath(); g.arc(x + w - 0.06 * w, y + 0.11 * h, 2.2 * F, 0, Math.PI * 2); g.fill();
    g.globalAlpha = f.alpha * k0;
    const k = now.k;
    T.text(String(k.label || d.label || 'DISTANCE').toUpperCase(), px, y + 0.29 * h, { font: T.mono(px_(7), 700), track: 1.6, color: C.amber, shadow: 0 });
    const big = typeof now.v === 'number' ? `${short(now.v)} ${k.unit || ''}`.trim() : String(now.v);
    let size = px_(20);
    while (size > px_(11) && T.measure(big.toUpperCase(), T.display(size), 1) > w * 0.88) size -= 1;
    T.text(big.toUpperCase(), px, y + 0.52 * h, { font: T.display(size), track: 1, color: C.white, shadow: 0, glow: now.fresh > 0.05 ? 'rgba(0,229,255,0.5)' : null });
    if (k.status) T.text(String(k.status).toUpperCase(), px, y + 0.66 * h, { font: T.mono(px_(6.5), 600), track: 1.1, color: C.label, shadow: 0 });
    const stages = d.stages || [];
    if (stages.length > 1) {
      const rx = px, ry = y + 0.8 * h, rw = w * 0.86, n = stages.length - 1, cur = Math.max(0, Math.min(n, k.stage ?? 0));
      T.line(rx, ry, rx + rw, ry, { color: 'rgba(255,255,255,0.28)', width: 1.2 });
      for (let i = 0; i <= n; i++) {
        const nx = rx + (rw * i) / n;
        if (i === cur) T.node(nx, ry, { color: C.cyan, r: 3.6 * F / T.S });
        else { g.fillStyle = i < cur ? C.white : 'rgba(255,255,255,0.55)'; g.beginPath(); g.arc(nx, ry, (i < cur ? 2.2 : 1.8) * F, 0, Math.PI * 2); g.fill(); }
      }
      const lx = Math.min(rx + rw - 0.1 * w, Math.max(rx + 0.1 * w, rx + (rw * cur) / n));
      T.text(String(stages[cur]).toUpperCase(), lx, y + 0.93 * h, { font: T.mono(px_(5.5), 700), track: 1, color: C.cyan, align: 'center', shadow: 0 });
    }
    g.restore();
  },
};
