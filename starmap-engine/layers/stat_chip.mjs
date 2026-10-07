// STAT_CHIP: a number panel (yellow figure, white line under it) that can count up.
//   { "type": "stat_chip", "value": 384400, "unit": "KM", "label": "EARTH TO MOON", "corner": "bl",
//     "count_up": { "t0": 12, "t1": 14, "from": 0 }, "decimals": 0 }
// value may also be text ("3 ASTRONAUTS"); corner: tl / tr / bl / br, or x / y (top-left, 1920-wide units).
import { progressAt } from '../lib/timing.mjs';

const fmt = (v, dec) => v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });

export default {
  type: 'stat_chip',
  space: 'screen',
  create: (def) => { if (def.value == null) throw new Error('stat_chip: "value" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, W, H } = f;
    let big = String(d.value);
    if (typeof d.value === 'number') {
      const from = d.count_up?.from ?? 0, k = d.count_up ? progressAt(d.count_up, f.t, f.mu) : 1;
      big = fmt(from + (d.value - from) * k, d.decimals ?? 0);
    }
    if (d.unit) big += ` ${d.unit}`;
    const c = d.corner || 'bl', right = c.endsWith('r'), top = c.startsWith('t');
    const x = d.x != null ? d.x * u.S : right ? W - 63 * u.S : 44 * u.S;
    const y = d.y != null ? d.y * u.S : top ? 190 * u.S : H - 66 * u.S - 168 * u.S;
    f.g.save(); f.g.globalAlpha = f.alpha;
    f.u.panel(x, y, big, d.label || '', { bigPx: 78, smallPx: 24, h: 168, minW: 260, align: d.x != null ? 'left' : right ? 'right' : 'left' });
    f.g.restore();
  },
};
