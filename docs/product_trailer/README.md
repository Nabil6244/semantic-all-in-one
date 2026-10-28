# Product Trailer

A music-only "concept trailer" for a phone, in the style of a launch teaser: a code-built phone floating in a star field, hard cuts on
the beat, short white type beside the phone. Input is a small feature CSV plus a music track; output is an mp4. The phone is drawn in
code (no model download, no per-video assets). Plan and reference analysis: `PLAN.md`.

## How to use

**App:** pick style **Product Trailer**, choose the feature CSV and the music file, press **Generate** (builds the plan/spec; nothing
starts before this), check it, then press **Render**.

**CLI:**

```
python -m product_trailer <features.csv> --music <track.mp3> --out <trailer.mp4>
```

To write a CSV for a new phone, paste `CSV_prompt.txt` into ChatGPT or Claude, fill in the phone name, and save the reply as `.csv`.
Ready-made examples: `samples/galaxy_s27_ultra.csv`, `samples/iphone_17_pro.csv`, `samples/pixel_10_pro.csv`.

## CSV format

UTF-8, comma-separated. Optional `#` lines first, then one header row, then one row per feature.

```
#product,Galaxy S27 Ultra,Titanium Black,Galaxy S27 Ultra,09:41,Tue 27 Oct
#disclaimer,Concept trailer. Not affiliated with Samsung. Logos belong to their owners.
order,feature,kicker,value,sub,look
1,design,,Slimmer. Stronger,,
2,camera,The next-gen,200MP,main sensor,
4,frame,,Aluminum Frame,,wash:red
```

**Product block** (optional, before the header; any order; each at most once):

| Line | Fields | Default if missing |
|---|---|---|
| `#product` | phone name or preset, colour, wordmark on the back, lock-screen time, lock-screen date | name from the CSV file name; preset colour; wordmark = name; `09:41`; today's date |
| `#disclaimer` | the end-card text (rest of the line, may not contain commas) | a generic "Concept trailer. Not affiliated with the brand. Logos belong to their owners." |

Empty trailing fields in `#product` keep their defaults. Any other `#` line is a comment and is ignored.

**Header:** exactly `order,feature,kicker,value,sub,look`.

| Column | Meaning | Limit |
|---|---|---|
| `order` | position in the film (rows are sorted by it) | integer |
| `feature` | `camera, frame, design, display, chip, os, battery, charging, ai, durability, other`; picks the camera move | unknown -> `other` |
| `kicker` | small line above the big figure | 24 chars, may be empty |
| `value` | the big figure or words | 14 chars (a tagline row: 20) |
| `sub` | small line under the big figure | 24 chars, may be empty |
| `look` | optional background and extras for that row (see below) | empty = star field |

**Background per row (`look`):**

| look | background |
|---|---|
| empty or `stars` | night-sky star field (the reference's look) |
| `wash:red`, `wash:purple`, `wash:#00aaff`, `wash:blue:swoosh`, `wash:gold:aurora` | flowing colour light: `swoosh` = ribbon (like "Aluminum Frame"), `aurora` = curtains (like "Android 17") |
| `gradient`, `gradient:blue`, `gradient:#3355ff` | one soft colour glow fading to black |
| `horizon` | night horizon with distant city lights |
| `studio` | dark studio with a floor and a soft shadow |
| `image:skyline.jpg` | your own picture (next to the CSV, or a full path), dimmed so the phone stays brightest; missing file = star field |

Colour names: red, orange, purple, blue, gold, green, pink, or any `#hex`. A look can also add `bigtype` or `badge`
(e.g. `gradient:blue bigtype`).

A row with `kicker` and `sub` both empty and a multi-word `value` is a **tagline** (`pt_tagline`, e.g. "Slimmer. Stronger"); every
other row is a **feature card** (`pt_feature`). `bigtype` draws `value` huge over a macro (`pt_bigtype`); `badge` shows a generic chip
badge with a gold spark burst.

Feature -> move (default): camera -> island/monolith, frame -> edge (+ swoosh), design -> profile, display -> screen, chip -> chip badge,
os -> hero front with the lock screen, others -> hero/orbit. The planner never repeats a move back to back and the cold open has no text.

## How the phone is chosen

1. **Preset catalog** `whatif-engine/data/phones.json`: each entry holds the build (camera layout, frame, size, colours, wordmark).
2. **Fuzzy name match** of the `#product` name (or the CSV file name) against the catalog names and aliases ("s27 ultra",
   "Galaxy S27 Ultra", "samsung s27u" all hit the same preset).
3. **Generic fallback by brand**: no match -> a generic body for the brand found in the name (Samsung/Galaxy, Apple/iPhone,
   Google/Pixel, ...), else a neutral generic phone. The colour and wordmark from `#product` are still applied.

## Defaults

- Music only (no voice-over).
- Generic badges and plain-text wordmarks; no real brand logos.
- 1920x1080 at 30 fps.
- Disclaimer end card on.

## Test spec

`test_spec_20s.json` is a hand-written 20 s What If engine spec (Phase 1 look match): the reference's cold open (island, monolith,
profile, edge, lock screen), the "Slimmer. Stronger" tagline, the 200MP feature beat and the Aluminum Frame swoosh beat. Render with
`node whatif-engine/render.mjs docs/product_trailer/test_spec_20s.json out/product_trailer_20s.mp4`; music is muxed separately.

## Pace: reveal

Add `#pace,reveal` (or `build_spec(..., pace="reveal")`) for a slow studio film: ~6 s shots on beats (a 6 s grid without music),
phone centred on a charcoal fog backdrop, the back->front `reveal` move every 4 shots, one `pt_caption` per feature, and the phone's
colours cycled across shots from `#colors,Navy,Sky Blue,Pink,White`. Sample: `samples/galaxy_s27_ultra_reveal.csv`.
The default `trailer` pace caps front-facing shots (hero, screen, orbit, rise, flip) at 30 % of product shots.
