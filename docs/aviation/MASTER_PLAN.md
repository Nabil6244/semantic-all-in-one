# Aviation style — master plan v4 (2026-11-13)

**Direction:** one Aviation style whose **narration chooses the look of each moment**. Three looks from the references:
the **sticker story** (Why Singapore Airlines and Malaysia Airlines Split Apart) as the default for history / business stories,
the **news** look (Plane Curious) and the **flight** look (Vistara 611). Made with **Flow used the Rep Theory / Jung way**, with **real
pictures from YouTube and web capture**, cut for **retention**, and built **on top of everything already built** (commit 4120ab6).
Video only: the script and voice-over are the user's and are never changed.

Older plans, kept for detail and history: `PLAN.md` (news + flight looks, footage rules, source plan v2, status),
`STICKER_STORY_PLAN.md` (sticker look detail, Flow uses F1–F9 / V1–V6), `REFERENCE_STUDY.md` (measurements, A1–A7, B1–B20).

---

## 0. Rules this plan keeps

- Test-first, smallest changes; `app.py` additions only, check `test_fixtures/*_protected.json` before editing.
- Fetched assets go through the **Visuals tab**, renders end on **Export** (`visual_bridge.py`).
- **Nothing starts until Generate**: picking files / options only remembers.
- A supplied **CSV run makes zero Gemini calls**; the CSV and its prompt carry the searches, URLs and graphics.
- **No per-video asset burden**: stickers, flags, models, icons, b-roll and Flow pictures are made or sourced once into a shared
  library and reused.
- **No still screens**: something moves or arrives every 2–4 s; maps never freeze.
- **Keep existing features**: the news and flight looks, the 12 graphics and every built card stay; new looks are added, never swapped in.
- **Fix the code, not the video**: a bug seen in a render becomes a general rule + a synthetic test.
- **Flow never fakes** a real named event or a real person's face; Flow pictures carry an `AI ILLUSTRATION` chip; Flow videos cost
  credits and are asked once per film.
- Every borrowed picture carries `Source:` / `Credits:`. Audio -14 LUFS, BT.709 encode.
- No renders, Flow runs, full test suites or test films unless asked; only touched tests are run.

---

## 1. What is built (4120ab6) and its job in v4

| Built | Module | Job in v4 |
|---|---|---|
| catalog: 56 airlines (liveries, hubs), 29 aircraft types, 90+ airports | `aviation/catalog.py`, `data/*.json` | sticker liveries, logo-card colours, aircraft body per type, places on maps, livery checks |
| narration router: modes + values (dates, money, counts, changes, fuel, altitudes, flights, places) | `aviation/router.py` | picks the look per line; feeds the year badge, numbers on cards, flight HUD |
| blue article card, window collage, `Source:` tag | `aviation/cards.py` | the news look; restyled as the "newspaper" paper sticker for the sticker look |
| dark satellite map (Sentinel-2 + hillshade), curved routes, holds, range ring, callouts, storms | `aviation/basemap.py`, `flightmap.py` | the flight look; the base for the political and route maps (S6, S7) |
| clock / fuel / altitude HUD, fuel stack bar, radio lines | `aviation/hud.py` | the flight look, unchanged |
| graphics: counters, weather icons, place title, briefing sheet, altitude side view, end card | `aviation/gfx.py` | flight / news looks; end card = next-episode card |
| 12 aviation graphics: fleet grid, route network, seat map, then→now bars, big number, timeline, crew card, gauge, runway, glide slope, descent, title | `aviation/gfx_air.py` | kept as the news skin; restyled into the sticker skin (step 3) |
| footage rules: search phrases, clip rules, livery score, cut lengths | `aviation/footage.py` | rules for every source (section 4) |
| YouTube footage director (storyboard checks, capture) | `aviation/director.py` | source 2 (section 4) |
| website screenshots (headline box, overlays hidden, cached) | `aviation/webshot.py`, `webshot.mjs` | the base of web capture (section 4) |
| Flow routing + credit question, one shared look | `aviation/flow.py`, `ui/aviation_section.py` | extended by the bible and library (section 5) |
| planner (modes → timeline, map stretches, re-framed beats) | `aviation/planner.py` | gains the stage, the source router and the retention pass |
| renderer bridge, CSV columns + prompt, app page, Visuals / Export, make_video autorun, chunked render | `bridge.py`, `csv_rows.py`, `data/aviation_csv_prompt.txt`, `runner.py` | unchanged base; new CSV columns added |

