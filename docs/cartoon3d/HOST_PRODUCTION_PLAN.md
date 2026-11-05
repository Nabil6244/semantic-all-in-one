# Preschool host: production plan from approved design h10

Status: plan only. Nothing below has started. Each stage ends at a gate and waits for approval.

## Approved design

Hybrid h10, approved 2026-11-05. Frozen copy: `cartoon3d-engine/authoring/build/revisions/h10_approved/` (model, renders, board, scripts, textures).
h10 is the visual target. Every stage is compared with it under the same camera and light. A passing validator is never visual approval.

## Starting point

| Part | Now | Issue |
|---|---|---|
| Head | 490,333 verts, 980,506 tris | Far too heavy, no animation edge loops, no UVs, colours are per-vertex |
| Hair | 221,532 verts, 443,048 tris | Far too heavy, no skinning |
| Eyes, teeth, mouth, band, tie, brows | About 11,000 tris | Fine, need skinning and UV checks |
| Body and clothes | About 54,000 tris including hidden body head and shoes | Stage 3 clothes, kept as they are |
| Rig | 166 bones: original 163 plus 3 ponytail | Head bones still fit r5, not h10 |
| Expressions | 94 on the r5 head | Smile on h10 is one prototype key |

## Budget for the final GLB

| Part | Target tris |
|---|---|
| Head and neck | 14,000 to 18,000 |
| Hair and ponytail | 10,000 to 14,000 |
| Eyes, teeth, tongue, mouth | 5,000 |
| Band, tie, brows | 2,000 |
| Body and clothes | 30,000, as now once hidden parts are out |
| **Total** | **About 65,000 to 70,000** |

Textures: face 2048, hair 1024 to 2048, others 1024. File: aim under 15 MB (r5 test GLB is 24 MB).

## Stage 1: clean head topology

Recommended route: wrap the existing MPFB head onto the h10 surface, guided by landmarks (eye corners, lid edges, mouth corners, lip line, nose, chin, ears).
Why: that mesh already has animation loops around eyes and mouth, UVs, skin weights and all shape keys on matching vertices. It should save the most work and carries the existing facial system over.
Risk: the wrap may lose some of h10's shapes, especially lids and lips. It starts with a short test on the head only.
Fallback: new quad mesh from Blender's remesher with hand-placed guide loops, then surface-based key transfer. Slower, and more expression rework.

Gate 1: low-poly head beside h10 from all views. It must match the approved look, with clean loops around eyes and mouth.

## Stage 2: optimisation and materials

- Hair and ponytail: low-poly meshes, with lock detail baked to normal maps.
- Head colours to a real 2048 skin texture: blush, lips, lash line, lid colour, hairline shadow.
- Soft skin look without Blender's subsurface shading, which glTF does not carry: warm painted shading, roughness map, tuned Three.js lighting.

Gate 2: optimised neutral and prototype smile against h10, in Blender and in Three.js.

## Stage 3: skeleton integration

- Fit head, jaw, eye, tongue and neck bones to h10; keep all 163 original bone names and the 3 ponytail bones.
- Skin head, hair, band, teeth and eyes. Join the neck to the body with no visible seam.
- Check head size against the body, since h10 has new proportions.

Gate 3: head turn, nod, jaw, eye look, ponytail swing, and full-body view.

## Stage 4: facial shape keys

Order: blink first, then the 15 Meta visemes, 52 ARKit shapes, then smile, laugh, surprise, curious, talk. Microsoft visemes are kept in the Blender file.
Each key is retargeted, not only copied, then reviewed on h10 proportions. Lids, lash line, brows, teeth and tongue must move together. Hand-tune smile, blink and visemes.
Checks: every key moves, no key tears, combinations tested (smile + blink, smile + speech, surprise + speech), 45% smile reads on camera.

Gate 4: expression board at video size and close-up.

## Stage 5: Three.js validation

