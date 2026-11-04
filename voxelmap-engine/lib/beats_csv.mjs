// The story CSV. Same row-type convention as Hybrid's beat CSV (hybrid/beat_csv.py: a `row` column naming plan / chapter /
// beat rows, rarely edited values as JSON in `extra`), with this engine's own columns. Hybrid's parser is not used: its
// rows carry Hybrid camera modes and layers that mean nothing here.
//
//   row        plan | chapter | territory | label | beat
//   plan       id = title, extra = {world, width, height, fps, wpm, subtitle (shown under the title on a globe opening)}
//   chapter    id, text = title (the beats after it belong to it)
//   territory  id = key, date = YYYY-MM it starts, extra = {legend: [{label, color}], rules: [...]}   (see lib/territory.mjs)
//   label      text = name, lon, lat, extra = {kind: country|city, min_alt, max_alt}
//   beat       id, date = YYYY-MM, place, lon, lat, rung = globe|map|oblique|ground, alt, heading, site = recipe, gap = seconds of
//              silence before it (planned narration gap), text = the narration (sentences),
//              extra = {territory, seed, shot (see lib/director.mjs), path: [[lon, lat], ...] for an aerial track,
//                       factions: [..] (lib/figures.mjs), names: ["Gen. X"], signs: ["WELCOME"], light: day|sunset|night|fog|dawn,
//                       effects: [{kind: blasts|smoke|fires|planes, at: [lon, lat], to?: [lon, lat]}], museum: {item, name, note}}

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

/** CSV text -> story spec. Throws with the row number on anything that would make a wrong video. */
export function parseStory(text) {
  const spec = { title: '', world: '', width: 1280, height: 720, fps: 30, wpm: 140, chapters: [], territories: [], labels: [], beats: [] };
  let chapter = null;
  parseCsv(text).forEach((r, n) => {
    const at = `row ${n + 2} (${r.row})`, x = json(r.extra, at);
    if (r.row === 'plan') Object.assign(spec, { title: r.id, ...x });
    else if (r.row === 'chapter') { chapter = { id: r.id, title: r.text }; spec.chapters.push(chapter); }
    else if (r.row === 'territory') { if (!/^\d{4}-\d{2}$/.test(r.date)) throw new Error(`${at}: date must be YYYY-MM`); spec.territories.push({ key: r.id, date: r.date, legend: x.legend || [], rules: x.rules || [] }); }
    else if (r.row === 'label') spec.labels.push({ name: r.text, lon: num(r.lon), lat: num(r.lat), kind: x.kind || 'city', min_alt: x.min_alt ?? 40, max_alt: x.max_alt ?? 3000 });
    else if (r.row === 'beat') {
      if (!chapter) throw new Error(`${at}: a beat needs a chapter row before it`);
      if (!/^\d{4}-\d{2}$/.test(r.date)) throw new Error(`${at}: date must be YYYY-MM`);
      if (num(r.lon) == null || num(r.lat) == null) throw new Error(`${at}: beat needs lon and lat`);
      const rung = r.rung || 'map';
      if (!['globe', 'map', 'oblique', 'ground'].includes(rung)) throw new Error(`${at}: rung must be globe, map, oblique or ground`);
      spec.beats.push({ id: r.id || `b${spec.beats.length + 1}`, chapter: chapter.id, date: r.date, place: r.place, lon: num(r.lon), lat: num(r.lat), rung,
        alt: num(r.alt), heading: num(r.heading), site: r.site || null, gap: num(r.gap), sentences: splitSentences(r.text), territory: x.territory || null,
        orbit: x.orbit ?? null, seed: x.seed ?? seedOf(r.id, r.place, r.date), shot: x.shot ?? null, path: x.path ?? null,
        factions: x.factions ?? null, names: x.names ?? null, signs: x.signs ?? null, light: x.light ?? null, effects: x.effects ?? null, museum: x.museum ?? null });
    } else if (r.row) throw new Error(`${at}: unknown row type`);
  });
  if (!spec.beats.length) throw new Error('the story has no beat rows');
  return spec;
}
