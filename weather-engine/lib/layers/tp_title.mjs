// Weather Teamplate's title cards, over footage or map (weather/teamplate apply_spec turns each beat's HUD title into one):
//   kind 'keyword': heavy white words appearing one after another, the key word in a red box ("THE [PATH]"), about 3 s;
//   kind 'chapter': a serif italic kicker ("SEPTEMBER 2022") over a tracked title wiped in from the left ("HURRICANE IAN").
// The words are the plan's own title words. Event: {type: 'tp_title', kind, words, accent} | {type: 'tp_title', kind: 'chapter', title, kicker}.
import { TP, keywordLayout, keywordPositions, wordIn, chapterProgress } from '../wxu_tp_style.mjs';

function shadowed(ctx, on) {
  ctx.shadowColor = on ? TP.shadow : 'transparent'; ctx.shadowBlur = on ? 22 : 0; ctx.shadowOffsetY = on ? 3 : 0;
}

function drawKeyword(e, t, h, a) {
  const { ctx } = h, K = TP.keyword;
  const measure = (s, px) => h.measure(s, px, K.weight) + K.spacing * s.length;
  const pos = keywordPositions(keywordLayout(e.words, e.accent, measure));
  const px = keywordLayout(e.words, e.accent, measure).px;
  pos.forEach((w, i) => {
    const k = wordIn(t, e.t_in, i); if (k <= 0) return;
    ctx.save(); ctx.globalAlpha = a * k;
    if (w.accent) {
      const wipe = Math.min(1, (t - e.t_in - i * K.stagger) / K.boxWipe);
      const top = w.y - px * 0.36 - K.boxH / 2;
      shadowed(ctx, true); ctx.fillStyle = TP.red; ctx.fillRect(w.x, top, w.w * Math.max(0, wipe), K.boxH); shadowed(ctx, false);
      if (wipe >= 1) h.text(w.text, w.x + K.boxPadX, w.y, px, TP.white, 'left', K.weight, K.spacing);
    } else {
      shadowed(ctx, true); h.text(w.text, w.x, w.y, px, TP.white, 'left', K.weight, K.spacing);
    }
    ctx.restore();
  });
}

function drawChapter(e, t, h, a) {
  const { ctx } = h, C = TP.chapter;
  let px = C.titlePx;
  while (px > C.minPx && h.measure(e.title, px, C.weight) + C.spacing * e.title.length > C.maxW) px -= 4;
  const p = chapterProgress(t, e.t_in);
  ctx.save(); ctx.globalAlpha = a; shadowed(ctx, true);
  if (e.kicker && p.kicker > 0) {
    ctx.save(); ctx.globalAlpha = a * p.kicker;
    ctx.font = `italic 500 ${C.kickerPx}px ${TP.serif}`; ctx.fillStyle = 'rgba(255,255,255,0.94)'; ctx.textAlign = 'left';
    ctx.letterSpacing = '1px'; ctx.fillText(e.kicker, C.left + C.kickerIndent, C.kickerY); ctx.letterSpacing = '0px';
    ctx.restore();
  }
  if (p.title > 0) {
    const w = h.measure(e.title, px, C.weight) + C.spacing * e.title.length;
    ctx.save(); ctx.beginPath(); ctx.rect(C.left - 10, C.titleY - px * 1.1, (w + 40) * p.title, px * 1.5); ctx.clip();
    h.text(e.title, C.left, C.titleY, px, TP.white, 'left', C.weight, C.spacing);
    ctx.restore();
  }
  ctx.restore();
}

export default {
  type: 'tp_title',
  order: 97,
  overFootage: true,
  validate(e) {
    if (e.kind === 'chapter') return e.title ? [] : ['tp_title (chapter) needs a title'];
    if (e.kind !== 'keyword') return ['tp_title kind must be keyword or chapter'];
    const out = [];
    if (!Array.isArray(e.words) || !e.words.length) out.push('tp_title (keyword) needs words');
    else if (!Number.isInteger(e.accent) || e.accent < 0 || e.accent >= e.words.length) out.push('tp_title accent must be the index of one of its words');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.01, 0.3); if (a <= 0) return;
    if (e.kind === 'chapter') drawChapter(e, t, h, a); else drawKeyword(e, t, h, a);
  },
};
