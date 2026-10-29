# Body-map scenes (Health Cinema)

One continuous 3D shot of a whole body. The camera, highlights, labels, illustration cards and effects follow the narration, one **beat per CSV row**. Code: `health_cinema/bodymap.py`
(validation + spec), `illustrations.py` (library), `bodymap_flow.py` (fills the library through the app's Flow image workflow), `threejs/bodymap.js` (skin block, route), `overlay.py` (cards).

## The body stage
`bench/prep_body.py` merges the models already prepared in `~/HealthCinemaTools/bench/` into `body.glb` + `anchors_body.json` (no download; same Z-Anatomy frame, metres, Z up, front -Y, left = +X):
skin shell, muscle, skeleton, discs, ligaments (chest + msk); heart, lungs, vessels (chest); liver, pancreas, spleen, stomach, intestines, bladder, kidneys + ureters (BodyParts3D, CC BY 4.0) (abdomen);
cortex, cerebellum, eyes, head arteries (head). Region anchors are measured from the skin shell and cut at the skeleton's joints: body, head, neck, chest, abdomen, pelvis, upper_arm / forearm / hand / thigh / shin / foot
(`_l` / `_r`, each with a `surface` point on the skin), plus the organ anchors (heart, lungs, liver_only, pancreas, stomach, intestines, spleen, bladder, kidneys, brain, cortex, eyes, shoulder/elbow/wrist/hip/knee).
Re-run `python3 health_cinema/bench/prep_body.py` after any model changes.

## CSV columns (visual=body; consecutive body rows are one scene)
| column | values |
|---|---|
| `body_region` | an anchor name (required) |
| `body_scale` | `whole` (full body) / `region` / `close` |
| `body_focus` | `body` (hologram body + faint skeleton) / `skin` / `vessels` / `organ` (the region's organ layers forward; needs an organ region) |
| `body_effect` | `none` / `skin_layers` (magnified skin block with a lesion, on a skin-surface region) / `spread` (illustrative route from the earlier lesion to the heart; arm or leg chain) / `fatty` / `inflamed` (the organ's colour moves toward the condition; liver, pancreas, stomach, intestines, spleen) |
| `body_label` | text pinned to the region (default: the region's name) |
| `card_type` | `none` / `lesion` / `microscopic` / `mechanism` / `anatomy` / `treatment` / `test` |
| `card_ref` | id of an illustration in the library (needed for a card) |
| `card_prompt` | what to generate when `card_ref` is new |
| `card_at` | seconds into the beat when the card appears (default 0.8) |

Checked before any frame is drawn (`bodymap.validate`): unknown region/scale/focus/effect, a `spread` without an earlier `skin_layers`, `organ` focus on a non-organ, condition effects on the wrong organ,
a card with no `card_ref`/`card_prompt`. A card whose picture is not in the library is left out and reported; the rest of the shot still renders. Invalid beats fall back through the existing 3D fallback.
Effects are illustrations: the route is labelled "Illustrative route: not literal anatomy", cards "ILLUSTRATION" + "AI-generated medical illustration, not a clinical photograph".

## Illustration library
`~/HealthCinemaTools/illustrations/` (`HEALTH_CINEMA_ILLUSTRATION_DIR` overrides): `index.json` + pictures; each entry has id, topic, view, kind, prompt, style (`holo-medical-v1`), source (flow / supplied / placeholder), sha256.
A placeholder is never used in a final render. Before generating, list what a CSV needs (no credit spent):

    python3 -m health_cinema.bodymap_flow --csv scenes.csv            # what is missing
    python3 -m health_cinema.bodymap_flow --csv scenes.csv --go --account <id>   # one Flow image per missing id

One image per id, never a variation; an id already in the library is reused. New topics still cost one generation each; reuse only saves repeats.
