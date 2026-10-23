# Explainer style guide (Phase 0)

Status: draft for approval. Planning only. No application code was changed.
Reference evidence: [explainer_reference_manifest.json](explainer_reference_manifest.json) (R2, 0:00 to 1:59.7, 24 shots) plus 12 + 17 coarse contact sheets of both references.

How to read the labels: **[measured]** = taken from frames or audio in this session; **[estimated]** = judged by eye, ±; **[proposal]** = our design choice, not a reference fact; **[unknown]** = not established.
The references are 640×360 H.264. Fine detail (small type, mouth shapes, exact colours) is low confidence.

## 1. Visual identity and palette

Four scene families, one narrator, one colour language. In the R2 opening, seconds on screen [measured from the shot list]: cartoon 33%, board 33%, map 27%, archival 8% (R2 0:00 to 1:59.7 only; the whole-video mix is **[unknown]**, the coarse sheets suggest the same thirds).

| Family | Look |
|---|---|
| Board | Flat light grey, no texture, no vignette. Measured dominant value about **#C0C0C0** (±8 per channel: the measurement is quantized and compressed). Objects are flat with a thin dark outline. |
| Cream paper | Scroll or card on the board. About **#F0E8C8** (±8). Dark-brown wooden rods. |
| Cartoon | Flat colour, no gradients except sky and one time-of-day shift. Sky pale blue, sand and brown ground, green cacti and pines. A thin dark outline on characters, none on backgrounds. |
| Map | Dark satellite imagery with soft white or gold translucent fills, white dashed lines, yellow pins, small grey date chip. |
| Archival | Paintings, engravings and photographs full frame with the edges softly darkened or blurred. Text overlaid. |

**Colour roles** (held across all four families in the segment) **[measured by inspection]**:
- blue = the poor / north / USA side
- green = the Mexico side
- gold or yellow = rich / south / treasure / the key phrase on dark backgrounds
- red = emphasis, conclusion, loss, down arrows
- navy = tags with a number or ratio

These roles are a story device (the viewer reads a colour before the words). The guide treats them as rules, with each video declaring its own role table up front. **[proposal]**

## 2. Typography and font hierarchy

Observed in the reference **[estimated]**: three voices.
1. **Body lettering**: thin, casual handwriting, lower case, wide letter spacing. Dark on board, white (sometimes with a thin dark outline) on scenes and maps, yellow for the key phrase on dark backgrounds.
2. **Display title**: heavy, outlined, slightly irregular yellow lettering (for example a chapter-style title). It scales in with overshoot.
3. **Chip type**: rounded clean sans on a dark pill (a year, a ratio).

### Candidates and how to choose
Do not decide from a screenshot of the font catalogue. Procedure **[proposal]**:
1. Render the same 20 phrases taken from the reference (short on-screen labels) at the **target output resolution** (1920×1080 and the actual pixel size the type will have, about 3× the reference size) in each candidate.
2. Lay each render next to a crop of the reference scaled to the same height. Compare x-height, stroke contrast, letter spacing, the shapes of `a`, `g`, `y`, `t`, and how digits look (1700, 2009, 100,000).
3. Check legibility on grey, on satellite imagery and on a painting, with and without an outline.
4. Three reviewers rate "same family of feel" 1 to 5. Ties go to the font with the better licence record and the more complete glyph set.

| Candidate | Why try it | Verify before use |
|---|---|---|
| **Patrick Hand** | Neat, regular hand lettering, good for a body face | Licence text from the font's own package; glyph coverage for accented Latin (place names such as Potosí, Saint-Domingue); weights available |
| **Kalam** | Looser, more informal hand style, has more weights | Same checks; the Devanagari portion is not needed so a Latin-only subset is fine |
| Others to include in the same test | Caveat Brush or Gaegu-style faces for titles, a rounded heavy display face for the outlined title | Same checks |

Both named fonts are, to my knowledge, published under the SIL Open Font License 1.1, but **this was not verified in this session** (no network lookup, no licence file read). Do not rely on that until the licence file is read from the downloaded package and stored beside the font (see section 10).

**Existing font situation in the repo** (verified):
- `assets/fonts/ChalkboardSE.ttc` is used by the Overscaled style and Doc Style. The code comments say it is "bundled from macOS's own Supplemental fonts" ([scene_graph/composition.py:17](../../scene_graph/composition.py), [graphics/doc_looks.py:45](../../graphics/doc_looks.py)). That is an Apple font, not an OFL font. The repo's CI builds Windows and macOS installers ([.github/workflows/build-desktop.yml](../../.github/workflows/build-desktop.yml)), so this file is shipped to Windows users. Whether Apple's licence allows that was **not verified** and should be treated as a licensing risk to confirm. Do not choose it for Explainer.
- `assets/fonts/` contains no licence files. `gfx-core/fonts/OFL.txt` covers Cormorant Garamond only. `pakmap-engine/assets/fonts/README.txt` records Montserrat as OFL 1.1 with its source URL: this is the pattern to copy.

