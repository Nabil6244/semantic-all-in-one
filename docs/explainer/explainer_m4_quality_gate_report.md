# Content-quality gate report (after M4a)

Date: 2026-10-23. Scope as approved: fix the key phrases, improve board composition and density with the existing M1 to M3 components, report story structure honestly, re-run the same five topics, compare before and after, keep determinism and every earlier check.
**Nothing committed, staged or pushed. `app.py`, the spec, `settings.json`, protected files, the manifest, installers and UI were not touched; `m4_app_patch.diff` was not applied (it still applies cleanly); M4b was not started.**
Offline, one Mac. The five topics, their word times (made by rule) and their scripts are the same as in M4a; **the narration is not a human voice, the offline map has no imagery, and I am the only reviewer of how the boards look: there are no independent ratings.**
Evidence: [m4_quality_evidence/](m4_quality_evidence/) (before and after contact sheets per topic, phrase listings per sentence, every number as JSON). Spec updated: [explainer_director_spec.md](explainer_director_spec.md) sections 3 to 5.

## What changed (only `explainer/director/` and its checks; no board, narrator, caption or plan-builder code)
1. **Clauses.** Sentences are cut at the script's commas, colons and dashes (aligned to the words), at pauses of 0.25 s or more, and before clause words (`but`, `so`, `because`, `which`, ...). Punctuation is computed on the whole sentence before a long one is split, so split parts keep it.
2. **Phrases.** A card, header or caption is now the best contiguous quote of one clause, 2 to 8 words, never beginning or ending on a function or weak word (allow-listed openers that change the meaning: `no`, `not`, `every`, `only`, `few`, ...; a whole clause may open with `who`, `how`, `it`). It must fit its card at 40 px or larger and a caption at 44 px or larger.
   Before, the rule took the best run of up to 4 non-function words, which is how "almost", "go", "hand across", "water tore" came about.
3. **Density and composition (existing components only).** Up to 2 or 3 cards per sentence by length; one long thought is split into two cards as its halves are spoken; a phrase of 6 or more words goes to the caption band and is revealed word by word (a change on every word); cards go to the lower row first, level with the narrator's figure; headers never repeat words a card shows; chips carry the whole quantity (`2 billion`); repair cards never repeat shown words and are always contiguous quotes, with a narrator pose change as the repair when nothing new is being said; map caption repairs are 2 to 6 words with clean edges.
4. **Story labels.** The last sentence is **no longer labelled a conclusion by position**; a conclusion needs a cue (`in the end`, `that is why`, `the lesson`, `therefore`, ... or a sentence-initial `so` in the last quarter). `twist` is documented as a **contrast marker**, not a plot twist; the hook is reported as positional. The report records for each label whether a cue produced it.
5. Sentence-start names the offline lookup knows (for example "Rome") are capitalised, and 'In', 'Nice', 'Mobile', 'Sale' stay out (as in M4a).

