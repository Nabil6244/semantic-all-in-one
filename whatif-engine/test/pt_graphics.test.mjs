// Review graphics layers (pt_curve, pt_compare3, pt_subtitle): they create from their data, reject bad data, and draw at every moment without a NaN. Run: node --test test/pt_graphics.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { mockCanvas } from '../lib/mockcanvas.mjs';
import { createRegistry } from '../lib/layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';

const reg = registerBuiltins(createRegistry());
import { runLayers } from '../lib/layers.mjs';
const impl = async (def) => reg.instantiate([def], { spec: {}, W: 1280, H: 720, loadImage: async () => null, warn() {} }, { lenient: false, warn() {} });
// draws one frame through the real layer runner; counts the text calls so a layer that draws nothing is noticed
function drawAt(layers, t) {
  const { g: base, bad } = mockCanvas();
  let texts = 0;
  const g = new Proxy(base, { get(o, k) { if (k === 'fillText') return (...a) => { texts++; return o.fillText(...a); }; return o[k]; }, set(o, k, v) { o[k] = v; return true; } });
  runLayers(layers, { t, W: 1280, H: 720, g, spec: {}, shot: null, claims: [], reserved: [] }, 'draw', () => true, () => {});
  return { bad, texts };
}

const CURVE = { type: 'pt_curve', title: 'Crease depth', note: 'Internal test', x_label: 'Time folded', y_label: 'Depth', start: 1, end: 9,
  points: [[0, 0], [0.1, 0.55], [0.3, 0.85], [1, 0.95]], marks: [{ x: 0.3, text: 'Rapid deepening' }], level: { y: 0.95, text: 'Stabilises' } };
const CMP = { type: 'pt_compare3', title: 'Peak brightness', unit: 'nit', start: 1, end: 9,
  cols: [{ label: 'Foldable', value: 300, highlight: true }, { label: 'Max', value: 300 }, { label: 'Pro', value: 280 }] };
const SUB = { type: 'pt_subtitle', chunks: [{ start: 1, end: 3, text: 'the folding part really works well' }, { start: 3, end: 5, text: 'and the hinge feels firm in the hand' }] };

const PAPER = { type: 'pt_paper', start: 1, end: 9 };
const FLAT = { type: 'pt_flatphones', title: 'Charging', start: 1, end: 9, phones: [{ label: 'S26 Ultra', text: '60W', color: '#5b5a86', cams: 4, fill: 0.95, top: '5000mAh' }, { label: 'S27 Ultra', text: '60W', cams: 3, fill: 0.99 }] };
const GAUGE = { type: 'pt_gauge', title: 'Upload speed', unit: 'Mbps', start: 1, end: 9, gauges: [{ label: 'A', value: 30.12 }, { label: 'B', value: 127.51, highlight: true }] };
const TWEET = { type: 'pt_tweet', author: 'Walle', handle: '@x', date: 'Aug 24', text: 'This stems from the new charging optimization, allowing the phone to sustain 55W longer than before.', highlight: 'sustain 55W longer', start: 1, end: 9 };

const THERMAL = { type: 'pt_thermal', title: '30 min gaming', start: 1, end: 9, phones: [{ label: 'A', temp: 41.2 }, { label: 'B', temp: 46.8, highlight: true }] };
const COST = { type: 'pt_coststack', title: 'Bill of materials', total: '$466', start: 1, end: 9, rows: [{ label: 'Display', value: 90 }, { label: 'Camera', value: 120 }, { label: 'Processor', value: 160 }] };

const DOC = { type: 'pt_doc', title: 'Battery listing', chip: 'BIS CERTIFICATION', rows: 7, highlight: 3, stamp: '5G', start: 1, end: 9 };

const GLASS = { type: 'pt_glass', heading: 'Latency', start: 1, end: 9, cards: [{ title: 'iPhone 18 Pro', value: 1.2, unit: 'ms', delta: '-98%', tint: 'teal', x: 0.27, y: 0.2 }, { title: 'iPhone 17 Pro', value: 59, unit: 'ms', tint: 'green', x: 0.73, y: 0.2 }] };

