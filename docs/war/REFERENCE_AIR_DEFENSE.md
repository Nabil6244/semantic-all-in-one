# Reference study: "Ukraine's Air Defense" (21:00 geopolitical documentary) — 2026-11-08

Source file: `~/Downloads/Ukraines-Air-Defense-SnapYT.App.mp4` (third-party video; studied for patterns only, nothing copied).
Contact sheets, key frames and the word-timed transcript: `out/reference_air_defense/` (git-ignored, the repo is public).

## 1. Measurements

| What | Value |
|---|---|
| Length / format | 21:00, 1280x720, 30 fps |
| Cuts (scene detection) | 346, **mean shot 3.6 s, median 2.5 s**; 56 % of shots under 3 s, 9 shots over 15 s |
| Pace over time | 3.1-4.0 s per cut in every 3-minute block: no slow middle |
| Narration | 3,366 words, **160 wpm**, one narrator, continuous |
| Audio | **-14.4 LUFS integrated, LRA 3.9 LU** (heavily levelled), music bed under the whole film, only 2 pauses > 0.6 s in 21 min |
| Soundbites | 6 narration gaps of 5-11 s where a clip's own speaker is heard (Trump at 0:00, Zelensky 2:07 and 5:41 with burned captions ...) |
| Sync | on-screen words land on the spoken word (HEAT 21.8 s, 1 PERCENT 1:31, 44 MISSILES 7:00, SAMARA 12:32: within ~1 s) |

Approximate screen share (252 frames, one per 5 s): real footage ~60 %, article / post / infographic screenshots ~14 %, maps ~13 %
(flat political + satellite close-ups), speaker quote cards ~6 %, full-frame text and other graphics ~7 %.

## 2. Structure

- **Cold open (0:00-0:40)**: a real soundbite first (Trump, "It's a defensive weapon"), then the stakes in 4 sentences over 2-3 s cuts,
  each with a burned caption or one keyword ("HEAT", red "BALLISTIC"), ending on the problem line in a quote box
  ("AND HERE IS THE PROBLEM UKRAINE CANNOT SOLVE ON ITS OWN").
- **Body**: problem, then "Then Washington made its move", Russian strikes, the numbers, Europe's options, production. No chapter cards:
  the narration's own turns ("Then ...", "Meanwhile ...") carry the chapters.
- **End**: three audience questions, channel line ("This is the frontline media ..."), end screen pointing at two other videos.
- Subscribe pill pops up 3 times (6:05, 10:30, 20:50) over footage.

## 3. Visual grammar (the templates)

