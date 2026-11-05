// RH_MARK: annotations -- tag, sight line, countdown ring, danger cross. All in fractions of the frame.
//   { "type": "rh_mark", "kind": "tag", "text": "NORMAL", "x": 0.3, "y": 0.2, "color": "white" }
//   { "type": "rh_mark", "kind": "sight", "from": [0.6, 0.5], "to": [0.3, 0.5] }
//   { "type": "rh_mark", "kind": "ring", "text": "00:03", "x": 0.85, "y": 0.2, "seconds": 3 }
//   { "type": "rh_mark", "kind": "cross", "x": 0.5, "y": 0.5 }
//   { "type": "rh_mark", "kind": "bubble", "text": "COME HERE.", "x": 0.3, "y": 0.3, "to": [0.32, 0.42] }   { "kind": "banner", "text": "DO NOT PET IT" }
import { drawTag, drawSight, drawRing, drawCross, applyCam, lineWidth, clamp01, RED, WHITE } from '../lib/rhkit.mjs';
import { drawBubble, drawBanner } from '../lib/rhart.mjs';
import { tm } from './tm_theme.mjs';
const KINDS = ['tag', 'sight', 'ring', 'cross', 'bubble', 'banner'];
export default {
  type: 'rh_mark', space: 'screen',
  create: (def) => { if (!KINDS.includes(def.kind)) throw new Error(`rh_mark: kind must be one of ${KINDS.join(', ')}`); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), lw = lineWidth(H), age = f.t - (d.start ?? 0);
    const col = d.color === 'white' ? WHITE : RED, px = H * (d.size ?? 0.045);
    g.save(); g.globalAlpha = f.alpha ?? 1; applyCam(g, W, H, d, f.t);
    const fam = T.sans(1, 800).split('px ')[1];
    if (d.kind === 'bubble') drawBubble(g, String(d.text || ''), d.x * W, d.y * H, (d.to?.[0] ?? d.x) * W, (d.to?.[1] ?? d.y + 0.1) * H, px, fam, age);
    else if (d.kind === 'banner') drawBanner(g, String(d.text || '').toUpperCase(), d.x * W, d.y * H, px, fam);
    else if (d.kind === 'tag') drawTag(g, String(d.text || '').toUpperCase(), d.x * W, d.y * H, px, { color: col, font: `800 ${Math.round(px)}px ${T.sans(1, 800).split('px ')[1]}`, fill: !!d.fill });
    else if (d.kind === 'sight') drawSight(g, [d.from[0] * W, d.from[1] * H], [d.to[0] * W, d.to[1] * H], f.t, lw, { color: col, grow: clamp01(age / 0.5) });
    else if (d.kind === 'ring') {
      const secs = Math.max(0.5, d.seconds ?? 3), left = Math.max(0, secs - age), mm = Math.floor(left / 60), ss = Math.floor(left % 60);
      drawRing(g, d.x * W, d.y * H, H * (d.r ?? 0.09), left / secs, lw * 1.3, d.text ?? `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`, `700 ${Math.round(H * 0.03)}px ${T.mono(1).split('px ')[1]}`, { color: col });
    } else drawCross(g, d.x * W, d.y * H, H * (d.r ?? 0.05) * clamp01(age / 0.18 + 0.3), lw, col);
    g.restore();
  },
};