for (const def of [CURVE, CMP, SUB, PAPER, FLAT, GAUGE, TWEET, THERMAL, COST, DOC, GLASS]) {
  test(`${def.type}: draws text inside its window and nothing bad at any moment`, async () => {
    const layers = await impl(def);
    for (const t of [0, 0.5, 1, 1.4, 2, 3.5, 4.2, 6, 8.9, 12]) assert.deepEqual(drawAt(layers, t).bad, [], `t=${t}`);
    const inside = def.type === 'pt_subtitle' ? 2 : 5;
    if (def.type !== 'pt_paper') assert.ok(drawAt(layers, inside).texts > 0, 'something is drawn while visible');
  });
}

test('bad data is rejected with a clear message', async () => {
  await assert.rejects(() => impl({ type: 'pt_curve', points: [[0, 0]] }), /at least two/);
  await assert.rejects(() => impl({ type: 'pt_compare3', cols: [{ label: 'a', value: 1 }] }), /at least two/);
  await assert.rejects(() => impl({ type: 'pt_subtitle', chunks: [] }), /chunks/);
});

test('infographic layers reject bad data', async () => {
  await assert.rejects(() => impl({ type: 'pt_flatphones', phones: [] }), /phones/);
  await assert.rejects(() => impl({ type: 'pt_gauge', gauges: [] }), /gauges/);
  await assert.rejects(() => impl({ type: 'pt_tweet', text: ' ' }), /text/);
});

test('infographic layers draw without throwing (the layer runner would hide an error)', async () => {
  for (const def of [FLAT, GAUGE, TWEET, PAPER, THERMAL, COST, DOC, GLASS]) {
    const layer = reg.get ? reg.get(def.type) : null;
    const mod = (await import(`../layers/${def.type}.mjs`)).default, inst = mod.create(def);
    for (const t of [1, 1.5, 2.5, 4, 8.8]) { const { g } = mockCanvas(); assert.doesNotThrow(() => mod.draw(inst, { g, W: 1280, H: 720, t, alpha: 1 }), `${def.type} t=${t}`); }
    void layer;
  }
});

test('pt_card wraps a long disclaimer inside the card width', async () => {
  const { wrapLines } = await import('../layers/pt_card.mjs');
  const g = { measureText: (s) => ({ width: s.length * 10 }) };
  const long = 'This is a conceptual trailer made by a fan. It is not affiliated with, endorsed by or sponsored by the manufacturer.';
  const out = wrapLines(g, [long, 'Short.'], 300);
  assert.ok(out.length > 3);
  assert.ok(out.every((l) => l.length * 10 <= 300 || !l.includes(' ')));
  assert.equal(out.join(' '), `${long} Short.`.replace(/\s+/g, ' '));
  assert.equal(out[out.length - 1], 'Short.');
});

test('pt_flatphones: a row of four phones stays inside the frame', async () => {
  const { mockCanvas } = await import('../lib/mockcanvas.mjs');
  const mod = (await import('../layers/pt_flatphones.mjs')).default;
  const { g } = mockCanvas();
  const xs = [];
  const orig = g.fillRect?.bind(g);
  const rr = g.roundRect?.bind(g);
  g.roundRect = (x, y, w, h, r) => { xs.push([x, x + w]); return rr ? rr(x, y, w, h, r) : undefined; };
  const def = { type: 'pt_flatphones', start: 0, end: 5, phones: [1, 2, 3, 4].map((i) => ({ label: `P${i}`, cams: 3, badge: 'Yes' })) };
  mod.draw(mod.create(def), { g, W: 1920, H: 1080, t: 3, alpha: 1 });
  if (orig) g.fillRect = orig;
  assert.ok(xs.length > 0);
  assert.ok(xs.every(([a, b]) => a >= 0 && b <= 1920), JSON.stringify(xs.slice(0, 6)));
});

