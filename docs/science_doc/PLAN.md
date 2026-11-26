# Science Doc style: plan

Working name: **Science Doc**. It makes a long narrated science documentary in the look of the Mr. Science video
"The Longest Ice Age in History Changed Everything" (youtube.com/watch?v=ABWrP69A6mE, 33 min, 2026-11-23).
Written 2026-11-26. Nothing is built yet.

## 1. What the reference does (from 75 preview frames across the whole video)

| On screen | How often | What it is |
|---|---|---|
| Numbered chapter cards ("01 Budyko's Frozen Earth", "07 Out of the Ice") | every chapter | big number, serif title, misty backdrop with a soft sun |
| 3D Earth on black: sun on the left, light arrows, labels, the planet turning white | many | a lit globe with a halo, small orange labels |
| Cross-sections: sea surface, water, sea floor, ice sheets, rock layers | very many | a flat teal diagram with a soft depth haze, sometimes with a cut-out inset |
| Photo cards: a scientist's portrait with a name and a role, rock samples with a caption | many | real photos in a white or thin frame, small caption |
| Timeline bars ("500 million years ago", "the snowball") | some | one bar, a highlighted band, labels |
| Moon or planet discs with a big figure ("4 in every 10,000") | some | a disc on black, a number next to it |
| Stock footage: reef, ocean, Antarctica, smoke stacks | between graphics | real clips, graded to the teal look |
| Archive photos (1960s scientists), a real interview clip | a few | black-and-white photos; one talking scientist |

The whole film keeps one palette (teal, black, white, small orange accents), one serif for titles and one sans for labels.
That consistency is what makes it look expensive, not costly 3D.

## 2. What we already have (build on it, don't rebuild)

- **What If engine** (`whatif/`, `whatif-engine/`): 88 JSON templates, 24 primitives, 13 motions, 34 icons, a planner that
  places diagram plates into the timeline from the narration, per-template sound (`whatif/sound.py`), three.js hero shots.
  This is the closest base: it already makes "space and planet explainers with diagram plates".
- **gfx-core** (`gfx-core/`): 8 families of canvas templates drawn as a pure function of time (`drawGfx(inst, g, W, H, t)`).
  Already has `chapter_serif`, `photo_plate_1..3`, `polaroid_board`, `name_bar`, `timeline_strip`, `dossier_card`, `big_number`.
- **Hybrid Map / StarMap Cinema**: stock footage (HD cut), Flow pictures, Wikimedia photos, maps, "documentary photos with
  a source line", cuts in the narration's pauses.
- **Visuals tab + Export**: every fetched asset goes through them (owner rule).
- **Whisper alignment** (`whisper_backend.py`, GPU) and the streaming audio mixer.

## 3. Ideas taken from the repos we studied

| Idea | From | Where it goes |
|---|---|---|
| One cue sheet that both picture and sound read | mg-styles-15 `cues.json` | the plan file: every template's build/hit times written once; `sound.py` reads the same times |
| Signature features written so they can be checked (exact easing, frame counts, colours) | mg-styles-15 prompts | `docs/science_doc/LOOK.md`, used by the template builder and by the checks |
| Key frames before motion: stills first, fix, then animate | mg-styles-15 | Phase 2: one still per template from the mock canvas, no render |
| Strict jury rubric with exact fixes and timecodes | mg-styles-15 `rubric.md` | Phase 6: a 7-point review of the 30 s test, adapted for documentaries |
| Fixed "slop" rules checked without AI | Impeccable (62 rules) | Phase 6: plan-level lint before render |
| Frame-accurate cut measurement of a reference | HyperFrames `reverse-any-video` | Phase 0: measure the reference's real shot lengths (its tools are a paid Pro feature, so we use our own ffmpeg scene measure plus frame reads) |
| Upscale small archive photos | Real-ESRGAN (BSD-3) | Phase 4: photos under 1080 px are upscaled once and cached |
| Motion blur from sub-frames | mg-styles-15 `--mb 4 --shutter 0.5` | Phase 3: only on fast moves (globe spin, slides), so render time barely grows |

