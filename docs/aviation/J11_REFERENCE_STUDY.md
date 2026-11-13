# Reference study — "How China Turned Russia's Su-27 Into the J-11" (2026-11-13)

File: `~/Desktop/How China Turned Russias Su-27 Into the J-11.mp4` — 20:18, 1920x1080, 29.97 fps. Studied for patterns only;
nothing is copied (no frames, no wording, no channel mark). Frame sheets: `out/ref_j11/` (git-ignored). Only the picture was
studied here (no transcript yet).

## 1. Measurements

| What | Value |
|---|---|
| Cuts (scene change > 0.3) | 181 in 20:18 |
| Median shot / mean | 4.2 s / 6.6 s; 20 % of shots under 2 s |
| First 60 s | 8 cuts (calm open: a few long, moving shots) |
| Screen share (estimated by eye from 150 frames sampled every 8 s) | real footage ~45 %, dark-card graphics ~35 %, 3D aircraft renders ~15 %, maps ~5 % |

The pace comes from motion inside a shot (bars filling, counters, a camera drift over a 3D model), not from fast cutting. Real
footage and graphics alternate every one or two shots; no look runs longer than ~15 s.

## 2. Visual grammar (what it uses and when)

| # | Template | Look | When |
|---|---|---|---|
| J1 | **Footage + chips** | full-screen real footage; a small caps chip top-left saying what / where / when ("UKRAINIAN SU-27, 2011"); a tiny source line bottom-right; sometimes one orange stat chip lower-left ("-70 %", "NOV 2015", "$2-2.5 BN") | every claim about a real aircraft or event; ~45 % of the film |
| J2 | **3D aircraft over a cloud sea** | clean CG aircraft flying over white clouds, slow drift; 1-2 callout labels with leader lines | introducing a type; "what it is" lines |
| J3 | **3D hangar studio** | aircraft model in a bright white hangar: dimension line ("~22 M"), part callouts (rudders, flaperons), x-ray / exploded parts in translucent blue, fuel tanks shown as a yellow overlay on a top view | "how it works" and "what changed" lines |
| J4 | **Dark dossier cards** | graphite backdrop with a faint grid; title top-left in small caps with a short orange rule above it and a grey source line under it; one idea per card | every number, comparison, quote or condition |
| J4a | share bar | one long bar split orange (China) / light blue (Russia), big % on the right, an aircraft silhouette under it | "how much was Chinese" |
| J4b | range bar | a bar between two values with ticks ("$1.2 BN ... $2.7 BN"), a red note "no official figure" | estimates that disagree |
| J4c | icon grid + big number | rows of small aircraft icons filling in, a big number on the right ("26", "200", "~270") | counts of aircraft |
| J4d | timeline with markers | thin axis with years, labelled markers popping in, a stopped line ending in a red x ("kits: stopped 2003") | dates, two programmes compared |
| J4e | two option cards | side by side, coloured left rule each ("BUY AIRCRAFT" / "BUY A LICENCE"), silhouette in each | choices, before / after |
| J4f | quote card | big quote mark, the line in caps, red-orange left rule, small attribution; two claims stacked to show they disagree | statements, official positions |
| J4g | newspaper card | cream paper card with the outlet's name and the headline typeset (not a screenshot), translation note | "the press said" |
| J4h | flow list | two columns (RUSSIA / CHINA) with arrows running between rows of items | what moved from one side to the other |
| J4i | family tree | variant cards (name + one line + silhouette) added one by one | aircraft families, variants |
| J4j | silhouette reveal | grey silhouette with "?", then the real top view slides in | "what it became" |
| J4k | single part in 3D | one object (turbine blade, nozzle) turning slowly on the dark card, short labels pointing at it | technical explanations |
| J5 | **Dark map** | dark land, a curved route line drawing between two cities with date chips, a country filled red (USSR 1991), a world map with one country in orange | where / political change |
| J6 | **Framed photo over its own blur** | an archive photo in a thin white frame, the same photo blurred and darkened behind it, chip top-left | old photos that are not 16:9 |
| J7 | **Infrared / targeting footage** | grey FLIR video with tracking boxes and HUD marks | intercepts, encounters |

