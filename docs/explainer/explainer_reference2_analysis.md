# Explainer: second reference ("Why Did Hitler Leave Switzerland and Sweden Alone?") analysis and upgrade plan (2026-10-27)

Analysis and planning only. No production code, `app.py`, spec, `settings.json`, `hybrid/`, `pakmap/`, manifest or git state was changed. `m4_app_patch.diff` is still not applied. Only this file and `reference2_evidence/` (4 contact sheets, 2 burst sheets, the cut list; all small JPG/TXT) were added.

## 0. How the reference was examined (and what was not)

- File: 1280x720, 23.976 fps, 728.1 s (12:08), with audio.
- **Observed**: 109 scene cuts from ffmpeg scene detection (threshold 0.25; cuts per 120 s: 19, 16, 17, 17, 18, 22; median shot 6.3 s, mean 6.6 s, longest 24.7 s). This **undercounts** (it misses builds inside a shot and light-to-light cuts). I then looked at one frame every 6 s for 0:00-1:58, 2:00-3:58, 6:00-7:58 and 10:00-11:58 (four sheets, 80 frames) and three 4 fps bursts (~0:29-0:36 stamp, ~0:42-0:49 arrows, ~2:08-2:15 map zoom/outline). Sheets for 4:00-5:58, 8:00-9:58 and 12:00-12:08 exist in my scratch but I did **not** look at them; timestamps are +/-3 s (sheet position x 6 s), bursts +/-0.25 s.
- **Not verified**: sound effects, music, voice-sync of any cue (I cannot listen, and no transcript was available, so every "synchronised with narration" claim is an interpretation from on-screen captions and cue placement). Easing curves are read from 4 fps bursts, so "ease-out" is an inference. Whether boards/cartoon shots carry a continuous slow zoom is not established (map shots clearly change crop; cartoon shots in my bursts looked static apart from bubbles and stamps).
- Observation vs interpretation is marked **[O]** / **[I]**.

Important framing: this reference is a different family from the earlier R2 board reference (grey board + one narrator, see `explainer_phase0_report.md`). It is a **story-world cartoon**: no persistent narrator, in-story actors with speech bubbles, hand-composed scenes per beat, stylised watercolour maps, document/prop inserts, and heavy use of stamps. Our current Explainer is R2-shaped (board + narrator) plus a generic cartoon set pack. So "closer to this reference" means adding a motion/props vocabulary, not retuning the board.

## 1. Reference breakdown (timestamps are approximate, see section 0)

