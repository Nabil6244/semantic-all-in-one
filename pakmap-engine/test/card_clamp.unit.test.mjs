import test from 'node:test';
import assert from 'node:assert/strict';
import { clampShift, cardBox } from '../lib/draw.mjs';
import { cardRect, cardLabelRect, FRAME } from '../lib/layout.mjs';

const measure = (text, px) => text.length * px * 0.66;
const M = 36;

test('no map movement: the shift is untouched, so a static camera renders as before', () => {
  assert.deepEqual(clampShift({ x: 1400, y: 190, w: 420, h: 360 }, 0, 0, FRAME, M), [0, 0]);
});

test('a card the map drags past the right edge stops inside the frame, label included', () => {
  const rect = cardRect({ anchor: 'tr' }), box = cardBox(rect, 'KOOLASUCHUS', measure);
  const [dx, dy] = clampShift(box, 300, 0, FRAME, M);
  assert.ok(box.x + box.w + dx <= FRAME.w - M + 1e-9, 'right edge');
  assert.equal(dy, 0);
  assert.ok(dx < 300);
});

test('dragged past the left, top and bottom edges', () => {
  const box = cardBox(cardRect({ anchor: 'bl' }), 'X', measure);
  const [dx, dy] = clampShift(box, -900, 900, FRAME, M);
  assert.ok(box.x + dx >= M - 1e-9);
  assert.ok(box.y + box.h + dy <= FRAME.h - Math.min(M, FRAME.h - box.y - box.h) + 1e-9);   // never nearer the edge than where the layout put it
  const [, dy2] = clampShift(box, 0, -5000, FRAME, M);
  assert.ok(box.y + dy2 >= M - 1e-9);
});

test('a card that stays inside is not moved', () => {
  const box = cardBox(cardRect({ anchor: 'tr' }), 'A', measure);
  assert.deepEqual(clampShift(box, -40, 20, FRAME, M), [-40, 20]);
});

test('the label can be wider than the card and still fits', () => {
  const rect = cardRect({ anchor: 'tr' }), label = 'A VERY LONG PHOTO CARD LABEL';
  const box = cardBox(rect, label, measure);
  assert.ok(box.w >= cardLabelRect(rect, label, measure).w);
  const [dx] = clampShift(box, 500, 0, FRAME, M);
  assert.ok(box.x + box.w + dx <= FRAME.w - Math.min(M, FRAME.w - box.x - box.w) + 1e-9);
  assert.ok(box.x + box.w + dx <= FRAME.w);
});

test('a box bigger than the frame is centred, never thrown off by the clamp', () => {
  const [dx] = clampShift({ x: 0, y: 0, w: 2400, h: 100 }, 50, 0, FRAME, M);
  assert.ok(Number.isFinite(dx));
});

test('a card the layout placed nearer the edge than the margin (bottom anchors, label included) is not pushed by float noise', () => {
  for (const anchor of ['bl', 'br', 'tl', 'tr', 'ml', 'mr', 'center']) {
    const box = cardBox(cardRect({ anchor }), 'LABEL', measure);
    const [dx, dy] = clampShift(box, 3e-13, -2e-13, FRAME, M);
    assert.ok(Math.abs(dx - 3e-13) < 1e-9 && Math.abs(dy + 2e-13) < 1e-9, anchor);
  }
});
