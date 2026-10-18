// Hybrid Map: a map_template flagged over_footage runs on narration time and is drawn above full-screen footage (pakmap-engine/lib).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { footageWindows, shiftedEvent } from '../../pakmap-engine/lib/hybrid.mjs';
import { footageShortcut } from '../../pakmap-engine/lib/footage_pass.mjs';
import { mediaKey } from '../../pakmap-engine/lib/events.mjs';

const clip = { type: 'media_full', t_in: 3, t_out: 8, media: 'a.mp4', cover_ui: true };
const tpl = (extra = {}) => ({ type: 'map_template', id: 'g', t_in: 4, t_out: 7, template: { items: [] }, ...extra });

test('an ordinary template is held under footage, a flagged one is not', () => {
  const w = footageWindows([clip]);
  assert.equal(shiftedEvent(tpl(), 5, w).t_in, 5);                          // frozen: local time 0 all through the clip
  assert.equal(shiftedEvent(tpl({ over_footage: true }), 5, w).t_in, 4);    // real time
  const e = tpl({ over_footage: true });
  assert.equal(shiftedEvent(e, 5, w), e);                                   // the very same object
  assert.equal(shiftedEvent(e, 5, []), e);
});

test('a flagged graphic keeps the page drawing the frame; without it the clip frame goes straight to the encoder', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ovf-'));
  fs.writeFileSync(path.join(dir, '00001.jpg'), Buffer.from('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABQODxIPDRQSEBIXFRQYHjIhHhwcHj0sLiQySUBMS0dARkVQWnNiUFVtVkVGZIhlbXd7gYKBTmCNl4x9lnN+gXz/2wBDARUXFx4aHjshITt8U0ZTfHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHz/wAARCAAkAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDPooorlOkKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD//2Q==', 'base64'));
  const spec = { hybrid: { pause_overlays: true }, width: 64, height: 36, fps: 30 };
  const media = { index: { [mediaKey('a.mp4', 0)]: { kind: 'video', id: 'a', count: 1 } }, files: { a: { dir, count: 1 } } };
  const plain = footageShortcut(spec, [clip], media), flagged = footageShortcut(spec, [clip, tpl({ over_footage: true })], media), unflagged = footageShortcut(spec, [clip, tpl()], media);
  assert.ok(plain(5));                                                      // fully faded in, nothing over it: the shortcut applies
  assert.ok(unflagged(5));                                                  // an ordinary template is under the clip anyway: unchanged
  assert.equal(flagged(5), null);                                           // while the flagged graphic is live the page draws
  assert.ok(flagged(7.5));                                                  // after it ends the shortcut is back
});
