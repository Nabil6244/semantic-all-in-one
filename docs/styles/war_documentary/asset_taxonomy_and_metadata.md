# War Documentary style — asset taxonomy and metadata schema

Status: design only. No code, no assets, nothing downloaded. Labels: **[repo]** = read in this checkout; **[proposal]** = our design; **[assumption]** = outside fact I believe but have not verified, check before relying on it.

Scope: Russia–Ukraine war analysis. Every factual visual in a video is one *asset* (a file or a data record) used by one or more *claims* (what the visual asserts, e.g. "this footage shows a Pantsir-S1 near Moscow"). Provenance is kept per asset; claims are kept per use (see the policy file).

## 1. What the repo gives us and where it stops [repo]

| Existing mechanism | What it carries | Limit for this style |
|---|---|---|
| `.asset_manifest.json` in the project `Images/` folder (`asset_manager.AssetManifest`) | one dict per **scene number**; `record.update(result.metadata)` copies provider extras such as `provider_asset_id`, `author`, `source_url`; Openverse adds `license`, `license_version` | per scene, not per asset; `AssetManifest.set()` replaces the whole record, so any key not re-copied is lost; no dates, no verification, no flags; stock providers (Pexels, Pixabay) store no licence field |
| `.stock_used_assets.json` (`providers/stock/cache.py`) | set of used `provider_asset_id`s for the repeat penalty | ids only, no meaning beyond "already used" |
| `boundary_source.py` per-user cache (`map_scene` cache dir `/boundaries`) | content-keyed JSON (`sha1` of name+region+country+lon/lat), `licence`, `attribution`, `fetched`, TTL for good (365 d) and rejected (30 d) answers | the model to copy for a **canonical entity cache**; it is for city polygons only |
| `weather/provenance.py` (`Sourced`, `NumbersReport`) | value, unit, product, url, where, issued, fetched, plus a per-video report of every number | the model for **statistic provenance**; Weather is protected, so copy the pattern, never import |
| `downloaded_assets.py` | `PIPELINE_SOURCES` vs `PROTECTED_SOURCES = {local, manual}`; "Clear downloaded assets" deletes pipeline files and spares protected ones | a verified war asset in the scene folder as a *pipeline* source can be deleted by cleanup; see policy §8 |
| `cache_manager.py` | project temp, preview and generated-asset cache sizes and clearing | clears the project, not a per-user registry |
| `gfx-core/templates/index.json` (79 templates) + layer slots | template id + slots (label, sub, text, values, geo...) | **no provenance slot**; a card cannot say where its number came from |
| `learning/` (`ledger.py` sqlite, `assets.py` vocabulary) | `KNOWN_SOURCES` incl. `archive_video`, `commons_image`, `youtube_video`, `research`, `map` | a source vocabulary only; do not add war fields to the ledger |

**Consequence:** the existing manifest can *point* to an asset but cannot *describe* it. All descriptive fields live in a separate registry (policy §7), referenced by one id.

## 2. Core metadata schema (every asset) [proposal]

JSON-schema style. `req` = required before an asset can be planned; `claim` = required only when the asset backs a factual claim.

