// Scene assembly, shared by the browser renderer and Node (tests, QC, the audio plan). From a planned scene it builds the
// world, stages the cast and vehicles, plans the effects and the sound cues they cause, and answers "where is the camera
// at time t" with shot continuity and collision. Same input -> same answer in both places.

import { makeRng, smooth, lerp, clamp } from './rng.mjs';
import { makeWorld } from './world.mjs';
import { stageScene, evaluateActor } from './stage.mjs';
import { vehicleState, VEHICLES } from './vehicles.mjs';
import { shotCamera, constrain } from './camera.mjs';
import { particlesAt } from './fx.mjs';

const HEADING = { beach: 0, sea: 0, port: 0, island: 0, interior: 0 };

export function assembleScene(scene) {
  const W = makeWorld(scene.env === 'map' ? 'map' : scene.env, { seed: scene.seed, culture: scene.culture, era: scene.era, time: scene.time, weather: scene.weather, damaged: ['battle', 'aftermath', 'city_occupation', 'airstrike', 'landing_operation'].includes(scene.event), variant: scene.extra.variant });
  const heading = scene.extra.heading ?? HEADING[scene.env] ?? (W.roads.length ? Math.PI / 2 : 0);
  scene.heading = heading;
  const rampAt = scene.event === 'landing_operation' ? (scene.actionsTimed.find((a) => a.word && /ramp|dropped/.test(a.word))?.time ?? (scene.sentences.map((s) => s.words.find((w) => /^ramp/.test(w.word))).find(Boolean)?.start) ?? scene.t0 + (scene.t1 - scene.t0) * 0.35) : null;
  const castSpec = scene.cast.map((c) => ({ ...c, anchor: c.anchor || anchorFor(c, scene, W) }));
  const vehSpec = scene.vehicles.map((v) => ({ ...v, motion: v.motion || defaultMotion(v.kind, scene, W), anchor: v.anchor || vehicleAnchor(v.kind, scene, W) }));
  const stage = scene.env === 'map' ? { actors: [], vehicles: [] } : stageScene(W, { cast: castSpec, vehicles: vehSpec, actionsTimed: scene.actionsTimed, t0: scene.t0, t1: scene.t1, seed: scene.seed, era: scene.era, factions: scene.factions, heading, rampAt });
  const vIndex = new Map(stage.vehicles.map((v) => [v.id, v]));
  const A = { scene, world: W, stage, vIndex, heading, rampAt };
  A.actorAt = (a, t) => evaluateActor(a, t, W, vIndex);
  A.vehicleAt = (v, t) => vehicleState(v, t, W);
  const fxp = planFx(A);
  A.emitters = fxp.emitters; A.cues = fxp.cues; A.lights = fxp.lights;
  A.subjectAt = (sub, t) => subjectPoint(A, sub, t);
  A.cameraAt = (t) => sceneCamera(A, t);
  return A;
}

const anchorFor = (c, scene, W) => (c.formation === 'boats' ? 'center' : c.formation === 'sky' ? 'center' : c.anchor) || (W.anchors.center ? 'center' : 'center');
function defaultMotion(kind, scene, W) {
  const spec = VEHICLES[kind]; if (!spec) return 'park';
  if (spec.cls === 'air') return 'flyover';
  if (spec.cls === 'water') return scene.env === 'beach' && kind === 'landing_craft' ? 'approach_beach' : scene.env === 'sea' && kind === 'landing_craft' ? 'advance' : 'drift';
  return W.roads.length && ['convoy_movement', 'liberation', 'troop_deployment'].includes(scene.event) ? 'convoy' : spec.speed ? 'advance' : 'park';
}
function vehicleAnchor(kind, scene, W) {
  const spec = VEHICLES[kind]; if (!spec) return 'center';
  if (spec.cls === 'water' && W.anchors.offshore && kind !== 'landing_craft') return W.anchors.far_sea ? 'far_sea' : 'offshore';
  if (spec.cls === 'water' && W.anchors.waterline) return 'waterline';
  return 'center';
}

