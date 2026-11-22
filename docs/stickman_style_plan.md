# Stickman style — plan (2026-11-19)

Faceless stickman explainers / stories, made by our app with no clicks after Generate.
Pattern source: kaomei/stickman-video-director (MIT). We study its looks and rules;
we write our own code and do not copy its art, characters or sample films.

## What the video looks like

- Code-drawn stickmen (round head, line body) acting out each sentence, with big
  code-drawn props (phone, money, clock, brain, house, car…), arrows, labels and
  bold one-line captions.
- One main picture state never holds longer than **3 s**. A zoom, caption change or
  wiggle does not count as a new state. (Fits our "no still screens" rule.)
- First 3 s always build up: hook line + the biggest action of the video.
- Native 16:9 and 9:16 (Shorts). Each one gets its own layout, not a crop.

## Looks (first 5, our own designs)

| Look | Feel |
|---|---|
| Ink Paper | warm paper, black wobbly ink line, red accent, handwritten titles |
| Chalk Dark | white line on black, glow, good for science / facts |
| Colour Pop | flat coloured rooms and streets, coloured shirts on stickmen |
| Retro TV | CRT frame, scanlines, channel-switch cuts, rounded white figures |
| Night Thriller | dark blue/black, red warning text, harder cuts, survival / mystery |

Later: **Host Explainer** (the user's picture as a presenter bottom-right, reusing
puppet2d) and a **Meme** look (painted backgrounds from Flow, stickmen on top).

## Engine — new `stickman/` package

Reuses what we already have instead of starting from nothing:

- **Transforms, camera and tweening** from `cartoon2d/render.py` (T/R/S matrices, smooth, gait, hops).
- **Skeleton rig:** head, neck, torso, two-part arms and legs. Every look is a pen
  (line width, wobble noise, colour, end caps), so the same pose works in every look.
- **Pose library** (~40 to start): stand, walk, run, point, shrug, think, facepalm,
  cheer, fall, jump, sit, sleep, carry, push, pull, scared, angry, cry, wave, type,
  phone, count money… Poses tween with feet pinned to the ground and hands pinned
  to the prop they hold.
- **Prop library** (~60 code-drawn icons), plus existing gfx-core cards for numbers,
  charts, timelines and maps.
- **Places:** simple code-drawn rooms and streets per look; optional Flow-painted
  backgrounds (Toon Tales pattern) for the Colour Pop and Meme looks.
- **Render:** supersampled frames, all cores in parallel (Rep Theory pattern),
  ffmpeg encode BT.709, 1080p default, 720p fast preview.

## Director (script → shots)

- Splits narration into beats with the Whisper times we already make.
- Each beat gets an **action + props + place + caption + camera + sound** from local
  keyword rules (no Gemini on a CSV run).
- A **variety guard**: no pose or prop repeated within 3 beats, at least one camera
  move every ~6 s, a new place at least every ~30 s.
- A **checker** (like `cartoon2d/storycheck.py`) before render: 3 s rule, hook,
  empty beats, captions too long, figures off-screen. It repairs what it can and
  only then renders.

## Stickman CSV

Columns: `line, action, props, place, text, camera, sfx, look`. Empty cells are filled
by the director. A "CSV prompt" button (same pattern as other styles) gives the
prompt to write it in a chat.

## Sound

- Voice from the Voiceover tab (Edge / Chatterbox clone), not Gemini.
- Pops, swishes and boings tied to actions (a pose landing, a prop appearing), plus
  a quiet bed per look, using our `sfx/` and `kids_audio` mixer.
- Optional: import the repo's credited sound pack. **Only items whose licence is CC0
  or CC-BY**, with a credits file kept next to them. Checked one by one first.

## App

- New style page "Stickman" in the grouped style picker, with a look picker.
- Same flow as the others: pick files/options (nothing starts) → Generate scenes →
  Render → mp4 shown.
- `make_video.py` autorun support, so stickman videos can go in the overnight queue.
- Shorts 9:16 button.

## Phases

1. **Rig + 10 poses + 1 look (Ink Paper)** → a 20 s test clip from a short script.
   Done when: figures move smoothly, feet stay on the ground, nothing holds > 3 s.
2. **Director + checker + captions + sound** → a 60 s video from a plain script.
3. **Remaining 4 looks + 40 poses + 60 props + places.**
4. **Stickman CSV, app page, autorun, Shorts.**
5. **Host Explainer and Meme looks** (after the first four phases are approved).

Tests: new `test_stickman_*.py` only; full suite only when asked.

## What I need from you

- 8+ real stickman channel videos you like (YouTube links or mp4s in Downloads).
  The repo's sample clips are study material too, but your own picks decide the look.
- Which look and which niche (explainer, story, money, history, horror…) to build first.