| # | Template | Look | When |
|---|---|---|---|
| T1 | **Source tag** | yellow box, black bold "Source: X \| @handle" / "SOURCE: DEFENSENEWS", top-right, on almost every clip and screenshot | every non-own visual |
| T2 | **Keyword label** | yellow box, black caps, top-left ("PATRIOT", "ISKANDER-M", "44 MISSILES", "UNFRIENDLY COUNTRIES", "FRIDAY 13 OCTOBER 2026 / 500 PAC-3 MSE") | the noun/number just spoken, ~1 per 15-20 s |
| T3 | **Quote caption box** | white box, black heavy caps, lower-centre, 2-3 lines ("AMERICA USED UP ABOUT HALF OF ITS OWN PATRIOTS ...") | quoted or reported speech, over footage |
| T4 | **Big word over footage** | one word or figure, very large, centred ("BALLISTIC" red, "HEAT", "1 PERCENT", "2.1 BILLION DOLLARS / PATRIOT MISSILES", "BORROW FIND AND BUILD") | the sentence's key word |
| T5 | **Article screenshot card** | real web article (headline highlighted yellow, key sentence highlighted orange), white page, slow push, over a blurred photo plate with topographic lines + crosshair circles; source tag | every cited report (~25 times) |
| T6 | **Social post / infographic card** | X post or infographic screenshot, same plate | a statement made on social media |
| T7 | **Speaker quote card** | black left panel, gold serif NAME, role in caps, quote typed word by word, round portrait in a white ring on the right | a named official's words (Raufoglu, Ihnat, Grynkewich, Novak, Zelensky) |
| T8 | **Lower-third name** | yellow/orange box, name + role, bottom-left | person on screen |
| T9 | **Framed video** | clip inside a bordered frame over a blurred copy of itself; vertical social videos centred with blurred side fill | social/vertical or press clips |
| T10 | **Split screen** | 2-3 clips side by side ("JUMPSTART") | parallel events |
| T11 | **Political map** | flat blue Ukraine / red Russia / magenta occupied **over satellite-relief texture**; teal tag labels with a pin dot; regions re-coloured or striped | geography, every few minutes |
| T12 | **Map + icons** | drone / missile / launcher icons (flag livery) flying in swarms; "1,214 DRONES · 29 OCTOBER" count; date banner "Sunday, 1st November 2026"; explosion icons on targets | attack nights |
| T13 | **Map + circle inset** | round picture-in-picture (ring) of a weapon or event pinned to a map place | what happened at a place |
| T14 | **Map + portrait link** | arrow from a region to a framed portrait with name ("SERGEI SOBYANIN · 862 drones towards Moscow") | the official responsible |
| T15 | **Satellite close-up** | Google-Earth-style imagery, pin drop, building footprint highlighted (pink), river label, place name letters animating in, distance line "260 Kilometers" | a specific site |
| T16 | **Unit / pictogram chart** | a row of missile icons, "1 PERCENT", infographic counts | stocks and ratios |
| T17 | **Transitions** | mostly hard cuts; white/pink light flashes, glitch on screenshots, zoom-blur | section turns, ~1 per minute |
| T18 | **Soundbites** | the clip's own audio with burned subtitles, narration pauses | key statements |

## 4. What we have, what is partial, what is missing

| Pattern | War engine today | Gap |
|---|---|---|
| Fast cutting (2.5 s median) | long shots split into 3-6 s pieces (rule 15) | **partial**: our cuts are 3-6 s; no 1.5-3 s rhythm on high-energy lines |
| Word-synced graphics | yes (word times) | ok |
| Cold-open hook | montage of the film's clips under the opening words (story.py) | **partial**: no soundbite first, no keyword/quote-box rhythm in the open |
| T1 source tag | footage chip / badge (status words), credits file | **missing**: no "Source: <channel/outlet>" tag from the clip's own metadata |
| T2 keyword label | kit_tag (hook phrase), kit_ribbon | **partial**: no noun/number label on the word, top-left yellow style |
| T3 quote caption box | kit_quote is full-frame | **missing**: quote/reported-speech box over footage |
| T4 big word over footage | kit_kinetic on a plate (dims footage) | **partial**: no single-word/figure punch over clean footage |
| T5 article card | lay_document (typeset page or a screenshot on a desk) | **partial**: no web-article look, no blurred photo plate, no headline highlight; **no way to capture a real article URL** |
| T6 social post card | none | **missing** |
| T7 speaker quote card | kit_quote, lay_figure_hero | **partial**: no typed quote + round portrait layout |
| T8 lower third | kit_speaker (white card, top-right) | ok (style variant possible) |
| T9 framed / vertical video | clips are scaled to fill | **missing**: vertical social clips are cropped instead of framed over a blurred fill |
| T10 split screen | none | **missing** |
| T11 political map | tac_map political theme, flat | **partial**: no relief/satellite texture under the fills; no teal tag labels; no striped regions |
| T12 icon swarms + counts + date banner | swarm glyph (chevrons), stickers on map | **partial**: no livery icons flying in numbers, no count/date banner on the map |
| T13 circle inset on map | none | **missing** |
| T14 map-to-portrait link | none | **missing** |
| T15 satellite close-up | none (no imagery source in the app) | **missing**: needs a licensed imagery source (decision below) |
| T16 pictogram chart | kit_scale (people in single file), kit_chart | **partial** |
| T17 transitions | dissolves and hard cuts | **missing** flash / glitch / zoom-blur (the app has xfade/zoom-blur code in other styles to reuse) |
| T18 soundbites | clip audio is never used | **missing** |
| Music bed + SFX | none in War (voice only) | **missing**: the app already has 8 music beds and a curated SFX library (whoosh, impact, riser, transition, ui) |
| Loudness -14 LUFS | not normalised in War | **missing** |
| Subscribe pill, end screen, CTA | none | **missing** (optional, per channel) |