| # | Time | What visibly happens [O] | Technique [I] | Why it works | Translation to our engine | Difficulty / cost |
|---|---|---|---|---|---|---|
| 1 | 0:00-0:06 | Title card "THE SWISS BORDER / JUNE 1940" over a red dusk mountain silhouette, three planes drift in the sky | Cold open with place+date plate, parallax-like sky layer | Sets time/place before any narration of facts | `title` + date chip + backdrop (backdrop set exists) | low / low |
| 2 | 0:06 | Three goggled pilots stand in front of a green hill, name plate "SWISS FIGHTER PILOTS" under them, a plane on the runway | Group figure + name-plate caption | Labels the cast in one glance | figure/crowd styles exist; add name plate | low / low |
| 3 | ~0:12 | Cream spec card: "MESSERSCHMITT Bf 109", plane with Swiss flag, small grey German-cross tile -> red arrow -> Swiss-flag tile, plate "BOUGHT FROM GERMANY" | Mini infographic: object + cause arrow + label | Explains an odd fact (Swiss planes were German) in one static-but-built diagram | flow layout + arrow exist; add flag tiles + object illustration | medium (new art once) / low |
| 4 | ~0:24-0:30 | Dark stage, spotlights, a figure with a speech bubble "FURIOUS!"; next, a cone of light sweeps over sabotage figures | Spotlight + speech bubble | Emotion in one word; light directs the eye | `figure` + bubble element; spotlight cone sprite | low-medium / low |
| 5 | ~0:29-0:36 (burst) | Night airfield: tag "SABOTEURS" above 3 figures walking in; at ~0:31 two soldiers and a light cone appear (slide in), **then a rubber-stamp "CAUGHT" lands tilted and stays ~4+ s**; label corner "SWISS AIRFIELD, NIGHT" | Slide-in actors, stamp slam-and-hold, corner location plate | The stamp is the verdict; it lands on the key word | **new stamp primitive** (largest single gap) | low / low |
| 6 | ~0:36-0:42 | Europe map, "FRANCE FALLS" plate, date chip "JUNE 1940" top right, two red arrows grow from Germany into France, small grey unit icon with a cross appears | Map as a stage: plate -> arrows grow -> unit icon, one new element about every 1-2 s | Motion = what the sentence says | map beats exist; layers lack grown arrows/unit icons | medium / low |
| 7 | ~0:42-0:49 (burst) | Zoomed map: Switzerland tinted pink with red outline, arrow from "GERMANY" grows down, arrow from "ITALY" grows up, **"SURROUNDED" stamp** already on, then a third arrow + tiny label "GERMAN-CONTROLLED FRANCE" | Stepped diagram build, one element per spoken fact, stamp as the thesis | Cause-and-effect is shown by order of appearance | arrow cue + stamp + labels, driven by words | medium / low |
| 8 | ~0:48-1:00 | Scandinavia map: Sweden yellow with red outline, grey neighbours labelled "NORWAY - GONE", "DENMARK - GONE", "FINLAND - AT WAR", plate "GERMANY EVERYWHERE" | Colour-role fills + status labels | Whole situation readable without audio | fills + zone labels exist (Phase 4); add status labels | low / low |
| 9 | ~1:00-1:06 | A small figure stands on a glowing white disc **on the map** (Hitler "standing on" Switzerland, again on Sweden later); plate "ALREADY SWALLOWED" | Character as map pin | Fuses person and place; recurring motif | new `figure_on_map` overlay | medium / low |
| 10 | ~1:06-1:24 | Black screen, then spotlit folder "INVASION OF SWITZERLAND" stamped "GEHEIM"; folder multiplies; stamp "PLANNED"; kinetic text "FAR STRANGER THAN ANY ARMY." with STRANGER in red | Dark "dossier" stage, prop + stamps, big two-colour display type | Hard contrast change = new chapter; keyword colour = emphasis | dark backdrop + prop + title with keyword role colour | low-medium / low |
| 11 | ~1:24-1:56 | Meadow "RUTLI" and 1291 chip, bearded trio "WHERE SWITZERLAND WAS BORN"; General Guisan on podium over rows of soldiers; red bar timeline 10 MAY -> 22 JUNE "COLLAPSED" (the great French army) | Place+date chips, cast + crowd, **timeline bar that fills** | Duration shown as a bar, not a number | crowd exists; add timeline-bar visual | medium / low |
| 12 | ~2:00-2:24 | Two men in a Bern office with speech bubble "We must 'adapt' to the new Europe."; map zooms in to Switzerland, a red outline **draws on** around it, "PULL BACK INTO THE ALPS" plate, three arrows push inward | Dialogue bubbles; map push-in; outline draw-on; arrows as strategy | Abstract politics become a drawn plan | bubble element; camera steps exist; draw-on is new | medium / medium |
| 13 | ~2:24-2:50 | "THE REDUIT": a mountain fortress block with cannons popping on, soldiers in windows, a barrier arm, a train passing | Cutaway illustration assembled piece by piece | Build-up = understanding of a layered defence | prop kit extension (once) | medium-high (art) / low |
| 14 | ~2:50-3:10 | Soldier grid with big yellow figure "364,690 soldiers in the field", then "430,000" and "A RIFLE IN ALMOST EVERY HOME" with a house and a person | **Count-up / grid of icons that fills**, big outlined number | Scale made countable; the changing number is the payoff | `chip` quantity exists; add count-up + icon grid | low-medium / low |
| 15 | ~3:10-3:40 | Document "TANNENBAUM", highlighted line "INVASION OF SWITZERLAND"; row of helmets appearing; vault door with Swiss cross opens to gold bars, "ITS MONEY." | Document with highlighter, sprites that appear in a row, door open reveal | Concrete props for abstract claims (plan, losses, money) | scroll element exists; add highlighter + prop reveals | medium / low |
| 16 | ~3:40-4:00 | "WORTHLESS" stamp on an "RM" plate between a Portuguese and a Swedish man; Europe map with Portugal speech bubble "Not in Rei..."; two circles Germany -> Swiss National Bank with a dotted line carrying gold bars | Stamp, bubble on map, **flow along a path with moving tokens** | Flow of money is visible | arrow along a path + moving tokens | medium / medium |
| 17 | ~6:00-6:30 | "NO..." with five circular icons (ORE, STEEL, TANKS, SHIPS, GUNS) each crossed out in turn; Sweden map with railway route lines KIRUNA, NARVIK, LULEA and a red arrow route | Icon row + cross-out, route lines on map | Rhythm: one cross per beat of speech | icon row exists in `visual` tiles; add cross-out | low / low |
| 18 | ~6:30-7:30 | Two characters in an office with bubbles; three tilted panels "FLOODED MINES / WRECKED RAILWAYS / ONE MORE COUNTRY" (perspective cards); trains of dots along a map route; "2,000,000 TRIPS IN THREE YEARS" over a repeating tree-and-track strip; red "YES" stamp over a group | Dialogue scenes, 3D-tilted cards, looping strip, stamp | Variety of metaphors in the same palette | tilted card = 2D transform of existing card | low-medium / low |
| 19 | ~7:30-8:00 | "SWEDEN, 1940" factory dusk; LUFTWAFFE grid of planes vs three small soldiers "A SMALL ARMY"; hourglass "EVERY CONCESSION BOUGHT TIME"; "BALL BEARINGS" circle | Comparison by quantity (many vs few), metaphor prop | Imbalance read instantly | icon grid + two-sided layout | low-medium / low |
| 20 | ~10:00-10:30 | "SWEDEN PULLS BACK": calendar cards 1943 and 1944 receive stamps STOPPED and CUT; seesaw "LEANING" with Swiss/Swedish tokens between German and British flags | Cards + stamps; balance metaphor | A dynamic metaphor for a hedge | prop + tilt animation | medium / low |
| 21 | ~10:30-11:20 | "SO WHY LEAVE THEM ALONE?" map with Hitler pin; three ticked circles (mountains, army, threat); chalkboard "ONE COLD CALCULATION"; **split screen CONQUERED vs NEUTRAL** with icons sorted left/right under Swiss then Swedish flag | Question beat, checklist, sorting layout | Final reasoning shown as a sorting task | split layout, tokens slide to a side | medium / low |
| 22 | ~11:20-12:08 | "COWARDICE?" and "THE ONLY SANE CHOICE?" labels around a ring of German-cross tokens; newspaper stack "THE NAZI GOLD QUESTION"; closing poll "WHAT'S YOURS? A SMART? B LUCKY?" | Ring-of-enemies composition, newspaper cards, call to action | Callbacks to earlier motifs (tokens, Tannenbaum folder, stamps) | motif reuse by asset id | low / low |

