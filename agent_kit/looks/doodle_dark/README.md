# doodle_dark — how to make a Doodle Survival video

Day-by-day survival stories (zombie outbreak, end of the world) as flat 2D cartoon at night.
Everything on screen is drawn in SVG by you, scene by scene. No footage, no fixed sets.

## The one rule: follow the narration, new picture for every sentence
- Read the sentence, list every concrete thing it names (place, object, action, number, feeling), and draw exactly
  that. "On day 12 he found a radio in the attic" → `dayTag(12)`, a dusty attic drawn now, Scout crouching, a radio in his
  hand, a light shaft from the roof window. The next sentence gets its own new picture.
- When the story stays in one place for several sentences, keep that place's look (same colours, same objects in the
  same spots) but change the shot: wide → close-up → object insert → reaction face. Never reuse a still frame.
- Something changes every 2–3 s: a cut, a camera push, a pose change, an object appearing, a light flicker.
- Inside a scene, cut to a second shot on the key word: an object insert (the bolt sliding, the can label), a reaction
  close-up, or a wide → close change. Most 3–5 s scenes should have 2–3 shots.
- Never an empty room: every place gets wall texture, floor, 3+ props, contact shadows, and one blurred foreground shape.

## Building blocks
| file | what it gives you |
|---|---|
| `look.css` | colours, Anton display font (`.title`, `.display`), `.kicker .label .small .card .chip .caption .grain .vignette .flash` |
| `palette.js` | `P` colours for SVG (night wall/floor/window, zombie colours) |
| `hero.js` | `hero(t, { face, pose, item, x, y, scale, facing, talking, closeup, light })` — Scout, the mascot |
| `light.js` | `defs()` (put once in each `<svg>`), `shaft()` light beams, `glow()`, `dust()` floating motes, `treeline()`, `R()` rect, `lin()/rad()` gradients, `dayTag(n)`; detail: `wallTex()`, `floorBoards()`, `door()`, `contact()` shadows, `fg()` blurred foreground, `frame() clock() plant() rug() clutter()` |
| `places.js` | three EXAMPLE places (farm dusk, bedroom night, pantry). Style reference only — do not reuse them as sets |

### Scout
- faces: calm, scared, panic, worried, relieved, angry, sad, thinking, sleeping (blinks by himself; `talking:true` moves the mouth)
- poses: stand, walk, run, sneak, crouch, sit, hold, point, handsup, push, peek, eat, cower, lie
- items in his right hand: can, bat, torch, radio, phone, knife, axe (anything else: draw it yourself at his hand)
- `SPEED.walk / run / sneak` px per second so feet don't slide when you move `x`
- `light`: 'night' | 'moon' | 'dusk' | 'warm' | 'day' — tint him with the place's light, always
- wide shots: small (scale 0.5–0.8); emotion beats: `closeup:true`, scale 2.5–4, centred
- `joints: {...}` overrides any joint angle for a one-off pose
- `heroAt(t, [{at, pose, face, item, x, facing}...], base)` — key-frame him on spoken words: poses blend with a small
  anticipation dip, x glides between keys. Use it instead of hard pose switches.
- he casts a soft floor shadow (`shadow:false` when lying in bed); scarf tail and hat bobble swing on their own

## The look (from studying the reference)
- **Minimal flat shapes, muted colours.** Few shapes per object, soft gradients, ink outlines 4–6 px. Not detailed art.
- **Light makes it expensive.** Every place has one key light: moon through a window, a bulb cone, a torch beam, fire
  glow, low dusk sun. Add `shaft()` + `dust()` inside it, `glow()` on lamps and windows, haze near the horizon.
- **Dim palette.** Night navy `#1e2638 → #141a28`, dusk grey-violet sky into warm horizon, rooms grey `#2a2d33`.
  Warm accents only from lights (`#ffd27a`), danger red only for threats.
- `dayTag(n)` top-left on every scene once a day has been said.

## Explainer cards (about half the scenes)
One system for all of them: near-black `#0d0f14` with a faint dot grid + grain, thin amber line icons (`stroke:#e7b45a`,
3–4 px, drawn on with stroke-dash), small widely spaced CAPS labels in off-white under each icon. Ideas:
- icon row (2–4 icons pop in one by one: "DIRTY HANDS / SPOILED FOOD / STRESS")
- rule card: icon in a circle, kicker "RULE 1", a 2-line rule
- metaphor diagram: a balance scale tipping, a chain of cause → effect arrows
- blueprint cut-away: thin-line house section, tiny figures inside, a big amber counter top-left, dots for the horde
- object close-up through a camera viewfinder (REC corners, "IMG_2096 · FLASH") with a label
- TV insert: old TV, red LIVE tag, red lower-third headline; radio close-up with a signal line
- tally marks filling a wall on day changes; a timer bottom-right; pointer labels in a scene ("TOO FAST")

## Threats
Zombies: draw them with `hero()`-style shapes in grey-green (`P.zSkin`, `P.zCloth`, red eyes `P.zEye`), shambling, in rows
with fog between rows for a horde. Bangs on doors: shake the door + dust puff + an impact sound in `join`.