## 5. How to add it without damaging what we have

Rules for every addition:
1. **New modules, additive hooks.** New cards go in a new `war/broadcast.py` (+ `war/audio.py`, `war/transitions.py`) registered through
   `registry.all_cards()`; direction.py only gains calls at the end of `apply`, behind config keys (`broadcast`, `music`, `soundbites`,
   `transitions`), like map_events / frontline / story.
2. **A plan snapshot guard.** Before any change, record the planned layers of three fixed scripts (the 2-min War CSV, a no-footage script,
   a footage-heavy script). A test fails if an existing card disappears or moves, unless the change is named in the test. New layers may
   be added; old ones may not vanish silently.
3. **CSV wins, narration decides.** Every new card is made from the sentence it sits under or from the clip's own metadata; a CSV
   graphic still keeps its seconds; small cards (T1, T2, T3, T8) coexist with clips like the existing corner cards.
4. **Touched tests only, then one real render** of the 2-minute video and a frame check, before anything is committed.

Phases (each one shippable alone):

| Phase | Adds | Reuses |
|---|---|---|
| A. Broadcast overlays | T1 source tag (clip channel/outlet from provenance), T2 keyword label, T3 quote caption box, T4 big word over footage, T8 yellow lower-third variant | provenance.py, semantics (numbers, quotes, entities), word times |
| B. Sound | music bed under voice (ducked, -14 LUFS master), whoosh/impact on cuts to graphics, riser into the hook end; soundbite slots (narration gap + clip audio + burned caption) when the CSV marks a row `soundbite` | assets/music, sfx/library catalog, kids/what-if mixers |
| C. Screens | T5 web-article card + blurred plate + highlight; T6 social post card; T7 speaker quote card with round portrait; T9 framed/vertical video; T10 split screen | lay_document, portraits.py, segments compositor |
| D. Map upgrades | relief texture under political fills (Natural Earth shaded relief, public domain); teal tag labels; T12 livery icon swarms with count + date banner; T13 circle inset; T14 portrait link | maps_tactical, map_events, stickers |
| E. Rhythm | 1.5-3 s cut rhythm on high-energy sentences, flash/glitch/zoom-blur transitions at section turns, opening soundbite + keyword rhythm in the hook, optional subscribe pill / end screen | story.py, existing xfade/zoom-blur code |
| F. Satellite close-ups (T15) | pin drop, footprint highlight, distance line on imagery | **needs a decision on an imagery source**: Sentinel-2 cloudless (EOX, CC BY 4.0 for the 2016 mosaic), NASA GIBS (public domain, coarse), or a commercial key the user owns |

Decisions needed from the owner: the imagery source for F; whether capturing real article pages from a URL in the CSV is wanted
(a headless browser screenshot of the page the script cites); whether the channel elements (subscribe pill, end screen) are wanted.

## 6. Status

- **Phase A built (2026-11-08, uncommitted)**: `war/broadcast.py` (bc_source, bc_label, bc_caption, bc_bigword), placed last in the
  direction pass behind config `broadcast` (and bc_source / bc_label / bc_caption / bc_bigword); CSV graphic names `label`, `caption`,
  `big word`; the old status chip keeps only its status word where the new tag shows the source. Guard: `test_war_plan_guard.py`
  (fixture `test_fixtures/war_plan_guard.json`) proves no existing card moved. Tests: `test_war_broadcast.py`.
