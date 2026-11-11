# War engine fix plan — after render 050 (Ukraine update, 2026-11-11)

Render: `~/Downloads/VideoGenerator/Video_2026-11-11_050_ukraine_war_update` (24:36). Contact sheets: `review/sheets/` (1 frame / 3 s).
Owner verdict: first clip garbage, many clips don't match narration, maps boring, graphics boring, rich panels never came, many broken scenes.
Rule: fix the general rule in code + a synthetic test, never tune for this video.

## What the render shows (numbers)
- Footage on only **75 of 255 scenes**; ~120 scenes sent to graphics by the Footage Director's sentence reader.
- Graphics used: tac_map 82, **keywords 72**, kit_field 53, locator 34, **kinetic 26**, stat split 12, bignum 12 — timeline 0, compare 0, chart 0, supply 1.
- Same clip reused up to 5x (Kremlin round table, Putin-in-truck, Kanal13 aerial, NY Post drone).

## Root causes found in the code
| Symptom | Cause |
|---|---|
| 0:00 clip = UATV studio graphic about a satellite system | `director_frames.classify` calls a photo+text news panel "footage" (it only catches pale full-screen text, presenter skin in the centre, flat graphics). The window was picked inside a 15-min news show by title words ("drones, petersburg"); transcript hint weight is `/30`, so the moment is unchecked. |
| Bad picks survive a rerun | `footage_director.run`: "chosen by an earlier run: kept" — old picks are never re-checked. |
| Ticker from another war (15:51), "SUBSCRIBE" outro (7:42), Kyiv Times "~7,000" graphic (16:42), Donetsk clip for Kirishi (8:27) | No ticker/lower-third/outro detector; no check that the clip's own place/war label matches the sentence. |
| Same clip 4-5x on unrelated lines | `direction._broll_returns` refills empty spots with any of the video's clips; no subject match, no per-source cap. |
| Talking heads with burnt subtitles | `caption` flag only lowers the score (-2.5), never rejects. |
| Event sentences get no footage | `narration_read.read` marks anything without a named place as ANALYSIS → `footage_director.graphic_for` → **"keywords"** (the catch-all). Live-search slots are spent in script order, before the director drops rows, so key events (Abu Dhabi, prisoner swap, Kyiv strike, grid) got nothing. |
| "WITHDREW / RUSSIAN / COUNTRY" | `direction._motion_options` builds kit_keywords from entity names / long words of any sentence. |
| "two WEEKS WHERE", "one MATTERS EVEN", "2 SIDES Reported by Reports", "0", "100 DOLLARS" | `narration_read._statistic` counts number words (one/two/three, "three-way") as figures; `direction` number_raw labels a bignum with the **next 4 words**; "a few hundred dollars" → 100; "S-400" → "400". |
| "THE INSTITUTE ALSO POINTED", "AND ON", "IN" | kinetic accepts sentence fragments; no rate limit in practice (26 in 25 min). |
| Washington map for "oil export income" / "drones fleet" | `direction._point_bare_maps` pins the last place named within `BACK_REF_S`, across topics. |
| Maps that look like an empty blue sea | close zoom (`close_steps`) on one city with no minimum frame size; Ukraine fill ≈ sea colour; no borders/rivers in frame. |
| Donetsk, Bakhmut, Mariupol, Melitopol painted Ukrainian | `data/frontlines/` is empty (README only), so no occupied-area layer is ever drawn. |
| Blank 3-6 s screens, empty cards, half-built cards, overlaps | `kit_field` (backdrop) counts as coverage in `_final_coverage`; card reveal starts with an empty frame; no single-text-layer rule per screen region; chapter cards sit on an empty field. |

## The fix, in build order