**Pacing summary [O]**: shot median 6.3 s; but inside a shot something new appears about every 1-2 s (arrows, labels, stamps, tokens), so long shots do not feel static. Long beats are held by a **build sequence**, not by camera. Layouts rotate through ~6 families (map, character-in-set, spec/infographic card, dark dossier stage, icon grid, split-screen). Cuts are hard cuts; I saw no transitions between shots in the sheets (dissolves cannot be ruled out between 6 s samples).

**Recurring motifs [O]**: the stamp (CAUGHT, SURROUNDED, GEHEIM, PLANNED, WORTHLESS, YES, STOPPED, CUT, HUGE AMOUNTS), the small German-cross token, the Tannenbaum folder, the pink-with-red-outline target country, name/place/date plates, the spotlight on a dark stage.

**Typography [O]**: heavy outlined display face (yellow or white, thick dark stroke) for numbers/verdicts; small caps in rectangular plates for labels; a keyword in red inside a white title; very small low-contrast hand-lettered caption at the bottom (a weakness: hard to read on a phone; do not copy).

## 2. Gap matrix (current Explainer vs this reference)

Evidence used for "works": rendered frames in `m4_visual_fidelity_evidence/sheets/`, `phase7_evidence/` (Korea cartoon sample mp4), `phase4_evidence/` (7 s map imagery sample). Everything was rendered offline with synthetic voice and rule-made word times; nobody has rated it.

