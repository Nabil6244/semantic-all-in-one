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

export const BUILTIN_LAYERS = [tm_metric, tm_caption, tm_title, tm_cite, tm_clock, tm_survival, tm_gauge, tm_logaxis, tm_bars, tm_curve, tm_compare, tm_composition, tm_timeline, tm_fade, tm_dial, tm_wave, tm_section, tm_grid, tm_orbitmap, tm_phase, tm_discmap, tm_annotate, tm_template, tm_mission];

export function registerBuiltins(registry) {
  for (const L of BUILTIN_LAYERS) registry.register(L);
  return registry;
}
