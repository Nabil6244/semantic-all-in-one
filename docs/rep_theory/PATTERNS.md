# Rep Theory — pattern study of 9 reference videos (2026-10-29)

Method: vIQ "watch" (end-to-end walkthrough) of 9 of the channel's 26 long-form videos, same nine-point prompt each. Channel list + views from vidIQ. Sample is small and views are confounded by title/thumbnail/topic; treat the performance notes as hints.

| Video | Len | Views | Format |
|---|---|---|---|
| How Training Tendons Makes You Stronger Than Big Guys | 8:03 | 3.93M | mechanism explainer, 4 numbered holds, benchmark payoff |
| Quit the Gym, Do Calisthenics | 8:02 | 1.22M | countdown #5→#1, interactive hook, scorecard payoff |
| How Some Skinny Guys Are Stronger Than Big Guys | 4:45 | 1.10M | story hook, 3 reasons, 12-week plan |
| How Isometric Holds Give You Supernatural Strength (Full Guide) | 14:15 | 581k | 6 holds + rule + Q&A + program + tier board |
| How To Start Calisthenics From Zero | 8:07 | 81k | levels 0-4, rule + 3 mistakes, plan |
| 90-Day Calisthenics Roadmap | 8:15 | 67k | 3 phases, habit trap, rank board (E→S) |
| Forearm Exercise Tier List | 8:24 | 20k | 19 ranked items, tier board, product pitch |
| How to Force your Skinny Calves to Grow | 8:06 | 21k | countdown #5→#1, weakest: templated, assets reused |
| How To Force Your Skinny Wrists To Look Thicker | 3:34 | 18k | myth → anatomy → 3 moves → limit → prescription |

## Patterns (what repeats across videos)

1. **Hook, ~15 s, four variants.** (a) face-off / counter-intuitive claim ("some skinny guys are stronger than their size") + "by the end you will know"; (b) **interactive benchmark** ("do X now, keep your number, at the end I'll tell you what it says"); (c) a concrete story/number (1988, 60 kg lifts 190 kg); (d) misconception + anatomy ("wrist curls won't fix skinny wrists, you can't change the bone").
2. **Roadmap inside the first 30-45 s**: 3-box / 4-card / 5-card preview of what follows.
3. **Unit grammar.** Hook → premise/roadmap → numbered units (45-90 s each: unit card → demo → mechanism/anatomy → study card → cue / common mistake / progression) → The Rule → full routine → timeline + safety → benchmark payoff → CTA → one-line sign-off. 3.5 min = 3 moves + a limit/nuance + prescription; 8 min = 4-6 units; 14 min = 6 units + Q&A lightning round.
4. **Claim → skepticism → proof → drill.** "Sounds lazy? It isn't." → study card with author/year + bar chart → "here's the cue". Contrast formula "X ≠ Y", "you can't change X, you can change Y".
5. **Cadence.** A visual change every 2.0-3.5 s (1.0-1.5 s in intros and routine recaps, 1.2-2.5 s in tier lists). Longest static hold 4-6 s, and even those have internal motion (timer, drawing line, filling bar).
6. **Visual rotation across ≥4 modes**: character art (35-70% of runtime), anatomy plates (10-20%), data (bar chart, line graph, dot plot, gauge, slider, 10-12%), UI mockups (comment, calendar, phone, ~4-6%), analogies/props (engine on rope, spring vs steel cable, ant/elephant), checklists/ladders/grids, historical plate; stock footage <4%. Elements layer in progressively.
7. **Text system.** Top-left breadcrumb that CHANGES per unit (`HOLD 1 · THE WALL HOLD`, `PHASE 1 · DAYS 1-30`), chapter tracker (5-cell pills that fill), headline, value chip, mini-header, bottom-left safety chip. Colour semantics: white = instruction, orange/red = emphasis / warning / muscle, green = positive / verified. Text lands on the stressed syllable (0-0.2 s ahead).
8. **Motion vocabulary.** Punch zoom to a joint, slow push-in, target ring + arrow, red glow on engaged muscle, lines/bars that draw themselves, ticking counters (rep counter, stopwatch ring), stamped checkmarks, strike-through X on myths, ghost trails showing a movement path; 95% hard cuts with pop/swoosh SFX.
9. **Gamified loop.** Baseline test introduced ~0:45 → scorecard / tier board payoff at ~85-95% → "comment your number, retest in N weeks, reply to your own comment".
10. **Ending.** Engagement CTA → free community (phone mockup) → product only where relevant (PDF plan) → one-line sign-off. No generic subscribe screen.
11. **Narration.** 5-10 word sentences, second person, recurring signposts ("Here's the cue", "Why only #3?", "Move 1", "Start one level lower than your ego wants").
12. **Performance hints.** Biggest hits frame a skinny-vs-big contrast with science and a test. The weakest sampled video (calves) was the most templated, reused the same character/step asset, and spent a minute on "it's genetic".

## Rep Theory today vs these patterns (judgement)

| Pattern | State |
|---|---|
| Cadence 2-3 s | Gap: 8 scenes in 62 s = ~7.8 s per scene; several 5-10 s single-picture holds |
| Hook / roadmap / unit grammar / payoff loop | Not built: planner reads one sentence at a time |
| Unit breadcrumb + chapter tracker | Tag is one static title; no tracker |
| Visual modes | 5 of ~10: character, anatomy, prop+ring, equation, tier board. No data viz, study card, UI mockups, checklist/ladder/grid, analogy diagrams |
| Colour semantics | Orange only; no green / red semantics, no safety chip |
| Motion | Ring, glow, slow push, drawing connector. No punch zoom, counters/timers, strike-through, ghost trails |
| Benchmark / scorecard | Tier board exists for one ranked item; no end scorecard |
| Ending | Generic optional end card; no comment-CTA / community mock |
| Script / narration layer | Not built |

## Proposed approach (patterns as data, not a fixed style)
Blueprints (hook type, unit slots, durations per video kind) + a rotation scheduler that picks a visual MODE per beat from what the sentence is (claim, mechanism, study, cue, mistake, progression, number, routine, benchmark, CTA), never repeating a mode back-to-back, a cadence controller that gives every clause a state change every 2-3 s, and a small library of code-drawn components (data card, study card, checklist/ladder, UI mockups, tracker, timeline, safety chip, strike-out). Most of it needs no new Flow images.
