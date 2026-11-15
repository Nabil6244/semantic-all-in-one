// Sky Sim text kit (docs/skysim/PLAN.md 3.4): very sparse, light type over a held scene.
//   sk_stats      top-left block of 1-4 rows { rows: [{ label, value }] }: a small tracked label over a larger light value
//   sk_readout    the same, one row, top-right
//   sk_clocks     twin running clocks top-right { rate, labels: [here, far] } (time dilation)
//   sk_title      spaced caps title above the sky object { text }
//   sk_scalering  dashed circle at `ratio` of the sky object's size, labelled { ratio, label }
//   sk_leader     a label with a leader line to a sky object too small to see { text }
//   sk_subtitle   one centred sentence { text }
// Every value is computed by skysim/physics.py; these layers only draw.
import { clamp01 } from './tm_theme.mjs';

const FONT = 'StarMapSans';            // Montserrat VF: light weights for values, medium for tracked labels
const font = (px, w, S) => `${w} ${Math.round(px * S)}px ${FONT}, sans-serif`;
const ease = (x) => { const k = clamp01(x); return 1 - (1 - k) ** 3; };
const LABEL = 'rgba(196,204,214,0.72)';
const RING = '#8FC4F2';

function shadow(g, S, on = 0.6) { g.shadowColor = `rgba(0,0,0,${on})`; g.shadowBlur = 10 * S; g.shadowOffsetY = 1.5 * S; }

/** The sky shot this layer belongs to (by its start), and where that shot drew its sky object. */
function anchorOf(f) {
  const t0 = (f.def.start ?? 0) + 0.01;
  const s = (f.spec.shots || []).find((x) => t0 >= x.start && t0 < x.end) || f.shot;
  return s && s._anchor ? s._anchor : null;
}

function rowsBlock(f, rows, anchor) {
  const { g, W, H } = f, S = H / 1080, right = anchor === 'tr';
  const x = right ? W - 104 * S : 104 * S;
  let y = 92 * S;
  g.save(); g.textAlign = right ? 'right' : 'left'; g.textBaseline = 'alphabetic';
  rows.forEach((r, i) => {
    const k = ease((f.t - (f.def.start ?? 0) - 0.15 - 0.16 * i) / 0.6);
    g.globalAlpha = (f.alpha ?? 1) * k;
    const lift = (1 - k) * 8 * S;
    shadow(g, S, 0.5);
    g.letterSpacing = `${3 * S}px`; g.font = font(13, 600, S); g.fillStyle = LABEL;
    g.fillText(String(r.label).toUpperCase(), x, y + lift);
    g.letterSpacing = `${0.6 * S}px`; g.font = font(30, 300, S); g.fillStyle = '#FFFFFF';
    g.fillText(String(r.value).toUpperCase(), x, y + 36 * S + lift);
    y += 74 * S;
  });
  g.restore();
}

const make = (type, check, draw) => ({ type, space: 'screen', create: (def) => { check(def); return { def }; }, draw });

const sk_stats = make('sk_stats', (d) => { if (!Array.isArray(d.rows) || !d.rows.length) throw new Error('sk_stats: "rows" is required'); },
  (inst, f) => rowsBlock(f, inst.def.rows.slice(0, 4), inst.def.anchor === 'tr' ? 'tr' : 'tl'));

const sk_readout = make('sk_readout', (d) => { if (!Array.isArray(d.rows) || !d.rows.length) throw new Error('sk_readout: "rows" is required'); },
  (inst, f) => rowsBlock(f, inst.def.rows.slice(0, 1), inst.def.anchor === 'tl' ? 'tl' : 'tr'));

const YEAR = 365.25 * 86400;
const two = (n) => String(n).padStart(2, '0');
const hereClock = (s) => `${two(Math.floor(s / 3600))}:${two(Math.floor(s % 3600 / 60))}:${two(Math.floor(s % 60))}`;
function farClock(s) {
  if (s >= YEAR) { const y = Math.floor(s / YEAR); return `${y} y ${Math.floor((s - y * YEAR) / 86400)} d`; }
  if (s >= 86400) return `${Math.floor(s / 86400)} d ${Math.floor(s % 86400 / 3600)} h`;
  return `${Math.floor(s / 3600)} h ${Math.floor(s % 3600 / 60)} m`;
}
const sk_clocks = make('sk_clocks', (d) => { if (!(Number(d.rate) > 0)) throw new Error('sk_clocks: "rate" must be > 0'); },
  (inst, f) => {
    const d = inst.def, here = Math.max(0, f.t - (d.start ?? 0)) + (Number(d.offset_s) || 0), [a, b] = d.labels || ['TIME HERE', 'FAR AWAY'];
    rowsBlock(f, [{ label: a, value: hereClock(here) }, { label: b, value: farClock(here * Number(d.rate)) }], d.anchor === 'tl' ? 'tl' : 'tr');
  });

const sk_title = make('sk_title', (d) => { if (!String(d.text || '').trim()) throw new Error('sk_title: "text" is required'); },
  (inst, f) => {
    const { g, W, H } = f, S = H / 1080, a = anchorOf(f);
    const y = Math.max(H * 0.16, a ? a.y - Math.max(a.r * 1.5, a.r + 46 * S) - 26 * S : H * 0.3);
    const k = ease((f.t - (f.def.start ?? 0)) / 0.9);
    g.save(); g.globalAlpha = (f.alpha ?? 1) * k; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.letterSpacing = `${(5 + 3 * k) * S}px`; g.font = font(22, 500, S); g.fillStyle = '#FFFFFF'; shadow(g, S);
    g.fillText(String(inst.def.text).toUpperCase(), W / 2, y);
    g.restore();
  });

