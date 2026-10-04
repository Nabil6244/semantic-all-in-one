# Hybrid CSV import

## Beat CSV (recommended)

`composition_styles/hybrid_beats_prompt.txt`: give it and your script to an AI (for example Claude). It writes the plan itself, one row per
beat, layer, photo card and clip, timed by the narrator's own words. **Hybrid panel > Plan / CSV > Browse** recognises it by its header (`beat,row,...`),
reads the narration, and loads it **as written**: nothing is re-cut or dropped. Camera moves come from each map beat's place, as for an AI plan.
A problem names its row ("row 14: vo_anchor 'the capital' is not in the narration"). No Gemini or Groq call is made (Repair errors is optional).

**Open plan file** writes the current plan (however it was made) as `hybrid/hybrid_beats.csv` in seconds and opens it in your spreadsheet app;
edit, save, and **Browse** to it again: it loads exactly, without reading the narration again.

## Hybrid CSV (pakMap rows)

A CSV written to `composition_styles/hybrid_csv_prompt.txt` (give that prompt and your script to any AI) loads straight into Hybrid mode:
**Hybrid panel > Load CSV…** (the voiceover must be chosen first: the rows are tied to the narrator's own words).

## What the importer does

1. Reads the CSV with pakMap's own reader and resolves every anchor and every layer's time with pakMap's own compiler, so a row means exactly
   what it means in PakMap.
2. Re-cuts that timeline as a Hybrid plan:
   * a run of full-screen clips (`media_full`) becomes a **footage beat** (clips that follow each other are one beat with several clips);
   * the stretches between them become **map beats**; a map beat that has a photo card (`pip`) is a **map + card** beat, and a second card far
     enough from the first gets a map beat of its own;
   * titles, markers, zone labels, fills, routes, number chips and captions go to the map beat they fall in, keeping the CSV's own times and
     how long they stay;
   * camera rows become camera steps: one `start`, moves only on the map (never under footage), spaced so they do not overlap.
3. The result is an ordinary plan. The footage and cards appear in the Visual Tab, the validator and "Repair errors" apply, and rendering uses
   the Hybrid behaviours a plain PakMap import does not get: the map and its animations freeze under footage and return exactly as they were,
   footage dissolves in and out, a short clip slows down instead of repeating, stills drift slowly, and clips are cut into frames only when needed.

## What it changes, and tells you

* A layer that would appear **under** footage is moved to just after the footage (noted).
* A camera move under footage waits until the map returns; one with no room in its beat is left out (noted).
* A CSV with no camera `start` gets one on its first place (noted).
* A second card too close to another is left out (noted).
* Layers Hybrid cannot draw yet (`dots`, `filmstrip`, `sticker`, `value_overlay`, `ghost_shape`, `streak`, `cluster`) are left out (noted).
* Problems in the CSV itself (a phrase the narrator never says, a bad column) stop the import and name the row; the current plan is kept.

Notes and the CSV compiler's warnings appear under the plan in the Hybrid panel and in the log.
