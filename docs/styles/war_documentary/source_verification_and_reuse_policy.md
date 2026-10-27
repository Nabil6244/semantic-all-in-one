# War Documentary style — source verification and reuse policy

Status: design only, for approval. Labels: **[repo]** read in this checkout; **[proposal]**; **[assumption]** outside fact not verified, check before use. Schema fields are defined in `asset_taxonomy_and_metadata.md`.

## 1. Principle

A visual in this style is either **evidence** (it asserts something about the real war) or **furniture** (it organises the story and asserts nothing). Only evidence needs provenance; furniture must be unmistakably furniture. When in doubt a visual is downgraded: evidence → labelled b-roll → furniture. Nothing in this policy lets the planner "fill a gap" with a real-looking image.

Every factual visual claim carries: **what is claimed**, **by which source**, **on which date**, **how verified**, **how the viewer is told**. The plan report lists one line per claim, in the manner of the Weather numbers report [repo, `weather/provenance.NumbersReport`], so a video can be checked against its sources line by line.

## 2. Verification states and what the planner may do

`verification` enum, in rising strength. A state is set by a human or by an explicit, logged check, never by the planner itself.

| State | Meaning | Planner may | Planner may not |
|---|---|---|---|
| `unreviewed` | found, nothing checked | use as generic b-roll with **no** factual caption, only if `flags.mismatch = false` and the licence permits | claim a place, date, unit, weapon or event; use as evidence; show a portrait |
| `source_cited` | the publisher states what it shows; we have not checked | show with the caption "<publisher> says: …" or an attributed tag "FOOTAGE · <publisher> · <published date>" | state the claim in the narrator's voice on screen |
| `provenance_traced` | earliest publication found and matches the use | caption with `captured` date if `basis` is `metadata` or `source_statement`; use as evidence of "this footage exists / was published" | assert exact location unless `geolocated` |
| `geolocated` | location confirmed by a method written in `verification.note` | show place with `geo.precision` honestly; pin on a map at that precision | assert the date of capture unless also dated |
| `event_matched` | date, place and event all match the narration | full factual caption; may anchor a map beat | nothing further |
| `disputed` | named parties contradict it | show only inside a two-sided frame: "<A> claims … · <B> says …", both sourced | a one-sided caption |
| `rejected` | wrong, fake, recycled for this use, or unlicensed | nothing | any use; kept in the registry so it is not re-found |

Defaults: assets from stock libraries start at `unreviewed` with `class = footage` and `source.kind = stock_library`: **b-roll only**. Assets from an official ministry start at `source_cited` and are labelled with the ministry as the party making the claim, because belligerent publishers state their own aims. Statistics from a named tally start at `source_cited`; a statistic with no named source is not planned.

## 3. Flags and how each is raised and shown

| Flag | Raised when | Shown on screen | Plan report |
|---|---|---|---|
| `recycled` | an earlier publication predates the event it is used for (reverse image search, source archive date, watermark date) | footage is not used for that event; if kept as context: "FILE FOOTAGE · <first seen date>" | line "RECYCLED: first seen <date> <url>" and the scene is blocked until a human decides |
| `uncertain identification` (`identification.confidence = uncertain` or `visual_only`) | weapon, unit, aircraft or person named by us but not by the source | no model name in a caption; use the class label ("air-defence system") and the source's wording | "ID uncertain: <subject> visual only" |
| `disputed` | any named party contradicts it, or two sources give different numbers | two-sided frame (§2) or a range with both claimants named | "DISPUTED: <parties>" |
| `mismatch` | wrong country, system, period, or the narration is about X and the asset shows Y | not shown as evidence; if used it is labelled b-roll: "ILLUSTRATIVE FOOTAGE" or "FILE FOOTAGE" | "MISMATCH: <reason>"; the reference video's US Patriot battery under a Russia narration is the model failure to catch [repo doc: war_explainer_reverse_engineering.md] |
| `illustrative` | diagram, icon, generated image, schematic arc, range ring from a published number | permanent "ILLUSTRATIVE" tag on the graphic for its whole duration | "ILLUSTRATIVE: <kind>" |

A flagged scene never blocks a render silently: it goes to a **review list** shown before Render, one line each, with the choices "replace", "relabel", "accept with label". Render does not start while a `recycled` or `rejected` asset is planned (mirrors the existing "Generate scenes → Render only when every scene is ready" gate [repo memory: `project_hybrid_scenes_then_render`]).

## 4. Never fabricate

The planner and any generator in this style must not produce:

