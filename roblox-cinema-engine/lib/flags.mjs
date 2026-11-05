// Country flags for the on-screen tag: when the narration names a country (or its people), its flag slides in for a few seconds.
// Flags are drawn here as small SVGs (no downloads, no per-video assets, identical on every machine). Pure and deterministic.
// Each svg is drawn on a 30 x 20 box. Countries without an entry simply get no flag.

const star = (cx, cy, R, r = R * 0.4, n = 5, rot = -90) => Array.from({ length: n * 2 }, (_, i) => { const a = ((rot + (i * 180) / n) * Math.PI) / 180, k = i % 2 ? r : R; return `${(cx + Math.cos(a) * k).toFixed(2)},${(cy + Math.sin(a) * k).toFixed(2)}`; }).join(' ');
const hs = (colors) => colors.map((c, i) => `<rect x="0" y="${(20 / colors.length) * i}" width="30" height="${20 / colors.length + 0.05}" fill="${c}"/>`).join('');
const vs = (colors) => colors.map((c, i) => `<rect y="0" x="${(30 / colors.length) * i}" height="20" width="${30 / colors.length + 0.05}" fill="${c}"/>`).join('');
const crescent = (cx, cy, r, fg, bg, dx = r * 0.3) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fg}"/><circle cx="${cx + dx}" cy="${cy}" r="${r * 0.8}" fill="${bg}"/>`;

const usStars = Array.from({ length: 20 }, (_, i) => `<circle cx="${1.6 + (i % 5) * 2.2 + (Math.floor(i / 5) % 2) * 1.1}" cy="${1.5 + Math.floor(i / 5) * 1.9}" r="0.45" fill="#fff"/>`).join('');
const SVG = {
  us: `${Array.from({ length: 13 }, (_, i) => `<rect y="${(20 / 13) * i}" width="30" height="${20 / 13 + 0.05}" fill="${i % 2 ? '#fff' : '#b22234'}"/>`).join('')}<rect width="12.5" height="10.8" fill="#3c3b6e"/>${usStars}`,
  uk: `<rect width="30" height="20" fill="#012169"/><path d="M0 0L30 20M30 0L0 20" stroke="#fff" stroke-width="4"/><path d="M0 0L30 20M30 0L0 20" stroke="#c8102e" stroke-width="1.3"/><path d="M15 0V20M0 10H30" stroke="#fff" stroke-width="6"/><path d="M15 0V20M0 10H30" stroke="#c8102e" stroke-width="3.4"/>`,
  il: `<rect width="30" height="20" fill="#fff"/><rect y="2.2" width="30" height="2.6" fill="#0038b8"/><rect y="15.2" width="30" height="2.6" fill="#0038b8"/><polygon points="15,6.2 19,13 11,13" fill="none" stroke="#0038b8" stroke-width="0.9"/><polygon points="15,13.8 19,7 11,7" fill="none" stroke="#0038b8" stroke-width="0.9"/>`,
  ir: `${hs(['#239f40', '#fff', '#da0000'])}<g fill="none" stroke="#da0000" stroke-width="0.9"><path d="M12.6 12.2C13.4 8.2 14.6 8.2 15 10.2C15.4 8.2 16.6 8.2 17.4 12.2"/><path d="M15 8.4V12.2"/><path d="M11.8 12.8H18.2"/></g><g fill="#fff"><rect y="5.9" width="30" height="0.5"/><rect y="13.7" width="30" height="0.5"/></g>`,
  fr: vs(['#0055a4', '#fff', '#ef4135']), de: hs(['#000', '#dd0000', '#ffce00']), ru: hs(['#fff', '#0039a6', '#d52b1e']), it: vs(['#009246', '#fff', '#ce2b37']),
  cn: `<rect width="30" height="20" fill="#de2910"/><polygon points="${star(5, 5, 3)}" fill="#ffde00"/>${[[10, 2], [12, 4], [12, 7], [10, 9]].map(([x, y]) => `<polygon points="${star(x, y, 1)}" fill="#ffde00"/>`).join('')}`,
  jp: `<rect width="30" height="20" fill="#fff"/><circle cx="15" cy="10" r="6" fill="#bc002d"/>`,
  ua: hs(['#0057b7', '#ffd700']), pl: hs(['#fff', '#dc143c']), nl: hs(['#ae1c28', '#fff', '#21468b']),
  pk: `<rect width="30" height="20" fill="#01411c"/><rect width="7.5" height="20" fill="#fff"/>${crescent(19, 10, 5, '#fff', '#01411c', 1.6)}<polygon points="${star(22.6, 7.6, 1.9)}" fill="#fff"/>`,
  in: `${hs(['#ff9933', '#fff', '#138808'])}<circle cx="15" cy="10" r="2.6" fill="none" stroke="#000080" stroke-width="0.5"/><circle cx="15" cy="10" r="0.5" fill="#000080"/>`,
  tr: `<rect width="30" height="20" fill="#e30a17"/>${crescent(11.5, 10, 5, '#fff', '#e30a17', 1.5)}<polygon points="${star(17.4, 10, 2.1)}" fill="#fff"/>`,
  iq: hs(['#ce1126', '#fff', '#000']),
  eg: hs(['#ce1126', '#fff', '#000']),
  ca: `<rect width="30" height="20" fill="#fff"/><rect width="7.5" height="20" fill="#d52b1e"/><rect x="22.5" width="7.5" height="20" fill="#d52b1e"/><polygon points="15,4 16.4,8 19.4,7.2 17.8,10.4 19.6,11.6 15.6,12.4 15.6,16 14.4,16 14.4,12.4 10.4,11.6 12.2,10.4 10.6,7.2 13.6,8" fill="#d52b1e"/>`,
  es: `<rect width="30" height="20" fill="#aa151b"/><rect y="5" width="30" height="10" fill="#f1bf00"/>`,
  ae: `<rect width="30" height="20" fill="#fff"/><rect width="30" height="6.7" fill="#00732f"/><rect y="13.3" width="30" height="6.7" fill="#000"/><rect width="7.5" height="20" fill="#ff0000"/>`,
  kp: `<rect width="30" height="20" fill="#024fa2"/><rect y="3.2" width="30" height="13.6" fill="#fff"/><rect y="4" width="30" height="12" fill="#ed1c27"/><circle cx="10.5" cy="10" r="3.6" fill="#fff"/><polygon points="${star(10.5, 10, 3.2)}" fill="#ed1c27"/>`,
};

