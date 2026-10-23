# Explainer board cue schema, version 1 (frozen for Milestone 1)

Date: 2026-10-22. Code: `explainer/board/cues.py` (resolution), `explainer/board/render.py` (layout and drawing), `explainer/board/icons.py` (icon registry).
Legacy kinds `type`, `pop`, `title`, `clear` keep their exact behaviour; this document adds kinds, it does not change them.

## Cue fields

| Field | Used by | Meaning |
|---|---|---|
| `id` | all | unique within a beat; appears in the manifest |
| `kind` | all | see the kind table |
| `anchor` | all | `{"word": w, "occurrence": n}` (nth spoken occurrence inside the beat), `{"index": k}` (kth word inside the beat) or `{"time": t}` (absolute narration seconds). Unchanged from the legacy cues |
| `offset_s` | all | seconds after the anchor; `None` = the default of the kind. Appearance time = anchor word start + offset |
| `text` | type, title, card, header, chip, icon (label), pop (label) | words drawn |
| `role` | pop, card (accent), icon, chip (ignored), arrow | colour role: `blue`, `green`, `gold`, `red`; arrows also accept `ink` (dark) |
| `asset` | icon (required), card (optional) | icon id from the registry, written `icon:<name>` |
| `src`, `dst` | arrow | ids of the two cues the arrow joins |
| `grow_s` | arrow | seconds the shaft takes to grow (default 0.4) |
| `slot` | card, icon, header, chip | name of a layout slot; `None` = first free slot |
| `pos` | all | explicit position in pixels (legacy meaning for legacy kinds; for new kinds the top-left of the cue's box, which is then bounds- and collision-checked) |
| `cps`, `finish_with`, `at` | type, header, clear | unchanged |
| `params` | all | free dictionary reserved for future kinds (narrator pose, caption style, map options); ignored by M1 kinds |

Unknown fields in a dictionary are ignored (`Cue.from_dict`), so newer cue files load in older code. Unknown kinds are a problem, never a guess.

## Kinds

| Kind | Status | Appears at | Reveal | Needs |
|---|---|---|---|---|
| `type`, `pop`, `title`, `clear` | legacy, unchanged | anchor word + 0.0 / 0.2 / 0.1 / 0.0 s | as before | as before |
| `header` | new | anchor + 0.0 s | typed at `cps` with an underline that grows with the text | `text`; slot class `header` |
| `card` | new | anchor + 0.1 s | cream card scales in with overshoot (0.25 s), text centred, optional icon on the left | `text` (or `asset`); slot class `cell` |
| `icon` | new | anchor + 0.2 s | scales in like `pop`; label under it | `asset`; slot class `cell` |
| `chip` | new | anchor + 0.1 s | dark pill scales in | `text`; slot class `chip` |
| `arrow` | new | anchor + 0.0 s | shaft grows along its length over `grow_s`; the head shows from 30 px of length | `src`, `dst` |
| `narrator`, `caption`, `map`, `footage` | **reserved** | not implemented | | resolving one gives the problem "reserved for a later milestone" |

Frame rule (all kinds): the first visible frame is `ceil(appearance_time_in_clip * fps)`, the same rule as the legacy kinds. An element is visible on that frame itself
(a scale-in starts at 40 %, a typed line shows its first character, an arrow shows at least 6 px of shaft).
Clearing: a `clear` cue empties everything that appeared before it, exactly as before; an element has no other way to disappear.

## Dependencies between cues

An arrow's `src` and `dst` must be cues of this beat, drawable, and visible at the arrow's appearance time. If an endpoint appears later than the arrow, or is missing,
the arrow is a problem (nothing is guessed). An arrow is drawn between the facing edges of its two endpoints with a 14 px gap.

## Layout (fixed slots, 1920 x 1080)

Margin 96 px on every side. The left 544 px of the safe area (x from 96 to 640) is reserved for the narrator in Milestone 2; M1 never draws there except through legacy cues.
Content region: x 640 to 1824, y 96 to 984.

| Slot class | Slots | Rectangle (x0, y0, x1, y1) |
|---|---|---|
| header | `H1`, `H2` | (640, 96, 1152, 190), (1312, 96, 1824, 190) |
| cell (card, icon) | `C1`, `C2`, `C3`, `C4` | (640, 230, 1152, 510), (1312, 230, 1824, 510), (640, 610, 1152, 890), (1312, 610, 1824, 890) |
| chip | `K1`, `K2`, `K3` | (640, 904, 960, 980), (1000, 904, 1320, 980), (1360, 904, 1680, 980) |

Rules:
1. A cue with `slot` set uses only that slot. Otherwise it takes the first slot of its class (in the order above) that does not collide.
2. Two elements collide when their boxes intersect **and** their visible periods overlap (an element is visible from its first frame until the next `clear` cue, or the end). A slot is free again after a clear.
3. Legacy cues are placed first, exactly where they were; new cues avoid their boxes. Legacy cues are never moved or checked, only avoided.
4. An explicit `pos` must keep the box inside the margins and collide with nothing visible at the same time.
5. Text is fitted: Patrick Hand at 52 px, shrinking in 4 px steps to 40 px, wrapped to at most 3 lines. If it still does not fit the box, that is a problem.
6. An arrow's line may not pass through any other visible element's box (sampled every 4 px).

## Fallbacks (nothing is guessed)

| Situation | Result |
|---|---|
| unknown kind, missing text, missing asset | problem on the cue; strict mode raises before anything is drawn, non-strict leaves the cue out and records it |
| unknown icon id | problem (lists the available ids) |
| no free slot, text too long, explicit position outside the margins or colliding, arrow blocked or endpoint missing | problem, same handling |
| a problem on one cue | never affects other cues' timing or places (a left-out cue frees its slot) |

## Manifest additions

Each cue's manifest row keeps every legacy key and adds `slot`, `asset`, `src`, `dst`, `grow_s`, `lines`, `font_px`; each item's `bbox` is the box used for collision and for onset detection.
`schema_version` (1) is recorded at the top of the manifest.