| Field | Type | req | Meaning |
|---|---|---|---|
| `asset_id` | string | yes | canonical id, `<class>:<slug>` e.g. `equip:pantsir-s1`, `person:valery-gerasimov`, `geo:ua-oblast-kharkiv`, `footage:<sha1[:12]>` |
| `class` | enum | yes | one of the categories in §3 (`geography`, `equipment`, `person`, `institution`, `footage`, `satellite`, `archival`, `facility`, `statistic`, `territory`, `graphic_furniture`, ...) |
| `title` | string | yes | human label shown in the plan report |
| `files` | array | if file | `{path, sha256, bytes, mime, width, height, duration_s}`; sha256 is an integrity check, not part of the cache key |
| `source.url` | string | yes | the page or file the asset came from (normalised: scheme+host+path, no tracking query) |
| `source.publisher` | string | yes | outlet, agency, ministry, uploader |
| `source.kind` | enum | yes | `primary_official`, `primary_open_data`, `wire_agency`, `news_outlet`, `osint`, `social_post`, `stock_library`, `commons`, `government_archive`, `own_production`, `ai_generated` |
| `dates.event` | `{value, precision}` | claim | when the thing happened (`day`, `month`, `year`, `range`, `unknown`) |
| `dates.captured` | `{value, precision, basis}` | footage/images | when the footage or image was recorded; `basis` = `metadata`, `source_statement`, `geolocation_analysis`, `inferred` |
| `dates.published` | `{value}` | yes | first publication by the source we can show |
| `dates.fetched` | ISO time | yes | when we retrieved it |
| `licence.spdx` | string | yes | `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `PD-USGov`, `ODbL-1.0`, `LICENSED-PAID`, `USER-SUPPLIED`, `UNKNOWN` |
| `licence.url` | string | if known | licence text or terms page |
| `licence.attribution` | string | if required | the exact credit line to show |
| `licence.reuse` | enum | yes | `free`, `attribution_required`, `share_alike`, `editorial_only`, `terms_check`, `none`; `UNKNOWN` licence maps to `none` |
| `geo.name` | string | geo | place name as the source states it |
| `geo.lat`, `geo.lon` | number | geo | WGS84 |
| `geo.precision` | enum | geo | `exact` (geolocated to a feature), `site` (installation or district), `city`, `oblast`, `country`, `region`, `unknown` |
| `geo.basis` | enum | geo | `source_statement`, `geolocation_analysis`, `metadata_exif`, `inferred` |
| `verification` | enum | yes | `unreviewed`, `source_cited`, `provenance_traced`, `geolocated`, `event_matched`, `disputed`, `rejected` (rules in policy §2) |
| `verification.by` / `.on` / `.note` | string/time | if > unreviewed | who checked, when, what was checked |
| `flags.recycled` | bool + `first_seen` | footage | true when earlier publication shows it predates the event it is used for |
| `flags.disputed` | bool + `parties` | claim | true when named parties contradict the claim |
| `flags.mismatch` | bool + `reason` | yes | true when the asset does not match the narration (wrong country, wrong weapon, wrong period) |
| `flags.illustrative` | bool | yes | true for any diagram, icon, generated or schematic image; renders the on-screen "Illustrative" label |
| `identification.subject` | string | equipment/person | what the asset is said to show |
| `identification.confidence` | enum | equipment/person | `confirmed` (source names it and a second source agrees), `stated` (source names it), `visual_only` (we matched it by eye), `uncertain` |
| `identification.source` | string | if confirmed/stated | who identified it |
| `provenance` | array | yes | ordered chain `[{step, actor, url, time}]`, e.g. `captured by` → `posted by` → `reposted by` → `we retrieved from`; at least the first and last link |
| `reuse.key` | string | yes | cache identity (policy §6) |
| `reuse.used_in` | array | no | `[{project, scene, time}]` for audit |
| `ai_provenance` | object | if ai | `{tool, prompt_hash, purpose}`; AI images may be `flags.illustrative` only, never evidence |

Statistics reuse the `Sourced` pattern [repo, `weather/provenance.py`]: `{value, unit, product, url, where, issued, fetched}` plus new `as_of` (date the figure describes), `method` (count, estimate, claim), `claimant`, and `range` when the source gives low/high.

## 3. Categories

Each category lists: **metadata** (beyond §2), **sourcing**, **reuse**, **treatments**, **animations**. Treatments and animations use the motion patterns of the visual catalog (separate document); only the names are used here.

### A. Geography

**A1. Countries and alliances (borders, flags as map fills)**
- Metadata: ISO3, name variants (Cyrillic, Ukrainian, transliteration), `border_status` (`recognised`, `disputed`, `occupied_as_of:<date>`), alliance membership with `as_of`.
- Sourcing: the app's own Natural Earth country data [repo, `map_scene/data/countries.json.gz`]; disputed territory is drawn per policy §4 and labelled with its basis.
- Reuse: one polygon set for the whole app; no per-video copy.
- Treatments: map fill, outline, region label, side-by-side alliance panel.
- Animations: fill spread, outline draw, camera push from region to country.

**A2. Oblasts and regions**
- Metadata: oblast name, ISO 3166-2 code, `status_as_of`, capital, name variants.
- Sourcing: `map_scene/data/admin1.json.gz` [repo]; occupation status needs a dated source (A5).
- Reuse: id `geo:ua-oblast-<slug>`; shared polygon.
- Treatments: highlighted region, label, mini-map inset.
- Animations: boundary highlight (existing `place_focus` fill event), region label pop.

**A3. Cities and towns**
- Metadata: lat/lon, population (as_of), region, `strategic_note` (source required), outline from OSM.
- Sourcing: `boundary_source.py` for outlines (ODbL, cached 365 d) [repo]; names from the script.
- Reuse: cache key already content-based [repo]; add nothing.
- Treatments: pin with one-line note, outline highlight, lower-third place tag.
- Animations: pin drop, outline fade, camera push.

**A4. Strategic locations (refineries, ports, bases, bridges, power plants, airfields)**
- Metadata: facility type, operator, coordinates with `geo.precision`, `status` (operating, struck, damaged) each with date and source, `satellite_ref` ids.
- Sourcing: facility position from OSM/Wikidata [assumption: available], damage claims only from a cited source (company, official, imagery provider, OSINT with method).
- Reuse: id `site:<slug>`; one record per facility across videos.
- Treatments: pin with note, framed aerial, before/after pair, satellite crop with translucent band.
- Animations: pin drop, band wipe, before/after slider (existing `before_after_slider`).

**A5. Front lines and territorial control**
- Metadata: `as_of` date, `source` (named assessment, e.g. an institute's daily map), `method`, `geometry` (polygon of controlled area), `confidence`, `contested` flag, `layer` (control, claimed, contested).
- Sourcing: a dated third-party assessment, cited on screen; **never drawn by hand from narration**. Licence of the source map must allow reuse; otherwise only the *statement* is shown as a source card.
- Reuse: one registry record per `(source, as_of)`; change-over-time sequences reuse the same series.
- Treatments: dated control map with legend; change overlay between two dates; "as of" chip always visible.
- Animations: fill morph between two dated polygons (only between two sourced dates; no interpolated "in between" positions are presented as real), date scrubber.

**A6. Routes, trajectories, ranges** (`flags.illustrative = true` unless sourced)
- Metadata: origin, target, `kind` (`reported_route`, `range_ring`, `illustrative_arc`), source or `illustrative`.
- Sourcing: reported routes need a source (official statement, tracked flight data with provider); range rings need the system's published range and its source.
- Reuse: id `route:<hash>`.
- Treatments: dotted arc with "illustrative" tag, range ring, distance chip (existing `route_travel`, `distance_ruler`).
- Animations: route draw, ring expand.

### B. Military equipment

Shared metadata for B1–B9: `designation` (official), `nato_name` if any, `country_of_origin`, `role`, `family`, `variants`, `spec` (each spec value is a `Sourced`: range, calibre, speed, crew, year introduced), `operators` with `as_of`, `identification.*`, `look_alike_risk` (similar models to avoid confusing). Specs come from manufacturer or ministry data, or a named reference work; unsourced numbers are not shown. Visual identification is `visual_only` until a second source agrees.

**B1. Tanks** — main battle tanks and light tanks. Reuse: one card per designation (`equip:<designation>`), photo from Commons/government sources. Treatments: identification card (photo + designation + 3 sourced specs), side comparison, blueprint line diagram (illustrative). Animations: card slide-in, spec rows revealed in order, callout lines drawn on a photo with fixed screen-space labels (no tracking claim).

**B2. Armoured fighting vehicles** — IFVs, APCs, MRAPs, engineering vehicles. Same as B1. Extra: variant names often differ by operator; store `operator_variant`.

**B3. Artillery** — towed and self-propelled guns, mortars. Extra: calibre, range per ammunition type (source states which). Treatments: card, range ring on map (illustrative until sourced), counts in a bar compare.

**B4. Rocket artillery** — MLRS and rocket systems. Extra: rocket types, range per type, launcher vs rocket distinction. Treatments: card, launch footage with `captured` date, range ring. Animations: ring expand.

**B5. Missiles** — cruise, ballistic, anti-ship, anti-radiation, glide bombs. Extra: launch platform, warhead (as stated by source), `range_km` as published, `reported_use` list with dates. Never show a trajectory for a specific strike unless a source supplies it; otherwise `illustrative_arc`. Treatments: card, comparison table, debris/remains photo with source. Animations: arc draw (labelled illustrative).

**B6. Air defence** — SAM, gun-missile systems, interceptors, short-range systems. Extra: engagement envelope (published), layers (short, medium, long), `deployment_note` with source and date. Treatments: card, layered rings diagram (illustrative), site photo with `geo.precision`. Animations: rings expand, layer labels staggered.

**B7. Drones** — one-way attack, FPV, reconnaissance, naval drones. Extra: `type`, payload, range as published, `origin` (domestic, imported) with source, `counts` as `Sourced` statistics. Treatments: card, footage with `captured` date, count tally. Animations: count-up, tally dots.

**B8. Aircraft and helicopters** — fighters, bombers, transports, rotary. Extra: `role`, `losses_claim` as a `claimed` statistic with claimant. Treatments: card, comparison, footage. Animations: card, spec rows.

**B9. Naval** — ships, submarines, missile boats, port facilities. Extra: `hull_id`, `fleet`, `status_as_of`. Treatments: card, port aerial, map pin. Animations: pin drop, status chip change (dated).

**B10. Radar and electronic warfare** — radars, jammers, SIGINT, GNSS interference. Extra: `band`, `function`, `coverage` as published. Treatments: card, schematic coverage fan (illustrative), site photo. Animations: fan sweep (illustrative label permanent).

Sourcing for B (all): manufacturer/ministry data sheet, a named reference publication, or Commons/government photo with its own licence. Reuse: equipment cards are the most reusable asset class: one card layout per category, one photo per designation, cached by `asset_id`.

### C. People and institutions

**C1. Political leaders** — heads of state and government, ministers, parliament.
- Metadata: full name variants, role with `from`/`to` dates, `portrait` asset (rights below), `statement` records `{text, date, venue, language, translation_by, source_url}`.
- Sourcing: portrait from the office's own site or Commons with a verified licence and credit; statements from the primary transcript or a wire report.
- Reuse: `person:<slug>`; the same portrait file in every video; portrait cut-out cached once.
- Treatments: circle portrait + name plate + role line; attributed statement card with date and venue; split pair for negotiations.
- Animations: portrait scale-in with ring, plate wipe, quote words darkening as spoken.

**C2. Military officials** — chiefs of staff, commanders, defence ministers, spokespersons.
- Same as C1; extra `rank_as_of`, `command` and `unit`. Statements about the battlefield are claims by the speaker and are attributed, never shown as fact.

**C3. Government institutions and bodies** — ministries, general staffs, security councils, parliaments.
- Metadata: official name variants, `acronym`, `seat`, emblem asset id (verified insignia, D6).
- Sourcing: the institution's own publication; emblem rights checked.
- Reuse: `inst:<slug>`; emblem cached once.
- Treatments: source card header, lower-third "statement by", emblem on a document card.
- Animations: card fade, highlighter on the cited line.

**C4. Diplomatic events and alliances** — summits, talks, treaties, sanctions packages, aid conferences.
- Metadata: `event_date`, `venue`, `participants[]` (person ids), `outcome_statement` with source, `treaty_text_ref`.
- Sourcing: official readouts and wire reports; photos from the host or agency with licence.
- Reuse: `event:<slug>`; photos cached per event.
- Treatments: dated chapter card, participant row, layered photos on paper (versus scenes), timeline strip.
- Animations: timeline draw, photo layer slide, chapter wipe.

### D. Footage, imagery and documents

**D1. Battlefield footage**
- Metadata: §2 plus `claimed_location`, `claimed_event`, `unit_if_stated`, `audio_has_voice` (translation needed), `watermark` (outlet or channel), `graphic_content` (yes/no, controls blur).
- Sourcing: official ministry or unit channels (state their own aims; label as such), wire/news licensed clips, OSINT archives with licence, stock libraries only for generic b-roll. Date and place are taken from the source's statement and must be cross-checked (policy §3); otherwise `captured.basis = inferred` and the footage is b-roll only.
- Reuse: id `footage:<sha1[:12]>`; one clip may serve several scenes; track `used_in` so the planner can avoid showing the same clip for two different events.
- Treatments: full-frame with shot headline and a "FOOTAGE · <date> · <source>" tag; dimmed backdrop; split before/after; picture-in-picture over a map.
- Animations: push, dim ramp, source tag fade.

**D2. Satellite and aerial imagery**
- Metadata: provider, sensor, `captured` (to the minute where known), resolution, `tile_bounds`, licence (commercial imagery is usually restricted), `before_after_pair_id`.
- Sourcing: open imagery (public programmes) or licensed provider imagery; images posted by third parties are `osint` and cited.
- Reuse: `sat:<provider>:<scene-id>`; crop regions are derived views of one master.
- Treatments: translucent band over a site, before/after slider, labelled crop with scale bar.
- Animations: band wipe, slider, crop zoom.

**D3. Archival material** — historic photos, film, maps, treaties.
- Metadata: `event_date` (history) vs `captured`, archive reference number, rights holder, `restoration_note` (if cleaned).
- Sourcing: public archives (Commons, national archives, Internet Archive [repo, `providers/archive`]); each item's own licence.
- Reuse: `archival:<archive>:<ref>`.
- Treatments: B&W with vignette, layered photos on paper, framed still, document zoom.
- Animations: Ken Burns, layer slide, highlighter.

**D4. Industrial facilities and infrastructure** — refineries, power grid, bridges, rail, ports, data centres.
- Metadata: as A4; `capacity` as `Sourced`; `damage_reports[]` each `{date, source, claim, confidence}`.
- Sourcing: company or ministry data; imagery per D2.
- Reuse: one `site:` record, many assets.
- Treatments: framed aerial with caption, status chips, capacity bar.
- Animations: chip change dated, bar fill.

**D5. Logistics** — rail, ports, fuel supply, corridors, border crossings, convoys.
- Metadata: route id, `capacity`, `bottleneck` note with source, corridor `status_as_of`.
- Sourcing: official statements, trade data (as `Sourced`), imagery.
- Reuse: route records.
- Treatments: route map, flow arrows labelled illustrative unless sourced, counts.
- Animations: route draw, flow pulses.

**D6. Document and evidence cards** — official statements, press releases, intercepted-style claims, leaked or declassified documents.
- Metadata: `document_type`, `issuer`, `date_issued`, `date_accessed`, `url`, `language`, `translation` (who, machine/human), `quoted_span` (exact words shown), `authenticity` (`official_publication`, `authenticated`, `unverified`).
- Sourcing: the primary page; for unauthenticated documents the card says "unverified".
- Reuse: `doc:<sha1[:12]>`; the card renders from the record, never from a screenshot we do not hold rights to.
- Treatments: paper source card, highlighter on the quoted span, pen circle on a date; screen-recorded page only with rights.
- Animations: card fade, word-by-word darkening, highlighter wipe (measured in reference A).

### E. Numbers and comparisons

**E1. Military statistics** — equipment counts, losses, strikes, intercepts, production.
- Metadata: `Sourced` + `as_of`, `claimant` (who counts), `method` (`confirmed_visually`, `official_claim`, `estimate`), `range`, `counter_claim` (the other side's number with source), `unit`.
- Sourcing: named tallies; claims from belligerents are labelled as claims. **Casualty figures are never composed by us.**
- Reuse: one statistic record per (claimant, metric, as_of); re-used in recaps.
- Treatments: number card with "claimed by <x>, <date>" sub-line, paired claims side by side, uncertainty range bar.
- Animations: count-up, rule draw, bar compare from zero axis.

**E2. Equipment comparisons**
- Metadata: two or more `equip:` ids, shared spec keys only, each value sourced, `comparison_basis` note (same ammunition, same variant).
- Sourcing: the B-class spec records.
- Reuse: composes existing equipment records.
- Treatments: two-pane chip-labelled split, bar compare, table.
- Animations: row reveal, bars from zero.

**E3. Territorial change**
- Metadata: two dated A5 records, `area_km2` as `Sourced` with method, `period`.
- Sourcing: same as A5; area numbers from the same assessment.
- Reuse: series records.
- Treatments: dated before/after map, line chart over dates, change number card.
- Animations: fill morph between two sourced dates, line draw.

**E4. Aid and sanctions**
- Metadata: `donor`, `category` (military, financial, humanitarian), `amount` with currency and `as_of`, `commitment_vs_delivered`, `package_name`, `measure` (sanction type, target, date in force).
- Sourcing: donor government releases, institute trackers [assumption: Kiel Institute style trackers exist; verify], EU/US official journals.
- Reuse: statistic records per package.
- Treatments: ranked bars, stacked comparison, timeline of measures, list card.
- Animations: bar race from zero, list rows, timeline draw.

**E5. Economic effects**
- Metadata: indicator (price, GDP, trade volume, inflation), `series` of `Sourced` points with dates, `unit`, `base_period`, `seasonal_note`.
- Sourcing: statistical offices, central banks, exchanges, IEA-type agencies [assumption].
- Reuse: series cached per (indicator, source, retrieval date).
- Treatments: line chart, change number, before/after bars.
- Animations: line draw, count-up. Axes start at zero for bars; line charts show the axis range.

### F. Graphic furniture

**F1. Flags** — Metadata: country, `flag_version_date`, SVG file, licence (most state flags are PD [assumption]); one record per flag. Treatments: map-pin flag, name plate flag, panel header. Animations: pin drop, fade.

**F2. Verified insignia and emblems** — state emblems, service badges, unit patches. Metadata: `issuer`, `usage_restriction` (some emblems are legally restricted), `verification` (taken from the issuing body's own site). **Unit symbols and patches are never guessed from a photo.** Treatments: document header, person plate, unit card. Animations: fade only.

**F3. Unit symbols (map)** — tactical symbols for units. Metadata: `symbol_set` (a recognised standard, [assumption: APP-6 style]), `unit_name`, `echelon`, `position_basis`, `as_of`. A unit position is **only** shown when a source gives it; otherwise no marker. Treatments: marker on map with the "as of" chip. Animations: marker appears at its dated position; moves only between two sourced positions.

**F4. Equipment icons** — generic silhouettes by class (tank, SPG, MLRS, missile, SAM, drone, aircraft, ship, radar). Metadata: `class_id`, `style_version`, `flags.illustrative = true`. Made once as a small set (not per video), used in counts, legends, map markers. They stand for a *class*, never a specific model.

**F5. Map markers and labels** — pins, region labels, distance chips, range rings, arrows. Metadata: `marker_type`, `geo.*`, `note` (one line), `source_ref`, `illustrative`. Treatments and animations as A3–A6.

**F6. Source cards** — paper card with outlet, date chip, quoted span, highlighter. Rendered from a D6/E record. Never invent the outlet, date or text. A source card of an unverified claim carries the word "claim".

**F7. Evidence highlights** — highlighter bar, pen ellipse, underline, arrow on a document or photo. Metadata: `target_asset`, `span`, `purpose` (`quote`, `date`, `figure`, `feature`). A highlight on a photo must mark something the source states is there; it never points at an unconfirmed object.

**F8. Kicker, chapter and recap cards** — editorial furniture. Metadata: `chapter_title`, `claims_summarised[]` (ids). A recap card may only repeat claims already shown with the same wording and sources.

## 4. Metadata that has no home in the repo today (the honest list)

| Field group | Existing carrier | Verdict |
|---|---|---|
| author, source_url, provider_asset_id | manifest record via `result.metadata` [repo] | usable as is |
| licence | Openverse only (`license`, `license_version`); `boundary_source` meta `licence`/`attribution` | **partly**; Pexels/Pixabay record no licence field in the manifest |
| three dates (event / captured / published) | none | **new** |
| verification state, flags (recycled, disputed, mismatch, illustrative) | none | **new** |
| identification confidence | none | **new** |
| geo precision and basis | none; `boundary_source` has coordinates but no precision level | **new** |
| provenance chain | none; `weather/provenance.Sourced` is a single hop | **new** (list of hops) |
| statistic provenance | `Sourced` pattern [repo] | copy the pattern into the new package, add `as_of`, `claimant`, `method` |
| cache identity independent of scene number | `boundary_source.key()` pattern; manifest is scene-keyed | **new registry** keyed by `asset_id`; manifest stores only `war_asset_id` |

Carrying the new fields as extra keys on the manifest record would work only until the next `AssetManifest.set()` replaces the record, and would put per-asset facts in a per-scene file, so the proposal is a separate registry (policy §7).
