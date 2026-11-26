// doodle_dark EXAMPLE places: how a place looks in this style (minimal flat shapes, muted colours, lit like a film).
// They are style references, NOT sets to reuse: draw each scene new from what its sentence says.
// Each returns { sky, back, mid, front, light, hero: { y, scale, light } } as SVG strings in 1920x1080.
import { rand } from '/agent_kit/lib/kit.js';
import { R, lin, shaft, glow, dust, treeline } from './light.js';
export { defs, dayTag } from './light.js';

const INK = '#0b0f18';

// ---------------------------------------------------------------- places
const PLACES = {};

// FARM — exterior at dusk: hazy low sun, tree line, barn, silo, farmhouse, fence, dirt path
PLACES.farm = (t) => {
  const sky = `<defs>${lin('fsky', [[0, '#2b3550'], [0.55, '#6b6a7e'], [0.8, '#b48a78'], [1, '#c9967a']])}</defs>` +
    R(0, 0, 1920, 1080, 'url(#fsky)') + glow(1380, 640, 260, '#ffd9a8', 0.55) + `<circle cx="1380" cy="640" r="46" fill="#ffe6c2" opacity=".9"/>`;
  const back = treeline(700, '#3d4459', 11, 110, 60) + treeline(735, '#323849', 23, 70, 40);
  const ground = `<defs>${lin('fgr', [[0, '#3c4a3c'], [1, '#1d241f']])}</defs>` + R(0, 730, 1920, 350, 'url(#fgr)') +
    `<path d="M900 1080 Q980 860 1010 740 L1050 740 Q1100 860 1240 1080 Z" fill="#4b4740" opacity=".8"/>`;
  // barn
  const barn = `<g transform="translate(1180 470)">` +
    `<path d="M0 120 L150 0 L300 120 L300 300 L0 300 Z" fill="#6e3b38" stroke="${INK}" stroke-width="6" stroke-linejoin="round"/>` +
    `<path d="M-12 128 L150 -10 L312 128" fill="none" stroke="#4d2a28" stroke-width="16" stroke-linecap="round"/>` +
    R(95, 170, 110, 130, '#5a302e', `stroke="${INK}" stroke-width="5"`) + `<path d="M95 170 L205 300 M205 170 L95 300" stroke="#d9c7b0" stroke-width="6"/>` +
    R(122, 66, 56, 50, '#5a302e', `stroke="#d9c7b0" stroke-width="5"`) + `</g>`;
  const silo = `<g transform="translate(1540 400)">` + `<path d="M0 60 Q55 0 110 60 L110 370 L0 370 Z" fill="#7c8390" stroke="${INK}" stroke-width="6"/>` +
    [100, 170, 240, 310].map((y) => `<path d="M0 ${y} L110 ${y}" stroke="#5d636e" stroke-width="4"/>`).join('') + `</g>`;
  const house = `<g transform="translate(140 430)">` +
    `<path d="M0 130 L160 20 L320 130 L320 330 L0 330 Z" fill="#5d6272" stroke="${INK}" stroke-width="6" stroke-linejoin="round"/>` +
    `<path d="M-16 140 L160 8 L336 140" fill="none" stroke="#3b3f4c" stroke-width="18" stroke-linecap="round"/>` +
    R(220, -10, 34, 70, '#3b3f4c', `stroke="${INK}" stroke-width="5"`) +
    R(46, 170, 70, 70, '#ffcf86', `stroke="${INK}" stroke-width="5"`) + R(200, 170, 70, 70, '#2b3040', `stroke="${INK}" stroke-width="5"`) +
    R(130, 230, 60, 100, '#3b3f4c', `stroke="${INK}" stroke-width="5"`) + `<path d="M81 170 v70 M46 205 h70" stroke="${INK}" stroke-width="4"/>` +
    `</g>` + glow(221, 635, 90, '#ffbf6a', 0.35 + 0.04 * Math.sin(t * 3.1));
  let fence = '';
  for (let x = -20; x < 1960; x += 120) fence += R(x, 790, 16, 80, '#4a4136', `stroke="${INK}" stroke-width="4"`);
  fence += R(-20, 805, 1980, 12, '#5a4f42', `stroke="${INK}" stroke-width="4"`) + R(-20, 840, 1980, 12, '#5a4f42', `stroke="${INK}" stroke-width="4"`);
  const haze = `<defs>${lin('fhz', [[0, '#e8b48e', 0], [0.6, '#e8b48e', 0.18], [1, '#e8b48e', 0]])}</defs>` + R(0, 560, 1920, 260, 'url(#fhz)');
  return { sky, back: back + haze, mid: ground + house + barn + silo + fence, front: '', light: '',
           hero: { y: 1000, scale: 0.62, light: 'dusk' }, floor: 1000 };
};

