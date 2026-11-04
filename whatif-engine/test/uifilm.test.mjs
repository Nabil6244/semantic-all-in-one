// UI product film pieces: the interface kit (layout, scripted cursor, toggles), pt_words and pt_iconbuild draw at every moment without a NaN,
// and the cursor and toggles follow the script. Run: node --test test/uifilm.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { mockCanvas } from '../lib/mockcanvas.mjs';
import { createRegistry, runLayers } from '../lib/layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';
import { uiDraw, uiLayout, cursorState, glyphFor, SCREEN_H } from '../lib/uikit.mjs';

const reg = registerBuiltins(createRegistry());
const make = (defs) => reg.instantiate(defs, { spec: {}, W: 1280, H: 720, loadImage: async () => null, warn() {} }, { lenient: false, warn() {} });

const UI = { theme: 'dark', accent: '#7a5cff', top: 160, cursor: 'touch',
  components: [{ type: 'header', text: 'Control Center', sub: 'Quick Controls' }, { type: 'list', rows: [{ label: 'Wi-Fi', toggle: false }, { label: 'Bluetooth', toggle: true }, { label: 'Battery', value: '82%' }] },
    { type: 'widget', title: 'Today', big: '9:41', sub: 'Tuesday' }, { type: 'notif', app: 'Messages', title: 'Alex', body: 'Hello' }, { type: 'dock', icons: [{ label: 'Phone' }, { label: 'Camera' }] },
    { type: 'grid', icons: [{ label: 'Mail' }, { label: 'Music' }] }, { type: 'slider', label: 'Brightness', value: 0.4 }, { type: 'clock', time: '9:41' }],
  script: [{ at: 1.5, comp: 1, row: 0 }, { at: 3.0, comp: 1, row: 2 }] };

test('the interface draws at every moment without a broken number', () => {
  for (const t of [0, 0.4, 0.8, 1.5, 1.6, 2.2, 3.0, 3.3, 6]) {
    const { g, bad } = mockCanvas(540, 1170);
    uiDraw(g, UI, t, {});
    assert.deepEqual(bad, [], `t=${t}`);
  }
});

test('components stack from the top without overlapping', () => {
  const r = uiLayout(UI);
  for (let i = 1; i < r.length; i++) assert.ok(r[i].y >= r[i - 1].y + r[i - 1].h, `component ${i} overlaps the one before`);
  assert.ok(r[0].y >= 150 && r[0].y < SCREEN_H);
});

test('the cursor glides to the scripted row, presses, then moves on', () => {
  const rects = uiLayout(UI);
  assert.equal(cursorState(UI, rects, 0), null, 'no cursor before its first move');
  const atPress = cursorState(UI, rects, 1.55), later = cursorState(UI, rects, 2.8);
  assert.ok(atPress && atPress.press > 0, 'pressing at the scripted time');
  assert.ok(later && Math.abs(later.y - atPress.y) > 50, 'travels to the next row');
  assert.equal(cursorState({ ...UI, cursor: false }, rects, 1.55), null, 'cursor:false hides it');
});

test('glyphs come from the label, any label still gets a tile', () => {
  assert.equal(glyphFor('Wi-Fi'), 'wifi');
  assert.equal(glyphFor('Airplane Mode'), 'plane');
  assert.equal(glyphFor('Zebra'), null);
});

test('pt_words types word by word and pt_iconbuild draws every stage', async () => {
  const layers = await make([{ type: 'pt_words', text: 'A brand new interface for everyone', start: 1, end: 6, ink: 'dark' },
    { type: 'pt_iconbuild', icon: 'camera', label: 'Camera', start: 1, end: 7, ink: 'light' }]);
  const texts = [];
  for (const t of [0.5, 1.1, 1.4, 1.9, 2.6, 3.4, 4.5, 5.8, 6.5]) {
    const { g: base, bad } = mockCanvas(1280, 720);
    let n = 0;
    const g = new Proxy(base, { get(o, k) { if (k === 'fillText') return (...a) => { n++; return o.fillText(...a); }; return o[k]; }, set(o, k, v) { o[k] = v; return true; } });
    runLayers(layers.slice(0, 1), { t, W: 1280, H: 720, g, spec: {}, shot: null, claims: [], reserved: [] }, 'draw', () => true, () => {});
    runLayers(layers.slice(1), { t, W: 1280, H: 720, g: base, spec: {}, shot: null, claims: [], reserved: [] }, 'draw', () => true, () => {});
    assert.deepEqual(bad, [], `t=${t}`);
    texts.push(n);
  }
  assert.equal(texts[0], 0, 'nothing before the start');
  assert.ok(texts[1] < texts[4], 'more words appear as time passes');
  await assert.rejects(make([{ type: 'pt_words', text: '  ' }]));
  await assert.rejects(make([{ type: 'pt_iconbuild' }]));
});

test('flat phones: brand layouts from the name, badge above the label, clear of the subtitle band', async () => {
  const { designFor } = await import('../layers/pt_flatphones.mjs');
  assert.equal(designFor({ label: 'iPhone 18 Pro' }), 'iphone');
  assert.equal(designFor({ label: 'Earlier leak', top: 'Google-like' }), 'pixel');
  assert.equal(designFor({ label: 'Galaxy S26 Ultra' }), null);
  const def = { type: 'pt_flatphones', title: 'Price', start: 0, end: 6, phones: [{ label: 'iPhone 18 Pro', text: '$999', top: 'Now', badge: '-20%' }, { label: 'Pixel 11', text: '$799' }] };
  const bottoms = {};
  for (const subs of [false, true]) {
    const spec = { layers: subs ? [def, { type: 'pt_subtitle', chunks: [] }] : [def] };
    const [L] = await reg.instantiate([def], { spec, W: 1280, H: 720, loadImage: async () => null, warn() {} }, { lenient: false, warn() {} });
    const { g: base, bad } = mockCanvas(1280, 720);
    let low = 0, badgeY = Infinity, topY = -Infinity;
    const g = new Proxy(base, { get(o, k) {
      if (k === 'roundRect') return (x, y, w, h, r) => { if (h > 200) low = Math.max(low, y + h); if (Math.abs(h - 44 * 1280 / 1920) < 1) badgeY = Math.min(badgeY, y + h); return o.roundRect(x, y, w, h, r); };
      if (k === 'fillText') return (t, x, y) => { if (t === 'Now') topY = y; return o.fillText(t, x, y); };
      return o[k]; }, set(o, k, v) { o[k] = v; return true; } });
    runLayers([L], { t: 3, W: 1280, H: 720, g, spec, shot: null, claims: [], reserved: [] }, 'draw', () => true, () => {});
    assert.deepEqual(bad, []);
    assert.ok(badgeY < topY - 20, `badge ${badgeY} must sit above the label at ${topY}`);
    bottoms[subs] = low;
  }
  assert.ok(bottoms[true] <= 720 * 0.83, `with subtitles the phones end at ${bottoms[true]}`);
  assert.ok(bottoms[false] > bottoms[true], 'without subtitles they may use the full height');
});
