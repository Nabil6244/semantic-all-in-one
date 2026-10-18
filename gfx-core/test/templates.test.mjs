import test from 'node:test';
import assert from 'node:assert/strict';
import { loadLibrary, validate } from '../lib/library.mjs';
import { createGfx, drawGfx } from '../lib/render.mjs';
import { mockCanvas } from '../lib/mockcanvas.mjs';
import { TEXT_STYLE_NAMES } from '../lib/textstyles.mjs';
import { theme } from '../lib/theme.mjs';

const LIB = loadLibrary();

test('the library is valid and covers charts, facts, geo, editorial and every text style', () => {
  assert.ok(LIB.size >= 30, `only ${LIB.size} templates`);
  assert.deepEqual([...LIB.values()].flatMap(validate), []);
  for (const s of TEXT_STYLE_NAMES.filter((x) => x !== 'plain')) assert.ok(LIB.has(`text_${s}`), `no template for text style ${s}`);
  for (const id of ['rank_bars', 'month_columns', 'trend_line', 'fact_card', 'region_label', 'chapter_next', 'quote_card']) assert.ok(LIB.has(id), id);
});

test('every template draws at 7 moments without a broken number, and restores the theme', () => {
  const before = theme();
  for (const t of LIB.values()) {
    const inst = createGfx(t, {});
    const { g, bad } = mockCanvas(1920, 1080);
    const project = (lon, lat) => ({ x: 960 + lon * 6, y: 540 - lat * 6 });
    for (const k of [0, 0.05, 0.2, 0.4, 0.6, 0.85, 1]) drawGfx(inst, g, 1920, 1080, inst.len * k, { project, follow: [0.5, 0.5] });
    assert.deepEqual(bad.slice(0, 3), [], `${t.id} drew a broken number`);
  }
  assert.equal(theme(), before);
});

test('a slot the template cannot use keeps its default instead of failing', () => {
  const t = LIB.get('rank_bars'), warns = [];
  const inst = createGfx(t, { rows: [{ label: 'A', value: 3 }, { label: 'B', value: 9 }], title: 'X' }, { warn: (m) => warns.push(m) });
  assert.equal(inst.items.length, 2);
  const { g, bad } = mockCanvas(1920, 1080); drawGfx(inst, g, 1920, 1080, 3); assert.deepEqual(bad, []);
});
