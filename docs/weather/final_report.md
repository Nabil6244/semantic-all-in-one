# Weather style: integration report (2026-10-13)

Phases 1A/1B (Forecast), 2 (automation), 3 (News), 4 (Post-Event) and part of 5 (polish) are now in one working tree.
Nothing is committed. Weather is still off by default (Settings > General), and no existing style was touched:
no file under pakmap/, pakmap-engine/, hybrid/, starmap*/, map-engine/, map_scene/, providers/ or flow-engine/ changed, and
app.py / VideoGenerator.spec only have the additive phase-1 changes.

## What the integration added (Weather-owned files only)
| Where | What |
|---|---|
| `weather/app_section.py` | **Format** picker in the Weather card (Forecast / News / Post-Event), saved per project in `weather/weather.json`; "Copy the CSV prompt" copies that format's prompt. **Prepare today's forecast** button (Forecast: `weather.automation.prep` writes script.txt + plan + data into the project; an edited script.txt is kept). Settings > General: **Prepare the forecast every morning** switch, which installs/removes the OS task only when the user clicks it. Fetch data needs the NWS contact only for Forecast. |
| `weather/prompts/news_csv_prompt.txt`, `post_event_csv_prompt.txt` | The CSV prompts for News and Post-Event (layer patterns, anchors, screen and wording rules from the phase 3/4 reports). |
| `weather/footage.py` | `footage_problems(plan, project_root)`: an event clip in `weather/clips/` must be approved in `weather/clips.json`. A `youtube:` asset is still refused (it can only be used as an approved, downloaded clip). |
| `weather/cli.py`, `weather/generate.py` | `fetch` works without `--contact` when no row needs NWS data; the CLI lists the News/Post-Event products it fetched. |
| `weather/alerts.py` | NWS colours for Extreme Wind, Special Marine and Snow Squall warnings. |
| `weather-engine/lib/wx_draw.mjs` | Plugins with `overFootage` (the footage credit chip) are drawn on the footage itself, at full strength. |
| `weather-engine/render.mjs` | At most 4 radar tiles fetched at once (to go easy on IEM); pakMap's misleading "Grid data: mrms_….asc (supplied by the author)" credit is dropped (MRMS is credited properly). |
| `weather/automation/record.py` | Records `weather/testdata/automation/prep_recording.json.gz` for the prep tests (see "Still open"). |
| `test_weather_sidecar.py`, `test_weather_render.py`, `test_weather_auto_prep.py` | The unknown-type example is now `lightning` (`radar` is a real type now); the new YouTube message; the prep tests skip until the recording exists. |

## Gates
- Full Python suite: 3746 tests OK (8 skipped: the 6 prep tests waiting for their recording, and 2 that were skipped before).
- weather-engine 46/46, pakmap-engine 133/133, starmap-engine 54/54; `check_upstream.mjs`: no drift.
- `test_weather_isolation.py` passes (it runs as part of the full suite).

## Test renders
- News: Hurricane Ian 2022 (`news_e2e`: satellite loop, best track, advisory-24 cone + track, radar + archived warnings, Extreme
  Wind Warning counter, WPC rainfall outlook, NASA clip with its credit). Test voice (macOS `say`).
- Post-Event: Hurricane Harvey 2017 (`post_e2e`: timeline, MRMS rain map, gauge totals, Houston record day, Buffalo Bayou crest
  with its chart, MODIS false-colour before/after). Test voice.
Results and frames: see the RENDERS section at the end of this file.

## Still open
1. **The prep recording.** `test_weather_auto_prep.py` needs a recording of one real prep. The NWS forecasts are too old for a
   prep between about 10 PM and 4 AM Central (a known limit), so it could not be recorded at integration time. Run
   `.venv310/bin/python -m weather.automation.record` between 5:30 AM and 9 PM Central (3:30 PM–7 AM Pakistan time), then the
   6 tests run.
2. **Event footage panel (News, phase 3 R9)**: search / approve / reject / download clips and "Use in beat" in the app. The data side
   (`weather.news.footage_pool`, `approval.ClipStore`) is built and tested; today clips are approved from Python.
