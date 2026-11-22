# Food Files — reference study + build plan (2026-11-22)

Working name **Food Files**: a host-led countdown of real food stories ("The Deadliest X Ever Sold").
Pattern source: the YouTube channel **@stevetalksfood** (all 8 uploads studied). We adopt its *patterns*
(story shape, pacing, card types, rhythm). We do **not** copy its host, name, logo, art or wording.

---

## 1. What the channel is

| Video | Views | Length |
|---|---|---|
| The Deadliest Candy Ever Sold | 5.6 M | 14:13 |
| The Deadliest Snacks Ever Sold | 2.3 M | 19:21 |
| The Deadliest Fast Food Items Ever Sold | 1.3 M | 17:01 |
| The Deadliest Halloween Candy Ever Given Out | 716 K | 17:50 |
| The Most Dangerous Breakfast Cereals Ever Sold | 382 K | 15:48 |
| The Deadliest Energy Drinks Ever Sold | 351 K | 18:15 |
| Every Restaurant Chain That Accidentally Destroyed Itself | 136 K | 19:08 |
| The Deadliest Thanksgiving Meals Ever Made | 100 K | 15:33 |

8 videos, ~10 M views. One formula: **"The Deadliest/Most Dangerous [food category] Ever Sold"**.
Seasonal spins (Halloween, Thanksgiving) and a business spin (chains that destroyed themselves).

## 2. Script formula (from the transcripts)

- **Length:** 2,500–3,100 words, ~180 words/min (fast, chatty). 14–19 min.
- **Items:** 7–10 numbered entries, ~90–150 s each. Not ranked worst-to-best; the order follows story energy.
- **Cold open (0–25 s):** 2–3 shocking teasers in one sentence ("From X that did Y to Z that did W…"),
  then the title line "this is the deadliest candy ever sold", then "But first, we're starting with…".
