// Stage: puts a scene's cast on its set. Formations place people, paths say where they go, schedules say what they do and
// when (narration actions land on the spoken word). evaluateActor() gives position, facing and pose at any time; it is the
// one function both the renderer and the tests use, so what the tests check is what the frames show.

import { makeRng, clamp, smooth, lerp } from './rng.mjs';
import { makeCharacter } from './characters.mjs';
import { poseAt, travelAt, SPEED } from './animation.mjs';
import { planVehicles, vehicleState, VEHICLES } from './vehicles.mjs';

const MOVING = new Set(['walk', 'run', 'march', 'wade', 'crawl', 'carry', 'enter_vehicle', 'exit_vehicle']);
const ARMED_ROLES = new Set(['soldier', 'paratrooper', 'guard']);

function pathLen(p) { let L = 0; for (let i = 1; i < p.length; i++) L += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]); return L; }
function along(p, d) {
  let acc = 0;
  for (let i = 1; i < p.length; i++) {
    const L = Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
    if (acc + L >= d) { const k = (d - acc) / (L || 1); return { x: lerp(p[i - 1][0], p[i][0], k), z: lerp(p[i - 1][1], p[i][1], k), yaw: Math.atan2(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]) }; }
    acc += L;
  }
  const n = p.length - 1, yaw = n > 0 ? Math.atan2(p[n][0] - p[n - 1][0], p[n][1] - p[n - 1][1]) : 0;
  return { x: p[n][0], z: p[n][1], yaw, end: true };
}

