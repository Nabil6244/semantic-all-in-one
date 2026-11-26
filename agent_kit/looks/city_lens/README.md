# city_lens — urban-planning documentaries ("Why X has America's worst downtown")

A city explained from above: real satellite pictures darkened to grey with one glowing orange outline on the thing
being talked about, dark navy line maps (counties, rail, beltways), a warm paper ground for infographics (tables,
bars, timelines, feedback loops, newspaper and zoning-code cards), big orange money numbers, a 3D grey block city for
"from above" shots, and real street/drone/archive footage of THAT city. Learned from studying a city-planning channel
(16-minute videos, about 5 hard cuts a minute but something new is added to the frame every 2-3 s); its own code.

## The one rule: the map is the story, and it builds up
- **Every place named is shown on its real map**: call `satellite` (downtown 15-16, a metro 11-12) or `map` for the box,
  then draw on it in frame pixels with `C.geoPath(proj, [[lon, lat], ...])` / `K.lonlat`. Never a generic city.
- **One orange outline = "the thing"** (the freeway loop, the downtown, the district). It comes back in every map scene
  in the same place, so the viewer always knows where they are. Other things get other colours: red = the problem
  (parking, congestion, lost buildings), green = the fix (park, lid, river trail), blue = water, yellow = roads/rail on
  night maps.
- **The causes stack up**: when the video names its causes one by one (river, parking, freeways, anchors…), add a tile
  to `C.layerStack(items, shown)` top right each time and keep it on every later map scene. The payoff scene shows the
  whole stack as an exploded 3D/isometric pile.
- **Different picture for every sentence, same world**: satellite wide → push to the junction (hotspot) → paper card
  with the number → footage of the street → back to the map with one more layer.

## Building blocks
| file | what it gives you |
|---|---|
| `look.css` | `CL Serif` (italic Cormorant: place names, years, titles) and `CL Sans` (Inter: labels, numbers). Classes `.title .year .place .kicker .label .big .chip(.orange/.red/.green) .card .caption .hl .sat .source .grain .vignette .flash`; `<body class="paper">` for the paper ground |
| `palette.js` | `P` (night, paper, card, ink, orange, glow, yellow, red, green, blue, ochre, block…) and `shade` |
| `city.js` (`C`) | grounds `sat nightGround paperGround`; map marks `blob glowLoop glowLine route river zone pin placeLabel dots scatter ring hotspot layerStack geoPath geoSmooth smoothPath lonlat`; type `chip bigNumber yearTag title sourceLine text`; paper `docCard table bars columns timeline cycle iconRow crossSection`; helpers `defs draw pop rise fade` |
| `city3d.js` | `makeCity(canvas, {seed, blocks, towers})` → `render({cam, rise, gone, corridor, ring})`, `screen(x, z)` |
| `examples/` | a satellite loop scene, a paper card scene, a 3D block city. Style only |

- `C.defs()` first in every `<svg>`. Put the layer stack, big numbers and source line in `svg#tags` (outside the
  moving camera) so a camera push never cuts them.
- Satellite scenes: `s.innerHTML = C.defs() + C.sat('dt') + ...` and move `#cam` (slow push 1.0 → 1.12 + drift).
- 3D city: a `<canvas id="c3" width="1920" height="1080">` inside `#h`, `const C3 = await makeCity(c3, {...})` at the
  top, then `C3.render({...})` in `renderAt`. `#h` sits above `svg#s`, so labels go in `svg#tags`, placed with `C3.screen(x, z)`.

## Scene kinds to mix (never the same kind twice in a row)
1. **Satellite map**: the city from above, grey; the orange loop draws on, pins pop with black chips, red dots fill
   the parking lots, a green zone for the park, the layer stack top right. Slow push in.
2. **Night line map**: navy ground, counties as ochre shapes or thin outlines, rail/roads as yellow lines drawing on,
   italic place names, a big number top right.
3. **Paper card**: on the paper ground, one card: a comparison `table`, `bars`/`columns`, a `timeline` ruler with
   years, a `cycle` (cause loops back to itself), a `docCard` (newspaper, zoning code, study) with the key line
   highlighted yellow, an `iconRow` ("4 of the 10 largest").
4. **Big number**: a money or size number counting up (`bigNumber` + `K.countUp`), with its chip ("for one block").
5. **Cross-section / 3D**: `crossSection` (river bottoms vs bluff downtown) or the `makeCity` block city with a red
   elevated freeway `corridor` cutting through, buildings `gone` for parking, a green lid, a glowing `ring`.
6. **Footage (often)**: real drone, street and archive footage of THAT city between the maps: one clip about
   every 20 s, 25-40 % of the runtime (`check_plan` asks for it). Search with the city's name ("Houston freeway aerial",
   "Houston downtown drone", kind=wiki for archive); when the sentence names a thing (townhomes, a flood, a stadium) use
   footage of that thing, best in that city. Every clip gets an overlay: a `yearTag` on archive ("1957 / Intercity
   Freeway / Kansas City · October 1957"), a `placeLabel`, a `pin` or a `bigNumber`.

## The look
- Grounds: satellite grey (`.sat`), navy `#1e2431`, paper `#ecebe6`. One orange glow per frame, never two.
- Type: italic serif for places and titles, Inter for labels; labels are 1–4 words in black chips. Never a sentence of
  narration on screen; quotes only on a paper card.
- Small source line bottom left on every map, chart and document ("Imagery: Esri, Maxar", "Kansas City Star, 1957").

## Keep them watching
- Something added every 2–3 s inside a scene (a pin, a dot field, a new layer, a counter, a highlight), hooked on the
  spoken word with `K.when`. The camera always moves (slow push on maps, orbit on 3D).
- Open with the most surprising contrast: archive year tag → the old newspaper/ad → today's footage → the big number.
- Sound is automatic (`sound.json`): `join` lays this look's own calm bed (`sound/bed.opus`, made by `make_bed.py`)
  and matching ambience under the scenes (traffic under freeways, rain under floods, water under bayous and rivers, city
  hum under street footage; paper and night cards stay quiet). Pass only these effects, about one every 3-5 s:
  `whoosh` (map push, card entry), `tick` (pins, dots, counters), `paper` (a document lands), `hit` (a stamp or a big
  number). They are levelled for you; risers and booms are left out. Do not pass `music`.