### Phase A — footage that matches the narration (owner's #1 complaint)
1. **Frame check on the real clip, not only storyboard tiles** (`director_frames`): sample the cut window at 2 fps after download and reject a window with any of
   - lower-third / headline bar (wide flat-colour band with dense text edges in the bottom 35 %),
   - text panel next to a photo (one half text-dense, other half still),
   - ticker (moving text band at the bottom),
   - presenter / studio / "subscribe" end-card (existing studio rule + big logo/social-handle text),
   - burnt subtitles on more than half the window (now a reject, not -2.5),
   - watermark/handle text (t.me/…, channel bug) covering > 2 % of frame for the whole window.
2. **Moment must be on topic**: in videos longer than 4 min, the window must sit within ±20 s of a transcript hit for the sentence's key term; no hit → next candidate. Prefer videos under 4 min.
3. **Place/war contradiction**: reject a clip whose title, description, burnt-in label or transcript names a different place on the same side (Donetsk for Kirishi) or another war (Israel, Lebanon, Gaza, Syria …). Uses the existing `contradictions` list.
4. **Re-check old picks** with the new checks instead of "kept".
5. **Reuse rule**: one source video at most 2 uses per film, 3 min apart; `_broll_returns` may only reuse a clip whose subject matches the sentence (Putin/Kremlin clip only for Putin/Kremlin lines).
6. **Footage for event sentences**: a sentence with no named place inherits the section's subject (previous sentences' places / terms / equipment) instead of becoming ANALYSIS. Only true linking lines become graphics.
7. **Live searches by value, not order**: rank rows (named event + place + date first) before applying `war_live_searches`; rows the director will turn into graphics never use a slot.
8. **Library hygiene**: remove `factory_workers` "Mr. Untold Factories" clip; AI-badged clips only when the owner switches them on.
Target: footage on ≥ 60 % of screen time, no clip shown more than twice.

### Phase B — rich graphics instead of word salad
1. **No keyword card from random words.** kit_keywords only for a real list in the sentence (3+ comma items). Otherwise the sentence gets footage (Phase A6) or a rich panel.
2. **Real numbers only.** A bignum needs digits or a number word + countable noun ("1,500 prisoners", "36 ballistic missiles"); never "two weeks", "three-way", "one", "first". Label = the noun phrase of the figure, attribution only when an outlet is named. "a few hundred", "S-400", "Kh-59", "Su-34" are not figures (S-400 → equipment).
3. **Kinetic** only for a whole sentence of ≤ 8 words, max 1 per 90 s.
4. **Turn on the rich panels that never fire** (all built from the narration, across sentences of one section):
   - timeline: 3+ dated sentences in a row (the 7 refinery strikes Oct 30 – Nov 7) → one timeline that adds a row per sentence;
   - compare: two figures of the same kind close together (162 vs 155 drones, 205 vs 156 clashes);
   - equipment: every named system (Patriot, Iskander-M, S-400, Pantsir, Kh-59, Shahed, glide bomb/KAB, FPV drone) with photo;
   - speaker / figure cards for named people (Zelensky, Putin, Trump, Drozdenko);
   - institution cards (ISW, Rostec, Surgutneftegas, Transneft, Lukoil, Rosneft);
   - section recap panel at each "Part …" end.
5. **Plan gate**: ≥ 1 rich panel per 45 s; keywords ≤ 1 per 2 min; bignum ≤ 1 per 60 s; fail → replace before render.

### Phase C — maps that move and are right
1. **No carry-over pins**: a bare map only uses a place named in the same or previous sentence of the same section; no place → no map (fixes Washington, Kirishi-for-Ust-Luga, Orikhiv-for-"deep inside Russia").
2. **Readable framing**: minimum frame ~250 km with borders, rivers and 4+ city labels; Ukraine fill clearly different from sea.
3. **Occupied areas**: add a sourced control layer (Russian-held area GeoJSON, dated) in `data/frontlines/`; one download, reused for every video. Until it exists, never paint occupied oblasts as Ukrainian (neutral contested fill).
4. **Campaign map**: dated strikes on named targets → one map that adds a burst + date chip per sentence (refinery campaign), camera moving between them.
5. **Always moving**: something new on a map every ≤ 3 s; map hold ≤ 8 s; same framing not repeated within 60 s.