/** Build actors + vehicles for a scene. spec: {cast, vehicles, actionsTimed:[{state,time,word}], t0, t1, seed, era, factions:{a,b}, heading, rampAt} */
export function stageScene(world, spec) {
  const rng = makeRng(`stage:${spec.seed}`), actors = [], t0 = spec.t0, t1 = spec.t1, dur = t1 - t0;
  const heading = spec.heading ?? 0, fx = Math.sin(heading), fz = Math.cos(heading), sx = fz, sz = -fx;
  // vehicles first: people may ride in them
  const vehicles = [];
  for (const v of spec.vehicles || []) vehicles.push(...planVehicles(v.kind, v.count, v.motion, world, { t0: t0 - (v.lead ?? 1.5), t1: t1 + 2, seed: `${spec.seed}:${v.kind}`, anchor: v.anchor || (VEHICLES[v.kind]?.cls === 'water' && world.env === 'beach' ? 'waterline' : 'center'), heading: v.heading ?? heading, rampAt: spec.rampAt }));
  const crafts = vehicles.filter((v) => v.kind === 'landing_craft' && v.rampAt != null);
  let ci = 0, mi = 0;
  for (const group of spec.cast || []) {
    const n = group.count || 1, anchor = world.anchorY(group.anchor || anchorFor(group, world));
    const target = group.moveTo ? world.anchorY(group.moveTo) : null;
    for (let i = 0; i < n; i++) {
      const faction = group.side === 'civ' ? 'civilian' : group.side === 'b' ? (spec.factions?.b || 'germany') : (spec.factions?.a || 'allied');
      const look = makeCharacter({ role: group.role, faction, era: spec.era, name: group.named && i === 0 ? group.name : null, seed: `${spec.seed}:${group.role}:${i}`, mood: group.mood });
      if (group.costume) look.costume = group.costume;
      const a = { id: `${group.role}_${actors.length}`, role: group.role, look, phase: rng(), armed: ARMED_ROLES.has(group.role) && !!look.weapon, schedule: [], path: null, face: null, ride: null, sky: null, group: group.role };
      const col = i % 4, row = Math.floor(i / 4);
      let x = anchor[0], z = anchor[2];
      switch (group.formation) {
        case 'files': x += sx * (col - 1.5) * 3.2 - fx * row * 3.6 - fx * 30; z += sz * (col - 1.5) * 3.2 - fz * row * 3.6 - fz * 30; break;
        case 'line': x += sx * (i - (n - 1) / 2) * 4.5; z += sz * (i - (n - 1) / 2) * 4.5; break;
        case 'front': { const gap = group.facing === 'lead' ? 5.4 : 10; x += fx * gap + sx * (i - (n - 1) / 2) * 4; z += fz * gap + sz * (i - (n - 1) / 2) * 4; if (group.facing === 'lead') a.face = [anchor[0], anchor[2]]; break; }   // face to face at arm's reach
        case 'behind': x -= fx * 9 + sx * 1.5; z -= fz * 9 + sz * 1.5; break;   // keeps pace a few steps behind the lead (horror pursuit)
        case 'head': x = 0; z = -8.5; a.face = [0, 0]; break;
        case 'table': { const ang = (i / Math.max(1, n)) * Math.PI * 1.2 + Math.PI * 0.4; x = Math.cos(ang) * 9; z = Math.sin(ang) * 6 + 1; a.face = [0, 0]; break; }
        case 'table_far': x = (i - (n - 1) / 2) * 5 + 10; z = 7.5; a.face = [0, -6]; break;
        case 'spread': x += rng.range(-150, 150); z += rng.range(-12, 22); break;
        case 'crowd': x += rng.range(-40, 40); z += rng.range(-14, 14); break;
        case 'roadside': { const side = i % 2 ? 1 : -1; x += rng.range(-160, 160); z += side * rng.range(14, 22); a.face = [x, anchor[2]]; break; }
        case 'stack': x += -60 + row * 3.5; z += (col % 2 ? 1 : -1) * 7; break;
        case 'corners': x += rng.pick([-1, 1]) * rng.range(15, 30); z += rng.pick([-1, 1]) * 9; break;
        case 'hidden': x += rng.range(-40, 40); z += rng.range(30, 45); break;
        case 'mark': { const k = mi++, spots = [[0, 0], [5, 2.5], [-5, 2.5], [0, 5.5]], [ox, oz] = spots[k] || [((k % 4) - 1.5) * 4, 6 + Math.floor(k / 4) * 3.5];
          x += ox; z += oz; if (k === 0) { if (spec.face) a.face = [spec.face[0], spec.face[2]]; } else a.face = [anchor[0], anchor[2]]; break; }
        case 'center': break;
        case 'sky': x += rng.range(-90, 90); z += rng.range(-70, 70); break;
        case 'boats': break;
        default: x += rng.range(-45, 45); z += rng.range(-30, 30);
      }
      // avoid putting anyone inside a building or (unless wading) in deep water
      if (world.room) { x = clamp(x, world.room.x0 + 1.5, world.room.x1 - 1.5); z = clamp(z, world.room.z0 + 1.5, world.room.z1 - 1.5); }
      for (let k = 0; k < 6 && blockedAt(world, x, z) && group.formation !== 'boats' && group.formation !== 'sky'; k++) { x += rng.range(-8, 8); z += rng.range(-8, 8); }
      const st = group.action || 'idle';
      if (group.formation === 'boats' && crafts.length) {
        const craft = crafts[ci++ % crafts.length], seat = Math.floor(ci / crafts.length);
        a.ride = { vehicle: craft.id, ox: ((seat % 3) - 1) * 1.8, oz: -2 - Math.floor(seat / 3) * 2.2, until: craft.rampAt + 0.5 + seat * 0.28 };
        const exitAt = a.ride.until;
        const craftEnd = craft.to, tz = target ? target[2] : craftEnd[2] + 60;
        a.path = [[craftEnd[0] + a.ride.ox, craftEnd[2] + 6], [craftEnd[0] + a.ride.ox + rng.range(-10, 10), tz + rng.range(-6, 6)]];
        a.schedule = [{ t0: -1e9, t1: exitAt, state: 'ride' }, { t0: exitAt, t1: exitAt + 0.6, state: 'exit_vehicle', speed: 3 }, { t0: exitAt + 0.6, t1: t1 + 5, state: st === 'wade' ? 'wade' : st }];
      } else if (group.formation === 'sky') {
        const land = t0 + dur * rng.range(0.45, 0.85), drop = t0 - rng.range(0, 3);
        a.sky = { y0: anchor[1] + rng.range(70, 110), land, drop };
        a.schedule = [{ t0: -1e9, t1: land, state: 'parachute' }, { t0: land, t1: land + 0.8, state: 'crouch' }, { t0: land + 0.8, t1: t1 + 5, state: rng.chance(0.5) ? 'look' : 'run', speed: 5 }];
        a.path = [[x, z], [x + rng.range(-20, 20), z + rng.range(-20, 20)]];
      } else {
        const moving = MOVING.has(st) || !!target;
        if (moving) {
          const tx = target ? target[0] + rng.range(-25, 25) : x + fx * (SPEED[st] || 4) * dur, tz = target ? target[2] + rng.range(-8, 8) : z + fz * (SPEED[st] || 4) * dur;
          a.path = [[x, z], [tx, tz]];
        } else a.path = [[x, z]];
        a.schedule = [{ t0: -1e9, t1: t1 + 5, state: MOVING.has(st) || !target ? st : 'run' }];
        if (target && !MOVING.has(st)) { // run to the target, then do the action there (take cover at the shingle, etc.)
          const runT = t0 + rng.range(0, dur * 0.25);
          a.schedule = [{ t0: -1e9, t1: runT, state: st }, { t0: runT, t1: t1 + 5, state: 'run' }];
          a.arrive = st;
        }
        if (st === 'fire' || st === 'cover') a.schedule[0].opts = { rate: rng.range(1.2, 2.6) };
      }
      // a horror story: nobody ends up standing inside a house
      if (group.keepOut) for (const c of world.colliders) if (!c.inside && x > c.x0 - 1 && x < c.x1 + 1 && z > c.z0 - 1 && z < c.z1 + 1) { const out = [[c.x0 - 1.5 - x, 0], [c.x1 + 1.5 - x, 0], [0, c.z0 - 1.5 - z], [0, c.z1 + 1.5 - z]].sort((p, q) => Math.hypot(...p) - Math.hypot(...q))[0]; x += out[0]; z += out[1]; if (a.path) a.path = a.path.map(([px, pz]) => [px + out[0], pz + out[1]]); }
      if (group.formation === 'head' || group.formation === 'table' || group.formation === 'table_far' || group.formation === 'mark') a.path = [[x, z]];
      a.yaw0 = a.face ? Math.atan2(a.face[0] - x, a.face[1] - z) : heading + (group.side === 'b' ? Math.PI : 0) + rng.range(-0.3, 0.3);
      actors.push(a);
    }
  }
  applyNarrationActions(actors, spec.actionsTimed || [], rng, t1, world);
  return { actors, vehicles };
}

