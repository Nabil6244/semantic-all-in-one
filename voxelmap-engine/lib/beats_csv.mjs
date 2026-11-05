// The story CSV. Same row-type convention as Hybrid's beat CSV (hybrid/beat_csv.py: a `row` column naming plan / chapter /
// beat rows, rarely edited values as JSON in `extra`), with this engine's own columns. Hybrid's parser is not used: its
// rows carry Hybrid camera modes and layers that mean nothing here.
//
//   row        plan | chapter | territory | label | beat | card
//   plan       id = title, extra = {world, width, height, fps, wpm, subtitle (shown under the title on a globe opening)}
//   chapter    id, text = title (the beats after it belong to it)
//   territory  id = key, date = YYYY-MM it starts, extra = {legend: [{label, color}], rules: [...]}   (see lib/territory.mjs)
//   label      text = name, lon, lat, extra = {kind: country|city, min_alt, max_alt}
//   card       id = the beat it belongs to, text = caption, lon/lat = place a leader line points to (optional),
//              extra = {asset: image file or folder-relative path, words: a few words of the sentence it shows, t: seconds after the
//              beat starts to speaking (wins over words), hold: seconds on screen, anchor: tl|tr|ml|mr|center, kind: portrait|artefact|document|painting}
//   beat       id, date = YYYY-MM, place, lon, lat, rung = globe|map|oblique|ground, alt, heading, site = recipe, gap = seconds of
//              silence before it (planned narration gap), text = the narration (sentences),
//              extra = {territory, seed, shot (see lib/director.mjs), path: [[lon, lat], ...] for an aerial track,
//                       factions: [..] (lib/figures.mjs), names: ["Gen. X"], signs: ["WELCOME"], light: day|sunset|night|fog|dawn,
//                       effects: [{kind: blasts|smoke|fires|planes, at: [lon, lat], to?: [lon, lat]}], museum: {item, name, note}}
import { landmarkFor } from './landmarks.mjs';

export const CARD_ANCHORS = ['tl', 'tr', 'ml', 'mr', 'center'];
export const MAX_CARDS = 3;   // photo cards one beat may show

export function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; continue; }
    if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const head = rows.shift().map((h) => h.trim());
  return rows.filter((r) => r.some((c) => c.trim())).map((r) => Object.fromEntries(head.map((h, i) => [h, (r[i] ?? '').trim()])));
}

const num = (v) => (v === '' || v == null ? null : Number(v));
const json = (v, at) => { if (!v) return {}; try { return JSON.parse(v); } catch { throw new Error(`${at}: extra is not valid JSON`); } };
/** A beat's seed from its own story data, so two beats never share a layout unless the story says so. */
export const seedOf = (...parts) => { let h = 2166136261; for (const ch of parts.join('|')) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0; return h || 1; };
export const splitSentences =(s) => (s.match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g) || []).map((x) => x.trim()).filter(Boolean);

/** YYYY-MM from the forms a story writer types: 1754, 1754-5, 1754-05-12, 1754/05 (BC years with a leading -). Anything else stays as is. */
export function normDate(v) {
  const m = String(v ?? '').trim().match(/^(-?\d{1,4})(?:[-/.](\d{1,2})(?:[-/.]\d{1,2})?)?$/);
  if (!m) return String(v ?? '').trim();
  const mo = m[2] ? Number(m[2]) : 1;
  if (mo < 1 || mo > 12) return String(v).trim();
  const y = m[1].startsWith('-') ? `-${m[1].slice(1).padStart(4, '0')}` : m[1].padStart(4, '0');
  return `${y}-${String(mo).padStart(2, '0')}`;
}

export const STORY_COLUMNS = ['row', 'id', 'date', 'place', 'lon', 'lat', 'rung', 'text', 'extra'];
/** A CSV made for another style fails here with what it is and where it goes, not with a puzzling row error later. */
export function checkColumns(head) {
  const has = (c) => head.includes(c), missing = ['row', 'date', 'lon', 'lat', 'text'].filter((c) => !has(c));
  if (!missing.length) return;
  let kind = '';
  if (has('location') && has('environment')) kind = 'a Roblox Cinema story CSV (Rules Horror / story scenes): load it in the Roblox Cinema section';
  else if (has('vo_anchor') && has('mode')) kind = 'a Hybrid Map / StarMap beat plan: load it in that section';
  throw new Error(`this is not a Voxel Map story CSV${kind ? `, it is ${kind}` : ''}. A Voxel Map story needs the columns ${STORY_COLUMNS.join(', ')} `
    + `(missing: ${missing.join(', ')}). Copy the CSV prompt in this section to write one.`);
}

