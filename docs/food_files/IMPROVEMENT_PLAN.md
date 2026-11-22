# Food Files — improvement plan (2026-11-22)

Goal: Food Files videos that look and run like the reference channel (@stevetalksfood): **better visuals, more of its
graphic types, a steady supply of real stories, and full 14–19 minute videos**, made by our app with no per-video asset
work. Based on our first render (`out/foodfiles/sweets_two_items.mp4`, 1:49) next to 300+ frames from all 8 reference
videos.

---

## 1. Where we are vs the reference

| | Reference | Our test video | Gap |
|---|---|---|---|
| Length | 14–19 min, 7–11 items, 2,500–3,100 words | 1:49, 2 items | full-length scripts + production at scale |
| Cuts | median 4.7 s, a new element every 1–2 s | ~5.2 s, but cards build slowly | faster builds, shorter number cards |
| Host share | ~35–40 % | 39 % | ✔ |
| Real imagery | real product photos, news screenshots, TV/film frames, documents — on almost every item | none (all Flow-made) | **biggest gap** |
| Card fill | elements fill 60–80 % of the frame | small boxes/icons on big empty backgrounds | sizes + layouts |
| Flat scenes | cartoon people in rooms/streets acting the moment (turkey carrier, classroom, heart monitor) | none | new scene builder |
| Graphic types | ~25 kinds (see 2.4) | 13 kinds | ~12 more |
| Number card | ~2–3 s | ~6 s | cap at 3 s |
| Big numbers | huge, with an icon or photo beside them | small, slow count | bigger, faster, paired |
| Next-up sting | "?" over a themed silhouette (chocolate bar, fries, apple) | plain "?" | themed silhouettes |
| Host | one angle, same wardrobe | one angle | 2 framings + wardrobe per video |

## 2. Visuals

