// Historical periods and sides. The era (from the story's dates) decides which vehicles, weapons, helmets and buildings may
// appear: a 1944 story never gets a helicopter or a jet unless a beat asks for one by name (and then a warning says so).
// Faction looks are colour/kit families, not insignia: no real flags, badges or national symbols are drawn.

export const ERAS = [
  { id: 'ancient', from: -3000, to: 499, label: 'Antiquity', weapons: ['spear', 'sword', 'bow'], helmets: ['crest', 'cap_soft'], vehicles: ['cart', 'galley', 'horse'], buildings: 'ancient' },
  { id: 'medieval', from: 500, to: 1449, label: 'Middle Ages', weapons: ['sword', 'spear', 'bow'], helmets: ['kettle', 'hood'], vehicles: ['cart', 'galley', 'horse'], buildings: 'medieval' },
  { id: 'early_modern', from: 1450, to: 1789, label: 'Early modern', weapons: ['musket', 'sword'], helmets: ['tricorn', 'cap_soft'], vehicles: ['cart', 'sailing_ship', 'horse', 'cannon'], buildings: 'old_town' },
  { id: 'nineteenth', from: 1790, to: 1913, label: '19th century', weapons: ['musket', 'rifle_old', 'sword'], helmets: ['shako', 'kepi', 'cap_soft'], vehicles: ['cart', 'sailing_ship', 'steam_ship', 'horse', 'cannon', 'train'], buildings: 'old_town' },
  { id: 'ww1', from: 1914, to: 1918, label: 'First World War', weapons: ['rifle_bolt', 'machine_gun'], helmets: ['brodie', 'stahl', 'adrian', 'cap_soft'], vehicles: ['truck_old', 'tank_ww1', 'biplane', 'artillery', 'steam_ship', 'horse', 'train'], buildings: 'old_town' },
  { id: 'interwar', from: 1919, to: 1938, label: 'Interwar', weapons: ['rifle_bolt'], helmets: ['cap_soft', 'peaked'], vehicles: ['car_old', 'truck', 'biplane', 'steam_ship', 'train'], buildings: 'old_town' },
  { id: 'ww2', from: 1939, to: 1945, label: 'Second World War', weapons: ['rifle_bolt', 'rifle_semi', 'smg', 'machine_gun'], helmets: ['m1', 'brodie', 'stahl', 'ssh', 'kabuto', 'peaked', 'beret', 'cap_soft', 'pilot_cap'],
    vehicles: ['tank', 'jeep', 'truck', 'halftrack', 'artillery', 'transport_plane', 'fighter_prop', 'bomber', 'landing_craft', 'ship', 'battleship', 'submarine', 'car_old', 'radar', 'motorbike', 'train'], buildings: 'old_town' },
  { id: 'cold_war', from: 1946, to: 1990, label: 'Cold War', weapons: ['rifle_assault', 'rifle_semi', 'machine_gun'], helmets: ['m1', 'ssh', 'pith', 'boonie', 'beret', 'peaked', 'cap_soft', 'pilot_helmet', 'conical'],
    vehicles: ['tank', 'apc', 'jeep', 'truck', 'artillery', 'helicopter', 'jet', 'transport_plane', 'bomber', 'landing_craft', 'ship', 'submarine', 'car', 'radar', 'patrol_boat', 'sampan', 'bicycle', 'motorbike'], buildings: 'modern_old' },
  { id: 'modern', from: 1991, to: 2100, label: 'Modern', weapons: ['rifle_assault', 'machine_gun'], helmets: ['modern', 'beret', 'cap_soft', 'pilot_helmet'],
    vehicles: ['tank', 'apc', 'humvee', 'truck', 'artillery', 'helicopter', 'jet', 'transport_plane', 'ship', 'submarine', 'car', 'radar', 'patrol_boat', 'drone', 'motorbike'], buildings: 'modern' },
];

export function eraOf(year) {
  if (!Number.isFinite(year)) return ERAS.find((e) => e.id === 'ww2');
  return ERAS.find((e) => year >= e.from && year <= e.to) || ERAS[ERAS.length - 1];
}

/** Vehicles that stand in for one another when the era forbids the asked one (a 1944 "helicopter" becomes a transport plane). */
export const ERA_SUBSTITUTE = { helicopter: 'transport_plane', jet: 'fighter_prop', apc: 'halftrack', humvee: 'jeep', drone: 'fighter_prop', car: 'car_old', tank_ww1: 'tank', biplane: 'fighter_prop', patrol_boat: 'landing_craft', sampan: 'landing_craft' };

