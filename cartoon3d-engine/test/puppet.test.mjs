import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { visemeWeights, mouthShape, speakingAmount, puppetMotion, armPose, armJoints, reachFor, GESTURE_NAMES, SIGN_NAMES, signPose, signAt, withSign, sleeveShape, performance, ponySwing, TILT_MAX } from '../web/puppet_rules.mjs';
import { signsForLines, WORD_SIGNS } from '../lib/signs.mjs';

const spec = JSON.parse(fs.readFileSync(new URL('../assets/puppets/girl/spec.json', import.meta.url)));
const rig = spec.arms, SIDES = { l: [rig.left, -1], r: [rig.right, 1] };
const wrist = (pose, k) => armJoints(SIDES[k][0].pivot, SIDES[k][1], pose[k], rig.upper, rig.fore).W;
const moved = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const REST = armPose(rig, { gesture: 'idle' }, 0);

test('at rest her hands are on her hips, where the picture has them', () => {
  assert.ok(moved(wrist(REST, 'l'), [395, 1490]) < 70, String(wrist(REST, 'l')));
  assert.ok(moved(wrist(REST, 'r'), [850, 1470]) < 70, String(wrist(REST, 'r')));
});

test('every gesture the lesson can ask for moves a hand, and the body or head', () => {
  for (const gesture of ['wave', 'point', 'pointDown', 'present', 'open', 'clap', 'cheer', 'jump', 'heart', 'lean', 'think']) {
    assert.ok(GESTURE_NAMES.includes(gesture), gesture);
    const pose = armPose(rig, { gesture, gt: 0.7, gw: 1 }, 0.7);
    assert.ok(Math.max(moved(wrist(pose, 'l'), wrist(REST, 'l')), moved(wrist(pose, 'r'), wrist(REST, 'r'))) > 100, gesture);
    const calm = puppetMotion({ gesture: 'idle' }, 0.7), m = puppetMotion({ gesture, gt: 0.7, gw: 1 }, 0.7);
    assert.ok(['hop', 'lean', 'tilt', 'headTilt', 'nod'].some((k) => Math.abs(m[k] - calm[k]) > 0.004), gesture);
  }
});

test('a wave keeps moving, a cheer lifts both hands above her shoulders, a clap brings the hands together', () => {
  const ys = [0.5, 0.6, 0.7, 0.8].map((g) => wrist(armPose(rig, { gesture: 'wave', gt: g, gw: 1 }, g), 'r')[0]);
  assert.ok(Math.max(...ys) - Math.min(...ys) > 30);
  const up = armPose(rig, { gesture: 'cheer', gt: 1, gw: 1 }, 1);
  assert.ok(wrist(up, 'l')[1] < rig.left.pivot[1] - 150 && wrist(up, 'r')[1] < rig.right.pivot[1] - 150);
  const beat = 0.5, closed = armPose(rig, { gesture: 'clap', gt: beat, gw: 1, beat }, 1);
  assert.ok(moved(wrist(closed, 'l'), wrist(closed, 'r')) < 70);
});

test('when she speaks with no gesture, one hand comes off her hip and keeps moving', () => {
  const a = armPose(rig, { gesture: 'idle' }, 2, 1), b = armPose(rig, { gesture: 'idle' }, 2.5, 1);
  assert.ok(moved(wrist(a, 'r'), wrist(REST, 'r')) > 100);
  assert.ok(moved(wrist(a, 'r'), wrist(b, 'r')) > 15);
});

test('gesture changes blend: no hand jumps between two frames', () => {
  const s0 = { gesture: 'cheer', gt: 0, gw: 0, prev: { gesture: 'present', gt: 3 } };
  let last = null;
  for (let u = 0; u <= 1; u += 1 / 10) {
    const p = wrist(armPose(rig, { ...s0, gw: u, gt: u * 0.35 }, 3), 'r');
    if (last) assert.ok(moved(p, last) < 200, String(u));
    last = p;
  }
});

test('reachFor puts the wrist on the target', () => {
  for (const [pv, sd, t] of [[rig.left.pivot, -1, [560, 1250]], [rig.right.pivot, 1, [650, 1250]], [rig.right.pivot, 1, [720, 1010]]]) {
    const r = reachFor(pv, sd, t, rig.upper, rig.fore), W = armJoints(pv, sd, r, rig.upper, rig.fore).W;
    assert.ok(moved(W, t) < 2, String(W));
  }
});

test('she has a whole body: hops only upward, and legs reach the floor', () => {
  for (const gesture of [...GESTURE_NAMES, 'nope']) for (let t = 0; t < 6; t += 0.1) assert.ok(puppetMotion({ gesture, gt: t, gw: 1 }, t).hop >= 0);
  assert.ok(Math.max(...[0.2, 0.45, 0.7].map((g) => puppetMotion({ gesture: 'jump', gt: g, gw: 1 }, g).hop)) > 0.1);
  assert.equal(spec.legs.foot, spec.height.rows);
  assert.ok(spec.warp.pony.x[0] < spec.warp.pony.x[1] && spec.warp.pony.y[0] < spec.warp.pony.y[1], 'bend ranges run low to high');
  assert.ok(spec.warp.pony.x[1] < spec.mouth.mask[0][0], 'the bend stops before her mouth');
  assert.ok(spec.legs.hipBottom > 1525 && spec.legs.cuff > spec.legs.hipBottom);
});

