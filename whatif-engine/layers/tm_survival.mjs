// TM_SURVIVAL: the survival clock (telemetry look): a dark frosted card pinned top-left for an act -- "SURVIVAL CLOCK",
// "YOU'D LAST", a big verdict ("SECONDS", "? MIN", "∞") and a row of hazard chips. A chip that becomes lethal turns red and
// flashes three times (150 ms); the verdict changes with the states. It steps back over diagram plates.
//   { "type": "tm_survival", "chips": ["AIR", "TEMPERATURE", "PRESSURE", "ACID"],
//     "states": [{ "t": 30, "verdict": "SECONDS", "sub": "UNPROTECTED, ON THE GROUND", "color": "red", "lethal": ["AIR", "TEMPERATURE"] }],
//     "start": 28, "end": 400, "intro": { "start": 25.5, "end": 31 } }
//   intro: for that long the card is the whole scene, centred and large (42 % x 49 % of the frame, as the reference's survival-clock scene
//   at V1 0:25.5-0:31); then it eases into the top-left corner (3.4 %, 5.6 %, 19 % x 22 %) and stays there for the act.
import { C, tm, colour, quartOut, glideOut, stepKey, plateAlpha } from './tm_theme.mjs';

// tiny line glyphs for the chips (centred on 0,0, about 14 px at 1920)
const GLYPHS = {
  AIR: (g, s) => { g.beginPath(); g.arc(-3 * s, 2 * s, 4 * s, 0, Math.PI * 2); g.moveTo(8 * s, -4 * s); g.arc(5 * s, -4 * s, 3 * s, 0, Math.PI * 2); g.stroke(); },
  OXYGEN: (g, s) => GLYPHS.AIR(g, s),
  TEMPERATURE: (g, s) => { g.beginPath(); g.moveTo(0, -9 * s); g.lineTo(0, 3 * s); g.stroke(); g.beginPath(); g.arc(0, 6 * s, 4 * s, 0, Math.PI * 2); g.fill(); },
  HEAT: (g, s) => GLYPHS.TEMPERATURE(g, s),
  COLD: (g, s) => { for (let a = 0; a < 3; a++) { const r = a * Math.PI / 3; g.beginPath(); g.moveTo(-Math.cos(r) * 9 * s, -Math.sin(r) * 9 * s); g.lineTo(Math.cos(r) * 9 * s, Math.sin(r) * 9 * s); g.stroke(); } },
  PRESSURE: (g, s) => { g.beginPath(); g.arc(0, 4 * s, 9 * s, Math.PI * 1.1, Math.PI * 1.9); g.stroke(); g.beginPath(); g.moveTo(0, 4 * s); g.lineTo(4 * s, -3 * s); g.stroke(); },
  ACID: (g, s) => { g.beginPath(); g.moveTo(0, -9 * s); g.quadraticCurveTo(8 * s, 2 * s, 0, 7 * s); g.quadraticCurveTo(-8 * s, 2 * s, 0, -9 * s); g.stroke(); },
  RADIATION: (g, s) => { for (let a = 0; a < 3; a++) { const r = a * Math.PI * 2 / 3 - Math.PI / 2; g.beginPath(); g.moveTo(0, 0); g.arc(0, 0, 9 * s, r - 0.45, r + 0.45); g.closePath(); g.fill(); } },
  WATER: (g, s) => GLYPHS.ACID(g, s),
  FOOD: (g, s) => { g.beginPath(); g.arc(0, 1 * s, 7 * s, 0, Math.PI * 2); g.stroke(); },
};

