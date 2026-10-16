// Node side of video shots: cuts each clip into JPEG frames just before it is needed (scaled and cropped to the video size),
// serves them to the page, and deletes them once the shot is over, so disk use does not grow with the length of the video.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { videoShots } from './lib/shots.mjs';

const run = (cmd, args) => new Promise((resolve, reject) => {
  const p = spawn(cmd, args, { stdio: ['ignore', 'ignore', 'pipe'] });
  let err = '';
  p.stderr.on('data', (d) => { err += d; });
  p.on('error', reject);
  p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}: ${err.trim().slice(-400)}`))));
});
export const resolveMedia = (file, mediaDir) => (path.isAbsolute(file) ? file : path.join(mediaDir, file));

export function createCutter({ spec, mediaDir, ffmpeg = 'ffmpeg', tmpRoot = os.tmpdir() }) {
  const { width: W, height: H, fps } = spec;
  const root = fs.mkdtempSync(path.join(tmpRoot, 'whatif-footage-'));
  const vids = videoShots(spec), state = new Map(), problems = [], stats = { cut: 0, frames: 0 };
  for (const { s } of vids) if (!fs.existsSync(resolveMedia(s.file, mediaDir))) problems.push(`shot ${s.id}: file not found: ${resolveMedia(s.file, mediaDir)}`);
  async function cut({ s, i }) {
    const dir = path.join(root, String(i)); fs.mkdirSync(dir, { recursive: true });
    const sp = s.speed || 1, len = (s.end - s.start) * sp + 0.5;
    await run(ffmpeg, ['-y', '-loglevel', 'error', ...(s.loop ? ['-stream_loop', '-1'] : []), '-ss', String(s.in_s || 0), '-i', resolveMedia(s.file, mediaDir), '-t', len.toFixed(3), '-an',
      '-vf', `fps=${fps},scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},setsar=1`, '-q:v', '2', '-start_number', '0', path.join(dir, '%d.jpg')]);
    const count = fs.readdirSync(dir).filter((n) => n.endsWith('.jpg')).length;
    if (!count) throw new Error(`shot ${s.id}: no frames could be read from ${s.file}`);
    stats.cut += 1; stats.frames += count;
    return { dir, count };
  }
  return {
    problems, stats,
    async ensure(t, { keepAll = false } = {}) {
      for (const v of vids) {
        const live = t >= v.s.start - 0.5 && t <= v.s.end;
        if (live && !state.has(v.i)) state.set(v.i, { ready: cut(v) });
        if (!live && !keepAll && state.has(v.i) && t > v.s.end) {
          const x = await state.get(v.i).ready.catch(() => null);
          if (x) fs.rmSync(x.dir, { recursive: true, force: true });
          state.delete(v.i);
        }
      }
      for (const v of vids) if (state.has(v.i) && t >= v.s.start - 0.5 && t <= v.s.end) state.get(v.i).value = await state.get(v.i).ready;
    },
    frameFile(i, k) { const s = state.get(i); return s && s.value ? path.join(s.value.dir, `${Math.min(Math.max(0, k), s.value.count - 1)}.jpg`) : null; },
    cleanup() { fs.rmSync(root, { recursive: true, force: true }); },
  };
}
