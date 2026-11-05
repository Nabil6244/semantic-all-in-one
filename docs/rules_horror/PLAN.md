# Rules Horror style — plan (2026-11-05)

New style for 6-7 min narrated "survival rules" horror videos: "If X happens... DON'T do Y", then seven rules, then a twist.
Patterns come from a study of 9 Final Sight videos (frames and measurements for all 9, transcripts for 6). We use the format and
our own art, card designs, characters, names and stories. No titles, scripts or artwork are taken from the channel.

Status: plan only. Nothing is built.

## What we are making

**First look: white on black with one red accent, about 3.5 s per shot.** Motion or a change every few seconds, no still screens.

| Measure | Reference (oldest 3 of the 9, the same look) | Our default |
|---|---|---|
| Length | 5:57 - 6:50 | 6-7 min |
| Median shot | 3.1 - 4.5 s | 3.5 s |
| Cuts | 79 - 104 | about 110 |
| Voice pace | 162 - 177 wpm | follows the voice-over |
| Loudness | about -14.4 LUFS, range 3.4 LU | -14 LUFS |

Later looks (dark colour, then full colour) use the same system with more Flow pictures. They are not in this plan's first build.

## Where each part of the picture comes from

| Part | Source | Notes |
|---|---|---|
| Stick figures | Code | Stand, walk, sit, sleep, look, flinch, run; blink and small idle moves |
| Rooms and sets | Code, line-drawn | House cross-section, bedroom, hallway, stairs, door, window, yard, classroom grid and similar |
| Sight lines, tags, countdown ring, seat or floor maps | Code | `YOU`, `PREY`, `NORMAL`, `00:01`, dotted lines, red danger marks |
| Rule cards | Code | Black typed card first; a design can be swapped per video later |
| In-world documents | Code | Incident report, security camera frame, timeline, radio transcript |
| One-phrase captions | Code + voice timing | Small white capitals, bottom centre |
| **Main subject** (deer, dog, mannequin) | **Flow** | 6-8 poses per subject, white shape on pure black |
| **Reveal close-ups** (grin, staring eyes) | **Flow** | A few per video |
| Static, colour-split glitch, grain, vignette | Code | Grain and vignette already exist in `whatif-engine/page.js` |

**No cut-out step.** Flow pictures are made on pure black and drawn over the code-drawn set with a lighten blend, so black
disappears. No new background-removal dependency is needed.

**Estimated Flow use:** 20-30 pictures per video (not tested yet; Stage 0 checks it). Flow is not a per-shot cost here.

## Story structure (enforced by the script prompt and checked at Generate)

1. **Hook:** "If you ever see X, do Y. Don't do A. Don't do B."
2. **Narrowing:** "I'm not talking about... I'm talking about..."
3. **Turn:** the detail that makes it wrong.
4. **Promise:** "follow these seven rules", with a plant such as "most people break the third one".
5. **Seven rules:** rule 1 starts within 30-80 s; each rule is a command, the reason, then a scare or someone who broke it.
6. **Twist:** 17-37% of the words from rule 7 onward, starting from something like "there's one thing I haven't told you yet".
7. **Closing line:** repeats the title ("So if...") and ends on one last scare.

A failed check warns and never blocks Render.

## Input and flow through the app

`CSV + voice-over (+ optional bed)`, press **Generate**, check the Visuals tab, press **Render**, finish on **Export**.

- A CSV run makes **zero Gemini calls**. The prompt the user pastes into a chat writes the script and the CSV.
- Picking files only remembers them. **Nothing starts until Generate.**
- Flow pictures go through the **Visuals tab** using `visual_bridge.py`, so Retry, Change source and Local clip all work.

```
#subject,deer,"tall deer, long thin legs, antlers"
#location,house,yard
order,section,line,set,shot,subject,pose,action,tag,value,prompt
1,hook,If you ever wake up at three in the morning,bedroom,wide,,,figure_sleep,,3:00 AM,
2,hook,and see a deer standing in your yard,window,push_in,deer,stand_side,,,,
9,turn,It's looking at something behind it,house_section,wide,deer,stare,sight_line,YOU,,
14,rule,Do not turn on the lights,card,,,,rule_card,,1,
21,scare,it's practising how to look like you,closeup,push_in,,,glitch,,,"a grinning white face filling the frame, pure black background"
```