test('mouth shapes: closed, small, wide, round and FF come out of the visemes', () => {
  assert.equal(mouthShape({}).o, 0);
  assert.equal(mouthShape({ PP: 1 }).o, 0);
  assert.ok(mouthShape({ SS: 1 }).o < 0.25);
  assert.ok(mouthShape({ aa: 1 }).o === 1 && mouthShape({ aa: 1 }).w >= 1);
  assert.ok(mouthShape({ O: 1 }).r === 1 && mouthShape({ O: 1 }).w < 0.7);
  assert.equal(mouthShape({ FF: 1 }).ff, 1);
  assert.ok(mouthShape({ aa: 0.3 }).o < mouthShape({ aa: 1 }).o);
});

test('her own smile shows between lines, the drawn mouth inside them', () => {
  const lines = [{ t0: 2, t1: 4 }, { t0: 8, t1: 9 }];
  assert.equal(speakingAmount(lines, 0), 0);
  assert.equal(speakingAmount(lines, 3), 1);
  assert.equal(speakingAmount(lines, 6), 0);
  assert.ok(speakingAmount(lines, 1.91) > 0 && speakingAmount(lines, 1.91) < 1);
});

test('viseme weights read and blend the plan track', () => {
  const track = { fps: 10, names: ['aa', 'O'], frames: [[0, 100], [100, 0]] };
  assert.deepEqual(visemeWeights(track, 0), { O: 1 });
  assert.ok(Math.abs(visemeWeights(track, 0.05).aa - 0.5) < 1e-9);
  assert.deepEqual(visemeWeights(null, 1), {});
});

test('the cut line and spec points fit her picture', () => {
  for (const pt of [...spec.head.cut, ...spec.mouth.mask, spec.head.pivot, ...spec.eyes.flatMap((e) => e.contour)]) {
    assert.ok(pt[0] >= 0 && pt[0] <= 1043 && pt[1] >= 0 && pt[1] <= 1525, String(pt));
  }
});

test('every sign word has a sign, and every sign reaches its hands to the targets', () => {
  for (const sign of new Set(Object.values(WORD_SIGNS))) assert.ok(SIGN_NAMES.includes(sign), sign);
  for (const name of SIGN_NAMES) for (const u of [0, 0.5, 1]) {
    const p = signPose(rig, name, u, u * 1.3);
    assert.ok(p.l || p.r, name);
    for (const k of ['l', 'r']) if (p[k]) assert.ok(Number.isFinite(p[k].a) && Number.isFinite(p[k].b), `${name} ${k}`);
  }
});

test('open is palms, shut is fists, on the same spot', () => {
  const o = signPose(rig, 'open', 0, 0), c = signPose(rig, 'shut', 0, 0);
  assert.equal(o.r.hand, 'spread'); assert.equal(c.r.hand, 'fist');
  assert.ok(moved(wrist(o, 'r'), wrist(c, 'r')) < 20);
});

test('the spider climbs and the rain falls', () => {
  assert.ok(wrist(signPose(rig, 'spider', 1, 0), 'r')[1] < wrist(signPose(rig, 'spider', 0, 0), 'r')[1] - 300);
  assert.ok(wrist(signPose(rig, 'rain', 1, 0), 'r')[1] > wrist(signPose(rig, 'rain', 0, 0), 'r')[1] + 300);
});

test('a key word gets its sign when it is said, repeats join, the next word is not delayed', () => {
  const w = (text, t0) => ({ text, t0, t1: t0 + 0.4 });
  const signs = signsForLines([{ t0: 0, t1: 4, words: [w('Open,', 0), w('shut', 0.5), w('them', 1), w('clap,', 1.5), w('clap,', 2), w('clap', 2.5), w('the', 3)] }], SIGN_NAMES);
  assert.deepEqual(signs.map((x) => x.sign), ['open', 'shut', 'clap']);
  assert.equal(signs[0].t0, 0); assert.equal(signs[1].t0, 0.5);
  assert.ok(signs[0].t1 <= signs[1].t0);
  assert.ok(signs[2].t1 >= 2.9);
});

