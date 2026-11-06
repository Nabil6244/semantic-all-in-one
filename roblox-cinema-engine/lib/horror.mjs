// Horror story mode. A plan row with extra.genre = "horror" (or the app's Story type switch) turns the film from a war/history
// documentary into a quiet modern story: one or two people on an empty street or in a room, the same hero in every scene, no
// soldiers, no crowds, no statistic callouts. Everything here is general (any horror script), never tuned to one video.
// Additions only: a story without the genre takes none of these paths, so history films plan exactly as before.

export const HORROR_ROLES = new Set(['hero', 'stranger', 'mother', 'parent']);

/** the hero and the stranger keep one face across the film: their groups are named, so the look is seeded by the name */
const HERO = { role: 'hero', count: 1, side: 'civ', named: true, name: 'Hero' };
const STRANGER = { role: 'stranger', count: 1, side: 'civ', named: true, name: 'Stranger' };

// recipes: cast, set, cameras and bed for each kind of horror beat (same shape as lib/recipes.mjs)
export const HORROR_RECIPES = {
  quiet_moment: { env: 'town', intent: 'the hero alone in an empty place', cast: [{ ...HERO, formation: 'center', action: 'look' }], vehicles: [], fx: [],
    shots: ['hold_breathe', 'side_track', 'creep_in', 'low_angle'], ambience: 'horror_street', cues: [] },
  encounter: { env: 'town', intent: 'a stranger stops in front of the hero', cast: [{ ...HERO, formation: 'center', action: 'look' }, { ...STRANGER, formation: 'front', action: 'idle' }], vehicles: [], fx: [],
    shots: ['over_shoulder', 'creep_in', 'hold_breathe', 'low_angle', 'static_close'], ambience: 'horror_street', cues: [] },
  pursuit_slow: { env: 'town', intent: 'the hero walks on and something keeps pace behind', cast: [{ ...HERO, formation: 'center', action: 'walk' }, { ...STRANGER, formation: 'behind', action: 'walk' }], vehicles: [], fx: [],
    shots: ['behind_follow', 'ground_track', 'side_track', 'over_shoulder'], ambience: 'horror_street', cues: [] },
  alone_inside: { env: 'interior', room: 'kitchen', intent: 'the hero at home with what they found', cast: [{ ...HERO, formation: 'mark', action: 'look' }], vehicles: [], fx: [],
    shots: ['establishing_interior', 'creep_in', 'hold_breathe'], ambience: 'horror_room', cues: [] },
  phone_call: { env: 'interior', room: 'kitchen', intent: 'a call the hero must not trust', cast: [{ ...HERO, formation: 'mark', action: 'listen' }], vehicles: [], fx: [],
    shots: ['hold_breathe', 'creep_in', 'over_shoulder', 'establishing_interior'], ambience: 'horror_room', cues: [] },
  flashback: { env: 'town', intent: 'a memory from long ago', cast: [{ role: 'child', count: 1, side: 'civ', named: true, name: 'Hero (young)', formation: 'center', action: 'look' }, { ...STRANGER, formation: 'front', action: 'idle' }], vehicles: [], fx: [],
    shots: ['dolly_in', 'low_angle', 'creep_in'], ambience: 'horror_street', cues: [] },
  refuge: { env: 'interior', room: 'hallway', intent: 'the hero reaches someone who loves them', cast: [{ ...HERO, formation: 'mark', action: 'listen' }, { role: 'parent', count: 1, side: 'civ', named: true, name: 'Loved one', formation: 'mark', action: 'talk' }], vehicles: [], fx: [],
    shots: ['establishing_interior', 'over_shoulder', 'creep_in'], ambience: 'horror_room', cues: [] },
};

/** which sets suit each horror beat (a place's biome is only used when it is one of these) */
export const HORROR_EVENT_ENVS = {
  quiet_moment: ['town', 'city', 'village'], encounter: ['town', 'city', 'village'], pursuit_slow: ['town', 'city', 'village'], flashback: ['town', 'city', 'village', 'farmland'],
  alone_inside: ['interior'], phone_call: ['interior'], refuge: ['interior'],
};

// keyword -> weight per horror beat; a beat that scores nothing is a quiet_moment
export const HORROR_RULES = {
  encounter: { 'a child': 2, 'the child': 2, 'holds out': 2, doorbell: 3, 'open the door': 3, porch: 1, stranger: 2, 'old woman': 3, 'old man': 3, woman: 1, handed: 2, hands: 1, gave: 2, gift: 2, offer: 2, offering: 2, 'in front of you': 3, smiling: 1, smiled: 1, 'bus stop': 2, 'bus shelter': 2, shelter: 1 },
  pursuit_slow: { behind: 2, following: 3, followed: 3, 'walk away': 3, 'keep walking': 3, walking: 1, footsteps: 2, chasing: 2, "don't turn": 3, 'do not turn': 3, 'calls your name': 2, 'call your name': 2, run: 1, running: 1 },
  phone_call: { phone: 3, rings: 3, ringing: 3, call: 2, 'on the line': 4, 'hang up': 4, voice: 1, answer: 1 },
  alone_inside: { home: 2, house: 2, table: 2, kitchen: 3, pocket: 1, coat: 1, 'light on': 2, 'lights on': 2 },
  flashback: { 'years ago': 4, 'long time ago': 4, 'when you were': 4, 'as a child': 3, childhood: 3, 'nine-year-old': 3, remember: 2, ago: 1 },
  refuge: { 'loves you': 4, 'who loves': 3, doorway: 3, 'wake them': 3, safe: 2, 'out loud': 2 },
};

