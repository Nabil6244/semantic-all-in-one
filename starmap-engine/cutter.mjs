// Node side of footage beats: cuts each video beat into frames just before it is needed (scaled and cropped to the video
// size), serves them to the page, and deletes them once the beat is over -- so disk use does not grow with the length of
// the video (the same idea as Hybrid's media_lazy).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { planFootage, extractPlan } from './lib/footage.mjs';

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    let err = '';
    p.stderr.on('data', (d) => { err += d; });
    p.on('error', reject);
    p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}: ${err.trim().slice(-400)}`))));
  });
}

/** Where a beat's file lives: absolute, or in the spec's media folder. */
export function resolveMedia(file, mediaDir) {
  return path.isAbsolute(file) ? file : path.join(mediaDir, file);
}

export function createCutter({ spec, mediaDir, ffmpeg = 'ffmpeg', tmpRoot = os.tmpdir() }) {
  const fp = planFootage(spec);
  const { width: W, height: H, fps } = spec;
  const root = fs.mkdtempSync(path.join(tmpRoot, 'starmap-footage-'));
  const state = new Map();                      // beat index -> { dir, count, ready: Promise }
  const stats = { cut: 0, frames: 0, deleted: 0 };
  const videos = fp.beats.filter((b) => b.kind === 'video');
  for (const b of fp.beats) {
    const f = resolveMedia(b.file, mediaDir);
    if (!fs.existsSync(f)) fp.problems.push(`footage ${b.id}: file not found: ${f}`);
  }

  async function cut(b) {
    const dir = path.join(root, String(b.i));
    fs.mkdirSync(dir, { recursive: true });
    const { fromS, durS, rate } = extractPlan(b, fps);
    const fit = b.fit === 'contain'
      ? `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:black`
      : `scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H}`;
    await run(ffmpeg, ['-y', '-loglevel', 'error', ...(b.loop ? ['-stream_loop', '-1'] : []), '-ss', fromS.toFixed(3), '-i', resolveMedia(b.file, mediaDir),
      '-t', durS.toFixed(3), '-an', '-vf', `fps=${rate},${fit},setsar=1`, '-q:v', '2', '-start_number', '0', path.join(dir, '%d.jpg')]);
    const count = fs.readdirSync(dir).filter((n) => n.endsWith('.jpg')).length;
    if (!count) throw new Error(`footage ${b.id}: no frames could be read from ${b.file} at ${fromS.toFixed(2)} s`);
    stats.cut += 1; stats.frames += count;
    return { dir, count };
  }

  return {
    plan: fp,
    stats,
    /** Make sure every video beat on screen at narration t is cut; drop the ones that are over (or not yet needed). */
    async ensure(t, { keepAll = false } = {}) {
      for (const b of videos) {
        const live = t >= b.t0 - 0.5 && t <= b.t1;
        if (live && !state.has(b.i)) state.set(b.i, { ready: cut(b) });
        if (!live && !keepAll && state.has(b.i) && t > b.t1) {
          const s = await state.get(b.i).ready.catch(() => null);
          if (s) { fs.rmSync(s.dir, { recursive: true, force: true }); stats.deleted += 1; }
          state.delete(b.i);
        }
      }
      for (const b of videos) if (state.has(b.i) && t >= b.t0 - 0.5 && t <= b.t1) state.get(b.i).value = await state.get(b.i).ready;
    },
    /** The file for /footage/<beat>/<k>.jpg (the last frame is held if the clip is shorter than the beat). */
    frameFile(i, k) {
      const s = state.get(i);
      if (!s || !s.value) return null;
      return path.join(s.value.dir, `${Math.min(Math.max(0, k), s.value.count - 1)}.jpg`);
    },
    cleanup() { fs.rmSync(root, { recursive: true, force: true }); },
  };
}
