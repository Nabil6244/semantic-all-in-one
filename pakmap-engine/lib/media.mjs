// Pictures and clips for photo cards, filmstrips, stickers and full-screen interludes (node side).
// Pictures are served as they are. Video clips are cut into JPEG frames at the render's frame
// rate up front, so a given frame of the video always shows the same frame of the clip
// (deterministic, and no <video> element timing in the browser).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { mediaRefs, mediaKey } from './events.mjs';
import { DataError } from './datasets.mjs';
import { fitRate } from './hybrid.mjs';

export const IMAGE_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'];
export const VIDEO_EXT = ['.mp4', '.mov', '.m4v', '.webm', '.mkv'];
export const kindOf = (file) => (IMAGE_EXT.includes(path.extname(file).toLowerCase()) ? 'image' : VIDEO_EXT.includes(path.extname(file).toLowerCase()) ? 'video' : null);

const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp' };
export const mimeOf = (file) => MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';

/**
 * Work out every media file the events use. Returns { index, files } where index maps the key the
 * page uses ("path@start") to { id, kind, count?, fps? } and files maps id -> disk path / frame dir.
 */
export function prepareMedia(spec, { baseDir = '.', ffmpeg = 'ffmpeg', workDir = null, lazy = false, ffprobe = 'ffprobe' } = {}) {
  const fps = spec.fps, index = {}, files = {};
  const uses = new Map(); // key -> { path, start_s, maxW, seconds, who, lastUse }; maxW doubles at pixel_scale 2 (4K export)
  for (const e of spec.events || []) {
    for (const ref of mediaRefs(e)) {
      const key = mediaKey(ref.path, ref.start_s);
      const u = uses.get(key) || { path: ref.path, start_s: ref.start_s, maxW: 0, seconds: 0, who: e, lastUse: 0 };
      u.maxW = Math.max(u.maxW, ref.maxW * (spec.pixel_scale || 1)); u.seconds = Math.max(u.seconds, e.t_out - e.t_in); u.lastUse = Math.max(u.lastUse, e.t_out); u.fit = u.fit || !!ref.fit;
      uses.set(key, u);
    }
  }
  let n = 0;
  for (const [key, u] of uses) {
    const where = `${u.who.type} "${u.who.id}"`;
    const file = path.resolve(baseDir, u.path), kind = kindOf(file);
    if (!kind) throw new DataError(`${where}: ${u.path} is not a picture or video file (pictures: ${IMAGE_EXT.join(' ')}; videos: ${VIDEO_EXT.join(' ')})`);
    if (!fs.existsSync(file)) throw new DataError(`${where}: ${kind === 'image' ? 'picture' : 'video'} not found: ${u.path} (looked in ${path.dirname(file)})`);
    const id = `m${n++}`;
    if (kind === 'image') { index[key] = { id, kind: 'image' }; files[id] = { file, mime: mimeOf(file) }; continue; }
    if (lazy) {
      // Long videos: a clip's frames are cut when the render first needs them and deleted once its last use has passed, so the disk holds
      // only the clips on screen now, however long the video is. The frame count comes from the clip's length (the server clamps to what exists).
      const probe = spawnSync(ffprobe, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], { encoding: 'utf8' });
      const len = Number.parseFloat(String(probe.stdout || '').trim());
      if (probe.status !== 0 || !(len > 0)) throw new DataError(`${where}: could not read ${u.path}${probe.stderr ? ` (${probe.stderr.trim().split('\n').pop()})` : ''}`);
      const have = Math.max(0, len - u.start_s), rate = u.fit ? fitRate(have, u.seconds) : 1; // a short clip is slowed to fit its slot (fit: "slow"), never looped hard
      const need = u.seconds * rate, frames = Math.max(1, Math.ceil(need * fps) + 1), avail = Math.max(1, Math.floor(have * fps) + 1);
      index[key] = { id, kind: 'video', count: Math.min(frames, avail), fps, ...(u.fit ? { rate, fit: true } : {}) };
      files[id] = { dir: null, lazy: { file, start_s: u.start_s, seconds: need, maxW: u.maxW, frames, where, path: u.path, lastUse: u.lastUse } };
      continue;
    }
    const dir = fs.mkdtempSync(path.join(workDir || os.tmpdir(), `pakmap-clip-${id}-`));
    const frames = Math.max(1, Math.ceil(u.seconds * fps) + 1);
    const r = spawnSync(ffmpeg, ['-v', 'error', '-y', '-ss', String(u.start_s), '-i', file, '-t', String(u.seconds + 1 / fps), '-vf', `fps=${fps},scale='min(${u.maxW},iw)':-2`, '-frames:v', String(frames), '-q:v', '3', path.join(dir, '%05d.jpg')], { encoding: 'utf8' });
    const count = fs.readdirSync(dir).filter((f) => f.endsWith('.jpg')).length;
    if (r.status !== 0 || count === 0) throw new DataError(`${where}: could not read frames from ${u.path}${r.stderr ? ` (${r.stderr.trim().split('\n').pop()})` : ''}`);
    index[key] = { id, kind: 'video', count, fps };
    files[id] = { dir };
  }
  return { index, files };
}

/** Cut the frames of a lazy clip now (a no-op when they exist). Returns the folder. */
export function materializeClip(entry, { ffmpeg = 'ffmpeg', workDir = null, fps }) {
  if (entry.dir && fs.existsSync(entry.dir)) return entry.dir;
  const z = entry.lazy;
  const dir = fs.mkdtempSync(path.join(workDir || os.tmpdir(), 'pakmap-clip-'));
  const r = spawnSync(ffmpeg, ['-v', 'error', '-y', '-ss', String(z.start_s), '-i', z.file, '-t', String(z.seconds + 1 / fps), '-vf', `fps=${fps},scale='min(${z.maxW},iw)':-2`, '-frames:v', String(z.frames), '-q:v', '3', path.join(dir, '%05d.jpg')], { encoding: 'utf8' });
  const count = fs.readdirSync(dir).filter((f) => f.endsWith('.jpg')).length;
  if (r.status !== 0 || count === 0) { fs.rmSync(dir, { recursive: true, force: true }); throw new DataError(`${z.where}: could not read frames from ${z.path}${r.stderr ? ` (${r.stderr.trim().split('\n').pop()})` : ''}`); }
  entry.dir = dir; entry.count = count;
  return dir;
}

/** Delete the frames of every lazy clip whose last use ended before `t` (a second of margin). Returns how many folders went. */
export function releaseClips(files, t) {
  let n = 0;
  for (const entry of Object.values(files)) {
    if (entry.lazy && entry.dir && entry.lazy.lastUse + 1 < t) { fs.rmSync(entry.dir, { recursive: true, force: true }); entry.dir = null; n++; }
  }
  return n;
}

/** Delete every frame folder this render made (lazy or not). Safe to call twice. */
export function disposeMedia(files) {
  for (const entry of Object.values(files || {})) {
    if (entry.dir) { fs.rmSync(entry.dir, { recursive: true, force: true }); entry.dir = null; }
  }
}
