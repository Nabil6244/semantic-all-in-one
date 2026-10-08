// Re-rendering only what changed. The video is cut into short chunks (whole frames, CHUNK_S long); each chunk gets a
// fingerprint of everything its pixels depend on, worked out the same way the page works them out:
//   * for every frame: the date in space, the camera (only while the map shows), how much of the map shows, and which
//     footage shows with how much opacity and at which frame of its clip;
//   * every layer on screen in the chunk (after its start/end are moved off the footage, as the page does), in draw order,
//     with the contents of any picture or clip it shows;
//   * the frame size and rate, the world, the encoder settings, the GPU mode and the renderer's own code and assets.
// A chunk whose fingerprint is in the cache is reused as it is; the rest are drawn. Anything left out of a fingerprint
// would show a stale picture, so when in doubt something is put in (the price is only drawing a chunk again).
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { planFootage, clipFrameIndex } from './footage.mjs';
import { createClock } from './clock.mjs';
import { buildWorld } from './world.mjs';
import { createCamera } from './camera.mjs';
import { trajectoryLookup } from './paths.mjs';
import { createRegistry, defaultLayers } from './layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';

export const CHUNK_S = 4;
const MARGIN_S = 0.25;                      // a layer this close to a chunk counts as in it (frame rounding, nothing more)

/** Frames 0..total-1 cut into chunks of CHUNK_S: [{ i, k0, k1 }] (k1 exclusive). */
export function planChunks(total, fps, chunkS = CHUNK_S) {
  const n = Math.max(1, Math.round(chunkS * fps)), out = [];
  for (let k0 = 0, i = 0; k0 < total; k0 += n, i++) out.push({ i, k0, k1: Math.min(total, k0 + n) });
  return out;
}

/** A file's fingerprint: its size and a hash of its first and last megabyte (media is copied afresh for every render, so
 *  dates mean nothing; a whole-file hash of a long clip would cost seconds for nothing). */
const fileMemo = new Map();
export function fileFingerprint(file) {
  if (!file) return null;
  let st;
  try { st = fs.statSync(file); } catch { return 'missing'; }
  const memo = `${file}|${st.size}|${st.mtimeMs}`;
  if (fileMemo.has(memo)) return fileMemo.get(memo);
  const h = crypto.createHash('sha1').update(String(st.size));
  const fd = fs.openSync(file, 'r'), MB = 1 << 20, buf = Buffer.alloc(Math.min(MB, st.size));
  try {
    fs.readSync(fd, buf, 0, buf.length, 0); h.update(buf);
    if (st.size > MB) { const n = fs.readSync(fd, buf, 0, buf.length, Math.max(0, st.size - MB)); h.update(buf.subarray(0, n)); }
  } finally { fs.closeSync(fd); }
  const out = h.digest('hex');
  fileMemo.set(memo, out);
  return out;
}

/** The renderer's own code and assets: a change to any of them redraws everything. */
export function engineFingerprint(root) {
  const h = crypto.createHash('sha1');
  const walk = (dir, contents) => {
    if (!fs.existsSync(dir)) return;
    for (const name of fs.readdirSync(dir).sort()) {
      const f = path.join(dir, name), st = fs.statSync(f);
      if (st.isDirectory()) walk(f, contents);
      else { h.update(path.relative(root, f) + '|' + st.size); if (contents) h.update(fs.readFileSync(f)); }
    }
  };
  for (const f of ['page.js', 'page.html', 'cutter.mjs']) { const p = path.join(root, f); if (fs.existsSync(p)) h.update(f).update(fs.readFileSync(p)); }
  walk(path.join(root, 'lib'), true);
  walk(path.join(root, 'layers'), true);
  walk(path.join(root, 'assets'), false);                  // textures, catalogs, fonts: names and sizes
  const three = path.join(root, 'node_modules', 'three', 'package.json');
  if (fs.existsSync(three)) h.update(fs.readFileSync(three));
  return h.digest('hex');
}