/** the film is a horror story when its plan row says so */
export const isHorror = (story) => String(story?.plan?.extra?.genre || '').toLowerCase() === 'horror';

const lowerPad = (s) => ` ${String(s).toLowerCase().replace(/[’‘]/g, "'").replace(/[^a-z0-9' -]+/g, ' ').replace(/\s+/g, ' ')} `;

/** the horror beat a narration describes: {type, scores}; ties go to the earlier rule */
export function classifyHorror(text) {
  // "you'll want to remember", "remember this": a warning about now, not a memory
  const t = lowerPad(text).replace(/ (?:want to|have to|need to|must|should|always|just|please|and) remember /g, ' ').replace(/ remember (?:this|that|these|those|the rule) /g, ' '), scores = {};
  for (const [type, rules] of Object.entries(HORROR_RULES)) { let s = 0; for (const [k, w] of Object.entries(rules)) if (t.includes(` ${k} `)) s += w; scores[type] = s; }
  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  return { type: ranked[0][1] > 0 ? ranked[0][0] : 'quiet_moment', scores };
}

/** actions read from horror narration that belong to war films, never to a quiet story (a CSV action is always kept) */
export const COMBAT_STATES = new Set(['aim', 'fire', 'salute', 'march', 'parachute', 'wade', 'cover', 'crawl', 'hands_up', 'enter_vehicle', 'exit_vehicle', 'ride']);

// sounds the narration names, placed on the spoken word (once per scene each): [cue, word test, sentence test or null, gain dB]
const CUE_RULES = [
  ['phone_ring', /^(rings?|ringing|rang)$/, /\bphone\b/i, -20],
  ['paper_rustle', /^(rustl\w*|crinkl\w*)$/, null, -24],
  ['door_chime', /^chim(e|es|ed)$/, null, -22],
  ['footsteps_slow', /^(footsteps?|steps)$/, null, -24],
  ['whisper_name', /^(whisper\w*|calls?|calling|called)$/, /\byour name\b/i, -26],
];

