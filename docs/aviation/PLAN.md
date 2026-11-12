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

## 6. Open questions

- Style name: "Aviation" (working name).
- More references: a clean Air France copy plus 6+ more videos would firm up NEWS pacing beyond the first 1:22.
- 3D aircraft: free CC0/CC-BY airliner GLB sourced once (needs the user's OK to download), or skip 3D and use footage only.
