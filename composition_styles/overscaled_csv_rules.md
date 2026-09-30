# Overscaled CSV rules

Paste these into whatever prompt writes Overscaled visual-plan CSVs. They
describe the target look: a whiteboard collage that builds up card by card
and then clears — not a series of Exp Solar-style side-by-side screens.

Columns: `scene_number, script_segment, node_id, node_type, role, asset_type,
prompt, caption, highlight, edge_from, edge_to, edge_label, edge_style,
chapter_title, node_label`.

## Rhythm
- One row per narration beat of roughly **2.5–3.5 seconds** of speech
  (about 7–10 words). Split long sentences into several rows.
- A new card roughly every 2–2.5 s; a composition resets roughly every
  3.5–4 s (after 1–3 cards).

## Compositions (a group of cards on screen together)
- At most **3 cards** at once. Aim for about **40% solo, 42% two-card,
  16% three-card** compositions.
- Build progressively: **1 → 2 → 3**. Each new card is its own row, added
  next to the cards already on screen. Never introduce 2–3 new cards on
  one row.
- Cards join the same composition only through an edge (`edge_from` →
  `edge_to`). A card with no edge to the current cards starts a new
  composition (the board clears).
- Card 1 of a composition should be the subject or cause; later cards are
  what it leads to, proves, or sits alongside.

## Arrows vs. grouping
- Use an arrow (`edge_style` empty) **only for a meaningful relationship**
  — cause → effect, before → after, thing → what it produces. Roughly half
  of multi-card compositions have an arrow.
- Related cards that should simply appear together **without an arrow**
  use `edge_style=group` (still fill `edge_from`/`edge_to`).
- `edge_label`: occasional only — about 1 arrow in 4, one or two words
  (e.g. `produces`, `789 hp`). Leave it empty otherwise.
- Do **not** use `edge_style=callout` as a routine emphasis device. Reserve
  it for at most one genuine "this is the proof" moment per video, or skip
  it entirely.

## Text
- `chapter_title`: **one per subject**, set on the subject's first row only
  (a subject usually lasts 45–90 s). Never a new title per subtopic or per
  composition.
- `node_label`: leave **empty** by default. Don't label every card; put a
  name or number in the caption and highlight it instead.
- `caption`: follow the narration — use the spoken words of this beat
  (trimmed to ≤10 words), not a paraphrase or summary.
- `highlight`: the one or two key names, numbers, or terms from the caption.

## Subject anchor (header photo)
- Each subject gets **one anchor**: a small photo shown at the left of the
  title row, next to the subject's `chapter_title`, for the whole subject.
- Put it on the subject's **first row**, together with that subject's
  `chapter_title`: `node_id` like `a1`, `node_type=anchor`, `role=anchor`,
  an image `asset_type` (e.g. `stock_image`), and a `prompt` for a clean,
  instantly recognizable photo of the subject itself (the car, the
  aircraft, the person) — ideally on a plain background, landscape.
- Leave `caption`, `highlight`, `node_label`, and all edge columns empty
  on the anchor row. Never draw an arrow to or from an anchor.
- The anchor row's `script_segment` is the subject's opening words (e.g.
  just the subject name). It shows the header only; the first content card
  comes on the next row.
- The next subject's anchor replaces the previous one. Don't add an anchor
  for subtopics, and don't repeat one within a subject.

## Holding a card
- When the narration keeps talking about a card already on screen, add a
  **narration-only row**: fill `scene_number` and `script_segment`, and
  leave `node_id`, `asset_type`, `prompt`, and `caption` empty. The current
  cards stay visible through that beat.

## Example (one subject: anchor, then solo → 2 → 3 → reset)

| script_segment | node_id | node_type | prompt | caption | edge_from | edge_to | edge_label | edge_style | chapter_title |
|---|---|---|---|---|---|---|---|---|---|
| Batteries. | a1 | anchor | single AA battery on a white background | | | | | | How Batteries Work |
| Inside every battery sits a tiny chemical machine. | n1 | image | battery cross-section | a tiny chemical machine | | | | | |
| Two different materials face each other, | n2 | diagram | anode and cathode diagram | two different materials | n1 | n2 | | group | |
| and that imbalance pushes electrons through the wire. | n3 | video_loop | electrons flowing through a wire | pushes electrons through the wire | n2 | n3 | pushes | | |
| That push is what we call voltage. | | | | | | | | | |
| Heat speeds those reactions up. | n4 | image | battery near a heat source | heat speeds reactions up | | | | | |