const NEGATION = /^(not|no|never|without|don't|dont|nor)$/;

/** word-timed horror cues for one scene: [{t, cue, gain, scene}] */
export function horrorCues(scene, wordTime) {
  const out = [];
  for (const [cue, word, need, gain] of CUE_RULES) {
    for (const s of scene.sentences) {
      if (need && !need.test(s.text)) continue;
      const w = s.words.find((x, k) => word.test(x.word) && !NEGATION.test(s.words[k - 1]?.word || '')); if (!w) continue;   // "not footsteps" makes no sound
      const t = w.start ?? wordTime(s, w.word); if (t == null) continue;   // a word the voice-over did not match has no time
      if (t >= scene.t0 && t < scene.t1) { out.push({ t: +t.toFixed(3), cue, gain, scene: scene.id }); break; }
    }
  }
  return out;
}

/** the bed under a horror scene: rain on the street or on the window, or the place's own quiet, always with the drone */
export const horrorBed = (scene, bed) => (scene.weather === 'rain' || scene.weather === 'storm') ? (scene.env === 'interior' ? 'horror_room_rain' : 'horror_rain')
  : bed && bed.startsWith('horror_') ? bed : scene.env === 'interior' ? 'horror_room' : 'horror_street';

// street sets a beat names (lib/world.mjs streetSet): the words in the CSV location first, then the narration
export const QUIET_FX = new Set(['rain', 'rain_light', 'fog', 'haze', 'dust_motes', 'snow']);   // no fires, smoke or confetti in a quiet story, whatever a CSV row asks
/** a CSV written for a history film names its lead "civilian:You": in a horror story that person is the hero */
export const isHeroName = (name) => /^(you|your?self|hero|narrator|protagonist)$/i.test(String(name || '').trim());
const SHEET_WORDS = /\bwhite sheets?\b|\bbed ?sheets?\b|\bin a (?:plain )?(?:white )?sheet\b|\bsheet with\b|\bghost costumes?\b/i;
/** a history film builds these only when they are really named: anything the CSV's location or props say, and unmistakable words in the narration ("stores of grain" is no shop) */
export const STRONG_SET_WORDS = /\bbus (?:stop|shelter)s?\b|\bporch(?:es)?\b|\bdoorsteps?\b|\bfront doors?\b|\bdoorbells?\b|\bpumpkins?\b|\b(?:candy|sweet|toy) (?:shop|store)\b|\bbakery\b/i;
/** the film's unnamed child wears the sheet its narration describes, in every beat. A child with a name of their own (Eli) does not. */
export const wearsSheet = (filmText, role, name) => role === 'child' && (!name || /^(child|kid|the child)$/i.test(name)) && SHEET_WORDS.test(filmText);
const SET_WORDS = [
  [/\bbus (?:stop|shelter|station)s?\b/i, 'bus_stop'],
  [/\b(?:candy|sweet|sweets|toy|corner|gift|all-night|night) (?:shop|store)\b|\bsweet ?shop\b|\bbakery\b|\bshop\b|\bstore\b/i, 'shop'],
  [/\bporch(?:es)?\b|\bdoorsteps?\b|\bfront doors?\b|\bdoor ?mats?\b|\bdoorbells?\b|\bfront (?:steps?|lawn|yard)\b|\bpumpkins?\b/i, 'porch'],
];
const SHOP_LABEL = [[/\b(candy|sweet|sweets)\b/i, 'CANDY'], [/\bbakery\b/i, 'BAKERY'], [/\btoy\b/i, 'TOYS']];

/** {set, label} for a beat, or null. A set carries into the next beat while the same moment goes on (same event, same place). */
export function streetSetFor(text, location, last) {
  for (const src of [location, text]) for (const [re, set] of SET_WORDS) {
    const m = String(src || '').match(re);
    if (m) { const lab = set === 'shop' ? (SHOP_LABEL.find(([r]) => r.test(src)) || [null, 'SHOP'])[1] : null; return { set, label: lab, why: `"${m[0]}" in the ${src === location ? 'location' : 'narration'}` }; }
  }
  return last ? { set: last.set, label: last.setLabel, why: `the same moment goes on at the ${last.set.replace('_', ' ')}` } : null;
}

// ---- things people hold (Step 4) --------------------------------------------------------------------------------------------
// [item, words, who holds it]. 'give' = the stranger holds it until the narration puts it in the hero's hand, then the hero does.
export const HELD_ITEMS = ['paper_bag', 'gift_small', 'letter', 'card_id', 'drawing', 'phone'];
const ITEM_WORDS = [
  ['paper_bag', /\b(?:paper )?bags?\b/i, 'stranger'],
  ['gift_small', /\b(candy|candies|sweets?|butterscotch|toffees?|wrappers?|gift|lollipops?|chocolates?)\b/i, 'give'],
  ['letter', /\b(letters?|envelopes?)\b/i, 'hero'],
  ['card_id', /\b(licen[cs]es?|id card|passport|badge)\b/i, 'hero'],
  ['drawing', /\b(drawings?|drew)\b/i, 'hero'],
  ['phone', /\bphones?\b/i, 'hero'],
];
const GIVEN = /\b(?:in|into) your (?:open )?hands?\b|\bgives? (?:it to )?you\b|\bhand(?:s|ed)? you\b|\bplaces? it in\b|\bpresses? (?:it|a .{0,20}) into\b|\bholds? (?:it )?out\b/i;
const PUT_AWAY = /\b(?:in|into) (?:your|the) (?:inside )?pockets?\b|\bput it away\b|\bthrow it away\b|\bdrop it\b/i;
const COLOURS = [[/\bgold(?:en)?\b/i, '#d9b13b'], [/\bsilver\b/i, '#c9cdd2'], [/\bred\b/i, '#c0392b'], [/\bgreen\b/i, '#3f9a4a'], [/\bblue\b/i, '#2f6fb0'], [/\bpurple\b/i, '#7a4a9a'], [/\bwhite\b/i, '#eeeeee']];
const firstWordTime = (scene, re, wordTime) => {
  for (const s of scene.sentences) { const m = s.text.match(re); if (m) { const w = m[0].split(/\s+/)[0]; return wordTime(s, w) ?? s.start; } }   // the phrase's first word
  return null;
};

/** the words name the thing as present somewhere in the text, not only as "no X" */
const saidAsThere = (text, re) => [...text.matchAll(new RegExp(re.source, 'gi'))].some((m) => !NOT_THERE.test(text.slice(0, m.index)));

/** what each person holds in a scene, and when: [{role, item, color, hand, t0, t1, why}]. last = the scene before when the same moment goes on. */
export function horrorHolds(scene, wordTime, last, lead = 'hero') {
  const text = scene.text, roles = new Set(scene.cast.map((c) => c.role)), out = [];
  const giver = roles.has('stranger') ? 'stranger' : roles.has(lead) && lead !== 'child' && roles.has('child') ? 'child' : null;   // whoever stands in front of the hero and offers it
  const holder = (who) => who === 'stranger' ? (giver || (roles.has(lead) ? lead : null)) : roles.has(lead) ? lead : roles.has('child') ? 'child' : null;
  for (const [item, re, who] of ITEM_WORDS) {
    if (item === 'phone' && scene.env === 'interior') continue;          // indoors the phone is part of the room (lib/rooms.mjs)
    if (!saidAsThere(text, re)) continue;   // "No bag." puts no bag in anyone's hand
    const color = item === 'gift_small' ? (COLOURS.find(([c]) => c.test(text)) || [null, '#d9b13b'])[1] : null;
    if (who === 'give') {
      const tGive = GIVEN.test(text) ? firstWordTime(scene, GIVEN, wordTime) : null;
      if (tGive != null && giver && roles.has(lead)) {
        out.push({ role: giver, item, color, hand: 'R', t0: scene.t0, t1: tGive, why: `the ${giver} holds it out` });
        out.push({ role: lead, item, color, hand: 'R', t0: tGive, t1: scene.t1, at: tGive, handover: giver, why: `given into the ${lead}'s hand` });
      } else { const r = tGive != null || /\byour\b/i.test(text) ? holder(lead) : holder('stranger'); if (r) out.push({ role: r, item, color, hand: 'R', t0: scene.t0, t1: scene.t1, at: firstWordTime(scene, re, wordTime), why: `"${text.match(re)[0]}" in the narration` }); }
      continue;
    }
    const r = holder(who); if (r && !out.some((h) => h.role === r && h.hand === (item === 'paper_bag' ? 'L' : 'R')))
      out.push({ role: r, item, color, hand: item === 'paper_bag' ? 'L' : 'R', t0: scene.t0, t1: scene.t1, at: firstWordTime(scene, re, wordTime), why: `"${text.match(re)[0]}" in the narration` });
  }
  // the same moment goes on: what was still in a hand at the end of the scene before stays there (unless it is put away)
  if (last && last.holds) for (const h of last.holds) {
    if (h.t1 < last.t1 - 0.05 || !roles.has(h.role) || out.some((o) => o.role === h.role && o.hand === h.hand)) continue;
    const tAway = PUT_AWAY.test(text) && h.role === lead ? firstWordTime(scene, PUT_AWAY, wordTime) : null;
    const { at, ...rest } = h; out.push({ ...rest, t0: scene.t0, t1: tAway ?? scene.t1, why: tAway != null ? 'still in the hand until it is put away' : 'still in the hand (the same moment goes on)' });
  }
  return out;
}

// ---- the dry circle (Step 4): rain that does not touch one person ----------------------------------------------------------
const DRY_WORDS = /\b(?:isn't|is not|wasn't|was not|doesn't|does not|never) (?:falling|fall|landing|touching|touch) (?:on )?(?:her|him)\b|\bdry in a (?:perfect )?circle\b|\b(?:ground|pavement|street) (?:around|under|beneath) (?:her|him)(?: feet)? (?:is|was|stays) dry\b|\brain (?:doesn't|does not|won't|will not) touch (?:her|him)\b|\bweather hasn't been invited\b/i;
export const DRY_RADIUS = 3.4;
/** the person the rain avoids in this scene (the stranger), when the narration says so */
export const dryCircleFor = (scene) => DRY_WORDS.test(scene.text) && scene.cast.some((c) => c.role === 'stranger') && scene.env !== 'interior' ? { role: 'stranger', r: DRY_RADIUS } : null;
/** rain streaks to skip: [{x, z, r}] at time t (used by the renderer, tested in Node) */
export function dryCircles(A, t) {
  const d = A.scene.dry; if (!d) return [];
  return A.stage.actors.filter((a) => a.role === d.role).map((a) => { const s = A.actorAt(a, t); return { x: s.x, z: s.z, r: d.r }; });
}
export const inDry = (circles, x, z) => circles.some((c) => (x - c.x) ** 2 + (z - c.z) ** 2 < c.r * c.r);

// ---- picture cards (Step 5): close-up details the blocky world cannot show ---------------------------------------------------
// A name on a wrapper, a child's handwriting, drawings with blank faces, a blank ID or letter, a phone or clock showing the time.
// A beat's card comes from the CSV (extra.card, or a `card: ...` prop), or else from the narration's own words. The camera pushes
// into the held thing, then the film dissolves to the card (web/card_art.js, web/look.js). Every kind can be drawn in code, so a
// picture that never arrived still gives a card: never a blank screen. Pictures come through the Visuals tab (cards.py).
export const CARD_KINDS = ['phone_screen', 'clock', 'name', 'handwriting', 'drawing', 'id_card', 'letter', 'note'];
export const CARD_PUSH = 1.5;     // seconds of push into the object before the dissolve starts
const CARD_GAP = 6;               // cards the narration implies stay this far apart (a CSV card is always kept)
const CODE_MADE = new Set(['phone_screen', 'clock', 'name']);   // drawn in code unless the CSV names a picture for them
const CARD_ITEM = { phone_screen: 'phone', clock: null, name: 'letter', handwriting: 'letter', drawing: 'drawing', id_card: 'card_id', letter: 'letter', note: 'letter' };
const CARD_SEARCH = {   // what a narrated card's picture shows
  handwriting: "a child's pencil handwriting on lined school paper", drawing: "a child's crayon drawing of people", id_card: "a driver's license card with an empty photo box",
  letter: 'an old folded handwritten letter', note: 'a small handwritten note on paper',
};
const HOURS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 };
const ONES = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9 };
const TEENS = { ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19 };
const TENS = { twenty: 20, thirty: 30, forty: 40, fifty: 50 };
const pad2 = (n) => String(n).padStart(2, '0');
const WORD_TIME = new RegExp(`\\b(${Object.keys(HOURS).join('|')})[ -](?:(oh)[ -](${Object.keys(ONES).join('|')})|(${Object.keys(TENS).join('|')})(?:[ -](${Object.keys(ONES).join('|')}))?|(${Object.keys(TEENS).join('|')}))\\b`, 'i');

