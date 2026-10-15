# Weather: script + voiceover → video (no CSV) — plan

Written 2026-10-15; built the same day (all four phases, uncommitted) — see section 8. The CSV path stays exactly as it is and still wins
when a CSV is loaded.

## 1. What you do

1. Create a Weather project (or choose one).
2. Paste your script on the Script page.
3. Import your recorded voiceover.
4. Click **Generate**.

The steps "Copy the CSV prompt", "Load plan" and "Fetch data" disappear from this path. The optional **Check plan** button
shows the plan before you render (step 4.8 below).

## 2. What the app does after Generate

```
script + voiceover
  │
  ├─ 1. Transcribe the voiceover (Whisper, on your Mac, once per recording)
  ├─ 2. Line up the script with the recording (exact spelling from the script, exact times from the voice)
  ├─ 3. Understand the story: event type, date, states/counties/cities, storm names, numbers, phases
  ├─ 4. Pick the format (Forecast / News / Post-Event) and the editing style
  ├─ 5. Find the event and fetch its official data (NWS, NHC, SPC, IEM, USGS, ACIS, MRMS)
  ├─ 6. Build the beats: map beats + footage beats + opening + closing
  ├─ 7. Choose graphics for each beat from the data (only numbers the sources show)
  ├─ 8. Self-check and auto-fix (stillness, map share, places, timing, sources)
  ├─ 9. Find footage (your library first, then Pexels/Pixabay; never AI-generated)
  └─ 10. Render (the same weather-engine render as today) + report
```

### Step 1: transcribe (exists)
`weather/app_section.voiceover_words`: Whisper on your Mac, cached in `weather/_work/voiceover_words.json`.

### Step 2: script ↔ voice (exists, one gap)
`hybrid.narration.build_sentences` uses the script's sentences and the voice's times. **Gap:** the engine reads the script only
from `weather/script.txt`, but you paste it on the Script page. **Change:** Generate saves the Script page text to
`weather/script.txt` when that file is missing or was written by the app. A `script.txt` you wrote yourself is never replaced.
Without any script, the transcript's pauses are used (this already works).

### Step 3: understand the story (exists)
`weather/intel/understand.py` gives the event category, dates, places, storm names, spoken numbers and the phase of each part.

### Step 4: format and style (new, small)
- **Format** from the story: future words and a forecast category → Forecast; an event with a date in the past plus aftermath
  words ("damage", "survey", "recovery", "cleanup") → Post-Event; otherwise → News. The card's Format picker becomes an override
  ("Auto" is the new default).
- **Editing style:** Teamplate for News and Post-Event, Classic for Forecast. The Editing style picker is still an override.

### Step 5: event and data (exists)
`weather/intel/engine.py` finds the event and fetches the data. Nothing is invented: a number no source shows is reported as
"not verified", never drawn.

### Step 6: beats (exists for map beats; upgraded)
Today, `weather/intel/beats.py` cuts the narration into map beats of about 14 s, and footage only appears afterwards as
"cutaways". The upgrade builds the beats properly:

| Beat | When | What is on screen |
|---|---|---|
| Opening (b1) | first 1–2 sentences | the event's region with the headline title (event, date, place) |
| Map beat | the sentence names a place, a number, a time, a warning, a track | camera on that place + data graphics |
| Footage beat | the sentence describes what people saw or suffered: damage, flooding, rescues, wind, waves | 1–2 shots of exactly that (library first, then stock) |
| Explainer | "how", "why", "what is" sentences | the explainer graphic (exists) |
| Closing | last 1–2 sentences | pull back to the region + source credits |