const MEDIA_KEYS = ['image', 'video', 'file', 'model'];
const VOLATILE = new Set(['video_frames', 'card_index']);    // written by the cutter after the fingerprints are taken

/** spec -> one fingerprint per chunk (hex), in chunk order. mediaDir resolves media names; extra = what else changes
 *  pixels outside the spec (the engine's code, the GPU mode). */
export function chunkFingerprints(spec, chunks, { mediaDir, extra = '' } = {}) {
  const fps = spec.fps, fp = planFootage(spec);
  const clock = createClock(fp.mapClock(spec.clock));
  const world = buildWorld(spec.world, { date: clock.utc(fp.mu(0)) });
  const camAt = createCamera(world, { fov_deg: spec.fov_deg || 40, ...fp.mapCamera(spec.camera) }, { trajectory: trajectoryLookup(world, spec.layers || []) });
  const registry = registerBuiltins(createRegistry());
  const media = (name) => (name ? fileFingerprint(path.isAbsolute(name) ? name : path.join(mediaDir || '', path.basename(name))) : null);
  const withMedia = (def) => {
    const out = {};
    for (const [k, v] of Object.entries(def)) if (!VOLATILE.has(k)) out[k] = v;
    for (const k of MEDIA_KEYS) if (def[k]) out[k] = media(def[k]);   // by content: the app renumbers media files when one is added or removed
    return out;
  };
  // the layers as the page draws them: defaults added, starts and ends moved off the footage
  const layers = defaultLayers(spec).map((d) => ((d.over_footage ?? registry.get(d.type)?.over_footage) ? { def: d, over: true } : { def: fp.adjustLayer(d), over: false }));
  const global = JSON.stringify({ w: spec.width, h: spec.height, fps, fov: spec.fov_deg || 40, world: spec.world, wm: spec.watermark || null,
    preset: spec.x264_preset || 'medium', crf: spec.crf ?? 18, tex: spec.texture_dir || null, extra });
  const out = [];
  for (const c of chunks) {
    const h = crypto.createHash('sha1').update(global);
    let mapShows = false;
    for (let k = c.k0; k < c.k1; k++) {
      const t = k / fps, cover = fp.coverage(t), ma = fp.mapAlpha(t), date = clock.utc(fp.mu(t));
      h.update(`|${k}|${date.toISOString()}|${ma.toFixed(6)}`);
      for (const { beat: b, alpha } of cover) h.update(`|f${b.i}:${alpha.toFixed(6)}:${b.kind === 'video' ? clipFrameIndex(b, t, fps) : 'still'}`);
      if (ma > 0.001) {
        mapShows = true;
        world.setTime(date);
        const cam = camAt(fp.mu(t));
        h.update(`|c${cam.anchor}:${cam.position.join(',')}:${cam.target.join(',')}:${cam.up.join(',')}`);
      }
    }
    const t0 = c.k0 / fps - MARGIN_S, t1 = (c.k1 - 1) / fps + MARGIN_S;
    for (const { def, over } of layers) {
      if (!over && !mapShows) continue;                     // the map is hidden for the whole chunk: its layers do not show
      if ((def.start ?? -Infinity) > t1 || (def.end ?? Infinity) < t0) continue;
      h.update('|L' + JSON.stringify(withMedia(def)));
    }
    for (const b of fp.beats) {
      if (b.t1 < t0 || b.t0 > t1) continue;
      // the authored entry plus its worked-out timing (not the links to its neighbours: back-to-back clips point at each other)
      const { prevAdjacent, nextAdjacent, ...own } = b;
      h.update('|F' + JSON.stringify(withMedia(own)) + (nextAdjacent ? `>${nextAdjacent.i}` : '') + (prevAdjacent ? `<${prevAdjacent.i}` : ''));
    }
    out.push(h.digest('hex'));
  }
  return out;
}