- Export with morph normals. Run gltf-validator, then the app's Three.js 0.170 through `glb_check.mjs`.
- Check textures, morphs, bones including fingers and jaw, blink shading, skinning at the neck.
- Measure load time, render speed and memory on the M2.

Gate 5: Three.js stills beside h10 renders, plus a short test clip with lip sync.

## Out of scope until later approval

Animation library, classroom worlds, app integration. Clothing work stays on hold except the neckline decision below.

## Decisions needed

1. Microsoft visemes in the shipped GLB. Recommendation: leave them out (Meta and ARKit cover speech, smaller file); they stay in the Blender file.
2. Collar: the head join touches the tee neckline, which is rough. Recommendation: allow a neckline-only fix in Stage 3.
3. Which head route to test first. Recommendation: wrap the MPFB head.

## Main risks

- Lid and lip shapes may soften in the low-poly version. Gate 1 and 2 protect the approved look.
- Retargeted expressions may need more hand work than planned, especially visemes on the wider mouth.
- Three.js has no true subsurface skin, so she will look slightly less soft than the Blender renders.

## Stage 1 wrap test result (2026-11-05)

Tests t1 to t4 in `cartoon3d-engine/authoring/build/wrap/`, scripts `host/wrap_test.py`, `host/wrap_board.py`. Head only, h10 untouched.

- Works: forehead, cheeks, jaw, chin, nose, neck and ears match h10 closely on about 9,000 triangles, from front, 3/4 and side.
- Fails: lid edges and lips. Lid rims are ragged and the mouth does not open cleanly. MPFB's mouth is a closed folded pocket that does not suit h10's lips, teeth and cavity.
- Keys: copied MPFB smile breaks; the h10 smile field also breaks on this mouth. Blink closes, but needs lid work and a better texture.
- Surface error (0.006 mm mean) did not predict quality. Judge by renders only.
- Bake: t3 settings gave cleaner lips, t4 gave fewer holes. Neither is final; Stage 2 needs a proper bake.

Proposed change to Stage 1, pending approval: keep the wrap for the head, and rebuild only the eye and mouth zones with purpose-made loops, plus a separate mouth interior. Lip and lid shape keys are then authored for this mesh instead of copied.

## Stage 1 head candidate c4 (2026-11-05)

Built by `host/wrap_head2.py` from a copy of wrap t3. Boards `host/wrap_board2.py`. Output in `cartoon3d-engine/authoring/build/wrap/`: `cand_c4.blend`, `c4_compare.jpg`, `c4_expressions.jpg`, `c4_detail.jpg`, `c4_regions.jpg`, `c4_anim_strip.jpg`, `c4/anim.mp4`.

The full replacement mesh is not needed: lids and lips work on the wrapped mesh once those zones are rebuilt. Head is 4,318 verts, 8,372 tris.

| Gate | Result | Evidence and defects |
|---|---|---|
| Preserved head shape | Pass with one defect | Forehead, cheeks, jaw, chin, nose, neck match h10. Ears are flatter than h10. |
| Lid rims | Pass with defects | Clean rim and lash line. Eyes stay more open than h10, faint rim ring. |
| Blink | Pass with defects | Full closure, 50% stays on the ball using a corrective key the renderer must drive. Closed lid shows an outline and a faint pale mark on the right lid. |
| Lips and mouth interior | Pass with defects | Separate interior, teeth and tongue work. White sliver in the seam at 3/4. |
| Smile | Pass with defects | Clear teeth from the front. Near side distorts at 3/4, lower tooth fragment shows. |
| Jaw and speech | Partial | jawOpen and 15 Meta visemes authored; open and round shapes read well. FF, SS and teeth-to-lip shapes are weak; tongue barely seen. |
| Texture | Pass with defects | No ray bake, no black patches at eyes, ears, lips, neck. Pale lid mark remains. |
| Animation | Partial | 52-frame talk and blink clip plays smoothly. Timing is a simple test, not real lip sync. |