// word-timed builds (product_trailer/wordcue.py): an item with `at` waits for its word, items without it keep the stagger
test('pt_flatphones / pt_bench / pt_tweet: items with "at" appear on their word, not before', async () => {
  const flat = { type: 'pt_flatphones', start: 1, end: 9, phones: [{ label: 'Black', at: 0 }, { label: 'Blue', at: 3, badge: 'NEW', badge_at: 5 }] };
  const bench = { type: 'pt_bench', title: 'Geekbench', start: 1, end: 9, rows: [{ label: 'Exynos', value: 14000, at: 0 }, { label: 'Snapdragon', value: 12856, at: 3 }] };
  for (const def of [flat, bench]) {
    const layers = await impl(def);
    const early = drawAt(layers, 2.5), late = drawAt(layers, 5.0);
    assert.equal(early.bad.length + late.bad.length, 0, def.type);
    assert.ok(late.texts > early.texts, `${def.type}: the second item is drawn only after its word (${early.texts} -> ${late.texts})`);
  }
  const fl = await impl(flat);
  assert.ok(drawAt(fl, 7).texts > drawAt(fl, 5.5).texts, 'the badge lands on its own word');
  const tw = await impl({ ...TWEET, highlight_at: 4 });
  assert.equal(drawAt(tw, 3).bad.length + drawAt(tw, 6).bad.length, 0);
});

// a building canvas (product_trailer/canvas.py): a continued scene is on screen at once; kept / dimmed / replaced facts draw without NaN
test('pt_flatphones: "cont" shows the phones at once, "keep" never fades out, dim / fresh / was draw cleanly', async () => {
  const base = { type: 'pt_flatphones', start: 4, end: 9, phones: [{ label: 'S27', text: '10MP', top: '12GB RAM', badge: 'Exynos', fresh: ['text', 'top'], dim: ['badge'], was: { text: '??MP' }, at: 2 }, { label: 'S27 Plus', text: '10MP', fresh: ['text'], at: 2.2 }] };
  const plain = await impl({ ...base, phones: base.phones.map(({ fresh, dim, was, at, ...p }) => p) });
  const cont = await impl({ ...base, cont: true, t0: 0, fade_in: 0 });
  assert.equal(drawAt(plain, 4.001).texts, 0, 'a fresh scene enters from nothing');
  assert.ok(drawAt(cont, 4.001).texts > 0, 'a continued scene is already there');
  for (const t of [4.001, 5, 6.1, 6.3, 8.99]) assert.equal(drawAt(cont, t).bad.length, 0, `no NaN at ${t}`);
  const keep = await impl({ ...base, keep: true, fade_out: 0 });
  assert.ok(drawAt(keep, 8.99).texts > 0, 'a kept scene is still drawn at its last frame');
});

// colour cards (gap 3): cards pop on their words, "?" drops in, an older model's colour slides over its match and away again
test('pt_swatches: cards on their words, "?" and an older colour draw cleanly', async () => {
  const def = { type: 'pt_swatches', title: 'S27 Ultra colour options', start: 1, end: 15, q_at: 6,
    cards: [{ name: 'Black', color: '#2b2b2e', at: 0.2 }, { name: 'Blue', color: '#3f6fb5', at: 1, ref: { label: 'Galaxy S26 Ultra', name: 'Sky Blue', color: '#8fc3ea', at: 8 } },
      { name: 'Light Pink', color: '#e9b4c4', at: 1.6 }, { name: 'White', color: '#ecebea', at: 2.2 }, { name: 'Violet', color: '#b98ce0', tag: 'Online Exclusive', at: 4 }] };
  const L = await impl(def);
  const counts = [1.5, 2.5, 4.0, 6.0, 7.5, 9.5, 14.9].map((t) => { const r = drawAt(L, t); assert.equal(r.bad.length, 0, `no NaN at ${t}`); return r.texts; });
  assert.ok(counts[1] < counts[2] && counts[2] < counts[3], `more cards as the colours are said (${counts})`);
  assert.ok(counts[4] > counts[3], 'the "?" marks add text');
  assert.ok(counts[5] > counts[4], 'the older colour card adds its label');
  assert.ok(counts[6] < counts[5], 'and slides away again');
  await assert.rejects(() => impl({ type: 'pt_swatches', cards: [] }));
});

