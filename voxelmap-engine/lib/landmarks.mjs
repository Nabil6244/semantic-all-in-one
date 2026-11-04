// Real places, as recognisable block models (built in lib/props.mjs). A ground beat gets one from its CSV extra
// ({"landmark": "colosseum"}, or "none"), else from its place name and narration. Pure, no imports.

export const LANDMARKS = ['colosseum', 'temple', 'pantheon', 'palace', 'domed', 'mosque', 'cathedral', 'castle', 'wall', 'arch', 'pyramid', 'column'];

// first match wins, so the specific names come before the generic words
const HINTS = [
  [/colosse|amphitheat|gladiator/i, 'colosseum'],
  [/pantheon/i, 'pantheon'],
  [/hagia sophia|aya sofya/i, 'domed'],
  [/blue mosque|\bmosque\b|minaret/i, 'mosque'],
  [/winter palace|versailles|hall of mirrors|kremlin|hofburg|sch[oö]nbrunn|buckingham|\bpalace\b|palatine/i, 'palace'],
  [/notre[- ]dame|cathedral|basilica|abbey|st\.? peter/i, 'cathedral'],
  [/hadrian'?s wall|antonine wall|great wall|\bthe wall\b/i, 'wall'],
  [/triumphal arch|arc de triomphe|arch of (titus|constantine|septimius)/i, 'arch'],
  [/pyramid|giza/i, 'pyramid'],
  [/trajan'?s column|obelisk|nelson'?s column|\bcolumn\b/i, 'column'],
  [/senate house|curia|\bforum\b|capitol|temple of|parthenon|acropolis|\btemple\b/i, 'temple'],
  [/\bcastle\b|citadel|tower of london|krak/i, 'castle'],
];

/** The landmark a beat's place and narration name, or null. */
export function landmarkFromText(text) {
  for (const [re, name] of HINTS) if (re.test(text || '')) return name;
  return null;
}

/** A beat's landmark: the CSV's (a known name, or "none" for no landmark), else the one its words name. Ground beats only. */
export function landmarkFor(beat, extra = {}) {
  if (beat.rung !== 'ground') return null;
  const asked = extra.landmark;
  if (asked === 'none' || asked === false) return null;
  if (typeof asked === 'string' && LANDMARKS.includes(asked)) return asked;
  // read from the words only where a building can be the scene: never a battlefield, beach, jungle, trail or a room
  if (/^(battle|beach_landing|jungle|trail|delta|airfield|lz|hall|office)$/.test(beat.site || '')) return null;
  return landmarkFromText(`${beat.place || ''} ${(beat.sentences || []).join(' ')}`);
}
