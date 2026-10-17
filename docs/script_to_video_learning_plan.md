# Script → Video without AI: a planner that learns from users' CSVs

Status: PLAN ONLY (2026-10-15). Nothing below is built yet.

## Goal

The user gives a **script and a voiceover**, and the tool makes the plan (the CSV) itself, then renders.
- No Gemini, no Claude, no paid API, no cost per video. Everything runs on the user's PC.
- The tool learns from the roughly **50 CSV videos users make every day**. Every video that renders successfully
  becomes a worked example: this sentence got this shot, this layout and this search, and stayed on screen this long.
- The output is the **same CSV each style already imports**, so the importers, renderers, caches and QA all stay as
  they are. The planner just writes the CSV for the user.

## Why this works (and what it can't do)

- One 10-minute video is about 100–200 CSV rows, so 50 videos a day is about **5,000–10,000 sentence→visual examples
  a day**. That's plenty for *matching* (find past sentences like this one) and *statistics* (how long each style
  holds a shot, which layout follows which).
- It doesn't invent new ideas. It reuses and adapts what real users chose for similar sentences. Image prompts are
  adapted from past prompts (the subject words get swapped), not written fresh.
- The quality floor is the existing importer, plus repair, plus the "no still screens" checks. A weak match can make a
  plain shot, but it can never stop a render.

---

## Phase 0 — Know which styles people use (small, do first)

`video_generation_events.render_engine` only says `normal / hybrid / starmap / pakmap / weather`. Overscaled, Exp Solar
and Enoch Template all render under `normal` (app.py:13637).

- Migration: add a `composition_style text` column to `video_generation_events`.
- `GenerationTracker.start()` sends the style the user picked (overscaled, exp_solar, enoch_template, normal, …).
- After 2–3 days, check the per-style counts. **The style with the most videos gets the planner first.**

## Phase 1 — Consent + collection (the urgent part: every day without it loses ~50 videos)

### 1a. Consent
- Add a "Help improve automatic planning" paragraph to the About & Ownership terms (`licensing/terms.py`), and bump
  `CURRENT_TERMS_VERSION` so existing users see it once.
- Settings > General gets a **"Share my scripts and plans to improve the tool"** switch, **on only after the user
  agrees**. They can turn it off any time.
- "Delete my shared data" button: calls an RPC that removes that user's files and rows.

### 1b. What is uploaded (text only, zipped)
After a render **passes final validation** (the same place `GenerationTracker.complete()` counts a video), one JSON
record, gzipped, about 30–40 KB:

| Field | Source |
|---|---|
| style, app_version, video duration | already known at completion |
| script text | `ProjectWorkspace.script_path` |
| **first** CSV (as imported or generated) | snapshot saved at import time (new: `csv/_first_import.csv`) |
| **final** CSV (as rendered) | the style's CSV in `csv/` (or the Hybrid/StarMap/pakMap plan) |
| voiceover word times | the saved transcript (e.g. `_work/voiceover_words.json`) when one exists |
| hand edits | per-scene list of changed source / clip / prompt / layout (from scene state) |

**Never uploaded:** audio, video, images, API keys, or local file paths. Paths like `D:\clips\a.mp4` in local-video
CSVs are replaced with just the file name. A record over 2 MB is skipped.

The **first vs final CSV** is the most valuable part: it shows exactly where users had to fix the plan.

### 1c. Where it goes (free Supabase plan)
- A **Storage bucket** `training-records` (private) in the existing project, with files at
  `<user_id>/<generation_id>.json.gz`. Storage has its own 1 GB limit, separate from the 500 MB database, so it can
  never fill the database that sign-in and licensing depend on.
- A tiny index table `training_records` (one row of about 300 bytes per video: user_id, generation_id, style,
  duration, size, created_at). That's about 5 MB a year.
- RLS: a signed-in user can **insert** only their own rows and files. Nobody can read through the app. Only we can
  read, with the service key, from our machine.
- Upload runs on a background thread and reuses the pending-file retry of `generation_tracking.py`. It never slows down
  or fails a render.
