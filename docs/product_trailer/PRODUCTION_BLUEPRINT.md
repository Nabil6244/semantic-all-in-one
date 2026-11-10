# Production blueprint: what the reference videos do, and what Semantic YT Studio must do to match (2026-11-06, Phase 2B)

Read-only synthesis. Nothing was built, rendered, downloaded or sent to an AI for this document.

**Sources read in full or in part:** REVIEW_REFERENCE.md (Duo lab review), REVIEW_REFERENCE_2.md (How's This Possible, iPhone 18 Pro review),
REVIEW_REFERENCE_3.md (three news compilations), REVIEW_REFERENCE_4.md / _5.md (S27 series, Design CHANGED), REFERENCE_DELIVERY.md,
CONCEPT_REFERENCE_BLUEPRINT.md, quality/QUALITY_GAP.html, WHAT_WE_HAVE.html, plus today's Phase 1-2A.1 findings (diagnostic.py,
DIAGNOSTIC_DUO.md, the Duo transcript, the model stills).
**Verified against the actual files in this phase:** the contact sheet `quality/ref_never_expected.jpg` (30 frames, one per 6 s): every frame is
real material of the exact phone (hands, dummies, tweet and certification screenshots, a teardown, UI recordings, official promo clips, a game),
no captions, bright natural light. The Duo review's own transcript (it says the crease is "almost invisible"; its durability test is a pencil scratch test).
**Not re-verified (taken from the earlier analyses):** the shot-length statistics, loudness figures and per-sentence tables. Their detectors differed
(thresholds 0.25 / 0.28), so numbers below are ranges.

---------------------------------------------------------------------------------------------------------------------------------

## A. Reference visual grammar

### A1. Universal techniques (seen in every family of reference; the product must have these)

1. **The picture is the proof of the sentence.** Each sentence is shown with the thing it says: the source that says it, the figure itself, the real
   object, or the real event. A plain product beauty shot appears only when the sentence is about the design. (All families; the clearest in the
   news compilations: "Nothing generic: no clip is a beauty shot unrelated to the sentence".)
2. **Text lives inside the evidence, not on top of it.** News compilations and the infographic channel have no subtitles; the only text is inside
   a screenshot or part of a drawing (a number on the phone body, a label under a figure). (QUALITY_GAP: 4 of 5 references have none; ours put captions on ~60% of shots.)
3. **One shot keeps adding information.** A held picture gains a label, badge, number or highlight on the exact word, so a 5-25 s hold never feels
   still; cuts happen when the topic changes. (REF_4: 55% flat graphics; the picture changes every 1-2 s inside a graphic shot.) Pace comes from new facts, not from camera angles.
4. **Every noun is on screen when it is said.** Figures, names, colours and chips appear on their word, in the spoken order. (REF_4 Rule 1, REF_5 table.)
5. **Continuity inside a topic, change at a topic boundary.** The same canvas and positions carry across consecutive sentences, new facts are added
   and old ones dim; a new topic changes the set (wipe, tint, or a hard cut to footage). (REF_4 Rule 3.)
6. **Unknowns are drawn and later resolved** ("??MP" becomes "10MP"; "?" on every colour card). (REF_4.)
7. **Opinion gets a human or hands; facts get graphics.** "I", "honestly", "I'd rather" never get a graphic: hands on the phone, the presenter, a
   headline of the opinion at most. (REF_4 Rule 2; REF_5 "Not Very Excited..." over the presenter.)
8. **Sources are always visible.** Post cards with the real avatar and tick, a database page with the row highlighted, an outlet wordmark, the
   creator's name on borrowed footage. The marked phrase follows the narrator's words (karaoke), then the camera pushes into the marked line. (REF_4 Rule 4, REF_5 gap 16.)
9. **One look per film.** Each reference stays in one visual world (paper all the way; real footage all the way; presenter set). Ours switched among
   three looks every few seconds. (QUALITY_GAP.)
10. **Rhythm is clustered, not uniform.** Cuts bunch on lists and montages and slow on explanations; the first ~15 s is a hook montage, one shot per
    topic in the order named. (REF_2 B: 33 cuts in one 2-minute block; REF_4/5 hook montage.)
