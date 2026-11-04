// Blocky characters defined by data. A character is a role + faction + era + seed; the generator turns that into a full look
// (skin, face decal, clothing, headwear, gear, weapon). Same name -> same look, everywhere in the film (recurring identity).
// Proportions (in studs): legs 2 tall, torso 2x2x1, arms 1x2x1, head 1.25 wide; 5 studs to the top of the head.

import { hash, makeRng } from './rng.mjs';
import { FACTIONS } from './eras.mjs';

export const BODY = { legH: 2, legW: 1, torsoW: 2, torsoH: 2, torsoD: 1, armW: 1, armH: 2, headW: 1.25, headH: 1.15, height: 5.15 };

export const ROLES = ['soldier', 'officer', 'commander', 'leader', 'politician', 'civilian', 'farmer', 'worker', 'police', 'pilot', 'sailor', 'medic',
  'journalist', 'crowd', 'paratrooper', 'tank_crew', 'child', 'forecaster', 'guard'];

const SKIN = ['#f1c9a5', '#e8b48f', '#d9a074', '#c68a5e', '#a86f45', '#8a5734', '#6b4127', '#f5d3b5', '#e0a982', '#b77b52'];
const HAIR = ['#2b2018', '#3d2a1c', '#5a3b22', '#7a5230', '#a87b45', '#c9a86a', '#1c1c1c', '#6d6d6d', '#b8b2a6'];
const CIV_SHIRT = ['#b04a3c', '#3d6aa8', '#e2d6b8', '#6b8f4e', '#8a5a9e', '#d39a3a', '#4d7f86', '#c7c2b4', '#7d3f3f', '#2f4f6f'];
const CIV_PANTS = ['#3a3f4a', '#4a3b2c', '#2d3a52', '#6a6255', '#303030', '#5a4a3a'];
const SUIT = ['#2c2f36', '#3b3a3f', '#2a3344', '#4a4136'];

export const FACES = {
  eyes: ['dots', 'ovals', 'narrow', 'wide', 'tired'],
  brows: ['none', 'flat', 'stern', 'worried', 'raised'],
  mouth: ['smile', 'flat', 'frown', 'open', 'grin', 'determined', 'smirk'],
  hair: ['none', 'short', 'side', 'bald_sides', 'long', 'bun'],
  facial: ['none', 'none', 'none', 'mustache', 'beard', 'stubble'],
};