- **Finding**: today's full-frame cards (stat split, equipment hero, maps) take almost every figure and quote moment over footage, so
  labels / captions / big words rarely get a free moment. The reference keeps footage on screen ~60 % and uses overlays for those beats.
  Matching it means letting overlays take some beats from full-frame cards: an owner decision (it changes existing cards).

## 7. Story building with visuals (how the film stays engaging)

Read from the full transcript against the pictures. The graphics are the surface; these devices are why people keep watching.

**One central question, stated early, paid off at the end.** 0:27 "And here is the problem Ukraine cannot solve on its own" -> the
whole film is a race: "Who runs out first this winter? Putin's ballistic missiles, or Ukraine's interceptors?" (asked again at 20:35).
Every section moves one side of that race. Visually the problem line gets the white box on Zelensky's face: the thesis is *seen*.

**Stakes before facts.** Power, light, heat, families sleeping in metro stations (0:05-0:30) come before any number. Each stake gets its
own literal picture and one word on it (POWER on the power plant, HEAT on the boiler room, the metro platform).

**A face for every actor; one antagonist named all the time.** "Putin's missiles", "Putin's winter plan", "Putin's deputy" (60+ times).
Whenever a person is named their face is on screen (Putin, Zelensky, Trump, Hegseth, Rubio, Sobyanin, Novak); officials' words come as
speaker quote cards with their portrait. Abstract policy becomes people doing things.

