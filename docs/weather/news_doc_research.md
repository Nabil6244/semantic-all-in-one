# News Doc: research before building (2026-10-14)

Goal: make videos like `videoplayback (6).mp4` (SoCal coast / Storm Rachel, 19:26) with our tool, footage-first, NOT another PakMap.
Everything below was measured locally (ffmpeg, faster-whisper, reading our code). No paid service was used.

---------------------------------------------------------------------------------------------------------------------------------
## 1. The reference, element by element

### 1.1 Edit
- ~227 cuts in 19.4 min (sensitive count) -> a new shot every ~5 s. Median shot 4.2 s; bursts of 1-2 s shots in the cold open and the
  climax; longest ~35 s (a wave shot under a long sentence).
- Map: ONE shot (17:20, flat 2-D vector map, US blue / Mexico red, "1,109 KM", "Southern California", "Baja California"). Not satellite.
- Footage: ~1/3 local TV news (CBS LA, KTLA 5, FOX 5, NBC 4, ABC7, 10News, KCAL, AP, Global) with the station's lower third and logo
  left on; ~2/3 drone/stock b-roll and interviews. News audio is always muted: only the narrator speaks.
- One news upload is reused for several shots (the CBS LA Long Beach flooding report appears 5+ times at different moments).
- Hard cuts. Glitch transitions (RGB slices, white flash) between parts (0:30, 2:27).

### 1.2 Graphics (21 kinds seen)
| # | Element | Look | Motion | Trigger in the narration |
|---|---|---|---|---|
| 1 | Place tag | black box bottom-left, white bold NAME + small grey sub ("ALAMITOS PENINSULA / Long Beach, California") | fade in | a place named for the first time |
| 2 | Yellow tag | yellow pill, black caps ("CRYSTAL COVE", "CALIFORNIA COASTAL ACT") | slides in from the right | a place or a law/agency |
| 3 | Big number | huge white heavy number + small caps label under it ("400K CY / sand placed in Carlsbad", "26 COTTAGES") over footage | slides in with motion blur | one big number |
| 4 | Corner number | white number top right + tiny sub ("$55M", "$4-6.7M", "$50,000") | counts up | a price / cost |
| 5 | Big year | huge white year ("2019", "2026", "1950") | wipes in digit by digit | a year |
| 6 | Ring gauge | cyan ring with % in the middle + white label chip ("90% / chance of very strong El Niño") | ring fills 0 -> 90 | a percent / chance |
| 7 | Line chart | dark navy full screen, title caps, white line with labelled points, red last point ("CARLSBAD SAND VOLUME") | line draws in | numbers that change over time |
| 8 | Bar chart | dark navy, vertical cyan bars with value labels, one bar turns green ("BEACH ROAD HOMES TAGGED 10 / 7") | bars grow, highlight | 2-3 amounts compared |
| 9 | Horizontal bars | dark navy, coloured bars ("NEWPORT BEACH PROPERTY VALUES 20M / 10M / 3.4M") | bars grow | ranked amounts |
| 10 | Checklist card | paper card, red header ("5 WEEKS, 6 COMMUNITIES"), handwritten items ticked one by one, over footage | items tick on their words | a list |
| 11 | Quote card | white heavy caps, 1-3 phrases in red boxes ("...CANNOT REPLACE WHAT STORMS REMOVE.") on black or over dimmed footage/interview | words appear | the key line of a section |
| 12 | Pull quote | serif italic quote + "COUNCIL MEMBER" attribution beside a person | fade | a quoted person |
| 13 | Name tag | orange bar + condensed white name + handle ("JULIE LAUGHTON") | slides in | a person speaking |
| 14 | Chapter title | huge white word over footage ("RETREAT") or caption bottom-left ("THE PRIVATIZATION OF COASTAL DEFENSE") | fade | a new section |
| 15 | Side panel | footage pushed to the left ~45 %, dark panel right with title + 3 bullets ("THE CONVEYOR BROKEN") | panel slides | an explanation with steps |
| 16 | Framed picture | a still/clip inside a thin frame on dark navy + caption ("KELVIN WAVE", "LONG BEACH", "PROPERTY VALUE") | slow push | a thing with no footage |
| 17 | Polaroids | pinned polaroids on paper texture + taped label ("TWO TYPES OF LOSS: UNDERMINING / INUNDATION") | drop in | a two-way comparison |
| 18 | Dossier | a case-file card with a red-circled name ("STORM RACHEL") | zoom | the storm/person introduced |
| 19 | Three rings | three outlined circles with words ("INSURANCE / RECORD / REPAIRS") on black | pop one by one | "three things..." |
| 20 | Connection board | yellow lines joining photo thumbnails ("RAIL LINE / BOARDWALK / HIGHWAY") | lines draw | things that are linked |
| 21 | Diagram | white sine wave with dots and labels ("HIGH TIDES ... TROPICAL SWELLS") | draws in | a mechanism |
Also: a growing green square chip over news footage ("$282.7B real estate in the impact zone"), a flat 2-D map (§1.1).

