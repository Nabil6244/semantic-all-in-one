// Indoor sets. A scene's room comes from the CSV location, then its props, then the narration: a bathroom story gets a bathroom with
// a mirror, not the war room. Each room says where its people stand (the mark), what the camera may look at (focus points, one per
// prop the story can name) and how it opens wide. Shared by the renderer and Node, so tests check what the frames show.

// prop words -> focus key; the first match in a phrase wins, so "glass of water" is a cup and "glass" alone is the mirror
const PROP_WORDS = [
  [/\bglass of water\b|\bcoffee\b|\bmug\b|\bcups?\b/g, 'cup'], [/\bplates?\b|\beggs\b|\bbreakfast\b/g, 'plate'],
  [/\bmirrors?\b|\breflections?\b|\bhandprints?\b|\bglass\b/g, 'mirror'], [/\bsinks?\b|\btaps?\b|\bfaucets?\b|\bsoap\b/g, 'sink'],
  [/\btowels?\b|\bhooks?\b/g, 'towel'], [/\bbathtub\b|\bbath\b|\btub\b/g, 'tub'], [/\btoilet\b/g, 'toilet'],
  [/\bdoors?\b/g, 'door'], [/\blight switch\b|\bswitch\b/g, 'switch'], [/\bwindows?\b/g, 'window'],
  [/\btiles?\b|\bfloorboards?\b|\bfloor\b/g, 'floor'], [/\bbed\b|\bpillow\b/g, 'bed'], [/\blamps?\b/g, 'lamp'],
  [/\btelevisions?\b|\btv\b/g, 'tv'], [/\bphones?\b/g, 'phone'], [/\btables?\b/g, 'table'], [/\bcabinets?\b|\bcupboards?\b/g, 'cabinet'],
  [/\bhands?\b|\brings?\b|\bfingers?\b/g, 'hands'],
];
export const SMALL_FOCUS = new Set(['cup', 'plate', 'phone', 'switch', 'hands']);

/** Prop keys named in a text, in spoken order, without repeats. */
export function propsIn(text) {
  const s = String(text || '').toLowerCase(), found = [], taken = [];
  for (const [re, key] of PROP_WORDS) for (const m of s.matchAll(re)) {
    const a = m.index, b = a + m[0].length;
    if (taken.some(([x, y]) => a < y && b > x)) continue;
    taken.push([a, b]); found.push([a, key]);
  }
  return [...new Set(found.sort((x, y) => x[0] - y[0]).map((f) => f[1]))];
}

const ROOM_WORDS = [[/\bbath ?rooms?\b|\bwashrooms?\b|\brestrooms?\b/, 'bathroom'], [/\bkitchens?\b/, 'kitchen'], [/\bhallways?\b|\bcorridors?\b|\bentryway\b/, 'hallway'],
  [/\bbedrooms?\b/, 'bedroom'], [/\bliving rooms?\b|\blounge\b|\bsitting room\b|\bparlou?r\b/, 'living'], [/\bheadquarters\b|\bwar room\b|\bbunker\b|\bcommand post\b|\bmap room\b|\bpalace\b/, 'war']];
const PROP_ROOMS = [[/\bbathtub\b|\btoilet\b|\btowel\b|\bfaucet\b|\bsoap\b/, 'bathroom'], [/\bcoffee\b|\bkitchen table\b|\bplate\b|\bkitchen cabinet\b/, 'kitchen'], [/\bbed\b|\bpillow\b/, 'bedroom'], [/\btelevision\b|\bsofa\b|\bcouch\b/, 'living']];
const scan = (text, list) => { const s = String(text || '').toLowerCase(); for (const [re, k] of list) if (re.test(s)) return k; return null; };

/** "Bathroom" is a room, not a place missing from the gazetteer. */
export const isRoomName = (location) => !!scan(location, ROOM_WORDS);

/** Which room an interior scene plays in. Meetings stay in the war room; a civilian scene that names no room gets the last one or a living room. */
export function roomKindFor({ location = '', props = [], text = '', event = '', civilian = false, last = null }) {
  const propText = [].concat(props).join('; ');
  return scan(location, ROOM_WORDS)
    || (event === 'political_meeting' || event === 'peace_agreement' ? 'war' : null)
    || scan(propText, ROOM_WORDS) || scan(propText, PROP_ROOMS) || scan(text, ROOM_WORDS)
    || last || (civilian ? 'living' : 'war');
}

