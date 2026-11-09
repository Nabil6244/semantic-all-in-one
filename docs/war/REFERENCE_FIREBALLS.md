# Reference study: "GIANT FIREBALLS ERUPT Across Russia… Ukraine Is Hunting EVERYTHING" (Paradox News)

Studied 2026-11-10. 26:07, 1280x720, 25 fps. Method: 345 detected cuts, one frame every 4 s (16 contact sheets),
two map stretches at 4 fps (0:04-0:10, 3:19-3:25), local Whisper transcript matched to the pictures.
Patterns to adopt, not a look to copy.

## 1. What the film is made of (screen share, from the 1-per-4-s frames)

| Part | Share | What it looks like |
|---|---|---|
| Generic military footage | ~50 % | Clean b-roll: soldiers in trenches and snow, tanks / BMPs / trucks on winter roads, jets (Su-34, Tornado, Typhoon), air-defence trucks, drones being prepared, power lines, trains, Moscow metro, airports. No anchors, no other channel's captions or logos. |
| Maps | ~15 % | Tilted 3D political map (Ukraine blue, Russia red, others yellow) or a beige "position approximate" paper map |
| Article screenshots | ~10 % | The outlet's page, headline highlighted in yellow, outlet + date chip under it, blurred footage behind |
| Big numbers | ~8 % | Huge yellow figure + white label + red source chip over darkened footage ("250+ KM", "~140 IN SERVICE vs 43 DESTROYED", "73,451 CIVILIAN CASUALTIES") |
| Speaker cards | ~7 % | Portrait in a glowing ring, "AS REPORTED" chip, the quote typed word by word, name / role / date |
| Icon chains | ~5 % | Dark screen, a row of orange ring icons joined by a line, built one per spoken word ("THE PLANT -> EXPLOSIVES -> ROCKET FUEL -> GUNPOWDER") |
| Title words | ~5 % | One or two huge white words over footage ("STORM SHADOW", "RUSSIA WAS WRONG", "IRREPLACEABLE", "ROUND THREE"), small yellow sub-line |

Shots: median 3.0 s, mean 4.5 s. Footage cuts are 2-4 s; only maps, articles, number and speaker cards hold longer (12 s+).

## 2. How generic footage is used (the main lesson)

The footage is almost never the event. The facts are carried by graphics; the footage only shows the KIND of thing the sentence
is about:

| Narration | Picture |
|---|---|
| "Ukraine is on the hunt…" | a soldier in a trench (any) |
| "Ukraine is switching its focus to the industrial belly…", "Russia can no longer handle…" | jets on a snowy airfield, artillery range, tanks in snow, soldiers in snow |
| "Storm Shadow is an Anglo-French air-launched cruise missile…" | Tornado / Typhoon jets in flight, refuelling, cockpit; title word STORM SHADOW; big number 250+ KM |
| "a Russian chemical plant in Bryansk… explosives, rocket fuel, gunpowder" | icon chain built word by word (no plant footage) |
| "a pair of Russian Su-34 fighter bombers… Neptune" | Su-34s in flight / on the runway (archive), article page, big number ~140 vs 43 |
| "Moscow's airports were closed…" | a Moscow airport at night, the Euronews article, beige map with VNUKOVO / ZHUKOVSKY / DOMODEDOVO |
| "Putin's own aircraft… diverted" | Putin at his desk (any meeting), chip "PUTIN'S PLANE DIVERTED" |
| "Peskov told reporters…" | Peskov speaker card with the quote typed |

Rules seen:
1. Footage = the sentence's kind of subject (soldiers / jets / tanks / air defence / trains / power lines / a city), from a pool of
   clean b-roll that is reused across the film (the same winter tank column appears several times).
2. A named person = archive footage of that person (Putin at a desk) or a speaker card. Never a news-anchor shot.
3. Named facts (places, numbers, dates, outlets) never rely on footage: map, article page, big number, icon chain.
4. Generic footage carries text: caption boxes ("A FIRESTORM AGAINST TARGETS PUTIN BELIEVED UNTOUCHABLE", "HUNDREDS OF THOUSANDS
   LEFT WITHOUT ELECTRICITY", "PROTECT MOSCOW OR PROTECT LIPETSK"), title words, big numbers on it darkened.
5. Footage is clean: no burned captions, no channel logos, no anchors, no phone-video bars. Winter grading dominates.

## 3. Map animation (what our maps are missing)

Seen at 4 fps (0:04-0:10 and 3:19-3:25):
- A tilted 3D map with extruded country names ("RUSSIA", "UKRAINE" in 3D type with a shadow) that drifts and zooms slowly the
  whole time.
- **Missiles fly**: white 3D missile models leave Ukraine one after another and travel in a straight line to each target; a red tag
  rides along ("STORM SHADOW (REPORTED)").
- **Impacts**: each target gets a double white ring around a red dot that pulses / expands; an orange fireball flash at the moment of
  impact; several targets light up in sequence ("strikes across Russia").
- Labels: black tags with white text for places ("OREL · PROTON", "YELETS · ENERGIYA"), typed in; a yellow date/title chip top-left
  typed letter by letter ("OCTOBER 23-25 · ORYOL AND LIPETSK REGIONS"); "MAP ILLUSTRATION · SIMULATION" top-right.
- Supply routes: a thick white curved arrow drawn from origin to destination (London -> Kyiv).
- Site maps: a beige paper map, "POSITION APPROXIMATE", black label tags, slow push-in.

Our engine already has: strike arcs with a projectile head, impact flash and shock ring (maps_tactical `strike` routes),
advance arrows, pins, rings, explosion / swarm glyphs, date chips. Why none showed in the Moskva film: a strike route needs two
named places (from -> to). "Two Neptune missiles struck the ship south of Odesa" has one place and a target with no map position
(a ship), so no route was drawn and the map stayed still. Missing pieces: a strike from the actor's side when only the target is
named; a target that is a ship (sea point near the named place); several missiles in sequence; the missile model riding the arc
instead of a dot; pulsing target rings; the typed title chip.

## 4. Gaps in our War engine, in order of effect

1. **Generic footage mode** (biggest): search clean b-roll by KIND for scenes without a named subject ("Ukrainian soldiers winter
   trench b-roll", "Su-34 jets flying", "Russian air defence Pantsir truck") and prefer military / stock channels over news
   reports; reject anchors, burned captions and logos; cut generic footage every 2-4 s; reuse the film's own pool. Flow can fill a
   kind with no clip.
2. **Strike animation on the map** whenever the sentence has a strike verb: from the actor's side to the target; ships and bases as
   targets; missiles in sequence; pulsing rings + fireball.
3. **Text on footage instead of maps for no-place sentences**: caption box / title word / big number over generic footage (our
   broadcast.py has these) instead of a country-filler map.
4. Keep: article pages, speaker cards, big numbers, icon chains (kit_icons) already match this reference; use them for named facts.
