# Explainer board cue schema v1.1 (additive; Milestone 2)

Date: 2026-10-22. Adds the `narrator` kind and eight `prop:*` assets. [Schema v1](explainer_cue_schema.md) is unchanged: every v1 cue means exactly what it meant, and
`schema_version` in the manifest stays 1 for clips without a narrator and becomes `"1.1"` only when a narrator cue is present.
Still reserved (not implemented): `caption`, `map`, `footage`.

## The `narrator` cue

`Cue(id, kind="narrator", anchor=..., offset_s=None, params={...})`. Anchor and offset work as for every cue (default offset 0.0). The cue's **first frame** is
`ceil(time_in_clip * fps)`, the same rule as every other kind. Everything below is counted in **clip frames** from that number.

| `params` key | Values | Used by |
|---|---|---|
| `action` | `show` (enter), `pose` (change pose), `hide` (leave) | required |
| `pose` | `idle`, `point`, `surprise`, `think`, `shrug`, `explain` | show, pose |
| `side` | `left` (default), `right`; the narrator faces the content: the art is mirrored for `right` | show only |
| `scale` | 0.45 to 1.0 in steps of 0.01; 1.0 = about 540 px tall at 1080p | show, pose |
| `enter`, `exit` | `slide` (default) or `none` | show (enter), hide (exit) |

State machine (a violation is a problem on the cue; nothing is guessed):
1. The first narrator cue must be `show`. `show` while visible, `pose` or `hide` while not visible: problem.
2. `pose` and `hide` cues must come at least `ENTER_FRAMES` after a sliding `show`, and at least `FADE_FRAMES` after the previous `pose`.
3. A `board clear` cue does not affect the narrator. One narrator per beat.
4. Missing, edited or unreadable narrator assets: problem on every narrator cue (see Assets).

## Animation timing (all frame-based; no clocks, no floating-point time accumulation)

Let `n` be the clip frame, `f_show`, `f_pose_i`, `f_hide` the first frames of the cues.

| Behaviour | Definition |
|---|---|
| Enter (slide) | Frames `f_show` to `f_show+11` the figure moves from `START_VISIBLE_PX` = 40 px of the **current pose's** outline inside the frame edge to its settled place; position = start + (settled - start) * ease(k), k = (n - f_show) / 12, ease(k) = 1 - (1 - k)^3, rounded to whole pixels. It is first visible on frame `f_show` (k = 0) and settled from `f_show+12`. `enter=none`: settled from `f_show` |
| Exit (slide) | p = (n - f_hide + 1) / 12 for n = `f_hide` .. `f_hide+11`; position = settled + (start - settled) * p^2 (ease-in quadratic, so the figure has already moved on the first frame; a cubic ease-in did not move a whole pixel on frame 1 and was rejected); not drawn from `f_hide+12`. `exit=none`: not drawn from `f_hide` |
| Pose change | Cross-fade over `FADE_FRAMES` = 4: the new pose is drawn over the previous one at alpha 0.25, 0.5, 0.75, 1.0 on frames `f_pose` .. `f_pose+3`; settled from `f_pose+4`. A scale change happens in the same cross-fade (both sprites bottom-aligned at the same feet line) |
| Bob | vertical offset in whole pixels from a fixed 90-entry table (amplitude 3 px, one sine period per 90 frames), indexed by `(n - f_show) mod 90`. The table is a literal in `timeline.py`; the program checks at import that no table value was a rounding tie |
| Blink | The eyes layer `blink` is shown for `BLINK_FRAMES` = 4 frames. Blink start frames come from a SHA-256 chain seeded with `"<beat_id>\|narrator\|blink"`: the gap before each blink is `75 + (first two digest bytes as a big-endian integer mod 61)` frames, the next digest is the SHA-256 of the previous. First blink: `f_show` + first gap. Never uses `random` or Python `hash()`. No blink while the pose's eyes are `happy` (pose `explain`) |
| Eyes | `open` for every pose except `explain` (`happy`); `blink` on blink frames |
| Mouth | Speech runs come from the word times: a word covers clip frames `ceil((start - origin)*fps)` to `ceil((end - origin)*fps)`; runs separated by at most `MOUTH_BRIDGE` = 4 frames are merged. Inside a run, with `i` = frames since the run start: if `i mod 6 < 3` the mouth is open, else `closed`; the open shape cycles by `(i div 6) mod 3`: `open`, `o`, `wide`. Outside runs: `closed`. The mouth follows speech activity, not phonemes |
| Placement | Left zone x 96..640, right zone x 1280..1824; figure centred in its zone, the lowest opaque pixel of any pose at y = 981 before bob (+3 = 984, the bottom safe line) |

## Collision (the narrator is a layout object)
The collision box of the narrator is the **union of the exact opaque bounding boxes of every frame it is on screen**: all poses and scales used, both layers during
a cross-fade, bob, and the whole slide path. It is registered for the period from `f_show` to `f_hide + 12` (or the clip end). Cards, icons, props, chips, headers and
arrows are placed to avoid it; an explicit `pos` that touches it is a problem; an arrow whose line would cross it is a problem. The slide path and the frames of a
transition are part of the box. A clip's settled figure never has pixels outside the safe area; during an enter or exit slide the figure is partly outside the frame
**by design** (it slides over the frame edge) and nothing else does.

## Assets
Generated once by `python3 explainer/narrator/build_assets.py` (never at render time) into `explainer/assets/narrator/`: six body layers, three eye layers, four
mouth layers and `manifest.json` (SHA-256 and size of every file, canvas size, feet line, head anchor, opaque bounding boxes). The renderer loads the PNGs and verifies each
SHA-256 against the manifest. **Fallback:** if a file is missing, unreadable or does not match, every narrator cue gets a problem naming the cause and the build command;
strict mode raises before anything is drawn, non-strict leaves the narrator out and renders everything else. The renderer never redraws the character.
Regenerate: `python3 -B explainer/narrator/build_assets.py` (writes only that folder); `--check` rebuilds in memory and compares bytes with the files on disk.

## Props
Eight code-drawn assets, usable wherever an icon asset is accepted (`icon` cue, `card.asset`): `prop:note`, `prop:scale`, `prop:magnifier`, `prop:book`, `prop:key`,
`prop:flag`, `prop:chest`, `prop:bulb`. An unknown id lists all available ids (icons and props).

## Manifest additions
Narrator cues appear in the manifest like every cue; the manifest also records `schema_version` `"1.1"`, `narrator` (asset id, manifest SHA-256, per-frame state summary:
`show`, `pose` and `hide` frames, blink frames, speech runs, collision box, settled box) when a narrator is present.