| Capability | Status | Evidence / note |
|---|---|---|
| Board clips, word-timed cards/titles/arrows/chips (`board/`) | **Implemented, works** | Rendered frames exist; arrows grow with ease-out cubic (`elements.py:182`) |
| Narrator rig, 6 poses, blink, mouth from word times | **Implemented, works, visually basic** | Fixed single character on grey board; not in the reference at all (the reference uses in-story actors) |
| Cartoon sets/figures/crowd/props (`cartoon/`, `compose_cartoon.py`) | **Implemented, visually basic** | Korea sample: generic sunny desert town for "family business"/"prison camp"; figures only pop and bob; sets not animated; one caption per beat |
| Map beats via pakMap (camera steps, fills, zone labels, stats) | **Implemented, works** | NASA imagery, framing proof; **no arrows, stamps, unit icons, pins, plates**; no layers on short beats; imagery style is realistic satellite, the reference is a stylised watercolour map |
| Captions word-by-word | Implemented | Fine; the reference captions are poor, so not a target |
| Stamps (slam, tilt, grunge, hold) | **Missing, worth adding** | No stamp code (`grep` finds none) |
| Place/date/name plates, corner chips | **Partial** | `chip` and `header` exist; no location/date plate family |
| Speech bubbles / dialogue | **Missing** | Phase 7 limit says "no dialogue scenes" |
| Count-up numbers, icon grids that fill, timeline bars | **Partial** | Static `chip`/`crowd`; no count-up, no bar |
| Draw-on outline, route lines, moving tokens along a path | **Missing** | Map `line` layers deliberately not used (Phase 4) |
| Spotlight / dark dossier stage, vignette, snow-grain overlay | **Missing** | Single flat background (grey) or flat sets; the reference's constant light grain/particles keep frames alive |
| Camera on boards and cartoon scenes (push-in, reframe) | **Missing** (maps only) | Ken Burns exists only for footage (`beats/footage.py:36`) |
| Transitions | **Basic** | Hard cuts or one global dissolve (`options.py`); equals the reference as observed |
| Split-screen / sort layout, seesaw, tilted cards, hourglass | **Missing** | Possible with 2D transforms of existing elements |
| Scene choice by meaning | **Weak** | `scene_for` matches keywords; wrong-scene risk acknowledged in Phase 7 |
| Motion presets with shared timing/easing | **Missing as a system** | Easing is ad hoc per element (pop, grow, bob) |
| Packaging of Explainer assets | Implemented, tested in a scratch copy | Phase 8 prep |
| App integration (switch + button) | **Patch exists, not applied**, scratch GUI smoke test only (no pixels) | Still awaiting your decision |
| 3D, rigged walking/talking characters, generated per-render art | **Not worth adding** | See section 7 |

## 3. Proposed motion and editing system

One new internal package, **`explainer/motion/`**, holding timing/easing presets and sprite helpers; every new element is a `visual` style (the schema already carries `visual` with free placement and collision checks) so the director, cue timing and renderer do not change shape. Nothing here needs new dependencies (PIL/numpy already used); frame functions are pure and deterministic (precomputed tables like the existing `BOB` table), so re-render stays byte-identical.