Not done: the 52 ARKit shapes, Microsoft visemes, brows in expressions, eye gaze with lids, skinning, Three.js test of this head. Hair and body are unchanged.

Stage 1 stays open until the defects above are fixed and you accept the boards. Integration has not started.

## Stage 1 head candidate c6 (2026-11-05, replaces c4 as current)

`cartoon3d-engine/authoring/build/wrap/cand_c6.blend`, boards `c6_compare.jpg`, `c6_expressions.jpg`, `c6_detail.jpg`, `c6_regions.jpg`, `c6_anim_strip.jpg`, clip `c6/anim.mp4`. c4 and c5 are kept. c5 had a regression (eye showing through the closed lid), fixed in c6.

| Gate | c4 | c6 | Still open in c6 |
|---|---|---|---|
| Head shape kept | Pass, one defect | Pass, one defect | Ears still flatter than h10 from the side |
| Lid rims | Pass with defects | Pass | Slightly heavier lash than h10 |
| Blink | Pass with defects | Pass | Soft lid outline when closed; 50% needs the corrective key |
| Lips and interior | Pass with defects | Pass | None seen |
| Smile | Pass with defects | Pass, one defect | Near side at 3/4 is still a little stretched |
| Jaw and speech | Partial | Mostly pass | FF is subtle; TH tongue is hard to see at video size |
| Texture | Pass with defects | Pass | None seen at eyes, lips, ears, neck in these views |
| Animation | Partial | Partial | Timing test only, no real lip sync |

Still not done: 52 ARKit shapes, Microsoft visemes, brows in expressions, lids following gaze, skinning, Three.js test.

## Gate 1 accepted (2026-11-05)

c6 accepted for Gate 1. Frozen copy: `cartoon3d-engine/authoring/build/revisions/c6_gate1/`.
Carried forward as known items: ears flatter than h10 from the side, soft closed-lid outline, slight stretch at 3/4 smile, weak FF and TH. Tune in Stage 4.
Stage 2 (hair optimisation and materials) has not started and waits for go-ahead.

## Stage 2 result s2 (2026-11-05), awaiting Gate 2

Scripts `host/stage2_build.py`, `stage2_check.mjs`, `stage2_board.py`. Output `cartoon3d-engine/authoring/build/stage2/`: `stage2_s2.blend`, `s2/bust.glb`, `s2_compare.jpg`, `s2_face.jpg`, `s2_three_expr.jpg`.

- Hair 443,048 to 13,289 tris, colour and normal maps baked. Budget met; look very close to h10.
- Skin: no subsurface in the shipped material. Roughness map plus low emissive from the skin texture (0.14) stands in for it.
- Bust GLB: 68,903 tris, 14.2 MB, 21 morph targets, validator no errors. It has no legs, shoes or skinning, so the full GLB will be larger.
- Three.js 0.170: loads in about 0.25 s, no console errors, about 3 ms per frame headless at 800 x 950 (rough figure). Expressions and blink corrective work.
- Three.js lighting lives in `stage2_check.mjs`: key with soft shadow, fill, rim, bounce, environment 0.4. These values must move into the app's renderer later.

Open defects: neutral mouth thicker and straighter than h10; pale ring around the eyes in Three.js; hair darker with less sheen in Three.js; lip corners slightly rough in Three.js; hard shadow edges from a single light; collar still rough (neckline decision).

## Handoff state (2026-11-05, end of session)

Gate 2 not yet accepted. After s2, the mouth and eye fix ran through c7 to c11 (Stage 2 s3 to s7). Done: thinner curved lips, front-projection face UVs at 3072 px, front-wins texture paint, lid shading painted, lower teeth deeper. c10/s6 is the last reviewed result: open eyes and lips clean in Blender and Three.js. Defect at c10: dark lash blocks at eye corners when closed. c11/s7 tapers the lash to fix this and was still building at handoff, not reviewed. Check `build/wrap/c11_detail.jpg` and `build/stage2/s7_face.jpg`; if s7 is missing, rerun the commands in the handoff prompt.

