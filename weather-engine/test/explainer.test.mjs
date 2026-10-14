// explainer (lib/layers/explainer.mjs): event checks, the cards inside the frame, words wrapped to the card.
import test from 'node:test';
import assert from 'node:assert/strict';
import explainer, { explainerRects, wrap, EX } from '../lib/layers/explainer.mjs';

test('an explainer has one or two cards with kicker and text', () => {
  assert.deepEqual(explainer.validate({ cards: [{ kicker: 'TORNADO WATCH', text: 'X' }, { kicker: 'TORNADO WARNING', text: 'Y' }] }), []);
  assert.ok(explainer.validate({ cards: [] }).length);
  assert.ok(explainer.validate({ cards: [{ kicker: 'A' }] }).length);
});

test('two cards sit side by side inside the frame, above the source line', () => {
  const [a, b] = explainerRects(2);
  assert.ok(a.x >= 40 && b.x + b.w <= 1880 && a.x + a.w < b.x);
  assert.ok(a.y > 500 && a.y + a.h <= 1080 - 100);
});

test('long text wraps to the card width', () => {
  const measure = (s) => s.length * 12;
  const lines = wrap('A TORNADO HAS BEEN SIGHTED OR INDICATED BY WEATHER RADAR', EX.w - 2 * EX.padX, measure);
  assert.ok(lines.length >= 2);
  for (const l of lines) assert.ok(measure(l) <= EX.w - 2 * EX.padX);
});
