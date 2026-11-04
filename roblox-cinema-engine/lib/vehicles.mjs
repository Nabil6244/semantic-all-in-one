// Vehicles and equipment: what each kind is (size, class, parts look) and how it moves. Motion is a pure function of time
// on the set (vehicleState), so tanks sit on the ground, ships on the water and aircraft above the clearance on every frame.

import { makeRng, clamp, smooth, lerp } from './rng.mjs';

// class: ground | water | air ; len/wid/hgt in studs ; sound: the audio cue it carries
export const VEHICLES = {
  tank: { cls: 'ground', len: 15, wid: 8, hgt: 6.5, speed: 7, sound: 'tank_engine', color: '#5f6448', dust: true },
  tank_ww1: { cls: 'ground', len: 16, wid: 8, hgt: 5.5, speed: 3, sound: 'tank_engine', color: '#6b6248', dust: true },
  halftrack: { cls: 'ground', len: 13, wid: 5.5, hgt: 5, speed: 9, sound: 'truck_engine', color: '#5f6448', dust: true, seats: 8 },
  apc: { cls: 'ground', len: 13, wid: 6, hgt: 5, speed: 10, sound: 'truck_engine', color: '#56603f', dust: true, seats: 8 },
  jeep: { cls: 'ground', len: 7.5, wid: 4.2, hgt: 3.6, speed: 14, sound: 'jeep_engine', color: '#5a6140', dust: true, seats: 3 },
  humvee: { cls: 'ground', len: 9, wid: 5, hgt: 4.4, speed: 14, sound: 'truck_engine', color: '#b59f74', dust: true, seats: 3 },
  truck: { cls: 'ground', len: 13, wid: 5.2, hgt: 6.2, speed: 11, sound: 'truck_engine', color: '#565c3e', dust: true, seats: 10 },
  truck_old: { cls: 'ground', len: 11, wid: 5, hgt: 5.5, speed: 8, sound: 'truck_engine', color: '#5b5440', dust: true, seats: 8 },
  car_old: { cls: 'ground', len: 9, wid: 4.2, hgt: 3.8, speed: 12, sound: 'car_engine', color: '#2c2f36', dust: false },
  car: { cls: 'ground', len: 9, wid: 4.4, hgt: 3.6, speed: 14, sound: 'car_engine', color: '#3a5068', dust: false },
  motorbike: { cls: 'ground', len: 5, wid: 1.6, hgt: 3, speed: 15, sound: 'jeep_engine', color: '#3d4030', dust: true },
  bicycle: { cls: 'ground', len: 4.5, wid: 1, hgt: 2.6, speed: 5, sound: null, color: '#2a2a2a', dust: false },
  artillery: { cls: 'ground', len: 10, wid: 5, hgt: 4, speed: 0, sound: 'artillery', color: '#55593f', dust: false },
  radar: { cls: 'ground', len: 6, wid: 6, hgt: 9, speed: 0, sound: null, color: '#6a6f62', dust: false },
  cart: { cls: 'ground', len: 7, wid: 3.5, hgt: 3, speed: 3, sound: null, color: '#7a5a3a', dust: true },
  train: { cls: 'ground', len: 28, wid: 6, hgt: 9, speed: 10, sound: 'truck_engine', color: '#2b2b2b', dust: false },
  landing_craft: { cls: 'water', len: 18, wid: 7, hgt: 5, speed: 8, sound: 'boat_engine', color: '#6d7a76', seats: 30, wake: true },
  patrol_boat: { cls: 'water', len: 16, wid: 5, hgt: 5, speed: 14, sound: 'boat_engine', color: '#5f6c66', wake: true },
  sampan: { cls: 'water', len: 9, wid: 2.6, hgt: 2, speed: 3, sound: null, color: '#6b4a2e', wake: true },
  ship: { cls: 'water', len: 70, wid: 10, hgt: 20, speed: 6, sound: 'ship_horn', color: '#7a8288', wake: true },
  battleship: { cls: 'water', len: 110, wid: 16, hgt: 28, speed: 5, sound: 'ship_horn', color: '#747c82', wake: true },
  steam_ship: { cls: 'water', len: 60, wid: 10, hgt: 18, speed: 5, sound: 'ship_horn', color: '#4a4440', wake: true },
  sailing_ship: { cls: 'water', len: 50, wid: 12, hgt: 40, speed: 4, sound: null, color: '#6b4a30', wake: true },
  galley: { cls: 'water', len: 40, wid: 8, hgt: 10, speed: 4, sound: null, color: '#7a5a3a', wake: true },
  submarine: { cls: 'water', len: 50, wid: 6, hgt: 8, speed: 5, sound: 'boat_engine', color: '#3f4448', wake: true },
  transport_plane: { cls: 'air', len: 30, wid: 46, hgt: 8, speed: 55, sound: 'prop_plane', color: '#7f8a62', props: 2 },
  bomber: { cls: 'air', len: 36, wid: 56, hgt: 9, speed: 60, sound: 'prop_plane', color: '#6b7060', props: 4 },
  fighter_prop: { cls: 'air', len: 16, wid: 20, hgt: 5, speed: 85, sound: 'prop_plane', color: '#6a7058', props: 1 },
  biplane: { cls: 'air', len: 14, wid: 18, hgt: 6, speed: 45, sound: 'prop_plane', color: '#8a7a5a', props: 1 },
  jet: { cls: 'air', len: 22, wid: 15, hgt: 6, speed: 140, sound: 'jet', color: '#6f767a' },
  helicopter: { cls: 'air', len: 20, wid: 6, hgt: 7, speed: 35, sound: 'helicopter', color: '#545c40', rotor: true },
  drone: { cls: 'air', len: 10, wid: 16, hgt: 3, speed: 50, sound: 'jet', color: '#8a8f92' },
  horse: { cls: 'ground', len: 6, wid: 2, hgt: 5.5, speed: 8, sound: null, color: '#5a3b22', dust: true },
};