Hierarchy **[proposal]**: display (titles) → body hand (labels, typed lines) → chip sans (numbers). At most two sizes of body type per scene. Dark ink on board, white-with-outline on scenes, never body type below a size that is legible at 1080p.

## 3. Board layout and composition rules

Observed **[estimated]**:
- One idea per board. Content is added in the order it is spoken and the whole board is cleared on the next sentence start (measured: cards cleared at 62.3 s, the same moment the next sentence begins).
- Narrator on the left, content to the right, using about half of the frame width. Narrator shrinks when the content needs space (about half of frame height, down to about one quarter).
- Column headers (two sides) typed first, rows after.
- Objects arrive with a short pop or scale-in, then hold still. Arrows grow along their length.
- Labels are one to three words, typed under or beside the object.
- Whitespace is generous. A board has at most about six objects plus text.

Rules **[proposal]**: a safe margin; objects aligned to a loose grid but allowed slight irregularity in angle (a few degrees) so it does not look machine-made; one primary colour role per object; no more than one new object per 1.0 s of speech.

## 4. Narrator identity, poses, position and animation

**Observed** (R2 opening) **[estimated]**:
- One recurring stick figure, hat and spear, present about half of the segment.
- Position: left on boards, right edge on maps, absent in cartoon and archival shots.
- Scale: about half the frame height on boards, about one third at the map edge, large for one second on a question beat, small on dense boards.
- Poses seen: standing with arm extended toward content; standing with both arms raised (surprise); closed mouth to open mouth to pointing within 3 s; leaves frame while the map pans.
- Mouth toggles open and closed every 0.15 to 0.3 s while speaking; eyes blink (measured 62.0 to 65.0 s). Whether the mouth is driven by the audio or a fixed loop is **unknown**.
- Longest absence in the segment: 25.8 s (seven shots), first absence 17.35 s.

**Proposal.** An **original** character, not a copy of the reference's. Do not reproduce the reference's straw-hat figure: the reference is somebody else's character and copying it would be a likeness and trademark risk. Keep the role (an anchor who reacts and points) and the framing rules, change the design.
- A canonical reference sheet (front view, three-quarter, side) plus reusable pose layers (about 6 to 8) and separate layers for eyes (open, blink, happy) and mouth (closed, open, wide, "o").
- Mouth driven by narration activity (speech/no-speech from the word times), not by phonemes. Blink on a randomised timer.
- Placement rules as above; enter and leave by sliding.
- Narrator may be absent for long stretches. The reference leaves a 17 to 26 s gap, so an every-3-beats rule would be stricter than the source. Make the return interval a style setting, default around 20 to 30 s, to be set by the scorecard.

### Three ways to get the character
| Option | Consistency | Licensing | Asset effort | Render-time cost |
|---|---|---|---|---|
| Draw an original character (vector, layered) | Best: one source of truth | Clean: fully ours | Highest up front (design, poses, expressions) | Lowest: pre-rendered PNG layers or a small vector rig |
| Adapt a licensed character pack | Good if the pack has all poses | Must verify the licence allows modification and redistribution in a commercial desktop app | Medium; limited pose set | Low |
| Generate a reference sheet with an image model, then trace | Risky: style drift between poses; tracing hides it only if every pose is retraced | Depends on the model terms and must be checked; tracing a generated image does not remove those terms | Medium, plus manual clean-up | Low once traced |

Recommendation **[proposal]**: draw (or commission) an original layered character, using a generated sheet only as inspiration for the design brief, not as the source art. This costs most up front and removes the licensing and drift risks. Repository evidence does not suggest a better option: nothing in the repository animates characters (searched `whatif-engine`, `gfx-core`, `scene_graph`, `weather`; the only character-like assets are icons).

Do not create the art in Phase 0.

## 5. Map and archival visual rules

Map **[measured/estimated]**:
- Dark satellite imagery. Camera pushes in on the place, pans between places and pulls out to the globe for "zoom out" beats.
- Overlays: dashed white border line, yellow pin with label, translucent white fill for the subject country, translucent gold fill for a group (Latin America), white route lines, small icons beside pins (sugar), small grey date chip at the top left, gold coin pins.
- Text on map: white heading, yellow typed key phrase; labels small.
- The narrator is at the right edge and may leave while the camera moves.

Archival:
- Paintings, engravings and photographs full frame, edges softened to fill 16:9, a slow zoom or none, text on top, sometimes a counting counter.
- Paired with a cartoon of the same subject in the next or previous shot (painting then cartoon), a story device in this segment.

