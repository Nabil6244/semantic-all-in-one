# Enoch Template — how the style works

A separate, evidence-first style for documentaries about ancient texts (first subject: 1 Enoch), built from a reverse-engineered
reference video. It is chosen on its own card in the style picker or as the project's style at creation; it is never
auto-detected. Book of Enoch (`styles/book_of_enoch.json`) is a different style and is unchanged.

## What turns on when a project uses it

"On" means the project's `video_style.style_id` is `enoch_template`. Leaving the card restores the style the project had before.

| Stage | What happens | Where |
|---|---|---|
| Research | "Copy research prompt" → paste into any AI → save its JSON as `state/enoch_template/claims.json` | `composition_styles/enoch_template_research_prompt.txt` |
| Script | "Copy script prompt" (fills in the ledger) → save the script, and the script map as `state/enoch_template/script_map.json` | `composition_styles/enoch_template_script_prompt.txt` |
| Visual plan | "Copy the CSV prompt" copies this style's CSV prompt (same CSV format as Normal) | `composition_styles/enoch_template_csv_prompt.txt` |
| Import / plan | the refine pass runs on both planning paths (CSV import and the Visual Director plan) | `ancient_texts/plan.py`, `integration.refine` |
| Editing | hard cuts dominate, low SFX, no ambience bed (until the reference's music/SFX are confirmed by listening); no overlay drawn over a card | `integration.smart_editing_settings`, `drop_graphics_on_cards` |
| After render | audio finishing (−16 LUFS ±1.5, true peak ≤ −1 dBTP, video stream copied) and the QC report | `ancient_texts/audio.py`, `qc.py` |

Nothing in this style calls an AI provider, Flow or the network on its own. The refine pass can only remove Flow work.

## Rules

**Required (hard failures):** no claim marked documented without a source and locator that support it; no source recorded as
not found; no interpretation or dispute stated as settled fact; no quotation card without a quotation a person verified against a
named edition and locator; no credential printed on a card; no picture described as an avoided subject; no AI run over the
limit when a relevant non-AI picture exists; true peak ≤ −1 dBTP; audio and video the same length; no paid or network call.

**Style targets (soft deviations, compared with what the script asks for):** AI share ≤ 12% of visual scenes (the reference
shows about 8%; the value is `selection_rules.max_ai_share` in the style file, a ceiling, never a quota), at most 2 AI scenes in a
row; median shot 4–6 s and none over 9 s; cards 8–35% of scenes, statement cards ≤ 15%; context shots ≤ 15%; loudness −16 ±1.5 LUFS.

**Review (a person decides):** every interpretation and dispute, every unreviewed claim, every AI reconstruction, every
context shot, whether each picture really shows what its narration names, and whether the story is clear and fair. The QC report
never calls a video equivalent to the reference.

## Visual mix (ancient_texts/visual_mix.py)

Every scene gets one primary type, by precedence: unresolved (no installed picture; never counted as a visual) → AI
reconstruction (asset type or file provenance, whatever the search words say) → text card (statement, section break) →
map/diagram (map, comparison, cited source card) → historical artwork → manuscript/document (incl. a framed photo of one) →
real-world/location. Each also gets its evidence relationship: direct evidence, illustration, interpretation (a text card
carrying an interpretive or disputed claim), reconstruction, or narration text.

The **planned** mix (plan_report.json, after the refine pass) and the **actual** mix (qc_report.json, from the files really in
the Images folder plus their provenance: the download manifest and `state/enoch_template/asset_provenance.json`) are reported
separately. The actual mix reports missing files (hard), AI files labelled as anything else (hard), identical files on
several scenes, cards replaced by hand, and files of unknown origin.

Targets are soft and live in `reference_profiles/enoch_ref_01.json` → `visual_mix`: standalone text cards 15–20% (warning
above 25%, strong warning above 30%), AI ≤ 12%, and a warning for 2+ text cards in a row (3+ called out). They are reported,
never met by inserting pictures.

Fallback order when a scene needs a different picture: existing evidence (the document or place it names, then a historical
depiction of it) → an explanatory graphic (a verified quotation, else a cited summary of a documented claim with its locator)
→ a labelled reconstruction only where the plan already keeps one within the ceiling (an AI row the asset mix removed is not
restored: that could create Flow work) → a text card of the narration's own words. Never unrelated stock.

## The refine pass, in order

1. The CSV's own non-AI source wins: where an earlier step (the asset mix's provider quotas, or the CSV-to-plan conversion that
   turns map/archive/commons rows into stock video) replaced it, it is restored. AI rows are never restored.
2. Every search must be tied to its narration: an unrelated, avoided or generation-prompt-length query is re-aimed at what the
   narration names (a real artwork, a document or place motif, a style search term). An artwork or document is searched as a
   still. A scene never repeats its neighbour's search. With nothing to aim at, a generation prompt becomes a statement card of
   the narration's own words; anything else is flagged for review, never filled with unrelated stock.
3. AI ceiling and run limit, by replacing the AI scenes that least need reconstruction with, in order: a real artwork → a real
   document/place search → a verified-quotation card → a requested card → a statement card. If none fits, the scene stays AI and
   the report says the ceiling was not met and which scenes had no alternative.
4. Motifs (the pack's anchor images) may return deliberately; other repeats within 3 minutes are reported.

Cards are written as the scene's numbered file (`NNN.png`) in the project's Images folder and the scene becomes `local`. A card
is never installed next to another file for the same scene (that would let the renderer pick a stale file): the conflict is
reported instead.

## Files a project gets (`state/enoch_template/`)

`claims.json`, `script_map.json`, `cards.json` (optional inputs) · `plan_report.json` (reasons, AI share and its denominator,
every change and why, every issue) · `sources.md` (the verification sheet; "unreviewed" where nobody checked) · `qc_report.json`
(after a render) · `previous_style.json` (to restore on leaving the card).

## Known limits

- At download time only the existing avoided-subject gate runs. Whether the downloaded picture really shows the narrated
  subject is checked afterwards from the provider's own description (`qc.check_acquired_assets`) and flagged, not swapped.
- Cut timing stays on word onsets (the reference cuts about 0.5 s earlier, inside the pause). Moving cuts needs the shared
  alignment/timeline code (`video_generator.py`, protected), so it is reported, not implemented.
- Music, ambience and SFX policies are conservative placeholders until a listening pass of the reference.
- Cards draw Latin-script text (with accents). Scripts the fonts cannot draw (Ge'ez, Hebrew, Greek polytonic …) are refused with
  a clear message rather than drawn as boxes.
- The research watch-list in `ancient_texts/packs/enoch.json` is a list of open questions, not findings.