**Promise -> broken promise (setup and payoff).** 2:45 Putin said in 2018 the Kinzhal beats every air defence -> 2023 a Patriot shot one
down. 18:30 "Putin called the Patriot quite an old system" -> it is still stopping his missiles; the last line calls back to it ("before
Putin stops calling it old"). The same claim is shown, then its failure: the viewer is waiting for the payoff.

**Questions open every section, answered within a minute.** "Here is what was approved and when it can arrive." "So why are other
countries paying?" "So if allies are paying, what was the holdup?" "So can Russia just build missiles faster?" "So how does Ukraine get
through the winters before 2030?" Each question line is a turn: the picture changes register (map -> documents -> factory).

**A roadmap the viewer can hold.** "Borrow, find and build. First, borrow ... Second, find ... Third, build." Three words on screen
(BORROW FIND AND BUILD), then each part opens on its word.

**Receipts on screen.** Every claim is followed by its proof: the article with the sentence highlighted, the X post, the ministry
statement, the leader's own video ("Here is how he announced it" -> his clip plays with subtitles). The narrator points at evidence:
"This is the bridge the next morning", "This is the platform after the strike", "This is what the repair crews found" -> the picture
holds on the consequence, no graphic on top.

**Geography as distance and reach.** Each strike is located from wide to street level (city -> river -> campus pin -> building). Distance
is stakes: Camden -> Kyiv 9,000 km, Fatesh 400 km, Kremenchuk 260 km, Samara 900 km "from Ukraine's border". The maps escalate from Kyiv
outward to the Urals: the war's reach grows on screen.

**Numbers as contrasts, not lists.** $4M Iskander vs a $25,000 decoy; 35 interceptors used vs 12 delivered; 55-60 Iskanders a month vs
500 PAC-3 a year; 1,940 drones at Ukraine vs 2,700 at Russia in three nights. Each pair is one label or one highlighted line.

**Human cost moments slow down.** "A woman was killed and 15 people were hurt"; "an 11-year-old boy was among the badly wounded": the
cut rhythm drops and the footage of the aftermath holds with the label.

**Rhythm by meaning.** Strike nights and escalation: 1-2 s cuts, flashes, maps with flying icons. Explanation (Jumpstart, Pearl, loans):
documents and slower pushes. The pace follows what the sentence is doing.

**Recap, then what's next, then the series.** 18:24 "Here is the full account" (the whole story in 30 s over the film's own key
pictures), 19:10 "Here is what comes next", 19:35 the previous video tied in by the same theme ("Putin made the promise, and Ukraine
found a way through it"), then audience questions. Two subscribe asks are framed as value ("We check the official announcement to find
out", "If you are on the side that wants Putin's winter plan to fail").

### What our engine does and does not do here

| Device | War engine now | To build (Phase S, "story") |
|---|---|---|
| Literal picture per noun | yes (footage match, stickers, equipment, maps) | - |
| Stakes before facts | depends on the script | detect stake lines in the opening; give each its literal clip + one word |
| Thesis line seen | no | detect "the problem / the question / here is" lines; type them in the caption box over a face |
| Face for every named person | partly (portraits, catalogue name cards) | person named -> their face (clip, portrait or name card) on that sentence, every time |
| Setup -> payoff callback | no | when a later sentence refers back ("he had said", "called it", "promised"), re-show the earlier picture as a callback |
| Section questions | no | "So why ...?", "Here is ..." lines -> the turn: a register change (map/document/footage) + optional question box |
| Roadmap (first/second/third) | kit_chips (once) | three-word roadmap that reappears with the current part lit |
| Receipts | lay_document (typeset or a supplied screenshot) | real article / post capture from a CSV link (decision pending); "here is how he announced it" -> soundbite slot |
| "This is X" evidence lines | no | hold the clip, no overlay, slower cut |
| Distance as stakes | route km on maps | "N kilometres from/to" -> a distance line on the map, every time it is said |
| Contrast numbers | kit_versus when the pattern is literal | detect pairs across a sentence or two ("costs $4M ... worth $25,000") -> versus label / highlighted line |
| Human cost slow-down | no | killed / wounded / child sentences -> longer holds, no flashes, label only |
| Rhythm by meaning | uniform 3-6 s split | cut length from sentence type (strike/escalation fast, explanation slow) |
| Recap montage | no | "Here is the full account / to sum up" -> the film's own key shots and cards again, one per recap sentence |
| Series tie-in, CTA questions | no | end questions as on-screen question cards; optional end screen |

## 8. Built in one pass (2026-11-08, uncommitted)

| Phase | Module | What it adds | Switch |
|---|---|---|---|
| A (redone) | broadcast.py | source tag; keyword label typing on letter by letter (figures, systems, places, things, date as second line, contrasts "35 … VS 12 …"); caption box filling word by word (quotes, reported words, key lines, section questions); big figure; one text element per sentence; evidence lines ("This is the bridge …") hold with nothing on top; footage-first on fitting clips | broadcast, bc_*, footage_first |
| S | storyline.py | roadmap words (said, then each part lit); callbacks to the earlier picture on "had said / promised / called it"; recap montage after "Here is the full account"; light flash on section turns; strike lines re-cut to 1.4-2.4 s | storyline |
| B | audio.py | bundled music bed ducked under the voice; whoosh / impact / text SFX on graphics; loudnorm -14 LUFS (measured -14.1, LRA 2.6) | music, music_track, music_db, sfx |
| C | graphics_lib.py | speaker quote card (name, role, typed quote, round portrait); article page over a blurred plate of its own scene's clip with the headline highlighted; vertical clips were already framed over a blurred fill | speaker_quotes |
| D | map_events.py, maps_tactical.py | count banner from the narration ("1,214 DRONES / 29 OCTOBER"); round inset of the scene's own clip pinned to the place | map_events |
| E | storyline.py | flashes at turns, pace by meaning (above) | storyline |
| F | - | satellite close-ups: waiting for the imagery-source decision | - |

Not built: soundbites (the narration would need gaps where the clip's own voice plays), real article capture from a URL, subscribe pill / end screen.
Guard: test_war_plan_guard.py unchanged (no existing card or shot moved for clips without match data). Tests: test_war_storyline.py.

## 9. Engagement check (no render)

`war/engagement.py`, run at the end of planning (config `engagement`, `engagement_fix`): per 3-minute block the seconds between picture
changes (flag > 5.5 s) and footage share (note < 30 %); one kind of picture held too long (maps > 25 s, others > 15 s); nothing new on
screen for > 7 s (an animated full-frame card may hold 10 s); no question or turn in the narration for > 150 s. Slow stretches of clips that
fit their sentence are re-cut into ~3 s shots; everything else is reported. Report: `<video>.engagement.txt`, and after Generate scenes
`state/war_engagement.txt` plus the first lines in the app log. Tests: test_war_engagement.py.

## 10. Pacing and pictures against the narration (re-check 2026-11-09, 1080p copy)

Method: scene detection on the 1080p copy (threshold 0.25, 394 cuts) lined up with the word-timed transcript; one frame per 5 s and one
frame from every shot over 8 s, read against the sentence spoken over it. Our side measured the same way on two real War renders of the
same 2:15 script (Video_038 here, `dsf` on Ahmed's Mac).

| | Reference | Our War renders |
|---|---|---|
| Median shot (real cuts) | **2.3 s** | **4.4 s** (both renders) |
| Shots under 2 s | 41 % (161 of 395) | 2-6 of ~28 |
| Pace by 3-minute block | 3.0-3.9 s per cut, no slow block | one block, ~4.7-5.2 s mean |
| Cuts on a word start (±0.25 s) | 83 % | scene joins are word-timed |
| What the engagement check reports | - | "2.5 s per change": it counts card changes too, so it reads faster than the picture really cuts |

Narration -> picture rules seen in the reference:
1. **The picture is the sentence's concrete subject.** "Putin could not break Ukraine" shows Putin; "their heat" a power plant + HEAT;
   "metro stations" the people underground; "Then Washington made its move" Trump signing; "Canada, Germany and Norway" flags + a
   label; "unfriendly countries" the TASS page. A generic clip of the topic is almost never used.
2. **Every cited source shows its own receipt**: "CNN sources said" a quote box; "Zelensky says" the article page with the sentence
   highlighted; "Novak admitted" a speaker card with portrait. The attribution word is what triggers the picture.
3. **Every figure is typed on screen when spoken** (1 PERCENT, 2.1 BILLION DOLLARS, FRIDAY 13 OCTOBER / 500 PAC-3 MSE).
4. **A place plus an event goes to a map or satellite close-up of that place**: Kinzhal over Kyiv = map + round inset, Camden = the
   plant footprint, "9,000 kilometers" = distance line.
5. **Long holds (32 shots over 8 s) only when the picture keeps telling**: soundbites (Trump, Zelensky on CNN), a map animating the attack
   night (35 s through the drone sentences), speaker quote cards typing the quote, article pages, satellite sites. A generic or
   unrelated clip is never held.
6. **Short sentences and turns cut fastest** ("But that shield is cracking", "Then ..."): ~1.3-1.6 s per picture; numbers and reports
   hold ~2 s.

Gaps this shows in our engine (not built):
- **Cut rate**: rule 15 / engagement fix re-cut only clips that "fit" their sentence; most CSV clips are rated illustrative
  (relevance 0.05-0.2 in the `dsf` report), so they keep 4-8 s shots. Needed: a sentence-level cut (one picture per sentence or clause,
  2-3 s) for every clip, the engagement check counting real cuts only.
- **Subject match**: footage is chosen per scene from the CSV search, not per sentence subject; people named in the narration
  (Putin, Zelensky, an official) do not get their face; 5 of 27 `dsf` scenes used stock that "nothing in the clip's metadata relates to".
- **Long holds on generic pictures**: our 6-7 s document / stat cards are fine (they animate), but generic stock held 4-8 s is the
  reference's one forbidden case.
- Still open from section 8: soundbites, satellite close-ups (F), real article capture.
