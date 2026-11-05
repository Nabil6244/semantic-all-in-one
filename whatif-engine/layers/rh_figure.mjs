// RH_FIGURE: a stick figure. pose: stand | look | flinch | sit | sleep | walk | run. "moves": [{ at, pose }] changes pose (0.3 s blend).
//   { "type": "rh_figure", "pose": "stand", "x": 0.4, "set": "bedroom", "size": 0.34, "facing": "right", "tag": "YOU", "eyes": "red",
//     "walk_to": 0.7, "moves": [{ "at": 2, "pose": "flinch" }] }
// x = horizontal centre (fraction of W); the feet rest on the ground line of "set" (or "ground" as a fraction of H). walk_to glides x over the layer's life.
import { poseAt, skeleton, drawFigure, drawChair, drawTag, applyCam, lineWidth, setGround, smooth, palOf, RED, WHITE } from '../lib/rhkit.mjs';
import { tm } from './tm_theme.mjs';
export default {
  type: 'rh_figure', space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const start = d.start ?? 0, end = d.end ?? start + 4, lw = lineWidth(H);
    const x0 = (d.x ?? 0.5), x1 = d.walk_to ?? x0, x = (x0 + (x1 - x0) * smooth((f.t - start) / Math.max(0.1, end - start))) * W;
    const ground = (d.ground ?? setGround(d.set)) * H, size = (d.size ?? 0.34) * H;
    const pose = poseAt(d, f.t), J = skeleton(pose, x, ground, size, d.facing === 'left' ? -1 : 1);
    g.save(); g.globalAlpha = f.alpha ?? 1;
    applyCam(g, W, H, d, f.t);
    if (pose.chair) drawChair(g, J, lw);
    drawFigure(g, J, lw, { color: d.color || WHITE, eye: d.eyes ? (d.eyes === 'red' ? RED : d.eyes) : null, stare: !!d.stare, hollow: !!d.hollow, look: d.look || null, pal: palOf(f, d), seed: d.seed ?? (d.tag_color === 'red' ? 7 : 3), outfit: d.outfit || null, face: d.face || 'neutral' });
    if (d.tag) drawTag(g, String(d.tag).toUpperCase(), J.head[0], J.head[1] - J.r - Math.max(size * 0.16, H * 0.045), Math.max(size * 0.085, H * 0.024), { color: d.tag_color === 'white' ? WHITE : RED, font: T.sans(1, 800).replace(/\d+px/, `${Math.round(Math.max(size * 0.085, H * 0.024))}px`) });
    g.restore();
  },
};
