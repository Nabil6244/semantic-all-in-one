// The Roblox Cinema story CSV. Same row-type convention as the app's other beat CSVs (Hybrid, StarMap): a `row` column says
// what the row is (plan / chapter / beat), every other column is optional, and `extra` carries structured JSON. Only the
// narration text is required on a beat: everything else is inferred by the director when it is blank (manual override when
// filled). validateStory() catches malformed data before anything renders.
//
//   row      plan | chapter | beat
//   id       beat id (stable seed for its set; defaults to b<n>)
//   chapter  chapter title (on a chapter row) / chapter the beat belongs to
//   text     narration (beat), film title (plan)
//   date     "6 June 1944", "1944", "June 1944" -> date badge; the plan's date sets the era
//   location a place name ("Omaha Beach", "Portsmouth") -> gazetteer; "lon,lat" also accepted
//   event    event type (see recipes.EVENT_TYPES); blank = classified from the narration
//   environment  environment recipe (see world.ENVIRONMENTS); blank = from the event + place
//   time     dawn | day | sunset | dusk | night ; weather: clear | overcast | rain | storm | fog | snow
//   characters   "role[:Name][*count]; ..."  e.g. "commander:Eisenhower; officer*3"
//   actions      "state[@keyword]; ..."  e.g. "point@order; talk"  (the keyword times the action to the spoken word)
//   vehicles     "kind[*count][>motion]; ..."  e.g. "landing_craft*6>advance; transport_plane*5>flyover"
//   props, effects  "; " lists
//   camera   a camera behaviour (camera.BEHAVIOURS) or "a>b" for two shots
//   subtitle override caption text ; audio: "; " list of cue names ; transition: cut | dissolve | dip | clouds | map_dive | match
//   duration seconds (only used without a voiceover)
//   extra    JSON: {"label": "...", "stat": "156,000 | troops ashore", "map": {...}, "seed": 3, ...}

export const COLUMNS = ['row', 'id', 'chapter', 'text', 'date', 'location', 'event', 'environment', 'time', 'weather', 'characters',
  'actions', 'vehicles', 'props', 'effects', 'camera', 'subtitle', 'audio', 'transition', 'duration', 'extra'];

/** RFC 4180 CSV -> array of rows (arrays of strings). Handles quotes, doubled quotes, CRLF and a BOM. */
export function parseCsv(text) {
  const s = String(text).replace(/^﻿/, '');
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === '"') { if (s[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && s[i + 1] === '\n') i++;
      row.push(cell); cell = '';
      if (row.some((x) => x.trim() !== '')) rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell);
  if (row.some((x) => x.trim() !== '')) rows.push(row);
  return rows;
}

const splitList = (v) => String(v || '').split(/[;|]/).map((x) => x.trim()).filter(Boolean);

/** "commander:Eisenhower*1; soldier*20" -> [{role, name, count}] */
export function parseCast(v) {
  return splitList(v).map((item) => {
    const m = item.match(/^([a-z_]+)(?::([^*]+))?(?:\*(\d+))?$/i);
    if (!m) return { bad: item };
    return { role: m[1].toLowerCase(), name: m[2] ? m[2].trim() : null, count: m[3] ? Number(m[3]) : 1 };
  });
}

/** "point@order; talk" -> [{state, at}] */
export function parseActions(v) {
  return splitList(v).map((item) => { const [state, at] = item.split('@').map((x) => x.trim()); return { state: state.toLowerCase(), at: at || null }; });
}

/** "landing_craft*6>advance" -> [{kind, count, motion}] */
export function parseVehicles(v) {
  return splitList(v).map((item) => {
    const m = item.match(/^([a-z_0-9]+)(?:\*(\d+))?(?:>([a-z_]+))?$/i);
    if (!m) return { bad: item };
    return { kind: m[1].toLowerCase(), count: m[2] ? Number(m[2]) : 1, motion: m[3] ? m[3].toLowerCase() : null };
  });
}

