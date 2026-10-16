// TM_CITE: the small monospaced citation bottom-left on every shot (telemetry look): what the viewer is looking at and where
// it comes from -- "○ ILLUSTRATION", "○ DIAGRAM · DISTANCES IN LIGHT-TRAVEL TIME, LOGARITHMIC SCALE",
// "○ REAL IMAGE · MARINER 10, 1974 · NASA/JPL-CALTECH". The text changes with the shot (hard, with the cut).
//   { "type": "tm_cite", "segments": [{ "t0": 0, "t1": 6.2, "kind": "ILLUSTRATION", "text": "" }, ...] }
import { C, tm } from './tm_theme.mjs';

export default {
  type: 'tm_cite',
  space: 'screen',
  over_footage: true,
  create: (def) => ({ def, segs: (def.segments || []).slice().sort((a, b) => a.t0 - b.t0) }),
  draw(inst, f) {
    const s = inst.segs.find((x) => f.t >= x.t0 && f.t < x.t1);
    if (!s || !(s.kind || s.text)) return;
    const { g, W, H } = f, T = tm(g, W);
    const words = [s.kind, s.text].filter(Boolean).join(' · ').toUpperCase();
    // as the reference: x 3.6 %, baseline 94 %; a hollow ring for an illustration or a diagram, a filled blue dot for a real photograph
    const x = 0.036 * W, y = 0.945 * H, real = /^REAL/.test(s.kind || '');
    g.save(); g.globalAlpha = f.alpha * 0.72;
    g.beginPath(); g.arc(x + 5 * T.S, y - 5.5 * T.S, 4.5 * T.S, 0, Math.PI * 2);
    if (real) { g.fillStyle = '#3FA9F5'; g.fill(); } else { g.strokeStyle = C.label; g.lineWidth = 1.6 * T.S; g.stroke(); }
    let txt = words;
    while (txt.length > 12 && T.measure(txt, T.mono(17, 600), 1.8) > W * 0.7) txt = txt.slice(0, -2);
    T.text(txt === words ? txt : `${txt.trimEnd()}…`, x + 20 * T.S, y, { font: T.mono(17, 600), track: 1.8, color: C.label, shadow: 0.4 });
    g.restore();
  },
};