- **Battlefield positions:** no unit marker, arrow of advance or front line unless a dated source supplies the geometry (`A5`, `F3`). No interpolated position between two dates is presented as a real position; a morph between two sourced dates is labelled "between <date> and <date>, not a track".
- **Weapon identification:** a model name appears only if the source names it (`stated`) or two sources agree (`confirmed`). Visual matching alone yields a class label.
- **Trajectories:** a missile or drone path is an `illustrative_arc` unless a source supplies it; it is labelled illustrative and drawn as a generic arc between two named places, never along a claimed real path.
- **Casualty counts and loss counts:** never computed, summed, extrapolated or "rounded for the graphic" by us; a figure is shown exactly as sourced, with claimant and date, and a counter-claim is shown beside it when one is on record.
- **Events:** no scene depicts an event as having happened unless a source states it; no AI-generated image is used as evidence of a real event, and AI imagery is allowed only as `illustrative` furniture with its tag.
- **Quotations and attributions:** a quote card uses the exact words and the speaker's role at that date; translation is marked "translated by <who>".

If the data is missing, the correct output is **no graphic**, or a graphic that says what is not known ("location not confirmed").

## 5. Portrait rights

1. A portrait is shown only for a named, identified person in a scene where the narration names them in a way that supports it (policy for the planner: name + role are both stated; a person who is merely mentioned does not get a portrait).
2. The portrait file must have: a source URL, a licence record (`licence.spdx` and `licence.attribution`), and `identification.confidence ∈ {confirmed, stated}`. Government portraits are not automatically free: record the actual terms [assumption: some heads-of-state sites publish under CC BY 4.0, verify per site].
3. Do not assume public domain. Commons files keep their own licence and credit.
4. `licence.reuse = none` or `UNKNOWN` → no portrait; the name plate alone is shown.
5. The credit line is shown on screen or in the end credits and the description file, as the licence requires.
6. One portrait per person (`person:<slug>` → one file, one crop) for every video; a *different* photograph is used only when the context calls for it (e.g. an event photo) and then under its own record.
7. Cut-outs, circle crops and colour treatments are derived views cached against the master; the master is never altered.
8. A portrait is not shown for a private individual unless they are named by the source as a public speaker or official.
9. Placeholder silhouettes (as in the Phase 1 demo) are only for demos and are tagged "placeholder".

## 6. Licensing checks

Before an asset enters the plan:

1. `licence.spdx` is known and `licence.reuse ∈ {free, attribution_required, share_alike}` or the project holds a written permission recorded in `licence.url`.
2. Attribution string is non-empty when required.
3. Share-alike items are flagged for the user (the finished video may need the same licence for derivative parts; this is a legal question for the user, not decided here).
4. `editorial_only` assets are blocked unless the user confirms the use is editorial.
5. User-supplied clips (Local clip, MANUAL) are accepted as `USER-SUPPLIED` with the user's own statement of rights; they are never blocked, never deleted by cleanup [repo: `downloaded_assets.PROTECTED_SOURCES = {local, manual}`], but are still flagged for provenance if used as evidence.
6. Sources that the existing provider code already labels are reused as they are: Openverse items carry `license` and `license_version` [repo, `providers/stock/openverse.py`]; Pexels/Pixabay items record only `author` and `source_url` [repo], so the licence is the provider's blanket licence, stored once per provider in the registry, not per item [assumption: provider terms permit this use; verify at integration].
7. Terms of services for scraping or API use are respected: the existing Nominatim module sets the pattern (identifying User-Agent, rate limit, cache results, remember rejections) [repo, `boundary_source.py`]; any new lookup follows it.

The `youtube_video` provider is *not* a licence: footage found on YouTube keeps the uploader's rights; the registry marks `licence.spdx = UNKNOWN` and `reuse = terms_check` until a human sets otherwise [assumption: repo treats YouTube clips as a source, not as licensed content; confirm in `providers/youtube`].

## 7. Where each rule lives in the existing code (reuse map)

