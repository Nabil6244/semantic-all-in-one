# Real bugs from real projects (2026-10-19 overnight)

Source: `~/Downloads/VideoGenerator/*/logs/generation.log` (23 projects) and `state/production_events.jsonl`, read only.
Each item was traced in today's code; "replayed" means the real project data was run through today's code (on a copy, no
network unless stated). Status as of branch `upgrade/overnight-2026-10-19`.

| ID | Evidence | Root cause | Status |
|---|---|---|---|
| RB-01 | `HybridCompileError` traceback through `_on_generate` (#021, 18x) | layer anchored before its map beat | **Already fixed** at bf3e566 (`hybrid/local_fix.clamp_layers`). Replayed #021's `plan.json`: 2 problems before, 0 after |
| RB-02 | `[WEATHER] Generation failed: beat 2: type` (#005, 10-14) | unknown; source CSV `plan (1).csv` not on disk | Not reproduced (pre-"never stops" build) |
| RB-03/06 | same CSV error after 3 Generate presses (Weather #005, What If #019) | the error dialog's only action was Retry | **Fixed** b4fbc4f: plan/CSV errors offer "Copy fix prompt" |
| RB-04 | Flow prompt sent as a stock search (#016) | Change source copied the prompt | **Already fixed** c15cf1e (`providers/base._search_words`) |
| RB-05 | What If `stock_image provider is not configured` (97 scenes, #013/#015/#016) | run built without a stock provider | Not in any 10-18/19 project; `_make_asset_manager` now always builds one (Openverse needs no key) |
| RB-07 | What If `frame missing at 348.57 s` (#013, 10-16) | render-time | Old build; not reproduced |
| RB-09 | Flow `PUBLIC_ERROR_UNUSUAL_ACTIVITY` 300x (#015, 10-16) | Google hold; automatic retry fanned out | **Already handled** (`asset_manager` skips the automatic retry on a hold) |
| RB-11 | Pixabay API key written into generation.log; 400 on long queries (#016) | requests' error quotes the URL (key in the query) | **Fixed** e27b627 (redacted, 100-char query limit) |
| RB-12 | `certificate verify failed` keeping the first 30 s of a big stock clip (#021, #022, #023, **live**) | the bundled ffmpeg has no certificate store; this command did not pass `-ca_file` | **Fixed** 8fbca64; reproduced old-fails / new-works on the same Pexels clip with the bundled ffmpeg |
| RB-13 | What If runs end in "N picture(s) need attention" 2-4x before a render (#019, #022, #023) | dialog offered only Retry (same not-found searches) | **Fixed** 706564f: "Fix in Visual Plan" opens the issues list |
| RB-14 | StarMap `footage 0.1 s is too short` / `footage overlaps` at render (#012, #014, 10-16) | late validation | Old build (before StarMap never-stop render work); the app heals rows before compile now. Not re-verified through the full app path |

## Findings for the owner (not changed tonight, with evidence)

**F-1 NASA picture search stops at the first query that returns anything.** `starmap/nasa_images.search` breaks on the
first query with any items, even when every item scores below the 0.4 the fetch needs. Live check (NASA public API):
"heliosphere shape" -> 20 IMAP spacecraft photos (score 0.12), so "heliosphere" (PIA22566 "Voyager Probes Heliosphere Chart",
score 0.50, passes `contradicts`) is never tried; `queries()` also never drops to one word for a two-word description.
**Not fixed** because the broader search is dangerous here: "Titan full disk Voyager 1" broadened finds "Voyager 1 Launch"
(the *Titan* rocket) and it passes the current checks: a wrong-subject picture. A safe fix needs a subject rule (moon vs
launch vehicle), and a decision from you.

**F-2 Cassini pictures are rejected for Voyager rows.** "Titan crescent Voyager 1" -> PIA08733 "Titan Crescent View" (Cassini)
is rejected: "it never mentions Voyager". That rule exists on purpose (an Apollo 11 launch stood in for "Voyager 1 launch").
Whether a later mission's photo of the same body may stand in is an editorial choice.

**F-3 "Voyager Golden Record" was "No NASA image" in #023** but matches today (PIA21741, score 1.00). Most likely a dropped
NASA connection at the time (#019 logged "NASA's image library did not answer ... Connection reset"); `patient()` retries 3x.

**F-4 What If logs NASA lookups as `[StarMap]`** (shared `starmap/nasa_images` code). Cosmetic, confusing in a What If log.

**F-5 `ffmpeg_clip._tls_opts` adds `-ca_file` for `http://` too.** Fine when http redirects to https (checked), but ffmpeg
rejects it for a plain http server ("Option ca_file not found"). Real sources are https.

**F-6 124 silent `except Exception: pass` in app.py.** Not mass-edited (merge risk with other sessions' app.py work).

**F-7 Protected-file manifests are stale at bf3e566** (test_enoch_template_phase0, test_weather_isolation fail on master).
Refreshing them needs your approval.
