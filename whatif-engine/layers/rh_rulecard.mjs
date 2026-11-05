// RH_RULECARD: a black typed card. "RULE", a big number, a red line, the rule typed on character by character with a blinking cursor, seven progress dashes.
//   { "type": "rh_rulecard", "number": 3, "text": "Do not turn on the lights.", "start": 20, "end": 25 }
import { drawRuleCard, drawHazardCard, drawTagCard, drawPaperCard, drawSignCard } from '../lib/rhart.mjs';
import { schemeOf, moodOf } from '../lib/rhkit.mjs';
import { tm } from './tm_theme.mjs';
export default {
  type: 'rh_rulecard', space: 'screen',
  create: (def) => { if (!String(def.text || '').trim()) throw new Error('rh_rulecard: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), fam = T.sans(1, 900).split('px ')[1];
    g.save(); g.globalAlpha = f.alpha ?? 1;
    // style (from the video's reference profile): black | dim (over the darkened scene) | hazard | tag | paper | sign; none = by scheme as before
    const st = d.style || (schemeOf(f) === 'colour' || (schemeOf(f) === 'story' && ['day', 'warm', 'dawn'].includes(moodOf(f, d))) ? 'hazard' : 'black');
    const age = f.t - (d.start ?? 0), tot = d.total ?? 7;
    if (st === 'hazard') drawHazardCard(g, W, H, d, age, fam, tot); else if (st === 'tag') drawTagCard(g, W, H, d, age, fam, tot);
    else if (st === 'paper') drawPaperCard(g, W, H, d, age, fam, tot); else if (st === 'sign') drawSignCard(g, W, H, d, age, fam, tot);
    else drawRuleCard(g, W, H, d, age, fam, tot, { dim: st === 'dim' });
    g.restore();
  },
};
