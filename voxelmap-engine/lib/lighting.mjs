// Light presets per beat (CSV extra.light): day, dawn, sunset, night, fog. A preset sets the terrain shader's ambient and
// sun colours, the haze colour and thickness, the sky and the scene lights; changes blend over LIGHT_BLEND seconds.
// Pure: the page applies lightAt(lights, t).

export const LIGHT_BLEND = 1.6;
export const PRESETS = {
  day:    { amb: [1, 1, 1],          sun: [1, 1, 1],          sunK: 1,    fog: [0.74, 0.81, 0.87], sky: [0.33, 0.52, 0.78], haze: 1,   hemi: 1.9, dir: 1.8 },
  dawn:   { amb: [0.82, 0.8, 0.88],  sun: [1, 0.84, 0.72],    sunK: 0.8,  fog: [0.8, 0.77, 0.8],   sky: [0.42, 0.5, 0.72],  haze: 1.4, hemi: 1.5, dir: 1.4 },
  sunset: { amb: [0.86, 0.72, 0.66], sun: [1, 0.7, 0.44],     sunK: 1.05, fog: [0.86, 0.66, 0.52], sky: [0.32, 0.36, 0.6],  haze: 1.3, hemi: 1.3, dir: 1.9 },
  night:  { amb: [0.3, 0.36, 0.54],  sun: [0.55, 0.62, 0.86], sunK: 0.32, fog: [0.07, 0.09, 0.15], sky: [0.03, 0.05, 0.1],  haze: 1.2, hemi: 0.5, dir: 0.4 },
  fog:    { amb: [0.95, 0.97, 1],    sun: [0.95, 0.95, 0.95], sunK: 0.42, fog: [0.78, 0.8, 0.82],  sky: [0.7, 0.73, 0.76],  haze: 2.4, hemi: 1.6, dir: 0.8 },
};

const mix = (a, b, k) => (Array.isArray(a) ? a.map((v, i) => v + (b[i] - v) * k) : a + (b - a) * k);
const smooth = (k) => { k = Math.max(0, Math.min(1, k)); return k * k * (3 - 2 * k); };

/** The light at time t from the timeline's lights list [{t, preset}] (sorted). Unknown presets fall back to day. */
export function lightAt(lights, t) {
  const list = lights && lights.length ? lights : [{ t: 0, preset: 'day' }];
  let i = 0;
  while (i + 1 < list.length && list[i + 1].t <= t) i++;
  const cur = PRESETS[list[i].preset] || PRESETS.day, prev = i > 0 ? PRESETS[list[i - 1].preset] || PRESETS.day : cur;
  const k = i > 0 ? smooth((t - list[i].t) / LIGHT_BLEND) : 1;
  const out = {};
  for (const key of Object.keys(cur)) out[key] = mix(prev[key], cur[key], k);
  return out;
}