- Budget: about 50–60 MB a month zipped, so 1 GB lasts about 1–1.5 years. After records are learned into the planner,
  the raw files older than 6 months can be deleted to stay free. If needed later: Pro at $25/mo.

## Phase 2 — Corpus tools (runs on our machine, not in the app)

`scripts/corpus_pull.py`: download new records with the service key into a local `corpus/` folder.
`scripts/corpus_build.py`, per style:
1. **Filter:** only validated renders, scripts of at least 150 words, no duplicates (same script hash).
2. **Align:** match every CSV row to its sentence(s) and its time span in the voiceover.
3. **Score each row:** a row the user kept unchanged is a *good* example, and a row the user replaced is a *bad*
   example. The replacement is the good one.
4. Output one file per style: `planner_packs/<style>.sqlite` (the learned planner, described below).

Rebuild weekly at first, then monthly.

## Phase 3 — The learned planner (offline, no neural network)

Per style, the pack holds:

| Part | What it learns | Used for |
|---|---|---|
| **Example index** | every good row: sentence, keywords, places/people/numbers/dates, the row it got | find the 5–10 most similar past sentences (BM25 keyword search) |
| **Shot rules** | which kind of sentence gets which asset type / layout (a number → stat card, a place → map, a list → checklist, a person → portrait…) | the base choice when matches are weak |
| **Rhythm** | seconds per shot, shots per sentence, how often each layout appears | cut timing and mix |
| **Sequence** | which layout tends to follow which (a transition table) | variety, so it never makes 5 of the same in a row |
| **Search/prompt templates** | past searches and prompts with the subject words marked as slots | fill a new row's search/prompt with this script's subjects |

The steps for a new script:
1. Split it into sentences and time them from the voiceover (the existing transcription).
2. For each sentence, extract its features (keywords, entities, numbers, places using the map gazetteer we already
   have).
3. Look up similar past sentences, which vote on asset type/layout. The shot rules and sequence table break ties.
4. Fill searches/prompts from the templates, using this script's own subjects.
5. Set cut times from the rhythm stats, aligned to word times.
6. Write the style's CSV, then run **its own importer and validator** (overscaled_csv, exp_solar_csv,
   pakmap.schema.parse_csv, hybrid.beat_csv.import_beats, starmap load_plan, …), then local repair, then the
   no-still-screen and variety checks.
7. Show the CSV in the app so the user can edit it before rendering. Those edits go back into Phase 1.

## Phase 4 — Prove it before users see it

- **Hold-out test:** run the planner on 100 past scripts it never learned from and compare with what users made:
  asset-type agreement %, layout mix, average shot length, and the share of rows that a user would have changed.
- **Render test:** 5 real scripts per style, rendered, with ffmpeg freeze-detect and a look by you.
- **Gate:** a style ships only when its renders have no frozen stretches of 5 s or more, pass the importer with 0
  errors, and you approve them.

## Phase 5 — In the app

- In each style's panel: **"Make plan from script"** (next to the CSV import). It writes the CSV to the same place an
  imported CSV goes, so everything after it is unchanged.
- The planner pack ships **inside the app update** (not downloaded from Supabase, which protects the 5 GB/month
  egress).
- A style without a pack yet shows "Not enough examples yet. Import a CSV."

## Rollout order

1. Phase 0 + Phase 1 (collection), as soon as possible.
2. Phases 2–3 for the **top style by volume**, built first from CSVs already on this PC and then from the collected
   data.
3. Phase 4 gate, then Phase 5 for that style.
4. Repeat for the next styles. Weather already has a rules-based script-to-video and can later be improved using the
   same records.

Rough timing: collection works within days. The first style's planner is useful at about 1,000 of its videos and good
at about 3,000 (that depends on how many videos per day that style gets).

## Open questions for you

1. Should the share switch be **on by default after agreeing to the terms** (more data) or **off until the user turns
   it on** (more private)?
2. Is the existing Supabase project fine for the Storage bucket, or do you want a separate one?
3. Do you have past CSVs + scripts on this PC (or from users) we can use to build and test the planner before collected
   data arrives?
