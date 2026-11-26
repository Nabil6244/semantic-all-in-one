// history_toon colours for SVG drawing (same values as look.css). Muted, warm, slightly faded: like printed paper.
export const P = {
  ink: '#2b2620', paper: '#f3ead4', paper2: '#e6d9b8', mute: '#6f6a5c', red: '#c8463a', gold: '#d9a441',
  pen: '#2c4a8c', olive: '#7a7f45', oliveDark: '#5e6236', navy: '#2c3a55', khaki: '#a89a6a',
  // backgrounds
  teal: '#5f8a83', tealLight: '#7ea49b', tealDark: '#3f625d', sea: '#9cc7c0', seaDeep: '#6fa7a3', land: '#e7d6a6',
  sky: '#bcd9df', skyWarm: '#f1c98f', cloud: '#fbf6ea', hill: '#7f9a68', hillFar: '#a7b996', grass: '#8ba25a',
  wood: '#a8774a', woodDark: '#7c5533', woodLight: '#c9975f', wall: '#e6d6b4', wallDark: '#cdb994', floor: '#9b6c42',
  chalk: '#3f5a46', metal: '#8a8f8a', metalDark: '#5c605c',
  skin: '#f6f1e6', skinShade: '#ddd5c4',   // the cast's round white faces
  ink_w: 4.5,
};

/** Lighten (amt > 0) or darken (amt < 0) a #rrggbb colour. */
export function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const f = (c) => Math.round(Math.min(255, Math.max(0, amt >= 0 ? c + (255 - c) * amt : c * (1 + amt))));
  const r = f(n >> 16), g = f((n >> 8) & 255), b = f(n & 255);
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
}
