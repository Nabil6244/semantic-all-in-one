# Voxel Map: image cards (plan, 2026-11-05)

Status (2026-11-05): decision = cards from the CSV AND auto-planned, CSV wins.
Phases 1-2 BUILT, uncommitted: `card` rows (lib/beats_csv.mjs), timing from words/seconds (lib/timeline.mjs), drawing + layout
(lib/hud.mjs `cardRect`, `reservedBoxes`, `drawCard`), image loading (page.js), file resolving and serving (render.mjs `--cards dir`),
tests in test/cards.test.mjs. Anchors supported: tl, tr, ml, mr, center (ml/mr are the free sides used automatically).
Phases 3-4 BUILT (uncommitted): voxelmap-engine/cards.py (auto planner: one named thing per card from the narration, <=1 per 12 s,
none on the globe opening / scenes under 6 s, always one in a scene over 15 s; CSV card rows present = nothing planned; fetch through the
app's AssetManager as commons_image rows, no Gemini; story_cards.csv written for the engine; credits lines), ui/voxelmap_section.py
(Generate fetches into the Visuals tab, Render uses what the tab holds), visual_bridge owner "voxel_map". Tests: test_voxelmap_cards.py.
NOT built: phase 5 (card kinds). Not yet checked in a real still frame or a live fetch.

## Goal
While a scene is spoken, a photo card (portrait, painting, artefact, ruin, map of the battle) slides onto the voxel
scene, shows *what* the narrator is talking about, and leaves. The voxel world says where; the card says what. Same idea
as Hybrid's MAP+FOOTAGE `card` rows, built the same way: assets come through the Visuals tab, the render reads them.

## What Hybrid already gives us (reuse, do not rebuild)
- `hybrid/plan.py` `Support` (asset, t, place, label, hold, anchor), `MAX_CARDS = 3`, anchors tr/tl/br/bl/ml/mr/center.
- `hybrid/beat_csv.py` `card` rows, `t` found by matching the card's words in the voice-over transcript.
- `hybrid/app_integration.py` turns cards into Visual Plan rows ("beat b3 · supporting card 2"), with Stock / Flow / YouTube
  sources, Retry, Change source, Local clip, Skip.
- `visual_bridge.py` (fill / restore / rows / records) is the standard route for engines that render on their own page.
  Voxel Map does not use it yet (`ui/voxelmap_section.py` has no Visuals step).
- Museum inset in `voxelmap-engine/lib/hud.mjs` + `page.js` already draws a canvas image over the scene with fade in/out.
  Cards reuse that drawing path.

## Phases

### 1. Data: `card` rows in the story CSV
- `lib/beats_csv.mjs`: new row type `card` (beat, asset, label, place, t, hold, anchor, `words`) with the same columns
  Hybrid uses. `asset` is a search query or a local file. Validate in `render.mjs --check` (max 3 per beat, anchors valid,
  hold fits inside the beat).
- `t` is optional. When empty it is found from `words` (a few words of the sentence it illustrates) in the existing
  narration alignment (`tools/narration_timing.py`); if not found it appears a little after its beat starts.
- Tests: parsing, limits, timing from words, missing words fall back (never stop the render).

### 2. Draw: card layer in the HUD
- `lib/hud.mjs`: `drawCards(g, cards, t)`: framed photo (white border, slight tilt, drop shadow), caption strip in Monocraft,
  slide-in from its anchor edge, 0.5 s fade, gentle Ken Burns inside the frame, optional leader line to the card's `place`
  (project lon/lat through the current camera; hide the line when the place is off screen).
- `page.js`: preload card images into bitmaps before the frame loop (like the museum icons); pass active cards each frame.
- Layout rules in one pure function (testable): no overlap with the date panel, caption log, hotbar, museum inset; two
  cards at once take different anchors; a card never covers the beat's focus point (use the camera's projected target,
  move the card to the opposite side); size scales with output height.
