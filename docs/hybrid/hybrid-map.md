# Hybrid Map: how it works

Hybrid Map is the third map style, next to Fact Map and PakMap. All three share the same map renderer, the same asset providers and the same Visual Plan tab; they differ in their **editorial grammar**:

| Style | Primary surface | Grammar |
|---|---|---|
| Fact Map | footage | footage, with an occasional separate map clip |
| PakMap | the map | one persistent map camera; pictures are inserts |
| **Hybrid Map** | **both** | **map (explain space) -> footage (experience it) -> map**, one continuous documentary |

The map explains **where, how far, how large, what connects to what**. Footage shows what the viewer should **see and feel**: people, animals, machines, landscapes, weather, cities, history. The decision is made per **story beat** (a thought: a range of sentences), never sentence by sentence.

## The workflow

```
script + voiceover
  -> timed sentences (Whisper words aligned to the script)
  -> Hybrid Director (own prompt, Gemini)           beats = ranges of sentences, a mode each
  -> HybridPlan (the editable source of truth, saved in the project)
  -> deterministic validation                        errors block rendering, warnings never do
  -> Hybrid critic (Gemini)                          structured findings: weak beats / notes
  -> repair of ONLY the weak beats (at most 2 passes)
  -> Visual Plan tab                                 the footage, to review / change / retry / skip
  -> compile (HybridPlan -> pakMap rows -> pakMap spec)
  -> pakMap engine with the Hybrid options -> video
```

The compiled pakMap script (`hybrid_script.csv` in the work folder) is compiler output for debugging. **You never write it.**

### In the app
1. Pick **Hybrid Map** (the third switch on the Visual Director page; it turns pakMap and Overscaled off).
2. Choose the voiceover (and paste the script on the Script page if you have it: it gives the sentences exact boundaries).
3. **Plan with AI** (or **Load plan...** for a plan file). The plan appears beat by beat: time span, MAP / FOOTAGE / MAP+FOOTAGE, why, the camera, the layers, the clips, warnings.
4. Open the **Visual Plan** tab: every footage clip (and every supporting card) is a row with its source (Stock / Flow / YouTube). Use the normal **Change source, Retry, Skip, Local clip**. Your replacements survive reruns and reopening the project.
5. **Check plan** validates and compiles (every place is looked up, the renderer's own rules are applied). **Repair errors** sends only the beats with errors back to the Director. **Open plan file** opens the JSON for a manual edit; **Load plan...** reads it back.
6. **Generate.** Flow clips cost credits, so the app asks before generating anything new with Flow; clips already saved or replaced are reused.

## Modes of a beat
- **MAP**: the map is on screen with its overlays (title, region fills, markers, lines, number chips, captions). The camera glides from place to place and never cuts.
- **FOOTAGE**: full-screen clips (one or several; they dissolve into each other without the map showing between).
- **MAP+FOOTAGE**: a map beat with one photo card on the map: the map says where, the card shows what.

## Map state across footage
The map is not restarted after footage. The camera cannot move under footage and its drift stops. The map layers' animation clocks stop too, so a line that was half drawn when the footage came is half drawn when the map returns, and carries on from there. A layer's planned end stays in narration time: a layer meant to leave with its beat leaves under the dissolve; a layer meant to persist (`until: after_footage`) is still there on return; a layer whose end would fall deep under the footage is held 0.8 s after the map returns and then leaves (`return_grace_s`, 0 = strict).

## Transitions
Map <-> footage and footage <-> footage are **0.5 s dissolves, centred on the beat boundary**, so a dissolve does not eat the footage beat's own time. Footage straight after footage dissolves over the previous clip and never over the map. No transition makes a sound unless the Director asks for one for a dramatic entry.

## What the validator checks (deterministic)
Errors (block): beats with gaps/overlaps or no timing, invalid mode, a map beat with no geography at all, a footage beat with no clip, unsupported asset type or source, unsupported transition, a camera move that would run under footage, a place that cannot be found (use coordinates for rivers, mountains, seas, small towns), a fill that is not an area, overlays that cannot coexist (more than 2 stat chips, two titles), footage under 2 s.
Warnings (never block): visual churn, footage under 3.5 s, a map beat that repeats the previous one, a static long map or long single-clip footage, repeated footage, no stated purpose, low Director confidence, a coordinate far from the story's other places, an overly dense map.

## Footage audio
Footage is muted in this version; the narration and the existing pakMap sound design (effects and ambience) are the only audio.