/** "11:40", "3 a.m.", "eleven forty", "three oh five", "midnight" -> {time, match, index}; null when the text names no clock time */
export function timeIn(text) {
  const s = String(text || '');
  let m = s.match(/\b(\d{1,2}):([0-5]\d)\b/);
  if (m && Number(m[1]) <= 24) return { time: `${Number(m[1])}:${m[2]}`, match: m[0], index: m.index };
  m = s.match(WORD_TIME);
  if (m) { const k = (x) => (x || '').toLowerCase(), min = m[2] ? ONES[k(m[3])] : m[4] ? TENS[k(m[4])] + (m[5] ? ONES[k(m[5])] : 0) : TEENS[k(m[6])]; return { time: `${HOURS[k(m[1])]}:${pad2(min)}`, match: m[0], index: m.index }; }
  m = s.match(/\b(\d{1,2})\s?[ap]\.?m\b/i);
  if (m && Number(m[1]) >= 1 && Number(m[1]) <= 12) return { time: `${Number(m[1])}:00`, match: m[0], index: m.index };
  m = s.match(new RegExp(`\\b(${Object.keys(HOURS).join('|')})\\s(?:[ap]\\.?m\\b|o'clock\\b)`, 'i'));
  if (m) return { time: `${HOURS[m[1].toLowerCase()]}:00`, match: m[0], index: m.index };
  m = s.match(/\bmidnight\b/i);
  return m ? { time: '12:00', match: m[0], index: m.index } : null;
}