export const MOTIONS = ['advance', 'convoy', 'flyover', 'circle', 'land', 'takeoff', 'park', 'drift', 'approach_beach', 'patrol', 'cross'];

const ang = (dx, dz) => Math.atan2(dx, dz);

/** Lay out n vehicles of a kind with a motion on a set. Returns plain data the page and the tests share. */
export function planVehicles(kind, n, motion, world, { t0 = 0, t1 = 10, seed = 0, anchor = 'center', heading = null, rampAt = null } = {}) {
  const spec = VEHICLES[kind]; if (!spec) return [];
  const rng = makeRng(`veh:${kind}:${seed}`), a = world.anchorY(anchor), out = [];
  const mot = motion || (spec.cls === 'air' ? 'flyover' : spec.cls === 'water' ? 'drift' : spec.speed ? 'advance' : 'park');
  const dir = heading ?? (world.env === 'beach' && spec.cls === 'water' ? 0 : rng.range(0, Math.PI * 2)); // 0 = toward +z (inland from the sea)
  const fx = Math.sin(dir), fz = Math.cos(dir), sx = fz, sz = -fx;
  for (let i = 0; i < n; i++) {
    const row = Math.floor(i / 4), col = (i % 4) - 1.5, jitter = () => rng.range(-0.3, 0.3);
    const v = { kind, motion: mot, id: `${kind}_${seed}_${i}`, i, t0, t1, speed: spec.speed * (0.92 + rng() * 0.16), phase: rng(), cls: spec.cls };
    if (spec.cls === 'air') {
      const alt = (kind === 'helicopter' ? 28 : 70) + row * 6 + rng.range(-4, 4);
      const lateral = col * (spec.wid * 1.6) + jitter() * 10, behind = row * spec.len * 2.2 + rng.range(0, 8);
      const L = Math.max(260, v.speed * (t1 - t0) * 0.5);
      v.from = [a[0] - fx * (L + behind) + sx * lateral, a[1] + alt, a[2] - fz * (L + behind) + sz * lateral];
      v.to = [a[0] + fx * (L - behind) + sx * lateral, a[1] + alt, a[2] + fz * (L - behind) + sz * lateral];
      if (mot === 'land') { v.from = [a[0] - fx * 140 + sx * lateral, a[1] + 60, a[2] - fz * 140 + sz * lateral]; v.to = [a[0] + sx * lateral, a[1], a[2] + sz * lateral]; }
      if (mot === 'takeoff') { v.from = [a[0] - fx * 200, a[1], a[2] - fz * 200 + col * 30]; v.to = [a[0] + fx * 300, a[1] + 80, a[2] + fz * 300 + col * 30]; }
      if (mot === 'circle') { v.center = [a[0], a[1] + alt, a[2]]; v.radius = 120 + i * 18; }
    } else if (spec.cls === 'water') {
      const spread = kind === 'landing_craft' ? 26 : spec.len * 1.4;
      const lateral = (i - (n - 1) / 2) * spread + rng.range(-4, 4);
      const back = kind === 'landing_craft' ? rng.range(0, 30) : row * spec.len * 1.2;
      if (mot === 'approach_beach' && world.shoreZ) {
        const x = a[0] + lateral, zShore = world.shoreZ(x);
        v.from = [x, 0, zShore - 120 - back]; v.to = [x, 0, zShore - 6 - rng.range(0, 6)]; v.rampAt = rampAt ?? t0 + (t1 - t0) * 0.62 + rng.range(-0.4, 0.4);
      } else {
        const off = world.env === 'sea' ? 0 : -140;
        v.from = [a[0] + lateral * (kind === 'landing_craft' ? 1 : 2.2), 0, a[2] + off - back - (mot === 'drift' ? 0 : 60)];
        v.to = [v.from[0] + (mot === 'drift' ? fx * 20 : fx * 140), 0, v.from[2] + (mot === 'drift' ? fz * 20 : fz * 140)];
      }
    } else {
      const spacing = spec.len * 1.8;
      const road = world.roads.find((r) => r.kind !== 'runway' && r.kind !== 'rail');
      if ((mot === 'convoy' || mot === 'advance') && road && mot === 'convoy') {
        v.path = road.points; v.offset = -i * spacing; v.lane = (i % 2 ? 1 : -1) * 0.18 * road.width;
      } else {
        const lateral = col * spec.wid * 2.4, back = row * spacing;
        v.from = [a[0] - fx * (40 + back) + sx * lateral, 0, a[2] - fz * (40 + back) + sz * lateral];
        const travel = mot === 'park' || !spec.speed ? 0 : v.speed * (t1 - t0) * 0.85;
        v.to = [v.from[0] + fx * travel, 0, v.from[2] + fz * travel];
      }
    }
    out.push(v);
  }
  return out;
}

