# Cinematic Explainer — style specification (Phase 0 draft)

Status: proposal for approval. Colours and sizes marked **[A]** are measured from the supplied war video; **[proposal]** are our choices; motion numbers are **[to measure in Phase 1]**.

## 1. Identity
Footage-led news explainer. Graphics are *evidence*: a number, a source, a person, a place, a list. Quiet footage stays quiet: target **card time 25–35 %** of the video (A is 35–40 %, Harris drone film ~0 %), **lower-third shot headlines on 30–40 %** of footage shots, nothing on screen for more than 8 s without a visual change.

## 2. Look
- **Backdrop under a card:** the current footage, brightness ≈ 0.22, gaussian blur 18–24 px, soft vignette **[A, proposal values]**.
- **Palette:** charcoal/navy `#0E1624`, red `#D61C28` (opposition, loss, emphasis), yellow `#FFD500` (baseline, key figure, highlighter), paper `#F4EFE4` (sources), white text **[A]**.
- **Type:** condensed bold sans for numbers and headlines (Oswald-style, already shipped), clean sans for body, serif only on source cards. All from fonts already in the app.
- **Kicker tag:** top-left, small red box, spaced capitals, names the section **[A]**.
- **Geometry:** one card radius, one safe margin (5 % of width), cards never touch the lower third zone.

## 3. Components (and decision source)
| Component | Behaviour | Source |
|---|---|---|
| Source card | paper, red top edge, serif headline, date chip, yellow highlighter sweeps phrases as spoken, optional red pen ellipse | A, B1 |
| Number card | figure in red or yellow, condensed label, rule underneath, count-up for tallies | A |
| List card | rows appear one by one with numerals; same list returns as recap | A |
| Bar compare | two bars, yellow baseline vs red now, values as stated, axis from zero | A |
| Portrait | circle with ring, red name plate, one role line; only with a verified portrait | A, C1 |
| Framed photo | white frame, headline inside, slow drift | A |
| Layered photos | two cut-outs on paper, small offset, for versus scenes | B1 |
| Map skin | relief or dark base, muted fills, white dashed disputed lines, pins with one-line notes, chapter panel | A, C1 |
| Satellite crop | translucent band + two labels | C2 |
| Shot headline | black box, yellow tick, 3–7 words, typed in | A |

## 4. Motion (balanced)
Measured in reference A (±0.1 s): backdrop dims over 0.2 s; source card fades in 0.3 s with a small upward slide, whole sentence pale grey, **words darken in sequence with the narration**; number counts ~0.4 s then label fades 0.2 s and a rule draws left to right in 0.5 s; list rows fade in 0.3 s, one per narrated item. Our values copy these. Highlighter: left-to-right wipe synced to the word timings the pipeline already has. Numbers: final state held ≥ 1.5 s. Map: camera push ≤ 3 s, ease-in-out. Foreground and backdrop animate independently (backdrop is a still blur plate, so no per-frame blur cost). **Hard cut is the default transition**; allowed extras: short push, masked reveal, brief blur-assisted cut. No glitch, no random zoom.

## 5. Story rules (planner)
Choose by meaning, never by a mentioned name: number stated → number card; outlet or institution cited with a claim → source card; named person with a verified portrait and a role → portrait; two things compared → bars or layered photos; place is the subject of a *where* sentence → map; a list of 3–6 items announced → list card; chapter break → map revisit or chapter headline; final 10 % → recap list only if a list was announced earlier. No two cards together; at most one card per 7 s; a full-screen card at most every 25 s.

## 6. Assets and honesty
Reuse the render cache; same person = same portrait file, keyed by name + source URL. Portrait must carry licence and attribution in the plan report; if none is verified, use no portrait (name plate only). Footage must match the subject; a mismatch is flagged, not hidden. Numbers are only those in the script.

## 7. Out of scope
New map engine, presenter compositing, saturated illustration identity, logo bug, automatic subscribe prompts, glitch effects.
