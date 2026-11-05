# 3D Cartoon style — plan (2026-11-05)

Status: **plan only, nothing built.** One new style with two modes that share the same characters, worlds and render pipeline:

- **Story**: 3D cartoon stories with characters who talk to each other (any topic: history, morals, fables, explainers).
- **Kids Learn**: toddler learning videos in the spirit of the reference (talk, words, colours, counting, up/down, animals), but with 3D cartoon hosts instead of a filmed person.

## What the reference video actually does (checked at 1:00, 10:00, 25:00)

- A real presenter filmed live in a museum/room, or in front of a **green screen** composited onto a flat paper-craft cartoon set (balloon, rainbow, clouds, hills).
- Very slow, clear speech; the host looks straight into the camera; one idea per few seconds, repeated ("this is up, this is down").
- Big bottom captions, bright saturated colours, soft daylight, no fast cuts.

We adopt the patterns (direct address, repetition, pauses for the child to answer, bright soft worlds, big captions), not the look or the person.

## Built on what already exists (no changes to Roblox Cinema's behaviour)

New folder `cartoon3d-engine/`. It reuses, by import or copy, the proven parts of `roblox-cinema-engine/`:

| Reused | From |
|---|---|
| Headless GPU Chromium frame render, x264 encode, cue list | `render.mjs` |
| Light presets, sky, shadows, post grade, transitions | `web/look.js` |
| Voice-over timing, SFX, −14 LUFS mix, QC (frozen/black/jump checks) | `tools/` |
| CSV reading, seeded randomness, camera rig | `lib/csv.mjs`, `lib/rng.mjs`, `lib/camera.mjs` |
| Edge voices (free) | `edge_voiceover.py` |

Roblox Cinema keeps working exactly as today.

## New pieces

1. **Cartoon characters** (`web/toon.js`):
   - Round, soft bodies, big eyes with highlights, blinks, eyebrows for emotion, squash and stretch on every move.
   - **Mouth driven by the voice**: loudness per frame from the voice file opens and closes the mouth (no extra tool, no Gemini).
   - Gestures: wave, point, clap, jump, think, laugh, sad, surprised, walk, sit.
   - Built from a free CC0 pack sourced **once** (e.g. Quaternius or Kenney animated characters), recoloured and given outfits procedurally. No per-video model making. (Download needs your OK first.)
2. **Toy worlds** (`web/worlds.js`): about 8 reusable sets made once: bedroom, classroom, park, farm, sky with balloon, beach, town street, space. Soft toon shading, outline pass, warm light.
3. **Story mode** (`lib/story.mjs`):
   - CSV per line: `speaker, line, emotion, place, action, camera`.
   - One Edge voice per character; two-shot, close-up and over-shoulder camera picked automatically from who talks.
4. **Kids Learn mode** (`lib/learn.mjs`):
   - Beat types: `word` (object pops in with a bounce and the word in big letters), `repeat` (host says it, pauses ~2 s for the child), `count` (objects drop in one by one, numbers appear), `colour`, `opposite` (up/down, big/small), `animal` (animal + sound), `song` (original simple tune + bouncing words).
   - Slow pacing defaults, host looks into the lens, big captions.
5. **App page**: new "3D Cartoon" entry in the style picker with a Story / Kids Learn switch, using Visuals + Export like every other style. Nothing starts until Generate.
6. **CSV prompt**: a ready prompt (like `roblox-cinema-engine/docs/story_prompt.md`) that turns a topic into the CSV for either mode.

## Optional later

- **AI look**: Flow makes Pixar-style pictures/clips per scene in agent mode, cut to the voice. It looks richer but characters drift between scenes, so the engine route stays the default.
- **You in the cartoon world**: record yourself on a green screen, key it, place it into a 3D set (what the reference does at 25:00).

## Steps (each tested before the next)

1. Character spike: one toon character, blink + voice-driven mouth + 3 gestures, 10 s clip.
2. Two worlds + toon shading/outline.
3. Story mode end to end (CSV → voices → video) on a 60 s sample.
4. Kids Learn mode end to end on a 60 s sample.
5. App page + CSV prompt.
6. More worlds/gestures/beat types.

## Open questions

- OK to download one free CC0 character pack (step 1)? I'll state the file, source and size first.
- Kids Learn language: English only, or also Urdu?