- Tests: layout never overlaps reserved HUD boxes at 720p/1080p; cards keep out of the focus point; timing windows.

### 3. Automatic cards (no CSV rows needed)
- Planner step in the Python layer (`voxelmap-engine/runner.py` plan job, mirrors `hybrid/director.py`): for each scene
  pick up to 1-2 card subjects from the narration: named people, battles/treaties, landmarks, artefacts, dates. Skip
  scenes with a landmark already built in 3D, and scenes under ~6 s.
- Pacing rule: at most one card per ~12 s overall, none during chapter cards or the globe opening, and at least one card in
  any scene longer than ~15 s (the same long-scene gap that made the first minute feel static).
- CSV-supplied runs make zero Gemini calls (house rule): when the CSV carries `card` rows, no auto planning runs.
- Query writing: reuse Hybrid's `clean_place` and its photo-query helpers so searches are specific ("Romulus and Remus
  Capitoline Wolf bronze", not "Rome history").

### 4. Assets through the Visuals tab, ending on Export
- Add the Visuals step to the Voxel Map page like other styles: Generate (scenes + card requests) -> Visuals tab
  (`visual_bridge.fill/rows/records`, owner `voxel_map`, folder `state/voxel_map/assets`) -> Render reads `records` ->
  Export.
- Sources: Stock images and Wikimedia Commons first (free, attributable), Flow images optional (app-wide switch).
  Never one generated asset per render for decor; cards are story-specific so fetched, then cached by query.
- Credits: add each card's source/licence to the end-credits panel automatically (Commons requires attribution).
- Sourcing failures: a card with no image is dropped silently (logged), the render never stops.

### 5. Variety and quality
- Card styles by kind: portrait (tall, sepia), artefact (square on plinth colour), document/map (wide), painting (gilt
  frame). Chosen from the card's kind, not random.
- Vision check is off for CSV runs; for auto runs only the cheap relevance gate Hybrid uses (title/caption word match).
- Reject tiny images (< 600 px short side), watermarks/stock logos by source filter.

## Order and size
1. CSV rows + parser + tests (small). 2. Card drawing + layout + tests (medium, the visual core). 3. Visuals tab wiring
(medium, copies Hybrid/pakMap pattern). 4. Auto planner (medium). 5. Card kinds (small).
Phases 1-2 give working cards from a hand-written CSV with local images; 3-4 make it automatic.

## Checks before calling it done
- Touched tests only (house rule): beats_csv, hud layout, narration alignment, visual_bridge for voxel owner.
- One still-frame check at 1080p of each card kind over a ground scene, a map scene and a globe-to-map descent.
- No change to scenes without cards (renders identical), no new per-frame cost beyond one drawImage.

## Open questions for the user
- Cards only from the CSV, or also auto-planned from the narration? (Plan assumes both, CSV wins.)
- Image sources allowed: Commons + stock only, or Flow-generated illustrations too for things with no photo (ancient
  events)?
- Corner cards (Hybrid style) or larger centre cards for key moments?

## Picture relevance (2026-11-05)
Openverse returned snapshots and doodles for bare names (a board-game box for Hannibal). Fetch now tries the Wikipedia lead picture first
(`cards.wiki_picture`: search the article, name must match its title/description, no disambiguation pages, Wikimedia Commons files only so
non-free local images are never used), files it in the Visuals manifest with a Wikimedia credit, and only searches stock for cards Wikipedia
has no picture for. Names are classed person/place/event/other for the stock query. Live check: Hannibal, Roman Senate, Carthage, Scipio,
Pompey and Mark Antony all got the right picture.

## Follow-ups built (2026-11-05)
- Planned cards that Wikipedia has no picture for are dropped (no stock guess); CSV-authored cards still use the stock search.
- Phase 5 done: frame by kind in lib/hud.mjs `CARD_STYLES` (photo print, portrait sepia, painting gilt, artefact plinth, document parchment); mr card centre moved to 0.60 H so tall cards clear the museum inset.
