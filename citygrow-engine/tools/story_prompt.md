You are writing a story CSV for a "City Timelapse" video: a low-poly 3D model of one real city growing over the centuries,
on its real ground, with music only (no narration). On screen: the year (bottom right), the population (top right), the era's
flag and name (bottom left), a big serif title card for the most important eras, and one or two short captions per era.

City: <WRITE THE CITY HERE>
Time span: <e.g. "founding to today", or "800 to 1700">

Write ONLY a CSV (no commentary) with exactly this header:

row,year,until,era_name,flag,population,caption,title,kicker,style,shot,focus,hold,kind,radius,weight,extra

Rows (the `row` column says which kind):

1. One `plan` row:
   - era_name = the city's name as the video should show it (e.g. "Rome")
   - focus = "lon,lat" of the historic centre (decimal degrees, longitude first). The map covers 8 km around this point.
   - extra = JSON: {"world":"<lowercase_id>","seed":7}   (optional "size": 6–12 km, "music": one of ascending_the_vale,
     echoes_of_time_v2, despair_and_triumph, lost_frontier, long_note_four, dark_fog, interloper, stormfront,
     "climate": "arid" for a desert city, "temperate" for a green one: say it for any city that is NOT on the Arabian
     Peninsula or in North Africa, because only those are recognised as desert on their own, e.g. Jodhpur, Phoenix, Samarkand)

2. 3–7 `district` rows: the places the city started from and grew out of, in the order they were settled.
   - year = when it was settled; focus = "lon,lat"; era_name = its name; weight = 0.6–1.5 (bigger pulls more growth)

3. 8–15 `era` rows, in time order (each year later than the one before):
   - year: "-753" or "753 BC" or "AD 540" or "1453"
   - era_name: short period name in English ("Roman Republic", "Ottoman Istanbul")
   - flag: a simple flag spec drawn by the app:
       "h:#c1,#c2,#c3" horizontal stripes, "v:#c1,#c2,#c3" vertical stripes, "plain:#bg", "cross:#bg,#fg" (Nordic cross),
       "george:#bg,#fg" (centred cross), "saltire:#bg,#fg", "crescent:#bg,#fg", "disc:#bg,#fg";
       add "|TEXT" to letter a symbol in the middle, e.g. "plain:#7b1e24,#e9c46a|SPQR"
   - population: the best historical estimate as a plain number (e.g. 450000), for the built-up area that fits inside the map,
     not a whole metropolitan region. It drives how many houses stand.
   - caption: ONE sentence, 8–20 words, what changed in this era. Plain, factual.
   - title + kicker: ONLY for the 2–4 biggest moments (e.g. title "THE GOLDEN AGE", kicker "Eastern Rome"); else leave empty
   - style: house look: ancient, medieval, ottoman, nordic, early_modern, industrial, modern, south_asian (flat-roofed brick and mud) or south_asian_modern
   - leave shot, focus, hold empty unless you have a reason (the camera picks its own moves; a new landmark gets a close orbit)

4. 6–14 `landmark` rows: the buildings that make this city recognisable.
   - year = when it was completed and open (not when it was planned or begun); until = when destroyed (empty if it still stands);
     era_name = its name; focus = "lon,lat" of the building's own centre on land (exact to about 50 m; not the district's centre)
   - kind: dome_church, mosque, church, cathedral, temple, forum, market, amphitheatre, hippodrome, castle, palace, station, tower,
     lighthouse, column, skyscraper (its size is the real height in metres: Burj Khalifa 828; 250 m and above is drawn as a tapering tower with a spire), or a path kind: wall, harbour, aqueduct, bridge
   - extra JSON: {"size": metres, "rot": degrees the long side is turned (0 = east–west), "minarets": n,
     "color": "marble"|"stone"|"brick"|"#hex", "roof": "terracotta"|"slate"|"lead"|"#hex", "dome": "lead"|"gold"}
   - what "size" means depends on the kind, and it must be the REAL figure from a reliable source:
       HEIGHT in metres:  skyscraper, tower, lighthouse, column      (Burj Khalifa 828, Eiffel Tower 330, Pharos 100)
       LENGTH of the long side in metres:  every other kind          (Colosseum 188, Hagia Sophia 82, Dubai Mall 300)
     a skyscraper under 250 m is drawn as a box and at 250 m or more as a stepped, tapering tower with a spire; if its
     size is smaller than the ordinary buildings around it, it will not be seen, so never write a width or a guess.
   - path kinds give the line as extra {"path": [[lon,lat],[lon,lat],...], "height": metres} and leave focus empty

5. 0–3 `event` rows: fires, sieges, earthquakes that destroyed part of the city.
   - year, focus = "lon,lat" of the centre, radius = metres (300–1500), kind = fire|siege|quake|flood, caption = one sentence,
     extra {"regrow": years until rebuilt}

Rules:
- Use real coordinates. Every district, landmark and event must be within half of the plan's size (default 8 km: 4 km) of the
  plan's focus, on land (not in the sea or a lake).
- Populations must be real estimates for that city and year; let them fall when the city shrank.
- Keep captions short; never more than 25 words.
- Quote any cell that contains a comma. Escape quotes inside JSON by doubling them (""like this"").
- Never invent a number. If you do not know a landmark's real height or length, leave that landmark out.
- Before you answer, check: the header is exact; every `year` is later than the one above it within its row kind; each landmark
  stands in an era that shows it (its year is not before the city exists); every skyscraper/tower size is a height in metres; every
  focus is "lon,lat" with longitude first; no cell with a comma is unquoted.
