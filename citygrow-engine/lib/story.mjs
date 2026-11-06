// Story CSV for a city timelapse. One row per line, `row` says what it is:
//   plan      — city, world, center (lon,lat), size (km), title, music (file), seed
//   era       — year, era_name, flag, population, caption, title, kicker, style, shot, focus, hold
//   district  — a place the city starts or grows from: year, focus (lon,lat), weight
//   landmark  — kind, focus (lon,lat), year (built), until (gone), extra JSON (size, rot, path, minarets…)
//   event     — kind (fire / siege / quake / flood), year, focus (lon,lat), radius (m), caption
// Extra settings go in the `extra` column as JSON. Years: "-658", "658 BC", "AD 540", "540", "c. 1200".

export const COLUMNS = ['row', 'year', 'until', 'era_name', 'flag', 'population', 'caption', 'title', 'kicker', 'style', 'shot', 'focus', 'hold', 'kind', 'radius', 'weight', 'extra'];

export function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') q = false;
      else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); cell = '';
      if (row.some((c) => c.trim() !== '')) rows.push(row);
      row = [];
    } else cell += ch;
  }
  row.push(cell); if (row.some((c) => c.trim() !== '')) rows.push(row);
  return rows;
}

/** "-658" | "658 BC" | "658 BCE" | "AD 540" | "540 AD" | "c. 1200" | "1200s" -> signed year (BC negative). null if none. */
export function parseYear(v) {
  if (v == null) return null;
  const s = String(v).trim().toUpperCase().replace(/^C(IRCA|A)?\.?\s*/, '');
  if (!s) return null;
  const m = s.match(/^(-?\d{1,5})\s*(S)?\s*(BCE?|B\.C\.?|AD|CE|A\.D\.?)?$/) || s.match(/^(?:AD|A\.D\.?|CE)\s*(\d{1,5})$/);
  if (!m) return null;
  let y = Number(m[1]);
  if (m[3] && /^B/.test(m[3])) y = -Math.abs(y);
  return y;
}

/** A year as the counter shows it: "658 BC", "AD 540" (only while the story crosses into AD), "1319". */
export function yearLabel(y, { adPrefix = false } = {}) {
  const r = Math.round(y);
  if (r < 0) return `${-r} BC`;
  if (r === 0) return '1 BC';
  return adPrefix && r < 1000 ? `AD ${r}` : String(r);
}

export function parseLonLat(v) {
  if (!v) return null;
  const m = String(v).match(/(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)/);
  return m ? { lon: Number(m[1]), lat: Number(m[2]) } : null;
}

const num = (v) => { if (v == null || String(v).trim() === '') return null; const n = Number(String(v).replace(/[,_\s]/g, '').replace(/^c\.?/i, '')); return Number.isFinite(n) ? n : null; };
function json(v, warn, where) { if (!v || !String(v).trim()) return {}; try { return JSON.parse(v); } catch { warn(`${where}: extra is not valid JSON (ignored)`); return {}; } }

export function parseStory(text) {
  const rows = parseCsv(text.replace(/^﻿/, ''));
  if (!rows.length) throw new Error('story CSV is empty');
  const head = rows[0].map((h) => h.trim().toLowerCase());
  if (!head.includes('row')) throw new Error('story CSV needs a header with a "row" column');
  const warnings = [], warn = (m) => warnings.push(m);
  const story = { plan: {}, eras: [], districts: [], landmarks: [], events: [], warnings };
  rows.slice(1).forEach((cells, k) => {
    const r = {}; head.forEach((h, i) => { r[h] = (cells[i] ?? '').trim(); });
    const line = k + 2, type = r.row.toLowerCase(), extra = json(r.extra, warn, `line ${line}`);
    if (type === 'plan') {
      Object.assign(story.plan, { city: r.era_name || r.title || extra.city, center: parseLonLat(r.focus), ...extra });
      if (r.title) story.plan.title = r.title;
    } else if (type === 'era') {
      const year = parseYear(r.year);
      if (year == null) { warn(`line ${line}: era has no readable year ("${r.year}") — skipped`); return; }
      story.eras.push({ line, year, name: r.era_name, flag: r.flag, population: num(r.population), caption: r.caption,
        title: r.title, kicker: r.kicker, style: r.style || null, shot: r.shot || null, focus: parseLonLat(r.focus),
        focusId: !parseLonLat(r.focus) && r.focus ? r.focus : null, hold: num(r.hold), extra });
    } else if (type === 'district') {
      const at = parseLonLat(r.focus);
      if (!at) { warn(`line ${line}: district needs focus "lon,lat" — skipped`); return; }
      story.districts.push({ line, year: parseYear(r.year), ...at, weight: num(r.weight) || 1, name: r.era_name || r.title || '' });
    } else if (type === 'landmark') {
      const at = parseLonLat(r.focus);
      if (!at && !extra.path) { warn(`line ${line}: landmark needs focus "lon,lat" or a path — skipped`); return; }
      story.landmarks.push({ line, id: extra.id || r.era_name || `lm${line}`, kind: (r.kind || 'tower').toLowerCase(), ...(at || {}),
        year: parseYear(r.year), until: parseYear(r.until), name: r.era_name || '', extra });
    } else if (type === 'event') {
      const at = parseLonLat(r.focus), year = parseYear(r.year);
      if (!at || year == null) { warn(`line ${line}: event needs a year and focus "lon,lat" — skipped`); return; }
      story.events.push({ line, kind: (r.kind || 'fire').toLowerCase(), year, ...at, radius: num(r.radius) || 600,
        caption: r.caption, regrow: extra.regrow, down: extra.down });
    } else warn(`line ${line}: unknown row type "${r.row}" — skipped`);
  });
  if (!story.eras.length) throw new Error('story has no era rows');
  for (let i = 1; i < story.eras.length; i++) {
    if (story.eras[i].year <= story.eras[i - 1].year) warn(`line ${story.eras[i].line}: year ${story.eras[i].year} is not after the era before it`);
  }
  // populations: fill gaps from neighbours so the counter never jumps to nothing
  const known = story.eras.filter((e) => e.population != null);
  if (!known.length) { warn('no era has a population: using 10,000 throughout'); story.eras.forEach((e) => { e.population = 10000; }); }
  else story.eras.forEach((e, i) => {
    if (e.population != null) return;
    const prev = [...story.eras.slice(0, i)].reverse().find((x) => x.population != null), next = story.eras.slice(i + 1).find((x) => x.population != null);
    e.population = prev && next ? Math.round(prev.population + (next.population - prev.population) * (e.year - prev.year) / (next.year - prev.year)) : (prev || next).population;
    warn(`line ${e.line}: no population, using ${e.population.toLocaleString('en-US')}`);
  });
  return story;
}

/** House look by period, when the era row does not name one. */
export function styleForYear(y) {
  if (y < 400) return 'ancient';
  if (y < 1500) return 'medieval';
  if (y < 1800) return 'early_modern';
  if (y < 1930) return 'industrial';
  return 'modern';
}
