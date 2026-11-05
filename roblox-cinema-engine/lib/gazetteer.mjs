// Built-in places: lon/lat (WGS84, decimal degrees), what kind of place it is, its terrain and its building culture.
// Coordinates are city/landmark centres from public reference data (rounded to 0.01°); a place not listed here is looked up
// in the Natural Earth country table (mapdata.mjs) or given as "lon,lat" in the CSV. `culture` picks building styles,
// `biome` the ground. Beaches of Normandy are the sector centres (approximate: the sectors were kilometres wide).

export const PLACES = [
  // Roman world
  { name: 'Rome', lon: 12.5, lat: 41.9, kind: 'city', biome: 'city', culture: 'european', country: 'Italy' },
  { name: 'Roman Forum', lon: 12.49, lat: 41.89, kind: 'city', biome: 'city', culture: 'european', country: 'Italy' },
  { name: 'Tiber River', lon: 12.4, lat: 41.9, kind: 'river', biome: 'river', culture: 'european', country: 'Italy' },
  { name: 'Italy', lon: 12.6, lat: 42.5, kind: 'region', biome: 'farmland', culture: 'european', country: 'Italy' },
  { name: 'Carthage', lon: 10.32, lat: 36.85, kind: 'port', biome: 'coast', culture: 'middle_east', country: 'Tunisia' },
  { name: 'Sicily', lon: 14.0, lat: 37.6, kind: 'region', biome: 'farmland', culture: 'european', country: 'Italy' },
  { name: 'Cannae', lon: 16.13, lat: 41.3, kind: 'region', biome: 'farmland', culture: 'european', country: 'Italy' },
  { name: 'Zama', lon: 9.4, lat: 36.0, kind: 'region', biome: 'farmland', culture: 'middle_east', country: 'Tunisia' },
  { name: 'Actium', lon: 20.74, lat: 38.95, kind: 'sea', biome: 'sea', culture: 'european', country: 'Greece' },
  { name: 'Corinth', lon: 22.88, lat: 37.91, kind: 'city', biome: 'city', culture: 'european', country: 'Greece' },
  { name: 'Gaul', lon: 2.5, lat: 46.5, kind: 'region', biome: 'farmland', culture: 'european', country: 'France' },
  { name: 'Rubicon River', lon: 12.4, lat: 44.1, kind: 'river', biome: 'river', culture: 'european', country: 'Italy' },
  { name: 'Egypt', lon: 31.2, lat: 27.0, kind: 'region', biome: 'desert', culture: 'middle_east', country: 'Egypt' },
  { name: 'Constantinople', lon: 28.98, lat: 41.01, kind: 'city', biome: 'city', culture: 'middle_east', country: 'Turkey' },
  { name: 'Adrianople', lon: 26.56, lat: 41.68, kind: 'region', biome: 'farmland', culture: 'european', country: 'Turkey' },
  { name: 'Milvian Bridge', lon: 12.47, lat: 41.93, kind: 'river', biome: 'river', culture: 'european', country: 'Italy' },
  { name: 'Alps', lon: 8.0, lat: 46.5, kind: 'region', biome: 'mountains', culture: 'european', country: 'Switzerland' },
  { name: 'Britain', lon: -1.5, lat: 53.0, kind: 'region', biome: 'farmland', culture: 'european', country: 'United Kingdom' },
  { name: 'Mesopotamia', lon: 44.0, lat: 33.0, kind: 'region', biome: 'desert', culture: 'middle_east', country: 'Iraq' },
  { name: 'Mediterranean Sea', lon: 15.0, lat: 35.0, kind: 'sea', biome: 'sea', culture: 'european', country: '' },
  { name: 'Tunisia', lon: 9.5, lat: 34.0, kind: 'region', biome: 'desert', culture: 'middle_east', country: 'Tunisia' },
  { name: 'Spain', lon: -3.7, lat: 40.4, kind: 'region', biome: 'farmland', culture: 'european', country: 'Spain' },
  // India-Pakistan 1971
  { name: 'Lahore', lon: 74.34, lat: 31.55, kind: 'city', biome: 'city', culture: 'south_asian', country: 'Pakistan' },
  { name: 'Karachi', lon: 67.01, lat: 24.86, kind: 'port', biome: 'coast', culture: 'south_asian', country: 'Pakistan' },
  { name: 'Dhaka', lon: 90.41, lat: 23.81, kind: 'city', biome: 'city', culture: 'south_asian', country: 'Bangladesh' },
  { name: 'New Delhi', lon: 77.21, lat: 28.61, kind: 'city', biome: 'city', culture: 'south_asian', country: 'India' },
  { name: 'Amritsar', lon: 74.87, lat: 31.63, kind: 'city', biome: 'city', culture: 'south_asian', country: 'India' },
  { name: 'Eastern front', lon: 89.0, lat: 24.0, kind: 'region', biome: 'farmland', culture: 'south_asian', country: 'India' },
  // Normandy 1944
  { name: 'Normandy', lon: -0.6, lat: 49.2, kind: 'region', biome: 'farmland', culture: 'european', country: 'France' },
  { name: 'Omaha Beach', lon: -0.88, lat: 49.37, kind: 'beach', biome: 'beach', culture: 'european', country: 'France' },
  { name: 'Utah Beach', lon: -1.17, lat: 49.41, kind: 'beach', biome: 'beach', culture: 'european', country: 'France' },
  { name: 'Gold Beach', lon: -0.57, lat: 49.34, kind: 'beach', biome: 'beach', culture: 'european', country: 'France' },
  { name: 'Juno Beach', lon: -0.4, lat: 49.33, kind: 'beach', biome: 'beach', culture: 'european', country: 'France' },
  { name: 'Sword Beach', lon: -0.25, lat: 49.29, kind: 'beach', biome: 'beach', culture: 'european', country: 'France' },
  { name: 'Sainte-Mère-Église', alt: ['Sainte-Mere-Eglise', 'Sainte Mere Eglise'], lon: -1.32, lat: 49.41, kind: 'town', biome: 'farmland', culture: 'european', country: 'France' },
  { name: 'Caen', lon: -0.37, lat: 49.18, kind: 'city', biome: 'farmland', culture: 'european', country: 'France' },
  { name: 'Cherbourg', lon: -1.62, lat: 49.64, kind: 'port', biome: 'coast', culture: 'european', country: 'France' },
  { name: 'Bayeux', lon: -0.7, lat: 49.28, kind: 'town', biome: 'farmland', culture: 'european', country: 'France' },
  { name: 'Portsmouth', lon: -1.09, lat: 50.8, kind: 'port', biome: 'coast', culture: 'european', country: 'United Kingdom' },
  { name: 'Southwick House', lon: -1.11, lat: 50.87, kind: 'building', biome: 'farmland', culture: 'european', country: 'United Kingdom' },
  { name: 'southern England', alt: ['southern england', 'south of England'], lon: -1.5, lat: 51.0, kind: 'region', biome: 'farmland', culture: 'european', country: 'United Kingdom' },
  { name: 'English Channel', alt: ['the Channel'], lon: -1.0, lat: 50.1, kind: 'sea', biome: 'sea', culture: 'european' },
  { name: 'Paris', lon: 2.35, lat: 48.86, kind: 'city', biome: 'city', culture: 'european', country: 'France' },
  { name: 'London', lon: -0.13, lat: 51.51, kind: 'city', biome: 'city', culture: 'european', country: 'United Kingdom' },
  { name: 'Dunkirk', lon: 2.38, lat: 51.03, kind: 'beach', biome: 'beach', culture: 'european', country: 'France' },
  { name: 'Berlin', lon: 13.4, lat: 52.52, kind: 'city', biome: 'city', culture: 'european', country: 'Germany' },
  { name: 'Warsaw', lon: 21.01, lat: 52.23, kind: 'city', biome: 'city', culture: 'european', country: 'Poland' },
  { name: 'Moscow', lon: 37.62, lat: 55.76, kind: 'city', biome: 'city', culture: 'european', country: 'Russia' },
  { name: 'Stalingrad', alt: ['Volgograd'], lon: 44.52, lat: 48.71, kind: 'city', biome: 'city', culture: 'european', country: 'Russia' },
  { name: 'Kyiv', alt: ['Kiev'], lon: 30.52, lat: 50.45, kind: 'city', biome: 'city', culture: 'european', country: 'Ukraine' },
  { name: 'Rome', lon: 12.5, lat: 41.9, kind: 'city', biome: 'city', culture: 'european', country: 'Italy' },
  { name: 'Verdun', lon: 5.38, lat: 49.16, kind: 'town', biome: 'battlefield', culture: 'european', country: 'France' },
  { name: 'the Somme', alt: ['Somme'], lon: 2.7, lat: 50.0, kind: 'region', biome: 'battlefield', culture: 'european', country: 'France' },
  { name: 'Waterloo', lon: 4.4, lat: 50.68, kind: 'town', biome: 'farmland', culture: 'european', country: 'Belgium' },
  { name: 'Gallipoli', lon: 26.4, lat: 40.25, kind: 'beach', biome: 'beach', culture: 'middle_east', country: 'Turkey' },
  { name: 'El Alamein', lon: 28.95, lat: 30.83, kind: 'town', biome: 'desert', culture: 'middle_east', country: 'Egypt' },
  { name: 'Cairo', lon: 31.24, lat: 30.04, kind: 'city', biome: 'desert', culture: 'middle_east', country: 'Egypt' },
  { name: 'Baghdad', lon: 44.37, lat: 33.31, kind: 'city', biome: 'desert', culture: 'middle_east', country: 'Iraq' },
  { name: 'Kuwait City', lon: 47.98, lat: 29.38, kind: 'city', biome: 'desert', culture: 'middle_east', country: 'Kuwait' },
  { name: 'Kabul', lon: 69.17, lat: 34.53, kind: 'city', biome: 'mountains', culture: 'middle_east', country: 'Afghanistan' },
  { name: 'Pearl Harbor', lon: -157.95, lat: 21.35, kind: 'port', biome: 'coast', culture: 'american', country: 'United States' },
  { name: 'Midway', lon: -177.37, lat: 28.21, kind: 'island', biome: 'island', culture: 'american' },
  { name: 'Iwo Jima', lon: 141.32, lat: 24.78, kind: 'island', biome: 'island', culture: 'asian', country: 'Japan' },
  { name: 'Okinawa', lon: 127.8, lat: 26.5, kind: 'island', biome: 'island', culture: 'asian', country: 'Japan' },
  { name: 'Tokyo', lon: 139.69, lat: 35.69, kind: 'city', biome: 'city', culture: 'asian', country: 'Japan' },
  { name: 'Hiroshima', lon: 132.46, lat: 34.39, kind: 'city', biome: 'city', culture: 'asian', country: 'Japan' },
  { name: 'Seoul', lon: 126.98, lat: 37.57, kind: 'city', biome: 'city', culture: 'asian', country: 'South Korea' },
  { name: 'Inchon', alt: ['Incheon'], lon: 126.62, lat: 37.46, kind: 'port', biome: 'coast', culture: 'asian', country: 'South Korea' },
  { name: 'Pyongyang', lon: 125.76, lat: 39.04, kind: 'city', biome: 'city', culture: 'asian', country: 'North Korea' },
  { name: 'Hanoi', lon: 105.85, lat: 21.03, kind: 'city', biome: 'city', culture: 'asian', country: 'Vietnam' },
  { name: 'Saigon', alt: ['Ho Chi Minh City'], lon: 106.7, lat: 10.78, kind: 'city', biome: 'city', culture: 'asian', country: 'Vietnam' },
  { name: 'Hue', alt: ['Huế'], lon: 107.59, lat: 16.46, kind: 'city', biome: 'city', culture: 'asian', country: 'Vietnam' },
  { name: 'Da Nang', alt: ['Danang'], lon: 108.22, lat: 16.05, kind: 'port', biome: 'coast', culture: 'asian', country: 'Vietnam' },
  { name: 'Khe Sanh', lon: 106.73, lat: 16.62, kind: 'base', biome: 'jungle', culture: 'asian', country: 'Vietnam' },
  { name: 'Dien Bien Phu', lon: 103.02, lat: 21.39, kind: 'valley', biome: 'jungle', culture: 'asian', country: 'Vietnam' },
  { name: 'Mekong Delta', alt: ['the Mekong'], lon: 105.8, lat: 10.0, kind: 'river', biome: 'jungle', culture: 'asian', country: 'Vietnam' },
  // Iran and the Gulf
  { name: 'Natanz', lon: 51.72, lat: 33.72, kind: 'base', biome: 'desert', culture: 'middle_east', country: 'Iran' },
  { name: 'Fordow', alt: ['Fordo'], lon: 50.99, lat: 34.88, kind: 'base', biome: 'mountains', culture: 'middle_east', country: 'Iran' },
  { name: 'Isfahan', alt: ['Esfahan'], lon: 51.67, lat: 32.65, kind: 'city', biome: 'city', culture: 'middle_east', country: 'Iran' },
  { name: 'Tehran', alt: ['Teheran'], lon: 51.39, lat: 35.69, kind: 'city', biome: 'city', culture: 'middle_east', country: 'Iran' },
  { name: 'Iran', lon: 53.7, lat: 32.4, kind: 'region', biome: 'desert', culture: 'middle_east', country: 'Iran' },
  { name: 'Tel Aviv', lon: 34.78, lat: 32.08, kind: 'city', biome: 'city', culture: 'middle_east', country: 'Israel' },
  { name: 'Missouri', lon: -92.6, lat: 38.6, kind: 'region', biome: 'farmland', culture: 'american', country: 'United States' },
  { name: 'Washington', lon: -77.04, lat: 38.9, kind: 'city', biome: 'city', culture: 'american', country: 'United States' },
  { name: 'Gettysburg', lon: -77.23, lat: 39.83, kind: 'town', biome: 'farmland', culture: 'american', country: 'United States' },
  { name: 'New York', lon: -74.0, lat: 40.71, kind: 'city', biome: 'city', culture: 'american', country: 'United States' },
];

const norm = (s) => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();

/** Index: normalised name -> place. Extra places (from the CSV's plan row or Natural Earth) may be merged in. */
export function makeGazetteer(extra = []) {
  const idx = new Map();
  for (const p of [...PLACES, ...extra]) for (const n of [p.name, ...(p.alt || [])]) idx.set(norm(n), p);
  const names = [...idx.keys()].sort((a, b) => b.length - a.length);
  return {
    get: (name) => {
      if (!name) return null;
      const m = String(name).match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
      if (m) return { name: String(name), lon: +m[1], lat: +m[2], kind: 'point', biome: '', culture: 'european' };
      return idx.get(norm(name)) || null;
    },
    /** every place named in a text, longest names first, without overlaps; [{place, index}] in reading order */
    find: (text) => {
      let t = ` ${norm(text)} `; const out = [];
      for (const n of names) {
        const k = t.indexOf(` ${n} `);
        if (k >= 0) { out.push({ place: idx.get(n), index: k }); t = t.slice(0, k + 1) + '#'.repeat(n.length) + t.slice(k + 1 + n.length); }
      }
      return out.sort((a, b) => a.index - b.index);
    },
  };
}
