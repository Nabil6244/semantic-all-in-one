# Architecture

```
story CSV / narration ──► lib/csv.mjs ──► story {plan, chapters, beats}
voice-over ──► tools/narration_timing.py ──► words.json
                                    │
                         lib/director.mjs  direct(story, {words})
          narration.mjs (sentences, dates, numbers, events, actions, vehicles) · gazetteer.mjs · eras.mjs · recipes.mjs
                                    │
                              PLAN (json): scenes[ shots, transitionIn, cast, vehicles, fx, light, map ], hud{subtitles,dates,places,chapters,stats,labels},
                                    audio{ambience,cues,music}, warnings, per-decision reasons
                                    │
        ┌───────────────────────────┴───────────────────────────────┐
  render.mjs (Node)                                         tools/mix_audio.py
  serves page + three.js, crops Natural Earth per map scene   ambience beds + synthesized event sounds on the planned cues
  headless Chromium (--use-angle=metal), window.renderFrame(t)   + music (ducked with health_cinema speech_duck) + voice
  screenshot -> ffmpeg (BT.709, x264)                          -> two-pass loudnorm -14 LUFS, limiter -> muxed
```

## Determinism
Every frame is a pure function of the film time `t`: positions, poses, particles, camera and HUD are computed from seeds and `t` (`lib/rng.mjs`),
never from the previous frame. A frame can be drawn alone, in any order, or in a part of a parallel render.

## The scene as one object (`lib/assemble.mjs`)
`assembleScene(scene)` builds the world (`world.mjs`), stages the cast and vehicles (`stage.mjs`: formations, boat riders -> wade, paratroopers,
narration actions fired on the spoken word), plans effects and the sound cues they cause (`fx.mjs`), and answers `cameraAt(t)` with shot continuity,
terrain/roof/vehicle collision and smoothing. Node uses it for tests and the cue list; the page uses the same code to draw.

## Browser runtime (`web/main.js`)
Per scene: its own `THREE.Scene` (sky, sun with a follow shadow window, hemisphere, fog, clouds), world, one rig per actor and vehicle, an effects layer
(instanced block particles), at most two point lights for fires and flashes. Scenes build lazily at the first frame that needs them and are freed when
two scenes behind. Frames render into half-float MSAA targets; `look.js` composites (tone map, grade, vignette, dissolve / dip / cloud wipe) to the canvas;
`hud.js` is DOM text over it. Shared materials, geometries and textures are keyed caches (`gfx.js`).

## Director decisions
Event: CSV > classified from the words (27 rule sets). Environment: CSV > words that suit the event > the place's biome > the recipe default. Time/weather carry
across beats until the narration changes them. Cuts fall in the pause before a scene's first spoken word. Shots are 3.6-9.5 s, never the same behaviour twice
in a row, aerial-to-aerial changes are continuous moves. Transitions: chapter change = dip, time passing = dissolve, map in/out = cloud wipe, else cut.
Every decision keeps a `why` string in the plan.

## Audio
Ambience bed per scene (library groups + a synthesized layer), cues from visible events (explosions, ramps, flak, guns) at their time, scene recipe cues
(tanks, marching, planes), music split across its tracks with 5 s crossfades and ducked under the voice, loudnorm to -14 LUFS with a limiter before it.
