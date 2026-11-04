// The director: narration in, film plan out. For every beat it decides what the scene must show (event, place, era, time,
// weather), stages it (environment, cast, vehicles, effects), shoots it (shots, camera behaviours, transitions) and dresses
// it (subtitles, date, place tag, chapter card, statistic callouts, sound cues). Every decision is recorded with its reason
// in `report`, and any CSV value overrides the inference. Pure and deterministic: the same story gives the same plan.

import { makeRng, hash } from './rng.mjs';
import { analyseSentence, splitSentences, estimateTiming, alignTiming, wordTime, extractDates, dateLabel, formatCount } from './narration.mjs';
import { makeGazetteer } from './gazetteer.mjs';
import { eraOf, factionsIn, vehicleForEra, FACTIONS } from './eras.mjs';
import { RECIPES, BIOME_ENV, EVENT_ENVS } from './recipes.mjs';
import { ENVIRONMENTS } from './world.mjs';
import { BEHAVIOURS } from './camera.mjs';
import { STATES } from './animation.mjs';
import { VEHICLES } from './vehicles.mjs';
import { EFFECTS } from './fx.mjs';
import { ROLES } from './characters.mjs';
import { bboxAround } from './mapproj.mjs';

export const TRANSITIONS = ['cut', 'dissolve', 'dip', 'clouds', 'map_dive', 'match', 'continuous'];
export const TIMES = ['dawn', 'day', 'sunset', 'dusk', 'night'];
export const WEATHERS = ['clear', 'overcast', 'rain', 'storm', 'fog', 'snow'];
export const VOCAB = {
  events: new Set(Object.keys(RECIPES)), environments: new Set(ENVIRONMENTS), roles: new Set(ROLES), vehicles: new Set(Object.keys(VEHICLES)),
  actions: new Set(STATES), effects: new Set(EFFECTS), cameras: new Set(BEHAVIOURS), transitions: new Set(TRANSITIONS), times: new Set(TIMES), weathers: new Set(WEATHERS),
};

const TIME_PASS = /\b(that night|the next (?:day|morning)|weeks? later|in the weeks that followed|months? later|years? later|by nightfall|by dawn|at sunrise|later that)\b/i;
const AERIAL = new Set(['establishing_wide', 'aerial_geo', 'descend', 'rise', 'flyover', 'pullback_reveal', 'map_overview', 'map_dive']);