### Phase D — no broken scenes
1. Backdrop-only (`kit_field`) spans count as holes in `_final_coverage` → filled with a matching clip or the neighbour extended.
2. Cards enter with their content (no empty/half-built frame > 0.3 s); dossier/keyword never with an empty body; titles fit (shrink/wrap, no "THE GRID HAS FEWER SPARE PA").
3. One text layer per screen region at a time (sticker over list, headline over headline, panel over interview).
4. Chapter cards over footage of the section, not a blank field; outro over a short montage, never a blank screen.
5. Render QA becomes a gate: blank > 0.5 s, empty card, repeated clip, text-on-text → auto-fix pass, then report.

### Phase E — checking without burning time
- Synthetic tests per rule (new `test_war_render050_fixes.py`).
- Plan-only check on this CSV (no render): footage %, rich-panel rate, keyword count, map places vs sentence.
- Then one 3-minute slice render + contact sheet; full re-render only when the owner asks.

## Open decision for the owner
- Front-line data source for C3 (needs a one-time download, e.g. a public dated GeoJSON of Russian-controlled territory).

---

## Owner's requirements (2026-11-11) — the build order now used
A baseline + regression fixtures -> B footage integrity (video relevance, moment relevance, visual usability as three separate checks; every
earlier pick re-validated; no arbitrary fill; subject discovery for lines without a place) -> C graphics integrity (no random keyword
fallback, semantic numbers, rich panels only when supported, complete synced cards) -> D rendering + final-frame QA (judged on real output
frames, compared with narration/storyboard) -> E map integrity (explicit subject/scope/data/zoom, no inherited places; territorial data a
separate step, source shown to the owner before any download) -> F integrated validation (scene plan + one 3-minute sample, no full render).
War only; no shared downloader/browser/other-style changes; no Gemini/new APIs; dirty/untracked files kept; no commits.

## Stage A report — baseline and regression fixtures (done 2026-11-11)
Preserved: `Video_2026-11-11_050_ukraine_war_update/baseline_050/` (APFS clone of project, csv, audio, final incl. mp4, logs, review
sheets) + `BASELINE_MANIFEST.txt` (git HEAD, dirty files, sha256 of every report/decision file).

New files (War only):
- `cinematic_explainer/war/plan_audit.py` — measures a plan against its narration without rendering: footage share, backdrop-only time
  (a background is not coverage), reuse per SOURCE video, keyword/kinetic counts, kinetic fragments, number cards with no stated quantity,
  map places the narration does not name.
- `test_fixtures/war_render050/`: `scenes.json` (255 aligned lines + their sources), `defects.json` (every defect seen, by stage and
  component), `baseline_audit.json`, `director_decisions.json`, `targets.json`, `frames/` (28 real frames from 14 clips + `labels.json`).
- `test_war_render050_baseline.py` — 12 tests, all pass.

Baseline (plan audit of render 050): footage 25 % of 24:36; backdrop-only 125 s in 20 stretches; 11 source videos used 3-6x; keyword
cards 72; kinetic 26 (20 fragments); 12 figure cards with no stated quantity; 52 map pins of places the line does not name.
Frame check baseline: `director_frames.classify` accepts all 8 unusable frames (studio panel, end screen, ticker, lower-third,
talking heads, channel graphic) as footage.

Root causes added by stage A:
- Library reuse: `library.py` matches a row's CSV prompt, not the line's meaning, and allows MAX_USES 3 — one road clip went to scenes 4, 17,
  34 and one Kremlin clip to 38 and 51 because they shared a generic prompt. (The generic prompt came from our own CSV builder; the engine must
  still refuse a clip whose subject the line does not mention.)
- Planning the 255-scene film takes ~290 s before any rendering (planner + harden_measured) — to be measured and reported in stage F.