`line` is a short phrase from the voice-over. Rows are placed on the voice by the existing `align_lines` in
`product_trailer/voiceover.py`. Cuts follow the row timing, and each caption shows one phrase.

## Code layout

| Path | What |
|---|---|
| `rules_horror/` (new) | `csv_io.py`, `planner.py`, `compile.py`, `check.py` (story and screen checks), `assets.py` (Flow requests, poses), `sound.py`, `runner.py`, `prompt.txt` |
| `whatif-engine/layers/rh_*.mjs` (new) | `rh_figure`, `rh_set`, `rh_subject`, `rh_rulecard`, `rh_caption`, `rh_doc`, `rh_glitch` |
| `whatif-engine/layers/index.mjs` | Add the new layers to the list, nothing else |
| `ui/rules_horror_section.py` (new) | The style's own page, shaped like `ui/roblox_cinema_section.py` |
| `ui/style_registry.py` | Append "Rules Horror" in its own block, the same way Voxel Map is added |
| `app.py` | Additions only: page hook and deactivate call |
| `test_rules_horror*.py` (new) | Synthetic tests; no test depends on a specific video |

Rendering reuses the What If renderer, because it already provides per-frame drawing, grain, vignette and templates.

**Constraints found while checking the code:**
- `app_csv_prompts.py` is listed in `test_fixtures/weather_protected.json` as a file that must not change, so the prompt stays in
  `rules_horror/` and the style's page shows it.
- `whatif-engine/lib/scene3d.mjs` and `whatif-engine/lib/car.mjs` have uncommitted work from other tasks. This build must not touch them.
- New layers are only used when a Rules Horror spec names them, so What If and Product Trailer output should not change. Stage 2 checks this.

## Sound

- Voice-over from the user's recording or the Voiceover tab's Edge voices.
- A low continuous bed under the whole video, because the references have almost no pauses (0-2 per video). Output is normalised with the helpers in `whatif/sound.py`.
- Short sounds on rule cards, reveals and glitches, using the existing riser, impact and whoosh folders.
- **Gap:** no file in the bundled SFX or music folders has static, glitch, drone, horror, heartbeat, creak or sting in its name.
  Source a small free CC0 set once, not per video. **Downloads need the user's approval first.**

## Stages

**Stage 0: prove the risky part (Flow test, no app code).**
Generate one subject in 8 poses on black using the existing character references, then composite them on one hand-made line set.
*Done when:* the subject looks like the same animal in all 8, the black disappears cleanly, and the user approves a still sheet.
*If it fails:* use a code-drawn subject library for common animals and figures, and Flow only for close-ups. Decide this before Stage 1.

**Stage 1: drawing kit.**
Stick figure with poses, line-drawn sets, tags, sight lines, captions, black rule card, glitch.
*Done when:* tests pass and the user approves one still sheet of everything. Measure render speed on a 60 s sample here.

**Stage 2: CSV to video, no Flow and no app page.**
CSV reader, voice alignment, planner, compile, sound. Missing subjects use a code-drawn dark figure with red eyes.
*Done when:* a 60 s test renders from the command line with voice, cuts and captions in sync, and an existing What If test still passes.

**Stage 3: app page and script prompt.**
Page, style picker entry, Generate → Visuals → Render → Export, Flow requests, and the prompt.
*Done when:* one complete CSV goes through the real app, with zero Gemini calls.

**Stage 4: first full video.**
A 6-7 min original story, rendered at full length after the user approves that render. Fixes go into the general rules, not that video.
Compare it to the 9-video measurements. *Done when:* the user approves the result.

**Stage 5: follow-ups (separate decisions).** Themed rule cards, more documents, dark colour look, full colour look.

## Rules this build follows

- A missing or failed picture never stops the render: the style falls back to a code-drawn figure and reports it in Visuals.
- Tests: only the touched tests during work, the full suite only when the user asks.
- Render previews and sheets only where a stage above lists them, or when the user asks.
- Every commit and push is asked for first.
- No subagents without asking.

## Not in the first build

Rigged talking characters, lip sync, full-colour sets, Shorts, Gemini script writing, like/subscribe animation (easy to add later).

## Questions for the user

1. **Name:** "Rules Horror" is a working title. Keep it or change it?
2. **CC0 sounds:** may we download a small free set during Stage 2? The source and file list will be shown first.
