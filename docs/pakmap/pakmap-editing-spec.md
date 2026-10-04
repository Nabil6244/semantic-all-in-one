# pakMap — Reverse-Engineered Editing Specification

Sources: **Reference 1** `Pakmap.mov` — 1920×1080, 30 fps, 13:18 (798.03 s), HEVC. **Reference 2** `2nd reference.mov` — 1920×1080, 30 fps, 3:14 (193.7 s), HEVC, *silent audio track* (see §17).
Sections 1–16 are Reference 1. §17 adds Reference 2 and lists every place where it **overrides** Reference 1.
Reference video: a 30-item countdown ("30 FACTS / COUNTING DOWN") of geographic facts about Russia,
channel watermark `▶ EXPLAINS-IT` bottom-right.

Analysis method: frames sampled at 0.5 s / 2 s intervals across the full runtime, plus
full-resolution frames for typography and colour sampling, plus ffmpeg scene-change detection.

---

## 0. The single most important finding

**The video contains essentially zero hard cuts.**

ffmpeg scene detection at threshold 0.08 (very sensitive) returns ~20 hits in 798 s, and almost all
of them sit *inside* one fast train-POV clip (370–373 s). At threshold 0.2 it returns **zero**.

The entire 13 minutes is **one continuously moving satellite-map camera**. Everything that looks
like a "shot change" is actually:

- an **overlay swap** (chips/labels/markers/PiP enter and exit) over a map that never stops moving, or
- a **0.4–0.6 s cross-dissolve** when the base layer changes (map ⇄ full-screen footage).

This is the defining property of the editing language. Any implementation that cuts between map
shots will not look like this reference.

---

## 1. Global layout and visual system

### Canvas
- Map is **always 100 % full-frame**. No split screens, no letterboxing, no map-in-a-box.
- Everything else is an overlay **on top** of the map.
- Safe margins: ~40 px left/right, ~30 px top, ~40 px bottom.

### Basemap
- Google-Earth-style **satellite imagery** with a stylised dark-teal ocean (`#091525`-ish),
  white 2 px country borders, light grey internal admin borders.
- No street labels, no place names from the basemap — **all text is authored overlay**.
- At extreme zoom (Batagaika crater, 8:20) it is raw high-resolution satellite with no overlay at all.
- The intro and outro use a **3D globe** (curved limb, black space background).
- One shot uses a **polar/top-down Arctic projection globe** on black (4:10).

### Typography
- One family throughout: a heavy geometric sans (Poppins / Montserrat ExtraBold class), **ALL CAPS**, tight tracking.
- Three type sizes only:
  - **Headline** (~64–72 px) — stat chip number
  - **Title** (~40–44 px) — "NUMBER 14"
  - **Caption** (~20–26 px) — subtitles, labels, chip sub-lines

### Colour tokens (sampled)
| Token | Value | Meaning |
| --- | --- | --- |
| Chip white | `#FFFFFF` | the "NUMBER NN" title chip background |
| Panel black | `#111111` → `#0E1A24` @ ~90 % | subtitle chip, stat chip background |
| Brand yellow | `≈ #F8E840` | stat numbers, the featured/measured entity |
| Subject red | `≈ #E8233C` | the critical fact / the subject under discussion |
| Compare blue | `≈ #2E7BE8` | the *other* entity in a comparison |
| Neutral white chip | `#FFFFFF` | ordinary place labels |
| Primary region fill | `≈ #6B2820` (dark red, ~45 % over satellite) | Russia / the subject country |
| Secondary region fill | orange `≈ #D2641E` | a sub-region of the subject |
| Tertiary region fill | steel blue `≈ #4A7FB5` | a comparison country |
| Accent region fill | purple `≈ #7B4FC4` | a third-party country |
| Water highlight | cyan `≈ #3FC8E0` | lakes, seas, rivers |
| Route orange | `≈ #F09030` | ocean current / flow |
| Boundary yellow | `≈ #F8E840` | highlighted border, continental divide, date line |

### Persistent HUD (present ~96 % of the runtime)
1. **Title chip** — top-left, white rounded rect, black text: `NUMBER 14`
2. **Subtitle chip** — directly beneath it, black rounded rect, white text, wraps to 2 lines:
   `SIBERIA ALONE WOULD BE THE BIGGEST COUNTRY`
3. **Watermark** — bottom-right, low-opacity `▶ EXPLAINS-IT`

The title/subtitle pair **persists through everything**, including full-screen archival photos and
full-screen b-roll. It is the spine that lets the editor dissolve freely without the viewer losing place.

---

## 2. The overlay vocabulary (eight element types — that is the whole system)

| # | Element | Description | Enter | Exit | Typical life |
| --- | --- | --- | --- | --- | --- |
| 1 | **Title + subtitle chip** | top-left pair | title chip scales/wipes in, subtitle **typewriters** character-by-character with a block cursor | fades/wipes out ~0.5 s before next item | whole item (20–36 s) |
| 2 | **Stat chip** | big yellow number + small white sub-line, on a black panel. Bottom-left, bottom-right, bottom-centre, or top-right | slides up + fades, number **counts/ramps** to its value (`12.6M → 17.1M`, `0/5 → 1/5`, `−37 → −38 °C`, `299 → 300`) | fades out | 3–6 s |
| 3 | **Marker** | small ring dot + text chip, anchored to a geo coordinate. Can carry a value (`MT ELBRUS · 5,642 M`) or a date (`TUNGUSKA · 1908`), and can have a **sub-chip** beneath (`LAST ERUPTED ABOUT 2,000 YEARS AGO`) | dot pops, label chip **typewriters** open | fades | 5–20 s |
| 4 | **Region fill** | polygon filled with a token colour + 2 px bright outline | fades/wipes in over ~0.3–0.5 s | fades | 5–25 s |
| 5 | **Line** | route (orange, with arrowhead), river (cyan), railway (white), border trace (yellow), reference line (dashed), date line (dashed yellow vertical) | **draws progressively head-first, MEASURED 0.90 s, ease-out** | fades | 5–20 s |
| 6 | **PiP card** | rounded-corner photo/video card, white 3 px border, drop shadow. Landscape, square or portrait. Left or right third. Sometimes with a **leader line** to a marker | **snap-in: ~115 % scale at ~40 % opacity for 1 frame, then settles to 100 % / full opacity. Total ≈ 0.15–0.20 s** | straight fade, no shrink, ≈ 0.4–0.5 s | 4–8 s; content can **crossfade to a second image** inside the same frame |
| 7 | **3D sticker** | cut-out 3D illustration sitting on the map (hiker, mammoth, clock pair, exploding fireball, stilt house, sinking house, waterfall slab, geological core) | **pops in at full size, ≤ 0.2 s** | straight fade, ≈ 0.5 s | 3–6 s |
| 8 | **Point cluster** | many small dots appearing in sequence (300 volcanoes orange, aftershocks red, 11 time-zone dots yellow) | staggered pop, ~30–60 ms apart | fades together | 5–10 s |

There is **no**: legend, scale bar, north arrow, axis, chart, graph, callout arrow pointing at text,
lower-third name bar, bullet list, on-screen narration subtitles, or transition wipe/zoom "whoosh".

### 2a. PiP cards and 3D stickers — measured detail

**Entry is a snap, not a graceful animation.** Measured at 15 fps on the Murmansk PiP (291.6 s):
one frame at ~115 % scale and ~40 % opacity, the next at ~102 %, the next settled at 100 %.
**Total entry ≈ 0.15–0.20 s (4–6 frames at 30 fps), easing out.** The card scales *down* into place,
which reads as "landing toward the viewer" — not scaling up from small. There is also a small
positional offset: it arrives from slightly up-and-right of its final spot.

**Exit is a plain fade over ~0.4–0.5 s.** No shrink, no slide.

**Both PiP and sticker are map-anchored** — they drift with the camera rather than sitting in
screen space.

**The sticker is a static PNG.** It has no idle animation, no bob, no rotation. It pops in at full
size in ≤ 0.2 s and holds motionless while the map drifts beneath it.

**Every sticker sits on a diorama base** — a cut-out ground plinth (ice floe with rocks for the
mammoth, mossy rock for the hiker, a ring of forest for the Tunguska fireball, a stratigraphic
column for the borehole). The base replaces a cast shadow; nothing is composited onto the map
surface itself.

**Sticker size is large**: 35–50 % of frame height. These are hero moments, not decorations.

**Layer budget — the sticker replaces the PiP.** At 662.1 s the PiP card and the stat chip fade out
on the *same frame* that the mammoth appears. They never coexist. The rule is: one "rich media"
object on screen at a time — either a PiP card or a sticker, never both.

**Number ramps ease out.** Measured at 7.5 fps: `3,927 → 3,981 → 3,998 → 4,000` across ~0.4 s,
decelerating into the final value with no overshoot.

**Inventory**: ~10 stickers across 30 items — roughly one every third item. PiP cards appear in
almost every item, ~1.4 per item, present ~55 % of total runtime.

---

## 3. Map scene types actually present

| Type | What happens | Example |
| --- | --- | --- |
| **A. Establishing globe** | 3D globe, subject country filled, slow rotate + push-in toward the region | 0:00, 12:55 |
| **B. Country canvas** | whole subject country filled red, continental framing, slow drift | 2:45, 6:20 |
| **C. Location reveal** | fly/push to a place, marker + label types in, PiP photo of the place | Murmansk 4:46, Norilsk 7:22 |
| **D. Geographic zoom-in** | continuous push from country framing to regional to local satellite | Batagaika 8:20 |
| **E. Region highlight / sub-region** | a polygon inside the subject is filled a second colour and labelled | European Russia 0:34, Siberia 6:50, Yakutia 7:00 |
| **F. Two-region comparison** | two polygons in two colours on screen at once, usually with **two stat chips simultaneously** | Russia vs Ukraine 0:40, 3-in-4 vs 1-in-4 7:48, India vs Yakutia 7:08 |
| **G. Two-marker comparison** | two markers on one frame, sometimes with a connecting dashed line | Mont Blanc / Elbrus 1:38, Big & Little Diomede 12:26 |
| **H. Route / flow draw** | polyline animates head-first, often while the camera **pulls back** to fit it | Gulf Stream 5:00, Trans-Siberian 5:58 |
| **I. River draw** | cyan polyline draws along a real river, mouth label appears | Volga 3:12, Yenisei 3:44 |
| **J. Boundary / divide highlight** | an existing border or a conceptual line is traced in yellow and zone-labelled on both sides | Europe/Asia 1:14, Russia–Kazakhstan 2:25, Date line 12:35 |
| **K. Feature outline** | a dashed outline traces an island chain / small feature | Kuril Islands 5:33 |
| **L. Water body highlight** | a lake or sea is filled cyan and labelled | Ladoga 1:00, Caspian 3:22, Baikal 11:12 |
| **M. Reference line** | a dashed latitude line with a text label | Arctic Circle 4:44, 7:38 |
| **N. Point-cluster map** | dozens of small dots revealed progressively, counted by a stat chip | 300 volcanoes 9:38, time zones 12:02 |
| **O. Polar / alternate projection** | top-down Arctic globe on black | 4:10 |
| **P. Non-geographic comparison** | a map scene whose PiP is not a place at all (Pluto, a cheque) used for scale/ history | 6:30, 12:45 |
| **Q. Full-screen media interlude** | map dissolves away entirely to b-roll or archival photo; HUD stays | 2:50, 6:10, 8:50 |
| **R. Outro / CTA** | pull back to globe, centred CTA chips | 12:55 |