| Rule | Reuse | New |
|---|---|---|
| Per-scene file and its fetch record | `.asset_manifest.json` via `AssetManifest` [repo] | add **one** key, `war_asset_id`, via provider metadata; nothing else |
| Author, source URL, provider id, Openverse licence | already in the manifest record [repo] | none |
| Repeat-use penalty for stock | `.stock_used_assets.json` [repo] | none |
| Entity cache (people, equipment, facilities, statistics, documents) | pattern of `boundary_source` (content key, licence, attribution, fetched, TTL, rejected-answer memory) | a registry directory `war_registry/` beside the boundary cache (`map_scene.render.cache_dir()`), JSON files, one per `asset_id` |
| Statistic provenance | `Sourced` pattern [repo, Weather: copy, do not import] | new `StatSourced` adds `as_of`, `claimant`, `method`, `range` |
| Per-video claims report | `NumbersReport` pattern | new `ClaimsReport` (one line per claim) |
| Geometry and place outlines | `map_scene/data/*.json.gz`, `boundary_source` [repo] | none for geometry; occupation status is a dated registry record |
| Templates | `gfx-core` slots `label/sub/text/values/geo` [repo] | **provenance sub-line** is passed in `sub` (e.g. "Claimed by X · 12 Oct") so no template change is needed; a new `illustrative` tag and `claim` tag are small templates, not changes to existing ones |
| Cleanup safety | `PROTECTED_SOURCES`, `is_protected_asset_name` [repo] | registry lives outside the project folder so project cleanup cannot delete it; the project copy of a file may be cleared and re-linked from the registry |
| Learning ledger | `learning/` source vocabulary [repo] | none: do not write war fields into `learning.sqlite` |
| Review gate before Render | "Generate scenes first, Render only when every scene is ready" [repo, recent commit 99a0ee8] | the flag review list is a new step in that gate |

**Where the existing mechanism cannot carry a field:** the three dates, verification state, the four flags, identification confidence, geo precision/basis and the provenance chain have no existing field (taxonomy §4). They go into the registry, not into the manifest, because the manifest record is per scene and is replaced wholesale on every write [repo, `AssetManager._record_from_result` comment].

No database migration is required: registry files are JSON, as the boundary cache and manifests already are. No new dependency is required for this part.

## 8. Cache identity and reuse

1. **Identity key** [proposal]: `reuse.key = sha1(canonical_id | normalised_source_url | licence_spdx)[:20]`, the same shape as `boundary_source.key()` [repo]. The content `sha256` is stored as an integrity check; if the bytes at the same key change, the registry records a new `revision` and marks dependent claims for review (a source that edits an image must not silently change a video).
2. The same asset is **never re-fetched or regenerated** for another scene or video: the planner asks the registry first by `asset_id`; only on a miss does a provider run.
3. A `rejected` or `recycled` verdict is cached like a good answer (as `boundary_source` caches rejections, 30 days) and does not expire silently: it expires only by a human action.
4. Generated or derived views (circle crop, dim plate, thumbnail, cut-out, icon) are cached under the master's key plus a `view` string, e.g. `<key>:circle250`.
5. Equipment cards, portraits, flags, icons and the facility catalogue are shared across all videos; footage clips are shared across scenes in a project and reusable across projects when licensed for it.
6. **Do not reuse across different claims silently:** the same clip may appear again only if the new claim is the same or compatible; the planner records `used_in` and blocks showing one clip as two different events in one video (a video-level check, listed in the plan report).
7. Per-video cap on visual repetition is a planning rule, not a cache rule: the same non-furniture asset appears at most twice in a video unless the story deliberately returns to it (recap), following the "recurring visual" idea in the reference analysis.
8. Time to live: facts that change (control of a place, status of a facility, a running statistic) carry `as_of` and are re-checked when older than a window set by the user (default proposal: 30 days for status, 365 for static data like a spec sheet).

## 9. Roles and logging

- The registry records `verification.by` and `.on`; automated checks log their name and version.
- The planner reads the registry and never writes `verification` upgrades.
- Every scene in the plan report carries: visual class, `asset_id`, state, flags, caption text, licence line.
- Credits: the "assets and sources" list is generated from the registry for the video description (one line per attributed asset).

## 10. Decisions needed from you

1. Registry location: a new per-user `war_registry/` beside the boundary cache, outside project folders (recommended), or inside each project?
2. Who sets `verification` upgrades: you only, or may a named automated check (reverse search, geolocation hint) raise it to `provenance_traced`?
3. Scope of "official" footage: may ministry-published clips be used at all as `source_cited` (with the "<ministry> says" label), or only as quoted statements?
4. Casualty and loss figures: allow only as exact sourced numbers with claimant (recommended), or exclude them from this style?
5. Front-line maps: which dated assessment may we cite and show (licence must allow it), or should we show only a "source says" card and no drawn front line?
6. Portraits: approve a rule that a portrait needs `confirmed`/`stated` identity plus a recorded licence, otherwise name plate only?
7. Licence of stock providers (Pexels, Pixabay): accept the provider's blanket licence recorded once per provider, or require per-asset licence text?
8. YouTube-found footage: treat as `UNKNOWN` licence needing your explicit clearance per clip (recommended), or exclude from this style?
9. Flag review list before Render: a blocking step (recommended for `recycled`, `rejected`) or advisory only?
10. Status time to live: 30 days for changing facts and 365 for static data, or other windows?
