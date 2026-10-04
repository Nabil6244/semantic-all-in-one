# Phase 0 report

Scope: lock the contract, measure the unknowns, run the imagery look test, check licences. No product code was written. Throwaway measurement and look-test scripts lived in the session scratchpad.

## 1. Deliverables
- `csv-schema.md` - CSV contract draft.
- `pakmap.draft.json` - draft constants (kept out of `composition_styles/` on purpose, because the app's style-preset loader scans that folder).
- This report, with images in `images/`.

## 2. Measurements (full-resolution frames, 1920x1080, 30 fps)

| Item | Result | Evidence |
|---|---|---|
| `PART` chip geometry | **Same as `NUMBER` chip**: height 67 px, x=45, y=37, radius about 10 px, width content-driven (`PART 1` = 208 px, `NUMBER 30` = 335 px) | Reference 2 at 60 s, Reference 1 at 44 s |
| Subtitle chip | x=44, y=112, height 39 px, 9 px under the title chip, cap height 15 px, fill `#111111` | Reference 2 at 60 s |
| Typeface | Visually matches **Montserrat ExtraBold** (geometric, tight caps, distinctive `R`, `W`, `1`). Not identified from pixels | Both references |
| Subtitle reveal | Chip grows first (about 0.27 s), title chip pops in 2-3 frames (about 0.07 s), then text appears **word by word, about 2 frames (0.067 s) per word**; `THE EMPTY HALF` complete in 0.13 s. No cursor seen | Reference 2, 57.0-57.5 s |
| Reference 1 reveal | My measurement was contaminated by map content; the earlier "typewriter with block cursor" claim is **unconfirmed** | Reference 1 at 29.3 s |
| Compare-blue | Chip `#2978D8` (41,120,216). Fills use a translucent version over the satellite | Reference 1 at 44 s |
| Yellow stat number | `#FDE23E` (Reference 2) vs `#FBE040` (Reference 1); treat as one token | Reference 2 at 40 s |
| Panel dark | About `#081320` to `#0E1327` | Both |
| Dot-density reveal | Starts at 3.8 s, grows **roughly linearly over about 3.1 s**; at least 800 visible clusters (true dots more, they merge); dots about 6 px; yellow | Reference 2, 3.6-7.9 s |
| Region-fill fade-in | About 0.3 s (**inferred**, mixed with camera motion) | Reference 2 at 95 s |
| Cold open | **No HUD for the first 57 s** of Reference 2; `PART 1` appears at about 57.2 s | Reference 2 |

Still unknown: the exact typeface file, Reference 1 reveal style, exact dot count, marker pop animation, streak curve timing.

## 3. Imagery look test

> **CORRECTION (found during Phase 1):** the "local" comparison below (`images/cmp_local.jpg`) is **not** a 20 km frame. It was rendered at zoom 10 on 256-px tiles at latitude 3 degrees, which is about **150 m per pixel, a frame about 290 km wide**. At that scale every layer is *downsampled*, so the comparison shows nothing about close-zoom softness, and the "usable at local scale" verdict for Landsat was **not actually tested**. What the numbers do say (from native resolution, no rendering needed): Blue Marble is 1:1 only for frames about 1,170 km wide; Landsat WELD is 1:1 for frames about 73 km wide and is stretched about 2x at 37 km and about 2.9x at 25 km; the 25 km figure is therefore an estimate of where Landsat gets soft, not a measured result. Phase 1 renders a real narrow shot (about 21 km frame) to measure it. The country-scale comparison (`cmp_country.jpg`, about 1,000 km frame) and the ocean comparison are valid.

Same Kenya frame (about 1,000 km wide) rendered from each source and compared with Reference 2; see `images/cmp_country.jpg`, `images/cmp_local.jpg`, `images/cmp_ocean.jpg`.

| Source | Country scale | Local scale (about 20 km frame) | Verdict |
|---|---|---|---|
| NASA Blue Marble (z8) | Smooth, muted, **closest to the reference** | Too soft | Use for global and country scale |
| NASA Blue Marble + Bathymetry (z8) | Same land, plus seafloor detail in the ocean, which the reference has | Too soft | **Use as the base**; ocean needs a teal grade |
| NASA MODIS true colour (z9) | Single-day cloud and swath gaps | Clouds | **Rejected** unless a cloud-free mosaic is built |
| NASA Landsat WELD annual (z12, 30 m) | Slightly flat, black holes offshore | Downsampled in this test (see correction above); no clouds; imagery is from the 1998-2000 era | **Use for region and close zoom; softness below about 70 km frames still to be measured in Phase 1** |
| EOX Sentinel-2 cloudless (z13, 10 m) | Too saturated and orange, needs desaturating | **Sharpest** | Visually best, but **licence not cleared** (below) |

Conclusion: a NASA-only stack (Blue Marble + Bathymetry, then Landsat WELD for close zooms) works for country-scale framing, which is where Reference 2 lives. Region and close framing depend on Landsat, whose real softness is measured in Phase 1. The colour grade (darker mids, contrast, slight desaturation, teal lift in the ocean) is required; one test grade is in `images/cmp_ocean.jpg`.

## 4. Licence check

Primary pages were read where noted; others come from web-search summaries and still need a primary-source confirmation before shipping.

| Source | Finding | Confidence |
|---|---|---|
| NASA GIBS | Open sharing. Required acknowledgement: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS)." Commercial use is not explicitly addressed on the page I read; confirm with earthdata-support@nasa.gov | Primary page; commercial wording unconfirmed |
| EOX Sentinel-2 cloudless | **Conflicting.** The current EOX site says: non-commercial = CC BY-NC-SA 4.0; commercial = a separate "EOX Commercial Attribution-RestrictedUse" licence. A 2017 EOX post says the 2016 data is CC BY-SA 4.0. **My earlier statement that the 2016 edition is CC BY 4.0 was wrong/unverified.** Do not ship until EOX confirms (cloudless@eox.at) | Primary pages, conflicting |
| GEBCO grid | Public domain, commercial use allowed, attribution "GEBCO Compilation Group (2024) GEBCO 2024 Grid (doi:...)"; not for navigation | Primary page |
| Natural Earth | Public domain, no attribution needed | Primary page |
| geoBoundaries | CC BY 4.0; credit "geoBoundaries" with a link | Primary page |
| WorldPop | CC BY 4.0 (official licence page returned 404) | Search summary |
| GHSL | CC BY 4.0 | Search summary |
| CHIRPS | Public domain | Search summary |
| CHELSA | CC BY 4.0 (v1.2 confirmed; check the version we would use) | Search summary |
| GADM | Avoid (restrictive terms; not rechecked this pass) | From memory |

