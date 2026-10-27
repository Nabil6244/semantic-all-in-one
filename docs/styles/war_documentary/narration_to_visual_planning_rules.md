# War documentary style: narration-to-visual planning rules (design only)

Status: proposal. No code written. Examples use **invented neutral fixture sentences**; none is a real claim.

Labels: **[existing]** = rule already in our code (file named); **[proposal]** = new; **[estimate]** = number to tune in the demonstration.

## 1. What already exists and is reused

| Existing rule | Where | Reuse |
|---|---|---|
| Extractors copy only what the narration says; a required slot not filled = no graphic | `gfx_extractors.py` header | **Core principle, kept** |
| Auto placement per template: `AUTO` table, numbers, quotes, names, places, comparisons, routes, years | `gfx_templates.py` (39 templates with a rule; list in `docs/hybrid/template_inventory.md`) | Reused as candidate generators |
| Spacing: `MIN_SPACING_S` 6.0, `MIN_VISIBLE_S` 3.0, `MAX_PER_MINUTE` 3 (5 over footage), `SAME_TEMPLATE_GAP_S` 12, `SAME_TEMPLATE_MAX` 2 per 120 s, `NEAR_DUPLICATE_S` 240, `FIRST_AT_S` 4.0 | `gfx_templates.py` | Reused; war style may tighten, not loosen |
| Doc Style extras: one at a time, ≥ 7 s apart, full-screen ≥ 25 s apart, quote ≥ 30 s apart, glitch every ~75 s | `graphics/doc_plan.py` | Reused values (`GAP_S`, `FULL_GAP_S`, `QUOTE_GAP_S`) |
| Graphics Director: "simplest treatment that improves comprehension", does not invent charts/maps without data | `graphics/director.py` | Reused as the restraint layer |
| Hybrid Director: beats as sentence ranges, overlays anchored to narration words, problems fed to a repair loop, map vs footage vs map+footage | `hybrid/director.py`, `hybrid/plan.py` | Reused as the beat/layer model |
| Map pacing: picture gap ≤ 25 s, ≥ 3 moments/min, footage insert 5–12 s, card hand-off | `pakmap/pacing.py` | Reused |
| Place focus: boundary outline only when a place is *discussed* (motion/location cue or subject of sentence; possessives, parts, passing mentions excluded; one resolution; 45 s no repeat) | `docs/hybrid/place-boundary-highlighting.md` | Reused wholesale for map triggers |
| Zoom-blur only at big moments | `editorial/zoom_blur.py` | Reused |
| Keyword callouts: ≤ 1 per scene, ≥ 7 s apart, never for a bare year | `editorial/keyword_callouts.py` | Reused |

**New in the war style:** the provenance gate (§5), the "clean footage floor" (§4), claimant/illustrative rules (§6), equipment and portrait *identity* gates, front-line sourcing gate, and a single arbiter across candidates (§3).

## 2. Decision order (per sentence or beat)

The planner works on timed sentences (the pipeline already supplies word times) and produces **at most one primary visual per beat**. Order of evaluation:

1. **Is there a verified real clip for this beat's subject?** Yes → real footage is the base surface (treatment 1.1). Cards may sit on it; a card never *replaces* a clip that exists.
2. **Does the sentence ask for a card by its own content?** Evaluate candidates in this order, keep those whose inputs are complete **and** provenance gate passes:
   1. Evidence/source card (outlet or institution cited + a line read or paraphrased).
   2. Attributed statement with portrait (quotation or "X said" + verified identity).
   3. Statistic / comparison (number with unit and referent; two comparable numbers).
   4. Equipment card (named equipment + a stated attribute).
   5. Front-line / territorial change (two dated states + sourced polygons).
   6. Animated map (a *where* or *movement* sentence, see §3.2).
   7. Illustrative trajectory (general route in narration; always labelled).
   8. Technical diagram (explanatory "how it works" sentence, approved diagram exists).
   9. Archival document / satellite (asset exists and the sentence is about that very item).
3. **Arbitrate** (§7) → winner, or none.
4. **Apply density and spacing limits** (§4). A winner that violates them is dropped, not delayed past `LATE_START_S` 2.0 s [existing].
5. **No visual** is a valid, logged outcome (§8).

## 3. Trigger conditions and exclusions per visual

### 3.1 Real footage
- **Trigger:** beat subject = event, place, object or person with a matching clip whose `verification` ≠ `disputed`.
- **Exclusion:** no clip whose `event_date`/`place` contradicts the sentence; a `recycled` clip needs the date-unconfirmed chip or is skipped; clips are never "mood filler" for a specific claim (e.g. a generic clip under "this specific unit").
- **Reuse allowed:** same clip returns for the same subject (reference A reuses 3–8×); never for a different subject.