Not taken: HyperFrames style templates (paid, server-checked, can't be studied), Remotion (licence and a second engine),
Blender for the globe (three.js is enough for this look and much faster).

## 4. Phases

Each phase ends with its own tests (only the touched ones). No render without asking first.

### Phase 0: reference study (needs links from the owner)
- Owner rule: study 8+ reference videos and adopt patterns, not one fixed copy. Ask for 8+ Mr. Science (or similar) videos.
- For each: shot lengths (scene-cut measure), share of graphics vs footage vs photos, chapter count and spacing,
  template inventory, palette, fonts, sound (music bed, whooshes, hits).
- Output: `docs/science_doc/REFERENCES.md` and `reference_targets.json` (target ranges the checks use).
- Done when: targets exist for shot length, graphic share, chapter spacing and template variety.

### Phase 1: the look
- A `doc_teal` theme in `gfx-core/lib/theme.mjs` and the What If theme: palette (teal-black backdrop, white, one orange accent),
  title serif (Cormorant Garamond is already in `gfx-core/fonts`, OFL), label sans, grain, soft vignette, depth haze.
- A colour grade for stock footage so clips match the graphics (one ffmpeg chain, the same for every clip).
- `LOOK.md`: the signature features, written as checkable numbers.
- Done when: one still of each existing template that the style reuses looks like the reference next to it.

### Phase 2: new templates (stills first)
About 12 new JSON templates, in a `science` family, each with sound hooks:

| Template | What it shows |
|---|---|
| `chapter_numbered` | big chapter number + serif title over a misty backdrop with a soft sun |
| `globe_lit` | three.js Earth: sun on one side, light arrows, labels; slots: texture, rotation, label list |
| `globe_freeze` | the same globe with ice caps growing to the equator (a shader mask over time) |
| `cross_section` | sea surface, water column, sea floor, rock; slots for ice thickness, layers, labels, an inset |
| `strata_column` | stacked rock layers with dated labels and a highlighted band |
| `era_timeline` | one long bar, a highlighted span, "N million years ago" labels |
| `body_disc` | a moon/planet disc on black with a big number beside it |
| `scientist_card` | portrait photo + name + role + year, white frame |
| `sample_card` | a rock/fossil photo with caption and a scale bar |
| `site_map` | a flat world map with a pinned place and a lower third |
| `process_steps` | 3–5 step diagram (cause → effect) with arrows that draw on |
| `quote_paper` | a quote from a paper or scientist, with the source line |

- Each template: stills at 3 key times from the mock canvas (`gfx-core/lib/mockcanvas.mjs`), looked at before motion is added.
- Done when: the catalog sheet shows all 12, each passing the `LOOK.md` checks.

### Phase 3: the planner and the cue sheet
- A `science_doc` mode in the What If planner: narration → beats → template, footage, photo or clip for each beat.
  Rules from `reference_targets.json` (shot lengths, graphic share, no template twice in a row, a chapter card at each part).
- Names, years, places and numbers in the narration fill the slots (the What If `engage.py` path).
- One cue sheet per video: every build and hit time. Picture and `sound.py` both read it.
- Motion blur sub-frames only on moves faster than a set speed.
- A supplied CSV makes zero Gemini calls (owner rule); a CSV prompt in `docs/science_doc/CSV_prompt.txt`.
- Done when: a sample narration plans with no long static stretches and passes the plan checks.

### Phase 4: pictures and clips
- Stock footage, Wikimedia photos and Flow pictures through the existing Hybrid fetchers, shown in the Visuals tab.
- Interview and news clips allowed as clip rows (owner rule).
- Real-ESRGAN upscale step: photos under 1080 px on their short side are upscaled once (`realesrgan-ncnn-vulkan` on the Mac GPU),
  cached by file hash; if the binary is missing, the photo is used as it is (never a stop).
- Done when: a sample plan fills every picture slot, and small photos come out sharp on 1080p cards.

### Phase 5: sound
- Music bed per chapter (calm, curious), whoosh on cuts, soft hits on builds, all at the cue-sheet times.
- Loudness: −14 LUFS, true peak ≤ −1 dBTP (the existing `audio_level.py`).
- Done when: a sound check shows hits within 1 frame of their picture events.

### Phase 6: checks before and after render
- **Plan lint (no AI, before render)**: text overlap, text outside 5 % safe margins, the same template twice in a row,
  a static stretch over the target, missing font, an empty slot, a photo under the size floor.
- **Stills sheet**: one frame per template use, from the mock canvas, without rendering video.
- **Jury review of the 30 s test**: the rubric adapted for documentaries (style match, clarity of the science, motion, typography,
  finish, sound sync, technical), with fixes by timecode. Fixes go into the code, not into this one video (owner rule).
- Done when: the 30 s test passes the lint and scores at least 7 on each point.

### Phase 7: app wiring
- Style page in the Documentary group (`ui/style_registry.py`), CSV prompt, Generate → Render, Render 30 s, autorun (`make_video.py`).
- Check `test_fixtures/*_protected.json` before touching shared files; keep every existing style's features.
- Done when: a voiceover goes in and a full video comes out from the app with no clicks after Generate.

## 5. Open questions for the owner
1. Name: "Science Doc", or something else?
2. The 8+ reference videos for Phase 0: which channel(s) and which videos?
3. Voice: your own voiceover, or the Voiceover tab (Edge / Chatterbox clone)?
4. Long-form only, or Shorts too from the start?
