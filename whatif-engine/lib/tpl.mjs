// TEMPLATES: a visual as data. A template (whatif-engine/templates/<family>/<id>.json) places PRIMITIVES (lib/prims.mjs) on the frame
// and animates them with MOTIONS; SLOTS are what a CSV row fills ({label}, {value_to}, {pairs} ...), so one template serves every topic.
// This module turns a template + slot values + narration cues into concrete items, and gives every item's state at a time. It draws
// nothing (prims.mjs does), so node tests can check every template without a browser.
//
//   { "id": "two_clocks_ratio", "family": "time", "use": "...", "plate": true, "hold": 8, "tags": ["time"],
//     "slots": { "left": { "default": "EARTH", "from": "label" }, "ratio": { "default": 10, "from": "value_to" } },
//     "items": [ { "p": "clock", "at": [0.3, 0.5], "r": 0.14, "label": "{left}", "in": 0.2 },
//                { "p": "number", "at": [0.05, 0.88], "m": "count", "from": 1, "to": "{ratio}", "dur": 2.5, "in": "@hours" } ] }
//
// Times ("in", "out", animation keys) are seconds from the layer's start, or "40%" of its length, or "end-1.5", or "@word" / "@word+0.4":
// the moment the narrator says that word (cues, found by the planner; a word not heard falls back to "or" / an even spread).
// Any string "{slot}" is replaced; a string that is exactly "{slot}" takes the slot's value as it is (a number, a list). A string starting
// with "=" is arithmetic ("=0.2+0.12*{i}"). "each": "<list slot>" repeats an item per element ({it}, {it.key}, {i}, {n}); "stagger" delays each.
// "m" (with "dur") is a motion shorthand; "anim": { param: [[t, v], ...] } animates any parameter (numbers, [x, y], colours).

export const MOTIONS = ['draw', 'count', 'move', 'scale', 'shrink', 'grow', 'fade_out', 'rotate', 'stretch', 'flash', 'colour', 'typewriter', 'pop'];

const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * (3 - 2 * k); };
const EASE = { smooth, linear: (x) => Math.min(1, Math.max(0, x)), out: (x) => 1 - (1 - Math.min(1, Math.max(0, x))) ** 3, step: (x) => (x >= 1 ? 1 : 0),
  in: (x) => Math.min(1, Math.max(0, x)) ** 2 };

// ---- slots ----------------------------------------------------------------------------------------------------------------------
const SLOT_RE = /\{([a-zA-Z_][\w.]*)\}/g;
function lookup(vars, path) {
  let v = vars;
  for (const k of path.split('.')) { if (v == null || typeof v !== 'object' || !(k in v)) return undefined; v = v[k]; }
  return v;
}
/** Replace {name} in every string of a JSON value. A string that is exactly "{name}" takes the raw value. */
export function fill(x, vars) {
  if (typeof x === 'string') {
    // only the template's own strings may be formulas: a CSV value that starts with "=" ("= 1 HOUR") is shown as written
    const guard = (v) => (typeof v === 'string' && v.startsWith('=') ? `\u2060${v}` : v);
    const whole = x.match(/^\{([a-zA-Z_][\w.]*)\}$/);
    if (whole) { const v = lookup(vars, whole[1]); return v === undefined ? x : guard(v); }
    const formula = x.startsWith('=');      // a negative number in a formula is bracketed: "0.5-{it}" with -0.26 must not become "0.5--0.26"
    const r = x.replace(SLOT_RE, (m, k) => { const v = lookup(vars, k); return v === undefined || v === null ? m : (typeof v === 'object' ? JSON.stringify(v) : formula && typeof v === 'number' ? `(${v})` : String(v)); });
    return formula ? r : guard(r);
  }
  if (Array.isArray(x)) return x.map((e) => fill(e, vars));
  if (x && typeof x === 'object') { const o = {}; for (const [k, v] of Object.entries(x)) o[k] = k === 'each' ? v : fill(v, vars); return o; }
  return x;
}

// ---- arithmetic -----------------------------------------------------------------------------------------------------------------
const FN = { min: Math.min, max: Math.max, abs: Math.abs, sqrt: Math.sqrt, log10: Math.log10, pow: Math.pow, floor: Math.floor, round: Math.round, PI: Math.PI,
  sin: Math.sin, cos: Math.cos, clamp: (v, a, b) => Math.min(b, Math.max(a, v)) };
/** "=0.2+0.12*3" -> 0.56. Only numbers, + - * / % ( ) , and the names in FN: a slot value can never run code. */
export function calc(expr) {
  const body = String(expr).slice(1).trim();
  const names = body.match(/[A-Za-z_]\w*/g) || [];
  for (const n of names) if (!(n in FN) && !/^e\d*$/.test(n)) throw new Error(`template arithmetic: unknown name "${n}" in ${expr}`);
  if (!/^[\w\s+\-*/%().,]*$/.test(body)) throw new Error(`template arithmetic: not a formula: ${expr}`);
  // eslint-disable-next-line no-new-func
  const v = Function(...Object.keys(FN), `return (${body});`)(...Object.values(FN));
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new Error(`template arithmetic: ${expr} is not a number`);
  return v;
}
function calcAll(x) {
  if (typeof x === 'string') return x.startsWith('=') && x.length > 1 ? calc(x) : x;
  if (Array.isArray(x)) return x.map(calcAll);
  if (x && typeof x === 'object') { const o = {}; for (const [k, v] of Object.entries(x)) o[k] = calcAll(v); return o; }
  return x;
}