export function vehicleForEra(kind, era) {
  if (era.vehicles.includes(kind)) return { kind, substituted: false };
  const sub = ERA_SUBSTITUTE[kind];
  if (sub && era.vehicles.includes(sub)) return { kind: sub, substituted: true };
  return { kind, substituted: false, anachronism: true };
}

// Faction kit families: uniform colours, helmet shape, weapon. Matched from words in the narration ("American", "German" ...).
export const FACTIONS = {
  us: { words: ['american', 'americans', 'u.s.', 'us army', 'united states', 'yanks', 'gi', 'marines'], label: 'United States', shirt: '#6b6a45', pants: '#5d5b3c', helmet: { ww2: 'm1', cold_war: 'm1', modern: 'modern' }, gear: '#4d4a33', accent: '#7f7c55' },
  uk: { words: ['british', 'britain', 'english', 'canadian', 'canadians', 'commonwealth'], label: 'British & Commonwealth', shirt: '#7b6a48', pants: '#6e5f40', helmet: { ww1: 'brodie', ww2: 'brodie' }, gear: '#5a4e36', accent: '#8a7a54' },
  allied: { words: ['allied', 'allies'], label: 'Allied', shirt: '#6f6a47', pants: '#605c3d', helmet: { ww2: 'm1' }, gear: '#4f4b35', accent: '#7e7a55' },
  germany: { words: ['german', 'germans', 'wehrmacht', 'nazi'], label: 'German', shirt: '#5e655a', pants: '#545a50', helmet: { ww1: 'stahl', ww2: 'stahl' }, gear: '#3f423b', accent: '#6f766a' },
  soviet: { words: ['soviet', 'soviets', 'red army', 'russian', 'russians'], label: 'Soviet', shirt: '#7c7650', pants: '#5f5b3e', helmet: { ww2: 'ssh', cold_war: 'ssh' }, gear: '#4a4733', accent: '#8c8660' },
  japan: { words: ['japanese', 'imperial japanese'], label: 'Japanese', shirt: '#857b4b', pants: '#76703f', helmet: { ww2: 'kabuto' }, gear: '#5b5532', accent: '#958b5a' },
  france: { words: ['french', 'france'], label: 'French', shirt: '#5b6a7a', pants: '#4f5c6a', helmet: { ww1: 'adrian', ww2: 'adrian' }, gear: '#3d4652', accent: '#6c7b8c' },
  north_vietnam: { words: ['north vietnamese', 'viet minh', 'viet cong', 'nva'], label: 'North Vietnamese', shirt: '#5f6b45', pants: '#56613d', helmet: { cold_war: 'pith' }, gear: '#444d31', accent: '#738056' },
  south_vietnam: { words: ['south vietnamese', 'arvn'], label: 'South Vietnamese', shirt: '#55663f', pants: '#4b5a37', helmet: { cold_war: 'm1' }, gear: '#3d4a2d', accent: '#6a7d50' },
  india: { words: ['indian', 'indians', 'india'], label: 'Indian', shirt: '#6f7448', pants: '#636840', helmet: { cold_war: 'm1', modern: 'modern' }, gear: '#4b4f31', accent: '#82875a' },
  pakistan: { words: ['pakistani', 'pakistanis', 'pakistan'], label: 'Pakistani', shirt: '#59693f', pants: '#4f5d38', helmet: { cold_war: 'm1', modern: 'modern' }, gear: '#3c4729', accent: '#6c7d4d' },
  roman: { words: ['roman', 'romans', 'rome', 'legion', 'legions', 'legionaries'], label: 'Roman', shirt: '#9a3b2e', pants: '#8a6a4a', helmet: { ancient: 'crest' }, gear: '#b08a3c', accent: '#c9a24a' },
  carthage: { words: ['carthaginian', 'carthaginians', 'carthage', 'hannibal'], label: 'Carthaginian', shirt: '#5e3f7a', pants: '#7a6a4a', helmet: { ancient: 'crest' }, gear: '#8a7a3c', accent: '#b49ad0' },
  civilian: { words: [], label: 'Civilians', shirt: null, pants: null, helmet: {}, gear: '#6b5a44', accent: '#8b7a64' },
};

/** Factions named in a text, in order of first mention. */
export function factionsIn(text) {
  const t = ` ${String(text).toLowerCase()} `;
  const hits = [];
  for (const [id, f] of Object.entries(FACTIONS)) {
    let first = Infinity;
    for (const w of f.words) { const k = t.search(new RegExp(`[^a-z]${w.replace(/[.]/g, '\\.')}[^a-z]`)); if (k >= 0) first = Math.min(first, k); }
    if (first < Infinity) hits.push({ id, first });
  }
  return hits.sort((a, b) => a.first - b.first).map((h) => h.id);
}