---

## 2. The three looks and the router

The router classifies each sentence by rules (no Gemini). A film can mix all three looks (step 13 adds the shared transitions).

| Mode | Narration triggers | Look |
|---|---|---|
| **story** (new) | founded, formed, split, merged, joint, owned, stake, shares, government, independence, renamed, rebrand, flag carrier, national airline; a year far before the story's "now" | **sticker stage** (section 3) |
| **news** | announced, ordered, deal, CEO, launched, profit, loss, strike, report says, a date + an airline | real clips 1–2 s + blue article card every 10–20 s, or on a story film the paper sticker |
| **numbers** | money, passengers, percentages | icon stat / sticker piles (story) or blue graphics (news) |
| **fleet / tech** | aircraft types, engines, seats, range, wings | fleet card + beauty clips / Flow of that type and livery; spec, seat map |
| **people** | captain, first officer, named executive / politician | portrait + quote (S9) for named people with a real credited photo; crew card / Flow cast for unnamed crew |
| **flight** | took off, climbed, descended, route, diverted, hold, fuel, minutes, feet, knots, ATC | dark map + gold route + HUD, aircraft shots, flight title (S14) to open |
| **weather** | storm, monsoon, hail, gusts, visibility | dark map + storm cells + weather icon list |
| **evidence** | investigation, report found, court, regulator | report / court pages with highlighted lines, redaction boxes; web capture of the real report |

Pacing per mode (from the references): news cuts 1–2 s, fleet 4–8 s, flight holds 5–15 s on a moving map, the stage adds an element
every 2–4 s.

### Flight-look pieces still missing (from Vistara, B-list)

| # | Piece | Status |
|---|---|---|
| B15 | instrument close-ups (ECAM / fuel page, warning box) | not built → step 6 |
| B16 | picture-in-picture pinned on the map (a photo near a place) | not built → step 6 |
| B17 | airspeed tape (boxed value, WINDSHEAR tag) | not built → step 6 |
| B18 | report / court pages with highlights and redactions | partly (briefing sheet) → step 6, uses web capture of the real page |
| B19 | cartoon analogy (concept teaching) | left out; Flow explainer plates cover "how it works" (F4) |
| N10 | 3D aircraft (GLB) | not built; Flow covers the aircraft shots; a free airliner GLB needs your OK to download |

---

## 3. The sticker story look

**One stage, not cuts.** A black stage that builds up: elements pop in, move, stay across many lines and are pushed out; the year
badge keeps time. The stage is a scene graph (element + enter / move / exit / stay, each sprite drawn once and moved), so a chapter
is one evolving picture. This is the biggest jump in feel.

| # | Element | Data from | Built by |
|---|---|---|---|
| S1 | **Aircraft sticker**: side view in livery, thick white die-cut edge, shadow, slow float | catalog type + livery | Flow image (library) or a real photo cut out (web / Openverse); code-drawn fallback by body type |
| S2 | **Year badge** top-right, spaced digits, ticks when the story moves | router dates / years, carried line to line | code |
| S3 | **Logo card**: white rounded card, tail-fin mark + name + years, on a timeline bar with a moving dot | catalog (+ `founded`, `defunct`, `previous_names`) | code (tail-fin mark drawn from livery, never a copied logo) |
| S4 | **Split / merger tree** | catalog `parent` / `successors` + the line's words | code |
| S5 | **Flag characters + speech bubbles**, the aircraft sticker tugged between them | the line's own clauses; shipped flag set (~40, geometric first) | code (flags, bubbles, hands), Flow hands optional |
| S6 | **Political map**: black land, countries filled, serif title | Natural Earth shapes (app has them) + places named | code on the built basemap |
| S7 | **Route-map card**: routes from hubs, legend, year | catalog airports, places named | code (reuses flight-map drawing) |
| S8 | **Ownership diagram**: logo → owners (flags / logos, %) | CSV `owners`, the line's "% stake", web data capture | code |
| S9 | **Portrait + quote**: round b/w portrait, name, role, bubble | CSV `person` / `role` + the line's quote; photo only from the user or a credited web capture; else a silhouette | code |
| S10 | **Fleet card**: sticker + yellow `3x Boeing 707-320` badge | router counts + catalog | code + S1 |
| S11 | **Icon stat**: yellow line icon + one figure | router money / counts | code |
| S12 | **Who-got-what board**: flag on top, icons with captions | CSV `split` | code |
| S13 | **Handwriting**: a name written, struck through, rewritten | the line's named brand | code |
| S14 | **Flight title**: `SQ 108` between two airport dots | router flight + airports | code |
| S15 | **Photo card**: photo, title top-left, `Credits: X` lower-left | web capture / YouTube stills / Flow era plates | code frame |
| S16 | **Big type opener**: bold words with arrows to stickers | the hook line's key words; CSV `graphic` = `hook` | code |
| S17 | **Paper sticker** ("the newspaper said…"): page shot as a torn paper sticker, key line highlighted | web capture (section 4) | code + built webshot |
| S18 | **Numbers made physical**: fleet grids of the airline's own stickers, cash as sticker piles, seats as a sticker cabin | router numbers | the 12 built graphics, restyled |

