// The built-in layers of the What If look. A layer is a module { type, space: 'screen', create(def, ctx), draw(inst, frame) }.
import tm_metric from './tm_metric.mjs';
import tm_caption from './tm_caption.mjs';
import tm_title from './tm_title.mjs';
import tm_cite from './tm_cite.mjs';
import tm_clock from './tm_clock.mjs';
import tm_survival from './tm_survival.mjs';
import tm_gauge from './tm_gauge.mjs';
import tm_logaxis from './tm_logaxis.mjs';
import tm_bars from './tm_bars.mjs';
import tm_curve from './tm_curve.mjs';
import tm_compare from './tm_compare.mjs';
import tm_composition from './tm_composition.mjs';
import tm_timeline from './tm_timeline.mjs';
import tm_fade from './tm_fade.mjs';
import tm_dial from './tm_dial.mjs';
import tm_wave from './tm_wave.mjs';
import tm_section from './tm_section.mjs';
import tm_grid from './tm_grid.mjs';
import tm_orbitmap from './tm_orbitmap.mjs';
import tm_phase from './tm_phase.mjs';
import tm_discmap from './tm_discmap.mjs';
import tm_annotate from './tm_annotate.mjs';
import tm_template from './tm_template.mjs';
import tm_mission from './tm_mission.mjs';
import pt_bench from './pt_bench.mjs';
import pt_feature from './pt_feature.mjs';
import pt_tagline from './pt_tagline.mjs';
import pt_bigtype from './pt_bigtype.mjs';
import pt_reveal from './pt_reveal.mjs';
import pt_card from './pt_card.mjs';
import pt_subtitle from './pt_subtitle.mjs';
import pt_curve from './pt_curve.mjs';
import pt_compare3 from './pt_compare3.mjs';
import pt_badge from './pt_badge.mjs';
import pt_caption from './pt_caption.mjs';
import pt_paper from './pt_paper.mjs';
import pt_flatphones from './pt_flatphones.mjs';
import pt_gauge from './pt_gauge.mjs';
import pt_tweet from './pt_tweet.mjs';
import pt_thermal from './pt_thermal.mjs';
import pt_coststack from './pt_coststack.mjs';
import pt_doc from './pt_doc.mjs';
import pt_glass from './pt_glass.mjs';

export const BUILTIN_LAYERS = [tm_metric, tm_caption, tm_title, tm_cite, tm_clock, tm_survival, tm_gauge, tm_logaxis, tm_bars, tm_curve, tm_compare, tm_composition, tm_timeline, tm_fade, tm_dial, tm_wave, tm_section, tm_grid, tm_orbitmap, tm_phase, tm_discmap, tm_annotate, tm_template, tm_mission, pt_bench, pt_feature, pt_tagline, pt_bigtype, pt_reveal, pt_card, pt_badge, pt_caption, pt_subtitle, pt_curve, pt_compare3, pt_paper, pt_flatphones, pt_gauge, pt_tweet, pt_thermal, pt_coststack, pt_doc, pt_glass];

export function registerBuiltins(registry) {
  for (const L of BUILTIN_LAYERS) registry.register(L);
  return registry;
}