// ---- subjects -------------------------------------------------------------------------------------------------------------
function rawSubject(A, sub, t) {
  if (!sub) return A.world.anchorY('center');
  if (sub.type === 'anchor') return A.world.anchorY(sub.name);
  if (sub.type === 'vehicles') {
    const vs = A.stage.vehicles.filter((v) => v.kind === sub.kind); if (!vs.length) return A.world.anchorY('center');
    if (sub.pick === 'middle') { const v = vs[Math.floor(vs.length / 2)], s = A.vehicleAt(v, t); return [s.x, s.y + VEHICLES[v.kind].hgt * 0.4, s.z]; }
    const ps = vs.map((v) => A.vehicleAt(v, t)); return [avg(ps.map((p) => p.x)), avg(ps.map((p) => p.y)), avg(ps.map((p) => p.z))];
  }
  const pool = A.stage.actors.filter((a) => a.role === sub.role);
  const list = pool.length ? pool : A.stage.actors;
  if (!list.length) return A.world.anchorY('center');
  if (sub.type === 'actor') { const s = A.actorAt(list[Math.min(sub.index || 0, list.length - 1)], t); return [s.x, s.y, s.z]; }
  const ps = list.slice(0, 40).map((a) => A.actorAt(a, t));
  if (sub.pick === 'front') { const h = A.heading, f = (p) => p.x * Math.sin(h) + p.z * Math.cos(h); const ground = ps.filter((p) => !p.riding) ; const pp = ground.length ? ground : ps; const fm = Math.max(...pp.map(f)), wts = pp.map((p) => Math.exp((f(p) - fm) / 6)), ws = wts.reduce((a, b) => a + b, 0); const best = { x: pp.reduce((s, p, i) => s + p.x * wts[i], 0) / ws, y: pp.reduce((s, p, i) => s + p.y * wts[i], 0) / ws, z: pp.reduce((s, p, i) => s + p.z * wts[i], 0) / ws }; /* soft-max, not argmax: the point glides as people move instead of jumping to whoever is now in front */ const c = [avg(pp.map((p) => p.x)), avg(pp.map((p) => p.y)), avg(pp.map((p) => p.z))]; return [lerp(c[0], best.x, 0.5), lerp(c[1], best.y, 0.5), lerp(c[2], best.z, 0.5)]; }
  if (sub.pick === 'nearest') return [ps[0].x, ps[0].y, ps[0].z];
  return [avg(ps.map((p) => p.x)), avg(ps.map((p) => p.y)), avg(ps.map((p) => p.z))];
}
const avg = (xs) => xs.reduce((s, x) => s + x, 0) / Math.max(1, xs.length);
function subjectPoint(A, sub, t) {
  // averaged over +-0.6 s: walking bodies and bobbing boats do not shake the frame
  const ks = [-0.6, -0.3, 0, 0.3, 0.6], ps = ks.map((k) => rawSubject(A, sub, t + k));
  return [avg(ps.map((p) => p[0])), avg(ps.map((p) => p[1])), avg(ps.map((p) => p[2]))];
}
function subjectScale(A, sub) {
  if (!sub) return 1;
  if (sub.type === 'vehicles') { const s = VEHICLES[sub.kind]; return s ? clamp(Math.sqrt(s.len / 14), 0.8, 2.6) : 1; }
  if (sub.type === 'actor') return 1;
  if (sub.type === 'group') { const n = A.stage.actors.filter((a) => a.role === sub.role).length; return 1 + Math.min(1.6, n / 26); }
  return 1.5;
}

