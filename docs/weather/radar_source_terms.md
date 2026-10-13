# Radar source — licensing, attribution and redistribution

Status: documentation for approval (2026-10-13). IEM is **proposed** as the default radar provider; it is not yet selected. Whatever is chosen, the provider stays a setting (see §4).

Pages read on 2026-10-13 (copies of the page text are in the session scratchpad, not the repo):
- IEM disclaimer — `https://mesonet.agron.iastate.edu/disclaimer.php`
- IEM OGC / Tile Map Service — `https://mesonet.agron.iastate.edu/ogc/`
- IEM NEXRAD mosaic documentation — `https://mesonet.agron.iastate.edu/docs/nexrad_mosaic/`
- IEM GIS RADAR information — `https://mesonet.agron.iastate.edu/GIS/ridge.phtml`
- NWS disclaimer — `https://www.weather.gov/disclaimer`
- NCEI NEXRAD product page — `https://www.ncei.noaa.gov/products/radar/next-generation-weather-radar`

## 1. The specific IEM products
| Use | Product | Access | Coverage |
|---|---|---|---|
| Live radar | NEXRAD base-reflectivity mosaic, `ridge::USCOMP-N0Q-0` / `nexrad-n0q-900913` | TMS tiles, `/cache/tile.py/1.0.0/...` (5-minute cache header) | latest scan |
| Past-event radar | the same mosaic, archived: `ridge::USCOMP-N0Q-YYYYMMDDHHMI` | TMS tiles, `/c/tile.py/1.0.0/...` (14-day cache header) | every 5 minutes since 13 Nov 2010 (N0Q, 0.5 dBZ); N0R (5 dBZ) since 1 Jan 1995 |
| Past-event radar, whole CONUS | `archive/data/YYYY/MM/DD/GIS/uscomp/n0q_YYYYMMDDHHMI.png` + `.wld` | one 12200×5400 PNG per time step | as above |
| Rain totals (phase 4) | MRMS `q2-p24h/p48h/p72h`, `mrms::a2m-…` | TMS tiles | archive since early 2015 |

The underlying data is NOAA/NWS NEXRAD Level III (and NOAA MRMS), mosaicked and coloured by IEM. IEM's documentation notes that since 2022 the N0Q mosaic is a downscaled N0B, because the NWS stopped sending N0Q.

## 2. What the terms say
**IEM, site-wide (applies to every product above; there's no separate per-product licence):**
- The materials "are in the public domain and may be used freely by anyone for any lawful purpose."
- Attributing the Iowa Environmental Mesonet of Iowa State University "would be appreciated" — requested, not required.
- The data is provided without any warranty of accuracy; errors can occur from equipment failure, and users should use their own judgement.

**IEM, radar services specifically:**
- The services are "provided as-is and without warranty"; their purpose is an archive that supports display applications and GIS plots.
- **Capacity request:** please don't use these services in applications with thousands of simultaneous users.
- The mosaic page warns that errors can and do occur during automated generation, so the images should be used with care.

**Underlying NOAA/NWS data (NWS disclaimer):** public domain unless noted. Conditions: don't claim it as your own; don't imply NOAA/NWS endorsement; don't present modified content as official government material; no NWS/NOAA name or logo used as an identifier without permission.

## 3. What this means for Weather videos
| Question | Answer | Basis |
|---|---|---|
| Show IEM radar in a monetised YouTube video? | Yes | public domain, "any lawful purpose" |
| Redistribute (frames in a published video)? | Yes; no restriction is stated | public domain |
| Attribution required? | Not required, but **we always credit** | IEM requests it; plan §12 |
| Can we call it "official NWS radar"? | **No** — it's a mosaic made by IEM from NWS data, recoloured by us | NWS rule on modified content |
| NWS or NOAA logo on screen? | **No** | NWS disclaimer |
| Bundle IEM images inside the installer? | Not planned; fetched at render time and cached per user | — |
| Load on IEM | each user's app fetches only the tiles its shots need, caches them, and limits parallel requests (proposed: at most 4 at a time, honouring the cache headers) | capacity request |

**On-screen and description credit (proposed):** "Radar: NOAA/NWS NEXRAD via Iowa Environmental Mesonet (Iowa State University)", plus the scan time.

**Residual risks:**
- No uptime promise. Mitigated by the cache, the alternative providers in §4, and a radar beat that stays on the map without radar (and says so) when tiles can't be fetched.
- The terms could change. Each render records the provider and the terms URL in its sidecar, and the terms are re-checked before any release.

## 4. Keeping the provider configurable
A small Weather-owned registry, `weather/radar_providers.py` (phase 3, where the radar loop is built). It follows the same idea as pakMap's `imagery.mjs` provider records but is not shared with pakMap. Each record holds:
`id`, `title`, `url_template` (live), `archive_url_template`, `archive_from`, `max_zoom`, `tile_size`, `legend` (dBZ ramp), `attribution`, `terms_url`, `licence_note`, `max_parallel`.

Initial records:
1. `iem_n0q` — default (pending your approval).
2. `noaa_mapservices` — NOAA `radar_base_reflectivity_time` ImageServer. Federal, but live only (about 2 hours of history), so it can't be used for past events.
3. `none` — no radar layer; radar beats stay on the map with a note.

The provider is chosen per project in the Weather card, with the app-wide default in Weather settings. The renderer only ever sees the resolved record, never a hard-coded URL.

Phase 1 (Forecast MVP) **doesn't use radar**, so this decision only has to be made before phase 3.
