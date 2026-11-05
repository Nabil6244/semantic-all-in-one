// The reflection as a performer. A mirror normally copies whoever stands at it; when the narration says the reflection acts on its own
// (smiles first, moves early, blinks, turns, presses to the glass, stutters, is gone) that is planned here as timed acts on the spoken
// word. The renderer draws a double only the mirror can see, so the person in the room and the person in the glass can differ.

import { clamp, smooth } from './rng.mjs';

export const AHEAD = 0.6; // seconds the reflection runs ahead of you
const GLASS = /\b(reflections?|mirrors?|glass|it|its|thing|something)\b/;
// [act, sentence test, word the act lands on, seconds it lasts (null = to the end of the scene)]
const RULES = [
  ['empty', /\b(mirror|glass) (was|is|stood) empty\b|\bno reflection\b/, 'empty', null],
  ['noface', /\bno face\b/, 'face', 4.5],
  ['press', /\bface\b.*\b(pressed|against the glass)\b/, 'pressed', null],
  ['blink', /\bblink/, 'blink', 0.6],
  ['turn', /\breflections?\b.*\b(turn|turned|turns|looked at|looks at)\b/, 'turned', 5],
  ['still', /\bstutter|\bgo(es)? still\b/, 'stutter', null],
  ['hands', /\breflection(['’]s)? hands\b/, 'hands', 4],
  ['ahead', /\bmoved? first\b|\bmoves first\b|\bgot ahead\b|\bhalf.?second\b|\bhair early\b|\bbefore (you|they)\b/, null, 6],
  ['smile', /\bsmil/, 'smil', null],
];

/** acts for one scene: [{act, t0, t1, carried?}] plus the actions the person in the room does because of them. carry: {chapter, smile}. */
export function planMirrorPlay(scene, wordTime, carry = {}) {
  const play = [], actions = [];
  const propText = (scene.props || []).join('; ').toLowerCase();
  const start = scene.sentences[0]?.start ?? 0, last = scene.sentences[scene.sentences.length - 1]?.end ?? start;
  if (/\bempty mirror\b/.test(propText)) play.push({ act: 'empty', t0: start, t1: last + 5 });
  for (const s of scene.sentences) {
    const text = s.text.toLowerCase(); if (!GLASS.test(text)) continue;
    for (const [act, re, word, dur] of RULES) {
      if (!re.test(text) || play.some((p) => p.act === act)) continue;
      const t0 = (word && wordTime(s, word)) ?? s.start;
      play.push({ act, t0, t1: dur ? t0 + dur : Math.max(last + 5, t0 + 5) });
      if (act === 'ahead') actions.push({ state: 'look', time: t0 + AHEAD, word: null, csv: true }); // you follow, a beat late
    }
  }
  const empty = play.some((p) => p.act === 'empty');
  const smiling = !empty && (play.some((p) => p.act === 'smile') || (carry.smile && carry.chapter === scene.chapter));
  if (smiling && !play.some((p) => p.act === 'smile')) play.push({ act: 'smile', t0: start - 2, t1: last + 5, carried: true });
  return { play, actions, carry: { chapter: scene.chapter, smile: smiling } };
}

/** What the reflection is doing at time t. Numbers run 0..1 so moves ease in. */
export function mirrorStateAt(play = [], t) {
  const on = (act) => play.find((p) => p.act === act && t >= p.t0 && t < p.t1);
  const ease = (p, d = 0.5) => (p ? smooth(clamp((t - p.t0) / d, 0, 1)) : 0);
  const still = on('still'), blink = on('blink'), u = blink ? t - blink.t0 : 0;
  return { empty: !!on('empty'), smile: !!on('smile') || !!on('press'), noface: !!on('noface'), press: ease(on('press'), 0.9), turn: ease(on('turn')), hands: ease(on('hands'), 0.7),
    ahead: !!on('ahead'), frozenAt: still ? still.t0 : null, blink: !!blink && (u < 0.16 || (u > 0.32 && u < 0.46)) };
}