// lens callouts (gap 4): each callout appears on its word, "??" turns into the answer at set_at
test('pt_lenses: callouts on their words and a "??" that resolves draw cleanly', async () => {
  const def = { type: 'pt_lenses', start: 1, end: 12, phones: [{ label: 'Galaxy S27 Plus', color: '#7a2f45' }, { label: 'Galaxy S27', color: '#7a2f45' }],
    lenses: [{ kind: 'ultrawide', cap: 'ultrawide', value: '12MP', at: 0.5 }, { kind: 'main', cap: 'main', value: null, at: 2 }, { kind: 'telephoto', cap: '3x telephoto', value: '10MP', was: '??', at: 4, set_at: 7 }] };
  const L = await impl(def);
  const n = [1.4, 2.5, 4.0, 6.0, 8.5, 11.9].map((t) => { const r = drawAt(L, t); assert.equal(r.bad.length, 0, `no NaN at ${t}`); return r.texts; });
  assert.ok(n[0] < n[1] && n[1] < n[2] && n[2] < n[3], `callouts come in on their words (${n})`);
  assert.equal(n[4], n[3], 'the answer replaces the "??", it does not add a line');
  await assert.rejects(() => impl({ type: 'pt_lenses', phones: [] }));
});

// ring highlight (gap 5): follows the 3D lens it is told to, falls back to its own spot, waits for its word
test('pt_ring: tracks frame.parts lenses, falls back, waits for "at"', async () => {
  const L = await impl({ type: 'pt_ring', part: 'lens', index: -1, at: 1, x: 0.5, y: 0.4, r: 0.07, start: 2, end: 8 });
  const arcs = (t, parts) => {
    const { g: base, bad } = mockCanvas(); const seen = [];
    const g = new Proxy(base, { get(o, k) { if (k === 'arc') return (...a) => { seen.push(a); return o.arc(...a); }; return o[k]; }, set(o, k, v) { o[k] = v; return true; } });
    runLayers(L, { t, W: 1280, H: 720, g, spec: {}, shot: null, claims: [], reserved: [], parts }, 'draw', () => true, () => {});
    assert.equal(bad.length, 0); return seen;
  };
  assert.equal(arcs(2.5, null).length, 0, 'nothing before its word');
  const fb = arcs(4, null);
  assert.equal(fb.length, 1); assert.ok(Math.abs(fb[0][0] - 640) < 1 && Math.abs(fb[0][1] - 288) < 1, 'fallback spot');
  const tr = arcs(4, { lenses: [{ x: 100, y: 100, r: 20 }, { x: 900, y: 300, r: 30 }] });
  assert.ok(Math.abs(tr[0][0] - 900) < 1 && Math.abs(tr[0][1] - 300) < 1, 'round the last (zoom) lens');
  const off = arcs(4, { lenses: [{ x: 100, y: 100, r: 20 }, null] });
  assert.ok(Math.abs(off[0][0] - 640) < 1, 'a lens facing away: the fallback spot');
  const ln = await impl({ type: 'pt_lenses', start: 0, end: 9, phones: [{ label: 'S27' }], lenses: [{ kind: 'telephoto', value: '10MP', at: 0.5, ring_at: 3 }] });
  for (const t of [2, 3.2, 8]) assert.equal(drawAt(ln, t).bad.length, 0);
});

// two-sided figures (gap 17): left and right figures land on their words, the small lines follow
test('pt_sides: each figure on its word, both inks draw cleanly', async () => {
  for (const ink of ['dark', 'light']) {
    const L = await impl({ type: 'pt_sides', ink, start: 1, end: 8, items: [{ value: '$1,299', sub: 'S26 Ultra Launch Price', side: 'left', at: 0.3 }, { value: '$1,499', sub: 'S27 Ultra Leaked Price', side: 'right', at: 3 }] });
    const n = [1.1, 2.0, 3.5, 5.0, 7.9].map((t) => { const r = drawAt(L, t); assert.equal(r.bad.length, 0, `no NaN at ${t} (${ink})`); return r.texts; });
    assert.equal(n[0], 0, 'nothing before the first word');
    assert.ok(n[1] > 0 && n[3] > n[1], `the second figure comes on its word (${n})`);
  }
  await assert.rejects(() => impl({ type: 'pt_sides', items: [] }));
});
