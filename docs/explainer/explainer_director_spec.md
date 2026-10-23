# Explainer director spec (Milestone 4a)

Date: 2026-10-22. Code: `explainer/director/`, `explainer/integration.py`. Architecture B (approved): the director builds the **Hybrid plan** from the narration words and the optional script;
the application would install it through its existing plan path (`_hybrid_set_plan`). No app code is changed in M4a. Deterministic rules, no network, no AI at plan time, no randomness.
Everything marked *(provisional)* lives in `DirectorOptions` and is a proposal from the single 2-minute reference segment.

## 1. Inputs and outputs
Input: `words` = `[(text, start, end)]` in narration seconds (the app's words: lower-case, no punctuation); `script` = text or None; `DirectorOptions`.
Output (`direct()` returns a `DirectorResult`): `plan` (a Hybrid plan dict, schema version 1, accepted by `HybridPlan.from_dict`), `report` (every decision), `problems`, `warnings`.
It never raises: an internal failure returns `plan=None` and the reason, and the caller keeps its current plan.

## 2. Beats
1. Sentences come from `hybrid.narration.build_sentences` (script-aligned when a script exists, else pauses). A sentence longer than `split_over_s` (6.4 s) is split at its longest word gap (at least 0.25 s) near the middle; without such a gap, at the middle word.
2. Sentences are grouped greedily into beats: a beat runs to the next sentence's start (it includes the pause after its last sentence); it closes when it is at least `min_beat_s` long, or at a paragraph end, and a sentence is never added if it would make the beat longer than `max_beat_s`
   (a lone longer sentence is split as above). A final beat shorter than 2 s joins the previous one. Beats tile 0 to the narration length with no gap: each beat starts at its first sentence's start, the first at 0 and the last ends at the duration.
3. **Kind of each beat, in this order:** *map* if a place (below) is spoken inside the beat and the map budget allows; else *archive* if the library has a picture whose subject is spoken inside the beat and the archive budget allows;
   else *board*. Map budget: at most `max_map_share` of the runtime, at most 2 map beats in a row, a map beat at least `map_min_beat_s` long. Archive budget: `max_archive_share`, each picture once.
4. **The plan must contain a map beat** (Hybrid's `validate_plan` requires exactly one camera `start`). If no place qualifies, beat 1 becomes a map beat at `fallback_place` and a warning says the place is arbitrary.
5. **Places:** candidates are the caller's `places` plus capitalised words and runs of up to 3 capitalised words of the script; a capitalised word at a sentence start counts only if it resolves to a country or region ('In', 'Nice', 'Mobile', 'Sale' and 'Reading' all resolve to something) or is capitalised elsewhere; each must resolve with the application's offline lookup (`hybrid.geo.resolve`)
   and be spoken as consecutive narration tokens inside the beat. Without a script only the caller's list is used. A name that does not resolve is ignored and listed.
6. Map beats are built with `explainer.beats.make_map_beat` (fill for countries, markers for the others, `fly_to` for later map beats at the spoken place; the first map beat carries the camera start); archive beats with `make_archive_beat`.
   Board beats are footage beats whose clip is a local explainer clip.

## 3. Board beat authoring (one idea per board; the board is cleared at the next sentence start) — revised by the content-quality gate (2026-10-23)
**Clauses.** Each sentence is cut into clauses: after a word followed by a comma, semicolon, colon or dash of the script (script tokens aligned to the words with difflib; computed on the whole sentence before a long one is split), after a pause of at least 0.25 s, and before a clause word
(`but`, `so`, `because`, `which`, `while`, `when`, `if`, `then`, `until`, `although`, `whereas`, `since`). `and` does not cut ("pipes and pumps").
**Phrase.** A phrase is the best contiguous quote of the narration inside one clause: 2 to 8 words; it must not begin or end on a function word or on a weak word (`almost`, `simply`, `many`, ...), with three exceptions that change the meaning: it may begin with `no`, `not`, `never`, `every`, `each`, `all`, `only`, `more`, `most`, `less`, `few`
(followed by a content word), and a phrase that is a whole clause may begin with a relative or question word (`who`, `how`, `it`, ...). A single word is allowed only if it is a number, a name capitalised in the script or a metaphor keyword. Score = content weight (2 + length/5, +3 digit, +2 script capital, +1.5 keyword; function words 0.4),
+2 if it begins and +2 if it ends with its clause (a complete thought), −0.2 per word above 5; it must fit its card at 40 px or larger (a caption at 44 px or larger in the full band). Capitalisation comes from the script (a sentence-start name that never occurs in lower case and that the offline place lookup knows is capitalised too).
**Cues**, all anchored on narration words (`{"index": k}` inside the beat), never on a guessed time:
- **cards**: up to 1 (sentences under 8 words), 2 (8 to 17) or 3 (18 or more) phrases, best clauses first, shown in time order; icon or prop from the keyword tables (caller's first), role from polarity (loss red, gain green, else blue). Cards go to the lower row first (C3, C4, then C1, C2): that is the height of the narrator's figure.
  One long thought with no second clause (9 or more words) is split into two cards at the middle (each half's best phrase). A phrase of 6 or more words, when another card remains in the sentence, is shown in the caption band instead, revealed word by word (rung 1 by construction);
- **arrow** between the first two cards when a cause or contrast word, or a clause end, lies between them (red for contrast, ink otherwise);
- **header** for a hook or twist sentence: the best window of at most 3 words among words **no card of the sentence already shows** (no header if there is none);
- **leftover caption**: for a sentence of 10 or more words that is not a twist or conclusion, the best leftover thought of 3 to 6 words (not repeating a card), word by word; **twist or conclusion caption**: the best 3-to-6-word window of the last clause, unless it repeats a card or a long-phrase caption already exists;
- **chip** for the first digit token, with its quantity word (`2 billion`, `40 percent`), after the captions: the caption band keeps its legible size, and a chip that finds no free slot is dropped and listed (the number is still in its card's text);
- **clear** anchored on the first word of the next sentence of the same beat; **narrator**: §5.
Every board beat is dry-built (resolution plus layout, no encoding). A cue that produces a problem (no free slot, text too long, collision) is dropped and listed; the beat is rebuilt until it is clean (at most 4 rounds).

## 4. Story structure (labels, never invented text) — revised by the content-quality gate
Per sentence, first match wins: `hook` (the first sentence: **by position, reported as such**), `question` (a script sentence ending in `?`, or, without a script, a sentence that starts with a question word; a question can also be the hook, and the report counts it), `twist` (a **contrast marker**: `but`, `however`, `yet`, `except`, `actually`, ... starting
the sentence or within its first four words; the report names the marker; it does not claim a plot twist), `conclusion` (`therefore`, `finally`, `remember`, `overall`, `ultimately`, `in the end`, `that is why`, `to sum`, ..., or a sentence-initial `so` in the last quarter of the narration), else `explain`.
**The last sentence is no longer labelled a conclusion without such a cue**; the sentence then stays `explain`, the conclusion is reported absent, and no conclusion treatment (pose, caption) is applied. The report gives, for each of hook within 30 s, a question within 120 s, a twist, a conclusion: present or absent, the sentence, the trigger and whether it came from a cue (`explicit`).
Nothing is added to satisfy the structure.

## 5. Narrator and pacing
- The narrator runs in **runs of consecutive board beats**: the first beat of a run shows it with an enter slide, interior beats show it settled (`enter` and `exit` `none`, continuing the previous pose), the last beat hides it with an exit slide.
  Runs are chosen to keep the share near `narrator_share` (0.45) and the longest absence at most `narrator_every_s`; a run lasts at least 2 beats unless the narrator is already past half the runtime; beats of other kinds are absences.
- Poses by sentence label: hook surprise, question think, twist surprise, explain explain or point (alternating), conclusion idle; a pose change needs the state machine's spacing (12 frames after the enter, 4 after a pose); otherwise it is skipped and listed.
- **Static time repair:** if a board has no change (cue appearance, clear, narrator pose, and every word a words-mode caption reveals) for more than `max_still_s` (2.0 s), a card with the best phrase of the words **inside the gap that no card, header or caption already shows** is added (icon and role from the same tables; words stay contiguous), else a caption; when nothing new is being said (a pause, or words already shown) and the narrator is on screen, a pose change in the middle of the gap; up to 3 repairs per beat; the remaining gap is reported. A map beat is repaired with whole-phrase caption layers of 2 to 6 words that neither begin nor end on a function word (anchored at least 2.6 s before the beat ends, so the application's editorial check can read them; a gap near the end of a short map beat usually cannot be repaired); camera drift is not counted as a change; an archive beat counts as one change at its start (Ken Burns motion is not counted).
- Change density, shot-length statistics, narrator share and longest absence, and the layer mix are **computed from the produced plan and reported** against the scorecard targets; they are not forced.

## 6. Recurring metaphors and colour roles
`metaphors` and `roles` tables (caller's entries first). A keyword always yields the same asset id and the same role anywhere in the video; the report lists, per keyword, the occurrences and asset ids, and a checker fails if one keyword ever maps to two assets or two roles.

## 7. Gates (a plan that fails a gate is repaired or reported, never half-installed)
`validate_plan` (0 problems), `explainer.beats.check_plan` (0 problems; board clips count as footage whose subject is the beat's own key phrase), the application's editorial validator `hybrid.validate` (0 errors; its warnings are returned), every board clip built with non-strict cues and an empty problem list after dropping,
every asset a local file, no `stock_*`/`flow_*`/`youtube_*`/URL reference. If the plan still fails: `plan=None`, the problems are returned, nothing is installed.

## 8. Cache and reproducibility
Board clips are written to `work_dir/explainer/board_<sha256[:16]>.mp4`; the key covers the explainer version, the narrator asset manifest hash, the cues, the beat times, the words of the beat, the dissolve and the geometry. An existing non-empty file is reused.
The same inputs give the same plan JSON byte for byte and the same clip bytes.

## 9. Not in M4a
No app, spec or settings change (the exact diff is delivered separately for approval), no UI, no per-project persistence, no cartoon beats, no narrator over a rendered map, no AI authoring, no cross-OS run.
