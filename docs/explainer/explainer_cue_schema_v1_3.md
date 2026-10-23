# Explainer schema v1.3 (additive): the `visual` cue (reference-style board elements)

Date: 2026-10-23. [v1](explainer_cue_schema.md), [v1.1](explainer_cue_schema_v1_1.md) and [v1.2](explainer_cue_schema_v1_2.md) are unchanged; every earlier cue means what it meant.
The manifest `schema_version` becomes `"1.3"` only when a `visual` cue is present (otherwise `1`, `"1.1"` or `"1.2"` as before). Nothing here touches a protected file.
Code: `explainer/board/styles.py` (measure, sprites, typed line), `explainer/board/cues.py`, `explainer/board/render.py`, `explainer/board/elements.py`.

## The `visual` cue
`Cue(id, kind="visual", anchor, text, role, asset, offset_s, cps, pos, params)`. Default offset 0.1 s (as `card`). First frame = `ceil((t - clip_origin) * fps)`, the same rule as every cue.
Required: `params.style` (one of the seven below), `pos` (top-left corner of the element, in 1920x1080 pixels) and `text` or `asset`. The element is measured first; the box (+ margin) is checked against
the narrator, every element on screen at that time and the safe area exactly like cards; a violation is a problem on the cue (strict raises, non-strict drops and records it).

| `params.style` | What is drawn | Size |
|---|---|---|
| `tile` | white rounded square with an orange (gold) or role-coloured outline, the registry icon `asset` inside, a 1 to 3 word label in the role colour under it | 330 x (300 + label) |
| `circle` | white circle with a role-coloured ring, icon inside, label under it | 300 x (270 + label) |
| `box` | filled rounded box in the role colour, white text (a diagram node such as "richest") | text width up to 520 |
| `lite` | light rounded box with a role-coloured outline and text (a diagram node such as "poor north") | text width up to 520 |
| `tag` | dark navy tilted tag with yellow lettering (quantities such as "x3 income") | text width up to 520 |
| `scroll` | cream scroll with brown rods and the text (a question beat) | 780 x 300 |
| `line` | typed line in the role colour on the bare board; `params.width`, `params.px`, `params.lines`; `params.sync` makes it a word-synced line | `width` x lines |

`params.px` is a starting size; text shrinks (not below 44 px, 40 px for boxes) to fit. Icons come only from the existing registry (`icons.py`, `props.py`); nothing is generated.

### Synced lines
A `line` with `params.sync = true` uses the v1.2 caption ladder (`all_matched` / `partial` / `anchor_only` / `unresolvable`) unchanged: word `k` is revealed on its `reveal_frames[k]`, the rung and the reveal
frames are recorded in the manifest record. Without `sync` the line is typed at `cps` (default 30) from the cue's first frame. `align` is `left` (default) or `center` (centred on the full final text width, so words never move).

### Other changes in this version
- `arrow` accepts `params.width` (default 9, byte-identical output at the default); the head scales with the width. The director uses 16 for the big diagram arrow.
- `chip` accepts `params.px` (default unchanged).
- The `title` cue of v1 is used for the heavy outlined yellow display title (upper case, Kalam Bold with outline); no change to its meaning.

## Manifest additions
Each visual cue appears like every cue; its record adds `style`, the measured box, the lines/px chosen and, for a synced line, the caption record (`rung`, `matched`, `reveal_frames`, `word_boxes`).

## Compatibility
Old cue files load unchanged; `visual` only exists in files that use it. Plans built with `look="classic"` (the earlier director behaviour; the director's default is now `reference`) contain no `visual` cue and are byte-identical to before.
