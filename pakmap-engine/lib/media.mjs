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

export const IMAGE_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'];
export const VIDEO_EXT = ['.mp4', '.mov', '.m4v', '.webm', '.mkv'];
export const kindOf = (file) => (IMAGE_EXT.includes(path.extname(file).toLowerCase()) ? 'image' : VIDEO_EXT.includes(path.extname(file).toLowerCase()) ? 'video' : null);

const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp' };
export const mimeOf = (file) => MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';

/**
 * Work out every media file the events use. Returns { index, files } where index maps the key the
 * page uses ("path@start") to { id, kind, count?, fps? } and files maps id -> disk path / frame dir.
 */
export function prepareMedia(spec, { baseDir = '.', ffmpeg = 'ffmpeg', workDir = null } = {}) {
  const fps = spec.fps, index = {}, files = {};
  const uses = new Map(); // key -> { path, start_s, maxW, seconds, who }
  for (const e of spec.events || []) {
    for (const ref of mediaRefs(e)) {
      const key = mediaKey(ref.path, ref.start_s);
      const u = uses.get(key) || { path: ref.path, start_s: ref.start_s, maxW: 0, seconds: 0, who: e };
      u.maxW = Math.max(u.maxW, ref.maxW); u.seconds = Math.max(u.seconds, e.t_out - e.t_in);
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
