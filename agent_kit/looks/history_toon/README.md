# history_toon — illustrated cartoon history documentaries

A history story told with flat 2D cartoon art: people with big round white faces in the clothes of their era,
painted places (airfields, barracks, offices, villages, seas), and paper props that fill themselves in (forms,
maps, calendars, scrolls, cards, stamps). Everything is drawn in SVG by you. No footage, no photos, no fixed sets.
Learned from studying an illustrated WWII history video (9:36, about 14 cuts a minute); this pack is its own code
and art, not a copy.

## The one rule: every video is new
- **Design a new cast for each video** from its script: who are the main people, what era, what they wear.
  Start from `OUTFITS` but change the colours, hats and extras (headband, scarf, glasses, beard, cape, badge) so
  this film's people look like this story's people (Roman soldiers, Ottoman clerks, 1920s miners, Viking farmers).
  Write the cast once in the film's `common.js` (`export const ENA = {...OUTFITS.pilot, headband:true}`) and use it in
  every scene, so the main character keeps one look through the whole film.
- **Draw every place new from the sentence.** There is no place library. "He was locked in a barracks near Fukuoka"
  → that barracks drawn now: plank walls, a row of beds, a hanging lamp, a guard at the door. The examples only
  show the style.
- **New picture for every sentence.** When the story stays in one place, keep that place's look but change the shot:
  wide → close-up face (`closeup:true`) → object insert (the form, the letter) → reaction.

## Building blocks
| file | what it gives you |
|---|---|
| `look.css` | colours, `HT Display` (heavy rounded caps) and `HT Hand` (handwriting) fonts, `.title .kicker .label .hand .card .chip .caption .grain .vignette .flash` |
| `palette.js` | `P` colours (paper, ink, red, olive, navy, sea, sky, wood...) and `shade(hex, amt)` |
| `person.js` | `person(t, {outfit, face, pose, x, y, scale, facing, talking, closeup, look, hold, seed})`, `personAt(t, keys, base)` key-framed on words, `OUTFITS`, `FACES`, `POSES` |
| `props.js` | sets: `sky cloud hills trees ground sea puff plankWall floorBoards windowFrame lamp desk crate barrel deskTop`; paper: `paperForm penHand stamp notebook`; maps: `mapSea land zone pin arrow ring`; tags: `dateTag counterTag banner scroll calendar card nameTag pointLabel plate`; explainers: `chalkboard chalkText tally balance thought statusPanel poster`; vehicles: `plane ship`; helpers `defs draw pop rise text rect` |
| `examples/` | a field scene, a form being filled in, a map. Style reference only |

- Put `H.defs()` first in every `<svg>` (it resets ids so they stay the same each frame).
- Keep `dateTag` / `counterTag` / `nameTag` in a second `<svg>` OUTSIDE the moving camera div, so the zoom never cuts them.
- faces: calm, happy, smile, scared, shock, worried, sweat, sad, cry, angry, thinking, determined, smug, sleep
- poses: stand, walk, wave, salute, point, hold, armsup, shrug, think, fist, sit, bow, hug, write (`joints:[...]` for one-offs;
  sit/write put the hips at y −128 — draw the chair seat there). `SPEED.walk` px/s so feet don't slide.

## The look
- Muted printed-paper colours: teal-green backgrounds, cream paper, olive and navy uniforms, one red accent.
- Ink outlines 4–5 px on everything, flat fills, one soft shade line. Faint grain + vignette on top.
- Text is short and in-world: a stamp ("RETURNED"), a banner ("22ND UNIT"), a form value written by hand, a label
  on a pin. Never a sentence of narration on screen.

## Scene kinds to mix (never the same kind twice in a row)
1. **Story shot**: the cast in a drawn place doing what the sentence says (2–3 shots per scene).
2. **Paper insert**: a form/letter/notebook filled by a pen hand, word by word on the narration; a stamp slams at the end.
3. **Map**: paper map, red hatched zone growing, pins popping, red arrows drawing, a ring around the key place, date tag.
4. **Cards**: a row of character cards; one lifts and gets a gold edge; stamps ("SURVIVED", "?") on the others.
5. **Object metaphor**: a balance scale tipping, a calendar with the day circled, tally marks on a chalkboard,
   a thought bubble with the fear inside, a status panel with bars dropping, a "type of person" plate.
6. **Title**: a scroll unrolling with a place or unit name, or a red banner over a wide shot.

## Keep them watching
- A cut or a new element every 2–3 s; every scene has 2+ hook moves on spoken words (`K.when`): pop, stamp, ring,
  arrow, punch, shake. Something written appears exactly when it is said.
- Faces carry the emotion: change the face on the word (`personAt` keys), sweat drops when nervous, shock on reveals.
- Camera always drifting slowly (`K.drift`), a punch on the reveal word.
- Sound: a pen scratch/ui tick while writing, an impact on stamps, a whoosh on banners and scroll unrolls, a calm
  period-feeling music bed at about −20 dB.