/** CSV text -> story spec. Throws with the row number on anything that would make a wrong video. */

export function parseStory(text) {
  const spec = { title: '', world: '', width: 1280, height: 720, fps: 30, wpm: 140, chapters: [], territories: [], labels: [], beats: [] };
  let chapter = null;
  const cardRows = [];
  const rows = parseCsv(text);
  checkColumns(rows[0] ? Object.keys(rows[0]) : []);
  rows.forEach((r, n) => {
    if (r.row === 'beat' || (r.row === 'territory' && r.date)) r.date = normDate(r.date);
    const at = `row ${n + 2} (${r.row})`, x = json(r.extra, at);
    if (r.row === 'plan') Object.assign(spec, { title: r.id, ...x });
    else if (r.row === 'chapter') { chapter = { id: r.id, title: r.text }; spec.chapters.push(chapter); }
    else if (r.row === 'territory') { if (r.date && !/^-?\d{4}-\d{2}$/.test(r.date)) throw new Error(`${at}: date must be YYYY-MM (or empty: the territory then starts with the first beat)`); spec.territories.push({ key: r.id, date: r.date || null, legend: x.legend || [], rules: x.rules || [] }); }
    else if (r.row === 'label') spec.labels.push({ name: r.text, lon: num(r.lon), lat: num(r.lat), kind: x.kind || 'city', min_alt: x.min_alt ?? 40, max_alt: x.max_alt ?? 3000 });
    else if (r.row === 'beat') {
      if (!chapter) throw new Error(`${at}: a beat needs a chapter row before it`);
      if (!/^-?\d{4}-\d{2}$/.test(r.date)) throw new Error(`${at}: date must be YYYY-MM`);
      if (num(r.lon) == null || num(r.lat) == null) throw new Error(`${at}: beat needs lon and lat`);
      const rung = r.rung || 'map';
      if (!['globe', 'map', 'oblique', 'ground'].includes(rung)) throw new Error(`${at}: rung must be globe, map, oblique or ground`);
      spec.beats.push({ id: r.id || `b${spec.beats.length + 1}`, chapter: chapter.id, date: r.date, place: r.place, lon: num(r.lon), lat: num(r.lat), rung,
        alt: num(r.alt), heading: num(r.heading), site: r.site || null, gap: num(r.gap), sentences: splitSentences(r.text), territory: x.territory || null,
        orbit: x.orbit ?? null, seed: x.seed ?? seedOf(r.id, r.place, r.date), shot: x.shot ?? null, path: x.path ?? null,
        landmark: null, landmarkAsked: x.landmark ?? null, factions: x.factions ?? null, names: x.names ?? null, signs: x.signs ?? null, light: x.light ?? null, effects: x.effects ?? null, museum: x.museum ?? null });
    } else if (r.row === 'card') {
      if (!r.id) throw new Error(`${at}: a card needs the id of its beat`);
      if (!x.asset) throw new Error(`${at}: a card needs extra.asset (an image file)`);
      if (x.anchor && !CARD_ANCHORS.includes(x.anchor)) throw new Error(`${at}: card anchor must be ${CARD_ANCHORS.join(', ')}`);
      cardRows.push({ at, beat: r.id, asset: String(x.asset), label: r.text || '', lon: num(r.lon), lat: num(r.lat), t: x.t ?? null, hold: x.hold ?? null, anchor: x.anchor || '', words: x.words || '', kind: x.kind || 'photo' });
    } else if (r.row) throw new Error(`${at}: unknown row type`);
  });
  if (!spec.beats.length) throw new Error('the story has no beat rows');
  for (const bt of spec.beats) bt.cards = [];
  for (const c of cardRows) {   // a card row may sit anywhere in the file: it joins the beat it names
    const bt = spec.beats.find((b) => b.id === c.beat);
    if (!bt) throw new Error(`${c.at}: card names beat "${c.beat}", which does not exist`);
    if (bt.cards.length >= MAX_CARDS) throw new Error(`${c.at}: beat ${bt.id} already has ${MAX_CARDS} photo cards (the most a beat shows)`);
    bt.cards.push({ asset: c.asset, label: c.label, lon: c.lon, lat: c.lat, t: c.t, hold: c.hold, anchor: c.anchor, words: c.words, kind: c.kind });
  }
  for (const t of spec.territories) if (!t.date) t.date = spec.beats[0].date;
  // a territory row with no date starts with the story; a ground scene gets its real place (lib/landmarks.mjs)
  for (const bt of spec.beats) bt.landmark = landmarkFor(bt, { landmark: bt.landmarkAsked });
  return spec;
}