**Channel identity:** one fixed palette, typeface, year-badge style, sticker edge and sound set for every film; every element is a
reusable template.

---

## 4. Picture sources

For each line the **source router** tries these in order; the first that passes the checks wins.

| # | Source | Module | Best for | Shown as |
|---|---|---|---|---|
| 1 | **Shared library** (approved once, reused by every film): b-roll clips + approved stickers, photos, Flow pictures, captured pages | War `library.py` format; `assets/aviation/library/<airline>/<era>/` | common types in flight / take-off / landing, aprons, cabins, cockpits, engines, factories, check-in, rain on runways; everything already made for that airline | anything |
| 2 | **YouTube, checked** (news, airline press, spotters, archive channels) | `aviation/director.py` | named real events, the named airline's real aircraft, press conferences, old-era archive clips | 1–2 s inserts, photo cards, flight chapters |
| 3 | **Web search + capture** (below) — the main source for history, business and data | `research/engine` (DuckDuckGo, keyless; page / metadata / structured-data / fact extraction; robots + rate limit) + `aviation/webshot.py` | the cited article, the airline's history / newsroom pages, Wikipedia pages of the airline and aircraft, aviation news, lead photos, fleet / ownership / route numbers | paper stickers, photo cards, data cards, scroll captures, sticker cut-outs |
| 4 | **Openverse** (CC images) | `providers/stock/openverse.py` | spotter photos of exact type + livery + registration | sticker cut-outs, photo cards |
| 5 | **Pexels / Pixabay** (existing keys) | `providers/stock/pexels.py`, `pixabay.py` | generic clouds, skylines, money, offices, crowds, airport halls | short inserts, never for a named airline |
| 6 | **NASA** (public domain) | `providers/nasa` | research / supersonic / future-aircraft tests, earth-from-orbit route openers | inserts, photo cards |
| 7 | **User's own files** (sim captures, own clips, CSV `local`) | `providers/local_provider.py` + Visuals-tab attach | flight-sim shots in the right livery, anything the user has | as the line asks |
| 8 | **Flow image / video** | section 5 | moments nobody filmed or photographed, old eras, future aircraft | `AI ILLUSTRATION` chip |
| 9 | **Code graphics** | sections 2, 3 | numbers, maps, diagrams; the never-black fallback | stage elements |

**Dropped:** Internet Archive (too slow), Wikimedia Commons (links fail). Old-era pictures come from web capture, YouTube archive
channels and labelled Flow era plates.

### Web search + capture

1. **Search, no Gemini:** queries from the line's names + CSV `search` / `url` (a CSV URL always first). Preferred sites first:
   the airline's newsroom / history page, Wikipedia, Reuters / AP / BBC, aviation news sites, planespotter photo pages.
2. **Four captures** per good page, one throwaway browser, parallel, a time limit per page, cached by URL:
   - **page shot**: headline + date + lead photo, the key sentence highlighted (built) → paper sticker S17 / blue article card;
   - **scroll capture**: a 3–5 s video scrolling to the highlighted sentence (motion, not a still);
   - **element capture**: the lead photo, a Wikipedia infobox, a fleet table, a timeline, a share-price chart → photo cards or a sticker;
   - **data capture**: founded year, fleet counts, % stakes, routes, passengers via the rule-based fact / structured-data extraction →
     year badge, ownership, fleet card, icon stats, with the page as `Source:`. The narration wins: data fills or confirms, never contradicts.