3. **YouTube clips (phase 3 R4)**: downloading approved YouTube clips through the app's yt-dlp backend before the render.
4. **Suggested reports (phase 4 #6)**: the "a post-event report is ready to make" list in the card (`weather.post.suggest`).
5. **Federal live radar (`noaa_mapservices`, phase 3 R6)** and the before/after **wipe** (phase 4 #4, needs a shared file): not built.
6. Real 30–60 minute runs with a real voice, and the Meteocons / Census downloads, still wait for the user's go-ahead.

---

# Broadcast upgrade (2026-10-13, later the same day)

## Visual defects found (frames of the first Ian and Harvey renders)
| Time | What the viewer saw | Cause | Fix |
|---|---|---|---|
| Harvey 0:10–2:30 | The map over Mississippi/Louisiana, not Houston; the rain map in the bottom-left corner, half off screen | pakMap's always-on camera drift (0.5 % of the view a second, north-east) built up over 2 minutes of `hold` beats | Weather plans set `drift_pct_per_s` to 0 (`weather/generate.py`); Hybrid's idle push-in keeps the picture moving. Fixes every Weather video |
| Ian 0:24–0:56 | Florida and the track against the left edge, ~60 % empty dark ocean | the same drift | the same |
| Ian 0:00–0:16 | An empty Caribbean map under a title chip | the satellite loop started on a later sentence | the plan starts it on the first words; a lower-third headline opens the video |
| Ian 0:48, Harvey 2:50–end, Ian 2:00 | Several seconds of an empty map (forecast beat, closings) | nothing planned for those words | headline lower-thirds on the opening and closing beats, cone from the beat's first words |
| Both, whole video | No place names: the viewer cannot tell where Houston, Fort Myers or Tampa is | no layer for it | new `place_label` layer |
| Both | Only small title chips; nothing reads as broadcast graphics | — | new `headline` lower-third (kicker tab, big title, date strip; red news, blue forecast, amber post-event) |
| Harvey 2:30 | Before/after only fades | — | optional wipe (`"transition": "wipe"`) with a white divider |

## What changed (Weather-owned files only)
- `weather/generate.py`: no camera drift on Weather maps.
- `weather/layers/broadcast.py` + `weather-engine/lib/layers/headline.mjs`, `place_label.mjs`: the two compositions. Headlines refuse
  digits in kicker and title (numbers come from data layers). A place name never overlaps a panel or another name: it moves to the
  other side of its dot, or is left out.
- `weather-engine/lib/wx_draw.mjs`: panels record where they land (labels avoid them); the radar/satellite time chip moves above a
  lower-third instead of under it.
- `weather-engine/page.js` + `weather/layers/beforeafter.py`: the before/after wipe (the map is drawn twice only during the wipe).
- Event footage screen (`weather/clip_review.py`, Weather card > Format News > "Event footage…"): search, preview, source and rights
  evidence, why picked / why not usable, approve / reject, historical / illustrative label (shown on the credit chip), the beat it is
  for, download, and "Use approved clips in their beats". Approving says plainly that it is not a licence.
- Suggested reports (`weather/post/feed.py`, Format Post-Event > "Suggested reports…"): NWS significant warnings of the last month +
  SPC reports of the last 10 days -> `weather.post.suggest`; picking one copies the Post-Event prompt with the event filled in.
  Checked live once: it found real recent events (NM/CO storms, CA flooding).
- All three CSV prompts describe `headline` and `place_label`; Post-Event describes the wipe.

## Evidence (docs/weather/renders/)
- `compare_ian.jpg`, `compare_harvey.jpg`: original (left) vs new (right) at the same times, same narration and data.
- `harvey_wipe.jpg`: the wipe mid-way. New videos: `news_ian_2022_v2.mp4`, `post_harvey_2017_v2.mp4`.
- Render time unchanged: Ian 186–253 s, Harvey 233–238 s (the new videos are also half the file size: no drift, so frames repeat).

## Status
- Implemented, tested and visually reviewed in real renders: drift fix, headline, place labels, time-chip placement, wipe.
- Implemented and unit-tested, NOT seen in the running app: the Event footage screen and the Suggested reports window (their logic is
  tested; the windows themselves were not opened).
- Known limits: Harvey's "after" picture (Aug 31) is mostly cloud over Houston, so pick a clearer day (a Sep 1 picture exists in the
  earlier probes). A place name near a moving panel edge can appear and disappear as the camera moves. Smoother radar (more frames)
  and the federal live radar were not done: the IEM radar already plays coherently and nothing showed a need for them.
- Real-world checks still open: 3 Forecast runs with the user's own recordings; a tornado outbreak rebuilt for News and Post-Event;
  the prep recording (`python -m weather.automation.record`, 5:30 AM–9 PM Central).