### Motion presets (the "grammar")
| Preset | Curve / timing | Use |
|---|---|---|
| `slam` | scale 1.45 -> 1.0 in 6 frames with 8% overshoot, rotation settles to its tilt (-6..+6 degrees), 2-frame 3 px shake, then hold | stamps, verdicts |
| `pop` | scale 0 -> 1.08 -> 1.0 over 8 frames | tokens, icons (replace ad hoc pop) |
| `slide_in` | 12 frames ease-out cubic from 140 px off-axis | actors, plates |
| `grow` | length 0 -> full, ease-out cubic (exists) | arrows, bars, outlines |
| `draw_on` | stroke revealed along a path in 14-24 frames | region outlines, routes |
| `count_up` | ease-out integer roll to target in 0.8-1.2 s, lands on the spoken word | numbers |
| `cross_out` | two strokes drawn 5 frames each | negations |
| `wipe_in` / `fade` | 6-10 frames | panels, folder multiply |
Rules: (1) one preset family per role (verdict = slam, thing = pop, relation = grow, place = slide); (2) an element's first visible frame is its cue-word frame +0 to +0.3 s (existing T08 rule); (3) **one new meaningful element per 1.5-2.0 s inside every shot**, never more than 3 concurrent animations; (4) a shot holds its final state at least 0.6 s before the next cut; (5) emphasis colour = one role colour per video (existing colour-role continuity rule); (6) a stamp always lands on the word that states the verdict, not before.

### Capabilities, with the requested specification
| Capability | Visual result | Trigger | Module | Cue timing | Assets / cache | Cost | Test |
|---|---|---|---|---|---|---|---|
| **Stamp** | Tilted grunge stamp slams on a verdict word, holds | verdict/negation words ("caught", "worthless", "surrounded", "no", "never"), a `twist`/`conclusion` label, lexicon list | `motion/presets.py`, `board/styles.py` (`stamp`), `director/compose_ref.py` | `onset = word time + 0.1 s`; first frame = slam frame 0 | grunge texture + 8 stamp colours built once by a `--build/--check` script like `cartoon/build_assets.py`, shipped in `assets/` with manifest SHA | very low (sprite scaled from a cached image) | frame at onset-1 empty, onset+8 within 3% of final bbox; same plan -> same bytes; text is a contiguous quote of the beat |
| **Plates and chips** (place, date, name) | corner plate "BERN" / "JUNE 1940"; name under a figure | entity detection already in lexicon (places, years, titles) | `board/styles.py` (`plate`), `compose_ref.py` | slide_in at first mention in the beat | code-drawn, no asset | very low | each plate text occurs in the beat's narration window |
| **Staged diagram** | Plate, then arrows, then labels, one per spoken fact | beats with 2+ entity relations (X to Y, "surrounded by") | `compose_ref.py` flow family, `board/elements.py` arrow | arrow starts on the source word, label on the target word | none | low | longest still gap <= 2 s in these beats (existing T04 measure) |
| **Count-up and grid** | Number rolls up; icon grid fills in rows | spoken quantity (existing `_stats_for`, `chip`) | `motion/presets.py` count_up, `styles.py` grid | roll ends on the spoken number's end | icons exist (code-drawn) | low | final value equals the quantity word; frame count budget |
| **Map overlay layer** | Arrows, stamp, plates, pin disc drawn over the pakMap clip | map beats with a spoken relation | new `explainer/beats/overlay.py` composites onto the compiled map clip **inside the Explainer's own renderer** | same word times as map layers | none | medium (one extra composite pass per map beat) | overlay pixel positions inside the framing proof's view; no `pakmap/` diff |
| **Draw-on outline** | Red outline traces a country | "target" place spoken | `overlay.py`, polygon from `pakmap.geo` read-only | starts on the place word | none | medium | outline stays inside the view (reuse `check_framing`) |
| **Spotlight stage / vignette / grain** | Dark dossier backdrop with a light cone; light grain or snow on every shot | dark-register beats ("secret", "plan", "document"); grain everywhere | `board/backdrops.py` | static layer; no timing | built once as sprites | low | grain is deterministic per frame index; mean luma stays in range |
| **Dialogue bubble** | Two figures with bubbles | quoted speech or "said", "asked" | `compose_cartoon.py`, `board/elements.py` | bubble on the first quoted word | bubble code-drawn | low | bubble text is a contiguous quote, fits without clipping |
| **Camera move on boards** | Slow push-in (3-6%) on every shot >4 s, a reframe on key words | all board/cartoon beats | `board/render.py` global transform | continuous | none | medium (affine per frame; numpy) | frame-to-frame difference > 0 during holds; text edges stay in safe area |
| **Sort / split / balance layouts** | CONQUERED vs NEUTRAL, seesaw, tilted cards | contrast labels (`twist`), "versus", two-sided quantities | `compose_ref.py` layouts | tokens slide on cue words | icons from existing set | low-medium | tokens end on the correct side |
| **Variety by narration** | Layout family chosen by sentence type and not repeated more than twice in a row | existing `select` + a repetition counter | `director/select.py`, `pacing.py` | n/a | n/a | none | no family appears 3x consecutively in a 10-minute plan |

