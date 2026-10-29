# Rep Theory style — Phase 0 (study + plan)

Source: https://www.youtube.com/@thereptheory111 (49.3K subs, 26 videos, fitness / calisthenics for skinny guys,
beginners and home training). Studied 2026-10-29: the channel page, the full video list, and six frames of the
newest video ("Forearm Exercise Tier List (No Gym)", 8:24, 1280x720). A second video stalled on buffering, so
everything below that is not marked *seen* is inferred from titles and descriptions. Verify against a second
video before Phase 1.

## What the format is

Three video lengths, same look:

| Kind | Length | Examples |
|---|---|---|
| Explainer | 8:00-8:15 (very consistent) | "How Training Tendons Makes You Stronger Than Big Guys" |
| Deep guide | 10-15 min | "How Isometric Holds Give You Supernatural Strength (Full Guide)" |
| Short explainer | 3:30-5:15 | "How To Force Your Skinny Wrists To Look Thicker" |

Subtypes: tier list, 90-day roadmap, body-part "force it to grow", myth-bust, how-to-start.

## Features to adopt (every one)

**Look (seen)**
1. Near-black background, 16:9, no stock footage — all illustration and graphics.
2. Illustrated manga/anime-style character (shirtless trainee) doing the exercise, left or centre.
3. Anatomy illustrations with white all-caps labels ("NO MUSCLES", skin/fat/vein cross-section).
4. Props drawn realistically (2 L bottle, towels on a bar, backpack) with an **orange ring + arrow** highlight.
5. Right-hand callout column: big bold yellow/white headline ("THE TRICK"), a value ("3 s"), pill chips with a coloured outline ("EVERYONE HAS ONE", "CAP ON TIGHT").
6. Equation/fact lockups ("2 L ≈ 2 KG").
7. Top-left **section tag** with a red bar ("THE TEST · 2 L BOTTLE PINCH", "THE PLAN · GRIP THEORY 12 · link in description").
8. **Tier-list overlay** for ranking videos: S/A/B/C/D tiers on the left edge, header "TIER LIST · 4/20 RANKED", a "NOW RANKING" card with the item's thumbnail, clown emoji for the bottom tier.
9. **Plan reveal** end card: the product plan page mockup (e.g. "THE 12 WEEKS" table + "THE BAR HANG" exercise card), "GO HEAVIER, NOT LONGER." tagline, link-in-description tag.
10. Captions are YouTube auto-captions, not burned in. Burned-in text is only the callouts above.

**Script and structure (inferred from titles + captions)**
11. Second person, instructional, short sentences, one science claim per item.
12. Title patterns: "How to Force Your ___ to Grow (no gym)", "...especially if you're skinny", "Quit the Gym, Do ___", "___ Roadmap to start from ZERO", "___ Tier List (No Gym)".
13. Audience lock: skinny guys, beginners, no equipment. Every exercise has a no-equipment variant (bottle, towel, backpack, door).
14. Named method series ("GRIP THEORY 12") as the product hook, sold via link in description.
15. Description: emoji lead line, product link, then summary. Telegram link in the channel.
16. Fixed ~8-minute budget with an optional long-form mode.

## Proposed build (same pattern as Health Cinema / What If)

Self-contained package `reptheory/`, one entry in `STYLE_CHOICES` in `app.py`, its own `app_section.py`
(loaded only when picked). Nothing in other styles changes; I will grep `test_fixtures/*_protected.json` first.

- Phase 1 — Spike (one 60 s scene set): background, callout column, section tag, ring highlight, pill chips. Renders to mp4.
- Phase 2 — Planner: narration → beats typed as *item / test / trick / anatomy / equation / tier-ranking / plan*. CSV scene file optional.
- Phase 3 — Art: character + anatomy + props source (see question). Library built once, never per render.
- Phase 4 — Tier-list engine (S–F board, progress header, NOW RANKING card, running placement).
- Phase 5 — Plan-reveal end card + link-in-description tag; description/title generator in the channel's patterns.
- Phase 6 — Script prompt (8 min, second-person, one claim per item) and tests.

## Decisions needed

1. **Art source.** The channel uses AI-generated anime-style art that resembles an existing anime character (white-spiky-haired). I will not copy that character. Options: (a) original character via Flow, generated once per exercise pose into a reusable library (recommended); (b) per-video Flow generation (conflicts with your no-per-video-asset-burden rule); (c) vector/puppet figures built in code.
2. **Product end card.** Keep the "plan reveal" with your own product name/link as an editable field, or omit.
3. **Go-ahead** for the Phase 1 spike.
