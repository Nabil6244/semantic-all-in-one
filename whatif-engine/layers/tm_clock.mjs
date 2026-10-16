// TM_CLOCK: the episode's measuring instrument, pinned to a top corner for an act (telemetry look).
//   mode "dual"   two cards, EARTH TIME (amber, top-left) and TRAVELLER (cyan, top-right); each shows the last of its keys
//                 [{ "t": 12.4, "text": "1.3", "unit": "SECONDS", "note": "BACK HOME" }]
//   mode "light"  a dial and a running HH:MM:SS ("LIGHT FROM EARTH"), counting between keys [{ "t", "seconds" }] -- a value
//                 the narration gives; between two keys it runs, so the clock is never frozen while the journey goes on
//   mode "date"   a date top-right ("14 FEBRUARY 1990"), from keys [{ "t", "text" }] or, with "from_clock": true, the
//                 universe date the video is at
//   { "type": "tm_clock", "mode": "dual", "left": { "label": "EARTH TIME", "color": "amber", "keys": [...] },
//     "right": { "label": "TRAVELLER", "color": "cyan", "keys": [...] }, "start": 50, "end": 300 }
import { C, tm, colour, quartOut, stepKey, plateAlpha } from './tm_theme.mjs';

const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
const hms = (s) => { s = Math.max(0, Math.floor(s)); return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((x) => String(x).padStart(2, '0')).join(':'); };

function valueCard(T, g, x, y, side, f, align) {
  const k = stepKey(side.keys, f.t) || side.keys?.[0] || {};
  const w = 0.187 * T.W, h = 0.158 * T.H, bx = align === 'right' ? x - w : x;      // 18.7 % x 15.8 % of the frame (V2 0:31)
  const accent = colour(side.color, align === 'right' ? C.cyan : C.amber);
  T.card(bx, y, w, h, { accent, fill: 'rgba(10,13,18,0.62)' });
  const tx = align === 'right' ? bx + w - 20 * T.S : bx + 20 * T.S;
  T.text(String(side.label || '').toUpperCase(), tx, y + 34 * T.S, { font: T.sans(20, 800), track: 3, color: accent, align, shadow: 0 });
  // a value that just changed flashes brighter for a moment
  const fresh = k.t != null ? 1 - quartOut((f.t - k.t) / 0.6) : 0;
  T.text(k.text ?? '0', tx, y + 86 * T.S, { font: T.mono(50, 700), color: C.white, align, shadow: 0, glow: fresh > 0.05 ? accent : null, alpha: 0.82 + 0.18 * fresh });
  if (k.unit) T.text(String(k.unit).toUpperCase(), tx, y + 112 * T.S, { font: T.sans(17, 800), track: 2, color: '#D6DCE4', align, shadow: 0 });
  if (k.note || side.note) T.text(String(k.note || side.note).toUpperCase(), tx, y + 131 * T.S, { font: T.sans(14, 700), track: 2, color: C.label, align, shadow: 0 });
}

export default {
  type: 'tm_clock',
  space: 'screen',
  over_footage: true,
  create: (def) => {
    if (!['dual', 'light', 'date'].includes(def.mode || 'dual')) throw new Error('tm_clock: mode must be dual, light or date');
    return { def };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), mode = d.mode || 'dual';
    const k = quartOut((f.t - (d.start ?? 0)) / 0.3), s = 0.95 + 0.05 * k;
    const away = d.hide_on_plates ? 1 - plateAlpha(f.spec, f.t) : 1;
    g.save(); g.globalAlpha = f.alpha * k * away;
    if (mode === 'dual') {
      g.save(); g.translate(0.034 * W, 0.05 * H); g.scale(s, s); valueCard(T, g, 0, 0, d.left || {}, f, 'left'); g.restore();
      g.save(); g.translate(0.966 * W, 0.05 * H); g.scale(s, s); valueCard(T, g, 0, 0, d.right || {}, f, 'right'); g.restore();
    } else if (mode === 'light') {
      const keys = d.keys || [];
      let sec = 0;
      if (keys.length) {
        // runs between keys at the pace the two keys set, and holds after the last
        const i = keys.findIndex((x) => x.t > f.t);
        if (i === -1) sec = keys[keys.length - 1].seconds;
        else if (i === 0) sec = keys[0].seconds;
        else { const a = keys[i - 1], b = keys[i]; sec = a.seconds + (b.seconds - a.seconds) * ((f.t - a.t) / (b.t - a.t)); }
      }
      const x = 44 * T.S, y = 36 * T.S, w = 380 * T.S, h = 112 * T.S;
      g.translate(x, y); g.scale(s, s);
      T.card(0, 0, w, h, { fill: 'rgba(10,13,18,0.55)' });
      const cx = 58 * T.S, cy = h / 2, r = 34 * T.S;
      g.strokeStyle = 'rgba(255,255,255,0.55)'; g.lineWidth = 2 * T.S; g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke();
      const ang = ((sec % 86400) / 86400) * Math.PI * 2 - Math.PI / 2;
      g.strokeStyle = colour(d.color, C.amber); g.lineWidth = 3 * T.S; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(ang) * r * 0.86, cy + Math.sin(ang) * r * 0.86); g.stroke();
      T.text(String(d.label || 'LIGHT FROM EARTH').toUpperCase(), 112 * T.S, 34 * T.S, { font: T.sans(16, 800), track: 2.5, color: colour(d.color, C.amber), shadow: 0 });
      T.text(hms(sec), 110 * T.S, 78 * T.S, { font: T.mono(46, 700), color: C.white, shadow: 0 });
      const sub = stepKey(d.notes, f.t);
      if (sub?.text) T.text(String(sub.text).toUpperCase(), 112 * T.S, 101 * T.S, { font: T.mono(15, 600), track: 1.5, color: C.label, shadow: 0 });
    } else {
      let text = stepKey(d.keys, f.t)?.text;
      if (d.from_clock && f.date) { const dt = new Date(f.date); if (!isNaN(dt)) text = `${dt.getUTCDate()} ${MONTHS[dt.getUTCMonth()]} ${dt.getUTCFullYear()}`; }
      if (text) {
        const x = W - 62 * T.S, y = 66 * T.S;
        const w = T.text(String(text).toUpperCase(), x, y, { font: T.mono(30, 600), track: 2, align: 'right', shadow: 0.5 });
        T.line(x - w, y + 14 * T.S, x, y + 14 * T.S, { color: C.white, width: 1.5, alpha: 0.5 });
      }
    }
    g.restore();
  },
};