// role -> kit. `helmet` true = the faction's era helmet; strings are fixed headwear; weapons only for armed roles.
const KITS = {
  soldier: { torso: 'uniform', hat: 'helmet', gear: ['webbing', 'backpack'], weapon: true, mouth: ['determined', 'flat', 'frown', 'open'] },
  paratrooper: { torso: 'uniform', hat: 'helmet', gear: ['webbing', 'chute_pack', 'backpack'], weapon: true, mouth: ['determined', 'flat', 'open'] },
  guard: { torso: 'uniform', hat: 'helmet', gear: ['webbing'], weapon: true, mouth: ['flat', 'stern'] },
  tank_crew: { torso: 'coveralls', hat: 'cap_soft', gear: [], weapon: false, mouth: ['flat', 'determined'] },
  officer: { torso: 'uniform_officer', hat: 'peaked', gear: ['holster', 'binoculars'], weapon: false, mouth: ['flat', 'determined', 'smirk'] },
  commander: { torso: 'uniform_officer', hat: 'peaked', gear: ['holster'], weapon: false, mouth: ['smile', 'flat', 'determined'] },
  leader: { torso: 'suit', hat: null, gear: [], weapon: false, mouth: ['flat', 'smile', 'determined'] },
  politician: { torso: 'suit', hat: null, gear: [], weapon: false, mouth: ['smile', 'flat', 'smirk'] },
  forecaster: { torso: 'uniform_officer', hat: null, gear: ['papers'], weapon: false, mouth: ['flat', 'worried'] },
  civilian: { torso: 'shirt', hat: [null, null, 'flat_cap', 'beret', 'headscarf'], gear: [], weapon: false, mouth: ['smile', 'flat', 'open', 'grin'] },
  crowd: { torso: 'shirt', hat: [null, null, 'flat_cap', 'beret'], gear: [], weapon: false, mouth: ['smile', 'grin', 'open'] },
  child: { torso: 'shirt', hat: [null, 'flat_cap'], gear: [], weapon: false, mouth: ['smile', 'grin', 'open'] },
  farmer: { torso: 'overalls', hat: ['straw', 'flat_cap'], gear: [], weapon: false, mouth: ['flat', 'smile'] },
  worker: { torso: 'overalls', hat: ['flat_cap', 'hardhat'], gear: [], weapon: false, mouth: ['flat', 'determined'] },
  police: { torso: 'police', hat: 'police_cap', gear: ['holster'], weapon: false, mouth: ['flat', 'stern'] },
  pilot: { torso: 'flight_jacket', hat: 'pilot_cap', gear: [], weapon: false, mouth: ['smile', 'determined'] },
  sailor: { torso: 'sailor', hat: 'sailor_cap', gear: [], weapon: false, mouth: ['flat', 'smile'] },
  medic: { torso: 'uniform', hat: 'helmet_medic', gear: ['medbag'], weapon: false, mouth: ['worried', 'determined'] },
  journalist: { torso: 'jacket', hat: ['fedora', null], gear: ['camera', 'notepad'], weapon: false, mouth: ['open', 'flat'] },
};

const WEAPON_BY_ERA = { ancient: 'spear', medieval: 'sword', early_modern: 'musket', nineteenth: 'musket', ww1: 'rifle_bolt', interwar: 'rifle_bolt', ww2: 'rifle_semi', cold_war: 'rifle_assault', modern: 'rifle_assault' };
const ERA_HELMET = { ww1: 'brodie', ww2: 'm1', cold_war: 'm1', modern: 'modern' };

const pickOr = (rng, v) => (Array.isArray(v) ? rng.pick(v) : v);

