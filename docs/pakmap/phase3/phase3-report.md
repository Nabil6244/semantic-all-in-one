# Phase 3 report: data layers

Code: `pakmap-engine/` (tests: `cd pakmap-engine && npm test`, 82 pass). Preview: `data-layers-preview.mp4` (960x540); side by side with the reference: `reference-vs-ours.jpg`. Demo spec: `pakmap-engine/samples/data-layers-kenya.json`.

## What exists now
| Layer | Event type | Data | Notes |
|---|---|---|---|
| Rainfall-style colour overlay | `value_overlay` | bundled `rainfall_chirps` (CHIRPS 2016-2020 mean, 0.1 degree) or the author's own GeoTIFF / ESRI ASCII grid / `lon,lat,value` CSV | Clipped to a country (`clip_iso`), colour ramp (`rainfall`: dry orange to wet blue; `heat`, `density`, `diverging`, or custom stops), no legend, fades in and out. Pairs with a normal `stat` chip for the "UP TO 2,000 MM" counter. |
| Dot density | `dots` with `data` | bundled `populated_places` (Natural Earth, public domain) or the author's own `lat,lon` CSV | Bundled dots are generated around real towns in proportion to population (`per_million`); see the honesty note below. |
| Same-size comparison | `ghost_shape` | any country in the bundled boundaries | A country's outline moved to another place at its **true size** (kilometres, not degrees), translucent blue by default. |
| Streaks | `streak` | none | Decorative curved white streaks inside a region, drawing in one after another ("something you can't see"). |

Everything an author may want to quote in a chip is reported in the render's `plan` event and the sidecar (`layer_facts`): the area of a ghost shape (Poland: 312,219 km2 against the official 312,696), the data range under an overlay (Kenya rainfall: 151 to 2,393 mm per year), dot counts.

## Data rules (decided in the plan, section 2b)
- **Bundled** data is small and offline (1.6 MB in `pakmap-engine/data/`), rebuilt by `tools/build_datasets.py`. **User files win** simply by being named (`"data": "file:my_grid.tif"`).
- **Missing data is an error, never a silent drop**, and it says what to supply. Examples that are tested: no data given; unknown dataset; the dataset does not cover the region ("covers only 0% of the region. It covers land between 50 N and 50 S. Supply your own grid with data: \"file:...\""); file not found; GeoTIFF in another projection ("uses EPSG:3857; pakMap needs plain longitude/latitude (EPSG:4326)"); unknown country code; no area given for dots or streaks.
- **Credits travel with the render**: the sidecar lists each dataset's attribution, and "supplied by the author" for user files.

## Checked
| Check | Result |
|---|---|
| Bundled rainfall sanity | Lodwar (dry north-west) under 450 mm; Kakamega (western highlands) over 1,300 mm; Amazon over 1,800 mm; no data north of 50 N |
| Rainfall overlay in a real render | Dry area renders warm, wet area renders green-blue, ocean and Ethiopia untouched (clipped to Kenya); fades in, gone after its window |
| Ghost shape true scale | Poland moved onto the equator measures about 312,700 km2 on screen (within 12 %); a plain degree shift from 52 N to the equator would change its area by more than 20 %, and a test proves it |
| Polygon rules | Holes and multi-part countries handled; overseas islets dropped from a country's main landmass (Norway no longer reaches Bouvet Island) |
| Files | GeoTIFF (EPSG:4326) loads, ASCII grid and CSV grid load, other projections are refused |
| Dots | Deterministic; all inside the country; more around Nairobi than Lodwar |
| Streaks | Drawn inside the region |
| Existing tests | The 63 earlier tests still pass |

## Bug found and fixed on the way
The coverage check sampled a country's bounding box, which for Norway reaches Bouvet Island in the south Atlantic and wrongly reported 43 % coverage for a country that has no data at all. It now samples only points inside the country's main landmass.

## Honest limits
- **Bundled dots are an approximation.** They are generated around real towns, so they cluster around towns and thin out between them; the reference's dot map looks like a real population surface, with a much denser rural scatter. For exact distributions the author should supply a point file or a population grid (GHSL / WorldPop are CC BY 4.0; the plan's licence note still needs a primary-source check). A later improvement could bundle a coarse population grid and sample from it.
- **Rainfall is a 5-year mean** at 0.1 degree (about 11 km), so it shows regional patterns, not valleys.
- **Coverage:** rainfall covers land between 50 N and 50 S only.
- The same-size comparison keeps *size*, not exact *shape* away from the source latitude (a country's outline is slightly distorted by Mercator at high latitude differences); fine for Poland to Kenya, noticeable for very large moves.
- Not in this phase: PiP cards, filmstrip, stickers, full-screen dissolves (Phase 4); narration anchoring and name-to-coordinate resolution (Phase 5); the globe zoom-out defect is still open.

## Licences
Rainfall: CHIRPS, public domain (cite Funk et al. 2015). Places: Natural Earth, public domain. Country outlines for ghost shapes and clipping come from the countries file `map_scene/data/countries.json.gz` already in the repo (its original source and licence are not recorded here; confirm before distribution).
