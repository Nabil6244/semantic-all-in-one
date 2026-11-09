# War Footage Director — investigation and implementation plan (2026-11-09)

Status: **plan only, awaiting approval.** Nothing below is built. It follows `FOOTAGE_RELEVANCE_AUDIT.md`.

## Part A — Investigation results

### A1. Can the existing downloader capture a specific video id at an exact time? **Yes, without changing it.**
- `providers/youtube/acquisition/browser_client.get_client().acquire(video_id, start, duration, dest)` is a public call. It takes a video id and a start second, opens `watch?v=<id>&t=<start>s&vq=hd1080` in the capture browser, seeks and records. War can call it directly (import only, no edit).
- **Limits** (from `browser_worker.mjs`, unchanged):
  - One capture is at most **8 s** (`Math.min(8, durationSec)`). A longer shot needs two captures.
  - The seek lands within **±1.25 s** of the requested second.
  - The result returns `ok, duration, bytes, width, height` but **not the actual start time**.
  - Capture runs in real time, one browser per job (the pool size is the existing setting).
  - Ads are waited out (another session's uncommitted edit to that file, left untouched).
- No War path calls it today. War goes through `AssetManager.resolve_all` → YouTube provider → search → candidate 1.

### A2. Can its output be validated? **Partly by the shared code, fully by War code.**
- **Shared:** `providers/youtube/strategies.validate_clip(path, expected_duration)` (importable, unchanged) checks the file is real video, has a video stream, and has a sane duration.
- **Missing, to be built in War:** proof that the clip shows *the intended moment*. Because the capture doesn't report its real start, War will compare captured frames with the video's own storyboard tiles around the requested second (see A3). A match confirms the moment and estimates the real offset. A mismatch (an ad, a wrong seek, a different video) is rejected. `archive_fast.frame_problem` already catches black frames and credit rolls.

### A3. Can candidates be inspected *before* capture? **Yes, cheaply, with no Gemini.**
- **Search results** (flat, ~1.5 s per query) already include title, channel, `channel_is_verified`, duration, view count and a **description snippet**. The current ranking ignores the description.
- **Full metadata** (`yt_dlp.extract_info`, no download): **3.5 s per video** in the test. It adds `upload_date`, the full description and tags.
- **Storyboards:** 320×180 frames about **every 2 s across the whole video**, as 3×3 JPEG sheets of ~40 KB from `i.ytimg.com` (YouTube's thumbnail server, not the video stream). One sheet fetched in 0.7 s. Tested on the Kanal13 "Fuel riots" video: the sheets plainly show supermarket shelves, a harbour and phone video with blurred side bars. Content and moment can be judged before any capture.
- **No OpenCV** in the environment. Frame checks will use numpy + Pillow (already used by War). Face detection without a model is weak (see Risks).

### A4. War code that already exists and will be reused
| Need | Existing War code |
|---|---|
| Entities, numbers, citations, claims, motion, location cues | `semantics.analyze_scene` (tested on audit scenes: it marks "Reuters reported…" and "Ukraine says…" as claims, finds 51 %) |
| Places with country | `catalog.find_place` + `data/places.json` (178 places, each with its country) |
| Facilities (refineries, bases, bridges…) | `data/strategic.json` (43 sites, only **1 refinery**: Kirishi, NORSI, Ryazan refinery etc. missing) |
| Equipment, figures, institutions | `catalog` + `data/equipment.json`, `figures.json`, `institutions.json` |
| Contradiction (other system, person, country, year) | `footage_match.score_clip` / `classify` |
| Internet Archive source with moment picking | `archive_fast` (`WarArchiveProvider`, `pick_moment`, `frame_problem`) |
| Stock source | `footage_discovery` (generic stock queries; non-CSV path only today) |
| Provenance and credits | `provenance.py`, `registry.py` |
| Graphics when there is no footage | `direction.py` (cards, CSV `graphic` column, motion cards, graphic floor), `map_build.py` (map stretches), `maps_tactical`/`map_events` (places, sites, moves), `subjects.py` (portraits), `storyline.py` (roadmap/chapters) |
| Writing to the Visuals tab | `AssetManifest.set` + `visual_bridge` (already used by `fix_repeats`) |

## Part B — Architecture

```
CSV + voiceover words
   │
   ▼
1 Narration reader ── sentence type + entities + actor/side + place + date + visual intent
   │                         │
   │                         └──► graphics intent (card / map / portrait / chapter) ──► direction.py (existing graphics)
   ▼ (EVENT, LOCATION, MOVEMENT, SUBJECT sentences only)
2 Query builder ── 3-5 entity-first queries per scene
   ▼
3 Sources (pooled) ── YouTube search ×N, Internet Archive (dated/historic), stock (generic SUBJECT only, labelled)
   ▼
4 Hard rules ── entity present, geography / country / side / subject / time contradictions, channel tier, duration
   ▼
5 Frames ── storyboard check: footage-like tiles, no studio/text/pillarbox/static; best 8 s window; tile hashes
   ▼
6 Authenticity (separate) ── origin channel, upload date vs event date, corroboration, red flags → class
   ▼
7 Dedupe ── same moment across scenes and across re-uploads (tile hashes)
   ▼
8 Capture + verify ── shared pool.acquire(id, start, 8 s) → validate_clip → captured frames vs storyboard
   ▼
9 Placement ── manifest record + provenance; no verified clip → the scene's graphics plan (never "any war footage")
```

### Sentence types and what each gets on screen
The director **never removes a graphic**. The CSV `graphic` column always wins, as today. Graphics are planned for every sentence; footage is an extra layer for the sentence types that can have it.

| Type | Example (038) | Footage? | Graphics (existing War kinds) |
|---|---|---|---|
| EVENT | "drones set the Ryazan refinery on fire" | yes, verified or corroborated only | headline/date card on footage, place pin on map when first named |
| LOCATION | "Kirishi, one of Russia's biggest diesel refineries" | yes if the place itself is filmed | map with site marker (`map_events` site), place label |
| MOVEMENT | "tankers changed course", "forces advanced from A to B" | yes if verified | tactical map route/advance (`_narrate_map`, `maps_tactical`) |
| SUBJECT | equipment / person | stock or archive allowed, **labelled illustrative** | equipment panel / portrait (`subjects.py`) |
| CLAIM | "Ukraine says…", "AP reported…" | no | source/claim card, quote card, stamp |
| STATISTIC | "51 percent", "up 19 percent", "40 hours" | no | stat panel, big number, comparison, chart kinds |
| ANALYSIS | "the picture is damage without collapse" | only a deliberate return of an accepted clip from the same subject | kinetic/keyword card, recap |
| QUESTION | "Is Russia really running out of fuel?" | no new search | title/question card |
| TRANSITION | "First…", "Second…", "Third…" | no | roadmap / chapter card (`storyline.roadmap`, `kit_chapter`) |

A sentence can carry two types (claim + event: "Reuters said Ryazan's unit was halted after an October attack"). The *event part* may get footage, while the *claim part* keeps its source card on top.

## Part C — Stages

Every stage is War-only, tested on its own, and leaves the old path working. The switch `footage_director` (War config + War Settings tab, **default off until Stage 9 is accepted**) chooses between the director and today's path.

### Stage 0 — Evaluation set first (baseline)
- **New:** `test_fixtures/war_director_eval.json`, made from the audit. For each of the 41 scenes in 038 and 033 it holds:
  - the narration
  - the expected type(s)
  - key entities, country and side
  - the hand verdict of today's clip
  - acceptable alternatives found in the audit (video ids)
- **New:** `cinematic_explainer/war/director_eval.py`. It scores a `discovery_report.json` against that set.
- **Metrics:** match / partial / generic / wrong, repeats, non-footage clips, graphics-only correctness.
- **Baseline recorded:** 038 = 1 / 3 / 6 / 7 (match / partial / generic / wrong).
- Candidate metadata is cached as text (titles, channels, descriptions). Third-party frames stay out of the public repo; frame tests use synthetic images.

### Stage 1 — Narration reader (`war/narration_read.py`, new)
- Builds on `semantics.analyze_scene` and `catalog`. Adds:
  - the sentence type (Part B table)
  - actor and side ("Ukraine's drones" → actor Ukraine; "Russia is hitting back" → actor Russia)
  - target and place (with country, from places/strategic)
  - date cues ("November 5", "in September", "overnight")
  - the event noun (strike, fire, queue, repair, export ban, tanker…)
  - a graphics intent
- **Data:** adds Russian/Ukrainian refineries, depots, ports and plants named in the War scripts so far to `data/strategic.json`. That's additive, and maps gain the same sites. Unknown capitalised names are flagged "unresolved place", never guessed.
- **CSV:** `read_scenes_csv` repairs a row split by an unquoted comma (scene 13).
- **Tests:** `test_war_narration_read.py`, over every 038/033 sentence plus synthetic ones (side reversal, a claim wrapping an event, rhetorical, transition).
- **Accept:** type correct for ≥ 38/41 eval sentences; actor/side correct for every sentence that names one; the scene 13 row is read correctly.

### Stage 2 — Queries and sources (`war/director_search.py`, new)
- **Queries:**
  - 3–5 per footage scene, from entities, never month words
  - `<facility/place> <event noun>`
  - `<agency> <place> <event noun>` for 2–3 agencies
  - `<place> <event noun> video`
  - the CSV prompt last
- **Pooled:** all results are merged (10 per query), not first-hit.
- **YouTube:** through `YtDlpBackend.search` (import only), plus `extract_info` for the shortlist.
- **Internet Archive:** through `archive_fast` when the date is before ~2005 or the CSV asks for archive.
- **Stock:** only for SUBJECT scenes, labelled.
- **Cache:** `state/war/director_cache/` (per video id: metadata, storyboard URLs) so Retry and Render never search again.
- **Pacing:** a pause between metadata calls and a cap per scene, so YouTube 429s are avoided.
- **Tests:** `test_war_director_search.py` (offline, fake backend: query shapes, pooling, cache, no month words, no Gemini import).
- **Accept:** for every eval scene whose alternative is known, that alternative is in the pooled set; discovery for 23 scenes in ≤ 6 min (network-dependent, measured once).

### Stage 3 — Hard rules and ranking (`war/director_rules.py`, new)
- **Reject** a candidate when:
  - **missing entity:** the title, description and tags don't name the scene's key place/facility/equipment (or its country, for a country-level event)
  - **geography:** a different named place or facility is the subject (e.g. Rostov warehouse for Kirishi)
  - **country/side:** the wrong country, or the actor reversed (Ukrainian drones for "Russia hits back")
  - **subject:** gas vs gasoline, warehouse vs refinery, US prices vs Russian prices
  - **time:** uploaded before the event date, or years away from a dated event
  - **format:** live streams, compilations, games/simulation/AI/animation, reaction/analysis/podcast titles, videos over 20 min for EVENT scenes
- Contradiction logic reuses `footage_match`; places and countries come from `places.json` / `strategic.json`.
- **Rank** the survivors:
  - **channel tier** (new `data/channels.json`: agencies and broadcasters > regional news > aggregators > commentary)
  - **short raw uploads first**
  - entity coverage
  - closeness of upload date to the event date
- **Tests:** `test_war_director_rules.py`, one case per audit failure (009, 015, 016, 017, 018, 021, 033 "hitting back") plus the 008 success.
- **Accept:** every "wrong" pick in the eval set is rejected by a rule that names its reason; the 008 Reuters clip still ranks first.

### Stage 4 — Frame inspection (`war/director_frames.py`, new)
- Fetch storyboard sheets for the top ~4 candidates. Mark each tile (numpy + Pillow):
  - pillarboxed phone video (blurred side bars)
  - text/article/graphic screen (high edge density on flat background, large uniform areas)
  - studio/presenter (static layout over many tiles + skin-tone block in the centre; heuristic)
  - black, still or near-duplicate frames
  - "footage-like" (scene change and motion between tiles)
- Choose the best 8 s window (4 tiles). For a short agency clip that's the most active stretch. For a long video it's the window that is footage-like and nearest any transcript hint.
- Each tile gets a 64-bit difference hash for Stage 6.
- **Tests:** `test_war_director_frames.py` with synthetic tiles (pillarbox, text page, flat studio, black, moving scene) and a stored storyboard sheet made from our own synthetic frames.
- **Accept:** detectors right on all synthetic cases. On the eval set (local only), every non-footage clip the audit found (011 poppy field, 015 presenter, 016 price graphic, 017 talking head, 018 article) is rejected or its window moved off the bad stretch.

### Stage 5 — Authenticity, separate from relevance (`war/director_authenticity.py`, new)
- **Class:**
  - `verified_event`: an agency/broadcaster channel, uploaded within days of the event date, entity in the title
  - `corroborated`: the same footage (tile hashes) in ≥ 2 independent channels; the earliest upload is noted as the likely origin
  - `unverified`: everything else
- **Red flags** cap a clip at `unverified`: AI/simulation/game markers, a "reconstruction" title, an aggregator channel with no date, an upload before the event.
- **Rule:**
  - EVENT and MOVEMENT scenes take only `verified_event` / `corroborated` clips.
  - LOCATION and SUBJECT scenes may take `unverified` clips, labelled "ILLUSTRATIVE" (the existing label).
  - Otherwise the scene goes to graphics.
- **Relevance and authenticity are two separate scores** in the report.
- **Tests:** `test_war_director_authenticity.py`.
- **Accept:** no EVENT scene in the eval set gets an `unverified` clip; each class is explained in the report.

### Stage 6 — No repeats (`war/director_rules.py`)
- A global set of moments already used: a video id with an overlapping window is rejected.
- A tile-hash match against any used moment (Hamming ≤ threshold on ≥ 2 of 4 tiles) is rejected, which catches the same phone video re-uploaded by Daily Mail, NY Post and Kanal13.
- At most 2 moments per video per film. "Find another clip" excludes everything already used.
- A deliberate return (an ANALYSIS sentence) is marked `reused`, never presented as new.
- **Tests:** in `test_war_director_rules.py` (same id overlap, re-upload with a different id, 3rd moment of one video).
- **Accept:** 0 repeated moments in the eval run, including across URLs.

### Stage 7 — Capture and verification (`war/director_capture.py`, new)
- `get_client().acquire(video_id, start, 8, dest)` through the shared pool (no edit).
- Then:
  - `validate_clip`
  - `archive_fast.frame_problem`
  - **moment check:** captured frames are compared with the storyboard tiles around `start ± 4 s`; the best match gives the real offset, no match rejects the capture (ad, wrong seek)
  - pillarbox check on the captured file
- Failure → next candidate (max 3), then graphics.
- **Write** the manifest record: `source: youtube_video`, `video_id`, `source_url`, `channel`, `upload_date`, `clip_start` (verified offset), `selection_method: war_director`, relevance score, authenticity class, reasons, and the provenance fields `provenance.py` reads. Also a `registry` entry by file content.
- The Visuals tab shows it like any clip. A clip the user picked (`user_override`, manual, local) is **never** touched.
- **Tests:** `test_war_director_capture.py` with a fake pool (ok, ad, wrong moment, failure, user pick kept).
- **Accept:** every placed clip passes the moment check; the provenance fields are complete for 100 % of placed clips.

### Stage 8 — Graphics and placement (`direction.py`, small additions)
- **Graphics plan:** the director's per-sentence decision becomes the scene's plan.
  - A scene with no verified clip is `no_footage` (already supported), so the existing map stretches, cards, motion graphics and graphic floor fill it.
  - The Stage 1 graphics intent is passed as a hint, so CLAIM sentences get a source/claim card, STATISTIC a stat panel, TRANSITION a chapter or roadmap, LOCATION/MOVEMENT a map.
- **Kept as today:** the CSV `graphic` column still wins. The existing card spacing and overlap rules still apply. No graphic kind is removed.
- **Source chip:** footage gets a small source line using an existing badge kind ("Video: Reuters · 5 Nov"), and the credits file lists every clip's channel, URL, upload date and class.
- **Tests:** extend `test_war_no_garbage.py` / `test_war_layouts.py`:
  - claim/stat/transition scenes get their card kind
  - no bare backdrop over 0.5 s
  - the CSV graphic is kept
  - every old graphic kind can still be produced (compared against the current plan for the eval CSVs)
- **Accept:** on both eval CSVs (plan only, no render):
  - 100 % of claim/stat/question/transition sentences have a graphic
  - 0 s of bare grid
  - the set of graphic kinds used is not smaller than today's plan

### Stage 9 — Wiring, report, CSV prompt
- `app_section.fetch_csv_footage`: with the switch on, YouTube/footage rows go to the director, and other rows (local, Flow, stock-only) follow today's path.
- `state/war/discovery_report.json`: queries, every candidate, scores, rejection reasons, chosen window, authenticity, capture check. The Visuals tab shows the one-line reason per scene.
- `data/war_csv_prompt.txt` (War-only): asks for entity + event queries, marks claim/stat/question/transition sentences `none` with a `graphic`, and quotes text with commas.
- **Tests:** `test_war_app_section.py` (switch on/off, user picks kept, no Gemini calls), the whole War suite, `test_weather_isolation.py` (proves no shared/protected file changed).
- **Accept:** see Part D. After acceptance the switch defaults to on.

### Stage 10 — No grey grid, no blank frames (problem 11)

**Audit (2026-11-09, `render_qa.py` on the finished 038 and 033 videos, every flagged stretch checked by eye).**

The backdrop enters the War code in four places: no-footage scenes (`integration.py:383`), timeline holes (`backdrop.fill_gaps`), a clip with no picture (`segments.swap_pictureless`), and a piece that fails twice (`segments.py` ~905).

| Cause seen | Evidence | Kind |
|---|---|---|
| Number/stat cards that build up on the empty grid | 038 0:31.4–0:36.1, 033 0:17.7 | bare |
| Maps drawn as thin outlines over the grid | 038 0:05.5–0:15.6, 0:36.1–0:43.1; 033 1:02.8–1:10.6, 1:26.4–1:32.2 | sparse |
| Small claim/stat card alone on the grid | 038 0:07, 1:37 | sparse |
| 3.5 s source clip ran out → grid with an orphan "UNVERIFIED · ABC NEWS" chip | 033 2:00.3–2:01.2 | bare |
| Card kinds refused on another machine (earlier Ahmed's-Mac report) → the scene's card missing over the grid | reported by the owner on other systems; logs needed | bare |

**Fix:**
- **No-footage stretches:** a no-footage stretch has a full-frame look: the scene's footage return, a filled map, or a motion card. Never a lone card on the grid.
- **Card failure:** a card that fails to draw is replaced by a full-frame motion card (kinetic/keyword) and logged.
- **Clip ending early:** a source chip never outlives its clip.
- **QA gate:** the final-render check runs after every War render, writes `final/<name>.qa.txt/.json` with times and reasons, and logs a warning line.

### Stage 11 — Shot durations, no one-second clips (problem 12)

**Causes found:**
1. `_fit_short_clips` cuts a running-out clip to `max(min(1.0, scene), left)`, which can be about 1 s.
2. `_broll_returns` fills the rest with returns as short as 1.2 s.
3. `MIN_SHOT_S` = 2.0, so slivers of 2 s survive.
4. Short sources (3.1–3.5 s in 033).
5. The source's own edit inside our capture (038 1:13.8 0.8 s; 033 1:57.3–2:00.3).
6. A frozen last frame (`tpad clone`) when a clip runs short.

**Fix:**
- **Footage shots:** 3 s minimum, 3–6 s typical. Shorter only inside the montage hook.
- **Moment choice:** the director picks windows with no internal cut (storyboard scene changes).
- **A clip too short for its slot:** handled by the neighbour or a graphic, never stretched or frozen.
- **Return lengths:** the minimum b-roll return goes to 3 s.

### Affected files (all War-only)
- **New code:** `cinematic_explainer/war/narration_read.py`, `director_search.py`, `director_rules.py`, `director_frames.py`, `director_authenticity.py`, `director_capture.py`, `footage_director.py` (orchestrator + report), `director_eval.py`.
- **New data:** `cinematic_explainer/war/data/channels.json`.
- **Data, entries added only:** `data/strategic.json`.
- **Changed (small, War-only):** `cinematic_explainer/war/app_section.py` (switch + CSV repair), `direction.py` (graphics-intent hint, source chip), `data/war_csv_prompt.txt`, the War Settings switch (inside War's own section; `app.py` untouched unless a line must be added, which would be additions only and asked first).
- **New tests:** `test_war_narration_read.py`, `test_war_director_search.py`, `test_war_director_rules.py`, `test_war_director_frames.py`, `test_war_director_authenticity.py`, `test_war_director_capture.py`, `test_war_footage_director.py` (end to end, offline fakes), plus `test_fixtures/war_director_eval.json`.
- **Not touched:** `providers/**`, `asset_manager.py`, `visual_bridge.py`, `browser_worker.mjs`, `app.py` (unless approved), other styles, the protected manifests.

## Part D — Acceptance criteria (measured on the 038 + 033 eval set, discovery + plan only, no render unless you ask)

| # | Criterion | Today | Target |
|---|---|---|---|
| 1 | Clips judged **wrong** (wrong place, side, subject, opposite meaning, not footage) | 7 / 17 (038) | **0** |
| 2 | Placed clips judged match or partial | 4 / 17 | **≥ 90 %** of placed clips |
| 3 | EVENT/LOCATION/MOVEMENT scenes with a clip naming their own entity | ~3 | **≥ 70 %** (the rest go to graphics, not filler) |
| 4 | Repeated moments (same id or same footage across URLs) | 5× one shot | **0** |
| 5 | Talking head / studio / text screen / pillarboxed phone clips placed | 13 | **0** (pillarbox only if nothing else exists *and* the class is verified, cropped and labelled) |
| 6 | Claim/stat/question/transition sentences shown with a graphic | partial | **100 %**, CSV `graphic` column always honoured |
| 7 | Bare grey grid on screen | yes | **0 s over 0.5 s** |
| 8 | Placed clips with full provenance (channel, URL, id, upload date, cut second, authenticity class) | partial | **100 %**, listed in the credits file |
| 9 | EVENT scenes with an `unverified` clip | n/a | **0** |
| 10 | Cut points verified against storyboard frames | 0 | **100 %** of placed YouTube clips |
| 11 | Gemini/API calls | 0 | **0** (test asserts) |
| 12 | Shared/protected file changes; other styles' tests | — | **none**; isolation test green |
| 13 | Discovery time for a 23-scene CSV | ~1.5 min | **≤ 6 min** (capture time unchanged) |
| 14 | Bare grid in the finished video (render_qa) | 038: 2.6 s / 033: 1.6 s | **0 s** |
| 15 | Sparse grid (graphics under 30 % of the frame) | 038: 21.0 s / 033: 22.6 s | **≤ 1 s per stretch** |
| 16 | Blank (black/flat) frames | 0 / 0 | **0 s** |
| 17 | Footage shots under 3 s outside the montage hook | 038: 1 / 033: 2 | **0** |
| 18 | QA report with exact timestamps and reasons written for every War render | no | **yes** |

### Stage 0 baseline (measured 2026-11-09 with `director_eval`, today's manifests)

| Metric | 038 (23 scenes, 17 clips) | 033 (25 scenes, 18 clips) |
|---|---|---|
| match / partial / generic / wrong | 1 / 3 / 6 / 7 | 1 / 2 / 4 / 11 |
| good share of placed clips | 24 % | 17 % |
| footage scenes with a clip naming their entity (not wrong) | 3 of 9 | 2 of 6 |
| repeated clips | 4 (one shot ×5) | 3 (one shot ×4) |
| non-footage / pillarboxed clips placed | 14 | 7 |
| claim/stat/question/transition scenes covered by footage | 9 | 10 |
| full provenance / moment verified / event clips unverified | 0 / 0 / 6 | 0 / 0 / 6 |

Re-run: `python -m cinematic_explainer.war.director_eval --render 038 --manifest <project>/state/war/assets/.asset_manifest.json` (or `--report` for a director report). Tests: `test_war_director_eval.py`.

## Risks and open points
- **Face detection without a model is weak.** The studio/presenter check uses layout and stillness heuristics. Adding `opencv-python-headless` (bundled face detector) would make it reliable, but it's a new dependency in the packaged app → only with your approval.
- **YouTube limits:** many metadata calls can trigger 429s. Mitigation: shortlist ≤ 4 videos per scene, cache, pacing. Storyboards may be missing on some videos; those candidates drop a tier rather than being guessed.
- **8 s per capture:** shots longer than 8 s need two captures of the same video (allowed, verified the same way).
- **Hand verdicts are judgement calls.** The eval set records the reason for each verdict so it can be reviewed.
- **Authenticity is an estimate** from public signals (agency, dates, corroboration), never a guarantee. The report and labels say so.
- **Fewer clips:** the stricter rules will leave some scenes without footage. That is intended: they get War graphics instead of unrelated footage.
- **Not in scope:** the protected capture quality fix (`convertToMp4`) from Step 1. It's still awaiting your separate decision.
- **Order:** 0 → 1 → 2 → 3 → 4 → 6 → 5 → 7 → 8 → 9. Each stage ends with its tests and an eval run. Nothing is committed without your approval.
