# Place boundary highlighting (Hybrid Map / pakMap, "Add graphics from the narration")

When the narration discusses a place, its real boundary is outlined on the map while the narrator talks about it. It is a `fill` event of the map engine
(translucent cyan, outlined, faded in and out) with the place's actual polygon, tagged `geo_focus` and `official_warning: false`. It is geographic focus
only: official warning areas are a separate layer with their own colours and are never produced by this feature.

Modules: `place_focus.py` (detection, resolution, timing, events), `boundary_source.py` (OpenStreetMap lookups and the cache). The only change to shared
code is a short hook in `pakmap/compile.py` (the auto-graphics block).

## What gets outlined
| Place | Boundary from |
|---|---|
| Countries | the map engine's own country outlines |
| States / provinces | `map_scene/data/admin1.json.gz` |
| US counties (only when the narration says "County" / "Parish") | `map_scene/data/us_counties.json.gz` |
| Cities | OpenStreetMap, looked up once while planning, validated, cached |

Never a point, circle or box: a city whose outline cannot be confirmed gets no highlight, and the plan report says why.

## When a place counts as discussed
A location or motion cue just before the name ("approaching Houston", "landfall in Florida", "flooding across Miami-Dade County"), or the place as the
subject of the sentence. Not highlighted: possessives ("Canada's east coast"), parts of a place ("the Texas coast", "northern Florida", "the Houston area"),
descriptions ("a port in Halifax"), passing mentions. The name must resolve to exactly one place; the script's other places (a state, a country) are the
evidence ("Portland" with Maine in the script). A bare name with several candidates and no evidence is skipped. A city that nothing else supports is
accepted only when it has a million people or more and no other city of 10,000 or more shares its name.

Timing: the outline starts at the word (0.3 s early) and ends 0.8 s after the sentence; a place discussed again in the next sentence keeps one outline;
a new place replaces the previous one; the same place is not outlined again within 45 s; nothing is outlined while full-screen footage hides the map.
The camera is not moved: a small place only shows if the camera frames it.

## OpenStreetMap data (cities)
Data © OpenStreetMap contributors, licensed under the Open Database Licence (ODbL) 1.0: https://www.openstreetmap.org/copyright
Credit line used: `Place boundaries: © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)`. A plan that uses an OSM outline
shows it as a `credit:` note in the plan report; add it to the video description or end card.

Nominatim usage policy (https://operations.osmfoundation.org/policies/nominatim/): requests are made only while planning, never while rendering; one
request per second at most; an identifying User-Agent (`SemanticYTStudio/<version> (place-boundary-highlighting; ...)`); at most 8 new places per plan; a
good answer is cached for a year and a rejected one for 30 days, in `<map cache>/boundaries/` (`~/Library/Caches/SemanticYTStudio/maps/boundaries` on
macOS); after a network failure no further request is made for 10 minutes. `VIDEOGEN_BOUNDARY_NETWORK=0` turns lookups off (cached outlines still work).

An answer is accepted only if it is a relation or way with a Polygon/MultiPolygon, of an administrative or place type, named as the city, in the right
country, smaller than 400 km across, and containing (or within 5 km of) the position the app's own city list gives. Two different valid answers are not
guessed between.