/** Full character look. opts: {role, faction, era (id), name, seed, mood} */
export function makeCharacter({ role = 'soldier', faction = 'civilian', era = 'ww2', name = null, seed = 0, mood = null } = {}) {
  const kit = KITS[role] || KITS.civilian;
  const rng = makeRng(name ? `person:${name}` : `${role}:${faction}:${seed}`);
  const f = FACTIONS[faction] || FACTIONS.civilian;
  const civ = !['uniform', 'uniform_officer', 'coveralls', 'flight_jacket', 'sailor', 'police'].includes(kit.torso) || faction === 'civilian';
  const skin = rng.pick(SKIN);
  const hairColor = rng.pick(HAIR);
  const shade = (hex, k) => { const n = parseInt(hex.slice(1), 16); const c = (s) => Math.max(0, Math.min(255, Math.round(((n >> s) & 255) * k))); return `#${((c(16) << 16) | (c(8) << 8) | c(0)).toString(16).padStart(6, '0')}`; };
  // small per-person colour drift so a squad in one uniform is not a row of clones
  const drift = 0.94 + rng() * 0.12;
  let shirt, pants;
  if (kit.torso === 'suit') { shirt = rng.pick(SUIT); pants = shirt; }
  else if (kit.torso === 'sailor') { shirt = '#e9ecef'; pants = '#20283a'; }
  else if (kit.torso === 'police') { shirt = '#25324a'; pants = '#1f2738'; }
  else if (kit.torso === 'flight_jacket') { shirt = '#6a4a2e'; pants = f.pants ? shade(f.pants, drift) : '#4a4a40'; }
  else if (civ && !f.shirt) { shirt = rng.pick(CIV_SHIRT); pants = rng.pick(CIV_PANTS); }
  else if (kit.torso === 'overalls') { shirt = rng.pick(['#c9c2ae', '#9fb3c8', '#b5a17f']); pants = rng.pick(['#3f5a7a', '#5a4a33']); }
  else { shirt = shade(f.shirt || '#6b6a45', drift); pants = shade(f.pants || '#5d5b3c', drift * (0.97 + rng() * 0.06)); }
  let hat = pickOr(rng, kit.hat);
  if (hat === 'helmet' || hat === 'helmet_medic') hat = { type: (f.helmet && f.helmet[era]) || ERA_HELMET[era] || 'cap_soft', medic: hat === 'helmet_medic' };
  else if (hat) hat = { type: hat };
  if (hat && ['m1', 'brodie', 'stahl', 'ssh', 'kabuto', 'adrian', 'pith', 'modern'].includes(hat.type)) {
    hat.color = shade(f.gear || '#4d4a33', 0.95 + rng() * 0.1);
    hat.net = era === 'ww2' && (faction === 'us' || faction === 'uk' || faction === 'allied') && rng.chance(0.55);
    hat.strap = rng.chance(0.6);
  } else if (hat) hat.color = hat.type === 'peaked' ? shade(f.shirt || '#5a5a40', 0.9) : hat.type === 'straw' ? '#d8c27a' : hat.type === 'police_cap' ? '#1d2536' : hat.type === 'sailor_cap' ? '#f2f2f2' : rng.pick(['#4a3b2c', '#3a3f4a', '#6a6255', '#2b2b2b']);
  const moodMouth = { tense: ['determined', 'frown', 'flat'], happy: ['smile', 'grin'], grave: ['flat', 'frown'], shout: ['open'] }[mood];
  const face = {
    eyes: rng.pick(FACES.eyes), brows: rng.pick(FACES.brows), mouth: rng.pick(moodMouth || kit.mouth),
    facial: role === 'child' ? 'none' : rng.pick(FACES.facial), glasses: rng.chance(role === 'journalist' || role === 'politician' || role === 'forecaster' ? 0.45 : 0.06),
    hair: hat && ['m1', 'brodie', 'stahl', 'ssh', 'kabuto', 'adrian', 'modern'].includes(hat.type) ? 'none' : rng.pick(FACES.hair), hairColor, scar: rng.chance(0.04),
  };
  const gear = [...kit.gear];
  if ((role === 'soldier' || role === 'paratrooper') && rng.chance(0.25)) gear.push('radio');
  const weapon = kit.weapon ? (rng.chance(0.15) && era === 'ww2' ? 'smg' : WEAPON_BY_ERA[era] || 'rifle_semi') : null;
  return {
    id: name ? `p_${hash(name).toString(36)}` : `c_${hash(`${role}:${faction}:${seed}`).toString(36)}`, name, role, faction, era,
    skin, shirt, pants, torso: kit.torso, tie: kit.torso === 'suit' ? rng.pick(['#7a1f24', '#1f3a7a', '#2a2a2a', '#5a4a1f']) : null,
    belt: kit.torso.startsWith('uniform') || kit.torso === 'police' ? shade(f.gear || '#3a3020', 0.8) : null, hat, face, gear, weapon,
    scale: role === 'child' ? 0.78 : 0.97 + rng() * 0.06, gearColor: f.gear || '#4d4a33', accent: f.accent || '#7a7a5a',
  };
}

/** How different two looks are (0 = identical): used by the variation test and the crowd builder. */
export function lookDistance(a, b) {
  let d = 0;
  for (const k of ['skin', 'shirt', 'pants', 'torso', 'weapon']) if (a[k] !== b[k]) d++;
  for (const k of ['eyes', 'brows', 'mouth', 'facial', 'hair', 'glasses', 'hairColor']) if (a.face[k] !== b.face[k]) d += 0.5;
  if ((a.hat && a.hat.type) !== (b.hat && b.hat.type)) d++;
  if (a.gear.join() !== b.gear.join()) d += 0.5;
  return d;
}