test('signs blend in and out, and close signs go straight to each other', () => {
  const signs = [{ t0: 1, t1: 2, sign: 'open' }, { t0: 2.5, t1: 3, sign: 'shut' }, { t0: 8, t1: 9, sign: 'clap' }];
  assert.equal(signAt(signs, 0), null);
  assert.equal(signAt(signs, 1.5).w, 1);
  assert.ok(signAt(signs, 0.94).w > 0 && signAt(signs, 0.94).w < 1);
  const hold = signAt(signs, 2.2); assert.equal(hold.name, 'open'); assert.equal(hold.w, 1);
  assert.equal(signAt(signs, 2.42).from.name, 'open');
  assert.equal(signAt(signs, 5), null);
  const base = armPose(rig, { gesture: 'idle' }, 1), half = withSign(rig, base, { name: 'open', u: 0, g: 0, w: 0.5, beat: 0.5 }), none = withSign(rig, base, null), full = withSign(rig, base, { name: 'open', u: 0, g: 0, w: 1, beat: 0.5 });
  assert.ok(moved(half.r.W, [(none.r.W[0] + full.r.W[0]) / 2, (none.r.W[1] + full.r.W[1]) / 2]) < 1e-6);
});

test('arms stay attached and in proportion in every pose and every in-between', () => {
  const check = (pose, what) => {
    for (const [k, S] of [['l', rig.left], ['r', rig.right]]) {
      const A = pose[k], up = moved(A.E, S.pivot), fo = moved(A.E, A.W);
      assert.ok(up <= rig.upper * 1.02 + 1, `${what} ${k} upper ${up}`);
      assert.ok(fo <= rig.fore * 1.2 + 1, `${what} ${k} forearm ${fo}`);
      const sl = sleeveShape(S.pivot, A.E, rig.sleeve);
      assert.ok(moved(sl.H, S.pivot) <= rig.sleeve.length + 1e-6);
      assert.ok(moved(sl.H, S.pivot) <= up + 1e-6, `${what} ${k} sleeve goes past the elbow`);
    }
  };
  const bases = [armPose(rig, { gesture: 'idle' }, 1), armPose(rig, { gesture: 'idle' }, 1, 1), armPose(rig, { gesture: 'cheer', gt: 1, gw: 1 }, 1)];
  for (const base of bases) for (const a of SIGN_NAMES) for (const w of [0, 0.25, 0.5, 0.75, 1]) {
    check(withSign(rig, base, { name: a, u: w, g: w, w, beat: 0.5 }), `${a} w=${w}`);
    for (const b of SIGN_NAMES) check(withSign(rig, base, { name: b, u: 0, g: 0, w, beat: 0.5, from: { name: a, u: 1, g: 1, beat: 0.5 } }), `${a}>${b} w=${w}`);
  }
});

const LINES = () => [
  { t0: 1, t1: 4, type: 'say', words: [['Open,', 1], ['shut', 1.5], ['them', 2], ['give', 2.5], ['little', 3], ['clap!', 3.5]].map(([text, t0]) => ({ text, t0, t1: t0 + 0.4 })) },
  { t0: 5, t1: 7, type: 'say', words: [['Can', 5], ['you', 5.5], ['say', 6], ['ball?', 6.5]].map(([text, t0]) => ({ text, t0, t1: t0 + 0.4 })) },
  { t0: 8, t1: 9, type: 'say', words: [['Great', 8], ['job!', 8.5]].map(([text, t0]) => ({ text, t0, t1: t0 + 0.4 })) },
];

test('her head moves with the stressed words, side to side, within the neck limit, with no jumps', () => {
  const L = LINES(); let last = null, min = 9, max = -9;
  for (let t = 0; t < 11; t += 1 / 30) {
    const p = performance(L, t);
    assert.ok(Math.abs(p.tilt) <= TILT_MAX, String(t));
    if (last !== null) assert.ok(Math.abs(p.tilt - last) < 0.05, `jump at ${t}`);
    last = p.tilt; if (t > 1 && t < 4) { min = Math.min(min, p.tilt); max = Math.max(max, p.tilt); }
  }
  assert.ok(min < -0.05 && max > 0.05);
  assert.ok(performance(L, 1.02).nod > performance(L, 1.4).nod);
});

test('she is never still between lines', () => {
  const L = LINES(), a = performance(L, 4.5).tilt, b = performance(L, 4.8).tilt;
  assert.ok(Math.abs(a - b) > 0.01);
});

test('she leans in on questions, lifts her brows when surprised, and winks now and then', () => {
  const L = LINES();
  assert.equal(performance(L, 2).leanIn, 0);
  assert.equal(performance(L, 6).leanIn, 1);
  assert.ok(performance(L, 1.2, 'surprised').brow > performance(L, 1.2, 'happy').brow);
  assert.equal(performance(L, 9.2).wink.eye, 1);
  assert.equal(performance(L, 2).wink, null);
});

test('the ponytail trails her head and stays in range', () => {
  const L = LINES(); let min = 9, max = -9;
  for (let t = 0; t < 11; t += 0.05) { const v = ponySwing(L, t); assert.ok(Math.abs(v) < 0.5); min = Math.min(min, v); max = Math.max(max, v); }
  assert.ok(max - min > 0.15);
});
