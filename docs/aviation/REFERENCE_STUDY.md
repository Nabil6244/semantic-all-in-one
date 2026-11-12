# Aviation reference study — 2026-11-12

Two reference videos supplied by the user (studied for patterns only; nothing copied):

| | A. "The Air France Airline Nobody Understood" | B. "22-Minute Flight Runs Out of Fuel – Vistara 611" |
|---|---|---|
| Channel / genre | Plane Curious — airline business explainer | flight-incident reconstruction (different channel) |
| File | `~/Desktop/The Air France Airline Nobody Understood.mp4` | `~/Desktop/22-Minute Flight Runs Out of Fuel - Vistara 611.mp4` |
| Usable | **video track broken after 1:22** (2,460 frames of 16:03; audio and transcript complete) | complete, 40:18, 1080p30 |

Sheets, transcripts and stats: `out/reference_aviation/` (git-ignored; the repo is public).
These are **two different styles**. A is a fast, real-footage news explainer; B is a slow, 3D-simulated documentary.
Only 2 videos so far: the rule is 8+ before building. A needs a clean re-download, plus 6 more from either channel.

---

## 1. Measurements

| What | A. Plane Curious | B. Vistara 611 |
|---|---|---|
| Length | 16:03 | 40:18 |
| Cuts | opening 0:00–1:22: **27 cuts in the first 60 s, median shot 1.6 s**, 57 % under 2 s | 193 cuts, **median 4.9 s**, mean 12.5 s; only 6 % under 2 s |
| Pace over time | (can't measure past 1:22) | 7–22 s per cut per 3-min block, plus long animated map holds (longest 4 min). The maps never freeze: camera, route line, clock and fuel counter move constantly, so scene detection undercounts the visual change |
| First 60 s | 27 cuts | 7 cuts |
| Narration | 2,436 words, **152 wpm**, almost no pauses (58 gaps > 0.6 s, 1 > 2 s) | 5,646 words, **140 wpm**, measured delivery (498 gaps > 0.6 s, 15 > 2 s) |
| Loudness | -14.0 LUFS, LRA 1.8 (flat, levelled) | -14.6 LUFS, LRA 2.9 |
| First word | 0.0 s (voice starts on frame 1) | 0.96 s |

---

## 2. Style A — Plane Curious (airline business explainer)

### Structure (from the full transcript)
- **Cold open = a dated hard event** ("On the 5th of October 2015, Air France confirmed plans to cut 2,900 jobs") over chaotic real
  news footage (strikes, the torn-shirt clip), cut every 1–2 s.
- **Thesis in ~20 s**: "the industry accepted a painful truth ...", then a **twist**: a new launch, with messaging that "said none of that".
- **The question** at ~1:16: "So how does an airline have no reason to exist after only 13 months?" This is the title's promise, stated as a question.
- **Body = chronological business case**: plan names, CEO names, fleet numbers, seat counts, route economics; every claim dated.
- **Ending = a concrete, physical payoff** (the cabin layout: "48 business, 32 premium economy, 212 economy"). No outro, no
  subscribe ask in the narration.
- Title formula across the channel: "Why X Is Weirdly Nervous", "– Against All Logic", "Nobody Understood", "The Rise And Fall Of",
  "How X Outsmarted Y", "The X Problem". Titles are the hook; the open delivers the hook's event in 5 s.

### Visual grammar (opening 1:22)
| # | Template | Look |
|---|---|---|
| A1 | **Real footage, full frame** | news/press/airline clips (Euronews, CBS, Air France), cut 1–2 s on action; aircraft beauty shots (in-flight, taxi, tail close-ups) |
| A2 | **Source tag** | tiny white "Source: Euronews" top-right on every borrowed clip |
| A3 | **Article card** | rounded "browser window" (red/yellow/green dots) holding a photo or clip, on the **brand-blue animated backdrop** (deep royal blue, faint dot grid, soft diagonal light bands). Under it: outlet logo (The Guardian / TRAVELWEEKLY / Simple Flying), headline in white bold, date small right-aligned. Window slides/pushes in, holds 4–6 s |
| A4 | **Name lower-third inside the card** | red square marker + "Xavier Broseta / Former deputy director of HR, Air France" |
| A5 | **Fact strip** | red square icon + one white sentence ("Carried 3 million passengers from December 2017 to December 2018") under a photo window |
| A6 | **Collage build** | 2–4 windows pop in one by one on the blue backdrop (team photo, uniform sketch, fleet livery chart, cabin render), with a faint "planecurious" wordmark behind them |
| A7 | **Brand watermark** | the channel wordmark in light blue in the background of collage cards |

Pattern: **footage → card → footage → card**. The blue card is the "anchor" screen every 10–20 s; between cards there are bursts of
3–6 real clips. Hard cuts throughout; the card windows animate in (scale and slide), never static.

---

## 3. Style B — Vistara 611 (incident reconstruction)

### Structure
- **Opening = calm normality**: date, time, place ("It's the 4th of July 2019, just after 12 o'clock at Srinagar airport"). Animated
  place title over a drone shot.
- **The seed of the problem in 70 s**: a 2-hour-old weather report ("The problem is that this report is well over 2 hours old").
- **"Let's meet the crew"**: ages and hours as typed counters.
- **Teach the concept before the story needs it**: a 3-minute **cartoon analogy** (a family car crossing a desert, using fuel as
  trip/contingency/alternate/reserve) introduces the **fuel bar** that then stays on screen for the rest of the film.
- **Real-time tension**: clock + fuel kg counter tick down on every map shot ("1:38 PM ~4,220 KG" ... "3:05 PM 540 KG").
- **Decision points** dramatised with ATC/crew radio lines as subtitles, plus alternatives on the map (100+ KM / ~300 KM / ~500 KM).
- **Investigation + aftermath**: report pages with highlighted lines, court orders, redacted names.
- **Ending = a hook to the next episode**: "11 days later, another Vistara flight ... This is the story of Vistara 944. I'll see you there."
  Then a title card "THE STORY OF / VISTARA FLIGHT 944".

### Visual grammar
| # | Template | Look | Screen share (sampled) |
|---|---|---|---|
| B1 | **Dark satellite map** | desaturated blue-grey relief, mountains lit, city dots with small labels (SRINAGAR, JAMMU), gold glow on the active place | **~50 %** |
| B2 | **Route line** | gold dotted line that draws; flown track becomes solid gold; holding pattern drawn as gold racetrack loops that stack up | on map |
| B3 | **Clock + fuel HUD** | top-left: "TIME 2:03 PM / FUEL ~3,040 KG / CLEARED TO 4,100 FT", small label above each big value; turns red when critical | every map shot after take-off |
| B4 | **Fuel stack bar** | vertical segmented bar right side (trip yellow / contingency teal / discretionary purple / alternate pink / final reserve grey + lock), values beside it (600 KG, 30 MIN 1,150 KG), drains in real time, "0 MIN" in red | persistent from 6:00 |
| B5 | **Weather clouds on the map** | soft volumetric cloud puffs drifting over the map, storm icons, "GUSTS 29 KT", "~10 NM" distance callouts | middle act |
| B6 | **Distance / choice callouts** | big white "100+ KM", "~300 KM", "~500 KM", "2 MIN" next to straight lines to alternates; crossed-out place names | decisions |
| B7 | **Range circle** | pink translucent circle around an airport (fuel range) | decisions |
| B8 | **3D sim footage** | flight-sim A320 in Vistara livery: drone orbits of the airport, take-off, chase cam in clouds, wing view, rain on runway, cockpit and cabin interiors with animated pilots | **~30 %** |
| B9 | **Radio subtitle** | lower-left: small coloured speaker label ("FIRST OFFICER", "JAMMU ATC") + white line of the call, 2 calls stacked | every ATC exchange |
| B10 | **Typed counters** | "1 3 9 PASSENGERS", "5 CABIN CREW", "2 PILOTS" stacking lower-left, digits in boxes | crew/pax intro |
| B11 | **Document sheet** | a paper "TRANSIT BRIEFING SHEET" slides in left, lines get highlighted yellow, red stamp "OVER 2 HOURS OLD" | evidence |
| B12 | **Weather icon list** | right column of icon + caps label + small sub-label (LIGHT WINDS / VARIABLE 2 KT, DUST HAZE, A FEW CLOUDS) | weather |
| B13 | **Place title** | huge spaced caps place name with a small red "● RIGHT NOW" pill above, over the location shot | location changes |
| B14 | **Side-view altitude schematic** | dark gradient sky, aircraft side icon, dashed altitude lines ("20,000 FT", "11,000 FT"), "500 FT" separation bracket, QNH tags | altitude moments |
| B15 | **Instrument close-ups** | ECAM/fuel page close-ups: "FOB 460 KG", "FUEL L+R PUMP LO PR" warning box | climax |
| B16 | **Picture-in-picture on the map** | rounded inset of footage/photo pinned near a place (e.g. hail-damaged IndiGo nose, 2020 note) | side stories |
| B17 | **Airspeed tape** | speed tape with boxed value 185 / 195, "WINDSHEAR" red tag, "40 KT" arrow | approach |
| B18 | **Report / court pages** | white pages on dark background, highlighted lines (yellow and red), redaction boxes, slow drift | aftermath (~3 min) |
| B19 | **Cartoon analogy** | flat 2D desert road, car with family, fuel gauge = the same stack bar | concept teaching |
| B20 | **Next-episode card** | black screen, "THE STORY OF" small spaced, "VISTARA FLIGHT 944" huge spaced, number in red | end |

Transitions: almost all hard cuts and slow map camera moves; no flashes, no whooshes in the picture language. Calm, cinematic.

---

## 4. What the app already has vs what each style needs

| Need | Closest existing piece | Gap |
|---|---|---|
| A3/A6 article cards on a branded backdrop | War engine **T5 article screenshot card** + source tags (`cinematic_explainer/war/`) | new blue "browser window" card skin, outlet logo + headline + date block, collage build |
| A1 fast real-footage cutting (1–2 s) | War footage director, Hybrid stock fetch | aviation footage sources (airline press, news clips; user allows news clips) |
| B1/B2 dark satellite map + gold routes | `map-engine` / pakMap / StarMap route drawing | dark aviation skin, holding-pattern racetracks, flown vs planned line |
| B3/B4 live clock + fuel HUD | War/Weather counters | a **persistent stateful HUD** fed by a per-beat timeline (time, fuel, altitude) |
| B5 clouds/storms on the map | Weather style storm layers | reuse the weather cells on the dark map |
| B8 3D aircraft footage | `whatif-engine` (three.js, GLB models), Roblox/Voxel camera rigs | an airliner GLB + liveries, terrain/clouds scene, chase/orbit/wing/cockpit cameras; the **biggest build** |
| B9 radio subtitles, B10 counters, B11 documents, B12 icons, B13 titles, B20 end card | gfx-core templates, What If typeset | new templates in one look; mostly small |
| B14 altitude schematic, B15 instruments, B17 speed tape | none | new graphics (2D, cheap) |
| B19 cartoon analogy | Kids/3D Cartoon scenes | optional; skip in v1 |

---

## 5. Decisions needed before building

1. **Which style**: A (Plane Curious business explainer), B (incident reconstruction), or both as two styles.
2. **More references**: re-download the Air France video (current file breaks at 1:22), plus 6+ more from the chosen channel(s).
3. For B: whether "3D sim footage" means our own three.js airliner renders (new build) or the user's own captured sim footage.