### 1.3 Story (from the transcript)
| Time | Part | What it does |
|---|---|---|
| 0:00 | Cold open | "Stand on the sand at..." one street, its prices, what broke last weekend, hard numbers |
| 1:14 | Widen | the same thing in 6 places in 5 weeks; the question; "and El Niño hasn't even started" |
| 1:59 | Subscribe ask | one sentence |
| 2:08 | Why | how the system works, how it broke, this year's extras, the physics |
| 4:40 | Framework | two ways it hurts (undermining vs inundation) |
| 5:32 | Place by place | in date order, each with date + number + a person/quote |
| 8:33 | Like ask + escalation | "the last five days are where it gets expensive" |
| 8:41 | Climax | the storm itself, place by place; "the knowledge was there" |
| 10:48 | Debate | the two sides, the law |
| 12:43 | The choices | armor, sand, or retreat, each with money |
| 15:56 | Fairness | what worked |
| 16:24 | Blame | five suspects, each answered |
| 17:34 | Picture it | "from a window on any of those streets" |
| 17:56 | Thesis | the baseline moved |
| 18:54 | Questions | 4 open questions + "tell me in the comments" |
Every sentence carries a place, a date or a number: that is what makes clip search and graphics automatic.

---------------------------------------------------------------------------------------------------------------------------------
## 2. Our tool today (what I read)

### 2.1 The pipeline
`beats.csv` (Hybrid beat CSV, 26 columns) + `weather_layers.csv` (or one 24-column `plan.csv` split by the app)
-> `weather.autofix.repair_beats` (anchors, modes, places, alignment) -> `hybrid.beat_csv.plan_from_csv` (vo_anchor -> seconds)
-> `layer_rows` + Weather Intelligence auto rows -> `load_snapshot` + `check_fresh` (NWS data REQUIRED)
-> windows / payload -> Teamplate edit (`apply_plan`, cutaways) -> `keep_map_under` (50 %) -> `keep_moving`
-> `fix_footage` + `footage_problems` -> `hybrid.generate` -> pakMap generator -> AssetManager fetches `stock_video:` / `youtube_video:`
(Visual Plan table, manifest cache) -> weather-engine renders every frame in a browser (footage-only frames now skip it).

### 2.2 What already exists and can be reused
| Need | We have | Where |
|---|---|---|
| YouTube search, ranking, transcript-matched timestamp, segment download (real Chrome playback, no full download) | yes | `providers/youtube/` (`YouTubeProvider`, `ytdlp_backend`, `strategies`) |
| `youtube_video:` assets in a plan, manifest cache, Retry / Change source / Local clip in the Visual Plan table | yes (Hybrid Map) | `pakmap/sourcing.py`, `hybrid/generate.py` |
| Event relevance: date window + place in the title | yes | `weather/news/footage_pool.py` |
| Hard cuts, ~5 s shots, keyword card with red box, chapter card, count-up number, tags, dips | yes | `weather/teamplate/`, `weather-engine/lib/layers/tp_*.mjs` |
| Graphics drawn over footage (`overFootage`) | yes | weather-engine plugins |
| Numbers spoken -> digits ("forty seven million") | yes | `weather/intel/numwords.py`, pakMap matcher |
| Script <-> transcript alignment, anchor repair | yes | `weather/autofix.py` |
| Footage-only frames skip the browser | yes (today) | `pakmap-engine/lib/footage_pass.mjs` |
| Bar chart, timeline, before/after, explainer | yes (data-bound) | `post_bars`, `post_timeline`, `post_beforeafter`, `explainer` |