// BEDROOM — night: dark wall, moonlit window, shaft across the floor with dust, bed, wardrobe, nightstand
PLACES.bedroom = (t) => {
  const wall = `<defs>${lin('bwall', [[0, '#1e2638'], [1, '#141a28']])}${lin('bfl', [[0, '#1a2030'], [1, '#0e121c']])}</defs>` +
    R(0, 0, 1920, 820, 'url(#bwall)') + R(0, 820, 1920, 260, 'url(#bfl)') + `<path d="M0 820 L1920 820" stroke="#0b0f18" stroke-width="8"/>`;
  const win = `<g transform="translate(1240 170)"><clipPath id="bwin"><rect width="360" height="300"/></clipPath><g clip-path="url(#bwin)">` + R(0, 0, 360, 300, '#0f1a30') +
    glow(250, 80, 60, '#dfe6ff', 0.5) + `<circle cx="250" cy="80" r="24" fill="#eef1fb"/>` +
    [[40, 50], [120, 30], [70, 140], [300, 180], [180, 110], [320, 40]].map(([x, y], i) =>
      `<circle cx="${x}" cy="${y}" r="2.4" fill="#dfe6ff" opacity="${0.4 + 0.5 * (0.5 + 0.5 * Math.sin(t * 2 + i))}"/>`).join('') +
    treeline(250, '#0a1120', 4, 50, 30).replace('M-60 1100', 'M0 300').replace('L1980 1100', 'L360 300') + '</g>' +
    `<path d="M0 0 H360 V300 H0 Z M180 0 V300 M0 150 H360" fill="none" stroke="#2a3348" stroke-width="16"/>` +
    R(-20, 296, 400, 22, '#2a3348', `stroke="${INK}" stroke-width="5"`) + `</g>`;
  const curtain = `<path d="M1200 150 Q1225 330 1205 500 L1255 500 Q1240 330 1252 150 Z" fill="#2c3550"/>` +
                  `<path d="M1590 150 Q1610 330 1598 500 L1645 500 Q1640 330 1640 150 Z" fill="#2c3550"/>`;
  const wardrobe = `<g transform="translate(150 300)">` + R(0, 0, 260, 520, '#262e40', `stroke="${INK}" stroke-width="6"`) +
    `<path d="M130 0 V520" stroke="${INK}" stroke-width="5"/>` + R(108, 240, 8, 50, '#4a5268') + R(144, 240, 8, 50, '#4a5268') + `</g>` +
    `<path d="M480 260 Q520 300 500 420 L540 420 Q520 300 560 262 Z" fill="#2a3245" opacity=".9"/>`; // coat on a hook
  const bed = `<g transform="translate(620 640)">` + R(0, 40, 560, 120, '#2e3852', `stroke="${INK}" stroke-width="6" rx="14"`) +
    R(-20, -40, 40, 220, '#2a2f3d', `stroke="${INK}" stroke-width="6" rx="8"`) + R(20, 20, 150, 50, '#c9cbd6', `stroke="${INK}" stroke-width="5" rx="20"`) +
    `<path d="M160 40 Q370 10 560 40 L560 120 L160 120 Z" fill="#46557a" stroke="${INK}" stroke-width="5"/>` + `</g>`;
  const stand = `<g transform="translate(1250 700)">` + R(0, 0, 130, 120, '#262e40', `stroke="${INK}" stroke-width="6"`) +
    R(30, -50, 70, 46, '#3b4256', `stroke="${INK}" stroke-width="5" rx="6"`) + `<path d="M96 -40 l20 -30" stroke="${INK}" stroke-width="4"/>` + `</g>`;
  // moonlight shaft from the window down across the floor
  const poly = [[1250, 190], [1600, 190], [1880, 1080], [980, 1080]];
  const light = shaft('bsh', poly, '#bcc9ee', 0.2, 0.015 * Math.sin(t * 0.9)) +
    `<polygon points="1060,880 1700,880 1830,1080 960,1080" fill="#9fb0dc" opacity=".10" filter="url(#blur40)" style="mix-blend-mode:screen"/>` +
    dust(t, poly, { n: 70, seed: 9, color: '#dfe6ff', id: 'bdust' });
  return { sky: wall + win + curtain, back: wardrobe, mid: bed + stand, front: '', light,
           hero: { y: 960, scale: 0.72, light: 'moon' }, floor: 960 };
};

