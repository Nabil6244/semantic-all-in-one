> Superseded by MASTER_PLAN.md (2026-11-13); kept for its detail and history.

# Aviation style — plan (2026-11-12)

A **third, new style** ("Aviation") that mixes both references and lets the **narration choose the look of each moment**:
business and news lines get the Plane Curious treatment (fast real footage + blue article cards); flight, route, weather and
emergency lines get the Vistara 611 treatment (dark map, gold route, live clock/fuel display, aircraft shots).
Reference study: `docs/aviation/REFERENCE_STUDY.md`.

Rules this plan follows: test-first, smallest changes; additions only in `app.py` (check `test_fixtures/*_protected.json` first);
fetched assets go through the Visuals tab and renders end on Export (`visual_bridge.py`); a supplied CSV run makes zero Gemini
calls; nothing starts until Generate; no per-video asset generation (models/icons sourced once); no still screens.

---

## 1. Built on the War Documentary engine

The War engine already does narration → plan → shots + card layers, deterministically, with a reason for every choice:
footage discovery and matching, an article/document card (`lay_document`), speaker quotes, charts, big numbers, stamps, tags,
maps with routes and pins, Visuals-tab flow, parallel segment render, render QA, a -14 LUFS mix.

So **Aviation = the War engine with an aviation theme** (registered with `BUILT_ON["Aviation"] = "War Documentary"`, the way Cat Theory
sits on Rep Theory). War behaviour stays byte-identical when the theme is off. New code goes in its own package `aviation/`, and
the War engine gets only small theme hooks.

Reused as they are: planner core, semantics, footage discovery/director/QA, segments/render, audio mix, Visuals bridge.
Reused with a skin: `lay_document` (→ article card), map builder (→ dark aviation map), speaker card, chart, big number, stamp.
Borrowed from other styles: weather storm cells (Weather), 3D GLB rendering and camera rigs (`whatif-engine`), counters and
typeset (What If / gfx-core).

---

## 2. The narration router (the heart of the style)

Each sentence is classified into one **mode**, by rules plus aviation word lists (no Gemini when a CSV is given):

| Mode | Narration triggers (examples) | Look |
|---|---|---|
| **NEWS** (Plane Curious) | announced, ordered, deal, CEO, launched, profit, loss, strike, report says, a date + an airline | real footage bursts (1–2 s cuts) + blue article card every 10–20 s |
| **FLIGHT** (Vistara) | took off, climbed, descended, route, diverted, hold, fuel, minutes, feet, knots, runway, ATC | dark map + gold route + clock/fuel HUD, aircraft shots |
| **WEATHER** | storm, monsoon, hail, gusts, visibility, clouds | dark map + storm cells + weather icon list |
| **FLEET / TECH** | aircraft type names, engines, seats, range, wings | aircraft beauty footage, 3D aircraft turn, spec cards, seat-layout card |
| **NUMBERS** | money, passenger counts, percentages | big number / chart cards (existing) on the blue backdrop |
| **EVIDENCE** | investigation, report found, court, regulator | report pages with highlighted lines, redaction boxes |
| **PEOPLE** | captain, first officer, named executive | speaker card / name lower-third, typed counters for crews |

One video can use any mix. A business video stays mostly NEWS; an incident video stays mostly FLIGHT; an airline-history video
switches between them. Pacing follows the mode: NEWS cuts 1–2 s, FLIGHT holds 5–15 s on a map that keeps moving.

---

## 3. New pieces to build

