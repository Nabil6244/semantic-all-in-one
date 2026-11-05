// Kids Learn planner: lesson CSV rows + per-line voice timings -> a frame-independent plan (pure, no I/O).
//
// CSV columns (header row required, any order; blank cells are fine):
//   type     say | word | repeat | count | color | cheer
//   text     what the tutor says (required)
//   object   prop kind for word/count/color (ball, apple, star, heart, block, balloon, duck, car, flower, sun, fish, banana, cup)
//   color    prop colour name (red, blue, ...) or #hex; for type=color it is also the word on the card
//   count    how many props for type=count (1-10)
//   word     card text (default: object name, or colour name for type=color)
//   gesture  override: wave, point, present, open, clap, cheer, heart, lean, think, idle
//   emotion  happy | laugh | surprised | neutral | sad
//   pause    extra seconds of quiet after the line (type=repeat defaults to 2.0 with a "Your turn!" badge)
//   sound    animal sound word for type=animal ("Moo"): the animal hops each time it is said
// More types:
//   opposite word "up/down", "big/small" or "fast/slow"; the prop moves on each spoken word, the tutor shows it
//   animal   object cat|dog|cow|pig|sheep|frog|duck|fish + sound
//   shape    object circle|square|triangle|star|heart
//   letter   word = the letter ("A"); the object pops on its word ("A is for apple")
//   feeling  word happy|sad|surprised|angry|sleepy; a feeling face appears and the tutor acts it
//   chant    spoken in rhythm: every word lands on the music's beat (needs opts.beat); she claps on the beat

export const TYPES = ['say', 'word', 'repeat', 'count', 'color', 'cheer', 'opposite', 'animal', 'shape', 'letter', 'feeling', 'chant'];
export const PAIRS = { 'up/down': ['up', 'down', 'balloon'], 'big/small': ['big', 'small', 'ball'], 'fast/slow': ['fast', 'slow', 'car'] };
const FEEL = { happy: 'happy', sad: 'sad', surprised: 'surprised', angry: 'angry', sleepy: 'neutral' };
const ONE_PROP = ['word', 'color', 'opposite', 'animal', 'shape', 'letter', 'feeling'];
const NUMBER_WORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
const DEFAULT_GESTURE = { say: 'idle', word: 'present', repeat: 'lean', count: 'present', color: 'present', cheer: 'cheer', opposite: 'present', animal: 'present', shape: 'present', letter: 'present', feeling: 'idle', chant: 'clap' };
const DEFAULT_EMOTION = { say: 'happy', word: 'surprised', repeat: 'happy', count: 'happy', color: 'happy', cheer: 'laugh', opposite: 'happy', animal: 'laugh', shape: 'happy', letter: 'happy', feeling: 'happy', chant: 'happy' };

export function parseCsv(text) {
  const rows = []; let field = '', q = false, row = [];
  const s = String(text).replace(/^﻿/, '');
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) { if (c === '"' && s[i + 1] === '"') { field += '"'; i++; } else if (c === '"') q = false; else field += c; continue; }
    if (c === '"') q = true; else if (c === ',') { row.push(field); field = ''; } else if (c === '\n' || c === '\r') { if (c === '\r' && s[i + 1] === '\n') i++; row.push(field); field = ''; if (row.some((x) => x.trim())) rows.push(row); row = []; } else field += c;
  }
  row.push(field); if (row.some((x) => x.trim())) rows.push(row);
  if (!rows.length) return [];
  const head = rows[0].map((h) => h.trim().toLowerCase());
  return rows.slice(1).map((r) => Object.fromEntries(head.map((h, k) => [h, (r[k] ?? '').trim()])));
}

