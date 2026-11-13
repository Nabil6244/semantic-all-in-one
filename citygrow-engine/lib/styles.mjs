// How houses look in each period. Walls and roofs are picked per house from these lists (by the house's own hash), so
// a district has variety but the same house keeps its colours. Heights in metres; `flat` = share of flat roofs.
export const STYLES = {
  ancient:      { walls: [0xe9e0cc, 0xdcd0b6, 0xefe8d8, 0xd6c3a0], roofs: [0xb6583c, 0xa84f36, 0xc0653f, 0x9c4a33], h: [3.5, 6], roofH: 0.32, flat: 0.25, road: 0xc9b48e, dense: true },
  medieval:     { walls: [0xd9c7a4, 0xcbb38b, 0xe2d4b6, 0xbfa27a, 0xa98c66], roofs: [0xa6503a, 0x94463a, 0xb35d3f, 0x7f4a3a], h: [5, 9], roofH: 0.4, flat: 0.05, road: 0xbfae8c, dense: true },
  ottoman:      { walls: [0xe6dcc8, 0xd8c4a2, 0xc9a77f, 0xb98d66, 0xe9e3d6], roofs: [0xb05a3c, 0xa24f38, 0xbd6a46], h: [6, 10], roofH: 0.33, flat: 0.03, road: 0xc4b392, dense: true },
  nordic:       { walls: [0xc9a46b, 0xb5523b, 0xe0c27a, 0xd9cbb0, 0x9e3b2c], roofs: [0x7b3b2f, 0x5c5552, 0x8a4535, 0x4f4a48], h: [6, 11], roofH: 0.5, flat: 0.02, road: 0xb8ac94, dense: true },
  early_modern: { walls: [0xe4d8c0, 0xd5c2a0, 0xc8b391, 0xece4d2, 0xb89f80], roofs: [0x9c4a36, 0x7d6a60, 0xa65a40, 0x5e5a58], h: [8, 13], roofH: 0.38, flat: 0.06, road: 0xb7ad9a, dense: true },
  industrial:   { walls: [0xa9654a, 0x9c5a44, 0xc8b8a0, 0xb47458, 0xd6ccbb], roofs: [0x5d5853, 0x6b625b, 0x7c4a3c, 0x4e4c4b], h: [10, 18], roofH: 0.3, flat: 0.25, road: 0x8f8b85 },
  south_asian:  { walls: [0xd9c29b, 0xc8a37a, 0xe6dac2, 0xb6825c, 0xeee6d6, 0xa9714f], roofs: [0xcdb48e, 0xb99470, 0xd8cbb0], h: [3.5, 7], roofH: 0.2, flat: 0.93, road: 0xc8b48f, dense: true, pph: 7 },
  south_asian_modern: { walls: [0xe9e4da, 0xd6cbb8, 0xc9b79c, 0xf1ece2, 0xbfae95, 0xd9c7a8], roofs: [0xb9b2a5, 0xa59d8f], h: [6, 16], roofH: 0.15, flat: 0.97, road: 0x7d7a74, pph: 9 },
  modern:       { walls: [0xd9d7d1, 0xc4c2bd, 0xe8e6e0, 0xb2b4b6, 0xd8cdb8], roofs: [0x8b8986, 0x6f6e6c, 0x9c9894, 0xa65a40], h: [14, 34], roofH: 0.18, flat: 0.8, road: 0x6f6d6a },
};
// dense: old towns, packed blocks (infill lots stand, narrow lanes are not drawn as streets)
// pph: people one lot stands for in this style (low-rise family houses), instead of the period's default (growth.peoplePerLot)
export const styleOf = (name) => STYLES[name] || STYLES.medieval;