/** name (lower-case, as spoken) -> code, plus the names' people ("iranian") */
const NAMES = {
  us: ['united states', 'usa', 'america', 'american', 'americans', 'u s'], uk: ['united kingdom', 'britain', 'british', 'england', 'english'],
  il: ['israel', 'israeli', 'israelis'], ir: ['iran', 'iranian', 'iranians', 'persia', 'persian'], fr: ['france', 'french'], de: ['germany', 'german', 'germans'],
  ru: ['russia', 'russian', 'russians', 'soviet union', 'soviet'], it: ['italy', 'italian', 'italians'], cn: ['china', 'chinese'], jp: ['japan', 'japanese'],
  ua: ['ukraine', 'ukrainian', 'ukrainians'], pl: ['poland', 'polish'], nl: ['netherlands', 'dutch'], pk: ['pakistan', 'pakistani', 'pakistanis'], in: ['india', 'indian', 'indians'],
  tr: ['turkey', 'turkish'], iq: ['iraq', 'iraqi', 'iraqis'], eg: ['egypt', 'egyptian', 'egyptians'], ca: ['canada', 'canadian'], es: ['spain', 'spanish'],
  ae: ['united arab emirates', 'uae', 'emirates'], kp: ['north korea', 'north korean'],
};
export const COUNTRY_NAME = { us: 'United States', uk: 'United Kingdom', il: 'Israel', ir: 'Iran', fr: 'France', de: 'Germany', ru: 'Russia', it: 'Italy', cn: 'China', jp: 'Japan', ua: 'Ukraine', pl: 'Poland', nl: 'Netherlands', pk: 'Pakistan', in: 'India', tr: 'Turkey', iq: 'Iraq', eg: 'Egypt', ca: 'Canada', es: 'Spain', ae: 'United Arab Emirates', kp: 'North Korea' };
const tokens = (s) => String(s).toLowerCase().replace(/[^a-z0-9' ]+/g, ' ').split(/\s+/).filter(Boolean);
const PHRASES = Object.entries(NAMES).flatMap(([code, list]) => list.map((n) => ({ code, toks: tokens(n) }))).sort((a, b) => b.toks.length - a.toks.length);

export const flagSvg = (code) => (SVG[code] ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20" preserveAspectRatio="none">${SVG[code]}</svg>` : '');
export const hasFlag = (code) => !!SVG[code];

/**
 * Flags to show: [{t0, t1, code, name}] from the timed sentences ({words:[{word,start}]}). A flag appears on the word that names the country
 * and stays `dur` s; the same flag is not repeated within `gap` s of its last appearance; at most `maxAtOnce` show together.
 */
export function flagCues(sentences, { dur = 3.8, gap = 14, maxAtOnce = 3 } = {}) {
  const hits = [];
  for (const s of sentences) {
    const ws = (s.words || []).map((w) => ({ t: w.start, k: tokens(w.word)[0] || '' }));
    for (let i = 0; i < ws.length; i++) for (const p of PHRASES) {
      if (p.toks.every((tk, j) => ws[i + j] && ws[i + j].k === tk)) { hits.push({ code: p.code, t: ws[i].t }); i += p.toks.length - 1; break; }
    }
  }
  hits.sort((a, b) => a.t - b.t);
  const out = [], lastAt = {};
  for (const h of hits) {
    if (!SVG[h.code] || (lastAt[h.code] != null && h.t - lastAt[h.code] < gap)) continue;
    if (out.filter((c) => c.t1 > h.t).length >= maxAtOnce) continue;
    lastAt[h.code] = h.t; out.push({ t0: +h.t.toFixed(3), t1: +(h.t + dur).toFixed(3), code: h.code, name: COUNTRY_NAME[h.code] });
  }
  return out;
}
