# War Documentary: what the reference videos do, and what to add

Studied 2026-10-31. Reference B: *THIS IS MASSIVE: 1,500 European Troops Prepare for Ukraine as Russia Tests NATO* (21:02, 1280x720, 30 fps).
Also compared with reference A (*2,250 Russian Casualties in One Day*) and our render #047.
Method: a frame every 4 s across the whole video (315 frames), full-size frames at key moments, and ffmpeg shot-cut detection.
The shares below are estimates from the sampled frames, not measurements.

These are patterns to adopt as blueprints, not a look to copy.

## What reference B is made of

| Part | Share of time (est.) | What it looks like |
|---|---|---|
| Political map with cards building up | ~50% | Dark navy sea and a faint grid; every country in the story has its own flat color; cards stack on the right |
| Cinematic footage (AI-generated, labelled) | ~30% | Moody, desaturated, filmic shots: ships, convoys, jets, ministries, press rooms, chess, dominoes |
| Flat 2D icon explainers | ~12% | Simple icons on a blurred photo: scales, Kremlin, refinery, ship on waves, clock and jet, wall of shields |
| Chapter cards and flag transitions | ~5% | "CHAPTER TWO" yellow chip over footage; a full-screen waving Ukrainian flag between parts |
| Big-number cards | ~3% | Huge yellow figure over the map, with a white label and a source line |

**Pacing:** 105 hard cuts in 21 minutes, but the screen never sits still. A map "shot" lasts 20-90 s and changes every 2-4 s:
a new card, a pulse, a zoom, a highlighted country. Footage cuts come every 3-6 s.
Our render #047 had 12 stretches with nothing on screen; the reference has none.

**Constants on every frame:** a channel logo bottom-left, "ILLUSTRATIVE MAP — APPROXIMATE POSITIONS" top-left on maps, and an "AI-generated illustration" note bottom-right on generated footage.

## The list: what to add to the tool

Ordered by impact on the next video. ✅ = we already have something close; the item says what to change.

### A. Maps (half the video, so the biggest win)

1. **One color per country across the whole video.** Russia red, Ukraine blue, then Germany gold, Poland teal, Belarus brown, France purple, UK pink, and so on.
   A country keeps its color in every map. Today `tac_map` uses either political (blue/red) or tactical with no per-country fills.
2. **Only the countries the narration names get a fill.** The rest stay dark grey, so the eye goes to the story.
3. **A map stays up and builds** for the whole stretch of narration about one place (20-90 s), adding a layer every 2-4 s instead of cutting away.
   Every sentence adds one thing: a card, a pulse, a route, a zoom, a newly filled country. This is the main fix for "still screens".
4. **A card stack on the right**, top to bottom, each card timed to the word that triggers it:
   - dark card: bold title + small subtitle (`17 OCTOBER` / "the jets went up")
   - white card: a fact with a sentence of context (`NO EARLIER CASE FOUND` / "a vessel sent down inside a NATO country's economic zone")
   - blue card: what our side says or has (`BULGARIA: A NATO MEMBER`)
   - red card: the threat or the bad news (`POWER PLANTS · BARRACKS · DEFENCE COMPANIES`)
   Older cards stay while new ones arrive, at most four, then the stack clears.
5. **Event markers on the map:** a pulsing ring and a burst at a strike, a dashed circle for a zone (economic zone, range, no-fly area),
   small drone arrows flying in, dashed routes for troops or supplies (UK → Germany → Poland → Ukraine).
   ✅ `tac_route` and glyphs exist; add the pulse, the zone circle and many small arrows moving.
6. **Camera moves per beat:** start on Europe, zoom to the Black Sea, then to Varna; pull back out when the story changes place.
   ✅ Map framing exists; tie each zoom to the next place the narration names.
7. **A source stamp on the map:** an angled red-bordered ribbon, `ACCORDING TO HUR`, `ON HOLD`, `ARTICLE FOUR`, at the moment the source is named.
   ✅ `kit_stamp` / `kit_ribbon` exist; allow them over maps, angled, carrying the narration's own source words.
8. **Two-number comparisons on the map:** `18 vs 6`, `106 vs 18` in large type over the country, with a label under each number.

### B. Numbers and text cards