// ---- times ----------------------------------------------------------------------------------------------------------------------
/** A template time -> seconds from the layer start (null when it is a cue nobody said and there is no fallback). */
export function seconds(v, len, cues = {}, fallback = null) {
  if (v == null || v === '') return fallback;
  if (typeof v === 'number') return v;
  const s = String(v).trim();
  let m = s.match(/^(-?[\d.]+)%$/);
  if (m) return (len * parseFloat(m[1])) / 100;
  m = s.match(/^end\s*([+-]\s*[\d.]+)?$/);
  if (m) return len + (m[1] ? parseFloat(m[1].replace(/\s/g, '')) : 0);
  m = s.match(/^@([\w'-]+)\s*([+-]\s*[\d.]+)?$/);
  if (m) { const c = cues[m[1].toLowerCase()]; if (c == null) return fallback; return c + (m[2] ? parseFloat(m[2].replace(/\s/g, '')) : 0); }
  if (/^-?[\d.]+$/.test(s)) return parseFloat(s);
  throw new Error(`template time ${JSON.stringify(v)}: use seconds, "40%", "end-1" or "@word"`);
}

// ---- motions -> animation keys --------------------------------------------------------------------------------------------------
function motionKeys(it, t0, dur) {
  const t1 = t0 + dur, a = {};
  switch (it.m) {
    case 'draw': case 'typewriter': a.progress = { keys: [[t0, 0], [t1, 1]], ease: it.ease || 'smooth' }; break;
    case 'count': a.value = { keys: [[t0, it.from ?? 0], [t1, it.to ?? it.value ?? 0]], ease: it.ease || 'out' }; break;
    case 'move': a.along = { keys: [[t0, 0], [t1, 1]], ease: it.ease || 'smooth' }; break;
    case 'scale': case 'grow': a.scale = { keys: [[t0, it.scale_from ?? 0.2], [t1, it.scale ?? 1]], ease: it.ease || 'out' }; break;
    case 'shrink': a.scale = { keys: [[t0, it.scale ?? 1], [t1, it.scale_to ?? 0.3]], ease: it.ease || 'smooth' }; break;
    case 'pop': a.scale = { keys: [[t0, 0.6], [t0 + dur * 0.6, 1.08], [t1, 1]], ease: 'smooth' }; break;
    case 'fade_out': a.alpha = { keys: [[t0, it.alpha ?? 1], [t1, 0]], ease: 'smooth' }; break;
    case 'rotate': a.rot = { keys: [[t0, it.rot ?? 0], [t1, it.rot_to ?? 90]], ease: it.ease || 'smooth' }; break;
    case 'stretch': a.sx = { keys: [[t0, 1], [t1, it.sx_to ?? 0.35]], ease: 'smooth' }; a.sy = { keys: [[t0, 1], [t1, it.sy_to ?? 2.6]], ease: 'smooth' }; break;
    case 'colour': a.color = { keys: [[t0, it.color ?? 'white'], [t1, it.color_to ?? 'red']], ease: 'smooth' }; break;
    case 'flash': break;   // handled at draw time from it._flash
    default: throw new Error(`template motion "${it.m}" is not one of ${MOTIONS.join(', ')}`);
  }
  return a;
}

/** Template + slot values + cues + layer length -> concrete items (positions, times and animations resolved). Throws naming the problem. */
export function build(template, slotValues = {}, { len = 6, cues = {} } = {}) {
  if (!template || !Array.isArray(template.items)) throw new Error('template: "items" must be a list');
  const vars = { ...defaults(template), ...Object.fromEntries(Object.entries(slotValues || {}).filter(([, v]) => v !== undefined && v !== null && v !== '')) };
  vars.len = len;
  const out = [];
  let auto = 0;
  const count = template.items.length;
  for (const [idx, raw] of template.items.entries()) {
    const copies = [];
    if (raw.each) {
      const list = vars[raw.each];
      if (!Array.isArray(list)) throw new Error(`template ${template.id}: item ${idx} repeats over "${raw.each}", which is not a list`);
      list.forEach((e, i) => copies.push({ item: raw, vars: { ...vars, it: e, i, n: list.length } }));
    } else copies.push({ item: raw, vars });
    for (const { item, vars: v } of copies) {
      const it = calcAll(fill({ ...item }, v));
      delete it.each;
      if (!it.p) throw new Error(`template ${template.id}: item ${idx} has no "p" (primitive)`);
      const stagger = raw.each ? (Number(it.stagger) || 0) * v.i : 0;
      const spread = (len * 0.12) + (len * 0.6 * (idx / Math.max(1, count)));          // where an unheard cue falls: an even spread
      it._in = (seconds(it.in, len, cues, it.or != null ? seconds(it.or, len, cues, spread) : spread) ?? 0) + stagger;
      it._out = it.out != null ? seconds(it.out, len, cues, null) : null;
      const anim = {};
      if (it.m) Object.assign(anim, motionKeys(it, it._in + (Number(it.delay) || 0), Number(it.dur) || 1.2));
      if (it.m === 'flash') it._flash = { t0: it._in, n: it.n ?? 3, hz: it.hz ?? 2.2, color: it.flash_color || 'red' };
      for (const [k, spec] of Object.entries(it.anim || {})) {
        const keys = (Array.isArray(spec) ? spec : spec.keys).map(([t, val]) => [seconds(t, len, cues, it._in - stagger) + stagger, val]);
        anim[k] = { keys: keys.sort((a, b) => a[0] - b[0]), ease: Array.isArray(spec) ? 'smooth' : (spec.ease || 'smooth') };
      }
      it._anim = anim;
      it._n = auto++;
      out.push(it);
    }
  }
  return out;
}

export function defaults(template) {
  const d = {};
  for (const [k, s] of Object.entries(template.slots || {})) if (s && s.default !== undefined) d[k] = s.default;
  return d;
}

// ---- per-frame values -----------------------------------------------------------------------------------------------------------
const NAMED = { cyan: '#00E5FF', info: '#00E5FF', amber: '#FFB703', gold: '#F5A640', warn: '#FFB703', red: '#FF2A4B', lethal: '#FF2A4B', white: '#FFFFFF',
  grey: '#8E99A8', gray: '#8E99A8', green: '#2EE6A8', cream: '#F3E3C3', blue: '#2F6BDF', orange: '#FF7A1A', dim: '#5A6472', black: '#000000' };
export const hex = (c) => NAMED[String(c).toLowerCase()] || c;
function rgb(c) {
  const h = hex(c);
  if (typeof h !== 'string' || !/^#[0-9a-f]{6}$/i.test(h)) return null;
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function lerp(a, b, k) {
  if (typeof a === 'number' && typeof b === 'number') return a + (b - a) * k;
  if (Array.isArray(a) && Array.isArray(b)) return a.map((x, i) => lerp(x, b[i] ?? x, k));
  const ca = rgb(a), cb = rgb(b);
  if (ca && cb) return '#' + ca.map((x, i) => Math.round(x + (cb[i] - x) * k).toString(16).padStart(2, '0')).join('');
  return k < 1 ? a : b;
}
/** A keyed value at time t (held before the first key and after the last). */
export function keyedAt(spec, t) {
  const keys = spec.keys, ease = EASE[spec.ease] || smooth;
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    const [ta, va] = keys[i - 1], [tb, vb] = keys[i];
    if (t <= tb) return tb > ta ? lerp(va, vb, ease((t - ta) / (tb - ta))) : vb;
  }
  return keys[keys.length - 1][1];
}

/** The item's parameter at time tr (seconds from the layer start). */
export function param(it, name, tr, fallback) {
  const a = it._anim && it._anim[name];
  if (a) return keyedAt(a, tr);
  return it[name] ?? fallback;
}

/** 0..1 visibility of an item at tr: it appears at "in" (0.35 s), leaves at "out" (0.3 s), and "flash" blinks it. */
export function visibility(it, tr) {
  if (tr < it._in) return 0;
  const fin = it.appear === 'cut' ? 1 : smooth((tr - it._in) / (it.fade ?? 0.35));
  const fout = it._out != null ? 1 - smooth((tr - it._out) / 0.3) : 1;
  let a = Math.min(fin, fout) * param(it, 'alpha', tr, 1);
  return Math.max(0, Math.min(1, a));
}

/** During a flash: true while the item shows its flash colour. */
export function flashing(it, tr) {
  const f = it._flash;
  if (!f) return false;
  const k = (tr - f.t0) * f.hz;
  return k >= 0 && k < f.n && (k % 1) < 0.5;
}

/** Every moment something changes in a built template (appearances, key times, motion ends) -- for the "never a still screen" check. */
export function changeTimes(items) {
  const ts = new Set();
  for (const it of items) {
    ts.add(+it._in.toFixed(2));
    if (it._out != null) ts.add(+it._out.toFixed(2));
    for (const a of Object.values(it._anim || {})) for (const [t] of a.keys) ts.add(+t.toFixed(2));
  }
  return [...ts].sort((a, b) => a - b);
}
/** Items that move all the time (an orbit, a flow, a spin, a pulse): a plate that has one is never still. */
export const continuous = (it) => !!(it.spin || it.flow || it.pulse || it.orbit || it.speed || it.p === 'particles' || it.p === 'clock' || it.p === 'grid');