## Stage B report — footage integrity (2026-11-11)
Decision points traced first (each render-050 footage defect -> the line of code that let it through):
| Defect | Decision point | Fix |
|---|---|---|
| Studio panel, end screen, ticker, lower-third, subtitled interviews, another channel's graphic accepted as footage | `director_frames.classify` saw no text (and capture checked frames at 160x90, where a subtitle is 1-2 px) | `text_lines` / `text_kind`: text read by line SHAPE (wide, short, isolated runs of character strokes) at 320x180; kinds `overlay_text`, `text_graphic` added to `BAD`; `director_capture.text_on_frames` refuses a captured clip with text on > 15 % of its frames |
| Render 050's first clip survived a second run unchecked | `footage_director.run`: "chosen by an earlier run: kept" | `footage_director.revalidate`: every earlier director pick passes the same visual + relevance + moment checks or is searched again (user picks stay untouched) |
| A 15-min programme cut at a satellite segment for a drones line | `choose_window` got no transcript hint; nothing checked the moment | `director_moment`: programmes > 4 min are cut only within -20/+45 s of a transcript passage that names the line's subject; no transcript -> refused. `director_search.Searcher.transcript` (cached; parsers reused from providers, unchanged) |
| Lines without a place sent to graphics without any search | `narration_read.read`: no place -> ANALYSIS/STATISTIC -> `footage_wanted` False | `narration_read.read_scenes` gives every line `section_terms` (its own filmable subject, else the latest concrete line within 4 lines, else the part's topic; reset at "Part ..."); `footage_director.widen_to_section` searches those; own-event lines pick first |
| One library clip on 3-5 unrelated lines | `library.plan` matched the CSV prompt only; MAX_USES 3 per file | `library.line_fits`: a clip's subject must be in the line or its section; MAX_USES 2 per SOURCE video; live slots spent on most specific lines first; `usable_clips` runs the text check on library clips (cached in `<library>/.usability.json`) |
| Arbitrary b-roll returns (Putin-in-truck x4) | `direction._broll_returns`: with no earned clips any clip returned, second pass up to 8x, same seconds re-shown | returns only over a line about the clip's subject, per source, unused seconds only, no second pass; a stretch nothing fits is composed by `_no_empty_stretch` (a side panel on the bare plate gives way to a full-frame graphic from the same line) |

Tests added: `test_war_footage_integrity.py` (24: real-frame windows, old-size failure shown, synthetic text/texture, capture refusal, subject discovery on the 050 script, moment check incl. the UATV case, re-validation of the 050 first clip, library line relevance / source reuse / cached checks). Changed existing tests (old behaviour the owner overruled): `test_war_library.py` fixtures now use narration that says what the prompt asks for + library check cache, MAX_USES 2 expectation; `test_war_no_garbage.py` return test now uses subject-matched clips, plus 2 new tests (no return to an unrelated line / a line with no text). Full War suite: 751 passed, 1 skipped.

Measured on a clone of render 050 (`stageB_050/`, no live search, no render): library visual check refuses 9 of 157 clips (7 real burnt text, 2 false positives: harbour cranes, circuit-board print); re-validation keeps 9 of 20 director picks and refuses 11 (all 8 bad clips from the review + 3 moment failures); 134 lines now search their section's subject. Plan audit vs baseline: reuse 11 -> 0 sources; footage 25 % -> 11 % (bad clips removed, replacements need a live Generate scenes); backdrop-only 125 -> 126 s; keyword cards 72 -> 82; map pins of unnamed places 52 -> 165 (more footage-free stretches are filled with maps that inherit places: stage E defect, now more visible).

Open after B: burnt place labels inside otherwise clean footage (TVP 'DONETSK REGION' for Kirishi) need OCR - not available; a talking head with no text (Zelensky address) is caught only by title rules / relevance; a 4-min programme without captions is now refused (may cost good footage); `text_screen` (old pale-area rule) still misreads bright skies in the Footage Director's own checks; planning the 255-scene film took 618 s on the clone.

## Stage B.1 audit (2026-11-11) — findings only, nothing implemented
Measured on `stageB_050/` (clone, offline) vs render 050. New measurement only: `plan_audit.map_view` (pins and camera as maps_tactical renders
them: a pin appears at its own start time; the raw `map_foreign_places` count is kept unchanged for comparison with Stage A).

1 Maps. The raw 52 -> 165 counted pins the renderer had not drawn yet. Renderer-faithful: pins appearing unspoken 11 -> 17; camera centred on
  an unspoken place 24 pieces / 116 s -> 23 / 111 s (pre-existing); OLD pins still on screen 25 / 97 s -> 97 / 178 s; longest building map
  87 s -> 307 s. Decision points: `map_build._runs` makes one map for any run of footage-free scenes (no length or section limit) and
  `_plan_params` keeps up to 8 pins for the whole map (no pin end time in maps_tactical); the run grew because B removed bad clips with no
  replacement yet. `map_build._plan_params` `context` fallback and `direction._point_bare_maps` (BACK_REF_S 150 s) put earlier places on maps
  whose line names none (St Petersburg for Abu Dhabi; Abu Dhabi is not in places.json). Smallest corrections proposed: (a) `_point_bare_maps`
  takes a place only from the map's own line or the line before it in the same section; (b) drop the `context` fallback; (c) `_runs` breaks at
  a section heading and after ~90 s, so pins reset. Pin end times in the renderer are a Stage E change.
2 Coverage (backdrop-only 125 -> 126 s). 050: transparent card on the plate 114 s (mostly the junk word bignums), field only 8.7 s, corner
  only 2.1 s. B: transparent card 86 s, field only 37.3 s, corner 2.3 s. The new empty time is `map_build.cap_pieces`: every 12 s of map it
  leaves a 4 s break for `_broll_returns`, which now (correctly) refuses unrelated clips, and `_no_empty_stretch` finds "nothing truthful"
  (`_phrase_or_lead` returns no phrase). Proposed: reserve a break only when a subject-matched clip exists for that run.
3 Planning time. Same conditions: 050 ~490 s, B ~497 s (planner 104/88 s + harden_measured 381/406 s); the 288 s / 618 s figures were
  taken under different machine load (618 s ran beside the full test suite). Stage B's checks run at fetch time, not in planning. ~80 % is
  `harden_measured` rendering 734-818 map frames: 82-105 mosaic builds, coastline shading ~150 s. Redundant work / caches: mosaic + coast shade
  per view; card cover per (params, t); `semantics.analyze_scene` 4,000 calls for 255 lines; `source_cuts` ffprobe 187-446 runs; clip decodes
  in `_fit_earned_shot`. Fetch side: 8 transcript calls (cached per video), library check once (cached), re-validation decodes each kept clip.
4 Live replacement test (proposal, not run): see the owner report.
5 Detector reliability: library 157 (reviewed) -> 9 refused, 7 real, 2 false (cranes, circuit board); 38 unreviewed fetched clips -> 23
  flagged, 23 real (0 false); misses are outside its scope (diagonal handle watermarks 3, a big logo, talking heads, studio split, a map
  screenshot without text). Old pale-area `text_screen`: 5 / 157 library (all false), 0 / 38 fetched. The pre-existing capture rule
  (>30 % of frames in BAD incl. dark / graphic) would refuse 36 / 157 clean library clips (night, fog); re-validation reuses it.
6 Evidence: BASELINE_MANIFEST hashes all OK; Stage A fixtures unchanged since 5509fb5; test changes in 5509fb5 removed no assertion.
7 Git: 5509fb5 authored and committed by Nabil6244 2026-11-11 23:00:43 +0500 with a Claude co-author line (made from another session);
  49 files. Uncommitted: direction.py (SIDE_CARDS), plan_audit.py (map_view), this doc.

## Stage B.2 — map corrections + controlled live-fetch slice (2026-11-12)
Code (War only): `direction._point_bare_maps` takes a place only from the map's own line(s) or the line just before, same section (no
BACK_REF_S reach-back); `map_build._plan_params` has no `context` fallback (a run naming no geography gets no map); `map_build._runs` breaks at a
section heading and after MAX_RUN_S 90 s; `map_build.split_by_geography` ends a map earlier when a line names only places > GEO_NEAR_KM 400 km
from everything on it (or, with no towns, no shared country). Each map's pins start empty. Renderer untouched (pin end times = later stage).
Side effect fixed: shorter maps carry no routes, so `_strike_maps` fired on a CSV flyover row and cleared it; `_strike_maps` now skips seconds
holding a CSV graphic. `test_war_plan_guard.ALLOWED` + "no_footage:tac_map@0.0" (94 s map split at the geography changes, same total time).
Tests: `test_war_map_b2.py` 9 (all fail on HEAD): Abu Dhabi/St Petersburg, Washington on oil-export income, line-before-only, old pins across
subjects, map across sections, 90 s runs, section break, no context fallback, same-region stays one map. War suite before the side-effect fix:
760 passed / 2 failed (both above, now pass); touched files after: 118 + 20 pass. Still inheriting: `_strike_maps` _BACK_REF (150 s) — not in scope.

