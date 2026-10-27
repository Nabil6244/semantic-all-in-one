# War documentary style: visual treatment and animation catalog (design only)

Status: proposal for approval. No code written, no assets made. Part of the Russia–Ukraine war documentary direction; builds on the Phase 1 prototype (`cinematic_explainer/`), which is preserved unchanged.

Labels: **[measured]** = reference A, ±0.1 s (`docs/styles/cinematic_explainer_research.md` §0b); **[existing]** = a constant already in our code; **[proposal]** = new number, to be tuned in the first demonstration; **[unknown]** = not established.

## 0. Shared rules for every treatment

1. **Provenance travels with the visual.** Every treatment has a `provenance` record (source, licence, capture date, publish date, location, verification status; schema in the asset taxonomy document). A treatment with a factual claim and no provenance is not built; the planner falls back (see each entry).
2. **Illustrative means labelled.** Anything not taken from a real record (a trajectory, a range ring, a schematic) carries a fixed on-screen chip `ILLUSTRATIVE` [proposal: small grey chip, bottom-left of the graphic, same size as the date chip] from its first frame to its last.
3. **Footage first.** Cards sit over dimmed/blurred footage (backdrop dims in 0.2 s [measured], brightness ×0.34, blur by 12× down/up scale [existing, `cinematic_explainer/look.py`]); the footage under a card is the scene's own real clip, never a stand-in chosen to fill space.
4. **Default timings** (cards): fade-in 0.3 s [measured; existing `CARD_IN_S`], exit 0.2 s [existing `CARD_OUT_S`], min on screen 3.0 s [existing `MIN_VISIBLE_S` in `gfx_templates.py`], hold ≥ 1.5 s after the last change so the final state can be read [proposal].
5. **Cost classes:** cheap = PIL card or ffmpeg filter, no per-frame heavy work; medium = a map/GL render or a pre-rendered clip cached per asset; expensive = new renderer work. A card is a pure function of time and is rendered per segment (bounded memory, see performance plan), never per frame regenerated if static.
6. **Stable positions.** Kicker top-left, shot headline lower-left, cards centred or left-third, ILLUSTRATIVE/source chip bottom-left above the headline zone. Nothing enters the lower 12 % except the headline and chips.

## 1. Catalog

Existing-component key: **GFX** = `gfx-core/templates/*` (79 templates, all render); **DOC** = `graphics/doc_looks.py` + `doc_plan.py`; **HYB** = Hybrid Map (`hybrid/`, `pakmap/`, `map_scene/`); **CE** = `cinematic_explainer/cards.py` (Phase 1: kicker, source, number, list, portrait, shot_head); **ED** = `editorial/`.

### 1.1 Real footage (the default surface)
- **Use:** whenever the narration is about an event, place, person or object for which a matching verified clip exists.
- **Treatment:** clean footage, no card; optional shot headline (3–7 words, black box, yellow tick, types in over ~0.5 s [existing CE `shot_head`; reference types in word by word, measured on some shots]). Ken Burns only on stills, ≤ 4 % scale over the shot [existing `ken_burns`; value proposal].
- **Timing:** shot length 4–5.5 s average, nothing static > 8 s [reference A measured 4.7 s average; cap from user rule "no still screens"].
- **Params:** `clip`, `in/out`, `headline`, `date_line` (optional).
- **Provenance fields:** `event_date`, `capture_date`, `publish_date` (separate), `place`, `source`, `licence`, `verification` (verified / unverified / recycled / disputed).
- **Fallback:** no verified clip → map, equipment card, or no visual (never an unrelated clip). A clip whose verification is `recycled` or `disputed` gets a yellow `FOOTAGE: DATE UNCONFIRMED` chip, or is not used.
- **Cost:** cheap. **Carrier:** existing footage pipeline + CE `shot_head`. **New:** verification chip.

### 1.2 Animated map reveal
- **Use:** the sentence is about *where* something is, moves, or changed (see planner rules). Not for a mere country mention.
- **Treatment:** HYB dark map with camera glide (globe → country → region → local), muted fills, white dashed disputed border, pins with one-line note, chapter panel bottom-right [reference A map; Vox Kashmir relief look]. Camera never cuts [existing Hybrid rule].
- **Timing:** camera push ≤ 3 s ease-in-out [proposal]; fill fade 0.3 s; pins stagger 0.25 s apart in the order named [proposal]; map visit 6–14 s [proposal]; revisit at chapter boundaries (reference A: 5 visits in 13:52 [measured]).
- **Params:** `frame`, `places[]`, `fills[{place, role}]`, `pins[{place, note}]`, `style` (dark/natural/satellite), `label`.
- **Provenance:** `geo_source` (Natural Earth / OSM / admin1), `as_of` date for any border or control status, `disputed` flag; the map footer chip `Map data: Natural Earth. Schematic.` [measured in reference A].
- **Fallback:** place not resolvable → no pin (existing: "a city whose outline cannot be confirmed gets no highlight"); never a drawn box or circle as a stand-in.
- **Cost:** medium. **Carrier:** HYB (`map_scene`, `pakmap`, `place_focus`, `boundary_source`). **New:** "news dark" skin tokens (colour roles, relief option), pin-note card style.

