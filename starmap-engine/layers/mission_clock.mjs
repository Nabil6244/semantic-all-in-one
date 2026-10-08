// MISSION_CLOCK: the universe clock on screen (top right): mission elapsed time over the date, or just the date.
//   { "type": "mission_clock", "show": "met+utc" | "met" | "utc" }
// A video may hold several missions: each clock layer can carry its own T-zero, a prefix and how precisely its date is known,
//   { "type": "mission_clock", "show": "met+utc", "met_zero": "2027-09-15T12:00:00Z", "prefix": "PLANNED", "date_precision": "month" }
// Before the T-zero it counts down (T- 12:04:00). Without met_zero it uses the spec clock's (an older spec's single mission).
// "motions": [{ start, end, t0, t1, from_utc, to_utc }]: inside [start, end) the clock shows the narration-paced craft's date
// (the planets hold still through a years-long cruise; the clock must not read launch day while the craft arrives).
import { motionWhen } from '../lib/timing.mjs';

const MONTHS = 'JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split(' ');

/** Mission elapsed time, in the unit a viewer can read for how long the mission has run: hh:mm:ss for the first ten days
 *  (a launch, a Moon landing), whole days up to two years (a Mars cruise), then years and days (Voyager). Display only. */
export function metText(dateMs, zeroMs) {
  const d = Math.round((dateMs - zeroMs) / 1000), s = Math.abs(d), sign = `T${d < 0 ? '−' : '+'} `;
  const days = Math.floor(s / 86400);
  if (days < 10) return `${sign}${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  if (days < 2 * 365.25) return `${sign}${days} DAYS`;
  const years = Math.floor(days / 365.25), rest = Math.floor(days - years * 365.25);
  return `${sign}${years} YEAR${years === 1 ? '' : 'S'}${rest ? ` ${rest} DAY${rest === 1 ? '' : 'S'}` : ''}`;
}

export function dateText(date, precision) {
  if (precision === 'year') return String(date.getUTCFullYear());
  if (precision === 'month') return `${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  if (precision === 'day') return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  return date.toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
}

export default {
  type: 'mission_clock',
  space: 'screen',
  create: (def) => ({ def, zero: def.met_zero ? Date.parse(def.met_zero) : null }),
  draw(inst, f) {
    const d = inst.def, show = d.show || 'met+utc', { u, g, W } = f;
    const m = (d.motions || []).find((x) => f.t >= x.start && f.t < x.end);
    const date = m ? new Date(motionWhen(m, f.t, f.mu)) : f.date;
    let met = null;
    if (show.includes('met')) met = inst.zero != null ? metText(+date, inst.zero) : m ? null : f.clock.met(f.t);
    const when = show.includes('utc') || !met ? dateText(date, d.date_precision) : null;
    let big = met || when, small = met ? when : null;
    if (d.prefix) { if (small) small = `${d.prefix} · ${small}`; else big = `${d.prefix} · ${big}`; }
    g.save(); g.globalAlpha = f.alpha;
    const w = Math.max(u.measure(big, 21), small ? u.measure(small, 13) : 0, 120 * u.S) + 28 * u.S, x = W - 52 * u.S - w, y = 37 * u.S, h = (small ? 58 : 40) * u.S;
    u.shadow(12, 0.45); u.box(x, y, w, h, 10, 'rgba(8,19,32,0.92)'); u.noShadow();
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = u.font(21); g.fillStyle = '#FBE040'; g.fillText(big, x + w / 2, y + 21 * u.S);
    if (small) { g.font = u.font(13); g.fillStyle = '#ffffff'; g.fillText(small, x + w / 2, y + 45 * u.S); }
    g.textAlign = 'left';
    g.restore();
    f.claim(x, y, w, h);
  },
};