11. **Bright, natural colour.** Daylight desks, white and pastel phones; very few dark frames outside concept trailers. (QUALITY_GAP.)
12. **Sound is finished.** Voice on top of a steady bed; loudness between -10.6 and -17.2 LUFS across references (news -11 to -13, infographic -17, 18 Pro review -16.7).

### A2. Techniques specific to one reference or family (do not generalise)

| Technique | Where | Rule |
|---|---|---|
| Burned-in 6-9 word subtitles | Duo review only | Optional per look; off for news and infographic |
| Presenter bubble, sponsor segment, own-app promo | Design CHANGED | Not adopted |
| Borrowed-footage watermark / "Video footage sourced online" tag | news channels, Duo review | A credit tag option, not a requirement |
| Dark void, rim light, fade to black, macro edge opening | concept trailers (Tech 2) | Only for Trailer / Reveal films, never for news or review |
| Flash-cut Nothing-style transitions | Nothing Phone concept | Opt-in "energetic" look |
| Lab rigs (force gauge, laser, clamps), CT scan | Duo review | Only when the user supplies that footage |
| Presenter in several sets | iPhone 18 Pro review, Duo review | Skipped: no presenter in our films |
| Diorama desk scenes | iPhone 18 Pro review | An optional 3D look |

### A3. Reference families and what each is the benchmark for

| Family | Examples | Benchmark for | Measured pace |
|---|---|---|---|
| News compilation (real footage) | NEVER Expected, S26 NEW CHANGES, iPhone 17 THE TRUTH | footage-first storytelling, evidence, matching clip to sentence | median 2.0-2.4 s, 40-50% under 2 s, ~95-100% real material, -10.6 to -13.3 LUFS |
| Flat infographic | How's This Possible | information density, figures on the drawing, one look | median 3.3-3.7 s, 7 shots over 8 s, ~10% real footage, -17.2 LUFS |
| Source-card news | S27 Surprising Decisions, There's More To This Upgrade | sentence karaoke on sources, canvas that keeps building, hook montage | median 3.6-5.1 s, a visual change every 1-2 s inside a shot |
| Presenter + sources | Design CHANGED Again | named sections, source cards, hard cuts | median 2.4 s, ~45% source cards |
| Lab / hands-on review | Duo review, iPhone 18 Pro review | real test footage, charts, CT/3D proof, chapter structure | Duo: ~320 cuts / 26 min (avg 4.8 s); 18 Pro: median 2.0 s, montage blocks |
| Concept trailer | iPhone 20 Pro, S26 Unboxing, Nothing Phone | premium product reveal for Trailer and Reveal only | 7-7.5 s premium, or 1-3 s energetic |

---------------------------------------------------------------------------------------------------------------------------------

## B. Visual selection rules (narration purpose -> treatment)

Rule 0: the planner must first classify the sentence by **primary purpose** (source attribution is a secondary property, as diagnostic.py now does),
then choose from the table. If the best treatment needs material that is not in the project, the plan **reports the missing asset and describes it**; it
does not substitute a generic 3D phone or generic stock footage.