const WAR_ITEMS = [{ kind: 'table_map', x: 0, z: 0, y: 0, rot: 0 }, { kind: 'wall_map', x: 0, z: -14.6, y: 0, rot: 0 }, { kind: 'lamp_hang', x: -8, z: 0, y: 0 }, { kind: 'lamp_hang', x: 8, z: 0, y: 0 },
  { kind: 'bookcase', x: 20, z: -13, y: 0, rot: 0 }, { kind: 'clock', x: -14, z: -14.6, y: 0 }, { kind: 'chair', x: -10, z: 6, y: 0, rot: Math.PI }, { kind: 'chair', x: 10, z: 6, y: 0, rot: Math.PI }, { kind: 'chair', x: 0, z: -7, y: 0, rot: 0 }, { kind: 'phone', x: 6, z: -1, y: 3.1 }];

const R = Math.PI / 2;
// fixed: always in the room. optional: added when the story names it. spots: where each focus key is, [x, height, z].
const ROOMS = {
  bathroom: { w: 30, d: 22, h: 14, wall: '#c3d0cc', tile: true, floor: 'tile', winW: 6, mark: [0, -4.5], main: 'mirror',
    fixed: [['mirror', 0, -10.65], ['vanity', 0, -9.1], ['towel_rail', -10, -10.6], ['bathtub', -10.5, 3, 0, 0], ['toilet', 10.5, -7.5, 0, 0], ['door', 14.65, 3.5, 0, -R], ['light_switch', 14.65, -1.5, 0, -R], ['lamp_hang', 0, 0]],
    spots: { mirror: [0, 6.8, -10.5], sink: [0, 3.4, -9], towel: [-10, 6, -10.4], tub: [-10.5, 2.8, 3], toilet: [10.5, 2.6, -7.5], door: [14.4, 5, 3.5], switch: [14.4, 5.2, -1.5], window: [-14.5, 7, 0], floor: [2, 0.2, 1], phone: [4, 3.5, -9], cup: [-3.2, 3.6, -9] } },
  kitchen: { w: 36, d: 26, h: 14, wall: '#d6c7a4', floor: 'planks', winW: 8, mark: [-7, 3], main: 'table',
    fixed: [['counter', 0, -11], ['wall_cabinet', 0, -12.4], ['table_plain', 4, 4], ['chair', 4, 9, 0, Math.PI], ['chair', 4, -1, 0, 0], ['door', 17.65, 7, 0, -R], ['lamp_hang', 4, 4]],
    optional: { mirror: ['mirror', -11, -12.65], cup: ['coffee_pot', 2, 4, 3.5], plate: ['plate', 6, 4, 3.5] },
    spots: { table: [4, 3.6, 4], sink: [0, 3.5, -11], cabinet: [0, 8.8, -12], door: [17.4, 5, 7], window: [-17.5, 7, 0], mirror: [-11, 6.8, -12.5], floor: [-2, 0.2, 6], phone: [1.5, 3.7, 3], cup: [2, 3.9, 4], plate: [6, 3.7, 4] } },
  hallway: { w: 40, d: 14, h: 14, wall: '#c9bda0', floor: 'planks', winW: 5, mark: [0.5, 1], main: 'mirror',
    fixed: [['mirror', 0, -6.65], ['door', 19.65, 0, 0, -R], ['door', -11, -6.65, 0, 0], ['side_table', 9, -5.3], ['lamp_hang', 2, 0], ['lamp_hang', -11, 0]],
    spots: { mirror: [0, 6.8, -6.5], door: [19.4, 5, 0], floor: [7, 0.2, 2], window: [-19.5, 7, 0], table: [9, 3.2, -5.3], phone: [9, 3.2, -5.3], cup: [9, 3.2, -5.3], lamp: [2, 10.5, 0] } },
  bedroom: { w: 34, d: 26, h: 14, wall: '#b9bcc9', floor: 'planks', winW: 8, mark: [6, 2], main: 'bed',
    fixed: [['bed', -7, -6], ['side_table', -14, -10.5], ['table_lamp', -14, -10.5, 3], ['door', 16.65, 6, 0, -R], ['lamp_hang', 2, 2]],
    optional: { mirror: ['mirror', 8, -12.65], tv: ['tv', 8, -12.3] },
    spots: { bed: [-7, 3, -6], lamp: [-14, 5, -10.5], door: [16.4, 5, 6], window: [-16.5, 7, 0], mirror: [8, 6.8, -12.5], tv: [8, 6, -12], floor: [2, 0.2, 7], phone: [-14, 3.3, -10.5], cup: [-13, 3.3, -10.5] } },
  living: { w: 36, d: 26, h: 14, wall: '#cdbf9f', floor: 'planks', winW: 8, mark: [0, 4], main: 'tv',
    fixed: [['tv', 0, -12.3], ['sofa', 0, 7], ['side_table', 11, 7], ['table_lamp', 11, 7, 3], ['door', 17.65, -6, 0, -R], ['lamp_hang', 0, 0]],
    optional: { mirror: ['mirror', -11, -12.65] },
    spots: { tv: [0, 6, -12], lamp: [11, 5, 7], door: [17.4, 5, -6], window: [-17.5, 7, 0], mirror: [-11, 6.8, -12.5], floor: [-3, 0.2, -3], table: [11, 3.2, 7], phone: [11, 3.3, 7], cup: [10, 3.3, 7] } },
};

