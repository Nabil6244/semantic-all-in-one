# Reference check 4: two S27 Ultra news reviews (studied 2026-11-06)

Videos (same creator, same series):
- **A** "Galaxy S27 Ultra - Samsung Just Made Some Surprising Decisions!" 4:10, 1280x640, 30 fps
- **B** "Samsung Galaxy S27 Ultra - There's More To This Upgrade" 4:49, 1280x640, 30 fps

Method: faster-whisper base transcript (48 + 72 segments), one frame every 2 s on contact sheets,
ffmpeg scene cuts (threshold 0.25). Each picture was read against the words spoken at that second.

## Rhythm
- Hard cuts: 37 in A, 38 in B. Median shot 5.1 s (A) and 3.6 s (B); long shots are always graphics.
- But the picture changes every **1-2 s** inside a graphic shot: a label, a badge, a number, a highlight
  appears on the exact word. A graphic "scene" is one canvas that **keeps building** across 2-4 sentences.
- About 55 % flat graphics on a light paper background, 30 % real footage (hands-on, dummies, event, stock),
  15 % official-looking renders (x-ray, lifestyle tables). No 3D was built by the creator; the "3D" look comes
  from pre-made renders.

## Rule 1: every noun is on screen when it is said
| Narration (time) | What is on screen |
|---|---|
| "design, cameras, processors, and even the launch timeline" (A 5 s) | hook montage: one shot per item, in that order: dummy camera close-up, "S27 Ultra" title, x-ray with copper chamber, "Galaxy Unpacked" title + event film |
| "compared against the iPhone 18 Pro Max, Pixel 11 Pro XL" (A 27-36 s) | the dummy beside a red iPhone, then beside the Pixel, one per name |
| "identical ... weight and thickness" (A 38-46 s) | side profile of the stacked phones |
| "camera bar similar to the Pixel" (A 51 s) | dummy next to the Pixel's bar |
| "the 5X camera lens looks smaller" (A 58-80 s) | angled lens close-up, then flat renders with a **yellow ring drawn on the 5x lens** of both phones, then a macro where the ring draws as an arc |
| "Pro ... standard 8 Elite Gen 6 / Ultra Extreme" (A 106-118 s) | Pro and Ultra backs with chip badges; "Regular Gen 6" and "Extreme Gen 6" appear on the words, then "+9 % GPU performance" with a green arrow |
| "European models" (A 119 s) | same canvas, background tints blue with the EU stars, title "Snapdragon comes to Europe" |
| "Ice Universe has also backed it up" (A 127 s) | tweet card; a black marker highlights **the exact words as they are read** (karaoke) |
| "S27 and S27 Plus ... Exynos" (A 136 s) | 4-phone lineup, chip badge under each (Exynos, Exynos, Snapdragon, Snapdragon) |
| "12GB of RAM and 256GB" / "16GB ... only with 1TB" (A 148-160 s) | Base/Plus/Pro/Ultra; "12GB RAM" pops on each, then "256GB Storage"; then "16GB RAM / 1TB" stamps on the Ultra only |
| "display sizes" (A 165 s) | phones turn grey with a ring, then colour in with 6.7", 6.3", 6.47", 6.9" |
| "main and ultra-wide ... telephoto?" (A 176-198 s) | callout lines from each lens: 12MP / 50MP / **??MP**; tweet "outdated 3x 10MP" highlighted; back to the callouts where ??MP turns into **10MP** |
| "launch in January ... sales in February" (A 216-236 s) | big type "Launch / January / Unpacked Event 2027", then the word morphs to "Release / February" |
| "four standard color options: black, blue, light pink, white" (B 25 s) | kinetic "4 standard color options", then colour cards appear **one per word in spoken order**, "Online Exclusive Violet" last |
| "we don't know the exact shades" (B 36 s) | a "?" drops on every card |
| "similar to the S26 Ultra sky blue / pink gold" (B 41-50 s) | an S26 Ultra card in that colour slides over the matching card, named |
| "2nm chip" (B 63 s) | phone back fades to x-ray, chip glows, "8 Elite Extreme Gen 6 for Galaxy" + "2nm" types on |
| "more performance means more heat" (B 70 s) | x-ray tints to heat colours, CPU / GPU / RAM bars rise |
| "much larger vapor chamber" (B 80 s) | phone turns sideways, copper chamber slides in, bars fall |
| "iPhone 18 Pro Max ... three times the surface area ... 40 %" (B 90-110 s) | two iPhones, heat-map x-rays, ghost "3X", then "40%" counts in |
| "memory positioned around the chip" (B 117 s) | event-stage footage of the chip maker's slide |
| "gaming, camera processing, AI workloads" (B 140 s) | hands gaming, camera app, a temperature gun on the phone |
| "TheElec reports ... 10 % more Exynos" (B 171 s) | outlet wordmark + Exynos badge, then fab footage with "↑10%" |
| "Pro ... Exynos in Asia and Europe" (B 186 s) | map wipes in behind the Pro, regions fill blue, "Asia & Europe" |
| "But what about the S27 Ultra?" (B 193 s) | previous frame dims, the Ultra tilts in large over it |
| "Samsung LSI ... wants the mobile division" (B 203 s) | corporate stock footage with "Samsung LSI" title |
| "long-term thermal efficiency, chip yields, and production costs" (B 215 s) | a list types in beside the x-ray phone, one line per item **on its word** |
| "10 % higher in multi-core" (B 230 s) | "Geekbench 6" bars Exynos 14000+ vs Snapdragon 12856, "↑10%" |
| "charging a ridiculous amount" (B 246 s) | price line rising, chip badge riding the line, "$260" |
| "similar stories in the past" (B 255 s) | line chart with three chip badges, the line dips |
| "click here to watch the full video" | end card "Check this video out", orange subscribe ring |

