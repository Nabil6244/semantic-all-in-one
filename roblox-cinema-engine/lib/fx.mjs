// Effects as deterministic emitters. A particle's whole life is a function of (emitter seed, particle index, time), so a
// frame can be rendered alone and the same frame always looks the same. The director creates emitters from events (an
// explosion has a time, a place and a sound cue); effects never appear on their own.

import { h01, hash, clamp } from './rng.mjs';

export const EFFECTS = ['smoke', 'smoke_light', 'fire', 'fire_small', 'dust', 'explosions', 'splashes', 'tracers_in', 'flak', 'rain', 'rain_light', 'snow', 'clouds',
  'clouds_storm', 'haze', 'fog', 'confetti', 'chimney_smoke', 'birds', 'dust_motes', 'contrails', 'naval_guns', 'waves_high', 'debris', 'muzzle'];

// per-type particle look: life (s), rise (studs/s), spread, size growth, colour, max live particles (budget)
export const PARTICLE = {
  smoke: { life: 9, rise: 2.2, spread: 1.6, size0: 2.5, size1: 9, color: [0.32, 0.31, 0.3], alpha: 0.55, budget: 90 },
  smoke_light: { life: 8, rise: 1.6, spread: 1.2, size0: 1.6, size1: 6, color: [0.5, 0.49, 0.47], alpha: 0.4, budget: 50 },
  fire: { life: 1.3, rise: 4, spread: 0.8, size0: 1.6, size1: 0.3, color: [1, 0.55, 0.15], alpha: 0.95, budget: 50, glow: true },
  dust: { life: 2.6, rise: 0.6, spread: 2.2, size0: 1, size1: 4.5, color: [0.62, 0.55, 0.42], alpha: 0.45, budget: 60 },
  explosion: { life: 1.4, rise: 6, spread: 9, size0: 1.6, size1: 4, color: [1, 0.6, 0.2], alpha: 1, budget: 40, glow: true },
  debris: { life: 1.8, rise: 12, spread: 7, size0: 0.8, size1: 0.6, color: [0.25, 0.22, 0.2], alpha: 1, budget: 40, gravity: 22 },
  splash: { life: 1.2, rise: 9, spread: 2, size0: 0.9, size1: 0.4, color: [0.9, 0.95, 1], alpha: 0.85, budget: 40, gravity: 18 },
  tracer: { life: 0.35, rise: 0, spread: 0, size0: 0.25, size1: 0.25, color: [1, 0.85, 0.4], alpha: 1, budget: 30, glow: true },
  flak: { life: 1.6, rise: 0.4, spread: 1.5, size0: 3, size1: 6, color: [0.2, 0.2, 0.2], alpha: 0.7, budget: 30 },
  rain: { life: 0.9, rise: -60, spread: 0, size0: 0.08, size1: 0.08, color: [0.75, 0.8, 0.9], alpha: 0.35, budget: 900, streak: 2.2 },
  snow: { life: 7, rise: -3, spread: 0.6, size0: 0.25, size1: 0.25, color: [1, 1, 1], alpha: 0.9, budget: 600 },
  confetti: { life: 6, rise: -2.5, spread: 1.2, size0: 0.35, size1: 0.35, color: [1, 1, 1], alpha: 1, budget: 300, colors: [[0.95, 0.3, 0.3], [0.3, 0.5, 0.95], [1, 1, 1], [0.95, 0.85, 0.3]] },
  muzzle: { life: 0.06, rise: 0, spread: 0, size0: 0.9, size1: 0.2, color: [1, 0.8, 0.4], alpha: 1, budget: 20, glow: true },
  dust_motes: { life: 12, rise: 0.08, spread: 0.15, size0: 0.08, size1: 0.08, color: [1, 0.95, 0.8], alpha: 0.6, budget: 120 },
  bird: { life: 30, rise: 0, spread: 0, size0: 0.6, size1: 0.6, color: [0.12, 0.12, 0.12], alpha: 1, budget: 24 },
};

/** emitter: {type, x,y,z, t0, t1, rate, area:[rx,rz], seed, dir:[x,y,z] (tracers), burst: true} */
export function particlesAt(em, t) {
  const P = PARTICLE[em.type]; if (!P) return [];
  const s = hash(em.seed ?? `${em.type}:${em.x}:${em.z}:${em.t0}`) | 0, out = [];
  const rate = em.rate || 6, life = P.life * (em.lifeScale || 1);
  const first = em.burst ? 0 : Math.max(0, Math.floor((t - life - em.t0) * rate)), last = em.burst ? (em.count || 24) - 1 : Math.floor((Math.min(t, em.t1) - em.t0) * rate);
  for (let i = first; i <= last && out.length < (em.budget || P.budget); i++) {
    const birth = em.burst ? em.t0 + h01(s, i, 9) * 0.12 : em.t0 + i / rate, age = t - birth;
    if (age < 0 || age > life) continue;
    const k = age / life, r1 = h01(s, i, 1), r2 = h01(s, i, 2), r3 = h01(s, i, 3);
    const [rx, rz] = em.area || [0.5, 0.5];
    let x = em.x + (r1 - 0.5) * 2 * rx, z = em.z + (r2 - 0.5) * 2 * rz, y = em.y;
    if (em.type === 'tracer') {
      const d = em.dir || [0, 0, 1], L = em.len || 120; const f = clamp(age / life, 0, 1);
      x = em.x + d[0] * L * f + (r1 - 0.5) * 18; y = em.y + d[1] * L * f + r3 * 3; z = em.z + d[2] * L * f + (r2 - 0.5) * 6;
    } else {
      const ang = r3 * Math.PI * 2, out_ = (P.spread * (em.spreadScale || 1)) * (em.type === 'explosion' || em.type === 'debris' ? (0.4 + r2) : age);
      x += Math.cos(ang) * out_ * (em.type === 'explosion' || em.type === 'debris' || em.type === 'splash' ? k * 2 : 1);
      z += Math.sin(ang) * out_ * (em.type === 'explosion' || em.type === 'debris' || em.type === 'splash' ? k * 2 : 1);
      y += P.rise * age * (0.6 + r1 * 0.8) - 0.5 * (P.gravity || 0) * age * age;
      if (em.wind) { x += em.wind[0] * age ** 1.3; z += em.wind[1] * age ** 1.3; }
      if (P.gravity && y < em.y - 0.5) continue;
    }
    const size = (P.size0 + (P.size1 - P.size0) * Math.sqrt(k)) * (0.7 + r2 * 0.6) * (em.sizeScale || 1);
    const fade = em.type === 'smoke' || em.type === 'smoke_light' || em.type === 'dust' || em.type === 'flak' ? Math.sin(Math.PI * Math.min(1, k * 1.1)) : 1 - k * k;
    const col = P.colors ? P.colors[i % P.colors.length] : P.color;
    out.push({ x, y, z, size, alpha: P.alpha * fade * (em.alpha ?? 1), color: col, spin: r1 * 6 + age * (r2 - 0.5) * 2, glow: !!P.glow, streak: P.streak || 0, k });
  }
  return out;
}

/** Live particle count of a set of emitters at time t (the budget test keeps every frame under the cap). */
export const liveCount = (emitters, t) => emitters.reduce((n, e) => n + particlesAt(e, t).length, 0);