// PANTRY — storage room: shelves of jars and sacks, labelled crates, one hanging bulb, a high window shaft
PLACES.pantry = (t) => {
  const r = rand(31);
  const wall = `<defs>${lin('pwall', [[0, '#2a2d33'], [1, '#1d1f25']])}</defs>` + R(0, 0, 1920, 860, 'url(#pwall)') + R(0, 860, 1920, 220, '#15171c') +
    `<path d="M0 860 L1920 860" stroke="#0b0f18" stroke-width="8"/>`;
  let shelves = '';
  [210, 380, 550].forEach((y, row) => {
    shelves += R(260, y, 1160, 16, '#4a4036', `stroke="${INK}" stroke-width="5"`);
    for (let x = 290; x < 1390; x += 58 + Math.floor(r() * 20)) {
      const h = 60 + r() * 50, w = 40 + r() * 16, c = ['#6b5a44', '#7d6a4a', '#5b6a5c', '#8a5a44', '#6d6f78'][Math.floor(r() * 5)];
      shelves += row === 2 && r() > 0.5
        ? `<path d="M${x} ${y} q-6 ${-h} ${w / 2} ${-h - 10} q${w / 2 + 6} 10 ${w / 2} ${h + 10} z" fill="#a89878" stroke="${INK}" stroke-width="4"/>`
        : R(x, y - h, w, h, c, `stroke="${INK}" stroke-width="4" rx="6"`) + R(x + 4, y - h - 8, w - 8, 10, '#3b3f48', `stroke="${INK}" stroke-width="3"`);
    }
  });
  const crate = (x, label) => `<g transform="translate(${x} 700)">` + R(0, 0, 170, 160, '#5c4a36', `stroke="${INK}" stroke-width="6"`) +
    `<path d="M0 54 H170 M0 108 H170" stroke="#4a3a2a" stroke-width="5"/>` + R(30, 50, 110, 40, '#d8cdb6', `stroke="${INK}" stroke-width="4" rx="4"`) +
    `<text x="85" y="78" text-anchor="middle" font-family="Helvetica Neue, Arial" font-weight="800" font-size="20" letter-spacing="2" fill="#2a2d33">${label}</text></g>`;
  const crates = crate(300, 'WATER') + crate(500, 'RICE') + crate(1260, 'BEANS');
  const sway = Math.sin(t * 0.8) * 3;
  const bulb = `<g transform="rotate(${sway} 860 0)"><path d="M860 0 V150" stroke="${INK}" stroke-width="4"/>` +
    `<path d="M830 150 h60 l-10 22 h-40 z" fill="#3b3f48" stroke="${INK}" stroke-width="4"/>` +
    `<circle cx="860" cy="186" r="20" fill="#ffe2a6"/>` + glow(860, 186, 60, '#ffd27a', 0.8) + `</g>`;
  const cone = [[860 + sway * 3, 190], [520 + sway * 8, 1080], [1200 + sway * 8, 1080]];
  const flick = 0.02 * Math.sin(t * 17) * Math.sin(t * 3.3);
  const win = R(1560, 120, 220, 110, '#3a4a66', `stroke="${INK}" stroke-width="6"`) + `<path d="M1670 120 V230" stroke="${INK}" stroke-width="5"/>`;
  const wpoly = [[1560, 230], [1780, 230], [1700, 1080], [1300, 1080]];
  const light = shaft('pbulb', cone, '#ffd9a0', 0.24, flick) + shaft('pwin', wpoly, '#b9c6e6', 0.12) +
    dust(t, cone, { n: 55, seed: 3, color: '#ffe7bf', id: 'pdust' }) + dust(t, wpoly, { n: 30, seed: 8, color: '#dfe6ff', id: 'pdust2' });
  return { sky: wall + win, back: shelves, mid: crates, front: '', light,
           hero: { y: 1000, scale: 0.78, light: 'warm' }, floor: 1000 };
};

export const PLACE_NAMES = Object.keys(PLACES);

export function place(name, t, opts = {}) {
  return (PLACES[name] || PLACES.bedroom)(t, opts);
}
