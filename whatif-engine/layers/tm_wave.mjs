// TM_WAVE: a signal on a dark plate (telemetry look): a live waveform, or one that dies -- the line flattens and the readout
// turns red ("TIME ON THE SURFACE 0:03:52" then flat). With a timer above it. Also the "noise -> processed signal" pair.
//   { "type": "tm_wave", "label": "TIME ON THE SURFACE", "timer": { "from": 0, "to": 7620, "format": "h:mm:ss" },
//     "die_at": 6.5, "color": "white", "start": 3, "end": 9 }        (die_at: narration time the line goes flat and red)
//   { "type": "tm_wave", "label": "AFTER COMPUTER PROCESSING", "style": "clean", "color": "cyan", "big": "23 MINUTES" }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

const hms = (s) => { s = Math.max(0, Math.floor(s)); return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
export default {
  type: 'tm_wave',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), tt = f.t - (d.start ?? 0);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    const dead = d.die_at != null && f.t >= d.die_at, k = d.die_at != null ? clamp01(1 - (f.t - d.die_at) / 0.5) : 1;
    const col = dead ? C.red : colour(d.color, C.white);
    if (d.label) T.text(String(d.label).toUpperCase(), W / 2, H * 0.3, { font: T.mono(17, 600), track: 3, align: 'center', color: C.label, shadow: 0 });
    if (d.timer) {
      const p = glideOut(tt / ((d.timer.s ?? (d.end - d.start)) || 5)), v = d.timer.from + (d.timer.to - d.timer.from) * p;
      T.text(hms(dead ? d.timer.to : v), W / 2, H * 0.4, { font: T.display(86), color: col, align: 'center', track: 2, glow: dead ? C.red : null });
    }
    const y0 = H * (d.timer ? 0.54 : 0.5), x0 = W * 0.2, x1 = W * 0.8, amp = 38 * T.S * k, style = d.style || 'live';
    g.strokeStyle = col; g.lineWidth = 2.2 * T.S; g.beginPath();
    for (let i = 0; i <= 360; i++) {
      const x = x0 + (x1 - x0) * i / 360, u = i / 360 * 22 + f.t * 3;
      const noise = style === 'noise' ? (Math.sin(u * 7.3) * 0.6 + Math.sin(u * 13.1 + f.t * 9) * 0.5 + Math.sin(u * 29.7) * 0.3) : Math.sin(u);
      const y = y0 + noise * amp * (style === 'noise' ? 1.1 : 1);
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.stroke();
    if (d.big) T.text(String(d.big).toUpperCase(), W / 2, y0 + 150 * T.S, { font: T.display(64), align: 'center', track: 2, glow: 'rgba(255,214,160,0.25)' });
    if (d.sub) T.text(String(d.sub).toUpperCase(), W / 2, y0 + 200 * T.S, { font: T.sans(20, 800), track: 3, align: 'center', color: C.cyan, shadow: 0 });
    g.restore();
  },
};