## 5. Changes this forces on the plan and spec
1. Imagery stack becomes **NASA-first**: Blue Marble + Bathymetry, then Landsat WELD for close zoom. Sentinel-2 cloudless is optional and gated on an EOX licence answer.
2. The "typewriter with block cursor" requirement is downgraded to "fast word-by-word reveal (Reference 2 measured), cursor unconfirmed".
3. HUD is optional and can start late (already in the spec, now with the measured cold-open length).
4. Constants are now in `pakmap.draft.json`; the CSV contract is in `csv-schema.md`.

## 6. Decisions needed from you
1. **Imagery route.** (a) NASA-only for v1 (recommended: no licence risk, matches the reference at country scale, slightly soft when zoomed in). (b) Email EOX for a commercial licence and add Sentinel-2 for sharper close-ups. (c) Both: ship (a), upgrade later.
2. **Landsat WELD age.** It is year-2000 imagery. Is that acceptable for close-up shots? Roads and cities will look old.

## 7. Phase 0 exit check
- Schema and constants: written, awaiting your review.
- Measurements: done except the items listed as unknown.
- Imagery look test: done; recommendation above.
- Licence check: done, with the EOX conflict and the primary-source confirmations still open.
- Fixtures (short clips cut from both references): not created yet; the test frames are in the scratchpad only. Say if you want them saved into the repo.