| # | Piece | What it is | Builds on |
|---|---|---|---|
| N1 | **Aviation catalog** | airlines (name, IATA/ICAO, colours, hub), aircraft types (maker, seats, range, engines), airports (code, lat/lon, runway headings). Shipped data files, sourced once | War `catalog.py` format |
| N2 | **Narration router** | sentence → mode (section 2), plus extraction of times, fuel, altitudes, distances, flight numbers, places | War `semantics.py` |
| N3 | **Blue article card** | browser-window card on an animated royal-blue dot-grid backdrop; outlet logo or name, headline, date; name lower-third, fact strip with an icon, 2–4 window collage | War `lay_document` / `cards_kit` |
| N4 | **Source tag** | "Source: X" top-right on every borrowed clip | War provenance |
| N5 | **Dark aviation map** | desaturated relief, airport dots and labels, gold glow on the active place, gold dotted planned route / solid flown track, holding-pattern racetracks, distance callouts, range circle, crossed-out airports | War `map_build` / map-engine |
| N6 | **Flight HUD** | persistent top-left TIME / FUEL / ALTITUDE values plus the right-side fuel stack bar; values come from a per-sentence state timeline, tick between beats, turn red when critical | new; state follows the narration |
| N7 | **Radio subtitles** | speaker label + call line, two calls stacked, lower-left | What If typeset |
| N8 | **Small graphics set** | typed counters (139 PASSENGERS), weather icon list, place title with a "● RIGHT NOW" pill, side-view altitude schematic, speed tape, instrument warning box, briefing sheet with highlight + stamp, next-episode end card | gfx-core / War cards |
| N9 | **Storm layer on the map** | drifting cloud cells, gust/distance labels | Weather storm layers |
| N10 | **3D aircraft shots** | one airliner GLB (narrow + wide body), livery colours from the catalog, cameras: orbit, chase in clouds, wing view, top-down on the map, side profile. No pilots/cabin in v1 | `whatif-engine` GLB render |
| N11 | **Footage sources** | airline press/news clips (user allows news clips), stock aircraft footage, spotter-style beauty shots; per-mode search words | War footage discovery + footage library |
| N12 | **CSV + prompt** | optional CSV columns: `mode`, `airline`, `aircraft`, `from`, `to`, `time`, `fuel`, `altitude`, `article` (outlet, headline, date), `radio`; a prompt file that writes them | War CSV prompt |
| N13 | **App page + make_video** | style card, picker entry, Visuals + Export flow, make_video autorun | `ui/style_registry.py`, `visual_bridge.py` |

Left out of v1: cartoon analogy scenes, animated pilots/cabin interiors, real court-document fetching.

---

## 4. Build order (each step tested, one at a time)

1. **N1 + N2**: catalog and router, with synthetic tests: given sentences → expected mode and extracted values. No render.
2. **N3 + N4**: blue article card and source tag; a 10 s still-check render only if asked.
3. **N5 + N6 + N7**: dark map, route, holding pattern, HUD, radio lines; one short FLIGHT sequence test.
4. **N8 + N9**: small graphics and the storm layer.
5. **N11 + N12**: footage search words and CSV/prompt.
6. **N13**: app page, Visuals/Export, make_video.
7. **N10**: 3D aircraft (largest piece, last, so the style works without it; until then FLIGHT uses footage + map).
8. First full test video (business topic) and a second one (incident topic), only when the user asks.

---

## 5. Footage plan