/** opts: {words (whisper words) | null, fps, width, height, extraPlaces} */
export function direct(story, opts = {}) {
  const fps = opts.fps || 24, gaz = makeGazetteer(opts.extraPlaces || []), warnings = [], report = [];
  const allText = story.beats.map((b) => b.text).join(' ');
  const planYear = (extractDates(story.plan.date || '')[0] || extractDates(allText)[0] || {}).year ?? null;
  const era = eraOf(planYear);
  const mentioned = factionsIn(allText).filter((f) => f !== 'civilian');
  const sideA = story.plan.extra?.side_a || mentioned.find((f) => ['us', 'allied', 'uk', 'soviet', 'north_vietnam'].includes(f)) || mentioned[0] || 'allied';
  const sideB = story.plan.extra?.side_b || mentioned.find((f) => f !== sideA && f !== 'allied' && f !== 'us' && f !== 'uk') || 'germany';

  // ---- timing: the voiceover's words when we have them, otherwise a planned read ------------------------------------------
  const timing = opts.words && opts.words.length ? alignTiming(story.beats, opts.words) : estimateTiming(story.beats);
  const sentences = timing.sentences;
  const tail = 2.6, duration = +(timing.end + tail).toFixed(3);
  const beatSent = story.beats.map((_, bi) => sentences.filter((s) => s.beat === bi));

  // ---- per-beat analysis and scene decisions --------------------------------------------------------------------------------
  let carryTime = 'day', carryWeather = 'clear', carryDate = '', carryPlace = null, lastScene = null;
  const scenes = [];
  story.beats.forEach((b, bi) => {
    const ss = beatSent[bi]; if (!ss.length) return;
    const A = ss.map((s) => analyseSentence(s.text, gaz, planYear));
    const text = b.text, why = {};
    // event
    let event = b.event || null;
    if (!event) {
      const sc = {}; A.forEach((a) => { for (const [k, v] of Object.entries(a.event.scores)) sc[k] = (sc[k] || 0) + v; });
      const ranked = Object.entries(sc).filter(([k]) => RECIPES[k]).sort((x, y) => y[1] - x[1]);
      event = ranked[0] && ranked[0][1] > 0 ? ranked[0][0] : 'establishing';
      why.event = `classified from the narration (${ranked.slice(0, 2).map(([k, v]) => `${k} ${v}`).join(', ')})`;
    } else why.event = 'set in the CSV';
    if (!RECIPES[event]) { warnings.push(`beat ${b.id}: no recipe for event "${event}", using establishing`); event = 'establishing'; }
    const R = RECIPES[event];
    // place
    const place = gaz.get(b.location) || A.flatMap((a) => a.places).find((p) => p.kind !== 'sea' && p.kind !== 'region') || A.flatMap((a) => a.places)[0] || carryPlace;
    if (b.location && !gaz.get(b.location)) warnings.push(`beat ${b.id}: place "${b.location}" is not in the gazetteer (no map pin; set "lon,lat")`);
    // environment: CSV > words that suit the event > place biome (if it suits) > recipe default
    const words = A.flatMap((a) => a.environments);
    const suits = EVENT_ENVS[event];
    let env = b.environment || null;
    if (env) why.env = 'set in the CSV';
    else {
      const fromWords = words.find((w) => !suits || suits.includes(w));
      const fromPlace = place && BIOME_ENV[place.kind === 'beach' ? 'beach' : place.biome] ;
      if (event === 'political_meeting' || event === 'peace_agreement') { env = 'interior'; why.env = 'meetings happen indoors'; }
      else if (fromWords && fromWords !== 'interior') { env = fromWords === 'sea' && event !== 'naval_operation' && event !== 'natural_disaster' ? (fromPlace || R.env) : fromWords; why.env = `named in the narration ("${fromWords}")`; }
      else if (fromPlace && (!suits || suits.includes(fromPlace))) { env = fromPlace; why.env = `the place (${place.name}) is ${place.biome}`; }
      else { env = R.env; why.env = `the ${event} recipe's default`; }
      if (env === 'town' && place && place.kind === 'city') env = 'city';
    }
    // time / weather (carried across beats until the narration changes them)
    const tWord = A.map((a) => a.time).find(Boolean), wWord = A.map((a) => a.weather).find(Boolean);
    const time = b.time || tWord || R.time || (b.chapter !== (lastScene && lastScene.chapter) && !tWord ? 'day' : carryTime);
    const weather = b.weather || wWord || (time !== carryTime ? 'clear' : carryWeather);
    carryTime = time === 'dusk' ? 'night' : time === 'dawn' ? 'day' : time; carryWeather = weather === 'storm' ? 'rain' : weather;
    // date
    const d0 = extractDates(b.date || '', planYear)[0] || A.flatMap((a) => a.dates)[0];
    const date = d0 ? dateLabel(d0) : carryDate; carryDate = date;
    // cast and vehicles
    const factions = { a: factionsIn(text)[0] && factionsIn(text)[0] !== 'civilian' && factionsIn(text)[0] !== sideB ? factionsIn(text)[0] : sideA, b: sideB };
    const people = A.flatMap((a) => a.people);
    let cast = b.cast.length ? b.cast.map((c) => ({ role: c.role, count: c.count, name: c.name, named: !!c.name, side: c.role === 'crowd' || c.role === 'civilian' ? 'civ' : 'a', formation: defaultFormation(c.role, R), action: defaultAction(c.role, R) })) : R.cast.map((c) => ({ ...c }));
    if (!b.cast.length && people.length) { const lead = cast.find((c) => c.named) || cast.find((c) => c.role === 'commander' || c.role === 'leader'); if (lead) lead.name = people[0].name; }
    let vehicles = b.vehicles.length ? b.vehicles.map((v) => ({ kind: v.kind, count: v.count, motion: v.motion })) : R.vehicles.map((v) => ({ ...v }));
    const spoken = A.flatMap((a) => a.vehicles);
    if (!b.vehicles.length) for (const k of spoken) if (!vehicles.some((v) => v.kind === k) && VEHICLES[k] && (env !== 'interior')) vehicles.push({ kind: k, count: VEHICLES[k].cls === 'air' ? 5 : 3, motion: null, spoken: true });
    vehicles = vehicles.map((v) => { const r = vehicleForEra(v.kind, era); if (r.substituted) warnings.push(`beat ${b.id}: ${v.kind} is not of the ${era.label} era, shown as ${r.kind}`); if (r.anachronism && b.vehicles.length) warnings.push(`beat ${b.id}: ${v.kind} is an anachronism for ${era.label} (kept: set in the CSV)`); return { ...v, kind: r.kind }; })
      .filter((v) => !(r0(v) && !b.vehicles.length)).filter((v) => env !== 'interior');
    function r0(v) { return vehicleForEra(v.kind, era).anachronism; }
    // narration actions, timed to the spoken word
    const actionsTimed = [];
    const csvActs = b.actions.map((a) => ({ state: a.state, word: a.at }));
    const spokenActs = A.flatMap((a, k) => a.actions.map((x) => ({ ...x, sent: k })));
    for (const act of csvActs.length ? csvActs : spokenActs) {
      const s = act.sent != null ? ss[act.sent] : ss.find((x) => wordTime(x, act.word) != null) || ss[0];
      const at = wordTime(s, act.word) ?? s.start;
      actionsTimed.push({ state: act.state, time: at, word: act.word });
    }
    // effects
    const fx = b.effects.length ? [...b.effects] : [...R.fx];
    if (weather === 'rain' || weather === 'storm') fx.push('rain'); if (weather === 'fog') fx.push('fog'); if (weather === 'snow') fx.push('snow');
    const scene = {
      id: `s${scenes.length + 1}`, beat: bi, beatId: b.id, chapter: b.chapter, text, event, recipeIntent: R.intent, env, place: place ? { name: place.name, lon: place.lon, lat: place.lat, country: place.country || '', kind: place.kind } : null,
      time, weather, date, era: era.id, factions, cast, vehicles, actionsTimed, fx, ambience: R.ambience, cues: R.cues || [], camera: b.camera, transitionReq: b.transition, extra: b.extra || {}, sentences: ss, analysis: A,
      seed: b.extra?.seed ?? hash(`${b.id}:${place ? place.name : ''}:${event}`) % 100000, culture: place ? place.culture : 'european', why,
    };
    if (env === 'map' || event === 'map') scene.env = 'map';
    // continuity: the same place and set as the scene before keeps its layout and its people
    if (lastScene && lastScene.env === scene.env && scene.env !== 'map' && lastScene.place && scene.place && lastScene.place.name === scene.place.name) {
      if (b.extra?.seed == null) scene.seed = lastScene.seed;
      if (!b.cast.length && R === RECIPES[lastScene.event]) scene.cast = lastScene.cast.map((c) => ({ ...c }));
      scene.continues = lastScene.id;
    }
    scenes.push(scene); lastScene = scene; carryPlace = place;
    report.push({ beat: b.id, event, env: scene.env, place: place ? place.name : null, time, weather, date, intent: R.intent, why });
  });

  // ---- scene time spans: cut in the pause before the first spoken word ---------------------------------------------------
  scenes.forEach((s, i) => {
    const first = s.sentences[0], prevEnd = i > 0 ? scenes[i - 1].sentences[scenes[i - 1].sentences.length - 1].end : 0;
    s.t0 = i === 0 ? 0 : +Math.max(prevEnd + 0.12, first.start - 0.4).toFixed(3);
  });
  scenes.forEach((s, i) => { s.t1 = i + 1 < scenes.length ? scenes[i + 1].t0 : duration; });

  // ---- map scenes: places, pins, routes ---------------------------------------------------------------------------------
  scenes.forEach((s, i) => {
    if (s.env !== 'map') return;
    const m = s.extra.map || {};
    const named = (m.pins || []).map((n) => gaz.get(n)).filter(Boolean);
    const near = [s, scenes[i + 1], scenes[i - 1]].filter(Boolean).flatMap((x) => x.analysis ? x.analysis.flatMap((a) => a.places) : []);
    const pins = (named.length ? named : near).filter((p, k, arr) => arr.findIndex((q) => q.name === p.name) === k);
    const arrows = (m.arrows || []).map(([a, b2]) => [gaz.get(a), gaz.get(b2)]).filter(([a, b2]) => a && b2).map(([a, b2], k) => ({ from: [a.lon, a.lat], to: [b2.lon, b2.lat], t0: s.t0 + 0.8 + k * 0.5, t1: s.t0 + 0.8 + k * 0.5 + Math.min(3.2, (s.t1 - s.t0) * 0.5), label: m.arrowLabel || '' }));
    const pts = [...pins.map((p) => [p.lon, p.lat]), ...arrows.flatMap((a) => [a.from, a.to])];
    if (!pts.length && s.place) pts.push([s.place.lon, s.place.lat]);
    if (!pts.length) { warnings.push(`map scene ${s.id}: no places to show; it falls back to a generic overview`); pts.push([0, 50]); }
    const next = scenes[i + 1];
    const diveTo = m.dive ? gaz.get(m.dive) : next && next.place ? next.place : null;
    s.map = { bbox: m.bbox || bboxAround(pts, m.margin ?? 1.2, m.span ?? 3), pins: pins.map((p, k) => ({ name: p.name, lon: p.lon, lat: p.lat, t: s.t0 + 0.6 + k * 0.35, kind: p.kind })), arrows,
      diveTo: diveTo ? [diveTo.lon, diveTo.lat] : null, regions: m.regions || [], illustrative: true, note: m.note || 'Present-day coastlines and borders shown for orientation. Positions approximate.' };
  });

  // ---- shots ------------------------------------------------------------------------------------------------------------
  const sideYaw = 0.55; let prevB = null, prev2 = null;
  scenes.forEach((s, i) => {
    const R = RECIPES[s.event] || RECIPES.establishing, rng = makeRng(`shots:${s.id}:${s.seed}`);
    const prevScene = scenes[i - 1];
    const newPlace = !prevScene || !prevScene.place || !s.place || prevScene.place.name !== s.place.name || prevScene.env !== s.env;
    const cuts = [s.t0];
    // split long scenes at sentence boundaries (in the pause), shots 3.6..8 s
    const D = s.t1 - s.t0;
    if (s.env !== 'map') for (let k = 1; k < s.sentences.length; k++) { const c = (s.sentences[k - 1].end + s.sentences[k].start) / 2; if (c - cuts[cuts.length - 1] >= 3.6 && s.t1 - c >= 3.6) cuts.push(+c.toFixed(3)); }
    // a very long sentence still gets a second shot half-way (camera never parks for more than ~9 s)
    for (let k = 0; k < cuts.length; k++) { const end = cuts[k + 1] ?? s.t1; if (end - cuts[k] > 9.5 && s.env !== 'map') cuts.splice(k + 1, 0, +(cuts[k] + (end - cuts[k]) / 2).toFixed(3)); }
    const requested = s.camera ? s.camera.split('>').map((x) => x.trim()) : [];
    const prefs = s.env === 'map' ? ['map_overview'] : [...R.shots];
    s.shots = cuts.map((c0, k) => {
      const c1 = cuts[k + 1] ?? s.t1;
      let beh = requested[k] || null, reason = beh ? 'set in the CSV' : '';
      if (!beh) {
        if (s.env === 'map') { beh = s.map && s.map.diveTo && k === cuts.length - 1 && D > 3 ? 'map_overview' : 'map_overview'; reason = 'geography'; }
        else if (k === 0 && prevScene && prevScene.env === 'map') { beh = 'descend'; reason = 'continues the map dive down to the ground'; }
        else if (k === 0 && newPlace && (s.event === 'establishing' || s.event === 'consequence' || s.event === 'troop_deployment' || s.event === 'naval_operation')) { beh = prefs.find((p) => AERIAL.has(p)) || 'establishing_wide'; reason = 'a new place opens wide'; }
        else if (s.event === 'political_meeting' && k === 0) { beh = 'establishing_interior'; reason = 'introduce the room and who is in it'; }
        else {
          const sent = s.sentences.find((x) => x.start >= c0 - 0.5 && x.start < c1) || s.sentences[0];
          const an = s.analysis[s.sentences.indexOf(sent)] || s.analysis[0];
          if (an && an.people.length && !['push_in', 'low_angle'].includes(prevB)) { beh = s.env === 'interior' ? 'push_in' : 'low_angle'; reason = `introduces ${an.people[0].title} ${an.people[0].name}`; }
          else if (an && an.vehicles.length && s.vehicles.some((v) => v.kind === an.vehicles[0]) && prevB !== 'vehicle_follow') { beh = 'vehicle_follow'; reason = `follows the ${an.vehicles[0].replace('_', ' ')} the narration names`; }
          else if (an && an.numbers.length && k === cuts.length - 1) { beh = prefs.includes('pullback_reveal') ? 'pullback_reveal' : 'rise'; reason = 'a number about scale: reveal the scale'; }
          else { beh = prefs.find((p) => p !== prevB && p !== prev2 && (k > 0 || !AERIAL.has(p) || newPlace)) || prefs.find((p) => p !== prevB) || prefs[0]; reason = `the ${s.event} recipe's next camera`; }
        }
      }
      if (beh === prevB && prefs.length > 1 && !requested[k]) { beh = prefs.find((p) => p !== prevB) || beh; reason += ' (varied: not the same as the last shot)'; }
      prev2 = prevB; prevB = beh;
      const subject = subjectFor(beh, s);
      const yaw = (s.heading ?? 0) + sideYaw + rng.range(-0.45, 0.45) + (beh === 'over_shoulder' ? 0 : 0);
      return { behaviour: beh, t0: c0, t1: c1, yaw, subject, reason, scale: 1 };
    });
    // within a scene: aerial-to-aerial changes are one continuous move, others are cuts
    s.shots.forEach((sh, k) => { sh.transition = k === 0 ? null : AERIAL.has(sh.behaviour) && AERIAL.has(s.shots[k - 1].behaviour) ? 'continuous' : 'cut'; });
    // transition into the scene
    let tr = s.transitionReq;
    const reasonTr = [];
    if (!tr) {
      if (i === 0) tr = 'dip';
      else if (s.env === 'map' || prevScene.env === 'map') tr = 'clouds';
      else if (s.chapter !== prevScene.chapter) tr = 'dip';
      else if (TIME_PASS.test(s.sentences[0].text) || prevScene.time !== s.time) tr = 'dissolve';
      else tr = 'cut';
    }
    reasonTr.push(tr);
    s.transitionIn = { type: tr, dur: { cut: 0, dissolve: 1.0, dip: 0.9, clouds: 1.4, map_dive: 1.4, match: 0, continuous: 1.2 }[tr] ?? 0 };
    s.light = lightPreset(s.time, s.weather, s.env);
  });

  // ---- HUD: subtitles, dates, places, chapter cards, statistics ------------------------------------------------------------
  const hud = { subtitles: [], dates: [], places: [], chapters: [], stats: [], labels: [], credit: null };
  for (const s of sentences) hud.subtitles.push(...captionCards(s));
  let lastDate = '';
  scenes.forEach((s) => {
    if (s.date && s.date !== lastDate) { hud.dates.push({ t0: s.t0 + (s.transitionIn.dur || 0) * 0.6, label: s.date, big: true }); lastDate = s.date; }
    const prevPlace = hud.places[hud.places.length - 1];
    if (s.place && s.env !== 'map' && (!prevPlace || prevPlace.label !== s.place.name.toUpperCase())) hud.places.push({ t0: s.t0 + 0.6 + (s.transitionIn.dur || 0) * 0.5, t1: Math.min(s.t1, s.t0 + 5.2), label: s.place.name.toUpperCase(), sub: [s.place.country].filter(Boolean).join(' · ').toUpperCase() });
    if (s.extra.label) hud.labels.push({ t0: s.t0 + 0.8, t1: Math.min(s.t1 - 0.2, s.t0 + 5), text: s.extra.label });
    const statDefs = s.extra.stats || (s.extra.stat ? [s.extra.stat] : null);
    if (statDefs) statDefs.forEach((def, k) => {
      const [value, label] = String(def).split('|').map((x) => x.trim()), at = s.sentences.find((x) => /\d|thousand|hundred|million/i.test(x.text)) || s.sentences[0];
      const span = (at.end - at.start + 2.2) / statDefs.length, a0 = at.start + 0.4 + k * span;
      hud.stats.push({ t0: +a0.toFixed(3), t1: +Math.min(s.t1 - 0.3, a0 + Math.max(2.6, span)).toFixed(3), value, label: (label || '').toUpperCase() });
    });
    else s.analysis.forEach((an, k) => { const n = an.numbers.find((x) => x.value >= 1000); if (n) { const sent = s.sentences[k]; const at = wordTime(sent, n.text.split(' ')[0]) ?? sent.start; hud.stats.push({ t0: at, t1: Math.min(s.t1 - 0.3, at + 4), value: formatCount(n.value), label: n.noun.toUpperCase() }); } });
  });
  story.chapters.forEach((c, ci) => {
    const s = scenes.find((x) => x.chapter === ci); if (!s) return;
    const first = s.sentences[0];
    const t0 = Math.max(0, s.t0 - 0.2), t1 = Math.max(t0 + 2.2, Math.min(first.start + 1.6, s.t0 + 3.4));
    hud.chapters.push({ t0, t1, index: ci + 1, title: c.title.toUpperCase(), date: c.date || '' });
  });
  for (const s of scenes) if (s.env === 'map' && s.map) hud.labels.push({ t0: s.t0 + 0.6, t1: s.t1 - 0.3, text: s.map.note, kind: 'note' });

  // ---- audio plan: ambience beds per scene, cues on visible events ----------------------------------------------------------
  const audio = { ambience: [], cues: [], music: pickMusic(story, scenes) };
  for (const s of scenes) {
    let bed = s.ambience;
    if (s.weather === 'rain' || s.weather === 'storm') bed = s.env === 'interior' ? 'room_rain' : 'rain';
    if (s.time === 'night' && bed === 'camp') bed = 'night_wind';
    audio.ambience.push({ t0: s.t0, t1: s.t1, bed, scene: s.id });
    if (s.transitionIn.type === 'clouds' || s.transitionIn.type === 'map_dive') audio.cues.push({ t: s.t0 - 0.3, cue: 'whoosh', gain: -16 });
    if (s.transitionIn.type === 'dip' && hud.chapters.some((c) => Math.abs(c.t0 - s.t0) < 0.5)) audio.cues.push({ t: s.t0 + 0.2, cue: 'chapter_hit', gain: -18 });
  }
  return { fps, width: opts.width || 1920, height: opts.height || 1080, duration, title: story.plan.title || '', era: era.id, eraLabel: era.label, sides: { a: sideA, b: sideB, labelA: FACTIONS[sideA]?.label, labelB: FACTIONS[sideB]?.label },
    sentences: sentences.map(({ beat, text, start, end, words }) => ({ beat, text, start, end, words })), scenes: scenes.map(stripScene), hud, audio, warnings, report, voiceTimed: !!(opts.words && opts.words.length) };
}