3. **Checks:** the page must name the line's airline / aircraft / event; photos pass the livery colour check when an airline is named;
   paywall / cookie wall / blank → skip (overlays hidden, never accepted); a real person's face only from a credited photo of that person.
4. **Speed:** search + capture run in the background at Generate while the plan is built; 6–8 pages usually cover a film; all saved
   to the shared library by airline.

### Rules for every source

- An aircraft-type line takes only that type (an A350 line never shows a 737).
- A named-airline line prefers its livery (title words, then the catalog colour check).
- A named event takes only a clip / photo of that event, else a card — never generic b-roll, never a wrong clip.
- YouTube: drop promos, trailers, safety videos, compilations, reactions, podcasts, studio desks, subtitles / tickers, cartoons;
  a clean 3–8 s window away from intros (built).
- A clip is used at most N times per film and never twice within a set gap; a line never borrows another scene's picture.
- Real photos (web, Openverse) can be cut out into stickers with the S1 edge — a real 1972 photo of a 707 on the stage.

### Library build (once, not per video)

A script lists candidate clips / photos per subject (~40 subjects: each common type × phase, aprons and terminals by hub, cabins by
class, cockpits, engines, factories, crowds, storms), makes a contact sheet, and you approve what goes in (the War library flow).
Downloads start only after you approve the list.

---

## 5. Flow, the Rep Theory / Jung way

**Bible** (one reading of the whole narration, rules only, like `reptheory/bible.py`): eras and their look · aircraft per airline per
era · livery per era (catalog colours + `livery_notes`) · places with landmarks · unnamed cast by role · the story's motifs · mood per
chapter. Every Flow prompt carries it.

**Consistency** (Jung's references, max 3 per prompt): a **hero image per airline aircraft per era** (every sticker and shot uses it;
the livery check retries wrong colours) · a **cast sheet** for unnamed people (captain, crew, officials as roles) · **place plates**
per airport / city. Approved in the Visuals tab, kept in the shared library.

| Flow images (free — used generously) | Flow videos (credits — asked once per film, with an option to make only some) |
|---|---|
| F1 aircraft stickers per airline × era × type, flags-with-hands, uniforms, props (tickets, timetables, cash, cargo) — die-cut on black, cut out in code | V1 sim-look aircraft shots: take-off, cloud, rain approach (built) |
| F2 era plates (sepia 1940s, 1960s colour) where no real photo exists | V2 image-to-video: an approved still comes alive (terminal crowd, propellers) |
| F3 unbuilt / future aircraft (JetZero, Boom, 777X) | V3 cast moments with the cast sheet (captain checks fuel, crew boards) |
| F4 explainer plates under code labels (engine cutaway, fuel tanks, hub bank) | V4 operations b-roll in the livery (cargo, hangar, de-icing, refuelling) |
| F5 card pictures where no clip exists | V5 illustrative reconstructions of places (a board room with two flags) |
| F6 place plates · F7 metaphor pictures from the motifs · F8 cabins by class and era | V6 sticker-to-real: the camera pushes into a sticker and lands on a real-looking shot of it |
| F9 thumbnail candidates (offered after Render, never automatic) | |

**Flow + code:** Flow paints, code states facts (numbers, names, dates, labels, maps); prompts say no text / logos / letters; one look
line per film. **Picture quality gate** (local, no extra render time): garbled text, livery, repeats (dHash), aspect, blur → retry once
with the reason, then a code graphic. **Agent-mode batches**: all a film's images in one batch; videos after the credit question.
**Library first:** Flow is spent on the library once per airline, so later films cost little.

---

## 6. Retention (video side)

| Moment | On screen |
|---|---|
| first 30 s | the strongest pictures dress the opening (best clip, hero sticker, most dramatic graphic); a picture change every 1–2 s; the narration's question gets big type (S16); the first 5 s match the thumbnail |
| every 60–90 s | turn lines ("But there is a catch…") get a re-hook: stage wipe, big type, a sound hit, a beat of silence before; no turn for 90 s → the picture makes one (new look, teaser, chapter card) |
| always | never more than 8 s of the same kind of picture; year badge (story) or clock + fuel (flight) on screen; the stage keeps building |
| the answer line | the opening's visual comes back (callback) |
| the end | next-episode card when the last line points at another story (built) |
| packaging | 3 thumbnail variants from the hero sticker / Flow plate + 2–3 code words |
| after publishing | import YouTube Studio's retention CSV, map dips to the picture on screen, tune the planner's limits |