// Check rows and fill defaults. Returns { beats, problems } - problems never stop the video; bad cells fall back.
export function normalizeRows(rows) {
  const beats = [], problems = [];
  rows.forEach((r, i) => {
    const line = i + 2, text = (r.text || '').trim();
    if (!text) { problems.push(`row ${line}: no text, skipped`); return; }
    let type = (r.type || 'say').toLowerCase();
    if (!TYPES.includes(type)) { problems.push(`row ${line}: unknown type "${r.type}", used say`); type = 'say'; }
    const b = { type, text, object: (r.object || '').toLowerCase() || null, color: (r.color || '').toLowerCase() || null, gesture: (r.gesture || '').toLowerCase() || DEFAULT_GESTURE[type], emotion: (r.emotion || '').toLowerCase() || DEFAULT_EMOTION[type], pause: Number(r.pause) || (type === 'repeat' ? 2.0 : 0) };
    if (type === 'count') { const n = Math.round(Number(r.count)); b.count = n >= 1 && n <= 10 ? n : (problems.push(`row ${line}: count "${r.count}" not 1-10, used 3`), 3); }
    if (type === 'opposite') {
      const key = (r.word || '').toLowerCase().replace(/\s/g, ''), pair = PAIRS[key] || PAIRS[key.split('/').reverse().join('/')];
      if (!pair) { problems.push(`row ${line}: opposite "${r.word}" unknown (use up/down, big/small, fast/slow), used up/down`); }
      const P = pair || PAIRS['up/down']; b.pair = key && PAIRS[key] ? [P[0], P[1]] : pair ? [P[1], P[0]] : [P[0], P[1]]; b.object = b.object || P[2];
    }
    if (type === 'feeling') { const f = (r.word || 'happy').toLowerCase(); b.mood = FEEL[f] ? f : (problems.push(`row ${line}: feeling "${r.word}" unknown, used happy`), 'happy'); b.object = 'face'; b.color = b.mood; if (!r.emotion) b.emotion = FEEL[b.mood]; }
    if (type === 'letter') { const L = (r.word || '').trim().charAt(0); b.letter = /[a-z]/i.test(L) ? L : (problems.push(`row ${line}: letter "${r.word}" missing, used A`), 'A'); }
    if (type === 'animal') b.sound = (r.sound || '').trim() || null;
    if ((['word', 'count', 'color', 'animal', 'shape', 'letter'].includes(type)) && !b.object) { b.object = type === 'color' ? 'balloon' : type === 'animal' ? 'cat' : type === 'shape' ? 'circle' : 'ball'; problems.push(`row ${line}: no object, used ${b.object}`); }
    b.word = type === 'letter' ? `${b.letter.toUpperCase()} ${b.letter.toLowerCase()}` : type === 'feeling' ? cap(b.mood) : type === 'opposite' ? null : r.word || (type === 'color' ? cap(b.color || '') : ['word', 'animal', 'shape'].includes(type) ? cap(b.object) : null);
    if (i === 0 && !r.gesture && type === 'say') b.gesture = 'wave';
    beats.push(b);
  });
  return { beats, problems };
}
const cap = (w) => (w ? w[0].toUpperCase() + w.slice(1) : w);

// Slots in the stage area on the tutor's right (world units; the tutor stands at TUTOR_X).
export const TUTOR_X = -0.5;
function slots(n) {
  if (n === 1) return [{ x: 0.6, y: 1.45, s: 2.4 }];
  const perRow = n <= 5 ? n : Math.ceil(n / 2), rowsN = n <= 5 ? 1 : 2, out = [];
  const s = n <= 3 ? 1.45 : n <= 5 ? 1.15 : 0.95, gap = 0.27 * s;
  for (let k = 0; k < n; k++) {
    const r = Math.floor(k / perRow), c = k % perRow, inRow = r === rowsN - 1 ? n - r * perRow : perRow;
    out.push({ x: 0.7 + (c - (inRow - 1) / 2) * gap, y: (rowsN === 1 ? 1.4 : 1.58 - r * 0.3), s });
  }
  return out;
}

