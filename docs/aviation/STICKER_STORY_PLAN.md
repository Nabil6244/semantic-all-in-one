> Superseded by MASTER_PLAN.md (2026-11-13); kept for its detail and history.

# Aviation "sticker story" look — plan (2026-11-13)

Reference: `~/Downloads/Why Singapore Airlines and Malaysia Airlines Split Apart.mp4` (6:56). Studied for patterns only; nothing copied.
A history / business explainer on black, built from die-cut "stickers": aircraft in livery, flags, logos, speech bubbles. It tells
*relationships* (who owned what, who split from whom, who argued with whom) where Plane Curious tells *numbers* and Vistara tells *a flight*.

## 1. What the reference shows

| # | Graphic | Look | When it is used |
|---|---|---|---|
| S1 | **Aircraft sticker** | side view in the airline's livery, thick white cut-out outline, soft shadow, slow float / tilt; on black | almost every beat: the airline "as a character" |
| S2 | **Year badge** | navy box top-right, spaced digits `1 9 6 3`, changes as the story moves | every dated beat; the clock of the story |
| S3 | **Logo card** | white rounded card: logo + name + years (`Malaysian Airways 1963–1966`), on a timeline bar with a moving dot | each new name / era of an airline |
| S4 | **Split tree** | one airline card branching into two (or merging), coloured lines, years on each | splits, mergers, spin-offs, rebrands |
| S5 | **Flag characters + speech bubbles** | flag stickers held by cartoon hands, white bubbles with the line's words (key words bold / yellow), the aircraft sticker between them tugged both ways | disagreements, negotiations, "X wanted…, Y wanted…" |
| S6 | **Dark political map** | black land, countries / regions filled red or blue, serif title (`British Malaya`), small labels | where, borders, independence |
| S7 | **Route-map card** | dark map, coloured route lines from hubs, legend + title top-right (`Scheduled Route Map`), a year | the network at a moment in time |
| S8 | **Ownership diagram** | logo at top, arrows down to owners (flags / logos, names, % shares) | who owns the airline, stake changes |
| S9 | **Portrait + quote** | round black-and-white portrait, name, role, a speech-bubble quote | a named person's words |
| S10 | **Fleet card** | title `The Fleet of X`, aircraft sticker, yellow count badge `3x Boeing 707-320` | fleet at a moment |
| S11 | **Icon stat** | big yellow line icon (chart, plane, globe) + one figure (`S$100 Million in Profit`) | a single number |
| S12 | **Split board ("who got what")** | a flag on top, a row of icons with captions: routes, aircraft stickers, HQ, reservation system | dividing assets / inheritances |
| S13 | **Handwriting** | a name written by hand on a card, then struck through and rewritten | names, rebrands, signatures |
| S14 | **Flight title** | big `SQ 108` between two airport dots, over a photo or sky | a named flight |
| S15 | **Photo card** | archive photo full frame, title top-left (`The Sarong Kebaya`) + small subtitle, `Credits: X – YouTube` lower-left | real people / places / objects |
| S16 | **Big type opener** | bold white words with arrows pointing at stickers (`Two Countries — One Airline`) | the hook / thesis line |

Pace: a new element every 2–4 s; elements slide / pop in on the same black stage rather than cutting away, so one "scene" builds up.

## 2. How it fits our storytelling

A third look inside the Aviation style, chosen per line by the narration router, next to the two we have:

| Story beat (router) | Plane Curious look | Vistara look | **Sticker look (new)** |
|---|---|---|---|
| business news, dated events | clips + blue article cards | — | — |
| numbers | blue graphics (bars, fleet grid…) | — | icon stat (S11) for a single figure in a history story |
| a flight | — | dark map, HUD, aircraft shots | flight title (S14) to open it |
| **history / relationships** (new mode `story`) | — | — | stickers, year badge, logo cards, split tree, flags + bubbles, ownership, maps |
| people | crew card / name card | crew card | portrait + quote (S9) for executives / politicians |

