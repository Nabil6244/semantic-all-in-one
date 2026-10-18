# What If: how the reference videos use graphics, and where #016 falls short

Analysed 2026-10-17 from 481 frames of the four references (V1 Venus, V2 Speed of Light, V3 One Light-Year every 4 s, V4 Black Hole)
and 134 frames of render #016 (Voyager 1). Side by side: `analysis/ref_vs_016.jpg`. Measured: near-empty frames are 1 % in V3 and
31 % in #016; centre detail (median) is 15.1 in V3 and 4.0 in #016.

## The reference's rules

### 1. One continuous world, never a slide
- The background in almost every frame is the real sky (a Milky Way photograph, ESO/S. Brunier) or the planet's own air (V1 Venus).
  Diagrams are drawn **into that world**: the solar system's orbits from above, Voyager's gold path, the Sun's bubble as a glowing
  cyan shell. There is no blank "diagram plate" with a heading at the top.
- A composition evolves inside one shot for 8 to 20 s (a line draws, a number lands, a label appears). V3 has about 5 hard cuts a
  minute but something changes every ~5 s.

### 2. A recurring hero with "YOU · ON BOARD"
- The Voyager 3D model comes back again and again, always with a thin ring marker and "YOU / ON BOARD". The viewer is the traveller.
  The model is lit, with the sky behind it, placed right of centre, leaving the left third for type.

### 3. The type system (the core of the look)
Every few seconds the same three-part block, in the left third, about 30 to 60 % down:
1. **Kicker**: cyan (#3FD0E8), small letter-spaced caps, 1 or 2 lines ("ALL SIX COMPUTERS TOGETHER / HOLD ABOUT").
2. **Headline or number**: huge heavy white display type, 6 to 10 % of the frame height ("70", "VOYAGER 1", "11 HOURS").
3. **Sub-line**: small caps, gold or white ("KILOBYTES", "THE SIZE OF A SMALL CAR").
Often followed by one comparison ("ONE PHOTO ON YOUR PHONE · A FEW THOUSAND KB") with a small bar.

### 4. Numbers are the hero, and each one gets a picture
"70 KILOBYTES" + a bar against a phone photo; "160 BITS PER SECOND" + a live bit stream; "ABOUT 4 WATTS A YEAR" + 45 bars from
470 W to 2022; "365 LIGHT-DAYS" + a waffle of 365 cells; "INSTRUMENTS STILL ON 8 → 5 → 2 OF 10" + a grid of 10 lamps going dark
with a year scrubber. The graphic fills 50 to 70 % of the frame.

### 5. Instruments that persist
- A small top-left light clock (time + year + age) for the whole act, counting at each beat. At key beats it grows into a large
  centred dial ("ONE LIGHT-DAY / 25,902,068,371 KM"). V1: a survival clock top-left and an altitude rail on the right edge.
  V4: a mission card top-right.
- Dates top-right in mono with a thin underline ("CLOSEST TO JUPITER · 5 MARCH 1979").

### 6. Real photos are cards, annotated
A real image sits in a framed card on the right half, text on the left. A thin ring + leader line + label points at the thing
("THE PLUME"). People appear only as a named lockup ("LINDA MORABITO · JPL NAVIGATION ENGINEER · 9 MARCH 1979").

### 7. Restraint
Near black + the real sky; cyan for labels and structure; amber/gold for paths, time and values; white for headlines; red only for
failure ("ONE CHIP HAS DIED"). A citation line at the bottom left of every frame (REAL IMAGE / ILLUSTRATION / DIAGRAM / COMPUTED).

## #016 against each rule

| Rule | Reference | #016 | Cause in the app |
|---|---|---|---|
| 1 World | sky everywhere; diagrams in the scene | flat navy plates with a small heading at the top centre ("TWO ROUTES COMPARED"), 28 of them near-empty | plates are their own screens (`drawPlate` title); diagram rows dropped |
| 1 Builds | one composition evolves 8-20 s | a hard cut every ~6 s, little change inside a shot | planner cuts per CSV row; templates are short (5-6 s) |
| 2 Hero | Voyager + "YOU · ON BOARD", recurring | Voyager model alone on black, no marker | no "you" marker layer on craft shots |
| 3 Type | kicker + huge number + sub, left third, every few s | headings tiny; lockups are shot directions ("VOYAGER 1 DRIFTING IN DEEP SPACE") | CSV label shown as a title (fixed: `screen_name`); no type block from the narration |
| 4 Numbers | each number gets its own picture | numbers float over unrelated photos ("6,500 KM" on a train plaque) | metric moments placed on whatever shot is there |
| 4 Data | 50-70 % of the frame, readable | thin lines, tiny text, literal "A\|B\|C" | diagram rows in the wrong columns (fixed: repairs); templates drawn small |
| 5 Clock | correct time, year, age; grows at key beats | "1197060:44:22" | "N years" read as light time (fixed) |
| 5 Card | real readout or none | black-hole stages, "0" | defaults from another video (fixed) |
| 6 Photos | card on the right, ring annotation | wrong pictures (lion statue, press photo, shuttle clip) | stock alternatives on NASA rows, weak NASA checks (fixed) |
| 7 Colour | cyan / gold / white, red for failure | similar palette | — |
| Sky | dense Milky Way | invisible (too faint) | star brightness (fixed) |
| Repeats | none | Pale Blue Dot 3× in 30 s | (fixed: 90 s rule) |

## What to build next, in order of effect
1. **Type block from the narration** (rule 3): for each sentence with a number or a key noun, a kicker / headline / sub block in the
   left third over the current shot, every 5-8 s. This is the single biggest visual difference.
2. **Diagrams in the world, not on plates** (rule 1): draw orbit / path / bubble diagrams over the star sky, with no top heading;
   keep a plate only for data graphics, and give those no heading either (the kicker carries it).
3. **"YOU · ON BOARD" marker** on every craft shot of the journey's own craft (rule 2).
4. **Longer shots that build** (rule 1): merge consecutive CSV rows about one subject into one shot whose layers arrive one by one.
5. **Data graphics at full size** (rule 4): templates scaled to 50-70 % of the frame, labels ≥ 2 % of the height.
6. **Date stamp top-right** whenever the narration names a date (rule 5).
7. **Photo cards with a ring annotation** on the named feature (rule 6).
