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