| Narration purpose | Best treatment | Asset needed | If the asset is missing |
|---|---|---|---|
| Opening / hook | Hook montage: one quick shot per topic named, in order, over the first sentence; then the news in one line | footage or renders per topic | 3D hero + typed topic list |
| Product introduction | Real product footage (official event, hands) or an accurate 3D hero of the verified model | official clips, verified GLB | 3D hero of the verified model only |
| Specification (one figure) | Phone with the figure beside it, label under, landing on its word | none | (always possible) |
| Two figures of one kind / comparison | Two-sided figures either side of the phone, each landing on its word; "Not X" for a downgrade | none | (always possible) |
| List (colours, models, tiers) | Cards or phones appearing one per word in spoken order; "?" where unknown | none | (always possible) |
| Price | Price figures on the phone (launch vs now), a rising line or table for ladders; the official price slide when it exists | official price slide (optional) | price graphic |
| Benchmark / performance | Bars with names and an arrow figure, or a game or recording clip | benchmark chart or clip | bars |
| Battery / charging | Capsule or gauge with the number; battery settings screen or charger footage | optional footage | capsule or gauge |
| Chip / thermal / internal | X-ray or heat view with labels; official chip animation | optional | 3D x-ray (labelled illustrative) |
| Camera lens details | Lens callouts or a ring on the lens; sample photo inside a phone frame, labelled | real samples for quality claims | callouts only; never an invented sample |
| Design / dimensions | Profile, macro or lineup of the verified model; dummy or hands footage; two phones side by side | verified model or footage | 3D of the verified model |
| Source attribution (leaker, outlet, official) | Source card: real screenshot where available (name, avatar, date), marked phrase following the narration, push-in on the marked line | screenshot of the actual source | generic card **labelled as a stand-in**; card only when a named source and a meaningful claim exist |
| Certification / database | The listing screenshot with the row marked | screenshot | evidence card, labelled |
| Reported incident / user problem | The actual evidence: owner photo or post, news clip, the report's screenshot | the real thing | **mark MISSING and describe the exact visual; never generic phone or stock footage** |
| Test or lab result | The real test footage plus the measurement chart or number | footage + data | chart or number alone |
| Teardown / internal proof | Teardown photo or footage; the maker's own diagram | photo/footage | 3D x-ray, labelled illustrative |
| Timeline / dates | Big date type that changes to the next date, or a line with a dot per event on its word | none | (always possible) |
| Historical development | Generations row (same figure popping above each model in turn) or a timeline | model images | row of 3D phones |
| Geography / regions | Map with regions filling | none | (planned) |
| Opinion / interpretation | Presenter or hands footage; at most the opinion as a headline | hands footage | hold the previous canvas for <=2.5 s; else a headline card |
| Question | Dim the previous scene, tilt the thing asked about in over it | none | (always possible) |
| Short bridge ("Now the problem.", "Nobody knows.") | A section label or merge into the next scene; never its own picture | none | (always possible) |
| Advice / verdict | Verdict headline on a plain background; opinion footage if available | optional | headline card |
| Earlier-video / viewer prompt | Earlier-video card; speech pill with the question | none | (planned) |
| Sign-off | End card with the call to action | none | (missing: only the disclaimer card exists) |