### 1.3 Front-line / territorial change
- **Use:** narration states that control, extent or a boundary changed between two dated points.
- **Treatment:** two polygons for date A and date B on the map; A shown first, B wipes in over it (left-to-right or by region), the changed area outlined; a date chip for each state.
- **Timing:** A held 1.5 s, wipe 1.2 s [proposal], B held ≥ 1.5 s, date chip swap 0.3 s.
- **Params:** `polygon_a`, `date_a`, `polygon_b`, `date_b`, `source_a/b`, `extent_note`.
- **Provenance (mandatory):** named source of each polygon (e.g. a published assessment), `as_of` date, `method` (assessed / claimed / reported), `claimant` (who asserts it). **We never draw a line from our own guess.** Without a sourced polygon the planner may only show the named places as pins (1.2).
- **Fallback:** no sourced polygon → pins only, or no visual.
- **Cost:** medium. **Carrier:** HYB `fill` events (translucent polygon) + `territory_clock` template (GFX, needs figures). **New:** the A→B wipe pattern, polygon import with provenance; the source data itself is an asset decision (see §2 of the taxonomy).

### 1.4 Equipment identification card
- **Use:** narration names a specific weapon or vehicle and says something about it (role, range, number in service).
- **Treatment:** framed photo of the real equipment (not a render), name plate (red), role line, up to 3 facts (row by row, 0.3 s each), `SOURCE` chip. Over dimmed footage.
- **Timing:** frame fade 0.3 s [measured card in]; facts staggered with their words, 5–6 s apart in lists, ≥ 1.0 s apart for short lists [measured list spacing; short spacing proposal]; hold ≥ 4 s; exit 0.2 s.
- **Params:** `equipment_id`, `photo`, `name`, `role`, `facts[{label, value, source}]`, `variant` flag.
- **Provenance:** `photo_source`, `licence`, `identification_status` (confirmed by source / unconfirmed), `specification_source` + `spec_as_of`. Specifications differ by variant; if the narration does not name the variant the card shows no figures.
- **Fallback:** no licensed photo → name plate + role over footage (no picture), or a labelled `ILLUSTRATIVE` silhouette icon from a neutral set; never a lookalike photo.
- **Cost:** cheap. **Carrier:** GFX `framed_still` + `dossier_card` + DOC `framed`, CE `portrait` geometry. **New:** equipment record schema and the `facts` row style.

### 1.5 Technical diagram (cutaway / system schematic)
- **Use:** explaining *how* a system works (layered defence, radar coverage idea, drone/missile stages) when no real footage can show it.
- **Treatment:** simple line schematic, built up part by part (parts draw in over 0.4 s each [proposal]); every diagram carries the `ILLUSTRATIVE` chip and a one-line "schematic, not to scale".
- **Params:** `diagram_id`, `parts[{label, appears_at}]`.
- **Provenance:** `basis` (which public description it simplifies), `author`, `licence`.
- **Fallback:** no approved diagram → equipment card or footage.
- **Cost:** medium (assets are drawn once, cached by `diagram_id`). **Carrier:** GFX has no diagram template. **New:** diagram template + a small approved diagram set (an asset decision; not generated now).

### 1.6 Equipment callout on footage
- **Use:** a labelled point on a real clip ("the radar dish") when the narration points at a visible part.
- **Treatment:** leader line draws from the label to a **fixed screen-space anchor** (line draw 0.4 s [proposal]); label fades in 0.3 s; held while the clip holds that framing.
- **Params:** `anchor_xy` (screen fraction), `label`, `clip_id`, `t_in/t_out`.
- **Provenance:** requires `identification_status = confirmed`; the human/planner-confirmed region must be recorded.
- **Fallback:** tracking is not reliable here → **no tracking**; if the object moves out of the anchor the callout is dropped. If identification is unconfirmed, no callout.
- **Cost:** cheap. **Carrier:** GFX `photo_leader`/`chokepoint_callout` (map-only today), `editorial/zoom_blur_callouts`. **New:** the over-footage callout with a fixed anchor.