## 4. Prioritisation (impact x frequency x feasibility, with risk and cost)

Scores 1-5 each (impact, frequency, feasibility), product out of 125.
| Rank | Upgrade | I | F | Fe | Score | Risk / cost note |
|---|---|---|---|---|---|---|
| 1 | Motion presets + **stamp** | 5 | 5 | 5 | 125 | tiny cost; one asset build |
| 2 | Plates / date chips / name plates | 4 | 5 | 5 | 100 | code-drawn |
| 3 | Staged diagram + count-up + icon grid + cross-out | 5 | 4 | 4 | 80 | needs word-bound cue rules |
| 4 | Map overlay (arrows, stamp, pin disc, plates, draw-on) | 5 | 3 | 3 | 45 | new compositing pass; must stay out of `pakmap/` |
| 5 | Camera push-in + grain/vignette on boards and cartoon | 4 | 5 | 3 | 60 | affine per frame; render time +; test determinism |
| 6 | Dialogue bubbles + dark dossier stage + spotlight | 4 | 3 | 4 | 48 | |
| 7 | Layout variety rule + split/sort/seesaw | 4 | 3 | 3 | 36 | |
| 8 | Prop cutaways (Reduit), documents with highlighter | 3 | 2 | 2 | 12 | art effort |

- **Five most perceptible**: stamp, plates/chips, staged diagram with count-up, map overlay, push-in with grain.
- **Quick wins on existing assets**: stamp, plates, cross-out, count-up, tilted cards, layout-repetition rule (all code-drawn or pure logic).
- **Distinctive, later**: map pin-disc character, draw-on outlines, split-screen sorting, motif recurrence (stamp/token/folder) as a declared signature.
- **Rejected / deferred**: simulated 3D, walking or lip-synced actors, per-beat bespoke illustrations (violates "no per-video asset burden"), sound-effect layer (reference SFX unverified), copying the small low-contrast captions, trying to imitate this video's hand-drawn art.

## 5. Mapping to modules

| Priority | Existing modules touched | New modules |
|---|---|---|
| Motion presets / stamp | `board/styles.py`, `board/cues.py`, `board/render.py`, `director/compose_ref.py`, `director/lexicon.py` | `explainer/motion/presets.py`, `explainer/motion/build_stamps.py`, `assets/stamps/` + manifest, `spike/test_phase9_motion.py` |
| Plates | `styles.py`, `compose_ref.py`, `board/layout.py` | none |
| Staged diagram / count-up / grid | `compose_ref.py`, `board/elements.py`, `director/plan.py` (`_stats_for`) | `motion/` only |
| Map overlay | `beats/mapbeat.py`, `beats/framing.py` (read), `director/plan.py` | `beats/overlay.py` |
| Camera + grain | `board/render.py`, `board/backdrops.py` | `motion/camera.py`, grain sprite in `assets/` |
| Bubbles / dossier stage | `compose_cartoon.py`, `backdrops.py` | `assets/` backdrops (build script) |
| Variety | `director/select.py`, `pacing.py` | none |

