# Reference 3: "iPhone Duo Review: After 3,000 Folds, Here's What We Found" (analysis, 2026-10-27)

A full lab-test review, not a trailer. 26 min 26 s, 1280x720 at 29.97 fps, about 320 cuts (average shot 4.8 s), voice-over driven (-19.8 LUFS, LRA 4.9).

## Rhythm
- Shot lengths: 47 under 1.5 s, 147 from 1.5 to 4 s, 82 from 4 to 8 s, 43 over 8 s. Cuts per 2 minutes run 10 to 39: calm explanation, then fast montage.
- Burned-in subtitles on every line, bottom centre, white sans with shadow, about 6 to 9 words at a time, word-chunk timing.
- Chapters: host intro, then sections (design, screen scan, hinge, crease depth, scratch test, brightness, charging, cameras, apps, verdict).

## Shot types seen (all on one timeline)
| Type | Share (est.) | Notes |
|---|---|---|
| Host on camera (neon-lit room) | 8 to 10 % | section intros and opinions; the same frame every time |
| Hands-on b-roll on a desk (real phone in hands, props like Lego landmarks, keyboards) | 30 % | real footage, shallow depth of field, many surfaces |
| Lab and test rig (clamps, force gauges, lasers, scales, 3D-printed jig) | 12 % | proof shots, close-ups |
| Product macros (edges, hinge, ports) on clean surfaces | 15 % | slow slides |
| Diagrams and charts, animated (crease-depth curve, brightness bars, comparisons) | 12 % | dark plate, blue/white type, labels and units |
| X-ray, CT and teardown renders (3D, annotated "3.05 mm") | 6 % | CG |
| Screen recordings and UI captures | 8 % | apps, charging screen |
| Split and triple comparisons (Duo vs 18 Pro Max vs 18 Pro, "300 nit") | 6 % | labelled columns |
| Stat callouts over footage ("1h40min", "30W", "100%") | 3 % | big numeric with an icon |
| Credits tags ("Video footage sourced online") | rare | small top-left text |

## What this means for the tool
This is the opposite of the first two references: the value is in real footage, tests and graphics, not in a rendered phone. The tool's job is to
**assemble and annotate**, and to **generate the graphics and CG**, not to invent the footage.

Needed (in order of how often they appear):
1. **Footage-first timeline from a script and voice-over:** the app already has this path (Hybrid, News Doc): scene list from the narration, clips from the user's folder, stock or Flow.
2. **Burned-in phrase subtitles** (6 to 9 words, bottom centre) from the voice-over alignment; ready in other styles, needs a "review" preset.
3. **Host segments:** reuse one shot of the presenter as a recurring section card; the tool places it, never makes it.
4. **Chart and comparison layers:** animated curve, bars, A/B and triple columns with units. The What If engine has `tm_bars`, `tm_compare`, `pt_bench`; add a curve and a triple-column compare.
5. **Stat callouts over footage** (`tm_metric` already close).
6. **3D teardown / X-ray / fold animations:** the 3D engine can do a labelled phone cut-away and a fold; this is where our phone models earn their keep.
7. **Lab-test slots:** the user's own footage tagged by test type; the planner matches narration lines ("scratch", "hinge", "brightness") to clips.
8. **Sound:** voice-over plus light bed and a few clicks; no beat grid.

AI scenes (Flow) are least useful here: only for lifestyle fill. 3D lineups and rooms are rare; 3D and diagrams carry the explanation.

## Open questions
- Does the review style start from the user's own footage and voice-over, or should it also build a script from research (TechIntel) and propose shot lists?
- Which sections matter first: design, display, camera, battery, durability?