// voices[i] = { dur, words: [{text,t0,t1}] } for beats[i] (seconds from the line start).
export function buildLesson(beats, voices, opts = {}) {
  const lead = opts.lead ?? 0.6, gap = opts.gap ?? 0.35, tail = opts.tail ?? 0.8;
  const lines = [], gestures = [], props = [], cards = [], badges = [];
  let t = lead, live = [];
  const endLive = (when) => { for (const p of live) p.t1 = when; live = []; };
  const beat = opts.beat || 0;
  beats.forEach((b, i) => {
    if (b.type === 'chant' && beat) t = Math.ceil((t - 1e-6) / (2 * beat)) * 2 * beat;      // chants start on a half-bar of the music
    const v = voices[i] || { dur: 1.5, words: [] }, t0 = t, t1 = t + v.dur;
    const words = (v.words.length ? v.words : spread(b.text, v.dur)).map((w) => ({ text: w.text, t0: +(t0 + w.t0).toFixed(3), t1: +(t0 + w.t1).toFixed(3) }));
    lines.push({ i, type: b.type, text: b.text, t0: +t0.toFixed(3), t1: +t1.toFixed(3), words: captionWords(b.text, words) });
    gestures.push({ t: Math.max(0, +(t0 - (b.type === 'chant' ? 0 : 0.15)).toFixed(3)), gesture: b.gesture, emotion: b.emotion, look: live.length || ['word', 'count', 'color'].includes(b.type) ? 'props' : 'camera', ...(b.type === 'chant' && beat ? { beat: +beat.toFixed(5) } : {}) });
    if (ONE_PROP.includes(b.type)) {
      endLive(t0 - 0.05);
      const find = (w) => words.find((x) => norm(x.text) === norm(w));
      // Letter lessons: the letter card comes first, the object pops on its own word.
      const objHit = b.type === 'letter' ? find(b.object) : null;
      const sl = slots(1)[0], p = { kind: b.object, color: b.color, t0: +((objHit ? objHit.t0 : t0) - 0.1).toFixed(3), t1: null, ...sl, n: null, anims: [] };
      props.push(p); live.push(p);
      if (b.type === 'opposite') {
        const at = (w, f) => { const h = find(w); return h ? h.t0 : t0 + v.dur * f; };
        b.pair.forEach((w, k) => { const tt = at(w, k ? 0.65 : 0.25); p.anims.push({ t: +tt.toFixed(3), kind: w }); cards.push({ text: cap(w), color: null, t0: tt, t1: null, big: true }); gestures.push({ t: +Math.max(t0, tt - 0.2).toFixed(3), gesture: OPP_GESTURE[w], emotion: k ? 'happy' : 'surprised', look: 'props' }); });
      } else {
        const hit = (b.type === 'letter' ? null : find(b.word)) || words[0];
        cards.push({ text: b.word, color: b.type === 'color' ? b.color : null, t0: b.type === 'letter' ? t0 : hit ? hit.t0 : t0, t1: null, big: b.type === 'letter' });
        if (b.type === 'animal' && b.sound) {
          const hits = words.filter((x) => norm(x.text) === norm(b.sound));
          for (const h of hits) p.anims.push({ t: h.t0, kind: 'hop' });
          if (hits.length) cards.push({ text: `${cap(b.sound)}!`, color: null, t0: hits[0].t0, t1: null, sound: true });
        }
      }
    } else if (b.type === 'count') {
      endLive(t0 - 0.05);
      const nums = words.filter((w) => NUMBER_WORDS[norm(w.text)] || /^\d+$/.test(norm(w.text)));
      const sl = slots(b.count);
      for (let k = 0; k < b.count; k++) {
        const at = nums[k] ? nums[k].t0 : t0 + (v.dur * (k + 1)) / (b.count + 1);
        const p = { kind: b.object, color: b.color, t0: +at.toFixed(3), t1: null, ...sl[k], n: k + 1 };
        props.push(p); live.push(p);
      }
      cards.push({ text: `${b.count}`, color: null, t0: nums[b.count - 1] ? nums[b.count - 1].t0 : t1 - 0.3, t1: null, big: true });
    } else if (b.type === 'say') {
      endLive(t0 - 0.05);
    }
    // A card lasts until the next card or until its props leave.
    if (b.type === 'say') for (const c of cards) if (c.t1 === null) c.t1 = t0 - 0.05;
    t = t1 + gap + b.pause;
    if (b.type === 'repeat') badges.push({ text: 'Your turn!', t0: +(t1 + 0.1).toFixed(3), t1: +(t1 + gap + b.pause - 0.1).toFixed(3) });
  });
  gestures.sort((a, b) => a.t - b.t);
  const duration = +(t - gap + tail).toFixed(3);
  endLive(duration);
  // Each card lasts until the next card appears (or its line's props leave, or the end).
  cards.sort((a, b) => a.t0 - b.t0);
  cards.forEach((c, k) => { const next = cards[k + 1]; c.t1 = Math.min(c.t1 ?? duration, next ? Math.max(c.t0 + 0.4, next.t0 - 0.02) : duration); });
  return { duration, lines, gestures, props, cards, badges };
}

const OPP_GESTURE = { up: 'point', down: 'pointDown', big: 'open', small: 'present', fast: 'clap', slow: 'present' };
const norm = (w) => String(w).toLowerCase().replace(/[^a-z0-9]/g, '');
function spread(text, dur) {
  const ws = text.split(/\s+/).filter(Boolean), lens = ws.map((w) => w.length + 1), tot = lens.reduce((a, b) => a + b, 0) || 1;
  let a = 0.1; return ws.map((w, k) => { const s = a; a += (dur - 0.3) * lens[k] / tot; return { text: w, t0: s, t1: a }; });
}
// Edge word timings drop punctuation; put it back from the script so captions read naturally.
function captionWords(text, timed) {
  const ws = text.split(/\s+/).filter(Boolean); let j = 0;
  return ws.map((w) => {
    let k = j; while (k < timed.length && k < j + 3 && norm(timed[k].text) !== norm(w)) k++;
    if (k < timed.length && k < j + 3) j = k;
    const hit = timed[Math.min(j, timed.length - 1)] || { t0: 0, t1: 0 }; j++;
    return { text: w, t0: hit.t0, t1: hit.t1 };
  });
}
