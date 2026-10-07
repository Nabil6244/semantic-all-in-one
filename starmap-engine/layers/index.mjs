// The built-in layer types. A new layer type is a module with { type, space, create, update?, draw? } added here (or
// registered by a content pack); the renderer itself never changes for it.
import body_labels from './body_labels.mjs';
import marker from './marker.mjs';
import region from './region.mjs';
import orbit from './orbit.mjs';
import trajectory from './trajectory.mjs';
import spacecraft from './spacecraft.mjs';
import atmosphere from './atmosphere.mjs';
import title from './title.mjs';
import stat_chip from './stat_chip.mjs';
import mission_clock from './mission_clock.mjs';
import distance from './distance.mjs';
import photo_card from './photo_card.mjs';
import caption from './caption.mjs';

export const BUILTIN_LAYERS = [body_labels, marker, region, orbit, trajectory, spacecraft, atmosphere,
  title, stat_chip, mission_clock, distance, photo_card, caption];

export function registerBuiltins(registry) {
  for (const L of BUILTIN_LAYERS) registry.register(L);
  return registry;
}