const anchorFor = (g, world) => (g.formation === 'roadside' || g.formation === 'files') && world.anchors.road ? 'road' : g.formation === 'stack' && world.anchors.street ? 'street' : g.formation === 'crowd' && world.anchors.crowd ? 'crowd' : 'center';
const blockedAt = (world, x, z) => world.buildings.some((b) => Math.abs(x - b.x) < b.w / 2 + 1.5 && Math.abs(z - b.z) < b.d / 2 + 1.5) || world.heightAt(x, z) < -2.2;

// narration action -> who performs it
const PERFORMERS = { point: ['commander', 'officer', 'leader'], talk: ['forecaster', 'officer', 'politician', 'leader'], listen: ['commander', 'officer'], salute: ['soldier', 'officer'],
  cover: ['soldier', 'paratrooper', 'medic'], wade: ['soldier', 'medic'], run: ['soldier', 'paratrooper', 'civilian', 'crowd'], fire: ['soldier', 'paratrooper'], cheer: ['crowd', 'civilian'],
  wave: ['crowd', 'civilian', 'leader'], hands_up: ['soldier', 'guard'], look: ['soldier', 'paratrooper', 'guard', 'civilian'], carry: ['soldier', 'worker', 'farmer'], gesture: ['leader', 'politician', 'commander'] };
const HOLD = { point: 2.6, salute: 2.8, talk: 4, gesture: 3, listen: 4, look: 3, wave: 3 }; // seconds a one-off action lasts (others last to the end)

function applyNarrationActions(actors, timed, rng, t1, world) {
  for (const act of timed) {
    const roles = PERFORMERS[act.state] || null;
    const free = actors.filter((a) => !a.sky), fits = free.filter((a) => !roles || roles.includes(a.role));
    // an action the CSV asks for is performed by the people the row names, whatever their role
    const who = fits.length || !act.csv ? fits : free;
    if (!who.length) continue;
    const many = !HOLD[act.state]; // group actions (cover, run, cheer...) go to everyone eligible, staggered
    const sel = many ? who : [who[0]];
    sel.forEach((a, k) => {
      const at = act.time + (many ? k * 0.07 + rng.range(0, 0.35) : 0), end = HOLD[act.state] ? at + HOLD[act.state] : t1 + 5;
      if (a.ride && at < a.ride.until) return; // still in the boat
      const seg = { t0: at, t1: end, state: act.state, opts: act.state === 'fire' ? { rate: rng.range(1.2, 2.6) } : undefined, narrated: act.word };
      const before = a.schedule.filter((s) => s.t0 < at).map((s) => ({ ...s, t1: Math.min(s.t1, at) }));
      const after = a.schedule.filter((s) => s.t1 > end).map((s) => ({ ...s, t0: Math.max(s.t0, end) }));
      a.schedule = [...before, seg, ...after];
      if (MOVING.has(act.state) && a.path.length === 1) {
        const [px, pz] = a.path[0];
        if (world?.room) a.path = [[clamp(px + rng.range(-4, 4), world.room.x0 + 1.5, world.room.x1 - 1.5), clamp(pz + 9, world.room.z0 + 1.5, world.room.z1 - 1.5)], [px, pz]]; // walks up to the mark, inside the walls
        else a.path = [a.path[0], [px + rng.range(-10, 10), pz + 30]];
      }
    });
  }
}

