# pakMap CSV schema (Phase 0 draft)

One row per **visual event**, grouped by item. This is a contract draft, not code. It extends spec section 12 with the Reference 2 layers.

## Columns

| Column | Required | Meaning |
|---|---|---|
| `item_no` | yes | Group number (countdown number, part number, or 0 for the cold open) |
| `beat` | yes | `clear`, `title`, `locate`, `reveal`, `support`, `release` |
| `vo_anchor` | one of anchor/time | Phrase from the narration that triggers the event (matched to Whisper words) |
| `t_start`, `t_end` | one of anchor/time | Seconds; fallback when no anchor. `t_start` is monotonic within an item |
| `layer_type` | yes | See layer list below |
| `layer_id` | yes | Unique id so later rows can update or remove it |
| `layer_action` | yes | `in`, `out`, `update` |
| `scene_type` | no | Spec section "Map scene types" name, for the plan preview |
| `camera_action` | no | `fly_to`, `push_in`, `pull_back`, `drift`, `globe` |
| `lat`, `lon`, `zoom`, `easing`, `camera_dur` | when camera_action set | Camera keyframe |
| `geo_ref` | map layers | Country / admin region / named feature / polygon id / polyline id |
| `label_text`, `sub_text` | chips | Chip text and second line |
| `color_role` | no | `neutral`, `featured`, `subject`, `compare`, `stat` (maps to colour tokens) |
| `value_from`, `value_to`, `value_format` | stat chips | Counter start, end and format (`12.6M`, `-67.7 C`, `1/5`, `54%`) |
| `anchor` | no | `tl`, `tr`, `bl`, `br`, `bc`, `center`, `map:<lat,lon>` |
| `asset_path`, `asset_kind` | media layers | `photo`, `video`, `archival`, `sticker`, `dataset` |
| `data_source` | data layers | `bundled:<name>` or a user file path |
| `reveal` | no | `fade`, `scale`, `draw`, `stagger`, `word` |
| `in_dur`, `hold`, `out_dur` | no | Seconds; defaults come from `pakmap.draft.json` |
| `notes` | no | Free text |

## Layer types

| `layer_type` | Notes |
|---|---|
| `hud_title` | Top-left chip: `label_text` = `NUMBER 14` / `PART 1`, `sub_text` = subtitle. **Optional**: an item may have none (cold open) |
| `caption` | Text-only chip, optional `sub_text` as source line (`MUNDAY ET AL. 2022`) |
| `stat` | Value chip with counter; max 2 at once |
| `marker` | Dot + label, optional value and sub-chip; `color_role` |
| `fill` | Region polygon; 2-3+ at once allowed |
| `line` | `geo_ref` + `line_kind`: route, river, rail, border, divide, reference, connector |
| `pip` | Single card; `anchor`; optional label chip |
| `filmstrip` | 3-7 small labelled cards along one edge (rows share a `layer_id`) |
| `sticker` | Static PNG, map-anchored; not together with a `pip` |
| `cluster` | Small staggered dot group (tens to hundreds) |
| `dots` | Dot-density from `data_source` (thousands) with counter chip separate |
| `value_overlay` | Colour-ramp raster clipped to `geo_ref`, from `data_source` |
| `ghost_shape` | `geo_ref` polygon moved to a target `anchor` at true scale |
| `streak` | Decorative drawn streaks over `geo_ref` |
| `media_full` | Full-screen footage/photo with dissolve in/out; HUD and stat chips stay on top |
| `camera` | Camera-only row |

## Validation rules (carried from the spec)
1. One `hud_title` per item, unless the item is marked `hud_off` (cold open).
2. A `clear` row at every item boundary (fixed 0.5 s).
3. `t_start` monotonic within an item.
4. At most 2 concurrent `stat` rows and 5 concurrent text layers.
5. `pip`/`filmstrip` and `sticker` never overlap in time.
6. No gap above 5 s without an event (warning, not error).
7. A data layer whose source is missing is an error that names the layer and what to supply.
8. Anchored rows that cannot be matched to the narration fall back to proportional timing and are flagged in the plan preview.