// ---- camera ---------------------------------------------------------------------------------------------------------------
function shotAt(A, t) { const sh = A.scene.shots; let i = sh.findIndex((s) => t >= s.t0 && t < s.t1); if (i < 0) i = t < sh[0].t0 ? 0 : sh.length - 1; return i; }
function rawCam(A, sh, t) {
  const sub = sh.subject;
  const subj = (tt) => A.subjectAt(sub, tt);
  const dirAt = (tt) => { const a = subj(tt - 0.5), b = subj(tt + 0.5); return Math.hypot(b[0] - a[0], b[2] - a[2]) > 0.3 ? Math.atan2(b[0] - a[0], b[2] - a[2]) : A.heading; };
  const shot = { ...sh, scale: subjectScale(A, sub), yaw: sh.yaw + (A.scene.env === 'interior' ? 0 : 0) };
  // a formation of aircraft is seen from far enough to read as aircraft, not as one wing filling the frame
  if (sub && sub.type === 'vehicles' && VEHICLES[sub.kind]?.cls === 'air' && sh.behaviour === 'vehicle_follow') { shot.dist = sh.dist || 150 * shot.scale; shot.height = sh.height ?? 60 * shot.scale; }
  if (sh.behaviour === 'over_shoulder' && sub && sub.lookAt) shot.lookAt = A.subjectAt(sub.lookAt, t);
  if (A.scene.env === 'map') { const c = A.mapFocus ? A.mapFocus(t) : [0, 0, 0]; return shotCamera(shot, t, () => c, dirAt); }
  return shotCamera(shot, t, subj, dirAt);
}
export function sceneCamera(A, t) {
  const i = shotAt(A, t), sh = A.scene.shots[i];
  let cam = rawCam(A, sh, t);
  if (sh.transition === 'continuous' && i > 0 && t - sh.t0 < 1.4) {
    const prev = rawCam(A, A.scene.shots[i - 1], t), k = smooth((t - sh.t0) / 1.4);
    cam = { pos: cam.pos.map((v, j) => lerp(prev.pos[j], v, k)), target: cam.target.map((v, j) => lerp(prev.target[j], v, k)), fov: lerp(prev.fov, cam.fov, k), roll: 0 };
  }
  if (A.scene.env === 'map') return cam;
  return avoidVehicles(A, constrain(cam, A.world), t);
}
/** the camera never sits inside a plane, boat or truck: pushed out of any vehicle's bounding sphere (a shot's subject excepted by distance) */
function avoidVehicles(A, cam, t) {
  const pos = [...cam.pos];
  for (const v of A.stage.vehicles) {
    const sp = VEHICLES[v.kind]; if (!sp) continue;
    const s = A.vehicleAt(v, t); if (s.visible === false) continue;
    const r = Math.max(7, sp.len * 0.75 + 3), dx = pos[0] - s.x, dy = pos[1] - (s.y + sp.hgt * 0.5), dz = pos[2] - s.z, d = Math.hypot(dx, dy, dz);
    if (d < r) { const k = d < 0.01 ? 1 : r / d, ux = d < 0.01 ? 0 : dx, uy = d < 0.01 ? 1 : dy, uz = d < 0.01 ? 0 : dz; pos[0] = s.x + ux * k; pos[1] = s.y + sp.hgt * 0.5 + uy * k; pos[2] = s.z + uz * k; }
  }
  return { ...cam, pos };
}

