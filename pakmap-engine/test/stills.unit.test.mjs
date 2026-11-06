import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { imageDims, stillFile } from '../lib/stills.mjs';
import { disposeMedia } from '../lib/media.mjs';

const make = (dir, name, w, h) => {
  const f = path.join(dir, name);
  const r = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', `color=c=red:s=${w}x${h}`, '-frames:v', '1', f]);
  assert.equal(r.status, 0, String(r.stderr));
  return f;
};

test('a picture far bigger than its slot is shrunk once; a normal one is served as it is', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'stills-test-'));
  try {
    const big = make(d, 'big.png', 6000, 4000), jpg = make(d, 'big.jpg', 5000, 3000), small = make(d, 'small.png', 1600, 900);
    assert.deepEqual(imageDims(big), { w: 6000, h: 4000 });
    assert.deepEqual(imageDims(jpg), { w: 5000, h: 3000 });
    const m = { file: big, maxW: 900, mime: 'image/png' };
    const out = stillFile(m);
    assert.notEqual(out, big);
    assert.equal(imageDims(out).w, 1800);                 // 2 x the card's width
    assert.equal(stillFile(m), out);                       // made once
    const m2 = { file: jpg, maxW: 1920, mime: 'image/jpeg' };
    assert.equal(imageDims(stillFile(m2)).w, 3840);
    assert.equal(stillFile({ file: small, maxW: 1920 }), small);
    disposeMedia({ a: m, b: m2 });
    assert.ok(!fs.existsSync(out));
  } finally { fs.rmSync(d, { recursive: true, force: true }); }
});