## Before and after, five topics (hard cuts; the dissolve setting changes only clip lengths)
Objective proxies, one function for both runs (they are not a judgement of meaning): **mean words per text** 2.0 to 2.4 → 4.8 to 6.2; texts that end on a function or weak word 4 of 94 → 0 of 63; texts that begin on one (not allow-listed) 8 → 0; single-word texts 27 → 0; **content-word coverage** (share of a sentence's content words that appear in a card, header or caption anchored inside it) 0.47 to 0.72 → 0.79 to 0.90; sentences with no text 1 (printing, the archive beat) → 1 (printing) plus 1 in inflation (its opening map sentence).
Every text is a contiguous quote of its own beat's narration (checked for all 63: 0 exceptions), none is repeated inside a beat, and none starts or ends on a function word except the allow-listed openers.

| Topic | Texts before → after | Mean words | Coverage | Change windows (target 95%) | Longest still gap (target ≤ 3 s) | Narrator share (35 to 60%) / longest absence |
|---|---|---|---|---|---|---|
| aqueducts | 27 → 17 | 2.1 → 5.7 | 0.72 → 0.89 | 95.8% → **100%** | 2.35 → **3.13 s (fails)** | 51% → 51% / 17.1 → 13.3 s |
| coffee | 19 → 12 | 2.2 → 5.8 | 0.68 → 0.90 | 100% → **100%** | 1.88 → 2.66 s | 58% → 48% / 5.9 → 9.6 s |
| inflation | 19 → 13 | 2.4 → 5.9 | 0.69 → 0.87 | 94.4% → 94.4% (**fails**, 17/18) | 1.88 → 2.55 s | **63% (above 60%) → 51%** / 4.8 → 9.0 s |
| printing | 16 → 12 | 2.3 → 4.8 | 0.55 → 0.78 | 93.8% → 93.8% (**fails**, 15/16) | 1.86 → 1.76 s | 48% → 48% / 8.8 s |
| glaciers | 13 → 9 | 2.0 → 6.2 | 0.47 → 0.79 | 88.2% → **76.5% (worse, fails, 13/17)** | 1.96 → 2.31 s | 54% → 54% / 10.1 s |
**Failures against targets, stated plainly:** the 95% change-window target is met by 2 of 5 topics before and after (aqueducts and coffee); **glaciers got worse** (two consecutive map beats whose short windows cannot take a caption, and one board gap of 2.3 s with nothing new being said); inflation and printing stay just under 95%; the 3-second still-time target now fails in aqueducts (a 3.13 s gap, in which the narrator is absent and the words are already shown). The narrator-share target is now met by 5 of 5 (it was 4 of 5). Fewer, longer texts mean fewer separate appearances, which is the cost of fixing fragments; the word-by-word captions give back much of it.
Map and archive beats get no extra changes (camera drift and Ken Burns motion are not counted); a map or archive stretch longer than 2 s without a layer is a window miss by construction.

## Phrases, in context (examples; full listings per sentence in the evidence folder)
| Sentence | Before | After |
|---|---|---|
| "Engineers measured the slope with almost no tools, a drop of only a few centimetres in every hundred metres." | engineers measured / few centimetres / almost / hundred metres | card "engineers measured the slope with almost no tools" + caption "only a few centimetres in every hundred metres" |
| "But if the slope was too steep, the water tore the stone apart." | header "water tore", card "slope", caption "tore the stone apart" | card "slope was too steep" → arrow → card "water tore the stone apart" |
| "So the principle has not changed: water still travels downhill, and every system we build is a way of persuading it to go where we need." | travels downhill / changed water / persuading / caption "go where we need" | card "principle has not changed" → arrow → card "water still travels downhill"; card "persuading it to go where we need" |
| coffee: "But the Dutch smuggled a single plant to their islands, and the monopoly broke." | Dutch smuggled / islands and the monopoly broke / monopoly broke | card "Dutch smuggled a single plant to their islands" → arrow → card "monopoly broke" |
**Remaining weaknesses I can see:** phrases are still extractive quotes, so a few read oddly ("end the ice is a clock" for "In the end the ice is a clock", "build is a way of persuading" was replaced but "Colombia were growing coffee on steep mountain" is cut by the 8-word limit); "monk many months to copy" drops "took a"; no phrase is summarised or reworded, so the board repeats the narration rather than explaining it. A language model or a human-written plan loaded through the same gates is still the way to real storytelling.
Composition after the change (from the contact sheets): text is larger and readable (cards 48 to 52 px, captions 48 px, minimum 40 px; at least one 36 px caption in the first attempt was removed by the 44 px rule); cards sit beside the narrator; but boards remain **sparse**: one or two cards in a large grey area, the upper half of the board is mostly empty, and the caption band is small compared with the cards. I did not add a new card type or layout.

## Story structure (reported, not invented)
| Topic | Hook (position) | Question | Contrast marker ("twist") | Conclusion (cue) |
|---|---|---|---|---|
| aqueducts | 0.5 s | yes, 0.5 s (script `?`; also the hook) | `but` 22.7 s | `so` (sentence-initial, last quarter) 40.5 s |
| coffee | 0.5 s | yes, 0.5 s | `but` 15.2 s | `so` 30.7 s |
| inflation | 0.5 s | yes, 0.5 s | `but` 16.5 s | `the lesson` 27.7 s |
| printing | 0.5 s | **none in the script** | `but` 20.5 s | `so` 28.3 s |
| glaciers | 0.5 s | **none in the script** | `but` 17.7 s | `in the end` 28.6 s |
Before the change, aqueducts, coffee and printing had their last sentence labelled a conclusion by position; all three do in fact open it with `So`, which is now the cue, and a script without such a cue gets no conclusion (tested with a short script: conclusion absent, twist absent; adding "So the cycle never ends." makes it explicit). Questions are absent in printing and glaciers and nothing was added to cover that. A contrast marker is not a plot twist: "But the Dutch smuggled a plant" is a turn, "But the cause was simple" is only a contrast.

## Scorecard (my own numbers; M-rows have no ratings)
| ID | Result before → after (5 topics) |
|---|---|
| T01 layer mix | board 70 to 90%, map 10 to 30%, archive 12% in one topic; **no cartoon beats exist, so the 33% cartoon share is unmet by design** |
| T02 shot length | median 4.7 to 5.1 s (unchanged), 100% of shots 2 to 8 s (unchanged) |
| T03 change density | 2 of 5 meet 95% before and after; glaciers worse (see table) |
| T04 still time | 4 of 5 within 3 s after (was 5 of 5); aqueducts 3.13 s |
| T05 narrator | share 48 to 54% (5 of 5 in 35 to 60%; was 4 of 5); longest absence 9 to 13 s (limit 30 s) |
| T07 cuts at sentence starts | 89% to 100% of beat starts within 0.3 s of a script sentence start (unchanged; target 70%) |
| T08 latency | cards 0.1 s after their first word, captions on each word (0 s); unchanged from M1 to M3 measurements |
| T09 caption policy | captions are 3 to 8 words (100% within 8); word-by-word reveal; typed mode unused here |
| T10 palette and type | board #C0C0C0 and role colours by construction; text 40 to 52 px; not measured on a rendered frame |
| T12 metaphor and role continuity | one asset and one role per keyword in every topic (5 of 5); recurrences per 10 minutes 74, 33, 98, 73 and **0 in glaciers** (fewer keyword icons because phrases are now sentences' main clauses) |
| T13 structure | hook 5/5 (positional), question 3/5, contrast marker 5/5, explicit conclusion cue 5/5 |
| H07 overlap | the dry build gate (resolution and layout) drops what collides: 2 chips were dropped when the caption band was used (the number stays in its card), 0 plan problems; M3's per-frame collision check was not repeated for these plans |
| M01 to M05 | **not rated**; visual quality is not claimed as proven |

## Regression and protection
- `verify_m4`: **160 of 160 checks** (149 old + 11 new content rules: contiguous quotes, clean edges, no repeated card text, long phrases as captions, lower-row cards, whole-quantity chip, no invented conclusion, `so` cue, positional hook, comma clause breaks, no phrase across a break). The five topics still produce valid plans in both dissolve settings, replay to identical clip bytes, and render through the unmodified `generate_hybrid_video` offline with 0 network attempts.
- `verify_m1` (21), `verify_m2` (41), `verify_m3` (115): all true, with cue rows, narrator state-change frames, caption frames, clip SHA-256s and asset hashes **identical** to their evidence; `verify_builder` and `verify_splice` identical (board clip bytes and the splice render byte-identical).
- Official guard `test_weather_isolation` OK before and after. **Caveat unchanged:** the manifest is dirty from another session, so this shows no change relative to that manifest, not relative to HEAD; I did not touch it. `git status`, the tracked diff, the off-mode snapshot, and the hashes of `app.py`, the spec and `settings.json` are identical before and after; `m4_app_patch.diff` still applies cleanly; no bytecode in `explainer/`.
- Changed files this step (all untracked, under `explainer/` and `docs/explainer/`): `director/{compose,lexicon,pacing,plan,segment}.py`, `spike/verify_m4.py`, new `spike/quality_gate.py` and `spike/quality_compare.py`, the director spec, this report and the evidence folder.

## Open issues
Boards are sparse and text-only; quotes can read oddly at clause edges; map and archive beats add no changes; glaciers' change density is worse; one still gap above 3 s; keyword icons recur less; real-voice word times, cross-OS runs, packaging and the GUI are untested (unchanged from M4a); Inter's licence is unverified. The authored text is better but is still not storytelling: judging that needs independent reviewers.
