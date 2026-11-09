# War Documentary — footage quality and "right clip" plan (2026-11-09)

Evidence: render `Video_2026-11-09_038_test_wasdf` (log `logs/generation.log`, clips `state/war/assets/`).

## What is actually wrong

| # | Problem | Evidence in render 038 | Root cause |
|---|---------|------------------------|------------|
| 1 | Clips look soft / low quality | Clips are 1920x1080 but only ~1.0-1.6 Mbps (YouTube's own 1080p is ~3-5 Mbps). One clip is variable-rate (2000/1 timebase). | YouTube clips are **screen-recorded** from a headless Chrome player (`browser_worker.mjs`, MediaRecorder, real time), then re-encoded to H.264, then re-encoded again by War segments (CRF 20 veryfast) and again in the final mix. Three to four generations of loss from an already-compressed stream. The player may also still be on a low ABR rung for the first seconds. |
| 2 | Clip is the wrong moment of the right video | 5 of 5 YouTube scenes: `no transcript match, falling back ... at 89.5s / 544s / 30s`. 0 transcript hits. Two `429 Too Many Requests` on transcripts. | When the transcript can't be fetched or doesn't match, the code still cuts a clip from a guessed timestamp instead of looking at the picture. |
| 3 | Wrong video / not the clip we want | Picked "Six Senators Warned US Banks…" (Orbisentinel, a commentary channel) for a tanker scene; one video (RxZltZjIZeI) supplies 5 of 16 clips. | Search takes the first passable result; no check that the frames show the subject; channel quality isn't ranked. |
| 5 | Blank grey grid on screen | Scenes 2, 7, 13, 14, 19 got no clip; their stretches sit on `war_backdrop_v3.mp4` (dark blue-grey field + creeping grid), sometimes with only a small chip or nothing on it. | `backdrop.py` plate is the fallback in four places: scene with no clip, clip with no picture (`segments.swap_pictureless`), piece that fails to render twice (`segments.py` ~l.905), and gaps shorter than the 2 s motion-card minimum / opened by late trims (`direction._final_coverage`). A plate with little on it reads as a broken frame. |
| 4 | Too complicated, footage gets buried | 37 card kinds, maps, panels, motion graphics, 2-7 s shot cuts. | Every rule added on top of footage; clips are chopped and covered, so even a good clip doesn't read. |

## Plan (smallest steps, each testable alone)

### Step 1 — Get the original pixels (fixes #1)
- For War only, try a **direct section download** first (`yt-dlp --download-sections "*start-end" -f "bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080]+ba"`) — yt-dlp 2026.08.19 is already installed. Browser capture becomes the fallback, not the default. Other styles untouched.
- If browser capture is still used: wait until `videoHeight >= 1080` **and** the player has played ~1.5 s at that height before recording; record at a higher bitrate; encode the webm → mp4 once with CRF 16-18 and constant 25 fps.
- War segments: footage pieces encode at CRF 18 `-preset medium` (cards can stay veryfast).
- **Quality gate** after each fetch: reject a clip if real height < 720, bitrate below a floor, or a blur score (Laplacian variance on 3 frames) below a floor → next candidate.
- Test: synthetic low-bitrate/blurred clip is rejected; a good clip passes; ffprobe of fetched clips shows ≥3 Mbps at 1080p.

**Step 1 findings (2026-11-09):**
- Direct yt-dlp download: works but YouTube throttles it (<1 MB in 4 min for an 8 s section). Not usable; browser capture stays.
- Real loss: `browser_worker.mjs convertToMp4` re-encodes the 8 Mbps VP9 capture with ffmpeg's default x264 (CRF 23) → ~1.2 Mbps 1080p. Recording also starts once `videoHeight >= 720`. Fix proposed (protected file, needs owner OK): `-crf 16 -preset fast -r 25 -pix_fmt yuv420p`, and wait for 1080 when the player offers it plus ~1 s settle.
- A blur-score gate is wrong: the softest clips were real smoke-in-sky shots, and one of the sharpest was a screenshot of a news article. Not built; on-screen-text detection moves to Step 3.
- Done: War pieces encode at CRF 18 (was 20), `cinematic_explainer/war/segments.py`.

### Step 2 — Cut the right moment (fixes #2)
- Transcripts: get subtitles through yt-dlp (`--write-auto-subs --skip-download`) with a small pause between videos and a cache per video id, so 429s stop.
- No transcript match → **no blind timestamp**. Instead sample frames across the video (every ~10 s, scene-change detection, free, no Gemini) and pick the stretch with the most motion and no talking-head / studio / on-screen-graphic look; if nothing qualifies, try the next video.
- Never take the first or last 5 % of a video (intros, end screens).
- Test: a scene with a failed transcript never logs "falling back ... at Xs"; a talking-head stretch loses to an action stretch.

### Step 3 — Pick the right video (fixes #3)
- Rank candidates: news-agency / broadcaster channels (Reuters, AP, AFP, Guardian News, BBC, Sky, DW, ministries of defence) up; commentary / "analysis" / reaction channels down; titles must share the scene's key nouns (place, weapon, event).
- One video may give at most 2 clips per film, and never two clips within 30 s of each other.
- Short search queries: 2-4 key nouns from the CSV prompt (place + thing + "footage"), not the whole sentence.
- Test: commentary channel loses to an agency upload with the same nouns; a 6th use of one video goes to the next candidate.

### Step 4 — Simpler film (fixes #4)
- Add a **"Footage first"** switch in the War section (on by default): footage clips play 5-8 s uncut, at most one small lower-third/chip on top, full-frame cards only where there is no good clip, maps only when a place is named for the first time.
- Keep every existing card/map (nothing removed); the switch only changes how often they appear, so the older look is one click away.
- Test: plan for a 3-min script with all clips available → footage ≥ 60 % of screen time, no clip shorter than 4 s, no card covering a clip more than 30 % of its time.

### Step 5 — No blank grey grid (fixes #5)
- Fewer empty scenes first: Steps 1-3 mean fewer failed fetches. A scene whose fetch fails tries a second, shorter query and then a stock clip (Pexels/Pixabay) for the same nouns before giving up.
- Fill order when a stretch still has no clip: (a) keep holding the previous clip or start the next one early if it is the same subject and ≤ 3 s; (b) a full-frame map or card that fills the frame (motion card, map, stat panel); (c) the grid plate only under a full-frame graphic, never bare and never with just a lone chip.
- A clip with no picture / a failed piece: retry with a plain scale-only encode, then a neighbouring clip of the same scene, before the plate.
- Final check before encode: any run of > 0.5 s where the plate is visible with < 30 % of the frame covered by graphics is a failure. It gets filled by rule (a)/(b) and logged with its time.
- Test: a plan with 3 clipless scenes, a pictureless clip and a 1.5 s gap has 0 s of bare grid; the plate never appears with only a chip on it.

### Order and checks
1 → 2 → 3 → 5 → 4 (the grid fix leans on better fetching, and the simpler look in Step 4 must not reopen gaps). After each step: only that step's tests + one Generate scenes run on the 038 CSV to compare clip bitrate and how many scenes logged "no transcript match". No full render until step 4, and only if you ask.

## Open decisions for you
- Step 1: OK to use direct download (yt-dlp) for War before browser capture? (It was swapped to browser capture app-wide earlier, likely because downloads were being blocked; if it is still blocked on this Mac the browser path stays as the fallback.)
- Step 4: should "Footage first" be the default, or an option you turn on?