### 3.2 Animated map
- **Trigger (any of):** a location cue *and* a place resolvable to exactly one place ("in", "near", "south of", "approaching", "across", "from … to …"); a verb of motion with an origin/destination ("moved", "advanced", "flew", "shipped", "withdrew"); a territorial statement ("took control of", "lost", "retook") with named places; a chapter boundary that changes region.
- **Exclusions [existing + proposal]:** never because a country name appears (possessive, adjective, passing mention: "the country's economy", "its Russian neighbour"); never for parts of a place ("northern …", "the … area") without an explicit anchor; never for a place that needs a disambiguating script place but has none; not within 45 s of the same place [existing]; not when full-screen footage is the beat's subject.
- **Density:** map visits at most one per ~120 s on average, ≥ 4 across a 14-minute video only when story regions change [estimate; reference A 5 in 13:52 measured]; a visit 6–14 s [estimate].

### 3.3 Equipment card / diagram
- **Trigger:** a named equipment type or system (matched against the equipment taxonomy by name or alias) **plus** at least one stated attribute (role, range, count, user, date) *or* the beat introduces it for the first time.
- **Exclusions:** generic words ("missile", "drone", "tanks") without a specific system → no card; a name that maps to several variants without the variant stated → card without figures; a system already carded in the last 120 s [proposal] unless the narration changes the topic.
- **Diagram:** only on sentences with explanatory structure ("works by", "in stages", "layered") and an approved diagram id; otherwise no diagram.

### 3.4 Portrait + attributed statement
- **Trigger:** a quotation in quotation marks with a named speaker (`gfx_extractors._attribution`: "said / told / according to …"), or an introduction sentence ("X, the minister of …").
- **Exclusions:** a name spoken without role or statement → **no portrait** (name plate over footage only if the planner needs it); pronoun attribution → no card; unverified identity or unlicensed portrait → name plate only; an unattributed quote is never shown with a face.
- **Density:** one portrait card per person per 180 s [proposal]; at most one quote every 30 s [existing `QUOTE_GAP_S`].

### 3.5 Statistic / comparison
- **Trigger:** numeric value with unit and referent (`gfx_templates` percent, big, times, versus, rank extractors); two comparable values in one sentence; a series with ≥ 3 stated points.
- **Exclusions:** bare years; numbers without a referent; any figure the narration does not state in full; figures that are **claims** (losses, "destroyed", casualties) are shown with the claimant chip or not at all; ratios the planner would have to compute itself.
- **Density:** `MAX_PER_MINUTE` 3 [existing], over footage 5; the same figure not repeated within 240 s [existing].

### 3.6 Evidence / archival card
- **Trigger:** an outlet/institution/document name in the sentence ("a report by …", "the ministry's statement", "according to the agency") and either a quoted line or a paraphrase the narrator reads. Keywords: *report, statement, document, filing, memo, order, communiqué, bulletin*.
- **Exclusions:** no named source → no card; a line the planner would have to write itself → no card; paraphrase must be marked `PARAPHRASED`.
- **Archival scan/photo:** only when an asset with that catalogue id is attached to the beat.

### 3.7 Front-line / territorial change
- **Trigger:** two dated states of control of the same area named in the narration **and** sourced polygons for both (`as_of` + source).
- **Exclusions:** one-date statements ("the city is held by …") → map pins only; contested control is shown with the claimant named; no polygon from our own drawing.

### 3.8 Illustrative trajectory
- **Trigger:** "from A to B" movement with both places resolved.
- **Exclusions:** no exact path, impact point, intercept, speed or time-of-flight; never when a published track is the subject (then a sourced record is needed, not an illustration).
- **Always:** `ILLUSTRATIVE` chip.

## 4. Density limits (summary)
| Limit | Value | Source |
|---|---|---|
| Nothing before | 4.0 s | existing `FIRST_AT_S` |
| Gap between any two graphics | ≥ 7 s (cards over footage ≥ 6 s clear) | existing `GAP_S` 7 / `MIN_SPACING_S` 6 |
| Full-screen card gap | ≥ 25 s | existing `FULL_GAP_S` |
| Per minute | ≤ 3 (≤ 5 over footage) | existing |
| Same template | ≥ 12 s apart, ≤ 2 per 120 s | existing |
| Same fact | not within 240 s | existing |
| **Card share of screen time** | **25–35 %** | proposal from the references (A measured ≈ 35–40 %; drone film ≈ 0 %) |
| **Clean-footage floor** | **≥ 55 % of screen time with no card** | [estimate] |
| Shot headline lower thirds | on 30–40 % of footage shots, never under a card | proposal (A ≈ 60 %) |
| Map visits | ≈ 1 per 2–3 min of story that changes region | [estimate] |
| No still screen | nothing unchanged > 8 s | user rule |

## 5. Provenance gate (applied before arbitration)
A candidate is **dropped** unless it passes:
1. `provenance` record present for every factual asset.
2. `event_date` ≠ `capture_date` ≠ `publish_date` are stored separately; the on-screen date is the one the card claims (a date line says "FILMED …" or "PUBLISHED …" if it is not the event date).
3. `verification` is verified, or the visual carries the required chip (date-unconfirmed / claimed / paraphrased / illustrative).
4. Identification (equipment, person, place) is confirmed by a named source, or the visual falls back to the no-identity form.
5. Licence allows use; attribution text is attached.

