# Explainer schema v1.4 (additive): the cartoon kit as `visual` styles

Date: 2026-10-23. v1 to v1.3 are unchanged. The manifest `schema_version` is `"1.4"` only when a clip contains a cartoon `visual` cue. No new cue kind: four styles are added to `visual`
(`explainer/board/styles.py`: `set`, `figure`, `crowd`, `prop`). The art is prebuilt (`python3 -B explainer/cartoon/build_assets.py`, files and `manifest.json` in `explainer/assets/cartoon/`,
`--check` compares them with a rebuild); `explainer/cartoon/kit.py` only reads them and verifies SHA-256 and size of every file. Nothing is generated while rendering.

| style | params | `pos` | size and collision |
|---|---|---|---|
| `set` | `set`: town, field, city, harbour, room; `tod`: day or dusk | not needed | full frame, drawn under everything (also under a narrator), exempt from collision and margins |
| `figure` | `cast` blue, green, red, gold; `pose` idle, point, surprise, think; `kit` a (b, c for idle); `height` (default 420); `flip` | top-left of the figure's visible pixels | its visible pixels; collides with text, captions, other figures and the margins; bobs with the narrator's integer table |
| `crowd` | `n` 2 to 14, `height` (default 170), `seed` | same | one box for the row; colours and looks cycle deterministically from `seed` |
| `prop` | `prop`: house, tree, cactus, fence, flag, sign, crate; `height` | same | scenery: may sit behind figures and other props, collides with text and captions |
An unknown set, colour, pose, look or prop is a problem on the cue (never a crash). Cues appear on their anchor word (frame rule of v1), pop in like a card, and the stage line of every set is y 880, above the caption band (y 900 to 984).
Director (opt-in): `DirectorOptions(cartoon_share=0.0)` by default; above 0 the board beats whose words suggest a scene and people become cartoon beats (a set, 2 to 3 figures, at most one prop,
a row of small figures when the beat is about many people, one word-by-word caption, no narrator), up to that share of the runtime and never three in a row.
