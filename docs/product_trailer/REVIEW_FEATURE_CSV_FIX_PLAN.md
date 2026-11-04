# Review film with a feature CSV: fix plan

Based on the `tecg` render (2026-11-03), reviewed in `TECG_RENDER_REVIEW.html`. Nothing has been built yet.

## Root cause (confirmed in code)

Here's how the Review path read the CSV:

1. `ui/product_trailer_section.py` `on_generate` sends the CSV path to `studio.plan_film("Review", csv=…)`.
2. `review.review_source()` sees an empty script box and calls `review.csv_to_script()` on the CSV.
3. `csv_to_script()` expects a *narration* CSV. It looks for a text, line or narration column in the **first row**. Here the first row was `#product,Galaxy S27 Ultra,…`, so no column matched and it fell back to "first cell of every row is a line". The script became `#product / #disclaimer / order / 1 … 9`.
4. Those 12 "lines" never appear in the voice, so `voiceover.align_lines()` returned `ok=False` and split the 214 s evenly by word count. Each one-word line got about 17.5 s.
5. Mixed style then sent those 12 lines to `llm_director.llm_direct` (Gemini). With no real content to go on, it invented topics and numbers.
6. The `#product` line was never read on this path (`csv_io.parse_csv_text` is only used by Trailer and Reveal). So the product name is `""`, cards say "Phone 1", and the lineup uses default colours.

## Fix steps (smallest first, each with a synthetic test)

**Step 1. Recognise a feature CSV in Review mode** (`review.py`, `studio.py`)
- Add `review.is_feature_csv(text)`: true when the CSV has `#product`/`#disclaimer` lines, or a header with `feature` and `value`, and no narration column.
- `csv_to_script()` must never turn `#…` lines, a header row or bare row numbers into narration lines.
- Test: the tecg CSV gives no script lines and is flagged as a feature CSV.

**Step 2. The voice is the script when no script was given** (`studio.plan_film`, `voiceover.py`)
- Review + voiceover + no pasted script (or only a feature CSV): build the lines from the Whisper words, splitting into sentences on pauses longer than about 0.5 s and on a word-count limit.
- Alignment is then exact (`ok=True`), so scenes follow the narrator and subtitles show the spoken words.
- Test: fake words for 3 sentences give 3 lines with the right start and end times, and no even split.

**Step 3. Feature rows become facts on the right sentence** (new small helper in `review.py`)
- Read the feature CSV with `csv_io.parse_csv_text` for the product (name, colour) and the feature rows.
- Match each row to the first sentence that mentions it. Use the value with number and unit forms (`200MP` ↔ "200 megapixel", `5700 mAh` ↔ "5 700", `60W` ↔ "60 watts"), then the feature or kicker word (`privacy`, `snapdragon`).
- That sentence gets a CSV-owned card (`_own=True`) showing kicker / value / sub, with the row's `look` (`wash:red`, `badge`, `horizon`). Rows with no match go into quiet stretches in CSV order.
- Product name and colour come from `#product` when the phone box is empty. The disclaimer comes from `#disclaimer` when the UI one is the default.
- Test: the tecg CSV plus a fake transcript puts 200MP, 5700 mAh, 60W, Privacy and Ultra on the sentences that say them, and the product name is "Galaxy S27 Ultra".

**Step 4. No Gemini when a CSV is supplied** (`ui/product_trailer_section.py` `_ai_args`, `studio.plan_film`)
- Following the "CSV means no Gemini" rule: when `o["csv"]` is set, `llm_run` is not passed. The built-in `director.auto_direct` plus the CSV cards (step 3) direct the film.
- Stock search terms come from the CSV and the product name ("Galaxy S27 Ultra back camera"), not from an AI.
- Test: `plan_film` with a CSV never calls a fake `llm_run`.

**Step 5. Fact gate: nothing on screen that isn't in the voice or the CSV** (`review.py`, before the spec is written)
- Any number, chip name or benchmark on a card must appear in the transcript or the CSV. If it doesn't, drop the card's number, or swap the card for a captionless 3D shot.
- `fold` / hinge shots only when the product or transcript says fold, flip or hinge.
- Placeholder labels ("Phone 1") are replaced by the product name, or dropped.
- Test: a planted `SNAPDRAGON 8 GEN 3`, `7200 pts` or `fold` with no support is removed.

**Step 6. No long still cards** (`review.plan_review_timed` `hold_copy`)
- A held card is capped at about 6 s. After that, cut to a moving 3D or footage beat. The same card is never repeated across 4 shots.
- Test: one 18 s line gives at least 3 different visuals.

**Step 7. Disclaimer end card wraps** (`render.py`, `pt_card`)
- Wrap long lines to the safe width and shrink the font if needed.
- Test: a 200-character disclaimer fits inside the frame width.

## Out of scope for now
- Thin footage (only one clip found). Better search terms come from step 4. The wider footage pool is a separate pass.

## Check before done
- Run only the touched tests (`test_product_trailer_*`).
- Make sure the old flows still work: a pasted script, and a narration CSV with a `text` column. Their tests must pass unchanged.
- Re-run tecg only when asked.