### 1.7 Chart reveal (numbers, comparisons, series)
- **Use:** the narration states two or more comparable figures, a ratio, a series or a share.
- **Treatment:** bar compare (yellow baseline vs red current, axis from zero), big-number card (figure counts ×1…×N, label fades, red rule draws), trend line, ring percent.
- **Timing (measured on A):** kicker first; count ~0.4 s; label fade 0.2 s; rule draw 0.5 s; hold ≥ 1.5 s. Bars grow 0.6 s each [proposal], second bar starts when its number is spoken.
- **Params:** `values[]`, `labels[]`, `unit`, `as_of`, `source`, `baseline`.
- **Provenance:** `figure_source` (the narration's cited source or the cited document), `as_of`, `claimant` for contested figures (casualties, losses, "destroyed" counts: always shown as `CLAIMED BY …` or `REPORTED BY …`, never as fact).
- **Fallback:** value not stated in full by the narration → no chart (existing extractor rule: "a required slot the narration does not fill means no graphic").
- **Cost:** cheap. **Carrier:** GFX `big_number`, `versus_numbers`, `rank_bars`, `trend_line`, `ring_percent`; DOC `number`, `chart`, `hbars`; CE `number`. **New:** claimant chip, red/yellow role palette.

### 1.8 Portrait introduction with attributed statement
- **Use:** a named person is introduced with a role, or a quotation is attributed to them in the narration.
- **Treatment:** circle portrait with white ring, red name plate, one role line; statement card beside it (portrait left, quote right), words light up as spoken [measured on A: card in 0.3 s, words darken in narration order].
- **Timing:** portrait scale 0.94→1.0 over 0.3 s [existing CE]; statement words 0.12 s each [existing `WORD_S`]; hold ≥ 4 s.
- **Params:** `person_id`, `name`, `role`, `image`, `statement`, `statement_date`, `venue/outlet`, `translation_flag`.
- **Provenance:** `portrait_source`, `licence`, `identity_verified` (by a named source such as an official site or agency archive), `statement_source`, `statement_date`, `original_language`. A translated statement says `TRANSLATED`.
- **Fallback:** identity not verified or no licensed portrait → **name plate only over footage** (no face); statement with no verifiable attribution → no quote card.
- **Cost:** cheap. **Carrier:** CE `portrait`, GFX `name_bar`, `quote_boxed`, `quote_card`, DOC `nametag`/`pullquote`. **New:** person record cache, verified-portrait lookup (decision needed).

### 1.9 Evidence / source card with highlight
- **Use:** the narration cites an outlet, institution, report or document and reads or paraphrases a line of it.
- **Treatment:** paper card, red top edge, serif outlet name, date chip, sentence in pale grey whose words darken as spoken, yellow highlighter on the key phrase following the words; optional red pen ellipse for a date or number [Harris Northwoods pattern, ADAPT].
- **Timing [measured]:** fade-in 0.3 s with small upward slide; words darken at narration pace (~0.1–0.3 s per word); highlighter follows the word. Card hold ≥ sentence length + 1.0 s [proposal]; exit 0.2 s.
- **Params:** `outlet`, `date`, `words[]`, `times[]`, `mark`, `url_or_ref`.
- **Provenance:** the text must be the **verbatim or clearly marked paraphrase** of a real published item; `retrieved_on`, `url_or_reference`, `language`. A paraphrase shows `PARAPHRASED`. Never an invented headline or an outlet logo we do not have rights to show.
- **Fallback:** no verifiable citation → no card (the line stays narration only).
- **Cost:** cheap. **Carrier:** CE `source` (done in Phase 1), GFX `quote_card`/`fact_card`. **New:** verbatim/paraphrase flag, reference field.

### 1.10 Archival / scanned document treatment
- **Use:** a real document, map, photograph or film clip from an archive is the evidence itself.
- **Treatment:** document on paper texture, zoom to the line (1.0→1.6 scale over 1.2 s [proposal]), highlighter, pull back; archival film with slight contrast lift and vignette [Harris Northwoods observed; motion not observed]; photos as layered cut-outs with ≤ 12 px offset for "X versus Y".
- **Params:** `asset_id`, `zoom_region`, `highlight_region`, `caption`.
- **Provenance:** `archive`, `catalogue_id`, `original_date`, `licence`, `restrictions`.
- **Fallback:** missing file → skip card; keep narration over footage.
- **Cost:** cheap–medium (zoom via cached still crop). **Carrier:** GFX `polaroid_board`, `photo_plate_*`, `framed_still`; Ken Burns. **New:** zoom-to-region + highlighter on an image.

### 1.11 Satellite / aerial treatment
- **Use:** "what is this place" on a specific facility or area, when an imagery source with rights exists.
- **Treatment:** satellite crop, translucent coloured band or outline, ≤ 2 labels [Wendover pattern, ADAPT]; before/after slider for change (two dated images).
- **Timing:** outline draws 0.6 s [proposal]; labels fade 0.3 s; slider sweep 1.5 s [proposal].
- **Params:** `image_id`, `bbox`, `outline`, `labels`, `date_a/b`.
- **Provenance:** `provider`, `acquisition_date` (never conflated with event date), `licence`, `resolution`, `outline_basis` (who defined the outline).
- **Fallback:** no licensed imagery → map at local frame or footage; never a mock-up.
- **Cost:** medium. **Carrier:** GFX `before_after_slider`, `region_spotlight`; HYB satellite style is **[unknown]** whether present (map_scene styles are dark/natural only). **New:** imagery asset type and licence field; adding a satellite base map is an approval item.

### 1.12 Trajectory / movement graphic (always illustrative)
- **Use:** narration describes a route, flight path or axis of movement *in general terms* (from A toward B).
- **Treatment:** dotted line from named place to named place draws over 1.0–2.0 s [proposal], arrowhead at end; `ILLUSTRATIVE` chip for its whole life; no speed, no timing, no intercept geometry drawn.
- **Params:** `from`, `to`, `via[]`, `kind` (route/axis/range ring), `distance_label` (only if the narration states it).
- **Provenance:** `basis` = "narration only"; if a published source gives the path, name it.
- **Fallback:** either end unresolvable → no line. Never show an exact trajectory, impact point or "intercepted here".
- **Cost:** cheap. **Carrier:** GFX `route_travel`, `flow_route`, `distance_ruler` (map-bound); HYB `flow` lines. **New:** the ILLUSTRATIVE chip rule and the distance-only-if-stated check.

### 1.13 Chapter transition
- **Use:** the script announces a part, or the story moves to a new question/phase.
- **Treatment:** one of: map revisit with chapter panel; kicker + `chapter_words`; hard cut (default). Zoom-blur only at map in/out and at most once per chapter [existing `zoom_blur.py` rule: "only at big moments"].
- **Timing:** card fade 0.3 s; zoom-blur ~0.27 s each side of the cut [existing]; no transition > 0.5 s [proposal].
- **Fallback:** hard cut.
- **Cost:** cheap. **Carrier:** GFX `chapter_words`, `chapter_serif`, `chapter_next`; ED `zoom_blur`. **New:** nothing.

### 1.14 Recap sequence
- **Use:** only if an agenda/list card was shown earlier, or the script itself ends with a numbered recap.
- **Treatment:** the same list card returns, rows appearing one per spoken item (5–6 s apart in A [measured]); numbers tied to earlier figure cards re-shown small.
- **Fallback:** no earlier agenda → no recap card (a closing line stays narration).
- **Cost:** cheap. **Carrier:** GFX `checklist_card`, CE `list`. **New:** the "was announced earlier" memory (`graphics/memory.py` exists; reuse to be checked).

## 2. Motion primitives needed (shared)
| Primitive | Exists? | Where |
|---|---|---|
| Card fade/slide in-out | yes | CE `look.card_alpha`, GFX |
| Count-up, rule draw | yes | CE `number` [measured values] |
| Word-by-word darken + highlighter | yes (Phase 1) | CE `source` |
| Row-by-row reveal | yes | CE `list_card` |
| Backdrop dim + blur | yes (whole-timeline; **memory growth**) | CE `render.py` |
| Leader-line draw | map-only | GFX geo templates |
| A→B polygon wipe | no | **new** |
| Zoom-to-region on image | no (Ken Burns only) | **new** |
| ILLUSTRATIVE / CLAIMED / PARAPHRASED chips | no | **new** (one chip primitive) |

## 3. What is genuinely new (and why)
1. Provenance-bearing record per visual (schema in taxonomy document).
2. Chip primitive (illustrative / claimed / paraphrased / date-unconfirmed).
3. A→B territorial wipe, only with sourced polygons.
4. Zoom-to-region with highlighter on documents.
5. Over-footage fixed-anchor callout.
6. Diagram template (assets are an approval decision).
7. News-dark map skin tokens.

Everything else reuses GFX/DOC/HYB/CE.
