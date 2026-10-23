# Milestone 2 report: narrator and visual toolkit

Date: 2026-10-22. Scope: original narrator (6 poses, eyes, mouth, blink, bob, enter/exit), 8 props, additive schema v1.1, narrator as a layout object.
**Nothing committed, staged or pushed. No protected file, `app.py`, spec, settings, UI, installer, packaging file or protection manifest was touched.** M3 and M4 not started; narrator is **not** integrated with maps or captions.
Spec: [explainer_cue_schema_v1_1.md](explainer_cue_schema_v1_1.md) (written before the code; v1 unchanged). Evidence: [m2_evidence/](m2_evidence/). One Mac, offline, **synthetic word times made by rule: not a human voice.**

## Files changed
New, under `explainer/`: `narrator/{__init__,build_assets,rig,timeline}.py`, `assets/narrator/` (6 body PNGs, 3 eye PNGs, 4 mouth PNGs, `manifest.json`; 14 files, 296 KB), `board/props.py`, `spike/verify_m2.py`.
New, under `docs/explainer/`: `explainer_cue_schema_v1_1.md`, this report, `m2_evidence/` (19 files).
Edited (all my own untracked files): `board/cues.py` (kind `narrator` implemented; `caption`, `map`, `footage` still reserved), `board/render.py` (narrator item, collision dispatch, drawing order), `board/builder.py` (narrator track, manifest `schema_version` "1.1" only when a narrator is present), `board/splice.py` (narrator layout checked before drawing), `board/icons.py` (props registered), `spike/verify_m1.py` (one line: the "reserved kind" check now uses `caption`, because `narrator` is no longer reserved; every M1 result is otherwise identical).

## Asset generation is separate from rendering
- One-time script `python3 -B explainer/narrator/build_assets.py` writes the PNG layers and `manifest.json` (SHA-256 and size of every file, canvas, opaque bounding boxes). `--check` rebuilds in memory and compares bytes with disk.
- The renderer (`rig.py`, `timeline.py`) loads the PNGs, verifies each SHA-256 against the manifest, pastes, scales (LANCZOS) and mirrors. It contains no drawing code and does not import the builder; a fresh interpreter that builds a narrator clip does not load `build_assets` (checked).
- **Fallback:** missing, edited or damaged asset: every narrator cue gets a problem naming the file and the build command; strict raises before anything is drawn (checked: no clip file written), non-strict renders everything else without the narrator (checked). Nothing is ever regenerated at render time.
- Asset hashes (Pillow 12.3.0): manifest SHA-256 `7360b9dd3c130a538ea7e98205d287dbf0bc15540a69143e1a3f93cb59dd8b64`, layers digest `448002c9…551fd6`. Pillow is the only dependency of the bytes; another Pillow or FreeType version could change them, and `--check` would then say so.
- Design: round-headed explorer, neckerchief, hair tuft, original (no hat, no spear). All colours and proportions are one table (`PARAMS`). Opaque height about 548 design px at scale 1.0 (target 540).

## Animation timing (all frame-based; full text in the schema)
Counted in clip frames from each cue's first frame (`ceil(time * fps)`, the same rule as every cue):
- enter: slide over 12 frames, ease-out cubic, first frame already shows 40 px of the pose's outline; exit: 12 frames, quadratic ease-in (a cubic ease-in did not move a whole pixel on frame one; my first run caught that as a +1-frame detection and it was fixed in the design, not in the threshold);
- pose change: cross-fade, alpha 0.25 / 0.5 / 0.75 / 1.0 on four frames; pose or hide during an enter slide or within 4 frames of a pose change is a problem;
- bob: fixed 90-entry integer table (amplitude 3 px), index `(n - show frame) mod 90`; the table is a literal and the code asserts no rounding ties;
- blink: 4 frames, start frames from a SHA-256 chain seeded with `"<beat_id>|narrator|blink"`; gap 75 to 135 frames; never `random`, never `hash()`;
- mouth: speech runs from word frames (gaps of 4 frames or fewer merged); inside a run a 6-frame cycle, open for 3 frames (shape cycles open, o, wide) and closed for 3; closed outside runs.

## Results: state changes against the clip map (hard cut / dissolve 0.5 s)
Method: for each event the narrator region (x 0..600, y 420..1000) of the **decoded render** is compared with the rig's expected frame and with the counterfactual track without that event, inside the pixels that differ; detected frame = first frame where the counterfactual explains the video worse by more than 0.3 gray levels (before the change the two expectations are identical, so the value is exactly 0). Pure board frames only (frames inside a dissolve are excluded).