A **visual retention check** runs before render and fixes what it can (one kind of picture too long, text cards in a row, slow
opening, a card held too long).

## 7. Sound

Pop / whoosh on every sticker, a typewriter tick on the year badge, a low hit on re-hooks, music that changes per chapter mood,
a short silence before the biggest reveal; flight chapters stay calm (no whooshes, like Vistara). Uses the app's SFX library and beds,
-14 LUFS, the theory-style lowered levels.

## 8. CSV and prompt

Existing: `mode`, `airline`, `aircraft`, `from`, `to`, `time`, `fuel`, `altitude`, `article`, `radio`, `graphic`, `url`,
`asset_type` (`flow_video`, `flow_image`, `web_screenshot`).
New: `mode` = `story`; `owners`; `split`; `person`, `role`; `search`; `local`; `graphic` values for S1–S18 (`hook`, `split`, `flags`,
`ownership`, `logo`, `fleet`, `portrait`, `handwriting`, `paper`, …); `asset_type` = `web_capture`. The prompt asks for real URLs only
(never invented) and Flow prompts that describe era, livery, phase of flight and camera.

## 9. Speed and output

1080p like the references (renders are 1280×720 today); each sticker drawn once and moved (cached sprites); chapters rendered in
parallel (chunked, built); searches, storyboards and web captures in parallel at Generate; elevation tiles prefetched in the background
at Generate; the app uses the script's sentences, not Whisper fragments, for cards.

---

## 10. Build order (on top of 4120ab6; each step code + tests, one still sheet to check; nothing renders until asked)

| # | Step | Credits / downloads |
|---|---|---|
| 1 | **Stage engine**: scene graph (enter / move / exit / stay across lines, cached sprites), sticker edge, shadow, float; channel style tokens (palette, type, sound set) | none |
| 2 | **Story mode + year badge + logo cards + timeline bar** (S2, S3); router `story`; catalog `founded`, `defunct`, `parent`, `successors`, `previous_names`, `livery_notes` | none |
| 3 | **Code-drawn stickers** (aircraft by body type in livery, flag set, props) as every sticker's fallback; restyle the 12 graphics into the sticker look (S18) | none |
| 4 | **Split tree, ownership, flag argument + bubbles, who-got-what** (S4, S5, S8, S12) | none |
| 5 | **Political map + route-map card** (S6, S7); **portrait + quote, fleet card, icon stat, handwriting, flight title, photo card, big type, paper sticker** (S9–S17) | none |
| 6 | **Flight-look gaps**: instrument close-ups, picture-in-picture on the map, airspeed tape, report / court pages (B15–B18) | none |
| 7 | **Source router + web search & capture**: search, scroll / element / data captures, real photos cut into stickers, credits on everything; CSV `search`, `local`, `web_capture` | web pages only, at Generate |
| 8 | **Shared library + b-roll library build** with contact sheet and your approval | downloads after you approve |
| 9 | **Bible** + Flow prompt builder v2 (bible + line + look line; references attached) | none |
| 10 | **Hero aircraft + cast sheet + place plates** with Visuals-tab approval; **picture quality gate**; Flow stickers cut out (F1) replacing code ones where approved; F2–F8 | Flow images (free) |
| 11 | **Retention pass**: opening dress, re-hooks, 8 s rule, callback, visual retention check | none |
| 12 | **Sound design** per element and beat | none |
| 13 | **Look transitions** (stage ↔ flight map ↔ news cards) | none |
| 14 | **Flow videos** V2–V6 under the credit question | Flow credits, asked |
| 15 | **1080p**, **thumbnails** (F9), **retention CSV import**; CSV prompt updated for every new column | none |
| 16 | A history test film in the sticker look, only when you ask | render, asked |

Steps 1–6, 9 and 11–13 are code only (no Flow credits, no downloads, no renders).

## 11. Open questions

- Style name: "Aviation" (working name).
- More references: only 1:22 of the Plane Curious video is usable and the sticker look has 1 reference (the rule is 8+); more videos
  would firm up pacing.
- 3D aircraft: download one free airliner GLB (needs your OK), or keep Flow for aircraft shots.
- Whether the `story` look is the default for every history / business film or chosen on the app page.
