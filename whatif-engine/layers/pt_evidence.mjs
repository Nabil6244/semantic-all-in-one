// PT_EVIDENCE: a statement, report or reported fact on a dark plate (Phase 3.2). A tracked source label with an accent mark, then the line as large
// left-aligned type that arrives word by word on the narrator's own timing, with the key fact picked out in the accent colour and underlined on its
// word. One layer carries the whole line as `beats` (its clauses): the label and the rule stay while the text moves from one beat to the next, so a
// long line never cuts between unrelated cards.
//   { "type": "pt_evidence", "start": 3, "end": 12, "kicker": "OWNER REPORTS", "accent": "#7fc4ff",
//     "beats": [{ "text": "Some owners report cracks along the fold", "from": 3.1, "to": 6, "times": [3.1, 3.3, ...] (absolute s per word), "hl": "cracks" }] }
import { tm, clamp01, quartOut } from './tm_theme.mjs';
import { ptFont } from './pt_feature.mjs';

export default {
  type: 'pt_evidence',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.beats) || !def.beats.length) throw new Error('pt_evidence: "beats" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, a = d.start ?? 0, b = d.end ?? a + 5, t = f.t;
    const inK = quartOut((t - a) / 0.25), outK = clamp01((b - t) / 0.4), K = Math.min(inK, outK);
    if (K <= 0.002) return;
    const L = !!d.light, INK = L ? '#161A21' : '#FFFFFF', accent = d.accent || (L ? '#1F63D6' : '#7fc4ff'), left = W * 0.085, maxW = W * 0.8;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * K;
    const vg = g.createRadialGradient(W * 0.3, H * 0.5, H * 0.1, W * 0.5, H * 0.5, W * 0.75);       // a gentle vignette keeps the type on a calm ground
    vg.addColorStop(0, 'rgba(10,14,22,0)'); vg.addColorStop(1, L ? 'rgba(0,0,0,0)' : 'rgba(0,0,0,0.5)'); g.fillStyle = vg; g.fillRect(0, 0, W, H);
    const cy = H * 0.5;
    const panelK = quartOut((t - a) / 0.3);                                                          // a frosted panel holds the statement (nothing is drawn that the narration does not say)
    g.save(); g.globalAlpha *= panelK; g.fillStyle = L ? 'rgba(255,255,255,0.92)' : 'rgba(14,20,32,0.55)'; if (L) { g.shadowColor = 'rgba(20,30,50,0.16)'; g.shadowBlur = 40 * S; g.shadowOffsetY = 10 * S; } g.beginPath(); g.roundRect(left - 70 * S, cy - H * 0.27, W * 0.86, H * 0.54, 26 * S); g.fill(); g.shadowColor = 'transparent';
    g.strokeStyle = L ? 'rgba(20,30,50,0.08)' : 'rgba(255,255,255,0.10)'; g.lineWidth = 2 * S; g.stroke(); g.restore();
    const rule = quartOut((t - a) / 0.9) * H * 0.4;                                                // the accent rule grows from the middle
    g.fillStyle = accent; g.fillRect(left - 34 * S, cy - rule / 2, 5 * S, rule);
    if (d.kicker) {
      const kk = quartOut((t - a - 0.1) / 0.5);
      g.fillStyle = accent; g.globalAlpha *= kk; g.beginPath(); g.arc(left + 11 * S, cy - H * 0.19 - 12 * S, 11 * S, 0, 7); g.fill(); g.globalAlpha = (f.alpha ?? 1) * K;
      T.text(String(d.kicker).toUpperCase(), left + 40 * S, cy - H * 0.19, { font: ptFont(S, 38, 700, 'sans'), track: 7, color: accent, shadow: 0, alpha: kk });
    }
    // the beat on screen: the last one whose first word has come, until the next beat's first word
    const beats = d.beats; let bi = 0;
    for (let i = 0; i < beats.length; i++) if (t >= (beats[i].times?.[0] ?? beats[i].from) - 0.05) bi = i;
    const drawBeat = (bt, alpha, lift) => {
      const words = String(bt.text).split(/\s+/); let px = 92;
      const font = (p) => ptFont(S, p, 700, 'sans'), sp = () => T.measure(' ', font(px));
      const wrap = () => { const L = []; let cur = []; let w = 0; for (const x of words) { const ww = T.measure(x, font(px)); if (cur.length && w + sp() + ww > maxW) { L.push(cur); cur = []; w = 0; } w += (cur.length ? sp() : 0) + ww; cur.push(x); } if (cur.length) L.push(cur); return L; };
      let lines = wrap(); while (lines.length > 3 && px > 44) { px -= 4; lines = wrap(); }
      const lh = px * 1.22 * S, y0 = cy - ((lines.length - 1) * lh) / 2 + px * S * 0.3;
      const hl = String(bt.hl || '').toLowerCase().split(/\s+/).filter(Boolean); let idx = 0;
      const hlSet = new Set(); if (hl.length) { const lw = words.map((x) => x.toLowerCase().replace(/[^a-z0-9.%$]/g, '')); const hw = hl.map((x) => x.replace(/[^a-z0-9.%$]/g, '')); for (let i = 0; i + hw.length <= lw.length; i++) if (hw.every((x, j) => lw[i + j] === x)) { for (let j = 0; j < hw.length; j++) hlSet.add(i + j); break; } }
      let hlX0 = null, hlX1 = 0, hlY = 0, hlT = null;
      lines.forEach((ws, li) => {
        let x = left; const y = y0 + li * lh;
        ws.forEach((w) => {
          const at = bt.times?.[idx] ?? (bt.from + idx * 0.25), k = quartOut((t - at) / 0.4), ww = T.measure(w, font(px));
          if (k <= 0.002) {                                                                          // not yet said: the word waits, dim, so the whole line can be read ahead of the voice
            g.save(); g.globalAlpha *= alpha * 0.2; T.text(w, x, y + lift, { font: font(px), color: INK, shadow: 0 }); g.restore();
          } else {
            const hi = hlSet.has(idx), warm = hi ? clamp01((t - at) / 0.5) : 0;
            g.save(); g.globalAlpha *= alpha * (0.2 + 0.8 * k);
            T.text(w, x, y + (1 - k) * 8 * S + lift, { font: font(px), color: hi ? accent : INK, shadow: L ? 0 : 0.35, glow: hi && warm > 0.5 ? 'rgba(127,196,255,0.35)' : null });
            g.restore();
          }
          if (hlSet.has(idx)) { if (hlX0 === null) { hlX0 = x; hlY = y; hlT = at; } hlX1 = x + ww; }
          x += ww + sp(); idx++;
        });
      });
      if (hlX0 !== null && hlT !== null) {                                                           // the key fact is underlined on its word
        const s = quartOut((t - hlT - 0.15) / 0.55);
        if (s > 0) { g.save(); g.globalAlpha *= alpha; g.fillStyle = accent; g.fillRect(hlX0, hlY + 14 * S + lift, (hlX1 - hlX0) * s, 5 * S); g.restore(); }
      }
    };
    if (beats.length > 1) {                                                                         // where the line is: one dot per beat, the current one lit
      beats.forEach((_, i) => { g.save(); g.globalAlpha *= i === bi ? 1 : 0.28; g.fillStyle = i === bi ? accent : INK; g.beginPath(); g.arc(left + 12 * S + i * 30 * S, cy + H * 0.215, 7 * S, 0, 7); g.fill(); g.restore(); });
    }
    const bt = beats[bi], nxt = beats[bi + 1], endAt = nxt ? (nxt.times?.[0] ?? nxt.from) - 0.05 : b;
    const fade = nxt ? clamp01((endAt - t) / 0.3) : 1;                                                // the old beat lifts away just before the next one's first word
    drawBeat(bt, fade, -(1 - fade) * 16 * S);
    g.restore();
  },
};
