# Cinematic Explainer — multi-reference research (Phase 0)

Status: research only. No application code changed, no production assets made, nothing committed.

## 0. How the references were inspected, and the limits

Method: each video was played in the built-in browser and **9 frames were captured at fixed fractions of its length** (2 %, 8 %, 17 %, 27 %, 38 %, 50 %, 62 %, 75 %, 90 %) and read on one contact sheet. Video was 360p. Reference A (the supplied war video) was analysed far more closely (175 cuts, 208 frames every 4 s, 12 full-resolution frames) in [war_explainer_reverse_engineering.md](war_explainer_reverse_engineering.md).

**What this does not show:** nothing about motion (easing, duration of a reveal), sound, or what happens between the 9 samples. Motion claims below are marked *(not observed)* and need Phase 1 to be settled from slower frame-by-frame captures of a few short passages. Small type is low confidence at 360p.

**Brief requirement not met:** the brief asks for 8–10 videos and two per direction. **Seven were inspected** (A plus six below). Not inspected: Vox chart video (a pre-roll ad blocked playback), RealLifeLore, Caspian Report, and any kinetic-typography reference, so **direction E (kinetic typography) has no video evidence** and is marked INVESTIGATE. Web searches for production breakdowns returned little; the only usable source was the Storybench interview with Vox's Sam Ellis, and only its summary (the full text was truncated).

| ID | Direction | Video | Creator | Length | URL |
|---|---|---|---|---|---|
| A | A geopolitics | Putin's General BREAKS SILENCE… | (supplied file) | 13:52 | local file |
| B1 | A / C documents | The Operation Northwoods Conspiracy, Explained | Johnny Harris | 14:27 | https://www.youtube.com/watch?v=8AHOgvsno5Q |
| B2 | A military | DIY Drones: War Will Never be the Same | Johnny Harris | 19:50 | https://www.youtube.com/watch?v=iE18uraHOcs |
| B3 | A / presenter + data | Putin's Energy War Against Europe, Explained | Johnny Harris | ~20 min | https://www.youtube.com/watch?v=ws0Ela-kdTs |
| C1 | B / D maps | The conflict in Kashmir, explained | Vox | 10:08 | https://www.youtube.com/watch?v=cyayif_nla8 |
| C2 | D maps, restrained | How Taiwan is Preparing to Get Invaded | Wendover Productions | ~16 min | https://www.youtube.com/watch?v=2iHPVsyv4GU |
| C3 | F illustrated | This Is What a Godlike Civilization Would Look Like | Kurzgesagt | 14:12 | https://www.youtube.com/watch?v=QW_jlUn4gA8 |