const sk_scalering = make('sk_scalering', (d) => { if (!(Number(d.ratio) > 0)) throw new Error('sk_scalering: "ratio" must be > 0'); },
  (inst, f) => {
    const a = anchorOf(f);
    if (!a) return;
    const { g, H } = f, S = H / 1080, r = a.r * Number(inst.def.ratio), k = ease((f.t - (f.def.start ?? 0) - 0.8) / 0.8);
    if (k <= 0) return;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * k; g.strokeStyle = RING; g.lineWidth = 1.6 * S; g.setLineDash([5 * S, 5 * S]);
    g.lineDashOffset = -f.t * 4 * S;                    // the dashes creep round slowly
    g.beginPath(); g.arc(a.x, a.y, Math.max(r, 3 * S), 0, Math.PI * 2); g.stroke();
    if (inst.def.label) {
      const ly = a.y + Math.max(a.r * 1.8, a.r + 60 * S) + 18 * S;
      g.setLineDash([4 * S, 5 * S]); g.beginPath(); g.moveTo(a.x - 200 * S, ly); g.lineTo(a.x - 150 * S, ly); g.stroke();
      g.textAlign = 'left'; g.textBaseline = 'middle'; g.letterSpacing = `${3 * S}px`; g.font = font(14, 600, S); g.fillStyle = RING; shadow(g, S, 0.5);
      g.fillText(String(inst.def.label).toUpperCase(), a.x - 138 * S, ly);
    }
    g.restore();
  });

const sk_leader = make('sk_leader', (d) => { if (!String(d.text || '').trim()) throw new Error('sk_leader: "text" is required'); },
  (inst, f) => {
    const a = anchorOf(f);
    if (!a) return;
    const { g, H } = f, S = H / 1080, k = ease((f.t - (f.def.start ?? 0) - 0.5) / 0.7);
    const x0 = a.x - a.r - 10 * S, x1 = x0 - 70 * S * k;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * clamp01(k * 1.4); g.strokeStyle = 'rgba(230,234,240,0.85)'; g.lineWidth = 1.2 * S;
    g.beginPath(); g.moveTo(x0, a.y); g.lineTo(x1, a.y); g.stroke();
    g.textAlign = 'right'; g.textBaseline = 'middle'; g.letterSpacing = `${3 * S}px`; g.font = font(13, 600, S); g.fillStyle = '#E6EAF0'; shadow(g, S, 0.5);
    g.fillText(String(inst.def.text).toUpperCase(), x1 - 10 * S, a.y);
    g.restore();
  });

function wrap(g, text, maxW) {
  const out = []; let cur = '';
  for (const w of String(text).split(/\s+/).filter(Boolean)) {
    const nx = cur ? `${cur} ${w}` : w;
    if (cur && g.measureText(nx).width > maxW) { out.push(cur); cur = w; } else cur = nx;
  }
  if (cur) out.push(cur);
  return out.slice(0, 2);
}
const sk_subtitle = make('sk_subtitle', (d) => { if (!String(d.text || '').trim()) throw new Error('sk_subtitle: "text" is required'); },
  (inst, f) => {
    const { g, W, H } = f, S = H / 1080;
    g.save(); g.font = font(33, 400, S); g.letterSpacing = `${0.3 * S}px`;
    const ls = wrap(g, inst.def.text, W * 0.62), lh = 44 * S, y0 = H * 0.865 - (ls.length - 1) * lh / 2;
    g.globalAlpha = f.alpha ?? 1; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#FFFFFF'; shadow(g, S, 0.75);
    ls.forEach((s, i) => g.fillText(s, W / 2, y0 + i * lh));
    g.restore();
  });

// the landscape rung card: the distance big and thin at the top left, two short facts under it
const sk_rungcard = make('sk_rungcard', (d) => { if (!String(d.value || '').trim()) throw new Error('sk_rungcard: "value" is required'); },
  (inst, f) => {
    const { g, H } = f, S = H / 1080, d = inst.def, x = 46 * S;
    const k = ease((f.t - (d.start ?? 0)) / 0.8);
    g.save(); g.textAlign = 'left'; g.textBaseline = 'alphabetic'; shadow(g, S, 0.45);
    g.globalAlpha = (f.alpha ?? 1) * k;
    g.letterSpacing = `${(6 - 2 * k) * S}px`; g.font = font(84, 200, S); g.fillStyle = '#FFFFFF';
    g.fillText(String(d.value).toUpperCase(), x, 150 * S);
    g.letterSpacing = `${0.4 * S}px`; g.font = font(24, 500, S); g.fillStyle = 'rgba(232,236,242,0.94)';
    (d.lines || []).slice(0, 3).forEach((ln, i) => {
      const ki = ease((f.t - (d.start ?? 0) - 0.35 - 0.2 * i) / 0.6);
      g.globalAlpha = (f.alpha ?? 1) * ki; g.fillText(String(ln), x, (198 + 34 * i) * S);
    });
    g.restore();
  });

export { sk_stats, sk_readout, sk_clocks, sk_title, sk_scalering, sk_leader, sk_subtitle, sk_rungcard };