/** CSV text -> story {plan, chapters, beats, errors}. Errors are collected, never thrown: validateStory() reports them. */
export function parseStory(text) {
  const rows = parseCsv(text);
  const errors = [];
  if (!rows.length) return { plan: {}, chapters: [], beats: [], errors: ['the CSV is empty'] };
  const head = rows[0].map((h) => h.trim().toLowerCase());
  if (!head.includes('row') || !head.includes('text')) errors.push('the header must have at least the columns "row" and "text"');
  for (const h of head) if (h && !COLUMNS.includes(h)) errors.push(`unknown column "${h}" (ignored)`);
  const plan = { title: '', date: '', extra: {} }, chapters = [], beats = [];
  let chapter = null;
  rows.slice(1).forEach((cells, k) => {
    const line = k + 2;
    const r = {}; head.forEach((h, i) => { r[h] = (cells[i] ?? '').trim(); });
    let extra = {};
    if (r.extra) { try { extra = JSON.parse(r.extra); if (typeof extra !== 'object' || Array.isArray(extra) || extra === null) throw new Error('not an object'); } catch (e) { errors.push(`line ${line}: extra is not a JSON object (${e.message})`); extra = {}; } }
    const kind = (r.row || 'beat').toLowerCase();
    if (kind === 'plan') { Object.assign(plan, { title: r.text, date: r.date, location: r.location, extra }); return; }
    if (kind === 'chapter') { chapter = { title: r.chapter || r.text, date: r.date, index: chapters.length, line }; chapters.push(chapter); return; }
    if (kind !== 'beat') { errors.push(`line ${line}: row must be plan, chapter or beat (got "${r.row}")`); return; }
    if (!r.text) errors.push(`line ${line}: a beat needs narration text`);
    const dur = r.duration ? Number(r.duration) : null;
    if (r.duration && !(dur > 0)) errors.push(`line ${line}: duration "${r.duration}" is not a positive number`);
    const b = {
      id: r.id || `b${beats.length + 1}`, line, index: beats.length, chapter: chapter ? chapter.index : -1, text: r.text,
      date: r.date || '', location: r.location || '', event: (r.event || '').toLowerCase(), environment: (r.environment || '').toLowerCase(),
      time: (r.time || '').toLowerCase(), weather: (r.weather || '').toLowerCase(),
      cast: parseCast(r.characters), actions: parseActions(r.actions), vehicles: parseVehicles(r.vehicles),
      props: splitList(r.props), effects: splitList(r.effects).map((x) => x.toLowerCase()), camera: (r.camera || '').toLowerCase(),
      subtitle: r.subtitle || '', audio: splitList(r.audio), transition: (r.transition || '').toLowerCase(), duration: dur, extra,
    };
    for (const c of b.cast) if (c.bad) errors.push(`line ${line}: character "${c.bad}" is not role[:Name][*count]`);
    for (const v of b.vehicles) if (v.bad) errors.push(`line ${line}: vehicle "${v.bad}" is not kind[*count][>motion]`);
    b.cast = b.cast.filter((c) => !c.bad); b.vehicles = b.vehicles.filter((v) => !v.bad);
    beats.push(b);
  });
  if (!beats.length) errors.push('the CSV has no beat rows');
  return { plan, chapters, beats, errors };
}

/** Narration text only (no CSV): one beat per paragraph, chapters from lines starting with "#". */
export function storyFromText(text, title = '') {
  const plan = { title, date: '', extra: {} }, chapters = [], beats = [];
  let chapter = -1;
  for (const para of String(text).split(/\n\s*\n|\n(?=#)/)) {
    const p = para.trim(); if (!p) continue;
    if (p.startsWith('#')) { chapters.push({ title: p.replace(/^#+\s*/, ''), index: chapters.length }); chapter = chapters.length - 1; continue; }
    beats.push({ id: `b${beats.length + 1}`, index: beats.length, chapter, text: p.replace(/\s+/g, ' '), date: '', location: '', event: '', environment: '', time: '', weather: '',
      cast: [], actions: [], vehicles: [], props: [], effects: [], camera: '', subtitle: '', audio: [], transition: '', duration: null, extra: {} });
  }
  return { plan, chapters, beats, errors: beats.length ? [] : ['the narration is empty'] };
}

/** Name checks against the engine's vocabularies (passed in so this file stays dependency-free). Returns error strings. */
export function validateStory(story, vocab) {
  const errs = [...(story.errors || [])];
  const known = (set, v) => !v || set.has(v);
  for (const b of story.beats) {
    const at = `line ${b.line ?? b.index + 1} (${b.id})`;
    if (!known(vocab.events, b.event)) errs.push(`${at}: unknown event "${b.event}"`);
    if (!known(vocab.environments, b.environment)) errs.push(`${at}: unknown environment "${b.environment}"`);
    for (const c of b.cast) if (!vocab.roles.has(c.role)) errs.push(`${at}: unknown character role "${c.role}"`);
    for (const v of b.vehicles) if (!vocab.vehicles.has(v.kind)) errs.push(`${at}: unknown vehicle "${v.kind}"`);
    for (const a of b.actions) if (!vocab.actions.has(a.state)) errs.push(`${at}: unknown action "${a.state}"`);
    for (const e of b.effects) if (!vocab.effects.has(e)) errs.push(`${at}: unknown effect "${e}"`);
    for (const cam of b.camera ? b.camera.split('>') : []) if (!vocab.cameras.has(cam.trim())) errs.push(`${at}: unknown camera "${cam}"`);
    if (b.transition && !vocab.transitions.has(b.transition)) errs.push(`${at}: unknown transition "${b.transition}"`);
    if (b.time && !vocab.times.has(b.time)) errs.push(`${at}: unknown time "${b.time}"`);
    if (b.weather && !vocab.weathers.has(b.weather)) errs.push(`${at}: unknown weather "${b.weather}"`);
  }
  return errs.filter((e) => !/\(ignored\)$/.test(e));
}