### 2.1 Real imagery first (the biggest gap)
Every item needs real pictures of the real thing. Order of sources per picture slot, all cached once in the library:
1. **Wikimedia Commons** (the app's commons provider): product photos, places, people, historic illustrations. The
   credit line is filled in automatically from the licence ("Photo: X / Wikimedia Commons, CC BY-SA 4.0").
2. **News and TV clips** (allowed by the owner): a few seconds of a news report or TV segment as a framed clip with an
   outlet + date strap, like the reference's MythBusters and news cuts. Fetched with the app's YouTube backend, cut to
   the moment by the transcript.
3. **Official pages as screenshots**: FDA / CPSC / FSIS recall notices, court documents, company statements, news
   headlines. Shown as browser or paper cards with a highlighter on the key line (headline cards built from the real
   page instead of typed text).
4. **Flow** only when 1–3 have nothing, and only for things that are fine to illustrate (a kitchen, a factory floor, a
   generic product). Never a fake "real" photo of a real person or event.

The CSV gets a `find` column ("Wonka Everlasting Gobstopper packaging", "Massachusetts General Hospital building");
the director fills it in by itself when the column is empty.

### 2.2 Bigger, denser cards
- Layout rules: main element 55–75 % of frame height; no row of boxes under 18 % of frame height; at most 30 % empty.
- Number card ≤ 3 s; its text centred; product photo slides in on the cream side when there is one.
- Big numbers 2× larger, a photo or icon beside them, count in ≤ 0.6 s.
- Explainer icons 2× larger with a drawn floor/shadow; 3–5 steps fill the width.
- Every build step lands on its spoken word (already timed); target a new element every 1–1.5 s.

### 2.3 Flat scenes (cartoon people acting it out)
A **scene builder** for the "mini scene" shots: a flat vector room / street / store / kitchen / classroom / hospital
background with 1–4 simple people who move, plus the props and labels.
- Backgrounds: a fixed set of ~20 flat places, made **once** in our flat style (Flow, a strict style prompt) and kept
  in the app; no per-video asset work.
- People: the code-drawn Stickman/cartoon2d rig redressed in the flat style (round heads, coloured clothes), with poses
  (walk, carry, eat, fall, point, sit, sick, cheer) and the count-up row ("4 KIDS HOSPITALIZED" with 1 2 3 4 under them).
- Overlays: speech/thought bubbles, symptom lists with red ✗, monitors (heartbeat line), scales with a dial,
  "HEAVY!" scribbles.
- CSV: `shot=scene2d`, `place=classroom`, `rows=kid: sick; label = SHORTNESS OF BREATH; label = NAUSEA`.

### 2.4 New card types (from the reference, our own drawing)
| Card | What it shows |
|---|---|
| Split compare | two coloured halves, a figure or icon on each ("FRANCHISE OWNERS" vs "CORPORATE") |
| Evidence tags | 2–3 evidence-bag cards with labels ("FOUND INSIDE THE HOME") |
| Symptom pills | map or person + 3 pills under it (JAUNDICE · FEVER · DARK URINE) |
| Multi-state map | several states lit with a label each ("THE STATES PILED ON") |
| Browser / FAQ | a web page mock with the real question or text, highlighter |
| Recall notice | the real notice screenshot (2.1.3) with a stamp |
| Quote + portrait | a framed photo of the speaker beside the quote |
| Red banner header | a strap across the top ("BUT IT STILL WASN'T ENOUGH") over host or picture |
| Product on a scale / dial | the object + a scale, the dial turns |
| Before / after | two photos, a wipe between them |
| Ranking / tally | items stacking into a count ("4 OUTBREAKS · 3 YEARS") |
| Themed next-up | the "?" over a silhouette of the next item's food (icon library) |

### 2.5 Host
- Two framings per clip (medium + tight punch-in) — already cut by the director; add a slight side angle as a third.
- Wardrobe per video (3–4 outfits of Theo, same face): a new set picture per outfit, made once.
- Reactions on hard cuts: a 1-second silent reaction clip (eyebrow raise, "yikes" face) reused across videos.

## 3. Stories (a steady supply for the channel)

### 3.1 Formats that work (reference views)
"Deadliest Candy" 5.6 M · "Deadliest Snacks" 2.3 M · "Deadliest Fast Food" 1.3 M · Halloween candy 716 K ·
cereals 382 K · energy drinks 351 K · restaurant chains 136 K · Thanksgiving 100 K.
→ Broad, kid-memory categories win; seasonal ones spike once a year; business stories are weaker.

### 3.2 A topic bank (first 30, our own angles)
Deadliest: candy (part 2), snacks (part 2), sodas, ice creams, fast-food toys, school lunches, baby foods, kids' drinks,
chips, gum, frozen dinners, gas-station foods, street foods around the world, festival foods, protein/diet products.
Banned / recalled: foods banned in the US but sold in Europe (and the reverse), the biggest recalls ever, products
pulled after one day, lunchbox foods that got recalled.
History: the deadliest food disasters in history, Victorian poison sweets, Prohibition-era drinks.
Seasonal: Halloween part 2, Christmas treats, Easter candy, Fourth of July, Super Bowl snacks.
Business: snack brands that ruined themselves, food mascots that got cancelled, menu items that bankrupted chains.

### 3.3 Research pipeline (before the script)
- Sources with free official data: **openFDA food enforcement API** (every US food recall since 2004), **CPSC recalls
  API** (choking hazards, toy-in-food), **USDA FSIS** recalls, UK FSA alerts, court records, Wikipedia lists of food
  contamination incidents, news archives.
- For each topic: collect 15–20 candidate stories, score them (real case with names/places, a number, a fallout, a
  visual we can show, surprise), keep the best 8–11.
- Each kept story gets a **story card**: product, year, place, who, mechanism (2–4 steps), numbers, fallout, 3+
  sources, pictures to find. The script is written only from story cards.
- A fact check pass: every claim in the script must point at a source on its card; "allegedly" where no court decided.

### 3.4 A Food Files skill (like the Geography Pipeline)
One skill that runs it end to end for a title: check-in (title, length, channel) → research + story cards → script
(DOCX, one paragraph = voiceover) → Food Files CSV → plan checker → titles, SEO, thumbnail ideas.

## 4. Full-length videos (same time as the competitor)

- Script: 2,500–3,100 words, 7–11 items, 90–150 s each (script prompt already says so; the skill enforces it).
- Voice pace ~180 wpm: Flow clips already talk fast; Edge lines get rate +8 % to match.

**Flow voice budget** for a 15-min video (host on screen ~38 %, ≤18 words per clip):

| Mode | Clips | Credits | Lips |
|---|---|---|---|
| All host lines in Flow voice | ~60–70 | ~600–700 | match everywhere |
| Smart: Flow voice for item openers, punchlines and on-camera hooks; the rest of the host lines over b-roll/cards | ~25–30 | ~250–300 | match on camera |
| Loops: 6 silent talking loops + cloned voice | 6 (once) | ~60 once | not matched |

Recommended default: **Smart**. The director moves long host lines onto cards/pictures and keeps on-camera time for
short punchy lines (which is also what the reference does).

**Time per video** (measured on the test: ~1.7 min per Flow clip; render 109 s of 720p in ~6 min):
- Clips: 30 × 1.7 min ≈ 50 min with one account; Flow's multiple accounts in parallel → ~15–20 min.
- Render: today a 15-min 1080p video would take ~1.5–2 h → speed work: cache static card layers, draw only what moves,
  more workers, hardware encode (videotoolbox on Mac). Target ≤ 30 min.
- Pictures: real-photo search is fast; Flow pictures only for gaps.

## 5. Packaging
- Thumbnail in the reference's pattern: the real product big on the right, 2–3 condensed words ("DEADLIEST CANDY"),
  a red stamp, Theo's shocked face small — 3 options per video.
- Titles from the proven patterns + SEO description with the sources list.
- Shorts: one item per Short (9:16 layout of the same cards), 30–50 s, made from the long video's plan.

## 6. Order of work

| Phase | What | Done when |
|---|---|---|
| 1 | Real imagery: Commons search + credits, recall/headline screenshots, news clips; `find` column | the sample re-renders with real photos on every item |
| 2 | Card upgrade: sizes/density rules, faster number + big-number cards, themed next-up | a sheet of every card has ≤ 30 % empty space |
| 3 | 12 new card types (2.4) | each drawn and tested; CSV prompt lists them |
| 4 | Flat scene builder (backgrounds once, people rig, overlays) | 5 scenes in the sample look like the reference's mini scenes |
| 5 | Story research + story cards + the Food Files skill | one full 15-min script + CSV with sources, checker clean |
| 6 | Smart Flow voice + render speed + parallel Flow accounts | a 15-min 1080p video in ≤ 1.5 h end to end |
| 7 | Packaging: thumbnails, titles, Shorts | 3 thumbnails + 3 Shorts from the long video |
| 8 | First full video, review, fix the code (not the video) | a full video you approve |

Phases 1–4 (look) and 5 (stories) can run in parallel; 6 needs 1–4 done to measure.

## 7. Decisions for you
1. Real news/TV clips inside the video: yes for all items, or photos and screenshots only?
2. Flow voice mode for full videos: Smart (recommended), All, or Loops?
3. First full video topic (e.g. "The Deadliest Sodas Ever Sold")?