## 6. Performance and packaging

- Frame generation is per-frame PIL; stamps/plates are cached sprites scaled with precomputed tables, so the marginal cost is small. Camera push-in (full-frame affine) is the first real cost: budget it per 1280x720 frame and measure on a 60 s clip before adopting for all shots (I did **not** measure it; it could add on the order of tens of percent to board render time).
- Map overlay adds one composite pass per map beat; avoid re-rendering pakMap (reuse the compiled map clip and the render cache).
- Assets: stamps (~10 PNGs), grain/spotlight sprites, bubble tails; estimate under 1 MB on top of the current 1.3 MB cartoon kit and 61 data files (an estimate, not measured). Built by an explicit `build_*.py --check` step, hashed in a manifest, never created during render (matches H06). `packaging.py` must list the new asset folder (its test enumerates every folder).
- No new dependencies, services or network.

## 7. Acceptance tests and recommended first phase

### Recommended Phase 9 (first implementation): **Motion kit + stamps + plates**
Why first: highest score, used in nearly every video, one asset build, no change to `hybrid/`, `pakmap/`, `app.py`; and the reference's most memorable device (the verdict stamp) is entirely missing. It also creates the preset grammar every later phase reuses.
Scope: `explainer/motion/presets.py` (slam, pop, slide_in, count_up, cross_out), stamp assets + manifest + build/check script, `stamp` and `plate` visual styles, lexicon rules for verdict words, a "verdict stamp" rule in `compose_ref.py`, opt-in `DirectorOptions.motion` (default off so existing renders and the 253-check `verify_m4` stay identical).

Focused tests (new `spike/test_phase9_motion.py`):
1. Presets are pure and deterministic: same inputs, same frame hashes; slam has overshoot and settles in <= 10 frames.
2. Stamp onset: first visible frame within [0, +0.3 s] of the verdict word; absent one frame before.
3. Stamp text is a verdict word present in the beat; never two stamps within 3 s; max 2 per 30 s.
4. Plates: every plate text appears in the beat's narration window.
5. Count-up ends exactly on the spoken number, never shows a wrong final value.
6. Off by default: `motion=False` plan, CSV and clip hashes equal the recorded evidence (`verify_m1/m2/m3/m4` unchanged).
7. Asset build `--check` passes; packaging test lists the stamp folder; nothing written under `assets/` during a render (directory hash).
8. Collision/safe-area: no stamp or plate clipped or over the narrator's face (existing H07 gate).
9. Never-stop: removing the stamp asset falls back to a plain card with a logged note, not a failure.
Then one real 2-minute render for a human look (needs your go-ahead for any render or voice work).

Later phases: 10 staged diagrams + count-up/grid; 11 camera + grain + dossier stage; 12 map overlay; 13 variety rules, split/sort layouts, bubbles.

## 8. Risks, assumptions, unverified

- Only 80 of ~120 six-second samples and 3 bursts were inspected; the 4:00-5:58 and 8:00-9:58 spans were not seen, so techniques there (and any transitions) are unknown.
- No audio analysis: sound effects, music and exact voice sync are **unverified**. Sync claims are inferred from caption text and cue placement.
- Easing/overshoot values for the presets are my design, tuned to 4 fps observations, not measured from the reference.
- This reference's art is hand-made; our code-drawn art will look simpler. The plan raises motion and structure quality, not illustration quality.
- Reference imagery and text are third-party content; only techniques are used, no assets or wording copied; only a few frames are stored as evidence.
- Hybrid-map reading: the user's "Hybridmap" look is interpreted as the Hybrid panel's Explainer style (the app patch is the only path to it, and it is still unapplied and never run with pixels visible).
- Another session has uncommitted War/Weather work in the tree (`cinematic_explainer/`, `weather/`); it was left untouched. Explainer files were already untracked/uncommitted before this task.
- Quality of the existing boards remains unrated by humans; relative claims here come from my own frame comparison.