Rules **[proposal]**: every map label must correspond to a place named in the narration window (checked automatically); every archival image must carry a reason in the plan ("what it shows that the map cannot"; Hybrid already has this field: `Clip.reason`, [hybrid/plan.py](../../hybrid/plan.py)).

## 6. Caption appearance and timing

Measured in two fine strips **[measured]** and the 1 fps sheets **[estimated]**:
- The reference does **not** subtitle the narration line by line. It types short **key phrases** (one to about eight words), as labels or one-line comments.
- Text is **typed per character**: partial words are visible in frames ("Nogal", "almost no", "complet", "BA"). Measured type-on: a 19-character phrase finished in about 0.6 s (about 30 characters per second).
- A display title instead **scales in** with overshoot, onset aligned to its key word (title onset 63.05 s, spoken word at about 63.0 s: lag about 0 to 0.2 s).
- A paired icon appears about 0.2 s after its key word (taco icon at about 23.8 s, word at about 23.6 s).
- A subtitle line may be timed to **finish with the sentence** instead of starting with it (completed at 64.85 s, sentence ended at about 64.8 s).
- Board content is cleared at the next sentence start (62.3 s).
- Cuts land on sentence or clause starts: 16 of 22 detected cuts within 0.25 s of a Whisper sentence start, 17 of 22 with clause starts. The remaining five are mid-sentence on a key phrase (one example at 88.4 s).

Sample sizes are small (three fine measurements). Thresholds in the scorecard that depend on them are **provisional**.

Current Hybrid behaviour for comparison **[verified]**: captions are drawn per scene ([normal_gfx/captions.py](../../normal_gfx/captions.py) for Normal Video; `caption` layer in pakMap rows, [pakmap-engine/lib/draw.mjs](../../pakmap-engine/lib/draw.mjs) `drawCaption`). The `typed_caption` gfx-core template types a whole phrase ([gfx-core/templates/news/typed_caption.json](../../gfx-core/templates/news/typed_caption.json)). A per-word or per-character cue tied to individual spoken words is available only through `gfx_templates.find_cues(...)` ([gfx_templates.py:236](../../gfx_templates.py)), which takes the word list.

## 7. Cartoon scenes and character continuity

Observed **[estimated]**:
- A cartoon **set** is reused across the passage: the same desert-town background appeared five times, once with a fence added, and again as a thumbnail on a board.
- The same set changes by adding props (flags, check-list, families) and by time of day (sun lowers across one shot).
- Characters are one body type with different clothes and colours; groups are shown as a row of small figures along the bottom for population.
- Two-set split screens with a thin divider show size contrast.
- Colour coding of clothing carries the story (blue family, green family).
- Other sets seen across R2's coarse sheets: board room, throne room, bank, ministry, classroom, parliament, ship deck, supermarket, plantation. Dialogue scenes with name labels under each character and dark silhouette scenes exist in R2 outside this segment and are **not** exercised by the test segment.

Rules **[proposal]**: a set has an id and a props list; a video may reuse a set as often as the story needs; a character has a fixed base body plus outfit and colour variants per era; one new prop per beat; time of day is a parameter of the set, not a new set.

## 8. Shot pacing and transitions

Measured on the 2-minute test segment **[measured, ±0.5 s]**: 24 shots, mean 4.99 s, median 4.6 s, shortest 2.2 s, longest 11.4 s (a map with camera motion), 9.7 s (a board that changes several times). Hand-annotated change events (a label, object, text or camera step) average 0.71 per second, median gap 1.0 s, longest gap 4.3 s; 58 of 60 two-second windows contain a change or a cut (provisional).

Whole-video scene-change counts (283 in R1, 318 in R2 at threshold 0.3, a mean of 7.5 s) are **lower bounds**, because the detector misses cuts between two light frames (for example cartoon to grey board at 23.05 s, verified at 10 fps). Do not quote 7 to 8 s as a shot length.

