# Car Concept style — plan (2026-11-05)

New editing style for 8-12 min narrated concept-car videos for a US audience.
Decisions from the user: no reference videos (we design it), visuals = Flow AI clips + code-built 3D,
audio = voiceover + music, input = CSV + voiceover (zero Gemini calls).

## The look

Premium auto-show feel: dark studio, cool rim light, white type with one accent colour per car
(taken from the car's paint), US units everywhere (hp, lb-ft, mph, miles, $).
Motion every few seconds — no still screens.

| Layer | Source | Used for |
|---|---|---|
| Hero / drive / interior / detail shots | **Flow clips** (Flow still + slow push if the clip fails) | Reveal, walkaround, "on the road", cabin, macro details |
| Spec + tech shots | **Code-built 3D car** (parametric: truck, SUV, sedan, coupe, muscle) in a clay / blueprint look | Turntable with spec callouts, x-ray (battery, motors, engine), dimensions, side-by-side silhouettes |
| Graphics | Code templates | Spec cards, compare bars ("vs Ford F-150"), price card, timeline (sketch → auto show → production), chapter titles, **"Will they build it?" verdict gauge** |

The 3D car is deliberately clay/blueprint style, not photoreal, so it reads as "engineering view"
next to the realistic Flow shots instead of looking like a cheap game car.

## Video structure (planner default)

1. Hook 0-15 s — best Flow hero shot + one big spec or price.
2. Chapter: Design — walkaround Flow shots, 3D turntable callouts.
3. Chapter: Interior.
4. Chapter: Under the skin — 3D x-ray, charts.
5. Chapter: Compare — vs today's US model it would replace.
6. Verdict — "Will they build it?" gauge %, end card.

## Input

`CSV + voiceover (+ optional music)`, press **Generate** (plan only), check, press **Render**.

```
#car,Ford Bronco 2030 Concept,Ford,2030,Cyber Orange,suv
#compare,Ford Bronco 2025,Jeep Wrangler 2025
order,section,line,visual,shot,prompt,value,sub
1,hook,Ford just showed a Bronco with no engine,flow,hero,"orange boxy electric SUV concept, dark studio, slow reveal",,
2,hook,and 600 miles of range,card,,,600 mi,EPA est.
5,tech,The battery sits in the floor,3d,xray,,,
9,verdict,So will Ford build it,gauge,,,72%,chance of production
```

- `line` = a short phrase from the voiceover; rows are placed by fuzzy alignment to the voice (existing Product Trailer aligner).
- `visual` = `flow | 3d | card | chart | gauge | title`; `shot` picks the camera move / 3D view.
- A ready-made `CSV_prompt.txt` turns your script into this CSV in ChatGPT/Claude.

## Car looks the same in every Flow shot

Biggest risk with AI clips: the car changes design shot to shot. Fix: generate **one hero reference
image first**, then every other Flow shot uses it as the reference/ingredient. Shots that fail fall back
to still + push, then to 3D, so a render never stops on a Flow failure.

## Build steps (each with its own tests)

1. `car_concept/` package: CSV parser, `#car`/`#compare` lines, validation + `CSV_prompt.txt`.
2. Planner: voiceover alignment, shot assignment, variety rules (no same shot twice in a row, Flow ≥ half
   the runtime, card length caps), output a What If spec.
3. Flow scene pack: hero reference first, then shots through `visual_bridge` → Visuals tab.
4. Parametric 3D car layer in `whatif-engine` (body types, paint, turntable, x-ray, dimensions, silhouettes).
5. Car graphics layers: spec card, compare bars, price, timeline, verdict gauge, chapter title.
6. App: "Car Concept" in the style picker + its own page, Generate → Render → Export, voice + music mix at -14 LUFS.
7. Touched tests only; one short test render only when you say so.

Reuses: `product_trailer/voiceover.py` (align + mix), `product_trailer/mixed.py` pattern, What If renderer,
`visual_bridge.py`. No changes to Product Trailer itself.