Cross-cutting rules:
- **No more than 2 consecutive scenes with the same layer and arrangement; no layer repeated within ~20 s unless the content changed.**
- **No still stretch over ~4 s without motion or a new element** (feedback_no_still_screens).
- **A 3D phone is allowed only when the sentence is about the physical design, or as the verified backdrop for a figure.** Type cards must not
  inherit an unrelated 3D phone (the Phase 1C finding: today's callout / bigtype sit over a 3D phone).
- **Real footage must match the narrated subject** (the Duo, not "a smartphone"); anything illustrative (3D, stock, concept) is labelled as such.
- **One look per film**, chosen up front (paper, real footage, or premium 3D); no mid-film switching.

---------------------------------------------------------------------------------------------------------------------------------

## C. Production requirements: what exists, what needs work, what is missing

Status was read from code and docs (WHAT_WE_HAVE.html, the layer headers, today's inspections). "Seen working" means it appeared in an earlier test render;
it does not mean it was checked against a reference.

| Capability | Status | Where / notes |
|---|---|---|
| Voice alignment, word times | Exists | voiceover.align_lines, faster-whisper (local); small model reads "Duo" as "dual", so names need a glossary pass |
| Sentence purpose classifier | Needs improvement | diagnostic.py classify() (diagnostic only, not in the pipeline); director.scene_for() is keyword-based |
| Plan-level quality report (no render) | Exists as a tool | diagnostic.py; not run automatically |
| Word-timed builds | Exists | wordcue.py; first item within 0.8 s |
| Canvas that keeps building | Exists (flat phones only) | canvas.py |
| Two-sided figures, colour cards, lens callouts, ring | Exist | sides.py, swatches.py, lenses.py, pt_ring (3D ring tracking not yet seen in a render) |
| Figure layers (bench, compare3, glass, gauge, thermal, coststack, curve) | Exist | whatif-engine/layers/pt_*.mjs |
| Source card | Needs improvement | pt_tweet (generic card, one fixed mark); pt_doc; needs sentence-by-sentence karaoke, push-in, real-screenshot slot |
| Real-screenshot / real-image slot for evidence | Missing | no acquisition; the Visuals tab manual attach exists in the app for footage |
| News-footage route (YouTube runs by topic) | Exists, unreachable | news_footage.py; the UI cannot select the "news" look |
| Stock footage resolver | Exists | footage.py; needs keys; generic, only 3 query types in director.footage_hint |
| User footage library matching by sentence | Missing | Footage Library is an empty shell; no per-clip index or sentence match |
| Transcript-based clip timestamps | Missing in the pipeline | done by hand today (duo_review_transcript) |
| Hook montage | Missing | REF_4 gap 12 |
| Section tag (chapter name bottom-left) | Missing for Review | tm_cite is a telemetry-look citation that could be a base; review.py has chapter cards only |
| Timeline / date scene | Needs improvement | tm_timeline exists (years along a line, event dots); needs day-level dates and the date-morph card (REF_4 gap 7) |
| Opinion router (opinion -> hands / presenter footage) | Missing | REF_4 gap 11 |
| Question beat (dim previous, tilt in) | Missing | REF_4 gap 13 |
| Karaoke tweet across sentences | Missing | REF_4 gap 9, REF_5 gap 16 |
| Region map, generations row, viewer prompt pill, earlier-video card, sample-photo card, slide box | Missing | REF_4/5 gaps 6, 18-22 |
| Annotation of a real photo (ring + label) | Exists | tm_annotate (generic What If layer) |
| End card with call to action | Missing | only pt_card (disclaimer) and pt_reveal ("Introducing") |
| 3D x-ray, fold, lineup, hero moves, rooms | Exist | whatif-engine/lib/product*.mjs |
| Real phone models | Needs improvement | engine loads static scenes: no AnimationMixer (verified in phone_glb.mjs), the orientation guess assumes one slab (the Pikkme Duo file is a multi-phone scene); the animated Duo models cannot fold in the engine today |
| Verified product design (Duo) | Needs work | extraakash model matches the open (1.41:1) and closed (0.70:1) proportions; camera layout unresolved; DESIGN.md says the closed phone is "short and wide" (wrong) |
| Pacing profiles (montage vs calm) | Missing | one pace per film |
| Unmatched asset reporting in the plan | Partly | diagnostic.py reports missing assets; the planner does not surface them |
| Loudness | Exists | render.py mixes to -14 LUFS |
| Subtitles per look | Exists | pt_subtitle; off for news by default |
| Post-render checks (motion, still stretch, loudness) | Missing | proposed in REF_2, never built |

---------------------------------------------------------------------------------------------------------------------------------

## D. Quality validation: measurable criteria

Two levels. **Plan level** runs without a render (extend diagnostic.py). **Render level** runs on the finished file with ffmpeg only.

### D1. Plan level (per film, from the spec and the transcript)

| # | Metric | Reference value | Pass threshold |
|---|---|---|---|
| P1 | Sentences with a non-generic visual that explains them | ~100% in news compilations | >= 90% |
| P2 | Seconds on an empty 3D phone (no graphic, no evidence) | ~0% | <= 5% (old Duo film: 38%) |
| P3 | Attributed claims (named source) that show a source card or screenshot | ~100% | >= 80%, rest reported |
| P4 | Reported incidents / tests that have real evidence | 100% | 100%, or a MISSING entry that describes the asset (never a generic substitute) |
| P5 | Figures / names / colours appearing within 0.5 s of their word | tight on all references | >= 90% within +-0.5 s, none before the word |
| P6 | Consecutive scenes with the same layer and arrangement | none | no run over 2; none repeating within 20 s unless the content changed |
| P7 | Opinion sentences with a graphic other than a headline | ~0 | 0 |
| P8 | Distinct looks in one film | 1 | 1 |
| P9 | Quote cards as a share of duration | ~45% in the source-card video, ~0-10% elsewhere | within the chosen family's range; never a stand-in for a missing screenshot unless labelled |
| P10 | Shot-length profile | see A3 | median within the family's band (e.g. 2.0-2.6 s news, 3.3-3.8 infographic, 3.6-5 source-card) and a hook montage in the first 15 s |
| P11 | Longest stretch with no new element | holds up to 25-54 s only while adding info | no stretch over ~4 s without motion or an addition |
| P12 | Missing assets listed with required description and source | n/a | all listed |

### D2. Render level

| # | Metric | Reference | Pass |
|---|---|---|---|
| R1 | Scene cuts per minute and median shot (ffmpeg scene filter, one threshold across all videos) | family band | inside the band |
| R2 | Share of shots under 2 s | news 40-50%, infographic ~29% | within +-10 points of the family |
| R3 | Loudness | -10.6 to -17.2 LUFS by family | within +-1 LUFS of the chosen target (render.py targets -14) |
| R4 | Frame-difference motion per second | no dead stretch | no >4 s stretch below a low-motion floor |
| R5 | Burned-in text coverage | none in news and infographic | 0% captions unless the look asks |
| R6 | Dark-frame share | very low outside concept trailers | below the family's level |
| R7 | Side-by-side contact sheet against a reference, same sampling | n/a | human sign-off on the sheet before a full watch |

### D3. Calibration

Run P and R on the references themselves first (the transcripts and cut lists exist for most). The thresholds above are starting values taken from the
earlier analyses; replace them with the measured values once the same detector has been run on every reference. Until then they are estimates.

---------------------------------------------------------------------------------------------------------------------------------

## E. Prioritised implementation roadmap (not started; each step needs approval)

The earlier failures came from building details before the backbone. The order below puts acquisition and the sentence-level plan first, and
stops after each step with a check against the references.

**Step 1: Gate (plan-level, no render).**
Promote diagnostic.py's classifier to the planner's pre-flight: print the sentence table and the missing-asset list before anything renders, and
refuse to start a render when P2 or P4 fails without the user's decision. Add a name glossary for the transcript.
*Acceptance:* the Duo script yields P1 >= 90% with all gaps listed.

**Step 2: Real-material intake.**
Index the user's footage by transcript (local faster-whisper, as done for the Duo review), match clips to sentences by topic and timestamp, add slots
for source screenshots and evidence photos in the Visuals tab, and expose the news-footage route in the UI. Credit tags (tm_cite) optional.
*Acceptance:* the Duo review clips resolve to #6, #39 and the camera lines with their timestamps; unmatched sentences stay listed as missing.

**Step 3: Verified Duo phone.**
Correct DESIGN.md; resolve the camera layout from an official back-view picture; extract one phone from the Pikkme scene or use the extraakash model;
add pose playback (AnimationMixer) for the fold. Stills of each model check shape, hinge, camera and materials.
*Acceptance:* one still per pose beside Apple's frames, signed off.

**Step 4: Evidence layers.**
Source card v2 (sentence karaoke, push-in, real-screenshot support); timeline with day-level dates and the date morph; section tag; end card with a
call to action.
*Acceptance:* the Duo sources (#17-28) and dates (#19-21, #42) render as plan-level scenes first, then one short check render.

**Step 5: Rhythm and continuity.**
Hook montage; opinion router to hands footage; question beat; pacing profiles (montage / calm); type cards that do not depend on a 3D phone; a
single look per film.
*Acceptance:* P6, P7, P8, P10, P11 pass on the Duo plan.

**Step 6: Render-level gate and sound.**
Post-render ffmpeg checks R1-R6; sound bed and ducking per family.
*Acceptance:* the metrics run on the references and on one test film and the numbers are comparable.

**Not on the roadmap until the above pass:** map and generations-row layers, sample-photo and earlier-video cards, viewer-prompt pill, 3D ring tracking
verification, further concept-trailer looks.

## Open questions for the user
1. Which look should the Duo news film take: real footage, flat paper, or a premium mix? (Rule: one look per film.)
2. Where will the incident footage and source screenshots come from (owner posts, news clips, manual screenshots)?
3. Confirm the Duo's rear camera layout from an official picture before the model is accepted.