const SCREEN_WORDS = /\b(phones?|screens?|cell|mobile|texts?)\b/i;
const TIME_CONTEXT = /\b(phones?|screens?|clocks?|watch|watches|time|reads?|says?|shows?|showing|display\w*)\b/i;
const NAME_WORDS = /\b(?:your|a|his|her|their|my|the) name\b.{0,30}?\b(?:printed|written|scrawled|scribbled|signed|stamped|inked|in (?:\w+ )?ink|in pencil)\b|\b(?:printed|written|scrawled|scribbled|signed|stamped|inked)\b.{0,30}?\b(?:your|a|his|her|their|my|the) name\b|\bname (?:on|in) (?:the|a|that|this) wrapper\b/i;
const DRAWING_WORDS = /\bdrawings?\b(?! (?:closer|near|back|away|breath))|\bdrew (?:you|your|me|him|her|them|us|pictures?|faces?|people|this|that|a (?:picture|face|house|family|person|figure|man|woman|child|circle))\b|\bcrayons?\b/i;
const ID_WORDS = /\b(?:driver'?s? )?licen[cs]e\b(?! plate)|\bid card\b|\bpassport\b/i;
const LETTER_WORDS = /\b(?:a|an|the|this|that|her|his|your|my) (?:(?:blank|handwritten|folded|old|sealed|yellowed|small|short) )*(?:letter|envelope|note)\b/i;
const HAND_WORDS = /\bhand-?writing\b|\bhandwritten\b|\bpencil\b|\bscrawl\w*\b/i;
const NOT_THERE = /\b(?:not|never|no|without|isn't|wasn't|aren't|weren't|don't|doesn't)\s+(?:\w+\s+){0,1}$/i;
const CHILD_WORDS = /\b(?:child|child's|children|kid|kid's|little|young|nine-year-old|crayons?|school)\b/i;
const BLANK_FACES = /\b(?:blank|empty|missing|no|without) (?:\w+ )?faces?\b|\bfaceless\b|\bno (?:eyes|mouths?)\b/i;

// narration rules, most specific first: the first one that names something in a sentence makes that sentence's card
const CARD_RULES = [
  ['time', (s) => { const m = timeIn(s); return m && TIME_CONTEXT.test(s) ? { match: m.match, index: m.index, time: m.time } : null; }],
  ['name', NAME_WORDS], ['drawing', DRAWING_WORDS], ['id_card', ID_WORDS], ['letter', LETTER_WORDS], ['handwriting', HAND_WORDS],
];
function ruleHit(rule, text) {
  const hit = typeof rule === 'function' ? rule(text) : (() => { const m = text.match(rule); return m ? { match: m[0], index: m.index } : null; })();
  return hit && !NOT_THERE.test(text.slice(0, hit.index)) && !/\b(?:not|never|isn't|wasn't)\b/i.test(hit.match) ? hit : null;
}
/** the kind of card a description (CSV) asks for */
export function cardKindFor(what, sceneText = '') {
  const w = String(what || '');
  if (timeIn(w) || /\bclocks?\b|\bwatch\b/i.test(w) || SCREEN_WORDS.test(w)) return SCREEN_WORDS.test(w) || (!/\bclocks?\b|\bwatch\b/i.test(w) && SCREEN_WORDS.test(sceneText)) ? 'phone_screen' : 'clock';
  if (DRAWING_WORDS.test(w) || /\bsketch(?:es)?\b/i.test(w)) return 'drawing';
  if (ID_WORDS.test(w) || /\b(?:id|badge)\b/i.test(w)) return 'id_card';
  if (/\bnames?\b|\bwrappers?\b/i.test(w)) return 'name';
  if (/\b(?:letter|envelope)\b/i.test(w)) return 'letter';
  if (HAND_WORDS.test(w) || /\bwritten\b|\bwriting\b|\bink\b/i.test(w)) return 'handwriting';
  return 'note';
}
const quoted = (s) => (String(s || '').match(/["“]([^"”]{1,60})["”]/) || [])[1] || '';
const inkStyle = (s) => /\bcrayons?\b/i.test(s) ? 'crayon' : /\bpencil\b/i.test(s) ? 'pencil' : /\bink\b|\bpen\b/i.test(s) ? 'ink' : /\bprint(?:ed|s)?\b/i.test(s) ? 'print' : 'ink';
/** the colour the words give the writing itself ("blue ink"), not any other thing in the sentence (a red wrapper) */
const inkColour = (s, style) => { const m = String(s).match(/\b\w+\s+(?:\w+\s+)?(?:ink|pencil|crayons?|pen|marker|letters?)\b/i), own = m && COLOURS.find(([c]) => c.test(m[0])); if (m && /\bblack\b/i.test(m[0])) return '#18181b'; return own ? own[1] : style === 'pencil' ? '#55565c' : style === 'crayon' ? '#b0302a' : '#1c2f6b'; };
const sentenceAt = (scene, t) => scene.sentences.find((s) => t >= s.start && t < s.end) || scene.sentences[0];
/** the moment a word is spoken: the matching word nearest to where it falls in the sentence, or that place itself (a voice with no such word) */
function spokenAt(sent, match, index) {
  const frac = sent.text.length ? index / sent.text.length : 0, want = sent.start + (sent.end - sent.start) * frac;
  const key = String(match).toLowerCase().replace(/[^a-z0-9' ]+/g, ' ').trim().split(/\s+/)[0];
  const hits = key ? (sent.words || []).filter((w) => w.word === key || w.word.startsWith(key)) : [];
  if (!hits.length) return want;
  return hits.reduce((b, w) => (Math.abs(w.start - want) < Math.abs(b.start - want) ? w : b)).start;
}
const isCardProp = (p) => /^cards?\b(?!_)\s*[:=]?/i.test(String(p));
export const isCardPropWord = isCardProp;
/** the card requests a beat's CSV cells make: `extra.card` (text, object or list) and `card: ...` props. [] = none; null = extra.card says none */
export function csvCardSpecs(beat) {
  const raw = beat.extra?.card;
  if (raw === false || raw === 'none') return null;
  const specs = (Array.isArray(raw) ? raw : raw != null ? [raw] : []).map((c) => (typeof c === 'string' ? { what: c } : c && typeof c === 'object' ? { ...c, what: c.what || c.card || c.prompt || '' } : null)).filter(Boolean);
  for (const p of beat.cardProps || []) specs.push({ what: String(p).replace(/^cards?\s*[:=]?\s*/i, '').trim() });
  return specs;
}

function makeCard(scene, fields, ctx) {
  const { kind, what = '', sentence = '', source } = fields, ctxText = `${what} ${sentence}`, style = fields.style || inkStyle(/\b(?:ink|pen|pencil|crayons?|printed)\b/i.test(ctxText) ? ctxText : scene.text);
  const wrapperWords = /\bwrappers?\b/i.test(ctxText) || (kind === 'name' && /\bwrappers?\b/i.test(scene.text));
  const card = { kind, what, source, scene: scene.id, beat: scene.beatId, word: fields.word || '', why: fields.why };
  if (kind === 'phone_screen' || kind === 'clock') card.time = fields.time || timeIn(what)?.time || timeIn(scene.text)?.time || '12:00';
  else {
    const said = quoted(sentence) || quoted(what), named = (String(sentence).match(/\bname(?: is|:)? ["“]?([A-Z][a-z]+)\b/) || [])[1];
    card.text = String(fields.text || said || named || (kind === 'note' ? what || sentence.split(/\s+/).slice(0, 8).join(' ') : kind === 'id_card' || kind === 'drawing' || kind === 'letter' ? '' : ctx.hero || 'your name'));
    card.style = style; card.color = inkColour(`${ctxText} ${scene.text}`, style); card.child = CHILD_WORDS.test(`${ctxText} ${scene.text}`) || style === 'crayon';
    if (kind === 'name') card.surface = wrapperWords ? 'wrapper' : 'paper';
    if (card.surface === 'wrapper') card.wrapColor = (COLOURS.find(([c]) => c.test(scene.text.replace(/\b\w+ ink\b/gi, ''))) || [null, '#d9b13b'])[1];
    if (kind === 'drawing') card.blankFaces = !/\bwith (?:smiling|happy|little) faces\b/i.test(ctxText) || BLANK_FACES.test(ctxText);
    if (kind === 'id_card' || kind === 'letter') card.blank = !card.text;
    if (kind === 'letter' && /\benvelopes?\b/i.test(ctxText)) card.envelope = true;
  }
  // a picture only for what code cannot draw well, or when the CSV names one; the code-made card stays underneath as the fallback
  const asset = String(fields.asset || ''), named = String(fields.prompt || '');
  card.picture = !!(asset || named || !CODE_MADE.has(kind));
  if (card.picture) { card.prompt = `${named || what || `${CARD_SEARCH[kind]}${card.blankFaces ? ' with blank faces, no eyes, no mouths' : ''}`}, extreme close-up photograph, dim light at night, shallow depth of field, film grain, no gore`; if (asset) card.asset = asset; }
  card.t0 = fields.t0; card.t1 = fields.t1;
  return card;
}
function timeCard(scene, at, hold) {
  const span = Math.max(1.5, Math.min(8, Number(hold) || 3.4));
  let t0 = at, t1 = at + span, limit = scene.t1 + 1.2;    // a word at the end of a beat: the card may run on over the next one's first words
  if (t1 > limit) { t1 = limit; if (t1 - t0 < 2.2) t0 = Math.max(scene.t0, t1 - 2.2); }
  return { t0: +t0.toFixed(3), t1: +t1.toFixed(3) };
}

/** a beat's cards: the CSV's own when it has any (they win), else the ones its narration implies. Times are film times; ids come from finishCards. */
export function horrorCards(scene, beat, ctx = {}) {
  const specs = csvCardSpecs(beat); if (specs === null) return [];
  const out = [];
  if (specs.length) {
    for (const sp of specs) {
      const kind = CARD_KINDS.includes(sp.kind) ? sp.kind : sp.time ? (SCREEN_WORDS.test(`${sp.what} ${scene.text}`) ? 'phone_screen' : 'clock') : sp.what ? cardKindFor(sp.what, scene.text) : (CARD_RULES.flatMap(([k, r]) => (scene.sentences.some((s) => ruleHit(r, s.text)) ? [k] : []))[0] || 'note');
      const finalKind = kind === 'time' ? (SCREEN_WORDS.test(scene.text) ? 'phone_screen' : 'clock') : kind;
      // when: on the word the CSV names, else where the narration names this kind of thing, else a third of the way through the beat
      let at = null, sent = scene.sentences[0];
      if (sp.at) for (const s of scene.sentences) { const i = s.text.toLowerCase().indexOf(String(sp.at).toLowerCase()); if (i >= 0) { at = spokenAt(s, sp.at, i); sent = s; break; } }
      if (at == null) { const rule = CARD_RULES.find(([k]) => k === finalKind || (k === 'time' && (finalKind === 'clock' || finalKind === 'phone_screen')))?.[1]; if (rule) for (const s of scene.sentences) { const h = ruleHit(rule, s.text); if (h) { at = spokenAt(s, h.match, h.index); sent = s; break; } } }
      if (at == null) { at = scene.t0 + (scene.t1 - scene.t0) * 0.34; sent = sentenceAt(scene, at); }
      out.push(makeCard(scene, { ...sp, kind: finalKind, sentence: sent.text, source: 'csv', why: 'set in the CSV', ...timeCard(scene, at, sp.hold) }, ctx));
    }
    return out;
  }
  // "The wrapper is printed in cheap black letters. It's your name.": the name may come a sentence after the writing it is on
  const writingHere = /\b(?:wrappers?|printed|written|scrawled|writing|letters)\b/i.test(scene.text);
  for (const s of scene.sentences) for (const [rule, test] of CARD_RULES) {
    const h = ruleHit(test, s.text) || (rule === 'name' && writingHere && !/\b(?:not|never|isn't|wasn't)\b/i.test(s.text) ? ruleHit(/\byour (?:full )?name\b/i, s.text) : null); if (!h) continue;
    const kind = rule === 'time' ? (SCREEN_WORDS.test(s.text) || SCREEN_WORDS.test(scene.text) ? 'phone_screen' : 'clock') : rule;
    out.push(makeCard(scene, { kind, sentence: s.text, time: h.time, word: h.match, source: 'narration', why: `"${h.match}" in the narration`, ...timeCard(scene, spokenAt(s, h.match, h.index), null) }, ctx));
    break;
  }
  return out;
}

/** the film's cards in order, spaced, numbered c1, c2, ... Two never overlap; a card is never left under the last-second fade. */
export function finishCards(cards, duration) {
  const kept = [];
  for (const c of [...cards].sort((a, b) => a.t0 - b.t0)) {
    const last = kept[kept.length - 1];
    if (c.source === 'narration' && last && c.t0 < last.t0 + CARD_GAP) continue;
    if (c.source === 'narration' && kept.some((k) => k.kind === c.kind && k.text === c.text && k.time === c.time && c.t0 - k.t0 < 30)) continue;
    if (last && c.t0 < last.t1 + 0.3) {
      if (c.t0 - 0.3 - last.t0 >= 1.6) last.t1 = +(c.t0 - 0.3).toFixed(3);
      else { c.t0 = +(last.t1 + 0.3).toFixed(3); c.t1 = +Math.max(c.t1, c.t0 + 1.6).toFixed(3); }
    }
    c.t1 = +Math.min(c.t1, duration - 1.2).toFixed(3);
    if (c.t1 - c.t0 >= 1) kept.push(c);
  }
  kept.forEach((c, i) => { c.id = `c${i + 1}`; });
  return kept;
}

/** the push into the held thing before the dissolve: outdoors a hand (given to the hero if no one holds it yet), indoors the room's phone or the hands */
export function cardPush(scene, card) {
  const item = CARD_ITEM[card.kind] === 'letter' && card.surface === 'wrapper' ? 'gift_small' : CARD_ITEM[card.kind];
  if (!item) return;
  if (scene.env === 'interior' && item === 'phone') { card.focus = 'phone'; if (!(scene.props || []).includes('phone')) scene.props = [...(scene.props || []), 'phone']; return; }
  const roles = new Set(scene.cast.map((c) => c.role)), at = (h) => h.t0 <= card.t0 + 0.01 && h.t1 >= card.t0 - 0.01;
  const holds = scene.holds || [], own = holds.find((h) => h.item === item && at(h));
  const taken = holds.find((h) => at(h) && h.hand === 'R' && (h.role === 'hero' || h.role === 'child'));
  const who = roles.has('hero') ? 'hero' : roles.has('child') ? 'child' : null;
  if (!own && !taken && who) (scene.holds = holds).push({ role: who, item, color: card.wrapColor || null, hand: 'R', t0: +Math.max(scene.t0, card.t0 - CARD_PUSH - 0.2).toFixed(3), t1: +Math.min(scene.t1 - 0.1, card.t1).toFixed(3), why: `what the ${card.kind.replace('_', ' ')} card shows` });
  const h = own || taken || (who ? { role: who, hand: 'R' } : null);
  if (h) { if (scene.env === 'interior') card.focus = 'hands'; else card.hand = { role: h.role, hand: h.hand }; }
}

/** which card covers the frame at time t: {card, a (0..1 dissolve), u (0..1 through it)}; null = none. Pure, so any frame renders alone. */
export function cardAt(cards, t) {
  const c = (cards || []).find((x) => t >= x.t0 && t < x.t1); if (!c) return null;
  const ramp = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  return { card: c, a: Math.min(ramp((t - c.t0) / 0.7), ramp((c.t1 - t) / 0.5)), u: (t - c.t0) / (c.t1 - c.t0) };
}

const IMAGE_FILE = /\.(png|jpe?g|webp)$/i;
/** puts the pictures the Visuals tab holds on the plan's cards ({card id: file}, then the CSV's own file). A card with none stays code-made. Returns notes. */
export function attachCardPictures(cards, files, { exists, resolve = (p) => p } = {}) {
  const notes = [];
  for (const c of cards || []) {
    const wanted = (files && files[c.id]) || (c.asset ? resolve(c.asset) : '');
    if (wanted && IMAGE_FILE.test(wanted) && exists(wanted)) { c.imageFile = wanted; c.image = `/card/${c.id}`; }
    else if (c.picture && files) notes.push(`card ${c.id} (${c.kind.replace('_', ' ')}): no picture in the Visuals tab, using the code-made card`);
  }
  return notes;
}