| Event | Clip frame (hard / dissolve) | Video frame expected = detected | Error (frames) | Measure at frame−1 / at frame (hard cut) |
|---|---|---|---|---|
| show idle | 6 / 14 | 216 / 217 | 0 / 0 | 0.00 / 1.68 (dissolve: frame−1 not a pure frame) |
| pose point | 24 / 32 | 234 / 235 | 0 / 0 | 0.00 / 0.92 |
| pose surprise | 59 / 67 | 269 / 270 | 0 / 0 | 0.00 / 1.40 |
| pose think | 108 / 116 | 318 / 319 | 0 / 0 | 0.00 / 1.03 |
| pose explain | 126 / 134 | 336 / 337 | 0 / 0 | 0.00 / 2.73 |
| pose shrug | 204 / 212 | 414 / 415 | 0 / 0 | 0.00 / 2.21 |
| hide (exit slide) | 284 / 291 | 494 / 494 | 0 / 0 | 0.00 / 6.62 |

(Video frame = clip frame + 210 hard cut, + 203 dissolve; the dissolve shifts the clip origin by 0.25 s, so the same cue lands on a different clip frame but the same video frame within one.)
Whole-region alignment: every pure frame (300 hard cut, 287 dissolve) is best explained by the expected frame at offset 0 (300/300 and 287/287; 68 and 66 of them decisively, the rest are frames identical to their neighbours, e.g. a repeated bob value). Mean absolute pixel error 0.40 / 0.44 gray levels, max 0.60 / 3.07 (the 3.07 is a frame next to the dissolve). 0 held frames, 0 skipped frames, one pure run per render.

## Results: M1 and legacy are preserved
- M1 cues inside the narrator fixture: all 11 land on the same clip frames as in the M1 evidence, 0 frames of error in both modes.
- `verify_m1`: 21/21 checks, cue rows identical to the M1 evidence, clip SHA-256 identical (`aca2cd87…edd`, instrumented `4cfaf4c2…380`).
- `verify_builder` (legacy): cue rows, checks and board clip bytes identical to the earlier baseline. `verify_splice`: checks identical, board clips and the rendered video byte-identical.

## Results: faces, mouth activity, poses (synthetic timings)
Classifier: the decoded mouth/eye region is matched by minimum mean absolute error against the rig's four mouth renders and three eye renders for that frame's position (template matching). Denominators: settled pure frames with a single pose layer, 246 (hard cut) and 245 (dissolve).
- Mouth state: 100% agreement with the schedule in both modes (closed 141 / open 27 / wide 39 / o 39 hard cut; 142 / 27 / 39 / 37 dissolve). Eyes: 100% (5 scheduled blinks, 5 decoded, in each mode).
- Speech ground truth = speech runs from the synthetic word times. **Speech frames: 184 of 184 (hard cut) and 182 of 182 (dissolve) have a moving mouth** (window of 7 decoded frames contains both an open and a closed mouth); 109 speech frames are closed by design (the closed half of each cycle).
- **Silence:** per frame, 0 of 32 (hard cut) and 0 of 33 (dissolve) silence frames show an open mouth (false positives 0). With the 7-frame window, 6 of 26 (23.1%) and 3 of 27 (11.1%) silence frames count as "moving" only because they lie within 3 frames of a speech run; for silence at least 4 frames from speech it is 0 of 16 and 0 of 17. The scorecard's T06 target (silence moving at most 10%) is therefore met per frame and for silence away from speech, and **not met under the edge-inclusive windowed definition in hard cut (23.1%)**; the definition itself is provisional.
- False negatives for the speech/mouth link cannot be judged against a human voice; the mouth follows word activity, not phonemes.
- **Poses in pixels:** all six poses are recognised from the decoded frames at the middle of their intervals (best match equals scheduled pose for 6 of 6 in both modes; mean error 0.38 to 0.44 gray levels). One asset id (`narrator_explorer_v1`) and one manifest hash on every frame.

## Collisions and frame bounds
- The narrator's collision box is the union of the exact opaque boxes of every frame: all poses, both layers during cross-fades, bob and the slide path (checked: no frame's box leaves it, both sides, scales 1.0 and 0.8). It is registered before other elements are placed.
- Explicit positions that touch it are problems for a card, an icon, a prop card, a chip and a header (5 of 5). An element appearing while the narrator is present or sliding is a problem; after an exit slide has finished, or after an instant exit, the same position is allowed (3 of 3). With the narrator on the right, the right-hand slots are skipped (cards go to C1, C3; the third card gets "no free slot") and a named right-hand slot is refused.
- Pixel check on the real sample, every frame: the narrator's exact opaque pixels never intersect any visible element's box, which includes the scale-in overshoot: **0 collisions** over 290 frames and 11 elements, both modes.
- Out-of-frame: **0 settled frames with pixels outside the frame, 0 settled frames below the 984 px safe line.** 6 transition frames (the enter and exit slides) have pixels outside the frame on the left edge only, up to 77,183 pixels (the figure sliding over the edge, by design; this is the one place I read "no out-of-frame pixels" as meaning settled frames). Say if you want the transitions to stay inside the frame instead.