## 6. Claims, disputes, mismatches
- Contested figures (losses, destroyed, casualties) → claimant chip (`CLAIMED BY …`) or not shown; never as a plain number.
- Disputed footage or identification → flagged in the plan report; not used as evidence.
- Footage/subject mismatch (e.g. equipment of a different country than the sentence) → the planner reports the mismatch and prefers no footage card; if used, a neutral shot headline, no identification.
- Never fabricate position, weapon identification, trajectory, casualty count or event.

## 7. Conflict resolution between candidates
When two candidates fall in the same ≤ 7 s window:
1. A card that **cites a source** beats a card that does not.
2. **Identity** (portrait/equipment) beats **location** (map) when the sentence's grammatical subject is the person/equipment; location beats identity when the sentence's subject is the place.
3. **Number** beats text/headline if the number is the new information; number loses to evidence if the number is quoted from the cited document (show the document, put the number in its highlight).
4. A full-screen card loses to a lower-third if a full-screen card ran in the last `FULL_GAP_S`.
5. Tie → keep the earlier-in-sentence trigger; the other may move to the next beat only within `LATE_START_S` 2.0 s, otherwise dropped.
6. Never two cards at once (existing "no overlap"), except kicker + its own card.

## 8. The "no visual" outcome
Logged with a reason code: `no_trigger`, `slot_incomplete`, `provenance_failed`, `density`, `conflict_lost`, `clean_floor`, `ambiguous_entity`, `quiet_moment`. A **quiet moment** is deliberate: after a heavy sequence (two cards in 20 s) the next ≥ 10 s stay clean unless the narration asks for a card by §3 *and* it is evidence-type.

## 9. Chapter and recap rules
- **Chapter:** announced by the script ("Part/Chapter N" + title, existing `chapter_serif` rule) or by an explicit region/time change; treatment = kicker + chapter words, or a map revisit. At most one chapter treatment per 90 s [estimate]; zoom-blur only on map in/out, once per chapter [existing rule, count proposal].
- **Recap:** only if an agenda list was shown (list card with rows) earlier in the video or the script contains a numbered close; recap card shows only items that were announced; rows timed to the spoken items. No recap for a script with no agenda. No engagement prompt (subscribe pill) by default.

## 10. Worked examples (invented fixtures)

**A. Map yes / no.**
- "The convoy moved from Alderton to the port of Merrow before dawn." → motion verb + two resolvable places → map with a dotted illustrative route, `ILLUSTRATIVE` chip; footage if a verified clip of the port exists, then the route card is dropped (footage first, §2.1).
- "Fenland's economy shrank last year." → country as possessive/subject of economics, no location cue → **no map**; if a figure is stated in full → statistic card.

**B. Portrait yes / no.**
- "'We will not move the depot,' said Minister Dorrin Vale." → quotation + attribution + role → portrait + statement card **if** the portrait is verified/licensed; else name plate only.
- "Dorrin Vale arrived late." → name only, no role, no statement → **no portrait**.

**C. Statistic with claimant.**
- "The ministry says output rose from 40 to 200 units a month." → two stated values, source named → bar compare with chip `REPORTED BY THE MINISTRY`, axis from zero.
- "Output rose a lot." → no values → no chart.

**D. Evidence card.**
- "The Brightwater Agency's bulletin called the repair 'only partial'." → outlet + quoted line → source card, `Brightwater Agency` (fixture name), words darken as spoken, highlight on "only partial"; date chip shows the bulletin date.
- "Analysts believe it was partial." → no named source → no card.

**E. Equipment card.**
- "The Mark-9 launcher carries four tubes." → named system (fixture) + attribute → equipment card with one fact; no variant → no range figure.
- "A launcher hit the depot." → generic → no card; footage or no visual.

**F. Conflict.** "The Brightwater bulletin says the depot lost 12 vehicles near Merrow." → candidates: evidence card (source cited), statistic (number, claimed), map (place). Arbitration: evidence wins (rule 1/3); the number is highlighted inside the evidence card with claimant chip; the map is dropped (conflict_lost) unless a chapter boundary follows within 7 s.

**G. Quiet moment.** After a number card (t = 40 s) and a portrait card (t = 52 s), the sentence at t = 60 s names a place in passing: no map, logged `quiet_moment`.

## 11. Decisions needed from the user (10 lines)
1. Condensed + news-serif fonts (Oswald, Source Serif 4, both OFL): approve adding, or keep bundled fonts?
2. Portrait source: licensed/verified lookup per named person (cached once) vs user-supplied only?
3. Equipment photos and diagrams: curate a small approved library once (which sources/licences?) vs footage-only identification?
4. Front-line polygons: allowed only from a named published source you choose; which source(s), or skip this treatment for now?
5. Satellite base map or imagery: add a licensed provider, or stay with the dark/natural map styles?
6. Claimed figures (losses, "destroyed"): always show with a claimant chip, or leave out of graphics entirely?
7. Clean-footage floor (≥ 55 %) and card share (25–35 %): accept, or match reference A's heavier 35–40 %?
8. `ILLUSTRATIVE` trajectories: allowed at all, or maps with pins only?
9. Subscribe/engagement pill: off by default as proposed, or do you want it as a manual option?
10. Representative demo content: fixture text only, or one real script you supply for the demonstration sequence?
