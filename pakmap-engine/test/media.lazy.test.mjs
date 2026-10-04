// Long videos: clip frames are cut when the render needs them and deleted when it is done with them, so the disk holds only the clips on
// screen now. Hybrid Map opts in (spec.media_lazy); everything else keeps cutting its clips up front, exactly as before.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { prepareMedia, materializeClip, releaseClips, disposeMedia } from '../lib/media.mjs';

const have = spawnSync('ffmpeg', ['-version']).status === 0 && spawnSync('ffprobe', ['-version']).status === 0;
const skip = have ? false : 'ffmpeg/ffprobe not found';
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'lazy-test-'));
const clip = (name, secs) => { const f = path.join(dir, name); spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', `testsrc=size=160x90:rate=30:duration=${secs}`, '-pix_fmt', 'yuv420p', f]); return f; };
const framesOf = (d) => fs.readdirSync(d).filter((f) => f.endsWith('.jpg')).length;
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'lazy-work-'));   // private, so other tests rendering at the same time cannot disturb the counts
const mine = () => fs.readdirSync(work);

function spec(events) { return { width: 160, height: 90, fps: 30, duration: 20, events }; }

test('lazy: nothing is cut at start, the frames appear on first use, and go once the clip is finished with', { skip }, () => {
  clip('a.mp4', 2); clip('b.mp4', 2);
  const events = [
    { id: 'a', type: 'media_full', t_in: 1, t_out: 3, media: 'a.mp4' },
    { id: 'b', type: 'media_full', t_in: 10, t_out: 12, media: 'b.mp4' },
  ];
  const before = mine().length;
  const m = prepareMedia(spec(events), { baseDir: dir, lazy: true, workDir: work });
  assert.equal(mine().length, before, 'nothing was cut up front');
  const [ia, ib] = ['a.mp4@0', 'b.mp4@0'].map((k) => m.index[k]);
  assert.ok(ia.kind === 'video' && ia.count > 30 && ia.count <= 61, `frame count from the clip's length: ${ia.count}`);
  const ea = m.files[ia.id];
  assert.equal(ea.dir, null);
  materializeClip(ea, { fps: 30, workDir: work });
  assert.ok(framesOf(ea.dir) >= 60, 'frames exist after the first request');
  assert.equal(m.files[ib.id].dir, null, 'the later clip is still not cut');
  assert.equal(releaseClips(m.files, 2), 0, 'still in use at 2 s');
  assert.equal(releaseClips(m.files, 5), 1, 'finished at 3 s: its frames go');
  assert.equal(ea.dir, null);
  materializeClip(m.files[ib.id], { fps: 30, workDir: work });
  disposeMedia(m.files);
  assert.equal(m.files[ib.id].dir, null);
  assert.equal(mine().length, before, 'no folder is left behind');
});

test('without lazy the clips are cut up front, as before', { skip }, () => {
  clip('c.mp4', 1);
  const m = prepareMedia(spec([{ id: 'c', type: 'media_full', t_in: 0, t_out: 1, media: 'c.mp4' }]), { baseDir: dir, workDir: work });
  const id = m.index['c.mp4@0'].id;
  assert.ok(m.files[id].dir && framesOf(m.files[id].dir) >= 30);
  disposeMedia(m.files);
  assert.equal(fs.existsSync(path.join(m.files[id].dir || 'x')), false);
});

test('fit: a 2 s clip in a 3.5 s slot is slowed (rate 0.571) and cut only as far as it needs; a clip long enough is left alone; PakMap events are never fitted', { skip }, () => {
  clip('short.mp4', 2); clip('long.mp4', 6);
  const events = [
    { id: 's', type: 'media_full', t_in: 0, t_out: 3.5, media: 'short.mp4', fit: 'slow' },
    { id: 'l', type: 'media_full', t_in: 5, t_out: 8.5, media: 'long.mp4', fit: 'slow' },
    { id: 'p', type: 'media_full', t_in: 10, t_out: 13.5, media: 'short.mp4#plain' },
  ];
  events[2].media = 'short.mp4';                      // same file, used by a PakMap-style event (no fit) at another time
  const m = prepareMedia(spec(events), { baseDir: dir, lazy: true, workDir: work });
  const s = m.index['short.mp4@0'], l = m.index['long.mp4@0'];
  assert.ok(s.fit && Math.abs(s.rate - 2 / 3.5) < 0.03, `rate ${s.rate}`);
  assert.ok(l.fit && l.rate === 1);
  assert.ok(s.count <= 62, 'only the material that exists is cut');
  disposeMedia(m.files);
});