---

## 4. Geographic hierarchy actually used

The reference uses a **shallow, 4-level hierarchy** and it never goes below city/feature level
except with raw satellite imagery.

```
GLOBE  (intro / outro / one polar shot)
  └─ CONTINENTAL  (Eurasia framing — the default "home" view, used in ~40 % of shots)
       └─ COUNTRY  (Russia filled; neighbours filled for comparison)
            └─ REGION  (European Russia, Siberia, Yakutia, Kamchatka, Kola, Kuril arc)
                 └─ LOCAL  (city marker / lake / mountain / crater — ~50–200 km across)
                      └─ RAW SATELLITE  (one case: Batagaika, ~5–10 km across, no overlays)
```

Rules observed:
- The **continental framing is "home"**. Most items begin and end there.
- Descent is **continuous**, never a cut: a single long push-in from country → region → local.
- Ascent (pull-back) is used to **fit a route or a comparison** into frame, and at the end of an item.
- The video never zooms to street level and never uses 3D terrain tilt — the camera is **always top-down**.

---

## 5. Camera / motion grammar

| Move | When | Speed |
| --- | --- | --- |
| **Idle drift** | *always on*. The map is never completely static. | **MEASURED 0.4–0.9 % of frame width per second** (4–9 px/s at 960-px width). Continues unchanged under PiP cards and stickers. |
| **Slow push-in** | during a sustained explanation on one place | scale ×1.0 → ×1.25 over 8–15 s, ease-in-out |
| **Fly-to** | between items, or when narration names a new place | 1.5–2.5 s, strong ease-in-out, simultaneous pan + zoom (a single curved interpolation, not pan-then-zoom) |
| **Fast pull-back** | to fit a route or a wide comparison | 1.5–2 s, ease-out |
| **Globe rotate** | intro/outro only | ~3–5 °/s |

**There is no**: rotation of the map, bearing change, tilt/pitch, camera shake, whip-pan, snap-zoom,
or speed-ramped "zoom whoosh".

---

## 6. Rhythm and density

