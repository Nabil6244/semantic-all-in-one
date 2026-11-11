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
