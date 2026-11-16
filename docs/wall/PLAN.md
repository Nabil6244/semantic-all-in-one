# Wall Moments — plan

A new feature: for **about 20% of a video**, the film leaves full-screen footage and the camera pulls back onto one dark
"evidence wall". There the numbers, stamps, pen rings, notes and red string land on the spoken word. Then the camera dives
back into the next clip, which plays full screen again. The other **80% stays exactly as the app makes it today**
(footage, pictures and the existing graphic cards).

Idea taken from Moh4696/cinematic-skill (MIT). We adopt the patterns and write our own code; we never copy their files.
Approved by the owner on 2026-11-16 after watching the Lisbon TAP test.

## Reference material (already in the repo)

- `out/wall_demo/compare_mixed.mp4`: the approved look. Left is v7 today, right is the mixed version, with notes.
- `out/wall_demo/mixed.mp4`: the approved look on its own.
- `docs/wall/demo/wall_mix.py`: the demo renderer that made it (PIL). It has a monotone camera spline, prints, video
  prints, counters, stamps, notes, string, pen rings, spotlight, old-item dimming, motion blur, grain, and a camera clamp
  so a full-screen clip never shows its border.
- `docs/wall/demo/wall_sfx.py`: the synthesised item sounds (drop, pop, slide, marker, pencil, ticks, impact, stamp,
  boom, whoosh, room tone).
- `docs/wall/demo/wall_demo.py`: the earlier all-wall version (stills only). The owner rejected it because the videos
  were frozen. Never freeze footage.
- Test project: `~/Downloads/VideoGenerator/Video_2026-11-13_057_Lisbon_TAP_Lufthansa_Hub`. It has the clean voice
  `audio/voiceover.mp3`, word timings `state/narration_words.json`, scenes `state/aviation/scenes.json`, clips
  `state/aviation/assets/`, and the last render `final/Lisbon_TAP_Lufthansa_Hub_v7.mp4`.

## Rules the owner set

1. **About 20% of runtime** is wall: a budget of 18–22%, never above 25%. The rest is untouched.
2. **Footage always plays full screen** in its own scenes. On the wall, clips keep moving inside their prints (ping-pong
   loop). Never use a frozen frame.
3. Wall moments **replace** the flat graphic cards in the scenes they cover, so the video does not get more graphics on
   top of what it already has. Outside wall moments, today's cards stay.
4. Hits land on the spoken word, using the Whisper word times the app already has.
5. Keep every existing feature. A run with a CSV makes no Gemini calls. Nothing starts until Generate. No commit or push
   without asking. Run only the touched tests. Show every render to the owner.

## How a wall moment plays (from the approved test)

1. **Enter**: the full-screen clip of the scene before stays playing while the camera pulls back (about 1.2 s). The clip
   becomes a pinned print with a red name bar. No hard cut.
2. **On the wall** (8–20 s): a red string draws to the next item, which then:
   - counters count up and land on their number word
   - pen ring on "percent / of X"
   - underline and a handwritten note on the follow-up fact
   - stamp plus camera shake on the verdict word ("+40% WORSE", "NO MAJORITY")
   - older items dim, and the spotlight follows the camera
3. **Exit**: the camera dives into the next scene's clip until it fills the frame (zoom = 1280 / print width × 1.025,
   roll 0, no handheld drift). The clip plays full screen as normal.
4. On full-screen footage, small word hits are still allowed: a pen ring on the runway, a stamp on "majority", a title
   slam on "here is the strange part". At most one or two per scene.
5. Optional, once per video: the closing pull-back shows the whole wall with every clip still playing.

## Phases

### Phase 1 — `wall/` engine (style-neutral package)
- Port the demo into `wall/engine.py`: Spline, Item types (Print, VideoPrint, Text, Counter, Stamp, Note, String,
  PenRing, Underline), camera with shake, drift, full-screen clamp and motion blur, spotlight, dimming, grain.
- Expose it as a render layer: `wall.lay_wall(t, dur, params) -> RGBA 1280x720`, registered like `ocean.lay_ocean`, so
  the existing chunked `cinematic_explainer.render` pipeline and parallel chunks keep working.
- VideoPrint reads clip frames through a small decoded-frame cache (ffmpeg to JPEG frames once per clip in the work
  dir). Memory stays bounded on 16 GB machines.
- `params` is plain JSON (items, camera keys, clip paths), so plans stay inspectable and cacheable.
- Tests in `test_wall_engine.py`:
  - spline monotone (no overshoot)
  - full-screen clamp never shows the border
  - counters land on time
  - layer returns the right size
  - the same params give the same frame
- Tool `wall/probe.py <plan> --at 3,7.5,12`: stills and a contact sheet for checks without a render.

### Phase 2 — the planner (`wall/planner.py`)
- Input: the style's scenes (text, start, end, visual kind, clip path), Whisper words, and total length.
- Score each run of 1–4 adjacent scenes:
  - plus for numbers, money, percents and years in the text
  - plus for scenes that today become graphic cards
  - plus for "twist" lines ("here is the strange part", "but", "yet")
  - minus for scenes whose own clip is strong footage (those stay full screen)
- Pick segments greedily up to the 20% budget:
  - each 8–20 s long, at least 45 s apart
  - not in the first 5 s
  - never the very last scene
  - one closing pull-back allowed in the last minute
- For each segment, build its items from the narration with shared fact parsing: number plus unit becomes a Counter,
  "percent of X" a Counter plus PenRing, a verdict word a Stamp, a follow-up clause a Note. Then lay out a cluster to
  the right of the last one and add camera keys on word times.
- Neighbour scenes give the entry and exit clips, as VideoPrints at the full-screen zoom.
- Tests in `test_wall_planner.py`:
  - budget stays within 18–22% on 3 real scripts
  - segments never overlap clips that must stay full screen
  - deterministic output

### Phase 3 — Aviation first (the style of the test video)
- `aviation/runner.py` / `aviation/planner.py`: after the normal plan, run the wall planner. The scenes it picks swap
  their card layers for one `wall.lay_wall` layer, and the neighbouring clips become entry and exit prints. Everything
  else is unchanged.
- Sound: add the wall items' cues to the events `aviation.sound.mix` already takes. Put the synthesised sounds in
  `assets/bundled-sfx/wall/` (made once, no licences needed). The mixer's MIN_GAP rule still applies.
- UI: on the Aviation page, a "Wall moments" switch (default ON) and a 0–30% slider (default 20). Both are remembered,
  and nothing runs until Generate.
- Test on Lisbon TAP:
  1. probe stills of every wall moment
  2. a 60–90 s draft render, sent to the owner
  3. the full video only after the owner says yes

### Phase 4 — other styles, one at a time, each with the owner's OK
Each style needs only an adapter that gives the planner its scenes and swaps the layers. Suggested order: Explainer,
War, News Doc, Hybrid, StarMap Cinema, Ocean, Theory styles. Kids, Toon Tales, Roblox and Sky Sim are skipped unless asked.

## Done means
- Aviation renders with wall moments at about 20% of runtime, footage full screen elsewhere, cards replaced only inside
  wall moments.
- Engine and planner tests pass, and the touched Aviation tests pass.
- A Lisbon TAP draft is sent to the owner and approved.
- Nothing is committed without asking.

## Open questions for the owner (ask at the start)
- Should the switch default to ON for new Aviation videos, or OFF until tested on more videos?
- Should the wall look follow each style's colours (Aviation dark slate, War darker, News Doc paper), or always use the
  dark slate from the test?
