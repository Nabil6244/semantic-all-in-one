# Story video: master plan (2026-10-29)

Goal: a finished video that is NEVER a slideshow. Something meaningful changes every 2-3 s, in sync with the voice, one consistent character, pictures that link into each other, no water look, no pasted-on dolls.

Decided with the user: go with everything below; the end result is judged by eye, not by the audit alone.

## 0. Scope (user, 2026-10-29): this is a TOOL feature, not a fix for one video
hrt is only the first test project. Everything must work for any script/CSV/voice (Hindi or English, any niche that uses Normal-style stills):
- no hrt-specific constants, paths or hand-made lanes in the code path; hand overrides stay optional;
- every step has a safe fallback (no depth -> plain camera, no alignment evidence -> app aligner, no ground line -> no narrator) so a video always renders;
- the same gates run on every render and the tool repairs what it can (add shots, change link, re-time) before telling the user;
- acceptance = at least 3 DIFFERENT projects (different topic, language mix, length) pass the gates, not only hrt.

## 1. What exists (all uncommitted)
- CSV (scene_number, script_segment, asset_type, prompt) -> Flow stills (engraved sepia collage). Upgraded prompt: docs/story/story_csv_prompt.md.
- story_align.py: pictures appear when their words are spoken (hrt words-in-window 55.6% -> 95.3%).
- shot_director.py: 2-5 s shots, one protagonist, shot list schema in docs/story/shot_director.md.
- puppet/motion.py + effects.py: calm RIGID motion only (camera affine, +-1 px jitter, grain, flicker, dust). Warp residual 0.14 px vs 1.8 px for the old mesh path.
- puppet/travel.py: torn-seam strip, dwell/travel schedule, flat ink-man walker (foot-locked), slices per scene.
- story_audit.py: still stretches, flash frames, sync, contact sheets.
- Hooks: puppet_stills.py, story_pipeline.py (additive; app.py +13 lines, ui/views.py +7 lines, off by default).

## 2. Known gaps (from the 69 s hrt test)
1. Only 7 pictures in 69 s: dwells of 6-13 s. Audit passes (drift counts as motion) but it still reads as static.
2. Walker ground line is global (88%); it floats over maps/diagrams and overlaps people.
3. No layered parallax yet (depth-shear parallax is what caused the water look; it must be rigid layers only).
4. Travel render is 3.3 s per output second (277 s video ~ 15 min).
5. Travel not wired into the app (switch `story_travel`).

## 3. Target design
Per shot (2-5 s, from narration phrases) one of:
- DWELL+TRAVEL on the strip (about 60% of changes): camera dwells, then travels at the phrase boundary, torn seam, walker walks while travelling.
- LAYERED PARALLAX (about 20%): still split into background / middle / foreground cut-out layers, background inpainted, each layer a RIGID piece moving at its own speed. Only when the still has a clean foreground subject; otherwise plain camera drift.
- LINK (about 10%): torn wipe, push-through, match cut, whip.
- AI IMAGE-TO-VIDEO (about 10%, key beats only): Flow first/last frame.
The VIDEO (moving, changing pictures) is the requirement. The walker is optional: a narrator figure, not the subject. It is a per-video switch (default off), appears only on pictures with a ground line or a clean spot, never over maps/charts/diagrams or people, and is never needed for the video to work.
Rule: rigid transforms only. No mesh warps, no displacement.

## 4. Milestones (each ends with a demo to the user; nothing renders at scale or touches Flow without asking)
M1 Parallax test (5-6 hrt stills): layer split + inpaint + rigid multi-speed move. Review frame sequences for edge halos and ghosting. Go/no-go.
M2 (optional narrator, lowest priority, after M1/M3/M4): Walker placement: per-picture ground line (detect floor, hand lanes as override), fade on maps/charts/diagrams, no overlap with people.
M3 Density: shot director + CSV prompt produce ~80-90 scene rows for hrt; check that every shot has a picture; Flow only after user approval (quota; max 3 references per run).
M4 Speed: render per-shot slices in parallel, reuse cache; target <= 1 s of render per output second.
M5 App wiring: `story_travel` switch (off by default), additive hook lines only, weather isolation test, protected-manifest check.
M5b Generalise: shot director + CSV prompt + parallax thresholds + alignment tested on 2 more projects from the user's video folder (different niches/languages); fix hrt-specific assumptions found.
M6 Full hrt render (277 s) with audit + contact sheets reviewed BEFORE it is called good.

## 5. Definition of "perfect" (all must hold)
- No picture held longer than ~4 s without a visible change (new picture, travel, layer move, or character action).
- story_audit: still stretches > 3 s = 0, flash frames = 0, timing in-window >= 90%.
- Zero warp: warp_energy ratio <= 0.2 on every clip.
- No seam halos. If the narrator is on: no popping, feet planted, never covering content.
- User watches the video and agrees.

## 6. Risks
- Parallax may look cheap on engraved art with no clean foreground: then fall back to travel + links, do not force it.
- 80-90 Flow images per video is a quota decision (user to confirm); Flow live testing may be blocked by the Google-side hold.
- Protagonist consistency across 80+ images depends on reference sheets.

## 7. Rules (unchanged)
Ask before every git commit/push; video_generator.py is protected, app.py/ui additions only; ask before Whisper, renders at scale, Flow spend; nothing starts until Generate in the app.