const inside = (I, m = 1.5) => ({ inside: true, x0: -I.w / 2 + m, x1: I.w / 2 - m, z0: -I.d / 2 + m, z1: I.d / 2 - m, y0: 1, y1: I.h - 1 });

/** The set for a room kind: {interior, items, collider, anchors, focus, main, wide}. wanted = prop keys the scene names. */
export function buildRoom(kind, wanted = [], opts = {}) {
  const D = ROOMS[kind];
  if (!D) {
    const interior = { w: 44, d: 30, h: 14, wall: opts.variant === 'bunker' ? '#7c7a72' : '#c9bfa8', floor: 'planks', winW: 12, beams: true, rainOutside: opts.rainOutside };
    return { kind: 'war', interior, items: WAR_ITEMS.map((p) => ({ ...p })), collider: inside(interior), main: 'table',
      anchors: { center: [0, 0], table: [0, 0], head: [0, -6], window: [-21, 0], door: [21, 8], mark: [0, 9.5] },
      focus: { table: [0, 3.6, 0], phone: [6, 3.4, -1], door: [21, 5, 8], window: [-21, 7, 0], floor: [8, 0.2, 9] },
      wide: { from: [-17, 10.5, 11], to: [-12, 10.5, 9], target: [2, 2.5, -3] } };
  }
  const interior = { w: D.w, d: D.d, h: D.h, wall: D.wall, tile: !!D.tile, floor: D.floor, winW: D.winW, beams: false, rainOutside: opts.rainOutside };
  const item = ([kind2, x, z, y = 0, rot = 0]) => ({ kind: kind2, x, z, y, rot });
  const items = D.fixed.map(item);
  for (const k of wanted) if (D.optional && D.optional[k]) items.push(item(D.optional[k]));
  if (wanted.includes('phone')) { const p = D.spots.phone; if (p) items.push({ kind: 'phone', x: p[0], z: p[2], y: p[1] - 0.1, rot: 0.4 }); }
  if (wanted.includes('cup') && !(D.optional && D.optional.cup)) { const p = D.spots.cup; if (p) items.push({ kind: 'cup', x: p[0], z: p[2], y: p[1] - 0.1, rot: 0 }); }
  const focus = {};
  for (const [k, p] of Object.entries(D.spots)) { const opt = D.optional && D.optional[k], small = k === 'phone' || k === 'cup'; if ((!opt && !small) || wanted.includes(k)) focus[k] = p; }
  const [mx, mz] = D.mark, cx = -D.w / 2 + 3, cz = D.d / 2 - 3;
  return { kind, interior, items, collider: inside(interior), main: D.main, focus,
    anchors: { center: [mx, mz], mark: [mx, mz], door: [D.w / 2 - 2, D.d / 4] },
    wide: { from: [cx, D.h - 3, cz], to: [cx + 2.5, D.h - 3.6, cz - 1.2], target: [mx * 0.5, 3.5, mz * 0.5 - D.d * 0.12] } };
}
