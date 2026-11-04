// Narration analysis: the narration is the backbone, so everything visual starts here. Sentences, word timings, dates,
// places, people, numbers, the kind of event a sentence describes, the actions and vehicles it names, the time of day and
// weather it implies. Rule-based and deterministic (no network, no model): the same narration always gives the same plan.

const ONES = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13,
  fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 };
const ORD = { first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10, eleventh: 11, twelfth: 12, thirteenth: 13,
  fourteenth: 14, fifteenth: 15, sixteenth: 16, seventeenth: 17, eighteenth: 18, nineteenth: 19, twentieth: 20, thirtieth: 30 };
const SCALE = { hundred: 100, thousand: 1000, million: 1e6 };
export const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];

/** Sentences of a paragraph. Keeps "Gen." / "U.S." / decimals together. */
export function splitSentences(text) {
  const t = String(text).replace(/\s+/g, ' ').trim();
  if (!t) return [];
  const out = []; let cur = '';
  const words = t.split(' ');
  for (let i = 0; i < words.length; i++) {
    cur += (cur ? ' ' : '') + words[i];
    const w = words[i];
    if (/[.!?]["')\]]?$/.test(w) && !/^(?:gen|col|lt|sgt|capt|adm|dr|mr|mrs|st|vs|u\.s|e\.g|i\.e)\.$/i.test(w) && !/^[A-Z]\.$/.test(w)) { out.push(cur); cur = ''; }
  }
  if (cur) out.push(cur);
  return out;
}

/** "one hundred and fifty six thousand" -> 156000 ; returns null when the words are not a number. */
export function wordsToNumber(words) {
  let total = 0, cur = 0, any = false;
  for (const raw of words) {
    const w = raw.toLowerCase().replace(/[^a-z-]/g, '');
    if (!w || w === 'and') continue;
    for (const part of w.split('-')) {
      if (part in ONES) { cur += ONES[part]; any = true; }
      else if (part === 'hundred') { cur = (cur || 1) * 100; any = true; }
      else if (part in SCALE) { total += (cur || 1) * SCALE[part]; cur = 0; any = true; }
      else return null;
    }
  }
  return any ? total + cur : null;
}

/** Numbers in a sentence with what they count: [{value, text, noun}] — digits ("156,000") or words ("seven thousand"). */
export function extractNumbers(text) {
  const out = [];
  const re = /\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(thousand|million)?\s+([a-z][a-z-]+(?:\s+[a-z][a-z-]+)?)/gi;
  let m;
  while ((m = re.exec(text))) {
    const v = parseFloat(m[1].replace(/,/g, '')) * (m[2] ? SCALE[m[2].toLowerCase()] : 1);
    if (v >= 1000 && v <= 2100 && !m[2] && !m[1].includes(',')) continue; // a year, not a count
    out.push({ value: v, text: m[0], noun: m[3].toLowerCase() });
  }
  const tokens = String(text).split(/\s+/);
  for (let i = 0; i < tokens.length; i++) {
    let j = i, best = null;
    while (j < tokens.length && wordsToNumber(tokens.slice(i, j + 1)) !== null) { best = j; j++; }
    if (best !== null && !/^and$/i.test(tokens[i])) {
      const value = wordsToNumber(tokens.slice(i, best + 1));
      const noun = (tokens.slice(best + 1, best + 3).join(' ').toLowerCase().match(/^[a-z][a-z-]*(?:\s+[a-z][a-z-]*)?/) || [''])[0];
      const ordinalNext = /^of$/i.test(tokens[best + 1] || '');
      if (value >= 100 && !ordinalNext) out.push({ value, text: tokens.slice(i, best + 1).join(' '), noun });
      i = best;
    }
  }
  return out;
}

export function formatCount(v) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(v % 1e6 ? 1 : 0)} million`;
  return Math.round(v).toLocaleString('en-US');
}

/** Dates in a sentence: [{label, year, month, day, season}] — "6 June 1944", "June 6, 1944", "the sixth of June", "spring of 1944", "1944". */
export function extractDates(text, contextYear = null) {
  const t = String(text), out = [];
  const mi = (s) => MONTHS.indexOf(s.toLowerCase());
  const ordinal = (s) => { const w = s.toLowerCase().replace(/[^a-z-]/g, ''); if (w in ORD) return ORD[w]; const parts = w.split('-'); if (parts.length === 2 && parts[0] in ONES && parts[1] in ORD) return ONES[parts[0]] + ORD[parts[1]]; return null; };
  let m;
  const r1 = /\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:,?\s+(\d{4}))?/gi;
  while ((m = r1.exec(t))) out.push({ day: +m[1], month: mi(m[2]) + 1, year: m[3] ? +m[3] : contextYear, index: m.index });
  const r2 = /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?/gi;
  while ((m = r2.exec(t))) out.push({ day: +m[2], month: mi(m[1]) + 1, year: m[3] ? +m[3] : contextYear, index: m.index });
  const r3 = /\bthe\s+((?:twenty|thirty)[\s-])?([a-z]+)\s+of\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:,?\s+(\d{4}))?/gi;
  while ((m = r3.exec(t))) {
    const d = ordinal(((m[1] || '').trim() ? `${m[1].replace(/[\s-]+$/, '')}-` : '') + m[2]);
    if (d) out.push({ day: d, month: mi(m[3]) + 1, year: m[4] ? +m[4] : contextYear, index: m.index });
  }
  const r4 = /\b(spring|summer|autumn|fall|winter)\s+(?:of\s+)?(\d{4})/gi;
  while ((m = r4.exec(t))) out.push({ season: m[1].toLowerCase(), year: +m[2], index: m.index });
  const r5 = /\b(?:in\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b/gi;
  while ((m = r5.exec(t))) if (!out.some((d) => Math.abs(d.index - m.index) < 12)) out.push({ month: mi(m[1]) + 1, year: +m[2], index: m.index });
  const r6 = /\b(1[0-9]{3}|20[0-9]{2})\b/g;
  while ((m = r6.exec(t))) if (!out.some((d) => d.year === +m[1])) out.push({ year: +m[1], index: m.index });
  return out.sort((a, b) => a.index - b.index).map((d) => ({ ...d, label: dateLabel(d) }));
}

export function dateLabel(d) {
  if (!d) return '';
  const M = (k) => MONTHS[k - 1].toUpperCase();
  if (d.day && d.month) return `${d.day} ${M(d.month)}${d.year ? ' ' + d.year : ''}`;
  if (d.month) return `${M(d.month)}${d.year ? ' ' + d.year : ''}`;
  if (d.season) return `${d.season.toUpperCase()} ${d.year}`;
  return d.year ? String(d.year) : '';
}

const TITLES = ['General', 'Field Marshal', 'Marshal', 'Admiral', 'President', 'Prime Minister', 'King', 'Queen', 'Emperor', 'Chancellor', 'Colonel', 'Major', 'Captain', 'Lieutenant', 'Sergeant', 'Premier', 'Chairman', 'Commander'];
/** People named with a title: [{title, name, role}] ("General Dwight Eisenhower" -> commander). */
export function extractPeople(text) {
  const out = [];
  const re = new RegExp(`\\b(${TITLES.join('|')})\\s+((?:[A-Z][a-zA-Z'-]+\\s?){1,3})`, 'g');
  let m;
  while ((m = re.exec(text))) {
    const name = m[2].trim().replace(/\s+(?:listened|gave|said|ordered|was|had|and|who)$/, '');
    const title = m[1];
    const role = /General|Marshal|Admiral|Commander|Colonel/.test(title) ? 'commander' : /President|Prime|King|Queen|Emperor|Chancellor|Premier|Chairman/.test(title) ? 'leader' : 'officer';
    out.push({ title, name, role, index: m.index });
  }
  return out;
}

// ---- event classification ----------------------------------------------------------------------------------------------
// keyword -> weight per event type. A sentence takes the best-scoring type; ties go to the earlier type in this list.
export const EVENT_RULES = {
  landing_operation: { landing: 3, landings: 3, ashore: 3, 'landing craft': 3, ramps: 3, ramp: 2, beach: 2, beaches: 2, waded: 3, surf: 2, amphibious: 3 },
  airborne_drop: { paratroopers: 4, parachute: 4, parachutes: 4, airborne: 3, dropped: 1, 'transport planes': 2 },
  naval_operation: { ships: 3, fleet: 3, navy: 3, naval: 3, vessels: 2, warships: 3, sea: 1, convoy: 1, sailed: 2, harbour: 1, harbor: 1 },
  airstrike: { bombers: 3, bombed: 3, bombing: 3, airstrike: 4, 'air raid': 4, raid: 2, bombs: 3 },
  battle: { battle: 3, fought: 3, fire: 2, 'under fire': 3, attack: 2, attacked: 2, assault: 3, fighting: 3, casualties: 2, killed: 2, machine: 1, guns: 2, shelling: 3, cover: 1 },
  ambush: { ambush: 5, ambushed: 5, trap: 2, hidden: 1 },
  defensive_position: { bunkers: 3, defences: 3, defenses: 3, fortified: 3, mines: 2, obstacles: 2, trenches: 3, held: 1, wall: 1, guarded: 2 },
  military_invasion: { invasion: 3, invaded: 4, invade: 3, offensive: 3, crossed: 2, advanced: 2, advance: 2, push: 1 },
  troop_deployment: { soldiers: 1, troops: 1, waited: 2, camp: 3, camps: 3, gathered: 2, assembled: 2, deployed: 3, prepared: 2, training: 2, airfields: 1, ports: 1, tents: 2 },
  convoy_movement: { tanks: 2, trucks: 2, rolled: 3, convoy: 3, columns: 2, inland: 2, countryside: 1, road: 1, roads: 1 },
  city_occupation: { occupied: 3, captured: 3, liberated: 3, liberation: 3, fell: 2, entered: 2, streets: 2, 'in their hands': 4, seized: 3, took: 1 },
  retreat: { retreat: 4, retreated: 4, withdrew: 4, withdrawal: 4, fled: 3 },
  surrender: { surrender: 5, surrendered: 5, capitulated: 5 },
  peace_agreement: { treaty: 4, signed: 3, armistice: 4, peace: 3, agreement: 3, ceasefire: 4 },
  political_meeting: { meeting: 3, met: 2, conference: 3, decision: 2, decided: 2, order: 2, ordered: 2, forecasters: 3, listened: 2, plan: 1, planned: 1, generals: 1, headquarters: 3, council: 3, cabinet: 3 },
  protest: { protest: 4, protesters: 4, demonstration: 4, marched: 1, rally: 3 },
  revolution: { revolution: 4, uprising: 4, rebels: 3, revolt: 4, overthrew: 4 },
  assassination: { assassinated: 5, assassination: 5, shot: 2 },
  natural_disaster: { earthquake: 5, flood: 4, hurricane: 4, storm: 2, tsunami: 5, eruption: 5, famine: 3 },
  evacuation: { evacuated: 4, evacuation: 4, rescued: 3, escape: 2, refugees: 3 },
  civilian_life: { villagers: 3, families: 2, farmers: 3, market: 3, celebrated: 2, cheered: 2, crowds: 2, people: 1 },
  industrial_production: { factories: 4, factory: 4, production: 3, built: 1, workers: 3, produced: 3 },
  infrastructure_construction: { construction: 4, bridge: 2, railway: 3, built: 2, roads: 1 },
  historical_discovery: { discovered: 4, discovery: 4, found: 2, ruins: 3 },
  liberation: { liberated: 4, liberation: 4, welcomed: 3, cheered: 2, cheering: 2, freed: 3 },
  aftermath: { 'by nightfall': 3, 'at a cost': 4, cost: 2, toll: 3, aftermath: 5, wounded: 1, 'were ashore': 2 },
  consequence: { 'road to': 3, 'the end of the war': 3, changed: 2, legacy: 3, 'had opened': 3, 'would never': 2, history: 1 },
  establishing: { had: 0.2, became: 1, vast: 1, region: 1, country: 1, nation: 1, across: 0.5, coast: 1, empire: 1, war: 0.5, opened: 0.5 },
};
export const EVENT_TYPES = Object.keys(EVENT_RULES);

const lowerPad = (s) => ` ${String(s).toLowerCase().replace(/[^a-z0-9' -]+/g, ' ').replace(/\s+/g, ' ')} `;

export function classifyEvent(text) {
  const t = lowerPad(text), scores = {};
  for (const [type, rules] of Object.entries(EVENT_RULES)) {
    let s = 0;
    for (const [k, w] of Object.entries(rules)) if (t.includes(` ${k} `)) s += w;
    scores[type] = s;
  }
  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1] || EVENT_TYPES.indexOf(a[0]) - EVENT_TYPES.indexOf(b[0]));
  const [best, s] = ranked[0];
  return { type: s > 0 ? best : 'establishing', score: s, runnerUp: ranked[1][1] > 0 ? ranked[1][0] : null, scores };
}

// verb/phrase -> animation state (animation.STATES). The matched word's spoken time drives the action.
export const ACTION_WORDS = [
  [/\bwad(?:e|ed|ing)\b/, 'wade'], [/\btook cover|taking cover|take cover|sheltered\b/, 'cover'], [/\bcrouch(?:ed|ing)?\b/, 'crouch'],
  [/\bpoint(?:ed|ing)?\b/, 'point'], [/\bgave the order|ordered|commanded\b/, 'point'], [/\blistened|listening\b/, 'listen'],
  [/\bsalut(?:e|ed|ing)\b/, 'salute'], [/\btalk(?:ed|ing)?|spoke|discuss(?:ed)?|argued|predicted|forecast\b/, 'talk'],
  [/\bmarch(?:ed|ing)?\b/, 'walk'], [/\bwalk(?:ed|ing)?\b/, 'walk'], [/\bran\b|\brushed|charged|sprinted|stormed\b/, 'run'],
  [/\bpushed toward|pushed inland|advanced|moved\b/, 'run'], [/\bfought|firing|fired|shot\b/, 'fire'], [/\bclimb(?:ed|ing)?|scaled\b/, 'climb'],
  [/\bcarr(?:y|ied|ying)|unloaded|loaded\b/, 'carry'], [/\bwait(?:ed|ing)?\b/, 'idle'], [/\bwatched|looked\b/, 'look'],
  [/\bcelebrat(?:ed|ing)|cheer(?:ed|ing)|welcomed\b/, 'cheer'], [/\bsurrender(?:ed)?\b/, 'hands_up'], [/\bfell\b|collapsed\b/, 'fall'],
  [/\blanded|parachuted|dropped\b/, 'parachute'], [/\bboarded|climbed aboard|embarked\b/, 'enter_vehicle'], [/\bdisembarked|jumped out\b/, 'exit_vehicle'],
  [/\bscattered\b/, 'look'], [/\bgestur(?:ed|ing)\b/, 'gesture'], [/\bwaved|waving\b/, 'wave'],
];

/** Actions named in a sentence: [{state, word}] (word = the matched text, for timing). */
export function extractActions(text) {
  const t = String(text).toLowerCase(), out = [];
  for (const [re, state] of ACTION_WORDS) { const m = t.match(re); if (m && !out.some((a) => a.state === state)) out.push({ state, word: m[0].split(' ')[0], index: m.index }); }
  return out.sort((a, b) => a.index - b.index);
}

export const VEHICLE_WORDS = [
  [/\blanding craft\b/, 'landing_craft'], [/\btransport planes?|transport aircraft|c-47s?|dakotas?\b/, 'transport_plane'], [/\bbombers?\b/, 'bomber'],
  [/\bfighters?\b|\bfighter planes?\b|\bspitfires?\b/, 'fighter_prop'], [/\bhelicopters?|choppers?|hueys?\b/, 'helicopter'], [/\bjets?\b/, 'jet'],
  [/\bbattleships?\b/, 'battleship'], [/\bwarships?|destroyers?|cruisers?\b/, 'ship'], [/\bships?|vessels?|fleet\b/, 'ship'], [/\bsubmarines?|u-boats?\b/, 'submarine'],
  [/\btanks?\b/, 'tank'], [/\bjeeps?\b/, 'jeep'], [/\btrucks?|lorries\b/, 'truck'], [/\bhalf-?tracks?\b/, 'halftrack'], [/\bartillery|guns\b|cannons?\b/, 'artillery'],
  [/\bplanes?|aircraft\b/, 'transport_plane'], [/\bradar\b/, 'radar'], [/\bboats?\b/, 'landing_craft'], [/\bbicycles?\b/, 'bicycle'], [/\btrains?\b/, 'train'],
];
export function extractVehicles(text) {
  const t = String(text).toLowerCase(), out = []; let rest = t;
  for (const [re, kind] of VEHICLE_WORDS) { const m = rest.match(re); if (m) { if (!out.includes(kind)) out.push(kind); rest = rest.replace(re, ' '); } }
  return out;
}

export const ENV_WORDS = [
  [/\bbeach(?:es)?|surf|shore|coast(?:line)?\b/, 'beach'], [/\bvillage|hamlet\b/, 'village'], [/\btown\b|streets?\b/, 'town'], [/\bcity|capital\b|\bparis\b/, 'city'],
  [/\bhedgerows?|fields?|farms?|countryside\b/, 'farmland'], [/\bforest|woods\b/, 'forest'], [/\bjungle\b/, 'jungle'], [/\briver|bank\b/, 'river'],
  [/\bmountains?|hills?|bluffs?\b/, 'hills'], [/\bdesert|sand dunes\b/, 'desert'], [/\bairfields?|runways?|airport\b/, 'airfield'], [/\bport|harbou?r|docks?\b/, 'port'],
  [/\bcamps?|base|barracks|tents\b/, 'military_base'], [/\bhouse|headquarters|room|hall|palace|office\b/, 'interior'], [/\bfactor(?:y|ies)\b/, 'factory'],
  [/\bchannel|sea|ocean|waters?\b/, 'sea'], [/\btrenches|no man's land|battlefield\b/, 'battlefield'], [/\bisland\b/, 'island'],
];
export function extractEnvironments(text) {
  const t = String(text).toLowerCase(), out = [];
  for (const [re, env] of ENV_WORDS) if (re.test(t) && !out.includes(env)) out.push(env);
  return out;
}

export function extractTime(text) {
  const t = String(text).toLowerCase();
  if (/\bnight(?:fall)?\b|\bin the dark|midnight|that night/.test(t)) return /nightfall/.test(t) ? 'dusk' : 'night';
  if (/\bsunrise|dawn|first light|daybreak|morning\b/.test(t)) return 'dawn';
  if (/\bsunset|dusk|evening\b/.test(t)) return 'sunset';
  return '';
}
export function extractWeather(text) {
  const t = String(text).toLowerCase();
  if (/\bstorm|gale\b/.test(t)) return 'storm';
  if (/\brain|downpour\b/.test(t)) return 'rain';
  if (/\bfog|mist\b/.test(t)) return 'fog';
  if (/\bsnow|blizzard|winter\b/.test(t)) return 'snow';
  return '';
}

/** Everything the director needs about one sentence. */
export function analyseSentence(text, gaz, contextYear = null) {
  return {
    text, dates: extractDates(text, contextYear), places: gaz ? gaz.find(text).map((p) => p.place) : [], people: extractPeople(text),
    numbers: extractNumbers(text), event: classifyEvent(text), actions: extractActions(text), vehicles: extractVehicles(text),
    environments: extractEnvironments(text), time: extractTime(text), weather: extractWeather(text),
  };
}

// ---- timing ----------------------------------------------------------------------------------------------------------------
const tok = (s) => String(s).toLowerCase().replace(/[^a-z0-9' ]+/g, ' ').split(/\s+/).filter(Boolean);

/** Planned timing without a voiceover: 2.6 words per second, pauses between sentences and longer ones between beats/chapters. */
export function estimateTiming(beats, { wps = 2.6, sentenceGap = 0.45, beatGap = 0.8, chapterGap = 1.8, lead = 1.2 } = {}) {
  let t = lead; const sentences = [];
  beats.forEach((b, bi) => {
    if (bi > 0) t += beats[bi - 1].chapter !== b.chapter ? chapterGap : beatGap;
    splitSentences(b.text).forEach((s, si) => {
      if (si > 0) t += sentenceGap;
      const ws = tok(s), dur = Math.max(1.2, ws.length / wps);
      const words = ws.map((w, k) => ({ word: w, start: t + (k / ws.length) * dur, end: t + ((k + 1) / ws.length) * dur }));
      sentences.push({ beat: bi, text: s, start: t, end: t + dur, words });
      t += dur;
    });
  });
  return { sentences, end: t };
}

/** Align a real voiceover's words (whisper: [{word,start,end}]) to the beats' sentences by greedy token matching with
 *  look-ahead, so a misheard word or two never shifts the rest. Returns the same shape as estimateTiming. */
export function alignTiming(beats, words) {
  const W = words.map((w) => ({ ...w, t: tok(w.word)[0] || '' })).filter((w) => w.t);
  const sentences = []; let j = 0;
  beats.forEach((b, bi) => {
    for (const s of splitSentences(b.text)) {
      const ws = tok(s), matched = [];
      for (const w of ws) {
        let k = -1;
        for (let d = 0; d < 8 && j + d < W.length; d++) if (W[j + d].t === w || (w.length > 4 && W[j + d].t.slice(0, 4) === w.slice(0, 4))) { k = j + d; break; }
        if (k >= 0) { matched.push({ word: w, start: W[k].start, end: W[k].end }); j = k + 1; }
        else matched.push({ word: w, start: null, end: null });
      }
      // fill unmatched words by interpolation between matched neighbours
      for (let i = 0; i < matched.length; i++) if (matched[i].start === null) {
        const prev = matched.slice(0, i).reverse().find((m) => m.start !== null), next = matched.slice(i + 1).find((m) => m.start !== null);
        const a = prev ? prev.end : next ? next.start - 0.3 : (W[j] || W[W.length - 1] || { start: 0 }).start, c = next ? next.start : a + 0.3;
        matched[i].start = a; matched[i].end = Math.max(a + 0.05, Math.min(c, a + 0.35));
      }
      sentences.push({ beat: bi, text: s, start: matched[0].start, end: matched[matched.length - 1].end, words: matched });
    }
  });
  return { sentences, end: sentences.length ? sentences[sentences.length - 1].end : 0 };
}

/** The spoken time of a word in a sentence (first word starting with `key`), or null. */
export function wordTime(sentence, key) {
  if (!key) return null;
  const k = tok(key)[0];
  const w = sentence.words.find((x) => x.word === k || x.word.startsWith(k.slice(0, Math.max(3, k.length - 2))));
  return w ? w.start : null;
}

/** Pauses (gaps between sentences) of at least `min` seconds. */
export function pauses(sentences, min = 0.35) {
  const out = [];
  for (let i = 1; i < sentences.length; i++) { const g = sentences[i].start - sentences[i - 1].end; if (g >= min) out.push({ start: sentences[i - 1].end, end: sentences[i].start, after: i - 1 }); }
  return out;
}