- **Each entry has the same beats:**
  1. **Hook / setup** — what the product is, one fun fact, "it's still edible, right?"
  2. **The case** — year + place + person + age ("in 2003, a 9-year-old girl in Starke, Florida…").
  3. **Doubt line** — "Sounds fake, right?" / "So what exactly happened?"
  4. **Proof** — a test, a study, a report, a headline.
  5. **Why (the science)** — one simple mechanism in 2–4 steps (layers trap heat → molten core → burst).
  6. **Numbers** — counts, percents, "70 million", "1,300% increase".
  7. **Fallout** — lawsuit, recall, ban, settlement, statement from the company.
  8. **Punchline** — a dry one-liner ("So, yeah… can literally blow up your face"; "…Kinda.").
  9. **Bridge** — the last line ties into the next item ("But while X did its damage in a split second,
     this next candy took its time.").
- **Outro:** points to another video of ours + one open teaser ("one TikTok trend went so viral…"), "click this video right here".
- **Voice:** casual first person, rhetorical questions, light sarcasm, no gore.

## 3. Visual language (from 300+ sampled frames)

**Shot mix** (top video): 164 hard cuts in 853 s, median shot **4.7 s** (p25 2.1 s, p75 7.2 s, max 19 s).
Long shots are never still — a card adds a new element every 1–2 s.
About **35–40 % host on camera, 60–65 % graphics/photos**.

| Shot | What it is |
|---|---|
| **Host** | Man at a desk, studio mic, hoodie, purple/blue LED back-light, gestures a lot. Medium shot. |
| **Word captions** | Bottom-centre, 2–4 words at a time, white condensed bold caps, one **yellow** keyword. On host shots only. |
| **Side scribble** | Handwritten yellow/red note top-right of the host ("DOESN'T LAST FOREVER", "…KINDA"). |
| **Name bar** | Lower-left two-line strap: name / role ("WILLIAM HARDAKER — 'Humbug Billy', candy stall"). |
| **Title open** | Hazard-tape (yellow/black) bands top and bottom, dark red bg, "THE DEADLIEST / CANDY / EVER SOLD". |
| **Number card** | Red diagonal slab with big "#1" + cream panel: subtitle, product name in red, year pill. Hazard tape at bottom. |
| **Next-up sting** | Hazard tape, dark bg, red "?" silhouette, teaser text ("A SPLIT SECOND…"). |
| **Photo card** | Tilted white-border photo over a blurred copy of itself, yellow caption pill, tiny source credit. |
| **Flat explainer** | Cream or dark-brown bg, flat vector icons that **build step by step** with arrows (fridge → sun → fridge; core → layers → spinning pan; cross-section bursts). Header pill on top. |
| **Map** | Dark US/world map, state turns red, pin + label, header "2003 · STARKE, FLORIDA", pill "9-YEAR-OLD GIRL". |
| **Stamp** | Red rubber stamp slammed on ("ALLEGEDLY EXPLODED", "SETTLED", "RECALLED", "NO ONE JAILED", "STOLEN"). |
| **Case folder** | Manila folder: FILED BY / AGAINST / WHY / OUTCOME rows type in, then stamp. |
| **Headline card** | News outlet + date, headline, photo, highlighter sweep on key words. |
| **Tweet / statement** | Social post card or quote card with highlight, then reply counter ("2,300+ replies"). |
| **Big number** | Huge number counting up ("141,850,885 boxes", "$85,000", "~20 DEAD / 200+ ILL"). |
| **Flow chart** | 3 boxes with arrows ("SUGAR = EXPENSIVE → BULK IT UP → 'DAFF' CHEAP FILLER"). |
| **Mini scene** | Flat cartoon street/room with simple characters acting a moment (man carrying turkey, car at night). |
| **Timeline / settle** | Dot timeline, checkmarks, date pills. |

**Look:** cream `#F6EEDC`, dark maroon/brown `#2A1414`, red `#D8262B`, warning yellow `#F5C518`, black.
Condensed heavy sans for titles, handwritten font for scribbles, flat vector art with thin outlines.

**Sound:** quiet music bed, whoosh on card slides, thump on stamps, pop on icon builds, tick on counters.

## 4. What we already have (reuse, don't rebuild)

| Need | Reuse from |
|---|---|
| AI host talking clips (own face, consistent) | `prepper_host/` — Flow talking clips, host pack, host/split/pip shots, name bar, director rhythm |
| Word-by-word captions, card reveals on word times | `prepper_host/director.py` + Whisper times |
| Product / big number / compare / checklist cards | `prepper_host/render.py` card set |
| Flat vector icons that build | Aviation v4 sticker stage, Stickman prop library |
| US / world maps with highlighted region + pin | explainer / map-engine |
| Stamps, folders, headline cards | War reference cards, News Doc headline cards, gfx-core `news` / `stats` templates |
| Pictures of products / places | Flow picture director (cached library), Visuals tab + Export flow |
| Voice | Edge (default) or the Flow host voice used by Prepper Host |
| Loudness levelling | `audio_level.py` |

So Food Files = **Prepper Host's spine + a new card pack + a new script/CSV shape**. Not a new engine from zero.

## 5. Build plan

### Step 1 — Look pack + host
- New package `foodfiles/` built on the Prepper Host runner (import, don't fork).
- Our own host (new face pack, not Steve, not Dale): desk, mic, coloured back-light. Option for a
  **faceless** mode (no host; host lines become photo/icon shots) and a **real-me** mode (user drops in his own
  talking-head clip, we cut it on sentence times).
- Palette, fonts (condensed heavy + handwritten), hazard-tape asset, sound pack (whoosh, stamp thump, pop, tick).

### Step 2 — Card pack (code-drawn, PIL, all with build animation)
Title open · Number card (#N slab + name + year) · Next-up sting · Photo card (tilted, blurred bg, pill, credit) ·
Map card (state/country fill + pin + header + pill) · Stamp (any word, slam + shake) · Case folder (rows type in + stamp) ·
Headline card (highlighter sweep) · Quote/statement card · Tweet card + reply counter · Big number (count-up) ·
Flow chart (2–4 boxes) · Timeline · Side scribble · Name bar · Word captions (yellow keyword).
Every card: no still state over 3 s (rule from "No still screens").

### Step 3 — Flat explainer builder
- An icon library (~80 food/science/legal icons: fridge, sun, jar, bottle, pill, heart, kidney, factory, truck,
  courthouse, kid, doctor, can, candy, burger, fire…) drawn in our own flat style (code or one-time Flow batch, reused
  for all videos — no per-video asset burden).
- A small step-script: `icon → arrow → icon`, `cross-section reveal`, `equals` (turkey = bowling ball),
  `counter row` (4 kids hospitalized), `before/after`. Director turns "why" sentences into 2–4 build steps.

### Step 4 — Script + CSV
- `script_prompt.txt`: the formula in section 2 (cold open, 7–10 items, 9 beats each, bridges, outro).
  Facts must come with a source line (year, place, outlet) — the cards show the source credit.
- `csv_prompt.txt`: one row per sentence: `line, shot, item, visual, title, year, place, stamp, number, source, steps`.
  `shot` ∈ host / photo / map / stamp / folder / headline / quote / tweet / number / flow / explain / scene / next / title.
- A supplied CSV makes **zero Gemini calls** (rule).

### Step 5 — Director + checker
- Rhythm: host ~35–40 %, cut every ~4–5 s, no two host shots in a row longer than 8 s, every item opens with a
  Number card and ends with a Next-up sting.
- Auto-fills: year/place line → map card; "sued / settled / recalled / banned" → stamp; numbers → big number;
  "why / here's why" → flat explainer; outlet names → headline card.
- Plan checker before render: every item has a case + a number + a fallout; no still >3 s; captions fit; source line present.

### Step 6 — Wire into the app
- Style page (Explainers group), CSV/script prompt buttons, Visuals tab + Export path, autorun `make_video.py food-files`,
  Shorts 9:16 layout (one item per Short), thumbnail (product photo + red stamp + big "DEADLIEST").
- Tests: `test_foodfiles.py` (CSV parse, director rhythm, card render smoke, checker).

### Step 7 — First test
- One 60–90 s single-item sample first (one item, all card types), then a full 15-min video only after you OK it.

## 6. Open choices for the owner
1. **Host:** AI host (new face via Flow), faceless, or your own recorded face?
2. **Voice:** Edge voice, or Flow host voice like Prepper Host?
3. **Topic range:** only "deadliest food" lists, or also "chains that destroyed themselves" / "banned foods" / business stories?