Live slice (clone `stageB2_live/` of baseline_050, scenes 17-32 + 78-90 = 178 s, other rows read but not fetched, war_live_searches 15,
Generate scenes only). Files: `stageB2_live/slice_lines.json` (per line: decision, clip, queries, rule rejections, candidates and why),
`slice_contact_sheet.jpg`, `slice_run.log`, `project/discovery_report.json`.
- 480 s total: library 11 s, director 463 s (search+details+storyboards 181 s, 7 captures ok 145 s, 4 failed 87 s); 23 searches, 15 transcript
  calls, 7 transcript 429 (rate limit). 346 candidates rejected by rules (prompt 169, format 139, country 31), 47 shortlisted, 20 refused on frames.
- Footage on 9 of 23 footage rows (050: 7), 9 unique sources (050: 6). Judged on frames:
  relevant 4 = 26 AP Abu Dhabi talks podium (prisoner line, contextual), 28 NBC Kremlin/officials (contextual), 79 Afipsky aerial (place,
  illustrative), 80 Kanal13 Saratov smoke (exact, kept); ~26.9 s on screen (050 same lines: ~9.7 s relevant of 31.2 s shown).
  weak 1 = 24 FRANCE 24 window is a Zelensky selfie address (talking head) for the talks line.
  wrong 4 (~18.8 s) = 18 Reuters "Abu Dhabi's Growth Plan" business panel; 78 AP Putin-Kushner for "Ryazan refinery"; 86 Reuters St Petersburg
  protest arrests for fuel supply; 89 TVP 'DONETSK REGION' clip re-validated and kept for Kirishi.