function stripScene(s) { const { analysis, ...rest } = s; return { ...rest, numbers: analysis.flatMap((a) => a.numbers), people: analysis.flatMap((a) => a.people) }; }

function defaultFormation(role, R) { const g = R.cast.find((c) => c.role === role); return g ? g.formation : role === 'crowd' ? 'crowd' : role === 'commander' || role === 'leader' ? 'head' : 'scatter'; }
function defaultAction(role, R) { const g = R.cast.find((c) => c.role === role); return g ? g.action : 'idle'; }

/** what a camera behaviour looks at in a scene (resolved to positions by the stage at render time) */
function subjectFor(beh, s) {
  const groups = s.cast.map((c) => c.role);
  const lead = s.cast.find((c) => c.named) || s.cast.find((c) => ['commander', 'leader', 'officer'].includes(c.role));
  const movers = s.vehicles.find((v) => v.motion !== 'park' && v.motion !== 'drift') || s.vehicles[0];
  switch (beh) {
    case 'vehicle_follow': return movers ? { type: 'vehicles', kind: movers.kind, pick: 'middle' } : { type: 'group', role: groups[0] };
    case 'push_in': case 'low_angle': case 'static_close': return lead ? { type: 'actor', role: lead.role, index: 0 } : { type: 'group', role: groups[0], pick: 'nearest' };
    case 'over_shoulder': return lead ? { type: 'actor', role: lead.role, index: 0, lookAt: { type: 'group', role: s.cast.find((c) => c !== lead)?.role || lead.role } } : { type: 'group', role: groups[0] };
    case 'ground_track': case 'follow': return groups.length ? { type: 'group', role: groups[0], pick: 'front' } : { type: 'anchor', name: 'center' };
    case 'establishing_wide': case 'aerial_geo': case 'descend': case 'rise': case 'flyover': case 'pullback_reveal': return s.vehicles.length && s.env === 'sea' ? { type: 'vehicles', kind: s.vehicles[0].kind, pick: 'centroid' } : groups.length ? { type: 'group', role: groups[0], pick: 'centroid' } : { type: 'anchor', name: 'center' };
    default: return groups.length ? { type: 'group', role: groups[0], pick: 'centroid' } : movers ? { type: 'vehicles', kind: movers.kind, pick: 'centroid' } : { type: 'anchor', name: 'center' };
  }
}