**Colour = side.** Orange / yellow is always China, light blue is always Russia, red is warnings and stops, grey is neutral.
The same colours run through bars, maps, cards and chips, so a viewer reads who is who without labels.

**Typography system.** The same small caps chip style is used on footage, cards and maps; titles always sit top-left with the
same orange rule; source lines are always tiny and grey. That consistency is what makes 20 minutes feel like one film.

## 3. What we have vs what it adds

| Reference piece | Closest piece we have (built) | Gap |
|---|---|---|
| J1 footage + chips | YouTube director + `cards.tag_source` (Source tag) | the what/where/when chip top-left and the stat chip lower-left on footage |
| J2 3D over clouds | Flow videos (sim look) | a code-rendered aircraft over clouds (whatif-engine GLB) — optional, Flow covers it |
| J3 3D hangar | none | biggest new piece; needs a GLB per type (or Flow stills + code callouts as a first step) |
| J4 dossier cards | `gfx_air` (blue news skin), `gfx_sticker` (sticker skin) | a third skin: graphite dossier cards J4a-J4k |
| J4f quote / J4g newspaper | `story_cards2` portrait + quote, `paper` sticker, blue article card | dossier quote card, typeset newspaper card |
| J4j silhouette reveal | none | new card |
| J5 maps | `story_maps` political + route map, flight map | date chips on route lines; already close |
| J6 framed photo over blur | `photo_card`, `photo_full` | the blurred-self background variant for non-16:9 photos |
| J7 infrared | none | a FLIR look filter for footage (grey, contrast, HUD box) — only for real FLIR-like clips |
| colour = side | `style.py` palette | a per-film side map (country / airline -> colour) used by every graphic |

## 4. Balancing it with v1 (nothing old is dropped)

The Aviation style now has looks from four references; the narration still picks per line and the **balance director** keeps
the mix. Target shares for a history / business film (measured on the plan before render, like the sticker-stage balance):

| Look | From | Target share |
|---|---|---|
| real footage (+ J1 chips) | Plane Curious, J-11 | 35-45 % |
| sticker stage (stickers, year badge, logo cards, splits, flags) | sticker reference | 20-30 % |
| dossier cards J4 (numbers, comparisons, quotes, conditions) | J-11 | 15-20 % |
| full-screen photos / Flow era pictures | sticker reference, J-11 J6 | 10-15 % |
| maps (political, route, flight + HUD) | Vistara, sticker, J-11 | 5-10 % |
| blue news cards (article windows) | Plane Curious | 5 % |

Rules: no look longer than ~15 s; the same template never twice in a row; a number line rotates between the dossier skin, the
sticker skin and the news skin by chapter, so all three are used in one film; colour = side across all skins.

## 5. Build order (each step code + tests, a still sheet to check; nothing renders until asked)

Status 2026-11-13: step 1 skipped; steps 2-7 built (commits 0ece0b1, 02a6ef9, 101e5b2, 38c75f1 + the FLIR look). Not yet seen in a
real Generate + render.

1. ~~Footage chips (J1)~~ — skipped (user, 2026-11-13: not needed; footage keeps its plain Source tag).
2. **Dossier skin (J4a-J4f, J4h, J4i):** graphite backdrop + title system; share bar, range bar, icon grid, marker timeline,
   option cards, quote card(s), flow list, family tree — fed by the router's values like `gfx_air`.
3. **Side colours:** a per-film map from countries / airlines to colours, read by every graphic.
4. **Newspaper card (J4g), silhouette reveal (J4j), framed photo over blur (J6).**
5. **Balance director v2:** the share targets above measured on the plan; it swaps skins / looks to meet them.
6. **Single part / hangar callouts (J3, J4k):** first as Flow stills with code callouts; a GLB hangar only if asked.
7. **FLIR look (J7)** for clips whose title says infrared / FLIR / targeting pod.
8. A test render only when asked.