## Gate 2 accepted (2026-11-05)

The user accepted Gate 2 on c11/s7 as is. It is frozen in `cartoon3d-engine/authoring/build/revisions/s7_gate2/` (cand_c11.blend, stage2_s7.blend, s7/ bust GLB + Three.js renders, boards, scripts).

Accepted with known defects, carried forward:
- Closed eyes: thin vertical lash marks at outer corners; dark wedge with light chip at the inner corner of the screen-left eye; pale, soft halo around the closed lid. Visible in close-ups only.
- Ears flatter than h10 from the side; slight near-side stretch in the 3/4 smile; weak FF and TH visemes.
- Hair darker in Three.js; single-light shadow edges; rough tee collar.
- Bust GLB 14.6 MB without legs or shoes: textures may need compressing.
- The renderer must drive the blink corrective key: eyeBlinkArc = 4w(1-w). Three.js light values live only in host/stage2_check.mjs.

Not done: 52 ARKit shapes, Microsoft visemes, brows in expressions, lids following gaze, skinning.

Decisions made by the user 2026-11-05: (1) Microsoft visemes stay out of the shipped GLB and are kept in the Blender file; (2) a neckline-only collar fix is allowed in Stage 3, with no other clothing work. Stage 3 has not started and waits for the user's go-ahead.

## Stage 3 result g2 (2026-11-05)

Built from the frozen Gate 2 file with `host/stage3_rig.py` (poses in `host/stage3_shots.json`, Three.js replay `host/stage3_check.mjs`, boards `host/stage3_board.py`). Output: `build/stage3/stage3_g2.blend`, `build/stage3/g2/host.glb`, boards `build/stage3/g2_poses.jpg` and `g2_body.jpg`.
Run: `blender -b -noaudio build/revisions/s7_gate2/stage2_s7.blend --python host/stage3_rig.py -- gN`, then from the repo root `node cartoon3d-engine/authoring/host/stage3_check.mjs gN`, then `python3 host/stage3_board.py gN`.

