// RH_ANIMAL: a solid white animal silhouette (deer, dog) with a glowing eye. pose: stand | head_low | stare | walk | raise_paw.
//   { "type": "rh_animal", "animal": "deer", "pose": "stand", "x": 0.7, "size": 0.5, "ground": 0.8, "facing": "left", "eye": "yellow", "walk_to": 0.5 }
import { applyCam, smooth } from '../lib/rhkit.mjs';
import { drawAnimal, ANIMAL_NAMES, YELLOW } from '../lib/rhart.mjs';
import { RED, palOf } from '../lib/rhkit.mjs';
import { toner } from '../lib/rhrooms.mjs';
// colour looks: a muted bone colour that belongs to the scene (white only in the white-on-black looks)
const animalFill = (pal) => (pal ? (toner(pal).day ? '#cbbfa8' : '#b7b1a3') : '#F2F2F2');
export default {
  type: 'rh_animal', space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, start = d.start ?? 0, end = d.end ?? start + 4;
    const x0 = d.x ?? 0.6, x1 = d.walk_to ?? x0, x = (x0 + (x1 - x0) * smooth((f.t - start) / Math.max(0.1, end - start))) * W;
    const kind = ANIMAL_NAMES.includes(d.animal) ? d.animal : 'deer';
    let pose = d.pose || 'stand'; for (const m of d.moves || []) if (f.t >= m.at) pose = m.pose;
    g.save(); g.globalAlpha = f.alpha ?? 1; applyCam(g, W, H, d, f.t);
    drawAnimal(g, kind, pose, x, (d.ground ?? 0.8) * H, (d.size ?? 0.5) * H, d.facing === 'right' ? 1 : -1, f.t, { eye: d.eye === 'red' ? RED : d.eye === 'none' ? null : YELLOW, fill: animalFill(palOf(f, d)) });
    g.restore();
  },
};