- Removed correctly, not replaced: 84 UATV end screen, 90 Moscow-refinery clip for Kirishi, 17 Pokrovsk roads for Washington.
Root causes seen: (1) R.match_level gives "exact" when the title names the place alone (Abu Dhabi, St Petersburg) with no event word;
(2) `_prompt_subjects` puts the CSV prompt's subject (Putin, Kremlin) ahead of the line's own (Ryazan refinery) — first query was
"Putin meeting Kremlin"; (3) no OCR, so burnt place labels pass re-validation; (4) transcript 429s turn long programmes into "cannot be
checked" refusals (84, 87, 90 lost candidates); (5) 4 rows sent to graphics by the library with no search (27, 31, 32, 83).
Verdict: replacement works (prisoner lines got real footage, 050 had none) but precision ~4/9 — not yet dependable. Stage C not started.

## Stage B.3 — narration-first matching + repeat slice (2026-11-12, uncommitted)
Code (War only): `director_rules` place / event / subject judged separately (`dimensions`, `events_in`, event families, `stale`); exact =
the line's event AND its place or subject in the title, not uploaded before the event; a title about another kind of event (protest,
business, a meeting for a refinery line) is rejected. `footage_director.prompt_conflict`/`queries_for`: a CSV prompt about something
else (other event family, or none of the line's own places) is only a last search hint, never key terms or a gate. `burnt_label` +
`_location_verdict`: text lines on >= 2 frames / 20 % = location unverified (never exact); unread label + footage older than a named-place
event = refused (also in revalidate). `narration_read`: `section_date`; a missing year comes from the latest year reached, not an aside
('demands made in 2021' had dated every November line 2021). Transcripts (subagent): caption track + chapters cached with details, 429 ->
4 s / 12 s backoff, 60 s cooldown, never cached; `moment_check` passes status/chapters -> 'rate-limited: not checked', never 'irrelevant'.
Tests: test_war_footage_b3.py 9 (business panel, Putin-Kushner vs Ryazan, protest vs fuel, place alone not exact, older Kirishi package with
a label, right video wrong moment + rate-limit wording, year aside, Moskva prompt kept, real label frame) + test_war_transcript_limits.py 7.
War suite: exit 0.

Repeat slice (`stageB3_live/`, fresh clone, same lines, limit 15; B.2 evidence in `stageB2_live/` untouched). Judged on frames:
| | B.2 | B.3 |
|---|---|---|
| lines with footage | 9 | 6 |
| relevant | 4 lines / 26.9 s | 4 lines / 25.7 s (26 AP talks podium, 28 NBC Kremlin/officials, 78 Kanal13 Ryazan refinery, 79 Afipsky aerial) |
| wrong / unusable | 5 / 26.8 s | 2 / 12.7 s (18 Reuters 'Abu Dhabi and IHC' business-market clip; 24 FRANCE 24 Zelensky selfie talking head) |
| precision | 4/9 = 44 % | 4/6 = 67 % |
| eligible lines with relevant footage | 4/23 | 4/23 |
| unique sources | 9 | 6 |
Levels (judged): exact 0, contextual 3 (26, 28, 78 = Nov 2025 Ryazan strike, honestly labelled contextual), illustrative 1 (79, 2023).
Engine labels: exact 1 (24), contextual 4, illustrative 1. Time 829 s (B.2 480): search/preview 168 s, 6 captures ok 234 s, 8 failed 209 s,
other 155 s (backoff waits); 23 searches, 20 transcript calls, 7 rate-limited (now explicit). Rejections: 390 by rules (format 161, prompt
139, country 44, entity 20, event 11, time 7), 64 shortlisted, 26 refused on frames, 20 on moment.
Fixed vs B.2: Putin-Kushner -> real Ryazan refinery clip; St Petersburg protest, Abu Dhabi growth-panel, TVP Donetsk-label clips refused.
Lost: Saratov (B.2's clip was a Sept 2026 upload mislabelled exact; the time rule now refuses it). Still wrong: 18 (place-only Abu Dhabi
clip with no event words passes on a LOCATION-type line: the event rule only bites EVENT/MOVEMENT lines); 24 (talking head without text
needs face detection, not available). Below the 80 % target. Stage C not started.

## Production slice 6:43-9:44 (2026-11-12, uncommitted) — `slice3_production/` (clone; render 050 untouched)
Rendered `final/slice_6m43_9m44.mp4` (180.8 s, 1080p); first attempt kept in `final_v1/`. Review: `review2/compare_1.jpg`, `compare_2.jpg`
(render 050 | new, every 2 s), `review2/checks.json`.
Code (War only): keyword cards only for real lists; `semantics.find_numbers` drops model numbers (S-400), durations (two weeks, nine days),
'one'; `direction._campaign_timeline` + `dated_strike` (a summary line after 3+ dated strike lines in one section); map_build strike
markers for dated list lines; `_strike_maps` place only from the line before (same section); `_grounded_fill` + `gap_flags`;
`_text_layers_clear`; dossier enters with its title; lay_timeline up to 8 items, captions shrink to fit. Tests: test_war_slice_production.py
(10); test_war_planner density bound and test_war_render048 'the port' updated to the approved rules (reasons in the tests).
Production choices on the clone (not engine changes): 92/93/96/97/98 picks dropped as unrelated (Starlink road, grass field, presenter,
Siemens office, Google Maps screenshot); 78/79 restored from the B.3 full-film run (slice-only context loses the story period).
Remaining defects seen: Ryazan line shows labels on a dark field (Kanal13 Ryazan clip not on screen); '2026' date card on the ISW line;
kinetic fragments ('ON THE SECOND', 'THE', 'THE COUNTRY'); dossier title cut 'FOR RUSSIA, DEFEN'; Kirishi lines 7:50-7:53 near-empty dark
frames; same words twice (FALLING DEBRIS dossier then kinetic); 6 dossier cards in 3 min; Ust-Luga pin tiny on a Europe-wide map;
footage only ~4 clips (Samara inset, Afipsky aerial, Moscow refinery fire x2 lines). Checker 'framing' 54 s = maps misread as pillarbox.

## Pictures pass (2026-11-12, uncommitted) — `slice4_pictures/` (clone)
Owner: final videos need video + images. Code (War only): `library.fallback` (a row the live search left empty takes a library clip of its
kind, illustrative, each clip once per film; setting `war_library_fallback`); `direction.facility_facts` + CSV graphic `facility` (Iskander-
style photo + facts card from the narration's own words; picture from the CSV `images` column, credit 'AI illustration · Google Flow',
ILLUSTRATIVE chip); CSV `subject` column read; `flow_pictures.make` (attaches to the app's running Flow engine, app's image settings/accounts,
labelled, no real-person likeness); any ai_generated record is labelled AI. Tests: test_war_pictures.py (6); test_war_library / test_war_wiring
updated (no keyword graphic; facility row). Run: unlimited search budget; 8 Flow pictures made; Wikimedia unreachable (DNS REFUSED on this
network). Slice now: euronews Ufa, Reuters Samara, Moscow refinery fire, chemical-plant aerial, AI refinery/industry clips, Flow debris house,
3 facility cards (Kirishi, Morozov, Ust-Luga). Production choices on the clone: dropped 073 (Bakhmut drone view), 091, 096 (presenter, picked
again despite the project blocklist: open defect). Render 050 mp4 in baseline_050/final and final/ was deleted 02:08 by someone else; the
3-min reference is kept in slice3_production/review2/r050_same_3min.mp4.

## Flash + picture-floor fixes (2026-11-12, uncommitted, not re-rendered at the owner's request)
Owner: "there are many flashes", "16 sec flash and then a long continuous map", full-screen pictures >= 30 %. Measured on the 30 % render:
two flash kinds at card hand-offs - a 0.1-0.3 s glimpse of the clip underneath (7.1, 24.4, 152.3 s) and a blank-plate blink between two
cards (88.6, 97.5, 163.1, 169.9, 176.4 s); a 7 s text card + empty map at 15-24 s; one map frame held ~10 s (77-89 s).
Root causes: library AI montages cut every 0.3-1.6 s, so harden_measured's _absorb_short_pieces covered each piece with a NEW card fading in
over the clip; cards back to back each fade out then in; the map camera pushed 4 % per step however long the step; the fallback counted
records of scenes outside the script as uses; harden undid the picture floor (30 % planned -> 17 % rendered).
Fixes (War only): direction._handoffs (a full-frame layer followed within 0.35 s stays until the next has faded in, last step of
harden_measured); _absorb_short_pieces gives a short clip piece back the seconds it lacks from the map/card before it (same clip only) and
continues a cover only for slivers < 1.2 s; _picture_floor also at render time, undoing any change that would reveal a short piece;
maps_tactical._camera push scales with the hold (~1.5 %/s, 4-14 %); library.steady + fallback only clips whose uncut runs are all >= 3 s;
fallback counts only scenes of the current script. Plan check on slice4 (hardened): short pieces 0, slivers 0, card gaps 0, bare 0;
picture share 25 % (27 % planned; target 30 % not reached - 2 floor changes undone, remaining lines have no steady clip). Tests: 397 pass in
the affected War files; test_war_pictures.py 8.
