# StarMap "Cosmic Telemetry" style — plan (2026-10-16)

A second StarMap look, modelled on three reference videos ("How Long Could You Survive on Venus?", "What If You Traveled at
the Speed of Light?", "What If You Tried to Travel One Light-Year?"). Classic StarMap stays the default and is unchanged.

## What the references do (measured from the frames)

- One visual idea every ~4-5 s; hard cuts; fade to black only for a death / silence.
- Three kinds of picture: a 3D/CG plate of a planet or craft with slow drift; a dark diagram plate (#05070B..#0B0E14 with a
  faint lighter centre) holding a log-scale light-time axis, bar chart, curve, comparison cards, composition bar or
  timeline; a real photo, always cited.
- Type: huge heavy sans numbers with a soft glow ("464 °C", "1.4 SECONDS"); a small tracked bold line under them in amber or
  cyan; lower-left lockups ("47 KM: PARACHUTE RELEASED" + mono sub); a title card in white + accent second line.
- Persistent HUD per act: survival clock card (top-left, chips AIR / TEMPERATURE / PRESSURE / ACID turning red), dual
  EARTH TIME / TRAVELLER cards, a light-from-Earth clock with a dial, a right-hand altitude gauge, a top-right date.
- A monospaced citation bottom-left on every shot: "○ ILLUSTRATION", "○ DIAGRAM · …", "○ REAL IMAGE · … · NASA/JPL".
- Desaturated, lifted blacks, amber (#FFB703) / cyan (#00E5FF) / red (#FF2A4B) as the only strong colours.

## Where it plugs in (real code)

| Need | Reused | Added |
|---|---|---|
| Style selection | StarMap tab, workspace starmap settings, `generate_starmap_video` | `style` setting ("classic" / "telemetry"), CSV plan row `extra {"style": "telemetry"}`, CLI `--style` |
| Pacing | `compile.build_camera` shot cutting on word starts | telemetry cut lengths (min 3 s, a cut every ~4.5 s, cycling close-up / new angle) |
| Narration → visual | `plan.words` (Whisper times), NASA picture rows | `starmap/telemetry.py`: metric / ratio / light-time / survival / descent / death extraction from the words, at word time − 0.1 s |
| Graphics | layer registry (`lib/layers.mjs`), `ui.mjs` helpers | `layers/tm_*.mjs`: plate, metric, caption, title, cite, clock, survival, gauge, logaxis, bars, curve, compare, composition, timeline, fade |
| Classic layers | compile_plan's title / stat / caption / big_number / mission_clock | converted to tm equivalents in telemetry style only |
| Look | `spec.look` glow / vignette / grain | `grade` (saturation 0.8, black lift #080B10), footage credit moved into the citation |
| Transitions | footage `transition_in/out` | hard cuts in telemetry; `tm_fade` for death / silence lines |
| Stills | footage Ken Burns | 1.00 → 1.04 drift |
| Audit | `lib/audit.mjs` | full-screen plates count like footage (no false "empty") and as pattern interrupts |
| Sound | `starmap/sound.py` cue table, `music.py` | UI clicks on metric / HUD pops, thud on title / fade; ambient music moods |
| Prompt | `starmap_beats_prompt.txt` | telemetry addendum: `metric`, `diagram`, `hud` rows |

## Fallbacks

No picture → the beat stays on the 3D plate (existing behaviour) with its ILLUSTRATION citation; a number with no
diagram → a metric callout; nothing extractable for > 6.5 s → a context lockup naming the subject.