New router mode **`story`**: a line about founding, ownership, a split, a merger, a rebrand, a government or a country
(words: founded, formed, split, merged, joint, owned, stake, shares, government, independence, renamed, rebrand, flag carrier, national
airline; or a year far before the story's "now"). Up to now these fell into `news` and got clips that rarely exist for 1960s events.

## 3. What each graphic needs (no invention)

Everything comes from the narration, the CSV or the shipped catalog; nothing is made up.

| Graphic | Data | Source |
|---|---|---|
| S1 aircraft sticker | aircraft type + airline livery | catalog (body shape from `aircraft.glb`-style family: narrow / wide / jumbo / turboprop / old types), livery colours from `airlines.json`; drawn in code, no image needed |
| S2 year badge | the year the line is about | router dates / years; carried forward line to line |
| S3 logo card | airline name + years | catalog (+ new `founded` / `defunct` / `previous_names` fields); logo: a coloured tail-fin mark drawn from the livery (never a copied logo) |
| S4 split tree | parent → children (or parents → merged) | catalog `parent` / `successors` fields + the line's words ("split into", "merged with") |
| S5 flags + bubbles | two countries + what each wanted | flags drawn from a small shipped set (country code → flag drawing); bubble text = the line's own clause for each side ("Malaysia wanted…", "Singapore wanted…") |
| S6 political map | countries named | our dark basemap + Natural Earth country shapes the app already ships (War maps) |
| S7 route-map card | hub + destinations named / year | catalog airports; routes only between places the line names |
| S8 ownership | owners + shares | CSV column `owners` ("Malaysia 42.79% / Singapore 42.79% / BOAC / Qantas") or the line's own "% stake" phrases |
| S9 portrait + quote | name, role, quote | the CSV (`person`, `role`); photo only from the user's file or a fetched, credited picture; else a drawn silhouette |
| S10 fleet card | count + type | router counts + catalog type |
| S11 icon stat | one figure + its word (profit, routes, passengers) | router money / counts |
| S12 split board | who got what | CSV column `split` (side : items) — this one needs the script writer to spell it out |
| S13 handwriting | a name | the line's quoted / named brand |
| S14 flight title | flight number + two airports | router flight numbers + airports |
| S15 photo card | archive photo + title + credit | YouTube / web capture (footage director, still frame), credit from the source |
| S16 big type opener | the hook line's key words | the first line of a story stretch; CSV `graphic` = `hook` |

## 4. Build order (small, testable steps; nothing renders until asked)

1. **Sticker kit** (`aviation/stickers.py`): aircraft side views per body type in livery with the white die-cut outline and shadow;
   flags (a shipped set of ~40 country drawings: stripes, circles, stars — simple geometric flags first); a tail-fin "logo" mark;
   speech bubble; cartoon hand. Float / pop-in / slide motion helpers. Tests: outline present, livery colour used, flags by code.
2. **Year badge + logo card + timeline bar** (S2, S3) and the **`story` mode** in the router (with tests on real sentences).
3. **Split tree + ownership diagram** (S4, S8) + catalog fields `parent`, `successors`, `founded`, `previous_names` for the
   airlines we ship (MSA, SIA, MAS, Joon, Air France-KLM, IAG, Lufthansa Group…), CSV `owners`.
4. **Flags + speech bubbles** (S5): two sides, the line's own clauses in the bubbles, the aircraft sticker tugged between them.
5. **Dark political map + route-map card** (S6, S7) on the existing basemap; country shapes from the app's Natural Earth data.
6. **Portrait + quote, fleet card, icon stat, flight title, photo card, big type opener, handwriting** (S9-S16).
7. **Planner**: a `story` stretch is one black stage that builds up (stickers stay, new ones pop in every 2–4 s, the year badge
   ticks) instead of cuts; CSV `graphic` values for each; the CSV prompt learns `story`, `owners`, `split`, `person`.
8. One short test film on a history script (e.g. the MSA split or Air France–KLM), only when you ask.

Cost note: steps 1–7 are code + tests; checking the look costs one still sheet per step (no renders).

---

# Part 2 — Flow everywhere (images + videos), the Rep Theory / Jung way

Rep Theory reads the whole script once (`reptheory/bible.py`: cast, sections, the script's own names, the sentence each picture
needs) and Jung keeps one character identical across pictures with up to 3 reference images per Flow prompt (`reptheory/art.py`).
Aviation takes both ideas much further. Rule that stays: **Flow never fakes a real named event or a real person's face**; it
illustrates, reconstructs places and types, and every such picture carries a small `AI ILLUSTRATION` chip.

## A. The aviation bible (one reading of the whole script, rules only, no Gemini)

Before any picture is described, the script is read once into a bible that every Flow prompt carries:

| Part | What it holds | Why |
|---|---|---|
| eras | each section's years (1947, 1963, 1972, 2026) and the look of that era | a 1963 line gets a 1963 airport, uniforms and aircraft, not today's |
| fleet by era | the aircraft types the script names per airline per era (Comet 4, 707-320, 737-100; A380, 777F) | the right type on screen in every shot |
| liveries | each airline's livery per era (catalog colours + `livery_notes`: "yellow tail with the MSA bird", "white with gold cheatline") | Flow paints the right airline |
| places | airports and cities named, with landmarks (Changi control tower, Burj Khalifa skyline) | establishing shots look like the place |
| cast | the unnamed people of the story by role: captain, first officer, cabin crew, dispatcher, ATC, airline boss (as a role) | the same captain in every cockpit shot |
| motifs | the script's own recurring images ("two borrowed planes", "cash and cargo holding it up", "the split") | metaphor pictures come back as the story's visual thread |
| section moods | rise / crisis / split / recovery → light, palette, weather | the picture's mood follows the story |

## B. Consistency through reference images (the Jung pattern, at film scale)

1. **Cast sheet**: on Generate, one Flow image per unnamed cast member (front, in the airline's uniform of the era); approved in the
   Visuals tab; every later picture with that person attaches it as a reference (max 3 per prompt).
2. **Hero aircraft**: one Flow image of each airline's aircraft in its livery (side and three-quarter view); every later shot of
   that aircraft attaches it, so the livery never drifts between shots. A livery check (`footage.livery_score`) rejects and retries a
   picture whose colours are wrong.
3. **Place plates**: one establishing image per airport / city, reused behind place titles, route cards and photo cards.
4. Kept per project and, when approved, in a **shared library** (`assets/aviation/library/<airline>/<era>/`), so the next film
   about the same airline starts with its cast, aircraft and places already made (no per-video asset burden).

## C. Flow images: where they go

| # | Use | Example | Placed by |
|---|---|---|---|
| F1 | **Sticker library**: aircraft side views per airline × era × type, flags, uniforms, props (tickets, timetables, cash stacks, fuel trucks, cargo pallets) generated as die-cut stickers on black, background removed in code | the MSA 707 sticker, a Kebaya uniform sticker | sticker look (Part 1) |
| F2 | **Era illustrations** in the era's photo style (sepia / Kodachrome / 70s colour, film grain) | 1947 Kallang airport with a DC-3, a 1960s check-in hall | `story` lines with no archive footage |
| F3 | **Unbuilt and future aircraft** | JetZero blended wing at the gate, Boom Overture over the Atlantic, 777X folding wingtips | fleet lines about aircraft not yet flying |
| F4 | **Explainer plates** under code-drawn labels | an engine cutaway (bleed air, fan), fuel tank layout, a hub bank at dusk seen isometric | "how it works" lines; labels and arrows drawn by code, never by Flow |
| F5 | **Card pictures** | the picture inside a blue article / fact card when no clip exists | replaces today's text-only cards |
| F6 | **Place plates** | Dubai skyline with the airport, Changi tower, Paya Lebar in 1955 | place titles, route cards |
| F7 | **Metaphor pictures** from the bible's motifs | an A380 balanced on a stack of gold coins and cargo pallets ("cash and cargo are holding it up") | hook lines and section turns |
| F8 | **Cabin and service** by class and era | a 1972 first-class lounge, today's A380 shower spa | fleet / product lines |
| F9 | **Thumbnail candidates** | the film's hero aircraft + one bold idea, three variants | after Render, offered, never automatic |

## D. Flow videos: where they go (credits, so asked first)

| # | Use | Example |
|---|---|---|
| V1 | **Sim-look aircraft shots** (built) | take-off, climb through cloud, approach in rain |
| V2 | **Image to video**: an approved still from C comes alive | the 1963 terminal crowd moves, the DC-3's propellers turn, the coins stack grows |
| V3 | **Cast moments** with the cast sheet as reference | the captain checking fuel, the first officer on the radio, crew boarding |
| V4 | **Operations b-roll** in the airline's livery | cargo loading a 777F at night, a hangar check, de-icing, refuelling |
| V5 | **Illustrative reconstructions of places** (never the real event itself) | a 1970s board room with two flags on the table, a stormy approach to an unnamed runway |
| V6 | **Transitions**: the camera flies from a sticker scene into a Flow shot of the same aircraft | the sticker 707 becomes a real-looking 707 in flight |

## E. Flow and code together

- **Flow paints, code states facts**: numbers, names, dates, maps, routes and labels are always drawn by code over or beside the Flow
  picture; prompts always say "no text, no logos, no letters" (Flow's lettering is never trusted).
- **One look per film**: every Flow prompt ends with the film's look line (sim-look, era photo, sticker or explainer), chosen from the bible.
- **Picture director (quality gate, no extra render time)**: each Flow result is checked locally before it is used: text / garbled
  letters (War's frame text check), livery colours (`livery_score`), repeats (dHash), aspect and blur; a failure is retried once with
  the reason added to the prompt, then falls back to a code graphic.
- **Agent-mode batches**: all of a film's Flow images go to Flow in one agent batch (as Rep Theory does), videos after the credit question.

## F. Cost and control

- Images are free → used generously (every no-footage line can have a picture).
- Videos cost credits → counted per film and asked once ("12 Flow videos = 120 credits"), with the option to make only V1 / V3.
- The shared library means the 2nd film about an airline needs far fewer new pictures.
- `AI ILLUSTRATION` chip on every Flow picture in a history / news story; Flow is never presented as archive footage.

## G. Updated build order (Parts 1 + 2)

1. Sticker kit (code) — Part 1 step 1.
2. **Aviation bible** (`aviation/bible.py`): eras, fleet by era, liveries, places, cast, motifs, moods; tests on real scripts.
3. **Flow prompt builder v2**: every image / video prompt from the bible + the line + the look line; reference images attached.
4. **Cast sheet + hero aircraft + place plates** with the Visuals-tab approval and the shared library.
5. **Picture director** for Flow results (text, livery, repeats), retry once.
6. Year badge, logo cards, `story` mode (Part 1 step 2), now with F1 stickers and F2 era plates.
7. Split tree, ownership, flags + bubbles, maps (Part 1 steps 3-5).
8. Image-to-video (V2) and cast moments (V3) for hero beats; operations b-roll (V4).
9. Metaphor pictures (F7), explainer plates (F4), thumbnails (F9).
10. Planner: per line, choose footage → Flow → code graphic by what the line needs and what exists; CSV prompt learns the new columns.
11. One test film on a history script, only when you ask.