Rules:
- A new beat starts where the place or the topic changes, not every 14 s; a beat is 5–24 s long.
- Each beat starts on a sentence start (no cut in the middle of a word).
- Footage beats are at most 40% of the video (Teamplate's existing cap). The map is at most half the video, as today.
- Two footage beats in a row only when the narration stays on impacts.
- Camera places: county/city → close-up; state → region; a region the map does not know ("Southern Plains") → the state(s) the
  story names (the same fallback just fixed in `weather/autofix.fix_places`).

### Step 7: graphics (exists)
`weather/intel/catalog.py` + `planner.py` choose the graphics (radar, warnings, track, cone, totals, reports, crests, survey
tracks, before/after, counters, timelines) and place each one on the words that say it.

### Step 8: self-check and auto-fix (mostly exists; collected in one place)
Before rendering, checks run and fix what they can:
- no still stretch over about 7 s (`weather/motion.keep_moving`);
- the map at most half the video (`keep_map_under`);
- unknown places replaced (`autofix.fix_places`);
- unheard anchors retimed (`autofix`);
- every number on screen has a source.

The result is one list of "Fixed for you" notes. It stops only for what it truly cannot fix, with a clear message:
- no voiceover;
- the event cannot be found: you're asked to add the date and state to the first sentences, or to set them in the card;
- no internet for the data.

### Step 9: footage (exists)
The search request is built from the sentence's own words: your footage library first, then Pexels/Pixabay. Flow and any
AI-generated footage are never used. If nothing relevant is found, the beat stays on the map (never unrelated stock).

### Step 10: render and report (exists)
The same render as today. After it, `weather/intel/report.md` lists the event found, the sources, the graphics, the numbers
shown and the fixes.

## 3. AI and cost
No external AI is called on this path. Whisper runs on your Mac; the plan is built by rules; the data comes from free official
sources; footage comes from your library or free stock searches. A test will fail if any AI provider is called on this path
(like Enoch Template's NoPaidCalls guard). The only AI step left is optional: "Copy the script prompt", if you choose to have
Claude write the script.

## 4. What changes in the app
- `has_plan()` is true with no CSV when Intelligence is on and there is a voiceover. The Generate button goes from
  "Import voiceover" straight to "Generate".
- The Format picker gets "Auto"; the Weather card text explains the two ways (script only, or CSV).
- Visual Plan: after Check plan or Generate, it shows the automatic beats, so any shot can be replaced or retried, as today.
- Loading a CSV switches the project back to the CSV path (the CSV wins). Removing the CSV goes back to automatic.

## 5. Build order
| Phase | What | Size | Result |
|---|---|---|---|
| 1 | Script saved to the project; `has_plan` without CSV; Generate straight away; Auto format/style | small | script + voiceover → video works today's way (map beats + cutaways) |
| 2 | Beat builder upgrade (opening, footage beats, explainer, closing, topic/place splits) | medium | a video close to a hand-made CSV |
| 3 | One self-check list; clear stop messages; optional quick low-res preview | small | fewer surprises before the long render |
| 4 | Tests (no-CSV path, CSV path unchanged, no AI calls, other styles untouched) + render your #007 script without its CSV and compare with the CSV version | medium | proof |

## 6. Rules
- No change to PakMap, Hybrid, StarMap or other styles (`test_weather_isolation.py` guards it).
- Your files (`beats.csv`, `weather_layers.csv`, `plan.csv`, `script.txt` you wrote) are never overwritten.
- No commit without asking.
- Quick, targeted tests and as few re-renders as possible (credits).

## 7. Limits
- The voiceover is required: every cut is timed to your words.
- The event must be findable: a full date and a state in the first two sentences (the script prompt already asks for this).
- An automatic plan is more uniform than a hand-tuned CSV; for a special video, the CSV path is still there.
- Small towns the map does not know get no place label (as today).

## 8. What was built (2026-10-15)

| Piece | File |
|---|---|
| Auto format (Forecast / News / Post-Event from the script) and Auto editing style | `weather/autopick.py`; Format and Editing style pickers get "Auto" (`weather/app_section.py`); `python -m weather` resolves Auto the same way (`weather/cli.py`) |
| No CSV is a plan; Generate goes straight from Import voiceover to Generate (no Fetch data step) | `app_section.has_plan`, `is_auto`, `sync_cta` |
| The Script page reaches the plan (`weather/script.txt`; a script.txt you wrote is never replaced) | `app_section.sync_script` |
| Beat builder: opening / map / footage / closing beats, splits on place and topic, footage only for impacts (max 40 %), requests that pass Weather Teamplate's relevance rule, camera stays on the last named county | `weather/intel/beats.py` (`plan_from_narration`, `footage_request`, `use_library`) |
| Your footage library used for the automatic plan too | `beats.use_library` from `generate.plan_layers` |
| Checks before the render (longest still stretch, map share, footage share, repeated searches, numbers on screen) | `weather/selfcheck.py`; shown by Check plan, logged by Generate |
| Quick preview (12 fps, no sound design, `weather/_work/preview.mp4`) | `app_section.run_generation(preview=True)`, button next to Check plan |
| Clear message when no plan can be made | `generate.plan_layers` |
| Fix found on the way: a year said only to compare ("a previous crest … back on May 9th, 2019") no longer dates the event (project #007 got 2019 radar and crests, with or without a CSV) | `weather/intel/understand.py` (`REFERENCE`, `DateMention.reference`), `weather/intel/context.py` |
| Fix found on the way: an unknown opening place ("Southern Plains") no longer removes the camera start | `weather/autofix.fix_places` |

Tests: `test_weather_script_to_video.py` (16, incl. a NoPaidCalls run of the whole script → plan path).
