// Hybrid Map / Weather: frames that are nothing but one full-screen video clip skip the browser.
//
// Under Hybrid footage (media_full with cover_ui) the map, its layers and the cards are all covered. When the clip is fully
// faded in, is a video (no push-in: kenburns "auto" gives a push-in to stills only), fills the frame at the output size and
// nothing is drawn over it (no watermark, no debug HUD, no graphic the caller says draws on footage), the page would draw
// exactly that clip frame -- the same JPEG file the page itself would load. The renderer sends that file straight to the
// encoder: the map is rendered only where it can be seen. Every other frame (map, dissolves, stills, graphics on footage)
// is drawn by the page as before. Off for pakMap specs (no spec.hybrid) and with spec.footage_shortcut === false.

import fs from 'node:fs';
import path from 'node:path';
import { mediaKey } from './events.mjs';
import { footageAlpha, fitFrame, resolveKenBurns } from './hybrid.mjs';
import { clipFrame } from './anim.mjs';
import { materializeClip } from './media.mjs';
import { TIMING } from './style.mjs';

/** Width and height of a JPEG (its first SOF marker), or null. */
export function jpegSize(file) {
  let buf;
  try { buf = fs.readFileSync(file); } catch { return null; }
  if (buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xff) { i++; continue; }
    const m = buf[i + 1];
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
    if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
    i += 2 + buf.readUInt16BE(i + 2);
  }
  return null;
}

/**
 * (t) => the clip frame file to use as frame t, or null when the page must draw it.
 * busy(t): the caller's own graphics drawn over footage at t (Weather's credit chip, Teamplate titles ...).
 */
export function footageShortcut(spec, events, media, { busy = () => false } = {}) {
  const none = () => null;
  const wm = spec.watermark;
  if (!spec.hybrid || spec.footage_shortcut === false || spec.debug_hud || (wm && wm.text && wm.enabled !== false)) return none;
  const all = events || [];
  const fulls = all.filter((e) => e.type === 'media_full');
  if (!fulls.length) return none;
  const W = Math.round(spec.width * (spec.pixel_scale || 1)), H = Math.round(spec.height * (spec.pixel_scale || 1));
  const sizeOk = new Map();   // clip folder -> its frames are exactly the output size
  return (t) => {
    const live = fulls.filter((e) => t >= e.t_in && t < e.t_out);
    if (live.length !== 1) return null;
    const e = live[0];
    if (e.cover_ui !== true || footageAlpha(e, t, all, e.dissolve_s ?? TIMING.dissolve) < 1) return null;
    const info = media.index[mediaKey(e.media, e.start_s ?? 0)];
    if (!info || info.kind !== 'video' || resolveKenBurns(e, info).kenburns) return null;
    if (busy(t)) return null;
    const m = media.files[info.id];
    if (!m) return null;
    if (m.lazy && !m.dir) materializeClip(m, { ffmpeg: spec.ffmpeg || 'ffmpeg', fps: spec.fps });
    if (!m.dir) return null;
    const idx = info.fit ? fitFrame(t, e.t_in, spec.fps, info.count, info.rate) : clipFrame(t, e.t_in, spec.fps, info.count, e.loop);
    let n = Math.max(1, idx + 1);
    if (m.count) n = Math.min(n, m.count);   // as the page's media server clamps a lazy clip
    const f = path.join(m.dir, `${String(n).padStart(5, '0')}.jpg`);
    if (!fs.existsSync(f)) return null;
    if (!sizeOk.has(m.dir)) { const s = jpegSize(f); sizeOk.set(m.dir, !!s && s.w === W && s.h === H); }
    return sizeOk.get(m.dir) ? f : null;
  };
}