## Props
Eight props (`prop:note, scale, magnifier, book, key, flag, chest, bulb`), accepted wherever an icon asset is: all draw inside their sprite with a margin; four as card icons and four as icon cues build with no problems ([props_sheet.png](m2_evidence/props_sheet.png)). No new cue kind.

## Deterministic builds (comparison method)
| Comparison | Method | Result |
|---|---|---|
| Asset build twice, in memory | byte equality of all 14 files | identical |
| Assets on disk vs rebuild | byte equality, and no extra files | identical |
| Narrator clip twice, same process, plain and instrumented | SHA-256 of the file, `ffmpeg -f framemd5` of all frames, manifest JSON text equal after masking the file name | identical (6 of 6) |
| Clip in a separate interpreter | SHA-256 of the plain clip | identical |
Clip hashes (10 s fixture with narrator): plain `ee17b594…399` (549,307 bytes), instrumented `e03d1005…c96`; asset manifest hash above.

## Protection, Git state, off-mode
| Check | Result |
|---|---|
| Official guard `test_weather_isolation` (4 tests), before and after | OK, OK. **Caveat unchanged:** the manifest is dirty (another session refreshed it to match its edits to 4 protected files), so this proves no change relative to that manifest, not relative to HEAD. I did not edit the manifest and added no file to a protected folder |
| `git status` and the tracked diff, before vs after | identical |
| Off-mode snapshot (original fixture, compiled twice; 571 protected-scope hashes; 1,331-file folder census; HEAD; `settings.json` hash) | identical in every field |
| Bytecode in `explainer/` | none |
| Files that changed in `explainer/`/`docs/explainer/` since the M2 baseline | the six edited files named above (new files excluded) |

## Visual scorecard against the reference
| ID | Result |
|---|---|
| H07 overlap/legibility | PASS on geometry (0 narrator/element collisions, 0 settled out-of-frame, 0 below the safe line); no caption or map test yet |
| T05 narrator presence | not measurable on 10 s; narrator on screen 9.4 of 10 s, which is far above the reference's roughly 50% |
| T06 consistency and mouth activity | one asset id 100%; 6 distinct poses in 10 s (target at least 4 per 2 min); mouth moving in 100% of speech frames; silence per frame 0%, windowed 23.1% / 11.1% (see above); synthetic timings |
| T08 latency | narrator state changes have 0 offset by design; M1 cue latencies unchanged |
| T10 palette/type | board #C0C0C0 and role colours unchanged |
| M02 narrator appeal and consistency | **no independent ratings: M02 has not received three reviewer ratings.** My own read: charming and consistent, but plain |
Not applicable yet: T01 to T04, T07, T09, T11 to T13, M01, M03 to M05.

**Unresolved visual differences from the reference** (my reading): flat code-drawn vector with uniform outlines versus the reference's hand-drawn illustration; arms and legs are tubes, hands are discs; only front view, six poses, three eye and four mouth shapes; no walk, no turn, no props held in the hand; the figure stays in a fixed zone at one scale per pose (scale is a parameter, tested only as a unit check); the face does not follow content; the mouth is a timer, not lip-sync.

## Limits and what is still open
- **Art:** simple by construction; redesign is cheap (`PARAMS`) but needs a rebuild and new hashes.
- **Timing:** word times here are made by rule; blink, bob and the mouth cycle are deterministic but untested against real speech; the earlier unresolved items (Whisper word-time accuracy, the 2-frame tail adjustment) are unchanged and not used here.
- **Fonts:** Patrick Hand and Kalam Bold OFL texts are stored; **Inter's licence text is still unverified.** The narrator has no text.
- **Packaging:** `explainer/` and `explainer/assets/narrator/` are not in the PyInstaller spec; the installers are untouched; **Windows and macOS packaging not tested.** The asset bytes depend on the Pillow version, and the loader fails closed (problem) on a mismatch rather than redrawing.
- Cross-platform: the bob and slide positions use floating-point `sin`/cubic then round to whole pixels (the bob is a literal table); not run on Windows.
- Not done by design: narrator over maps, captions, director, UI, any app integration.

## Next smallest step
M3 needs your approval first. Smallest slice: a word-timed `caption` cue on board clips (typed key phrase, same anchor and slot rules) before touching maps.