export default {
  type: 'tm_survival',
  space: 'screen',
  create: (def) => ({ def, chips: (def.chips || ['AIR', 'TEMPERATURE', 'PRESSURE']).map((c) => String(c).toUpperCase()).slice(0, 6) }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const intro = d.intro, inIntro = intro && f.t < intro.end + 0.7;
    const away = inIntro ? 1 : (d.hide_on_plates === false ? 1 : 1 - plateAlpha(f.spec, f.t));
    const k = quartOut((f.t - (intro ? intro.start : d.start ?? 0)) / 0.4);
    const st = stepKey(d.states, f.t) || {};
    const lethal = new Set((st.lethal || []).map((x) => String(x).toUpperCase()));
    const since = {};          // when each chip last turned lethal, for its flashes
    let prev = new Set();
    for (const x of d.states || []) {
      if (x.t > f.t + 1e-6) break;
      const now = new Set((x.lethal || []).map((c) => String(c).toUpperCase()));
      for (const c of now) if (!prev.has(c)) since[c] = x.t;
      prev = now;
    }
    // the card's box: the corner (V1 0:40 at 1280: x 43, y 40, 247 x 161 -> 3.4 %, 5.6 %, 19.3 % x 22.4 %) or the centred scene card (42 % x 49 %)
    const corner = { x: 0.034 * W, y: 0.056 * H, w: 0.193 * W, h: 0.224 * H }, mid = { x: 0.288 * W, y: 0.178 * H, w: 0.424 * W, h: 0.49 * H };
    const e = intro ? glideOut((f.t - intro.end) / 0.7) : 1;
    const bx = mid.x + (corner.x - mid.x) * e, by = mid.y + (corner.y - mid.y) * e, w = mid.w + (corner.w - mid.w) * e, h = mid.h + (corner.h - mid.h) * e;
    const u = w / (370 * T.S);   // the card's own scale: its content is laid out for a 370 px wide card at 1920
    const fresh = st.t != null ? 1 - quartOut((f.t - st.t) / 0.7) : 0;
    g.save(); g.globalAlpha = f.alpha * k * away;
    g.translate(bx, by);
    T.card(0, 0, w, h, { fill: 'rgba(22,12,9,0.88)', border: fresh > 0.05 ? `rgba(80,210,255,${0.35 + 0.6 * fresh})` : 'rgba(120,200,220,0.32)', r: 14 * u });
    const X = (v) => v * u * T.S, ft = (px) => px * u;
    T.text(String(d.header || 'SURVIVAL CLOCK'), X(21), X(28), { font: T.mono(ft(13), 600), track: 3 * u, color: C.label, shadow: 0 });
    g.fillStyle = C.cyan; g.beginPath(); g.arc(w - X(18), X(23), X(3.4), 0, Math.PI * 2); g.fill();
    T.text(String(d.lead || "YOU'D LAST"), X(21), X(55), { font: T.mono(ft(16), 700), track: 2 * u, color: '#F3E3C3', shadow: 0 });
    const verdict = st.verdict || '—';
    const vcol = colour(st.color, verdict === '—' ? C.white : '#F0525A');
    let vp = 56;
    while (vp > 22 && T.measure(verdict, T.display(ft(vp)), 1.5 * u) > w - X(42)) vp -= 3;
    if (verdict === '—') { g.fillStyle = C.white; g.fillRect(X(21), X(108), X(24), X(5)); }
    else T.text(verdict, X(21), X(116), { font: T.display(ft(vp)), track: 1.5 * u, color: vcol, shadow: 0, glow: fresh > 0.05 ? vcol : null });
    if (st.sub) T.text(String(st.sub).toUpperCase(), X(21), X(144), { font: T.mono(ft(13), 600), track: 1.2 * u, color: '#D8D2C8', shadow: 0 });
    const n = inst.chips.length, gap = X(8), cw = (w - X(42) - gap * (n - 1)) / n, ch = h * 0.215, cy = h - ch - h * 0.07;
    inst.chips.forEach((c, i) => {
      const cx = X(21) + i * (cw + gap), dead = lethal.has(c);
      const age = since[c] != null ? f.t - since[c] : 99;
      const flash = dead && age < 1.3 && Math.floor(age / 0.22) % 2 === 1;     // red on/off three times as it turns lethal
      const col = dead ? '#F0525A' : 'rgba(235,232,226,0.82)';
      g.save();
      g.fillStyle = flash ? 'rgba(240,82,90,0.05)' : dead ? 'rgba(240,82,90,0.16)' : 'rgba(255,255,255,0.03)';
      g.strokeStyle = flash ? 'rgba(240,82,90,0.25)' : col; g.lineWidth = 1.5 * T.S * u; g.beginPath(); g.roundRect(cx, cy, cw, ch, X(8)); g.fill(); g.stroke();
      g.translate(cx + cw / 2, cy + ch * 0.36); g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 1.6 * T.S * u;
      (GLYPHS[c] || GLYPHS.FOOD)(g, T.S * 0.8 * u);
      g.restore();
      let px = 11 * u;
      while (px > 6 && T.measure(c, T.sans(px, 800), 1) > cw - X(8)) px -= 0.5;
      T.text(c, cx + cw / 2, cy + ch * 0.82, { font: T.sans(px, 800), track: 1, color: flash ? 'rgba(240,82,90,0.3)' : col, align: 'center', shadow: 0 });
    });
    g.restore();
  },
};
