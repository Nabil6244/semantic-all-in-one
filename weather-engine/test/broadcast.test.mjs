// Phase 5 broadcast compositions: the lower-third stays inside the frame and above the source line.
import test from 'node:test';
import assert from 'node:assert/strict';
import { headlineLayout, LT } from '../lib/layers/headline.mjs';
import { WX } from '../lib/wx_layout.mjs';

test('the lower-third stays in the frame and above the source line, with or without kicker and sub', () => {
  const sourceTop = 1080 - WX.source.baselineFromBottom - WX.source.h;
  for (const [tw, kw, sw] of [[200, 0, 0], [900, 160, 300], [5000, 400, 4000]]) {
    const L = headlineLayout(tw, kw, sw);
    assert.ok(L.x + L.w <= 1920 - 44, `width ${L.w}`);
    assert.ok(L.top >= 0);
    const bottom = L.sub ? L.sub.y + L.sub.h : L.title.y + L.title.h;
    assert.ok(bottom <= sourceTop, `bottom ${bottom} over the source line at ${sourceTop}`);
    assert.ok(L.w >= LT.minW);
  }
});

test('a place label is left out rather than drawn over a panel or another name', async () => {
  const { default: pl } = await import('../lib/layers/place_label.mjs');
  const calls = [];
  const placed = [];
  const ctx = new Proxy({}, { get: (_t, k) => (k in _t ? _t[k] : () => calls.push(k)), set: (t, k, v) => { t[k] = v; return true; } });
  const h = { ctx, S: 1, project: (lon, lat) => ({ x: lon, y: lat }), measure: () => 100, lifeAlpha: () => 1, vis: () => 1, easeOut: (v) => v,
    clamp01: (v) => Math.max(0, Math.min(1, v)), panel: () => calls.push('panel'), text: () => calls.push('text'), placed: () => placed,
    panels: () => [{ x: 600, y: 400, w: 400, h: 300 }] };
  pl.draw({ lon: 500, lat: 500, text: 'A', t_in: 0, t_out: 9 }, 1, h);        // name right of the dot would hit the panel: drawn on the left
  assert.equal(placed.length, 1); assert.ok(placed[0].x + placed[0].w <= 500);
  pl.draw({ lon: 700, lat: 500, text: 'B', t_in: 0, t_out: 9 }, 1, h);        // the dot is under the panel: left out
  pl.draw({ lon: 505, lat: 505, text: 'C', t_in: 0, t_out: 9 }, 1, h);        // both sides taken (panel, name A): left out
  assert.equal(placed.length, 1);
});
