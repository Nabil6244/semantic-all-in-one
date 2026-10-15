// The weather layers a render can draw: an event its own checks refuse is left out with a warning, never a reason to stop the
// video (one bad graphic used to stop a whole render). Used by render.mjs and tools/validate_weather.mjs (the dry run), so both
// leave out exactly the same events.
import { validateWxEvents } from './wx_draw.mjs';
import { validateRasters } from './wx_raster.mjs';

/** {events, rasters, dropped: [message]}: the layers that pass every check. */
export function sanitizeWeather(weather, duration, plugins) {
  const dropped = [];
  let events = [...((weather && weather.events) || [])];
  // each event alone (its own rules), then the rules between events (a duplicate id, two forecast strips at once)
  events = events.filter((e) => {
    const errs = validateWxEvents([e], duration, plugins);
    if (errs.length) dropped.push(`weather graphic ${e.id || e.type || '?'} left out: ${errs.join('; ')}`);
    return !errs.length;
  });
  const seen = new Set();
  events = events.filter((e) => {
    if (seen.has(e.id)) { dropped.push(`weather graphic ${e.id} left out: its id is used twice`); return false; }
    seen.add(e.id); return true;
  });
  for (let guard = 0; guard < 50; guard++) {
    const errs = validateWxEvents(events, duration, plugins);
    if (!errs.length) break;
    const m = errs[0].match(/overlap \(([^,]+), ([^)]+)\)/);
    const id = m ? m[2] : null;
    if (!id) { dropped.push(...errs.map((x) => `weather layers: ${x} (left out)`)); events = []; break; }
    dropped.push(`weather graphic ${id} left out: ${errs[0]}`);
    events = events.filter((e) => e.id !== id);
  }
  const rasters = ((weather && weather.rasters) || []).filter((r) => {
    const errs = validateRasters([r], duration);
    if (errs.length) dropped.push(`weather picture ${r.id || '?'} left out: ${errs.join('; ')}`);
    return !errs.length;
  });
  return { events, rasters, dropped };
}
