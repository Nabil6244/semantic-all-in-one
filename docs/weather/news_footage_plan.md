# Weather: real news footage of the event — plan (2026-10-15)

Problem: the script → video render of #007 (docs/weather/renders/chota_007_no_csv.mp4) had too little good footage. Stock answered
"family taking shelter during a storm" with a girl on a phone and a family in bed, and generic drone floods stood in for the Canadian
River. Fix: take the news-clip part of the News Doc research (docs/weather/news_doc_research.md §3.2) and use it in Weather, with
footage of the actual event first and stock last. Using news clips is allowed (owner, 2026-10-15). Nothing here is built yet.

## 1. Footage order for every footage shot

1. **News footage of this event at this place** (a local station's report on the Pecos County tornado).
2. **News footage of this event** (anywhere in the event).
3. **Your footage library** (exists: `weather/footage_library.py`).
4. **Public-domain / CC event footage** (exists: NASA, Commons, YouTube CC in `weather/news/footage_pool.py`).
5. **Stock**, only if its description matches the line (new check, §5).
6. **Nothing fits:** the beat stays on the map with its graphics. Never unrelated footage.

## 2. Finding the clips (new: `weather/news/harvest.py`)

The engine already knows the event (type, date, states, counties, rivers, storm name) from `weather/intel/understand.py`.

- **Searches:** one per event part (place + topic + date), not one per shot.
  - #007 examples: "Pecos County tornado October 2026", "Fort Stockton storm", "Canadian River flooding Oklahoma October 2026",
    "Foard County storm", "Fairfield County Ohio storm".
  - About 8–15 searches for a 10-minute video, using the existing `providers/youtube` search (yt-dlp backend).
- **Ranking** (reusing `footage_pool.relevance`):
  - must have: published inside the event window, and a place or the event named in the title or description;
  - preferred: local station channels (KWES, KOSA, KFOR, KOCO, NBC4 …), videos 1–8 minutes long, more views;
  - dropped: livestreams, compilations, "explained" videos and studio-only reports.
- **Few downloads, many shots:**
  - from the best 2–3 videos of each part, download one piece of about 40 s each, skipping the first ~8 s (the studio anchor);
  - cut every shot for that part from those pieces locally (ffmpeg scene cuts), skipping low-motion stretches;
  - never reuse the same 3 seconds; audio always muted.
  - About 20–30 segment downloads per 10-minute video, using the existing download strategies (DASH, HLS, browser playback).
- **Cache:** everything (searches, chosen videos, pieces, cut shots) is stored in `weather/_work/news_cache/`, so a re-render or a
  Retry asks YouTube nothing.
- **Pacing:** one request at a time, 3–5 s apart. On a 429 or a bot check: wait, retry once, then that part falls back to the next
  source in §1. The render never stops because of this.

## 3. Using the clips in the plan (News Doc)

- **News Doc builds its own plan** from the narration (`weather/newsdoc/plan.py`). It is footage-first:
  - every sentence gets a shot: news, drone/b-roll, a reporter on camera, a full-screen graphic, or (within the 10 % budget, §5b)
    a map shot;
  - it does not reuse Weather's or Teamplate's beat builder, cutaways or map rules.
- **Matching shots to lines:** by place first (the county or city the line names → a video about that place), then by topic
  (tornado, flood, hail, damage words against the video's title, description and auto-captions).
- **News runs:** a news shot is one continuous 5–15 s run from a downloaded piece, with the station's own cuts and lower third.
  A long line gets a run, not several 3 s bits.
- **Tags:** our place tag may sit on a real news clip (above the station's bar). Station logos stay as they are in the clip.
- **Credits:** each clip's channel, title, date and link go into the credits file next to the video.
- **Weather and Weather Teamplate are unchanged.** They can use the same harvested news clips later only if you ask; this plan does
  not touch them.

## 4. In the app

- **Visual Plan:** each news shot is a row, showing the channel, the video title, the date and the moment used. Retry gives the
  next moment or video; Change source and Use local clip work as today.
- **Weather card:** "News Doc" in the Editing style picker; nothing else changes on the card.
- **Report** (`weather/intel/report.md`): the searches made, the videos used, the parts that fell back to stock and why.

## 5. Better stock when it is still needed

- **Relevance check after download:** read the provider's description, tags and URL words of each stock result.
  - rejected: indoor and people-at-home results for weather lines (no beds, sofas or phones), and results naming none of the request's words;
  - then take the provider's next result (up to 3). This is the same idea as Enoch Template's `check_acquired_assets`.
- **Pixabay video as well as Pexels** (the key is set) for more choice.
- **Better requests:** always weather or damage you can see outdoors (already done for shelter lines in the script-to-video beats:
  "dark storm clouds over houses").

## 5b. The edit: "News Doc", a new editing option built from the reference

"News Doc" is a NEW option in the Weather card's Editing style picker (Weather | Weather Teamplate | News Doc). With the picker on
Auto, News and Post-Event stories get News Doc when enough news footage was found (≥ 30 % of the video), else Weather Teamplate. Weather and Weather Teamplate
stay exactly as they are.

**Not a copy of an existing style (owner, 2026-10-15).** News Doc's look and edit are built from the reference video, frame by frame:
- its own look module (`weather/newsdoc/`) and its own engine pieces (`weather-engine/lib/layers/nd_*.mjs`), each matched against
  reference frames (font weight, sizes, colours, positions, motion timing);
- nothing is a restyled Teamplate or Weather piece: no `tp_*` layer, no Teamplate timing, no Teamplate cutaways, no
  `keep_map_under`. A piece that looks similar is still drawn by News Doc's own code, to the reference's measurements;
- shared with the other styles is only the plumbing that is not a look: reading the story and finding the data (`weather/intel`),
  fetching clips (`providers/youtube`, stock providers), aligning to the voiceover, and the renderer that draws the frames.

### What the reference does (measured 2026-10-15)
Reference: `~/Downloads/videoplayback (6).mp4` (19:26, 640x360). Frame every 10 s: `docs/weather/news_doc_ref_every10s_1..4.jpg`
(117 frames); transitions sampled at 6 frames a second.

**Screen time** (counted on the 117 frames):

| Kind | Share | Examples |
|---|---|---|
| Plain footage (drone aerials, b-roll, news without our graphics) | ~50 % | |
| Footage with one of our graphics on it | ~33 % | place tags, big numbers, checklists, quote text over dimmed footage, side panel, yellow tags |
| Full-screen graphic on a dark navy / black ground | ~16 % | charts, quote cards, framed pictures, connection board, three rings, sine diagram, polaroids |
| Map | ~2 % | 2 shots in 19 min: a flat blue US map with a "LONG BEACH" pin (1:20) and a red Mexico map (17:20); no satellite map |

- About 20 % of all frames carry a TV station's lower third or logo (CBS LA, KCAL, NBC 4, ABC 7, FOX 5, KTLA 5, ABC 10, AP, CBS 2).
- People on screen: muted reporters, officials and interviewees from the news clips (3:00, 3:50, 4:10, 10:00, 14:40, 15:00).

**Rhythm:**
- 172 hard / clear cuts detected, median 4.75 s, mean 6.8 s.
- Shot lengths: 30 shots under 1.5 s, 34 of 1.5–3 s, 25 of 3–5 s, 39 of 5–8 s, 44 of 8 s or more.
- 8–13 cuts a minute in the first 12 minutes, 5–9 later (the explanation and debate part is calmer); 2 in the last half-minute.
- The detector also misses soft changes: the "30 s holds" (2:00, 3:10, 7:20, 10:53, 12:07, 14:16) are 3–4 different shots and
  graphics each, joined by crossfades. Real shot length ≈ 4–7 s throughout.

**Transitions:**
- Hard cuts between footage.
- A short crossfade (~0.3 s) into chapter words and full-screen graphics.
- At a new part, glitch + flash: 1–2 frames of RGB pixel blocks over the outgoing clip, a white flash with cyan diagonal stripes, a
  quick fade into the next thing (0:29, 2:27).

**News clips:**
- Played as one continuous run of 5–15 s, keeping the station's own internal cuts, with its lower third staying up (1:58–2:00:
  two CBS LA shots under one "BRACING FOR ROUGH SURF" bar).
- Never cropped. Our graphics sit above the station's bar ("$4-6.7M" top right; "400K CY" centre).
- Some sentences are covered by a reporter or an official talking (muted).

**Graphics** (all seen; × = times in the 117 frames):
- Place tag: black box bottom-left, white name + grey sub (×6).
- Yellow tag, small caps on yellow (×4).
- Big number / year, white, heavy, on footage (×9: "$4-6.7M", "$400,000", "26 COTTAGES", "+300%", "20 YRS", "$15", "2025",
  "1950", "$285M"); a green box over the area it means ("$300B real estate in the impact zone").
- Keyword / quote:
  - black full-screen card, white caps, red boxes on 1–3 phrases (×3);
  - the same text over darkened footage (×2);
  - chapter word typed in over footage ("HARD PHYSICS", "WHO IS", "RETREAT") or a small caption bottom-left
    ("THE PRIVATIZATION OF COASTAL DEFENSE").
- Checklist: paper card with a red header, handwritten items ticked one by one, on the right over a still photo (×5).
- Side panel: footage on the left ~45 %, a thin teal line, a dark panel with a title and 3–4 bullets (×2).
- Charts on dark navy (×4): line (draws in over ~2 s; last point red), vertical bars, horizontal bars.
- Others:
  - framed picture on navy with a small caption (×4);
  - ring gauge "90%";
  - three outlined rings;
  - sine diagram;
  - polaroids on a paper board;
  - a yellow-line connection board with photo thumbnails (×2);
  - a name tag (orange bar, condensed white name + handle);
  - a serif pull quote with attribution.
- A still photo with a graphic on it may hold still for 3–5 s (the checklist frames do not move).

### How News Doc does it

| Reference | News Doc | New / reused |
|---|---|---|
| Shot ≈ 4–7 s, faster (1.5–3 s) in the first ~75 s and the climax, calmer in explanation parts | shot length from the part: opening and climax beat 1.5–3 s, impact 3–5 s, explanation 5–8 s | new: `newsdoc/edit.py` |
| A news clip runs 5–15 s with its own cuts and its own lower third | a news shot is one continuous run of 5–15 s from the downloaded piece (not cut into 3 s bits), never cropped | harvester + plan (§2, §3) |
| Our graphics above the station's bar | layout rule: our tags and numbers keep out of the bottom ~22 % on news shots | new |
| Hard cuts between footage; ~0.3 s crossfade into chapter words and full-screen graphics | hard cuts; a 0.3 s fade only into/out of full-screen graphics and chapter words | new: `newsdoc/edit.py` |
| Glitch + white/cyan-stripe flash at a new part | at a new part of the story (another state / event part), ~1 per 2–3 min | new `nd_glitch.mjs`, `nd_flash.mjs` |
| Footage ~83 %, full-screen graphics ~16 %, map ~2 % | satellite storm-data map shots, **at most 10 % of the video** (50 s of map in a 500 s video), see "Map shots" below | new map budget |
| Big number on footage, about every 2 min | a number the narrator says (and the data or the script backs), on the shot on screen | new `nd_number.mjs` |
| Place tag black, yellow tag | place first named → black tag; warning / agency / storm name → yellow tag | new `nd_place.mjs`, `nd_ytag.mjs` |
| Quote card / keyword over footage / chapter word | last line of a part → black quote card with red boxes; new part → chapter word typed in | new `nd_quote.mjs`, `nd_chapter.mjs` |
| Checklist ticked item by item | a line listing 3+ places or things ("Pecos, Foard and Knox counties") | new `nd_checklist.mjs` |
| Side panel with bullets | "how" / "why" lines (the explainer's text) | new `nd_panel.mjs` |
| Line / bar charts on navy | river levels over days, rain totals compared, warning counts (Weather's data) | new `nd_chart.mjs` (the data comes from the engine; the drawing is News Doc's) |
| Framed picture, ring, rings, polaroids, board, pull quote, name tag | later batch, only where the script gives a reason | later |
| Reporters / officials talking (muted) | allowed: a news run may include a reporter on camera | harvester ranking keeps them, but never the studio anchor |
| Calmer at the end, last shot is footage with the last word | closing beat = calm wide news / drone shot + chapter-word close | new: `newsdoc/edit.py` |

### Map shots (owner's rule, 2026-10-15): satellite map with the storm data, ≤ 10 % of the video

Unlike the reference (flat maps, 2 %), News Doc keeps Weather's strength: the dark satellite map with the event's own data on it.
But only as short, data-packed shots inside a footage-first video.

- **Budget:** map time ≤ 10 % of the video: 50 s for 500 s, 60 s for 10 min.
  Counted over every map frame (data graphics on the map included); full-screen navy charts are not map time.
- **What a map shot shows:** the satellite map plus what the engine found for this event:
  - hurricane: track, cone, landfall point, wind / category stats card (`storm_stats`);
  - severe: radar loop (rain greens to reds), warning polygons, storm reports, surveyed tracks;
  - flood / rain: rain-total map, river crests, gauge chips;
  - plus a count-up stat on the map (warnings issued, rain total, peak wind) when the narrator says it.
  - Nothing is drawn without data: a map shot with no data layer is not made.
- **Shot length:** 5–8 s each, a radar or satellite loop up to 10 s. That is about 6–8 map shots in a 500 s video.
  - Each opens with a quick push in, the data arriving, the stat counting up, then a hard cut back to footage.
  - No still map: the existing motion rules apply.
- **Which moments get the budget** (ranked, until the 10 % is spent):
  1. the first "where": the event's region with its headline (opening);
  2. the strongest data moment of each event part (landfall, peak radar, warning count, record total / crest);
  3. a line that reads out a measured number the map can show;
  4. the closing "where it went" (a track or total map), if budget is left.
- **Spacing:** at least ~40 s of footage between two map shots, so the map punctuates and never dominates.
- **Everything else goes to footage:**
  - data lines that miss the budget are shown as footage plus a number on it, or as a full-screen navy chart;
  - Auto never adds map time back to fill gaps (no `keep_map_under` 50 % in News Doc).
- **Check before render** (`weather/selfcheck.py`): "map 48 s of 500 s (9.6 %, limit 10 %)", with each map shot listed and what it shows.

What stays the same: every number on screen is said or sourced; nothing is generated (no Flow).

## 6. Build order

| Step | What | Test |
|---|---|---|
| 1 | News Doc accepts news clips (only when News Doc is the editing style; Weather and Weather Teamplate keep refusing them exactly as today), credits | unit + the other styles unchanged |
| 2 | `harvest.py`: searches per event part, ranking, cache, pacing, fallbacks | recorded search answers, no network |
| 3 | Piece download + local shot cutting (scene cuts, motion check, no reuse, mute) | a short local test video |
| 4 | News Doc's own plan (`weather/newsdoc/plan.py`): a shot for every sentence, news runs, graphics moments, map budget | plan-level tests |
| 5 | Stock relevance check + Pixabay video | recorded provider answers |
| 6 | App: News Doc in the Editing style picker, Visual Plan rows for news shots, report section | fake-app tests |
| 7 | News Doc edit: style key + Auto rule, shot lengths by part, 5–15 s news runs, layout rule for station bars, 0.3 s fades into graphics, map budget ≤ 10 % (ranked data moments, 5–8 s shots, ~40 s apart) | plan-level tests |
| 8 | News Doc's own engine pieces (`nd_*.mjs`), each matched against reference frames: place tag, yellow tag, big number, quote card, chapter word, checklist, side panel, navy charts, glitch, flash; its own map-shot look | `weather-engine` tests + side-by-side frames with the reference |
| 9 | Real test: #007 with no CSV in News Doc, rendered; frame sheet next to the reference's; shot-length histogram vs the reference; news / stock / map shares; stillness check | render |

## 7. Rules
- Weather only: no change to PakMap, Hybrid or StarMap files (`test_weather_isolation.py`); the YouTube provider is used, not changed.
- No AI anywhere on this path. Searches and downloads are only to YouTube, the free footage sources and the stock sites.
- Ask before every commit.

## 8. What was built (2026-10-15)

| Piece | File |
|---|---|
| Story reader: sentences, parts (script headings / a new state), places with their state, spoken numbers, lists, warning / agency / storm names | `weather/newsdoc/story.py` |
| News harvester: per part a local search (town or county + hazard), then state + month; a title must name the hazard and a local place (or the state and the month); other years / months, livestreams, compilations, "top 10", comparisons, schools … skipped; the video's real upload date must be 3 days before to 60 days after the event; NWS office towns ("the Weather Service in Midland") are not searched; one 40 s piece per video cut into 5–12 s muted 1080p runs; cache in `weather/_work/news_cache` | `weather/newsdoc/harvest.py` |
| Timeline: map shots only at data moments (priority: track/cone/stats, radar, warnings, reports, crests, totals), ≤ 10 % of the video, 5–9 s, ≥ 40 s apart; news runs first, stock of what the line says next (repeats reframed); hard cuts | `weather/newsdoc/plan.py` |
| Graphics, drawn to the reference frames: place tag, yellow tag, big number (count-up), chapter word, quote over footage, quote card, checklist, navy bar chart, side panel, glitch + flash | `weather/newsdoc/graphics.py` |
| Overlay pass (narration kept; falls back to batches, then to the video without graphics) | `weather/newsdoc/finish.py` |
| Orchestrator, report (`*.newsdoc.json`), credits incl. every news clip's channel, title and link | `weather/newsdoc/generate.py` |
| App: "News Doc" in the Editing style picker; Check plan and Generate branch to it; CLI `--style newsdoc` | `weather/app_section.py`, `weather/cli.py` |
| Engine fix found on the way: a date said only to compare no longer sets the key moment | `weather/intel/context.py` |

Not done: Auto does not pick News Doc by itself (it stays an explicit choice); the rarer reference pieces (framed picture, rings,
polaroids, connection board, split screen, pull quote, name tag) are not built.

Tests: `test_weather_newsdoc.py` (13, offline: fake YouTube serving a generated video; NoPaidCalls over the whole plan).