/** subtitle cards for a sentence: <= 2 lines of <= 42 characters, split at word times when longer */
export function captionCards(s, maxLine = 42) {
  const cards = []; let cur = [], len = 0;
  const flush = () => { if (!cur.length) return; cards.push(cur); cur = []; len = 0; };
  const ws = s.text.split(/\s+/);
  ws.forEach((w) => { if (len + w.length + 1 > maxLine * 2 - 4 && cur.length) flush(); cur.push(w); len += w.length + 1; });
  flush();
  // never leave one or two words alone on a card: fold them into the card before
  if (cards.length > 1) { const last = cards[cards.length - 1], prev = cards[cards.length - 2]; while (last.length < 3 && prev.length > 4) last.unshift(prev.pop()); }
  let wi = 0;
  return cards.map((c, k) => {
    const t0 = s.words[Math.min(wi, s.words.length - 1)]?.start ?? s.start; wi += c.length;
    const t1 = k === cards.length - 1 ? s.end + 0.25 : (s.words[Math.min(wi, s.words.length - 1)]?.start ?? s.end) - 0.02;
    const text = c.join(' '), lines = [];
    let line = '';
    for (const w of c) { if ((line + ' ' + w).trim().length > maxLine && line) { lines.push(line); line = w; } else line = (line + ' ' + w).trim(); }
    if (line) lines.push(line);
    return { t0: +t0.toFixed(3), t1: +t1.toFixed(3), text, lines, words: s.words.slice(wi - c.length, wi).map((w) => ({ start: w.start })) };
  });
}

export function lightPreset(time, weather, env) {
  if (env === 'interior') return weather === 'rain' || weather === 'storm' ? 'interior_storm' : 'interior_warm';
  if (env === 'map') return 'map';
  if (time === 'night') return 'night';
  if (weather === 'storm') return 'storm';
  if (time === 'dawn') return weather === 'overcast' ? 'overcast' : 'dawn';
  if (time === 'sunset') return 'sunset';
  if (time === 'dusk') return 'dusk';
  if (weather === 'overcast' || weather === 'rain' || weather === 'fog') return 'overcast';
  return 'day';
}

function pickMusic(story, scenes) {
  const m = story.plan.extra?.music;
  if (m) return { tracks: [m], reason: 'set in the CSV' };
  const battle = scenes.some((s) => ['battle', 'landing_operation', 'airstrike', 'military_invasion'].includes(s.event));
  return battle ? { tracks: ['stormfront', 'despair_and_triumph'], reason: 'war story: tense bed into an epic one' } : { tracks: ['echoes_of_time_v2', 'ascending_the_vale'], reason: 'calm history story' };
}

export { splitSentences };
