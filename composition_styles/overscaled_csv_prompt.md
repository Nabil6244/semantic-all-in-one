# Overscaled CSV prompt

Copy everything below the line into your LLM, then paste the narration
script at the end.

---

You are writing a visual-plan CSV for **Semantic YT Studio's Overscaled
style**: a white whiteboard canvas where photo/video cards are added one at a
time as the narrator speaks, linked by hand-drawn arrows, then the board
clears and the next small collage starts. A small subject photo and the
subject's title stay in the top-left header for the whole subject.

Output **only** the CSV (header row first), no commentary, no code fences.

## Columns (exactly these, in this order)

`scene_number,script_segment,node_id,node_type,role,asset_type,prompt,caption,highlight,camera_action,camera_target,edge_from,edge_to,edge_label,edge_style,chapter_title,node_label`

| Column | What to put |
|---|---|
| `scene_number` | 1, 2, 3 … one per row, no gaps. |
| `script_segment` | The narration for this beat, copied **word for word**. All rows joined in order must reproduce the script exactly. |
| `node_id` | A new card's id (`n1`, `n2` …; anchors `a1`, `a2` …). Empty on narration-only rows. Never reuse an id for a new card. |
| `node_type` | `image`, `video_loop`, `diagram`, or `anchor`. |
| `role` | Usually empty. `anchor` on anchor rows. Optionally `hero` on the one card of a composition that should get the most emphasis. |
| `asset_type` | `stock_image`, `stock_video`, `image` (AI image), `video` (AI video), `youtube_video`, `archive_video`, `nasa_video`, `commons_image`, `commons_video`, or `map`. Use video types for `video_loop` cards. |
| `prompt` | Search query or generation prompt for the card's visual (for `map`: the place, big to small, e.g. `Florida > Florida Panhandle`). |
| `caption` | The spoken words of this beat, trimmed to ≤10 words. Not a paraphrase. |
| `highlight` | One or two key names, numbers, or terms. Must appear **exactly** (same letters and case) inside `caption`. |
| `camera_action`, `camera_target` | Always empty. |
| `edge_from`, `edge_to` | Link this row's new card (`edge_to`) to an earlier card still on screen (`edge_from`). |
| `edge_label` | Usually empty; 1–2 words on about 1 arrow in 4. |
| `edge_style` | Empty = a visible arrow. `group` = same composition, no arrow. Avoid `callout`. |
| `chapter_title` | Only on each subject's first row. |
| `node_label` | Always empty. |

Quote any field that contains a comma.

## Rhythm
- One row per beat of about **2.5–3.5 seconds** of speech (7–10 words).
  Split long sentences across rows at natural pauses.
- Aim for a new card roughly every 2–2.5 s and a fresh composition roughly
  every 3.5–4 s.

## Subjects
- A subject is the thing being explained (a car, an aircraft, a person, "How
  batteries work"). Most videos have 1–4 subjects; each usually lasts
  45–90 seconds.
- A subject's **first row** is its anchor: `node_id` `a1`/`a2`…,
  `node_type=anchor`, `role=anchor`, an image `asset_type`, a `prompt` for a
  clean, recognizable photo of the subject on a plain background, and the
  subject's `chapter_title`. `script_segment` is just the subject's opening
  words. Leave `caption`, `highlight`, and edges empty.
- Never use `chapter_title` for subtopics. Never put an arrow to or from an
  anchor.

## Compositions
- A composition is the set of cards on screen together: **1 to 3 cards**,
  never more. Target mix: about **40% solo, 42% two-card, 16% three-card**.
- Build progressively, **1 → 2 → 3**: each new card is its own row. Never
  introduce two cards on one row.
- A card joins the current composition only through an edge
  (`edge_from` = a card already on screen, `edge_to` = the new card). A new
  card with **no edge** clears the board and starts a new composition.
- Card 1 is the subject or cause; later cards are what it leads to, proves,
  or sits beside.

## Arrows vs. `group`
- Draw an arrow (empty `edge_style`) only for a **meaningful relationship**:
  cause → effect, before → after, myth → reality, thing → what it produces.
  About half of multi-card compositions have one.
- Cards that simply belong together (a comparison, a list, two views of one
  thing) use `edge_style=group`: same composition, no arrow.
- Label an arrow only when the label adds meaning (`pushes`, `789 hp`).

## Holding a card
- When the narration keeps talking about what is already on screen, add a
  **narration-only row**: only `scene_number` and `script_segment` filled,
  everything else empty. The current cards stay up through that beat. Use
  these freely so each row stays 2.5–3.5 s without needing a new visual.

## Self-check before answering
1. Joining every `script_segment` in order gives back the script exactly.
2. Each subject starts with one anchor row carrying its `chapter_title`; no
   other row has a `chapter_title`.
3. No composition ever has more than 3 cards on screen.
4. Every `edge_from` is a card from the current composition; no edges touch
   anchors.
5. Every `highlight` is an exact substring of its `caption`.
6. `node_label`, `camera_action`, `camera_target` are empty everywhere;
   `callout` is not used.
7. Rows average about 2.5–3.5 seconds of speech.

## Example (first rows of a battery explainer)

```
scene_number,script_segment,node_id,node_type,role,asset_type,prompt,caption,highlight,camera_action,camera_target,edge_from,edge_to,edge_label,edge_style,chapter_title,node_label
1,Most people think,a1,anchor,anchor,stock_image,AA battery isolated,,,,,,,,,How Batteries Really Work,
2,a battery simply stores electricity.,n1,image,,stock_image,glowing AA battery dark,a battery simply stores electricity,stores electricity,,,,,,,,
3,But a battery is actually a tiny chemical machine,n2,video_loop,,stock_video,battery chemistry particles animation,a battery is actually a tiny chemical machine,tiny chemical machine,,,n1,n2,,,,
4,that constantly moves charged particles.,,,,,,,,,,,,,,,
5,"Inside the battery, two different materials",n3,diagram,,stock_image,battery cross section diagram,two different materials,different materials,,,,,,,,
6,create a chemical imbalance.,,,,,,,,,,,,,,,
7,That imbalance pushes electrons through a circuit,n4,video_loop,,stock_video,electric current circuit animation,that imbalance pushes electrons through a circuit,pushes electrons,,,n3,n4,pushes,,,
```

## Narration script

<paste the script here>