Background source read: [Storybench, Vox Atlas producer Sam Ellis](https://www.storybench.org/vox-atlas-producer-sam-ellis-on-his-map-animations/) (summary only): maps combined with news clips, photos and data visualisations; a single episode can take five weeks.

## 0b. Re-check after approval (2026-10-27)

The sheets were re-read and Reference A's three key graphics were re-extracted at 5–10 fps. **Measured motion for reference A** (frame steps of 0.1 s, so ±0.1 s):

| Graphic | Measured behaviour |
|---|---|
| Footage under a card | the footage is already dark/blurred on the first frame of the shot; at the cut from clear footage to a card shot it dims over **~0.2 s** (35.6 s clear → 35.8 s dark). During a long list the backdrop keeps darkening slowly |
| Source card | fades in over **~0.3 s** with a small upward slide (4.7 s → 4.9 s); the whole sentence is shown at once in **pale grey**, then **words turn dark in sequence at the narrator's pace** (~0.1–0.3 s per word). It is not typed in; this corrects my earlier "typed" wording for source cards |
| Number card | kicker tag appears first (35.9 s); the figure **counts ×1 → ×4 in 0.1 s steps (~0.4 s)**, settles on ×5 by 36.5 s; the label fades in at 36.1–36.3 s; the red rule **draws left to right over ~0.5 s** (36.3 → 36.8 s); then holds still |
| List card | title first, then **one row per narrated item, rows 5–6 s apart** (53.0 s, 58.5 s, third later), each row fades in over ~0.3 s; earlier rows stay |
| Portrait card | on near-black backdrop, held static ~1 s after settling (34.5–35.5 s) |
| Lower-third caption | present from the first frame of the shot (3.0 s) in some shots; types in word by word in others (0:16–0:20) |

Corrections to this file after the re-check: Wendover length is about 17 min (last sample at 15:14 = 90 %), Johnny Harris Energy War about 21 min. In the second Johnny Harris Northwoods sheet the time labels are unreliable because two sampling runs overlapped, so only the **content** of those frames is used (document highlighter, archival B&W, layered photos), not their times.

## 1. Per-reference findings

### A. Supplied war explainer
See the dedicated file. In short: footage dimmed and blurred under cards, red kicker tag, number cards, numbered lists revealed row by row, paper source cards with highlighter, circle portraits, lower-third headline on most footage shots, a dark map revisited five times; average shot 4.7 s; −14 LUFS, voice always on.

### B1. Johnny Harris, Northwoods (documents)
- **Look [observed]:** off-white **paper texture with a faint dot-grid** behind everything graphic; scanned typed documents full frame, with a **yellow highlighter bar** over the key phrase and a **hand-drawn red pen circle** around a date or phrase ("13 March 1962" circled in red); a small pencil icon bottom-right of document frames.
- **Photos [observed]:** archival photos placed as **layered cut-outs on the paper**, two overlapping (colour JFK + B&W JFK), not full-frame; B&W archival film is shown with contrast and a vignette.
- **Evidence flow [observed]:** the document is shown, zoomed to the line, highlighted, then pulled back; portraits of the officials shown in a row with caption names ("General George Brown…").
- **Presenter and a phone mock-up** appear in the sponsor segment (not relevant).
- **Motion *(not observed)*:** highlighter and pen circle are drawn on progressively in the finished video; the speed is unknown.
- **Verdict:** the **highlighter + pen-circle evidence treatment is the strongest idea found** and fits our paper source card.

### B2. Johnny Harris, DIY Drones
- **[observed]:** in all 9 samples there is **no graphic at all**: real location footage, interviews, FPV footage, a presenter in an office. Graphics are rare here.
- **Verdict:** supports the brief's "preserve clean footage and quieter moments"; a style that puts a card on every 5th shot would be heavier than this reference.

### B3. Johnny Harris, Energy War
- **[observed]:** presenter on a set with a map wall; a **red data line composited into the room around him** (Price of Natural Gas 2022); a **screen-recorded Wikipedia page** used as evidence; interview clips with **subtitle plus a name tag** ("Protester").
- **Verdict:** screen-recorded source (page, headline) as evidence = ADAPT into the source card. Presenter compositing is out of scope (no presenter in our tool).

### C1. Vox, Kashmir (maps and data journalism)
- **Map look [observed]:** **dark relief-shaded terrain**, desaturated fills (muted green and rust), a **white stippled disputed-border line**, small labels in boxes ("Pakistan", "Princely states"), **icon circles** (rifle, tank) on the map, a **circle portrait with a name plate** ("ADIL AHMED DAR") with arrows connecting it to icons.
- **Camera [observed across frames]:** world dot → continent with fills → zoom into region → tight on the territory; **each frame is a different zoom level**, so the camera is moving through the story.
- **Archive / interviews [observed]:** protest photo full frame, B&W UN footage side-by-side, street interview with a **white name lower-third** ("Ghadaf Zehra"); a **Vox logo bug top-right on every frame**.
- **Motion *(not observed)*:** fill spreading, border drawing, zoom easing.
- **Verdict:** ADAPT relief map skin, icon circles and linked portrait callout for Hybrid Map; our red/blue country fill from reference A is closer to the news look, Vox's muted fills read as more serious.

### C2. Wendover, Taiwan (restrained map and satellite)
- **[observed]:** mostly real footage; **satellite imagery with a coloured translucent band and two small labels** ("airstrip" overlay, ~10:29); a **sepia engraved old map**; a **satellite view with tight labelled area**; no card-heavy look at all.
- **Verdict:** ADAPT satellite + translucent band + two labels for "what is this place" scenes; confirms the restraint principle.

### C3. Kurzgesagt (illustrated systems)
- **[observed]:** fully illustrated, **saturated colour** per scene, speech bubbles on characters, a **dark blue isometric blueprint** of a megastructure (10:38), **labelled two-pane comparison** ("Large Scale / Small Scale" chips).
- **Verdict:** its identity (saturated flat characters) is REJECT; our footage-led style must not look like it. ADAPT: **chip-labelled split-screen comparison** and a **blueprint line-drawing diagram** for infrastructure (refinery, air defence rings) — the latter would be a new asset type and is INVESTIGATE for cost.

### Not inspected
RealLifeLore, Caspian Report, Vox charts, kinetic typography references: **no observations**. Everything about them in earlier notes is from search snippets and is not evidence.

## 2. Comparison matrix

| Technique | A war | B1 Cuba | B2 Drones | B3 Energy | C1 Vox | C2 Wendover | C3 Kurz |
|---|---|---|---|---|---|---|---|
| Footage dimmed/blurred under card | ● | – | – | – | – | – | – |
| Paper / document source card | ● | ● | – | ◐ (screen rec) | – | – | – |
| Highlighter on evidence | ● | ● | – | – | – | – | – |
| Hand-drawn pen circle | – | ● | – | – | – | – | – |
| Circle portrait + name plate | ● | – (row of photos) | – | – | ● | – | – |
| Number / stat card | ● | – | – | – | – | – | – |
| Progressive chart | ● bars | – | – | ● overlay | – | – | – |
| Map with fills | ● | – | – | ◐ wall | ● | ◐ satellite | – |
| Lower-third shot headline | ● | – | – | – | ◐ (interview names) | – | – |
| Logo/bug | – | – | – | – | ● | – | – |
| Clean footage periods | ◐ (60 %) | ● | ●● | ● | ● | ●● | n/a |
| Subscribe pill | ● ×3 | – | – | – | – | – | – |

● seen · ◐ partly · – not seen in the 9 samples (a technique absent from 9 samples may exist elsewhere).

## 3. Decisions

| # | Technique | Decision | Reason |
|---|---|---|---|
| 1 | Dimmed + blurred footage under cards | **ADOPT** | Seen only in A, but it is what makes cards belong to the footage; cheap to render once per card |
| 2 | Paper source card + yellow highlighter | **ADOPT** | A and B1 both use it; strongest evidence idea |
| 3 | Red pen circle / underline drawn on a document | **ADAPT** | B1 only; implement as a drawn ellipse on the card, never on a real scanned document we do not own |
| 4 | Layered cut-out photos on paper with slight offset | **ADAPT** | B1; for the "X versus Y" evidence scenes (existing `polaroid_board` is the base) |
| 5 | Number card in red/yellow, count-up | **ADOPT** | A; existing templates |
| 6 | Numbered list revealed row by row + recap | **ADOPT** | A; existing templates |
| 7 | Circle portrait + name plate | **ADOPT**, only with a verified portrait | A and C1 |
| 8 | Linked callout (portrait with arrows to icons) | **INVESTIGATE** | C1; needs reliable place anchoring on the map |
| 9 | Dark map with relief + muted fills | **ADAPT** | C1 and A; skin on the existing Hybrid Map engine, no new map engine |
| 10 | Map revisited at chapter changes | **ADOPT** | A (5×), C1 progression |
| 11 | Satellite crop + translucent band + two labels | **ADAPT** | C2; only where a satellite/aerial asset of that place exists |
| 12 | Shot-headline lower third on most footage shots | **ADAPT (reduce)** | A does it on ~60 %; B2/C2 use almost none. Target 30–40 % so quiet moments remain |
| 13 | Logo bug in a corner | **REJECT** | Channel branding is not a style feature; Doc Style already has an optional watermark |
| 14 | Subscribe pill with cursor click | **REJECT by default**, optional | Brief says no automatic engagement prompts; offer as a manual setting only |
| 15 | Presenter on a set with composited chart | **REJECT** | No presenter |
| 16 | Kurzgesagt saturated illustration identity | **REJECT** | Different style identity |
| 17 | Chip-labelled split comparison | **ADAPT** | C3; fits the "X vs Y" extractor |
| 18 | Isometric / blueprint diagram | **INVESTIGATE** | C3; needs a new asset type, cost unknown |
| 19 | Kinetic typography (masks, word emphasis) | **INVESTIGATE** | No video evidence gathered; keep to the existing typed-caption and word-by-word quote reveal until reviewed |
| 20 | Glitch effects | **REJECT** | Brief rules it out; keep `glitch_cut` unused |
| 21 | Parallax / camera push on photographs | **ADOPT (restrained)** | Ken Burns exists; evidence from B1's layered photos, motion *(not observed)* |

## 4. Open questions that block final numbers
1. Reveal durations and easing (highlighter sweep, number count, list rows). Plan: Phase 1 captures 2–3 short passages frame by frame (25 fps) from A, which we hold as a file, and measures them there; the other references stay style evidence only.
2. Whether the supplied war video's look was made in a template tool; irrelevant to the decision but affects how closely its timings can be copied.