Transitions: **hard cuts** in every case verified at fine resolution (23.05 s). No dissolves were observed. The whole-video behaviour is **unknown** (the repository's Hybrid default is a dissolve, so this is a deliberate difference: see section 12).

Rules **[proposal]**: a shot is 2 to 10 s; something visible changes at least every 2 s (a text, an object, the camera); a deliberate hold is allowed where narration is a reflective statement, marked in the plan so the pacing check does not flag it (the existing pakMap pacing module already allows this: `hud_title params {"pacing": "abstract"}`, [pakmap/pacing.py](../../pakmap/pacing.py)).

## 9. Story structure and recurring metaphors

Observed in the R2 opening **[estimated from narration idea and shots]**:
1. Human-scale **hook** (a border town, two towns, a fence): 0 to 46 s.
2. **Evidence** of sameness in small steps (desert, weather, families, food, music), then the surprise number (three times the income).
3. **Zoom out** to the world map (46.6 s).
4. **Twist** announced with a title (63 s): it was not always like this.
5. **Historical reversal** with proof from paintings and cities (73 to 99 s).
6. **Question** stated plainly (99.6 s): how did the poor north become the richest while the rich south fell behind?
7. **Step back in time** with the date chip and routes (107 s).
8. **Aphorism** on a scroll (112 s), drawn as a paradox with arrows (115 to 119.7 s).

Recurring metaphor in the segment: the colour roles and the rich-falls / poor-rises arrow pair. The **signature metaphors** (sticky note and scale in R2, whale and shrimp in R1) occur later; their frequency and build-up were **not measured in Phase 0** (see report: recommended second test segment).

Not yet established, so deliberately not turned into rules: how often recaps occur, what the final callback looks like, and the exact narrator-return interval across the whole video.

## 10. Asset reuse, packaging and resolution rules

Applying the standing rule (no per-video asset burden) **[proposal]**:
- Everything the style draws (narrator layers, icons, sets, props, board objects, chips) is created or sourced **once**, versioned and shipped as a package. A render never generates art. If an asset id is missing, fall back (section 11); never create it on the fly.
- Each asset has an id, family, tags, source, licence name, licence file, author, date added, and the colour roles it supports.
- Package layout follows the existing patterns: fonts under `assets/fonts` with a notice file beside each font (copy the Montserrat README pattern), engine assets under the engine's own `assets` folder.
- The PyInstaller spec already bundles `assets/fonts` and `assets/smart_previews` ([VideoGenerator.spec](../../VideoGenerator.spec)); any new asset folder needs an explicit line there, and a test that the file list in the spec matches the library index.
- Resolution: author for **1920×1080** output (the Hybrid default is `width=1920, height=1080, fps=30`, [hybrid/compile.py:406](../../hybrid/compile.py)). Raster art at no less than 2× its largest display size; prefer vector for characters and icons and rasterise at packaging time to PNG sprites (the engine's `sticker` layer needs a PNG with transparency, [pakmap/compile.py:597](../../pakmap/compile.py)).
- Archival images are fetched like any footage (Commons provider exists), not packaged; their credit must be recorded in a credits file. A `Sahara_Hybrid_Map-credits.txt` exists in Downloads from an earlier render, but the code that writes it was not traced in Phase 0, so whether Hybrid already produces credits automatically is **unverified**.

## 11. Fallback behaviour when an asset or beat type is unavailable

Principle: never stop, never invent. **[proposal]**, in order:
1. A missing icon or prop → use the nearest tagged icon, else a text chip with the label.
2. A missing set → the neutral set of the same family (day variant), else a board beat carrying the same idea.
3. A missing narrator pose → the neutral pose.
4. A `cartoon` beat when the cartoon kit is absent (Phases 1 to 6 are usable without Phase 7) → a `board` beat with the same idea; if that is not possible, the current Hybrid beat types.
5. A missing archival image → a map or board beat (do not substitute an unrelated picture; this follows the existing behaviour "providers return a failed result with a reason, never a substitute asset", [docs/hybrid/architecture-proposal.md](../hybrid/architecture-proposal.md)).
6. Explainer off → the current Hybrid output, unchanged.
Every fallback is logged in the plan notes so the scorecard can count them.

## 12. Differences between the reference and our implementation

| Topic | Reference | Ours (proposal) | Why |
|---|---|---|---|
| Narrator | Straw-hat stick figure | **Original** design with the same job | Avoid copying a character; keep the framing function |
| Resolution | 640×360 | 1920×1080 | Hybrid default; assets authored for it |
| Map | Dark satellite look | pakMap engine imagery and camera | Already built, tested and maintained; the look is closer than the board or cartoon |
| Captions | Typed key phrases, per character | Typed key phrases driven by word times; a switch for a plain per-scene caption | The reference does not subtitle verbatim |
| Transitions | Hard cuts (verified in one place) | Hard cuts for board and cartoon beats, existing dissolve kept for map↔footage | Hybrid's compile and `media_full` logic assumes dissolves at footage boundaries |
| Beat types | Not applicable | New `board` and `cartoon` modes beside `map`, `footage`, `map_footage` | The plan model has only three modes ([hybrid/plan.py:26](../../hybrid/plan.py)) |
| Signature metaphor | Written by a human author | Chosen by the script step, then scheduled | Needs a decision on who writes it |
| Content | Real history essay | Any topic | The kit must be topic-neutral |
| Asset effort | One studio's hand-drawn library | Packaged once, grown over time | Per-video art is not allowed |
| Colour roles | Fixed in the video | Declared per video in the plan | Keeps meaning consistent without copying the palette |
| Licensing | Unknown | Every asset records its licence; fonts verified | Desktop app is redistributed |