## Rule 2: opinion lines get hands, facts get graphics
Sentences with "I", "honestly", "I'd rather", "hopefully", "let me explain", "what's up guys" never get a graphic.
They get hands-on footage: phone turned in hand, S Pen writing, scrolling, a box on a desk. Facts and numbers always get a graphic.

## Rule 3: continuity inside a topic
- Same paper, same phone positions across consecutive sentences; new facts are **added**, old ones dim but stay.
- A new topic changes the set: colour wipe (blue / purple panel swipe), background tint, or a hard cut to footage.
- Unknowns are drawn as "?" and **resolved later** on screen when the narration gives the answer (??MP -> 10MP).
- The previous generation is shown only when named, sliding in beside the new one, with its name.

## Rule 4: sources are always visible
Tweet card with karaoke highlight, database page with a yellow-highlighter headline, outlet wordmark card,
small avatar badge for the tipster, borrowed-footage credit ("AH" watermark, creator name bottom-left).

## Where we use 3D instead of their flat renders (user's request)
| Their flat shot | Our 3D version (existing engine pieces) |
|---|---|
| x-ray phone with chip, heat tint, vapor chamber slide | `product_xray.mjs` tone heat + explode; add chamber-grow and chip-swap (Snapdragon -> Exynos label) |
| yellow ring on the 5x lens | hero `island` move + a screen-space ring that tracks the lens position |
| side profile "weight and thickness" | `profile` move with two phones + `dims` lines |
| dummy next to iPhone / Pixel | `product_room` lineup with the competitor model from `phone_models.mjs` |
| "But what about the Ultra?" tilt-in | hero `rise` / `orbit` over a dimmed copy of the previous frame |
| lineup with chips / RAM labels | 3D lineup with 2D labels pinned above each phone |
| lens callout lines (12MP / 50MP / ??MP) | `island` macro with callout lines pinned to the 3D lens centres |

Flat graphics stay where they read better (colour cards, bars, charts, tweet, date type).

## What we already have (keep all of it)
19 `pt_*` layers, 6 3D builders, 14 hero moves, Review looks Mixed / Cinematic / Infographic / News,
feature-CSV placement, fact gate, balance pass, news footage route. See WHAT_WE_HAVE.html. Nothing below replaces any of these.

## Gaps found (not built yet)
1. ~~**Word-timed builds**~~ **built 2026-11-06**: `product_trailer/wordcue.py` writes `at` / `badge_at` / `highlight_at` from the
   narrator's word times onto pt_flatphones, pt_bench, pt_compare3, pt_glass, pt_gauge, pt_thermal, pt_coststack and pt_tweet
   (timed Review only, when the voice matched). Unnamed items keep the old stagger; a fresh graphic shows its first item within 0.8 s.
2. ~~**Canvas that keeps building**~~ **built 2026-11-06**: `product_trailer/canvas.py` joins consecutive flat-phone scenes of the same
   phones (max 4 scenes / 24 s, only when something new is added): no fade-out / re-entrance, new facts land on their word, facts no
   longer named stay at 40 %, a replaced value (??MP -> 10MP) shows the old one until the new one is said.
3. ~~**Colour cards**~~ **built 2026-11-06**: `layers/pt_swatches.mjs` + `product_trailer/swatches.py`. A sentence with 3+ colours and a
   colour word gets cards in spoken order (every other colour sentence keeps the old colour phones); following colour sentences keep the
   cards up (max 20 s) and add an "Online Exclusive" card, a "?" on unknown shades, and an older model's colour sliding over its match.
4. ~~**Lens callouts**~~ **built 2026-11-06**: `layers/pt_lenses.mjs` + `product_trailer/lenses.py`. Two lenses named (or one asked
   about) draw callout lines from the phone's lenses; following camera sentences keep the scene and add lenses / "??"; an answer said in
   the scene flips "??" to the figure on its word, an answer said up to 30 s later cuts back to a short recap of the callouts after the
   shot it is said in (that shot keeps 3 s). Every other such sentence keeps the older camera scenes.
5. ~~**Ring highlight**~~ **built 2026-11-06**: "the 5X lens looks smaller" -> lens macro (3D `island`) with `layers/pt_ring.mjs`
   sweeping round that lens on its word; `lib/product.mjs` reports each lens's screen position per frame (`parts()`, via scene3d + page.js)
   so the ring follows the camera; inside lens callouts `ring_at` rings that callout's lens. 3D tracking NOT yet seen in a render.
6. **Region map** (Europe / Asia / US) behind a phone with a chip badge.
7. **Date card** (Launch January -> Release February morph).
8. **Reason list** typed beside the product, one line per spoken item.
9. **Karaoke tweet**: `pt_tweet` marker sweeps on a fixed delay; sync it to the spoken words.
10. **Chip on a line** (price / history chart with badges riding the line), extending `pt_curve`.
11. **Opinion router**: opinion sentences -> hands-on footage instead of a graphic.
12. **Hook montage**: a list in the first sentence -> one quick shot per item.
13. **Question beat**: "But what about X?" -> dim previous frame + 3D tilt-in.
14. **3D**: chip swap, vapor chamber grow, lens ring tracking, two-phone profile with dims, competitor lineup.

## More references
Reference 5 (a third video, different creator) adds gaps 15-22: see REVIEW_REFERENCE_5.md.