### 2.3 What blocks this kind of video today
1. **Weather refuses YouTube**: `weather/footage.py` allows only stock + approved clips; `fix_footage` turns `youtube_video:` into stock.
2. **Data is mandatory**: Generate stops without `resolved.json`, and `check_fresh` stops on expired alerts (#005). A coast-erosion story has no NWS data.
3. **Map-first plan**: every beat is `mode=map` in the prompts; footage is a cutaway. Map share 50 % at best.
4. **Teamplate hides tags over footage** ("generic stock is never captioned as the event") - with real news clips the reference does the opposite.
5. **Numbers on screen must come from an API** (Weather counters). The reference's numbers come from the script (news reports).
6. **The CSV is hard for an AI**: 24 columns, exact empty cells, anchors - most of our #005/#006 failures were CSV shape and anchors.
7. **YouTube volume**: Modern Tech run 2 sent ~39 searches + 39 downloads and got 429 / DNS errors; the run aborted.
8. **Clip moment**: the transcript match picks where the anchor SAYS the words - often the studio anchor, not the pictures.
9. Missing graphics: #2 yellow tag, #6 ring, #7 line chart (general), #10 checklist, #12 pull quote, #13 name tag, #15 side panel,
   #16 framed picture, #17 polaroids, #19 three rings, #20 board, glitch transition, flat 2-D map.

---------------------------------------------------------------------------------------------------------------------------------
## 3. Design: "News Doc", a footage-first style (not a PakMap copy)

Principle: the **story CSV is a shot list**, the map is one shot kind among many (<= 10 %), graphics come from the sentence.

### 3.1 A simpler CSV for the AI (11 columns, one row per sentence)
```
sentence,vo_anchor,part,shot,search,graphic,g_text,g_value,g_items,place,when
s1,Stand on the sand,cold_open,news,"Long Beach Alamitos Peninsula flooding October 2026",place_tag,ALAMITOS PENINSULA,,,"Long Beach, CA",2026-10-09
s2,It is a wall made of wood,cold_open,broll,"old wooden boardwalk bulkhead beach",,,,,,
s3,houses that sell between,cold_open,broll,"luxury beach houses aerial",corner_number,ON THE PENINSULA,$4-6.7M,,,
s7,Six communities five weeks,widen,broll,"southern california coast aerial",checklist,"5 WEEKS, 6 COMMUNITIES",,"Dana Point homes tagged;Carlsbad parking lot destroyed;...",,
```
- `shot`: news | broll | interview | map | card. `search` = place + event + month for news, filmable words for broll.
- `graphic` is optional: the tool picks one from the sentence when it is empty (3.3). The AI may override.
- The tool compiles this into the Hybrid plan itself (beats, clips, layers): the AI never writes the 24-column format again.
- The old Weather CSVs keep working; this is a new file (`story.csv`) for the new style only.

### 3.2 News clips: few requests, many shots
- Group sentences by event (place + month). ONE search per group (~10-15 per 20-min video, not 60).
- Rank results with what we have: title relevance + `footage_pool` date window + place in title; prefer local stations, 1-6 min uploads.
- From the best 2-3 videos of a group, download ONE longer piece each (~40 s, after the anchor intro), then cut all shots of the group
  from it locally (ffmpeg scene cuts). 60 shots -> ~25 downloads.
- Pick the moment by pictures, not words: inside the 40 s, skip low-motion stretches and the first seconds (studio anchor); never reuse the
  same 3 s twice; mute.
- Everything cached in the project (`_work/news_cache/`: searches, ids, pieces): a re-render asks YouTube nothing.
- One request at a time, 3-5 s apart; on 429/bot check: wait, retry once, then the group falls back (3.4). The render never stops.

### 3.3 Auto graphics from the sentence (deterministic, no AI)
| Sentence has | Graphic | Check |
|---|---|---|
| a place first named | place tag (news shot) / yellow tag | place found in gazetteer |
| one money/size number | big number or corner number | the number is SAID at that moment (numwords) |
| a year | big year | said |
| a % or "chance" | ring gauge | said |
| 3+ numbers of one thing over dates | line chart | all said in the beat |
| 2-4 amounts compared | bar chart | all said |
| "first ... second ... third" / a list of places | checklist or three rings | items said |
| the last line of a part / a short punchy sentence | quote card (red on 1-3 key words) | max 1 per part |
| a new part | chapter title | from `part` |
| "X said / according to" + a name | name tag / pull quote | name said |
Rules: a number on screen is always one the narrator says (no invented data); max 1 big graphic per ~15 s; no kind twice in a row;
>= 8 kinds per video; graphics sit on footage (dimmed), not on a map.

### 3.4 Errors: never stop, always fall back, always a note
| Problem | Fallback chain |
|---|---|
| no news result / blocked | another video of the same group -> broll of the place -> broll of the subject -> framed still card |
| clip too short | cut the next shot earlier; never loop |
| same clip twice | next moment of the same video, then next video |
| anchor not heard | whole-script alignment (have it) |
| place unknown | nearest known place (have it), else no tag |
| number not said | graphic dropped, note |
| no weather data / expired alerts | data graphics left out (archive mode), video continues |
| bad CSV row | that row skipped with a note naming it; never the whole video |
| render failure on one graphic | that graphic dropped (engine validate), video continues |
A final **quality report** next to the video: map %, shot length, graphic kinds, news vs broll share, every fallback used.

### 3.5 The map shot = the Normal style's map clip (decided 2026-10-14)
- `shot=map` uses `map_scene` (the map the Normal / Overscaled / Exp Solar styles use): prompt
  `Parent > Focus > Inner | camera: zoom_in | label: TEXT | style: dark` -> map-engine renders an ordinary MP4 (NASA Blue Marble,
  glowing borders, label, push-in), marked as a map clip (holds its last frame, never loops), cached.
- In News Doc it is just another clip in the footage timeline: rendered before the plan is built and handed to Hybrid as a local file,
  so no change to PakMap / `pakmap/sourcing.py` (which has no `map` source) and no PakMap-engine map at all.
- Places come only from map_scene's bundled data (countries, states/provinces, named regions, US counties); the AI place resolver is
  NOT passed (no credits). A place it cannot find -> the shot becomes broll of the place, with a note.
- In story.csv: `s40,storms spinning up off Mexico,blame,map,"North America > Mexico > Baja California | camera: zoom_in | label: 1,109 KM",,,,,,`

### 3.6 Render
- Same weather-engine (graphics) + footage shortcut: frames that are only a clip skip the browser, so a footage-first video renders fast.
- Glitch transition as a new engine piece; no change to PakMap files.

---------------------------------------------------------------------------------------------------------------------------------
## 4. Build order (each step tested before the next; ask before each commit)
1. **Unblock**: News Doc style key; allow `youtube_video:` in it; data optional; tags allowed on news footage.
2. **story.csv -> plan compiler** + its autofix (row skipped, never the video) + tests.
3. **News clip harvester** (group search, one long piece per video, local shot cutting, cache, pacing, fallbacks) + tests with recorded answers.
4. **Auto graphics** from sentences + number-said check + variety rules.
5. **Graphics batch 1** (most used): place tag, big number/year, corner number, quote card, chapter title, checklist, ring, bar/line chart, name tag.
6. **Graphics batch 2**: side panel, framed picture, polaroids, three rings, board, pull quote, glitch.
   Map shots: Normal-style map clips (§3.5), wired in step 2.
7. **Prompts**: script prompt (the 15-part story) + story.csv prompt.
8. **Real test**: 3-minute piece of your story with your voice; compare against the reference with the same measurements as §1.

## 5. Open choices for you
- Style name: "News Doc" (new style card) or a mode inside Weather Teamplate.
- ~~Map look~~: decided, the Normal style's map clip (§3.5).
- Clip length per news shot: 2-6 s (reference) - default 4 s.