const pathPoint = (pts, d) => {
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const [ax, az] = pts[i - 1], [bx, bz] = pts[i], L = Math.hypot(bx - ax, bz - az);
    if (acc + L >= d || i === pts.length - 1) { const k = clamp((d - acc) / L, 0, 1); return { x: ax + (bx - ax) * k, z: az + (bz - az) * k, yaw: ang(bx - ax, bz - az) }; }
    acc += L;
  }
  return { x: pts[0][0], z: pts[0][1], yaw: 0 };
};

/** Where a vehicle is and how it is posed at film time t. */
export function vehicleState(v, t, world) {
  const spec = VEHICLES[v.kind], u = clamp((t - v.t0) / Math.max(0.01, v.t1 - v.t0), 0, 1), out = { x: 0, y: 0, z: 0, yaw: 0, pitch: 0, roll: 0, wheel: 0, rotor: t * 22, prop: t * 40, ramp: 0, dust: 0, wake: 0, visible: true, moving: false };
  if (spec.cls === 'air') {
    if (v.motion === 'circle') {
      const th = (t - v.t0) * v.speed / v.radius + v.phase * 6.28;
      out.x = v.center[0] + Math.cos(th) * v.radius; out.z = v.center[2] + Math.sin(th) * v.radius; out.y = v.center[1]; out.yaw = -th; out.roll = -0.35;
    } else {
      const k = v.motion === 'land' ? smooth(u) : v.motion === 'takeoff' ? u * u : u;
      out.x = lerp(v.from[0], v.to[0], k); out.y = lerp(v.from[1], v.to[1], v.motion === 'land' ? smooth(u * 1.15) : k); out.z = lerp(v.from[2], v.to[2], k);
      out.yaw = ang(v.to[0] - v.from[0], v.to[2] - v.from[2]);
      out.pitch = v.motion === 'takeoff' ? -0.18 * smooth(u * 3) : v.motion === 'land' ? 0.06 : Math.sin((t + v.phase * 9) * 0.6) * 0.02;
      out.roll = Math.sin((t + v.phase * 7) * 0.45) * 0.06;
      if (v.motion === 'land') out.y = Math.max(out.y, world.heightAt(out.x, out.z) + 0.2);
    }
    const ground = world.heightAt(out.x, out.z);
    if (v.motion !== 'land' && v.motion !== 'takeoff') out.y = Math.max(out.y, ground + 30);
    out.moving = true;
    return out;
  }
  if (spec.cls === 'water') {
    const k = v.motion === 'approach_beach' ? smooth(clamp((t - v.t0) / Math.max(0.01, (v.rampAt ?? v.t1) - v.t0), 0, 1)) : u;
    out.x = lerp(v.from[0], v.to[0], k); out.z = lerp(v.from[2], v.to[2], k);
    out.yaw = ang(v.to[0] - v.from[0], v.to[2] - v.from[2]);
    const bobA = spec.len > 40 ? 0.15 : 0.5;
    out.y = (world.water ? world.water.level : 0) + Math.sin((t + v.phase * 5) * 1.3) * bobA * 0.4;
    out.pitch = Math.sin((t + v.phase * 3) * 1.1) * (spec.len > 40 ? 0.004 : 0.03); out.roll = Math.sin((t + v.phase * 4) * 0.9) * (spec.len > 40 ? 0.006 : 0.04);
    if (v.rampAt != null) out.ramp = smooth((t - v.rampAt) / 1.2);
    out.wake = v.motion === 'approach_beach' ? (t < (v.rampAt ?? 1e9) ? 1 : 0.15) : 0.6;
    out.moving = out.wake > 0.3;
    return out;
  }
  if (v.path) {
    const d = Math.max(0, (t - v.t0) * v.speed + v.offset + 60), p = pathPoint(v.path, d);
    out.x = p.x + Math.cos(p.yaw) * v.lane; out.z = p.z - Math.sin(p.yaw) * v.lane; out.yaw = p.yaw;
    out.moving = d > 0;
  } else {
    out.x = lerp(v.from[0], v.to[0], u); out.z = lerp(v.from[2], v.to[2], u);
    const dx = v.to[0] - v.from[0], dz = v.to[2] - v.from[2];
    out.yaw = dx || dz ? ang(dx, dz) : (v.phase * 6.28);
    out.moving = (dx || dz) && u > 0 && u < 1;
  }
  // sit on the terrain: height under the centre, pitch/roll from the slope under the hull
  const L = spec.len / 2, Wd = spec.wid / 2, fx = Math.sin(out.yaw), fz = Math.cos(out.yaw);
  const hF = world.heightAt(out.x + fx * L, out.z + fz * L), hB = world.heightAt(out.x - fx * L, out.z - fz * L);
  const hR = world.heightAt(out.x + fz * Wd, out.z - fx * Wd), hL = world.heightAt(out.x - fz * Wd, out.z + fx * Wd);
  out.y = Math.max((hF + hB + hR + hL) / 4, world.heightAt(out.x, out.z));
  if (world.water && out.y < world.water.level - 1.5) out.y = world.water.level - 1.5; // wading vehicles sink no deeper
  out.pitch = -Math.atan2(hF - hB, spec.len); out.roll = Math.atan2(hR - hL, spec.wid);
  if (out.moving) { out.y += Math.sin((t + v.phase) * 9) * 0.05; out.wheel = (t - v.t0) * v.speed / 1.2; out.dust = spec.dust ? 1 : 0; }
  return out;
}
