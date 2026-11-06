# New 3D in every video — plan (2026-11-06)

Status: plan only. Nothing below is built yet.

## Why the 3D repeats today (measured on the S27 leaks film, out/s27_leaks)

| What | Today | Why it repeats |
|---|---|---|
| 3D share | 48 of 59 shots (≈80 %) | only 4 stock clips and 7 cards were planned, so 3D fills everything |
| Camera moves | 11 used; orbit ×7, island/flip/monolith/screen ×5 each | 14 fixed moves in `planner.MOVES`; the director only picks a name |
| Set | 37 of 48 on the same `daylight` backdrop; rooms in 5 | `review.ROOMS` is 3 bright rooms; rooms only appear in lineups |
| Phone | one code-built phone | `assets/models/phones/` was empty (filled 2026-11-06, see below) |
| Lighting / colour | one light rig; colour never set per shot | no light or colour choice in the shot at all |
| Across videos | the same rules + same script words → the same film | no seed per video, no memory of what earlier videos used |

`balance.py` only stops one look three times in a row. It cannot invent anything new.

## Step 0 — real phone models (done 2026-11-06)

`whatif-engine/assets/models/phones/` now holds 14 GLBs, each with a `.LICENSE.txt`:
galaxy_s27_ultra / s25_ultra / s24_ultra, iphone_16_pro / 17_pro / 17_pro_max / 18_pro_max (+ `_b`, `_black`),
iphone_duo, iphone_duo_fold_night_sky / star_white (animated), pixel_10_pro (Pixel 9 low poly), oneplus_13 (OnePlus 12).
- CC-BY ones need a credit line in the video description (text is in each `.LICENSE.txt`).
- The three Sketchfab Standard ones are git-ignored (allowed in videos, not to be shared).
- `iphone_duo_nc.glb` (zhe_kan, CC-BY-NC-SA) is non-commercial only. It is added at your request. The `_nc` suffix keeps
  it out of automatic picks (Step 1): it is used only when you choose it for a video that earns nothing.

## Step 1 — use every model, not only the film's phone

- Add the new ids to `whatif-engine/data/phones.json` (galaxy_s24_ultra, iphone_18_pro_max, iphone_duo, iphone_duo_fold).
- Variants: when a phone has more than one file (`iphone_18_pro_max`, `_b`, `_black`), the video's seed picks one.
  A file ending in `_nc` (non-commercial licence) is never picked automatically; a Settings switch "non-commercial video"
  allows it.
- Comparison shots ("700 more than the S26 Ultra", "the S27 Pro gets 3x") load the other phone's real model
  (closest one we have: S26 → S25 Ultra model) instead of a recoloured copy of the hero phone.
- Fold models play their own fold animation on "fold" sentences.
- After the render, write `credits.txt` next to the mp4 with the credit line of every CC-BY model the film used.

## Step 2 — shots built from parts, not picked from a list

A 3D shot becomes a combination instead of one of 14 names:

| Part | Choices (start) |
|---|---|
| Camera path | the 14 moves become path *families*; start/end angle, distance, height, roll and speed are drawn from ranges by the seed |
| Framing | wide, medium, close, macro, low hero, top-down, edge-on |
| Set | daylight, gallery, loft, terrace, desk, workbench, dark studio, coloured wash, glass plinth, water/reflection floor |
| Light | soft day, hard rim, neon edge, sunset window, top spot, studio three-point |
| Colour | the phone's real finishes (one per film, from the preset), plus accent colour of the set |
| Props | cable + charger, S Pen, notebook, coffee cup, receipt/price tag, magnetic puck, lens cap |
| Motion of the phone | still, slow turn, float, drop-in, slide-in, stand-up from flat |

Even 7 framings × 10 sets × 6 lights × 14 path families gives about 5,900 distinct shots before the angle ranges.

## Step 3 — the sentence picks the set and props (no AI call)

Plain keyword rules, the same way `director.py` already reads figures:

| The narration talks about | Set / props / framing |
|---|---|
| battery, mAh, charging, watts | desk or workbench, cable + charger, magnetic puck for wireless; macro on the port |
| camera, telephoto, megapixel, lens | macro on the bar, dark studio + rim light, lens close-ups |
| design, back, floating rings, island | top-down and low hero, glass plinth, soft day |
| privacy display | café/desk, a second phone or a person's shoulder at the side, screen-angle move |
| price, cost, dollars | receipt/price tag prop, shop-like gallery |
| S Pen | desk + notebook, the pen sliding out |
| launch, unveil, January | stage-like dark set with a top spot |
| glass, scratches, Gorilla | macro across the screen, hard light raking the glass |

## Step 4 — every video different from the last ones

- Each film gets its own seed (from the voice-over file + date), so the same rule never gives the same numbers twice.
- A small history file per project/channel (`state_dir/3d_history.json`) keeps a fingerprint of every 3D shot
  (path family + framing + set + light). A new film avoids the fingerprints of the last 5 films; when it must reuse one, it
  changes at least two parts.
- Inside one film: no fingerprint twice, no path family more than about 10 % of the 3D shots, no set twice in a row.
- Same idea as the Health Cinema uniqueness check, so the code can be shared.

## Step 5 — less 3D, more of everything else

- Target ≤ 45 % 3D in a Review film. The rest: real footage (stock now; the News route's YouTube clips only with your OK),
  cards, charts, flat-phone comparisons.
- `balance.py` gets the share limit; 3D is kept for the sentences that are about the phone's body (design, camera, colours).

## Step 6 — tests (synthetic, no network, no render)

- Same script, two seeds: under 20 % of 3D fingerprints shared.
- History: film 2 shares no fingerprint with film 1.
- One film: no fingerprint twice; no path family over its share; 3D share ≤ 45 %.
- Keyword rules: a battery sentence gets the charger set, a price sentence gets the price prop.
- Credits: a film that used `galaxy_s27_ultra.glb` writes its credit line.

## Cost

No AI calls and no extra render time per frame: the parts are chosen while planning. New props and sets are built once
(code-built, like the existing rooms), never per video.

## Order

1 → 2 → 4 → 3 → 5 → 6 (tests written with each step). Step 1 alone already changes every phone shot; Steps 2 and 4 are
what make each video new.