**Source order for every sentence that needs footage** (the War engine's order, with an aviation library):
1. **Aviation library**: a one-time, reviewed b-roll folder (`library.py` format: `index.json` + `<subject>/<clip>.mp4`), no watermarks or subtitles.
   About 40 subjects: each common type in flight / take-off / landing / taxi (A320 family, 737, A220, 787, 777/777X, A350, A330, A380, 747, E-jets, ATR),
   airport aprons and terminals by hub, cabins (economy / business / first), cockpits, engines and wings, maintenance and factories, crowds and check-in, storms and runways in rain.
2. **Live YouTube news and press clips** (allowed): airline official channels, news outlets and plane-spotting channels, searched with the narration's own names
   ("Air France Joon launch", "Air France strike shirt 2015"). This is the main source for NEWS lines, because Plane Curious's open is real event footage.
3. **Stock** (Pexels / Pixabay, existing keys): generic airport, cabin, clouds, city, money shots.
4. **Flow AI video**: only for moments nobody filmed (a 1960s cockpit, a meeting room); labelled AI, never for a named real event.
5. **Graphics fallback**: an article card, map or number card, never a black or repeated frame.

**Match rules** (from text only, so a CSV run makes no Gemini calls):
- A sentence that names an aircraft type takes only a clip that carries that type (an A350 line never shows a 737).
- A sentence that names an airline prefers its livery: clip title and words first, then a cheap local frame-colour check against the catalog's livery colours.
- A named event (a launch, strike, crash, delivery) takes only a clip about that event; if none is found → article card for that event, not generic b-roll.
- A clip is used at most N times per video and never twice within a set gap (War reuse rule).

**Picking inside a clip**: the War moment director chooses the action part (rotation, touchdown, crowd surge), cuts away from logos, subtitles and talking heads
unless the line quotes that person, and slices 1–2 s pieces from different clips for NEWS bursts and 4–8 s pieces for FLEET beauty shots.
Every borrowed clip gets a small "Source: <channel>" tag.

**By mode**: NEWS = 3–6 real event clips per burst, cut on the stressed words, then an article card. FLEET = slow beauty shots of the named type and livery.
FLIGHT = the dark map carries the story; footage (or later the 3D aircraft) is cut in for take-off, clouds, approach, landing. WEATHER = storm, rain and windsock shots.
PEOPLE = press-conference clip or portrait with a name lower-third.

**Library build (once, not per video)**: a script lists candidate clips per subject from airline and spotter channels, makes a contact sheet,
and the user approves what goes in (same import/approve flow as the War library). The user's own flight-sim captures can be added as library subjects too.

## 6. Status (2026-11-12)

| Piece | Module | State |
|---|---|---|
| N1 catalog, N2 router | `aviation/catalog.py`, `router.py`, `data/*.json` | committed b7ecd5f |
| N3 article card, collage, N4 source tag | `aviation/cards.py` | committed 6e134ee |
| N5 dark relief map, route, holding, callouts, range ring | `aviation/basemap.py`, `flightmap.py` | built, uncommitted |
| N6 clock/fuel HUD + fuel bar, N7 radio lines | `aviation/hud.py` | built, uncommitted |
| N8 counters, weather icons, place title, briefing sheet, altitude side view, end card; N9 storms on map | `aviation/gfx.py`, `flightmap.py` | built, uncommitted |
| N11 search phrases, clip rules, livery check, cut lengths | `aviation/footage.py` | built, uncommitted |
| N12 CSV columns + prompt | `aviation/csv_rows.py`, `data/aviation_csv_prompt.txt` | built, uncommitted |
| Planner (modes -> timeline) | `aviation/planner.py` | built, uncommitted |
| Renderer bridge (plan -> Shot/Layer, card_table) | `aviation/bridge.py` | built, uncommitted; 4 s real render passes |
| N13 app page, Visuals/Export, footage director hookup, segmented long render, make_video | - | **next** (touches app.py / UI) |
| N10 3D aircraft | - | waits for OK to download one free airliner model |

Checked on the two reference narrations (Whisper timings, no render): Vistara plans ~68 % map / ~26 % footage (reference ~50 / 30),
end card found; Air France plans 35 cuts in the first minute (reference 27), a card every ~24 s without a CSV (reference 10-20 s;
a CSV with real headlines adds more), no generic search phrases left.
Known: elevation tiles download once per area (Kashmir took ~90 s the first time, then cached); prefetch them at Generate in the
background when the app hookup is built. Fragments from Whisper make some fact cards half-sentences; the app uses the script's sentences.

## 7. Source plan v2 (2026-11-13, after the first real render)

The first real render took the top YouTube hit per scene without looking at it: 5 of 10 clips were wrong (a studio desk, a channel
promo, a full-frame French subtitle, an unbranded wing, a cartoon safety video). The user's direction: **YouTube + Flow images +
Flow videos + website screenshots + cards**, each used where it fits.

### Five sources, chosen per scene

| Source | Used for | Never for |
|---|---|---|
| **YouTube** (checked) | named real events (strikes, launches, crashes), the named airline's real aircraft, airports, press conferences of named people | anything its frames fail on |
| **Website screenshot** | the article or report the line cites: the real page (headline + photo) inside the blue window, the key line highlighted | made-up pages: only a URL from the CSV |
| **Flow video** | the Vistara simulator look: the aircraft in the airline's livery taking off, climbing, in cloud, on approach in rain; cockpit with two pilots; cabin; storms over an airport | a named real event, a named real person's face |
| **Flow image** | a picture where no footage is needed or exists: the card window picture, an old aircraft type, an idea (a fuel gauge, a hub map at night) | a named real event or person |
| **Cards** | numbers, facts, quotes, evidence, the flight map and all its graphics | - |

### By mode

- **news**: 2-3 checked YouTube clips per line (bursts cut between different videos); a website-screenshot card for each cited article; fact cards between.
- **fleet**: YouTube beauty shots of the named type in the named livery; Flow video of that type and livery when YouTube has none that passes.
- **flight / weather**: map beats (5-10 s, re-framed per beat: wide for a route, close on the airport for storm / hold / approach) alternating with Flow video shots of the aircraft, cockpit and cabin; YouTube flight-sim clips are a second choice.
- **people**: unnamed crew -> Flow video (cockpit); named people -> YouTube press clip, else a name card (never an AI face of a real person).
- **numbers / evidence**: cards; a report line with a URL -> screenshot of the report page with the line highlighted.

### YouTube check (aviation footage director, reusing War's war-neutral parts)

1. Search several videos per scene (the CSV's searches + the sentence's own names), pooled and cached (`director_search.Searcher`).
2. Title / channel rules: must name the line's airline, aircraft type or event (`footage.clip_ok`); drop promos, trailers, safety videos,
   compilations, reactions, podcasts, interviews unless the line quotes that person; prefer English.
3. Storyboard frames before any download (`director_frames`): reject studio, text screens, subtitles / tickers, title cards, cartoons /
   flat graphics, still, dark; pick a clean uncut 3-8 s window away from the first / last 5 % (no channel intros).
4. Capture and check the captured seconds against the storyboard (`director_capture`).
5. Nothing passes -> Flow video (if the mode allows) -> card. Never a wrong clip.

### Website screenshots

CSV column `url` (article / report page). Headless Chromium (Playwright, already installed for Flow) opens the page, hides fixed
overlays (cookie bars, pop-ups: declined, never accepted), takes the top of the page at 1280 px, and the card shows it in the window with
the headline / key sentence highlighted (War's document highlight). A page that fails (paywall, block) -> the typeset card.

### Flow credits

Before Generate spends any Flow credits it shows how many Flow videos and images it will make and the credit cost, and asks yes / no
(like War). No: those scenes use YouTube or cards. All Flow prompts share one look per video (sim-style daylight, the airline's livery
from the catalog) so the shots match each other.

### CSV changes

`asset_type` adds `flow_video`, `flow_image`, `web_screenshot`; a new column `url`; the prompt file asks for real URLs only (never invented)
and for Flow prompts that describe livery, phase of flight and camera (chase, wing, cockpit, cabin, tower view).

### Build order

1. YouTube footage director with frame checks (+ 2-3 clips per news line).
2. Website screenshot capture + screenshot card.
3. Flow video / image routing with the credit question and one shared look.
4. Flight beats: map re-framed per beat, alternating with Flow / YouTube aircraft shots.
5. CSV + prompt update; re-run the same 2-minute film in the real app; clip sheet + side-by-side with the references.

### Status (2026-11-13, all built, uncommitted; waiting for the user's new script before a render)

| Step | Built in | Checked |
|---|---|---|
| 1 YouTube footage director | `aviation/director.py` (War's storyboard checks + capture reused) | 25 tests; real YouTube run: AP Archive protest, Joon unveiling, A320 cockpit, Vistara A320 in rain; nothing off-topic |
| 2 Website screenshots | `aviation/webshot.mjs` + `webshot.py`, `cards.lay_article(page=...)`, CSV `url` | 10 tests incl. a real headless browser on a local page (cookie bar hidden, never accepted) |
| 3 Flow routing + credit question | `aviation/flow.py`, `ui/aviation_section._make_flow` | 11 tests; one shared sim look; never a named event or person |
| 4 Flight beats | `planner._map_stretch` (clips cut into one continuous map), `flightmap.view_at` (re-framed per line) | 7 tests + real-terrain still |
| 5 CSV + prompt | `data/aviation_csv_prompt.txt` (flow_video / flow_image / url) | prompt-button test |
| 6 Routes | curved legs, glow, top-down airliner icon, legs drawn when said | tests + still |
| 7 Flight maps | Sentinel-2 cloudless 2016 imagery (CC BY 4.0) lit by the hillshade; missing tiles fall back to relief | tests + real still |
| 8 Animations | label pop-in when first named, count-up numbers, card exit, camera eases between framings | tests |
| 9 Graphics | 60 % card window + bigger type; CSV `graphic` column; RIGHT NOW place titles; altitude side view; weather sheet from the line's words; textured storm cells | tests |

Not done: renders are still 1280x720 (the shared renderer's size); 3D aircraft (N10) not built (Flow covers the aircraft shots).

### After the Emirates render (2026-11-13)

Fixed: black gaps (slices now use the clip file's real length), crew counters from '53.2 million passengers', podcast channels and
passenger-777 clips for freighter lines, the headline crop of page screenshots, pictures borrowed from other scenes (a line without its
own clip now gets an aviation graphic or a clean text card). Speed: searches and storyboards for all scenes in parallel, 2 capture tries per
scene, a 2 s clean stretch for news, the search cache shared across projects.

New aviation graphics (`aviation/gfx_air.py`), each triggered by the line's own numbers or words:
fleet grid, route network from the hub, seat map (load factor), then -> now bars, big number with an aircraft / freighter, timeline;
and, borrowed from the Green Dot Aviation reference (Eastern 855): crew card, instrument gauge, runway diagram, approach side view
(glide slope), descent graphic (knots / feet per minute), title card (CSV graphic `title`).

## 8. Open questions

- Style name: "Aviation" (working name).
- More references: a clean Air France copy plus 6+ more videos would firm up NEWS pacing beyond the first 1:22.
- 3D aircraft: free CC0/CC-BY airliner GLB sourced once (needs the user's OK to download), or skip 3D and use footage only.