// ---- effects and the sounds they cause ---------------------------------------------------------------------------------------
function planFx(A) {
  const s = A.scene, W = A.world, rng = makeRng(`fx:${s.id}:${s.seed}`), em = [], cues = [], lights = [];
  const t0 = s.t0, t1 = s.t1, D = t1 - t0, want = new Set(s.fx);
  const castPts = A.stage.actors.slice(0, 30).map((a) => { const p = A.actorAt(a, t0 + D * 0.5); return [p.x, p.z]; });
  const farFromCast = (x, z, r) => castPts.every(([cx, cz]) => Math.hypot(cx - x, cz - z) > r);
  const groundY = (x, z) => Math.max(W.heightAt(x, z), W.water ? W.water.level : -1e9);
  const pick = (zone) => { for (let k = 0; k < 20; k++) { const [x, z] = zone(); if (farFromCast(x, z, 18)) return [x, z]; } return zone(); };
  const zone = () => {
    if (W.env === 'beach') { const x = rng.range(-180, 180); return [x, W.shoreZ(x) + rng.range(20, 110)]; }
    if (W.env === 'sea') return [rng.range(-200, 200), rng.range(-160, 60)];
    return [rng.range(-120, 120), rng.range(-120, 120)];
  };
  if (want.has('smoke') || want.has('smoke_light')) {
    const n = want.has('smoke') ? 5 : 3, type = want.has('smoke') ? 'smoke' : 'smoke_light';
    const spots = W.props.filter((p) => p.kind === 'bunker' || p.kind === 'wreck').concat(W.buildings.filter((b) => b.damaged));
    for (let i = 0; i < n; i++) { const sp = spots[i] || null, [x, z] = sp ? [sp.x + rng.range(-3, 3), sp.z + rng.range(-3, 3)] : pick(zone); em.push({ type, x, y: groundY(x, z) + 1, z, t0: t0 - 12, t1: t1 + 2, rate: 2.2, area: [2, 2], wind: [1.4, 0.4], seed: `${s.id}:sm${i}` }); }
  }
  if (want.has('fire') || want.has('fire_small')) for (let i = 0; i < (want.has('fire') ? 4 : 2); i++) { const b = W.buildings.find((x, k) => x.damaged && k % 3 === i) || null; const [x, z] = b ? [b.x, b.z] : pick(zone); const y = groundY(x, z) + (b ? 2 : 0.5); em.push({ type: 'fire', x, y, z, t0: t0 - 2, t1: t1 + 2, rate: 18, area: [2, 2], seed: `${s.id}:f${i}` }, { type: 'smoke', x, y: y + 3, z, t0: t0 - 10, t1: t1 + 2, rate: 1.5, area: [1.5, 1.5], wind: [1.2, 0.3], seed: `${s.id}:fs${i}` }); lights.push({ type: 'fire', x, y: y + 3, z, intensity: 1 }); }
  if (want.has('explosions')) {
    const n = Math.max(1, Math.min(5, Math.floor(D / 3.2)));
    for (let i = 0; i < n; i++) {
      const at = t0 + (i + 0.6 + rng.range(-0.25, 0.25)) * (D / (n + 0.4)), [x, z] = pick(zone), y = groundY(x, z);
      const wet = W.water && W.heightAt(x, z) < 0;
      em.push({ type: wet ? 'splash' : 'explosion', x, y, z, t0: at, t1: at + 0.1, burst: true, count: wet ? 30 : 26, spreadScale: 1, seed: `${s.id}:x${i}`, sizeScale: wet ? 2.2 : 1.6 },
        { type: 'debris', x, y, z, t0: at, t1: at + 0.1, burst: true, count: wet ? 0 : 18, seed: `${s.id}:d${i}` },
        { type: wet ? 'splash' : 'smoke_light', x, y: y + 1, z, t0: at + 0.05, t1: at + 3, rate: 6, area: [2, 2], wind: [1.2, 0.4], seed: `${s.id}:xs${i}` });
      lights.push({ type: 'flash', x, y: y + 4, z, t: at, intensity: 3 });
      cues.push({ t: at, cue: wet ? 'water_explosion' : 'explosion', gain: -9, x, z });
    }
  }
  if (want.has('tracers_in')) {
    const src = W.env === 'beach' ? (x) => [x, W.heightAt(x, W.shoreZ(x) + 104) + 4, W.shoreZ(x) + 104] : () => [rng.range(-80, 80), 6, 120];
    for (let i = 0; i < 6; i++) { const x = rng.range(-150, 150), [sx, sy, sz] = src(x); em.push({ type: 'tracer', x: sx, y: sy, z: sz, t0, t1, rate: 1.1 + rng.range(0, 0.8), dir: [rng.range(-0.2, 0.2), -0.05, -1], len: 140, seed: `${s.id}:tr${i}` }); }
    cues.push({ t: t0, t1, cue: 'gunfire_far', gain: -18, loop: true });
  }
  if (want.has('splashes') && W.water) for (let i = 0; i < 3; i++) { const x = rng.range(-140, 140), z = (W.shoreZ ? W.shoreZ(x) : 0) - rng.range(4, 50); em.push({ type: 'splash', x, y: 0, z, t0, t1, rate: 1.6, area: [30, 12], seed: `${s.id}:sp${i}`, sizeScale: 0.8 }); }
  if (want.has('dust') || A.stage.vehicles.some((v) => VEHICLES[v.kind].dust)) for (const v of A.stage.vehicles.filter((x) => VEHICLES[x.kind].dust && x.motion !== 'park').slice(0, 10)) em.push({ type: 'dust', follow: v.id, t0, t1, rate: 5, area: [VEHICLES[v.kind].wid / 2, 1], seed: `${s.id}:du:${v.id}`, sizeScale: VEHICLES[v.kind].len / 12 });
  if (want.has('flak')) for (let i = 0; i < Math.floor(D / 1.2); i++) { const at = t0 + i * 1.2 + rng.range(0, 0.8), x = rng.range(-120, 120), z = rng.range(-120, 120); em.push({ type: 'flak', x, y: 80 + rng.range(-10, 25), z, t0: at, t1: at + 0.1, burst: true, count: 8, seed: `${s.id}:fl${i}` }); lights.push({ type: 'flash', x, y: 90, z, t: at, intensity: 1.2 }); cues.push({ t: at, cue: 'flak', gain: -22 }); }
  if (want.has('naval_guns')) { const ships = A.stage.vehicles.filter((v) => v.kind === 'battleship' || v.kind === 'ship'); for (let i = 0; i < Math.min(6, Math.floor(D / 2)); i++) { const v = ships[i % Math.max(1, ships.length)]; if (!v) break; const at = t0 + 0.8 + i * (D / 6) + rng.range(0, 0.6), st = A.vehicleAt(v, at); em.push({ type: 'muzzle', x: st.x, y: st.y + 9, z: st.z, t0: at, t1: at + 0.1, burst: true, count: 3, sizeScale: 9, seed: `${s.id}:ng${i}` }, { type: 'smoke_light', x: st.x, y: st.y + 9, z: st.z, t0: at, t1: at + 0.6, rate: 10, area: [4, 4], wind: [2, 0], seed: `${s.id}:ngs${i}`, sizeScale: 2 }); lights.push({ type: 'flash', x: st.x, y: st.y + 12, z: st.z, t: at, intensity: 2.5 }); cues.push({ t: at, cue: 'ship_guns', gain: -12 }); } }
  if (want.has('confetti')) em.push({ type: 'confetti', x: 0, y: 26, z: 0, t0: t0 - 2, t1, rate: 40, area: [80, 20], seed: `${s.id}:cf` });
  if (want.has('chimney_smoke')) W.props.filter((p) => p.kind === 'chimney').forEach((p, i) => em.push({ type: 'smoke', x: p.x, y: p.y + 30, z: p.z, t0: t0 - 12, t1: t1 + 2, rate: 1.8, area: [1, 1], wind: [2, 0.4], seed: `${s.id}:ch${i}` }));
  if (want.has('dust_motes')) em.push({ type: 'dust_motes', x: -10, y: 6, z: 0, t0: t0 - 12, t1: t1 + 2, rate: 8, area: [10, 8], seed: `${s.id}:dm` });
  if (want.has('birds')) em.push({ type: 'bird', x: 0, y: 40, z: 0, t0: t0 - 20, t1: t1 + 2, rate: 0.8, area: [60, 60], seed: `${s.id}:bd` });
  // muzzle flashes of actors who fire: cues follow the flashes (one cue per burst window, not per frame)
  const shooters = A.stage.actors.filter((a) => a.armed && a.schedule.some((x) => x.state === 'fire'));
  if (shooters.length) cues.push({ t: t0, t1, cue: 'gunfire_near', gain: -16, loop: true, density: Math.min(1, shooters.length / 6) });
  // landing craft ramps
  for (const v of A.stage.vehicles) if (v.rampAt != null) cues.push({ t: v.rampAt, cue: 'ramp_drop', gain: -14, vehicle: v.id });
  return { emitters: em, cues, lights };
}

/** particles of an emitter, following its vehicle when it has one (each particle starts where the vehicle was at its birth) */
export function emitterParticles(A, em, t) {
  if (!em.follow) return particlesAt(em, t);
  const v = A.vIndex.get(em.follow); if (!v) return [];
  const out = [], life = 2.6, rate = em.rate;
  for (let b = Math.ceil((t - life) * rate) / rate; b <= t; b += 1 / rate) {
    if (b < em.t0 || b > em.t1) continue;
    const st = A.vehicleAt(v, b); if (!st.moving) continue;
    const back = VEHICLES[v.kind].len * 0.45, bx = st.x - Math.sin(st.yaw) * back, bz = st.z - Math.cos(st.yaw) * back;
    const ps = particlesAt({ ...em, follow: null, x: bx, y: st.y, z: bz, t0: b, t1: b + 0.01, burst: true, count: 2, seed: `${em.seed}:${Math.round(b * rate)}` }, t);
    out.push(...ps);
  }
  return out;
}