/** Position, facing and pose of an actor at film time t. vehicleIndex: id -> vehicle plan (for riders). */
export function evaluateActor(a, t, world, vehicleIndex = null) {
  const def = { armed: a.armed };
  if (a.ride && t < a.ride.until && vehicleIndex) {
    const v = vehicleIndex.get(a.ride.vehicle);
    if (v) {
      const vs = vehicleState(v, t, world), c = Math.cos(vs.yaw), s = Math.sin(vs.yaw);
      const x = vs.x + a.ride.ox * c + a.ride.oz * s, z = vs.z - a.ride.ox * s + a.ride.oz * c;
      return { x, y: vs.y + 0.9, z, yaw: vs.yaw, pose: poseAt([{ t0: -1e9, t1: 1e9, state: 'idle' }], t, a.phase, def), riding: true };
    }
  }
  if (a.sky && t < a.sky.land) {
    const u = clamp((t - a.sky.drop) / (a.sky.land - a.sky.drop), 0, 1), [x, z] = a.path[0];
    const g = world.heightAt(x, z);
    return { x, y: lerp(a.sky.y0, g, smooth(u) * 0.3 + u * 0.7), z, yaw: a.yaw0 + Math.sin(t * 0.4 + a.phase * 6) * 0.3, pose: poseAt(a.schedule, t, a.phase, def), airborne: true };
  }
  // distance along the path: only moving states advance; time before the path starts (riders, sky) does not count
  const startT = a.ride ? a.ride.until : a.sky ? a.sky.land : -1e9;
  const sched = a.schedule.map((s) => ({ ...s, t0: Math.max(s.t0, startT), speed: s.speed ?? (MOVING.has(s.state) ? SPEED[s.state] : 0) })).filter((s) => s.t1 > s.t0);
  const d = travelAt(sched, t), L = pathLen(a.path);
  const p = a.path.length > 1 ? along(a.path, Math.min(d, L)) : { x: a.path[0][0], z: a.path[0][1], yaw: a.yaw0, end: true };
  let schedule = a.schedule;
  const cur = a.schedule.find((s) => t >= s.t0 && t < s.t1);
  if (cur && MOVING.has(cur.state) && (d >= L || a.path.length < 2)) {
    // arrived: stop and do the arrival action (or look around) instead of running on the spot
    const arriveT = arrivalTime(sched, L);
    schedule = [{ t0: -1e9, t1: arriveT, state: cur.state }, { t0: arriveT, t1: 1e9, state: a.arrive || (a.armed ? 'cover' : 'look') }];
  }
  const ground = world.heightAt(p.x, p.z);
  let y = ground, wading = false;
  if (world.water && ground < world.water.level) { const depth = world.water.level - ground; wading = true; y = depth > 3.2 ? world.water.level - 3.2 : ground; }
  let yaw = p.end || !(cur && MOVING.has(cur.state)) ? (a.face ? Math.atan2(a.face[0] - p.x, a.face[1] - p.z) : (a.path.length > 1 ? p.yaw : a.yaw0)) : p.yaw;
  let pose = poseAt(schedule, t, a.phase, def);
  if (wading && cur && (cur.state === 'run' || cur.state === 'walk')) pose = poseAt([{ t0: -1e9, t1: 1e9, state: 'wade' }], t, a.phase, def);
  return { x: p.x, y, z: p.z, yaw, pose, wading };
}

function arrivalTime(sched, L) {
  let d = 0;
  for (const s of sched) { const v = s.speed || 0; if (v > 0 && d + v * (s.t1 - s.t0) >= L) return s.t0 + (L - d) / v; d += v * (s.t1 - s.t0); }
  return 1e9;
}
