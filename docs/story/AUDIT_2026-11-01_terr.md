# Story Motion audit: goal vs the latest render (2026-11-01)

Render: `~/Downloads/VideoGenerator/Video_2026-11-01_052_terr/final/terr.mp4` (Disney / Oswald script, English, 29 CSV pictures, 141.8 s, 1080p30, rendered 19:28).
Sources: `state/story/*.json`, `logs/generation.log`, the final mp4 (scene detection, black detection, frame-difference motion, frame sheets), `state/editorial_plan.json`, gfx overlay cache.

## The goal (docs/story/MASTER_PLAN.md, HANDOFF_PROMPT.md, user rules)
1. Never a slideshow: something meaningful changes every 2-3 s, nothing held more than ~4 s without a visible change.
2. In sync with the voice (timing in-window >= 90%).
3. Rigid motion only: no water look, no mesh warps.
4. Pictures that LINK into each other (travel strip with torn seams ~60%, layered parallax ~20%, links ~10%, AI image-to-video ~10% on key beats).
5. No flash frames, no seam halos. Narrator/character optional.
6. A tool for any script; the same gates run on every render and catch problems before the user sees them.
7. Render speed <= 1 s per output second.

## Scorecard

| Goal | Result in terr.mp4 | Verdict |
|---|---|---|
| Change every 2-3 s | 47 shots, avg 3.0 s, max 4.6 s. No quiet stretch >= 1.5 s in the final (frame-difference check). | Met |
| ...but real picture change | Only 29 different pictures = one new picture every 4.9 s. 15 of the 47 shots are reframes ("detail of") of the same picture; scenes hold one picture 6-8 s in 8 places (e.g. scene 14 = 8.4 s, 24 = 7.7 s). | Partly |
| Sync with voice | 100% of 343 matched words inside their scene window. | Met |
| Rigid motion, no water | Camera treatments only (push, pan, tilt, reveal, handheld, 3 parallax). No warping seen. | Met |
| Pictures link into each other | Shot director planned 25 dissolves, 4 whips, 3 torn wipes, 3 match cuts, 2 doorway pushes. The director output has `transition_in = cut` on all 47; continuity realised 16 camera-matched joins + 1 link. Scene detection shows hard cuts at almost every shot change. No travel strip, no torn seam. | Not met |
| AI image-to-video on key beats | 0 (gate is off; Flow video has no start image). | Not met (by decision) |
| No flash frames | White full-frame flash at 132.9 s; black dip at 4.2 s; a 0.4 s full-screen RGB glitch + cyan diagonal stripes at 82.8 s. | Not met |
| Gates catch problems | Story audit says flash frames 0, because it audits the story timeline BEFORE the app adds its own transitions and gfx overlays. It also reported FAIL (one 3.2 s still) while Editorial QA said 100/100. | Not met |
| Fits the topic | Snow falling inside 1920s offices (shots 005a, 005b, 006a) and sparkle "shimmer" over a boardroom (022a); 17 shots tagged location "sea". | Not met |
| Speed | 156 s local + 53 s final render for 142 s (story clips: 41 in 41 s). | Met |

## Defects found, with cause

1. **Cyan-stripe glitch at 82.8 s.** gfx-core template `news/glitch_cut` ("RGB slices then a white flash with cyan stripes"), placed by `normal_gfx/planner.py` doc-extras because the Mac-wide "Use Hybrid Map Graphics & Sound" / Doc Style switch is on. A news transition inside a 1930s painterly story. Cache: `~/Library/Caches/SemanticYTStudio/gfx_overlays/aa57146d1d023616b3ca4aaf`.
2. **White flash at 132.9 s and black dip at 4.2 s.** The app's Editorial Pacing transitions (`1=fade, 2=dissolve, 6=fade, 24=fade, 28=flash`) are applied on top of the Story Motion units. Two transition systems run at once; Story Motion's own joins are not the last word.
3. **Wrong weather/effects.** `story_fast/direct.py` `_lex` matches English stems at word START only, so `sea` hits "seats"/"sealed" (shimmer + location "sea") and `cold` (as in a cold look) triggers falling snow indoors. Same prefix matching drives the continuity location bible (17 x "sea").
4. **Planned links dropped.** shots.json carries varied transitions; direct.json sets every `transition_in` to `cut` (`MAX_CUT_RUN` comment: "plain cuts are what films mostly use"). Only 1 shot became a real link.
5. **Audit blind spot.** `story_audit` runs on the story timeline, not on the final mp4 after editorial transitions + gfx composite, so defects 1-2 passed.
6. **Text graphics are fragments.** Lower third "end up / owning some of the most", chapter card "And to see how, we have to", "Disney's empire / isn't built on": sentence pieces, not facts. From the editorial/gfx planner, not Story Motion.
7. **Inconsistent protagonist metadata** (harmless now, character is off): shots.json "Soldier, sepia paper-collage silhouette", log "woman", bible "man in a fedora". The default protagonist is not topic-aware.
8. **Hybrid sound leak.** Log: "Hybrid Map sound design: 8 effect(s)" plus Smart ambience 29 beds plus Story sound mix 5 beds, in one Story run. Not checked by ear.

## What is good
- Constant movement, no still screens, fast render, tight timing.
- Rigid camera language is clean; no water look.
- Picture quality and grade are consistent across the 29 stills.

## Where it stands against "perfect" (MASTER_PLAN section 5)
- No picture held > ~4 s without change: met by reframes, not by new pictures or travel.
- story_audit still > 3 s = 0: FAIL (one 3.2 s).
- Flash frames = 0: FAIL in the final file (audit says pass).
- Zero warp: met.
- 3 different projects pass: not done (terr is one).
- User agrees: open.

## Suggested fixes, in order (general rules, not tuned for this video)
1. In a Story Motion run, turn off the app's Editorial Pacing transitions and the Doc Style / Hybrid graphics and sound by default (Story Motion owns joins, sound and look); keep keyword callouts optional.
2. Run story_audit (flash, black dip, full-frame overlay) on the FINAL mp4 after all overlays; repair or report.
3. Fix `_lex` to whole words (or a short suffix list) and require 2 hits or an outdoor cue before weather particles; never snow/rain on an indoor shot.
4. Let planned links survive: realise the shot director's whips/torn wipes/match cuts where continuity allows (target ~10-20% links), and use the travel strip between related pictures.
5. Raise picture density: the dense CSV prompt should give ~1 picture per 2.5-3 s (about 50 for 142 s) instead of 29.