Done:
- 66 head, face, eye, jaw, neck and ponytail bones moved to h10 (face x 1.13, z -0.032; eyes at the eyeball centres; ponytail along the hair's centreline). All 166 bone names kept, no broken connections.
- Skinned: head (head/jaw/neck chain, shoulder flare follows the body like the tee), mouth interior head/jaw, lower teeth and tongue on jaw, eyes on eye.L/eye.R, hair on head plus 3 ponytail bones, band/tie/brows/upper teeth on head.
- The wrapped meshes carried stale weight entries (group indices up to 255); these are cleared before skinning. Without that the face warped on a head turn.
- Old body head, helpers and its 95 face keys removed; arms, hands, legs and shoes now show.
- Neckline-only collar fix: tee neck edge smoothed and held 2.5 mm outside the neck skin.
- Three.js 0.170: all poses replay with no missing bones and no errors; load 0.4 s, draw 3.6 ms.

Open defects:
- Small steps remain at the sides of the neckline; sleeve hems and the overalls' back top edge are still rough (outside the neckline-only scope).
- The jaw bone and the jawOpen key both open the mouth; the renderer must use one or the other.
- Lids do not follow gaze (known).
- GLB 25.9 MB and 80,067 tris, over the 15 MB / 65-70k budget (body and clothes added); texture compression and hidden-body trimming needed in Stage 5.
- Body is the r5 adult body: head reads slightly small for the cartoon style, and the side view shows adult chest and hip curves. Head scale is the user's call.

## Gate 3 accepted (2026-11-05)

The user accepted Gate 3 on g2 as is, with the defects above carried forward (head scale left unchanged). Frozen in `cartoon3d-engine/authoring/build/revisions/g2_gate3/` (stage3_g2.blend, g2/ skinned host.glb with Blender and Three.js renders, boards, scripts).
Stage 4 (facial shape keys: blink, 15 Meta visemes, 52 ARKit, smile/laugh/surprise/curious/talk; Microsoft visemes stay in the .blend only) has not started and waits for the user's go-ahead.

## Stage 4 result k3 (2026-11-05, lean scope)

The user approved a lean Stage 4: only the shapes Ms Rachel-style videos use. The 52 ARKit shapes are deferred.
Built from the frozen Gate 3 file with `host/stage4_keys.py` (shots `host/stage4_shots.json`, Three.js via `host/stage3_check.mjs k3 stage4_shots.json stage4`, boards `host/stage4_board.py k3`). Output: `build/stage4/stage4_k3.blend`, `build/stage4/k3/host.glb`, boards `k3_video.jpg`, `k3_closeup.jpg`, `k3_ff_th.jpg`.

Done:
- FF rebuilt from the clean SS parting with the lower lip raised to the upper teeth (the first try pulled the lip back and left corner notches; dropped).
- TH: wider parting, tongue tip forward between the teeth.
- New `surprise` (open oval mouth, wider lids, brows up) and `curious` (her left brow up, her right eye narrowed, small pursed smile).
- Brows now move: browInnerUp, browOuterUpLeft/Right, browDownLeft/Right (ARKit names), plus brow moves inside smile, laugh, surprise and curious. Brows slide over the forehead and keep their height above the skin.
- Combinations checked: smile + blink, smile + talk, curious + talk, 45% smile.
- 28 morph names in Three.js, no errors; GLB 26.3 MB.

Open defects:
- FF is clean but subtle; the upper teeth show only a little.
- Lids do not follow gaze; jaw bone and jawOpen overlap (renderer uses one).
- Deferred: 52 ARKit shapes; "talk" is a viseme sequence driven by the renderer, not a key.

## Gate 4 accepted (2026-11-05)

The user accepted Gate 4 on k3 as is (FF subtle, carried). Frozen in `cartoon3d-engine/authoring/build/revisions/k3_gate4/` (stage4_k3.blend, k3/ host.glb with Blender and Three.js renders, boards, scripts).
Stage 5 (GLB under 15 MB and about 70k tris, gltf-validator, M2 load/render/memory, Three.js stills beside h10 and a short lip-sync clip) has not started and waits for the user's go-ahead.

## Stage 5 result f1 (2026-11-05)

Built from the frozen Gate 4 file with `host/stage5_build.py`; checks `host/stage5_validate.py` (structural glTF checks, no download), `host/stage3_check.mjs f1 stage5_shots.json stage5`, `host/stage5_board.py f1`, lip-sync test `host/stage5_clip.mjs f1` (voice via `cartoon3d-engine/tools/tts_words.py`).
Output: `build/stage5/f1/host.glb`, boards `build/stage5/f1_compare.jpg` (h10 / Gate 4 / Stage 5), `f1_detail.jpg`, `f1_lipsync_frames.jpg`, clip `build/stage5/clip/lipsync_f1.mp4`.

Results:
- GLB 26.9 MB -> 7.1 MB (textures 21.4 -> 1.5 MB: face 2048, others 1024, roughness 512, colour maps JPEG q90, alpha maps PNG). No visible change in Three.js.
- Structural validation: 0 errors, 0 warnings (19 meshes, 166 joints, 28 morph names, all accessors in bounds, weights sum to 1, image data matches type).
- Three.js 0.170 on the M2: load 0.24 s, draw 4.2 ms per frame, 20 draw calls, JS heap 29 MB (was 72 MB).
- Lip-sync clip: 10.2 s rendered in 14.6 s. Edge word timings -> visemes by spelling rules; blinks with the arc corrective, brow lift on the question, small surprise on "Ball!", gentle head motion, smile in pauses.

Open:
- Triangles 80k, over the 65-70k plan, because the clothes are 46k (overalls 17.6k, tee 12.1k). Thinning them is clothing work and was not done. Speed is not affected.
- The official Khronos gltf-validator is not installed (would need an npm download, user's OK).
- Visemes come from spelling, not phonemes; good for a test, a phoneme source can come with the lesson renderer.

### Lip-sync tuning (2026-11-05, user asked before Gate 5)

`host/stage5_clip.mjs` now: a dictionary of common preschool words that spelling gets wrong; mouth opening gated by the real voice loudness (shut in gaps); visual lead of 40 ms; smooth bumps with 25 ms attack / 60 ms release; closed-lip smile in pauses. The Mac's built-in phoneme lookup is not reachable from scripts and no phoneme tool is installed, so visemes still come from spelling plus the dictionary.
Measured on the test line: mouth openness vs voice loudness correlation 0.57 -> 0.87; mouth shut in 100% of silent frames before and after. Clip re-rendered to `build/stage5/clip/lipsync_f1.mp4`; frames `build/stage5/f1_lipsync_frames.jpg`.

## Gate 5 accepted (2026-11-05): host model finished

The user accepted Gate 5 on f1 with the tuned lip-sync. Final host: `cartoon3d-engine/authoring/build/revisions/f1_gate5/f1/host.glb` (7.1 MB, 166 bones, 28 face shapes), source `stage5_f1.blend`, clip and scripts alongside.
Renderer rules: drive eyeBlinkArc = 4w(1-w) with eyeBlink; use either the jaw bone or jawOpen, not both; brows ride the same key names as the face; Three.js light values are in `host/stage3_check.mjs`.
Carried defects: closed-eye corner marks, flat ears, subtle FF, lids do not follow gaze, small collar steps, 80k tris from clothes.

Next toward Ms Rachel-style videos (each needs the user's go-ahead): connect the host to the lesson renderer in place of maya (voice -> visemes as in stage5_clip.mjs), movement library (wave, point, clap, simple signs, sit, dance, pick up toys), classrooms (each different), songs and music beds, app page.

## Integration step 1: host in the lesson renderer (2026-11-05)

`node cartoon3d-engine/lesson.mjs --csv lesson.csv --host host3d [--glb path]` renders a Kids Learn lesson with the approved host (default GLB: `authoring/build/revisions/f1_gate5/f1/host.glb`). maya/toon and other characters are unchanged.
- `lib/visemes.mjs`: the Gate 5 lip-sync (word list + spelling rules, loudness gating, 40 ms lead, attack/release) as a library; the plan carries a 30 fps viseme track.
- `web/host3d.js`: loads the GLB, arms from the A-pose to a relaxed hang, the toon gesture names as simple bone poses (wave, point, present, open, clap, cheer, jump, heart, lean, think; point/present use her left arm toward the props), head turns to props, speech nods, eye looks, emotions as face keys, blink with arc corrective.
- Hooks: `web/lesson.js` (host3d branch + soft environment for PBR), `lesson.mjs` (`--host host3d`, `--glb`, `/host.glb` route, viseme track). Three.js strips dots from bone names (upperarm01.R -> upperarm01R).
- Tests: `test/visemes.test.mjs` (2) + `test/lesson.test.mjs` (5) pass.
- Sample: first_words.csv, 54 s rendered in 56 s, -14.3 LUFS, no errors: `cartoon3d-engine/out/host3d_first_words.mp4`.
Camera (added same day, host3d only, `hostCamera` in web/lesson.js): one shot per line eased over 0.8 s. Props during the line -> two-shot sized to fit host + every prop (width and height); repeat lines -> head-and-shoulders close-up for speech modelling; other lines -> medium shot of the host. Full lesson re-rendered 54 s in 57 s.
Open: gestures are simple poses, not the movement library; PBR host vs outlined toon set style difference; GLB path points into git-ignored build/.
