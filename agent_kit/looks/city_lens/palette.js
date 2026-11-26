// city_lens colours: a dark night-map ground, a warm paper ground, one glowing orange for "the thing we talk about",
// red for bad (congestion, parking, decline), green for good (parks, fixes), blue for water.
export const P = {
  night: '#1e2431', night2: '#262d3c', grid: '#323a4b', line: '#4a5366',   // dark map ground and its faint lines
  paper: '#ecebe6', paper2: '#e2e0d9', card: '#f8f7f3', ink: '#1c1d20', mute: '#8a8a86', rule: '#c9c7c0',
  sat: '#2b2d2c',                                                              // under a satellite picture before it loads
  orange: '#f2a33a', glow: '#ffb547', gold: '#e8c14a', yellow: '#f3d34a',
  red: '#d9352e', green: '#3fbf4a', blue: '#2f7fd8', water: '#3a6ea8', ochre: '#9a7440', teal: '#2f8f86',
  block: '#cfd2d6', blockTop: '#eef0f2', chip: '#111214',
};
export const shade = (hex, amt) => {
  const n = parseInt(hex.slice(1), 16), f = (c) => Math.max(0, Math.min(255, Math.round(c + 255 * amt)));
  return '#' + [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(f).map((c) => c.toString(16).padStart(2, '0')).join('');
};
