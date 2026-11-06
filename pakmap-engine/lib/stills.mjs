// Pictures that are far bigger than their slot on screen are shrunk once (ffmpeg) before the browser decodes them.
// A 6000 x 4000 photo is 96 MB once decoded, a 12000 px scan 400 MB: a long film full of them kills the browser ("Target crashed").
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

/** { w, h } from a PNG or JPEG header, or null (other formats are left alone). */
export function imageDims(file) {
  let fd;
  try {
    fd = fs.openSync(file, 'r');
    const head = Buffer.alloc(32);
    fs.readSync(fd, head, 0, 32, 0);
    if (head.readUInt32BE(0) === 0x89504e47) return { w: head.readUInt32BE(16), h: head.readUInt32BE(20) };
    if (head[0] === 0xff && head[1] === 0xd8) {
      const size = fs.fstatSync(fd).size, buf = Buffer.alloc(Math.min(size, 1 << 20));
      fs.readSync(fd, buf, 0, buf.length, 0);
      let i = 2;
      while (i + 9 < buf.length) {
        if (buf[i] !== 0xff) { i++; continue; }
        const m = buf[i + 1];
        if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
        i += 2 + buf.readUInt16BE(i + 2);
      }
    }
  } catch { /* unreadable: served as it is */ } finally { if (fd != null) fs.closeSync(fd); }
  return null;
}

/** The file to serve for a still: itself, or a copy no wider than 2 x the widest slot it fills when it is bigger than that. */
export function stillFile(m, { ffmpeg = 'ffmpeg' } = {}) {
  if (m.small !== undefined) return m.small || m.file;
  m.small = null;
  const cap = Math.max(1200, Math.round((m.maxW || 1920) * 2));
  const d = imageDims(m.file);
  if (!d || (d.w <= cap && d.h <= cap * 1.2 && d.w * d.h <= 12e6)) return m.file;
  const png = /\.png$/i.test(m.file);
  m.smallDir = m.smallDir || fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-still-'));
  const out = path.join(m.smallDir, `s.${png ? 'png' : 'jpg'}`);
  const r = spawnSync(ffmpeg, ['-v', 'error', '-y', '-i', m.file, '-vf', `scale='min(${cap},iw)':-2:flags=lanczos`, '-frames:v', '1', ...(png ? [] : ['-q:v', '2']), out], { encoding: 'utf8' });
  if (r.status === 0 && fs.existsSync(out)) { m.small = out; m.mime = png ? 'image/png' : 'image/jpeg'; }
  return m.small || m.file;
}