9. **Big number over the map, not on a grey plate.** `over 1,000` / "SUSPICIOUS DRONE SIGHTINGS" / "since the start of 2025 · federal criminal police".
   The label is always what the number counts, and the line under it is the source named in the narration.
   ✅ `kit_bignum` / `lay_stat_split` exist; put them on the current map or footage.
10. **Ratio cards:** `8 in 10` VESSEL STRIKES IN THE BLACK SEA. Detect "x in y", "x out of y", "x%".
11. **Speaker card** when a named person or organization is quoted: name in bold, role underneath (`MICHEL HOFMAN` / "Belgian analyst").
    Shown over footage or the map, top-right.
12. **Dateline card** when the narration gives a date: `17 OCTOBER` + the clause after it.
13. **Chapter cards:** a yellow `CHAPTER TWO` chip with a short white subtitle, over a cinematic shot, wherever the script says "chapter", "part" or makes a clear topic jump.
    ✅ `_TOPIC` already finds "chapter"/"part"; give it its own card instead of a small NEXT ribbon.
14. **Short hook phrases as angled labels** on footage: `STAY SUPPLIED`, `ON GERMAN SOIL`, `NOT WAITING FOR PERMISSION`.
    Three or four words from the narration, white with a red border, slightly rotated. ✅ This replaces the plain yellow `kit_tag` strip that made #047 look empty.

### C. Footage

15. **Footage from the CSV's searches.** Done today: the CSV's `prompt` column is fetched through the app's own providers into the Visuals tab.
16. **A labelled cinematic AI-footage option** for scenes with no real footage: Flow video shots in a moody, desaturated look, always marked "AI-generated illustration".
    The CSV prompt would add a `flow_video` asset type for symbolic shots (chess pieces, a dark ministry, a press room, a ship at night).
    We already have Flow and the `ai_generated` class in `footage_match`; this needs a CSV column and a look preset. Ask before using credits.
17. **One color grade on all footage:** desaturated, teal shadows, a little grain and vignette, so stock, YouTube and AI shots look like one film. ✅ `kit_grain` exists; add a LUT step.
18. **Footage cuts every 3-6 s inside a footage scene:** two or three shots per scene when the clip pool allows, never one clip for 10 s or more.

### D. Explainer scenes (new kind)

19. **Flat icon explainers on a blurred background** for ideas that are not a place or a number:
    a balance with flags on each side (four countries vs one), the Kremlin with a question mark, a refinery with an arrow to a flag,
    a ship on waves with `INSURANCE` → `TRADE STOPS PAYING`, a clock with a jet (`~18:00`), a wall of shields with small fast arrows getting through (`SMALL · SLOW · CHEAP`).
    Build these from a small set of icons (ship, jet, drone, missile, tank, factory, refinery, Kremlin, flag, clock, calendar, balance, shield, soldier) placed by templates.
    ✅ `kit_sticker` icons exist; this needs a scene template that lays three or four of them out and animates them.
20. **Full-screen waving flag transition** (0.5-1 s) between chapters, using the flag of the country the next part is about.

### E. Always-on frame elements

21. **Channel logo bottom-left** on every frame (from the user's channel name / logo setting).
22. **"ILLUSTRATIVE MAP — APPROXIMATE POSITIONS"** top-left on every map. ✅ We have this; keep it.
23. **"AI-generated illustration"** bottom-right on any generated shot. ✅ Badges exist; use the same small corner text.

### F. Rules for the planner

24. **No more than 3-4 s without a change on screen**, anywhere in the video. Check this after planning and repair it, never just report it.
25. **Never a grey plate when a map is possible:** with no footage, fall back to the current chapter's map (zoomed on the last place named) and keep building cards on it.
26. **Card text is always the narration's own words**, shortened, never invented. Numbers come with their unit and source, or are not shown.
27. **One clip at most twice in a video**, never twice in a row. ✅ `footage_match.MAX_USES` already does this.

## Suggested build order

1. Map building: items 1-5 and 24-25. This fixes the empty look in most of the video.
2. Card set: items 4, 9-14 (the dark/white/blue/red stack, speaker, dateline, chapter, hook labels).
3. Footage grade and multi-shot scenes: items 17-18.
4. Icon explainer template: items 19-20.
5. Optional AI cinematic footage through Flow: item 16 (needs credits; ask first).

Each step gets a synthetic test (a short scripted plan checked for on-screen changes every 4 s and per-country colors), not tuning for one video.