| Metric | Measured value |
| --- | --- |
| Total runtime | 798 s |
| Countdown items | 30 (plus intro 29 s + outro 29 s) |
| Mean item duration | **~23.7 s** |
| Item duration range | 14 s (#22) → 36 s (#10) |
| Hard cuts | **0** |
| Cross-dissolves (base-layer changes) | ~12 across the video |
| Overlay events (chip/marker/fill/line/PiP in-or-out) | ~6–10 per item |
| **Visual change rate** | **~16–20 overlay events per minute — one roughly every 3–4 s** |
| Map screen-time | **~92 %** |
| Full-screen footage / photo screen-time | **~8 %** (3 b-roll interludes + 1 archival photo + 2 globe shots) |
| PiP present | ~55 % of runtime; ~1.4 PiP cards per item |

**Rhythm rule:** the viewer never goes more than ~4 seconds without *something* changing, but the
*base layer* changes at most once or twice per minute. Density lives in the overlays, not in cutting.

---

## 7. Item structure (the repeating 5-beat template)

Every one of the 30 items follows the same beat pattern:

```
BEAT 0  CLEAR      (0.5–1.0 s)  previous item's chips/PiP/fills fade out; map keeps moving
BEAT 1  TITLE      (1.0–1.5 s)  "NUMBER NN" chip in; subtitle typewriters
BEAT 2  LOCATE     (2–5 s)      camera flies/pushes to the subject; region fill or marker appears
BEAT 3  REVEAL     (6–15 s)     the geographic action: route draws / boundary traces / second region
                                fills / cluster populates; stat chip counts up; PiP photo enters
BEAT 4  SUPPORT    (4–8 s)      PiP content crossfades, 3D sticker or second stat chip, or a
                                dissolve to full-screen b-roll
BEAT 5  RELEASE    (1–2 s)      overlays fade; camera starts its move toward the next item
```

Beat 4 is optional and is where ~a third of items skip straight to Beat 5.

---

## 8. Narration → visual trigger rules (verified from the reference)

These are the rules the edit actually obeys. Each is **information-driven**, not time-driven:

| Narration event | Visual action | Verified at |
| --- | --- | --- |
| New fact begins (countdown beat) | Title chip swaps; everything else clears first | every item boundary |
| A **place name** is spoken | camera flies to it; marker dot + typewritten label | Murmansk 4:46, Norilsk 7:22, Oymyakon 10:28 |
| A **number / measurement** is spoken | stat chip slides up and **counts to the value** | 2:28 `7,523→7,600 KM`, 6:26 `12.6M→17.1M KM²` |
| **Two places/things compared** | both appear in frame simultaneously, in two different token colours; often two stat chips | 0:40 Russia/Ukraine, 7:08 India/Yakutia, 11:20 Baikal/Great Lakes |
| **Movement / flow / travel** is described | a line draws head-first along the path, often while the camera pulls back to fit it | 5:00 Gulf Stream, 5:58 Trans-Siberian, 3:12 Volga |
| A **boundary / division** is stated | the border traces in yellow and both sides get zone chips | 1:14 Europe/Asia, 2:25 Russia–Kazakhstan, 12:35 date line |
| An **area / proportion** is stated | region polygon fills with the secondary colour | 0:34 European Russia, 6:50 Siberia, 7:48 3-in-4 split |
| **Scale is explained** ("as big as…") | the camera zooms *out*, or a non-geographic PiP is introduced (Pluto, Great Lakes figure) | 6:30 |
| A place is **described sensorially** ("forests", "cold", "the train") | PiP photo enters; if the description runs >6 s, the map **dissolves to full-screen b-roll** | 2:50, 6:10 |
| A **historical event** is named | marker with the year; archival photo; 3D sticker of the event | 8:40 Tunguska 1908 |
| A **count of things** is stated | point cluster populates while the stat chip counts | 9:38 volcanoes, 12:02 time zones |
| A fact is **surprising / is the punchline** | the relevant chip turns **red** | Kaliningrad 5:12, `NO ROAD · NO RAIL` 7:28, `1 IN 4` 7:52 |
| Narration pauses / transitions | nothing new enters; the idle drift carries the gap | every Beat 0 |

**Negative findings — triggers the reference does *not* use:**
- It never shows a map for a sentence with no geographic content; in those moments it holds the
  existing map and lets the drift carry it.
- It never re-establishes with a globe mid-video (only intro/outro + one deliberate polar shot).
- It never animates a boundary just because a country is mentioned — boundaries only animate when
  the boundary itself is the fact.

---

## 9. Map ⇄ non-map relationship

The map is **the main visual, not a cutaway**. ~92 % of screen time.

| Non-map asset | How it is used | Transition in | Transition out |
| --- | --- | --- | --- |
| **Photograph** (place, landscape) | PiP card over the map, anchored left or right third | scale-up + fade, 0.3 s, from the anchor side | shrink + fade, 0.3 s |
| **Stock b-roll video** | mostly PiP; 3× it takes the **full frame** | 0.4–0.6 s cross-dissolve from the map | 0.4–0.6 s cross-dissolve back to the map — and the map returns at the *same* camera position it left |
| **Archival photo / document** | full frame (Tunguska) or PiP (Alaska cheque) | cross-dissolve / PiP scale-up | same |
| **Non-geographic image** (Pluto) | PiP, for a scale comparison | PiP scale-up | PiP shrink |
| **3D illustration sticker** | sits *on* the map, map-anchored, no card frame | scale-up with overshoot | shrink |
| **Second video inside a video** | a PiP card can sit over full-screen b-roll, and then the base dissolves back to the map leaving the PiP in place | — | — |

So, classified against the user's question, the map is:
- **the main visual** (primary role, ~92 %)
- **an establishing shot** (intro globe → country, outro country → globe)
- **an explanatory visual** (routes, fills, comparisons — this is where the information lives)
- **a bridge** between two real-world shots (the map is always what b-roll dissolves *to* and *from*)
- **never a transition device** (there is no "fly across the map to get to the next topic" whoosh)

---

## 10. Timeline table

Times are mm:ss, derived from frame sampling (±1 s). "Dur" is the item duration.

| Time | Narration / Event | Visual | Map Action | Motion | Dur | Transition | Purpose |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0:00 | Hook — one town, −68 °C to +38 °C | 3D globe, Russia red-filled, Verkhoyansk marker | globe → country → regional push | slow rotate + continuous fly-in | 29 s | — (open on globe) | establish subject + stakes |
| 0:02 | "…minus sixty-eight" | stat chip L counts `−48 → −68 °C / SAME TOWN` | — | chip slide-up + number ramp | | — | quantify |
| 0:05 | "…plus thirty-eight" | second stat chip R `+24 → +38 °C` | — | second chip, dual-chip layout | | — | contrast |
| 0:06 | "30 facts, counting down" | chip `0 → 30 FACTS / COUNTING DOWN` | — | count-up ramp | | — | format promise |
| 0:13 | — | PiP photo of the town | — | PiP scale-up from left | | — | sensory support |
| 0:16 | "between Russia and the USA" | markers `RUSSIA ◦ USA` across Bering | pan east to Bering Strait | lateral drift | | — | locate |
| 0:29 | **#30** "just the European part wins" | title chip + subtitle typewriter | back to continental framing | pull-back | 22 s | overlay swap, no cut | item open |
| 0:34 | "the European part alone" | European Russia fills orange inside red Russia | region highlight | fill crossfade 0.4 s | | — | sub-region |
| 0:38 | "4 million km²" | stat chip `4 MILLION KM²` | push-in to European Russia | push | | — | quantify |
| 0:42 | "six times Ukraine" | Ukraine fills blue + blue chip `UKRAINE · 0.6M KM²`; chip `6×+` | second-region compare | — | | — | comparison |
| 0:46 | river sunset b-roll | PiP portrait card | — | PiP scale-up right | | — | texture |
| 0:51 | **#29** "a country of lakes" | title swap; lakes darken into view | fly to NW Russia | fly-to 2 s | 20 s | overlay swap | item open |
| 0:56 | "1.2 → 2.7 million lakes" | stat chip counts | — | ramp | | — | quantify |
| 1:00 | "Lake Ladoga" | lake fills cyan, yellow chip `LAKE LADOGA · 17,700 KM²` (typewriter), marker `ST PETERSBURG` | water-body highlight | push-in | | — | feature reveal |
| 1:06 | "bigger than Montenegro" | chip `> MONTENEGRO / 13,800 KM²` + PiP lake photo | — | chip in / out crossfade | | — | scale comparison |
| 1:11 | **#28** "two continents, split by hills" | title swap | fly SE to the Urals | fly-to 2 s | 26 s | overlay swap | item open |
| 1:14 | "Europe ends here" | **yellow divide line** draws N–S; white chips `EUROPE` / `ASIA` on each side | boundary/divide highlight | line draw 2 s | | — | the fact itself |
| 1:18 | "the Urals" | PiP photo of the Urals monument | — | PiP right | | — | texture |
| 1:28 | "Mt Narodnaya, 1,895 m" | marker + value; later a leader-line PiP and a hiker 3D sticker | marker on the divide | push-in | | — | superlative |
| 1:37 | **#27** "Europe's highest peak is a volcano" | title swap | fly W to the Alps | fly-to 2 s | 22 s | overlay swap | item open |
| 1:39 | "not Mont Blanc" | marker `MONT BLANC · 4,806 M` | marker | drift | | — | set up misdirection |
| 1:44 | "it's Elbrus" | camera flies E to Caucasus; marker `MT ELBRUS · 5,642 M`; stat chip `5,642 M / EUROPE'S HIGHEST` | two-marker comparison across one move | fly-to 2 s | | — | payoff |
| 1:50 | "a volcano — last erupted 2,000 years ago" | PiP of Elbrus (2 photos crossfaded) + marker **sub-chip** typewriter | — | PiP left | | — | elaborate |
| 1:59 | **#26** "from Norway to North Korea" | title swap; Russia re-fills red; neighbours fill blue | country + neighbours | pull-back to continental | 22 s | overlay swap | item open |
| 2:01 | "fourteen land neighbours" | stat chip `14 / LAND NEIGHBOURS`; chip `CHINA · 14 TOO` | — | ramp | | — | quantify |
| 2:05 | "Norway… to North Korea" | marker `NORWAY`, then pan E, marker `NORTH KOREA`; NK fills purple | multi-location sweep | long lateral pan 3 s | | — | span |
| 2:14 | "a 17 km border" | yellow chip `17 KM` + leader-line PiP of the rail bridge | micro-feature | push-in | | — | surprising detail |
| 2:21 | **#25** "the longest unbroken border on Earth" | title swap; Kazakhstan fills blue | region compare | fly SW | 24 s | overlay swap | item open |
| 2:25 | "7,600 km" | **yellow border trace** animates around Kazakhstan; stat chip counts `7,523 → 7,600 KM` | boundary trace | draw 2.5 s | | — | the fact |
| 2:32 | "longer than Canada–USA, but Alaska splits that one" | chip `CANADA–USA / LONGER, BUT ALASKA SPLITS IT IN TWO` (typewriter sub-line) | — | chip swap in place | | — | qualify |
| 2:38 | "New York to LA and more than halfway back" | chip `NEW YORK → LA` | — | chip swap | | — | relatable scale |
| 2:45 | **#24** "a fifth of the world's trees" | title swap; Russia red fill | country canvas | slow drift | 24 s | overlay swap | item open |
| 2:47 | "a fifth of Earth's forests" | stat chip `0/5 → 1/5` | — | ramp | | — | quantify |
| 2:50 | forest description | **full-screen forest b-roll** | map leaves | **cross-dissolve 0.5 s** | 10 s | dissolve | immersion |
| 3:01 | — | PiP of a second forest clip appears *over* the b-roll | — | PiP right | | — | layering |
| 3:05 | — | base dissolves back to the red-filled country map, PiP stays | map returns at same camera pos | **cross-dissolve 0.5 s** | | dissolve | return home |
| 3:09 | **#23** "Europe's longest river never reaches the sea" | title swap | fly to Volga basin | fly-to | 32 s | overlay swap | item open |
| 3:12 | "the Volga, 3,500 km" | **cyan river polyline draws** N→S; stat chip counts `1,613 → 3,500 KM` | river draw | draw 2.5 s | | — | the subject |
| 3:20 | "it ends in the Caspian — which is a lake" | Caspian fills cyan, white chip `CASPIAN SEA · A LAKE` | water-body highlight | push-in | | — | the twist |
| 3:30 | "28 m below sea level" | stat chip **bottom-left** `−28 M / BELOW SEA LEVEL` + PiP coastline | — | chip (position moved to avoid the subject) | | — | quantify |
| 3:41 | **#22** "the river that splits Russia in two" | title swap | pull back to country | pull-back | 14 s | overlay swap | item open (shortest) |
| 3:43 | "the Yenisei" | cyan river draws S→N; marker `ARCTIC OCEAN`; stat chip `19,600 M³/S` | river draw | draw 2 s | | — | the subject |
| 3:48 | "flat to the west, mountains to the east" | white chips `FLAT` / `HILLS + MOUNTAINS` either side of the river; 3D waterfall sticker | zone labelling | — | | — | the fact |
| 3:55 | **#21** "three oceans, thirteen seas" | title swap; Russia red | continental | pull-back | 24 s | overlay swap | item open |
| 3:58 | naming the oceans | blue chips `ARCTIC`, `PACIFIC`, `ATLANTIC (BALTIC + BLACK SEA)` appear progressively, each on its basin | progressive multi-zone labelling | drift | | — | enumerate |
| 4:04 | "thirteen seas" | stat chip `13 / SEAS (WITH THE CASPIAN)`; icebreaker PiP | — | ramp | | — | quantify |
| 4:10 | "over half the Arctic Ocean coast" | **polar top-down globe on black**; stat chip counts `36,787 → 37,000+ KM`; yellow chip `OVER HALF THE ARCTIC OCEAN` | projection change | dissolve to globe, then back | | **cross-dissolve** | the payoff fact |
| 4:19 | **#20** "all that coast, and a port problem" | title swap; back to country red | continental | pull-back | 22 s | overlay swap | item open |
| 4:24 | "Vladivostok" | fly SE; marker + PiP of frozen bay | location reveal | fly-to 2 s | | — | locate |
| 4:31 | "the Danish Straits… the Bosporus" | fly W to Europe; two markers; PiP of the Bosporus | two-location sequence | long fly 2.5 s | | — | the constraint |
| 4:41 | **#19** "the Arctic port that never freezes" | title swap | fly N to Kola | fly-to 2 s | 26 s | overlay swap | item open |
| 4:44 | "above the Arctic Circle" | **dashed reference line** + chip `ARCTIC CIRCLE`; marker `MURMANSK` | reference line | drift | | — | geographic context |
| 4:48 | city description | PiP of Murmansk (4 s life) | — | PiP left | | — | texture |
| 5:00 | "the Gulf Stream reaches it" | **camera pulls back fast** to the N Atlantic while an **orange arrow route draws** head-first from the SW to Murmansk; red chip `GULF STREAM` types in at the origin | route draw + synchronised pull-back | pull-back 2 s, draw 2 s | | — | the mechanism |
| 5:07 | **#18** "a piece of Russia that doesn't touch Russia" | title swap | fly SW to Baltic | fly-to 2 s | 22 s | overlay swap | item open |
| 5:10 | "surrounded by Poland and Lithuania" | Poland fills blue; Kaliningrad traced | region highlight | push-in | | — | context |
| 5:12 | "Kaliningrad" | **red chip** `KALININGRAD` | subject marker (red = the punchline) | — | | — | the subject |
| 5:16 | "cut off from Moscow" | **yellow dashed connector** draws to marker `MOSCOW` | relation line | draw 1.5 s | | — | the relation |
| 5:20 | "an ice-free Baltic port" | yellow chip `ICE-FREE BALTIC PORT` above the red chip + beach PiP | stacked chips | — | | — | the why |
| 5:29 | **#17** "the islands that stopped a peace treaty" | title swap | long fly E to Hokkaido/Kurils | fly-to 2.5 s | 28 s | overlay swap | item open |
| 5:33 | "the Kuril Islands" | **yellow dashed outline traces the island arc** NE→SW; yellow chip `KURIL ISLANDS` | feature outline | draw 2.5 s | | — | the subject |
| 5:40 | "Japan calls them the Northern Territories" | Hokkaido + 4 islands fill blue; blue chip `"NORTHERN TERRITORIES"` | claim comparison | — | | — | the dispute |
| 5:52 | "24 km from Japan" | stat chip `24 KM / FROM JAPAN` | — | ramp | | — | quantify |
| 5:57 | **#16** "a week on one train" | title swap; country red | continental | pull-back | 22 s | overlay swap | item open |
| 5:59 | "Moscow to Vladivostok" | **white railway polyline draws** W→E; end markers; stat chip counts `9,272 → 9,300 KM`; station PiP | route draw | draw 2.5 s | | — | the subject |
| 6:10 | "a week of this" | **full-screen train-POV b-roll**; stat chip `8 / TIME ZONES` | map leaves | **cross-dissolve 0.5 s** | 4 s | dissolve | immersion |
| 6:15 | — | back to map with route still drawn + monument PiP | map returns | **cross-dissolve** | | dissolve | return home |
| 6:19 | **#15** "almost as big as Pluto" | title swap | continental | slow drift | 28 s | overlay swap | item open |
| 6:26 | "17.1 million km²" | stat chip counts `12.6M → 17.1M KM²` | — | ramp | | — | quantify |
| 6:30 | "Pluto's surface is 17.7" | **Pluto photo PiP** (non-geographic); second stat chip counts `13.4M → 17.7M KM²` | scale comparison | PiP right | | — | the comparison |
| 6:38 | "96 % of Pluto" | stat chip `5 % → 96 % / RUSSIA vs PLUTO` | — | ramp | | — | the payoff |
| 6:47 | **#14** "Siberia alone would be the biggest country" | title swap; Siberia fills **orange** with a straight western edge | sub-region highlight | fill crossfade | 30 s | overlay swap | item open |
| 6:50 | "13 million km²" | stat chip counts `10 → 13 MILLION KM² / SIBERIA`; chip `> CANADA · USA · CHINA` (typewriter) | — | ramp | | — | quantify + rank |
| 7:00 | "Yakutia alone" | Yakutia fills bright red with a **centred yellow chip** `YAKUTIA · 3.1M KM²` | nested sub-region | push-in | | — | nested scale |
| 7:08 | "India has 1.4 billion people; Yakutia has one million" | **two stat chips at once**: L `1.2 → 1.4 BILLION / INDIA`, R `1 MILLION / YAKUTIA` | dual-stat comparison | — | | — | emptiness |
| 7:17 | **#13** "a big city with no road out" | title swap | fly N to Taymyr | fly-to 2 s | 24 s | overlay swap | item open |
| 7:20 | "Norilsk" | marker (typewriter) + stat chip `175,000 / PEOPLE` | location reveal | push-in | | — | the subject |
| 7:26 | "above the Arctic Circle" | dashed `ARCTIC CIRCLE` line | reference line | — | | — | context |
| 7:28 | "no road, no rail" | **red chip** `NO ROAD · NO RAIL` (typewriter extends from `NO ROAD`) + industrial PiP, then city PiP; cyan river draws | the punchline | — | | — | the fact |
| 7:41 | **#12** "3 in 4 people, 1/4 of the land" | title swap; country red | continental | pull-back | 22 s | overlay swap | item open |
| 7:46 | "three in four Russians live west of the Urals" | west fills **yellow-orange** + yellow chip `3 IN 4 RUSSIANS`; east fills **darker orange** + **red chip** `1 IN 4` | two-region proportional split | fills crossfade, chips typewriter | | — | the fact |
| 7:54 | metro b-roll | PiP card | — | PiP left | | — | texture |
| 8:00 | "Chukotka: 47,000 people" | fly NE; Chukotka fills red; stat chip counts `46,463 → 47,000 / PEOPLE` + town PiP | region zoom | fly-to 2 s | | — | extreme case |
| 8:03 | **#11** "the ground is melting" | title swap; country red | continental | drift | 30 s | overlay swap | item open |
| 8:06 | "two thirds is permafrost" | stat chip `0/3 → 2/3 / OF RUSSIA IS PERMAFROST` | — | ramp | | — | quantify |
| 8:12 | "buildings are sinking" | 3D sticker of a collapsing house on the map | sticker | scale-up | | — | illustrate |
| 8:17 | "the Batagaika crater" | fly to Yakutia; marker; then **deep zoom into raw satellite imagery** (no overlays) | extreme geographic zoom | continuous push 4 s | | — | reveal |
| 8:24 | "about 1 km across and growing" | stat chip `ABOUT 1 KM / ACROSS · AND GROWING` + crater PiP | — | ramp | | — | quantify |
| 8:33 | **#10** "the blast that flattened eighty million trees" | title swap | fly SW to Tunguska | fly-to 2 s | 36 s | overlay swap | item open (longest) |
| 8:40 | "Tunguska, 1908" | marker `TUNGUSKA · 1908`; **3D explosion sticker** blooms on the map | historical marker + sticker | scale-up | | — | the event |
| 8:50 | "80 million trees" | **full-screen B&W archival photo** of flattened forest; stat chip counts `72 → 80 MILLION / TREES FLATTENED` | map leaves | **cross-dissolve 0.5 s** | 12 s | dissolve | historical evidence |
| 9:02 | "2,150 km² — bigger than London" | back to map; stat chip `2,150 KM² / BIGGER THAN LONDON` + small archival PiP | map returns | **cross-dissolve** | | dissolve | scale |
| 9:09 | **#09** "the deepest hole ever dug" | title swap | fly NW to Kola | fly-to 2.5 s | 26 s | overlay swap | item open |
| 9:12 | "the Kola Superdeep Borehole" | marker (long label) + PiP of the welded cap | location reveal | push-in | | — | the subject |
| 9:18 | "12,262 m" | stat chip counts `6,062 → 12,262 M / DEEP` | — | ramp | | — | quantify |
| 9:26 | "3 km deeper than Everest is tall" | **3D geological-core sticker** on the map; stat chip `+3 KM / DEEPER THAN EVEREST IS TALL` | sticker + compare | scale-up | | — | relatable scale |
| 9:35 | **#08** "a land of three hundred volcanoes" | title swap | long fly E to Kamchatka | fly-to 2.5 s | 26 s | overlay swap | item open |
| 9:38 | "three hundred volcanoes" | **orange point cluster** populates down the peninsula; stat chip counts `299 → 300 / VOLCANOES · 29 ACTIVE` | point cluster | staggered pop ~1.5 s | | — | the fact |
| 9:44 | "Klyuchevskaya" | **leader-line PiP** from one dot to a volcano photo | callout | — | | — | detail |
| 9:52 | "an M8.8 in July 2025" | marker `M8.8 · JULY 2025`; **red aftershock dots** populate down the trench | second cluster | staggered pop | | — | the event |
| 10:01 | **#07** "the coldest city on Earth" | title swap | fly W to Yakutsk | fly-to 2 s | 22 s | overlay swap | item open |
| 10:03 | "Yakutsk, −38 in January" | marker; stat chip counts `−37 → −38 °C / JANUARY AVERAGE`; PiP of a stilt building | location + stat | push-in | | — | the fact |
| 10:10 | "buildings stand on stilts" | **3D stilt-building sticker** + second PiP | sticker | scale-up | | — | illustrate |
| 10:23 | **#06** "the coldest village where people actually live" | title swap | small pan E | drift | 22 s | overlay swap | item open |
| 10:26 | "Oymyakon" | marker (typewriter) + "Pole of Cold" PiP | location reveal | push-in | | — | the subject |
| 10:30 | "−67.7 in 1933" | stat chip counts `−60.8 → −67.7 °C / 1933`; marker `VERKHOYANSK` added for the rival claim | two-marker comparison | — | | — | the record |
| 10:38 | boiling-water-toss | 3D sticker + portrait PiP video | sticker + PiP | scale-up | | — | texture |
| 10:45 | **#05** "the last mammoths lived here" | title swap | fly N to the Arctic coast | fly-to 2.5 s | 24 s | overlay swap | item open |
| 10:50 | "Wrangel Island" | marker whose **icon is a mini silhouette of the island**; island outlined | feature reveal | push-in | | — | the subject |
| 10:56 | "4,000 years ago" | stat chip `4,000 YEARS AGO / LAST MAMMOTHS` + mammoth-art PiP | — | ramp | | — | the fact |
| 11:02 | — | **large 3D mammoth sticker** scales up over the island | sticker | scale-up | | — | the image |
| 11:09 | **#04** "one lake, more water than all the Great Lakes" | title swap | fly S to Baikal | fly-to 2.5 s | 24 s | overlay swap | item open |
| 11:12 | "1,642 m deep" | Baikal fills cyan; stat chip counts `1,636 → 1,642 M / DEEPEST LAKE ON EARTH` | water highlight | push-in | | — | quantify |
| 11:16 | "25 million years old" | stat chip `8 → 25 MILLION YEARS / OLDEST LAKE` + lake PiPs (2, crossfaded) | — | ramp | | — | quantify |
| 11:20 | "more water than all five Great Lakes" | **two stat chips**: TR `23,600 KM³ / LAKE BAIKAL`, BR `22,591 KM³ / ALL 5 GREAT LAKES TOGETHER` | dual-stat comparison | — | | — | the payoff |
| 11:26 | "a fifth of Earth's unfrozen fresh surface water" | centred stat chip `1/5` (typewriter sub-line) + ice PiP | — | — | | — | the superlative |
| 11:33 | **#03** "minus 68 and plus 38" | title swap | fly NE to Verkhoyansk | fly-to 2 s | 26 s | overlay swap | item open |
| 11:36 | "−67.8 in Feb 1892" | monument PiP; marker; stat chip `−67.8 °C / FEBRUARY 1892` | location + stat | push-in | | — | the low |
| 11:44 | "+38 in June 2020" | stat chip `+18 → +38 °C / JUNE 2020 · ARCTIC RECORD` | — | ramp | | — | the high |
| 11:48 | "a 106-degree range" | stat chip `68 → 106 °C / BIGGEST RANGE ON EARTH` + winter PiP | — | ramp | | — | the payoff |
| 11:59 | **#02** "eleven time zones" | title swap; country red | pull-back to continental | pull-back 2 s | 20 s | overlay swap | item open |
| 12:02 | "eleven of them" | **yellow dot cluster** populates W→E across the country; stat chip `11 / TIME ZONES`; Kaliningrad PiP | point cluster | staggered pop ~2 s | | — | the fact |
| 12:09 | "midnight in Kaliningrad, 10 a.m. the next day in Kamchatka" | plain white text `12:00 AM` left + yellow chip `10:00 AM · NEXT DAY` right; **two 3D clock stickers** | dual-label comparison | scale-up | | — | the payoff |
| 12:19 | **#01** "3.8 km from America" | title swap | fly E to the Bering Strait | fly-to 2.5 s | 30 s | overlay swap | final item |
| 12:26 | "Big Diomede and Little Diomede" | two markers `BIG DIOMEDE · RUSSIA` / `LITTLE DIOMEDE · USA`; stat chip `3.8 KM / APART` | two-marker comparison | push-in | | — | the fact |
| 12:35 | "the date line runs between them" | **vertical yellow dashed line** draws between the islands; stat chip counts `16 → 21 HOURS / AHEAD`; chips `TOMORROW` (yellow) / `YESTERDAY` (blue) | divide line + zone labels | draw 1.5 s | | — | the payoff |
| 12:45 | "and Alaska was Russian until 1867" | pan E to Alaska; Alaska fills orange; yellow chip `ALASKA · SOLD 1867`; **archival cheque PiP**; stat chip `2¢ / PER ACRE` | historical territory | pan 2 s | | — | kicker |
| 12:49 | **Outro** — "what did we miss?" | map pulls back to the full globe; centred chips `WHAT DID WE MISS? / TELL US IN THE COMMENTS` (typewriter), then `WATCH NEXT → / WHY RUSSIA SOLD ALASKA` | pull-back to globe | continuous pull-back 6 s | 29 s | overlay swap | CTA |

---

## 11. Requirements for Semantic YT Studio

### 1. MUST HAVE — required to reproduce the editing language

1. **Continuous map camera with keyframed fly-to.** A single persistent map view for the whole video,
   driven by a timeline of camera keyframes `(lat, lon, zoom, t, easing)`. Top-down only.
   Moves: `fly_to` (1.5–2.5 s), `push_in`, `pull_back`, plus a **constant idle drift** so the map is never static.
2. **No cuts between map scenes.** Scene changes are overlay-level only. The only base-layer change is
   a 0.4–0.6 s cross-dissolve to/from full-screen media.
3. **Satellite basemap with no native labels**, stylised ocean, white country borders.
4. **Persistent HUD**: title chip + typewriter subtitle chip (top-left), watermark (bottom-right).
5. **Stat chip with number ramping.** Big yellow value + small white sub-line on a dark panel.
   Must support: 4 anchor positions, **two simultaneous chips**, count-up/count-down from a start value,
   and typewriter reveal of the sub-line.
6. **Markers**: geo-anchored dot + typewriter label chip, optional inline value, optional sub-chip,
   and 4 chip colour roles (white/yellow/red/blue).
7. **Region fill**: polygon by country / admin region / custom polygon, with colour tokens and a 0.3–0.5 s fade-in.
   Must support 2–3 simultaneous fills in different colours.
8. **Progressive line draw** with a shared engine for: route (with arrowhead), river, railway,
   border trace, dashed reference line, dashed connector between two markers.
   Head-first draw over 1.5–2.5 s.
9. **PiP card**: rounded photo/video card with white border + shadow, left/right anchor,
   landscape/square/portrait, scale-up-and-fade in/out, and **image carousel** (crossfade between 2–3
   images inside the same frame).
10. **Cross-dissolve to full-screen media** (b-roll / archival photo) with the HUD surviving the
    dissolve and the map returning at the *same* camera position.
11. **Narration-driven timing.** Every overlay event is anchored to a word/phrase in the VO, not to a
    fixed grid. The CSV must carry a time or a VO-anchor per event.
12. **The 5-beat item template** (clear → title → locate → reveal → support → release) as the unit of
    authoring, ~20–30 s.

### 2. SHOULD HAVE — improves similarity

1. **3D sticker layer** — map-anchored cut-out illustrations with scale-up overshoot.
2. **Point cluster** with staggered reveal (30–60 ms stagger) + a counter chip.
3. **Leader line** from a PiP card to a marker.
4. **Zone chips** — labels placed in empty space on either side of a divide line.
5. **Globe mode** for intro/outro, plus an alternate **polar projection**.
6. **Stacked chips** at one marker (two chips vertically, different colours).
7. **Chip auto-placement** that avoids the current subject (the reference moves the stat chip
   left/right/centre depending on where the subject sits).
8. **Centred label chip** inside a filled region.
9. **Marker icon slot** (e.g. a mini silhouette of the island).
10. **Route draw synchronised with a camera pull-back** that fits the route's bounding box.

### 3. OPTIONAL

1. Non-geographic PiP imagery (Pluto, documents) for scale/history comparisons.
2. PiP-over-full-screen-b-roll layering.
3. Deep zoom to raw satellite with all overlays suppressed.
4. Archival B&W full-screen stills.
5. Portrait-orientation PiP cards.
6. Dual 3D stickers side by side (the clock pair).

### 4. DO NOT BUILD — not used by the reference, and would add cost for nothing

1. **Hard cuts / whip-pans / zoom-whoosh transitions** between map shots. There are none.
2. **3D terrain tilt / pitch / bearing rotation.** The camera is strictly top-down and north-up.
3. **Split screens, side-by-side map comparison, map-in-a-corner.** Comparison is done with colour
   fills and dual chips on one full-frame map.
4. **Charts, graphs, bar races, timelines, legends, scale bars, north arrows, graticules.**
5. **Lower-third name bars, bullet lists, on-screen VO subtitles, kinetic paragraph text.**
   All text is chips of ≤ 6 words.
6. ~~**Animated weather/data layers, choropleths, heatmaps, flow particles.**~~ **SUPERSEDED by Reference 2 (§17):** a rainfall colour-ramp overlay, a dot-density layer and streak overlays ARE used. Still not used: animated weather, flow particles.
7. **Street-level / building-level zoom, 3D buildings, Street View.**
8. **Multiple map styles.** One basemap style for the whole video.
9. **Transitional "fly across the globe" sequences between items.** Item changes are overlay swaps;
   the camera move is a plain fly-to under the swap.
10. **Sound-design-driven cutting / beat-synced edits.** Nothing in the picture is music-locked.

---

## FINAL MAP VIDEO SPECIFICATION

### 1. Map scene types
`globe_establish`, `country_canvas`, `location_reveal`, `geo_zoom`, `region_highlight`,
`region_compare`, `marker_compare`, `route_draw`, `river_draw`, `boundary_highlight`,
`feature_outline`, `water_highlight`, `reference_line`, `point_cluster`, `polar_view`,
`scale_compare`, `media_fullscreen`, `outro_cta`.

Added by Reference 2 (§17): `cold_open_stat`, `dot_density`, `value_overlay` (colour-ramp layer), `ghost_shape_compare`, `subregion_set`, `reference_line_connect`, `streak_overlay`.

### 2. Geographic hierarchy
`globe → continental → country → region → local → raw_satellite`.
Continental is home. Descent is always a continuous move, never a cut. Ascent is used to fit routes
and comparisons, and to close an item. Never below ~5 km across. Never tilted.

### 3. Map animation rules
- Idle drift always on, **0.4–0.9 % frame width/s (measured)**. Never fully stops.
- `fly_to`: 1.5–2.5 s, combined pan+zoom, ease-in-out.
- `push_in`: ×1.0 → ×1.25 over 8–15 s.
- `pull_back`: 1.5–2 s, ease-out; used for routes, comparisons and item close.
- Globe rotate: 3–5 °/s, intro/outro only.
- No rotation, tilt, shake, or speed ramps.

### 4. Text / label rules
- All caps, one heavy geometric sans, three sizes only.
- Every string is a **chip** (rounded rect, 10–14 px padding). No naked text except the two time
  labels at 12:09.
- Chip colour = semantic role: white = neutral place, yellow = featured/measured, red = the punchline,
  blue = the comparison entity, black panel + yellow number = statistic.
- Titles ≤ 3 words, subtitles ≤ 8 words, stat sub-lines ≤ 6 words.
- Reveal: **typewriter with a block cursor** for subtitles, marker labels, and chip sub-lines.
  Chips themselves fade/scale in.
- Max simultaneous text objects on screen: **5** (title + subtitle + 1–2 stat chips + 1–2 labels).

### 5. Marker rules
- Ring-dot + label chip, label offset to the side with the most empty space.
- Optional inline value (`· 5,642 M`), optional date (`· 1908`), optional stacked sub-chip.
- Optional custom icon in place of the dot.
- Two markers max per comparison; a dashed connector when the *relation* between them is the fact.
- Lifetime 5–20 s; markers persist across an item, not across items.

### 6. Route rules
- Polyline, head-first draw, **0.90 s measured**, ease-out (immediate start, decelerating finish).
- Types: `flow` (orange + arrowhead), `river` (cyan), `rail` (white), `border_trace` (yellow, follows a
  real boundary), `divide` (yellow, conceptual), `reference` (dashed, e.g. Arctic Circle),
  `connector` (yellow dashed, marker→marker).
- Endpoints get markers; the origin or midpoint gets a label chip after the draw completes.
- A route draw is usually paired with a simultaneous camera pull-back to its bounding box.

### 7. Camera / zoom rules
- One camera for the whole video; every scene is a keyframe on it.
- Zoom levels used: globe, continental (~z3), country (~z3.5), region (~z5), local (~z7), satellite (~z10).
- Transitions between levels: always animated, 1.5–2.5 s.
- The camera continues moving **through** item boundaries and **through** dissolves.

### 8. Duration rules
- Item: 20–30 s (mean 24 s; hard floor 14 s, ceiling 36 s).
- Clear beat between items: **0.50–0.55 s, measured across 7 boundaries — treat as a fixed 0.5 s constant**.
- Stat chip: 3–6 s. Marker: 5–20 s. PiP: 4–8 s. Region fill: 5–25 s. Line: persists to end of beat.
- Full-screen media: 4–12 s, max 3–4 times per 13 minutes.
- Overlay event cadence: one every **3–4 s**; never a gap > 5 s with nothing changing.

### 9. Map → footage transitions
- 0.4–0.6 s **cross-dissolve** only.
- HUD (title + subtitle + watermark) stays on through the dissolve; the stat chip fades out just before.
- Triggered only by a sustained sensory/narrative passage (> 6 s) with no new geographic information.

### 10. Footage → map transitions
- 0.4–0.6 s **cross-dissolve** back.
- The map resumes at the **same camera position and the same overlay state** it left (any route stays drawn).
- A PiP card may be introduced *over* the footage first, so it is already on screen when the map returns.

### 11. Narration → map triggering rules
| Trigger in VO | Emitted visual |
| --- | --- |
| new countdown item | clear → title chip + typewriter subtitle |
| place name | `fly_to` + marker + typewriter label |
| number / measurement | stat chip with number ramp |
| comparison of two things | two fills or two markers in different colour roles + (often) two stat chips |
| movement / flow / journey | route draw + synchronised pull-back |
| boundary / division | border trace or divide line + zone chips on both sides |
| area / proportion | region fill in secondary colour |
| scale ("as big as…") | pull-back, or a non-geographic PiP |
| sensory description | PiP photo; if > 6 s, cross-dissolve to full-screen b-roll |
| historical event | marker with year + archival media + optional 3D sticker |
| count of things | point cluster + counter chip |
| the punchline of the fact | the relevant chip turns **red** |
| no geographic content | nothing new; idle drift carries the gap |

### 12. Required CSV representation
One row per **visual event**, grouped by item. Suggested columns:

```
item_no, beat, t_start, t_end, vo_anchor,
scene_type, camera_action, lat, lon, zoom, easing, camera_dur,
layer_type,            # title | stat | marker | fill | line | pip | sticker | cluster | media
layer_id, layer_action,# in | out | update
geo_ref,               # ISO code / admin id / named feature / polygon id / polyline id
label_text, sub_text,
color_role,            # neutral | featured | subject | compare | stat
value_from, value_to, value_format,   # for number ramps
anchor,                # tl | tr | bl | br | center | map:<lat,lon>
asset_path, asset_kind,# photo | video | archival | illustration | sticker
reveal,                # typewriter | fade | scale | draw | stagger
in_dur, hold, out_dur,
notes
```

Rules the CSV must enforce: one `title` row per item; a mandatory `clear` row at each item boundary;
`t_start` monotonic within an item; at most 2 concurrent `stat` rows; at most 5 concurrent text layers.

### 13. Renderer requirements
1. A **single long-lived map instance** with a camera timeline — not per-scene map instances.
2. Deterministic frame-accurate rendering (seek to frame *n*, render, repeat) so the camera,
   draws and ramps are reproducible.
3. Vector overlay layer composited over the map raster: polygons, polylines with animated
   `stroke-dashoffset`, dots, chips with measured text for auto-sizing.
4. A text-metrics pass so chips size to their content and the typewriter reveals by clipping, not by
   re-layout (the reference's chips do not reflow while typing).
5. Number formatter supporting `12.6M`, `17,700`, `−67.7 °C`, `1/5`, `2¢`, `9,300 KM`, `M8.8`.
6. Asset pipeline for PiP media (photo, video, PNG sticker with alpha) with rounded-corner + border +
   shadow treatment and a built-in crossfade carousel.
7. A dissolve compositor for the base layer (map ⇄ full-screen media) that keeps the HUD above it.
8. Collision-aware placement for chips and marker labels (keep off the subject, keep inside safe margins).
9. Easing library: ease-in-out cubic for camera, ease-out for draws and chip entries, linear for typewriter.
10. Caching of basemap tiles for the fixed camera path so renders are repeatable.

### 14. What must remain unchanged in Semantic YT Studio
- **Map Facts** — a *separate niche* that stays exactly as it is. Its basemap (NASA Blue Marble),
  opaque polygon fills, hard cuts, footage-led ratio, naked-text labels and glitch transitions are
  that niche's identity, not defects to fix. pakMap does not inherit from it and does not modify it.
- **Overscaled**, **Exp Solar**, **Flow** — untouched: CSV formats, skills, rendering rules.
- **The existing renderer** — pakMap registers as an additional, independent visual system. No changes
  to shared easing, compositing, or CSV parsing that existing formats depend on.
- **No architecture rewrite.** pakMap's two new needs — a persistent map camera and a vector overlay
  layer — are additive modules that live only in the pakMap path.

---

## 15. pakMap as a new niche — what "100 % of the reference" actually requires

Because pakMap is greenfield and additive, **the entire editing language in sections 1–13 is
reproducible.** Nothing in the existing tool constrains it. The engineering is ordinary 2D overlay
work plus one camera timeline.

Three things gate literal 100 %, and **none of them is a coding problem.**

### Gate 1 — Basemap imagery (the only hard one)
The reference is Google Earth imagery on a **3D globe with a perspective camera**, with **ocean
bathymetry** and an atmosphere limb. Three consequences:
- Country silhouettes are globe-projected, not Web Mercator. At continental framing this visibly
  changes every shape on screen.
- The ocean carries shelf/trench/ridge detail, so it reads as terrain rather than a flat backdrop.
- Imagery resolution must support continuous zoom from globe down to ~5 km across.

Options:
| Source | Globe | Bathymetry | Zoom depth | Commercial use |
| --- | --- | --- | --- | --- |
| Google Earth Studio | yes | yes | yes | restricted; manual, not API-driven |
| Cesium + Bing/Maxar | yes | partial | yes | licensable |
| Mapbox Satellite | flat (globe mode available) | no | yes | licensable |
| Esri World Imagery | flat | no | yes | licensable |
| Sentinel-2 / NASA GIBS | flat | no | medium | free |

**UPDATE (see §18): the decision is a FREE stack, not a licensed layer.** Original recommendation, kept for history: a globe-capable renderer (Cesium, or Mapbox globe projection) + a licensed
high-zoom imagery layer + a **separately composited bathymetry layer** (GEBCO) to recover the ocean
look. This gets ~95 % of the reference's map appearance without Google's licensing exposure.

### Gate 2 — 3D stickers
Mammoth, clock pair, exploding fireball, geological core, stilt building, sinking house, waterfall
slab, hiker. These are bespoke 3D renders chosen per fact and cannot be generated from a CSV row.
Requires a curated library; coverage will be partial. The reference uses ~10 across 30 items, so
roughly one every third item — a library of 60–80 generic ones covers most geography/nature/weather
/history beats.

### Gate 3 — Placement judgment
The reference moves the stat chip left/right/centre per shot to avoid the subject, and routes PiP
leader lines by eye. Collision-aware auto-placement gets most of the way; expect occasional
overlaps that a human would have caught.

### Everything else is buildable to 100 %
Chips, typewriter reveals, number ramping, markers with sub-chips, translucent region tints,
progressive line draws, PiP cards with carousels, point clusters, cross-dissolves, the colour-role
system, the 5-beat item template, the 20–30 s cadence, zero hard cuts, the persistent HUD.

### Build order for the new niche
1. Persistent map camera + keyframe timeline (globe, continuous, no cuts).
2. Basemap stack: imagery + bathymetry + admin hairlines + subject stroke with drop shadow.
3. Translucent region tint system with the colour-role tokens.
4. Chip engine: title, subtitle, stat, marker, zone — with typewriter and number ramping.
5. Line-draw engine (route / river / rail / border / divide / reference / connector).
6. PiP card system with carousel and leader lines.
7. Cross-dissolve compositor for full-screen media, HUD above it.
8. CSV schema (section 12) + narration word-anchoring.
9. Sticker and point-cluster layers.
10. Collision-aware placement pass.

---

*Specification derived entirely from frame-level analysis of `Pakmap.mov`. No implementation performed.*

---

## 16. MEASUREMENT PASS 2 — instrumented findings

Method: pixel measurement on full-resolution PNG frames; FFT phase-correlation camera tracking on
960×540 grayscale at 30 fps with 1.0 s frame gaps; STFT (1024/256 @ 48 kHz) spectral-flux onset
detection on the audio. Every number below is **OBSERVED** unless marked otherwise.

### 16.1 Typography — measured geometry (1920×1080)

| Element | Measured |
| --- | --- |
| Title chip height | **66–67 px** (stable across 8 sampled frames) |
| Title chip left edge | x = **44–46 px** from frame edge |
| Title chip top edge | y = **37 px** |
| Title cap height | **32–33 px** |
| Title padding | L **18–20 px**, T **15–16 px**, B **19 px** |
| Title chip width | **301–334 px** — content-driven, not fixed |
| Subtitle chip height | **39 px** (single line) |
| Subtitle cap height | **15 px** |
| Subtitle padding | L **14–17 px**, T **12 px**, B **12 px** |
| Gap, title bottom → subtitle top | **9 px** |
| Subtitle line spacing (2-line) | ≈ **27–28 px** baseline-to-baseline |
| Stat number cap height | **76 px** |
| Stat chip panel height | ≈ **116 px** single-line, up to ~171 px with sub-label |
| Stat chip right margin | ≈ **71 px** |
| Stat chip bottom margin | ≈ **51 px** |
| Title chip corner radius | ≈ **8–10 px** (small) |
| Stat chip corner radius | ≈ **24–28 px** (large) |

Title chip ratio: cap height is **~0.49 × chip height**. Subtitle: **~0.38 ×**.
Stat number is **~2.3 ×** title cap height and **~5 ×** subtitle cap height.

### 16.2 Colour tokens — measured medians

| Token | Hex | RGB | n sampled |
| --- | --- | --- | --- |
| Brand yellow | **#FBE040** (range #FADF43–#FDE23F) | 251, 224, 64 | 18 323 px |
| Subject red | **#DF2721** | 223, 39, 33 | 9 830 px |
| Panel dark | **#081320** | 8, 19, 32 | 194 832 px |
| Title chip white | **#FFFFFF** | 255, 255, 255 | — |
| Compare blue | UNKNOWN — not isolated in sampled frames | | |

### 16.3 Typeface — characteristics only

Geometric sans, **ExtraBold/Black** weight, ALL CAPS throughout, near-circular `O`, monolinear
strokes, no spur on `G`, flat-terminal `1`, open-aperture `4`. Title tracking appears slightly
**tight**; subtitle and stat sub-label tracking appears slightly **loose**.
Consistent with the Poppins ExtraBold / Montserrat ExtraBold family.
**Exact font: UNKNOWN** — not identifiable from raster evidence at this resolution.

### 16.4 Sound effects — definitive null result

Spectral-flux onset detection in the 6–16 kHz band found 160 transients above the 99.85th percentile
in 798 s. Discrimination:

- **145** had strong concurrent voice energy → speech sibilance.
- **15** occurred in a quiet context, but **14 of those were followed within 60–400 ms by strong
  voice energy** (1.6–5.8 × reference) → sentence-initial fricatives/plosives.
- Decay times of all candidates were **11–37 ms**, consistent with speech, not with a designed
  whoosh or impact (200–600 ms).
- **1 residual candidate: t = 135.84 s.** Weak (6 × HF, 11 ms decay). Most likely a mouth click,
  breath, or edit artefact. Classified **UNKNOWN**, not an SFX.

Hypothesis-driven test at measured visual-event times, against 4 000 random control times:

| Event class | n | HF energy (mean) | Control mean | % above control p90 |
| --- | --- | --- | --- | --- |
| Item boundary (title chip in) | 30 | **9.62** | 11.52 | **7 %** (chance = 10 %) |
| PiP entry (291.60 s) | 1 | **1.28** | 11.52 | 0 % |
| Sticker entry (662.15 s) | 1 | **8.18** | 11.52 | 0 % |
| Dissolve to full-screen footage | 3 | **11.28** | 11.52 | 0 % |

At every event class the audio energy is **at or below** the random-time baseline.

**OBSERVED: the reference contains no sound effects of any kind.** No whooshes, no UI ticks, no
typewriter clicks, no counter ticks, no impacts, no transition stingers. The mix is narration plus a
continuous sub-audible bed (−40 to −45 dB, never reaching true silence), integrated **−15.8 LUFS**,
loudness range **4.1 LU**.

This supersedes the earlier hedge that SFX were "likely absent but unverified."

### 16.5 Camera — measured motion

Phase correlation, 1.0 s frame gaps, 960-px-wide frames:

| Window | Context | Pan | Zoom |
| --- | --- | --- | --- |
| t = 100–104 | mid-item hold | **4.1 px/s (0.43 %/s)** | ~0 |
| t = 292–296 | PiP card on screen | **8.7 px/s (0.91 %/s)** | ~0 |
| t = 662–666 | 3D sticker on screen | **9.0 px/s (0.94 %/s)** | ~0 |
| t = 28–34 | item boundary | **4.6 px/s (0.48 %/s)** | ~0 |
| t = 104–109 | fly-to (Mont Blanc → Elbrus) | **32.9 px/s (3.4 %/s)** | peaks **−34 %/s** |
| t = 299–304 | pull-back during route draw | 4.0 px/s | peaks **+27 %/s** |
| t = 740–745 | final-item move | **31.6 px/s (3.3 %/s)** | peaks **−38 %/s** |

**Findings:**
1. The camera **never stops** — the floor is ~0.43 %/s, never 0.
2. Drift is **0.4–0.9 %/s**, roughly **half** the rate previously assumed.
3. Active moves run at **3.3–3.4 %/s pan**, i.e. **~7× the drift rate**. Two discrete speeds, not a
   continuum. (INFERRED from 3 move samples.)
4. Instantaneous zoom during a move peaks at **30–38 %/s**.
5. **The camera does not pause for PiP cards or stickers** — drift during both is at or above the
   mid-item baseline. Rich media does not freeze the frame.
6. Motion is **geographically anchored**: PiP cards and stickers translate with the map rather than
   holding screen position.

### 16.6 Route draw — measured

Gulf Stream polyline, orange-pixel count per frame at 30 fps:

- Draw begins **t = 298.20 s**, reaches 100 % at **t = 299.10 s**.
- **Duration = 0.90 s.**
- Growth per frame: 8.5 % on frame 1, decaying to ~1 % by the end → **ease-out with no ease-in**.
  The line is already 8.5 % drawn on its first visible frame.

This supersedes the earlier 1.5–2.5 s estimate, which was inferred from 0.5 s sampling.

### 16.7 Synchronisation — measured, and consistent

Title-chip OFF → ON transition, sampled at 20 fps across 7 clean item boundaries:

| Boundary | Chip OFF | Chip ON | Gap |
| --- | --- | --- | --- |
| ~51 s | 51.75 | 52.25 | **0.50 s** |
| ~97 s | 95.60 | 96.15 | **0.55 s** |
| ~141 s | 141.85 | 142.35 | **0.50 s** |
| ~189 s | 190.10 | 190.65 | **0.55 s** |
| ~259 s | 260.30 | 260.85 | **0.55 s** |
| ~407 s | 408.45 | 408.95 | **0.50 s** |
| ~645 s | 645.60 | 646.15 | **0.55 s** |

Mean **0.527 s**, spread **0.05 s** — one sample bin. **The clear beat is a fixed 0.5 s constant.**

Title chip ON vs the next narration onset:

| Chip ON | Narration onset | Offset |
| --- | --- | --- |
| 29.30 | 29.41 | **+0.11 s** |
| 96.15 | 96.42 | **+0.27 s** |
| 190.65 | 190.75 | **+0.10 s** |
| 260.85 | 261.02 | **+0.17 s** |
| 408.95 | 409.04 | **+0.09 s** |
| 646.15 | 646.37 | **+0.22 s** |
| 52.25 | 53.40 | +1.15 s (outlier) |
| 142.35 | 143.62 | +1.27 s (outlier) |

Median of the 6 consistent cases: **+0.14 s**.
**The title chip lands 0.10–0.25 s BEFORE the narrator begins the item's first sentence.**
The two outliers are likely detector error (second word caught) rather than a different rule —
classified **INFERRED**.

### 16.8 Still UNKNOWN after this pass

- Exact typeface name.
- Compare-blue hex.
- Typewriter character rate — the measurement band picked up map luminance; needs an isolated crop.
- Whether the typewriter reveals per character or per word.
- Region-fill duration and easing — the colour threshold could not separate the fill animation from
  concurrent camera zoom.
- Marker-dot entry animation (pop scale, overshoot) — not yet isolated.
- Point-cluster stagger interval.
- Max simultaneous overlay counts — estimated, not counted frame by frame.
- Full narration transcript — no ASR available in this environment.


---

## 17. REFERENCE 2 — `2nd reference.mov` (Kenya, 193.7 s)

Method: frames at 1/4 s, 1/5 s and 1/10 s intervals, scene-change detection, audio level check.
Same channel (`EXPLAINS-IT` watermark), same engine of ideas, different video structure.

### 17.1 What it confirms from Reference 1
- One full-frame satellite map, always moving; scene-change detection finds **no hard cuts**.
- Stat chips (yellow value + small white sub-line on dark panel), marker chips with value, PiP photo cards with white border, full-screen footage interludes, translucent region fills with white outlines, dashed reference line, all-caps heavy sans.

### 17.2 What it adds or CHANGES (overrides Reference 1 where they differ)

| # | Finding | Overrides / adds |
|---|---|---|
| 1 | **Structure is `PART n`, not `NUMBER nn`.** Top-left chip reads `PART 1` with subtitle `THE EMPTY HALF`, later `PART 2` / `THE EQUATOR PARADOX`. | The top-left chip text and subtitle are *authored*, not always a countdown number. |
| 2 | **Cold open with no HUD.** The first ≈ 54 s has no title/subtitle chip at all — only stat chips and markers (`47 MILLION PEOPLE`, `1.4 MILLION PEOPLE`, counters `354× → 445× SMALLER`). `PART 1` appears at ≈ 56 s; `PART 2` at ≈ 136 s. | The HUD is not "present ~96 % of runtime" in every video. It is **optional and can start late**. |
| 3 | **Dot-density layer.** Thousands of small yellow dots (≈ 2–4 px) revealed over the country: dense in the south-west/Nairobi, near-empty in the north. Used twice with the stat chip changing underneath (`54% OF THE LAND`, `14 / KM²`, `1,815+ / KM²`, `540 / KM²`). | New `dot_density` layer; far larger than Reference 1's 11–300 dot clusters. Needs point data (population grid / settlements), not hand-placed dots. |
| 4 | **Value-overlay (colour ramp) layer.** A rainfall layer in green → yellow → orange over Kenya with a stat chip `UP TO 2,000 MM`; the chip counts (`1,997 → 2,000`). No legend, no scale bar. | Overrides "DO NOT BUILD #6 (heatmaps/choropleths)". Needs a raster/colour-ramp source and a way to make the ramp from data. |
| 5 | **Ghost-shape comparison.** A foreign country (Poland) is placed on a *different region of the map* as a translucent blue silhouette at true scale beside a stat chip (`312,700 KM²`, later `253,621 KM²` / `POLAND · NORTHERN KENYA 313,100 KM²`). | New `ghost_shape_compare`; needs country polygons moved and kept at true scale. |
| 6 | **Sub-region set.** Several counties filled in different token colours at once (orange / yellow / purple / red / teal), each with a white label chip (`TURKANA`, `MARSABIT`, `WAJIR`, `MANDERA`, `SAMBURU`, `ISIOLO`), plus a **row of small labelled photo cards along the bottom** (one per county, yellow label under each), growing from 3 to 7 cards. | PiP is not only one big card; it can be a **filmstrip of 3–7 small cards**. More than 2–3 simultaneous fills are used. |
| 7 | **Single hero fill with hard stat.** The 54 %-of-Kenya region is filled solid red with chip `54% OF KENYA / BUT 9% OF ITS PEOPLE`; a single county is orange with `POPULATION: 0` large and a pulse ring at the centre. | Colour roles hold: red = punchline, orange = sub-region. |
| 8 | **Marker chips with values and no connector.** `NAIROBI · 4.4 MILLION`, `LODWAR · 83,000`, `GARISSA · 163,000`, `CHALBI DESERT` (dot + small chip, no leader line). | Confirms Reference 1 marker rules; markers can persist across several seconds while the stat chip changes. |
| 9 | **Equator / reference line with connect.** A dashed yellow line along the equator with chip `THE EQUATOR`; it then extends across the Atlantic to markers `CONGO RAINFOREST` and `AMAZON RAINFOREST`, each with a PiP (satellite-style rainforest thumbnail). | `reference_line` can span the globe and link two distant markers; the camera pulls back to show both. |
| 10 | **Streak overlay.** White diagonal streaks sweep across the country under a caption chip `SOMETHING YOU CAN'T SEE` (illustrates wind/airflow or an invisible force). | New `streak_overlay`; a drawn line family without a geo path (decorative). |
| 11 | **Caption-style chip.** Wide dark chip with yellow all-caps text and no number, bottom-left or bottom-centre: `SOMETHING YOU CAN'T SEE`, `THE LOWEST-LATITUDE DESERT ON EARTH` (2 lines) with a tiny **source credit** line `MUNDAY ET AL. 2022`. | New chip type: caption chip + source line. Sources are cited on screen. |
| 12 | **Archival black-and-white PiP** labelled `HISTORY`, plus a city skyline PiP labelled `POLAND`. PiP cards can carry a small yellow label chip at the bottom edge. | PiP label chip. |
| 13 | **Full-screen footage uses**: 3 interludes (road/plain drone shots, arid landscape) with the stat chip still on top (`6 / KM²`, `< 163 MM`, `POPULATION: 0`), no HUD loss; the footage returns to the map with the same overlays. | Confirms Reference 1 §9. Stat chips may stay over footage. |
| 14 | **Globe appears mid-video.** A 3D globe shot (Africa/Europe/South America) occurs once at ≈ 148 s when connecting Kenya to the Amazon. | Overrides "never re-establishes with a globe mid-video" (Reference 1 §8): a globe shot can be used as a bridge to a distant place. |
| 15 | **Stat chip positions.** Bottom-left, bottom-right, top-right, and *bottom-centre over footage*. Number size is large (≈ 2× the Reference 1 sub-line) and counters are frequent (`354× → 445×`, `1,815+`, `1,997 → 2,000`). | Confirms placement is per-shot. |
| 16 | **The `PART` chip looks smaller than the `NUMBER` chip** in the thumbnails, but this is NOT measured at full resolution. | Measure before locking `pakmap.json` (see 17.4). |

### 17.3 Audio
The audio stream of Reference 2 is **digital silence** (mean and max −91 dB, LUFS −70). It carries no evidence either way. **The only audio evidence remains Reference 1: narration plus a faint bed, no designed sound effects.** Treat sound design for pakMap as "none" unless a third reference with audio says otherwise.

### 17.4 Still UNKNOWN after Reference 2
- Full-resolution geometry of the `PART` chip and caption chip (not measured).
- Source of the dot data and rainfall layer (assumed population-grid and climate-raster data; not identifiable from pixels).
- Dot reveal stagger and total count.
- Streak overlay timing and curve shape.
- Whether the part chip swaps with the same 0.5 s clear beat (only two chip states are visible; not enough boundaries to measure).
- Narration (silent track; no script supplied).

### 17.5 Changes to the requirement lists (§11)
**MUST HAVE — add**
13. Authored HUD text: chip text and subtitle are free text, and the HUD may be **absent** (cold open) or start mid-video.
14. Caption chip (text only) with an optional tiny source line.
15. Filmstrip PiP: 3–7 small labelled photo cards along one edge, each with a yellow label chip.

**SHOULD HAVE — add**
11. `dot_density` layer driven by point data, with a counter chip underneath.
12. `value_overlay` colour-ramp layer (rainfall-style) with a counting chip, no legend.
13. `ghost_shape_compare` — move a country polygon onto another area at true scale.
14. Reference line that spans oceans and links two distant markers, with a camera pull-back / globe bridge.
15. Pulse ring on a marker or region centre.
16. Streak overlay (decorative drawn lines) for "invisible force" beats.

**DO NOT BUILD — remove**
- "Animated weather/data layers, choropleths, heatmaps": only *animated weather* and *flow particles* stay excluded.
- "Never a globe mid-video": allowed as a bridge shot.


---

## 18. IMAGERY STACK — decision: free sources

> **Partly superseded by §20 (Phase 0 look test and licence check):** the EOX Sentinel-2 row below is NOT cleared for commercial use, and the stack is now NASA-first.

Supersedes the "licensed imagery" recommendation in §15 Gate 1.

### 18.1 Requirement (from both references)
- Satellite look: dark teal ocean with seafloor detail, white country borders, no basemap text.
- Zoom range: globe, continental, country, region (Reference 2 stays here), local. Reference 1 has one raw-satellite shot about 5 km across.

### 18.2 Stack
| Layer | Source | Licence notes |
|---|---|---|
| Global base | NASA GIBS (Blue Marble, MODIS/VIIRS true colour about 250 m) | Free, no key; attribution expected |
| Regional / country zoom | Sentinel-2 cloudless mosaic by EOX, 10 m | 2016 edition CC BY 4.0; later editions non-commercial. Use 2016 and re-check terms |
| Ocean | GEBCO or NOAA ETOPO bathymetry rendered as shaded relief | Free, attribution |
| Borders / sub-regions | Natural Earth (public domain), geoBoundaries (counties) | Avoid GADM |
| Globe | MapLibre built-in globe projection | Free |
| Look | Colour grade in the renderer (darker teal ocean, contrast, white borders) | n/a |

Do not use: Google, Bing, Mapbox satellite, Esri World Imagery.

### 18.3 Known limits
- Sentinel-2 (10 m) goes soft below about a 20 km frame width; the Batagaika-style 5 km shot is optional or capped.
- Ocean detail is slightly less rich than the reference's.
- Imagery cannot reproduce the reference's atmosphere limb exactly; globe shots use MapLibre's globe rendering.

### 18.4 Delivery
Tiles are not bundled. They download on first use into the existing cache and are reused on repeat renders. Credits go in the video description or an end-card according to each licence.

### 18.5 Where it lands in the plan
Phase 0: look test and licence check. Phase 1: tile sources, cache, bathymetry shading, grade. Phase 8: optional licensed-key setting.

### 18.6 Still UNKNOWN
- Exact current terms of each source (verify before shipping).
- Whether the look test passes against the references at the zoom levels used.


---

## 19. DECISIONS RECORDED

| Decision | Choice |
|---|---|
| Imagery | Free stack (§18) |
| Data layers (dots, colour ramp, comparison shapes) | Bundled open datasets plus user files. Small coarse data ships with the app; large grids download on demand into the cache; user files override; a missing layer is a visible error, never a silent drop. Candidates: WorldPop/GHSL (population), CHELSA/CHIRPS (rainfall), Natural Earth/geoBoundaries (boundaries). Licences verified in Phase 0. |
| 3D stickers | Layer built, no library in v1 |
| Typeface | Montserrat ExtraBold |
| Sound design | None (§16.4, §17.3) |
| Existing niches | Map Facts, Overscaled, Exp Solar, Flow untouched (§14) |


---

## 20. PHASE 0 RESULTS (summary; full detail in `phase0/phase0-report.md`)

- **Imagery (supersedes §18.2):** NASA GIBS Blue Marble + Bathymetry for global/country/ocean, NASA Landsat WELD for close zoom. EOX Sentinel-2 cloudless is NOT cleared for commercial use (current EOX terms conflict with an older CC BY-SA statement); the earlier claim that the 2016 edition is CC BY 4.0 was wrong. MODIS/VIIRS daily imagery rejected (clouds).
- **Chip geometry:** `PART n` chip is identical to the `NUMBER nn` chip: 67 px high at x=45, y=37, radius about 10 px; subtitle chip 39 px high at y=112, 9 px below.
- **Subtitle reveal (corrects §2 table and §16.8):** measured on Reference 2 as word-by-word at about 0.067 s per word, after the chip grows (about 0.27 s) and the title chip pops (about 0.07 s). The "typewriter with block cursor" claim for Reference 1 is unconfirmed.
- **Dot-density reveal:** about 3.1 s, linear, about 6 px yellow dots, starting at 3.8 s in Reference 2.
- **Colours:** compare-blue chip `#2978D8`; yellow stat number `#FDE23E` / `#FBE040`.
- **Typeface:** visually matches Montserrat ExtraBold; not identified from pixels.
- **Cold open:** Reference 2 shows no HUD for its first 57 s.
- **Constants and CSV contract:** `phase0/pakmap.draft.json`, `phase0/csv-schema.md`.

- **Correction to §20 / the Phase 0 look test:** the "about 20 km local frame" comparison was really a ~290 km frame (zoom 10 on 256 px tiles), so Landsat's close-zoom quality was not tested there. The "soft below ~25 km" figure is an estimate from native resolution (Landsat is 1:1 at ~73 km frames and ~2.9x stretched at 25 km). Phase 1 measures it with a real narrow shot.
- **Imagery selection is scale-based (decision, Phase 1):** no rule ties a source to "country" or "close-up". Each provider declares its native resolution; the layer that is stretched past `max_upsample` hands over to the next finer one with a crossfade. `soft_limit_frame_km` (25) is a configurable warning, not a hard stop.


---

## 21. PHASE 2 MEASUREMENTS (Reference 2, full resolution)

- **Marker label**: white text on a dark translucent chip, 52 px high, 34 px font (24 px caps), chip starts 27 px right of the dot centre; ring dot 13 px radius, white ring, dark centre. White chips with dark text are for zone/county labels.
- **Caption chip**: 63 px text (44 px caps), chip 108 px high (32 px above and below the caps), yellow text on the dark panel, 66 px above the bottom edge; optional tiny source line (about 13 px).
- **Stat chip (with sub-line)**: 156 px high, 63 px from the right edge, 66 px from the bottom, 60 px number caps, radius about 26 px.
- **Subtitle reveal**: word by word at about 0.067 s per word, after the chip grows (0.27 s); title chip pops in about 0.17 s after the subtitle chip starts.


---

## 22. PHASE 3 RESULTS (summary; detail in `phase3/phase3-report.md`)

- Data layers built: `value_overlay` (colour ramp from a grid, clipped to a country), `dots` from data, `ghost_shape` (true-size outline moved elsewhere), `streak`.
- Bundled data (1.6 MB): CHIRPS 2016-2020 mean annual rainfall at 0.1 degree (public domain) and Natural Earth populated places (public domain). User GeoTIFF / ASCII grid / CSV files override them by being named.
- Missing or non-covering data is an error that names the layer and what to supply.
- Bundled dot maps are an approximation (generated around real towns); the reference's dot map is a real population surface. Supply a grid or point file for exact distributions.


---

## 23. PHASE 4 RESULTS (summary; detail in `phase4/phase4-report.md`)

- **Filmstrip geometry (Reference 2, measured):** cards 419 x 303 with 3 cards and 240 x 168 on a 255 px pitch with 6 cards; white border about 5 px, corner radius about 16 px, soft shadow; yellow label chip 42 px high, 6 px under the card, black 28 px text; the 6-card strip starts near x=76, the 3-card strip is centred.
- **Zone labels** (county names on their regions) are chips with no dot, white with dark text by default, yellow for the featured one; 52 px high.
- **Stat chips are positioned per shot** (for example top-right at y=171); the engine offers anchors plus an explicit position.
- **Built:** `pip` (with crossfade, label, leader line), `filmstrip`, `sticker`, `media_full` (linear dissolve, camera held still), zone labels. One rich picture at a time (sticker vs cards), one interlude at a time.


---

## 24. PHASE 5 RESULTS (summary; detail in `phase5/phase5-report.md`, author guide in `csv-reference.md`)

- The CSV schema in §12 / `phase0/csv-schema.md` is now implemented as `pakmap/` (Python): columns `item_no, vo_anchor, offset_s, t_start, t_end, hold, layer_type, layer_id, layer_action, camera_action, camera_dur, lat, lon, zoom, frame, easing, geo_ref, line_kind, label_text, sub_text, color_role, value_from, value_to, value_format, anchor, asset_path, data_source, params, notes`.
- Timing rules implemented from the measurements: title 0.14 s before its words, fixed 0.5 s clear beat, last item to the end of the narration, default hold times per layer.
- Added to the engine: `fill` events (country or inline polygons), a city name index, and a validator tool the compiler calls.


---

## 25. PHASE 6 RESULTS (summary; detail in `phase6/phase6-report.md`)

- pakMap is a third video style in the app (Visual Director page): CSV picker, channel name, Check plan, and the shared Generate/Stop button. The result is the engine's silent map video plus the narration, exported through the existing renderer and validated.
- Real Whisper output differs from typed scripts: numbers appear as digits ("250", "2,000"), names can be split or misheard. The anchor matcher handles spoken numbers and split names, and reports what was actually heard when it cannot match.
- Credits (NASA acknowledgement, Landsat "historical" note, dataset credits) are written next to every video.
